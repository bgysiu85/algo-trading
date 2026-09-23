#!/usr/bin/env python3
"""The section 3 report and the section 4 verdict (strategy/tsmom/report.py).

Expected numbers are computed by hand from small inputs, not read back from
the module and pasted in.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import common.tsmom_holdout as H
from strategy.tsmom import report as RP
from strategy.tsmom.book import run_book
from strategy.tsmom.registry import CORE, FRICTION, RATES_ARMS, Root
from tests.strategy.tsmom.fixtures import trending_root
from tests.strategy.tsmom.test_book import _inputs, _series

D = pd.Timestamp
ONE = Root("XX", 100.0, "MXX", 0.1)


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "tsmom_holdout_spent.json")


# --- small pieces, by hand -------------------------------------------------------

def test_drop_top_removes_the_largest_contributors_and_says_na_past_the_count():
    s = pd.Series({"A": 5.0, "B": -1.0, "C": 3.0})
    assert RP.drop_top(s, 1) == pytest.approx(2.0)       # drop A: 3 - 1
    assert RP.drop_top(s, 2) == pytest.approx(-1.0)      # drop A, C
    assert RP.drop_top(s, 3) is None                     # n/a, never $0
    assert RP.money(RP.drop_top(s, 3), 5) == "  n/a"


def test_cluster_boot_by_hand():
    # two units: +1 and -10. Totals of a 2-draw: +2 (1/4), -9 (1/2), -20 (1/4).
    b = RP.cluster_boot(pd.Series([1.0, -10.0]), n_boot=20_000, seed=7)
    assert b["share_pos"] == pytest.approx(0.25, abs=0.015)
    assert b["units"] == 2
    allpos = RP.cluster_boot(pd.Series([1.0, 2.0, 3.0]))
    assert allpos["share_pos"] == 1.0
    again = RP.cluster_boot(pd.Series([1.0, -10.0, 4.0]))
    assert again == RP.cluster_boot(pd.Series([1.0, -10.0, 4.0])), "seeded"


def test_cluster_boot_draws_as_many_units_as_there_are():
    # one big positive unit among many small negatives: drawing ONE unit per
    # resample would put share_pos near 1/n; drawing n with replacement
    # gives P(at least one draw of the big unit) = 1 - (1 - 1/n)^n.
    n = 10
    v = pd.Series([100.0] + [-1.0] * (n - 1))
    b = RP.cluster_boot(v, n_boot=20_000, seed=3)
    assert b["share_pos"] == pytest.approx(1 - (1 - 1 / n) ** n, abs=0.015)


def test_concentration_is_not_read_when_net_is_not_positive():
    assert RP.concentration(pd.Series({2019: 5.0, 2020: -6.0}), -1.0) == (None, None)
    k, s = RP.concentration(pd.Series({2019: 6.0, 2020: 4.0}), 10.0)
    assert k == 2019 and s == pytest.approx(0.6)


def test_pct_and_money_bracket_negatives():
    assert RP.money(-1234.4, 9) == "  (1,234)"
    assert RP.pct(-0.123, 8) == " (12.3)%"
    assert RP.pct(float("nan"), 5) == "  n/a"


# --- measure(), by hand on a one-root book -----------------------------------------

def _book(equity=3_000_000.0):
    inp = trending_root("XX")
    s = _series(inp, ONE)
    return s, run_book({"XX": s}, {"XX": ONE}, equity=equity)


def test_measure_net_is_gross_minus_sides_times_fee_at_every_level():
    s, b = _book()
    m = RP.measure(b, "frac")
    start = RP.first_live(b)
    g = b.pnl_frac.loc[b.pnl_frac.index >= start, "XX"]
    sides = (b.sides[("frac", "roll")] + b.sides[("frac", "rebalance")]).loc[g.index, "XX"]
    for lvl, fee in FRICTION.items():
        assert m.net[lvl] == pytest.approx(g.sum() - sides.sum() * fee)
    assert m.gross == pytest.approx(g.sum())
    assert m.by_year["net_mid"].sum() == pytest.approx(m.net["mid"])
    assert m.by_market["net_mid"].sum() == pytest.approx(m.net["mid"])
    daily = g - sides * FRICTION["mid"]
    assert m.realised_vol == pytest.approx(daily.std(ddof=1) * np.sqrt(261) / b.equity)
    assert m.ret_per_vol == pytest.approx(daily.mean() * 261 / (daily.std(ddof=1) * np.sqrt(261)))
    cum = daily.cumsum()
    assert m.max_dd == pytest.approx((cum - cum.cummax()).min())


def test_measure_starts_at_the_first_live_session_not_the_first_bar():
    s, b = _book()
    m = RP.measure(b, "frac")
    assert m.start == b.live["XX"].idxmax()
    assert m.start > b.pnl_frac.index[0]


def test_halves_split_at_the_median_active_month_and_add_up():
    s, b = _book()
    m = RP.measure(b, "frac")
    split, h1, h2 = RP.halves(m)
    months = sorted({d.strftime("%Y-%m") for d in m.daily_net_mid.index})
    assert split == months[len(months) // 2]
    assert h1 + h2 == pytest.approx(m.net["mid"])
    ym = m.daily_net_mid.index.strftime("%Y-%m")
    assert h2 == pytest.approx(m.daily_net_mid[ym >= split].sum())
    assert (ym == split).any() and m.daily_net_mid[ym == split].abs().sum() > 0


def test_linear_in_equity_fractional():
    """Amendment E item 1: E sets the dollar scale of the fractional book and
    nothing else."""
    _, a = _book(1_000_000.0)
    _, b = _book(2_000_000.0)
    ma, mb = RP.measure(a, "frac"), RP.measure(b, "frac")
    for lvl in FRICTION:
        assert mb.net[lvl] == pytest.approx(2 * ma.net[lvl])
    assert mb.realised_vol == pytest.approx(ma.realised_vol)


# --- the one-lot book reuses run_book's arithmetic ------------------------------------

def test_pnl_for_positions_reproduces_run_books_integer_book():
    a, b_ = trending_root("AA", seed=1), trending_root("BB", seed=2)
    ra, rb = Root("AA", 100.0, "MAA", 0.1), Root("BB", 100.0, "MBB", 0.1)
    ser = {"AA": _series(a, ra), "BB": _series(b_, rb)}
    roots = {"AA": ra, "BB": rb}
    bk = run_book(ser, roots, equity=5_000_000.0)
    pnl, r, reb = RP.pnl_for_positions(bk, ser, roots, bk.pos_int)
    assert np.allclose(pnl.to_numpy(), bk.pnl_int.to_numpy())
    assert np.allclose(r.to_numpy(), bk.sides[("int", "roll")].to_numpy())
    assert np.allclose(reb.to_numpy(), bk.sides[("int", "rebalance")].to_numpy())


def test_one_lot_book_holds_one_contract_in_the_sign_of_the_target():
    s, b = _book()
    ol = RP.one_lot_book(b, {"XX": s}, {"XX": ONE})
    held = ol.pos_int["XX"]
    assert set(np.unique(held)) <= {-1.0, 0.0, 1.0}
    assert (np.sign(b.pos_frac["XX"]) == held).all()


# --- criteria ---------------------------------------------------------------------

def _measure_like(by_year: dict, by_market: dict, high=None, rpv=1.0):
    total = sum(by_year.values())
    idx = pd.bdate_range("2012-01-02", "2019-12-31")
    daily = pd.Series(0.0, index=idx)
    for y, v in by_year.items():
        d = idx[idx.year == y]
        daily[d] = v / len(d)
    return RP.Measure(gross=total, net={"low": total, "mid": total,
                                        "high": total if high is None else high},
                      by_year=pd.DataFrame({"net_mid": pd.Series(by_year)}),
                      by_market=pd.DataFrame({"net_mid": pd.Series(by_market)}),
                      daily_net_mid=daily, years=8.0, start=idx[0], end=idx[-1],
                      realised_vol=0.1, ret_per_vol=rpv, max_dd=-1.0,
                      sides_roll_py=0.0, sides_reb_py=0.0)


def _even(total=8000.0):
    yrs = {y: total / 8 for y in range(2012, 2020)}
    mk = {m: total / 8 for m in "ABCDEFGH"}
    return yrs, mk


def test_a_clean_book_passes_all_nine():
    yrs, mk = _even()
    m = _measure_like(yrs, mk, rpv=1.0)
    bh = _measure_like({y: 10.0 for y in yrs}, mk, rpv=0.1)
    c = RP.criteria(m, bh, {1: 1.0, 3: 2.0, 6: 3.0, 9: 4.0, 12: 5.0, 24: 6.0}, 10.0)
    assert [x.n for x in c] == list(range(1, 10))
    assert all(x.passed for x in c), [x for x in c if not x.passed]


def test_one_strong_year_fails_criterion_7_even_when_everything_else_passes():
    yrs, mk = _even()
    yrs = {y: 100.0 for y in yrs}
    yrs[2016] = 8000.0 - 700.0              # 91% of net in one year
    m = _measure_like(yrs, mk)
    bh = _measure_like({y: 1.0 for y in yrs}, mk, rpv=0.1)
    c = {x.n: x for x in RP.criteria(m, bh, {k: 0.0 for k in (1, 3, 6, 9, 12, 24)}, 1.0)}
    assert not c[7].passed and "2016" in c[7].value
    assert c[1].passed


def test_one_market_over_half_fails_criterion_7():
    yrs, _ = _even()
    mk = {"A": 5000.0, "B": 1000.0, "C": 1000.0, "D": 1000.0}
    m = _measure_like(yrs, mk)
    bh = _measure_like({y: 1.0 for y in yrs}, mk, rpv=0.1)
    c = {x.n: x for x in RP.criteria(m, bh, {k: 0.0 for k in (1, 3, 6, 9, 12, 24)}, 1.0)}
    assert not c[7].passed and "A" in c[7].value


def test_criterion_3_and_8_and_9_and_6():
    yrs, _ = _even()
    mk = {"A": 6000.0, "B": 3000.0, "C": -1000.0}      # drop-top-2 = -1000
    m = _measure_like(yrs, mk, high=-5.0, rpv=0.5)
    bh = _measure_like({y: 500.0 for y in yrs}, mk, rpv=0.9)    # less net, better per unit of vol
    c = {x.n: x for x in RP.criteria(m, bh, {1: 1.0, 3: 2.0, 6: 30.0, 9: 40.0, 12: 5.0, 24: 6.0}, 5.0)}
    assert not c[3].passed           # drop-top-2 negative
    assert not c[9].passed           # high friction negative
    assert not c[6].passed           # net beats B&H but ret/vol does not: BOTH needed
    assert not c[8].passed           # median of six = (5+6)/2 = 5.5 > 5.0
    c8 = RP.criteria(m, bh, {1: 1.0, 3: 2.0, 6: 30.0, 9: 40.0, 12: 5.0, 24: 6.0}, 5.5)[7]
    assert c8.passed                 # equal to the median is "not beaten"


def test_an_empty_half_fails_criterion_2():
    yrs = {y: (0.0 if y >= 2016 else 2000.0) for y in range(2012, 2020)}
    m = _measure_like(yrs, {"A": 4000.0, "B": 4000.0})
    bh = _measure_like({y: 1.0 for y in yrs}, {"A": 1.0}, rpv=0.1)
    c = {x.n: x for x in RP.criteria(m, bh, {k: 0.0 for k in (1, 3, 6, 9, 12, 24)}, 1.0)}
    assert not c[2].passed


def test_bootstrap_criteria_use_95_percent():
    yrs, _ = _even()
    mk = {"A": 9000.0, **{c: -100.0 for c in "BCDEFGHIJK"}}   # most resamples > 0, not 95%
    m = _measure_like(yrs, mk)
    bh = _measure_like({y: 1.0 for y in yrs}, mk, rpv=0.1)
    c = {x.n: x for x in RP.criteria(m, bh, {k: 0.0 for k in (1, 3, 6, 9, 12, 24)}, 1.0)}
    share = RP.cluster_boot(pd.Series(mk))["share_pos"]
    assert 0.5 < share < 0.95
    assert not c[4].passed


# --- end to end, synthetic -------------------------------------------------------------

def test_build_end_to_end_reads_only_the_training_side(monkeypatch):
    calls = []
    real = H.split_months

    def spy(months, **kw):
        calls.append(kw.get("spend", False))
        return real(months, **kw)
    monkeypatch.setattr(H, "split_months", spy)
    rep = RP.build(_inputs())
    assert calls and not any(calls), "only the training side is ever asked for"
    assert rep.books["spec"].pnl_frac.index.max() < D(H.LOCK_FROM)
    for e, b in rep.books["int"].items():
        assert b.pnl_int.index.max() < D(H.LOCK_FROM)
    for head in ("SECTION 4", "ITEMS 1 & 3", "ITEM 2", "ITEMS 5 & 6", "ITEM 7", "ITEM 8",
                 "ITEM 9", "ITEM 10", "ITEM 11", "ITEM 12", "ITEM 13", "SECTION 5",
                 "drop-top-3", "EXCLUDED"):
        assert head in rep.text, head
    assert len(rep.crit) == 9
    assert rep.verdict == all(c.passed for c in rep.crit)
    assert H.read_ledger() is None, "the report never spends the holdout"


def test_build_refuses_a_series_that_reaches_the_holdout(monkeypatch):
    monkeypatch.setattr(H, "split_months", lambda months, **kw: (list(months), 0, "broken"))
    with pytest.raises(H.HoldoutRefused):
        RP.build(_inputs())


def test_every_arm_and_every_grid_cell_is_printed():
    rep = RP.build(_inputs())
    for arm in RATES_ARMS:
        assert f"\n{arm}" in rep.text
    for d in range(1, 22):
        assert f"d{d:<2}" in rep.text
    for k in (1, 3, 6, 9, 12, 24):
        assert f"k={k}" in rep.text
    for n in list(CORE) + ["TN"]:
        assert f"\n{n:>5}" in rep.text


def test_skip_month_neighbour_differs_from_the_spec_and_default_is_no_skip():
    inp = trending_root("XX", seed=5)
    s = _series(inp, ONE)
    base = run_book({"XX": s}, {"XX": ONE}, equity=1e6, ks=(12,))
    same = run_book({"XX": s}, {"XX": ONE}, equity=1e6, ks=(12,), skip_months=0)
    skip = run_book({"XX": s}, {"XX": ONE}, equity=1e6, ks=(12,), skip_months=1)
    assert np.array_equal(base.pos_frac.to_numpy(), same.pos_frac.to_numpy())
    assert not np.array_equal(base.signal.fillna(0).to_numpy(), skip.signal.fillna(0).to_numpy())
    assert RP.first_live(skip) > RP.first_live(base)      # one more month of warm-up
    with pytest.raises(ValueError):
        run_book({"XX": s}, {"XX": ONE}, equity=1e6, skip_months=-1)


def test_cluster_boot_counts_a_zero_total_as_not_positive():
    # units +1 and -1: a 2-draw totals +2 (1/4), 0 (1/2), -2 (1/4). "> 0" is 1/4.
    b = RP.cluster_boot(pd.Series([1.0, -1.0]), n_boot=20_000, seed=11)
    assert b["share_pos"] == pytest.approx(0.25, abs=0.015)


def _hand_book(daily):
    idx = pd.bdate_range("2020-01-01", periods=len(daily))
    z = pd.DataFrame(0.0, index=idx, columns=["XX"])
    pnl = pd.DataFrame({"XX": daily}, index=idx)
    from strategy.tsmom.book import BookResult
    return BookResult(roots=["XX"], equity=1000.0,
                      live=pd.DataFrame(True, index=idx, columns=["XX"]), signal=z,
                      pos_frac=z, pos_int=z, pnl_frac=pnl, pnl_int=pnl,
                      sides={(s, k): z for s in ("frac", "int") for k in ("roll", "rebalance")})


def test_max_drawdown_is_peak_to_trough_not_distance_from_the_final_high():
    # cum: 10, 4, 24, 20  -> worst peak-to-trough = 4 - 10 = -6
    # (distance from the overall high 24 would give 4 - 24 = -20)
    m = RP.measure(_hand_book([10.0, -6.0, 20.0, -4.0]), "frac")
    assert m.max_dd == pytest.approx(-6.0)


def test_one_lot_book_trades_markets_the_integer_book_rounds_to_zero():
    inp = trending_root("XX", level=4000.0)
    big = Root("XX", 1000.0, "MXX", 0.1)
    s = _series(inp, big)
    b = run_book({"XX": s}, {"XX": big}, equity=22_000.0)
    assert (b.pos_int["XX"] == 0).all() and (b.pos_frac["XX"] != 0).any()
    ol = RP.one_lot_book(b, {"XX": s}, {"XX": big})
    assert (ol.pos_int["XX"].abs() == 1).any()
    assert ol.pnl_int["XX"].abs().sum() > 0


def test_skip_month_signal_is_the_k_sign_one_month_earlier_by_hand():
    from strategy.tsmom.signal import trailing_sign
    inp = trending_root("XX", seed=5, drift=0.0)          # no drift: the sign flips
    s = _series(inp, ONE)
    skip = run_book({"XX": s}, {"XX": ONE}, equity=1e6, ks=(12,), skip_months=1)
    reb = skip.signal["XX"].dropna()
    assert len(reb) > 20 and (reb > 0).any() and (reb < 0).any()
    for d in reb.index:
        i = s.index[s.index.get_loc(d) - 1]                     # information date
        want = trailing_sign(s["cont"], pd.DatetimeIndex([i - pd.DateOffset(months=1)]), 12).iloc[0]
        assert reb[d] == want
