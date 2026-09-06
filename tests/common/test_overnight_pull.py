#!/usr/bin/env python3
"""Guards on a job that runs for hours with nobody watching.

Every test here pins something whose failure mode is discovered at 7am rather
than at 11pm: a job that stops the run, a disk that fills, a total that was
never checked.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from common import overnight_pull as O


SAMPLE = """
EQUS.MINI  ohlcv-1m  2023-03-28 -> 2026-09-04   43 monthly chunk(s)

already on disk, skipped : 1
to download              : 42
ESTIMATED SIZE           : 44,612.9 MB
ESTIMATED COST           : $0.0000
"""


def test_the_estimate_is_parsed_including_thousands_separators():
    """The size line is formatted with commas. A parser that chokes on them
    silently returns 0 MB, the disk check then passes trivially, and the run
    fills the drive at 3am."""
    mb, usd, todo = O._parse(SAMPLE)
    assert mb == pytest.approx(44_612.9)
    assert usd == 0.0
    assert todo == 42


def test_output_with_no_estimate_lines_yields_zeroes_not_an_exception():
    """A job that failed to plan must not take the whole run down with an
    AttributeError on a missing regex match."""
    assert O._parse("something went wrong") == (0.0, 0.0, 0)


def test_free_space_is_measured_on_an_ancestor_that_exists(tmp_path):
    """The archive directory does not exist before the first run. Calling
    disk_usage on a missing path raises, and the check would be skipped by
    exception rather than by decision."""
    missing = tmp_path / "databento" / "EQUS.MINI" / "ohlcv-1m"
    assert not missing.exists()
    assert O._free_gb(missing) > 0


def test_pair_jobs_stay_inside_the_free_l1_window():
    """L1 gets ONE ROLLING YEAR on Standard. A pair job without an --after
    reaching back past that window silently starts charging, and at 12,128
    candidate symbol-days a mis-set date is tens of dollars, not cents."""
    for j in O.PAIR_JOBS:
        assert j.after, f"{j.label} has no --after -- it would buy paid history"
        assert j.after >= "2025-09-01", (
            f"{j.label} reaches back past the rolling L1 window")


def test_l1_is_never_pulled_universe_wide():
    """tbbo for one year of all US equities is roughly 4.5 TB. L1 is only ever
    taken scoped to a pair list; if an L1 schema ever appears in JOBS, the
    overnight run stops being something anyone can leave alone."""
    l1 = {"trades", "tbbo", "bbo", "bbo-1s", "bbo-1m", "mbp-1",
          "cmbp-1", "cbbo", "tcbbo", "mbp-10", "mbo"}
    for j in O.JOBS + O.DEEP_JOBS:
        assert j.schema not in l1, f"{j.label} takes {j.schema} universe-wide"


def test_every_job_is_l0():
    """L0 -- ohlcv, definitions, statistics, status -- is the tier Standard
    grants 8+ years of and charges nothing for. L1 gets one rolling year and
    L2/L3 one month, so a full-universe pull of either would be enormous, most
    of it outside the plan, and none of it free. If a non-L0 schema ever
    appears in this list, the overnight run stops being safe to leave alone."""
    l0 = {"ohlcv-1s", "ohlcv-1m", "ohlcv-1h", "ohlcv-1d",
          "definition", "statistics", "status"}
    for j in O.JOBS + O.DEEP_JOBS:
        assert j.schema in l0, f"{j.label} is not L0 -- it is not free or bounded"


def test_every_job_states_why_it_is_worth_pulling():
    """A job list nobody can justify is a job list that grows. Each entry
    carries its reason, and the planning pass prints it."""
    for j in O.JOBS + O.PAIR_JOBS + O.DEEP_JOBS:
        assert len(j.why) > 40, f"{j.label} has no real justification"


def test_the_biggest_job_runs_last():
    """Ordered cheapest-and-most-useful first, so a run that dies partway has
    still delivered what the next step of the plan needs. The full-universe
    minute pull is the one that could run for hours."""
    assert O.JOBS[-1].schema == "ohlcv-1m"
    assert O.JOBS[-1].dataset == "EQUS.MINI"


# --- selecting which jobs run -----------------------------------------------

def test_a_dataset_pattern_takes_every_schema_under_it():
    picked = O.select(O.JOBS, ["EQUS.SUMMARY"], None)
    assert {j.schema for j in picked} == {"ohlcv-1d", "statistics"}


def test_a_dataset_schema_pattern_separates_jobs_sharing_a_dataset():
    """EQUS.SUMMARY carries a 362 MB daily job and a statistics job estimated
    at 2.4 TB. Filtering by dataset alone cannot keep one and drop the other,
    which is the entire reason the colon form exists."""
    kept = O.select(O.JOBS, None, ["EQUS.SUMMARY:statistics"])
    labels = {f"{j.dataset}:{j.schema}" for j in kept}
    assert "EQUS.SUMMARY:ohlcv-1d" in labels
    assert "EQUS.SUMMARY:statistics" not in labels
    assert len(kept) == len(O.JOBS) - 1


def test_patterns_are_case_insensitive():
    assert len(O.select(O.JOBS, None, ["equs.summary:STATISTICS"])) == len(O.JOBS) - 1


def test_a_pattern_that_matches_nothing_is_an_error_not_a_no_op():
    """A --skip is how someone excludes the one job that would otherwise run
    for days. A typo in it must not read as 'nothing to exclude': that failure
    is silent, and its cost is the whole night and the whole download."""
    with pytest.raises(SystemExit, match="matched no job"):
        O.select(O.JOBS, None, ["EQUS.SUMMARY:statistcs"])   # transposed
    with pytest.raises(SystemExit, match="matched no job"):
        O.select(O.JOBS, ["EQUS.SUMARY"], None)


def test_a_schema_pattern_does_not_leak_across_datasets():
    kept = O.select(O.JOBS, None, ["EQUS.MINI:ohlcv-1m"])
    assert any(j.dataset == "EQUS.SUMMARY" for j in kept)
    assert not any(j.dataset == "EQUS.MINI" and j.schema == "ohlcv-1m"
                   for j in kept)


def test_only_and_skip_compose():
    kept = O.select(O.JOBS, ["EQUS.SUMMARY"], ["EQUS.SUMMARY:statistics"])
    assert [f"{j.dataset}:{j.schema}" for j in kept] == ["EQUS.SUMMARY:ohlcv-1d"]


def test_pair_jobs_can_be_selected_the_same_way():
    """PairJob is a different dataclass to Job. The matcher reads .dataset and
    .schema off both, so a pattern must reach the quote jobs too."""
    kept = O.select(list(O.JOBS) + list(O.PAIR_JOBS), None, ["EQUS.MINI:tbbo"])
    assert not any(j.schema == "tbbo" for j in kept)


def test_a_failing_job_does_not_raise_out_of_run(monkeypatch):
    """One dataset being unavailable at 2am must not cost the other five.

    Patched on the PACKAGE, not in sys.modules. `_run` does
    `from common import databento_universe`, which reads the attribute on the
    already-imported `common` package -- so a sys.modules patch works only
    while nothing else has imported that module yet. This test passed alone and
    failed in the full suite for exactly that reason.
    """
    import common

    class Boom:
        @staticmethod
        def main(argv):
            raise RuntimeError("503 upstream")

    monkeypatch.setattr(common, "databento_universe", Boom, raising=False)
    rc, out = O._run(O.JOBS[0], "databento", confirm=False, max_cost=5.0)
    assert rc == 1
    assert "JOB FAILED" in out


def test_a_max_cost_abort_is_caught_as_a_failed_job_not_a_crash(monkeypatch):
    """databento_universe sys.exit()s when the estimate exceeds --max-cost.
    That is the guard working, and it must fail one job rather than the run."""
    import common

    class Abort:
        @staticmethod
        def main(argv):
            raise SystemExit("ABORTED: $9.00 exceeds --max-cost $5.00")

    monkeypatch.setattr(common, "databento_universe", Abort, raising=False)
    rc, _ = O._run(O.JOBS[0], "databento", confirm=False, max_cost=5.0)
    assert rc != 0


def test_job_output_streams_rather_than_being_held_to_the_end(capsys):
    """A job that makes ~500 metadata calls must show progress while it runs.

    Buffering to a StringIO and printing on return meant a job sat silent for
    minutes, which on an unattended overnight run is indistinguishable from a
    hang. The tee writes through as each line is produced.
    """
    import common

    class Chatty:
        @staticmethod
        def main(argv):
            print("  2023-03      2.0 MB   $ 0.0000")
            return 0

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(common, "databento_universe", Chatty, raising=False)
    try:
        rc, out = O._run(O.JOBS[0], "databento", confirm=False, max_cost=5.0)
    finally:
        monkeypatch.undo()

    assert rc == 0
    assert "2023-03" in out                       # captured for parsing
    assert "2023-03" in capsys.readouterr().out   # and seen by the terminal
