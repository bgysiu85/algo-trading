#!/usr/bin/env python3
"""HTF-Ben v0-TL: v0's E1-E4 entries plus a 4-hour trend-line break+retest
filter. W15-0007, REGISTERED_htf_ben_v0.md sec 2.6:

    "E1-E4 plus: within the 6 four-hour bars before t, a 4-hour trend-line
    break in the trade's direction followed by a retest (a bar whose low
    comes within 0.25 x ATR(14) of the broken line and closes back beyond
    it). Lines from common/tl_v0_lines.py (L=R=5), on the back-adjusted
    4-hour series."

NO P&L HERE, same discipline as preflight.py (module docstring): this scores
triggers the same way preflight.detect_v0 does (E1-E3, S1) with one more
condition gating the trigger itself -- the TL filter -- so it plugs into the
same G2 pre-flight machinery and the same runner.simulate() E5 walk without
a third code path for "is this a valid entry".

WHY THE TL FILTER RUNS ON ITS OWN 4-HOUR FRAME, NOT THE SCENARIO'S OWN CHART
-----------------------------------------------------------------------------
Sec 2.6 fixes v0-TL's trend-line geometry to "the back-adjusted 4-hour
series" for every scenario (B, A-2H, A-1H, A-4H) -- unlike E1-E4, which run
on each scenario's own entry chart (Amendment 0). So this module always
takes a `four_h_adj` frame built the same way as B/A-4H's own entry_adj
(preflight.prepare_grids()["4H"] after back_adjust -- prepare_grids already
returns it pre-back-adjusted), and maps each trigger's own t_open (whatever
chart it is on) to the last 4-hour bar that had ALREADY CLOSED as of that
t_open, using the global t_open timestamps -- not session/bucket arithmetic
-- so a 2H or 1H trigger never reads a 4-hour bar that is still forming.

WHY THE BROKEN LINE IS RE-EXTRAPOLATED FOR THE RETEST CHECK
----------------------------------------------------------------
common.tl_v0_lines.walk_line_and_breaks() marks a line "cold" (NaN) the
instant it breaks -- exactly right for TL-v0's own break signal, but sec
2.6 here needs to know whether price RETESTS that same (now broken) line
within the next few bars. walk_line_and_breaks does not carry the broken
line forward, so this module recovers the line's own (ref_idx, ref_val,
slope) from the two bars immediately before the break (both still on the
pre-break line, by construction: line[b] = ref_val + slope*(b - ref_idx) is
linear) and extrapolates it forward itself, only for the fixed
TL_LOOKBACK_BARS window sec 2.6 gives.

ASSUMPTION FLAGGED (a judgement call the registered text does not fully
pin down, in the same spirit as tl_v0_lines.py's own header note): "within
the 6 four-hour bars before t, a break ... followed by a retest" is read
here as the RETEST bar falling in the 6 bars immediately before t
(map_to_last_closed_4h's t4, back TL_LOOKBACK_BARS-1 more bars); the break
that retest belongs to may itself sit up to TL_LOOKBACK_BARS bars before
its own retest (tl_break_retest_series' own, separate lookback -- same
constant, reused for both gaps for lack of a second registered number). A
break whose only retest lands after t's own 6-bar window does not count,
and neither does a "retest" of a break so old its own break-to-retest gap
exceeds TL_LOOKBACK_BARS. Checked explicitly in
tests/strategy/htf/test_tl_variant.py.

Also assumed: "the low comes within 0.25*ATR14 of the line" is read as an
absolute distance test (works whether the retest bar's low sits a touch
above or a touch below the extrapolated line), mirroring tl_v0_lines.py's
own BUFFER_MULT convention of testing distance-from-line, not one-sided
containment.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import tl_v0_lines as TL
from strategy.htf import signals as SIG

TL_LR = 5
TL_LOOKBACK_BARS = 6
TL_RETEST_ATR_MULT = 0.25


def _recovered_line_at_break(line: np.ndarray, b: int) -> tuple[float, int, float] | None:
    """(ref_val, ref_idx, slope) for the line active just before break bar
    b, recovered from line[b-1]/line[b-2] (both pre-break, still on the
    straight line walk_line_and_breaks was extrapolating). None if there
    are not two valid bars before b to recover a slope from."""
    if b < 2:
        return None
    v1, v0 = line[b - 2], line[b - 1]
    if np.isnan(v1) or np.isnan(v0):
        return None
    slope = v0 - v1
    return (v0, b - 1, slope)


def tl_break_retest_series(four_h_adj: pd.DataFrame, *, LR: int = TL_LR,
                           lookback: int = TL_LOOKBACK_BARS,
                           retest_mult: float = TL_RETEST_ATR_MULT,
                           ) -> tuple[np.ndarray, np.ndarray]:
    """(bullish_ok, bearish_ok) bool arrays over four_h_adj: bullish_ok[j]
    (bearish_ok[j]) is True iff bar j itself is a valid retest of a
    resistance (support) break, with BOTH the break and the retest falling
    within the `lookback` bars ending at j (sec 2.6, window read as
    covering both events -- module docstring). Retest = low (bullish) /
    high (bearish) within retest_mult*ATR14 of the broken line's
    extrapolated level, AND the close already back beyond it."""
    high = four_h_adj["high_adj"].to_numpy(dtype=float)
    low = four_h_adj["low_adj"].to_numpy(dtype=float)
    close = four_h_adj["close_adj"].to_numpy(dtype=float)
    n = len(close)
    atr = TL.atr14(high, low, close)

    bullish_ok = np.zeros(n, dtype=bool)
    bearish_ok = np.zeros(n, dtype=bool)

    for kind, ok_arr, test_px in (("high", bullish_ok, low), ("low", bearish_ok, high)):
        pivots = TL.find_pivots(high if kind == "high" else low, LR, kind)
        line, breaks = TL.walk_line_and_breaks(n, pivots, LR, close, atr, kind)
        break_positions = np.where(breaks)[0]
        for b in break_positions:
            recovered = _recovered_line_at_break(line, b)
            if recovered is None:
                continue
            ref_val, ref_idx, slope = recovered
            window_end = min(b + lookback, n)  # window = [b - lookback + ... , window_end)
            # the break itself must fall within the lookback window ending
            # at the retest bar j; since j ranges b+1..window_end-1 here,
            # and the window (per bar j) is [j-lookback+1, j], b qualifies
            # for every j in this loop by construction (b <= j and
            # j - b < lookback iff j < b + lookback, enforced by window_end)
            for j in range(b + 1, window_end):
                lv = ref_val + slope * (j - ref_idx)
                dist = abs(test_px[j] - lv)
                if dist <= retest_mult * atr[j]:
                    beyond = (close[j] > lv) if kind == "high" else (close[j] < lv)
                    if beyond:
                        ok_arr[j] = True
                        break  # sec 2.6: one event per break, on its first retest
    return bullish_ok, bearish_ok


def map_to_last_closed_4h(entry_t_open: np.ndarray, four_h_t_open: np.ndarray,
                          bar_hours_4h: int = 4) -> np.ndarray:
    """For each entry-chart trigger's own t_open, the index (into the 4H
    frame) of the last 4-hour bar that had ALREADY CLOSED as of that
    t_open -- i.e. the largest i with four_h_t_open[i] + 4h <= entry_t_open.
    -1 where none exists yet (still inside warm-up). Global timestamp
    search (not session/bucket math), so it is correct across scenarios,
    across sessions and across the roll (t_open is a plain UTC instant on
    every grid -- bars.resample's own docstring)."""
    closes = four_h_t_open + np.timedelta64(bar_hours_4h, "h")
    idx = np.searchsorted(closes, entry_t_open, side="right") - 1
    return idx


def detect_v0_tl(entry_adj: pd.DataFrame, daily_adj: pd.DataFrame, four_h_adj: pd.DataFrame,
                 *, scenario: str, warmup_bars: int = SIG.WARMUP_ENTRY_BARS,
                 confirm_window: int = 2, swing_LR: int = 2,
                 tl_LR: int = TL_LR, tl_lookback: int = TL_LOOKBACK_BARS,
                 tl_retest_mult: float = TL_RETEST_ATR_MULT,
                 ) -> tuple[list[dict], dict]:
    """v0-TL: identical walk to preflight.detect_v0 (same E1/E2/E3/S1
    machinery, same counts shape), with one extra gate at the trigger bar
    i itself -- sec 2.6's TL condition, read off `four_h_adj` via
    map_to_last_closed_4h. A trigger that fails the TL gate is counted as
    `blocked_no_tl_setup`, distinct from `lapsed`/`blocked_daily_filter`/
    `voided` so the four block reasons stay separately readable (mirrors
    preflight's own count partition, extended by one bucket)."""
    from strategy.htf import bars as B
    from strategy.htf import preflight as P

    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    n = len(entry_adj)
    close = entry_adj["close_adj"]
    macd_line, signal_line = SIG.macd_seeded(close)
    up = SIG.macd_cross_up(macd_line, signal_line)
    down = SIG.macd_cross_down(macd_line, signal_line)
    confirms_long, confirms_short = SIG.confirmation_flags(close, macd_line, signal_line)
    daily_dir = SIG.daily_filter_as_of(entry_adj, daily_adj, bar_hours)
    ready = SIG.entry_ready_mask(entry_adj, warmup_bars)
    swing_low = SIG.swing_lows(entry_adj["low_adj"], L=swing_LR, R=swing_LR).ffill()
    swing_high = SIG.swing_highs(entry_adj["high_adj"], L=swing_LR, R=swing_LR).ffill()
    last_bar = SIG.session_last_bar_mask(entry_adj, bar_hours)
    low_adj = entry_adj["low_adj"].to_numpy()
    high_adj = entry_adj["high_adj"].to_numpy()
    open_adj = entry_adj["open_adj"].to_numpy()

    bullish_ok, bearish_ok = tl_break_retest_series(
        four_h_adj, LR=tl_LR, lookback=tl_lookback, retest_mult=tl_retest_mult)
    four_h_t_open = four_h_adj["t_open"].values
    entry_t_open = entry_adj["t_open"].values
    t4_idx = map_to_last_closed_4h(entry_t_open, four_h_t_open)

    counts = {"triggers": 0, "lapsed": 0, "blocked_daily_filter": 0,
             "blocked_no_tl_setup": 0, "blocked_end_of_session": 0,
             "voided": 0, "entries": 0}
    entries = []
    for i in range(n):
        if not ready[i]:
            continue
        if up.iloc[i]:
            direction = "long"
        elif down.iloc[i]:
            direction = "short"
        else:
            continue
        counts["triggers"] += 1

        t4 = int(t4_idx[i])
        ok_arr = bullish_ok if direction == "long" else bearish_ok
        window_lo = max(0, t4 - tl_lookback + 1)
        tl_ok = t4 >= 0 and bool(ok_arr[window_lo:t4 + 1].any())
        if not tl_ok:
            counts["blocked_no_tl_setup"] += 1
            continue

        confirms = confirms_long if direction == "long" else confirms_short
        c = SIG.confirmation_bar(confirms, i, window=confirm_window)
        if c is None:
            counts["lapsed"] += 1
            continue
        if daily_dir.iloc[c] != direction:
            counts["blocked_daily_filter"] += 1
            continue
        fill_idx = c + 1
        if fill_idx >= n:
            counts["lapsed"] += 1
            continue
        if scenario in P.INTRADAY_SCENARIOS and bool(last_bar[fill_idx]):
            counts["blocked_end_of_session"] += 1
            continue
        fill_price = float(open_adj[fill_idx])
        stop = P._initial_stop(direction, fill_idx, fill_price, swing_low, swing_high,
                               low_adj, high_adj)
        if stop is None:
            counts["voided"] += 1
            continue
        counts["entries"] += 1
        entries.append(P._entry_record(entry_adj, fill_idx, direction, fill_price, stop,
                                       scenario, bar_hours))
    return entries, counts
