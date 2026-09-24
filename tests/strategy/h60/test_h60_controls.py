"""§4.1 random-entry control, §4.3 positive control (gate G7), and §7's
criteria (REGISTERED_h60_v0.md)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from strategy.h60 import basket as K
from strategy.h60 import controls as CT
from strategy.h60 import engine as E
from strategy.h60 import rules as R
from strategy.h60 import score as SC
from strategy.h60.rules import Book
from tests.strategy.h60 import _synth as S


def quiet_panel(n_sym=40, n_days=45, vol=0.0004):
    days = S.sessions(n_days)
    return S.panel([S.random_walk(f"S{i:02d}", days, vol=vol, start=50 + i)
                    for i in range(n_sym)])


# --------------------------------------------------------------------------
# §4.3 positive control
# --------------------------------------------------------------------------

def test_positive_control_recovers_the_planted_twenty_bps():
    p = quiet_panel(n_sym=200)
    rate = 0.05
    flags = CT.flagged(p, rate=rate)
    res = CT.positive_control(p, K.build, flags=flags)
    assert res["planted"]["trades"] > 100
    # the planted and null runs trade the same names at the same prices bar
    # the plant, so their difference is the effect itself: 20 bps on ~$10k,
    # less the flagged names' own share of the basket (~rate)
    diff = res["planted"]["mr_gross_per_trade"] - res["null"]["mr_gross_per_trade"]
    assert diff == pytest.approx(20.0 * (1 - rate), abs=0.6)
    assert res["planted"]["mr_gross_per_trade"] == pytest.approx(20.0, abs=2.0)
    assert abs(res["null"]["mr_gross_per_trade"]) < 2.0
    assert res["pass"]


def test_positive_control_fails_a_harness_that_misses_the_effect(monkeypatch):
    """Mutation: plant the step BEFORE the entry (the 10:30 open raised too),
    so the rule's fill already contains it and nothing is captured. The
    control must fail -- a harness that finds nothing passes every null."""
    p = quiet_panel(n_sym=200)
    flags = CT.flagged(p, rate=0.05)
    real = CT.plant
    monkeypatch.setattr(CT, "plant", lambda panel, fl, bps=CT.PC_BPS, slot=CT.PC_SLOT:
                        real(panel, fl, bps, slot - 1))
    res = CT.positive_control(p, K.build, flags=flags)
    assert not res["pass"]
    assert abs(res["planted"]["mr_gross_per_trade"]) < 2.0


def test_positive_control_fails_if_the_basket_is_not_subtracted(monkeypatch):
    """Mutation: a market-relative number that is really gross. On a drifting
    market the null run is no longer ~0 and the control fails."""
    days = S.sessions(45)
    p = S.panel([S.random_walk(f"S{i:03d}", days, vol=0.0004, drift=0.0015, start=50 + i)
                 for i in range(200)])
    flags = CT.flagged(p, rate=0.05)
    assert CT.positive_control(p, K.build, flags=flags)["pass"]

    class Zero:
        def __init__(self, b):
            self.b = b

        def ret(self, a, x):
            return np.zeros(len(np.asarray(a)))
    res = CT.positive_control(p, lambda q: Zero(K.build(q)), flags=flags)
    assert not res["pass"]


def test_flags_are_eligible_seeded_and_order_free():
    p = quiet_panel(n_sym=10, n_days=40)
    f1 = CT.flagged(p, rate=0.1)
    f2 = CT.flagged(p, rate=0.1)
    assert f1 == f2 and 0.05 < len(f1) / (10 * 40) < 0.15
    assert all(p.elig[s][i] for s, i in f1)


def test_plant_touches_only_flagged_days_after_the_1030_open():
    p = quiet_panel(n_sym=3, n_days=5)
    flags = {("S00", 2)}
    q = CT.plant(p, flags)
    a, b = p.arrays("S00"), q.arrays("S00")
    day = a.s == 2
    k = 1.002
    assert np.array_equal(a.o[~day], b.o[~day]) and np.array_equal(a.c[~day], b.c[~day])
    at = day & (a.bar == 1)
    after = day & (a.bar > 1)
    assert np.array_equal(a.o[at], b.o[at])
    np.testing.assert_allclose(b.c[at], a.c[at] * k)
    np.testing.assert_allclose(b.o[after], a.o[after] * k)
    np.testing.assert_allclose(b.c[day & (a.bar == 0)], a.c[day & (a.bar == 0)])
    assert np.array_equal(p.arrays("S01").c, q.arrays("S01").c)


# --------------------------------------------------------------------------
# §4.1 random entries
# --------------------------------------------------------------------------

def test_random_control_is_seeded_and_keeps_to_its_sessions():
    p = quiet_panel(n_sym=8, n_days=40, vol=0.01)
    book = Book("DON-60", "DON-60", "channel", True)
    pairs = CT.price_pairs(p, book, K.build(p))
    assert len(pairs.mr_net) > 400
    eps = {32: 3, 35: 2, 39: 5}
    r1 = CT.random_control(pairs, eps, "DON-60", n_draws=200)
    r2 = CT.random_control(pairs, eps, "DON-60", n_draws=200)
    assert np.array_equal(r1["draws"], r2["draws"]) and r1["n_per_draw"] == 10
    r3 = CT.random_control(pairs, eps, "MCL-60", n_draws=200)
    assert not np.array_equal(r1["draws"], r3["draws"])      # own seed per book


def test_name_first_then_bar():
    """Name A has 1 valid bar in the session, name B has 99: A is drawn about
    half the time, not 1%."""
    sym = np.r_[np.zeros(1, np.int64), np.ones(99, np.int64)]
    pairs = CT.Pairs(sym=sym, s_sig=np.full(100, 7), mr_net=np.r_[1.0, np.zeros(99)],
                     names=["A", "B"])
    r = CT.random_control(pairs, {7: 1}, "x", n_draws=4000)
    assert 0.45 < r["draws"].mean() < 0.55


def test_unmatched_sessions_are_counted_not_filled():
    pairs = CT.Pairs(sym=np.zeros(3, np.int64), s_sig=np.array([1, 1, 2]),
                     mr_net=np.ones(3), names=["A"])
    r = CT.random_control(pairs, {1: 2, 5: 4}, "x", n_draws=10)
    assert r["unmatched"] == 4 and r["n_per_draw"] == 2


def test_random_pairs_use_the_books_own_exit_and_filters():
    """Every priced pair is one engine.candidates would admit, exited by the
    same simulate call: pricing the book's own signal bars through
    price_pairs reproduces the book's own trades."""
    p = quiet_panel(n_sym=5, n_days=45, vol=0.01)
    book = Book("DON-60", "DON-60", "channel", True)
    bk = K.build(p)
    pairs = CT.price_pairs(p, book, bk)
    trades, _ = E.run_book(p, book)
    sc = SC.score(trades, bk, p.grid)
    # every trade's (symbol, signal session, mr) appears among the pairs
    have = set(zip(pairs.sym.tolist(), pairs.s_sig.tolist(), np.round(pairs.mr_net, 6).tolist()))
    for sym, s, mr in zip(sc["symbol"], sc["s_signal"], sc["mr_net_L2"]):
        assert (pairs.names.index(sym), int(s), round(float(mr), 6)) in have


# --------------------------------------------------------------------------
# §7 criteria
# --------------------------------------------------------------------------

def book_frame(n=400, mr=5.0, net=3.0, l3=1.0, seed=1):
    rng = np.random.default_rng(seed)
    days = S.sessions(1500)
    ent = [days[i] for i in rng.integers(0, 1500, n)]
    syms = [f"N{i % 50:02d}" for i in range(n)]
    return pd.DataFrame({"symbol": syms, "entry_session": ent,
                         "mr_net_L2": mr + rng.normal(0, 1, n),
                         "net_L2": net + rng.normal(0, 1, n),
                         "mr_net_L3": l3 + rng.normal(0, 1, n)}), days


def test_a_clean_book_passes_every_criterion():
    t, days = book_frame()
    ev = SC.evaluate(t, name="X", training_sessions=days, random_p95=1.0)
    assert ev["all_pass"], {k: v for k, v in ev.items() if k != "all_pass" and not v["pass"]}


@pytest.mark.parametrize("mutate,crit", [
    (lambda t: t.assign(mr_net_L2=-t["mr_net_L2"]), "1_mr_net_per_trade_gt_0"),
    (lambda t: t.assign(net_L2=-t["net_L2"]), "2_net_per_trade_gt_0"),
    (lambda t: t.assign(mr_net_L3=-t["mr_net_L3"]), "8_mr_positive_at_L3"),
    (lambda t: t.iloc[:250], "9_at_least_300_trades"),
])
def test_each_criterion_can_fail(mutate, crit):
    t, days = book_frame()
    ev = SC.evaluate(mutate(t), name="X", training_sessions=days, random_p95=1.0)
    assert not ev[crit]["pass"] and not ev["all_pass"]


def test_halves_split_at_the_median_session_and_an_empty_half_fails():
    t, days = book_frame()
    early = t[t["entry_session"] < days[750]]
    ev = SC.evaluate(early, name="X", training_sessions=days, random_p95=1.0)
    assert ev["3_both_halves_mr_gt_0"]["value"]["second"] is None
    assert not ev["3_both_halves_mr_gt_0"]["pass"]


def test_drop_top5_and_concentration():
    t, days = book_frame(mr=-0.5, net=-0.5)
    t.loc[t["symbol"] == "N00", ["mr_net_L2", "net_L2"]] = 500.0
    ev = SC.evaluate(t, name="X", training_sessions=days, random_p95=-99)
    assert ev["1_mr_net_per_trade_gt_0"]["pass"]
    assert not ev["4_drop_top5_symbols_mr_gt_0"]["pass"]
    assert not ev["7_no_year_or_symbol_gt_50pct"]["pass"]
    assert ev["7_no_year_or_symbol_gt_50pct"]["value"]["symbol"] == "N00"


def test_bootstrap_is_seeded_and_strict():
    t, days = book_frame(mr=0.05)
    a = SC.bootstrap_share_positive(t, "mr_net_L2", "X")
    assert a == SC.bootstrap_share_positive(t, "mr_net_L2", "X")
    assert a < SC.BOOT_BAR
    assert SC.bootstrap_share_positive(book_frame(mr=5.0)[0], "mr_net_L2", "X") == 1.0


def test_random_control_criterion_and_tl_vs_don():
    t, days = book_frame(mr=2.0)
    assert not SC.evaluate(t, name="X", training_sessions=days,
                           random_p95=3.0)["6_beats_random_p95"]["pass"]
    assert not SC.evaluate(t, name="X", training_sessions=days,
                           random_p95=None)["6_beats_random_p95"]["pass"]
    ev = SC.evaluate(t, name="TL", training_sessions=days, random_p95=0.0,
                     don_mr_per_trade=10.0)
    assert not ev["10_tl_beats_don"]["pass"]


def test_ensemble_per_trade_is_per_ten_thousand():
    t, days = book_frame(n=900, mr=1.0)
    ev = SC.evaluate(t, name="TL", training_sessions=days, random_p95=0.0, sleeves=3)
    assert ev["9_at_least_300_trades"]["value"] == 300
    assert ev["1_mr_net_per_trade_gt_0"]["value"] == pytest.approx(3 * t["mr_net_L2"].mean())


def test_score_columns():
    p = quiet_panel(n_sym=4, n_days=40, vol=0.01)
    t, _ = E.run_book(p, Book("DON-60", "DON-60", "channel", True))
    sc = SC.score(t, K.build(p), p.grid)
    np.testing.assert_allclose(sc["net_L2"], sc["gross"] - sc["cost_L2"])
    np.testing.assert_allclose(sc["mr_net_L2"], sc["net_L2"] - sc["notional"] * sc["basket_ret"])
    assert (sc["cost_L3"] >= sc["cost_L2"]).all() and (sc["cost_L1"] > 0).all()
    assert SC.score(t.iloc[:0], K.build(p), p.grid).empty


def test_pairs_obey_the_same_split_and_bad_day_exclusions_as_trades():
    p = quiet_panel(n_sym=3, n_days=45, vol=0.01)
    book = Book("MCL-60", "MCL-60", "trail5", True)
    bk = K.build(p)
    base = CT.price_pairs(p, book, bk)
    sym = base.names[0]
    split = CT.price_pairs(p, book, bk, split_days={(sym, 36)})
    bad = CT.price_pairs(p, book, bk, excluded_days={(sym, 36)})
    assert len(split.mr_net) < len(base.mr_net) and len(bad.mr_net) < len(base.mr_net)
    # a bad day removes every pair that TOUCHES it; a split only those that
    # SPAN it (entered before, still held on it) -- so the bad day removes more
    assert len(bad.mr_net) < len(split.mr_net)
    other = [n for n in base.names[1:]]
    for q in (split, bad):
        for k, n in enumerate(base.names):
            if n != sym:
                assert (q.sym == k).sum() == (base.sym == k).sum()


def test_hits_interval_edges():
    d = {"A": np.array([5])}
    lo, hi = np.array([5, 4, 2, 6]), np.array([7, 5, 4, 9])
    assert list(CT._hits(d, "A", lo, hi, open_lo=True)) == [False, True, False, False]
    assert list(CT._hits(d, "A", lo, hi, open_lo=False)) == [True, True, False, False]
    assert not CT._hits(d, "B", lo, hi, open_lo=True).any()


def test_union_basket_counts_overlaps_once():
    class Lin:
        def ret(self, a, b):
            return (b - a) / 100.0
    t = pd.DataFrame({"entry_mark": [0, 5, 20], "exit_mark": [10, 12, 30]})
    got = SC.union_basket_return(t, Lin())
    assert got == pytest.approx((1 + 0.12) * (1 + 0.10) - 1)
