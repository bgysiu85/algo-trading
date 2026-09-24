#!/usr/bin/env python3
r"""H-X1 (W05-0003, `docs/research/REGISTERED_10sec.md` sections 5.1 and 7) --
T1 (10-second confirmation trigger) against B0 (the registered resting stop,
on seconds), full in-sample population, 446 sessions.

    python -m strategy.orb.tensec_hx1 --jobs 8
    python -m strategy.orb.tensec_hx1 --from-csv   # rescore only, skip resim

PRECONDITION: G2 (B0 parity) has PASSED (board W05-0003 subitems 4/9/10/11,
all Done, 2026-09-24). Nothing here is re-checked against that; it is the
board's job, not this module's.

WHAT THIS DOES, EXACTLY
------------------------
Re-simulates BOTH arms -- `strategy.orb.tensec_engine.b0_trade` and
`.t1_trade` -- from the primary ORB cell's published minute-bar ledger
(`var/cache/orb_sip/trades/`), on 1-second bars, for every one of the 7,239
in-sample primary-cell trades (holdout excluded, section 2). Side,
`or_high`/`or_low` and `r` come from the ledger and are never recomputed
here (section 2) -- only the entry/exit is built at second resolution, for
both arms, in the SAME pass over the archive (one read per symbol-day,
shared between B0 and T1, rather than G2's B0-only pass).

WHAT THIS SCORES -- and what it does NOT
------------------------------------------
Section 5.1 (H-X1's own controls) in full:
  1. paired delta, both denominators (per-trade, per-symbol-day)
  2. drop-top-N (N=1,3,5) on the delta, by symbol
  3. random-removal control, 2,000 draws, seed 20260916
  4. decomposition: abstention part, price part, confirmation premium,
     entry delay, entry-minute stop-outs avoided, top-50 trades kept

Section 7's criteria 1-6 (the pass bar), read on T1's own kept book, BASE
friction -- EXCEPT the section 4 fill check, which needs MBP-1 quote data
not pulled until step 6 (G4). A pass here is therefore provisional: "clears
every computable criterion, fill check pending" -- never "PASSES" outright.
A FAIL on any computable criterion is final regardless (section 7.1: the
whole sub-minute confirmation family retires on a fail, and the fill check
cannot turn a fail into a pass).

Reads:
  var/cache/orb_sip/trades/*.csv.gz              published minute-bar ledger
  E:\Databento\XNAS.ITCH\ohlcv-1s\<date>.dbn.zst  1-second prints (G1, landed)

Writes:
  var/cache/orb_sip/tensec_hx1_trades.csv.gz   per symbol-day, both arms
  var/reports/tensec_hx1_RESULT.txt            this module's report
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from common.breadth import RESAMPLES, SEED, cluster_bootstrap, pct
from strategy.orb import sip as S
from strategy.orb import sip_report as P
from strategy.orb import tensec_engine as E
from strategy.orb.tensec_pairs import primary_cell

TRADES_DEFAULT = Path("var/cache/orb_sip/trades")
OUT_DEFAULT = Path("var/reports/tensec_hx1_RESULT.txt")
CSV_DEFAULT = Path("var/cache/orb_sip/tensec_hx1_trades.csv.gz")
DATASET = "XNAS.ITCH"
SCHEMA = "ohlcv-1s"
LEVEL = "BASE"

DROPS = (1, 3, 5)
MIN_R_PER_TRADE = 0.05       # section 7 criterion 3
MIN_TRADES = 100             # section 7 criterion 4

RESULT_COLS = [
    "symbol", "date", "side", "r", "or_high", "or_low",
    "b0_why", "b0_entry_px", "b0_exit_px", "b0_exit_reason",
    "b0_entry_sec", "b0_exit_sec",
    "t1_why", "t1_entry_px", "t1_exit_px", "t1_exit_reason",
    "t1_entry_sec", "t1_exit_sec", "t1_trigger_sec",
]


def _one(args):
    archive, day, rows_json = args
    from common.dbn_io import read_dbn
    rows = pd.read_json(rows_json, orient="records")
    src = Path(archive) / DATASET / SCHEMA / f"{day}.dbn.zst"
    if not src.exists():
        return [dict(symbol=r.symbol, date=day, side=int(r.side), r=float(r.r),
                     or_high=float(r.or_high), or_low=float(r.or_low),
                     b0_why="NO_1S_FILE", b0_entry_px=np.nan, b0_exit_px=np.nan,
                     b0_exit_reason="", b0_entry_sec=np.nan, b0_exit_sec=np.nan,
                     t1_why="NO_1S_FILE", t1_entry_px=np.nan, t1_exit_px=np.nan,
                     t1_exit_reason="", t1_entry_sec=np.nan, t1_exit_sec=np.nan,
                     t1_trigger_sec=np.nan)
                for r in rows.itertuples()]
    bars = read_dbn(src)
    et = bars.index.tz_convert("America/New_York")
    sod_all = (et.hour * 3600 + et.minute * 60 + et.second).to_numpy()
    symbol_all = bars["symbol"].to_numpy()

    out = []
    for r in rows.itertuples():
        m = symbol_all == r.symbol
        sod = sod_all[m]
        order = np.argsort(sod, kind="stable")
        sod = sod[order]
        sub = bars[m].iloc[order]
        o = sub["open"].to_numpy(float)
        h = sub["high"].to_numpy(float)
        l = sub["low"].to_numpy(float)
        c = sub["close"].to_numpy(float)

        b0, b0_why = E.b0_trade(sod, o, h, l, c, int(r.side),
                                 float(r.or_high), float(r.or_low), float(r.r))
        t1, t1_why = E.t1_trade(sod, o, h, l, c, int(r.side),
                                 float(r.or_high), float(r.or_low), float(r.r))

        out.append(dict(
            symbol=r.symbol, date=day, side=int(r.side), r=float(r.r),
            or_high=float(r.or_high), or_low=float(r.or_low),
            b0_why=b0_why,
            b0_entry_px=np.nan if b0 is None else b0.entry_px,
            b0_exit_px=np.nan if b0 is None else b0.exit_px,
            b0_exit_reason="" if b0 is None else b0.exit_reason,
            b0_entry_sec=np.nan if b0 is None else b0.entry_sec,
            b0_exit_sec=np.nan if b0 is None else b0.exit_sec,
            t1_why=t1_why,
            t1_entry_px=np.nan if t1 is None else t1.entry_px,
            t1_exit_px=np.nan if t1 is None else t1.exit_px,
            t1_exit_reason="" if t1 is None else t1.exit_reason,
            t1_entry_sec=np.nan if t1 is None else t1.entry_sec,
            t1_exit_sec=np.nan if t1 is None else t1.exit_sec,
            t1_trigger_sec=np.nan if t1 is None else t1.trigger_sec,
        ))
    return out


def run(cell: pd.DataFrame, archive: Path, jobs: int, tmp: Path) -> pd.DataFrame:
    tmp.mkdir(parents=True, exist_ok=True)
    work = []
    for day, g in cell.groupby("date", sort=True):
        f = tmp / f"{day}.json"
        g[["symbol", "side", "r", "or_high", "or_low"]].to_json(f, orient="records")
        work.append((str(archive), day, str(f)))
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            parts = list(ex.map(_one, work))
    else:
        parts = [_one(w) for w in work]
    flat = [x for part in parts for x in part]
    return pd.DataFrame(flat, columns=RESULT_COLS)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

def _add_net_arm(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """`sip_report.add_net` on one arm's trades, columns renamed with prefix."""
    sub = pd.DataFrame({
        "entry_px": df[f"{prefix}_entry_px"],
        "exit_px": df[f"{prefix}_exit_px"],
        "exit_reason": df[f"{prefix}_exit_reason"],
        "side": df["side"],
        "r": df["r"],
    })
    sub = P.add_net(sub)
    return sub[f"R_{LEVEL}"], sub["gross_R"]


def drop_top(totals_by_symbol: dict[str, float], n: int) -> float:
    ranked = sorted(totals_by_symbol.values(), reverse=True)
    return float(sum(ranked[n:]))


def score(res: pd.DataFrame) -> dict:
    n_all = len(res)
    b0_ok = res[res["b0_why"] == "OK"].copy()
    n_b0_drop = n_all - len(b0_ok)

    b0_ok["b0_R"], b0_ok["b0_gross_R"] = _add_net_arm(b0_ok, "b0")

    t1_fired = b0_ok["t1_why"] == "OK"
    t1_ok = b0_ok[t1_fired].copy()
    t1_ok["t1_R"], t1_ok["t1_gross_R"] = _add_net_arm(t1_ok, "t1")

    b0_ok["t1_R"] = 0.0
    b0_ok.loc[t1_fired, "t1_R"] = t1_ok["t1_R"].to_numpy()
    b0_ok["delta_R"] = b0_ok["t1_R"] - b0_ok["b0_R"]

    n_b0 = len(b0_ok)
    n_t1 = len(t1_ok)
    n_skip = n_b0 - n_t1

    # ---- 5.1.1 paired delta, both denominators -----------------------
    per_trade_b0_mean = float(b0_ok["b0_R"].mean())
    per_trade_t1_mean = float(t1_ok["t1_R"].mean()) if n_t1 else float("nan")
    per_trade_delta = per_trade_t1_mean - per_trade_b0_mean

    per_symday_b0_mean = float(b0_ok["b0_R"].sum() / n_b0)
    per_symday_t1_mean = float(b0_ok["t1_R"].sum() / n_b0)
    per_symday_delta = per_symday_t1_mean - per_symday_b0_mean

    sign_agree = (np.sign(per_trade_delta) == np.sign(per_symday_delta)) or (
        per_trade_delta == 0 and per_symday_delta == 0)

    # ---- 5.1.2 drop-top-N on the delta, by symbol ---------------------
    delta_by_symbol = b0_ok.groupby("symbol")["delta_R"].sum().to_dict()
    drops_delta = {k: drop_top(delta_by_symbol, k) for k in DROPS}

    # ---- 5.1.3 random-removal control ---------------------------------
    b0_by_symbol_rows = b0_ok.groupby("symbol").indices  # symbol -> row positions
    b0_R_arr = b0_ok["b0_R"].to_numpy()
    symbols_arr = b0_ok["symbol"].to_numpy()
    rng = np.random.default_rng(SEED)
    ctrl_mean = np.empty(RESAMPLES)
    ctrl_drop5 = np.empty(RESAMPLES)
    idx_all = np.arange(n_b0)
    for i in range(RESAMPLES):
        removed = rng.choice(idx_all, size=n_skip, replace=False) if n_skip else np.array([], dtype=int)
        keep_mask = np.ones(n_b0, dtype=bool)
        keep_mask[removed] = False
        kept_R = b0_R_arr[keep_mask]
        kept_sym = symbols_arr[keep_mask]
        ctrl_mean[i] = float(kept_R.mean()) if kept_R.size else 0.0
        tot = pd.Series(kept_R).groupby(kept_sym).sum().to_dict()
        ctrl_drop5[i] = drop_top(tot, 5)
    ctrl_mean_p95 = float(np.percentile(ctrl_mean, 95))
    ctrl_drop5_p95 = float(np.percentile(ctrl_drop5, 95))
    beats_mean = per_trade_t1_mean > ctrl_mean_p95 if n_t1 else False
    t1_drop5_own = drop_top(t1_ok.groupby("symbol")["t1_R"].sum().to_dict(), 5) if n_t1 else float("nan")
    beats_drop5 = t1_drop5_own > ctrl_drop5_p95 if n_t1 else False

    # ---- 5.1.4 decomposition ------------------------------------------
    skipped = b0_ok[~t1_fired]
    abstention_part = float(skipped["b0_R"].sum())
    price_part = float((t1_ok["t1_R"] - t1_ok["b0_R"]).sum())

    level = np.where(t1_ok["side"] == 1, t1_ok["or_high"], t1_ok["or_low"])
    premium = (t1_ok["t1_entry_px"].to_numpy() - level) / t1_ok["r"].to_numpy()
    entry_delay = t1_ok["t1_entry_sec"].to_numpy() - t1_ok["b0_entry_sec"].to_numpy()

    same_min_stop = (b0_ok["b0_exit_reason"] == "stop") & (
        (b0_ok["b0_exit_sec"] // 60) == (b0_ok["b0_entry_sec"] // 60))
    n_entry_min_stopouts = int(same_min_stop.sum())
    avoided = same_min_stop & (
        (~t1_fired) | (
            (b0_ok["t1_exit_reason"] != "stop") |
            ((b0_ok["t1_exit_sec"] // 60) != (b0_ok["t1_entry_sec"] // 60))
        )
    )
    n_avoided = int(avoided.sum())

    top50_syms_days = b0_ok.assign(_r=b0_ok["b0_R"]).nlargest(50, "_r")
    n_top50_kept = int(top50_syms_days["t1_why"].eq("OK").sum())

    # ---- section 7, criteria 1-6, on T1's own kept book ----------------
    if n_t1:
        by_sym_t1 = t1_ok.groupby("symbol")["t1_R"].apply(list).to_dict()
        tot_t1 = {k: float(sum(v)) for k, v in by_sym_t1.items()}
        drop_t1 = {k: drop_top(tot_t1, k) for k in (1, 3, 5)}
        boot = cluster_bootstrap(by_sym_t1, RESAMPLES, SEED)
        boot_p = float(np.mean(np.asarray(boot["totals"]) > 0))
        mean_r_t1 = per_trade_t1_mean
        n_trades_t1 = n_t1
        split_date = t1_ok["date"].sort_values().iloc[n_t1 // 2]
        half1 = float(t1_ok[t1_ok["date"] < split_date]["t1_R"].sum())
        half2 = float(t1_ok[t1_ok["date"] >= split_date]["t1_R"].sum())
        long_r = float(t1_ok[t1_ok["side"] == 1]["t1_R"].sum())
        short_r = float(t1_ok[t1_ok["side"] == -1]["t1_R"].sum())
    else:
        drop_t1 = {k: 0.0 for k in (1, 3, 5)}
        boot_p = 0.0
        mean_r_t1 = float("nan")
        n_trades_t1 = 0
        half1 = half2 = long_r = short_r = 0.0

    crit1 = drop_t1[3] > 0 and drop_t1[5] > 0
    crit2 = boot_p >= 0.95
    crit3 = (mean_r_t1 >= MIN_R_PER_TRADE) if n_t1 else False
    crit4 = n_trades_t1 >= MIN_TRADES
    crit5 = half1 > 0 and half2 > 0
    crit6 = long_r > 0 and short_r > 0
    section7_pass = crit1 and crit2 and crit3 and crit4 and crit5 and crit6

    section51_pass = (drops_delta[3] > 0 and drops_delta[5] > 0
                       and beats_mean and beats_drop5 and sign_agree)

    return dict(
        n_all=n_all, n_b0_drop=n_b0_drop, n_b0=n_b0, n_t1=n_t1, n_skip=n_skip,
        per_trade_b0_mean=per_trade_b0_mean, per_trade_t1_mean=per_trade_t1_mean,
        per_trade_delta=per_trade_delta,
        per_symday_b0_mean=per_symday_b0_mean, per_symday_t1_mean=per_symday_t1_mean,
        per_symday_delta=per_symday_delta, sign_agree=bool(sign_agree),
        drops_delta=drops_delta,
        ctrl_mean_p95=ctrl_mean_p95, ctrl_drop5_p95=ctrl_drop5_p95,
        t1_drop5_own=t1_drop5_own, beats_mean=bool(beats_mean), beats_drop5=bool(beats_drop5),
        abstention_part=abstention_part, price_part=price_part,
        premium_mean=float(np.nanmean(premium)) if n_t1 else float("nan"),
        premium_p50=float(np.nanmedian(premium)) if n_t1 else float("nan"),
        entry_delay_mean=float(np.nanmean(entry_delay)) if n_t1 else float("nan"),
        entry_delay_p50=float(np.nanmedian(entry_delay)) if n_t1 else float("nan"),
        n_entry_min_stopouts=n_entry_min_stopouts, n_avoided=n_avoided,
        n_top50_kept=n_top50_kept,
        drop_t1=drop_t1, boot_p=boot_p, mean_r_t1=mean_r_t1, n_trades_t1=n_trades_t1,
        half1=half1, half2=half2, long_r=long_r, short_r=short_r,
        crit1=crit1, crit2=crit2, crit3=crit3, crit4=crit4, crit5=crit5, crit6=crit6,
        section7_pass=section7_pass, section51_pass=section51_pass,
    ), b0_ok


def render(sc: dict) -> list[str]:
    L = []
    a = L.append
    a("H-X1 (10-second confirmation trigger) vs B0 -- W05-0003 step 5")
    a("docs/research/REGISTERED_10sec.md sections 5.1 and 7 (section 4 fill check NOT YET run -- needs MBP-1, step 6)")
    a("=" * 78)
    a(f"population: {sc['n_all']:,} primary-cell trades; B0-on-seconds fired {sc['n_b0']:,} "
      f"({sc['n_b0_drop']} dropped, B0 did not reproduce a trade -- G2's own <1% slack)")
    a(f"T1 fired on {sc['n_t1']:,} of those {sc['n_b0']:,} symbol-days "
      f"({sc['n_t1']/sc['n_b0']*100:.1f}%); skipped {sc['n_skip']:,}")
    a("")
    a("-- section 5.1.1: paired delta, both denominators (BASE friction) --")
    a(f"  per-trade    B0 mean {sc['per_trade_b0_mean']:+.4f}R   T1 mean {sc['per_trade_t1_mean']:+.4f}R   delta {sc['per_trade_delta']:+.4f}R")
    a(f"  per-symday   B0 mean {sc['per_symday_b0_mean']:+.4f}R   T1 mean {sc['per_symday_t1_mean']:+.4f}R   delta {sc['per_symday_delta']:+.4f}R")
    a(f"  sign agreement: {'YES' if sc['sign_agree'] else 'NO -- REFUSAL'}")
    a("")
    a("-- section 5.1.2: drop-top-N on the delta, by symbol --")
    for k in DROPS:
        v = sc["drops_delta"][k]
        a(f"  drop-top-{k}: {v:+.2f}R  {'> 0 OK' if v > 0 else '<= 0 FAIL'}")
    a("")
    a("-- section 5.1.3: random-removal control (2,000 draws, seed 20260916) --")
    a(f"  control mean R,  95th pct: {sc['ctrl_mean_p95']:+.4f}R   T1 mean R: {sc['per_trade_t1_mean']:+.4f}R   "
      f"{'BEATS' if sc['beats_mean'] else 'DOES NOT BEAT'}")
    a(f"  control drop-top-5, 95th pct: {sc['ctrl_drop5_p95']:+.2f}R   T1 drop-top-5 (own book): {sc['t1_drop5_own']:+.2f}R   "
      f"{'BEATS' if sc['beats_drop5'] else 'DOES NOT BEAT'}")
    a("")
    a("-- section 5.1.4: decomposition --")
    a(f"  abstention part (B0's R on symbol-days T1 skipped): {sc['abstention_part']:+.2f}R")
    a(f"  price part (T1 R - B0 R on shared symbol-days):     {sc['price_part']:+.2f}R")
    a(f"  confirmation premium (T1 fill - level)/r: mean {sc['premium_mean']:+.4f}  median {sc['premium_p50']:+.4f}")
    a(f"  entry delay, seconds: mean {sc['entry_delay_mean']:.1f}  median {sc['entry_delay_p50']:.1f}")
    a(f"  B0 entry-minute stop-outs: {sc['n_entry_min_stopouts']}   T1 avoids: {sc['n_avoided']} "
      f"({sc['n_avoided']/sc['n_entry_min_stopouts']*100:.1f}%)" if sc['n_entry_min_stopouts'] else "  B0 entry-minute stop-outs: 0")
    a(f"  of B0's top-50 trades by R, T1 keeps: {sc['n_top50_kept']}/50")
    a("")
    a("-- section 7, criteria 1-6, on T1's own kept book (fill check PENDING, step 6) --")
    a(f"  1. drop-top-3 {sc['drop_t1'][3]:+.2f}R, drop-top-5 {sc['drop_t1'][5]:+.2f}R, both > 0: {'PASS' if sc['crit1'] else 'FAIL'}")
    a(f"  2. symbol-cluster bootstrap P(total>0) = {sc['boot_p']:.3f} >= 0.95: {'PASS' if sc['crit2'] else 'FAIL'}")
    a(f"  3. mean net R = {sc['mean_r_t1']:+.4f}R >= +0.05R: {'PASS' if sc['crit3'] else 'FAIL'}")
    a(f"  4. trades = {sc['n_trades_t1']} >= 100: {'PASS' if sc['crit4'] else 'FAIL'}")
    a(f"  5. both halves > 0 ({sc['half1']:+.2f}R, {sc['half2']:+.2f}R): {'PASS' if sc['crit5'] else 'FAIL'}")
    a(f"  6. both sides > 0 (long {sc['long_r']:+.2f}R, short {sc['short_r']:+.2f}R): {'PASS' if sc['crit6'] else 'FAIL'}")
    a("")
    a("=" * 78)
    if not sc["section51_pass"] or not sc["section7_pass"]:
        a("VERDICT: H-X1 NOT ADOPTABLE.")
        a("  Fails one or more computable criteria above -- section 7.1's retirement clause applies")
        a("  regardless of the pending section 4 fill check: the sub-minute confirmation family")
        a("  (5-, 15-, 30-second variants, 'two closes beyond', 'close beyond by k cents') is retired")
        a("  for ORB.")
    else:
        a("VERDICT: every computable criterion clears. PROVISIONAL -- the section 4 fill check")
        a("  (needs MBP-1 quote data, not pulled until step 6/G4) has not run. Not a pass until it does.")
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=str(TRADES_DEFAULT))
    p.add_argument("--archive", default=None)
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--csv", default=str(CSV_DEFAULT))
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--from-csv", action="store_true",
                    help="skip the 1-second resimulation and rescore the trades "
                         "already cached at --csv")
    a = p.parse_args(argv)

    if a.from_csv:
        res = pd.read_csv(a.csv)
        print(f"loaded {len(res):,} cached trades from {a.csv} (resimulation skipped)")
    else:
        ledger = P.load_ledger(Path(a.trades))          # holdout excluded by default
        cell = primary_cell(ledger)
        print(f"primary cell: {len(cell):,} trades, {cell['date'].nunique():,} sessions")

        if a.archive:
            archive = Path(a.archive)
        else:
            from common.databento_fetch import default_archive
            archive = default_archive()

        res = run(cell, archive, a.jobs, Path(a.csv).parent / "_tensec_hx1")
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        res.to_csv(a.csv, index=False, encoding="utf-8", compression="gzip")

    sc, scored = score(res)
    L = render(sc)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.out}\nwrote {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
