#!/usr/bin/env python3
"""W16 session calendar: XNYS trading days, early closes, and the 09:30-16:00
(or 09:30-13:00) regular-hours window the three baselines trade on.
REGISTERED_w16_session_baselines.md sec 2 ("Session", "Early closes", "Days
that don't count"). Board W16-0003 subitem 3.

WHY THIS DUPLICATES common.spy_intraday.market_closed_days IN MINIATURE
--------------------------------------------------------------------------
common/spy_intraday.py already has a tested NYSE-vs-federal holiday
calculation (its own docstring: "the NYSE calendar is NOT the federal one").
It is not imported here because importing that module means importing
common.spy_intraday_data, which does `from ib_async import IB, ...` at
MODULE LEVEL and sys.exit()s the whole process if ib_async is not
importable. This module never trades and never touches a broker -- it
should not need one installed just to know which days the NYSE was open.
The holiday logic itself (federal calendar minus Columbus/Veterans Day,
plus Good Friday, plus a short list of unscheduled full closures) is
therefore reproduced here, not re-derived: same rule, same reasoning,
independent import.

EARLY CLOSES: AN EMPIRICAL LIST, NOT A HAND-DERIVED RULE, PLUS A
CROSS-CHECKED FALLBACK RULE FOR YEARS OUTSIDE IT
--------------------------------------------------------------------------
"XNYS early-close day" (REGISTERED sec 2) means the market closed at 13:00
ET instead of 16:00 -- in practice: Black Friday (day after Thanksgiving,
always), and July 3rd / December 24th WHEN they fall on a business day that
is not itself shifted onto the actual July 4th / December 25th holiday. The
exact edge cases (what happens when July 4th or December 25th falls on a
Saturday or Sunday) are the kind of thing easy to get subtly wrong from
memory, so EARLY_CLOSES_2010_2025 below is not a rule I wrote -- it is
read directly off real NYSE trading data: every session in this repo's own
`bar_cache_spy/30min/SPY` archive (2004-01 -> 2026-09) whose bars run
contiguously from 09:30 with no gap and whose last bar is 12:30 (so its
close IS the 13:00 print), extracted 2026-09-27 by grouping that cache's
real timestamps -- not a calendar rule applied on faith. `early_close_rule`
below is a SEPARATE, independently-written implementation of the usual NYSE
pattern (Black Friday always; July 3/Dec 24 early-close only when the
adjacent July 4/Dec 25 holiday is NOT itself weekend-shifted onto that same
date), kept so a year outside the baked table (2026 onward, once the
archive grows) is not simply unsupported. test_sessions.py asserts the rule
reproduces EARLY_CLOSES_2010_2025 exactly over its own range -- if a future
edit to either one breaks that agreement, the test catches it; nothing here
extrapolates past 2025 without that same test having already validated the
rule it extrapolates with.
"""
from __future__ import annotations

from datetime import time as dtime

import pandas as pd

from strategy.w16.readback import RTH_END, RTH_START, local_naive_et  # reuse: one ET-conversion, one RTH-open time, matching G1 exactly

EARLY_CLOSE_START = RTH_START            # 09:30 -- the open is the same on every session
EARLY_CLOSE_END = dtime(13, 0)

# Weekdays NYSE was fully closed. Unscheduled closures duplicated (by value,
# not import) from common.spy_intraday.UNSCHEDULED_CLOSURES -- see module
# docstring for why this isn't an import.
UNSCHEDULED_CLOSURES = {
    "2004-06-11",                 # national day of mourning, Reagan
    "2007-01-02",                 # national day of mourning, Ford
    "2012-10-29", "2012-10-30",   # Hurricane Sandy
    "2018-12-05",                 # national day of mourning, G.H.W. Bush
    "2025-01-09",                 # national day of mourning, Carter
}

# Read 2026-09-27 off this repo's own bar_cache_spy/30min/SPY archive: every
# session whose bars run contiguously from 09:30 with no internal gap and
# whose last bar is 12:30 (7 bars total: 09:30..12:30). See module docstring.
EARLY_CLOSES_2010_2025 = frozenset({
    "2010-11-26",
    "2011-11-25",
    "2012-07-03", "2012-11-23", "2012-12-24",
    "2013-07-03", "2013-11-29", "2013-12-24",
    "2014-07-03", "2014-11-28", "2014-12-24",
    "2015-11-27", "2015-12-24",
    "2016-11-25",
    "2017-07-03", "2017-11-24",
    "2018-07-03", "2018-11-23", "2018-12-24",
    "2019-07-03", "2019-11-29", "2019-12-24",
    "2020-11-27", "2020-12-24",
    "2021-11-26",
    "2022-11-25",
    "2023-07-03", "2023-11-24",
    "2024-07-03", "2024-11-29", "2024-12-24",
    "2025-07-03", "2025-11-28", "2025-12-24",
})
_BAKED_RANGE = (2010, 2025)


def market_closed_days(y0: int, y1: int) -> set[str]:
    """Weekday dates the XNYS calendar treats as fully closed: federal
    holidays as the exchange actually keeps them (NOT Columbus Day or
    Veterans Day, which the exchange trades through), plus Good Friday,
    plus UNSCHEDULED_CLOSURES. See module docstring for why this duplicates
    rather than imports common.spy_intraday.market_closed_days."""
    from pandas.tseries.holiday import GoodFriday, USFederalHolidayCalendar
    cal = USFederalHolidayCalendar()
    drop_names = {"Columbus Day", "Veterans Day"}
    keep: set[str] = set()
    for rule in cal.rules:
        if rule.name in drop_names:
            continue
        for d in rule.dates(f"{y0}-01-01", f"{y1}-12-31"):
            keep.add(pd.Timestamp(d).strftime("%Y-%m-%d"))
    for d in GoodFriday.dates(f"{y0}-01-01", f"{y1}-12-31"):
        keep.add(pd.Timestamp(d).strftime("%Y-%m-%d"))
    return keep | UNSCHEDULED_CLOSURES


def _day_after_thanksgiving(y0: int, y1: int) -> set[str]:
    from pandas.tseries.holiday import USThanksgivingDay
    out = set()
    for d in USThanksgivingDay.dates(f"{y0}-01-01", f"{y1}-12-31"):
        out.add((pd.Timestamp(d) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    return out


def _july_3rd_and_dec_24th(y0: int, y1: int) -> set[str]:
    """July 3rd / December 24th get an early close only when they are
    themselves a business day (Mon-Thu) that is NOT the weekend-shifted
    observance of July 4th / December 25th -- see module docstring. Both
    dates share the same shape: 'the day before a holiday that lands on a
    weekday, itself landing on a weekday' -- Mon/Tue/Wed/Thu, never Friday
    (a Friday July 3rd or Dec 24th always means the holiday itself fell on
    Saturday and IS that Friday's full closure, not an early close)."""
    out = set()
    for y in range(y0, y1 + 1):
        for month, day in ((7, 3), (12, 24)):
            d = pd.Timestamp(year=y, month=month, day=day)
            if d.dayofweek in (0, 1, 2, 3):     # Mon-Thu
                out.add(d.strftime("%Y-%m-%d"))
    return out


def early_close_rule(y0: int, y1: int) -> set[str]:
    """Independently-derived NYSE early-close rule (see module docstring):
    Black Friday every year, plus July 3rd / December 24th when they fall
    Mon-Thu. Cross-checked against EARLY_CLOSES_2010_2025 by
    test_sessions.py, not assumed correct on its own."""
    return _day_after_thanksgiving(y0, y1) | _july_3rd_and_dec_24th(y0, y1)


def early_close_days(y0: int, y1: int) -> set[str]:
    """The early-close dates in [y0, y1], preferring the empirical table
    where it covers a year and falling back to `early_close_rule` outside
    it (see module docstring -- test_sessions.py checks the two agree on
    the overlap)."""
    out = set()
    baked_lo, baked_hi = _BAKED_RANGE
    for y in range(y0, y1 + 1):
        if baked_lo <= y <= baked_hi:
            out |= {d for d in EARLY_CLOSES_2010_2025 if d.startswith(f"{y}-")}
        else:
            out |= early_close_rule(y, y)
    return out


def is_early_close(date_str: str) -> bool:
    y = int(date_str[:4])
    return date_str in early_close_days(y, y)


def session_close_time(date_str: str) -> dtime:
    """13:00 on an early-close day, 16:00 otherwise (REGISTERED sec 2:
    "The 16:00 close" = close of the bar starting 15:59; every "16:00"
    on an early-close day means the 13:00 close instead)."""
    return EARLY_CLOSE_END if is_early_close(date_str) else RTH_END


def orb_time_exit(date_str: str) -> dtime:
    """B1's time-exit bar-start: 30 minutes before the session's own close
    (REGISTERED sec 2: "ORB's 15:30 time exit means 30 minutes before it"
    on an early-close day)."""
    close = session_close_time(date_str)
    minutes = close.hour * 60 + close.minute - 30
    return dtime(minutes // 60, minutes % 60)


def is_xnys_trading_day(date_str: str) -> bool:
    y = int(date_str[:4])
    d = pd.Timestamp(date_str)
    if d.dayofweek >= 5:                                   # Sat/Sun
        return False
    return date_str not in market_closed_days(y, y)


def session_date_range(y0: int, y1: int) -> list[str]:
    """Every XNYS trading day in [y0, y1], ascending."""
    days = pd.date_range(f"{y0}-01-01", f"{y1}-12-31", freq="D")
    closed = market_closed_days(y0, y1)
    return [d.strftime("%Y-%m-%d") for d in days
            if d.dayofweek < 5 and d.strftime("%Y-%m-%d") not in closed]


def split_by_session(df_1m: pd.DataFrame):
    """Yield (date_str, day_frame) for every ET calendar date present in
    `df_1m` (a tz-aware 1-minute bar frame, any columns), in ascending
    order, WITHOUT any RTH/early-close filtering -- callers apply
    `session_window_mask` themselves once they know whether that date is an
    early close."""
    if df_1m.empty:
        return
    naive = local_naive_et(df_1m.index)
    sess = pd.Series(naive.strftime("%Y-%m-%d"), index=df_1m.index)
    for date_str, part in df_1m.groupby(sess, sort=True):
        yield date_str, part


def session_window_mask(df_day: pd.DataFrame, date_str: str):
    """Bars of `df_day` (any date's bars, tz-aware index) that fall in
    [09:30, session_close_time(date_str)) ET -- the RTH window this study
    trades on, narrowed to 13:00 on an early-close day (REGISTERED sec 2)
    even if Globex kept printing bars past that close."""
    naive = local_naive_et(df_day.index)
    close = session_close_time(date_str)
    t = naive.time
    return (t >= EARLY_CLOSE_START) & (t < close)


def has_valid_open(df_session: pd.DataFrame, *, gap_minutes: int = 5) -> bool:
    """REGISTERED sec 2: "A session missing its 09:30 bar or with a gap >
    5 min inside 09:30-10:00 is skipped by ORB and VWAP and counted."
    `df_session` is already RTH-windowed (session_window_mask applied)."""
    if df_session.empty:
        return False
    naive = local_naive_et(df_session.index)
    if naive.time.min() != EARLY_CLOSE_START:
        return False
    first_hour = df_session[(naive.time >= EARLY_CLOSE_START) & (naive.time < dtime(10, 0))]
    if first_hour.empty:
        return False
    minutes = sorted((local_naive_et(first_hour.index).hour * 60
                       + local_naive_et(first_hour.index).minute))
    for a, b in zip(minutes, minutes[1:]):
        if b - a > gap_minutes:
            return False
    return True
