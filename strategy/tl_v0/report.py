#!/usr/bin/env python3
"""The section 3 report, the section 4 verdict, and W01-0005's reported-only
Davey figures. TRAINING SIDE ONLY (bars.py cuts the holdout before anything).

WHICH BOOK THE VERDICT IS READ ON (Amendment B, PRE-RUN)
---------------------------------------------------------
Section 4 says "ensemble spec, training sample" but not which sizing. As in
TSMOM (the predecessor on the same markets), the verdict is read on the
FRACTIONAL book at $22,129 (every trade risks exactly 1%, split 1/3 per pivot
size), and the INTEGER book at $22,129 is printed beside every verdict line.
If the two disagree in sign on net at mid friction, that is the headline.
Integer books at $100k and $500k are capacity readings, reported only.

WHAT IS COMPUTED ON WHAT
------------------------
  * totals, per-market totals and drop-top-N: from the trade list
  * calendar years, both halves, realised volatility, drawdown: from the
    DAILY mark-to-market (pnl.daily), which sums to the trade list exactly
  * halves: split at the median training session over all markets, from
    common.tl_v0_holdout.describe (the one implementation); not swept
  * realised volatility: std of the book's daily net x sqrt(252), in $;
    "net per unit of realised volatility" = net per year / that
  * bootstraps: 2,000 seeded resamples, markets (or calendar years) drawn with
    replacement, as many as there are

NOTHING IS RANKED. Rows print in registry order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import common.tl_v0_holdout as H
from strategy.tl_v0.spec import (DAVEY_DD_PAUSE, EQUITIES, EQUITY, LEVELS, MARKETS, MC_PATHS,
                                 N_BOOT, PIVOT_SIZES, RISK_PCT, SEED)

VERDICT = ("frac", EQUITY)
ANN = 252


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------

def money(v, w: int = 12) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a".rjust(w)
    s = f"${abs(v):,.0f}"
    return (f"({s})" if v < 0 else f" {s} ").rjust(w)


def pct(v, w: int = 7) -> str:
    if v is None or not np.isfinite(v):
        return "n/a".rjust(w)
    return f"{100 * v:.0f}%".rjust(w)


# ---------------------------------------------------------------------------
# books
# ---------------------------------------------------------------------------

BOOKS: tuple[tuple[str, str], ...] = (
    ("v0", "ens"), ("v0", "R3"), ("v0", "R5"), ("v0", "R8"),
    ("v0-rev", "ens"), ("v0-rev", "R3"), ("v0-rev", "R5"), ("v0-rev", "R8"),
    ("C1", "single"), ("C2", "ens"), ("C3|v0", "single"), ("C3|v0-rev", "single"),
)


def _members(spec: str, cut: str) -> list[tuple[str, int, str]]:
    """(spec, R, share) sleeves a book is the sum of."""
    if cut == "ens":
        return [(spec, R, "sleeve") for R in PIVOT_SIZES]
    if cut.startswith("R"):
        return [(spec, int(cut[1:]), "alone")]
    return [(spec, 0, "single")]


@dataclass
class Book:
    spec: str
    cut: str
    sizing: str
    equity: float
    trades: pd.DataFrame
    daily: dict                                   # level -> DataFrame(date x market)
    calendar: pd.DatetimeIndex
    notes: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        sz = "fractional" if self.sizing == "frac" else "integer"
        return f"{self.spec} {self.cut} | {sz} @ ${self.equity:,.0f}"

    def net(self, lv="mid") -> float:
        return float(self.trades["net_" + lv].sum()) if len(self.trades) else 0.0

    def gross(self) -> float:
        return float(self.trades["gross"].sum()) if len(self.trades) else 0.0

    def series(self, lv="mid") -> pd.Series:
        return self.daily[lv].sum(axis=1)

    def by_market(self, lv="mid") -> pd.Series:
        s = (self.trades.groupby("market")["net_" + lv].sum() if len(self.trades)
             else pd.Series(dtype=float))
        return s.reindex([m for m in MARKETS if m in self.daily[lv].columns]).fillna(0.0)

    def by_year(self, lv="mid") -> pd.Series:
        s = self.series(lv)
        return s.groupby(s.index.year).sum()


def build_book(runs: list, spec: str, cut: str, sizing: str, equity: float,
               calendar: pd.DatetimeIndex) -> Book:
    mem = _members(spec, cut)
    tr, per_level = [], {lv: {} for lv in LEVELS}
    for r in runs:
        t = r.trades
        if len(t):
            mask = np.zeros(len(t), bool)
            for (sp, R, share) in mem:
                mask |= ((t["spec"] == sp) & (t["R"] == R) & (t["share"] == share)).to_numpy()
            mask &= ((t["sizing"] == sizing) & (t["equity"] == equity)).to_numpy()
            tr.append(t[mask])
        acc = None
        for (sp, R, share) in mem:
            arr = r.daily.get((sp, R, share, sizing, equity))
            if arr is None:
                continue
            acc = arr.copy() if acc is None else acc + arr
        if acc is None:
            continue
        for i, lv in enumerate(LEVELS):
            per_level[lv][r.market] = pd.Series(acc[:, i], index=r.dates)
    daily = {lv: pd.DataFrame(per_level[lv]).reindex(calendar).fillna(0.0) for lv in LEVELS}
    trades = pd.concat(tr, ignore_index=True) if tr else pd.DataFrame()
    return Book(spec, cut, sizing, equity, trades, daily, calendar)


# ---------------------------------------------------------------------------
# measures
# ---------------------------------------------------------------------------

def years_span(cal: pd.DatetimeIndex) -> float:
    return max((cal[-1] - cal[0]).days / 365.25, 1e-9)


def halves(b: Book, lv="mid") -> tuple[str, float, float]:
    split = H.describe([d.strftime("%Y-%m-%d") for d in b.calendar])["both_halves_split"]
    s = b.series(lv)
    cut = pd.Timestamp(split)
    return split, float(s[s.index < cut].sum()), float(s[s.index >= cut].sum())


def drop_top(by_market: pd.Series, n: int):
    if n >= len(by_market):
        return None
    return float(by_market.sort_values(ascending=False).iloc[n:].sum())


def cluster_boot(units: pd.Series, n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    v = units.to_numpy(dtype=float)
    if len(v) == 0:
        return {"share_pos": np.nan, "p05": np.nan, "p50": np.nan, "p95": np.nan, "units": 0}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    tot = v[idx].sum(axis=1)
    return {"share_pos": float((tot > 0).mean()), "p05": float(np.percentile(tot, 5)),
            "p50": float(np.percentile(tot, 50)), "p95": float(np.percentile(tot, 95)),
            "units": len(v)}


def realised_vol(b: Book, lv="mid") -> float:
    s = b.series(lv)
    sd = float(s.std(ddof=1)) if len(s) > 1 else np.nan
    return sd * np.sqrt(ANN) if sd > 0 else np.nan


def net_per_vol(b: Book, lv="mid") -> float:
    v = realised_vol(b, lv)
    return (b.net(lv) / years_span(b.calendar)) / v if v and np.isfinite(v) else np.nan


def max_drawdown(values: np.ndarray) -> float:
    """Worst peak-to-trough fall of a cumulative $ path that starts at 0."""
    if len(values) == 0:
        return 0.0
    eq = np.r_[0.0, np.cumsum(values)]
    return float(np.max(np.maximum.accumulate(eq) - eq))


def concentration(parts: pd.Series, total: float):
    if total <= 0 or len(parts) == 0:
        return None, None
    return parts.idxmax(), float(parts.max() / total)


def trade_stats(t: pd.DataFrame, lv="mid") -> dict:
    if not len(t):
        return {"n": 0, "wins": 0, "losses": 0, "win_rate": np.nan, "avg_win": np.nan,
                "avg_loss": np.nan, "median_hold": np.nan, "largest_win": np.nan,
                "largest_loss": np.nan}
    x = t["net_" + lv]
    w, lo = x[x > 0], x[x <= 0]
    return {"n": len(x), "wins": len(w), "losses": len(lo), "win_rate": len(w) / len(x),
            "avg_win": float(w.mean()) if len(w) else np.nan,
            "avg_loss": float(lo.mean()) if len(lo) else np.nan,
            "median_hold": float(t["hold"].median()), "largest_win": float(x.max()),
            "largest_loss": float(x.min())}


# ---------------------------------------------------------------------------
# section 4
# ---------------------------------------------------------------------------

@dataclass
class Criterion:
    no: int
    text: str
    value: str
    passed: bool | None          # None = not read (counts as not passed)


def criteria(b: Book, c1: Book, singles: dict[str, Book]) -> list[Criterion]:
    out = []
    mid, high = b.net("mid"), b.net("high")
    out.append(Criterion(1, "net > $0 at mid friction", money(mid).strip(), mid > 0))
    split, h1, h2 = halves(b)
    out.append(Criterion(2, f"both halves > $0 (split {split}; an empty half is $0 and fails)",
                         f"{money(h1).strip()} / {money(h2).strip()}", (h1 > 0 and h2 > 0)))
    bm = b.by_market()
    d1, d2 = drop_top(bm, 1), drop_top(bm, 2)
    out.append(Criterion(3, "drop-top-1 and drop-top-2 by market > $0",
                         f"{money(d1).strip()} / {money(d2).strip()}",
                         (d1 is not None and d2 is not None and d1 > 0 and d2 > 0)))
    bmk, byr = cluster_boot(bm), cluster_boot(b.by_year())
    out.append(Criterion(4, "bootstrap by market AND by year: total > 0 in >= 95%",
                         f"{pct(bmk['share_pos']).strip()} / {pct(byr['share_pos']).strip()}",
                         (bmk["share_pos"] >= 0.95 and byr["share_pos"] >= 0.95)))
    c1n, c1v = c1.net("mid"), net_per_vol(c1)
    bv = net_per_vol(b)
    beats = mid > c1n and np.isfinite(bv) and np.isfinite(c1v) and bv > c1v
    out.append(Criterion(5, "beats C1 Donchian at mid on net AND net per unit realised vol",
                         f"{money(mid).strip()} vs {money(c1n).strip()}; "
                         f"{bv:.2f} vs {c1v:.2f}", bool(beats)))
    ky, sy = concentration(b.by_year(), mid)
    km, sm = concentration(bm, mid)
    ok6 = None if sy is None else (sy <= 0.5 and sm <= 0.5)
    out.append(Criterion(6, "no single year / market > 50% of net",
                         "not read (net <= 0)" if sy is None else
                         f"top year {ky} {pct(sy).strip()}, top market {km} {pct(sm).strip()}", ok6))
    sn = {k: v.net("mid") for k, v in singles.items()}
    med = float(np.median(list(sn.values()))) if sn else np.nan
    out.append(Criterion(7, "ensemble not beaten by the median single pivot size",
                         f"{money(mid).strip()} vs median {money(med).strip()} "
                         f"({', '.join(f'{k} {money(v).strip()}' for k, v in sn.items())})",
                         bool(np.isfinite(med) and mid >= med)))
    out.append(Criterion(8, "still > $0 at high friction", money(high).strip(), high > 0))
    return out


# ---------------------------------------------------------------------------
# Davey (W01-0005): reported only, never scored
# ---------------------------------------------------------------------------

def davey(b: Book, lv="mid", equity: float = EQUITY, paths: int = MC_PATHS,
          seed: int = SEED) -> dict:
    t = b.trades.sort_values(["exit_date", "entry_date"]) if len(b.trades) else b.trades
    x = t["net_" + lv].to_numpy(dtype=float) if len(t) else np.array([])
    out = {"trades": len(x)}
    if len(x) == 0:
        return out
    rng = np.random.default_rng(seed)
    draws = x[rng.integers(0, len(x), size=(paths, len(x)))]
    eq = np.concatenate([np.zeros((paths, 1)), np.cumsum(draws, axis=1)], axis=1)
    dd = (np.maximum.accumulate(eq, axis=1) - eq).max(axis=1)
    out.update(mc_dd_p50=float(np.percentile(dd, 50)), mc_dd_p95=float(np.percentile(dd, 95)),
               p_dd_30=float((dd >= 0.30 * equity).mean()), p_dd_50=float((dd >= 0.50 * equity).mean()))
    # the actual (training) trade sequence
    path = np.r_[0.0, np.cumsum(x)]
    under = np.maximum.accumulate(path) - path
    out["actual_dd"] = float(under.max())
    pause = DAVEY_DD_PAUSE * equity
    hit = np.nonzero(under[1:] >= pause)[0]
    out["pause_level"] = pause
    out["pause_first"] = str(pd.Timestamp(t["exit_date"].iloc[hit[0]]).date()) if hit.size else None
    starts = np.nonzero((under[1:] >= pause) & (np.r_[0.0, under[1:-1]] < pause))[0]
    out["pause_episodes"] = int(starts.size)
    q = out["mc_dd_p95"]
    hq = np.nonzero(under[1:] >= q)[0]
    out["quit_p95_first"] = str(pd.Timestamp(t["exit_date"].iloc[hq[0]]).date()) if hq.size else None
    losses = x <= 0
    run, streaks, first3 = 0, 0, None
    for i, isl in enumerate(losses):
        run = run + 1 if isl else 0
        if run == 3:
            streaks += 1
            if first3 is None:
                first3 = str(pd.Timestamp(t["exit_date"].iloc[i]).date())
    out["three_loss_events"] = streaks
    out["three_loss_first"] = first3
    return out


INCUBATION = """\
Incubation / paper-trading recommendation (design note; W01-0005 scope item 3;
NOT part of the verdict):
  * Only a rule set that PASSES section 4 on training AND its holdout (v0-rev
    only may spend it) is incubated. Nothing here is a reason to trade it.
  * Paper-trade the integer book at the live account size (MES/M2K/MCL/MGC/SIL/
    MHG/M6A/M6B/M6E/MTN micros; NG and 6J only if they size) for 6 months or 20
    closed trades, whichever is LATER, on daily closes, orders at the next open.
  * PASS condition, written before incubation starts: (a) net after actual
    fees >= $0; (b) worst drawdown below the MC 50th-percentile figure above;
    (c) every fill within one tick of the rule's price, or the gap-open price
    when the market opened through the stop; (d) no signal missed or taken
    that the engine, re-run over the same dates, would not have taken.
  * Quit points while live: stop and review after 3 consecutive losing
    trades; pause new entries at a 10% drawdown ($2,213 at $22,129); stop
    trading the method at the MC 95th-percentile drawdown above.
"""


# ---------------------------------------------------------------------------
# the text report
# ---------------------------------------------------------------------------

def _hdr(p, title):
    p("")
    p("=" * 100)
    p(title)
    p("=" * 100)


def _num(v, dp: int) -> str:
    return f"{v:.{dp}f}" if v is not None and np.isfinite(v) else "n/a"


def book_row(b: Book) -> dict:
    st = trade_stats(b.trades)
    yrs = years_span(b.calendar)
    return {"book": f"{b.spec} {b.cut}", "sizing": b.sizing, "equity": b.equity,
            "gross": b.gross(), "net_low": b.net("low"), "net_mid": b.net("mid"),
            "net_high": b.net("high"), "net_mid_per_yr": b.net("mid") / yrs,
            "trades": st["n"], "wins": st["wins"], "losses": st["losses"],
            "win_rate": st["win_rate"], "avg_win": st["avg_win"], "avg_loss": st["avg_loss"],
            "median_hold": st["median_hold"], "max_dd": max_drawdown(b.series("mid").to_numpy()),
            "realised_vol": realised_vol(b), "net_per_vol": net_per_vol(b)}


def render(runs: list, calendar: pd.DatetimeIndex, coverage: pd.DataFrame, *,
           scoped: bool, c3_hold: dict, header_notes: list[str]) -> tuple[str, pd.DataFrame]:
    L = []
    p = L.append
    books = {}
    for spec, cut in BOOKS:
        for sizing, eq in (("frac", EQUITY),) + tuple(("int", e) for e in EQUITIES):
            books[(spec, cut, sizing, eq)] = build_book(runs, spec, cut, sizing, eq, calendar)
    V = lambda spec, cut, sz=VERDICT: books[(spec, cut, sz[0], sz[1])]
    I22 = ("int", EQUITY)

    p("TL-v0 / TL-v0-rev STEP-4 BACKTEST -- REGISTERED_tl_v0.md sections 3-4 (W15-0014)")
    p("TRAINING SIDE ONLY: sessions from 2010-06-01 to before 2022-01-01, cut by")
    p("common.tl_v0_holdout.split_dates before any bar was built. Nothing is ranked.")
    if scoped:
        p("")
        p("!" * 100)
        p("SCOPED RUN (--markets): NOT THE REGISTERED RESULT. Read nothing below as the verdict.")
        p("!" * 100)
    for n in header_notes:
        p(n)
    p(f"Years in sample: {years_span(calendar):.2f}  ({calendar[0].date()} .. {calendar[-1].date()})")
    p("Money: whole dollars, negatives in (brackets). Friction per contract per side: "
      "low $0.50 / mid $1.25 / high $2.50, + 1 tick on every stop fill.")

    # ---- verdict --------------------------------------------------------
    singles = lambda rs: {f"R{R}": V(rs, f"R{R}") for R in PIVOT_SIZES}
    for rs, role in (("v0-rev", "HOLDOUT CANDIDATE -- its verdict decides whether the holdout is spent"),
                     ("v0", "reported neighbour -- scored on the same bar, cannot spend the holdout")):
        _hdr(p, f"1. SECTION 4 VERDICT -- {rs} ensemble, fractional @ ${EQUITY:,.0f}, mid friction ({role})")
        crit = criteria(V(rs, "ens"), V("C1", "single"), singles(rs))
        for c in crit:
            mark = "PASS" if c.passed else ("NOT READ" if c.passed is None else "FAIL")
            p(f"  {c.no}. [{mark:8}] {c.text}: {c.value}")
        allpass = all(c.passed for c in crit)
        p(f"  => {rs}: {'PASSES all eight' if allpass else 'DOES NOT PASS'}"
          + ("" if crit[4].passed else "  (criterion 5 failed: closes the study whatever else passes)"))
        fi, ii = V(rs, "ens").net("mid"), V(rs, "ens", I22).net("mid")
        nint = len(V(rs, "ens", I22).trades)
        flag = ("   <-- the integer book made NO trades at this size (every signal skipped)" if nint == 0
                else "   <-- OPPOSITE SIGNS: this is the headline (Amendment B)"
                if np.sign(fi) * np.sign(ii) < 0 else "")
        p(f"  Integer book @ ${EQUITY:,.0f} beside it: net at mid {money(fi).strip()} fractional vs "
          f"{money(ii).strip()} integer ({nint} trades){flag}")

    # ---- all books -------------------------------------------------------
    rows = [book_row(b) for b in books.values()]
    summary = pd.DataFrame(rows)
    for sz, title in ((VERDICT, "fractional"), (I22, "integer")):
        _hdr(p, f"2. EVERY BOOK, {title} sizing @ ${EQUITY:,.0f} -- registry order, unranked")
        p(f"{'book':<18}{'gross':>12}{'net low':>12}{'net mid':>12}{'net high':>12}{'mid/yr':>11}"
          f"{'trades':>8}{'W':>6}{'L':>6}{'win%':>6}{'hold':>6}{'worst DD':>12}{'$vol/yr':>11}{'net/vol':>8}")
        for spec, cut in BOOKS:
            r = book_row(books[(spec, cut, sz[0], sz[1])])
            p(f"{r['book']:<18}{money(r['gross'])}{money(r['net_low'])}{money(r['net_mid'])}"
              f"{money(r['net_high'])}{money(r['net_mid_per_yr'], 11)}{r['trades']:>8}{r['wins']:>6}"
              f"{r['losses']:>6}{pct(r['win_rate'], 6)}{_num(r['median_hold'], 0):>6}"
              f"{money(-r['max_dd'])}{money(r['realised_vol'], 11)}{_num(r['net_per_vol'], 2):>8}")
    p("C3|v0 / C3|v0-rev hold H sessions = the median hold of that rule set's ensemble trades: "
      + ", ".join(f"{k} H={v}" for k, v in c3_hold.items()))

    # ---- years and halves --------------------------------------------------
    _hdr(p, "3. EVERY CALENDAR YEAR, net at mid friction (fractional @ $22,129), and both halves")
    cols = [("v0", "ens"), ("v0-rev", "ens"), ("C1", "single"), ("C2", "ens"),
            ("C3|v0", "single"), ("C3|v0-rev", "single")]
    yt = pd.DataFrame({f"{s} {c}": V(s, c).by_year() for s, c in cols})
    p(f"{'year':<6}" + "".join(f"{k:>14}" for k in yt.columns))
    for y, r in yt.iterrows():
        p(f"{y:<6}" + "".join(money(v, 14) for v in r.to_numpy()))
    for s, c in cols:
        sp, h1, h2 = halves(V(s, c))
        p(f"  halves {s} {c}: before {sp} {money(h1).strip()}, from {sp} {money(h2).strip()}")

    # ---- markets -----------------------------------------------------------
    _hdr(p, "4. BY MARKET, net at mid (fractional @ $22,129); drop-top-N; cluster bootstraps")
    mt = pd.DataFrame({f"{s} {c}": V(s, c).by_market() for s, c in cols})
    p(f"{'market':<7}" + "".join(f"{k:>14}" for k in mt.columns))
    for m, r in mt.iterrows():
        p(f"{m:<7}" + "".join(money(v, 14) for v in r.to_numpy()))
    for s, c in cols:
        b = V(s, c)
        bm = b.by_market()
        dt = [drop_top(bm, n) for n in (1, 2, 3)]
        bk, by = cluster_boot(bm), cluster_boot(b.by_year())
        p(f"  {s} {c}: drop-top-1/2/3 {' / '.join(money(v).strip() for v in dt)}; "
          f"boot by market >0 {pct(bk['share_pos']).strip()} (p05 {money(bk['p05']).strip()}), "
          f"by year >0 {pct(by['share_pos']).strip()} (p05 {money(by['p05']).strip()})")

    # ---- counts ------------------------------------------------------------
    _hdr(p, "5. COUNTS (summed over markets and pivot sizes; per sleeve walk)")
    cnt = pd.concat([r.counts for r in runs], ignore_index=True)
    keep = ["breaks", "signals", "htf_blocked", "ignored_in_position", "reversals",
            "reversal_blocked_flat", "voided", "skipped_size", "no_stop", "unfilled_at_end", "entries"]
    for sz, eq in (VERDICT, I22):
        sub = cnt[(cnt["sizing"] == sz) & (cnt["equity"] == eq) & cnt["spec"].isin(["v0", "v0-rev", "C1", "C2"])]
        g = sub.groupby(["spec", "share"])[keep].sum()
        p(f"-- {sz} @ ${eq:,.0f} --")
        p(g.to_string())
    p("(skipped_size at integer @ $22,129: 'sleeve' rows risk 1/3 of 1% each; 'alone' rows risk the full 1%.)")

    # ---- capacity ----------------------------------------------------------
    _hdr(p, "6. INTEGER SIZING AT $22,129 / $100,000 / $500,000 (capacity; reported, not scored)")
    p(f"{'book':<18}" + "".join(f"{'@ $' + format(int(e), ','):>16}" for e in EQUITIES)
      + f"{'fractional R':>16}")
    for spec, cut in BOOKS:
        vals = [books[(spec, cut, 'int', e)].net("mid") for e in EQUITIES]
        rsum = books[(spec, cut, "frac", EQUITY)].net("mid") / (RISK_PCT * EQUITY)
        p(f"{spec + ' ' + cut:<18}" + "".join(money(v, 16) for v in vals) + f"{rsum:>15.1f}R")
    p("Fractional R = fractional net at mid / 1% of $22,129 (one full-risk trade = 1R).")

    # ---- 5.1 re-check ------------------------------------------------------
    _hdr(p, "7. SECTION 5.1 RE-CHECK ON THESE BARS (information; G1 was read on the pre-flight)")
    t = pd.concat([r.trades for r in runs], ignore_index=True)
    rev = t[(t["spec"] == "v0-rev") & (t["share"] == "alone") & (t["sizing"] == "frac")].copy()
    if len(rev):
        mult = rev["market"].map(lambda m: MARKETS[m].mult)
        rev["stop_usd"] = (rev["entry_px"] - rev["stop_init"]).abs() * mult
        rev["ok2"] = np.floor(0.02 * 22_000 / rev["stop_usd"]) >= 1
        g = rev.groupby("market")["ok2"].agg(["size", "mean"])
        n_clear = int((g["mean"] >= 0.5).sum())
        p(g.rename(columns={"size": "entries", "mean": "share_sizeable_2pct"}).round(2).to_string())
        need = len(g) // 2 + 1
        p(f"Reading A (Ben's choice on W01-0002): {n_clear} of {len(g)} markets have >= 50% of v0-rev "
          f"entries sizeable at 2% of $22,000; needs {need}. "
          + ("Still CLEARS." if n_clear >= need else "NO LONGER CLEARS on these bars -- raise before reading anything else."))

    # ---- Davey -------------------------------------------------------------
    _hdr(p, "8. DAVEY PROCESS FIGURES (W01-0005) -- REPORTED ONLY, NOT PART OF THE VERDICT")
    for rs in ("v0-rev", "v0"):
        for sz in (VERDICT, I22):
            b = V(rs, "ens", sz)
            d = davey(b)
            if d.get("trades", 0) == 0:
                p(f"  {b.label}: no trades")
                continue
            p(f"  {b.label}: {d['trades']} trades, mid friction, {MC_PATHS:,} resampled paths")
            p(f"     MC worst drawdown: median {money(d['mc_dd_p50']).strip()}, 95th pct "
              f"{money(d['mc_dd_p95']).strip()}; chance of a 30% ($6,639) drawdown {pct(d['p_dd_30']).strip()}, "
              f"of a 50% ($11,065) drawdown {pct(d['p_dd_50']).strip()}")
            p(f"     actual training sequence: worst drawdown {money(d['actual_dd']).strip()}; "
              f"10% pause ({money(d['pause_level']).strip()}) first hit {d['pause_first']} "
              f"({d['pause_episodes']} episodes); 3-losses-in-a-row {d['three_loss_events']} times "
              f"(first {d['three_loss_first']}); Davey quit point (MC p95) first reached {d['quit_p95_first']}")
    p("")
    p(INCUBATION)

    # ---- sample trades -----------------------------------------------------
    _hdr(p, "9. SAMPLE TRADES -- integer @ $22,129, mid friction, raw held-contract prices")
    for rs in ("v0-rev", "v0", "C1"):
        cut = "single" if rs == "C1" else "ens"
        tb = V(rs, cut, I22).trades
        if not len(tb):
            p(f"-- {rs}: none")
            continue
        tb = tb.sort_values("entry_date")
        step = max(len(tb) // 12, 1)
        smp = tb.iloc[::step].head(12)
        p(f"-- {rs} {cut}: {len(tb)} trades, every {step}th shown --")
        p(f"{'market':<7}{'R':>3}{'side':>6}{'entry':>12}{'exit':>12}{'contract':>14}{'qty':>5}"
          f"{'entry px':>13}{'exit px':>13}{'why':>13}{'net $':>11}")
        for _, r in smp.iterrows():
            p(f"{r['market']:<7}{r['R']:>3}{'long' if r['direction'] > 0 else 'short':>6}"
              f"{str(pd.Timestamp(r['entry_date']).date()):>12}{str(pd.Timestamp(r['exit_date']).date()):>12}"
              f"{r['entry_contract']:>14}{r['qty']:>5.0f}{r['entry_raw']:>13.6g}{r['exit_raw']:>13.6g}"
              f"{r['reason']:>13}{money(r['net_mid'], 11)}")

    # ---- coverage ----------------------------------------------------------
    _hdr(p, "10. COVERAGE (same pass): bars, dates, rolls, stale bars, weekend rows, roll cross-check")
    p(coverage.to_string())

    _hdr(p, "11. CAVEATS")
    p("""\
  * MTN: P&L is TN's held contract at MTN's $100/point; MTN listed 2024-03-25, so every
    2016-2021 MTN figure describes the signal, not something that could have been traded.
    Its stop-fill tick ($1.5625) is assumed = TN's 1/64 point.
  * NG and 6J are sized in FULL contracts (no micro in section 5): at $22,129 most of
    their signals skip; the skips are counted, never worked around.
  * Daily UTC bars (Databento ohlcv-1d), Sunday stubs folded into the next session
    (Amendment A). A stop is tested against the bar's high/low; which came first inside
    a bar is unknowable on daily bars, so a bar that both fills an entry at the open and
    trades through the stop is booked as a same-bar stop.
  * Equity is fixed per book (1% of $22,129 per trade, never of a running balance).
  * Roll legs are booked at the two contracts' closes on the roll session, no slippage,
    two sides of friction per contract.
  * THE BARS ARE UTC DAYS (00:00-00:00 UTC, i.e. ~7-8pm New York to the same time next
    day), not CME sessions. "Next bar's open" is the price at ~7-8pm New York, in the
    evening session. Tuesday-Friday opens are therefore close to the prior close: a stop
    gapped through at the 5pm CME halt or an 8:30am release is inside the bar and is
    booked at the stop + 1 tick, not at a gap price. The registered gap-at-the-open rule
    (sec 2.1, sec 8) mostly bites on Monday, where the folded Sunday stub is the reopen.
    For the same reason G3's Pine parity (TradingView session bars) does not carry over
    bar-for-bar to these bars; the rules are the same, the bars are not.
  * Trades touching a carried (stale) price -- a traded contract with no bar that session,
    or a roll priced from an earlier close of the new contract -- are flagged per trade
    (stale_fill / stale_roll in the trades CSV) and counted in section 10.
  * C3 has no stop; it is SIZED as if its stop were 3 x ATR(14) away, and each position is
    held exactly H sessions (a same-sign renewal still pays its round trip).
  * Realised volatility annualises daily $ P&L with sqrt(252) (criterion 5 compares a
    ratio, so the factor cancels).
  * Two explained Pine/Python differences in the G3-cleared line code (common/tl_v0_lines.py),
    left unchanged: a line's birth-validity test uses each bar's own ATR (Pine: the
    confirming bar's), and the 400-bar span is measured pivot-to-pivot (Pine: first
    pivot to the confirming bar, R bars longer).""")
    return "\n".join(L) + "\n", summary
