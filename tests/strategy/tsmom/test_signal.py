#!/usr/bin/env python3
"""The volatility estimator against a hand-built sum, the lag, and the signal.

REGISTERED_tsmom section 8: "a volatility estimator that is right in pandas and
wrong by hand, or the reverse. ewm(...).var(bias=True) versus bias=False is a
one-flag difference that produces a plausible number." These tests tell the
two apart.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.tsmom.registry import ANNUALISE, DELTA, WARMUP_RETURNS
from strategy.tsmom.signal import (ensemble_sign, ewma_var_annual, ewma_vol_info,
                                   ex_ante_vol, trailing_sign)
from tests.strategy.tsmom.fixtures import sessions


def _returns(n=400, seed=7):
    rng = np.random.default_rng(seed)
    idx = sessions("2019-01-01", "2023-12-31")[:n]
    r = pd.Series(0.0005 + 0.012 * rng.standard_normal(n), index=idx)
    r.iloc[0] = np.nan                     # the first session has no return
    return r


def _hand_var(r: np.ndarray) -> float:
    """MOP eq. (1) written out: weights (1-delta)delta^i, normalised to sum to
    one over the history available, variance about the EW mean, x 261."""
    x = r[~np.isnan(r)][::-1]              # most recent first
    w = (1 - DELTA) * DELTA ** np.arange(len(x))
    w = w / w.sum()
    m = np.sum(w * x)
    return ANNUALISE * np.sum(w * (x - m) ** 2)


def test_delta_is_sixty_over_sixty_one():
    assert DELTA == pytest.approx(60 / 61)
    assert DELTA / (1 - DELTA) == pytest.approx(60.0), "centre of mass 60 days"


def test_pandas_path_equals_the_hand_built_weighted_sum():
    r = _returns()
    got = ewma_var_annual(r)
    for n in (30, 261, 399):
        assert got.iloc[n] == pytest.approx(_hand_var(r.values[: n + 1]), rel=1e-10)


def test_the_test_can_tell_bias_true_from_bias_false():
    r = _returns()
    wrong = r.ewm(com=60, adjust=True).var(bias=False) * ANNUALISE
    hand = _hand_var(r.values)
    assert wrong.iloc[-1] != pytest.approx(hand, rel=1e-6), (
        "bias=False must be distinguishable from equation (1) at this tolerance, "
        "or the equality test above proves nothing")
    assert ewma_var_annual(r).iloc[-1] == pytest.approx(hand, rel=1e-10)


def test_variance_is_about_the_ew_mean_not_zero():
    r = _returns() + 0.01                  # a large mean
    about_zero = ANNUALISE * r.pow(2).ewm(com=60, adjust=True).mean()
    assert ewma_var_annual(r).iloc[-1] != pytest.approx(about_zero.iloc[-1], rel=1e-3)
    assert ewma_var_annual(r).iloc[-1] == pytest.approx(_hand_var(r.values), rel=1e-10)


def test_annualised_by_261():
    r = _returns()
    raw = r.ewm(com=60, adjust=True).var(bias=True)
    assert ewma_var_annual(r).iloc[-1] == pytest.approx(261 * raw.iloc[-1])


def test_ex_ante_vol_is_lagged_one_day():
    r = _returns()
    v = ex_ante_vol(r)
    info = ewma_vol_info(r)
    t = 300
    assert v.iloc[t] == pytest.approx(info.iloc[t - 1])
    shocked = r.copy()
    shocked.iloc[t] = 0.5
    assert ex_ante_vol(shocked).iloc[t] == pytest.approx(v.iloc[t]), \
        "the return of day t must not be in the estimate applied to day t"
    assert ex_ante_vol(shocked).iloc[t + 1] > 2 * v.iloc[t + 1]


def test_warm_up_needs_261_returns_before_the_day():
    r = _returns()
    v = ex_ante_vol(r)
    n_before = r.notna().cumsum().shift(1)
    assert v[n_before < WARMUP_RETURNS].isna().all()
    assert v[n_before >= WARMUP_RETURNS].notna().all()
    first = v.first_valid_index()
    assert int(n_before[first]) == WARMUP_RETURNS


# --- the signal ---------------------------------------------------------------

def _monthly_steps(values_by_month: dict[str, float]) -> pd.Series:
    """A series constant within each month at the given level."""
    idx = sessions("2020-01-01", "2020-12-31")
    s = pd.Series(np.nan, index=idx)
    for m, v in values_by_month.items():
        s[idx.strftime("%Y-%m") == m] = v
    return s


def test_hand_computed_sign():
    cont = _monthly_steps({"2020-01": 10, "2020-02": 12, "2020-03": 11,
                           "2020-04": 9, "2020-05": 13, "2020-06": 8})
    i = pd.DatetimeIndex([pd.Timestamp("2020-06-30")])
    # k=3: from the last session on/before 2020-03-30 (level 11) to 8 -> down
    assert trailing_sign(cont, i, 3).iloc[0] == -1
    # k=4: from 2020-02-28 (12) to 8 -> down; k=5: from 2020-01-30 (10) -> down
    assert trailing_sign(cont, i, 4).iloc[0] == -1
    i2 = pd.DatetimeIndex([pd.Timestamp("2020-05-29")])
    assert trailing_sign(cont, i2, 1).iloc[0] == 1          # 9 -> 13
    assert trailing_sign(cont, i2, 3).iloc[0] == 1          # 12 -> 13
    assert trailing_sign(cont, i2, 2).iloc[0] == 1          # 11 -> 13


def test_no_skip_month():
    """Down for eleven months, then a large up month: the 12-month signal is
    +1 because the most recent month IS in the window. With the
    cross-sectional skip convention (footnote 10) it would be -1."""
    levels = {f"2020-{m:02d}": 100 - m for m in range(1, 12)}   # 99 ... 89
    levels["2020-12"] = 120
    cont = _monthly_steps(levels)
    cont = pd.concat([pd.Series(100.0, index=sessions("2019-12-01", "2019-12-31")), cont])
    i = pd.DatetimeIndex([pd.Timestamp("2020-12-31")])
    assert trailing_sign(cont, i, 12).iloc[0] == 1
    # what a skip would have measured: the window ending a month earlier
    skipped = trailing_sign(cont, pd.DatetimeIndex([pd.Timestamp("2020-11-30")]), 11)
    assert skipped.iloc[0] == -1, "the skip variant really does disagree here"


def test_sign_is_nan_before_the_window_exists():
    cont = _monthly_steps({"2020-03": 1, "2020-04": 2})
    i = pd.DatetimeIndex([pd.Timestamp("2020-04-30")])
    assert np.isnan(trailing_sign(cont, i, 3).iloc[0])


def test_ensemble_is_the_mean_of_the_signs_and_needs_every_k():
    levels = {f"2020-{m:02d}": v for m, v in
              zip(range(1, 13), [50, 40, 30, 20, 25, 30, 35, 40, 30, 20, 10, 5])}
    cont = _monthly_steps(levels)
    cont = pd.concat([pd.Series(100.0, index=sessions("2019-01-01", "2019-12-31")), cont])
    i = pd.DatetimeIndex([pd.Timestamp("2020-08-31")])       # level 40
    # k=3: May(25)->40 up; k=6: Feb(40)->40 flat 0; k=9: Nov19(100)->40 down;
    # k=12: Aug19(100)->40 down
    assert trailing_sign(cont, i, 6).iloc[0] == 0
    e = ensemble_sign(cont, i, (3, 6, 9, 12)).iloc[0]
    assert e == pytest.approx((1 + 0 - 1 - 1) / 4)
    short = cont[cont.index >= "2020-01-01"]
    assert np.isnan(ensemble_sign(short, i, (3, 6, 9, 12)).iloc[0]), \
        "a root enters only when every lookback exists"


def test_the_signal_does_not_look_ahead():
    """Changing the future does not change a past signal -- including through
    the back-adjustment, whose gaps come from later rolls."""
    rng = np.random.default_rng(3)
    idx = sessions("2019-01-01", "2021-12-31")
    cont = pd.Series(np.cumsum(rng.standard_normal(len(idx))), index=idx)
    i = pd.DatetimeIndex(idx[300:400])
    base = ensemble_sign(cont, i, (3, 6, 9, 12))
    later = cont.copy()
    later[later.index > i[-1]] += 1000.0                    # a later "gap"
    later -= 57.0                                           # back-adjustment shifts levels
    assert base.equals(ensemble_sign(later, i, (3, 6, 9, 12)))
