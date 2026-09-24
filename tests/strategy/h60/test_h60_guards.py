"""Gate G5 -- the hindsight guards, each tested AND mutation-tested
(REGISTERED_h60_v0.md §6.1). Every guard here is shown to fire on the defect
it exists for; a guard that passes everything proves nothing."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from strategy.h60 import engine as E
from strategy.h60 import exits as X
from strategy.h60 import guards as G
from strategy.h60 import rules as R
from strategy.h60.panel import Panel, Universe
from strategy.h60.rules import Book, RuleOut
from strategy.swing import pit_universe as PU
from tests.strategy.h60 import _synth as S

BOOK = Book("TEST", "TEST", "v", True)


def every_bar_rule(a, variant=None):
    return RuleOut(entry=np.ones(a.n, bool), spec=X.ExitSpec(trail_pct=5.0))


# --------------------------------------------------------------------------
# 1. membership by date
# --------------------------------------------------------------------------

def member_panel(start: dt.date, end: dt.date):
    days = S.sessions(60)
    df = S.bars_from_closes("AAA", days, np.full(60 * 7, 100.0), spread=0.0)
    return S.panel([df], spells=S.spells_for(["AAA"], start=start, end=end)), days


def test_no_trade_outside_a_spell_and_the_edges_are_inclusive():
    days = S.sessions(60)
    p, _ = member_panel(days[35], days[45])
    t, _ = E.run_book(p, BOOK, rule_fn=every_bar_rule)
    assert G.check_membership(t, p) == len(t) > 0
    assert t["entry_session"].min() == days[35]
    assert t["entry_session"].max() <= days[45]
    # an entry signalled on the spell's last session's 15:30 bar fills the
    # next day, outside it -- dropped
    assert not ((t["s_signal"] == 45) & (t["s_entry"] == 46)).any()


def test_shifting_a_spell_date_by_one_day_is_caught(monkeypatch):
    """The registered mutation: shift the membership start by a day. The
    engine, fed the mutated Spell.covers, books a trade the day before the
    spell starts; the guard -- re-deriving eligibility from the real spells --
    must refuse it."""
    days = S.sessions(60)
    assert days[36].weekday() == 1             # a Tuesday: start - 1 is a session
    p, _ = member_panel(days[36], None)
    real = PU.Spell.covers

    def off_by_one(self, day):
        return real(self, day + dt.timedelta(days=1))   # admits start - 1

    monkeypatch.setattr(PU.Spell, "covers", off_by_one)
    mutated = Panel.build(p.bars, p.universe, p.grid)
    t, _ = E.run_book(mutated, BOOK, rule_fn=every_bar_rule)
    assert t["s_signal"].min() == 35                     # the leak happened
    monkeypatch.setattr(PU.Spell, "covers", real)
    with pytest.raises(G.HindsightError, match="outside membership"):
        G.check_membership(t, p)


# --------------------------------------------------------------------------
# 2. a bar is knowable only at its close
# --------------------------------------------------------------------------

BUILDABLE = [(R.mcl60, None), (R.mc5_60, None), (R.orb60, None), (R.don60, None),
             (R.vw9_60, "fixed_2r"), (R.vw9_60, "ride_ema9"), (R.vw9_60, "trail_atr"),
             (R.tl60_unchecked, "R3"), (R.tl60_unchecked, "R5"), (R.tl60_unchecked, "R8")]


@pytest.mark.parametrize("fn,variant", BUILDABLE,
                         ids=[f"{f.__name__}-{v}" for f, v in BUILDABLE])
def test_every_buildable_rule_reads_nothing_after_its_bar(fn, variant):
    days = S.sessions(40)
    a = S.panel([S.random_walk("AAA", days, vol=0.012, seed_extra="g5")]).arrays("AAA")
    cuts = list(range(60, a.n - 1, 7)) + list(range(63, a.n - 1, 11))
    assert G.check_no_lookahead(fn, a, cuts, variant) > 0


def test_a_rule_that_peeks_one_bar_ahead_is_caught():
    def peeking(a, variant=None):
        c = pd.Series(a.c)
        return RuleOut(entry=(c.shift(-1) > c).fillna(False).to_numpy(bool),
                       spec=X.ExitSpec(trail_pct=5.0))
    a = S.panel([S.random_walk("AAA", S.sessions(10))]).arrays("AAA")
    with pytest.raises(G.HindsightError, match="read a later bar"):
        G.check_no_lookahead(peeking, a, range(10, 60, 5))


def test_an_exit_input_that_peeks_is_caught():
    def peeking_exit(a, variant=None):
        c = pd.Series(a.c)
        return RuleOut(entry=np.zeros(a.n, bool), spec=X.ExitSpec(close_exit=True),
                       xsig=(c.shift(-2) < c).fillna(False).to_numpy(bool))
    a = S.panel([S.random_walk("AAA", S.sessions(10))]).arrays("AAA")
    with pytest.raises(G.HindsightError, match="xsig"):
        G.check_no_lookahead(peeking_exit, a, range(10, 60, 5))


def test_a_stop_that_reads_the_fill_bar_is_caught():
    def peeking_stop(a, variant=None):
        e = np.ones(a.n, bool)
        # the fill bar's LOW is not known when the stop is placed
        return RuleOut(entry=e, spec=X.ExitSpec(fixed_stop=True),
                       stop=lambda idx, px: a.l[np.minimum(np.asarray(idx) + 1, a.n - 1)])
    a = S.panel([S.random_walk("AAA", S.sessions(10))]).arrays("AAA")
    with pytest.raises(G.HindsightError, match="stop"):
        G.check_no_lookahead(peeking_stop, a, range(10, 60, 5))


def test_the_daily_filter_peeking_at_its_own_day_is_caught(monkeypatch):
    """Mutation: let the TL daily filter read the CURRENT session's daily bar
    (searchsorted side='right'). The cut series then disagrees mid-session."""
    import strategy.h60.rules as RR
    real = RR.daily_filter

    def peeking(a, Rp):
        from common.tl_v0_lines import atr14, find_pivots, walk_line_and_breaks
        o, h, l, c, ses = RR._daily(a)
        at = atr14(h, l, c)
        _, ups = walk_line_and_breaks(len(c), find_pivots(h, Rp, "high"), Rp, c, at, "high")
        pos = np.searchsorted(ses, a.s, side="right") - 1
        return ups[np.clip(pos, 0, None)] | (np.asarray(c)[np.clip(pos, 0, None)]
                                              > np.asarray(o)[np.clip(pos, 0, None)])
    monkeypatch.setattr(RR, "daily_filter", peeking)
    a = S.panel([S.random_walk("AAA", S.sessions(40), vol=0.012, seed_extra="g5")]).arrays("AAA")
    fn = lambda x, v: RuleOut(entry=RR.daily_filter(x, 3), spec=X.ExitSpec())
    with pytest.raises(G.HindsightError):
        G.check_no_lookahead(fn, a, range(60, a.n - 1, 3), "R3")
    monkeypatch.setattr(RR, "daily_filter", real)
    fn = lambda x, v: RuleOut(entry=RR.daily_filter(x, 3), spec=X.ExitSpec())
    G.check_no_lookahead(fn, a, range(60, a.n - 1, 3), "R3")


# --------------------------------------------------------------------------
# 3. entry fills at the next bar's open
# --------------------------------------------------------------------------

def test_real_books_fill_at_the_next_open():
    days = S.sessions(60)
    p = S.panel([S.random_walk(s, days, vol=0.01) for s in ("AAA", "BBB")])
    for fn in (R.mcl60, R.don60, R.orb60):
        t, _ = E.run_book(p, BOOK, rule_fn=fn)
        assert G.check_fills(t, p) == len(t)


def test_a_fill_at_the_signal_close_is_caught():
    days = S.sessions(60)
    p = S.panel([S.random_walk("AAA", days, vol=0.01)])
    t, _ = E.run_book(p, BOOK, rule_fn=R.don60)
    assert len(t)
    a = p.arrays("AAA")
    wrong = t.copy()
    wrong["entry_px"] = a.c[wrong["sig_idx"].to_numpy(int)]      # the mutation
    with pytest.raises(G.HindsightError, match="next bar's open"):
        G.check_fills(wrong, p)
    wrong = t.copy()
    wrong["fill_idx"] = wrong["sig_idx"]
    with pytest.raises(G.HindsightError):
        G.check_fills(wrong, p)


def test_an_engine_that_fills_on_the_signal_bar_is_caught(monkeypatch):
    """Mutate the engine itself (fill = signal bar) and run the guard on its
    output, rather than editing a finished frame."""
    real = E.candidates

    def same_bar(a, out, counts, **kw):
        c = real(a, out, counts, **kw)
        c["fill"] = c["sig"].copy()
        return c
    monkeypatch.setattr(E, "candidates", same_bar)
    days = S.sessions(60)
    p = S.panel([S.random_walk("AAA", days, vol=0.01)])
    t, _ = E.run_book(p, BOOK, rule_fn=R.don60)
    assert len(t)
    with pytest.raises(G.HindsightError):
        G.check_fills(t, p)


def test_tl_cut_exactly_on_a_signal_with_no_support_line():
    """The W14-0003 review's crash: a TL-60 signal with no support line takes
    the fallback stop, which reads the fill bar's slot of at_prev. Cut the
    series AT such bars and ask the guard for their stops: it must run clean,
    not IndexError. Real TL entries rarely lack a support line on a random
    walk, so the entry bits are widened to every no-line bar -- the stop
    function is TL's own."""
    import dataclasses
    a = S.panel([S.random_walk("AAA", S.sessions(40), vol=0.012,
                               seed_extra="tl")]).arrays("AAA")

    def widened(x, variant):
        out = R.tl60_unchecked(x, variant)
        return dataclasses.replace(out, entry=np.isnan(out.ratchet))
    full = widened(a, "R3")
    cuts = [int(t) for t in np.flatnonzero(full.entry) if 40 < t < a.n - 1][:40]
    assert len(cuts) >= 10
    fb = full.stop(np.array(cuts), a.o[np.array(cuts) + 1])
    assert np.isfinite(fb).any()                    # the fallback really ran
    G.check_no_lookahead(widened, a, cuts, "R3")
