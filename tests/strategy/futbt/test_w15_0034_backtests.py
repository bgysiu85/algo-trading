"""W15-0034: IBKR cost model, grids, C2/C3 wiring, report + verdict, and the runner refusals.
Synthetic bars only; no archive is read."""
from __future__ import annotations

import inspect
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from strategy.breit_cap import backtest as BB
from strategy.breit_cap import sim as BSIM
from strategy.breit_cap import signals as BSG
from strategy.crudele_3s import backtest as CB
from strategy.crudele_3s import sim as CSIM
from strategy.crudele_3s import spec as CS
from strategy.crudele_3s import states as CST
from strategy.futbt import core as K
from strategy.futbt import costs_ibkr as CI
from strategy.futbt import grid as GR
from strategy.futbt import loading as LD
from strategy.futbt import report_common as RC
from strategy.tl_v0 import report as Rp
from tests.strategy.futbt.synth import frame_from_close, squeeze_breakout_path


def crudele_frames():
    out = {}
    for m, seed in (("ES", 3), ("CL", 5)):
        path = np.r_[squeeze_breakout_path(seed=seed), squeeze_breakout_path(seed=seed + 1, up=False),
                     squeeze_breakout_path(seed=seed + 2)] + 50
        out[m] = CI.with_ibkr(replace(frame_from_close(path, spread=0.3, mult=5, tick_usd=1.25), market=m))
    return out


def breit_frames():
    out = {}
    for m, seed in (("ES", 1), ("CL", 2)):
        rng = np.random.default_rng(seed)
        r = rng.normal(0, 1, 1500)
        for i in range(60, 1500, 90):
            r[i:i + 5] = -3.5
            r[i + 5] = 2
        fr = frame_from_close(100 + np.cumsum(r) + 300, spread=0.6, mult=5, tick_usd=1.25,
                              start="2010-06-07", vol=rng.uniform(800, 3000, 1500))
        out[m] = CI.with_ibkr(replace(fr, market=m))
    return out


# --- costs ------------------------------------------------------------------------------------

def test_ibkr_levels_are_fee_plus_zero_one_two_ticks():
    v = CI.venue_for("MCL", 1.0)
    assert v.friction == {"low": 0.77, "mid": 1.77, "high": 2.77} and v.stop_slip_ticks == 0.0
    assert [round(2 * v.friction[k], 2) for k in ("low", "mid", "high")] == [1.54, 3.54, 5.54]   # registered round trips
    assert len(CI.table()) == 12 and CI.FEE_PER_SIDE["NG"] == 2.47


def test_booking_uses_the_ibkr_venue_and_no_separate_stop_tick():
    fr = crudele_frames()["ES"]
    t = K.Trade2(1, 5, 9, 100.0, 101.0, 99.0, 2.0, "stop", True)
    b = K.book_trade(t, fr)
    fee = CI.FEE_PER_SIDE["MES"]
    assert b["slip"] == 0.0
    assert b["net_low"] == pytest.approx(b["gross"] - fee * 2.0 * 2)
    assert b["net_mid"] == pytest.approx(b["gross"] - (fee + 1.25) * 2.0 * 2)
    assert b["net_high"] == pytest.approx(b["gross"] - (fee + 2.5) * 2.0 * 2)


def test_loader_applies_ibkr_only_when_asked():
    fr = frame_from_close(np.linspace(100, 110, 50), tick_usd=1.25)
    fr = replace(fr, market="ES")
    f0, _ = LD.load_daily(None, ["ES"], loader=lambda n: (fr, ""), log=lambda *a: None)
    f1, _ = LD.load_daily(None, ["ES"], loader=lambda n: (fr, ""), log=lambda *a: None, ibkr=True)
    assert f0["ES"].venue == K.DAILY_VENUE
    assert f1["ES"].venue.friction["mid"] == pytest.approx(0.62 + 1.25)


# --- grids ------------------------------------------------------------------------------------

def test_crudele_grid_has_27_cells_and_the_centre_reproduces_the_system():
    frames = crudele_frames()
    cells = GR.crudele_cells()
    assert len(cells) == 27
    g = GR.run_grid(frames, CST, CSIM, cells)
    net = sum(K.net_mid(CSIM.simulate(fr, CST.compute(fr, CS.PRIMARY), equity=K.EQUITY, integer=False)[0], fr)
              for fr in frames.values())
    m = np.isclose(g["bwr"], CS.SQ_THR) & (g["exp_bars"] == CS.EXP_BARS) & (g["exit_ma"] == CS.SMA_EXIT)
    assert m.sum() == 1 and g[m]["net_mid"].iloc[0] == pytest.approx(net)


def test_breit_grid_has_27_cells_and_the_centre_reproduces_the_system():
    from strategy.breit_cap import spec as BS
    frames = breit_frames()
    cells = GR.breit_cells()
    assert len(cells) == 27
    g = GR.run_grid(frames, BSG, BSIM, cells)
    net = sum(K.net_mid(BSIM.simulate(fr, BSG.compute(fr, BS.PRIMARY), equity=K.EQUITY, integer=False)[0], fr)
              for fr in frames.values())
    m = np.isclose(g["q2"], BS.Q2_ATR) & (g["k_min"] == BS.K_MIN) & np.isclose(g["q3_sd"], BS.Q3_SD)
    assert m.sum() == 1 and g[m]["net_mid"].iloc[0] == pytest.approx(net)


# --- pipeline + report ---------------------------------------------------------------------------

def test_crudele_pipeline_renders_and_c2_is_reproducible():
    frames = crudele_frames()
    r1 = CB.run_pipeline(frames, draws=3, log=lambda *a: None)
    r2 = CB.run_pipeline(frames, draws=3, log=lambda *a: None)
    assert np.array_equal(r1["c2"]["totals"], r2["c2"]["totals"])
    text, summ = CB.render(r1, scoped=True)
    for key in ("SECTION 4 VERDICT", "27-CELL", "BY ARM", "SAMPLE TRADES", "CONTROLS", "IBKR"):
        assert key in text
    assert "must be ~0" in text and len(summ)
    # the verdict book is the fractional system book, and its trades carry an arm tag
    assert set(r1["books"][("system", "frac")].trades["arm"]) <= set(CS.ARMS)


def test_breit_pipeline_renders_primary_and_single_market_secondary():
    frames = breit_frames()
    prim = BB.run_study(frames, "daily", draws=3, sessions=False, log=lambda *a: None)
    cl = BB.run_study({"CL4H": frames["CL"]}, "CL4H", draws=3, sessions=True, log=lambda *a: None)
    text, summ, verdicts = BB.render(prim, cl, scoped=True)
    assert "PART A" in text and "PART B" in text and set(verdicts) == {"primary", "cl4h"}
    assert "by year only" in text or "read by year" in text
    text2, _, v2 = BB.render(prim, None, scoped=True)
    assert "NOT EVALUATED" in text2 and "cl4h" not in v2


def test_sessions_aggregation_keeps_totals():
    frames = breit_frames()
    from strategy.futbt import engine as EN
    o = EN.run_market(frames["CL"], BSG, BSIM, {"system": BB.S.PRIMARY})
    s = RC.to_sessions(o)
    for k, arr in o.daily.items():
        assert s.daily[k].sum(axis=0) == pytest.approx(arr.sum(axis=0))
    assert len(s.dates) <= len(o.dates)


def test_criteria_not_read_under_150_trades_and_one_market_reads_by_year():
    prim = BB.run_study(breit_frames(), "daily", draws=2, sessions=False, log=lambda *a: None)
    b, c1 = prim["books"][("system", "frac")], prim["books"][("C1", "frac")]
    c6 = Rp.Criterion(6, "x", "y", True)
    crit = RC.criteria(b, c1, c6, prim["grid"], prim["markets"])
    assert len(crit) == 10 and [c.no for c in crit] == list(range(1, 11))
    lines = []
    v = RC.verdict_lines(lines.append, crit, 10, "holdout")
    assert v.startswith("NOT READ")
    crit1 = RC.criteria(b, c1, c6, prim["grid"], prim["markets"], single=True)
    assert "YEAR" in crit1[2].text and "by year only" in crit1[3].text and "one market" in crit1[6].text


# --- refusals ------------------------------------------------------------------------------------

@pytest.mark.parametrize("mod", [CB, BB])
@pytest.mark.parametrize("flag", ["--holdout", "--limit=5", "--seen", "--spend"])
def test_runners_refuse_holdout_and_narrowing_flags(mod, flag):
    with pytest.raises(SystemExit):
        mod.main([flag])


@pytest.mark.parametrize("mod", [CB, BB])
def test_backtest_runners_never_spend_or_read_the_holdout(mod):
    src = inspect.getsource(mod)
    assert "spend=True" not in src and "split_dates(" not in src
    assert "load_daily(arch, names, ibkr=True)" in src            # the holdout-cut loader, IBKR costs
