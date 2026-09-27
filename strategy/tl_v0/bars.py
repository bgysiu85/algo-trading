#!/usr/bin/env python3
"""Daily OHLC bars for the TL-v0 backtest: the held contract under the TSMOM
roll rule (with Amendment C), its difference-back-adjusted signal series, and
the raw prices P&L is booked on. REGISTERED_tl_v0 section 2.1, "Signal series"
and "P&L series".

WHY THIS IS NOT common/tl_v0_data.py (the pre-flight's loader)
---------------------------------------------------------------
Three things the pre-flight could live with and a P&L engine cannot:

1. SUNDAY STUBS. GLBX ohlcv-1d bars are UTC days; the row stamped Sunday is the
   first hour or two of Monday's Globex session (strategy/tsmom/archive.py,
   point 1). The pre-flight used them as full daily bars (61 of its 399 entries
   were dated Sunday). As a bar it is a tiny range that feeds ATR, pivots and
   breaks, and "enter at the next bar's open" after a Friday signal would fill
   on it. Here each Sunday row is FOLDED into the same contract's next row
   (open = Sunday's open -- the true Globex reopen -- high/low = the extremes of
   both, close = the next row's close, volume summed). A Sunday row with no
   row of the same contract within three days is dropped. Both counts are
   reported. Saturday rows are dropped and counted. (Amendment A.)

2. THE ROLL RULE. The registration says P&L uses "the TSMOM roll rule
   including Amendment C". That rule is strategy/tsmom/roll.py: the held
   contract from the `definition` calendar, five sessions before the event,
   sessions counted WITHOUT Sundays. It is imported, not re-derived.

3. THE ROLL GAP. common/tl_v0_data.back_adjust() takes the gap as the new
   contract's close on the first session after the roll minus the old
   contract's close the session before -- which removes one day's real price
   move from the signal series at every roll. Here the gap is measured on the
   roll session itself, between the two contracts' closes, exactly as
   strategy/tsmom/roll.held_series does.

TIMING
------
roll.held_contract gives held(t) = the contract held AFTER the close of t. The
bar the strategy trades on session t is therefore the contract held going INTO
t: traded(t) = held(t-1). On a roll session R the position is carried in the
old contract through R's close and moved into the new one AT that close, at
the two contracts' closes (no slippage; two sides of friction are charged per
contract by the P&L code).

    off(t) = sum of gap(R) over roll sessions R >= t,  gap(R) = C_new(R) - C_old(R)
    adjusted = raw + off(t)

so the adjusted close on R equals the new contract's raw close on R, and the
last segment is unadjusted. A price DIFFERENCE inside one contract is the same
on both series, which is why P&L computed leg by leg on raw prices equals the
adjusted difference -- a test pins that.

THE HOLDOUT IS CUT FIRST. Sessions go through common.tl_v0_holdout.split_dates
(the one implementation, gate G4) before the roll schedule, the offsets, or any
bar is built; a test spies on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

import common.tl_v0_holdout as H
from strategy.tl_v0.spec import TRAIN_START, Market
from strategy.tsmom.registry import Root
from strategy.tsmom.roll import held_contract, roll_schedule

OHLC = ("open", "high", "low", "close")


class BarsRefused(SystemExit):
    pass


# ---------------------------------------------------------------------------
# 1. weekend rows
# ---------------------------------------------------------------------------

def fold_weekend(rows: pd.DataFrame, max_gap_days: int = 3) -> tuple[pd.DataFrame, dict]:
    """Fold each Sunday row into the SAME contract's next row (within
    `max_gap_days`); drop Saturday rows and orphan Sunday rows.

    `rows`: columns date (naive, normalised), contract, open, high, low, close,
    volume (+ anything else, carried from the surviving row).
    """
    r = rows.sort_values(["contract", "date"]).reset_index(drop=True).copy()
    dow = r["date"].dt.dayofweek
    note = {"saturday_rows_dropped": int((dow == 5).sum())}
    r = r[dow != 5].reset_index(drop=True)
    dow = r["date"].dt.dayofweek
    same_next = r["contract"].shift(-1) == r["contract"]
    gap = (r["date"].shift(-1) - r["date"]).dt.days
    sun = (dow == 6).to_numpy()
    foldable = sun & same_next.to_numpy() & (gap.to_numpy() <= max_gap_days)
    # a Sunday followed by another Sunday of the same contract is never
    # foldable into it (the target must be a weekday row)
    nxt_is_sun = np.r_[sun[1:], False]
    foldable &= ~nxt_is_sun
    tgt = np.nonzero(foldable)[0] + 1
    src = tgt - 1
    o = r["open"].to_numpy(dtype=float).copy()
    h = r["high"].to_numpy(dtype=float).copy()
    lo = r["low"].to_numpy(dtype=float).copy()
    v = r["volume"].to_numpy(dtype=float).copy() if "volume" in r else None
    o[tgt] = o[src]
    h[tgt] = np.maximum(h[tgt], h[src])
    lo[tgt] = np.minimum(lo[tgt], lo[src])
    if v is not None:
        v[tgt] = v[tgt] + v[src]
    r["open"], r["high"], r["low"] = o, h, lo
    if v is not None:
        r["volume"] = v
    note["sunday_rows_folded"] = int(foldable.sum())
    note["sunday_rows_dropped"] = int(sun.sum() - foldable.sum())
    r = r[~sun].reset_index(drop=True)
    return r, note


# ---------------------------------------------------------------------------
# 2. the per-market bar frame (pure; tested on synthetic contracts)
# ---------------------------------------------------------------------------

@dataclass
class MarketBars:
    market: str
    frame: pd.DataFrame          # one row per session, see build_bars()
    schedule: pd.DataFrame       # roll.roll_schedule output
    notes: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.frame)


def training_sessions(dates) -> pd.DatetimeIndex:
    """Weekday sessions on the TRAINING side only: split_dates first (the one
    implementation), then the registered training start."""
    days = sorted({pd.Timestamp(d).strftime("%Y-%m-%d") for d in dates})
    keep, _n_locked, _label = H.split_dates(days)
    s = pd.DatetimeIndex(pd.to_datetime(keep))
    s = s[s >= pd.Timestamp(TRAIN_START)]
    if (s.dayofweek >= 5).any():
        raise BarsRefused("a weekend date reached the session calendar -- fold_weekend first")
    return s


def build_bars(rows: pd.DataFrame, contracts: pd.DataFrame, root: Root,
               market: str) -> MarketBars:
    """`rows`: folded weekday rows (date, contract, open, high, low, close).
    `contracts`: symbol, expiration, year, month (roll.roll_schedule input).

    Returns one row per TRAINING session with:
      contract            traded(t) = held(t-1): what a position holds during t
      ro rh rl rc         raw OHLC of `contract` on t (carried from its last
                          close, and flagged `stale`, if it printed no bar)
      roll_after          True if the position is moved into `next_contract` at t's close
      next_contract       held(t)
      new_close_raw       next_contract's close on t (only meaningful on a roll)
      off                 adjusted = raw + off
      open high low close the difference-back-adjusted signal bar
    """
    sessions = training_sessions(rows["date"].unique())
    if len(sessions) < 2:
        raise BarsRefused(f"{market}: fewer than two training sessions")
    rows = rows[rows["date"].isin(sessions)]
    piv = {k: rows.pivot(index="date", columns="contract", values=k)
               .reindex(sessions) for k in OHLC}
    sched = roll_schedule(contracts, sessions, root)
    held = held_contract(sched, sessions)                 # held after close of t
    traded = held.shift(1)
    traded.iloc[0] = held.iloc[0]
    missing = sorted(set(held) - set(piv["close"].columns))
    if missing:
        raise BarsRefused(f"{market}: held contracts with no bars: {missing[:5]}")

    close_ff = piv["close"].ffill()
    n = len(sessions)
    rows_ix = np.arange(n)
    cols = {c: i for i, c in enumerate(piv["close"].columns)}
    ti = np.array([cols[c] for c in traded.values])
    hi = np.array([cols[c] for c in held.values])
    raw = {k: piv[k].to_numpy(dtype=float)[rows_ix, ti] for k in OHLC}
    cff = close_ff.to_numpy(dtype=float)
    stale = np.isnan(raw["close"])
    carry = cff[rows_ix, ti]
    if np.isnan(carry[stale]).any():
        bad = sessions[stale & np.isnan(carry)][:5]
        raise BarsRefused(f"{market}: traded contract has no price yet on "
                          f"{[d.date() for d in bad]}")
    for k in OHLC:
        raw[k] = np.where(stale, carry, raw[k])
    # a bar with close but a missing o/h/l (never seen in GLBX, guarded anyway)
    for k in ("open", "high", "low"):
        raw[k] = np.where(np.isnan(raw[k]), raw["close"], raw[k])

    roll_after = held.values != traded.values
    new_close = cff[rows_ix, hi]
    if np.isnan(new_close[roll_after]).any():
        bad = sessions[roll_after & np.isnan(new_close)][:5]
        raise BarsRefused(f"{market}: new contract has no close on roll session(s) "
                          f"{[d.date() for d in bad]}")
    new_stale = roll_after & np.isnan(piv["close"].to_numpy(dtype=float)[rows_ix, hi])
    gap = np.where(roll_after, new_close - raw["close"], 0.0)
    off = np.cumsum(gap[::-1])[::-1]                         # sum of gaps at s >= t

    f = pd.DataFrame({
        "date": sessions, "contract": traded.values, "next_contract": held.values,
        "ro": raw["open"], "rh": raw["high"], "rl": raw["low"], "rc": raw["close"],
        "stale": stale, "roll_after": roll_after, "new_close_raw": np.where(roll_after, new_close, np.nan),
        "new_close_stale": new_stale, "gap": gap, "off": off,
    })
    for k, rk in zip(OHLC, ("ro", "rh", "rl", "rc")):
        f[k] = f[rk] + f["off"]
    notes = {"sessions": n, "first": sessions[0].date(), "last": sessions[-1].date(),
             "rolls": int(roll_after.sum()), "stale_bars": int(stale.sum()),
             "roll_new_close_stale": int(new_stale.sum())}
    return MarketBars(market, f, sched, notes)


# ---------------------------------------------------------------------------
# 3. reading the archive (Ben's machine only; E:\Databento\GLBX.MDP3)
# ---------------------------------------------------------------------------

def load_rows(archive: Path, signal_root: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, dict]:
    """OHLC rows for one archive root, mapped to contract keys and folded.

    Reuses strategy/tsmom/archive.py for everything it already does
    (definitions, instrument-id mapping, manifest refusal); only the columns
    kept differ (it keeps close/volume, this keeps OHLC).
    Returns (rows, contracts, c0 per session, notes).
    """
    from strategy.tsmom import archive as A
    files = [Path(archive) / "ohlcv-1d" / f"{signal_root}.dbn.zst"]
    extra = Path(archive) / "ohlcv-1d" / f"{signal_root}.c2-c4.dbn.zst"
    if extra.exists():
        files.append(extra)
    frames = []
    for fp in files:
        if not fp.exists():
            raise BarsRefused(f"missing bar file {fp}")
        frames.append(A._dbn_df(fp).reset_index())
    b = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(b["ts_event"])
    if ts.dt.tz is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    if (ts != ts.dt.normalize()).any():
        raise BarsRefused(f"{signal_root}: a daily bar not stamped at 00:00 UTC")
    b["date"] = ts.dt.normalize().astype("datetime64[ns]")
    # the holdout is cut HERE, before any row is folded, deduplicated or
    # mapped: rows dated 2022-01-01 onward are never looked at again
    keep_days = set(H.split_dates(sorted({d.strftime("%Y-%m-%d") for d in b["date"]}))[0])
    n_all = len(b)
    b = b[b["date"].dt.strftime("%Y-%m-%d").isin(keep_days)].copy()
    locked_rows = n_all - len(b)
    b["rank"] = b["symbol"].str.extract(r"\.c\.(\d+)$")[0].astype(int)
    con, revisions = A.load_definitions(archive, signal_root)
    b["contract"] = A.map_ids(b, con)
    unmapped = int(b["contract"].isna().sum())
    b = b.dropna(subset=["contract"])
    b = b[["date", "contract", "rank", "open", "high", "low", "close", "volume"]]
    dup = b.duplicated(["date", "contract"], keep=False)
    if dup.any():
        d = b[dup].groupby(["date", "contract"])["close"].nunique()
        if (d > 1).any():
            raise BarsRefused(f"{signal_root}: one contract with two closes on one date:\n"
                              f"{d[d > 1].head()}")
        b = b.drop_duplicates(["date", "contract"])
    folded, note = fold_weekend(b)
    note.update({"unmapped_rows": unmapped, "locked_rows_dropped_on_load": locked_rows, "expiration_revisions": len(revisions),
                 "point_value_mismatch": A.point_value_check(signal_root, con)})
    c0 = folded[folded["rank"] == 0].set_index("date")["contract"].sort_index()
    c0 = c0[~c0.index.duplicated()]
    contracts = con[["symbol", "expiration", "year", "month"]].drop_duplicates("symbol")
    return folded, contracts, c0, note


def load_market(archive: Path, m: Market) -> tuple[MarketBars, pd.Series]:
    rows, contracts, c0, note = load_rows(archive, m.signal_root)
    mb = build_bars(rows, contracts, m.root, m.name)
    mb.notes.update(note)
    c0 = c0[c0.index.isin(mb.frame["date"])]
    return mb, c0
