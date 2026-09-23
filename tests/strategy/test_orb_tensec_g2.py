"""Mutation-checked tests for tensec_g2.py's redesigned criteria (c)/(d)/(e)
(W12-0005, 2026-09-23 -- see docs/research/REGISTERED_10sec.md section 0.1).

These are pure-logic tests on synthetic data: no Databento, no archive, no
network. They exist because the original criterion (c) -- mean net R against
a headline "figure of record" -- was retired after that figure turned out to
be wrong; the replacement depends only on ground truth and the trades
themselves, so it can and must be tested without any real market data.
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.orb import tensec_g2 as G


def test_classify_reason_diff_splits_on_entry_price_match():
    reason_diff = pd.DataFrame({
        "symbol": ["AAA", "BBB", "CCC"],
        "date": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "sec_entry_px": [10.00, 20.05, 30.00],
        "ledger_entry_px": [10.00, 20.00, 30.10],
    })
    tie, gap = G.classify_reason_diff(reason_diff)
    assert list(tie["symbol"]) == ["AAA"]
    assert list(gap["symbol"]) == ["BBB", "CCC"]


def _ground_truth():
    return pd.DataFrame({
        "symbol": ["AAA", "BBB", "EEE"],
        "date": ["2025-01-01", "2025-01-02", "2025-01-05"],
        "sec_entry_px": [10.00, 20.05, 50.00],
        "sec_exit_px": [10.50, 19.90, 50.50],
    })


def test_ground_truth_perfect_match_scores_full_rate_and_partial_coverage():
    scored = pd.DataFrame({
        "symbol": ["AAA", "BBB", "DDD"],
        "date": ["2025-01-01", "2025-01-02", "2025-01-04"],
        "sec_entry_px": [10.00, 20.05, 40.00],
        "sec_exit_px": [10.50, 19.90, 39.50],
    })
    sc = G.score_ground_truth(scored, _ground_truth())
    assert sc["n"] == 2                       # AAA, BBB found; DDD is not in ground truth
    assert sc["rate"] == 1.0                  # both found trades match exactly
    assert sc["coverage"] == pytest.approx(2 / 3)   # EEE is in ground truth but not in `scored`


def test_ground_truth_catches_a_single_mismatch():
    scored = pd.DataFrame({
        "symbol": ["AAA", "BBB"],
        "date": ["2025-01-01", "2025-01-02"],
        "sec_entry_px": [10.00, 20.05],
        "sec_exit_px": [10.50, 99.0],          # BBB's exit is wrong
    })
    sc = G.score_ground_truth(scored, _ground_truth())
    assert sc["rate"] == 0.5
    assert list(sc["mismatches"]["symbol"]) == ["BBB"]


def test_ground_truth_empty_never_fails_the_gate():
    scored = pd.DataFrame({"symbol": [], "date": [], "sec_entry_px": [], "sec_exit_px": []})
    empty_gt = pd.DataFrame(columns=["symbol", "date", "sec_entry_px", "sec_exit_px"])
    sc = G.score_ground_truth(scored, empty_gt)
    assert sc["rate"] == 1.0 and sc["coverage"] == 1.0


def test_ground_truth_nan_exit_is_not_applicable_not_a_fail():
    """`stop_first` ground-truth rows carry no resolved exit (2026-09-23 fix):
    a NaN there must not force a fail when the entry matches -- the bug that
    turned 1,602 intentionally-unresolved rows into a manufactured failure."""
    scored = pd.DataFrame({
        "symbol": ["AAA", "BBB"],
        "date": ["2025-01-01", "2025-01-02"],
        "sec_entry_px": [10.00, 20.00],
        "sec_exit_px": [10.50, 21.00],   # BBB's exit -- ground truth has no answer for it
    })
    ground_truth = pd.DataFrame({
        "symbol": ["AAA", "BBB"],
        "date": ["2025-01-01", "2025-01-02"],
        "sec_entry_px": [10.00, 20.00],
        "sec_exit_px": [10.50, float("nan")],   # BBB is `stop_first`: unresolved by design
    })
    sc = G.score_ground_truth(scored, ground_truth)
    assert sc["rate"] == 1.0            # both count as OK -- entry matches, exit n/a for BBB
    assert sc["exit_checked"] == 1      # only AAA's exit was actually checkable
    assert len(sc["mismatches"]) == 0


def test_ground_truth_nan_exit_still_catches_a_real_entry_mismatch():
    scored = pd.DataFrame({
        "symbol": ["BBB"], "date": ["2025-01-02"],
        "sec_entry_px": [99.0],             # wrong -- ground truth says 20.00
        "sec_exit_px": [21.00],
    })
    ground_truth = pd.DataFrame({
        "symbol": ["BBB"], "date": ["2025-01-02"],
        "sec_entry_px": [20.00], "sec_exit_px": [float("nan")],
    })
    sc = G.score_ground_truth(scored, ground_truth)
    assert sc["rate"] == 0.0            # entry mismatch still fails, NaN exit or not
    assert len(sc["mismatches"]) == 1


def test_find_gap_population_excludes_ground_truth_and_matches():
    scored = pd.DataFrame({
        "symbol": ["AAA", "BBB", "CCC", "DDD"],
        "date": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
        "sec_entry_px": [10.00, 20.05, 30.20, 40.00],
        "ledger_entry_px": [10.00, 20.00, 30.00, 40.00],   # AAA, DDD match; BBB, CCC don't
    })
    ground_truth = pd.DataFrame({
        "symbol": ["BBB"], "date": ["2025-01-02"],          # BBB is explained by ground truth
        "sec_entry_px": [20.05], "sec_exit_px": [1.0],
    })
    gap = G.find_gap_population(scored, ground_truth)
    # only CCC: entry mismatches AND not covered by ground truth
    assert list(gap["symbol"]) == ["CCC"]


def test_find_gap_population_empty_ground_truth():
    scored = pd.DataFrame({
        "symbol": ["AAA", "BBB"], "date": ["2025-01-01", "2025-01-02"],
        "sec_entry_px": [10.00, 20.05], "ledger_entry_px": [10.00, 20.00],
    })
    empty_gt = pd.DataFrame(columns=["symbol", "date", "sec_entry_px", "sec_exit_px"])
    gap = G.find_gap_population(scored, empty_gt)
    assert list(gap["symbol"]) == ["BBB"]


def test_is_bad_tick_flags_spike_that_reverts_on_thin_volume():
    row = pd.Series({
        "sec_entry_px": 100.20, "sec_entry_px_baseline": 100.00,
        "sec_entry_px_revert": 100.01, "sec_entry_volume": 2.0,
        "sec_entry_vol_baseline": 50.0,
    })
    assert G.is_bad_tick(row) is True


def test_is_bad_tick_does_not_flag_a_real_sustained_move():
    row = pd.Series({
        "sec_entry_px": 100.20, "sec_entry_px_baseline": 100.00,
        "sec_entry_px_revert": 100.19, "sec_entry_volume": 300.0,
        "sec_entry_vol_baseline": 50.0,
    })
    assert G.is_bad_tick(row) is False


def test_is_bad_tick_does_not_flag_thin_volume_alone_without_reversion():
    # thin, but the price never reverts -- a real, if small, move
    row = pd.Series({
        "sec_entry_px": 100.20, "sec_entry_px_baseline": 100.00,
        "sec_entry_px_revert": 100.19, "sec_entry_volume": 2.0,
        "sec_entry_vol_baseline": 50.0,
    })
    assert G.is_bad_tick(row) is False


def test_is_bad_tick_never_flags_on_missing_context():
    row = pd.Series({
        "sec_entry_px": 100.20, "sec_entry_px_baseline": float("nan"),
        "sec_entry_px_revert": float("nan"), "sec_entry_volume": 2.0,
        "sec_entry_vol_baseline": 50.0,
    })
    assert G.is_bad_tick(row) is False


def test_score_gap_bucket_allowlist_and_unreviewed():
    spike = {"sec_entry_px": 100.20, "sec_entry_px_baseline": 100.00,
             "sec_entry_px_revert": 100.01, "sec_entry_volume": 2.0,
             "sec_entry_vol_baseline": 50.0}
    clean = {"sec_entry_px": 100.20, "sec_entry_px_baseline": 100.00,
             "sec_entry_px_revert": 100.19, "sec_entry_volume": 300.0,
             "sec_entry_vol_baseline": 50.0}
    gap = pd.DataFrame([
        {"symbol": "PPG", "date": "2025-04-09", **spike},   # flagged, on the allowlist
        {"symbol": "ZZZ", "date": "2025-06-01", **spike},   # flagged, NOT on the allowlist
        {"symbol": "QQQ", "date": "2025-06-02", **clean},   # never flagged
    ])
    sc = G.score_gap_bucket(gap, G.BADTICK_REVIEWED)
    assert sc["flagged"] == 2
    assert sc["unreviewed"] == 1
    assert sc["clean"] is False
    assert list(sc["rows"]["symbol"]) == ["ZZZ"]


def test_score_gap_bucket_empty_is_clean():
    empty = pd.DataFrame(columns=["symbol", "date", "sec_entry_px", "sec_entry_px_baseline",
                                   "sec_entry_px_revert", "sec_entry_volume",
                                   "sec_entry_vol_baseline"])
    sc = G.score_gap_bucket(empty, G.BADTICK_REVIEWED)
    assert sc["clean"] is True


def test_score_criterion_e_a_ground_truth_row_is_covered_by_c_not_d():
    """Regression for the 2026-09-23 criterion (e) bug: `classify_reason_diff`'s
    tie/gap split is partitioned by whether the entry price matches the
    LEDGER, but (c)'s and (d)'s coverage sets are partitioned by ground-truth
    MEMBERSHIP -- the two partitions don't line up. A real case (IBM,
    2024-07-25, found in the live rescore): entry price disagrees with the
    ledger (189.38 vs 189.30, so `classify_reason_diff` calls it "gap"), but
    the trade IS a ground-truth row, so it's covered by (c) and should never
    be forced through (d)'s bad-tick screen -- with no baseline/volume
    context at all here, the old code's `gap_covered` check would have
    failed the gate outright."""
    row = dict(
        symbol="IBM", date="2024-07-25", side=1, why=G.E.OK,
        ledger_entry_px=189.30, ledger_exit_px=185.00, ledger_exit_reason="stop",
        ledger_gapped_entry=False, ledger_r=-1.0, ledger_or_high=190.0, ledger_or_low=188.0,
        sec_entry_px=189.38, sec_exit_px=187.19, sec_exit_reason="session_end",
        sec_entry_sec=34200, sec_exit_sec=57600,
        sec_entry_volume=float("nan"), sec_entry_vol_baseline=float("nan"),
        sec_entry_px_baseline=float("nan"), sec_entry_px_revert=float("nan"),
    )
    res = pd.DataFrame([row])
    ground_truth = pd.DataFrame({
        "symbol": ["IBM"], "date": ["2024-07-25"], "verdict": ["stop_first"],
        "sec_entry_px": [189.38], "sec_exit_px": [float("nan")],
    })
    sc = G.score(res, ground_truth)
    assert sc["gate_c"] is True          # entry matches gt exactly, exit n/a
    assert sc["gap"]["n"] == 0           # excluded from (d)'s population -- it's a gt row
    assert sc["gate_d"] is True
    assert len(sc["unexplained"]) == 0
    assert sc["gate_e"] is True          # covered by (c), never asked to clear (d)'s screen
