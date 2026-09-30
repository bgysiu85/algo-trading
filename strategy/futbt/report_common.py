#!/usr/bin/env python3
"""Report pieces shared by the CRUDELE-3S and BREIT-CAP backtests (sec 3 emissions, sec 4 verdict).

CODING NOTES for sec 4 wording that admits more than one reading (PRE-RUN, fixed here, written into
both registrations as an amendment before any run):
  * criterion 2 "both halves": split at the median ENTRY date of the verdict book's trades; each half
    is the sum of net (mid) of the trades that entered in it. An empty half fails.
  * criterion 4: bootstrap by market and by calendar year, 2,000 seeded resamples each (TL-v0's
    cluster_boot, seed 20260927), share of resamples with net > 0 must be >= 95% in each.
  * criterion 5: beats C1 on net AND on net per unit of realised volatility (TL-v0's measure).
  * criterion 7 is NOT READ (counts as not passed) when net <= 0.
  * criterion 9 (grid): cells with net > $0 at mid among the 27, need >= 18.
  * criterion 10: fewer than 150 trades -> the study is NOT READ, not failed.
  * ONE-MARKET BOOK (BREIT-CAP CL 4H): criteria 3 and 7 are read by calendar YEAR only (drop the top 1 /
    top 2 years; no year above 50%); criterion 4 by year only. Daily P&L for volatility is summed to
    one value per session (a 4H bar's timestamp + 6 h, normalised) so 252 annualisation stays valid.
Money: whole dollars, negatives in (brackets).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.tl_v0 import report as Rp
from strategy.tl_v0.report import (Book, cluster_boot, concentration, drop_top, money, net_per_vol,
                                   pct, years_span)
from strategy.tl_v0.spec import EQUITY, LEVELS

MIN_TRADES = 150
CELLS_NEEDED = 18
VERDICT = ("frac", EQUITY)
I22 = ("int", EQUITY)


def hdr(p, title):
    p("")
    p("=" * 100)
    p(title)
    p("=" * 100)


def num(v, dp=0):
    return f"{v:.{dp}f}" if v is not None and np.isfinite(v) else "n/a"


# ---------------------------------------------------------------------------
# one-market books: sessions instead of 4H bars
# ---------------------------------------------------------------------------

def to_sessions(out):
    """A MarketOut whose daily arrays are summed to one row per session (4H books)."""
    from strategy.futbt.engine import MarketOut
    d = pd.DatetimeIndex(out.dates)
    sess = (d + pd.Timedelta(hours=6)).normalize()
    uniq = pd.DatetimeIndex(sorted(set(sess)))
    pos = uniq.get_indexer(sess)
    daily = {}
    for k, arr in out.daily.items():
        agg = np.zeros((len(uniq), arr.shape[1]))
        np.add.at(agg, pos, arr)
        daily[k] = agg
    return MarketOut(out.market, out.trades, daily, out.counts, uniq, out.signal_counts, out.extra)


def half_split(b: Book):
    t = b.trades
    if not len(t):
        return None, 0.0, 0.0, 0, 0
    ent = pd.to_datetime(t["entry_date"])
    split = ent.sort_values().iloc[len(ent) // 2]
    m = ent < split
    return (split, float(t.loc[m, "net_mid"].sum()), float(t.loc[~m, "net_mid"].sum()),
            int(m.sum()), int((~m).sum()))


def by_market(b: Book, markets) -> pd.Series:
    if not len(b.trades):
        return pd.Series(0.0, index=list(markets))
    return b.trades.groupby("market")["net_mid"].sum().reindex(list(markets)).fillna(0.0)


def criteria(b: Book, c1: Book, c6: Rp.Criterion, grid: pd.DataFrame | None, markets, *,
             single: bool = False, friction_label: str = "IBKR") -> list:
    C = Rp.Criterion
    out = []
    mid, high = b.net("mid"), b.net("high")
    n = len(b.trades)
    out.append(C(1, f"net > $0 at mid friction ({friction_label})", money(mid).strip(), mid > 0))
    split, h1, h2, n1, n2 = half_split(b)
    out.append(C(2, "both halves > $0 (split at median entry date; empty half fails)",
                 f"{money(h1).strip()} ({n1} trades) / {money(h2).strip()} ({n2} trades), split "
                 f"{None if split is None else str(pd.Timestamp(split).date())}",
                 bool(n1 > 0 and n2 > 0 and h1 > 0 and h2 > 0)))
    by = b.by_year()
    if single:
        d1, d2 = drop_top(by, 1), drop_top(by, 2)
        out.append(C(3, "drop-top-1 and drop-top-2 YEARS still > $0 (one market: read by year)",
                     f"{money(d1).strip()} / {money(d2).strip()}", bool(d1 is not None and d2 is not None and d1 > 0 and d2 > 0)))
        byr = cluster_boot(by)
        out.append(C(4, "bootstrap (2,000) by year: net > 0 in >= 95% (one market: by year only)",
                     pct(byr["share_pos"]).strip(), bool(byr["share_pos"] >= 0.95)))
    else:
        bm = by_market(b, markets)
        d1, d2 = drop_top(bm, 1), drop_top(bm, 2)
        out.append(C(3, "drop-top-1 and drop-top-2 by market still > $0",
                     f"{money(d1).strip()} / {money(d2).strip()}", bool(d1 is not None and d2 is not None and d1 > 0 and d2 > 0)))
        bmk, byr = cluster_boot(bm), cluster_boot(by)
        out.append(C(4, "bootstrap (2,000) by market AND by year: net > 0 in >= 95% each",
                     f"{pct(bmk['share_pos']).strip()} / {pct(byr['share_pos']).strip()}",
                     bool(bmk["share_pos"] >= 0.95 and byr["share_pos"] >= 0.95)))
    c1n, c1v, bv = c1.net("mid"), net_per_vol(c1), net_per_vol(b)
    beats = mid > c1n and np.isfinite(bv) and np.isfinite(c1v) and bv > c1v
    out.append(C(5, "beats C1 Donchian 20/10 on net AND net per unit realised volatility",
                 f"{money(mid).strip()} vs {money(c1n).strip()}; {bv:.2f} vs {c1v:.2f}", bool(beats)))
    out.append(c6)
    ky, sy = concentration(by, mid)
    if single:
        out.append(C(7, "no single year > 50% of net (one market: read by year)",
                     "not read (net <= 0)" if sy is None else f"top year {ky} {pct(sy).strip()}",
                     None if sy is None else bool(sy <= 0.5)))
    else:
        km, sm = concentration(bm, mid)
        out.append(C(7, "no single year and no single market > 50% of net",
                     "not read (net <= 0)" if sy is None else
                     f"top year {ky} {pct(sy).strip()}, top market {km} {pct(sm).strip()}",
                     None if sy is None else bool(sy <= 0.5 and sm <= 0.5)))
    out.append(C(8, "still net > $0 at high friction", money(high).strip(), high > 0))
    if grid is None:
        out.append(C(9, f">= {CELLS_NEEDED} of 27 neighbour cells net > $0", "grid not run", None))
    else:
        npos = int((grid["net_mid"] > 0).sum())
        out.append(C(9, f">= {CELLS_NEEDED} of 27 neighbour cells net > $0 (mid friction)",
                     f"{npos} of {len(grid)}", bool(npos >= CELLS_NEEDED)))
    out.append(C(10, f"at least {MIN_TRADES} trades (fewer = NOT READ, not failed)", f"{n} trades",
                 bool(n >= MIN_TRADES)))
    return out


def verdict_lines(p, crit, ntrades, holdout_name) -> str:
    for c in crit:
        mark = "PASS" if c.passed else ("NOT READ" if c.passed is None else "FAIL")
        p(f"  {c.no:>2}. [{mark:8}] {c.text}: {c.value}")
    if ntrades < MIN_TRADES:
        v = f"NOT READ (only {ntrades} trades; criterion 10) -- neither passed nor failed"
    elif all(c.passed for c in crit):
        v = f"PASSES all ten -- {holdout_name} may be spent (once; sec 6)"
    else:
        failed = [c.no for c in crit if not c.passed]
        v = f"DOES NOT PASS (failed or not read: criteria {failed})"
        if not (crit[4].passed and crit[5].passed):
            v += "  -- criterion 5 and/or 6 failed: the study closes whatever else passes (sec 4)"
    p(f"  => {v}")
    return v


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------

def books_table(p, books: list[tuple[str, Book]]):
    p(f"{'book':<18}{'gross':>12}{'costs':>12}{'net low':>12}{'net mid':>12}{'net high':>12}{'mid/yr':>11}"
      f"{'trades':>8}{'W':>6}{'L':>6}{'win%':>6}{'avg win':>10}{'avg loss':>10}{'worst':>10}{'hold':>6}{'worst DD':>12}{'net/vol':>8}")
    rows = []
    for name, b in books:
        r = Rp.book_row(b)
        rows.append(dict(r, book=name))
        st = Rp.trade_stats(b.trades)
        costs = r["gross"] - r["net_mid"]
        p(f"{name:<18}{money(r['gross'])}{money(costs)}{money(r['net_low'])}{money(r['net_mid'])}"
          f"{money(r['net_high'])}{money(r['net_mid_per_yr'], 11)}{r['trades']:>8}{r['wins']:>6}{r['losses']:>6}"
          f"{pct(r['win_rate'], 6)}{money(st['avg_win'], 10)}{money(st['avg_loss'], 10)}{money(st['largest_loss'], 10)}"
          f"{num(r['median_hold']):>6}{money(-r['max_dd'])}{num(r['net_per_vol'], 2):>8}")
    return pd.DataFrame(rows)


def worst_streak(t: pd.DataFrame) -> int:
    if not len(t):
        return 0
    x = (t.sort_values(["entry_date", "exit_date"])["net_mid"] <= 0).to_numpy()
    best = cur = 0
    for v in x:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def group_table(p, t: pd.DataFrame, keys: list, title: str, equity=EQUITY):
    p(f"-- {title} --")
    if not len(t):
        p("  (no trades)")
        return
    t = t.copy()
    risk = (t["risk_frac"] * equity).replace(0, np.nan)
    t["R"] = t["net_mid"] / risk
    g = t.groupby(keys)
    df = pd.DataFrame({"trades": g.size(), "wins": g["net_mid"].apply(lambda s: int((s > 0).sum())),
                       "gross": g["gross"].sum(), "net_mid": g["net_mid"].sum(),
                       "avg_net": g["net_mid"].mean(), "avg_R": g["R"].mean(),
                       "median_hold": g["hold"].median()})
    df["win%"] = 100 * df["wins"] / df["trades"]
    p(f"{'':<22}{'trades':>8}{'wins':>6}{'win%':>6}{'gross':>12}{'net mid':>12}{'avg net':>10}{'avg R':>8}{'hold':>6}")
    for idx, r in df.iterrows():
        lab = " / ".join(str(i) for i in (idx if isinstance(idx, tuple) else (idx,)))
        p(f"{lab:<22}{int(r['trades']):>8}{int(r['wins']):>6}{r['win%']:>6.0f}{money(r['gross'])}"
          f"{money(r['net_mid'])}{money(r['avg_net'], 10)}{r['avg_R']:>8.2f}{r['median_hold']:>6.0f}")


def year_market_tables(p, cols: list[tuple[str, Book]], markets, *, single=False):
    yt = pd.DataFrame({k: b.by_year() for k, b in cols})
    p(f"{'year':<6}" + "".join(f"{k:>18}" for k in yt.columns))
    for y, r in yt.iterrows():
        p(f"{y:<6}" + "".join(money(v, 18) for v in r.to_numpy()))
    if not single:
        mt = pd.DataFrame({k: by_market(b, markets) for k, b in cols})
        p(f"{'market':<7}" + "".join(f"{k:>18}" for k in mt.columns))
        for m, r in mt.iterrows():
            p(f"{m:<7}" + "".join(money(v, 18) for v in r.to_numpy()))
    k0, b0 = cols[0]
    s, h1, h2, n1, n2 = half_split(b0)
    p(f"  {k0}: halves split at median entry date {None if s is None else pd.Timestamp(s).date()}: "
      f"{money(h1).strip()} ({n1} trades) / {money(h2).strip()} ({n2} trades)")
    if not single:
        bm = by_market(b0, markets)
        dt = [drop_top(bm, n) for n in (1, 2, 3)]
        bo, by = cluster_boot(bm), cluster_boot(b0.by_year())
        p(f"  {k0}: drop-top-1/2/3 markets {' / '.join(money(v).strip() for v in dt)}; boot by market >0 "
          f"{pct(bo['share_pos']).strip()} (p05 {money(bo['p05']).strip()}), by year >0 {pct(by['share_pos']).strip()} "
          f"(p05 {money(by['p05']).strip()})")


def sample_trades(p, t: pd.DataFrame, extra_cols: list[tuple[str, str, str]], n_show=20):
    """every 1/20th trade of the (fractional verdict) book, by entry date."""
    if not len(t):
        p("  none")
        return
    t = t.sort_values(["entry_date", "market"]).reset_index(drop=True)
    step = max(len(t) // n_show, 1)
    p(f"{len(t)} trades, every {step}th shown (adjusted prices; qty fractional; net at mid)")
    head = f"{'market':<7}{'side':>6}{'entry':>12}{'exit':>12}{'qty':>7}{'entry px':>11}{'stop px':>11}{'exit px':>11}{'why':>14}"
    for _, lab, _fmt in extra_cols:
        head += f"{lab:>8}"
    p(head + f"{'gross':>10}{'net $':>10}")
    for _, r in t.iloc[::step].head(n_show).iterrows():
        line = (f"{r['market']:<7}{'long' if r['direction'] > 0 else 'short':>6}"
                f"{str(pd.Timestamp(r['entry_date']).date()):>12}{str(pd.Timestamp(r['exit_date']).date()):>12}"
                f"{r['qty']:>7.2f}{r['entry_px']:>11.5g}{r['stop_init']:>11.5g}{r['exit_px']:>11.5g}{r['reason']:>14}")
        for col, _lab, fmt in extra_cols:
            v = r.get(col, "")
            line += f"{format(v, fmt) if v != '' and not (isinstance(v, float) and np.isnan(v)) else '':>8}"
        p(line + f"{money(r['gross'], 10)}{money(r['net_mid'], 10)}")


def grid_lines(p, grid, label_cols, centre: dict, verdict_net: float):
    p("".join(f"{c:>10}" for c in label_cols) + f"{'net mid':>12}{'trades':>8}")
    for _, r in grid.iterrows():
        p("".join(f"{r[c]:>10.4g}" for c in label_cols) + f"{money(r['net_mid'])}{int(r['trades']):>8}")
    npos = int((grid["net_mid"] > 0).sum())
    msg = f"share of cells positive: {npos / len(grid):.0%} ({npos} of {len(grid)})."
    m = np.ones(len(grid), bool)
    for k, v in centre.items():
        m &= np.isclose(grid[k].to_numpy(float), v)
    if m.any():
        d = float(grid[m]["net_mid"].iloc[0]) - verdict_net
        msg += f" Centre cell vs the verdict book: difference {d:+.4f} (must be ~0)."
    p(msg)


def ibkr_header(p):
    from strategy.futbt import costs_ibkr as CI
    p("Costs (W15-0033, IBKR, per contract per side; low = all-in fee, mid = fee + 1 tick, high = fee + 2 ticks):")
    p(f"  {'market':<7}{'vehicle':<9}{'tick $':>8}{'fee':>7}{'low':>8}{'mid':>8}{'high':>8}")
    for m, v, tk, fee, lo, mi, hi in CI.table():
        p(f"  {m:<7}{v:<9}{tk:>8.3f}{fee:>7.2f}{lo:>8.2f}{mi:>8.2f}{hi:>8.2f}")
    for k, v in CI.ASSUMED.items():
        p(f"  ASSUMED {k}: {v}")
    p("  Slippage is inside the levels (every fill); the old separate 1 tick on stop fills is dropped. "
      "Roll legs: two sides per contract.")
