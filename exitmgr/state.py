#!/usr/bin/env python3
"""The exit manager's state file: what it is managing, rewritten atomically (temp file + fsync + os.replace) after every
change, so a crash or a Gateway restart resumes from the last good copy (REGISTERED sec 14 rail 13).

The state is the manager's own record only. The broker's positions are the truth; reconcile (manager.py) compares them.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

SEEN_MAX = 5000            # execution ids remembered (dedupe); oldest dropped first

# Position modes
NEW = "new"                # created by a fill, checks not run yet
WATCH = "watch"            # broker shows a position we cannot explain yet; inside the grace period
MANAGED = "managed"        # protected by the manager's stop; rule actions allowed
ALERT_ONLY = "alert_only"  # broker position not explained by tracked fills (rail 6 / 13): no new orders, safety trims only
OBSERVE_ONLY = "observe_only"  # another app's exit order is on the trade (rail 5): the manager places nothing
UNSAFE = "unsafe"          # unknown / switched-off / near-expiry / mismatched contract (rail 7): alert only
PASSIVE = (ALERT_ONLY, OBSERVE_ONLY, UNSAFE)


@dataclass
class PosState:
    con_id: int
    local_symbol: str = ""
    root: str = ""
    exchange: str = ""
    qty: int = 0                          # signed quantity explained by the fills this manager tracked
    mode: str = NEW
    reason: str = ""
    fill_id: str = ""                     # execId of the fill that opened the position (orderRef XM:<symbol>:<fill-id>)
    first_fill_px: float | None = None
    first_fill_at: str | None = None      # when the manager RECEIVED the opening fill (latency base, rail 3)
    stop_px: float | None = None
    emergency_dist: float | None = None
    over_cap: bool = False
    flat_state: str | None = None         # None | exit_sent | stop_cancelled | failed
    flat_kind: str | None = None          # "flat" (16:55) | "flatten" (kill switch)
    mismatch_since: str | None = None
    pending_since: str | None = None      # a fill not yet fully covered by the stop
    managed_since: str | None = None
    stale: bool = False
    stop_latency_ms: float | None = None
    alerts: list = field(default_factory=list)    # alert codes already raised for this position (no repeats)

    @property
    def long(self) -> bool:
        return self.qty > 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PosState":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class ManagerState:
    positions: dict = field(default_factory=dict)       # str(conId) -> PosState
    seen_exec: list = field(default_factory=list)
    saved_at: str | None = None
    runaway_day: str | None = None
    runaway_day_count: int = 0

    def to_dict(self) -> dict:
        return {"positions": {k: p.to_dict() for k, p in self.positions.items()}, "seen_exec": self.seen_exec[-SEEN_MAX:],
                "saved_at": self.saved_at, "runaway_day": self.runaway_day, "runaway_day_count": self.runaway_day_count}

    @classmethod
    def from_dict(cls, d: dict) -> "ManagerState":
        return cls(positions={str(k): PosState.from_dict(v) for k, v in (d.get("positions") or {}).items()},
                   seen_exec=list(d.get("seen_exec") or []), saved_at=d.get("saved_at"),
                   runaway_day=d.get("runaway_day"), runaway_day_count=int(d.get("runaway_day_count") or 0))


class StateError(Exception):
    pass


def save_atomic(path, obj: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load(path) -> ManagerState | None:
    """None when there is no state file (a fresh start). A file that cannot be read raises StateError."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return ManagerState.from_dict(json.load(f))
    except (ValueError, TypeError, AttributeError) as e:
        raise StateError(f"state file {path} is unreadable: {type(e).__name__}: {e}") from e
