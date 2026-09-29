#!/usr/bin/env python3
"""The TL-v1 sec 3 report and the sec 4 ten-criteria verdict. TRAINING SIDE ONLY.

Verdict book (as TL-v0 Amendment B, which sec 2.1 inherits): the FRACTIONAL ensemble at
$22,129, mid friction; the integer book at $22,129 is printed beside it. Nothing is ranked;
rows print in registry order.

CODING NOTES for sec 4 wording that admits more than one reading (PRE-RUN, fixed here):
  * criterion 2 "split at the median trade date": the split is the median ENTRY date of the
    verdict book's trades; each half is the sum of net at mid of the trades that entered in
    it. An empty half fails.
  * criterion 6 beats the p95 of C3's 1,000 draws on net at mid.
  * criterion 9: cells with net at mid > $0 among the 27 (fractional ensemble); needs >= 18.
  * criterion 10: fewer than 150 trades in the verdict book -> the study is NOT READ.
  * criterion 7 (concentration) is NOT READ (counts as not passed) when net <= 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.tl_v0 import report as Rp
from strategy.tl_v0.report import (Book, build_book, cluster_boot, concentration, drop_top, money,
                                   net_per_vol, pct, years_span)
from strategy.tl_v0.spec import EQUITIES, EQUITY, LEVELS, MARKETS, PIVOT_SIZES
from strategy.tl_v1.signals import ER_QS, REGISTERED_ER

VERDICT = ("frac", EQUITY)
I22 = ("int", EQUITY)
MIN_TRADES = 150
CELLS_NEEDED = 18

BOOKS: tuple[tuple[str, str], ...] = (
    ("v1", "ens"), ("v1", "R3"), ("v1", "R5"), ("v1", "R8"),
    ("v1-A+", "ens"), ("v1-A+", "R3"), ("v1-A+", "R5"), ("v1-A+", "R8"),
    ("v1-A3", "ens"), ("v1-A3", "R3"), ("v1-A3", "R5"), ("v1-A3", "R8"),
    ("v1-2touch", "ens"), ("v1-2touch", "R3"), ("v1-2touch", "R5"), ("v1-2touch", "R8"),
    ("C1", "single"),
)
VARIANT_SPECS = {"v1-A+", "v1-A3", "v1-2touch"}


def make_books(runs, calendar) -> dict:
    out = {}
    for spec, cut in BOOKS:
        sizings = (("frac", EQUITY),) + tuple(("int", e) for e in EQUITIES)
        if spec in VARIANT_SPECS:
            sizings = sizings[:2]
        for sz, eq in sizings:
            out[(spec, cut, sz, eq)] = build_book(runs, spec, cut, sz, eq, calendar)
    return out


def half_split(b: Book):
    t = b.trades
    if not len(t):
        return None, 0.0, 0.0, 0, 0
    ent = pd.to_datetime(t["entry_date"])
    split = ent.sort_values().iloc[len(ent) // 2]
    m = ent < split
    return (split, float(t.loc[m, "net_mid"].sum()), float(t.loc[~m, "net_mid"].sum()),
            int(m.sum()), int((~m).sum()))


def criteria(b: Book, c1: Book, c3: dict | None, grid: pd.DataFrame | None) -> list[Rp.Criterion]:
    C = Rp.Criterion
    out = []
    mid, high = b.net("mid"), b.net("high")
    n = len(b.trades)
    out.append(C(1, "net > $0 at mid friction ($1.25/side)", money(mid).strip(), mid > 0))
    split, h1, h2, n1, n2 = half_split(b)
    out.append(C(2, "both halves > $0 (split at median entry date; empty half fails)",
                 f"{money(h1).strip()} ({n1} trades) / {money(h2).strip()} ({n2} trades), split "
                 f"{None if split is None else str(pd.Timestamp(split).date())}",
                 bool(n1 > 0 and n2 > 0 and h1 > 0 and h2 > 0)))
    bm = b.by_market()
    d1, d2 = drop_top(bm, 1), drop_top(bm, 2)
    out.append(C(3, "drop-top-1 and drop-top-2 by market still > $0",
                 f"{money(d1).strip()} / {money(d2).strip()}",
                 bool(d1 is not None and d2 is not None and d1 > 0 and d2 > 0)))
    bmk, byr = cluster_boot(bm), cluster_boot(b.by_year())
    out.append(C(4, "bootstrap (2,000) by market AND by year: net > 0 in >= 95% each",
                 f"{pct(bmk['share_pos']).strip()} / {pct(byr['share_pos']).strip()}",
                 bool(bmk["share_pos"] >= 0.95 and byr["share_pos"] >= 0.95)))
    c1n, c1v, bv = c1.net("mid"), net_per_vol(c1), net_per_vol(b)
    beats = mid > c1n and np.isfinite(bv) and np.isfinite(c1v) and bv > c1v
    out.append(C(5, "beats C1 Donchian 20/10 on net AND net per unit realised volatility",
                 f"{money(mid).strip()} vs {money(c1n).strip()}; {bv:.2f} vs {c1v:.2f}", bool(beats)))
    if c3 is None:
        out.append(C(6, "beats the p95 of C3 (random selection of the same lines' breaks)",
                     "C3 not run", None))
    else:
        out.append(C(6, "beats the p95 of C3 (random selection of the same lines' breaks)",
                     f"{money(mid).strip()} vs p95 {money(c3['p95']).strip()} "
                     f"(p5 {money(c3['p5']).strip()}, p50 {money(c3['p50']).strip()})",
                     bool(mid > c3["p95"])))
    ky, sy = concentration(b.by_year(), mid)
    km, sm = concentration(bm, mid)
    out.append(C(7, "no single year and no single market > 50% of net",
                 "not read (net <= 0)" if sy is None else
                 f"top year {ky} {pct(sy).strip()}, top market {km} {pct(sm).strip()}",
                 None if sy is None else bool(sy <= 0.5 and sm <= 0.5)))
    out.append(C(8, "still net > $0 at high friction ($2.50/side)", money(high).strip(), high > 0))
    if grid is None:
        out.append(C(9, f">= {CELLS_NEEDED} of 27 neighbour cells net > $0", "grid not run", None))
    else:
        npos = int((grid["net_mid"] > 0).sum())
        out.append(C(9, f">= {CELLS_NEEDED} of 27 neighbour cells net > $0 (mid friction)",
                     f"{npos} of {len(grid)}", bool(npos >= CELLS_NEEDED)))
    out.append(C(10, f"at least {MIN_TRADES} trades (fewer = NOT READ, not failed)", f"{n} trades",
                 bool(n >= MIN_TRADES)))
    return out


def _num(v, dp=0):
    return f"{v:.{dp}f}" if v is not None and np.isfinite(v) else "n/a"


def _hdr(p, title):
    p("")
    p("=" * 100)
    p(title)
    p("=" * 100)


def load_c2_reference(path) -> dict | None:
    """TL-v0-rev ensemble, fractional @ $22,129 from W15-0014's books CSV. Reference only."""
    try:
        df = pd.read_csv(path, encoding="utf-8")
    except Exception:
        return None
    sel = df[(df["book"] == "v0-rev ens") & (df["sizing"] == "frac") & (df["equity"] == EQUITY)]
    return None if sel.empty else sel.iloc[0].to_dict()


def render(runs, ctxs, calendar, *, c3, grid, c2ref, scoped, notes) -> tuple[str, pd.DataFrame]:
    L = []
    p = L.append
    books = make_books(runs, calendar)
    V = lambda spec, cut, sz=VERDICT: books[(spec, cut, sz[0], sz[1])]
    p("TL-v1 BACKTEST -- REGISTERED_tl_v1.md sections 3-4 (W15-0020)")
    p("TRAINING SIDE ONLY: sessions 2010-06-01 .. 2021-12-31, cut by the holdout ledger before any bar")
    p("was built. The TL-v1 holdout (2022-01-03 .. 2025-09-22) is NOT read and NOT spent by this run.")
    p("Nothing is ranked; no best-cell table.")
    if scoped:
        p("")
        p("!" * 100)
        p("SCOPED / NON-REGISTERED RUN (--markets or --c3-draws): NOT THE REGISTERED RESULT.")
        p("!" * 100)
    for n in notes:
        p(n)
    p(f"Years in sample: {years_span(calendar):.2f}  ({calendar[0].date()} .. {calendar[-1].date()})")
    p("Money: whole dollars, negatives in (brackets). Friction per contract per side: low $0.50 / "
      "mid $1.25 / high $2.50, + 1 tick on every stop fill.")

    b, c1 = V("v1", "ens"), V("C1", "single")
    _hdr(p, f"1. SECTION 4 VERDICT -- TL-v1 ensemble, fractional @ ${EQUITY:,.0f}, mid friction")
    crit = criteria(b, c1, c3, grid)
    for c in crit:
        mark = "PASS" if c.passed else ("NOT READ" if c.passed is None else "FAIL")
        p(f"  {c.no:>2}. [{mark:8}] {c.text}: {c.value}")
    ntr = len(b.trades)
    if ntr < MIN_TRADES:
        verdict = f"NOT READ (only {ntr} trades; sec 4 criterion 10) -- neither passed nor failed"
    elif all(c.passed for c in crit):
        verdict = "PASSES all ten -- the TL-v1 holdout may be spent (once; sec 6)"
    else:
        failed = [c.no for c in crit if not c.passed]
        verdict = f"DOES NOT PASS (failed or not read: criteria {failed})"
        if not (crit[4].passed and crit[5].passed):
            verdict += "  -- criterion 5 and/or 6 failed: the study closes whatever else passes (sec 4)"
    p(f"  => {verdict}")
    fi, ii = b.net("mid"), V("v1", "ens", I22).net("mid")
    nint = len(V("v1", "ens", I22).trades)
    flag = ("   <-- the integer book made NO trades at this size" if nint == 0 else
            "   <-- OPPOSITE SIGNS: this is the headline" if np.sign(fi) * np.sign(ii) < 0 else "")
    p(f"  Integer book @ ${EQUITY:,.0f} beside it: net at mid {money(fi).strip()} fractional vs "
      f"{money(ii).strip()} integer ({nint} trades){flag}")
    if c2ref:
        p(f"  C2 (TL-v0-rev, W15-0014, reported beside, not a criterion): net at mid {money(c2ref['net_mid']).strip()}, "
          f"{int(c2ref['trades'])} trades, fractional @ ${EQUITY:,.0f}")
    else:
        p("  C2 (TL-v0-rev): W15-0014 books CSV not found -- pass --c2-books; reported, not a criterion.")

    rows = []
    for sz, title in ((VERDICT, "fractional"), (I22, "integer")):
        _hdr(p, f"2. EVERY BOOK, {title} @ ${EQUITY:,.0f} -- registry order, unranked")
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
    p(f"  C1 Donchian 20/10 (same markets/sizing/costs): net mid {money(c1.net('mid')).strip()}, "
      f"{len(c1.trades)} trades, net/vol {_num(net_per_vol(c1), 2)}")
    if c2ref:
        p(f"  C2 TL-v0-rev ensemble (W15-0014 run): net mid {money(c2ref['net_mid']).strip()}, "
          f"{int(c2ref['trades'])} trades")
    if c3:
        p(f"  C3 random selection, {c3['draws']:,} seeded draws (crc32 of draw number): net at mid "
          f"p5 {money(c3['p5']).strip()}  p50 {money(c3['p50']).strip()}  p95 {money(c3['p95']).strip()}  "
          f"mean {money(c3['mean']).strip()}")
        p(f"     pool {c3['pool_breaks']:,} weekly-agreeing breaks; TL-v1 selects {c3['selected_breaks']:,}; "
          f"draws fill a median {c3['entries_median']:.0f} entries vs TL-v1's {ntr} (fractional ensemble trades)")
        p(f"     TL-v1 at mid {money(b.net('mid')).strip()} sits at draw-percentile "
          f"{100 * float((c3['totals'] < b.net('mid')).mean()):.0f}")
    else:
        p("  C3: not run")

    _hdr(p, "4. COUNTS -- breaks and why they were or were not entries (bar level, per market x year)")
    ev = pd.concat([r.events for r in runs if len(r.events)], ignore_index=True) if runs else pd.DataFrame()
    if len(ev):
        ev["fail_weekly"] = ev["aplus"] & ~ev["weekly_ok"]
        ev["entry_ready"] = ev["aplus"] & ev["weekly_ok"]
        cols = ["fail_a1", "fail_a2", "fail_a3", "aplus", "fail_weekly", "entry_ready"]
        ev["breaks"] = 1
        for label, key in (("market", "market"), ("year", "year"), ("pivot size R", "R")):
            g = ev.groupby(key)[["breaks"] + cols].sum().astype(int)
            g["med_touches"] = ev[ev["entry_ready"]].groupby(key)["touches"].median()
            g["med_span_d"] = ev[ev["entry_ready"]].groupby(key)["span_days"].median()
            p(f"-- by {label} (all three pivot sizes summed; A1/A2/A3 failures counted independently) --")
            p(g.to_string(float_format=lambda v: f"{v:.1f}"))
        p(f"A2 as REGISTERED (A -> last counted touch) failed on {int(ev['fail_a2'].sum())} breaks; the "
          f"pre-flight's reading (A -> break bar) would fail {int(ev['fail_a2_preflight_reading'].sum())} of {len(ev)}. "
          f"(Information: A2 is doing {'little or no' if ev['fail_a2'].mean() < 0.01 else 'some'} filtering work.)")
    cnt = pd.concat([r.counts for r in runs], ignore_index=True)
    keep = ["breaks", "signals", "not_aplus", "htf_blocked", "ignored_in_position", "reversals",
            "reversal_blocked_flat", "voided", "skipped_size", "no_stop", "unfilled_at_end", "entries"]
    for sz in (VERDICT, I22):
        sub = cnt[(cnt["sizing"] == sz[0]) & (cnt["equity"] == sz[1]) & cnt["spec"].isin(["v1", "C1"])]
        p(f"-- simulator counts, {sz[0]} @ ${sz[1]:,.0f} (per sleeve walk, summed) --")
        p(sub.groupby(["spec", "share"])[keep].sum().to_string())

    _hdr(p, "5. THE 27-CELL NEIGHBOUR GRID (fractional ensemble, net at mid; robustness only, unranked)")
    if grid is not None:
        p(f"{'window':>7}{'touch buf':>11}{'ER pct':>8}{'net mid':>12}{'trades':>8}")
        for _, r in grid.iterrows():
            p(f"{int(r['window']):>7}{r['touch_buf']:>11.2f}{int(r['er_pct']):>8}{money(r['net_mid'])}{int(r['trades']):>8}")
        mid_cell = grid[(grid["window"] == 250) & (grid["touch_buf"] == 0.25) & (grid["er_pct"] == 25)]
        if len(mid_cell):
            delta = float(mid_cell["net_mid"].iloc[0]) - b.net("mid")
            p(f"share of cells positive: {(grid['net_mid'] > 0).mean():.0%} ({int((grid['net_mid'] > 0).sum())} of {len(grid)}). "
              f"Centre cell vs the verdict book: difference {delta:+.4f} (must be ~0).")
    else:
        p("  grid not run")

    _hdr(p, "6. EVERY CALENDAR YEAR and EVERY MARKET, net at mid (fractional @ $22,129)")
    cols = [("v1", "ens"), ("v1-A+", "ens"), ("v1-A3", "ens"), ("v1-2touch", "ens"), ("C1", "single")]
    yt = pd.DataFrame({f"{s} {c}": V(s, c).by_year() for s, c in cols})
    p(f"{'year':<6}" + "".join(f"{k:>16}" for k in yt.columns))
    for y, r in yt.iterrows():
        p(f"{y:<6}" + "".join(money(v, 16) for v in r.to_numpy()))
    mt = pd.DataFrame({f"{s} {c}": V(s, c).by_market() for s, c in cols})
    p(f"{'market':<7}" + "".join(f"{k:>16}" for k in mt.columns))
    for m, r in mt.iterrows():
        p(f"{m:<7}" + "".join(money(v, 16) for v in r.to_numpy()))
    for s, c in cols[:1]:
        bk = V(s, c)
        bm = bk.by_market()
        dt = [drop_top(bm, n) for n in (1, 2, 3)]
        bo, by = cluster_boot(bm), cluster_boot(bk.by_year())
        p(f"  {s} {c}: drop-top-1/2/3 {' / '.join(money(v).strip() for v in dt)}; boot by market >0 "
          f"{pct(bo['share_pos']).strip()} (p05 {money(bo['p05']).strip()}), by year >0 {pct(by['share_pos']).strip()} "
          f"(p05 {money(by['p05']).strip()})")

    _hdr(p, "7. A3 THRESHOLDS: computed from the training bars vs Amendment E (PRE-RUN table)")
    p(f"{'market':<7}" + "".join(f"{'q' + str(int(q * 100)) + ' calc':>10}{'reg':>8}" for q in ER_QS))
    worst = 0.0
    for name, ctx in ctxs.items():
        cells = ""
        for q in ER_QS:
            calc, reg = ctx.er_thr[q], REGISTERED_ER[q].get(name, np.nan)
            worst = max(worst, abs(calc - reg))
            cells += f"{calc:>10.3f}{reg:>8.3f}"
        p(f"{name:<7}{cells}")
    p(f"largest |calculated - registered| = {worst:.4f}"
      + ("  (rounding only)" if worst <= 0.0006 else "  <-- MORE THAN ROUNDING: the pre-flight's frame differs from this run's"))

    _hdr(p, "8. SAMPLE TRADES -- TL-v1 ensemble, integer @ $22,129, mid friction (raw held-contract prices)")
    tb = V("v1", "ens", I22).trades
    if len(tb):
        tb = tb.sort_values("entry_date")
        step = max(len(tb) // 12, 1)
        p(f"{len(tb)} trades, every {step}th shown")
        p(f"{'market':<7}{'R':>3}{'side':>6}{'entry':>12}{'exit':>12}{'contract':>14}{'qty':>5}{'touch':>6}"
          f"{'entry px':>13}{'exit px':>13}{'why':>13}{'net $':>11}")
        for _, r in tb.iloc[::step].head(12).iterrows():
            p(f"{r['market']:<7}{r['R']:>3}{'long' if r['direction'] > 0 else 'short':>6}"
              f"{str(pd.Timestamp(r['entry_date']).date()):>12}{str(pd.Timestamp(r['exit_date']).date()):>12}"
              f"{r['entry_contract']:>14}{r['qty']:>5.0f}{r.get('touches', 0):>6.0f}{r['entry_raw']:>13.6g}"
              f"{r['exit_raw']:>13.6g}{r['reason']:>13}{money(r['net_mid'], 11)}")
    else:
        p("  none (the integer book made no trades)")

    _hdr(p, "9. CAVEATS AND DEPARTURES")
    p("""\
  * NOT RUN HERE: the CL 4-hour variant (sec 2.5, reported, cannot spend the holdout) needs 4H bars
    from ohlcv-1h and TL-bounce/HTF-Ben's costs; it is a separate board item (see the Result doc).
    The seen window (2025-09-23 onward) lies inside the holdout region this runner cannot read;
    it is not scored ("seen -- not evidence").
  * Known departures (sec 2.5, not coded): wick-based line validity; her chained multi-timeframe
    ladder; S/R, double confirmation and news; break-and-retest; the volatility overlay; one
    instrument at a time; her 4-15% risk.
  * Bars are UTC days (Databento ohlcv-1d, Sunday stubs folded) -- see TL-v0's caveats: 'next
    open' is the evening session, gapped-stop fills mostly bite on Mondays.
  * MTN: P&L on TN's held contract at $100/point; MTN listed 2024-03-25, so 2010-2021 describes
    the signal, not a tradable history. NG and 6J are sized in full contracts (most signals skip).
  * The 1% risk is of a FIXED $22,129 (no compounding). Roll legs are booked at the two contracts'
    closes on the roll session, two sides of friction per contract.
  * A3's thresholds come from the training bars only (mb.frame is holdout-cut before any bar exists);
    section 7 compares them with Amendment E.""")
    return "\n".join(L) + "\n", summary
