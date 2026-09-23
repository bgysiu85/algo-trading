#!/usr/bin/env python3
r"""The 1-second engine -- W05-0003, `docs/research/REGISTERED_10sec.md` G2+G3.

One symbol-day, no aggregates, no selection -- the same contract as
`strategy/orb/sip.py`, which B0 exists to reproduce at finer resolution (G2).

THE HOST IS NOT DECIDED HERE (REGISTERED_10sec.md section 2)
--------------------------------------------------------------
Direction, the opening-range high/low, and `r` (10% of ATR(14)) are read on
MINUTE bars exactly as registered, and are the SAME number in every arm for a
given symbol-day -- this module takes them as arguments (from the published
ledger, `var/cache/orb_sip/trades/`) and never recomputes them. Only the
TRIGGER drops to sub-minute resolution. "1-minute setup, 10-second trigger."

B0 -- section 3.1, the baseline: the registered resting stop, on seconds
----------------------------------------------------------------------------
A stop order at the opening-range high (long) or low (short), live from
09:35:00 (the first second after the 5-minute range). This is
`sip.trade_symbol_day`'s exact rule, one resolution down -- not a new arm.
G2 exists to prove that.

  * fills in the first PRINTED second whose high/low reaches the trigger:
    at the trigger, or at that second's open if the second opened beyond it
    (gap through) -- identical to sip.py's entry fill.
  * the protective stop is `r` off the EXECUTED fill.
  * amendment A's registered primary (`sip.STOP_ON_ENTRY_BAR = True`)
    carries over: the entry second's own low/high CAN stop the trade out.
  * amendment D carries over one resolution down: on the entry second the
    stop fills AT the stop price (that second's open precedes the entry, so
    it cannot gap the exit); from the NEXT second on, a second opening
    beyond the stop gaps through, exactly like a later bar in sip.py.
  * exit: the stop, or the last print at or before 15:59:59.

T1 -- section 3.2, H-X1: the 10-second confirmation trigger
----------------------------------------------------------------------------
  * ten-second bars, clock-aligned to :00/:10/.../:50 within each minute,
    built from the 1-second prints. A 10-second interval with no print is
    not a bar and cannot trigger.
  * trigger: the first 10-second bar starting at or after 09:35:00 whose
    CLOSE is STRICTLY beyond the level (never a wick -- a high/low touch
    that closes back inside does not count).
  * fill: the OPEN of the first printed second at or after the trigger
    bar's end -- a marketable order sent when the bar completes. Never a
    price from inside the trigger bar itself.
  * no entry from a trigger bar ENDING after 15:59:00.
  * stop: `r` off the executed fill. Inside the fill second, if that
    second's own range reaches the stop, it fills AT THE STOP PRICE
    (amendment D, one resolution down; the `same_second` convention of
    amendment E.2 -- the conservative side), never at that second's open.
    From the next second on, a second opening beyond the stop gaps through.
  * exit: the stop, or the last print at or before 15:59:59.

Both arms return at most one trade (one entry per symbol-day, by
construction -- the loop returns on the first qualifying trigger and never
resumes searching after an exit).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

LONG, SHORT = 1, -1

RANGE_MINUTES = 5
RANGE_END_SEC = 9 * 3600 + 30 * 60 + RANGE_MINUTES * 60      # 09:35:00
LAST_SEC = 15 * 3600 + 59 * 60 + 59                          # 15:59:59
LAST_TRIGGER_END_SEC = 15 * 3600 + 59 * 60                   # 15:59:00

# why a symbol-day produced no trade, for either arm
NO_SECONDS = "NO_SECONDS"        # nothing printed at/after the range end
NO_TRIGGER = "NO_TRIGGER"        # the level (B0) or the close (T1) was never reached
NO_BAR_AFTER_TRIGGER = "NO_BAR_AFTER_TRIGGER"   # T1: no print at/after the trigger bar ends
TOO_LATE = "TOO_LATE"            # T1: the trigger bar ends after 15:59:00
OK = "OK"


@dataclass
class SecTrade:
    side: int
    entry_sec: int
    entry_px: float
    exit_sec: int
    exit_px: float
    exit_reason: str          # stop | session_end
    stop_px: float
    r: float
    trigger_sec: int          # B0: the entry second itself; T1: the trigger bar's start


def _trim(sod: np.ndarray, o, h, l, c):
    """Only printed seconds at or before 15:59:59 are ever tradeable."""
    keep = sod <= LAST_SEC
    return (sod[keep], np.asarray(o, float)[keep], np.asarray(h, float)[keep],
            np.asarray(l, float)[keep], np.asarray(c, float)[keep])


def _walk_stop(sod, o, h, l, c, side: int, entry_i: int, stop_px: float):
    """From `entry_i` (inclusive) to the end: the first second whose range
    reaches `stop_px`. Returns (exit_i, exit_px, reason).

    On the entry second itself (`j == entry_i`) the fill is the stop price,
    never that second's open -- the second's open precedes the entry
    (amendment D), so it cannot be used to gap the exit. From the NEXT
    second on, a second that opened beyond the stop gaps through.
    """
    stopped = (l[entry_i:] <= stop_px) if side == LONG else (h[entry_i:] >= stop_px)
    if not stopped.any():
        return len(sod) - 1, float(c[-1]), "session_end"
    j = entry_i + int(np.argmax(stopped))
    if j > entry_i:
        exit_px = min(stop_px, o[j]) if side == LONG else max(stop_px, o[j])
    else:
        exit_px = stop_px
    return j, float(exit_px), "stop"


def b0_trade(sod, o, h, l, c, side: int, or_high: float, or_low: float,
             r: float) -> tuple[SecTrade | None, str]:
    """B0, one symbol-day. `sod`/`o`/`h`/`l`/`c` are that day's PRINTED
    1-second bars, sorted ascending by `sod` (seconds since midnight, ET).
    `side`, `or_high`/`or_low` and `r` come from the published minute-bar
    ledger and are not recomputed here (section 2)."""
    sod, o, h, l, c = _trim(np.asarray(sod), o, h, l, c)
    trigger = or_high if side == LONG else or_low
    after = np.flatnonzero(sod >= RANGE_END_SEC)
    if after.size == 0:
        return None, NO_SECONDS

    reach = (h[after] >= trigger) if side == LONG else (l[after] <= trigger)
    if not reach.any():
        return None, NO_TRIGGER
    i = after[int(np.argmax(reach))]

    entry_px = max(trigger, o[i]) if side == LONG else min(trigger, o[i])
    stop_px = entry_px - side * r
    exit_i, exit_px, reason = _walk_stop(sod, o, h, l, c, side, i, stop_px)

    return SecTrade(side=side, entry_sec=int(sod[i]), entry_px=float(entry_px),
                    exit_sec=int(sod[exit_i]), exit_px=exit_px,
                    exit_reason=reason, stop_px=float(stop_px), r=float(r),
                    trigger_sec=int(sod[i])), OK


def build_10s_bars(sod: np.ndarray, o, h, l, c) -> pd.DataFrame:
    """Clock-aligned 10-second OHLC bars from 1-second prints. A bucket with
    no print is not a bar -- it is simply absent, never a placeholder."""
    bucket = (np.asarray(sod) // 10) * 10
    df = pd.DataFrame({"bucket": bucket, "o": np.asarray(o, float),
                       "h": np.asarray(h, float), "l": np.asarray(l, float),
                       "c": np.asarray(c, float)})
    g = df.groupby("bucket", sort=True)
    bars = pd.DataFrame({"open": g["o"].first(), "high": g["h"].max(),
                        "low": g["l"].min(), "close": g["c"].last()})
    bars.index.name = "bucket_start"
    return bars.reset_index()


def t1_trade(sod, o, h, l, c, side: int, or_high: float, or_low: float,
             r: float) -> tuple[SecTrade | None, str]:
    """T1 (H-X1), one symbol-day. Same inputs and host as `b0_trade`."""
    sod, o, h, l, c = _trim(np.asarray(sod), o, h, l, c)
    if sod.size == 0:
        return None, NO_SECONDS
    trigger = or_high if side == LONG else or_low

    bars = build_10s_bars(sod, o, h, l, c)
    live = bars[bars["bucket_start"] >= RANGE_END_SEC]
    if live.empty:
        return None, NO_SECONDS

    beyond = ((live["close"] > trigger) if side == LONG
              else (live["close"] < trigger)).to_numpy()
    if not beyond.any():
        return None, NO_TRIGGER
    trig_row = int(np.argmax(beyond))
    trig_bucket_start = int(live["bucket_start"].to_numpy()[trig_row])
    trig_bucket_end = trig_bucket_start + 10

    if trig_bucket_end > LAST_TRIGGER_END_SEC:
        return None, TOO_LATE

    after = np.flatnonzero(sod >= trig_bucket_end)
    if after.size == 0:
        return None, NO_BAR_AFTER_TRIGGER
    i = int(after[0])

    entry_px = float(o[i])          # a marketable order: fills at the open of
                                    # the first printed second, no gap logic --
                                    # there is no "trigger price" to gap past.
    stop_px = entry_px - side * r
    exit_i, exit_px, reason = _walk_stop(sod, o, h, l, c, side, i, stop_px)

    return SecTrade(side=side, entry_sec=int(sod[i]), entry_px=entry_px,
                    exit_sec=int(sod[exit_i]), exit_px=exit_px,
                    exit_reason=reason, stop_px=float(stop_px), r=float(r),
                    trigger_sec=trig_bucket_start), OK
