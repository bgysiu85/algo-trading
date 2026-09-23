#!/usr/bin/env python3
r"""G2 (W05-0003, `docs/research/REGISTERED_10sec.md`) -- B0 parity.

    python -m strategy.orb.tensec_g2 --jobs 8
    python -m strategy.orb.tensec_g2 --out var/reports/tensec_g2_parity.txt

WHAT THIS CHECKS, EXACTLY (section 0, gate G2)
-----------------------------------------------
B0 (`strategy.orb.tensec_engine.b0_trade`) re-simulated on 1-second bars must
give, against the primary cell of `var/cache/orb_sip/trades/` (outside the
locked holdout):

  (a) the same symbol-days and sides for >= 99% of its 7,239 trades
  (b) the same entry price wherever the ledger's entry did not gap
  (c) mean net R at BASE friction within +-0.02R of the resolved figure of
      record, +0.001R (`claude/orb_sip_RESOLVED_20260918.md`)

Every symbol-day whose exit reason differs from the ledger is listed with
its cause. NOTHING FROM THIS STUDY IS SCORED (H-X1, H-Q1) UNTIL THIS PASSES.

Side, `or_high`/`or_low` and `r` are read from the ledger and never
recomputed here (REGISTERED_10sec.md section 2: the host is the minute-bar
setup, unchanged; only the trigger drops to seconds) -- so a mismatch here
is a mismatch in FILL MECHANICS at finer resolution, not a different setup.
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.orb import sip as S
from strategy.orb import sip_report as P
from strategy.orb import tensec_engine as E
from strategy.orb.tensec_pairs import primary_cell

TRADES_DEFAULT = Path("var/cache/orb_sip/trades")
OUT_DEFAULT = Path("var/reports/tensec_g2_parity.txt")
CSV_DEFAULT = Path("var/cache/orb_sip/tensec_g2_trades.csv.gz")
DATASET = "XNAS.ITCH"
SCHEMA = "ohlcv-1s"

MATCH_GATE = 0.99            # criterion (a)
R_BAND = 0.02                # criterion (c)
R_OF_RECORD = 0.001          # claude/orb_sip_RESOLVED_20260918.md, RESOLVED, BASE

RESULT_COLS = [
    "symbol", "date", "side", "why",
    "ledger_entry_px", "ledger_exit_px", "ledger_exit_reason",
    "ledger_gapped_entry", "ledger_r", "ledger_or_high", "ledger_or_low",
    "sec_entry_px", "sec_exit_px", "sec_exit_reason",
]


def _one(args):
    archive, day, rows_json = args
    from common.dbn_io import read_dbn
    rows = pd.read_json(rows_json, orient="records")
    src = Path(archive) / DATASET / SCHEMA / f"{day}.dbn.zst"
    if not src.exists():
        return [dict(symbol=r.symbol, date=day, side=int(r.side), why="NO_1S_FILE",
                     ledger_entry_px=r.entry_px, ledger_exit_px=r.exit_px,
                     ledger_exit_reason=r.exit_reason,
                     ledger_gapped_entry=bool(r.gapped_entry), ledger_r=r.r,
                     ledger_or_high=r.or_high, ledger_or_low=r.or_low,
                     sec_entry_px=np.nan, sec_exit_px=np.nan, sec_exit_reason="")
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
        t, why = E.b0_trade(sod, sub["open"].to_numpy(float),
                            sub["high"].to_numpy(float),
                            sub["low"].to_numpy(float),
                            sub["close"].to_numpy(float),
                            int(r.side), float(r.or_high), float(r.or_low),
                            float(r.r))
        out.append(dict(
            symbol=r.symbol, date=day, side=int(r.side), why=why,
            ledger_entry_px=r.entry_px, ledger_exit_px=r.exit_px,
            ledger_exit_reason=r.exit_reason,
            ledger_gapped_entry=bool(r.gapped_entry), ledger_r=r.r,
            ledger_or_high=r.or_high, ledger_or_low=r.or_low,
            sec_entry_px=np.nan if t is None else t.entry_px,
            sec_exit_px=np.nan if t is None else t.exit_px,
            sec_exit_reason="" if t is None else t.exit_reason,
        ))
    return out


def run(ledger: pd.DataFrame, archive: Path, jobs: int, tmp: Path) -> pd.DataFrame:
    tmp.mkdir(parents=True, exist_ok=True)
    work = []
    for day, g in ledger.groupby("date", sort=True):
        f = tmp / f"{day}.json"
        g[["symbol", "side", "entry_px", "exit_px", "exit_reason",
           "gapped_entry", "r", "or_high", "or_low"]].to_json(f, orient="records")
        work.append((str(archive), day, str(f)))
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            parts = list(ex.map(_one, work))
    else:
        parts = [_one(w) for w in work]
    flat = [x for part in parts for x in part]
    return pd.DataFrame(flat, columns=RESULT_COLS)


def score(res: pd.DataFrame) -> dict:
    n = len(res)
    matched = res["why"] == E.OK          # (a): B0-on-seconds also traded
    match_rate = matched.mean() if n else 0.0

    ungapped = ~res["ledger_gapped_entry"] & matched
    entry_diff = (res.loc[ungapped, "sec_entry_px"]
                 - res.loc[ungapped, "ledger_entry_px"]).abs()
    entry_ok = int((entry_diff < 1e-6).sum())
    entry_n = int(ungapped.sum())

    scored = res[matched].copy()
    trades = pd.DataFrame({
        "side": scored["side"], "entry_px": scored["sec_entry_px"],
        "exit_px": scored["sec_exit_px"], "exit_reason": scored["sec_exit_reason"],
        "r": scored["ledger_r"],
    })
    net = P.add_net(trades)
    mean_r_base = float(net["R_BASE"].mean()) if len(net) else float("nan")
    within_band = abs(mean_r_base - R_OF_RECORD) <= R_BAND if len(net) else False

    reason_diff = scored[scored["sec_exit_reason"] != scored["ledger_exit_reason"]]

    return dict(n=n, match_rate=match_rate, matched=int(matched.sum()),
               entry_ok=entry_ok, entry_n=entry_n,
               entry_rate=entry_ok / entry_n if entry_n else 1.0,
               mean_r_base=mean_r_base, within_band=within_band,
               reason_diff=reason_diff,
               gate_a=match_rate >= MATCH_GATE,
               gate_b=(entry_ok == entry_n),
               gate_c=within_band)


def render(res: pd.DataFrame, sc: dict) -> list[str]:
    L = [
        "G2 -- B0 PARITY, THE 1-SECOND ENGINE AGAINST THE PUBLISHED LEDGER",
        "", "  registration     docs/research/REGISTERED_10sec.md, gate G2",
        "  seconds          XNAS.ITCH ohlcv-1s, whole session, primary cell",
        f"  trades checked   {sc['n']:,}", "",
        "CRITERION (a) -- same symbol-days and sides, >= 99%", "",
        f"  B0-on-seconds also traded    {sc['matched']:,} / {sc['n']:,}"
        f"   ({sc['match_rate']:.2%})",
        f"  gate (>= 99%)                 {'PASS' if sc['gate_a'] else 'FAIL'}", "",
        "CRITERION (b) -- same entry price wherever the ledger did not gap", "",
        f"  ungapped ledger entries       {sc['entry_n']:,}",
        f"  seconds entry matches         {sc['entry_ok']:,}   ({sc['entry_rate']:.2%})",
        f"  gate (exact match)             {'PASS' if sc['gate_b'] else 'FAIL'}", "",
        "CRITERION (c) -- mean net R at BASE within +-0.02R of +0.001R", "",
        f"  mean net R (BASE), B0-on-seconds   {sc['mean_r_base']:+.4f}R",
        f"  resolved figure of record          {R_OF_RECORD:+.4f}R",
        f"  gate (within +-{R_BAND}R)            "
        f"{'PASS' if sc['gate_c'] else 'FAIL'}", "",
        f"OVERALL: {'G2 PASSES' if (sc['gate_a'] and sc['gate_b'] and sc['gate_c']) else 'G2 FAILS -- do not score H-X1 or H-Q1'}",
        "", "EXIT-REASON DISAGREEMENTS, EVERY ONE LISTED", "",
    ]
    rd = sc["reason_diff"]
    if rd.empty:
        L.append("  none")
    else:
        L.append(f"  {len(rd):,} symbol-day(s) disagree on exit reason:")
        for row in rd.itertuples():
            L.append(f"    {row.symbol:<8} {row.date}  ledger={row.ledger_exit_reason:<12}"
                     f" seconds={row.sec_exit_reason:<12}"
                     f" ledger_exit={row.ledger_exit_px:.4f} seconds_exit={row.sec_exit_px:.4f}")
    not_matched = res[res["why"] != E.OK]
    if len(not_matched):
        L += ["", f"{len(not_matched):,} symbol-day(s) where B0-on-seconds found NO trade "
                  "(why, count):"]
        for why, cnt in not_matched["why"].value_counts().items():
            L.append(f"    {why:<16} {cnt:,}")
    L.append("")
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=str(TRADES_DEFAULT))
    p.add_argument("--archive", default=None)
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--csv", default=str(CSV_DEFAULT))
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = p.parse_args(argv)

    ledger = P.load_ledger(Path(a.trades))          # holdout excluded by default
    cell = primary_cell(ledger)
    print(f"primary cell: {len(cell):,} trades, {cell['date'].nunique():,} sessions")

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()

    res = run(cell, archive, a.jobs, Path(a.csv).parent / "_tensec_g2")
    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(a.csv, index=False, encoding="utf-8", compression="gzip")

    sc = score(res)
    L = render(res, sc)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.out}\nwrote {a.csv}")
    return 0 if (sc["gate_a"] and sc["gate_b"] and sc["gate_c"]) else 1


if __name__ == "__main__":
    sys.exit(main())
