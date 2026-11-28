#!/usr/bin/env python3
"""OWA-v0 controls: C-1 random later timing (scored), C-2 random long and
C-3 random side (reported). REGISTERED_w16_open_window.md sec 8.1-8.2.
Board W16-0040 sub 4.

HOW 1,000 DRAWS ARE MADE
------------------------------------------------------------------------
The exit walk is deterministic, so each control first walks every possible
entry ONCE (each candidate bar of each real trade) and keeps its net; a draw
is then one seeded pick per entry from that table. The result is the same as
walking each draw's picks, at a fraction of the work. Every draw is seeded
with zlib.crc32 of its number (strategy.w16.controls.draw_rng).

Draws are independent per trade: overlap is allowed and neither the daily cap
nor one-at-a-time is re-applied, so a draw has as many trades as the real
book. A control trade whose entry and exit fall on different contracts is
void and counts $0.
"""
from __future__ import annotations

import numpy as np

from strategy.w16 import open_window as OW
from strategy.w16.controls import N_DRAWS, draw_rng
from strategy.w16.costs import ibkr_round_trip, pnl_dollars

VEHICLE = "MNQ"
SCORE_LEVEL = "L2"


def _live(trades: list[dict]) -> list[dict]:
    return [t for t in trades if not t["voided"]]


def net_of(mk, day, fill_idx: int, side: str, stop: float, trail_mult: float,
           level: str = SCORE_LEVEL) -> float:
    """Net $ on 1 MNQ of a market entry at `fill_idx`'s open with this stop,
    walked by the same trail and time exit as the rule."""
    fill_price = float(mk.m1.o[fill_idx])
    exit_idx, exit_price, _ = OW.walk_exit(mk, day, fill_idx, fill_price, side, stop, trail_mult)
    if mk.m1.held[fill_idx] != mk.m1.held[exit_idx]:
        return 0.0
    return pnl_dollars(VEHICLE, fill_price, exit_price, side) - ibkr_round_trip(VEHICLE, level)


def entry_bars(mk, day) -> np.ndarray:
    """The day's 5-min bars starting 08:00..12:00 (the random entry opens)."""
    lo = int(np.searchsorted(mk.b5.day, day.day, side="left"))
    hi = int(np.searchsorted(mk.b5.day, day.day, side="right"))
    minute = mk.b5.minute[lo:hi]
    return lo + np.flatnonzero((minute >= OW.WINDOW_FIRST_MIN) & (minute <= OW.WINDOW_END_MIN))


def _draw_totals(flat: np.ndarray, offsets: np.ndarray, counts: np.ndarray,
                 n_draws: int) -> np.ndarray:
    totals = np.zeros(n_draws)
    if len(counts) == 0:
        return totals
    for i in range(n_draws):
        picks = draw_rng(i).integers(0, counts)
        totals[i] = flat[offsets + picks].sum()
    return totals


def _table(rows: list[list[float]]):
    counts = np.asarray([len(r) for r in rows], dtype=np.int64)
    offsets = np.concatenate(([0], np.cumsum(counts)[:-1])).astype(np.int64) if len(rows) else counts
    flat = np.asarray([v for r in rows for v in r], dtype=float)
    return flat, offsets, counts


def summarise(totals: np.ndarray, real_net: float | None = None) -> dict:
    if len(totals) == 0:
        return {"n_draws": 0, "p5": None, "p50": None, "p95": None}
    out = {"n_draws": int(len(totals)),
           "p5": float(np.percentile(totals, 5)),
           "p50": float(np.percentile(totals, 50)),
           "p95": float(np.percentile(totals, 95))}
    if real_net is not None:
        out["share_of_draws_below_real"] = float((totals < real_net).mean())
    return out


# ---------------------------------------------------------------------
# C-1 random later timing (scored, sec 8.1)
# ---------------------------------------------------------------------

def c1_candidates(mk, day, trade: dict) -> np.ndarray:
    """5-min bars of the same day starting no later than 12:00 whose open
    (first 1-min bar) is at or after the real fill."""
    bars = entry_bars(mk, day)
    return bars[mk.b5.first[bars] >= trade["fill_idx"]]


def c1_totals(mk, trades: list[dict], *, trail_mult: float = OW.TRAIL_ATR,
              n_draws: int = N_DRAWS) -> np.ndarray:
    by_date = {d.date: d for d in mk.days}
    rows = []
    for t in _live(trades):
        day = by_date[t["date"]]
        side, dist = t["direction"], t["stop_dist"]
        nets = []
        for b in c1_candidates(mk, day, t):
            i = int(mk.b5.first[b])
            price = float(mk.m1.o[i])
            stop = price - dist if side == OW.LONG else price + dist
            nets.append(net_of(mk, day, i, side, stop, trail_mult))
        if not nets:
            raise RuntimeError(f"C-1: no candidate bar for the {t['date']} trade -- its own "
                               "fill bar should always be one")
        rows.append(nets)
    return _draw_totals(*_table(rows), n_draws)


# ---------------------------------------------------------------------
# C-2 random long (reported, sec 8.2)
# ---------------------------------------------------------------------

def median_stop_atr(trades: list[dict]) -> float | None:
    live = _live(trades)
    if not live:
        return None
    return float(np.median([t["stop_dist"] / t["atr_signal"] for t in live]))


def c2_totals(mk, trades: list[dict], *, trail_mult: float = OW.TRAIL_ATR,
              n_draws: int = N_DRAWS) -> np.ndarray:
    """On each day the cell traded, the same number of LONG entries at random
    5-min opens 08:00-12:00. Stop distance = the real trades' median stop in
    ATR units x the ATR of the last completed bar before the random entry."""
    mult = median_stop_atr(trades)
    by_date = {d.date: d for d in mk.days}
    per_day: dict[str, int] = {}
    for t in _live(trades):
        per_day[t["date"]] = per_day.get(t["date"], 0) + 1
    rows = []
    for date, n in sorted(per_day.items()):
        day = by_date[date]
        nets = []
        for b in entry_bars(mk, day):
            i = int(mk.b5.first[b])
            price = float(mk.m1.o[i])
            dist = max(OW.nearest_tick(mult * float(mk.atr[b - 1])), OW.TICK)
            nets.append(net_of(mk, day, i, OW.LONG, price - dist, trail_mult))
        rows.extend([nets] * n)
    return _draw_totals(*_table(rows), n_draws)


# ---------------------------------------------------------------------
# C-3 random side (reported, sec 8.2)
# ---------------------------------------------------------------------

def c3_totals(mk, trades: list[dict], *, trail_mult: float = OW.TRAIL_ATR,
              n_draws: int = N_DRAWS) -> np.ndarray:
    """The real entry times, stop distance and exit rules; the side from a
    seeded coin."""
    by_date = {d.date: d for d in mk.days}
    rows = []
    for t in _live(trades):
        day = by_date[t["date"]]
        i, dist = t["fill_idx"], t["stop_dist"]
        price = float(mk.m1.o[i])
        rows.append([net_of(mk, day, i, OW.LONG, price - dist, trail_mult),
                     net_of(mk, day, i, OW.SHORT, price + dist, trail_mult)])
    return _draw_totals(*_table(rows), n_draws)
