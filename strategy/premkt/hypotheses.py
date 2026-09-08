#!/usr/bin/env python3
"""The three pre-registered pre-market hypotheses. Signals only.

    docs/premarket_hypotheses_20260908.md   -- the registration (commit 5075784)
    strategy/premkt/run.py                  -- runs them, scores them

EVERY NUMBER HERE IS FIXED BY THE REGISTRATION. The constants below are not
tunables -- changing one after a result exists is a new hypothesis, and it
spends from a budget of four. They are module constants rather than function
arguments so that the run script cannot sweep them by accident.

WHAT EACH ONE TESTS
-------------------
H0  Buy the screen. First bar at or after 04:30 ET, inside the band, hold on
    a trail. If this passes and nothing beats it, every entry rule ever
    layered on this screen was subtracting value.
H1  Runner. A new session high on >= 2x the session's average volume, with
    enough prior bars that "session high" means something.
H2  Pre-market opening range. The 04:00-04:29 range, broken to the upside on
    volume, after 04:30.

All three share one exit: an 8% trail from the peak since entry, or 09:30.
That is the point. The data said the exit is where the money is
(mcl_apex_macd_sweep.md, mcl_scale_up_decision.md), so the exit is held fixed
and only the entry varies.

WHAT "PRIOR BARS THIS SESSION" MEANS
------------------------------------
Bars of the SAME session date, from 04:00 ET up to but not including the bar
being evaluated. The cache file holds three sessions, and yesterday's high is
not today's session high. Every rolling quantity here restarts at 04:00.

Each function returns the frame with a boolean `entry` column, which is all
common.harness.run_session needs. The harness applies the price band at the
fill price, the trail, the session end, and the corrected fill model; nothing
about position management lives here.
"""
from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd

from common.harness import Exits, Rules

# --- registered parameters (docs/premarket_hypotheses_20260908.md) -----------
SESSION_START = dtime(4, 0)
SESSION_END = dtime(9, 30)
ENTRY_FROM = dtime(4, 30)          # H0 and H2: no entry before this
RANGE_END = dtime(4, 30)           # H2: range is [04:00, 04:30)

VOL_MULT = 2.0                     # H1, H2: volume >= this x reference mean
H1_MIN_PRIOR_BARS = 15             # H1: session high needs this much history
H2_MIN_RANGE_BARS = 10             # H2: range needs this many bars

TRAIL_PRIMARY = 8.0                # the registered trail
TRAILS_ROBUSTNESS = (5.0, 12.0)    # reported, never selected on
ENTRY_SHARES = 100                 # flat, every trade
FRICTION_PER_RT = 4.26             # measured live 2026-09-03, n=2 sessions

HYPOTHESES = ("H0", "H1", "H2")


def rules(trail_pct: float = TRAIL_PRIMARY) -> Rules:
    """The one exit all three hypotheses share, at the registered defaults.

    max_entries_per_session=1 is the registration's "one entry per
    symbol-session". use_exit_signal=False because there is no exit signal --
    the whole hypothesis is that there should not be one.
    """
    return Rules(
        session_start=SESSION_START,
        session_end=SESSION_END,
        exits=Exits(trail_pct=trail_pct, use_exit_signal=False,
                    flat_at_session_end=True),
        enforce_price_band=True,
        commission_plan="ibkr_tiered",
        max_entries_per_session=1,
        gap_fills=True,
        seed_peak_with_bar_high=False,
        stop_wins_ties=True,
    )


# --- helpers ------------------------------------------------------------------

def _session_mask(df: pd.DataFrame, session_date, tz) -> np.ndarray:
    local = df.index.tz_convert(tz)
    # .date and .time on a DatetimeIndex are object ndarrays, not Series, so
    # the comparisons below are already ndarrays.
    times = np.asarray(local.time)
    return (np.asarray(local.date) == session_date) \
        & (times >= SESSION_START) & (times < SESSION_END)


def _local_times(df: pd.DataFrame, tz) -> np.ndarray:
    return np.asarray(df.index.tz_convert(tz).time)


# --- H0: buy the screen ---------------------------------------------------------

def signal_h0(df: pd.DataFrame, session_date, tz) -> pd.DataFrame:
    """entry = the first session bar at or after 04:30 ET.

    The band is applied by the harness at the fill price, and the harness
    takes the FIRST bar whose entry is True (max_entries_per_session=1), so
    marking every bar from 04:30 on would enter on the first in-band one --
    which is not the registered rule. The registered rule is the first bar at
    or after 04:30, in band or not: if that bar is outside the band there is
    no H0 trade that day. So exactly one bar is marked.
    """
    out = df.copy()
    times = _local_times(out, tz)
    in_sess = _session_mask(out, session_date, tz)
    eligible = in_sess & (times >= ENTRY_FROM)
    entry = np.zeros(len(out), dtype=bool)
    hits = np.flatnonzero(eligible)
    if len(hits):
        entry[hits[0]] = True
    out["entry"] = entry
    return out


# --- H1: runner ----------------------------------------------------------------

def signal_h1(df: pd.DataFrame, session_date, tz) -> pd.DataFrame:
    """entry = close > every prior session high AND volume >= 2x prior mean.

    Both references are over PRIOR bars only -- the bar being evaluated is
    not part of its own session high, or the entry condition would be
    "close > own high", which is impossible, or "volume >= 2x a mean that
    includes itself", which is a different threshold.
    """
    out = df.copy()
    in_sess = _session_mask(out, session_date, tz)
    high = out["high"].to_numpy(dtype=float)
    close = out["close"].to_numpy(dtype=float)
    vol = out["volume"].to_numpy(dtype=float)

    entry = np.zeros(len(out), dtype=bool)
    idx = np.flatnonzero(in_sess)
    run_high = -np.inf
    vol_sum = 0.0
    n_prior = 0
    for i in idx:
        if n_prior >= H1_MIN_PRIOR_BARS:
            mean_vol = vol_sum / n_prior
            if close[i] > run_high and mean_vol > 0 and vol[i] >= VOL_MULT * mean_vol:
                entry[i] = True
        # update AFTER the check: this bar joins the history for the next one
        run_high = max(run_high, high[i])
        vol_sum += vol[i]
        n_prior += 1
    out["entry"] = entry
    return out


# --- H2: pre-market opening range ------------------------------------------------

def signal_h2(df: pd.DataFrame, session_date, tz) -> pd.DataFrame:
    """entry = first bar at/after 04:30 closing above the 04:00-04:29 range
    high on >= 2x the range's mean volume. Requires >= 10 range bars.

    "First" matters: only one bar is marked. A later, second break is not a
    registered entry, and max_entries_per_session=1 in the harness would take
    it if the first were outside the band. Marking only the first keeps the
    rule as written.
    """
    out = df.copy()
    times = _local_times(out, tz)
    in_sess = _session_mask(out, session_date, tz)
    in_range = in_sess & (times < RANGE_END)
    after = in_sess & (times >= ENTRY_FROM)

    entry = np.zeros(len(out), dtype=bool)
    r = np.flatnonzero(in_range)
    if len(r) >= H2_MIN_RANGE_BARS:
        range_high = float(out["high"].to_numpy()[r].max())
        range_vol = float(out["volume"].to_numpy()[r].mean())
        close = out["close"].to_numpy(dtype=float)
        vol = out["volume"].to_numpy(dtype=float)
        for i in np.flatnonzero(after):
            if close[i] > range_high and range_vol > 0 and vol[i] >= VOL_MULT * range_vol:
                entry[i] = True
                break
    out["entry"] = entry
    return out


SIGNALS = {"H0": signal_h0, "H1": signal_h1, "H2": signal_h2}
