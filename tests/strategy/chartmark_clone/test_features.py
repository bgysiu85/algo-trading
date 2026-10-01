"""G5: look-ahead guards for F1-F15. Truncation invariance (the features at t are identical when every bar after t is cut
off or replaced by garbage) and a one-bar-shift mutation that MUST break the guard (proves the guard can fail)."""
import numpy as np
import pandas as pd

from strategy.chartmark.data import make_frame
from strategy.chartmark_clone import features as FT
from strategy.chartmark_clone.chartdata import build_chart_data
from tests.strategy.chartmark.synth import walk

FR = walk(5000, 7, drift=0.005, vol=0.3, start="2015-01-05 00:00")
CANDS = [600, 777, 1203, 2048, 3333, 4100]


def feats(fr, t, level=None, j_open=None):
    cd = build_chart_data(fr)
    lv = float(fr.h[t] + 0.01) if level is None else level
    jo = fr.ny[min(t + 1, fr.n - 1)].tz_localize(None) if j_open is None else j_open
    return FT.features_at(cd, t, lv, jo)


def same(a, b):
    assert a.keys() == b.keys()
    for k in a:
        assert (np.isnan(a[k]) and np.isnan(b[k])) or a[k] == b[k], (k, a[k], b[k])


def cut_frame(fr, k):
    return make_frame(fr.t[:k], fr.o[:k], fr.h[:k], fr.l[:k], fr.c[:k], fr.v[:k], fr.roll_after[:k])


def garbage_after(fr, t, seed=0):
    rng = np.random.default_rng(seed)
    o, h, l, c, v = (x.copy() for x in (fr.o, fr.h, fr.l, fr.c, fr.v))
    for a in (o, h, l, c):
        a[t + 1:] = rng.uniform(1, 900, len(a) - t - 1)
    v[t + 1:] = rng.uniform(1, 9e6, len(v) - t - 1)
    return make_frame(fr.t, o, h, l, c, v, fr.roll_after)


def test_features_at_t_equal_on_the_cut_frame_and_on_a_frame_with_garbage_after_t():
    for t in CANDS:
        lv = float(FR.h[t] + 0.01)
        jo = FR.ny[t + 1].tz_localize(None)
        base = feats(FR, t, lv, jo)
        same(base, feats(cut_frame(FR, t + 1), t, lv, jo))
        same(base, feats(garbage_after(FR, t, t), t, lv, jo))


def test_features_are_finite_and_in_range_when_history_allows():
    t = 3333
    f = feats(FR, t)
    for k, v in f.items():
        assert not np.isnan(v), k
    assert f["F1"] in (-1.0, 1.0) and 0 <= f["F10"] <= 1 and 0 <= f["F13"] <= 1 and 0 <= f["F15"] <= 1
    assert 0 <= f["F14"] <= 50 and 0 <= f["F9"] <= 19 and f["F12_session"] in (0, 1, 2, 3) and 0 <= f["F12_weekday"] <= 6


def test_the_guard_can_fail_a_one_bar_look_ahead_is_caught():
    """Replace a feature's input bar t by bar t+1 (a one-bar shift). The truncation test must then differ."""
    t = 2048
    lv = float(FR.h[t] + 0.01)
    jo = FR.ny[t + 1].tz_localize(None)
    leaky_cd = build_chart_data(FR)
    leaky = FT.features_at(leaky_cd, t + 1, lv, jo)               # reads bar t+1: the leak
    honest = feats(cut_frame(FR, t + 1), t, lv, jo)
    diff = [k for k in leaky if not ((np.isnan(leaky[k]) and np.isnan(honest[k])) or leaky[k] == honest[k])]
    assert len(diff) >= 8, diff                                    # nearly every feature moves with a shift


def test_each_feature_is_sensitive_to_a_change_in_bar_t_itself():
    """Not vacuous: perturbing bar t (allowed to matter) moves the features that read it."""
    t = 3333
    base = feats(FR, t)
    o, h, l, c, v = (x.copy() for x in (FR.o, FR.h, FR.l, FR.c, FR.v))
    c[t] += 0.9
    h[t] = max(h[t], c[t]) + 0.1
    mut = make_frame(FR.t, o, h, l, c, v, FR.roll_after)
    new = feats(mut, t, float(FR.h[t] + 0.01), FR.ny[t + 1].tz_localize(None))
    moved = [k for k in base if base[k] != new[k]]
    assert {"F3", "F6", "F7", "F8", "F11", "F13"} <= set(moved), moved


def test_f12_uses_only_the_clock_of_bar_j():
    t = 3333
    for ts, sess in (("2015-03-04 19:00", 0), ("2015-03-04 03:00", 1), ("2015-03-04 09:00", 2), ("2015-03-04 14:00", 3)):
        f = feats(FR, t, None, pd.Timestamp(ts))
        assert f["F12_session"] == sess and f["F12_weekday"] == 2.0


def test_the_table_matches_features_at_and_keeps_manifest_order():
    cd = build_chart_data(FR)
    ts = [800, 1500, 2600]
    man = pd.DataFrame({"candidate_id": [FR.ny[t + 1].tz_localize(None).strftime("%Y-%m-%d %H:%M:%S") for t in ts],
                        "decision_idx": ts, "level": [float(FR.h[t] + 0.01) for t in ts]})
    tab = FT.feature_table(cd, man)
    assert list(tab["candidate_id"]) == list(man["candidate_id"]) and list(tab.columns) == ["candidate_id"] + FT.FEATURE_COLUMNS
    for i, t in enumerate(ts):
        same({k: float(tab.iloc[i][k]) for k in FT.FEATURE_COLUMNS},
             FT.features_at(cd, t, float(man.level[i]), pd.Timestamp(man.candidate_id[i])))
