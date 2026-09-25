#!/usr/bin/env python3
"""HTF-Ben weekly context. W15-0004 step 7 checkpoint 9.
REGISTERED_htf_ben_v0.md sec 2.2 E6 ("Weekly trend: computed and reported
per trade (with / against), never used as a filter in v0") and sec 3 item 6
("Weekly context: net of trades with vs against the weekly trend (E6),
reported only").

REGISTERED leaves the exact weekly-trend computation open -- unlike E3's
daily filter (an explicit close-vs-EMA9/EMA21 rule) there is no equivalent
sentence for the weekly read, only "reported only, never a filter", which
follows because E6 never gates a trade or spends multiplicity budget either
way. This module mirrors E3's own method (close vs EMA9/EMA21, SMA-seeded
per E7) at weekly granularity as the natural, symmetric choice -- ASSUMED,
same standing as S1's L=R=2 swing size or E2's "2-bar" confirmation window
before those were pinned down by Ben. No extra warm-up buffer is imposed
beyond what the EMAs themselves need (unlike daily_direction's explicit
WARMUP_DAILY_BARS=60 cushion): a reported-only context has no false-signal
cost the way E3's actual filter would.

NO P&L HERE. Like signals.py, this module produces a per-trade READ (weekly
direction, with/against) from data that already exists; book.py's Trade
objects supply net_pnl, this module never recomputes it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.htf import signals as SIG

WEEKLY_EMA_FAST, WEEKLY_EMA_SLOW = 9, 21   # mirrors E3's daily EMA9/21 (assumed, see module docstring)


def weekly_bars(daily_adj: pd.DataFrame) -> pd.DataFrame:
    """Weekly OHLC (back-adjusted columns only -- this is a trend read, not
    a P&L series, so the raw columns are not carried) built from the
    back-adjusted DAILY bars (bars.daily + bars.back_adjust's own output:
    needs "date", "open_adj", "high_adj", "low_adj", "close_adj"). One row
    per ISO week that has >= 1 session in daily_adj; open/high/low/close =
    first open / max high / min low / last close of that week's sessions,
    in daily_adj's own row order (already session-ordered, so grouping
    preserves chronological week order without re-sorting by date)."""
    d = daily_adj.copy().reset_index(drop=True)
    dates = pd.to_datetime(d["date"])
    iso = dates.dt.isocalendar()
    d["_week"] = list(zip(iso["year"].to_numpy(), iso["week"].to_numpy()))
    d["_order"] = np.arange(len(d))
    g = d.groupby("_week", sort=False)
    out = pd.DataFrame({
        "open_adj": g["open_adj"].first(), "high_adj": g["high_adj"].max(),
        "low_adj": g["low_adj"].min(), "close_adj": g["close_adj"].last(),
        "week_start": g["date"].first(), "week_end": g["date"].last(),
        "_order": g["_order"].first(),
    }).sort_values("_order").reset_index(drop=True)
    return out.drop(columns=["_order"])


def weekly_direction(weekly: pd.DataFrame, *, ema_fast: int = WEEKLY_EMA_FAST,
                     ema_slow: int = WEEKLY_EMA_SLOW,
                     warmup_bars: int | None = None) -> pd.Series:
    """'long' / 'short' / 'none' per weekly bar: close vs EMA9/EMA21 (both
    SMA-seeded, E7), mirroring signals.daily_direction at weekly
    granularity. `warmup_bars` defaults to `ema_slow` (the EMAs are simply
    not defined before that many weekly bars exist -- no extra cushion, see
    module docstring); overridable for tests running on a short synthetic
    weekly series where a shorter ema_fast/ema_slow is also passed."""
    if warmup_bars is None:
        warmup_bars = ema_slow
    close = weekly["close_adj"]
    ema9 = SIG.ema_seeded(close, ema_fast)
    ema21 = SIG.ema_seeded(close, ema_slow)
    long_ok = (close > ema9) & (close > ema21)
    short_ok = (close < ema9) & (close < ema21)
    warm = np.arange(len(weekly)) >= warmup_bars
    direction = np.where(long_ok.to_numpy() & warm, "long",
                 np.where(short_ok.to_numpy() & warm, "short", "none"))
    return pd.Series(direction, index=weekly.index)


def _session_of_ts(ts: pd.Timestamp):
    """The CME session date (America/New_York) a UTC timestamp falls in --
    same small wrapper account.py uses; kept local rather than imported to
    avoid a cross-module dependency for one three-line helper."""
    naive = B.local_naive(pd.DatetimeIndex([ts]))
    return B.session_of(naive)[0].date()


def trade_alignment(trades, daily_adj: pd.DataFrame, *, ema_fast: int = WEEKLY_EMA_FAST,
                    ema_slow: int = WEEKLY_EMA_SLOW,
                    warmup_bars: int | None = None) -> pd.DataFrame:
    """Per trade: the weekly direction and its alignment with the trade's
    own direction ('with' / 'against' / 'none'), using the most recently
    COMPLETED week's weekly_direction as of the trade's entry -- the entry
    week's own weekly bar is still forming (its week_end has not happened
    yet), so it is never read, even though E6 is reported-only and sec 8's
    G4 no-lookahead guards do not name it. 'none' covers both "no completed
    week exists yet" (very first trades) and "the completed week's own
    direction was 'none'" (EMAs not warmed up, or price between them).

    Returns a DataFrame with columns "trade" (the Trade object itself),
    "weekly_direction", "alignment" -- one row per input trade, in the
    order given (not sorted by exit_t; callers wanting exit order should
    sort `trades` themselves first, as book.py's other consumers do)."""
    weekly = weekly_bars(daily_adj)
    direction = weekly_direction(weekly, ema_fast=ema_fast, ema_slow=ema_slow,
                                 warmup_bars=warmup_bars)
    week_end = pd.to_datetime(weekly["week_end"])
    rows = []
    for t in trades:
        entry_day = pd.Timestamp(_session_of_ts(t.entry_t))
        completed = (week_end < entry_day).to_numpy()
        if not completed.any():
            rows.append({"trade": t, "weekly_direction": "none", "alignment": "none"})
            continue
        idx = int(np.where(completed)[0][-1])
        wd = direction.iloc[idx]
        if wd == "none":
            align = "none"
        elif wd == t.direction:
            align = "with"
        else:
            align = "against"
        rows.append({"trade": t, "weekly_direction": wd, "alignment": align})
    return pd.DataFrame(rows, columns=["trade", "weekly_direction", "alignment"])


def net_by_alignment(alignment_df: pd.DataFrame, symbol: str, level: str,
                     qty: int = 1) -> dict:
    """REGISTERED sec 3 item 6: {"with": {"trades", "net"}, "against": {...},
    "none": {...}} -- trade counts and net $ (symbol/level/qty) grouped by
    trade_alignment's own "alignment" column. Reported only: this never
    decides whether a trade counts toward sec.4's scoring."""
    out = {}
    for key in ("with", "against", "none"):
        sub = alignment_df[alignment_df["alignment"] == key]["trade"]
        net = sum(t.net_pnl(symbol, level, qty) for t in sub)
        out[key] = {"trades": int(len(sub)), "net": float(net)}
    return out
