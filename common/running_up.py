#!/usr/bin/env python3
r"""The "running up" features, as they could be computed AT an entry bar.

The concept is Warrior Trading's Day Trade Dash "Running Up" scanner: a list
that fires when a name is climbing fast on a burst of volume. This module is
the measurable half of that idea -- a set of features, each computable from
bars that have already CLOSED, so a gate built on them could have been read
live at the moment the strategy signalled.

NOTHING HERE IS A RULE. There is no threshold, no verdict and no P&L in this
file. It exists so `running_up_preflight` can ask a descriptive question --
do any of these separate the trades that turn out to last one bar from the
rest? -- before any threshold is registered. PROGRAM_INDEX §5: look at the
distribution of the thing a threshold will cut before registering the
threshold.

WHAT "KNOWABLE" MEANS HERE, EXACTLY
-----------------------------------
`ts_event` is the interval START and a bar is not knowable until it CLOSES
(§5). The engines enter at the close of the signal bar, so at the instant of
entry the signal bar HAS closed and is knowable, and so is every bar before
it. Features therefore read `index <= ts` and never past it. The session's
own history means bars from SESSION_START on the entry's own date -- not the
warm-up sessions build_frame puts in front, which are a different day's
volume and would flatter every ratio here.

THE BASELINE IS SELF-REFERENTIAL, AND THAT IS A CHOICE
------------------------------------------------------
Warrior's "Relative Volume (5 min %)" is almost certainly measured against
prior sessions at the same time of day. This project cannot compute that:
RVOL off `bar_cache_*` failed because 2 of 27,777 symbol-days carried ten
prior sessions (§5). So the baseline here is the SESSION'S OWN volume so far
-- this five minutes against the median five minutes since 04:00. It is
point-in-time clean, it needs no history the archive lacks, and it measures
the same thing the scanner is looking at: a burst against this name's own
normal. It is NOT comparable to Warrior's percentages and no threshold
observed on their screen may be carried onto these numbers.
"""
from __future__ import annotations

import zlib
from datetime import time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
SESSION_START = dtime(4, 0)

# Feature names, in report order. `rand` and `minutes_since_open` are controls
# and are documented as such where they are read.
SEED = 20260916          # common.breadth.SEED; the project's one seed

FEATURES = ("rvol_5m", "rvol_1m", "ret_1m", "ret_3m", "ret_5m", "up_bars_5",
            "accel", "pos_in_range", "dist_from_high", "minutes_since_0400",
            "rand")


def session_slice(df: pd.DataFrame, ts: pd.Timestamp) -> pd.DataFrame:
    """Bars of ts's own session, from 04:00 ET up to and including ts.

    `build_frame` prepends warm-up sessions, so slicing on the timestamp alone
    would pull a different day's volume into every ratio -- the `load_sessions`
    three-day-frame trap (§5), which once moved a detector's signals a median
    of 245 bars.
    """
    if df.empty:
        return df
    local = df.index.tz_convert(ET)
    day = ts.tz_convert(ET).date()
    mask = (local.date == day) & (local.time >= SESSION_START) & (df.index <= ts)
    return df[mask]


def _at(hist: pd.DataFrame, back: int) -> float:
    """Close `back` bars before the last one, or NaN when the history is short.

    Positional, never by timestamp: the 2025-06-09 slice carries duplicate
    `ts_event` rows and `index.get_loc` returns a slice on them (§5).
    """
    if len(hist) <= back:
        return float("nan")
    return float(hist["close"].iloc[-1 - back])


def _ret(hist: pd.DataFrame, back: int) -> float:
    prev = _at(hist, back)
    if prev != prev or prev == 0:
        return float("nan")
    return float(hist["close"].iloc[-1]) / prev - 1.0


def features(df: pd.DataFrame, ts, *, seed_key: str = "") -> dict:
    """Every feature at `ts`, from that session's closed bars only.

    Returns NaN for any feature the history is too short to support. The
    preflight drops NaNs per feature rather than per row, so a name that
    printed only two bars before its entry still contributes to `ret_1m`.
    """
    ts = pd.Timestamp(ts)
    if ts.tz is None:
        # A naive stamp is the trap `bar_after_exit` was written for: read as
        # UTC it moves every session boundary four or five hours and the
        # features still come back looking ordinary. Refused, named, here --
        # not three frames down inside pandas.
        raise ValueError(f"features() needs a tz-aware timestamp, got {ts!r}; "
                         "stamp it in ET (running_up.ET) before calling")
    hist = session_slice(df, ts)
    out = {k: float("nan") for k in FEATURES}
    # The null control is defined for every row, including ones with no bars,
    # so a feature that reads well only where history exists cannot quietly
    # beat a control that was computed on a different population.
    # crc32, NOT hash(): str hashing is salted per process, so hash() would
    # give a different "seeded" control in every worker and on every run --
    # a control that cannot be reproduced is not a control.
    out["rand"] = float(np.random.default_rng(
        (zlib.crc32(seed_key.encode("utf-8")) + SEED) % (2**32)).random())
    if hist.empty:
        return out

    vol = hist["volume"].to_numpy(dtype=float)
    close = hist["close"].to_numpy(dtype=float)
    n = len(hist)

    # Volume burst against this session's own normal. The median, not the
    # mean: one 400k print in a thin pre-market name would otherwise set the
    # baseline and read every later burst as ordinary.
    med = float(np.median(vol)) if n else 0.0
    if med > 0:
        out["rvol_1m"] = float(vol[-1] / med)
        if n >= 5:
            out["rvol_5m"] = float(vol[-5:].sum() / (5.0 * med))

    out["ret_1m"] = _ret(hist, 1)
    out["ret_3m"] = _ret(hist, 3)
    out["ret_5m"] = _ret(hist, 5)

    if n >= 6:
        ups = sum(1 for i in range(-5, 0) if close[i] > close[i - 1])
        out["up_bars_5"] = float(ups)

    # Is the move SPEEDING UP -- the last minute against the average minute of
    # the last three. A steady climb reads ~0; a burst reads positive.
    if out["ret_3m"] == out["ret_3m"] and out["ret_1m"] == out["ret_1m"]:
        out["accel"] = out["ret_1m"] - out["ret_3m"] / 3.0

    hi = float(hist["high"].max())
    lo = float(hist["low"].min())
    px = float(close[-1])
    if hi > lo:
        out["pos_in_range"] = (px - lo) / (hi - lo)
    if hi > 0:
        out["dist_from_high"] = px / hi - 1.0

    # THE CONFOUND CONTROL: minutes since 04:00 ET, the clock itself. Time of
    # day is a CLOSED question on these books, so if this separates and the
    # momentum features do not, the momentum features are a clock in disguise.
    et = ts.tz_convert(ET)
    out["minutes_since_0400"] = float(et.hour * 60 + et.minute - 4 * 60)
    return out


def ret_at(df: pd.DataFrame, ts, back: int = 5) -> float:
    """The `back`-minute return at `ts`, from that session's closed bars only.

    The one feature `entry_sweep` reads, without paying for the other ten.
    Same window rules as `features()`, and the same refusal of a naive stamp:
    read as UTC it would move every session boundary four or five hours.
    """
    ts = pd.Timestamp(ts)
    if ts.tz is None:
        raise ValueError(f"ret_at() needs a tz-aware timestamp, got {ts!r}; "
                         "stamp it in ET (running_up.ET) before calling")
    return _ret(session_slice(df, ts), back)


def ret_series(df: pd.DataFrame, back: int = 5) -> pd.Series:
    """`ret_at` for every bar, at once, on the same session rules.

    H-P1's gate needs the five-minute return at EVERY bar of every symbol-day,
    and calling `ret_at` per bar re-slices the frame each time -- minutes
    against seconds over 6,411 symbol-days.

    TWO IMPLEMENTATIONS, ON PURPOSE, WITH A TEST THAT PINS THEM TOGETHER.
    `tests/common/test_ret_series.py` asserts this agrees with `ret_at` bar for
    bar, including the NaN positions. That is the cheapest control this project
    has: the SPY caches caught a data-path defect the same way, by pulling the
    same number down two independent routes and requiring them to agree.

    Grouped by session date, because `back` is POSITIONAL within a session --
    `build_frame` prepends warm-up days, and a shift across the whole frame
    would compute the 04:00 bar's return against yesterday's last bars, which
    is the three-day-frame trap (§5) with a different mask.
    """
    if df.empty:
        return pd.Series(dtype=float, index=df.index)
    local = df.index.tz_convert(ET)
    inside = local.time >= SESSION_START
    out = pd.Series(np.nan, index=df.index, dtype=float)
    close = df["close"].astype(float)
    for day in pd.unique(local.date):
        m = (local.date == day) & inside
        if not m.any():
            continue
        c = close[m]
        prev = c.shift(back)
        # prev == 0 is NaN in `_ret`, not an infinite return.
        out.loc[c.index] = (c / prev.where(prev != 0) - 1.0).values
    return out


def dist_series(df: pd.DataFrame) -> pd.Series:
    """`features()['dist_from_high']` for every bar, on the same session rules.

    close / (the session's running high so far) - 1, so it is <= 0 and reads 0
    at a new session high. Point-in-time by construction: the running maximum
    uses only bars at or before each one.

    Same two-implementations-with-an-agreement-test arrangement as
    `ret_series`, and the same reason for grouping by session date: the frame
    carries warm-up days, and a cummax across the whole of it would measure
    today's price against yesterday's high.
    """
    if df.empty:
        return pd.Series(dtype=float, index=df.index)
    local = df.index.tz_convert(ET)
    inside = local.time >= SESSION_START
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for day in pd.unique(local.date):
        m = (local.date == day) & inside
        if not m.any():
            continue
        hi = df.loc[m, "high"].astype(float).cummax()
        px = df.loc[m, "close"].astype(float)
        out.loc[px.index] = (px / hi.where(hi > 0) - 1.0).values
    return out


# --- separation, computed the same way for every feature --------------------

def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(a random `pos` scores above a random `neg`), ties counted as half.

    The rank form of Mann-Whitney U. 0.50 is "this feature knows nothing",
    which is the number the `rand` control must land on -- a separation
    statistic whose null is not visible in the report is a control whose
    output is indistinguishable from the failure it detects (§4).
    """
    pos = pos[~np.isnan(pos)]
    neg = neg[~np.isnan(neg)]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty(len(allv), dtype=float)
    ranks[order] = np.arange(1, len(allv) + 1, dtype=float)
    # average ranks over ties, or a feature with many equal values (up_bars_5
    # takes six values) reads as separation it does not have
    sv = allv[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    r_pos = ranks[:len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def deciles(vals: np.ndarray) -> list[float]:
    v = vals[~np.isnan(vals)]
    if len(v) == 0:
        return []
    return [float(np.quantile(v, q / 10.0)) for q in range(1, 10)]


def bind_table(hot: np.ndarray, cold: np.ndarray, cuts: list[float]) -> list[tuple]:
    """At each cut, the share of each group a `feature >= cut` gate would KEEP.

    Deliberately reports shares and never P&L. A table of P&L by threshold is
    a search wearing a table's clothes, and the threshold is not chosen here
    -- it is chosen in the registration that follows, from the distribution.
    """
    out = []
    h = hot[~np.isnan(hot)]
    c = cold[~np.isnan(cold)]
    for cut in cuts:
        kh = float((h >= cut).mean()) if len(h) else float("nan")
        kc = float((c >= cut).mean()) if len(c) else float("nan")
        out.append((cut, kh, kc))
    return out
