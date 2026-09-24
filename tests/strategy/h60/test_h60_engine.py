"""strategy.h60.engine -- what turns a signal into a trade (REGISTERED_h60_v0.md §2.1, §2.3)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.h60 import engine as E
from strategy.h60 import exits as X
from strategy.h60.rules import Book, RuleOut
from tests.strategy.h60 import _synth as S

BOOK = Book("TEST", "TEST", "v", True)


def fixed_rule(bits, spec=None, **kw):
    """A rule that fires exactly on the given symbol-local bar indices."""
    def fn(a, variant):
        e = np.zeros(a.n, bool)
        e[[b for b in bits if b < a.n]] = True
        return RuleOut(entry=e, spec=spec or X.ExitSpec(trail_pct=5.0), **kw)
    return fn


def slot_rule(pairs, spec=None):
    """Fires on the given (session index, slot) bars -- independent of how
    the engine slices a symbol into segments."""
    want = set(pairs)

    def fn(a, variant):
        e = np.array([(int(s), int(b)) in want for s, b in zip(a.s, a.bar)], dtype=bool)
        return RuleOut(entry=e, spec=spec or X.ExitSpec(trail_pct=5.0))
    return fn


def flat_panel(n_days=45, px=100.0, spells=None, symbols=("AAA",)):
    days = S.sessions(n_days)
    frames = [S.bars_from_closes(s, days, np.full(n_days * 7, px), spread=0.0)
              for s in symbols]
    return S.panel(frames, spells=spells), days


def test_warmup_drops_the_first_thirty_sessions():
    p, _ = flat_panel()
    bits = [29 * 7 + 3, 30 * 7 + 3]
    t, c = E.run_book(p, BOOK, rule_fn=fixed_rule(bits))
    assert c["warmup"] == 1 and len(t) == 1
    assert t.loc[0, "s_signal"] == 30


def test_warmup_is_per_symbol_series():
    days = S.sessions(80)
    late = S.bars_from_closes("LATE", days[40:], np.full(40 * 7, 50.0), spread=0.0)
    early = S.bars_from_closes("EARLY", days, np.full(80 * 7, 50.0), spread=0.0)
    p = S.panel([early, late])
    t, c = E.run_book(p, BOOK, symbols=["LATE"], rule_fn=fixed_rule([10 * 7 + 1, 31 * 7 + 1]))
    assert c["warmup"] == 1 and len(t) == 1


def test_fill_is_the_next_bars_open():
    days = S.sessions(40)
    closes = np.full(40 * 7, 100.0)
    opens = closes.copy()
    k = 32 * 7 + 2
    opens[k + 1] = 101.0
    df = S.bars_from_closes("AAA", days, closes, opens=opens, spread=0.0)
    t, _ = E.run_book(S.panel([df]), BOOK, rule_fn=fixed_rule([k]))
    assert t.loc[0, "fill_idx"] == k + 1 and t.loc[0, "entry_px"] == 101.0


def test_one_position_at_a_time_and_the_next_fill_must_be_after_the_exit():
    p, _ = flat_panel(n_days=50)
    k = 31 * 7
    # three signals inside one five-session hold; the fourth is after its exit
    bits = [k, k + 3, k + 10, k + 6 * 7 + 1]
    t, c = E.run_book(p, BOOK, rule_fn=fixed_rule(bits))
    assert list(t["sig_idx"]) == [k, k + 6 * 7 + 1]
    assert c["in_position"] == 2
    assert (t["fill_idx"].iloc[1] > t["exit_idx"].iloc[0])


def test_a_signal_on_the_exit_bar_fills_on_the_next_bar():
    days = S.sessions(45)
    closes = np.full(45 * 7, 100.0)
    lows = closes.copy()
    k = 31 * 7
    lows[k + 3] = 90.0                               # stopped out on bar k+3
    df = S.bars_from_closes("AAA", days, closes, lows=lows, spread=0.0)
    t, c = E.run_book(S.panel([df]), BOOK, rule_fn=fixed_rule([k, k + 3]))
    assert list(t["sig_idx"]) == [k, k + 3]
    assert t.loc[0, "exit_idx"] == k + 3 and t.loc[1, "fill_idx"] == k + 4


def test_membership_on_signal_and_fill_session():
    import datetime as dt
    days = S.sessions(45)
    end = days[34]                                   # member through session 34
    p, _ = flat_panel(spells=S.spells_for(["AAA"], end=end))
    bits = [33 * 7 + 2, 34 * 7 + 6, 35 * 7 + 2]      # ok / fill on 35: not a member / not a member
    t, c = E.run_book(p, BOOK, rule_fn=fixed_rule(bits))
    assert list(t["sig_idx"]) == [33 * 7 + 2]
    assert c["not_member"] == 2


def test_the_five_dollar_floor_is_on_the_fill_price():
    p, _ = flat_panel(px=4.99)
    t, c = E.run_book(p, BOOK, rule_fn=fixed_rule([31 * 7]))
    assert len(t) == 0 and c["below_floor"] == 1


def test_shares_are_floor_of_notional_over_price_and_zero_is_a_skip():
    p, _ = flat_panel(px=333.0)
    t, _ = E.run_book(p, BOOK, rule_fn=fixed_rule([31 * 7]))
    assert t.loc[0, "qty"] == 30 and t.loc[0, "notional"] == pytest.approx(9990.0)
    big = Book("B", "TEST", "v", False, notional=300.0)
    t, c = E.run_book(p, big, rule_fn=fixed_rule([31 * 7]))
    assert len(t) == 0 and c["zero_shares"] == 1


def test_a_rule_that_needs_a_stop_and_has_none_is_dropped():
    p, _ = flat_panel()
    spec = X.ExitSpec(fixed_stop=True)
    stop = lambda idx, px: np.full(len(idx), np.nan)
    t, c = E.run_book(p, BOOK, rule_fn=fixed_rule([31 * 7], spec=spec, stop=stop))
    assert len(t) == 0 and c["no_stop"] == 1


def test_void_beyond_stop_is_counted_not_booked():
    p, _ = flat_panel()
    spec = X.ExitSpec(fixed_stop=True)
    stop = lambda idx, px: np.full(len(idx), 100.0)
    t, c = E.run_book(p, BOOK, rule_fn=fixed_rule([31 * 7], spec=spec, stop=stop))
    assert len(t) == 0 and c["void_beyond_stop"] == 1


def test_session_cap_counts_by_signal_session():
    days = S.sessions(45)
    closes = np.full(45 * 7, 100.0)
    lows = closes.copy()
    k = 31 * 7
    for j in range(k + 1, k + 7):
        lows[j] = 94.0                    # every bar stops the previous trade
    df = S.bars_from_closes("AAA", days, closes, lows=lows, spread=0.0)
    bits = [k, k + 1, k + 2, k + 3, k + 4, k + 5]
    t, c = E.run_book(S.panel([df]), BOOK, rule_fn=fixed_rule(bits, session_cap=2))
    assert len(t) == 2 and c["session_cap"] >= 1


def test_run_book_on_random_walks_is_internally_consistent():
    days = S.sessions(60)
    p = S.panel([S.random_walk(s, days, vol=0.01) for s in ("AAA", "BBB", "CCC")])
    rng = np.random.default_rng(7)
    bits = sorted(rng.choice(np.arange(31 * 7, 60 * 7), 40, replace=False))
    t, c = E.run_book(p, BOOK, rule_fn=fixed_rule(bits))
    assert len(t) > 5
    assert (t["exit_idx"] >= t["fill_idx"]).all()
    assert (t["fill_idx"] == t["sig_idx"] + 1).all()
    assert (t["sessions_held"] <= 5).all()
    assert (t["notional"] <= 10_000).all()
    np.testing.assert_allclose(t["gross"], t["qty"] * (t["exit_px"] - t["entry_px"]))
    for sym, g in t.groupby("symbol"):
        assert (g["fill_idx"].to_numpy()[1:] > g["exit_idx"].to_numpy()[:-1]).all()
    assert c["trades"] == len(t)


def test_concurrency_and_capped_book():
    t = pd.DataFrame({"symbol": list("ABCD"), "entry_session": [1, 1, 1, 1],
                      "entry_mark": [0, 0, 2, 10], "exit_mark": [5, 9, 20, 12],
                      "notional": [10_000.0] * 4})
    c = E.concurrency(t)
    assert c["max_concurrent"] == 3 and c["max_capital"] == 30_000.0
    capped = E.capped_book(t, cap=2)
    assert len(capped) == 3                   # C is refused at mark 2; D fits at 10
    assert "C" not in set(capped["symbol"])


def test_split_voids_and_bad_day_touches():
    t = pd.DataFrame({"symbol": ["A", "A", "B"], "s_signal": [2, 10, 3],
                      "s_entry": [3, 10, 3], "s_exit": [8, 12, 8]})
    v = E.voids_from_splits(t, {("A", 5)})
    assert list(v) == [True, False, False]
    assert list(E.voids_from_splits(t, {("A", 3)})) == [False, False, False]  # split ON entry day: already new basis
    assert list(E.touches_days(t, {("B", 8)})) == [False, False, True]
    # a 15:30 signal read off a bad day counts, though the fill is next session
    assert list(E.touches_days(t, {("A", 2)})) == [True, False, False]


# --------------------------------------------------------------------------
# segments: membership gaps and ticker reuse (the W14-0003 review's item 4)
# --------------------------------------------------------------------------

def gap_panel():
    days = S.sessions(120)
    keep = days[:40] + days[70:]                     # a 30-session hole
    df = S.bars_from_closes("AAA", keep, np.full(len(keep) * 7, 100.0), spread=0.0)
    other = S.bars_from_closes("ZZZ", days, np.full(120 * 7, 100.0), spread=0.0)
    return S.panel([df, other]), days


def test_a_long_gap_starts_a_new_segment_and_re_warms():
    p, days = gap_panel()
    assert p.segment_bounds("AAA") == [(0, 40 * 7), (40 * 7, 90 * 7)]
    assert p.segment_bounds("ZZZ") == [(0, 120 * 7)]
    a = p.arrays("AAA")
    # 10 and 31 sessions after the rejoin at session 70
    t, c = E.run_book(p, BOOK, symbols=["AAA"], rule_fn=slot_rule([(80, 2), (101, 2)]))
    assert c["warmup"] == 1 and len(t) == 1
    assert t.loc[0, "sig_idx"] == 40 * 7 + 31 * 7 + 2
    assert a.s[t.loc[0, "sig_idx"]] == 101


def test_indices_come_back_in_the_full_numbering():
    from strategy.h60 import guards as G
    p, days = gap_panel()
    t, _ = E.run_book(p, BOOK, symbols=["AAA"], rule_fn=slot_rule([(33, 1), (105, 1)]))
    assert len(t) == 2
    assert list(t["sig_idx"]) == [33 * 7 + 1, 40 * 7 + 35 * 7 + 1]
    assert G.check_fills(t, p) == 2


def test_a_rule_never_sees_bars_across_the_gap():
    seen = []

    def spy(a, variant):
        seen.append((int(a.s[0]), int(a.s[-1])))
        return RuleOut(entry=np.zeros(a.n, bool), spec=X.ExitSpec())
    p, _ = gap_panel()
    E.run_book(p, BOOK, symbols=["AAA"], rule_fn=spy)
    assert seen == [(0, 39), (70, 119)]


def test_ticker_reuse_is_two_segments():
    import datetime as dt
    days = S.sessions(80)
    df = S.bars_from_closes("XYZ", days, np.full(80 * 7, 100.0), spread=0.0)
    from strategy.swing.pit_universe import Spell
    spells = [Spell("sp500", "XYZ_OLD", "Old Co", None, days[39], False, True),
              Spell("sp400", "XYZ", "New Co", days[40], None, True, False)]
    p = S.panel([df], spells=spells)
    assert p.segment_bounds("XYZ") == [(0, 40 * 7), (40 * 7, 80 * 7)]


def test_segment_end_is_labelled_apart_from_data_end():
    p, days = gap_panel()
    t, _ = E.run_book(p, BOOK, symbols=["AAA"], rule_fn=slot_rule([(37, 1), (118, 1)]))
    assert list(t["reason"]) == ["segment_end", "data_end"]
