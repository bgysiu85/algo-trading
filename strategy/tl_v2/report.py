#!/usr/bin/env python3
"""The TL-v2 sec 3 report and the sec 4 ten-criteria verdict. TRAINING SIDE ONLY. Board: W15-0049.

Verdict book (as TL-v0 Amendment B, which TL-v1 and TL-v2 sec 2.1 inherit): the FRACTIONAL ensemble at
$22,129, IBKR MID friction (Amendment 1: fee + 1 tick per side); the integer book at $22,129 is printed
beside it. Nothing is ranked; rows print in registry order.

CODING NOTES for sec 4 wording that admits more than one reading (PRE-RUN, fixed here, Amendment 3):
  * criterion 2 "split at the median entry date": the median ENTRY date of the verdict book's trades;
    each half is the sum of net at mid of the trades that entered in it. An empty half fails.
    (strategy.tl_v1.report.half_split, unchanged.)
  * criterion 6 beats the **p99** of C3's 1,000 draws on net at IBKR mid (raised from p95 by Ben).
  * criterion 9: cells with net at mid > $0 among the 27 (touch buffer x W x N, fractional ensemble); >= 18.
  * criterion 10 / NOT READ: fewer than 150 trades in the verdict book -> the study is NOT READ, and so is
    every other criterion: the report prints their values "for information" but withholds pass/fail. It
    never says FAILED for a study that has too few trades (sec 4). No variant, N = 20 or S/R result is
    ever substituted (sec 4, sec 7).
  * criterion 7 (concentration) is NOT READ (counts as not passed) when net <= 0.
  * "beats C1 on net and net per unit of realised volatility": C1 is the Donchian 20/10 walk run by the
    engine at the same IBKR prices.
  * C2 (TL-v1 immediate entry) is REFERENCE ONLY, not a criterion (sec 4): the figures are the IBKR
    re-quote of W15-0020's book in Claude outputs/w15_0033_requote_ibkr_20260930.txt (Amendment 1).
    If TL-v2 passes yet is below C2, the FIRST line of the verdict block says so (sec 4).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.tl_v0 import report as Rp
from strategy.tl_v0.report import (Book, build_book, cluster_boot, concentration, drop_top, money,
                                   net_per_vol, pct, years_span)
from strategy.tl_v0.spec import EQUITIES, EQUITY, MARKETS
from strategy.tl_v1.report import _hdr, _num, half_split
from strategy.tl_v1.signals import REGISTERED_ER_Q25
from strategy.tl_v2 import holdout as TH

VERDICT = ("frac", EQUITY)
I22 = ("int", EQUITY)
MIN_TRADES = 150
CELLS_NEEDED = 18
SEEN_LABEL = "seen -- not evidence"

# TL-v1 immediate entry (W15-0020), verdict ensemble, fractional @ $22,129, re-quoted at IBKR costs.
# Transcribed from Claude outputs/w15_0033_requote_ibkr_20260930.txt ("v1 ENSEMBLE ... frac 636").
C2_REF = dict(trades=636, old_mid=775.0, ibkr_low=1185.0, ibkr_mid=606.0, ibkr_high=27.0)

BOOKS: tuple[tuple[str, str], ...] = (
    ("v2", "ens"), ("v2", "R3"), ("v2", "R5"), ("v2", "R8"),
    ("v2-SR", "ens"), ("v2-SR", "R3"), ("v2-SR", "R5"), ("v2-SR", "R8"),
    ("v2-N20", "ens"), ("v2-N20", "R3"), ("v2-N20", "R5"), ("v2-N20", "R8"),
    ("C1", "single"),
)
VARIANT_SPECS = {"v2-SR", "v2-N20"}


def make_books(runs, calendar) -> dict:
    out = {}
    for spec, cut in BOOKS:
        sizings = (("frac", EQUITY),) + tuple(("int", e) for e in EQUITIES)
        if spec in VARIANT_SPECS:
            sizings = sizings[:2]
        for sz, eq in sizings:
            out[(spec, cut, sz, eq)] = build_book(runs, spec, cut, sz, eq, calendar)
    return out


def criteria(b: Book, c1: Book, c3: dict | None, grid: pd.DataFrame | None) -> list[Rp.Criterion]:
    """The ten sec 4 criteria. Under MIN_TRADES trades nothing is passed or failed (NOT READ)."""
    C = Rp.Criterion
    n = len(b.trades)
    readable = n >= MIN_TRADES
    out: list[Rp.Criterion] = []

    def add(no, text, value, passed):
        if not readable:
            out.append(C(no, text, f"(for information only, {n} < {MIN_TRADES} trades) {value}", None))
        else:
            out.append(C(no, text, value, passed))

    mid, high = b.net("mid"), b.net("high")
    add(1, "net > $0 at IBKR mid friction", money(mid).strip(), mid > 0)
    split, h1, h2, n1, n2 = half_split(b)
    add(2, "both halves > $0 (split at median entry date; empty half fails)",
        f"{money(h1).strip()} ({n1} trades) / {money(h2).strip()} ({n2} trades), split "
        f"{None if split is None else str(pd.Timestamp(split).date())}",
        bool(n1 > 0 and n2 > 0 and h1 > 0 and h2 > 0))
    bm = b.by_market()
    d1, d2 = drop_top(bm, 1), drop_top(bm, 2)
    add(3, "drop-top-1 and drop-top-2 by market still > $0",
        f"{money(d1).strip()} / {money(d2).strip()}",
        bool(d1 is not None and d2 is not None and d1 > 0 and d2 > 0))
    bmk, byr = cluster_boot(bm), cluster_boot(b.by_year())
    add(4, "bootstrap (2,000) by market AND by year: net > 0 in >= 95% each",
        f"{pct(bmk['share_pos']).strip()} / {pct(byr['share_pos']).strip()}",
        bool(bmk["share_pos"] >= 0.95 and byr["share_pos"] >= 0.95))
    c1n, c1v, bv = c1.net("mid"), net_per_vol(c1), net_per_vol(b)
    beats = mid > c1n and np.isfinite(bv) and np.isfinite(c1v) and bv > c1v
    add(5, "beats C1 Donchian 20/10 on net AND net per unit realised volatility",
        f"{money(mid).strip()} vs {money(c1n).strip()}; {_num(bv, 2)} vs {_num(c1v, 2)}", bool(beats))
    text6 = "beats the p99 of C3 (random selection of retest entries of every line break)"
    if c3 is None:
        out.append(C(6, text6, "C3 not run", None))
    else:
        add(6, text6, f"{money(mid).strip()} vs p99 {money(c3['p99']).strip()} "
                      f"(p5 {money(c3['p5']).strip()}, p50 {money(c3['p50']).strip()}, "
                      f"p95 {money(c3['p95']).strip()})", bool(mid > c3["p99"]))
    ky, sy = concentration(b.by_year(), mid)
    km, sm = concentration(bm, mid)
    add(7, "no single year and no single market > 50% of net",
        "not read (net <= 0)" if sy is None else
        f"top year {ky} {pct(sy).strip()}, top market {km} {pct(sm).strip()}",
        None if sy is None else bool(sy <= 0.5 and sm <= 0.5))
    add(8, "still net > $0 at IBKR high friction", money(high).strip(), high > 0)
    if grid is None:
        out.append(C(9, f">= {CELLS_NEEDED} of 27 neighbour cells net > $0", "grid not run", None))
    else:
        npos = int((grid["net_mid"] > 0).sum())
        add(9, f">= {CELLS_NEEDED} of 27 neighbour cells net > $0 (IBKR mid)",
            f"{npos} of {len(grid)}", bool(npos >= CELLS_NEEDED))
    out.append(C(10, f"at least {MIN_TRADES} trades (fewer = NOT READ, not failed)", f"{n} trades",
                 True if readable else None))
    return out


def verdict_lines(crit: list[Rp.Criterion], n_trades: int, mid: float) -> list[str]:
    """First line = the headline. Sec 4: 'If TL-v2 passes yet is below TL-v1's, the write-up says so in
    the first line.'"""
    if n_trades < MIN_TRADES:
        return [f"NOT READ (only {n_trades} trades; sec 4 criterion 10) -- neither passed nor failed. "
                f"No variant, N = 20 or S/R result may be swapped in to rescue the count."]
    if all(c.passed for c in crit):
        first = "PASSES all ten -- the TL-v2 holdout may be spent (once; sec 6)"
        if mid < C2_REF["ibkr_mid"]:
            first = (f"PASSES all ten, BUT net {money(mid).strip()} is BELOW TL-v1's immediate entry "
                     f"({money(C2_REF['ibkr_mid']).strip()} at IBKR mid): waiting for the retest paid "
                     f"less than entering on the break. The holdout may be spent (once; sec 6).")
        return [first]
    failed = [c.no for c in crit if not c.passed]
    line = f"DOES NOT PASS (failed or not read: criteria {failed})"
    if not (crit[4].passed and crit[5].passed):
        line += "  -- criterion 5 and/or 6 failed: the study closes whatever else passes (sec 4)"
    return [line]


def load_events(runs) -> pd.DataFrame:
    """All runs' retest events with the calendar year of the BREAK bar t."""
    parts = []
    for r in runs:
        if len(r.events):
            ev = r.events.copy()
            ev["year"] = r.dates[ev["t"].to_numpy()].year
            parts.append(ev)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _outcome_table(ev: pd.DataFrame, key: str, trades: pd.DataFrame, counts: pd.DataFrame | None):
    """Sec 3 counts per market or per year: qualified breaks, retest entries, failed, no retest,
    skipped for size, median bars break->retest, median bars held."""
    ct = pd.crosstab(ev[key], ev["outcome"]).reindex(
        columns=["entry", "failed", "no_retest", "open_at_end", "ignored_pending"], fill_value=0)
    tab = pd.DataFrame({
        "qualified": ct.sum(axis=1) - ct["ignored_pending"],
        "entries": ct["entry"], "failed": ct["failed"], "no_retest": ct["no_retest"],
        "open_end": ct["open_at_end"], "ignored": ct["ignored_pending"],
    })
    tab["med_bars_to_retest"] = ev[ev["outcome"] == "entry"].groupby(key)["bars_to_retest"].median()
    if len(trades):
        t = trades.copy()
        t["year"] = pd.to_datetime(t["entry_date"]).dt.year
        tk = key if key in t.columns else "year"
        tab["med_bars_held"] = t.groupby(tk)["hold"].median()
    if counts is not None and key == "market":
        tab["skipped_size"] = counts.groupby("market")["skipped_size"].sum()
    return tab.fillna(0).round(1)


def render(runs, ctxs, calendar, *, c3, grid, scoped, notes, preflight_total=None) -> tuple[str, pd.DataFrame]:
    L = []
    p = L.append
    books = make_books(runs, calendar)
    V = lambda spec, cut, sz=VERDICT: books[(spec, cut, sz[0], sz[1])]
    p("TL-v2 BACKTEST -- REGISTERED_tl_v2.md sections 3-4, Amendments 1-3 (W15-0049 layer; W15-0031 run)")
    p("TRAINING SIDE ONLY: sessions 2010-06-01 .. 2021-12-31, cut by the holdout ledger before any bar")
    p("was built. The TL-v2 holdout (2022-01-03 .. 2025-09-22) is NOT read and NOT spent by this run.")
    p("Nothing is ranked; no best-cell table.")
    if scoped:
        p("")
        p("!" * 100)
        p("SCOPED / NON-REGISTERED RUN (--markets or --c3-draws): NOT THE REGISTERED RESULT.")
        p("!" * 100)
    for n in notes:
        p(n)
    if preflight_total is not None:
        p(f"Pre-flight stop rule (W15-0048) read before this run: {preflight_total} retest entries "
          f"(N = 10, 12 markets) >= 150.")
    p(f"Years in sample: {years_span(calendar):.2f}  ({calendar[0].date()} .. {calendar[-1].date()})")
    p("Money: whole dollars, negatives in (brackets). COSTS = IBKR (Amendment 1): per contract per side,")
    p("low = all-in fee, mid = fee + 1 tick, high = fee + 2 ticks; no separate stop-fill tick.")

    b, c1 = V("v2", "ens"), V("C1", "single")
    ntr = len(b.trades)
    _hdr(p, f"1. SECTION 4 VERDICT -- TL-v2 ensemble, fractional @ ${EQUITY:,.0f}, IBKR mid friction")
    crit = criteria(b, c1, c3, grid)
    vl = verdict_lines(crit, ntr, b.net("mid"))
    p(f"  => {vl[0]}")
    for c in crit:
        mark = "PASS" if c.passed else ("NOT READ" if c.passed is None else "FAIL")
        p(f"  {c.no:>2}. [{mark:8}] {c.text}: {c.value}")
    fi, ii = b.net("mid"), V("v2", "ens", I22).net("mid")
    nint = len(V("v2", "ens", I22).trades)
    flag = ("   <-- the integer book made NO trades at this size" if nint == 0 else
            "   <-- OPPOSITE SIGNS: this is the headline" if np.sign(fi) * np.sign(ii) < 0 else "")
    p(f"  Integer book @ ${EQUITY:,.0f} beside it: net at mid {money(fi).strip()} fractional vs "
      f"{money(ii).strip()} integer ({nint} trades){flag}")
    rel = "below" if fi < C2_REF["ibkr_mid"] else "at or above"
    p(f"  C2 (TL-v1 immediate entry, W15-0020, IBKR re-quote; reported beside, NOT a criterion): net at mid "
      f"{money(C2_REF['ibkr_mid']).strip()}, {C2_REF['trades']} trades. TL-v2 is {rel} it "
      f"(TL-v2 {money(fi).strip()}, {ntr} trades).")

    rows = []
    for sz, title in ((VERDICT, "fractional"), (I22, "integer")):
        _hdr(p, f"2. EVERY BOOK, {title} @ ${EQUITY:,.0f} -- registry order, unranked (IBKR low / mid / high)")
        p(f"{'book':<18}{'gross':>12}{'net low':>12}{'net mid':>12}{'net high':>12}{'mid/yr':>11}"
          f"{'trades':>8}{'W':>6}{'L':>6}{'win%':>6}{'hold':>6}{'worst DD':>12}{'net/vol':>8}")
        for spec, cut in BOOKS:
            key = (spec, cut, sz[0], sz[1])
            if key not in books:
                continue
            r = Rp.book_row(books[key])
            rows.append(r)
            p(f"{r['book']:<18}{money(r['gross'])}{money(r['net_low'])}{money(r['net_mid'])}"
              f"{money(r['net_high'])}{money(r['net_mid_per_yr'], 11)}{r['trades']:>8}{r['wins']:>6}"
              f"{r['losses']:>6}{pct(r['win_rate'], 6)}{_num(r['median_hold']):>6}"
              f"{money(-r['max_dd'])}{_num(r['net_per_vol'], 2):>8}")
    summary = pd.DataFrame(rows)

    _hdr(p, "3. CONTROLS")
    p(f"  C1 Donchian 20/10 (same markets/sizing/IBKR costs): net mid {money(c1.net('mid')).strip()}, "
      f"{len(c1.trades)} trades, net/vol {_num(net_per_vol(c1), 2)}")
    p(f"  C2 TL-v1 immediate entry (W15-0020, IBKR re-quote): net mid {money(C2_REF['ibkr_mid']).strip()}, "
      f"{C2_REF['trades']} trades  (old flat-friction mid {money(C2_REF['old_mid']).strip()})")
    if c3:
        p(f"  C3 random selection, {c3['draws']:,} seeded draws (crc32 of draw number): net at IBKR mid "
          f"p5 {money(c3['p5']).strip()}  p50 {money(c3['p50']).strip()}  p95 {money(c3['p95']).strip()}  "
          f"p99 {money(c3['p99']).strip()}  mean {money(c3['mean']).strip()}")
        p(f"     pool {c3['pool_entries']:,} retest entries of every weekly-agreeing line break (A+ not "
          f"required); TL-v2 selects {c3['selected_entries']:,}; draws fill a median "
          f"{c3['entries_median']:.0f} trades vs TL-v2's {ntr} (fractional ensemble trades)")
        gone = c3["own_total"] - c3["own_in_pool"]
        p(f"     TL-v2's own {c3['own_total']:,} retest entries: {c3['own_in_pool']:,} are also in the pool"
          + (f"; the other {gone:,} were displaced there by a non-A+ setup occupying the one live slot "
             f"(Amendment 2 C1 applies to the pool's scan too)" if gone else ""))
        p(f"     TL-v2 at mid {money(b.net('mid')).strip()} sits at draw-percentile "
          f"{100 * float((c3['totals'] < b.net('mid')).mean()):.0f}; p99 is about the 10th-largest of 1,000 draws")
    else:
        p("  C3: not run")

    _hdr(p, "4. COUNTS -- what happened to each qualified break (primary N = 10; three pivot sizes summed)")
    ev = load_events(runs)
    cnt = pd.concat([r.counts for r in runs], ignore_index=True)
    tr_v2 = b.trades
    if len(ev):
        ev10 = ev[ev["spec"] == "v2"]
        cnt10 = cnt[(cnt["spec"] == "v2") & (cnt["sizing"] == VERDICT[0]) & (cnt["equity"] == VERDICT[1])
                    & (cnt["share"] == "sleeve")]
        p("-- by market (skipped_size = entries the simulator skipped for zero contracts) --")
        p(_outcome_table(ev10, "market", tr_v2, cnt10).to_string())
        p("-- by year of the BREAK (skipped-for-size is counted per market by the simulator, not per year) --")
        p(_outcome_table(ev10, "year", tr_v2, None).to_string())
        p("-- by pivot size R --")
        p(_outcome_table(ev10, "R", tr_v2, None).to_string())
        ev20 = ev[ev["spec"] == "v2-N20"]
        p("-- reported variant N = 20: outcomes (all markets, three pivot sizes summed) --")
        p(ev20["outcome"].value_counts().to_string())
        p("(Amendment 2 C1: N = 20 can start FEWER setups than N = 10, because a longer-pending setup "
          "blocks a later same-side break.)")
    keep = ["breaks", "signals", "not_aplus", "htf_blocked", "ignored_in_position", "reversals",
            "reversal_blocked_flat", "voided", "skipped_size", "no_stop", "unfilled_at_end", "entries"]
    keep = [k for k in keep if k in cnt.columns]
    for sz in (VERDICT, I22):
        sub = cnt[(cnt["sizing"] == sz[0]) & (cnt["equity"] == sz[1]) & cnt["spec"].isin(["v2", "C1"])]
        p(f"-- simulator counts, {sz[0]} @ ${sz[1]:,.0f} (per sleeve walk, summed) --")
        p(sub.groupby(["spec", "share"])[keep].sum().to_string())

    _hdr(p, "5. THE 27-CELL NEIGHBOUR GRID (fractional ensemble, net at IBKR mid; robustness only, unranked)")
    if grid is not None:
        p(f"{'N':>4}{'window':>8}{'touch buf':>11}{'net mid':>12}{'trades':>8}")
        for _, r in grid.iterrows():
            p(f"{int(r['N']):>4}{int(r['window']):>8}{r['touch_buf']:>11.2f}{money(r['net_mid'])}{int(r['trades']):>8}")
        centre = grid[(grid["window"] == 250) & (grid["touch_buf"] == 0.25) & (grid["N"] == 10)]
        npos = int((grid["net_mid"] > 0).sum())
        p(f"share of cells positive: {(grid['net_mid'] > 0).mean():.0%} ({npos} of {len(grid)}); "
          f"criterion 9 needs {CELLS_NEEDED}.")
        if len(centre):
            delta = float(centre["net_mid"].iloc[0]) - b.net("mid")
            dn = int(centre["trades"].iloc[0]) - ntr
            p(f"Centre cell (0.25, 250, 10) vs the verdict book: net difference {delta:+.4f}, trade difference "
              f"{dn:+d} (both must be 0).")
    else:
        p("  grid not run")

    _hdr(p, f"6. EVERY CALENDAR YEAR and EVERY MARKET, net at IBKR mid (fractional @ ${EQUITY:,.0f})")
    cols = [("v2", "ens"), ("v2-SR", "ens"), ("v2-N20", "ens"), ("C1", "single")]
    yt = pd.DataFrame({f"{s} {c}": V(s, c).by_year() for s, c in cols})
    p(f"{'year':<6}" + "".join(f"{k:>16}" for k in yt.columns))
    for y, r in yt.iterrows():
        p(f"{y:<6}" + "".join(money(v, 16) for v in r.to_numpy()))
    mt = pd.DataFrame({f"{s} {c}": V(s, c).by_market() for s, c in cols})
    p(f"{'market':<7}" + "".join(f"{k:>16}" for k in mt.columns))
    for m, r in mt.iterrows():
        p(f"{m:<7}" + "".join(money(v, 16) for v in r.to_numpy()))
    bm = b.by_market()
    dt = [drop_top(bm, n) for n in (1, 2, 3)]
    bo, by = cluster_boot(bm), cluster_boot(b.by_year())
    p(f"  v2 ens: drop-top-1/2/3 {' / '.join(money(v).strip() for v in dt)}; boot by market >0 "
      f"{pct(bo['share_pos']).strip()} (p05 {money(bo['p05']).strip()}), by year >0 {pct(by['share_pos']).strip()} "
      f"(p05 {money(by['p05']).strip()})")

    _hdr(p, "7. A3 THRESHOLDS: computed from the training bars vs the registered TL-v1 q25 (should agree)")
    worst = 0.0
    p(f"{'market':<7}{'q25 calc':>10}{'reg':>8}")
    for name, ctx in ctxs.items():
        calc, reg = ctx.er_thr[0.25], REGISTERED_ER_Q25.get(name, np.nan)
        worst = max(worst, abs(calc - reg)) if np.isfinite(reg) else worst
        p(f"{name:<7}{calc:>10.3f}{reg:>8.3f}")
    p(f"largest |calculated - registered| = {worst:.4f}"
      + ("  (rounding only)" if worst <= 0.0006 else "  <-- MORE THAN ROUNDING: the pre-flight's frame differs from this run's"))

    _hdr(p, "8. SAMPLE TRADES -- TL-v2 ensemble, integer @ $22,129, IBKR mid friction (raw held-contract prices)")
    tb = V("v2", "ens", I22).trades
    if len(tb):
        tb = tb.sort_values("entry_date")
        step = max(len(tb) // 12, 1)
        p(f"{len(tb)} trades, every {step}th shown")
        p(f"{'market':<7}{'R':>3}{'side':>6}{'entry':>12}{'exit':>12}{'contract':>14}{'qty':>5}"
          f"{'entry px':>13}{'exit px':>13}{'why':>13}{'net $':>11}")
        for _, r in tb.iloc[::step].head(12).iterrows():
            p(f"{r['market']:<7}{r['R']:>3}{'long' if r['direction'] > 0 else 'short':>6}"
              f"{str(pd.Timestamp(r['entry_date']).date()):>12}{str(pd.Timestamp(r['exit_date']).date()):>12}"
              f"{r['entry_contract']:>14}{r['qty']:>5.0f}{r['entry_raw']:>13.6g}"
              f"{r['exit_raw']:>13.6g}{r['reason']:>13}{money(r['net_mid'], 11)}")
    else:
        p("  none (the integer book made no trades)")

    _hdr(p, "9. SEEN WINDOW (2025-09-23 onward)")
    dates = [d.strftime("%Y-%m-%d") for d in calendar]
    seen, label = TH.seen_dates(dates)
    p(f"  Label: \"{label}\". The training bars contain {len(seen)} session(s) in the seen window, as they "
      f"must (0): it lies inside the region strategy.tl_v0.bars cuts before any bar is built.")
    p("  It is NOT scored here (sec 6: \"never scored\"; same as TL-v1). Sec 3 lists it as \"reported only\"; "
      "a report needs bars this runner cannot read, so nothing is reported. Not evidence either way.")

    _hdr(p, "10. CAVEATS AND DEPARTURES")
    p("""\
  * Known departures (sec 2.3, not coded): wick-based line validity; her multi-timeframe ladder; news;
    volatility overlay; one instrument at a time; her 4-15% risk; her judgement of which retests to take.
  * Selection by survival (sec 8): T4 drops the fast runners that never come back; the no-retest count
    in section 4 is that cost.
  * C3 at p99 with 1,000 draws is about the 10th-largest draw: a weak bar in resolution, strong in level.
  * Bars are UTC days (Databento ohlcv-1d, Sunday stubs folded) -- see TL-v0's caveats.
  * MTN: P&L on TN's held contract at $100/point; MTN listed 2024-03-25, so 2010-2021 describes the
    signal, not a tradable history. NG and 6J are sized in full contracts (most signals skip).
  * The 1% risk is of a FIXED $22,129 (no compounding). Roll legs are booked at the two contracts'
    closes on the roll session, two sides of friction per contract.
  * A3's thresholds come from the training bars only; section 7 compares them with the registered q25.
  * The training bars have now been read by TL-v0, v0-rev, TL-bounce, TL-v1 and this run: a training-side
    pass alone is not a finding; only the holdout counts (sec 0, sec 6).""")
    return "\n".join(L) + "\n", summary
