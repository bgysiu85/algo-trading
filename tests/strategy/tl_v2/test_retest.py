"""TL-v2 retest scan (REGISTERED_tl_v2.md sec 2.2 T1-T5, C1-C5) on hand-built bars, and the
look-ahead guards of gate G4. Each test breaks when the rule it names breaks; where the rule is a
timing rule the test also runs a ONE-BAR-SHIFTED implementation on the same fixture and asserts the
answer changes, so the fixture cannot pass vacuously."""
from __future__ import annotations

import numpy as np

from strategy.tl_v2 import retest as RT

N_BARS = 30


def side(direction, n=N_BARS, *, t=5, line_val=100.0, pA=2, a_val=None, qual_at=(5,), raw_at=None,
         line=None):
    """A flat (slope 0) line at `line_val` broken at bar t unless told otherwise."""
    raw = np.zeros(n, bool)
    qual = np.zeros(n, bool)
    for j in (raw_at if raw_at is not None else qual_at):
        raw[j] = True
    for j in qual_at:
        qual[j] = True
    ln = np.full(n, line_val) if line is None else line
    anchor = np.full(n, pA)
    ext = np.full(n, line_val if a_val is None else a_val, float)
    return RT.Side(direction, raw, qual, ln, anchor, ext)


def bars(n=N_BARS, base=103.0):
    """Bars sitting well above a line at 100 (no retest anywhere) - long side."""
    h = np.full(n, base + 1.0)
    l = np.full(n, base - 1.0)
    c = np.full(n, base)
    return h, l, c, np.ones(n)


def run(h, l, c, atr, up=None, dn=None, **kw):
    up = up or side(1)
    dn = dn or side(-1, qual_at=(), raw_at=())
    return RT.scan(h, l, c, atr, up, dn, **kw)


def outcomes(sc):
    return list(sc.events["outcome"])


def test_t5_entry_is_the_first_bar_meeting_t1_and_t2_and_only_that_bar():
    h, l, c, a = bars()
    l[8] = 100.2            # 100.2 <= 100 + 0.25 x 1   (T1)
    c[8] = 101.0            # 101 >= 100 - 0.10 x 1     (T2)
    l[9] = 100.1            # a second retest bar: the setup is used once
    sc = run(h, l, c, a)
    assert list(np.nonzero(sc.ent_up)[0]) == [8] and not sc.ent_dn.any()
    assert outcomes(sc) == ["entry"]
    e = sc.events.iloc[0]
    assert e["t"] == 5 and e["s"] == 8 and e["bars_to_retest"] == 3


def test_t1_uses_bar_s_own_low_not_the_next_bars():
    """One-bar-shift guard: the touch is on bar 8's own low. A scan that read bar s+1's low would
    signal one bar early, on 7 - the fixture tells the two apart."""
    h, l, c, a = bars()
    l[8] = 100.2
    good = run(h, l, c, a)
    assert list(np.nonzero(good.ent_up)[0]) == [8]
    shifted_low = np.roll(l, -1)                    # bar j sees bar j+1's low: the look-ahead
    mutated = run(h, shifted_low, c, a)
    assert list(np.nonzero(mutated.ent_up)[0]) == [7]
    assert list(np.nonzero(mutated.ent_up)[0]) != list(np.nonzero(good.ent_up)[0])


def test_t1_boundary_is_inclusive_at_a_quarter_atr():
    h, l, c, a = bars()
    l[8] = 100.25
    assert run(h, l, c, a).ent_up[8]
    l[8] = 100.26
    assert not run(h, l, c, a).ent_up[8]


def test_t2_a_close_through_the_line_is_a_failure_not_a_retest():
    h, l, c, a = bars()
    l[8] = 99.0
    c[8] = 99.8             # < 100 - 0.10  -> not holding
    l[9] = 100.1            # a later touch must not resurrect the setup
    sc = run(h, l, c, a)
    assert not sc.ent_up.any()
    assert outcomes(sc) == ["failed"] and sc.events.iloc[0]["why"] == "closed_through"


def test_t2_boundary_a_close_exactly_at_line_minus_a_tenth_atr_holds():
    h, l, c, a = bars()
    l[8] = 100.1
    c[8] = 99.9
    assert run(h, l, c, a).ent_up[8]
    c[8] = 99.89
    assert not run(h, l, c, a).ent_up.any()


def test_t3_an_earlier_close_through_kills_a_later_retest():
    h, l, c, a = bars()
    c[7] = 99.5             # bar 7 closes through, before any retest bar
    l[7] = 99.4
    l[8] = 100.1
    sc = run(h, l, c, a)
    assert not sc.ent_up.any() and outcomes(sc) == ["failed"]


def test_t3_the_opposite_raw_break_kills_the_setup_and_wins_a_same_bar_retest():
    h, l, c, a = bars()
    l[8] = 100.1            # would be a retest on 8 ...
    dn = side(-1, qual_at=(), raw_at=(8,))          # ... but an opposite raw break happens on 8 (C2)
    sc = run(h, l, c, a, dn=dn)
    assert not sc.ent_up.any()
    assert outcomes(sc) == ["failed"] and sc.events.iloc[0]["why"] == "opposite_raw_break"


def test_t4_timeout_boundary_bar_t_plus_n_is_still_a_candidate_bar_and_t_plus_n_plus_1_is_not():
    h, l, c, a = bars()
    l[15] = 100.2           # t + N = 5 + 10
    sc = run(h, l, c, a, N=10)
    assert list(np.nonzero(sc.ent_up)[0]) == [15]
    h, l, c, a = bars()
    l[16] = 100.2           # one bar too late
    sc = run(h, l, c, a, N=10)
    assert not sc.ent_up.any() and outcomes(sc) == ["no_retest"]
    assert list(np.nonzero(run(h, l, c, a, N=20).ent_up)[0]) == [16]     # the N = 20 variant


def test_the_frozen_line_keeps_its_slope_and_is_not_the_flat_line():
    """Line through A=(0, 106) and (t=6, 100): slope -1 per bar, frozen. A flat line at 100 would be
    touched by bar 7's low (100.2); the frozen falling line (99 on bar 7) is first touched on bar 9."""
    n = N_BARS
    h, l, c, a = bars(n)
    ln = np.full(n, np.nan)
    ln[6:] = 100.0 - (np.arange(6, n) - 6) * 1.0       # what a still-armed line would show ...
    up = side(1, t=6, pA=0, a_val=106.0, qual_at=(6,), line=ln)
    l[7], l[8] = 100.2, 100.3
    l[9], c[9] = 97.2, 100.0                           # 97.2 <= 97 + 0.25
    sc = run(h, l, c, a, up=up)
    assert list(np.nonzero(sc.ent_up)[0]) == [9]
    flat = side(1, t=6, pA=0, a_val=100.0, qual_at=(6,))     # zero slope
    assert list(np.nonzero(run(h, l, c, a, up=flat).ent_up)[0]) == [7]


def test_the_frozen_line_ignores_everything_the_line_series_does_after_t():
    """G4: the line after t is projected, never re-read. Trash the line series after the break bar."""
    h, l, c, a = bars()
    l[8] = 100.2
    base = run(h, l, c, a)
    ln = np.full(N_BARS, 100.0)
    ln[6:] = 500.0                                      # a later re-anchored line, wildly different
    trashed = run(h, l, c, a, up=side(1, line=ln))
    assert np.array_equal(base.ent_up, trashed.ent_up)


def test_bars_after_the_entry_bar_cannot_change_the_entry_signal():
    h, l, c, a = bars()
    l[8] = 100.2
    base = run(h, l, c, a)
    h2, l2, c2 = h.copy(), l.copy(), c.copy()
    h2[9:], l2[9:], c2[9:] = 400.0, 1.0, 50.0
    assert np.array_equal(base.ent_up[:9], run(h2, l2, c2, a).ent_up[:9])


def test_short_side_is_the_mirror():
    n = N_BARS
    h, l, c, a = (np.full(n, 97.0 + 1), np.full(n, 97.0 - 1), np.full(n, 97.0), np.ones(n))
    dn = side(-1, qual_at=(5,), line_val=100.0)
    up = side(1, qual_at=(), raw_at=())
    h[8] = 99.8             # 99.8 >= 100 - 0.25
    c[8] = 99.0             # 99 <= 100 + 0.10
    sc = RT.scan(h, l, c, a, up, dn)
    assert list(np.nonzero(sc.ent_dn)[0]) == [8] and not sc.ent_up.any()
    c[8] = 100.2            # closes through (above) the resistance-turned line
    assert not RT.scan(h, l, c, a, up, dn).ent_dn.any()


def test_c1_one_pending_setup_a_second_same_side_break_is_ignored_and_counted():
    h, l, c, a = bars()
    l[8] = 100.1
    up = side(1, qual_at=(5, 6), raw_at=(5, 6))
    sc = run(h, l, c, a, up=up)
    assert int(sc.ent_up.sum()) == 1
    assert sorted(outcomes(sc)) == ["entry", "ignored_pending"]


def test_a_new_setup_can_start_after_the_previous_one_resolved():
    h, l, c, a = bars()
    l[8] = 100.1
    l[20] = 100.1
    up = side(1, qual_at=(5, 18), raw_at=(5, 18))
    sc = run(h, l, c, a, up=up)
    assert list(np.nonzero(sc.ent_up)[0]) == [8, 20]


def test_c4_a_retest_on_the_last_bar_cannot_be_filled():
    h, l, c, a = bars()
    l[N_BARS - 1] = 100.1
    sc = run(h, l, c, a, up=side(1, qual_at=(25,)))
    assert not sc.ent_up.any() and outcomes(sc) == ["open_at_end"]
    assert sc.events.iloc[0]["why"] == "retest_on_last_bar"


def test_a_break_still_pending_when_the_data_ends_is_reported_not_dropped():
    n = 10
    h, l, c, a = bars(n)
    sc = run(h, l, c, a, up=side(1, n=n, qual_at=(6,)), dn=side(-1, n=n, qual_at=(), raw_at=()))
    assert outcomes(sc) == ["open_at_end"]


# ---- S/R variant (sec 2.3, C5) ------------------------------------------------------------------

def _sr_side(pivots, **kw):
    s = side(1, **kw)
    s.sr_pivots = pivots
    return s


def test_sr_zone_needs_two_pivots_within_a_quarter_atr_near_the_line_and_confirmed_before_t():
    h, l, c, a = bars()
    l[8] = 100.2
    ok = _sr_side([(0, 5, 100.1), (1, 5, 100.2)], qual_at=(5,))
    ok.sr_pivots = [(0, 4, 100.1), (1, 4, 100.2)]                    # confirmed at 4 < t = 5
    sc = run(h, l, c, a, up=ok)
    assert sc.ent_up[8] and sc.sr_up[8]
    late = _sr_side([(0, 5, 100.1), (1, 5, 100.2)], qual_at=(5,))    # confirmed AT t: not usable
    sc = run(h, l, c, a, up=late)
    assert sc.ent_up[8] and not sc.sr_up[8]
    one = _sr_side([(0, 4, 100.1)], qual_at=(5,))
    assert not run(h, l, c, a, up=one).sr_up[8]
    wide = _sr_side([(0, 4, 100.0), (1, 4, 100.4)], qual_at=(5,))    # 0.4 apart > 0.25
    assert not run(h, l, c, a, up=wide).sr_up[8]
    far = _sr_side([(0, 4, 101.0), (1, 4, 101.1)], qual_at=(5,))     # mean 101.05, line 100: > 0.5 away
    assert not run(h, l, c, a, up=far).sr_up[8]


def test_sr_only_filters_the_entry_it_never_creates_one():
    h, l, c, a = bars()
    l[8] = 100.2
    sc = run(h, l, c, a, up=_sr_side([], qual_at=(5,)))
    assert sc.ent_up[8] and not sc.sr_up.any()
    assert (sc.sr_up <= sc.ent_up).all() and (sc.sr_dn <= sc.ent_dn).all()


def test_sr_zone_window_is_the_250_bars_before_t():
    h, l, c, a = bars(400)
    l[258] = 100.2
    up = side(1, n=400, t=255, qual_at=(255,))
    dn = side(-1, n=400, qual_at=(), raw_at=())
    up.sr_pivots = [(4, 9, 100.1), (5, 10, 100.2)]                   # 251 and 250 bars before t
    sc = RT.scan(h, l, c, a, up, dn)
    assert sc.ent_up[258] and not sc.sr_up[258]                     # pivot 4 is 251 bars back: only one usable pivot
    up.sr_pivots = [(5, 10, 100.1), (6, 11, 100.2)]                  # 250 and 249 bars before t
    sc = RT.scan(h, l, c, a, up, dn)
    assert sc.sr_up[258]
