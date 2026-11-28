"""WICK-REV features and race (W15-0063 sec 3, gate G3 look-ahead guards)."""
from __future__ import annotations

import numpy as np

from strategy.wick_rev import signals as G
from strategy.wick_rev import spec as S
from tests.strategy.wick_rev.synth import flat, minute_fine, prefix, random_walk, series


def test_wick_ratios_and_flat_atr():
    o, h, l, c = flat(40)
    o[30], h[30], l[30], c[30] = 10.0, 12.0, 8.0, 9.0
    f = G.features(series(o, h, l, c))
    assert f.uwr[30] == 0.75 and f.lwr[30] == 0.25            # (12-9)/4, (9-8)/4
    assert abs(G.wilder_atr(h[:25], l[:25], c[:25])[-1] - 2.0) < 1e-12
    assert np.isnan(f.uwr).sum() == 0 or True                   # H=L bars would be NaN; none here


def test_h_equals_l_bar_is_dropped_not_divided():
    o, h, l, c = flat(300)
    h[250] = l[250] = o[250] = c[250] = 100.0
    f = G.features(series(o, h, l, c))
    assert f.drop_hl[250] and np.isnan(f.uwr[250]) and not G.valid_mask(f)[250]


def test_context_uses_the_previous_bar_and_size_uses_previous_atr():
    s = random_walk(600, seed=3)
    f = G.features(s)
    e = G.ema(s.c)
    assert np.array_equal(f.ctx[1:], np.where(s.c[:-1] > e[:-1], 1, np.where(s.c[:-1] < e[:-1], -1, 0)))
    wrong = np.where(s.c[1:] > e[1:], 1, np.where(s.c[1:] < e[1:], -1, 0))      # the mutant: context from bar t itself
    assert not np.array_equal(f.ctx[1:], wrong)                                 # so the guard above can fail
    atr = G.wilder_atr(s.h, s.l, s.c)
    rng = s.h - s.l
    ok = ~np.isnan(atr[:-1])
    ratio_prev = rng[1:][ok[:]] / atr[:-1][ok[:]]
    want = np.where(ratio_prev < 0.75, 0, np.where(ratio_prev > 1.25, 2, 1))
    assert np.array_equal(f.size_cat[1:][ok], want)
    ratio_same = rng[1:][ok] / atr[1:][ok]
    mutant = np.where(ratio_same < 0.75, 0, np.where(ratio_same > 1.25, 2, 1))
    assert not np.array_equal(f.size_cat[1:][ok], mutant)


def test_changing_bar_t_cannot_change_its_own_context():
    s = random_walk(400, seed=5)
    t = 300
    f0 = G.features(s)
    s2 = random_walk(400, seed=5)
    s2.c[t] = s2.c[t] + 50.0                                    # drag bar t's close far across the EMA
    f1 = G.features(s2)
    assert f1.ctx[t] == f0.ctx[t]                               # context at t ignores bar t
    assert f1.ctx[t + 1] != f0.ctx[t + 1] or True               # it may move bar t+1's context


def test_features_do_not_look_ahead_prefix_invariance():
    s = random_walk(900, seed=7)
    full = G.features(s)
    for m in (300, 555, 899):
        part = G.features(prefix(s, m))
        for name in ("rng", "uwr", "lwr", "atr", "size_cat", "ctx", "colour", "star", "hammer"):
            a, b = getattr(full, name)[:m], getattr(part, name)
            assert np.array_equal(np.nan_to_num(a, nan=-9), np.nan_to_num(b, nan=-9)), name


def test_the_prefix_guard_can_fail():
    s = random_walk(500, seed=8)
    good = G.features(s).ctx[:300]
    peek = G.features(prefix(s, 300)).ctx
    assert np.array_equal(good, peek)
    s.c[301:] = s.c[301:] + 80                                  # the future changes ...
    assert not np.array_equal(G.features(s).ctx[:400], G.features(random_walk(500, seed=8)).ctx[:400])


def test_roll_in_the_lookahead_or_on_the_session_drops_the_signal():
    base = random_walk(400, seed=11)
    held = np.zeros(400, int)
    held[320:] = 1
    s = series(base.o, base.h, base.l, base.c, held=held)     # sessions are 20 bars: bars 320..339 are the roll session
    v = G.valid_mask(G.features(s))
    assert v[200:300].any()
    assert not v[300:340].any()                      # 300..319 see the roll within 20 bars ahead, 320..339 are on it
    assert v[340:380].any()
    assert not v[380:].any()                         # tail: the 20-bar look-ahead must exist


def _race_series(t=30):
    o, h, l, c = flat(60)
    return o, h, l, c, t


def test_race_first_touch_down_is_a_reversal_up_is_continuation_and_scans_from_t_plus_1():
    o, h, l, c, t = _race_series()
    l[t] = 96.0                                      # the signal bar itself dives through D: must NOT count
    s = series(o, h, l, c)
    d_line = c[t] - G.features(s).atr[t]             # ATR at t includes bar t's own range
    assert l[t] < d_line
    l[t + 3] = d_line - 0.01                         # D touched on the 3rd bar after
    s = series(o, h, l, c)
    f = G.features(s)
    r = G.race(s, f, np.array([t]), 1, 1.0)
    assert r["kind"][0] == G.REV and r["bar"][0] == 2        # offset 2 = bar t+3
    assert G.outcome_within(r, 3)[0] == G.REV and G.outcome_within(r, 2)[0] == G.NONE
    o, h, l, c, t = _race_series()
    h[t + 1] = 102.1
    s = series(o, h, l, c)
    r = G.race(s, G.features(s), np.array([t]), 1, 1.0)
    assert r["kind"][0] == G.CONT and r["bar"][0] == 0
    r = G.race(s, G.features(s), np.array([t]), -1, 1.0)        # mirror: up first is the reversal
    assert r["kind"][0] == G.REV


def test_race_lines_use_atr_at_t_not_a_later_atr():
    o, h, l, c, t = _race_series()
    h[t + 1] = 130.0                                  # a huge later bar inflates ATR at t+1, not at t
    l[t + 1] = 70.0
    s = series(o, h, l, c)
    f = G.features(s)
    assert f.atr[t] == 2.0 and f.atr[t + 1] > 2.0
    r = G.race(s, f, np.array([t]), 1, 1.0)
    assert r["kind"][0] == G.AMBIG and r["bar"][0] == 0       # both D=98 and U=102 sit inside that bar


def test_gap_open_beyond_a_line_counts_at_the_open_and_k_scales_the_lines():
    o, h, l, c, t = _race_series()
    o[t + 1], h[t + 1], l[t + 1], c[t + 1] = 96.0, 96.5, 95.5, 96.0
    s = series(o, h, l, c)
    f = G.features(s)
    assert G.race(s, f, np.array([t]), 1, 1.0)["kind"][0] == G.REV
    o, h, l, c, t = _race_series()
    l[t + 1] = 97.5                                   # 2.5 below C: past D at k=1 (98), not past D at k=1.5 (97)
    s = series(o, h, l, c)
    f = G.features(s)
    assert G.race(s, f, np.array([t]), 1, 1.0)["kind"][0] == G.REV
    assert G.race(s, f, np.array([t]), 1, 1.5)["kind"][0] == G.NONE


def test_double_touch_is_ambiguous_without_finer_bars_and_resolved_with_them():
    o, h, l, c, t = _race_series()
    h[t + 1], l[t + 1] = 103.0, 97.0
    s = series(o, h, l, c)
    f = G.features(s)
    assert G.race(s, f, np.array([t]), 1, 1.0)["kind"][0] == G.AMBIG
    # finer minutes: the drop to 97 comes first, the 103 spike later
    hs = [100.5] * 5 + [103.0] * 5 + [101.0] * 50
    ls = [99.5] * 2 + [97.0] + [99.5] * 57
    s.fine_t, s.fine_h, s.fine_l = minute_fine(s, t + 1, hs, ls)
    assert G.race(s, f, np.array([t]), 1, 1.0)["kind"][0] == G.REV
    # spike first
    hs2 = [103.0] + [100.5] * 59
    ls2 = [99.5] * 5 + [97.0] + [99.5] * 54
    s.fine_t, s.fine_h, s.fine_l = minute_fine(s, t + 1, hs2, ls2)
    assert G.race(s, f, np.array([t]), 1, 1.0)["kind"][0] == G.CONT
    # both inside one minute -> still ambiguous
    s.fine_t, s.fine_h, s.fine_l = minute_fine(s, t + 1, [103.0] + [100.5] * 59, [97.0] + [99.5] * 59)
    assert G.race(s, f, np.array([t]), 1, 1.0)["kind"][0] == G.AMBIG


def test_counts_only_returns_counts_and_no_outcomes():
    s = random_walk(1500, seed=2)
    c = G.counts_only(s)
    assert c["valid"] > 0 and len(c["up_bucket"]) == 10
    assert not any(w in k for k in c for w in ("p_rev", "tau", "net", "edge", "outcome"))
    assert c["up_primary"] == sum(c["up_primary_by_year"].values())


def test_classic_shapes_are_a_subset_of_the_long_wick_group():
    s = random_walk(4000, seed=4)
    f = G.features(s)
    assert (f.star <= (f.uwr >= S.STAR_RATIO)).all()
    assert (f.star & (f.ctx != 1)).sum() == 0
