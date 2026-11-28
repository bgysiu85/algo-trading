"""VA80 reported variants (REGISTERED_va80.md sec 2.5) and the trade lists the study scores. Never ranked, never scored
against a pass bar, cannot spend the holdout.

    primary    sec 2.2 / 2.3 exactly as engine.py (every trade gets `legs` = [(1.0, points, reason)])
    reclaim    trigger = the FIRST 1-minute close back inside the value area (Imre's looser reading)
    one bracket = grid cell (1, 30, 70%) -- not rebuilt here, the grid already runs it
    no stop    the primary entries with the stop removed: ends by the target or the 16:00 close only
    POC half   half out at the POC, the rest to the far edge (same stop on both halves)
    NQ         the primary on NQ -- run by the study with 1 MNQ

Choices the registration leaves open are PRE-RUN Amendment 3 (reclaim deadline, POC half geometry).
"""
from __future__ import annotations

import numpy as np

from strategy.va80 import engine as E
from strategy.va80 import spec as S
from strategy.va80.engine import Params


def iter_setups(store, days, p: Params = Params(), setup_fn=None):
    """Yields (date, status, pack). pack = (sess, prev_date, VAL, VAH, setup dict) when status == 'ok'. The same skip
    rules as engine.evaluate (skip_data / skip_roll); `setup_fn(sess, VAL, VAH)` replaces the engine's setup."""
    prev = E.previous_days(days)
    for d in days:
        s, pd_ = store.sess(d), prev[d]
        ps = store.sess(pd_) if pd_ else None
        if s is None or ps is None:
            yield d, "skip_data", None
            continue
        if len(s.inst | ps.inst) != 1:
            yield d, "skip_roll", None
            continue
        val, vah = store.va(pd_, p.share)
        st = E.setup(s, val, vah, p) if setup_fn is None else setup_fn(s, val, vah)
        yield d, "ok", (s, pd_, val, vah, st)


def finish_setup(s: E.Sess, val: float, vah: float, side_open: str, j: int) -> dict:
    """The tail of engine.setup for an entry at bar j: side, already-rotated test, entry, and (if not rotated) the
    far-edge target and the stop 1 tick past the day's extreme before the entry. Reads bars strictly before j."""
    side = S.SHORT if side_open == S.ABOVE else S.LONG
    rotated = bool(s.l[:j].min() <= val) if side == S.SHORT else bool(s.h[:j].max() >= vah)
    out = {"open": side_open, "trigger": True, "j": j, "side": side, "rotated": rotated,
           "entry_px": float(s.o[j]), "entry_minute": int(s.minute[j])}
    if not rotated:
        out["target"] = val if side == S.SHORT else vah
        out["stop"] = float(s.h[:j].max() + S.TICK) if side == S.SHORT else float(s.l[:j].min() - S.TICK)
    return out


def reclaim_setup(s: E.Sess, val: float, vah: float) -> dict:
    """Reclaim (Imre): the first 1-minute close inside [VAL, VAH] after an open outside is the trigger; entry at the next
    bar's open, which must start by 15:00 (the primary's deadline, as its entry can be no later than 15:00)."""
    side_open = E.open_side(s, val, vah)
    none = {"open": side_open, "trigger": False}
    if side_open == S.INSIDE:
        return none
    inside = np.flatnonzero((s.c >= val) & (s.c <= vah))
    if not len(inside):
        return none
    j = int(inside[0]) + 1
    if j >= s.n or int(s.minute[j]) > S.DEADLINE_MIN:
        return none
    return finish_setup(s, val, vah, side_open, j)


def with_legs(rec: dict) -> dict:
    rec["legs"] = [(1.0, rec["gross_points"], rec["exit_reason"])]
    return rec


def _trades(store, days, p=Params(), setup_fn=None, build=None) -> list[dict]:
    out = []
    for d, status, pack in iter_setups(store, days, p, setup_fn):
        if status != "ok":
            continue
        s, pd_, val, vah, st = pack
        if st["trigger"] and not st["rotated"]:
            out.append(build(s, pd_, val, vah, st))
    return out


def _plain(store):
    return lambda s, pd_, val, vah, st: with_legs(E.trade_record(s, st, val, vah))


def primary_trades(store, days, p: Params = Params()) -> list[dict]:
    return _trades(store, days, p, None, _plain(store))


def reclaim_trades(store, days) -> list[dict]:
    return _trades(store, days, Params(), reclaim_setup, _plain(store))


def nostop_trades(store, days) -> list[dict]:
    def build(s, pd_, val, vah, st):
        far = float("inf") if st["side"] == S.SHORT else float("-inf")
        rec = E.trade_record(s, dict(st, stop=far), val, vah)
        rec["stop"] = None
        return with_legs(rec)
    return _trades(store, days, Params(), None, build)


def poc_legs(s: E.Sess, j: int, side: int, entry_px: float, poc: float, target: float, stop: float) -> list:
    """Two half legs from bar j. Half 1's target is the POC when the POC lies strictly between the entry and the far
    edge, else the far edge; half 2's target is the far edge. Both halves carry the same stop and the usual fill rules
    (a limit needs a tick THROUGH; stop wins a tie; a gap fills at the open)."""
    between = (target < poc < entry_px) if side == S.SHORT else (entry_px < poc < target)
    first = poc if between else target
    legs = []
    for w, tg in ((0.5, first), (0.5, target)):
        _, px, why = E.walk_exit(s, j, side, tg, stop)
        legs.append((w, side * (px - entry_px), why))
    return legs


def poc_half_trades(store, days) -> list[dict]:
    def build(s, pd_, val, vah, st):
        rec = E.trade_record(s, st, val, vah)
        poc = store.profile(pd_).poc * S.TICK
        legs = poc_legs(s, st["j"], st["side"], st["entry_px"], poc, st["target"], st["stop"])
        rec["legs"] = legs
        rec["gross_points"] = sum(w * g for w, g, _ in legs)
        rec["exit_reason"] = legs[-1][2]
        rec["poc"] = poc
        return rec
    return _trades(store, days, Params(), None, build)
