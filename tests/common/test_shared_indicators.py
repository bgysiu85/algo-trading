#!/usr/bin/env python3
"""Pinned reference values for the shared indicators.

These moved into common/indicators.py from strategy/mcl and strategy/mc5,
where each had its own copy. At the merge every output was verified
bit-identical to the pre-merge implementations; the numbers below were
captured from that verified state, so they lock it in.

The point is narrow and worth being explicit about: four strategies now
share these functions, so a change here moves MCL, MC5, E15 and VW9 at
once. A silent drift in RSI would revalue every backtest in the repo. These
assertions are the tripwire.

Periods are passed explicitly rather than defaulted, because that is the
substantive change the merge made -- the old copies closed over their own
module's constants.
"""
import numpy as np
import pandas as pd

from common import indicators as I

TOL = 1e-12


def _frame():
    rng = np.random.default_rng(7)
    n = 120
    px = 10.0 * np.cumprod(1 + rng.uniform(-0.008, 0.010, n))
    idx = pd.date_range("2026-09-02 04:00", periods=n, freq="1min", tz="UTC")
    c = pd.Series(px, index=idx)
    v = pd.Series(rng.integers(2000, 8000, n).astype(float), index=idx)
    return c, c * 1.003, c * 0.997, v


def test_macd_pinned():
    c, _, _, _ = _frame()
    line, sig = I.macd(c)
    assert abs(float(line.iloc[-1]) - 0.1027357168659222) < TOL
    assert abs(float(sig.iloc[-1]) - 0.09121452469417347) < TOL


def test_rsi_pinned():
    c, _, _, _ = _frame()
    assert abs(float(I.rsi(c).iloc[-1]) - 65.9337514153417) < TOL


def test_mfi_pinned():
    c, h, l, v = _frame()
    assert abs(float(I.mfi(h, l, c, v).iloc[-1]) - 60.059087927049) < TOL


def test_gradients_pinned():
    c, _, _, _ = _frame()
    assert abs(float(I.ols_slope(c).iloc[-1]) - 0.034762377467546735) < TOL
    assert abs(float(I.roc_pct(c).iloc[-1]) - 0.6219201982399069) < TOL


def test_atr_pinned():
    c, h, l, _ = _frame()
    assert abs(float(I.atr(h, l, c).iloc[-1]) - 0.09300868446795775) < TOL


def test_periods_are_parameters_not_globals():
    """The merge's actual behavioural change: periods are arguments now.

    If these functions still closed over module constants, passing a
    different period would silently do nothing.
    """
    c, _, _, _ = _frame()
    # rsi() returns OBJECT dtype -- down.replace(0.0, pd.NA) makes the whole
    # arithmetic chain object-typed. Inherited unchanged from the pre-merge
    # implementation, so it is preserved rather than fixed here; cast before
    # any numpy comparison. Worth tidying separately, since it also costs
    # speed on every backtest bar.
    f = lambda s: s.dropna().astype(float)
    assert not np.allclose(f(I.macd(c, 5, 13, 4)[0]), f(I.macd(c, 12, 26, 9)[0]))
    assert not np.allclose(f(I.rsi(c, 7)), f(I.rsi(c, 14)))
    a, b = f(I.ols_slope(c, 5)), f(I.ols_slope(c, 3))
    n = min(len(a), len(b))          # different n leaves different lead-in NaNs
    assert not np.allclose(a[-n:], b[-n:])


def test_roc_floor_is_a_parameter():
    """MC5 passes its own ROC_MIN_BASE rather than the shared default."""
    s = pd.Series(np.linspace(0.5, 3.0, 40))
    assert not np.allclose(I.roc_pct(s, 3, 0.1).dropna().astype(float),
                           I.roc_pct(s, 3, 5.0).dropna().astype(float))
