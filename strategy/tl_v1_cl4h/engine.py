#!/usr/bin/env python3
"""TL-v1 on CL 4-hour bars (REGISTERED_tl_v1.md sec 2.5, last row). Board: W15-0027.
REPORTED ONLY: unranked, cannot spend the holdout, not a sec 4 criterion.

What sec 2.5 fixes:  CL only; 4-hour bars from ohlcv-1h on the 18:00 New York session
(strategy.htf.bars, as REGISTERED_tl_bounce.md sec 2.1); DAILY in place of WEEKLY for the
top-down filter and the safety line; costs as HTF-Ben v0 Amendment A per 1 MCL.

Everything else is TL-v1's, unchanged and REUSED, not re-implemented: the sec 2.2 line and
the A+ checklist (strategy.tl_v1.signals.MarketCtx / gate_for / v1_input), the walk
(strategy.tl_v0.sim.simulate, rule "reverse"), the v0-rev safety line (strategy.tl_v0.engine.tl_input).

CODING CHOICES THE REGISTRATION LEAVES OPEN (PRE-RUN; none is chosen from a return)
-----------------------------------------------------------------------------------
1. Bar-count parameters keep their registered NUMBERS in 4H bars: W = 250, span limit 400,
   pivots L = R in {3, 5, 8}, touch pivots L = R = 2, ER(20). (250 x 4H bars ~ 42 sessions.)
   A2 stays 7 CALENDAR days. A3 = q25 of CL's 4H ER(20) on the training bars (the registered
   daily thresholds do not apply to another bar size; the rule text is "q25 of that market's
   ER(20) over training bars only", which is what gate_for computes).
2. "Daily in place of weekly": the direction of the last daily line break and the armed daily
   support/resistance extrapolated one session ahead, from COMPLETED daily sessions only. A 4H
   bar of session S sees the state after session S-1 (never S itself). Same L = R as the sleeve.
3. The safety line is the opposing daily line -/+ 0.25 x ATR(14) of the EXECUTION (4H) bars,
   falling back to v0's 4H line, then the swing fallback (tl_input "v0-rev", unchanged).
4. P&L is booked on the difference-back-adjusted move (equal to the leg sum across rolls,
   the identity strategy.tl_v0.pnl asserts), x 100 $/point per MCL. Costs: strategy.htf.costs
   MCL (low $1.09 / mid $2.09 / high $3.09 per side, i.e. 0 / 1 / 2 ticks included),
   2 sides per trade plus 2 sides per roll inside the trade. No separate stop-slippage tick:
   Amendment A's mid/high levels already carry it.
5. Sizes: FIX = 1 MCL (ensemble = three sleeves at 1/3 MCL each; a sleeve alone = 1 MCL);
   FRAC22 = 1% of $22,129 fractional (TL-v1's verdict convention, MCL multiplier);
   INT22 = same, whole MCL, zero = skip (counted).
6. The training cut happens on the 1-hour frame BEFORE any bar is built.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, replace
from types import SimpleNamespace

import numpy as np
import pandas as pd

from common.tl_v0_lines import find_pivots, walk_line_and_breaks
from strategy.htf import bars as HB
from strategy.htf import costs as C
from strategy.tl_v0.engine import donchian_input, tl_input
from strategy.tl_v0.signals import (Signals, armed_line_next, atr_gated, market_signals)
from strategy.tl_v0.sim import SimInput, simulate
from strategy.tl_v0.spec import EQUITY, MARKETS, PIVOT_SIZES, RISK_PCT, STOP_BUF
from strategy.tl_v1.signals import VARIANTS, MarketCtx, v1_input

TRAIN_START = "2010-06-06"
TRAIN_END = "2021-12-31"
LEVELS = C.FRICTION_LEVELS
MULT = C.CONTRACT_MULT["MCL"]                    # 100 $/point
BOOKS = ("FIX", "FRAC22", "INT22")
GRID_BUF = (0.15, 0.25, 0.35)
GRID_W = (125, 250, 400)
GRID_Q = (0.20, 0.25, 0.33)


# ---------------------------------------------------------------------------
# bars
# ---------------------------------------------------------------------------

def cut_training(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Keep only source bars whose CME session is in [TRAIN_START, TRAIN_END]."""
    sess = HB.session_of(HB.local_naive(df_1h.index))
    keep = np.asarray((sess >= pd.Timestamp(TRAIN_START)) & (sess <= pd.Timestamp(TRAIN_END)))
    return df_1h[keep]


def build_frames(df_1h: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(4H frame, daily frame), both back-adjusted, training sessions only. The 4H frame carries
    the adjusted OHLC as open/high/low/close and `date` (naive UTC t_open); the raw held_id
    and adj_offset are kept for booking."""
    df = cut_training(df_1h)
    f4 = HB.back_adjust(HB.resample(df, "4H"))
    d1 = HB.back_adjust(HB.resample(df, "1D"))
    out = pd.DataFrame({"date": pd.DatetimeIndex(f4["t_open"]).tz_convert(None),
                        "session": pd.to_datetime(f4["session"]),
                        "held_id": f4["held_id"].to_numpy(),
                        "adj_offset": f4["adj_offset"].to_numpy()})
    for c in ("open", "high", "low", "close"):
        out[c] = f4[c + "_adj"].to_numpy(dtype=float)
    dd = pd.DataFrame({"session": pd.to_datetime(d1["session"])})
    for c in ("open", "high", "low", "close"):
        dd[c] = d1[c + "_adj"].to_numpy(dtype=float)
    return out.reset_index(drop=True), dd.reset_index(drop=True)


# ---------------------------------------------------------------------------
# daily in place of weekly
# ---------------------------------------------------------------------------

def daily_state(daily: pd.DataFrame, R: int) -> pd.DataFrame:
    """tl_v0.signals.weekly_state on DAILY bars: per completed session, the direction of the
    last line break (Pine `dir`) and the armed support/resistance extrapolated one session on."""
    dh, dl, dc = (daily[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    nd = len(dc)
    da = atr_gated(dh, dl, dc)
    ph, pl = find_pivots(dh, R, "high"), find_pivots(dl, R, "low")
    res, ups = walk_line_and_breaks(nd, ph, R, dc, da, "high")
    sup, dns = walk_line_and_breaks(nd, pl, R, dc, da, "low")
    _, res_next = armed_line_next(nd, ph, res, ups)
    _, sup_next = armed_line_next(nd, pl, sup, dns)
    d, state = np.zeros(nd), 0
    for j in range(nd):
        if ups[j]:
            state = 1
        if dns[j]:
            state = -1
        d[j] = state
    return pd.DataFrame({"session": daily["session"], "dir": d,
                         "res_next": res_next, "sup_next": sup_next})


def align_daily(sessions_4h: pd.Series, ds: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """A 4H bar of session S sees the daily state as of the last session STRICTLY BEFORE S."""
    s4 = pd.to_datetime(sessions_4h).to_numpy()
    sd = pd.to_datetime(ds["session"]).to_numpy()
    k = np.searchsorted(sd, s4, side="left") - 1          # sessions with date < S, last one
    out = {}
    for c in cols:
        v = ds[c].to_numpy(dtype=float)
        out[c] = np.where(k >= 0, v[np.clip(k, 0, None)], np.nan)
    return pd.DataFrame(out)


def signals_4h(frame: pd.DataFrame, daily: pd.DataFrame, R: int) -> Signals:
    """tl_v0.signals.market_signals on the 4H frame, with the weekly-derived fields (htf,
    cand_rev_*) replaced by their DAILY counterparts (sec 2.5). Its own weekly output on 4H
    bars is discarded."""
    s = market_signals(frame, R)
    al = align_daily(frame["session"], daily_state(daily, R), ["dir", "sup_next", "res_next"])
    return replace(s,
                   htf=al["dir"].fillna(0).to_numpy(dtype=float),
                   cand_rev_long=al["sup_next"].to_numpy(dtype=float) - STOP_BUF * s.atr,
                   cand_rev_short=al["res_next"].to_numpy(dtype=float) + STOP_BUF * s.atr)


class Ctx4H(MarketCtx):
    """strategy.tl_v1.signals.MarketCtx on the 4H frame, with the daily-based v0 signals."""

    def __init__(self, frame: pd.DataFrame, daily: pd.DataFrame):
        super().__init__(SimpleNamespace(frame=frame), MARKETS["CL"])
        self.daily = daily

    def v0sig(self, R):
        if R not in self._v0:
            self._v0[R] = signals_4h(self.frame, self.daily, R)
        return self._v0[R]


# ---------------------------------------------------------------------------
# booking
# ---------------------------------------------------------------------------

def n_rolls(held: np.ndarray, e: int, x: int) -> int:
    """held_id changes strictly after the entry bar and up to the exit bar."""
    if x <= e:
        return 0
    return int(np.sum(held[e + 1:x + 1] != held[e:x]))


def book_trades(trades, frame: pd.DataFrame, qty_override: float | None = None) -> pd.DataFrame:
    held = frame["held_id"].to_numpy()
    dates = frame["date"].to_numpy()
    sess = frame["session"].to_numpy()
    rows = []
    for t in trades:
        q = t.qty if qty_override is None else qty_override
        rolls = n_rolls(held, t.entry_j, t.exit_j)
        gross = t.direction * q * MULT * (t.exit_px - t.entry_px)
        row = dict(direction=t.direction, entry_j=t.entry_j, exit_j=t.exit_j,
                   entry_time=dates[t.entry_j], exit_time=dates[t.exit_j],
                   exit_session=sess[t.exit_j], entry_px=t.entry_px, exit_px=t.exit_px,
                   stop_init=t.stop_init, qty=q, reason=t.reason, n_rolls=rolls, gross=gross)
        for lv in LEVELS:
            cost = C.round_trip_cost("MCL", lv, n_round_trips=1 + rolls, qty=q)
            row["cost_" + lv] = cost
            row["net_" + lv] = gross - cost
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# one spec, every book
# ---------------------------------------------------------------------------

def _sizing(book: str):
    """(equity, integer) for a risk-sized book; FIX is simulated fractional and re-quantified."""
    return {"FIX": (EQUITY, False), "FRAC22": (EQUITY, False), "INT22": (EQUITY, True)}[book]


def run_spec(ctx: Ctx4H, spec: str, x_by_R: dict[int, SimInput], rule: str, books=BOOKS):
    """Per book: {'ens': trade DataFrame (three sleeves at 1/3), R: DataFrame (sleeve alone)}, plus counts."""
    out, counts = {}, []
    for book in books:
        eq, integer = _sizing(book)
        per = {}
        for R, x in x_by_R.items():
            for share, tag in ((1.0 / len(PIVOT_SIZES), "sleeve"), (1.0, "alone")):
                r = simulate(x, rule=rule, mult=MULT, risk_usd=RISK_PCT * eq * share, integer=integer)
                qty = None
                if book == "FIX":
                    qty = share                          # 1/3 MCL per sleeve in the ensemble, 1 MCL alone
                df = book_trades(r.trades, ctx.frame, qty)
                per[(R, tag)] = df
                counts.append(dict(spec=spec, book=book, R=R, share=tag, **r.counts.as_dict()))
        out[book] = per
    return out, counts


def ensemble(per: dict) -> pd.DataFrame:
    frames = [df.assign(R=R) for (R, tag), df in per.items() if tag == "sleeve" and len(df)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def run_all(ctx: Ctx4H, books=BOOKS):
    """Every variant (sec 2.5 rows that apply on CL), C1 and C2."""
    res, counts, gates = {}, [], {}
    for spec, kw in VARIANTS.items():
        xs = {}
        for R in PIVOT_SIZES:
            xs[R], gates[(spec, R)] = v1_input(ctx, R, **kw)
        res[spec], c = run_spec(ctx, spec, xs, "reverse", books)
        counts += c
    c2x = {R: tl_input(ctx.v0sig(R), "v0-rev") for R in PIVOT_SIZES}
    res["C2 v0-rev"], c = run_spec(ctx, "C2 v0-rev", c2x, "reverse", books)
    counts += c
    # C1 Donchian 20/10, one sleeve at full size, no top-down filter
    xd = donchian_input(ctx.frame)
    c1 = {}
    for book in books:
        eq, integer = _sizing(book)
        r = simulate(xd, rule="ignore", mult=MULT, risk_usd=RISK_PCT * eq, integer=integer)
        c1[book] = book_trades(r.trades, ctx.frame, 1.0 if book == "FIX" else None)
        counts.append(dict(spec="C1", book=book, R=0, share="single", **r.counts.as_dict()))
    res["C1"] = c1
    return res, pd.DataFrame(counts), gates


# ---------------------------------------------------------------------------
# controls: C3 (random selection), neighbour grid
# ---------------------------------------------------------------------------

def _net_mid_fix(ctx: Ctx4H, x: SimInput) -> tuple[float, int]:
    r = simulate(x, rule="reverse", mult=MULT, risk_usd=1.0, integer=False)
    df = book_trades(r.trades, ctx.frame, 1.0 / len(PIVOT_SIZES))
    return (float(df["net_mid"].sum()) if len(df) else 0.0), len(df)


def c3_setup(ctx: Ctx4H) -> dict:
    out = {}
    for R in PIVOT_SIZES:
        x, g = v1_input(ctx, R, aplus=False)
        pool_up = np.nonzero(g.raw_up & (x.htf == 1))[0]
        pool_dn = np.nonzero(g.raw_dn & (x.htf == -1))[0]
        n_sel = int((g.qual_up & (x.htf == 1)).sum() + (g.qual_dn & (x.htf == -1)).sum())
        out[R] = dict(x=x, pool_up=pool_up, pool_dn=pool_dn, n_sel=n_sel)
    return out


def c3_draw(ctx: Ctx4H, setup: dict, d: int) -> tuple[float, int]:
    """Same coding as strategy.tl_v1.controls.c3_draw: thin every-break pool to TL-v1's own
    selected-break count per sleeve; same seeds (crc32(draw), crc32('CL'), R)."""
    total, entries = 0.0, 0
    for R, s in setup.items():
        pu, pd_ = s["pool_up"], s["pool_dn"]
        size = len(pu) + len(pd_)
        k = min(s["n_sel"], size)
        if k == 0:
            continue
        rng = np.random.default_rng([zlib.crc32(str(d).encode()), zlib.crc32(b"CL"), R])
        pick = rng.choice(size, size=k, replace=False)
        n = len(s["x"].c)
        qu, qd = np.zeros(n, bool), np.zeros(n, bool)
        qu[pu[pick[pick < len(pu)]]] = True
        qd[pd_[pick[pick >= len(pu)] - len(pu)]] = True
        net, ne = _net_mid_fix(ctx, replace(s["x"], qual_up=qu, qual_dn=qd))
        total += net
        entries += ne
    return total, entries


def run_c3(ctx: Ctx4H, draws: int = 1000, progress=None) -> dict:
    setup = c3_setup(ctx)
    tot, ents = [], []
    for d in range(draws):
        t, e = c3_draw(ctx, setup, d)
        tot.append(t)
        ents.append(e)
        if progress and (d + 1) % 100 == 0:
            progress(d + 1)
    a = np.array(tot)
    return dict(draws=draws, p5=float(np.percentile(a, 5)), p50=float(np.percentile(a, 50)),
                p95=float(np.percentile(a, 95)), mean=float(a.mean()),
                entries_median=float(np.median(ents)),
                selected_breaks=int(sum(s["n_sel"] for s in setup.values())),
                pool_breaks=int(sum(len(s["pool_up"]) + len(s["pool_dn"]) for s in setup.values())),
                totals=a)


def run_grid(ctx: Ctx4H, progress=None) -> pd.DataFrame:
    rows = []
    for W in GRID_W:
        for buf in GRID_BUF:
            for q in GRID_Q:
                net, n = 0.0, 0
                for R in PIVOT_SIZES:
                    x, _ = v1_input(ctx, R, window=W, touch_buf=buf, erq=q)
                    a, b = _net_mid_fix(ctx, x)
                    net += a
                    n += b
                rows.append(dict(window=W, touch_buf=buf, er_pct=int(round(q * 100)),
                                 net_mid=net, trades=n))
                if progress:
                    progress(len(rows))
    return pd.DataFrame(rows)
