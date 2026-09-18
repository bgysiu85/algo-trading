"""Amendment E's recombination: every branch, and a mutation for each."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.orb import sip_entrybar as E
from strategy.orb import sip_resolved as R


def _trade(symbol, date, rank=1, rng=5, exit_reason="stop", entry_min=600,
           exit_min=600, exit_px=99.0, alt_exit_min=640, alt_exit_px=104.0,
           alt_exit_reason="close"):
    return {"date": date, "symbol": symbol, "range": rng, "side": 1,
            "rvol": 2.0, "rank": float(rank), "eligible": True, "atr": 10.0,
            "entry_min": entry_min, "entry_px": 100.0, "exit_min": exit_min,
            "exit_px": exit_px, "exit_reason": exit_reason, "r": 1.0,
            "bars_held": exit_min - entry_min, "gapped_entry": False,
            "or_high": 100.0, "or_low": 98.0, "alt_exit_min": alt_exit_min,
            "alt_exit_px": alt_exit_px, "alt_exit_reason": alt_exit_reason}


@pytest.fixture
def ledger():
    return pd.DataFrame([
        _trade("AAA", "2025-01-02"),                       # in scope
        _trade("BBB", "2025-01-02"),                       # in scope
        _trade("CCC", "2025-01-02"),                       # in scope
        _trade("DDD", "2025-01-02", rank=25),              # rank out of scope
        _trade("EEE", "2025-01-02", rng=15),               # range out of scope
        _trade("FFF", "2025-01-02", exit_reason="close"),  # not a stop
        _trade("GGG", "2025-01-02", exit_min=640),         # not the entry min
    ])


@pytest.fixture
def verdicts():
    return pd.DataFrame([
        {"symbol": "AAA", "date": "2025-01-02", "verdict": E.AFTER},
        {"symbol": "BBB", "date": "2025-01-02", "verdict": E.BEFORE},
        {"symbol": "CCC", "date": "2025-01-02", "verdict": E.SAME},
    ])


def test_in_scope_picks_only_the_primary_cell_entry_minute_stops(ledger):
    got = set(ledger.loc[R.in_scope(ledger), "symbol"])
    assert got == {"AAA", "BBB", "CCC"}


def test_entry_first_keeps_the_stop(ledger, verdicts):
    out = R.apply_verdicts(ledger, verdicts)
    row = out[out["symbol"] == "AAA"].iloc[0]
    assert row["exit_px"] == 99.0
    assert row["exit_reason"] == "stop"
    assert row["exit_min"] == 600


def test_stop_first_takes_the_alternative_path(ledger, verdicts):
    out = R.apply_verdicts(ledger, verdicts)
    row = out[out["symbol"] == "BBB"].iloc[0]
    assert row["exit_px"] == 104.0
    assert row["exit_reason"] == "close"
    assert row["exit_min"] == 640
    assert row["bars_held"] == 40


def test_same_second_keeps_the_stop_because_E2_says_conservative(ledger, verdicts):
    out = R.apply_verdicts(ledger, verdicts)
    row = out[out["symbol"] == "CCC"].iloc[0]
    assert row["exit_px"] == 99.0
    assert row["exit_reason"] == "stop"


def test_the_band_moves_same_second_and_nothing_else(ledger, verdicts):
    base = R.apply_verdicts(ledger, verdicts)
    band = R.apply_verdicts(ledger, verdicts, same_takes_alt=True)
    moved = band["symbol"][band["exit_px"].to_numpy() != base["exit_px"].to_numpy()]
    assert set(moved) == {"CCC"}


def test_rows_outside_scope_are_untouched_and_unlabelled(ledger, verdicts):
    out = R.apply_verdicts(ledger, verdicts)
    outside = out[~R.in_scope(ledger)]
    assert (outside["resolution"] == "").all()
    assert (outside["exit_px"] == 99.0).all()


def test_a_scoped_trade_with_no_verdict_is_refused(ledger, verdicts):
    with pytest.raises(ValueError, match="no verdict"):
        R.apply_verdicts(ledger, verdicts.iloc[:2])


def test_a_verdict_matching_no_scoped_trade_is_refused(ledger, verdicts):
    extra = pd.concat([verdicts, pd.DataFrame(
        [{"symbol": "ZZZ", "date": "2025-01-02", "verdict": E.AFTER}])])
    with pytest.raises(ValueError, match="no scoped trade"):
        R.apply_verdicts(ledger, extra)


def test_a_duplicate_verdict_is_refused(ledger, verdicts):
    dup = pd.concat([verdicts, verdicts.iloc[:1]])
    with pytest.raises(ValueError, match="duplicate symbol-days in verdicts"):
        R.apply_verdicts(ledger, dup)


def test_an_unknown_verdict_string_is_refused(ledger, verdicts):
    bad = verdicts.copy()
    bad.loc[0, "verdict"] = "maybe"
    with pytest.raises(ValueError, match="unknown verdict"):
        R.apply_verdicts(ledger, bad)


def test_counts_report_shares_against_the_right_denominators(ledger, verdicts):
    c = R.counts(ledger, verdicts)
    # rank<=20 and range 5: AAA BBB CCC FFF GGG. DDD is rank 25, EEE is 15-min.
    assert c["primary_trades"] == 5
    assert c["scoped"] == 3
    assert c["entry_first"] == 1
    assert c["stop_first"] == 1
    assert c["same_second"] == 1
    assert c["same_share"] == pytest.approx(1 / 3)
    assert c["scoped_share"] == pytest.approx(3 / 5)


def test_the_twenty_percent_gate_is_a_strict_greater_than():
    led = pd.DataFrame([_trade(f"S{i:02d}", "2025-01-02") for i in range(10)])
    v = pd.DataFrame([{"symbol": f"S{i:02d}", "date": "2025-01-02",
                       "verdict": E.SAME if i < 2 else E.AFTER}
                      for i in range(10)])
    assert R.counts(led, v)["same_share"] == pytest.approx(0.20)
    assert R.counts(led, v)["unresolved_over_gate"] is False


def test_the_gate_trips_above_twenty_percent():
    led = pd.DataFrame([_trade(f"S{i:02d}", "2025-01-02") for i in range(10)])
    v = pd.DataFrame([{"symbol": f"S{i:02d}", "date": "2025-01-02",
                       "verdict": E.SAME if i < 3 else E.AFTER}
                      for i in range(10)])
    assert R.counts(led, v)["unresolved_over_gate"] is True


def test_the_original_ledger_is_not_mutated(ledger, verdicts):
    before = ledger.copy(deep=True)
    R.apply_verdicts(ledger, verdicts)
    pd.testing.assert_frame_equal(ledger, before)


def _pair(reg_R, res_R, symbol="AAA"):
    reg = pd.DataFrame({"R_BASE": reg_R, "symbol": symbol})
    res = pd.DataFrame({"R_BASE": res_R, "symbol": symbol})
    return reg, res


def test_movers_separates_trades_that_died_anyway_from_real_changes():
    # A, B freed and unchanged; C freed and changed; D NOT freed but changed
    # anyway (which must not be counted); E untouched.
    reg, res = _pair([-1.0, -1.0, -1.0, -1.0, +0.5],
                     [-1.0, -1.0, +9.0, +4.0, +0.5], list("ABCDE"))
    lab = np.array([E.BEFORE, E.BEFORE, E.BEFORE, E.AFTER, ""])
    m = R.movers(reg, res, lab, "BASE")
    assert m["freed"] == 3               # A, B, C
    assert m["died_anyway"] == 2         # A, B: same exit either way
    assert m["changed"] == 1             # C only -- D is not freed
    assert m["mean_move"] == pytest.approx(10.0)
    assert m["max_R"] == pytest.approx(9.0)
    assert m["median_R"] == pytest.approx(9.0)


def test_movers_total_added_counts_every_row_not_just_freed_ones():
    # B is not freed, so it is not a "mover", but its delta is still part of
    # what the resolved book gained over the registered one.
    reg, res = _pair([-1.0, -1.0], [+1.0, +2.0], ["A", "B"])
    m = R.movers(reg, res, np.array([E.BEFORE, E.AFTER]), "BASE")
    assert m["changed"] == 1
    assert m["total_added"] == pytest.approx(5.0)


def test_movers_drop_ladder_is_by_symbol_total_descending():
    reg = pd.DataFrame({"R_BASE": [0.0] * 4, "symbol": list("ABCD")})
    res = pd.DataFrame({"R_BASE": [10.0, 5.0, 1.0, -4.0], "symbol": list("ABCD")})
    m = R.movers(reg, res, np.array([""] * 4), "BASE")
    assert m["total_R"] == pytest.approx(12.0)
    assert m["drop"][1] == pytest.approx(2.0)    # less A
    assert m["drop"][3] == pytest.approx(-4.0)   # less A, B, C
    assert [s for s, _ in m["top5"]] == ["A", "B", "C", "D"]


def test_movers_handles_nothing_changing():
    reg, res = _pair([-1.0, -1.0], [-1.0, -1.0], ["A", "B"])
    m = R.movers(reg, res, np.array([E.BEFORE, E.AFTER]), "BASE")
    assert m["changed"] == 0
    assert m["mean_move"] == 0.0
    assert m["max_R"] == 0.0
