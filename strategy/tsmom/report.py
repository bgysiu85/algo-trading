#!/usr/bin/env python3
"""The TSMOM section 3 report and the section 4 verdict, TRAINING SIDE ONLY.

REGISTERED_tsmom sections 3, 4 and 5; the readings this module needed are
amendment E (section 0.4), committed with this file BEFORE its first run.

WHAT IS READ, AND ON WHAT
-------------------------
Every root is cut by `engine.training_inputs` (-> `common.tsmom_holdout.
split_months`, the one implementation) before any series is built. Nothing
here can see 2022-01-01 onward; a test pins that.

The VERDICT (section 4) is read on ONE book, fixed before any return:
arm (b) MTN (G3), the k in {3,6,9,12} ensemble, five tranches, FRACTIONAL
sizing at E = $22,129. Fractional P/L and costs are both linear in E, so E
sets the dollar scale and nothing else. Arms (a) and (c) are scored the same
way and printed beside it, unranked; they do not feed the verdict.

Integer books at $22,129 / $100,000 / $500,000 are the capacity measurement of
section 5: reported, not scored. If the integer book at $22,129 has the
opposite sign to the fractional book, section 5 makes that the headline.

NOTHING IS RANKED. Every grid cell is printed, in registry order.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import common.tsmom_holdout as H
from common.report_fmt import acct
from strategy.tsmom.book import BookResult, _sides, run_book
from strategy.tsmom.engine import RootInputs, build_series, coverage, training_inputs
from strategy.tsmom.registry import (ALL_ROOTS, ANNUALISE, ENSEMBLE_KS, FRICTION,
                                     LOOKBACK_GRID, RATES_ARMS, TRADED_ARM,
                                     TRANCHE_DAYS, Root, book_roots)
from strategy.tsmom.roll import roll_volume_share

# --- fixed by amendment E, before the first run -------------------------------
EQUITY = 22_129.0                       # DUM215828 net liquidation (spec section 3)
EQUITIES = (22_129.0, 100_000.0, 500_000.0)   # section 5
LEVELS = ("low", "mid", "high")
N_BOOT = 2_000
SEED = 20260923
REBAL_DAYS = tuple(range(1, 22))        # section 3 item 10: all ~21 trading days
MIN_MONTHS = 60                         # section 4: < 60 months is not read
PORTFOLIO_VOL_REF = 0.12                # MOP p. 236: the book's realised ~12%
# Section 5's cap subsets: spec section 3's one-lot tables, computed from free
# data on 2026-09-17, BEFORE any data was bought or any return computed. They
# are NOT re-chosen from this run's realised volatilities (amendment E item 11).
CAP_SUBSETS = {"10%": ("NG", "6E", "6A", "6B", "6J"),
               "15%": ("RTY", "6E", "6A", "6B", "6J")}
VEHICLE = {n: r.vehicle for n, r in ALL_ROOTS.items()}


def money(v, w: int = 11) -> str:
    if v is None:
        return "n/a".rjust(w)
    return acct(float(v), w, 0)


def pct(v: float, w: int = 7, dp: int = 1) -> str:
    if v is None or not np.isfinite(v):
        return "n/a".rjust(w)
    return (acct(100.0 * float(v), w - 1, dp) + "%")


# --- the series, cut first ------------------------------------------------------

def training_series(inputs: dict[str, RootInputs]) -> tuple[dict[str, pd.DataFrame], dict]:
    """Held-contract series for every root, built from the TRAINING side only."""
    cut, held_back = training_inputs(inputs)
    series = {n: build_series(cut[n], ALL_ROOTS[n])[1] for n in cut}
    for n, s in series.items():
        if len(s) and s.index.max() >= pd.Timestamp(H.LOCK_FROM):
            raise H.HoldoutRefused(f"{n}: a locked session reached the report")
    return series, held_back


def book(series, roots: dict[str, Root], equity: float = EQUITY, **kw) -> BookResult:
    return run_book({n: series[n] for n in roots}, roots, equity=equity, **kw)


# --- measuring one book -----------------------------------------------------------

def first_live(b: BookResult) -> pd.Timestamp:
    any_live = b.live.any(axis=1)
    if not any_live.any():
        raise ValueError("no market is ever live in this book")
    return any_live.idxmax()


def window(frame: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    f = frame
    if start is not None:
        f = f.loc[f.index >= start]
    if end is not None:
        f = f.loc[f.index <= end]
    return f


@dataclass
class Measure:
    """One book, one sizing, one window. Money in USD."""
    gross: float
    net: dict               # level -> total
    by_year: pd.DataFrame   # rows year; cols gross, cost_<lvl>, net_<lvl>
    by_market: pd.DataFrame # rows market; gross, net_<lvl>, sides_roll, sides_reb
    daily_net_mid: pd.Series
    years: float
    start: pd.Timestamp
    end: pd.Timestamp
    realised_vol: float     # of daily net at mid, annualised, / equity
    ret_per_vol: float      # annualised mean / annualised std, daily net at mid
    max_dd: float           # worst peak-to-trough of cumulative net at mid, USD
    sides_roll_py: float
    sides_reb_py: float


def measure(b: BookResult, sizing: str, start=None, end=None) -> Measure:
    start = first_live(b) if start is None else start
    gross_f = window(b.pnl_frac if sizing == "frac" else b.pnl_int, start, end)
    end = gross_f.index[-1] if end is None else end
    sroll = window(b.sides[(sizing, "roll")], start, end)
    sreb = window(b.sides[(sizing, "rebalance")], start, end)
    years = (gross_f.index[-1] - gross_f.index[0]).days / 365.25
    yr = gross_f.index.year
    by_year = pd.DataFrame({"gross": gross_f.sum(axis=1).groupby(yr).sum()})
    by_market = pd.DataFrame({"gross": gross_f.sum()})
    net = {}
    for lvl in LEVELS:
        cost = (sroll + sreb) * FRICTION[lvl]
        n = gross_f - cost
        net[lvl] = float(n.to_numpy().sum())
        by_year[f"cost_{lvl}"] = cost.sum(axis=1).groupby(yr).sum()
        by_year[f"net_{lvl}"] = n.sum(axis=1).groupby(yr).sum()
        by_market[f"net_{lvl}"] = n.sum()
    by_market["sides_roll"] = sroll.sum()
    by_market["sides_reb"] = sreb.sum()
    daily = (gross_f - (sroll + sreb) * FRICTION["mid"]).sum(axis=1)
    sd = float(daily.std(ddof=1))
    mu = float(daily.mean())
    cum = daily.cumsum()
    dd = float((cum - cum.cummax()).min())
    return Measure(gross=float(gross_f.to_numpy().sum()), net=net, by_year=by_year,
                   by_market=by_market, daily_net_mid=daily, years=years,
                   start=gross_f.index[0], end=gross_f.index[-1],
                   realised_vol=sd * np.sqrt(ANNUALISE) / b.equity if sd > 0 else np.nan,
                   ret_per_vol=(mu * ANNUALISE) / (sd * np.sqrt(ANNUALISE)) if sd > 0 else np.nan,
                   max_dd=dd,
                   sides_roll_py=float(sroll.to_numpy().sum()) / years,
                   sides_reb_py=float(sreb.to_numpy().sum()) / years)


def halves(m: Measure) -> tuple[str, float, float]:
    """Section 4 criterion 2: split at the median month of the book's ACTIVE
    months, by `tsmom_holdout.describe` (the one implementation); not swept."""
    months = sorted({d.strftime("%Y-%m") for d in m.daily_net_mid.index})
    split = H.describe(months)["both_halves_split"]
    ym = m.daily_net_mid.index.strftime("%Y-%m")
    first = float(m.daily_net_mid[ym < split].sum())
    second = float(m.daily_net_mid[ym >= split].sum())
    return split, first, second


def drop_top(by_market_net: pd.Series, n: int):
    """Total net with the N largest-contributing markets' P/L removed (the
    book is not re-sized without them). None = n/a (N >= market count)."""
    if n >= len(by_market_net):
        return None
    return float(by_market_net.sort_values(ascending=False).iloc[n:].sum())


def cluster_boot(unit_totals: pd.Series, n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """Units (markets or years) drawn with replacement, as many as there are,
    every day of a drawn unit travelling with it. Share of resamples > 0."""
    v = unit_totals.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    tot = v[idx].sum(axis=1)
    return {"share_pos": float((tot > 0).mean()), "p05": float(np.percentile(tot, 5)),
            "p50": float(np.percentile(tot, 50)), "p95": float(np.percentile(tot, 95)),
            "units": len(v)}


def concentration(parts: pd.Series, total: float):
    """Largest single part's share of total net. None when total <= 0: the
    criterion is then not read and does not pass (amendment E item 7)."""
    if total <= 0:
        return None, None
    k = parts.idxmax()
    return k, float(parts.max() / total)


def live_months(b: BookResult) -> pd.Series:
    lv = b.live
    return lv.groupby(lv.index.to_period("M")).any().sum()


def position_vol(b: BookResult) -> pd.Series:
    """Per market: realised vol of daily P/L over its equal-weight capital
    share E/N (N = markets live that day), on days a position was carried.
    The ex-ante target is 40% times |mean sign| (a split vote is smaller)."""
    n_live = b.live.sum(axis=1).replace(0, np.nan)
    share = b.equity / n_live
    carried = b.pos_frac.shift(1).fillna(0.0) != 0
    out = {}
    for m in b.roots:
        r = (b.pnl_frac[m] / share)[carried[m]].dropna()
        out[m] = float(r.std(ddof=1) * np.sqrt(ANNUALISE)) if len(r) > 20 else np.nan
    return pd.Series(out)


# --- positions not produced by run_book (the one-lot book) ---------------------

def pnl_for_positions(b: BookResult, series, roots, pos: pd.DataFrame):
    """P/L and sides for an arbitrary position frame on b's master calendar,
    by the same arithmetic as run_book. A test holds this equal to run_book's
    own integer book, so the one-lot figures are not a second implementation
    that can drift."""
    names = b.roots
    master = b.pos_frac.index
    dP = np.column_stack([series[n]["dP"].fillna(0.0).reindex(master, fill_value=0.0)
                          .to_numpy() for n in names])
    rolled = np.column_stack([series[n]["rolled"].astype(bool)
                              .reindex(master, fill_value=False).to_numpy() for n in names])
    vpv = np.array([roots[n].vehicle_point_value for n in names])
    p = pos[names].to_numpy(dtype=float)
    prev = np.vstack([np.zeros((1, len(names))), p[:-1]])
    pnl = pd.DataFrame(prev * dP * vpv, index=master, columns=names)
    r, reb = _sides(prev, p, rolled)
    return (pnl, pd.DataFrame(r, index=master, columns=names),
            pd.DataFrame(reb, index=master, columns=names))


def one_lot_book(b: BookResult, series, roots) -> BookResult:
    """Spec section 3's forced one-lot book: +/-1 vehicle contract in the
    sign of the net sleeve target, flat when it is zero."""
    pos = np.sign(b.pos_frac)
    pnl, r, reb = pnl_for_positions(b, series, roots, pos)
    return BookResult(roots=b.roots, equity=b.equity, live=b.live, signal=b.signal,
                      pos_frac=b.pos_frac, pos_int=pos, pnl_frac=b.pnl_frac, pnl_int=pnl,
                      sides={("frac", "roll"): b.sides[("frac", "roll")],
                             ("frac", "rebalance"): b.sides[("frac", "rebalance")],
                             ("int", "roll"): r, ("int", "rebalance"): reb})


# --- the section 4 verdict -----------------------------------------------------------

@dataclass
class Criterion:
    n: int
    text: str
    value: str
    passed: bool


def criteria(m: Measure, bh: Measure, grid_net: dict, ens_common: float) -> list[Criterion]:
    split, h1, h2 = halves(m)
    bm = m.by_market["net_mid"]
    d1, d2 = drop_top(bm, 1), drop_top(bm, 2)
    bmk = cluster_boot(bm)
    byr = cluster_boot(m.by_year["net_mid"])
    ky, sy = concentration(m.by_year["net_mid"], m.net["mid"])
    km, sm = concentration(bm, m.net["mid"])
    med = float(np.median(list(grid_net.values())))
    out = [
        Criterion(1, "Positive after costs at mid friction ($1.25/side)",
                  f"${money(m.net['mid'], 0)}", m.net["mid"] > 0),
        Criterion(2, f"Both halves positive at mid (split {split}, not swept)",
                  f"${money(h1, 0)} / ${money(h2, 0)}", h1 > 0 and h2 > 0),
        Criterion(3, "drop-top-1 and drop-top-2 by market still positive",
                  f"${money(d1, 0)} / ${money(d2, 0)}",
                  d1 is not None and d2 is not None and d1 > 0 and d2 > 0),
        Criterion(4, "Cluster bootstrap by market: total > 0 in >= 95%",
                  f"{bmk['share_pos']:.1%} of {N_BOOT}", bmk["share_pos"] >= 0.95),
        Criterion(5, "Cluster bootstrap by year: total > 0 in >= 95%",
                  f"{byr['share_pos']:.1%} of {N_BOOT}", byr["share_pos"] >= 0.95),
        Criterion(6, "Beats buy-and-hold at mid, on net AND net per unit of realised vol",
                  f"${money(m.net['mid'], 0)} vs ${money(bh.net['mid'], 0)}; "
                  f"{m.ret_per_vol:.2f} vs {bh.ret_per_vol:.2f}",
                  m.net["mid"] > bh.net["mid"] and m.ret_per_vol > bh.ret_per_vol),
        Criterion(7, "No single year and no single market > 50% of net",
                  ("n/a: net not positive" if sy is None else
                   f"top year {ky} {sy:.0%}; top market {km} {sm:.0%}"),
                  sy is not None and sy <= 0.5 and sm <= 0.5),
        Criterion(8, "Ensemble not beaten by the median single-k spec (common window)",
                  f"${money(ens_common, 0)} vs median ${money(med, 0)}", ens_common >= med),
        Criterion(9, "Still positive at high friction ($2.50/side)",
                  f"${money(m.net['high'], 0)}", m.net["high"] > 0),
    ]
    return out


def beat_share(value: float, cells: dict) -> float:
    v = np.array(list(cells.values()), dtype=float)
    return float((value > v).mean())


# --- the whole report --------------------------------------------------------------

@dataclass
class Report:
    text: str
    verdict: bool
    headline: Measure
    crit: list
    books: dict


def build(inputs: dict[str, RootInputs], load_notes: dict | None = None,
          manifest: dict | None = None) -> Report:
    series, held_back = training_series(inputs)
    L: list[str] = []
    w = L.append

    # --- the books -----------------------------------------------------------
    arms = {a: book_roots(a) for a in RATES_ARMS}
    spec = {a: book(series, r) for a, r in arms.items()}
    bh = {a: book(series, r, signal_mode="long") for a, r in arms.items()}
    hr = arms[TRADED_ARM]
    head = spec[TRADED_ARM]
    M = {a: measure(spec[a], "frac") for a in arms}
    BH = {a: measure(bh[a], "frac", start=M[a].start) for a in arms}
    m = M[TRADED_ARM]

    grid = {k: book(series, hr, ks=(k,)) for k in LOOKBACK_GRID}
    common_start = max([first_live(head)] + [first_live(g) for g in grid.values()])
    grid_common = {k: measure(g, "frac", start=common_start).net["mid"] for k, g in grid.items()}
    ens_common = measure(head, "frac", start=common_start).net["mid"]
    grid_own = {k: measure(g, "frac") for k, g in grid.items()}
    skip12 = measure(book(series, hr, ks=(12,), skip_months=1), "frac")

    rebal = {d: measure(book(series, hr, tranche_days=(d,)), "frac", start=m.start)
             for d in REBAL_DAYS}

    ints = {e: {a: book(series, arms[a], equity=e) for a in arms} for e in EQUITIES}
    IM = {e: {a: measure(ints[e][a], "int", start=M[a].start) for a in arms} for e in EQUITIES}

    crit = criteria(m, BH[TRADED_ARM], grid_common, ens_common)
    verdict = all(c.passed for c in crit)

    # --- header ----------------------------------------------------------------
    w("TSMOM -- REGISTERED_tsmom section 3 report, TRAINING SIDE ONLY")
    w("=" * 78)
    if manifest:
        w(f"dataset {manifest.get('dataset')} (read from the archive manifest); "
          f"pulls: {len(manifest.get('pulls', []))}")
    w(f"holdout: LOCKED from {H.LOCK_FROM}; every root cut by split_months before any "
      "series was built. Ledger: " + ("UNSPENT" if H.read_ledger() is None else "SPENT"))
    w(f"verdict book: arm {TRADED_ARM} (G3), ensemble k={ENSEMBLE_KS}, tranches "
      f"{TRANCHE_DAYS}, FRACTIONAL sizing at E = ${EQUITY:,.0f}")
    w(f"window: {m.start.date()} .. {m.end.date()} ({m.years:.2f} years, from the first "
      "session any market is live)")
    w("money: USD; negatives in brackets. Gross is never the headline.")
    w("")

    # --- verdict ---------------------------------------------------------------
    w("SECTION 4 -- THE BAR (all nine, or the strategy is not carried forward)")
    w("-" * 78)
    for c in crit:
        w(f"  {c.n}. [{'PASS' if c.passed else 'FAIL'}] {c.text}")
        w(f"        {c.value}")
    w(f"  VERDICT: {'CARRIED FORWARD' if verdict else 'NOT CARRIED FORWARD'} "
      f"({sum(c.passed for c in crit)}/9 pass)")
    i22 = IM[EQUITIES[0]][TRADED_ARM]
    flip = np.sign(i22.net["mid"]) != np.sign(m.net["mid"])
    w(f"  Section 5 sign check: integer book at ${EQUITIES[0]:,.0f} nets "
      f"${money(i22.net['mid'], 0)} at mid vs fractional ${money(m.net['mid'], 0)} -- "
      + ("SIGN FLIPS: this is the headline (section 5)." if flip else "same sign."))
    w("")

    # --- item 1 + 3 ----------------------------------------------------------------
    w("ITEMS 1 & 3 -- NET AT THREE FRICTIONS, EVERY CALENDAR YEAR (verdict book)")
    w("-" * 78)
    w(f"{'year':>6}{'gross':>12}{'net low':>12}{'net mid':>12}{'net high':>12}"
      f"{'cost mid':>12}")
    for y, r in m.by_year.iterrows():
        w(f"{y:>6}{money(r.gross, 12)}{money(r.net_low, 12)}{money(r.net_mid, 12)}"
          f"{money(r.net_high, 12)}{money(r.cost_mid, 12)}")
    w(f"{'TOTAL':>6}{money(m.gross, 12)}{money(m.net['low'], 12)}{money(m.net['mid'], 12)}"
      f"{money(m.net['high'], 12)}{money(m.gross - m.net['mid'], 12)}")
    w(f"{'/yr':>6}{money(m.gross / m.years, 12)}{money(m.net['low'] / m.years, 12)}"
      f"{money(m.net['mid'] / m.years, 12)}{money(m.net['high'] / m.years, 12)}")
    w(f"  net mid per year = {pct(m.net['mid'] / m.years / EQUITY)} of ${EQUITY:,.0f}; "
      f"worst peak-to-trough (mid) ${money(m.max_dd, 0)} = {pct(m.max_dd / EQUITY)} of equity")
    w("")

    # --- item 2 -----------------------------------------------------------------
    split, h1, h2 = halves(m)
    w(f"ITEM 2 -- HALVES (split at {split}, the median active month; not swept)")
    w("-" * 78)
    w(f"  first half  ${money(h1)}    second half  ${money(h2)}    (net, mid)")
    w("")

    # --- per market / item 4 ----------------------------------------------------------
    bm = m.by_market
    lm = live_months(head)
    pv = position_vol(head)
    w("PER MARKET (verdict book, net at mid) -- and ITEM 4, drop-top-N by market")
    w("-" * 78)
    w(f"{'mkt':>5}{'vehicle':>8}{'live mo':>8}{'gross':>11}{'net mid':>11}{'share':>8}"
      f"{'sides/yr':>9}{'pos vol':>8}  note")
    for n in bm.index:
        r = bm.loc[n]
        share = r.net_mid / m.net["mid"] if m.net["mid"] > 0 else np.nan
        note = "" if lm[n] >= MIN_MONTHS else f"NOT READ: {int(lm[n])} < {MIN_MONTHS} months"
        w(f"{n:>5}{VEHICLE[n]:>8}{int(lm[n]):>8}{money(r.gross, 11)}{money(r.net_mid, 11)}"
          f"{pct(share, 8, 0)}{(r.sides_roll + r.sides_reb) / m.years:>9.1f}"
          f"{pct(pv[n], 8, 0)}  {note}")
    for k in (1, 2, 3):
        d = drop_top(bm["net_mid"], k)
        top = list(bm["net_mid"].sort_values(ascending=False).index[:k])
        w(f"  drop-top-{k} ({', '.join(top)}): " + ("n/a" if d is None else f"${money(d, 0)}"))
    w("  'pos vol' = realised vol of the market's P/L on its equal-weight capital share;"
      " the ex-ante target is 40% x |mean sign|.")
    w("")

    # --- items 5, 6 -------------------------------------------------------------------
    w(f"ITEMS 5 & 6 -- CLUSTER BOOTSTRAPS ({N_BOOT} resamples, seed {SEED}, net at mid)")
    w("-" * 78)
    for lab, s in (("by market", bm["net_mid"]), ("by year", m.by_year["net_mid"])):
        b_ = cluster_boot(s)
        w(f"  {lab:<10} units {b_['units']:>3}  total > 0 in {b_['share_pos']:.1%}   "
          f"5th ${money(b_['p05'], 0)}  median ${money(b_['p50'], 0)}  95th ${money(b_['p95'], 0)}")
    w("")

    # --- item 7 -------------------------------------------------------------------
    w("ITEM 7 -- BENCHMARKS, same markets, same vol scaling, same tranches and costs")
    w("-" * 78)
    w(f"{'book':<34}{'net mid':>12}{'net/yr':>11}{'ret/vol':>9}{'real vol':>10}")
    b_ = BH[TRADED_ARM]
    for lab, x in (("TSMOM ensemble (verdict book)", m), ("buy-and-hold (long every market)", b_)):
        w(f"{lab:<34}{money(x.net['mid'], 12)}{money(x.net['mid'] / x.years, 11)}"
          f"{x.ret_per_vol:>9.2f}{pct(x.realised_vol, 10)}")
    w(f"{'cash':<34}{money(0, 12)}{money(0, 11)}{0:>9.2f}{pct(0, 10)}")
    w("")

    # --- item 8 -------------------------------------------------------------------
    w("ITEM 8 -- REALISED PORTFOLIO VOLATILITY (net at mid) vs MOP's ~12%")
    w("-" * 78)
    w(f"  fractional, verdict book: {pct(m.realised_vol)}")
    for e in EQUITIES:
        w(f"  integer at ${e:>9,.0f}:   {pct(IM[e][TRADED_ARM].realised_vol)}")
    w("")

    # --- item 9 -------------------------------------------------------------------
    w("ITEM 9 -- TURNOVER, vehicle contract-sides per year")
    w("-" * 78)
    w(f"{'book':<28}{'rebalance':>11}{'roll':>9}{'cost mid/yr':>13}")
    w(f"{'fractional':<28}{m.sides_reb_py:>11.1f}{m.sides_roll_py:>9.1f}"
      f"{money((m.sides_reb_py + m.sides_roll_py) * FRICTION['mid'], 13)}")
    for e in EQUITIES:
        x = IM[e][TRADED_ARM]
        w(f"{'integer $' + format(e, ',.0f'):<28}{x.sides_reb_py:>11.1f}{x.sides_roll_py:>9.1f}"
          f"{money((x.sides_reb_py + x.sides_roll_py) * FRICTION['mid'], 13)}")
    w("")

    # --- item 10 ------------------------------------------------------------------
    w("ITEM 10 -- REBALANCE-DAY GRID: one sleeve on day d (net at mid, same window)")
    w("-" * 78)
    line = []
    for d, x in rebal.items():
        line.append(f"d{d:<2}{money(x.net['mid'], 9)}")
        if len(line) == 4:
            w("  " + "   ".join(line)); line = []
    if line:
        w("  " + "   ".join(line))
    rv = {d: x.net["mid"] for d, x in rebal.items()}
    w(f"  tranched spec ${money(m.net['mid'], 0)}: beats {beat_share(m.net['mid'], rv):.0%} "
      f"of the 21 single days; range ${money(min(rv.values()), 0)} .. "
      f"${money(max(rv.values()), 0)}; median ${money(float(np.median(list(rv.values()))), 0)}")
    w("")

    # --- item 11 ------------------------------------------------------------------
    w("ITEM 11 -- LOOKBACK GRID k in {1,3,6,9,12,24}, single-k books (net at mid)")
    w("-" * 78)
    w(f"  common window from {common_start.date()} (all seven books live)")
    w(f"{'cell':<22}{'own start':>12}{'own net':>12}{'own /yr':>11}{'common net':>12}")
    for k in LOOKBACK_GRID:
        x = grid_own[k]
        w(f"{'k=' + str(k):<22}{str(x.start.date()):>12}{money(x.net['mid'], 12)}"
          f"{money(x.net['mid'] / x.years, 11)}{money(grid_common[k], 12)}")
    w(f"{'ENSEMBLE {3,6,9,12}':<22}{str(m.start.date()):>12}{money(m.net['mid'], 12)}"
      f"{money(m.net['mid'] / m.years, 11)}{money(ens_common, 12)}")
    w(f"  the ensemble beat {beat_share(ens_common, grid_common):.0%} of single-k specs "
      "(common window)")
    w(f"  neighbours, reported only: k=12 alone is MOP's headline cell (above); "
      f"k=12 with a one-month skip nets ${money(skip12.net['mid'], 0)} "
      f"from {skip12.start.date()}")
    w("  k = 36 and 48 EXCLUDED (registered): with data from mid-2010 and the holdout"
      " at 2022, a 48-month lookback spends four of eleven in-sample years on warm-up.")
    w("")

    # --- item 13 ------------------------------------------------------------------
    w("ITEM 13 -- THE THREE RATES ARMS, SIDE BY SIDE, UNRANKED (registry order)")
    w("-" * 78)
    w(f"{'arm':<8}{'net low':>11}{'net mid':>11}{'net high':>11}{'B&H mid':>11}"
      f"{'ret/vol':>8}{'int $22k':>11}  criteria")
    for a in arms:
        x = M[a]
        gc = {k: measure(book(series, arms[a], ks=(k,)), "frac", start=common_start).net["mid"]
              for k in LOOKBACK_GRID} if a != TRADED_ARM else grid_common
        ec = measure(spec[a], "frac", start=common_start).net["mid"] if a != TRADED_ARM else ens_common
        ca = criteria(x, BH[a], gc, ec)
        w(f"{a:<8}{money(x.net['low'], 11)}{money(x.net['mid'], 11)}{money(x.net['high'], 11)}"
          f"{money(BH[a].net['mid'], 11)}{x.ret_per_vol:>8.2f}"
          f"{money(IM[EQUITIES[0]][a].net['mid'], 11)}  "
          f"{sum(c.passed for c in ca)}/9 "
          + "".join("P" if c.passed else "." for c in ca))
    w(f"  {TRADED_ARM} is the arm that would be traded (G3, chosen before any return);"
      " this table does not move it.")
    w("")

    # --- section 5 ------------------------------------------------------------------
    w("SECTION 5 -- CAPACITY (measured, not scored)")
    w("-" * 78)
    w(f"{'book':<22}{'net low':>11}{'net mid':>11}{'net high':>11}{'real vol':>9}"
      f"{'max DD':>11}{'mkts held':>10}")
    w(f"{'fractional @ $22,129':<22}{money(m.net['low'], 11)}{money(m.net['mid'], 11)}"
      f"{money(m.net['high'], 11)}{pct(m.realised_vol, 9)}{money(m.max_dd, 11)}"
      f"{len(bm):>10}")
    for e in EQUITIES:
        x = IM[e][TRADED_ARM]
        held = int((window(ints[e][TRADED_ARM].pos_int, m.start) != 0).any().sum())
        w(f"{'integer @ $' + format(e, ',.0f'):<22}{money(x.net['low'], 11)}"
          f"{money(x.net['mid'], 11)}{money(x.net['high'], 11)}{pct(x.realised_vol, 9)}"
          f"{money(x.max_dd, 11)}{held:>10}")
    w("")
    w("  the price of granularity, per market: net at mid, fractional scaled to E vs integer at E")
    w(f"{'mkt':>5}" + "".join(f"{'frac $' + format(e / 1000, '.0f') + 'k':>11}"
                                f"{'int $' + format(e / 1000, '.0f') + 'k':>11}" for e in EQUITIES)
      + f"{'% sess held@22k':>16}")
    for n in bm.index:
        row = f"{n:>5}"
        for e in EQUITIES:
            row += money(bm.at[n, "net_mid"] * e / EQUITY, 11)
            row += money(IM[e][TRADED_ARM].by_market.at[n, "net_mid"], 11)
        held = window(ints[EQUITIES[0]][TRADED_ARM].pos_int[n], m.start)
        row += f"{(held != 0).mean():>15.0%}"
        w(row)
    w("")
    w("  cap subsets at $22,129 (spec section 3's one-lot tables, fixed 2026-09-17, "
      "NOT re-chosen here)")
    w(f"{'subset':<34}{'book':<14}{'net mid':>11}{'net high':>11}{'real vol':>9}{'max DD':>11}")
    for cap, names in CAP_SUBSETS.items():
        roots = {n: ALL_ROOTS[n] for n in names}
        sb = book(series, roots, equity=EQUITY)
        lab = f"{cap}: " + ",".join(VEHICLE[n] for n in names)
        for kind, bb in (("vol-targeted", sb), ("one-lot", one_lot_book(sb, series, roots))):
            x = measure(bb, "int", start=m.start)
            w(f"{lab:<34}{kind:<14}{money(x.net['mid'], 11)}{money(x.net['high'], 11)}"
              f"{pct(x.realised_vol, 9)}{money(x.max_dd, 11)}")
            lab = ""
    w("")

    # --- item 12 + diagnostics ------------------------------------------------------
    w("ITEM 12 -- COVERAGE, TRAINING SIDE (same pass as the P/L)")
    w("-" * 78)
    cov = coverage(inputs)
    w(cov.to_string())
    w("")
    w("AMENDMENT C DIAGNOSTIC -- held contract's share of root volume on roll sessions "
      "(selects nothing)")
    w("-" * 78)
    cut, _ = training_inputs(inputs)
    w(f"{'root':>5}{'rolls':>7}{'median':>8}{'10th pct':>10}{'min':>7}")
    for n in ALL_ROOTS:
        if n not in cut or cut[n].volumes is None:
            continue
        s = series[n]
        rv_ = roll_volume_share(cut[n].volumes, s)["share"].dropna()
        if len(rv_):
            w(f"{n:>5}{len(rv_):>7}{rv_.median():>8.0%}{rv_.quantile(0.1):>10.0%}{rv_.min():>7.0%}")
    w("")
    if load_notes:
        w("LOAD NOTES (archive.py)")
        w("-" * 78)
        for n, note in load_notes.items():
            w(f"  {n:>4}: {note.get('bar_rows', '?')} bar rows, {note.get('unmapped_rows', '?')} "
              f"unmapped, {note.get('sunday_rows_dropped', '?')} Sunday rows dropped, "
              f"{len(note.get('expiration_revisions', []))} expiry revisions")
        w("")
    w("Nothing above is ranked. The grids are the distribution the registered spec sits"
      " in, not a menu (section 7).")
    return Report(text="\n".join(L), verdict=verdict, headline=m, crit=crit,
                  books={"spec": head, "bh": bh[TRADED_ARM],
                         "int": {e: ints[e][TRADED_ARM] for e in EQUITIES}})
