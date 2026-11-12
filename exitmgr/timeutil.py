#!/usr/bin/env python3
"""Clock and New York session helpers for the live exit manager (W15-0053 sub 4a).

Every time the manager reasons about is New York time. CME Globex (CL / MCL / MNQ ...): Sunday 18:00 to Friday 17:00 NY with
a daily maintenance halt 17:00-18:00 Monday to Thursday. Exchange holidays and early closes are NOT modelled here (a known
limit: on a holiday the manager may think the market is open; it only means a stale-data alert, never an order).
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
MAINT_START = dtime(17, 0)
MAINT_END = dtime(18, 0)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ny(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime: the manager only uses timezone-aware times")
    return dt.astimezone(NY)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def in_maintenance(dt: datetime) -> bool:
    """17:00-18:00 NY on any day (rail 13: no rule action in this hour)."""
    t = ny(dt).time()
    return MAINT_START <= t < MAINT_END


def globex_open(dt: datetime) -> bool:
    """True while the CME Globex session is open: Sun 18:00 -> Fri 17:00 NY, minus the daily 17:00-18:00 halt."""
    t = ny(dt)
    wd, tt = t.weekday(), t.time()              # Monday = 0
    if wd == 5:                                  # Saturday
        return False
    if wd == 6:                                  # Sunday: opens 18:00
        return tt >= MAINT_END
    if wd == 4:                                  # Friday: closes 17:00
        return tt < MAINT_START
    return not (MAINT_START <= tt < MAINT_END)


def trading_days_until(today: date, last: date) -> int:
    """Weekdays d with today < d <= last (no holiday calendar; rail 7 uses it conservatively)."""
    if last <= today:
        return 0
    n, d = 0, today
    while d < last:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def parse_ltd(s: str | None) -> date | None:
    """IBKR lastTradeDateOrContractMonth 'YYYYMMDD' (a bare 'YYYYMM' month is not an exact date -> None)."""
    s = (s or "").strip().split(" ")[0]
    if len(s) != 8 or not s.isdigit():
        return None
    return date(int(s[:4]), int(s[4:6]), int(s[6:]))
