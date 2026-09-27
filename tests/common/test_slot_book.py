#!/usr/bin/env python3
"""The slot walk (common/slot_book.py, W03-0003).

Tested against fake engines whose behaviour is known exactly, and against an
independent minute-by-minute forward simulation of a live trader on random
days. The walk (re-run the leg with a blocked bar, restart) and the forward
simulation are different algorithms for the same rule; they must agree trade
for trade.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd
import pytest

from common import slot_book as SB
from common.slot_book import Leg

T0 = pd.Timestamp("2026-03-02 09:00", tz="UTC")


def m(k: int) -> pd.Timestamp:
    return T0 + pd.Timedelta(minutes=k)


@dataclass
class FakeTrade:
    entry_time: str
    exit_time: str
    net: float = -1.0


def fake_engine(spec: dict[Leg, tuple[list[int], int]]):
    """Each leg: (signal bar starts in minutes, hold in bars). Flat -> enters
    on the first allowed signal bar; exits `hold` bars later; can enter again
    only from the bar AFTER its exit bar (the engines test `pos is None` at the
    top of the bar)."""
    calls = []

    def run(leg: Leg, blocked: frozenset):
        calls.append((leg, blocked))
        sig, hold = spec[leg]
        L = SB.BAR_MINUTES[leg.book]
        out, free_from = [], -10**9
        for s in sorted(sig):
            if s < free_from or m(s) in blocked:
                continue
            ex = s + hold * L
            out.append(FakeTrade(str(m(s)), str(m(ex))))
            free_from = ex + L
        return out
    run.calls = calls
    return run


def keys(trades):
    return sorted((leg.book, leg.symbol, t.entry_time, t.exit_time)
                  for leg, ts in trades.items() for t in ts)


# --- forward simulation: an independent live-trader model -------------------

def forward(spec, order, cap, scope):
    """Minute by minute. At each minute: exits whose bar closed now, then, in
    leg order, entries whose signal bar closed now."""
    state = {leg: None for leg in order}      # (entry_start, exit_close) or None
    free_from = {leg: -10**9 for leg in order}
    out = {leg: [] for leg in order}
    refused = 0
    last = max(max(s) + h * SB.BAR_MINUTES[lg.book] for lg, (s, h) in spec.items() if s) + 20
    for now in range(-5, last + 10):
        for leg in order:
            p = state[leg]
            if p and p[1] == now:
                state[leg] = None
        for leg in order:
            if state[leg] is not None:
                continue
            L = SB.BAR_MINUTES[leg.book]
            sig, hold = spec[leg]
            s = now - L                         # the bar that closes now
            if s not in sig or s < free_from[leg]:
                continue
            held = [lg for lg, p in state.items() if p is not None
                    and (scope == "account" or lg.book == leg.book)]
            if len(held) >= cap:
                refused += 1
                continue
            ex = s + hold * L
            state[leg] = (s, ex + L)
            out[leg].append(FakeTrade(str(m(s)), str(m(ex))))
            free_from[leg] = ex + L
    return out, refused


# --- the walk -----------------------------------------------------------------

A, B, C = Leg("MCL", "AAA"), Leg("MCL", "BBB"), Leg("MCL", "CCC")
X = Leg("MC5", "XXX")


def test_no_cap_is_the_free_book():
    spec = {A: ([0, 20], 5), B: ([2], 5)}
    tr, ref = SB.walk([A, B], fake_engine(spec), cap=None)
    assert not ref
    assert keys(tr) == keys({A: fake_engine(spec)(A, frozenset()),
                             B: fake_engine(spec)(B, frozenset())})


def test_refused_leg_re_enters_on_its_next_signal():
    # A holds 00->10 (slot until 11). B signals at 3 and 15. Cap 1.
    spec = {A: ([0], 10), B: ([3, 15], 2)}
    tr, ref = SB.walk([A, B], fake_engine(spec), cap=1)
    assert [r.bar for r in ref] == [m(3)]
    assert [t.entry_time for t in tr[B]] == [str(m(15))]


def test_persistent_signal_is_refused_every_bar_until_a_slot_frees():
    # A in at bar 0, exit bar 10 -> slot free at 11. B signals every minute.
    spec = {A: ([0], 10), B: (list(range(1, 30)), 3)}
    tr, ref = SB.walk([A, B], fake_engine(spec), cap=1)
    # B's bars 1..9 close at 2..10, all while A holds; bar 10 closes at 11,
    # the same minute A's exit bar closes -> exits first -> B enters.
    assert [r.bar for r in ref] == [m(k) for k in range(1, 10)]
    assert tr[B][0].entry_time == str(m(10))


def test_exit_frees_the_slot_for_an_entry_in_the_same_minute():
    spec = {A: ([0], 4), B: ([4], 2)}      # A exit closes at 5; B's bar 4 closes at 5
    tr, ref = SB.walk([A, B], fake_engine(spec), cap=1)
    assert not ref and len(tr[B]) == 1


def test_simultaneous_entries_follow_leg_order():
    spec = {A: ([5], 3), B: ([5], 3)}
    tr, ref = SB.walk([A, B], fake_engine(spec), cap=1)
    assert len(tr[A]) == 1 and not tr[B] and ref[0].leg == B
    tr, ref = SB.walk([B, A], fake_engine(spec), cap=1)
    assert len(tr[B]) == 1 and not tr[A] and ref[0].leg == A


def test_scope_strategy_gives_each_book_its_own_pool():
    spec = {A: ([0], 10), X: ([0], 2)}     # MCL A and MC5 X at the same time
    tr, ref = SB.walk([A, X], fake_engine(spec), cap=1, scope="strategy")
    assert not ref and tr[A] and tr[X]
    tr, ref = SB.walk([A, X], fake_engine(spec), cap=1, scope="account")
    assert ref and not tr[X]


def test_mc5_holds_its_slot_to_the_close_of_its_five_minute_bar():
    # X enters bar 0 (fills 5), exits bar 5 (closes 10). A signals bar 8
    # (fills 9) -- still inside X's exit bar -> refused under a shared cap.
    spec = {X: ([0], 1), A: ([8], 1)}
    tr, ref = SB.walk([X, A], fake_engine(spec), cap=1, scope="account")
    assert [r.bar for r in ref] == [m(8)]


def test_refusals_name_who_held_the_slots():
    spec = {A: ([0], 10), B: ([3], 2)}
    _, ref = SB.walk([A, B], fake_engine(spec), cap=1)
    assert ref[0].open_legs == (("MCL", "AAA"),)


def test_cache_is_shared_across_arms():
    spec = {A: ([0], 10), B: ([3, 15], 2)}
    eng, cache = fake_engine(spec), {}
    SB.walk([A, B], eng, cap=None, cache=cache)
    n = len(eng.calls)
    SB.walk([A, B], eng, cap=1, cache=cache)
    assert len(eng.calls) == n + 1          # only B-with-bar-3-blocked is new


def test_an_engine_that_ignores_the_block_fails_loudly():
    def stubborn(leg, blocked):
        return [FakeTrade(str(m(3 if leg == B else 0)), str(m(12)))]
    with pytest.raises(RuntimeError):
        SB.walk([A, B], stubborn, cap=1)


def test_bad_scope_is_refused():
    with pytest.raises(ValueError):
        SB.walk([A], fake_engine({A: ([0], 1)}), cap=1, scope="book")


@pytest.mark.parametrize("seed", range(60))
@pytest.mark.parametrize("scope", SB.SCOPES)
def test_walk_matches_an_independent_forward_simulation(seed, scope):
    rng = random.Random(seed)
    legs = ([Leg("MCL", f"M{k}") for k in range(rng.randint(2, 6))]
            + [Leg("MC5", f"F{k}") for k in range(rng.randint(1, 5))])
    spec = {}
    for leg in legs:
        L = SB.BAR_MINUTES[leg.book]
        n = rng.randint(0, 25)
        sig = sorted({rng.randrange(0, 300 // L) * L for _ in range(n)})
        spec[leg] = (sig, rng.randint(1, 12))
    cap = rng.randint(1, 3)
    tr, ref = SB.walk(legs, fake_engine(spec), cap=cap, scope=scope)
    fw, fw_ref = forward(spec, legs, cap, scope)
    assert keys(tr) == keys(fw)
    assert len(ref) == fw_ref


def test_gate_for():
    idx = pd.DatetimeIndex([m(k) for k in range(5)])
    assert SB.gate_for(idx, frozenset()) is None
    g = SB.gate_for(idx, frozenset({m(2)}))
    assert list(g) == [True, True, False, True, True]
    with pytest.raises(ValueError):
        SB.gate_for(idx, frozenset({m(99)}))
