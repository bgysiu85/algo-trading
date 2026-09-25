#!/usr/bin/env python3
"""HTF-Ben bars: CL 1-hour bars -> the registered 2H/4H/daily entry grids.
W15-0004, REGISTERED_htf_ben_v0.md sec 2.1 (board W15-0003).

THE SESSION AND WHY BUCKETING IS DONE IN WALL-CLOCK ET
--------------------------------------------------------
CME Globex: Sunday-Thursday 18:00 -> next day 17:00 America/New_York, labelled
by the DAYTIME (closing) date -- Sunday evening joins Monday's session. Ben's
chart shows 4-hour bars at 18:00, 22:00, 02:00, 06:00, 10:00, 14:00 New York,
every session, whatever the UTC offset is that week: the boundaries are wall
clock, not elapsed real time. Bucketing is therefore done on the NAIVE ET
wall-clock timestamp (tz_convert then tz_localize(None)), never by adding a
pd.Timedelta to a tz-aware one -- that shifts by absolute time and would put
one bar an hour off for half the year (REGISTERED sec 8, "daylight saving").

A 23-wall-clock-hour session (18:00 -> next day 17:00) does not divide evenly
by 4 or 2, and floor(elapsed_hours / bar_hours) needs no special-casing for
that: elapsed hours run 0..22, so floor(22/4)=5 and floor(20/4)=floor(21/4)=
floor(22/4)=5 -- bucket 5 (the "14:00" bar) collects exactly the three source
bars at 14:00/15:00/16:00 and nothing after, matching REGISTERED sec 2.1's
"the 14:00 bar runs to 17:00 (3 hours)" without a separate rule. The same
division makes the daily bar (bar_hours=24, one bucket per session) and the
raw 1-hour "resample" (bar_hours=1, an identity relabelling with session/bar
columns attached) reuse of the exact same function, rather than three.

CONVENTIONS THAT DECIDE RESULTS (see common/dbn_io.py's own docstring)
-----------------------------------------------------------------------
* ts_event is the interval START. A bar labelled 18:00 covers 18:00-18:59;
  a signal on the 4-hour bar labelled 18:00 closes at 22:00.
* No bar is emitted for an hour with no trade. Nothing is synthesised; a
  resampled bucket with zero source bars simply does not appear.
* Front-month root: CL.c.0 IS the held contract directly (no active-cycle
  logic), the same convention common/tl_v0_data.py's front_month_series uses
  for CL. held_id = instrument_id, so a roll is any (session, bar)-ordered
  change in it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = "CL"

# bar_hours -> number of session buckets. 24 is the whole session (daily).
GRID_HOURS = {"1H": 1, "2H": 2, "4H": 4, "1D": 24}

BAR_COLUMNS = ["session", "bar", "t_open", "held_id", "open", "high", "low",
               "close", "volume", "n_src"]


class SessionBoundsError(ValueError):
    """A source bar's wall-clock elapsed-since-open fell outside [0, 23)."""


def local_naive(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """A tz-aware (UTC or other) index -> naive America/New_York wall clock."""
    if idx.tz is None:
        raise ValueError("index must be tz-aware")
    return idx.tz_convert(ET).tz_localize(None)


def session_of(naive: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """CME session label (a date, held as midnight-naive Timestamps): the
    18:00 evening bars join the FOLLOWING calendar day's session."""
    d = naive.normalize()
    evening = naive.hour >= 18
    return d.where(~evening, d + pd.Timedelta(days=1))


def session_open_naive(session_day: pd.Series) -> pd.Series:
    """The naive ET wall-clock instant a session opened: previous day 18:00."""
    return session_day - pd.Timedelta(days=1) + pd.Timedelta(hours=18)


def split_held(df: pd.DataFrame) -> pd.DataFrame:
    """CL.c.0 rows only, held_id = instrument_id, de-duplicated on timestamp
    (c.0 and c.1 share every ts_event -- common/tl_v0_data.py's load_bars
    docstring). Sorted by time."""
    d = df[df["symbol"] == f"{ROOT}.c.0"].copy()
    key = d.index.to_series().astype(str)
    d = d[~key.duplicated(keep="first")]
    d["held_id"] = d["instrument_id"].astype("int64")
    return d.sort_index()


def settlement_bar_mask(df_1h: pd.DataFrame) -> np.ndarray:
    """True for a source bar landing exactly at elapsed==23h (wall-clock
    17:00, the session's own close instant): a real, recurring Databento
    print (a settlement/closing tick), found in G1 (readback.py) at roughly
    one per weekday session throughout the CL.c.0 archive. ts_event==17:00
    means the interval [17:00,18:00) -- AFTER the 18:00-17:00 session this
    study trades on ends -- so it is not a 24th intraday bar and is excluded
    from every grid, not folded into the last bucket. Reported by G1, not
    silently dropped: readback.py counts these and lists them in the report
    rather than raising."""
    if df_1h.empty:
        return np.zeros(0, dtype=bool)
    naive = local_naive(df_1h.index)
    sess = session_of(naive)
    open_naive = session_open_naive(sess)
    elapsed = ((naive - open_naive) / pd.Timedelta(hours=1)).to_numpy()
    return np.isclose(elapsed, 23.0)


def resample(df_1h: pd.DataFrame, grid: str) -> pd.DataFrame:
    """CL.c.0 1-hour bars (tz-aware UTC index; held_id/open/high/low/close/
    volume columns, e.g. from split_held) -> one of the registered grids.

    grid in GRID_HOURS ("1H", "2H", "4H", "1D"). A resampled bar exists iff
    >=1 source bar falls in its bucket; OHLC = first open, max high, min low,
    last close, summed volume, held_id = the LAST source bar's (so a roll
    inside a multi-hour bucket is reflected honestly rather than hidden).
    A bar at elapsed==23h (settlement_bar_mask) is excluded, not bucketed --
    see that function's docstring.
    """
    bar_hours = GRID_HOURS[grid]
    if df_1h.empty:
        return pd.DataFrame(columns=BAR_COLUMNS)
    naive = local_naive(df_1h.index)
    sess = session_of(naive)
    open_naive = session_open_naive(sess)
    elapsed_h = (naive - open_naive) / pd.Timedelta(hours=1)
    elapsed = elapsed_h.to_numpy()
    settlement = np.isclose(elapsed, 23.0)
    if ((elapsed < 0) | (elapsed > 23) & ~settlement).any():
        raise SessionBoundsError(
            "a source bar's elapsed-since-open fell outside [0,23]; the "
            "session/bucket derivation is wrong for at least one bar")
    keep = ~settlement
    df_1h, naive, sess, elapsed = df_1h[keep], naive[keep], sess[keep], elapsed[keep]
    bucket = np.floor(elapsed / bar_hours).astype(int)

    d = df_1h.copy()
    d["session"] = sess
    d["bar"] = bucket
    d["_t"] = d.index
    d = d.sort_values(["session", "bar", "_t"], kind="mergesort")
    g = d.groupby(["session", "bar"], sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "volume": g["volume"].sum(),
        "held_id": g["held_id"].last(), "n_src": g["open"].size(),
    }).reset_index()

    starts = session_open_naive(out["session"]) + out["bar"] * pd.Timedelta(hours=bar_hours)
    # DST: a bucket boundary that lands on the skipped spring-forward hour is
    # shifted forward an hour (there is no other wall-clock instant to label
    # it); the repeated fall-back hour resolves to its second (post-DST-end)
    # occurrence. Both are tested (test_bars.py::test_dst_crossing).
    out["t_open"] = (starts.dt.tz_localize(ET, nonexistent="shift_forward", ambiguous=False)
                     .dt.tz_convert("UTC"))
    out["session"] = out["session"].dt.date
    return out[BAR_COLUMNS]


def daily(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Session daily bars built from the same 1-hour bars (REGISTERED sec
    2.1): one bucket per session, so this is resample(df_1h, "1D") with the
    per-bucket "bar" column dropped (always 0)."""
    out = resample(df_1h, "1D")
    return out.drop(columns=["bar"]).rename(columns={"session": "date"})


def back_adjust(df: pd.DataFrame) -> pd.DataFrame:
    """Difference-back-adjust a held-contract bar frame, at whatever
    granularity it's given (raw 1H, or an already-resampled 2H/4H/daily
    frame) -- same algorithm as common/tl_v0_data.py's back_adjust (a roll is
    a held_id change between consecutive rows; the gap is the raw
    close-to-close difference on the two adjacent bars; offsets accumulate
    walking backward from the most recent, untouched segment). Reused rather
    than imported because that one keys on a daily 'date' column unique per
    row; this keys on 't_open', which is unique at every grid this study
    uses. NEVER ratio-adjusted: CL printed -$37.63 on 2020-04-20 (REGISTERED
    sec 8), and a ratio adjustment cannot survive a sign change.
    """
    if df.empty:
        return df
    df = df.sort_values("t_open").reset_index(drop=True)
    change = df["held_id"] != df["held_id"].shift(1)
    change.iloc[0] = False
    roll_idx = df.index[change].tolist()
    gaps = [(i, df.loc[i, "close"] - df.loc[i - 1, "close"]) for i in roll_idx]
    adj = np.zeros(len(df))
    for i, gap in reversed(gaps):
        adj[:i] = adj[:i] + gap
    for c in ("open", "high", "low", "close"):
        df[c + "_adj"] = df[c] + adj
    df["adj_offset"] = adj
    df["n_rolls"] = len(roll_idx)
    return df


def load_1h(archive) -> pd.DataFrame:
    """CL.c.0 1-hour bars, held_id attached, from the fetched archive file
    (strategy/htf/fetch.py's bar_path)."""
    from common.dbn_io import read_dbn
    from strategy.htf.fetch import bar_path
    raw = read_dbn(bar_path(archive))
    return split_held(raw)
