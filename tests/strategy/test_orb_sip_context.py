"""Amendment H: the gate's rule, its bar, and the four controls."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.orb import sip_context as X


def _led(rows):
    """rows: (date, symbol, side, R_BASE)"""
    return pd.DataFrame(rows, columns=["date", "symbol", "side", "R_BASE"])


def _state(pairs):
    return pd.DataFrame([{"date": d, "sign": s, "bars": 5, "error": ""}
                         for d, s in pairs])


# -------------------------------------------------------------- the variable

def test_or_sign_reads_last_close_against_first_open_in_the_window():
    """Built so each way of getting the window wrong flips the sign.

    569 opens high, 575 closes low, and the 570 bar itself closes DOWN -- so
    reaching one bar early, one bar late, or taking the first close instead of
    the last all produce -1 where the registered window gives +1.
    """
    m = [569, 570, 571, 574, 575]
    o = [900, 200, 201, 202, 202]
    c = [900, 199, 202, 205, 100]
    assert X.or_sign(m, o, c) == 1          # 205 against 200


def test_or_sign_is_negative_when_the_index_falls():
    assert X.or_sign([570, 574], [200, 199], [199, 198]) == -1


def test_or_sign_is_flat_on_an_exact_tie_rather_than_an_error():
    assert X.or_sign([570, 574], [200, 200], [200, 200]) == 0


def test_or_sign_refuses_a_window_with_no_bars():
    with pytest.raises(ValueError, match="no index bars"):
        X.or_sign([560, 561], [1, 1], [1, 1])


# --------------------------------------------------------------- H.1 buckets

def test_a_long_on_an_up_day_is_with_and_a_short_is_against():
    d = _led([("d1", "A", 1, 0.0), ("d1", "B", -1, 0.0)])
    got = list(X.bucket(d, _state([("d1", 1)])))
    assert got == [X.WITH, X.AGAINST]


def test_the_buckets_flip_on_a_down_day():
    d = _led([("d1", "A", 1, 0.0), ("d1", "B", -1, 0.0)])
    got = list(X.bucket(d, _state([("d1", -1)])))
    assert got == [X.AGAINST, X.WITH]


def test_a_flat_session_puts_every_trade_in_flat():
    d = _led([("d1", "A", 1, 0.0), ("d1", "B", -1, 0.0)])
    assert set(X.bucket(d, _state([("d1", 0)]))) == {X.FLAT}


def test_a_session_with_no_index_reading_is_refused_never_guessed():
    d = _led([("d1", "A", 1, 0.0), ("d2", "B", 1, 0.0)])
    with pytest.raises(ValueError, match="no index reading"):
        X.bucket(d, _state([("d1", 1)]))


def test_a_nan_sign_counts_as_no_reading():
    d = _led([("d1", "A", 1, 0.0)])
    st = _state([("d1", 1)])
    st.loc[0, "sign"] = np.nan
    with pytest.raises(ValueError, match="no index reading"):
        X.bucket(d, st)


# ------------------------------------------------------- H.3(a) shuffled sign

def _packable(rows):
    d = _led(rows)
    d["context"] = ""
    return d


def test_the_null_preserves_the_up_down_proportion():
    # 4 sessions, 3 up 1 down; every permutation must keep that mix
    rows = [(f"d{i}", f"S{i}", 1, float(i)) for i in range(4)]
    out = X.shuffled_sign_null(_packable(rows), np.array([1, 1, 1, -1.0]), draws=50)
    # all trades are long, so WITH == sessions marked up == always 3 of 4
    assert out["obs_mean"] == pytest.approx(np.mean([0.0, 1.0, 2.0]))


def test_the_null_permutes_and_never_empties_the_retained_bucket():
    """Two sessions, one up one down, every trade long.

    A permutation always leaves exactly one WITH session. Drawing signs with
    replacement would sometimes mark both sessions down, leaving the bucket
    empty -- which is how a resampling null quietly widens itself.
    """
    rows = [("d0", "A", 1, 1.0), ("d1", "B", 1, 5.0)]
    out = X.shuffled_sign_null(_packable(rows), np.array([1.0, -1.0]), draws=300)
    assert out["valid_draws"] == 300


def test_drop5_removes_the_five_largest_symbols():
    rows = [(f"d{i}", f"S{i}", 1, float(8 - i)) for i in range(8)]
    out = X.shuffled_sign_null(_packable(rows), np.ones(8), draws=10)
    assert out["obs_mean"] == pytest.approx(4.5)      # 8..1
    assert out["obs_drop5"] == pytest.approx(6.0)     # 3 + 2 + 1


def test_the_null_percentile_is_the_registered_ninety_fifth():
    assert X.NULL_PCT == 95


def test_a_gate_that_only_relabels_does_not_beat_its_own_shuffle():
    rng = np.random.default_rng(0)
    n = 400
    rows = [(f"d{i:03d}", f"S{i%40:02d}", 1 if i % 2 else -1,
             float(rng.normal())) for i in range(n)]
    signs = np.where(rng.random(n) > 0.5, 1.0, -1.0)
    out = X.shuffled_sign_null(_packable(rows), signs, draws=300)
    assert out["mean_beats"] is False


def test_a_real_effect_does_beat_the_shuffle():
    # every WITH trade pays +1, every AGAINST trade pays -1
    n = 300
    rows, signs = [], []
    for i in range(n):
        s = 1 if i % 2 == 0 else -1
        side = 1 if i % 3 else -1
        rows.append((f"d{i:03d}", f"S{i%30:02d}", side, 1.0 if side == s else -1.0))
        signs.append(float(s))
    out = X.shuffled_sign_null(_packable(rows), np.array(signs), draws=300)
    assert out["obs_mean"] == pytest.approx(1.0)
    assert out["mean_beats"] is True


def test_the_null_refuses_a_sign_vector_of_the_wrong_length():
    rows = [(f"d{i}", "A", 1, 0.0) for i in range(3)]
    with pytest.raises(ValueError, match="signs for"):
        X.shuffled_sign_null(_packable(rows), np.array([1.0, -1.0]), draws=5)


def test_the_null_is_seeded_and_repeatable():
    rows = [(f"d{i:02d}", f"S{i%5}", 1 if i % 2 else -1, float(i)) for i in range(40)]
    s = np.where(np.arange(40) % 3 == 0, 1.0, -1.0)
    a = X.shuffled_sign_null(_packable(rows), s, draws=100)
    b = X.shuffled_sign_null(_packable(rows), s, draws=100)
    assert a["mean_p"] == b["mean_p"] and a["drop5_p"] == b["drop5_p"]


# ------------------------------------------------------------ H.3(d) / H.3(b)

def test_the_delta_is_with_less_against_per_symbol():
    d = _led([("d1", "A", 1, 5.0), ("d1", "A", -1, 1.0),
              ("d1", "B", 1, 2.0), ("d1", "B", -1, 3.0)])
    d["context"] = [X.WITH, X.AGAINST, X.WITH, X.AGAINST]
    got = X.delta_drop(d)
    assert got["delta"] == pytest.approx(3.0)      # (5-1) + (2-3)
    assert got["drop1"] == pytest.approx(-1.0)     # less A's +4


def test_flat_trades_are_excluded_from_the_delta():
    d = _led([("d1", "A", 1, 5.0), ("d1", "A", -1, 1.0), ("d1", "C", 1, 99.0)])
    d["context"] = [X.WITH, X.AGAINST, X.FLAT]
    assert X.delta_drop(d)["symbols"] == 1


def test_within_side_splits_each_bucket_by_long_and_short():
    d = _led([("d1", "A", 1, 1.0), ("d1", "B", -1, 3.0),
              ("d1", "C", 1, 5.0), ("d1", "D", -1, 7.0)])
    d["context"] = [X.WITH, X.WITH, X.AGAINST, X.AGAINST]
    t = X.within_side(d)
    assert t.loc["long", ("mean_R", X.WITH)] == pytest.approx(1.0)
    assert t.loc["short", ("mean_R", X.AGAINST)] == pytest.approx(7.0)


# ------------------------------------------------------------------ H.2 bar

def _arm(**kw):
    base = {"trades": 500, "drop3_R": 10.0, "drop5_R": 5.0, "boot_p": 0.99,
            "mean_R": 0.20, "early_R": 5.0, "late_R": 5.0,
            "long_mean_R": 0.1, "short_mean_R": 0.1}
    return base | kw


def test_all_six_criteria_can_pass():
    assert X.criteria_pass(_arm())["all"] is True


def test_criterion_one_needs_both_drops_positive():
    assert X.criteria_pass(_arm(drop5_R=-1.0))[1] is False
    assert X.criteria_pass(_arm(drop3_R=-1.0))[1] is False


def test_criterion_three_uses_the_registered_five_hundredths_bar():
    assert X.criteria_pass(_arm(mean_R=0.05))[3] is True
    assert X.criteria_pass(_arm(mean_R=0.049))[3] is False


def test_criterion_six_needs_both_sides_positive():
    assert X.criteria_pass(_arm(short_mean_R=-0.01))[6] is False


def test_an_empty_bucket_passes_nothing():
    assert X.criteria_pass({"trades": 0})["all"] is False


def test_the_registered_constants_are_what_h_fixed():
    assert X.INDEX == "SPY"
    assert (X.OR_FROM, X.OR_TO) == (570, 574)
    assert X.DRAWS == 2000


def test_a_tie_with_the_null_is_not_a_beat():
    """All sessions up, all trades long: every permutation is the same split.

    The null then sits exactly on the observation, and a gate that merely ties
    with a random relabelling has demonstrated nothing. H.3(a) says the real
    bucket must EXCEED the 95th percentile, not reach it.
    """
    rows = [(f"d{i}", f"S{i}", 1, float(i)) for i in range(8)]
    out = X.shuffled_sign_null(_packable(rows), np.ones(8), draws=50)
    assert out["obs_mean"] == pytest.approx(out["mean_p95"])
    assert out["mean_beats"] is False
    assert out["drop5_beats"] is False


def test_valid_draws_counts_the_draws_that_retained_anything():
    """Every session down, every trade long: the gate keeps nothing, ever.

    A degenerate case rather than an expected one, but it is the only way to
    check that `valid_draws` counts rather than assumes -- which is what makes
    it able to detect a null that resamples instead of permuting.
    """
    rows = [(f"d{i}", f"S{i}", 1, float(i)) for i in range(4)]
    out = X.shuffled_sign_null(_packable(rows), -np.ones(4), draws=25)
    assert np.isnan(out["obs_mean"])
    assert out["valid_draws"] == 0
