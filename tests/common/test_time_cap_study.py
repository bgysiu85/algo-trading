#!/usr/bin/env python3
"""The time-cap study runner (common/time_cap_study.py, W03-0004).

Run on constructed sessions through the REAL engines, so the arms are checked
against the published books rather than against a model of them.
"""
from __future__ import annotations

from datetime import date, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from common import slot_book as SB
from common import time_cap_study as TC
from common.pit_strategy import engine
from tests.strategy.mc5.test_mc5_strategy import frame_1m, momentum_series

ET = ZoneInfo("America/New_York")
DAY = "2026-09-02"
FLOOR = time(4, 0)
GRID = (None, 5, 30)


def sym_frame(seed: int) -> pd.DataFrame:
    px = momentum_series(seed, n=600)
    rng = np.random.default_rng(seed + 100)
    vols = [5000.0] * 600
    for i in range(60, 600):
        vols[i] = vols[i - 1] * 4 if rng.random() < 0.08 else 5000.0 * (1 + rng.random())
    return frame_1m(px, vols=vols, start="00:00")


@pytest.fixture(scope="module")
def engines():
    return {"MCL": engine("mcl"), "MC5": engine("mc5")}


@pytest.fixture(scope="module")
def frames():
    return [(f"S{k}", sym_frame(k), FLOOR) for k in range(1, 9)]


@pytest.fixture(scope="module")
def result(frames, engines):
    return TC.run_symbols(DAY, frames, engines, grid=GRID)


def rows(res, arm, cap):
    return [r for r in res["trades"] if r["arm"] == arm and r["cap"] == TC.cap_label(cap)]


def key(r):
    return (r["book"], r["symbol"], r["entry_et"], r["exit_et"], r["net"])


def test_hold_bars_maps_minutes_to_each_books_bars():
    assert TC.hold_bars("MCL", 30) == 30 and TC.hold_bars("MC5", 30) == 6
    assert TC.hold_bars("MCL", None) is None and TC.hold_bars("MC5", None) is None
    with pytest.raises(ValueError):
        TC.hold_bars("MC5", 7)
    assert all(c is None or c % 5 == 0 for c in TC.GRID_MIN)


def test_registered_settings_are_the_ones_in_the_code():
    text = open(TC.REGISTERED, encoding="utf-8").read()
    assert "none, 5, 10, 15, 30, 60, 120" in text
    assert TC.GRID_MIN == (None, 5, 10, 15, 30, 60, 120)
    assert TC.PRIMARY == 30 and "**30 minutes**" in text
    assert TC.SLOTS == 3 and TC.EDGES == (5, 120)


def test_free_arm_with_no_cap_is_the_published_book(result, frames, engines):
    d = date.fromisoformat(DAY)
    want = []
    for sym, df, floor in frames:
        for book in TC.BOOKS:
            mod, extra = engines[book]
            for t in mod.backtest_session(df, d, ET, entry_shares=100,
                                          not_before=floor, **extra):
                want.append(key(TC.trade_row("free", None, SB.Leg(book, sym), DAY, t)))
    assert sorted(key(r) for r in rows(result, "free", None)) == sorted(want)
    assert want, "fixture produced no trades"


def test_the_slot_cap_binds_in_the_fixture(result):
    assert any(r["arm"] == "account" for r in result["refusals"])
    assert len(rows(result, "account", None)) < len(rows(result, "free", None))


def test_a_cap_nobody_reaches_changes_nothing(frames, engines):
    res = TC.run_symbols(DAY, frames, engines, grid=(None, 30),
                         arms={"free": (None, "strategy", False),
                               "huge": (99, "account", False)})
    for cap in (None, 30):
        assert sorted(map(key, rows(res, "huge", cap))) == sorted(map(key, rows(res, "free", cap)))
    assert not res["refusals"]


def _max_open(rs, scope):
    ev = []
    for r in rs:
        L = SB.BAR_MINUTES[r["book"]]
        tin = pd.Timestamp(f"{r['date']} {r['entry_et']}") + pd.Timedelta(minutes=L)
        tout = pd.Timestamp(f"{r['date']} {r['exit_et']}") + pd.Timedelta(minutes=L)
        grp = r["book"] if scope == "strategy" else "all"
        ev += [(tout, 0, grp), (tin, 1, grp)]
    open_, worst = {}, 0
    for _, k, g in sorted(ev):
        open_[g] = open_.get(g, 0) + (1 if k else -1)
        worst = max(worst, open_[g])
    return worst


@pytest.mark.parametrize("arm,scope", [("strategy", "strategy"), ("account", "account"),
                                       ("strategy-rev", "strategy"), ("account-rev", "account")])
def test_no_arm_ever_holds_more_than_three(result, arm, scope):
    for cap in GRID:
        assert _max_open(rows(result, arm, cap), scope) <= TC.SLOTS


def test_the_free_book_does_exceed_three(result):
    """Otherwise the test above proves nothing."""
    assert _max_open(rows(result, "free", None), "account") > TC.SLOTS


def test_no_trade_outlives_its_time_cap(result):
    for arm in TC.ARMS:
        for cap in (5, 30):
            for r in rows(result, arm, cap):
                assert r["bars_held"] * SB.BAR_MINUTES[r["book"]] <= cap, r


def test_the_time_cap_fires_in_the_fixture(result):
    assert any(r["reason"] == "hold_cap" for r in rows(result, "free", 30))


def test_every_arm_scores_the_same_symbol_days(result):
    syms = {r["symbol"] for r in rows(result, "free", None)}
    assert result["symdays"] == 8 and len(syms) >= 6


def test_a_broken_symbol_is_dropped_from_every_arm(frames, engines):
    sym, df, floor = frames[0]
    bad = pd.concat([df, df.iloc[-5:]])          # duplicate bar labels
    res = TC.run_symbols(DAY, [("BAD", bad, floor)] + frames[1:4], engines, grid=(None, 30))
    assert res["symdays"] == 3
    assert not [r for r in res["trades"] if r["symbol"] == "BAD"]
    assert res["errors"] and res["errors"][0].startswith("BAD")


def test_controls_arithmetic():
    days = ["d1", "d2", "d3", "d4"]
    base = pd.DataFrame({"date": days, "net": [TC.MEASURED_FRICTION] * 4})
    cell = pd.DataFrame({"date": days, "net": [TC.MEASURED_FRICTION + v for v in (10, 20, -5, 1)]})
    c = TC.controls(cell, base, days, split="d3")
    assert c["total"] == pytest.approx(26)
    assert c["early"] == pytest.approx(30) and c["late"] == pytest.approx(-4)
    assert c["dropped"] == pytest.approx(26 - 31)
    assert 0.5 < c["p_pos"] < 1.0
    allpos = TC.controls(cell.assign(net=TC.MEASURED_FRICTION + 1), base, days, "d3")
    assert allpos["p_pos"] == 1.0


def test_verdict_rule():
    good = {"total": 10, "early": 4, "late": 6, "dropped": 1, "p_pos": 0.97}
    assert TC.verdict(good, 30, 5)[0]
    assert not TC.verdict(good, 120, 5)[0]                       # boundary
    assert not TC.verdict(dict(good, late=-1), 30, 5)[0]          # halves
    assert not TC.verdict(dict(good, dropped=-1), 30, 5)[0]       # concentration
    assert not TC.verdict(dict(good, p_pos=0.9), 30, 5)[0]        # bootstrap
    assert not TC.verdict(dict(good, total=-1), 30, 5)[0]
    assert "PORTFOLIO" in "\n".join(TC.verdict(good, 30, 5)[1])
    assert "EXIT rule" in "\n".join(TC.verdict(good, 30, -1)[1])


def test_money_brackets_negatives():
    assert TC.money(-1234.5, 0) == "(1,234.50)"
    assert TC.money(12, 0) == "12.00"


def test_report_renders_on_real_output(result):
    t = pd.DataFrame(result["trades"], columns=TC.TRADE_COLS)
    r = pd.DataFrame(result["refusals"], columns=TC.REFUSAL_COLS)
    # the fixture only ran GRID; fill the other registered cells with the no-cap book
    extra = []
    for cap in TC.GRID_MIN:
        if cap not in GRID:
            extra.append(t[t.cap == "none"].assign(cap=TC.cap_label(cap)))
    t = pd.concat([t] + extra, ignore_index=True)
    text = "\n".join(TC.report(t, r, [DAY], result["symdays"], [], 1.0, 1))
    for must in ("1. THE SLOT CAP ON ITS OWN", "ARM 1", "3 SLOTS PER STRATEGY",
                 "PAIRED", "CONTROLS", "TIE-ORDER", "SAMPLE TRADES", "10. VERDICT"):
        assert must in text, must
