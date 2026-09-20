#!/usr/bin/env python3
"""Tranches, sizing, integer contracts, P/L on the held contract, arms, holdout.

Every expected number below is computed by hand from the fixture, not read back
from the engine and pasted in.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import common.tsmom_holdout as H
from strategy.tsmom import engine as E
from strategy.tsmom.book import _sides, round_half_away, run_book, tranche_calendar
from strategy.tsmom.registry import (CORE, FRICTION, RATES_ARMS, TARGET_VOL,
                                     WARMUP_RETURNS, Root, book_roots)
from strategy.tsmom.signal import ensemble_sign, ewma_vol_info
from tests.strategy.tsmom.fixtures import sessions, trending_root

D = pd.Timestamp
ONE = Root("XX", 100.0, "MXX", 0.1)            # vehicle point value $10


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "tsmom_holdout_spent.json")


def _series(inp, root=ONE):
    return E.build_series(inp, root)[1]


# --- rounding -----------------------------------------------------------------

@pytest.mark.parametrize("x,want", [(0.4, 0), (0.49, 0), (0.5, 1), (-0.5, -1),
                                    (-0.4, 0), (1.5, 2), (2.5, 3), (0.06, 0),
                                    (1.49, 1), (-2.5, -3), (0.0, 0)])
def test_round_half_away_from_zero(x, want):
    assert round_half_away(x) == want


def test_a_0_4_contract_target_is_not_traded():
    """Spec section 3: at $22k most markets round to 0 or 1 -- the capacity
    finding. A 0.4 target must be 0 contracts, and cost nothing."""
    assert round_half_away(np.array([0.4, -0.4])).tolist() == [0.0, 0.0]


# --- the tranche calendar -----------------------------------------------------

def test_tranche_days_in_a_month_with_a_holiday():
    m = sessions("2020-09-01", "2020-09-30", holidays=["2020-09-07"])   # Labor Day
    cal = tranche_calendar(m)
    days = {t.day: s for t, s in cal.items() if s >= 0}
    # sessions: 1,2,3,4,8,9,10,11,14,15,16,17,18,21,22,23,24 -> 1st/5th/9th/13th/17th
    assert days == {1: 0, 8: 1, 14: 2, 18: 3, 24: 4}


def test_tranche_calendar_restarts_each_month():
    cal = tranche_calendar(sessions("2020-01-01", "2020-03-31"))
    firsts = [t for t, s in cal.items() if s == 0]
    assert [t.date().isoformat() for t in firsts] == ["2020-01-01", "2020-02-03", "2020-03-02"]


# --- sides --------------------------------------------------------------------

def test_sides_accounting():
    old = np.array([2.0, 2.0, 2.0, 1.0, 0.0, 3.0])
    new = np.array([2.0, 3.0, -1.0, 1.0, 1.0, 1.0])
    rolled = np.array([True, True, True, False, False, False])
    roll, reb = _sides(old, new, rolled)
    assert roll.tolist() == [4.0, 4.0, 0.0, 0.0, 0.0, 0.0]
    assert reb.tolist() == [0.0, 1.0, 3.0, 0.0, 1.0, 2.0]


# --- one-root books built by hand ---------------------------------------------

def _one_root(**kw):
    inp = trending_root("XX", **kw)
    return inp, _series(inp)


def test_sizing_matches_the_formula_by_hand():
    inp, s = _one_root()
    res = run_book({"XX": s}, {"XX": ONE}, equity=1_000_000.0)
    cal = tranche_calendar(s.index)
    live_reb = [t for t in s.index if cal[t] >= 0 and res.live.at[t, "XX"]]
    d = live_reb[3]
    i = s.index[s.index.get_loc(d) - 1]                     # the information date
    vol = ewma_vol_info(s["ret"])[i]
    sign = ensemble_sign(s["cont"], pd.DatetimeIndex([i]), (3, 6, 9, 12)).iloc[0]
    want = sign * TARGET_VOL * (1_000_000.0 / 5) / 1 / (10.0 * s.at[i, "raw"] * vol)
    # the sleeve of day d holds `want`; the others hold their own last targets
    prev = res.pos_frac.shift(1).at[d, "XX"]
    moved = res.pos_frac.at[d, "XX"] - prev
    sleeve_before = [t for t in live_reb if t < d and cal[t] == cal[d]]
    old = 0.0
    if sleeve_before:
        t0 = sleeve_before[-1]
        i0 = s.index[s.index.get_loc(t0) - 1]
        v0 = ewma_vol_info(s["ret"])[i0]
        g0 = ensemble_sign(s["cont"], pd.DatetimeIndex([i0]), (3, 6, 9, 12)).iloc[0]
        old = g0 * TARGET_VOL * 200_000.0 / (10.0 * s.at[i0, "raw"] * v0)
    assert moved == pytest.approx(want - old, rel=1e-9)


def test_equal_weight_divides_by_the_number_of_live_markets():
    a, b = trending_root("AA", seed=1), trending_root("BB", seed=2)
    ra, rb = Root("AA", 100.0, "MAA", 0.1), Root("BB", 100.0, "MBB", 0.1)
    sa, sb = _series(a, ra), _series(b, rb)
    alone = run_book({"AA": sa}, {"AA": ra}, equity=1e6)
    both = run_book({"AA": sa, "BB": sb}, {"AA": ra, "BB": rb}, equity=1e6)
    t = alone.pos_frac.index[-1]
    assert both.pos_frac.at[t, "AA"] == pytest.approx(alone.pos_frac.at[t, "AA"] / 2)


def test_integer_book_at_22k_rounds_small_targets_to_zero():
    inp, s = _one_root(level=4000.0)                        # $40k per full contract
    big = Root("XX", 1000.0, "MXX", 0.1)                    # vehicle $100/pt -> $400k notional
    res = run_book({"XX": s}, {"XX": big}, equity=22_000.0)
    live = res.live["XX"]
    assert live.any()
    frac = res.pos_frac.loc[live, "XX"].abs()
    assert (frac < 0.5).all() and (frac > 0).any()
    assert (res.pos_int["XX"] == 0).all()
    assert res.costs("int", "high").to_numpy().sum() == 0.0
    assert res.pnl_int.to_numpy().sum() == 0.0


def test_roll_day_pnl_is_held_contract_pnl_plus_roll_cost():
    inp, s = _one_root(level=100.0)
    res = run_book({"XX": s}, {"XX": ONE}, equity=5_000_000.0)
    pos = res.pos_int["XX"]
    rolls = [t for t in s.index[s["rolled"]] if pos.shift(1)[t] != 0
             and pos[t] == pos.shift(1)[t]]
    assert rolls, "the fixture must roll while holding an unchanged position"
    t = rolls[0]
    prev = s.index[s.index.get_loc(t) - 1]
    old = s.at[prev, "held"]
    n = pos[prev]
    px = inp.prices
    held_pl = n * (px.at[t, old] - px.at[prev, old]) * ONE.vehicle_point_value
    for level, fee in FRICTION.items():
        assert res.net("int", level).at[t, "XX"] == pytest.approx(held_pl - 2 * abs(n) * fee)
    # and NOT the change in the spliced price, which jumps by the gap
    splice_pl = n * (s.at[t, "raw"] - s.at[prev, "raw"]) * ONE.vehicle_point_value
    assert res.pnl_int.at[t, "XX"] != pytest.approx(splice_pl)
    assert splice_pl - res.pnl_int.at[t, "XX"] == pytest.approx(
        n * s.at[t, "gap"] * ONE.vehicle_point_value)
    assert res.sides[("int", "roll")].at[t, "XX"] == 2 * abs(n)


def test_pnl_never_reads_the_continuous_series():
    """Shift the adjusted series' level: signals unchanged, P/L unchanged."""
    inp, s = _one_root()
    s2 = s.copy()
    s2["cont"] = s2["cont"] + 1234.5
    a = run_book({"XX": s}, {"XX": ONE}, equity=1e6)
    b = run_book({"XX": s2}, {"XX": ONE}, equity=1e6)
    assert np.allclose(a.pnl_frac.to_numpy(), b.pnl_frac.to_numpy())


def test_a_decision_does_not_read_the_bar_it_trades_on():
    inp, s = _one_root()
    res = run_book({"XX": s}, {"XX": ONE}, equity=1e6)
    cal = tranche_calendar(s.index)
    d = [t for t in s.index if cal[t] >= 0 and res.live.at[t, "XX"]][5]
    k = s.index.get_loc(d)

    def bumped(at):
        px = inp.prices.copy()
        px.loc[px.index >= s.index[at], :] *= 1.3
        return run_book({"XX": _series(E.RootInputs(inp.contracts, px))},
                        {"XX": ONE}, equity=1e6)
    assert bumped(k).pos_frac.at[d, "XX"] == pytest.approx(res.pos_frac.at[d, "XX"]), \
        "a shock AT d moved the position decided at d: look-ahead"
    assert bumped(k - 1).pos_frac.at[d, "XX"] != pytest.approx(res.pos_frac.at[d, "XX"])


def test_warm_up_absent_is_not_flat():
    inp, s = _one_root()
    res = run_book({"XX": s}, {"XX": ONE}, equity=1e6)
    first_live = res.live["XX"].idxmax()
    n_before = s["ret"].notna().cumsum().shift(1)
    assert n_before[first_live] >= WARMUP_RETURNS
    assert not res.live.loc[:first_live, "XX"].iloc[:-1].any()
    assert (res.pos_frac.loc[res.pos_frac.index < first_live, "XX"] == 0).all()


def test_a_late_root_enters_late():
    early = trending_root("AA", start="2017-01-02", seed=1)
    late = trending_root("BB", start="2019-06-03", seed=2)
    ra, rb = Root("AA", 100.0, "MAA", 0.1), Root("BB", 100.0, "MBB", 0.1)
    res = run_book({"AA": _series(early, ra), "BB": _series(late, rb)},
                   {"AA": ra, "BB": rb}, equity=1e6)
    ea, eb = res.live["AA"].idxmax(), res.live["BB"].idxmax()
    assert ea < D("2018-03-01") and D("2020-06-01") <= eb < D("2020-09-01")


def test_long_benchmark_is_long_everywhere_it_is_live():
    inp, s = _one_root(drift=-0.001)
    res = run_book({"XX": s}, {"XX": ONE}, equity=1e6, signal_mode="long")
    used = res.signal["XX"].dropna()
    assert len(used) and (used == 1.0).all()
    ts = run_book({"XX": s}, {"XX": ONE}, equity=1e6)
    assert (ts.signal["XX"].dropna() < 0).any(), "falling market: TSMOM goes short"


# --- the book across real roots, arms and the holdout --------------------------

def _inputs(end="2023-06-30"):
    roots = list(CORE) + ["ZN", "TN"]
    out = {}
    for i, n in enumerate(roots):
        start = "2017-07-10" if n == "RTY" else "2016-01-11" if n == "TN" else "2015-01-02"
        root = CORE.get(n) or {"ZN": RATES_ARMS["a_ZN"], "TN": RATES_ARMS["b_MTN"]}[n]
        months = root.cycle if root.rule == "cycle" else (3, 6, 9, 12)
        out[n] = trending_root(n, start=start, end=end, seed=i, months=months)
    return out


def test_all_three_rates_arms_are_built_and_not_ranked():
    books = E.training_books(_inputs(end="2019-12-31"), equity=22_000.0)
    assert list(books) == list(RATES_ARMS) == ["a_ZN", "b_MTN", "c_none"]
    assert "ZN" in books["a_ZN"].roots and "TN" not in books["a_ZN"].roots
    assert "TN" in books["b_MTN"].roots and "ZN" not in books["b_MTN"].roots
    assert not {"ZN", "TN"} & set(books["c_none"].roots)
    assert len(books["c_none"].roots) == 11
    assert book_roots("b_MTN")["TN"].vehicle == "MTN"
    assert book_roots("b_MTN")["TN"].vehicle_point_value == pytest.approx(100.0)
    assert not any(hasattr(b, "rank") for b in books.values())


def test_the_runner_takes_its_dates_through_split_months(monkeypatch):
    calls = []
    real = H.split_months

    def spy(months, **kw):
        calls.append(len(list(months)))
        return real(months, **kw)
    monkeypatch.setattr(H, "split_months", spy)
    res = E.training_book(_inputs(), "b_MTN", equity=22_000.0)
    assert len(calls) == 12, "every root in the book passes through split_months"
    assert res.pnl_frac.index.max() < D(H.LOCK_FROM)
    assert res.pos_frac.index.max() < D(H.LOCK_FROM)


def test_the_runner_honours_what_split_months_returns(monkeypatch):
    """If the runner called split_months and then ignored it, the spy test
    would still pass. Make split_months keep less and see the book shrink."""
    def only_2019(months, **kw):
        keep = [m for m in months if m < "2020-01-01"]
        return keep, len(months) - len(keep), "test"
    monkeypatch.setattr(H, "split_months", only_2019)
    res = E.training_book(_inputs(), "c_none", equity=22_000.0)
    assert res.pnl_frac.index.max() < D("2020-01-01")


def test_coverage_reports_the_training_side_and_entry():
    cov = E.coverage(_inputs())
    assert cov.loc["RTY", "first"].isoformat() == "2017-07-10"
    assert cov.loc["TN", "enters"] < cov.loc["RTY", "enters"]
    assert all(str(v) < H.LOCK_FROM for v in cov["last"])
    assert (cov["locked_sessions_set_aside"] > 0).all()


def test_pnl_is_yesterdays_position_times_todays_held_move_every_day():
    """By hand over the whole book, including every day the position changes:
    P/L(t) = pos(t-1) * dP(t) * vehicle point value."""
    inp, s = _one_root()
    res = run_book({"XX": s}, {"XX": ONE}, equity=3_000_000.0)
    dP = s["dP"].fillna(0.0)
    for pos, pnl in ((res.pos_frac, res.pnl_frac), (res.pos_int, res.pnl_int)):
        want = pos["XX"].shift(1).fillna(0.0) * dP * ONE.vehicle_point_value
        assert np.allclose(pnl["XX"].to_numpy(), want.to_numpy())
    changed = res.pos_int["XX"].diff().fillna(0) != 0
    assert changed.sum() > 5, "the fixture must change position on some days"


def test_the_261_return_warm_up_is_what_admits_a_root():
    """A root that trades three days a week: 261 returns take ~20 months, so
    the 12-month lookback is long available and the WARM-UP is what binds.
    The root is live on the first rebalance day with 261 returns BEFORE it,
    and not a session earlier."""
    full = trending_root("XX", start="2016-01-04", end="2020-12-31")
    keep = full.prices.index[full.prices.index.dayofweek.isin([0, 2, 4])]
    thin = E.RootInputs(full.contracts, full.prices.loc[keep])
    s = _series(thin)
    res = run_book({"XX": s}, {"XX": ONE}, equity=1e6, tranche_days=tuple(range(1, 24)))
    n_before = s["ret"].notna().cumsum().shift(1).fillna(0)
    first_live = res.live["XX"].idxmax()
    assert n_before[first_live] == WARMUP_RETURNS
    assert not res.live["XX"][n_before < WARMUP_RETURNS].any()
    assert first_live > s.index[0] + pd.DateOffset(months=18)
