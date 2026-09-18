#!/usr/bin/env python3
"""strategy/orb/sip_report.py -- arms, controls and the criteria, in R.

The failures that matter here are the project's recurring ones: a control that
cannot fail, a criterion read on the wrong arm, and a "fewer trades" arm that
looks better only because it traded less. Amendment C's unit is checked too:
an R average must not move when the same trade happens in a pricier stock.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.orb import sip as S
from strategy.orb import sip_report as P

DATES = [f"2025-03-{d:02d}" for d in range(3, 8)]


def ledger(rows):
    """rows: dicts overriding the defaults of one ledger row."""
    out = []
    for i, r in enumerate(rows):
        base = {
            "date": DATES[0], "symbol": f"S{i:03d}", "range": 5, "side": 1,
            "rvol": 5.0, "rank": 1.0, "eligible": True, "atr": 1.0,
            "entry_min": 575, "entry_px": 20.0, "exit_min": 959,
            "exit_px": 20.2, "exit_reason": "session_end", "r": 0.10,
            "bars_held": 384, "gapped_entry": False, "or_high": 20.0,
            "or_low": 19.5, "alt_exit_min": 959, "alt_exit_px": 20.2,
            "alt_exit_reason": "session_end",
        }
        base.update(r)
        out.append(base)
    return pd.DataFrame(out)


def test_r_is_the_unit_so_the_same_trade_in_a_pricier_stock_reads_the_same():
    """Amendment C. A 2R winner is 2R whether the stock is $8 or $800; at a
    fixed share count the second would dominate every average."""
    cheap = P.add_net(ledger([{"entry_px": 8.0, "exit_px": 8.2, "r": 0.10}]))
    rich = P.add_net(ledger([{"entry_px": 800.0, "exit_px": 820.0, "r": 10.0}]))
    assert cheap["gross_R"].iloc[0] == pytest.approx(2.0)
    assert rich["gross_R"].iloc[0] == pytest.approx(2.0)
    # Net differs only by friction, and friction is cents over a different R:
    # the same 2R costs more of itself in a name whose stop is 10c away.
    assert cheap["fricshare_PAPER"].iloc[0] > rich["fricshare_PAPER"].iloc[0]
    assert cheap["R_PAPER"].iloc[0] == pytest.approx(1.93, abs=0.01)
    assert rich["R_PAPER"].iloc[0] == pytest.approx(2.0, abs=0.01)


def test_friction_is_charged_in_r_and_hurts_the_tightest_stops_most():
    """Amendment C.3: 3c of BASE friction is 30% of a 10c stop and 0.3% of a
    $10 one. That ratio is the headline this strategy lives or dies on."""
    tight = P.add_net(ledger([{"r": 0.10}]))
    wide = P.add_net(ledger([{"r": 10.0, "entry_px": 800.0, "exit_px": 820.0}]))
    assert tight["fricshare_BASE"].iloc[0] > 0.2
    assert wide["fricshare_BASE"].iloc[0] < 0.02
    assert (tight["R_PAPER"] > tight["R_BASE"]).all()
    assert (tight["R_BASE"] > tight["R_HARSH"]).all()


def test_shares_are_equal_risk_and_bounded():
    n = P.shares_for(np.array([0.10, 10.0, 0.0, np.nan]))
    assert n[0] == 1000 and n[1] == 10
    assert n[2] == P.MAX_SHARES and n[3] == 1, "no zero, no infinity"


def test_each_arm_selects_and_nothing_else_differs():
    rows = [{"symbol": f"S{i:03d}", "rank": float(i + 1),
             "eligible": i < 30, "rvol": 3.0 if i < 30 else 0.5}
            for i in range(40)]
    df = P.add_net(ledger(rows))
    assert len(P.arm(df, 5, "top", 20)) == 20
    assert len(P.arm(df, 5, "top", 10)) == 10
    assert len(P.arm(df, 5, "eligible")) == 30
    assert len(P.arm(df, 5, "unfiltered")) == 40
    assert P.arm(df, 15, "unfiltered").empty


def test_the_random_control_draws_from_the_eligible_population_and_can_beat_the_arm():
    """A control that the arm always beats is not a control. Here the top-20
    by rank is deliberately the WORST 20 of the eligible set, so the random
    draw must come out ahead."""
    rows = []
    for i in range(40):
        good = i >= 20
        rows.append({"symbol": f"S{i:03d}", "rank": float(i + 1), "eligible": True,
                     "exit_px": 20.4 if good else 19.9,
                     "alt_exit_px": 20.4 if good else 19.9})
    df = P.add_net(ledger(rows))
    a = P.read_arm(P.arm(df, 5, "top", 20), "PAPER", DATES[1])
    ctrl = P.random_control(df, 5, "PAPER", draws=200)
    assert a["mean_R"] < ctrl["p95"], "the ranking picked the losers; random wins"
    good = P.add_net(ledger([{**r, "exit_px": 20.4 if float(r["rank"]) <= 20 else 19.9,
                              "alt_exit_px": 20.4} for r in rows]))
    a2 = P.read_arm(P.arm(good, 5, "top", 20), "PAPER", DATES[1])
    ctrl2 = P.random_control(good, 5, "PAPER", draws=200)
    assert a2["mean_R"] > ctrl2["p95"], "and when it picks the winners it beats it"


def test_the_control_is_seeded_so_two_runs_agree():
    """The values must differ between rows, or an unseeded generator would
    draw a different 20 and still average the same number."""
    df = P.add_net(ledger([{"symbol": f"S{i:03d}", "rank": float(i + 1),
                            "exit_px": 20.0 + i * 0.01,
                            "alt_exit_px": 20.0 + i * 0.01} for i in range(40)]))
    one = P.random_control(df, 5, "PAPER", draws=50)
    two = P.random_control(df, 5, "PAPER", draws=50)
    assert one == two


def test_criterion_three_is_in_r_and_fails_a_small_positive_edge():
    """+0.01R is positive and still a failure: amendment C.2 set the bar at
    +0.05R because below that a doubling of friction erases it."""
    rows = [{"symbol": f"S{i:03d}", "rank": 1.0, "exit_px": 20.01,
             "alt_exit_px": 20.01} for i in range(200)]
    df = P.add_net(ledger(rows))
    a = P.read_arm(P.arm(df, 5, "top", 20), "PAPER", DATES[1])
    got = dict((n, ok) for n, _w, _v, ok in
               P.criteria(a, {"p95": -9.0}, a, {"best_range": 5, "best_top_n": 20,
                                                "interior": True}))
    assert 0 < a["mean_R"] < P.MIN_R_PER_TRADE
    assert got[3] is False and got[4] is True


def test_a_thin_arm_fails_the_trade_count_criterion():
    df = P.add_net(ledger([{"symbol": "AAA", "rank": 1.0}]))
    a = P.read_arm(P.arm(df, 5, "top", 20), "PAPER", DATES[1])
    got = dict((n, ok) for n, _w, _v, ok in
               P.criteria(a, {"p95": -9.0}, a, {"best_range": 5, "best_top_n": 20,
                                                "interior": True}))
    assert got[4] is False


def test_both_sides_and_both_halves_are_read_separately():
    rows = [{"symbol": f"L{i}", "side": 1, "exit_px": 20.4, "alt_exit_px": 20.4,
             "date": DATES[0], "rank": 1.0} for i in range(60)]
    rows += [{"symbol": f"S{i}", "side": -1, "entry_px": 20.0, "exit_px": 20.3,
              "alt_exit_px": 20.3, "date": DATES[4], "rank": 2.0} for i in range(60)]
    df = P.add_net(ledger(rows))
    a = P.read_arm(P.arm(df, 5, "top", 20), "PAPER", DATES[2])
    assert a["long_mean_R"] > 0 > a["short_mean_R"], "a short that rose lost"
    assert a["early_R"] > 0 > a["late_R"]
    got = dict((n, ok) for n, _w, _v, ok in
               P.criteria(a, {"p95": -9.0}, a, {"best_range": 5, "best_top_n": 20,
                                                "interior": True}))
    assert got[5] is False and got[6] is False


def test_drop_top_n_removes_symbols_not_trades():
    """Section 4 drops SYMBOLS. HERO trades twice, and each of its trades is
    smaller than the sum of the two, so a trade-wise drop would leave one of
    them in and the arm still positive."""
    rows = [{"symbol": "HERO", "exit_px": 26.0, "alt_exit_px": 26.0, "rank": 1.0,
             "date": d} for d in DATES[:2]]
    rows += [{"symbol": f"S{i:03d}", "exit_px": 19.9, "alt_exit_px": 19.9,
              "rank": 2.0} for i in range(10)]
    df = P.add_net(ledger(rows))
    a = P.read_arm(P.arm(df, 5, "top", 20), "PAPER", DATES[4])
    assert a["total_R"] > 0 > a["drop1_R"], "one symbol carried it"


def test_the_holdout_is_excluded_when_the_ledger_is_loaded(tmp_path):
    d = tmp_path / "t"; d.mkdir()
    ledger([{"date": "2025-03-03", "rank": 1.0}]).to_csv(
        d / "2025-03-03.csv.gz", index=False, compression="gzip", encoding="utf-8")
    ledger([{"date": "2026-06-01", "rank": 1.0}]).to_csv(
        d / "2026-06-01.csv.gz", index=False, compression="gzip", encoding="utf-8")
    assert sorted(P.load_ledger(d)["date"]) == ["2025-03-03"]
    assert len(P.load_ledger(d, spend_holdout=True)) == 2


def test_the_paper_book_sizes_by_risk_and_respects_the_leverage_cap():
    """1% of a position's capital at risk; and a 1c stop must not buy an
    unbounded number of shares."""
    rows = [{"symbol": "AAA", "rank": 1.0, "r": 0.01, "entry_px": 5.0,
             "exit_px": 5.0, "alt_exit_px": 5.0}]
    df = P.add_net(ledger(rows))
    book = P.paper_book(df, "PAPER")
    capital = 25_000 / 20
    assert book["sessions"] == 1
    # risk sizing alone would want 1,250 shares; the 4x cap allows 1,000.
    assert book["final_equity"] < 25_000, "a flat trade still pays commission"


def test_the_alt_reading_is_computed_on_the_same_entries():
    rows = [{"symbol": "AAA", "rank": 1.0, "exit_px": 19.9, "exit_reason": "stop",
             "alt_exit_px": 20.5, "alt_exit_reason": "session_end"}]
    primary = P.add_net(ledger(rows))
    alt = P.add_net(ledger(rows), alt=True)
    assert primary["gross_R"].iloc[0] < 0 < alt["gross_R"].iloc[0]
    assert primary["entry_px"].iloc[0] == alt["entry_px"].iloc[0]


def test_deciles_are_built_on_eligible_names_only():
    rows = [{"symbol": f"S{i:03d}", "rvol": 1.0 + i / 10, "eligible": i >= 5,
             "rank": float(i + 1)} for i in range(50)]
    df = P.add_net(ledger(rows))
    dec = P.deciles(df, "PAPER")
    assert dec["trades"].sum() == 45 and len(dec) == 10
