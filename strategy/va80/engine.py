"""VA80 engine: session arrays, setup / trigger (sec 2.2) and exits (sec 2.3). REGISTERED_va80.md.

setup()/find_trigger() read bars only up to the entry bar: the bracket closes come from bars BEFORE the trigger
bracket's end, the entry price is the open of the first bar at or after that end, the already-rotated test and the
stop level use bars strictly before the entry bar. walk_exit() is the only function that reads later bars and the
pre-flight never calls it (a test poisons every bar after the entry minute and checks the counts do not move).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from strategy.va80 import spec as S
from strategy.va80.profile import Profile, build_profile, value_area


@dataclass
class Sess:
    date: str
    minute: np.ndarray            # bar-start minute since midnight ET
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    inst: frozenset
    close_min: int                # 960 (16:00) or 780 (13:00, early close)

    @property
    def n(self) -> int:
        return len(self.minute)


def from_frame(df, date_str: str) -> Sess:
    """A Sess from one date's RTH-windowed, time-sorted 1-min bars (strategy.w16.preflight.session_frames)."""
    from strategy.w16.readback import local_naive_et
    from strategy.w16.sessions import session_close_time
    df = df.sort_index()
    ne = local_naive_et(df.index)
    minute = (ne.hour * 60 + ne.minute).to_numpy(dtype=np.int64)
    idc = next((c for c in ("held_id", "instrument_id") if c in df.columns), None)
    inst = frozenset(df[idc].unique().tolist()) if idc else frozenset({0})
    ct = session_close_time(date_str)
    f = lambda k: df[k].to_numpy(dtype=float)
    return Sess(date_str, minute, f("open"), f("high"), f("low"), f("close"),
                f("volume") if "volume" in df.columns else np.ones(len(df)), inst, ct.hour * 60 + ct.minute)


def session_ok(s: Sess) -> bool:
    """sec 2.1: a session missing its 09:30 bar, or with a gap > 5 minutes inside it, is skipped. The stretch from
    the last bar to the session close counts as a gap too (interpretation, written as a PRE-RUN amendment)."""
    if s.n == 0 or s.minute[0] != S.OPEN_MIN:
        return False
    if (np.diff(s.minute) <= 0).any():
        return False
    return int(np.diff(np.r_[s.minute, s.close_min]).max()) <= S.MAX_GAP_MIN


def profile_of(s: Sess) -> Profile:
    return build_profile(s.h, s.l, s.v, last_close=float(s.c[-1]))


@dataclass(frozen=True)
class Params:
    accept: int = S.ACCEPT
    length: int = S.BRACKET_MIN
    share: float = S.VA_SHARE


def open_side(s: Sess, val: float, vah: float) -> str:
    o = float(s.o[0])
    return S.ABOVE if o > vah else (S.BELOW if o < val else S.INSIDE)


def find_trigger(s: Sess, val: float, vah: float, p: Params) -> int | None:
    """Index of the ENTRY bar (the first bar at or after the end of the bracket that completed the acceptance),
    or None. A bracket closes inside if its last 1-min bar closes in [VAL, VAH]; a bracket with no bar does not."""
    run, k = 0, 0
    while True:
        start = S.OPEN_MIN + k * p.length
        end = start + p.length
        if end > S.DEADLINE_MIN:
            return None
        i = int(np.searchsorted(s.minute, end, side="left")) - 1
        inside = i >= 0 and s.minute[i] >= start and val <= s.c[i] <= vah
        run = run + 1 if inside else 0
        if run >= p.accept:
            j = int(np.searchsorted(s.minute, end, side="left"))
            return j if j < s.n else None
        k += 1


def setup(s: Sess, val: float, vah: float, p: Params = Params()) -> dict:
    """{'open', 'trigger', and when triggered: 'j', 'side', 'rotated', 'entry_px', and if not rotated 'target', 'stop'}."""
    side_open = open_side(s, val, vah)
    out = {"open": side_open, "trigger": False}
    if side_open == S.INSIDE:
        return out
    j = find_trigger(s, val, vah, p)
    if j is None:
        return out
    side = S.SHORT if side_open == S.ABOVE else S.LONG
    rotated = bool(s.l[:j].min() <= val) if side == S.SHORT else bool(s.h[:j].max() >= vah)
    out.update(trigger=True, j=j, side=side, rotated=rotated, entry_px=float(s.o[j]),
               entry_minute=int(s.minute[j]))
    if not rotated:
        out["target"] = val if side == S.SHORT else vah
        out["stop"] = float(s.h[:j].max() + S.TICK) if side == S.SHORT else float(s.l[:j].min() - S.TICK)
    return out


def walk_exit(s: Sess, j: int, side: int, target: float, stop: float) -> tuple[int, float, str]:
    """From bar j INCLUSIVE: stop (gap-fill at the open), target (must trade >= 1 tick THROUGH), else the close of
    the last bar of the session. Stop wins a same-bar tie. Returns (exit bar index, price, reason)."""
    o, h, l = s.o[j:], s.h[j:], s.l[j:]
    if side == S.SHORT:
        hit_stop, hit_tgt = h >= stop, l <= target - S.TICK
    else:
        hit_stop, hit_tgt = l <= stop, h >= target + S.TICK
    big = len(o) + 1
    i_s = int(np.argmax(hit_stop)) if hit_stop.any() else big
    i_t = int(np.argmax(hit_tgt)) if hit_tgt.any() else big
    if i_s == big and i_t == big:
        return s.n - 1, float(s.c[-1]), S.TIME
    if i_s <= i_t:
        gapped = (o[i_s] >= stop) if side == S.SHORT else (o[i_s] <= stop)
        return j + i_s, float(o[i_s]) if gapped else float(stop), S.STOP
    return j + i_t, float(target), S.TARGET


def trade_record(s: Sess, st: dict, val: float, vah: float) -> dict:
    """Full trade for a triggered, not-rotated setup (P&L side only; the pre-flight never calls it)."""
    k, px, why = walk_exit(s, st["j"], st["side"], st["target"], st["stop"])
    return {"date": s.date, "side": st["side"], "val": val, "vah": vah, "entry_minute": st["entry_minute"],
            "entry_px": st["entry_px"], "target": st["target"], "stop": st["stop"], "exit_minute": int(s.minute[k]),
            "exit_px": px, "exit_reason": why, "gross_points": st["side"] * (px - st["entry_px"])}


@dataclass
class Store:
    """Lazy per-date Sess / profile / value-area cache over {date_str: RTH frame}."""
    frames: dict
    _s: dict = field(default_factory=dict)
    _p: dict = field(default_factory=dict)
    _va: dict = field(default_factory=dict)

    def sess(self, date: str) -> Sess | None:
        if date not in self._s:
            f = self.frames.get(date)
            s = from_frame(f, date) if f is not None and len(f) else None
            self._s[date] = s if (s is not None and session_ok(s)) else None
        return self._s[date]

    def profile(self, date: str) -> Profile:
        if date not in self._p:
            self._p[date] = profile_of(self.sess(date))
        return self._p[date]

    def va(self, date: str, share: float) -> tuple[float, float]:
        key = (date, share)
        if key not in self._va:
            self._va[key] = value_area(self.profile(date), share)
        return self._va[key]


def previous_days(days: list[str]) -> dict:
    """{day: previous XNYS trading day}. `days` must be the consecutive XNYS trading days."""
    return {d: (days[i - 1] if i else None) for i, d in enumerate(days)}


def evaluate(store: Store, days: list[str], p: Params = Params(), *, want_exit: bool = False) -> list[dict]:
    """One record per day: status ok / skip_data / skip_roll, the open side, trigger, rotated, side, VA width
    and (only when want_exit) the full trade. want_exit=False reads no bar after the entry bar."""
    prev = previous_days(days)
    recs = []
    for d in days:
        r = {"date": d, "year": int(d[:4]), "status": "ok", "open": "", "trigger": False, "rotated": False,
             "side": 0, "va_width": np.nan, "trade": None}
        s, pd_ = store.sess(d), prev[d]
        ps = store.sess(pd_) if pd_ else None
        if s is None or ps is None:
            r["status"] = "skip_data"
        elif len(s.inst | ps.inst) != 1:
            r["status"] = "skip_roll"
        else:
            val, vah = store.va(pd_, p.share)
            r["va_width"] = vah - val
            st = setup(s, val, vah, p)
            r.update(open=st["open"], trigger=st["trigger"])
            if st["trigger"]:
                r.update(rotated=st["rotated"], side=st["side"])
                if want_exit and not st["rotated"]:
                    r["trade"] = trade_record(s, st, val, vah)
        recs.append(r)
    return recs
