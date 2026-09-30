#!/usr/bin/env python3
"""Booking a simulated trade on the ACTUAL HELD CONTRACT, in dollars.

REGISTERED_tl_v0 section 2.1 ("P&L series: the actual held contract, roll
charged") and section 7 ("Reporting the continuous series' P&L" is NOT to be
done). sim.py walks the back-adjusted series; this module converts each fill
to the raw price of the contract actually held on that bar and books the trade
leg by leg:

    leg 1: entry (raw) -> the old contract's close on the first roll session
    leg 2: the new contract's close on that session -> next roll or the exit
    ...

Each roll inside the trade charges two more sides (close old, open new) at the
friction level, per contract. A stop fill charges one tick of the VEHICLE
(spec.Market.tick_usd) per contract, at every friction level. Friction is per
contract per side: $0.50 / $1.25 / $2.50.

Because the signal series is difference-adjusted with the gap measured on the
roll session itself (bars.py), the leg sum equals the adjusted price
difference exactly; `book()` checks it on every trade and raises if not -- a
cheap proof that nothing booked here came from the continuous series by
accident.

THE DAILY MARK-TO-MARKET (for years, halves, realised volatility)
-------------------------------------------------------------------
A trade's P&L is spread over the sessions it was open, on RAW held-contract
prices: entry open -> first close, close -> close (across a roll: the new
contract's roll-session close -> its next close), last close -> exit fill. Costs land on the session they
are paid (entry side on the entry bar, exit side and slippage on the exit bar,
roll sides on the roll bar). Summed, the daily series equals the trade list
to the cent; a test pins it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.tl_v0.sim import Trade
from strategy.tl_v0.spec import FRICTION, LEVELS, Market


class BookingError(AssertionError):
    pass


@dataclass
class Booked:
    gross: float
    slip: float
    sides: int
    n_rolls: int
    entry_raw: float
    exit_raw: float
    entry_contract: str
    exit_contract: str

    def net(self, level: str, qty: float) -> float:
        return self.gross - self.slip - FRICTION[level] * qty * self.sides


def book(t: Trade, frame: pd.DataFrame, m: Market) -> Booked:
    off = frame["off"].to_numpy()
    rc = frame["rc"].to_numpy()
    newc = frame["new_close_raw"].to_numpy()
    roll_after = frame["roll_after"].to_numpy()
    contract = frame["contract"].to_numpy()
    e, x = t.entry_j, t.exit_j
    entry_raw = t.entry_px - off[e]
    exit_raw = t.exit_px - off[x]
    rolls = [r for r in range(e, x) if roll_after[r]]
    move, start = 0.0, entry_raw
    for r in rolls:
        move += rc[r] - start
        start = newc[r]
    move += exit_raw - start
    adj_move = t.exit_px - t.entry_px
    tol = 1e-9 * max(1.0, abs(t.entry_px), abs(entry_raw))
    if not np.isclose(move, adj_move, rtol=1e-9, atol=tol):
        raise BookingError(f"{m.name}: raw legs {move} != adjusted move {adj_move} "
                           f"(entry {e}, exit {x}, rolls {rolls})")
    # the fills must land on the traded contract's OWN bar: every entry is at
    # an open, every exit inside that bar's range (checks the adjusted ->
    # raw mapping against the raw bar, not against itself)
    if not np.isclose(entry_raw, frame["ro"].iat[e], rtol=0, atol=tol):
        raise BookingError(f"{m.name}: entry {entry_raw} is not the open {frame['ro'].iat[e]} "
                           f"of {contract[e]} on bar {e}")
    lo_x, hi_x = frame["rl"].iat[x], frame["rh"].iat[x]
    if not (lo_x - tol <= exit_raw <= hi_x + tol):
        raise BookingError(f"{m.name}: exit {exit_raw} outside {contract[x]}'s bar "
                           f"[{lo_x}, {hi_x}] on bar {x}")
    gross = t.direction * t.qty * m.mult * move
    slip = m.tick_usd * t.qty if t.stop_fill else 0.0
    return Booked(gross, slip, 2 + 2 * len(rolls), len(rolls), entry_raw, exit_raw,
                  str(contract[e]), str(contract[x]))


def daily(trades: list[Trade], booked: list[Booked], frame: pd.DataFrame,
          m: Market, *, friction: dict | None = None, stop_slip: bool = True) -> np.ndarray:
    """(n_sessions, 3) daily net at low/mid/high for one sleeve's trades,
    marked on RAW held-contract prices: each session's change is the traded
    contract's close minus the price the position was carried at from the
    session before (that contract's own close, or on the session after a
    roll, the new contract's close on the roll session).

    `friction` / `stop_slip` default to TL-v0's flat $0.50 / $1.25 / $2.50 with one tick on stop
    fills. TL-v2 (REGISTERED_tl_v2.md Amendment 1, W15-0033) passes its IBKR per-side levels and
    stop_slip=False (the tick is inside the level, never counted twice)."""
    rc = frame["rc"].to_numpy()
    newc = frame["new_close_raw"].to_numpy()
    roll_after = frame["roll_after"].to_numpy()
    base_next = np.where(roll_after, newc, rc)     # carried-at price for session t+1
    n = len(rc)
    gross = np.zeros(n)
    sides = np.zeros(n)          # contract-sides, multiplied by the per-side fee later
    slip = np.zeros(n)
    for t, b in zip(trades, booked):
        e, x, d, q = t.entry_j, t.exit_j, t.direction, t.qty
        k = d * q * m.mult
        if x == e:
            gross[e] += k * (b.exit_raw - b.entry_raw)
        else:
            gross[e] += k * (rc[e] - b.entry_raw)
            if x - e > 1:
                gross[e + 1:x] += k * (rc[e + 1:x] - base_next[e:x - 1])
            gross[x] += k * (b.exit_raw - base_next[x - 1])
        sides[e] += q
        sides[x] += q
        for r in range(e, x):
            if roll_after[r]:
                sides[r] += 2 * q
        if stop_slip:
            slip[x] += b.slip
    fr = FRICTION if friction is None else friction
    out = np.empty((n, len(LEVELS)))
    for i, lv in enumerate(LEVELS):
        out[:, i] = gross - slip - fr[lv] * sides
    return out
