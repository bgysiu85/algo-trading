#!/usr/bin/env python3
r"""L2 order-book features at entry (H-L2, W02-0013 step 7): F1-F3, D1-D3.

Registered in docs/research/REGISTERED_l2_entry.md ("this document") section
3. This module is the G3 gate: nothing in section 5 may be scored until the
tests beside this file pass. It computes features only -- it does not decide
whether a trade is kept (that rule, "keep iff X > 0", is section 5's job in
the run script, W02-0013 subitem 9).

THE WINDOW
----------
W = [t - 60s, t), HALF-OPEN, for every feature. `t` is the order instant:

  * backtest -- the signal bar's close, `entry_et + bar_min` (`bar_min` is 1
    for MCL, 5 for MC5). This is exactly `common.quote_price.signal_close`,
    reused here rather than re-derived, because the two pricing paths
    disagreeing is the H-R1 grain defect again: MC5's bar is FIVE minutes,
    and pricing or reading the book one bar early has already happened once
    on this project.
  * live -- the fill log's own `ts_et` timestamp, to the second. No bar
    arithmetic; the log already carries the instant the order went out.

A record timestamped AT OR AFTER `t` is never read by any feature here (G3,
registration section 0). That is stricter than "before or at the window's
start": `lo = t - 60s` is a legitimate historical instant and a record
stamped exactly there is real book history, so it IS read; a record stamped
exactly at `t` is the moment the feature is trying to predict, and reading it
is look-ahead. `window()` and `as_of(..., strict=True)` are where this is
enforced; test_leak_control below breaks each one on purpose and checks it
fails.

TRADE-SIDE SEMANTICS
---------------------
Confirmed from the DBN spec (Databento's `Side` enum, `dbn` crate docs,
https://docs.rs/dbn/latest/src/dbn/enums.rs.html): "the side of the market
for resting orders, or the side of the aggressor for trades." For a Trade
record, `side == 'B'` (Bid) is a BUY aggressor and `side == 'A'` (Ask) is a
SELL aggressor; `side == 'N'` means the source did not report one. This is
the opposite sense from a resting order's `side`, and the two must not be
conflated -- a trade's side names who crossed the spread, not which side of
the book absorbed the print.

WHAT COUNTS AS A VALID BOOK STATE
----------------------------------
A record is a valid two-sided quote when `bid_px_00 > 0`, `ask_px_00 > 0`
and `bid_px_00 < ask_px_00` (strictly -- locked or crossed is excluded, per
the registration). An invalid record does not end the window's coverage: the
last valid state simply continues to be time-weighted across it, exactly as
it would if no event had fired at all. A window with no valid state anywhere
in it -- nothing before it either -- is NO_BOOK, never a silent zero.

BUCKETS (registration section 3.1)
------------------------------------
Every feature returns a `Feature(value, bucket)`. `bucket` is one of:

  ""         scored normally
  "FLAT"     the value computed to exactly 0 (F1, F2) or exactly 0.5 (F3)
  "NO_BOOK"  no valid two-sided quote anywhere in W (F1, F2, D1, D2)
  "NO_TRADES" no Nasdaq print in W (F3)

`value` is `None` for NO_BOOK / NO_TRADES; both are counted, never coerced
to 0.0 -- a zero from an empty book and a zero from a balanced book are not
the same reading, and this project has been burned by that conflation before
(PROGRAM_INDEX: "a lower failure rate is not a better book").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

WINDOW_S = 60
LEVELS_MBP10 = 10

BID_PX = [f"bid_px_{i:02d}" for i in range(LEVELS_MBP10)]
ASK_PX = [f"ask_px_{i:02d}" for i in range(LEVELS_MBP10)]
BID_SZ = [f"bid_sz_{i:02d}" for i in range(LEVELS_MBP10)]
ASK_SZ = [f"ask_sz_{i:02d}" for i in range(LEVELS_MBP10)]


@dataclass
class Feature:
    value: float | None
    bucket: str = ""          # "" | "FLAT" | "NO_BOOK" | "NO_TRADES"


# --- t, per book --------------------------------------------------------------

def backtest_entry_instant(day: str, entry_et: str, bar_min: int) -> datetime:
    """Backtest t. Delegates to common.quote_price.signal_close so this and
    the pricing pull cannot silently disagree on where the bar closes."""
    from common.quote_price import signal_close
    return signal_close(day, entry_et, bar_min)


def live_entry_instant(ts_et: str) -> datetime:
    """Live t: the fill log's own timestamp, to the second, in ET -> UTC.

    `ts_et` is "YYYY-MM-DD HH:MM:SS" (no offset -- it is ET by the column's
    name and every other consumer of these fill logs, e.g.
    w02_0013_entry_structure_screen.py's `live_signals()`)."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    naive = datetime.strptime(ts_et, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=et)


# --- reading the book ----------------------------------------------------------

def window(df: pd.DataFrame, t: datetime, window_s: int = WINDOW_S) -> pd.DataFrame:
    """Every record in W = [t - window_s, t). Half-open at t -- see module
    docstring. `df` must be UTC-indexed on ts_event (common.dbn_io.read_dbn's
    convention) and sorted ascending."""
    lo = t - timedelta(seconds=window_s)
    return df[(df.index >= lo) & (df.index < t)]


def as_of(df: pd.DataFrame, ts: datetime, *, strict: bool = False):
    """The last record at (strict=False) or strictly before (strict=True)
    `ts`, from the FULL frame -- never window-limited, so a quote set before
    W started but still standing when W began is not lost. None if nothing
    qualifies.

    `strict=True` is the G3 leak-control form: used whenever `ts` IS the
    order instant `t` itself, so the record stamped exactly at `t` -- if one
    exists -- is excluded, matching `window()`. `strict=False` (the window's
    OWN start, `lo`) is a legitimate historical boundary and is read
    inclusively."""
    sub = df[df.index < ts] if strict else df[df.index <= ts]
    return sub.iloc[-1] if len(sub) else None


def _two_sided(row) -> bool:
    if row is None:
        return False
    b, a = row.get("bid_px_00"), row.get("ask_px_00")
    return b is not None and a is not None and b == b and a == a and b > 0 and a > 0


def _locked_or_crossed(row) -> bool:
    return float(row["bid_px_00"]) >= float(row["ask_px_00"])


def _valid_quote(row) -> bool:
    return _two_sided(row) and not _locked_or_crossed(row)


# --- time-weighting -------------------------------------------------------------

def _time_weighted_avg(df: pd.DataFrame, t: datetime, window_s: int, value_fn):
    """Time-weight `value_fn(state)` over W=[t-window_s, t).

    Breakpoints: `lo` (state = the last valid-or-not record at/before `lo`),
    then every record strictly inside (lo, t) in order, ending at `t`. Each
    segment's duration is weighted by how long that state stood; a segment
    whose state is not a valid two-sided quote is skipped (not zeroed) --
    the surrounding valid state's weight is unaffected by an invalid blip
    inside the window.

    Returns (avg_or_None, covered_seconds). avg is None iff covered == 0,
    i.e. no valid state was observed anywhere in W (NO_BOOK).
    """
    lo = t - timedelta(seconds=window_s)
    start_state = as_of(df, lo)                       # inclusive: lo is history
    changes = window(df, t, window_s)
    times = [lo] + list(changes.index) + [t]
    states = [start_state] + [changes.iloc[i] for i in range(len(changes))]
    covered = 0.0
    acc = 0.0
    for i, state in enumerate(states):
        dur = (times[i + 1] - times[i]).total_seconds()
        if dur <= 0 or not _valid_quote(state):
            continue
        v = value_fn(state)
        if v is None:
            continue
        acc += v * dur
        covered += dur
    if covered <= 0:
        return None, 0.0
    return acc / covered, covered


# --- F1: time-weighted quote imbalance ------------------------------------------

def _qi(row) -> float | None:
    b, a = float(row["bid_sz_00"]), float(row["ask_sz_00"])
    return (b - a) / (b + a) if (b + a) > 0 else None


def f1_quote_imbalance(df: pd.DataFrame, t: datetime, window_s: int = WINDOW_S) -> Feature:
    """QI = (bid_sz - ask_sz) / (bid_sz + ask_sz) at NBBO... at Nasdaq's best
    bid/offer, time-weighted over W. Rule (section 5, not applied here): keep
    iff QI > 0."""
    avg, covered = _time_weighted_avg(df, t, window_s, _qi)
    if avg is None:
        return Feature(None, "NO_BOOK")
    if avg == 0:
        return Feature(0.0, "FLAT")
    return Feature(avg, "")


# --- F2: Cont-Kukanov-Stoikov order-flow imbalance ------------------------------

def _ofi_event(prev, cur) -> float:
    """e_n for one top-of-book transition prev -> cur (registration sec 3.1,
    Cont/Kukanov/Stoikov 2014). Hand-verify against a 5-event case in
    test_l2_features.py -- this is the G3 hand-computed check."""
    b_prev, a_prev = float(prev["bid_px_00"]), float(prev["ask_px_00"])
    qb_prev, qa_prev = float(prev["bid_sz_00"]), float(prev["ask_sz_00"])
    b_cur, a_cur = float(cur["bid_px_00"]), float(cur["ask_px_00"])
    qb_cur, qa_cur = float(cur["bid_sz_00"]), float(cur["ask_sz_00"])
    e = 0.0
    e += qb_cur if b_cur >= b_prev else 0.0
    e -= qb_prev if b_cur <= b_prev else 0.0
    e -= qa_cur if a_cur <= a_prev else 0.0
    e += qa_prev if a_cur >= a_prev else 0.0
    return e


def f2_order_flow_imbalance(df: pd.DataFrame, t: datetime, window_s: int = WINDOW_S) -> Feature:
    lo = t - timedelta(seconds=window_s)
    prev = as_of(df, lo)
    changes = window(df, t, window_s)
    total = 0.0
    saw_book = _valid_quote(prev)
    for _, cur in changes.iterrows():
        if _valid_quote(prev) and _valid_quote(cur):
            total += _ofi_event(prev, cur)
        if _valid_quote(cur):
            saw_book = True
            prev = cur
        # an invalid `cur` (locked/crossed/one-sided) is dropped, not adopted
        # as the new predecessor -- the last valid state carries forward.
    if not saw_book:
        return Feature(None, "NO_BOOK")
    if total == 0:
        return Feature(0.0, "FLAT")
    return Feature(total, "")


# --- F3: aggressor share ---------------------------------------------------------

def classify_by_quote_rule(df: pd.DataFrame) -> pd.Series:
    """Every trade in `df`, classified 'B' (buy), 'A' (sell) or 'N' (the
    rule does not apply), by the standing quote at the PRIOR record -- never
    this record's own post-trade snapshot, which on a level-clearing print
    already reflects the trade having happened. A print at or above the
    prior ask is buyer-initiated; at or below the prior bid, seller-
    initiated; strictly between, the rule does not apply.

    Used only to cross-check the `side` field (G3); not a feature itself.
    """
    out, idx = [], []
    prev_valid = None          # the last record (trade or not) that itself
                                # carried a valid two-sided quote -- a real
                                # MBP-1 trade record does carry one (it is the
                                # merged book+trade stream), so it becomes
                                # eligible as `prev` for a LATER trade, but
                                # never for classifying itself.
    for ts, row in df.iterrows():
        if row.get("action") == "T":
            if _valid_quote(prev_valid):
                p = float(row["price"])
                bid, ask = float(prev_valid["bid_px_00"]), float(prev_valid["ask_px_00"])
                if p >= ask:
                    out.append("B")
                elif p <= bid:
                    out.append("A")
                else:
                    out.append("N")
            else:
                out.append("N")
            idx.append(ts)
        if _valid_quote(row):
            prev_valid = row
    return pd.Series(out, index=idx, dtype="object")


def f3_aggressor_share(df: pd.DataFrame, t: datetime, window_s: int = WINDOW_S) -> Feature:
    """Buyer-initiated shares / all shares printed on Nasdaq in W, from the
    `side` field (see module docstring for the confirmed semantics)."""
    w = window(df, t, window_s)
    trades = w[w["action"] == "T"]
    if trades.empty:
        return Feature(None, "NO_TRADES")
    total = float(trades["size"].astype(float).sum())
    if total <= 0:
        return Feature(None, "NO_TRADES")
    buy = float(trades.loc[trades["side"] == "B", "size"].astype(float).sum())
    share = buy / total
    if share == 0.5:
        return Feature(0.5, "FLAT")
    return Feature(share, "")


# --- D1-D3: MBP-10, described only (registration sec 3.2) -----------------------

def _sum_levels(row, cols) -> float | None:
    vals = [float(row[c]) for c in cols if c in row.index and row[c] == row[c]]
    return sum(vals) if vals else None


def d1_depth_imbalance(df: pd.DataFrame, t: datetime, window_s: int = WINDOW_S) -> Feature:
    """(sum bid_sz_00..09 - sum ask_sz_00..09) / (sum + sum), time-weighted."""
    def value_fn(row):
        bsz, asz = _sum_levels(row, BID_SZ), _sum_levels(row, ASK_SZ)
        if bsz is None or asz is None or (bsz + asz) <= 0:
            return None
        return (bsz - asz) / (bsz + asz)
    avg, covered = _time_weighted_avg(df, t, window_s, value_fn)
    if avg is None:
        return Feature(None, "NO_BOOK")
    if avg == 0:
        return Feature(0.0, "FLAT")
    return Feature(avg, "")


def d2_ask_depth_change(df: pd.DataFrame, t: datetime, window_s: int = WINDOW_S) -> Feature:
    """Total ask size over 10 levels at t (strictly before -- G3) divided by
    the same at t - window_s."""
    now = as_of(df, t, strict=True)
    lo = t - timedelta(seconds=window_s)
    then = as_of(df, lo)
    if not _valid_quote(now) or not _valid_quote(then):
        return Feature(None, "NO_BOOK")
    a_now, a_then = _sum_levels(now, ASK_SZ), _sum_levels(then, ASK_SZ)
    if not a_now or not a_then or a_then <= 0:
        return Feature(None, "NO_BOOK")
    return Feature(a_now / a_then, "")


def d3_spread_pct(df: pd.DataFrame, t: datetime) -> Feature:
    """Spread at t (strictly before -- G3), in % of the midpoint."""
    now = as_of(df, t, strict=True)
    if not _valid_quote(now):
        return Feature(None, "NO_BOOK")
    bid, ask = float(now["bid_px_00"]), float(now["ask_px_00"])
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return Feature(None, "NO_BOOK")
    return Feature((ask - bid) / mid * 100.0, "")
