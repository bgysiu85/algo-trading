"""REGISTERED_tl_v2.md Amendment 1 (W15-0033): TL-v2 is priced at IBKR (fee + 0/1/2 ticks per side, no
separate stop-fill tick), never at TL-v0's flat $0.50 / $1.25 / $2.50."""
from __future__ import annotations

import inspect

import numpy as np
import pytest

import strategy.tl_v0.engine as V0E
from strategy.futbt import costs_ibkr as CI
from strategy.tl_v0.spec import LEVELS, MARKETS
from strategy.tl_v1.signals import MarketCtx
from strategy.tl_v2 import costs as C
from strategy.tl_v2 import engine as E
from tests.strategy.tl_v2.test_engine import _loader


@pytest.fixture(scope="module")
def run():
    mb = _loader("CL")
    r, _ = E.run_market(mb, MARKETS["CL"], MarketCtx(mb, MARKETS["CL"]))
    return r


def test_friction_is_the_ibkr_table_and_nothing_is_retyped():
    for name, m in MARKETS.items():
        f = C.friction(m)
        fee = CI.FEE_PER_SIDE[m.vehicle]
        assert f["low"] == pytest.approx(fee) and f["mid"] == pytest.approx(fee + m.tick_usd)
        assert f["high"] == pytest.approx(fee + 2 * m.tick_usd)
    assert C.friction(MARKETS["CL"]) == {"low": 0.77, "mid": 1.77, "high": 2.77}      # MCL: $0.77 + $1 ticks
    src = inspect.getsource(C)
    assert "FRICTION" not in src and "1.25" not in src and "2.50" not in src


def test_the_engine_uses_its_own_ibkr_run_not_tl_v0s(run):
    assert E._run is not V0E._run


def test_every_trade_row_is_gross_minus_ibkr_level_times_contracts_times_sides_with_no_stop_tick(run):
    t = run.trades
    assert len(t) > 0 and (t["slip"] == 0).all()
    f = C.friction(MARKETS["CL"])
    for lv in LEVELS:
        want = t["gross"] - f[lv] * t["qty"] * t["sides"]
        assert np.allclose(t["net_" + lv], want)
    stops = t[t["stop_fill"]]
    assert len(stops) > 0                                    # the fixture has stop fills to test this on
    assert np.allclose(stops["net_mid"], stops["gross"] - 1.77 * stops["qty"] * stops["sides"])


def test_the_flat_tl_v0_friction_would_have_given_a_different_number(run):
    """Mutation check: the old flat model (mid $1.25 + a tick on stop fills) is NOT what was booked."""
    t = run.trades
    old_mid = t["gross"] - 1.25 * t["qty"] * t["sides"] - np.where(t["stop_fill"], 1.0 * t["qty"], 0.0)
    assert not np.allclose(t["net_mid"], old_mid)


def test_the_daily_series_sums_to_the_trade_list_at_every_level(run):
    t = run.trades
    for key, arr in run.daily.items():
        spec, R, share, sizing, eq = key
        book = t[(t["spec"] == spec) & (t["R"] == R) & (t["share"] == share) & (t["sizing"] == sizing)
                 & (t["equity"] == eq)]
        for i, lv in enumerate(LEVELS):
            assert arr[:, i].sum() == pytest.approx(book["net_" + lv].sum(), abs=1e-6), (key, lv)
