"""G8: the per-symbol table reproduces the CL / MCL numbers of REGISTERED_exit_cmp.md sec 8 and sec 13 exactly."""
import pytest

from exitmgr import symbols as SY
from strategy.chartmark import spec as V1


def test_mcl_and_cl_round_trips_are_the_registered_ones():
    assert [round(SY.get("MCL").round_trip(l), 2) for l in SY.LEVELS] == [1.54, 3.54, 5.54]
    assert [round(SY.get("CL").round_trip(l), 2) for l in SY.LEVELS] == [4.74, 24.74, 44.74]


def test_table_equals_the_v1_spec_it_replaces():
    for sym in ("MCL", "CL"):
        s = SY.get(sym)
        assert s.fee == V1.FEE[sym] and s.tick == pytest.approx(V1.TICK) and s.point_usd == V1.MULT[sym]
        assert s.tick_usd == V1.TICK_USD[sym]
        for lv in SY.LEVELS:
            assert s.per_side(lv) == pytest.approx(V1.per_side(sym, lv))


def test_sec13_rows():
    rows = {"MES": (5, 0.25, 1.25, 0.62), "ES": (50, 0.25, 12.5, 2.26), "MNQ": (2, 0.25, 0.5, 0.62), "NQ": (20, 0.25, 5.0, 2.26)}
    for root, (pt, tick, tusd, fee) in rows.items():
        s = SY.get(root)
        assert (s.point_usd, s.tick_usd, s.fee) == (pt, tusd, fee)
        assert s.tick == pytest.approx(tick)


def test_other_rows_agree_with_the_repo_tables():
    from strategy.futbt.costs_ibkr import FEE_PER_SIDE
    from strategy.tl_v0.spec import MARKETS
    for m in MARKETS.values():
        if m.vehicle in SY.SYMBOLS and m.vehicle in FEE_PER_SIDE:
            s = SY.get(m.vehicle)
            assert s.point_usd == m.mult and s.tick_usd == pytest.approx(m.tick_usd) and s.fee == FEE_PER_SIDE[m.vehicle]


def test_distances():
    assert SY.arm_distance("CL") == SY.arm_distance("MCL") == 0.20
    assert SY.emergency_distance("MCL") == 0.60
    # ratchet arm in dollars on 10 CL: the "~$2,000" (sec 1)
    assert SY.arm_distance("CL") * SY.get("CL").point_usd * 10 == pytest.approx(2000.0)
    # another symbol: the CL value scaled by volatility; refuses to guess without the ATRs
    assert SY.arm_distance("MES", atr_at_fill=4.0, median_cl_atr=0.40) == pytest.approx(2.0)
    with pytest.raises(ValueError):
        SY.arm_distance("ES")


def test_unknown_symbol_is_an_error_not_a_guess():
    with pytest.raises(KeyError):
        SY.get("ZB")
