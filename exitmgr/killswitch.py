#!/usr/bin/env python3
"""Kill switches of the live exit manager (REGISTERED_exit_cmp.md sec 14 rail 9).

File flags in <XM_OUT_DIR>/control/, checked every loop:
  PAUSE         present = paused. No rule actions (16:55 flat, 4b rule exits / tightening) and no stop-LEVEL changes.
                The resting server-side stops stay. Safety work still runs: a new fill still gets its protective stop and
                the stop quantity still follows the position (a pause never leaves a fill unprotected), and a stale stop
                is still cancelled when the position goes flat (rail 11). Delete the file to resume.
  FLATTEN       market out every managed position (exit order working first, then its stop cancelled), then PAUSE.
                The file is renamed FLATTEN.done-<time> once acted on.
  STOP_MANAGER  the process exits cleanly, leaving the resting stops in place.
Console: Ctrl-C does the same as STOP_MANAGER (run_manager.py).

Runaway guard (rail 9d): more than 20 orders sent in a minute or more than 200 in a NY day -> the guard LATCHES: it refuses
every further order send or modification until the process is restarted (cancels are always allowed), writes PAUSE and
alerts. Cancels are not counted: a cancel can only remove exposure.
"""
from __future__ import annotations

from collections import deque
from datetime import timedelta
from pathlib import Path

from exitmgr.timeutil import iso, ny, utcnow

PAUSE, FLATTEN, STOP = "PAUSE", "FLATTEN", "STOP_MANAGER"


class KillSwitch:
    def __init__(self, control_dir, clock=utcnow):
        self.dir = Path(control_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.clock = clock

    def _p(self, name) -> Path:
        return self.dir / name

    def paused(self) -> bool:
        return self._p(PAUSE).exists()

    def pause(self, reason: str) -> None:
        with open(self._p(PAUSE), "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{iso(self.clock())} {reason}\n")

    def flatten_requested(self) -> bool:
        return self._p(FLATTEN).exists()

    def consume_flatten(self) -> None:
        p = self._p(FLATTEN)
        if p.exists():
            p.replace(self.dir / f"FLATTEN.done-{self.clock().strftime('%Y%m%dT%H%M%S')}")

    def stop_requested(self) -> bool:
        return self._p(STOP).exists()


class RunawayGuard:
    def __init__(self, per_min: int, per_day: int, clock=utcnow, on_trip=None, day: str | None = None, day_count: int = 0):
        self.per_min, self.per_day, self.clock, self.on_trip = per_min, per_day, clock, on_trip
        self.recent: deque = deque()
        self.day, self.day_count = day, day_count
        self.tripped: str | None = None

    def _roll(self, now) -> None:
        d = ny(now).date().isoformat()
        if d != self.day:
            self.day, self.day_count = d, 0
        cut = now - timedelta(seconds=60)
        while self.recent and self.recent[0] <= cut:
            self.recent.popleft()

    def check_and_record(self) -> bool:
        """True = this send is allowed (and is counted). False = refused; the guard is (now) latched."""
        if self.tripped:
            return False
        now = self.clock()
        self._roll(now)
        why = None
        if len(self.recent) >= self.per_min:
            why = f"more than {self.per_min} orders in a minute"
        elif self.day_count >= self.per_day:
            why = f"more than {self.per_day} orders today"
        if why:
            self.tripped = why
            if self.on_trip:
                self.on_trip(why)
            return False
        self.recent.append(now)
        self.day_count += 1
        return True
