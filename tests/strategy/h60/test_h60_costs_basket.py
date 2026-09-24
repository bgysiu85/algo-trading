"""strategy.h60.costs (§2.4) and strategy.h60.basket (§2.5, §4.2)."""
from __future__ import annotations

import numpy as np
import pytest

from common.commissions import order_cost
from strategy.h60 import basket as K
from strategy.h60 import costs as C
from strategy.h60 import exits as X
from tests.strategy.h60 import _synth as S


# --------------------------------------------------------------------------
# costs
# --------------------------------------------------------------------------

def test_the_g2_table_is_the_registered_one():
    assert C.SPREAD_BPS[570] == 7.98 and C.SPREAD_BPS[930] == 2.96
    assert len(C.SPREAD_BPS) == 13 and C.ALL_IN_BPS == 5.46


def test_which_half_hour_a_fill_is_charged():
    g = "primary"
    assert C.fill_spread_bps(0, X.PH_OPEN, g) == 7.98        # 09:30 open
    assert C.fill_spread_bps(6, X.PH_CLOSE, g) == 2.96       # 16:00 close
    assert C.fill_spread_bps(1, X.PH_OPEN, g) == 4.01        # 10:30 open
    assert C.fill_spread_bps(1, X.PH_CLOSE, g) == 3.94       # 11:00-11:30 is the bar's last
    assert C.fill_spread_bps(0, X.PH_INTRA, g) == 7.98       # the wider of 09:30 / 10:00
    assert C.fill_spread_bps(0, X.PH_OPEN, "fallback") == 7.98
    assert C.fill_spread_bps(1, X.PH_OPEN, "fallback") == 4.58   # 10:00


def test_l1_l2_l3_on_one_trade():
    q, ep, xp = 100, 100.0, 101.0
    r = C.trade_costs([q], [ep], [xp], [1], [6], [X.PH_CLOSE], [False], "primary")
    assert r["L1"][0] == pytest.approx(5.46 / 2 / 1e4 * (10_000 + 10_100))
    spread = 10_000 * 4.01 / 2 / 1e4 + 10_100 * 2.96 / 2 / 1e4
    comm = order_cost(q, ep, False, "ibkr_tiered") + order_cost(q, xp, True, "ibkr_tiered")
    assert r["L2"][0] == pytest.approx(spread + comm)
    assert r["L3"][0] == pytest.approx(2 * spread + comm)


def test_a_stop_fill_pays_one_extra_half_spread():
    a = C.trade_costs([100], [100.0], [95.0], [1], [2], [X.PH_INTRA], [False], "primary")
    b = C.trade_costs([100], [100.0], [95.0], [1], [2], [X.PH_INTRA], [True], "primary")
    half_out = 9_500 * max(C.SPREAD_BPS[690], C.SPREAD_BPS[720]) / 2 / 1e4
    assert b["L2"][0] - a["L2"][0] == pytest.approx(half_out)
    assert b["L3"][0] - a["L3"][0] == pytest.approx(2 * half_out)


def test_vectorised_commission_is_order_cost_exactly():
    qs = np.array([1, 3, 10, 29, 30, 99, 100, 101, 333, 1000, 5000, 20000])
    ps = np.array([0.5, 0.99, 1.0, 5.0, 12.34, 50.0, 333.0, 1234.5])
    Q, P = np.meshgrid(qs, ps)
    for sell in (False, True):
        vec = C.tiered_vec(Q.ravel(), P.ravel(), sell)
        ref = [order_cost(int(q), float(p), sell, "ibkr_tiered")
               for q, p in zip(Q.ravel(), P.ravel())]
        np.testing.assert_allclose(vec, ref, rtol=1e-12, atol=1e-12)
    assert C.tiered_vec([0], [10.0], True)[0] == 0.0


def test_financing_line():
    assert C.financing([10_000.0], [1])[0] == pytest.approx(10_000 * 0.5 * 0.0713 / 365)


# --------------------------------------------------------------------------
# basket
# --------------------------------------------------------------------------

def test_identical_names_make_market_relative_zero():
    days = S.sessions(6)
    base = S.random_walk("AAA", days, vol=0.01)
    frames = [base.assign(symbol=s) for s in ("AAA", "BBB", "CCC")]
    p = S.panel(frames)
    b = K.build(p)
    a = p.arrays("AAA")
    em, xm = 2 * a.g[3], 2 * a.g[30] + 1
    assert b.ret(em, xm) == pytest.approx(a.c[30] / a.o[3] - 1)


def test_the_index_steps_open_to_close_and_close_to_next_open():
    days = S.sessions(2)
    c = np.array([101, 102, 103, 104, 105, 106, 107, 110, 111, 112, 113, 114, 115, 116], float)
    o = np.r_[100.0, c[:-1]]
    o[7] = 108.0                                # overnight gap 107 -> 108
    p = S.panel([S.bars_from_closes("AAA", days, c, opens=o)])
    b = K.build(p)
    assert b.ret(0, 1) == pytest.approx(101 / 100 - 1)
    assert b.ret(13, 14) == pytest.approx(108 / 107 - 1)     # close of bar 6 -> open of bar 7
    assert b.ret(0, 27) == pytest.approx(116 / 100 - 1)


def test_a_name_missing_a_bar_contributes_nothing_across_the_gap():
    days = S.sessions(1)
    a = S.bars_from_closes("AAA", days, np.linspace(101, 107, 7), opens=np.linspace(100, 106, 7))
    b_ = S.bars_from_closes("BBB", days, np.full(7, 50.0), opens=np.full(7, 50.0))
    b_.loc[3, ["open", "close"]] = 500.0          # garbage that must not enter
    b_ = b_.drop(index=[3])
    p = S.panel([a, b_])
    k = K.build(p)
    # mark 7 (close of bar 3): only AAA has it
    assert k.ret(6, 7) == pytest.approx(104 / 103 - 1)
    # mark 8 (open of bar 4): BBB's previous mark is 5, not 7 -> not adjacent
    assert k.n_names[np.searchsorted(k.marks, 8)] == 1


def test_split_and_bad_days_are_dropped_from_the_basket():
    days = S.sessions(2)
    c = np.full(14, 100.0)
    a = S.bars_from_closes("AAA", days, c, opens=c)
    s = c.copy()
    s[7:] = 50.0
    b_ = S.bars_from_closes("SPL", days, s, opens=s)
    p = S.panel([a, b_])
    assert K.build(p).ret(13, 14) == pytest.approx(-0.25)       # the split read as -50%
    assert K.build(p, split_days={("SPL", 1)}).ret(13, 14) == 0.0
    assert K.build(p, excluded_days={("SPL", 1)}).ret(13, 27) == 0.0


def test_ineligible_names_are_not_in_the_basket():
    days = S.sessions(2)
    up = S.bars_from_closes("UP", days, np.full(14, 100.0) * np.r_[np.ones(7), 2 * np.ones(7)])
    fl = S.bars_from_closes("FL", days, np.full(14, 100.0))
    spells = S.spells_for(["FL"]) + S.spells_for(["UP"], end=days[0])
    p = S.panel([up, fl], spells=spells)
    assert K.build(p).ret(13, 27) == pytest.approx(0.0)


def test_unknown_marks_raise():
    p = S.panel([S.random_walk("AAA", S.sessions(1))])
    with pytest.raises(KeyError):
        K.build(p).at([10_000])


def test_an_excluded_day_leaks_nothing_into_or_out_of_the_basket():
    """The W14-0003 review's case: one name's session 20 is 30% too high and
    excluded. The basket from session 19's close to session 22's open must
    be flat -- the overnight step OUT of the bad close is dropped too."""
    days = S.sessions(25)
    frames = []
    for i in range(10):
        c = np.full(25 * 7, 100.0 + i)
        if i == 0:
            c[20 * 7:21 * 7] *= 1.3
        frames.append(S.bars_from_closes(f"N{i}", days, c, opens=c))
    p = S.panel(frames)
    a = p.arrays("N0")
    m19 = 2 * a.g[19 * 7 + 6] + 1
    m22 = 2 * a.g[22 * 7]
    assert K.build(p).ret(m19, m22) != 0.0                    # unexcluded: the error is in
    assert K.build(p, excluded_days={("N0", 20)}).ret(m19, m22) == pytest.approx(0.0, abs=1e-12)


def test_a_ticker_reused_on_consecutive_sessions_adds_no_step():
    from strategy.swing.pit_universe import Spell
    days = S.sessions(4)
    c = np.r_[np.full(14, 100.0), np.full(14, 20.0)]           # company B trades at 20
    x = S.bars_from_closes("XYZ", days, c, opens=c)
    f = S.bars_from_closes("FLT", days, np.full(28, 50.0))
    spells = [Spell("sp500", "XYZ_OLD", "A", None, days[1], False, True),
              Spell("sp400", "XYZ", "B", days[2], None, True, False),
              Spell("sp500", "FLT", "F", None, None, True, False)]
    p = S.panel([x, f], spells=spells)
    a = p.arrays("XYZ")
    assert K.build(p).ret(2 * a.g[13] + 1, 2 * a.g[14]) == 0.0   # not -80%
