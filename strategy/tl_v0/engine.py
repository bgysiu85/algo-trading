#!/usr/bin/env python3
"""Runs every registered sleeve and control on one market's training bars.

REGISTERED_tl_v0 section 3 items 6, 7, 9. For each market:

  TL rule sets   v0 and v0-rev, each pivot size R in {3, 5, 8}, each sized two
                 ways: as an ENSEMBLE sleeve (1/3 of the 1% risk) and ALONE
                 (the full 1%) -- the ensemble book is the sum of the three
                 sleeves, a "pivot size alone" book is that R at full risk
  C1             Donchian 20/10: close beyond the prior 20-bar high/low ->
                 next open; resting stop at the 10-bar opposite channel,
                 ratcheting; no weekly filter (a plain channel breakout);
                 one sleeve at 1%
  C2             v0's entries (weekly filter, ignore-in-position) with a
                 3 x ATR(14) chandelier stop instead of the safety line;
                 ensemble sleeves at 1/3 each
  C3             12-month TSMOM sign on the same market, each position held
                 exactly H sessions, then closed and a new one opened on the
                 sign at that time (see tsmom_hold_trades), where H is the
                 median hold of the TL rule set it is compared with (run once
                 for v0's H and once for v0-rev's); sized as if the stop were
                 3 x ATR(14) away (it has no stop), one sleeve at 1%

Every sleeve is simulated under each sizing: FRACTIONAL (never skips; sized at
spec.EQUITY) and INTEGER at each of spec.EQUITIES (floor; zero = skip). An
integer skip changes what the sleeve does next (it stays flat and can take the
next signal), so each sizing is its own walk. Equity is fixed per book (no
compounding): a trade's risk is 1% of the book's equity, never of a running
balance -- the same convention TSMOM's report used.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.tl_v0 import pnl
from strategy.tl_v0.bars import MarketBars
from strategy.tl_v0.signals import Signals, atr_gated, market_signals
from strategy.tl_v0.sim import SimInput, Trade, simulate
from strategy.tl_v0.spec import (CHANDELIER_ATR, DONCHIAN_ENTRY, DONCHIAN_EXIT, EQUITIES,
                                 EQUITY, LEVELS, PIVOT_SIZES, RISK_PCT, TSMOM_LOOKBACK, Market)

SIZINGS: tuple[tuple[str, float], ...] = (("frac", EQUITY),) + tuple(("int", e) for e in EQUITIES)


# ---------------------------------------------------------------------------
# stop policies -> SimInput
# ---------------------------------------------------------------------------

def _init(cand, fallback, c, side):
    ok = np.isfinite(cand) & ((cand < c) if side == 1 else (cand > c))
    return np.where(ok, cand, fallback)


def tl_input(s: Signals, ruleset: str) -> SimInput:
    """v0: safety line = opposing DAILY line (Pine longCand/shortCand).
    v0-rev: opposing WEEKLY line where one is armed, else v0's (sec 2.2)."""
    v0_il = _init(s.cand_v0_long, s.swlo, s.c, 1)
    v0_is = _init(s.cand_v0_short, s.swhi, s.c, -1)
    if ruleset == "v0":
        return SimInput(s.o, s.h, s.l, s.c, s.up, s.dn, s.htf, v0_il, v0_is,
                        s.cand_v0_long, s.cand_v0_short)
    if ruleset == "v0-rev":
        il = _init(s.cand_rev_long, v0_il, s.c, 1)
        is_ = _init(s.cand_rev_short, v0_is, s.c, -1)
        tl = np.where(np.isfinite(s.cand_rev_long), s.cand_rev_long, s.cand_v0_long)
        ts = np.where(np.isfinite(s.cand_rev_short), s.cand_rev_short, s.cand_v0_short)
        return SimInput(s.o, s.h, s.l, s.c, s.up, s.dn, s.htf, il, is_, tl, ts)
    raise ValueError(ruleset)


def chandelier_input(s: Signals) -> SimInput:
    nan = np.full(s.n, np.nan)
    return SimInput(s.o, s.h, s.l, s.c, s.up, s.dn, s.htf, nan, nan, nan, nan,
                    atr=s.atr, chandelier_k=CHANDELIER_ATR)


def donchian_input(frame: pd.DataFrame) -> SimInput:
    o, h, lo, c = (frame[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    hh = pd.Series(h).rolling(DONCHIAN_ENTRY, min_periods=DONCHIAN_ENTRY).max().shift(1).to_numpy()
    ll = pd.Series(lo).rolling(DONCHIAN_ENTRY, min_periods=DONCHIAN_ENTRY).min().shift(1).to_numpy()
    up = np.nan_to_num(c > hh, nan=False).astype(bool) & np.isfinite(hh)
    dn = np.nan_to_num(c < ll, nan=False).astype(bool) & np.isfinite(ll)
    ex_l = pd.Series(lo).rolling(DONCHIAN_EXIT, min_periods=DONCHIAN_EXIT).min().to_numpy()
    ex_s = pd.Series(h).rolling(DONCHIAN_EXIT, min_periods=DONCHIAN_EXIT).max().to_numpy()
    return SimInput(o, h, lo, c, up, dn, None, ex_l, ex_s, ex_l, ex_s)


# ---------------------------------------------------------------------------
# C3: TSMOM sign held for H sessions
# ---------------------------------------------------------------------------

def tsmom_hold_trades(frame: pd.DataFrame, H: int, *, mult: float, risk_usd: float,
                      integer: bool) -> tuple[list[Trade], dict]:
    """C3, read literally: "TSMOM sign (12-month) on the same market, held for
    the same median holding period". Decisions fall on a fixed grid every H
    sessions from the first session with a 12-month history and an ATR. At a
    decision close j the position in force (if any) is closed at the next
    open, and a new one is opened at that same open in the direction of the
    12-month sign -- even when the sign is unchanged, so every position is
    held exactly H sessions (the last one until the data ends) and pays its
    own round trip. Sized as if its stop were 3 x ATR(14) away (C3 has no
    stop); an integer size of zero skips that holding period (counted once)."""
    o, h, lo, c = (frame[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(c)
    a = atr_gated(h, lo, c)
    H = max(int(H), 1)
    trades, counts = [], {"entries": 0, "skipped_size": 0, "flat_sign": 0, "decisions": 0}
    first = next((j for j in range(TSMOM_LOOKBACK, n - 1) if np.isfinite(a[j])), None)
    if first is None:
        return trades, counts
    pos, qty, entry_j, entry_px = 0, 0.0, -1, np.nan
    for j in range(first, n - 1, H):
        counts["decisions"] += 1
        if pos != 0:
            trades.append(Trade(pos, entry_j, j + 1, entry_px, o[j + 1], np.nan, qty, "rebalance", False))
            pos, qty = 0, 0.0
        s = int(np.sign(c[j] - c[j - TSMOM_LOOKBACK]))
        if s == 0:
            counts["flat_sign"] += 1
            continue
        dist = 3.0 * a[j]
        q = risk_usd / (dist * mult) if dist > 0 else 0.0
        if integer:
            q = float(np.floor(q + 1e-12))
        if q <= 0:
            counts["skipped_size"] += 1
            continue
        pos, qty, entry_j, entry_px = s, q, j + 1, o[j + 1]
        counts["entries"] += 1
    if pos != 0:
        trades.append(Trade(pos, entry_j, n - 1, entry_px, c[n - 1], np.nan, qty, "data_end", False))
    return trades, counts


# ---------------------------------------------------------------------------
# one market, everything
# ---------------------------------------------------------------------------

@dataclass
class MarketRun:
    market: str
    trades: pd.DataFrame
    daily: dict                     # book key -> (n, 3) array
    counts: pd.DataFrame
    dates: pd.DatetimeIndex
    diagnostics: dict = field(default_factory=dict)


def _trade_rows(trades, booked, frame, key: dict, risk_usd: float) -> list[dict]:
    d = frame["date"].to_numpy()
    stale = frame["stale"].to_numpy()
    new_stale = frame["new_close_stale"].to_numpy()
    roll_after = frame["roll_after"].to_numpy()
    out = []
    for t, b in zip(trades, booked):
        row = dict(key)
        row.update(direction=t.direction, entry_date=d[t.entry_j], exit_date=d[t.exit_j],
                   entry_j=t.entry_j, exit_j=t.exit_j, hold=t.exit_j - t.entry_j,
                   entry_px=t.entry_px, exit_px=t.exit_px, entry_raw=b.entry_raw,
                   exit_raw=b.exit_raw, entry_contract=b.entry_contract,
                   exit_contract=b.exit_contract, stop_init=t.stop_init, qty=t.qty,
                   reason=t.reason, stop_fill=t.stop_fill, n_rolls=b.n_rolls,
                   sides=b.sides, gross=b.gross, slip=b.slip, risk_usd=risk_usd,
                   stale_fill=bool(stale[t.entry_j] or stale[t.exit_j]),
                   stale_roll=bool(any(roll_after[r] and (new_stale[r] or stale[r])
                                       for r in range(t.entry_j, t.exit_j))))
        for lv in LEVELS:
            row["net_" + lv] = b.net(lv, t.qty)
        out.append(row)
    return out


def _run(label_key: dict, trades, frame, m: Market, risk_usd, rows, daily_store, dkey):
    booked = [pnl.book(t, frame, m) for t in trades]
    rows.extend(_trade_rows(trades, booked, frame, label_key, risk_usd))
    daily_store[dkey] = pnl.daily(trades, booked, frame, m)


def run_market(mb: MarketBars, m: Market, *, c3_hold: dict[str, int] | None = None) -> MarketRun:
    """Everything except C3 unless `c3_hold` ({"v0": H, "v0-rev": H}) is
    given -- C3 needs the pooled median hold of the TL runs first."""
    frame = mb.frame
    rows, counts, daily = [], [], {}
    sigs = {R: market_signals(frame, R) for R in PIVOT_SIZES}

    def one(spec, R, share, x, rule, frac_share):
        for sizing, eq in SIZINGS:
            risk = RISK_PCT * eq * frac_share
            r = simulate(x, rule=rule, mult=m.mult, risk_usd=risk, integer=(sizing == "int"))
            key = dict(market=m.name, spec=spec, R=R, share=share, sizing=sizing, equity=eq)
            _run(key, r.trades, frame, m, risk, rows, daily, (spec, R, share, sizing, eq))
            counts.append({**key, **r.counts.as_dict()})

    if c3_hold is None:
        for R, s in sigs.items():
            for ruleset in ("v0", "v0-rev"):
                x = tl_input(s, ruleset)
                rule = "ignore" if ruleset == "v0" else "reverse"
                one(ruleset, R, "sleeve", x, rule, 1.0 / len(PIVOT_SIZES))
                one(ruleset, R, "alone", x, rule, 1.0)
            one("C2", R, "sleeve", chandelier_input(s), "ignore", 1.0 / len(PIVOT_SIZES))
        one("C1", 0, "single", donchian_input(frame), "ignore", 1.0)
    else:
        for rs, H in c3_hold.items():
            spec = "C3|" + rs
            for sizing, eq in SIZINGS:
                risk = RISK_PCT * eq
                tr, cn = tsmom_hold_trades(frame, H, mult=m.mult, risk_usd=risk,
                                           integer=(sizing == "int"))
                key = dict(market=m.name, spec=spec, R=0, share="single", sizing=sizing, equity=eq)
                _run(key, tr, frame, m, risk, rows, daily, (spec, 0, "single", sizing, eq))
                counts.append({**key, **cn, "hold_H": H})

    diag = {}
    if c3_hold is None:
        roll_ix = np.nonzero(frame["roll_after"].to_numpy())[0]
        for R, s in sigs.items():
            br = np.nonzero(s.up | s.dn)[0]
            near = sum(1 for j in br if roll_ix.size and np.min(np.abs(roll_ix - j)) <= 3)
            diag[f"breaks_R{R}"] = int(br.size)
            diag[f"breaks_within_3_of_roll_R{R}"] = int(near)
    return MarketRun(m.name, pd.DataFrame(rows), daily, pd.DataFrame(counts),
                     pd.DatetimeIndex(frame["date"]), diag)
