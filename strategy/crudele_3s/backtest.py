#!/usr/bin/env python3
"""CRUDELE-3S training-side backtest, sec 3 emissions + sec 4 verdict. W15-0034.

    python -m strategy.crudele_3s.backtest                 (the registered run: 12 markets, 1,000 C2 draws)
    python -m strategy.crudele_3s.backtest --draws 50      (scoped: banner says NOT the result)

TRAINING SIDE ONLY (2010-06 -> 2021-12-31). The bars come through strategy.futbt.loading, which cuts
2022-01-01 onward before any bar is built. This runner has NO path to the holdout or the seen window:
--holdout, --limit, --seen and --spend are refused. The holdout (holdout_crudele_3s.json) is spent
once, by a separate step, only after a training verdict that passes all ten criteria.
Costs: IBKR (W15-0033), fee + 0/1/2 ticks per side; see strategy/futbt/costs_ibkr.py.
"""
from __future__ import annotations

import sys
import time
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.crudele_3s import sim as SIM
from strategy.crudele_3s import spec as S
from strategy.crudele_3s import states as ST
from strategy.futbt import controls as CT
from strategy.futbt import core as K
from strategy.futbt import engine as EN
from strategy.futbt import grid as GR
from strategy.futbt import loading as LD
from strategy.futbt import report_common as RC
from strategy.futbt import runner_common as RN
from strategy.tl_v0 import report as Rp
from strategy.tl_v0.report import money, net_per_vol, pct, years_span
from strategy.tl_v0.spec import EQUITY

REGISTERED_DRAWS = 1000
REFUSED = ("--holdout", "--limit", "--seen", "--spend", "--pnl-holdout")
VARIANT_ORDER = list(S.VARIANTS)


class RunRefused(SystemExit):
    pass


def refuse(argv):
    bad = [a for a in argv if a.split("=")[0] in REFUSED]
    if bad:
        raise RunRefused(f"REFUSED {bad}: this runner reads the TRAINING side only (REGISTERED_crudele_3s.md "
                         "sec 6). The holdout is spent once, by a separate step, after a ten-of-ten "
                         "training pass; --limit and every narrowing of that run are refused.")


def _calendar(outs):
    return pd.DatetimeIndex(sorted(set().union(*[set(o.dates) for o in outs])))


def state_years(frames: dict) -> pd.DataFrame:
    """bars in each state per market per year (sec 3 item 5), from the system's own state series."""
    rows = []
    for m, fr in frames.items():
        sg = ST.compute(fr, S.PRIMARY)
        yr = fr.dates.year.to_numpy()
        for y in np.unique(yr):
            sel = sg.state[yr == y]
            rows.append(dict(market=m, year=int(y), **{ST.STATE_NAMES[k]: int((sel == k).sum()) for k in ST.STATE_NAMES}))
    return pd.DataFrame(rows)


def run_pipeline(frames: dict, *, draws: int = REGISTERED_DRAWS, frame_4h=None, log=print) -> dict:
    t0 = time.time()
    outs = []
    for name, fr in frames.items():
        outs.append(EN.run_market(fr, ST, SIM, S.VARIANTS))
        log(f"{name}: {fr.n} bars, {len(outs[-1].trades)} trade rows ({time.time() - t0:.0f}s)")
    cal = _calendar(outs)
    books = {}
    for v in list(S.VARIANTS) + ["C1"]:
        for sz, eq in K.VERDICT_SIZINGS:
            books[(v, sz)] = EN.build_book(outs, v, sz, eq, cal)
    real = pd.concat([o.trades for o in outs if len(o.trades)], ignore_index=True)
    real = real[(real["variant"] == "system") & (real["sizing"] == "frac")]
    log(f"C2: {draws} draws over {len(real)} system trades ...")
    c2 = CT.run_crudele_c2(frames, real, draws, EQUITY,
                           progress=lambda d: log(f"  C2 draw {d} ({time.time() - t0:.0f}s)"))
    log("27-cell grid ...")
    grid = GR.run_grid(frames, ST, SIM, GR.crudele_cells(), progress=lambda i: log(f"  cell {i}/27 ({time.time() - t0:.0f}s)"))
    res = dict(outs=outs, cal=cal, books=books, c2=c2, grid=grid, frames=frames, states=state_years(frames),
               index_slice=None, cl4h=None)
    idx = [m for m in S.INDEX_SLICE if m in frames]
    if idx:
        sub = [o for o in outs if o.market in idx]
        c = _calendar(sub)
        res["index_slice"] = EN.build_book(sub, "system", "frac", EQUITY, c)
    if frame_4h is not None:
        o4 = EN.run_market(frame_4h, ST, SIM, {"system": S.PRIMARY})
        o4 = RC.to_sessions(o4)
        c4 = pd.DatetimeIndex(o4.dates)
        res["cl4h"] = dict(system=EN.build_book([o4], "system", "frac", EQUITY, c4),
                           c1=EN.build_book([o4], "C1", "frac", EQUITY, c4), out=o4, frame=frame_4h)
    return res


def render(res: dict, *, scoped: bool, notes=(), draws=REGISTERED_DRAWS) -> tuple[str, pd.DataFrame]:
    L = []
    p = L.append
    books, c2, grid, outs, cal = res["books"], res["c2"], res["grid"], res["outs"], res["cal"]
    markets = [o.market for o in outs]
    V = lambda v, sz="frac": books[(v, sz)]
    b, c1 = V("system"), V("C1")
    p("CRUDELE-3S BACKTEST -- REGISTERED_crudele_3s.md sections 3-4 (W15-0034)")
    p("TRAINING SIDE ONLY: 2010-06 .. 2021-12-31, cut by the holdout ledger before any bar was built.")
    p("The holdout (2022-01-03 .. 2025-09-22) and the seen window (2025-09-23 onward) are NOT read and NOT spent by this run.")
    p("Nothing is ranked; there is no best-cell table.")
    if scoped:
        p("")
        p("!" * 100)
        p("SCOPED / NON-REGISTERED RUN (--markets, --draws or no CL 4H): NOT THE REGISTERED RESULT.")
        p("!" * 100)
    for n in notes:
        p(n)
    p(f"Years in sample: {years_span(cal):.2f} ({cal[0].date()} .. {cal[-1].date()}).  Fractional book at ${EQUITY:,.0f} is the verdict; "
      "the integer book is beside it.")
    RC.ibkr_header(p)

    RC.hdr(p, f"1. SECTION 4 VERDICT -- CRUDELE-3S (three arms), fractional @ ${EQUITY:,.0f}, mid friction")
    mid = b.net("mid")
    c6 = Rp.Criterion(6, "beats the p95 of C2 (matched random entries, per arm and side)",
                      f"{money(mid).strip()} vs p95 {money(c2['p95']).strip()} (p5 {money(c2['p5']).strip()}, p50 {money(c2['p50']).strip()})",
                      bool(mid > c2["p95"]))
    crit = RC.criteria(b, c1, c6, grid, markets, friction_label="IBKR mid")
    ntr = len(b.trades)
    verdict = RC.verdict_lines(p, crit, ntr, "the CRUDELE-3S holdout")
    fi, ii = mid, V("system", "int").net("mid")
    nint = len(V("system", "int").trades)
    flag = ("   <-- the integer book made NO trades at this size" if nint == 0 else
            "   <-- OPPOSITE SIGNS: this is the headline" if np.sign(fi) * np.sign(ii) < 0 else "")
    p(f"  Integer book beside it: net at mid {money(fi).strip()} fractional vs {money(ii).strip()} integer ({nint} trades){flag}")
    p("  The per-arm results below are reported, not scored: the hypothesis is the whole 3-state system (sec 4).")

    RC.hdr(p, "2. EVERY BOOK AND VARIANT -- sec 2.6 order, unranked")
    entries = []
    for sz, label in (("frac", "fractional"), ("int", "integer")):
        p(f"-- {label} @ ${EQUITY:,.0f} --")
        rows = [(v, V(v, sz)) for v in VARIANT_ORDER] + [("C1 Donchian", V("C1", sz))]
        if sz == "frac" and res["index_slice"] is not None:
            rows.insert(len(VARIANT_ORDER), ("index slice ES+RTY", res["index_slice"]))
        df = RC.books_table(p, rows)
        df["sizing"] = sz
        entries.append(df)
    summary = pd.concat(entries, ignore_index=True)
    p(f"worst run of losing trades (system, fractional): {RC.worst_streak(b.trades)}")

    RC.hdr(p, "3. BY MARKET, BY CALENDAR YEAR, AND HALVES (net at mid, fractional)")
    RC.year_market_tables(p, [("system", b), ("No-C", V("No-C")), ("T-no-squeeze", V("T-no-squeeze")), ("C1 Donchian", c1)], markets)

    RC.hdr(p, "4. BY ARM AND BY SIDE (system, fractional @ $22,129, net at mid)")
    t = b.trades
    RC.group_table(p, t, ["arm"], "by arm")
    RC.group_table(p, t, ["arm", "direction"], "by arm and side (1 = long, -1 = short)")
    RC.group_table(p, t, ["direction"], "by side")
    for arm in S.ARMS:
        n = int((t["arm"] == arm).sum()) if len(t) else 0
        if n < S.MIN_ARM_ENTRIES:
            p(f"  arm {arm}: {n} entries -- TOO FEW TO READ (< {S.MIN_ARM_ENTRIES})")
    p("Single-arm runs (books above): T-only, MR-only, C-only; each arm's own exits are below.")

    RC.hdr(p, "5. EXIT REASONS PER ARM AND MEDIAN HOLD (system, fractional)")
    if len(t):
        RC.group_table(p, t, ["arm", "reason"], "exit reasons per arm (hold = median bars)")

    RC.hdr(p, "6. COUNTS (bars in each state, transitions, T episodes, MR arms, C stop-runs, skips)")
    sy = res["states"]
    if len(sy):
        tot = sy.groupby("market")[["N", "C", "T", "MR"]].sum()
        p("-- bars in each state per market, all years (per-year table is in the states CSV) --")
        p(tot.to_string())
        yr = sy.groupby("year")[["N", "C", "T", "MR"]].sum()
        p("-- bars in each state per year, all markets --")
        p(yr.to_string())
    sc = pd.DataFrame({o.market: o.signal_counts.get("system", {}) for o in outs}).T
    p("-- signal counts per market (system) --")
    p(sc.to_string())
    ct = pd.DataFrame({o.market: o.counts.get(("system", "frac"), {}) for o in outs}).T
    p("-- walk counts per market (system, fractional): voided, skipped, entries by arm --")
    p(ct.to_string())
    p("-- walk counts summed --")
    p(ct.sum().to_string())

    RC.hdr(p, "7. CONTROLS")
    p(f"  C1 Donchian 20/10 (same markets, sizing, costs): net mid {money(c1.net('mid')).strip()}, {len(c1.trades)} trades, "
      f"net/vol {RC.num(net_per_vol(c1), 2)}; CRUDELE-3S {money(mid).strip()}, net/vol {RC.num(net_per_vol(b), 2)}")
    p(f"  C2 matched random entries, {c2['draws']:,} seeded draws (crc32 of draw number): net at mid p5 {money(c2['p5']).strip()}  "
      f"p50 {money(c2['p50']).strip()}  p95 {money(c2['p95']).strip()}  mean {money(c2['mean']).strip()}")
    p(f"      CRUDELE-3S at mid {money(mid).strip()} sits at draw-percentile {100 * float((c2['totals'] < mid).mean()):.0f}")
    p("      Caveat: random trades in one market may overlap in time (the real method holds one position); a random entry has no setup at all.")

    RC.hdr(p, "8. THE 27-CELL NEIGHBOUR GRID (fractional, net at mid; robustness only, unranked)")
    RC.grid_lines(p, grid, ["bwr", "exp_bars", "exit_ma"], dict(bwr=S.SQ_THR, exp_bars=S.EXP_BARS, exit_ma=S.SMA_EXIT), mid)

    RC.hdr(p, "9. 20 SAMPLE TRADES (every 1/20th, system, fractional)")
    RC.sample_trades(p, t, [("arm", "arm", ""), ("risk_frac", "risk", ".3f")])

    RC.hdr(p, "10. CL 4-HOUR VARIANT (sec 2.6: reported, not scored, cannot spend the holdout)")
    cl = res["cl4h"]
    if cl is None:
        p("  CL 4H NOT EVALUATED (1-hour file not found or --no-cl4h). The daily result is unaffected.")
    else:
        RC.books_table(p, [("CL4H system", cl["system"]), ("CL4H C1", cl["c1"])])
        RC.group_table(p, cl["system"].trades, ["arm"], "CL 4H by arm")

    RC.hdr(p, "11. CAVEATS AND DEPARTURES")
    p("""\
  * "Flat" and "expanding" are OUR reading of his eye (sec 8); the 27-cell grid shows how much it matters.
  * Bars are UTC days (Databento ohlcv-1d, Sunday stubs folded): 'next open' is the evening session.
  * MTN: P&L on TN's held contract; MTN listed 2024-03-25, so 2010-2021 describes the signal, not a tradable history.
    NG and 6J are sized in full contracts (most signals skip). SIL fee is ASSUMED (IBKR does not list it).
  * The 1% / 0.5% risk is of a FIXED $22,129 (no compounding). Roll legs: two sides per contract.
  * Costs are IBKR fee + 0/1/2 ticks on EVERY fill (Ben's choice, 2026-09-30); the old flat $0.50/1.25/2.50 is retired.
  * Prices in the sample table are difference-back-adjusted.""")
    return "\n".join(L) + "\n", summary


def main(argv=None) -> int:
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    argv = list(sys.argv[1:] if argv is None else argv)
    refuse(argv)
    ap = RN.base_parser("CRUDELE-3S training-side backtest (W15-0034)")
    ap.add_argument("--draws", type=int, default=REGISTERED_DRAWS)
    ap.add_argument("--no-cl4h", action="store_true")
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    a = ap.parse_args(argv)
    names, scoped_m = RN.pick_markets(a.markets)
    arch = RN.archive_path(a.archive)
    frames, notes = LD.load_daily(arch, names, ibkr=True)
    fr4, extra = None, []
    if not a.no_cl4h and "CL" in names:
        try:
            fr4 = LD.load_cl4h(arch, ibkr=True)
        except FileNotFoundError as e:
            extra.append(f"CL 4H NOT EVALUATED: 1-hour file not found ({e}).")
            print(extra[-1])
    scoped = scoped_m or a.draws != REGISTERED_DRAWS or a.no_cl4h
    res = run_pipeline(frames, draws=a.draws, frame_4h=fr4)
    text, summary = render(res, scoped=scoped, notes=[f"{m}: {n}" for m, n in notes.items() if n] + extra, draws=a.draws)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"w15_0034_crudele_backtest_{a.stamp}" + ("_scoped" if scoped else "")
    (out / f"{stem}.txt").write_text(text, encoding="utf-8")
    pd.concat([o.trades for o in res["outs"] if len(o.trades)], ignore_index=True).to_csv(out / f"{stem}_trades.csv", index=False)
    summary.to_csv(out / f"{stem}_books.csv", index=False)
    res["grid"].to_csv(out / f"{stem}_grid.csv", index=False)
    res["states"].to_csv(out / f"{stem}_states.csv", index=False)
    pd.DataFrame({"draw": range(len(res["c2"]["totals"])), "net_mid": res["c2"]["totals"]}).to_csv(out / f"{stem}_c2.csv", index=False)
    print(text)
    print(f"wrote {out / (stem + '.txt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
