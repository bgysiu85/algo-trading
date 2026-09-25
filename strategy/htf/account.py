#!/usr/bin/env python3
"""HTF-Ben account view. W15-0004 step 7 checkpoint 8.
REGISTERED_htf_ben_v0.md sec 2.5 (account view, sizing, overnight margin)
and sec 3 item 9 ("equity curve and worst drawdown in $ for n = 1 ... max
size + 1 MCL and for 1 CL; max size; ruin date if any; for B, the
overnight-margin count per n").

Reported, not scored (sec 4: "Account view (sec 2.5) is reported, not
scored -- Ben chooses the live size after seeing it"). Everything here
works from a completed trade LIST (strategy.htf.runner.Trade objects,
book.py's own input) plus costs.py's pricing -- no new backtest, no new
P&L source.

WHY THERE IS NO INTRADAY MARK-TO-MARKET
-----------------------------------------
The registered equity path is REALISED equity between trades: START, then
each trade's own net_pnl added at its exit, in exit order. A true
mark-to-market curve would need the full 1-hour price path under every
open position, which sec 2.5 never asks for -- "worst peak-to-trough
drawdown" and "an account whose equity touches $3,000" are both read off
this same realised curve. The one place intraday P&L would matter --
whether an overnight-held position could plausibly have covered its own
margin call before its OWN exit -- is exactly what sec 2.5 sidesteps with
"today's figures applied to all years ... a simplification, stated": the
margin check here compares a night's required margin against the running
REALISED equity as of that trade's own entry (before that trade's own,
not-yet-known outcome), never a mid-trade mark-to-market guess.

WHY "HELD NIGHTS" IS COUNTED IN SESSION-CALENDAR STEPS, NOT CALENDAR DAYS
--------------------------------------------------------------------------
A trade held from Thursday's session into Monday's is held over ONE
margin-relevant gap (Friday's close to Sunday evening's reopen), not three
calendar nights -- nothing trades Friday evening through Sunday afternoon,
so no extra margin call happens in that stretch versus a single ordinary
overnight hold. Indexing into the actual sorted list of session dates that
appear in the archive (`session_calendar`, e.g. daily_adj["date"]) gets
this right for free, the same trick bars.py's own bucket-floor arithmetic
uses to avoid special-casing the session length.
"""
from __future__ import annotations

import bisect

import numpy as np
import pandas as pd

from strategy.htf import bars as B

ACCOUNT_START = 10_000.0
DD_LIMIT = 7_000.0     # 70% of ACCOUNT_START (sec 2.5); breach = size not held
RUIN_LEVEL = 3_000.0   # sec 2.5: equity touching this stops trading
N_CAP = 50              # generous upper bound for the max-size search

# NinjaTrader's listed margins, 2026-09-25 (sec 2.5, Amendment 0's addition).
MARGIN = {
    "MCL": {"day": 100.0, "initial": 884.53, "maintenance": 804.11},
    "CL": {"day": 1000.0, "initial": 8823.20, "maintenance": 8021.09},
}


def equity_curve(trades, symbol: str, level: str, *, qty: int = 1,
                 start: float = ACCOUNT_START, stop_at_ruin: bool = True,
                 ruin_level: float = RUIN_LEVEL) -> list[tuple[pd.Timestamp, float]]:
    """[(exit_t, running equity)], one point per trade in exit-time order,
    starting from `start` and compounding trade.net_pnl(symbol, level, qty).
    When stop_at_ruin, no further points are appended once equity first
    reaches ruin_level or below (sec 2.5: "it stops trading" -- points after
    that are trades that, per the registered rule, would never have been
    taken at this size)."""
    pts: list[tuple[pd.Timestamp, float]] = []
    equity = start
    for t in sorted(trades, key=lambda x: x.exit_t):
        equity += t.net_pnl(symbol, level, qty)
        pts.append((t.exit_t, equity))
        if stop_at_ruin and equity <= ruin_level:
            break
    return pts


def worst_drawdown_dollars(points: list[tuple[pd.Timestamp, float]], *,
                           start: float = ACCOUNT_START) -> float:
    """Largest peak-to-trough drop in dollars, with `start` itself as the
    first peak -- a losing run right out of the gate is still a drawdown
    against the account's own starting size, not against its first (already
    reduced) equity point."""
    equities = np.array([start] + [e for _, e in points], dtype=float)
    running_max = np.maximum.accumulate(equities)
    dd = running_max - equities
    return float(dd.max()) if len(dd) else 0.0


def ruin_date(points: list[tuple[pd.Timestamp, float]], *,
             ruin_level: float = RUIN_LEVEL) -> pd.Timestamp | None:
    """The exit_t of the first point whose equity <= ruin_level, else None.
    Correct whether `points` was built with stop_at_ruin=True (checking only
    the possibly-truncated tail) or False (scanning the whole curve)."""
    for t, eq in points:
        if eq <= ruin_level:
            return t
    return None


def max_size(trades, symbol: str, level: str, *, dd_limit: float = DD_LIMIT,
            n_cap: int = N_CAP) -> int:
    """The largest whole n in [1, n_cap] whose worst peak-to-trough
    drawdown, run to completion at n contracts WITHOUT stopping at ruin (sec
    2.5 defines max size purely by the 70% drawdown test; whether that size
    would separately have been ruined along the way is ruin_date's own,
    reported, question), stays strictly under dd_limit. 0 if even n=1
    breaches it -- reported, not raised (an empty trade list also returns 0:
    a size test needs at least one trade to fail or pass -- with none, every
    n's drawdown is $0, which is technically "under" any positive limit, so
    this is checked explicitly rather than left to fall out of the loop)."""
    if not trades:
        return 0
    ok = [n for n in range(1, n_cap + 1)
         if worst_drawdown_dollars(equity_curve(trades, symbol, level, qty=n,
                                                 stop_at_ruin=False)) < dd_limit]
    return max(ok) if ok else 0


def _session_of_ts(ts: pd.Timestamp):
    """The CME session date (America/New_York) a UTC timestamp falls in.
    bars.session_of wants a DatetimeIndex; this wraps a single timestamp."""
    naive = B.local_naive(pd.DatetimeIndex([ts]))
    return B.session_of(naive)[0].date()


def nights_held(trade, session_calendar: list) -> int:
    """The number of session-to-session transitions the trade's open
    position sat across (see module docstring). `session_calendar` must be
    the sorted, deduplicated list of session dates the trade's own entry and
    exit sessions are drawn from (e.g. daily_adj["date"].tolist()). A trade
    that enters and exits within the same session (any A-scenario trade,
    and same-day B trades) returns 0. Uses bisect so a session date that
    happens not to be in the calendar (should not occur for a real trade)
    degrades to its insertion point rather than raising."""
    entry_day = _session_of_ts(trade.entry_t)
    exit_day = _session_of_ts(trade.exit_t)
    i0 = bisect.bisect_left(session_calendar, entry_day)
    i1 = bisect.bisect_left(session_calendar, exit_day)
    return max(0, i1 - i0)


def overnight_margin_breaches(trades, session_calendar: list, *, symbol: str = "MCL",
                              level: str = "mid", qty: int = 1,
                              start: float = ACCOUNT_START) -> int:
    """REGISTERED sec 2.5 (B, reported): the number of held nights on which
    qty x that symbol's INITIAL margin exceeded the account's own running
    REALISED equity as of that trade's entry (before that trade's own,
    not-yet-known P&L -- see module docstring). 0 = every held night could
    have been margined at this size. Trades are walked in exit order (the
    same order equity_curve uses) so "equity as of entry" for a trade is
    always every PRIOR trade's own net_pnl, already realised and booked."""
    initial = MARGIN[symbol]["initial"] * qty
    equity = start
    breaches = 0
    for t in sorted(trades, key=lambda x: x.exit_t):
        n = nights_held(t, session_calendar)
        if n > 0 and initial > equity:
            breaches += n
        equity += t.net_pnl(symbol, level, qty)
    return breaches


def account_view(trades, symbol: str, level: str, *, dd_limit: float = DD_LIMIT,
                 ruin_level: float = RUIN_LEVEL, n_cap: int = N_CAP,
                 session_calendar: list | None = None) -> dict:
    """Assembles REGISTERED sec 3 item 9's whole row set for one symbol at
    one friction level: max size, then equity curve + worst drawdown + ruin
    date for each n from 1 to max_size+1 (max_size+1 is shown on purpose --
    it is the one size that breaches the 70% test, so the report shows
    exactly where the line sits), and, when `session_calendar` is given
    (scenario B only, sec 2.5's overnight-margin check), the overnight-
    margin breach count for each of those same n. For symbol="CL", sec 3
    item 9 asks for n=1 only ("... for n = 1 ... max size + 1 MCL and for 1
    CL" -- MCL is the one that gets stepped, CL is reported once), so the
    max-size search and the stepped range are both skipped for CL and only
    a single n=1 row is built.

    Returns {"symbol", "max_size" (None for CL), "rows": [{"n",
    "final_equity", "worst_drawdown", "ruined", "equity_curve",
    "overnight_margin_breaches"?}]}.
    """
    if symbol == "MCL":
        m = max_size(trades, symbol, level, dd_limit=dd_limit, n_cap=n_cap)
        sizes = list(range(1, m + 2))
    else:
        m = None
        sizes = [1]

    rows = []
    for n in sizes:
        pts_full = equity_curve(trades, symbol, level, qty=n, stop_at_ruin=False)
        pts_stopped = equity_curve(trades, symbol, level, qty=n, stop_at_ruin=True,
                                   ruin_level=ruin_level)
        row = {
            "n": n,
            "final_equity": pts_stopped[-1][1] if pts_stopped else ACCOUNT_START,
            "worst_drawdown": worst_drawdown_dollars(pts_full),
            "ruined": ruin_date(pts_stopped, ruin_level=ruin_level),
            "equity_curve": pts_stopped,
        }
        if session_calendar is not None:
            row["overnight_margin_breaches"] = overnight_margin_breaches(
                trades, session_calendar, symbol=symbol, level=level, qty=n)
        rows.append(row)
    return {"symbol": symbol, "max_size": m, "rows": rows}
