#!/usr/bin/env python3
"""Everything a sleeve needs to know at each daily close, as arrays.

REGISTERED_tl_v0 section 2. Line geometry is NOT re-implemented here: pivots,
line validity and breaks come from common/tl_v0_lines.py (find_pivots,
walk_line_and_breaks), the code gates G3 (Pine parity) and G5 (hindsight
guard) were cleared on. This module only reads that output and derives, per
bar j, the values known at the CLOSE of j:

  up[j], dn[j]         action-line break at j's close (enter at j+1's open)
  htf[j]               weekly direction from COMPLETED weeks only (+1/-1/0)
  cand_v0_long/short   v0 safety-line level at j's close, Pine's `longCand`
                       / `shortCand`: the opposing daily line (if still armed
                       after j's close) -/+ 0.25 x ATR, else the last confirmed
                       swing low/high -/+ 0.25 x ATR
  cand_rev_long/short  v0-rev: the opposing WEEKLY line, built from completed
                       weeks and extrapolated to the current week, -/+ 0.25 x
                       daily ATR; NaN when no weekly line is armed (the
                       simulator then falls back to the v0 value, sec 2.2)
  swlo, swhi           lowest low - 0.25 x ATR / highest high + 0.25 x ATR of
                       the last 2R+1 bars incl. j (Pine's fallback initial
                       stop level, buffer already applied)

WHAT FOLLOWS PINE, WHERE THE REGISTRATION'S TEXT IS SILENT
-----------------------------------------------------------
Pine's TL_v0.pine is the G3 reference. Where the registration does not pin a
detail, Pine's behaviour is used and named:
  * weekly lines use the same L = R as the daily sleeve (Pine: htfDirPrev()
    calls tlCore(pivLen, ...));
  * the weekly direction takes the LAST event on a bar that breaks both ways
    (Pine sets dir := 1 then dir := -1); the daily entry takes the up-break
    first (Pine's `if upBrk ... else if dnBrk`);
  * initial stop: the safety-line candidate if it is on the right side of the
    signal close, else the 2L+1-bar extreme -/+ 0.25 x ATR (Pine's pendStop).
ATR(14) is treated as unknown for the first 13 bars (the repo's rma starts
at bar 1; Pine's does not produce a value until bar 14).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.tl_v0_lines import atr14, find_pivots, walk_line_and_breaks
from strategy.tl_v0.spec import ATR_LEN, STOP_BUF


# ---------------------------------------------------------------------------
# line state after each close
# ---------------------------------------------------------------------------

def armed_line_next(n: int, pivots, line: np.ndarray, breaks: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(armed_now, next_val): armed_now[j] = the line value at j if a line is
    still armed after j's close (NaN otherwise); next_val[j] = that same line
    extrapolated to bar j+1.

    The armed line after close j is always the one through the two most
    recently confirmed pivots (confirm index <= j) -- that is how
    walk_line_and_breaks builds it -- so its slope is read off those two
    pivots; whether it is armed is read off the walk itself. A mismatch
    between the two raises: it would mean the walk and this reading disagree
    about which line is in force.
    """
    armed_now = np.where(~np.isnan(line) & ~breaks, line, np.nan)
    nxt = np.full(n, np.nan)
    if not pivots:
        return armed_now, nxt
    conf = np.array([p[1] for p in pivots])
    for j in np.nonzero(~np.isnan(armed_now))[0]:
        k = np.searchsorted(conf, j, side="right")      # pivots confirmed <= j
        if k < 2:
            raise AssertionError(f"line armed at {j} with fewer than two confirmed pivots")
        (p1, _, v1), (p2, _, v2) = pivots[k - 2], pivots[k - 1]
        slope = (v2 - v1) / (p2 - p1)
        here = v2 + slope * (j - p2)
        if not np.isclose(here, armed_now[j], rtol=0, atol=1e-9 * max(1.0, abs(here))):
            raise AssertionError(f"armed line at {j}: walk says {armed_now[j]}, pivots say {here}")
        nxt[j] = v2 + slope * (j + 1 - p2)
    return armed_now, nxt


def last_pivot_value(n: int, pivots) -> np.ndarray:
    out = np.full(n, np.nan)
    for _pidx, cidx, val in pivots:
        if cidx < n:
            out[cidx] = val
    return pd.Series(out).ffill().to_numpy()


def atr_gated(h, lo, c) -> np.ndarray:
    a = atr14(h, lo, c).astype(float)
    a[: ATR_LEN - 1] = np.nan
    return a


# ---------------------------------------------------------------------------
# weekly: completed weeks only (same construction as common/tl_v0_preflight)
# ---------------------------------------------------------------------------

def build_weekly(frame: pd.DataFrame) -> pd.DataFrame:
    d = frame.set_index("date")[["open", "high", "low", "close"]]
    w = (d.resample("W-FRI").agg({"open": "first", "high": "max",
                                  "low": "min", "close": "last"})
         .dropna().reset_index().rename(columns={"date": "week_end"}))
    return w


def align_weekly(daily_dates: pd.Series, weekly: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """A daily bar sees the weekly state as of the PRIOR completed week, never
    the week it is itself inside of (common/tl_v0_preflight.align_weekly_to_daily)."""
    dd = pd.DataFrame({"date": pd.to_datetime(daily_dates).astype("datetime64[ns]")})
    dd["week_end"] = dd["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    dd["key"] = (dd["week_end"] - pd.Timedelta(days=7)).astype("datetime64[ns]")
    dd = dd.reset_index().rename(columns={"index": "_orig"})
    w = weekly[["week_end"] + cols].sort_values("week_end").copy()
    w["week_end"] = w["week_end"].astype("datetime64[ns]")
    merged = pd.merge_asof(dd.sort_values("key"), w, left_on="key", right_on="week_end",
                           direction="backward", suffixes=("", "_w")).sort_values("_orig")
    return merged[cols].reset_index(drop=True)


# ---------------------------------------------------------------------------
# the per-sleeve signal arrays
# ---------------------------------------------------------------------------

@dataclass
class Signals:
    R: int
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    atr: np.ndarray
    up: np.ndarray
    dn: np.ndarray
    htf: np.ndarray
    cand_v0_long: np.ndarray
    cand_v0_short: np.ndarray
    cand_rev_long: np.ndarray
    cand_rev_short: np.ndarray
    swlo: np.ndarray
    swhi: np.ndarray

    @property
    def n(self) -> int:
        return len(self.c)


def weekly_state(frame: pd.DataFrame, R: int) -> pd.DataFrame:
    """Per completed week: direction of the last line break (Pine tlCore
    `dir`), and the armed support/resistance extrapolated one week ahead."""
    w = build_weekly(frame)
    wo, wh, wl, wc = (w[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    nw = len(wc)
    wa = atr_gated(wh, wl, wc)                  # Pine: no weekly ATR for 13 weeks either
    ph, pl = find_pivots(wh, R, "high"), find_pivots(wl, R, "low")
    res, ups = walk_line_and_breaks(nw, ph, R, wc, wa, "high")
    sup, dns = walk_line_and_breaks(nw, pl, R, wc, wa, "low")
    _, res_next = armed_line_next(nw, ph, res, ups)
    _, sup_next = armed_line_next(nw, pl, sup, dns)
    d, state = np.zeros(nw), 0
    for j in range(nw):
        if ups[j]:
            state = 1
        if dns[j]:
            state = -1           # Pine: dir := 1 then dir := -1 on a two-way bar
        d[j] = state
    w["dir"], w["res_next"], w["sup_next"] = d, res_next, sup_next
    return w


def market_signals(frame: pd.DataFrame, R: int) -> Signals:
    o, h, lo, c = (frame[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(c)
    a = atr_gated(h, lo, c)
    ph, pl = find_pivots(h, R, "high"), find_pivots(lo, R, "low")
    res, ups = walk_line_and_breaks(n, ph, R, c, a, "high")
    sup, dns = walk_line_and_breaks(n, pl, R, c, a, "low")
    ups &= ~np.isnan(a)
    dns &= ~np.isnan(a)
    res_now, _ = armed_line_next(n, ph, res, ups)
    sup_now, _ = armed_line_next(n, pl, sup, dns)
    last_ph, last_pl = last_pivot_value(n, ph), last_pivot_value(n, pl)
    cand_long = np.where(~np.isnan(sup_now), sup_now, last_pl) - STOP_BUF * a
    cand_short = np.where(~np.isnan(res_now), res_now, last_ph) + STOP_BUF * a

    w = weekly_state(frame, R)
    al = align_weekly(frame["date"], w, ["dir", "sup_next", "res_next"])
    htf = al["dir"].fillna(0).to_numpy(dtype=float)
    cand_rev_long = al["sup_next"].to_numpy(dtype=float) - STOP_BUF * a
    cand_rev_short = al["res_next"].to_numpy(dtype=float) + STOP_BUF * a

    win = 2 * R + 1
    swlo = pd.Series(lo).rolling(win, min_periods=win).min().to_numpy() - STOP_BUF * a
    swhi = pd.Series(h).rolling(win, min_periods=win).max().to_numpy() + STOP_BUF * a
    return Signals(R, o, h, lo, c, a, ups, dns, htf, cand_long, cand_short,
                   cand_rev_long, cand_rev_short, swlo, swhi)
