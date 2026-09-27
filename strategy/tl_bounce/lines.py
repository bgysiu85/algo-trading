#!/usr/bin/env python3
"""Trend-line geometry and touches for TL-bounce. REGISTERED_tl_bounce.md
sec 2.1-2.2 (E0, E1) and sec 2.3 (S1's line term, X1).

Reuses common/tl_v0_lines.py word for word (sec 0: "Lines come from
common/tl_v0_lines.py, the same code HTF-Ben v1's F2 and T use"):
find_pivots + walk_line_and_breaks already implement exactly what sec 2.1
registers for TL-bounce's own lines --

  * confirmed-only pivots (index i, confirmed at i+R)
  * a rising line only through the two MOST RECENTLY confirmed swing lows,
    only if v2 > v1 (kind='low'); a falling line only through the two most
    recently confirmed swing highs, only if v2 < v1 (kind='high')
  * birth validity (no close on the wrong side by > BUFFER_MULT*ATR between
    the two pivots) and the 400-bar MAX_SPAN cap
  * "active ... until the first close below/above it by more than
    0.10 x ATR" IS walk_line_and_breaks' break condition (BUFFER_MULT=0.10),
    so TL-bounce's line-end and its X1 exit are the exact same array
    (REGISTERED note: "X1 and the line's end are the same event").

WHY "SEVERAL LINES QUALIFY ... THE HIGHEST" (sec 2.2, E1) DOES NOT APPLY HERE
-------------------------------------------------------------------------------
walk_line_and_breaks tracks only ONE active line per kind at a time -- the
line through the two most recently confirmed pivots of that kind, matching
TL-v0's own line model (common/tl_v0_lines.py module docstring: "NO older
pivots are searched for a qualifying earlier pair"). Under this shared line
code there is never more than one active rising line and one active falling
line simultaneously, so E1's "if several lines qualify, the highest" clause
is moot as coded -- same judgement call TL-v0 flagged, inherited rather than
re-litigated here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.tl_v0_lines import atr14, find_pivots, walk_line_and_breaks
from strategy.htf import bars as B
from strategy.tl_bounce.spec import ATR_LEN, PIVOT_L, PIVOT_R, TOUCH_BUF, X1_BUF


@dataclass
class EntryLines:
    """Per-bar arrays for one entry-chart market, both line kinds.

    sup / sup_breaks : rising (support) line -- kind='low'. Touched by
        longs (E1), broken downward by X1-longs.
    res / res_breaks : falling (resistance) line -- kind='high'. Touched by
        shorts (E1 mirror), broken upward by X1-shorts.
    """
    atr: np.ndarray
    sup: np.ndarray
    sup_breaks: np.ndarray
    res: np.ndarray
    res_breaks: np.ndarray
    sup_pivots: list
    res_pivots: list


def atr_gated(h, lo, c, atr_len: int = ATR_LEN) -> np.ndarray:
    a = atr14(h, lo, c).astype(float)
    a[: atr_len - 1] = np.nan
    return a


def entry_lines(o, h, lo, c, *, R: int = PIVOT_R, atr_len: int = ATR_LEN) -> EntryLines:
    """Build both line kinds on one back-adjusted entry-chart OHLC series."""
    n = len(c)
    a = atr_gated(h, lo, c, atr_len)
    pivots_low = find_pivots(lo, R, "low")
    pivots_high = find_pivots(h, R, "high")
    sup, sup_breaks = walk_line_and_breaks(n, pivots_low, R, c, a, "low")
    res, res_breaks = walk_line_and_breaks(n, pivots_high, R, c, a, "high")
    # a line cannot be armed (or break) before ATR is known
    sup = np.where(np.isnan(a), np.nan, sup)
    res = np.where(np.isnan(a), np.nan, res)
    sup_breaks = sup_breaks & ~np.isnan(a)
    res_breaks = res_breaks & ~np.isnan(a)
    return EntryLines(a, sup, sup_breaks, res, res_breaks, pivots_low, pivots_high)


def touch_signals(lo, h, c, lines: EntryLines, *, buf: float = TOUCH_BUF
                  ) -> tuple[np.ndarray, np.ndarray]:
    """(touch_long, touch_short) -- E1: bar t's close, for the currently
    armed line of the matching kind.

    Long (rising/support line): low[t] <= sup[t] + buf*ATR[t] and
        close[t] >= sup[t].
    Short (falling/resistance line), mirror: high[t] >= res[t] - buf*ATR[t]
        and close[t] <= res[t].
    NaN (no armed line, or ATR not yet known) -> no touch.
    """
    a = lines.atr
    sup, res = lines.sup, lines.res
    armed_sup = ~np.isnan(sup)
    touch_long = armed_sup & (lo <= sup + buf * a) & (c >= sup)
    armed_res = ~np.isnan(res)
    touch_short = armed_res & (h >= res - buf * a) & (c <= res)
    return touch_long, touch_short


# ---------------------------------------------------------------------------
# E0: next-higher-chart trend filter (sec 2.1)
# ---------------------------------------------------------------------------

def higher_chart_dir_state(o, h, lo, c, t_open: pd.Series, bar_hours: int,
                           *, R: int = PIVOT_R, atr_len: int = ATR_LEN
                           ) -> pd.DataFrame:
    """Per higher-chart bar: the direction of the LAST line break as of
    that bar's own close (Pine tlCore's `dir`: an upward break -> +1, a
    downward break -> -1, carried forward until the next break; 0 before
    any break). `close_t` is each bar's own interval close (t_open +
    bar_hours), the instant its direction becomes legally knowable.
    """
    lines = entry_lines(o, h, lo, c, R=R, atr_len=atr_len)
    n = len(c)
    d = np.zeros(n)
    state = 0
    for j in range(n):
        # sec 2.1: falling (res) line broken UPWARD -> bullish; rising
        # (sup) line broken DOWNWARD -> bearish (same convention as
        # strategy/tl_v0/signals.py weekly_state: "dir := 1 then dir := -1"
        # on a two-way bar -- downward resolves last).
        if lines.res_breaks[j]:
            state = 1
        if lines.sup_breaks[j]:
            state = -1
        d[j] = state
    close_t = t_open + pd.Timedelta(hours=bar_hours)
    return pd.DataFrame({"close_t": close_t, "dir": d})


def daily_frame_from_1h(df_1h: pd.DataFrame) -> pd.DataFrame:
    return B.back_adjust(B.daily(df_1h))


def e0_filter(entry_df: pd.DataFrame, higher_df: pd.DataFrame, higher_bar_hours: int,
             *, R: int = PIVOT_R, atr_len: int = ATR_LEN) -> np.ndarray:
    """Per entry-chart bar j: the higher-chart direction (+1/-1/0) legally
    knowable at bar j's own close -- sec 2.1: "Higher-chart lines from the
    same code, completed bars only." A higher bar's direction becomes
    usable at HIGHER_BAR_CLOSE = its own t_open + higher_bar_hours; an
    entry bar may use the latest higher bar whose own close is <= the
    entry bar's own close (t_open + entry_bar_hours). This naturally
    reduces to "the prior session's daily bar, except the entry chart's own
    last bar of the session, which may use that now-complete daily bar" for
    the 4H-over-daily case, without a special session-boundary rule: a
    daily bar's close (17:00) is <= an entry bar's close ONLY for that same
    session's last entry-chart bar.
    """
    ho, hh, hl, hc = (higher_df[k + "_adj"].to_numpy(dtype=float) for k in
                      ("open", "high", "low", "close"))
    hstate = higher_chart_dir_state(ho, hh, hl, hc, higher_df["t_open"],
                                    higher_bar_hours, R=R, atr_len=atr_len)
    entry_bar_hours = int(round(
        (entry_df["t_open"].iloc[1] - entry_df["t_open"].iloc[0]).total_seconds() / 3600
    )) if len(entry_df) > 1 else higher_bar_hours
    entry_close = entry_df["t_open"] + pd.Timedelta(hours=entry_bar_hours)
    left = pd.DataFrame({"_orig": np.arange(len(entry_df)), "close_t": entry_close}
                        ).sort_values("close_t")
    merged = pd.merge_asof(left, hstate.sort_values("close_t"), on="close_t",
                           direction="backward")
    out = np.zeros(len(entry_df))
    out[merged["_orig"].to_numpy()] = merged["dir"].fillna(0).to_numpy()
    return out
