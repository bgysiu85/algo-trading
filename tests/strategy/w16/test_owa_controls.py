"""OWA-v0 controls C-1 (scored), C-2 and C-3. REGISTERED_w16_open_window.md
sec 8. Board W16-0040 sub 4."""
from __future__ import annotations

import zlib

import numpy as np
import pytest

from strategy.w16 import open_window as OW
from strategy.w16 import owa_controls as C
from tests.strategy.w16 import owa_fixtures as F

COST = 2.24                       # 1 MNQ round trip at L2


@pytest.fixture(scope="module")
def walk():
    mk = OW.prepare(F.random_bars(F.weekdays(45)))
    book = OW.simulate_book(mk, OW.compute_signals(mk, "15"), "C")
    assert len(book["trades"]) > 10
    return mk, book["trades"]


def _trade(clock="09:00", edits=None):
    mk, date = F.flat_market(25, edits)
    j = F.bar_at(mk, date, clock)
    trades = OW.simulate_book(mk, F.forced_signals(mk, a_long=[j]), "A", [date])["trades"]
    return mk, date, trades


def test_net_of_prices_one_mnq_at_l2():
    def edits(df, date):
        F.set_from(df, date, "15:55", 1010.0)
    mk, date = F.flat_market(25, edits)
    i = F.minute_at(mk, date, "09:05")
    got = C.net_of(mk, F.day_of(mk, date), i, "long", 998.0, 2.5)
    assert got == pytest.approx(10 * 2.0 - COST)


def test_c1_candidates_run_from_the_real_fill_to_noon():
    mk, date, trades = _trade("09:00")
    bars = C.c1_candidates(mk, F.day_of(mk, date), trades[0])
    clocks = [OW.hhmm(int(mk.b5.minute[b])) for b in bars]
    assert clocks[0] == "09:05" and clocks[-1] == "12:00" and len(clocks) == 36


def test_c1_a_noon_fill_has_only_itself():
    def edits(df, date):
        F.set_from(df, date, "13:00", 1010.0)
    mk, date, trades = _trade("11:55", edits)
    assert len(C.c1_candidates(mk, F.day_of(mk, date), trades[0])) == 1
    totals = C.c1_totals(mk, trades, n_draws=20)
    assert totals == pytest.approx(np.full(20, 10 * 2.0 - COST))


def test_c1_matches_walking_each_draw_by_hand(walk):
    mk, trades = walk
    totals = C.c1_totals(mk, trades, n_draws=3)
    by_date = {d.date: d for d in mk.days}
    for i in range(3):
        rng = np.random.default_rng(zlib.crc32(str(i).encode()))
        counts = [len(C.c1_candidates(mk, by_date[t["date"]], t)) for t in trades]
        picks = rng.integers(0, np.asarray(counts))
        total = 0.0
        for t, pick in zip(trades, picks):
            day = by_date[t["date"]]
            b = C.c1_candidates(mk, day, t)[pick]
            first = int(mk.b5.first[b])
            assert first >= t["fill_idx"] and mk.b5.minute[b] <= 720
            sign = 1 if t["direction"] == "long" else -1
            price = mk.m1.o[first]
            exit_idx, exit_price, _ = OW.walk_exit(
                mk, day, first, price, t["direction"], price - sign * t["stop_dist"])
            total += sign * (exit_price - price) * 2.0 - COST
        assert totals[i] == pytest.approx(total)
    assert np.array_equal(totals, C.c1_totals(mk, trades, n_draws=3))      # seeded
    assert len(set(np.round(C.c1_totals(mk, trades, n_draws=30), 2))) > 1


def test_c2_is_long_only_with_the_median_stop_in_atr_units(walk, monkeypatch):
    mk, trades = walk
    mult = C.median_stop_atr(trades)
    assert 0.4 <= mult <= 2.1
    seen = []
    real = C.net_of

    def spy(mk_, day, i, side, stop, trail, level="L2"):
        b = int(mk_.m1.bar5[i])
        seen.append((day.date, side, mk_.m1.o[i] - stop, mk_.atr[b - 1], mk_.b5.minute[b]))
        return real(mk_, day, i, side, stop, trail, level)

    monkeypatch.setattr(C, "net_of", spy)
    totals = C.c2_totals(mk, trades, n_draws=25)
    assert len(totals) == 25
    assert {s[1] for s in seen} == {"long"}
    for _, _, dist, atr, minute in seen:
        assert dist == pytest.approx(max(OW.nearest_tick(mult * atr), OW.TICK))
        assert 480 <= minute <= 720
    assert {s[0] for s in seen} == {t["date"] for t in trades}


def test_c2_draws_one_entry_per_real_trade_on_its_day(walk, monkeypatch):
    mk, trades = walk
    monkeypatch.setattr(C, "net_of", lambda *a, **k: 1.0)
    assert C.c2_totals(mk, trades, n_draws=4).tolist() == [len(trades)] * 4
    assert C.c1_totals(mk, trades, n_draws=4).tolist() == [len(trades)] * 4
    assert C.c3_totals(mk, trades, n_draws=4).tolist() == [len(trades)] * 4


def test_c3_flips_only_the_side():
    def edits(df, date):
        F.set_from(df, date, "13:00", 1001.0)              # below both stops' reach
    mk, date, trades = _trade("09:00", edits)
    totals = C.c3_totals(mk, trades, n_draws=200)
    long_net, short_net = 1.0 * 2.0 - COST, None
    values = sorted(set(np.round(totals, 2)))
    assert len(values) == 2 and np.round(long_net, 2) in values
    share_long = (np.round(totals, 2) == np.round(long_net, 2)).mean()
    assert 0.35 < share_long < 0.65


def test_void_trades_are_left_out_and_empty_books_are_zero(walk):
    mk, trades = walk
    voided = [dict(t, voided=True) for t in trades]
    assert C.c1_totals(mk, voided, n_draws=5).tolist() == [0.0] * 5
    assert C.c2_totals(mk, voided, n_draws=5).tolist() == [0.0] * 5
    assert C.c3_totals(mk, [], n_draws=5).tolist() == [0.0] * 5


def test_summarise():
    s = C.summarise(np.arange(101.0), real_net=50.0)
    assert (s["p5"], s["p50"], s["p95"]) == (5.0, 50.0, 95.0)
    assert s["share_of_draws_below_real"] == pytest.approx(50 / 101)
