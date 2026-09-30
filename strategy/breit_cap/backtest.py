#!/usr/bin/env python3
"""BREIT-CAP training-side backtest, sec 3 emissions + sec 4 verdict. W15-0034.

    python -m strategy.breit_cap.backtest                (the registered run: 12 markets daily + CL 4H, 1,000 C3 draws)
    python -m strategy.breit_cap.backtest --draws 50     (scoped: banner says NOT the result)

TRAINING SIDE ONLY (2010-06 -> 2021-12-31). Bars come through strategy.futbt.loading (holdout cut first).
--holdout, --limit, --seen and --spend are refused. Two holdouts exist (holdout_breit_cap.json,
holdout_breit_cap_cl4h.json); each is spent once, by a separate step, only by a book that passed sec 4.
The daily 12-market book is the PRIMARY (verdict). CL 4H is a scored SECONDARY on the same ten criteria
(criteria 3, 4 and 7 read by year), reported beside the primary, never instead of it.
Costs: IBKR (W15-0033), fee + 0/1/2 ticks per side; see strategy/futbt/costs_ibkr.py.

CODING NOTE (PRE-RUN): criterion 6 part one, "beats C2 on net per trade (R-normalised)": average R per
trade = mean(net at mid / (risk fraction x $22,129)) of the fractional book; BREIT-CAP's average R must
exceed C2's (the unfiltered reversal at flat 1%). Part two: net at mid above the p95 of C3's 1,000 draws.
"""
from __future__ import annotations

import sys
import time
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.breit_cap import signals as SG
from strategy.breit_cap import sim as SIM
from strategy.breit_cap import spec as S
from strategy.futbt import controls as CT
from strategy.futbt import core as K
from strategy.futbt import engine as EN
from strategy.futbt import grid as GR
from strategy.futbt import loading as LD
from strategy.futbt import report_common as RC
from strategy.futbt import runner_common as RN
from strategy.tl_v0 import report as Rp
from strategy.tl_v0.report import money, net_per_vol, years_span
from strategy.tl_v0.spec import EQUITY

REGISTERED_DRAWS = 1000
REFUSED = ("--holdout", "--limit", "--seen", "--spend", "--pnl-holdout")
VARIANTS = dict(S.VARIANTS)
VARIANTS["C2 unfiltered"] = S.C2_UNFILTERED
ORDER = list(S.VARIANTS) + ["C2 unfiltered"]


class RunRefused(SystemExit):
    pass


def refuse(argv):
    bad = [a for a in argv if a.split("=")[0] in REFUSED]
    if bad:
        raise RunRefused(f"REFUSED {bad}: this runner reads the TRAINING side only (REGISTERED_breit_cap.md "
                         "sec 6). Each holdout is spent once, by a separate step, only by a book that passed "
                         "sec 4; --limit and every narrowing of that run are refused.")


def avg_r(t: pd.DataFrame) -> float:
    if not len(t):
        return float("nan")
    return float((t["net_mid"] / (t["risk_frac"] * EQUITY)).mean())


def run_study(frames: dict, label: str, *, draws: int, sessions: bool, log=print) -> dict:
    t0 = time.time()
    outs = []
    for name, fr in frames.items():
        o = EN.run_market(fr, SG, SIM, VARIANTS)
        outs.append(RC.to_sessions(o) if sessions else o)
        log(f"[{label}] {name}: {fr.n} bars, {len(o.trades)} trade rows ({time.time() - t0:.0f}s)")
    cal = pd.DatetimeIndex(sorted(set().union(*[set(o.dates) for o in outs])))
    books = {}
    for v in list(VARIANTS) + ["C1"]:
        for sz, eq in K.VERDICT_SIZINGS:
            books[(v, sz)] = EN.build_book(outs, v, sz, eq, cal)
    real = pd.concat([o.trades for o in outs if len(o.trades)], ignore_index=True)
    real = real[(real["variant"] == "system") & (real["sizing"] == "frac")]
    log(f"[{label}] C3: {draws} draws over {len(real)} system trades ...")
    c3 = CT.run_breit_c3(frames, real, draws, EQUITY,
                         progress=lambda d: log(f"  C3 draw {d} ({time.time() - t0:.0f}s)"))
    log(f"[{label}] 27-cell grid ...")
    grid = GR.run_grid(frames, SG, SIM, GR.breit_cells())
    return dict(label=label, outs=outs, cal=cal, books=books, c3=c3, grid=grid, frames=frames,
                single=sessions, markets=[o.market for o in outs])


def render_study(p, st: dict, *, title: str):
    books, c3, grid, cal = st["books"], st["c3"], st["grid"], st["cal"]
    V = lambda v, sz="frac": books[(v, sz)]
    b, c1, c2 = V("system"), V("C1"), V("C2 unfiltered")
    single, markets = st["single"], st["markets"]
    mid = b.net("mid")
    RC.hdr(p, f"1. SECTION 4 VERDICT -- {title}, fractional @ ${EQUITY:,.0f}, mid friction")
    r_sys, r_c2 = avg_r(b.trades), avg_r(c2.trades)
    ok_c2 = bool(np.isfinite(r_sys) and np.isfinite(r_c2) and r_sys > r_c2)
    ok_c3 = bool(mid > c3["p95"])
    c6 = Rp.Criterion(6, "beats C2 (unfiltered reversal) on net per trade (R-normalised) AND the p95 of C3 (random entries)",
                      f"avg R {RC.num(r_sys, 3)} vs C2 {RC.num(r_c2, 3)} ({'yes' if ok_c2 else 'no'}); net {money(mid).strip()} vs C3 p95 "
                      f"{money(c3['p95']).strip()} (p5 {money(c3['p5']).strip()}, p50 {money(c3['p50']).strip()}) ({'yes' if ok_c3 else 'no'})",
                      bool(ok_c2 and ok_c3))
    crit = RC.criteria(b, c1, c6, grid, markets, single=single, friction_label="IBKR mid")
    verdict = RC.verdict_lines(p, crit, len(b.trades), "this book's holdout")
    ii, nint = V("system", "int").net("mid"), len(V("system", "int").trades)
    flag = ("   <-- the integer book made NO trades at this size" if nint == 0 else
            "   <-- OPPOSITE SIGNS: this is the headline" if np.sign(mid) * np.sign(ii) < 0 else "")
    p(f"  Integer book beside it: net at mid {money(mid).strip()} fractional vs {money(ii).strip()} integer ({nint} trades){flag}")

    RC.hdr(p, "2. EVERY BOOK AND VARIANT -- sec 2.6 order, unranked")
    frames_ = []
    for sz, lab in (("frac", "fractional"), ("int", "integer")):
        p(f"-- {lab} @ ${EQUITY:,.0f} --")
        rows = [(v, V(v, sz)) for v in ORDER] + [("C1 Donchian", V("C1", sz))]
        df = RC.books_table(p, rows)
        df["sizing"] = sz
        frames_.append(df)
    p(f"worst run of losing trades (system, fractional): {RC.worst_streak(b.trades)}")

    RC.hdr(p, "3. BY " + ("CALENDAR YEAR AND HALVES" if single else "MARKET, CALENDAR YEAR AND HALVES") + " (net at mid, fractional)")
    RC.year_market_tables(p, [("system", b), ("flat-1pct", V("flat-1pct")), ("C2 unfiltered", c2), ("C1 Donchian", c1)],
                          markets, single=single)

    t = b.trades
    RC.hdr(p, "4. BY SIDE AND BY GRADE 0-5 (system, fractional; avg R = net / (risk fraction x $22,129))")
    RC.group_table(p, t, ["direction"], "by side (1 = long, -1 = short)")
    RC.group_table(p, t, ["grade"], "by grade")
    RC.group_table(p, t, ["direction", "grade"], "by side and grade")

    RC.hdr(p, "5. EXIT REASONS, HOLD, EXITS WITHIN 1 BAR (system, fractional)")
    if len(t):
        RC.group_table(p, t, ["reason"], "exit reasons (hold = median bars)")
        p(f"  median hold {t['hold'].median():.0f} bars; share exiting within 1 bar: {100 * float((t['hold'] <= 1).mean()):.0f}%")

    RC.hdr(p, "6. COUNTS")
    sc = pd.DataFrame({o.market: o.signal_counts.get("system", {}) for o in st["outs"]}).T
    p("-- signal counts per market (system): Q1 runs, runs failing Q2 / Q3, qualified, orders --")
    p(sc.to_string())
    ct = pd.DataFrame({o.market: o.counts.get(("system", "frac"), {}) for o in st["outs"]}).T
    p("-- walk counts per market (system, fractional): orders, unfilled, set up while a position was open, skipped for size, entries --")
    p(ct.to_string())
    p("-- summed --")
    p(ct.sum().to_string())
    if len(t):
        p("-- distribution of run length k and D/ATR[O] at entry --")
        p(t["k"].value_counts().sort_index().to_string())
        p(t["d_atr"].describe(percentiles=[.1, .5, .9]).round(2).to_string())

    RC.hdr(p, "7. CONTROLS")
    p(f"  C1 Donchian 20/10 (same markets, sizing, costs): net mid {money(c1.net('mid')).strip()}, {len(c1.trades)} trades, "
      f"net/vol {RC.num(net_per_vol(c1), 2)}; BREIT-CAP {money(mid).strip()}, net/vol {RC.num(net_per_vol(b), 2)}")
    p(f"  C2 unfiltered reversal (any Q1 run, flat 1%): net mid {money(c2.net('mid')).strip()}, {len(c2.trades)} trades, avg R "
      f"{RC.num(r_c2, 3)} vs BREIT-CAP {RC.num(r_sys, 3)}")
    p(f"  C3 random entries, {c3['draws']:,} seeded draws (crc32 of draw number): net at mid p5 {money(c3['p5']).strip()}  "
      f"p50 {money(c3['p50']).strip()}  p95 {money(c3['p95']).strip()}  mean {money(c3['mean']).strip()}")
    p(f"      BREIT-CAP at mid {money(mid).strip()} sits at draw-percentile {100 * float((c3['totals'] < mid).mean()):.0f}")
    p("      Caveat: random trades in one market may overlap in time; a random entry has no setup at all.")

    RC.hdr(p, "8. THE 27-CELL NEIGHBOUR GRID (fractional, net at mid; robustness only, unranked)")
    RC.grid_lines(p, grid, ["q2", "k_min", "q3_sd"], dict(q2=S.Q2_ATR, k_min=S.K_MIN, q3_sd=S.Q3_SD), mid)

    RC.hdr(p, "9. 20 SAMPLE TRADES (every 1/20th, system, fractional)")
    RC.sample_trades(p, t, [("k", "k", ".0f"), ("d_atr", "D/ATR", ".1f"), ("grade", "grade", ".0f")])
    return crit, verdict, pd.concat(frames_, ignore_index=True)


def render(prim: dict, cl4h: dict | None, *, scoped: bool, notes=()) -> tuple[str, pd.DataFrame, dict]:
    L = []
    p = L.append
    p("BREIT-CAP BACKTEST -- REGISTERED_breit_cap.md sections 3-4 (W15-0034)")
    p("TRAINING SIDE ONLY: 2010-06 .. 2021-12-31, cut by the holdout ledger before any bar was built.")
    p("The holdouts (2022-01-03 .. 2025-09-22) and the seen window (2025-09-23 onward) are NOT read and NOT spent by this run.")
    p("Nothing is ranked; there is no best-cell table.")
    if scoped:
        p("")
        p("!" * 100)
        p("SCOPED / NON-REGISTERED RUN (--markets, --draws or no CL 4H): NOT THE REGISTERED RESULT.")
        p("!" * 100)
    for n in notes:
        p(n)
    cal = prim["cal"]
    p(f"Years in sample: {years_span(cal):.2f} ({cal[0].date()} .. {cal[-1].date()}).")
    RC.ibkr_header(p)
    p("")
    p("#" * 100)
    p("PART A -- PRIMARY: daily, 12 markets, both sides, graded sizing (the sec 4 verdict)")
    p("#" * 100)
    crit, verdict, summ = render_study(p, prim, title="BREIT-CAP PRIMARY")
    summ["study"] = "primary"
    out = {"primary": verdict}
    frames_ = [summ]
    if cl4h is not None:
        p("")
        p("#" * 100)
        p("PART B -- SECONDARY: CL 4-hour, both sides, graded, per 1 MCL (scored on the same criteria; reported WITH the primary)")
        p("#" * 100)
        crit4, verdict4, summ4 = render_study(p, cl4h, title="BREIT-CAP CL 4H")
        summ4["study"] = "cl4h"
        frames_.append(summ4)
        out["cl4h"] = verdict4
    else:
        p("")
        p("PART B -- CL 4H: NOT EVALUATED (1-hour file not found or --no-cl4h). The daily primary is unaffected.")
    RC.hdr(p, "10. CAVEATS AND DEPARTURES")
    p("""\
  * Known departures (not coded): intra-bar and front-side entries in extreme panics; a daily chart checked
    against an intraday trigger; news, forced flows, sentiment; discretionary audibles on stops; scaling out.
  * Bars are UTC days (Databento ohlcv-1d, Sunday stubs folded). G-volume uses held-contract volume (G1 passed).
  * MTN: P&L on TN's held contract; listed 2024-03-25, so 2010-2021 describes the signal, not a tradable history.
    NG and 6J are sized in full contracts. SIL fee is ASSUMED (IBKR does not list it).
  * Risk is a fraction of a FIXED $22,129 (no compounding); grade sizing 0.5 / 1 / 2%, shorts half. Roll legs: two sides per contract.
  * Costs are IBKR fee + 0/1/2 ticks on EVERY fill (Ben's choice, 2026-09-30).
  * CL 4H: sessions are 18:00 New York; daily P&L for volatility is summed per session; the C3 random draws and grid run on the 4H bars.
  * Prices in the sample table are difference-back-adjusted.""")
    return "\n".join(L) + "\n", pd.concat(frames_, ignore_index=True), out


def main(argv=None) -> int:
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    argv = list(sys.argv[1:] if argv is None else argv)
    refuse(argv)
    ap = RN.base_parser("BREIT-CAP training-side backtest (W15-0034)")
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
    prim = run_study(frames, "daily", draws=a.draws, sessions=False)
    cl4h = run_study({"CL4H": fr4}, "CL4H", draws=a.draws, sessions=True) if fr4 is not None else None
    text, summary, verdicts = render(prim, cl4h, scoped=scoped, notes=[f"{m}: {n}" for m, n in notes.items() if n] + extra)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"w15_0034_breit_backtest_{a.stamp}" + ("_scoped" if scoped else "")
    (out / f"{stem}.txt").write_text(text, encoding="utf-8")
    for tag, st in (("daily", prim), ("cl4h", cl4h)):
        if st is None:
            continue
        pd.concat([o.trades for o in st["outs"] if len(o.trades)], ignore_index=True).to_csv(out / f"{stem}_trades_{tag}.csv", index=False)
        st["grid"].to_csv(out / f"{stem}_grid_{tag}.csv", index=False)
        pd.DataFrame({"draw": range(len(st["c3"]["totals"])), "net_mid": st["c3"]["totals"]}).to_csv(out / f"{stem}_c3_{tag}.csv", index=False)
    summary.to_csv(out / f"{stem}_books.csv", index=False)
    print(text)
    print(f"wrote {out / (stem + '.txt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
