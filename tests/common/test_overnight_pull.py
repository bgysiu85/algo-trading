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


L1_SCHEMAS = {"trades", "tbbo", "bbo", "bbo-1s", "bbo-1m", "mbp-1",
              "cmbp-1", "cbbo", "tcbbo", "mbp-10", "mbo"}


def test_every_pair_job_is_bounded_by_a_start_date():
    """Scoped or not, a pair job with no --after walks back to whatever the
    pair list holds -- which is 2023-03-28, from EQUS.MINI."""
    for j in O.PAIR_JOBS:
        assert j.after, f"{j.label} has no --after -- it is unbounded"


def test_l1_pair_jobs_stay_inside_the_free_rolling_window():
    """L1 gets ONE ROLLING YEAR on Standard. An L1 pair job reaching back past
    that window silently starts charging, and at 12,128 candidate symbol-days a
    mis-set date is tens of dollars, not cents.

    Scoped to L1 deliberately. This test once asserted the 2025-09-01 bound on
    EVERY pair job, which was true only while every pair job happened to be L1.
    EQUS.SUMMARY statistics is L0 -- free back to the dataset's own start in
    2024-07-01 -- and holding it to the L1 window would have thrown away
    fourteen months of free history to satisfy a rule that does not apply."""
    for j in O.PAIR_JOBS:
        if j.schema in L1_SCHEMAS:
            assert j.after >= "2025-09-01", (
                f"{j.label} is L1 and reaches back past the rolling window")


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
    picked = O.select(O.JOBS, ["EQUS.MINI"], None)
    assert {j.schema for j in picked} == {"definition", "ohlcv-1m"}


def test_a_dataset_schema_pattern_separates_jobs_sharing_a_dataset():
    """EQUS.MINI carries a 3.6 GB definition job and a 49 GB minute job.
    Filtering by dataset alone cannot keep one and drop the other, which is the
    entire reason the colon form exists."""
    kept = O.select(O.JOBS, None, ["EQUS.MINI:ohlcv-1m"])
    labels = {f"{j.dataset}:{j.schema}" for j in kept}
    assert "EQUS.MINI:definition" in labels
    assert "EQUS.MINI:ohlcv-1m" not in labels
    assert len(kept) == len(O.JOBS) - 1


def test_patterns_are_case_insensitive():
    assert len(O.select(O.JOBS, None, ["equs.mini:OHLCV-1M"])) == len(O.JOBS) - 1


def test_a_pattern_that_matches_nothing_is_an_error_not_a_no_op():
    """A --skip is how someone excludes a job that would otherwise run for
    days. A typo in it must not read as 'nothing to exclude': that failure is
    silent, and its cost is the whole night and the whole download."""
    with pytest.raises(SystemExit, match="matched no job"):
        O.select(O.JOBS, None, ["EQUS.MINI:ohlcv-1min"])
    with pytest.raises(SystemExit, match="matched no job"):
        O.select(O.JOBS, ["EQUS.SUMARY"], None)


def test_skipping_a_deep_job_needs_it_to_be_in_scope():
    """--skip is evaluated against the jobs this run assembled. The statistics
    job lives in DEEP_JOBS, so skipping it without --deep is a typo as far as
    this run is concerned -- and saying so is better than silently accepting a
    flag that excludes nothing."""
    with pytest.raises(SystemExit, match="matched no job"):
        O.select(O.JOBS, None, ["EQUS.SUMMARY:statistics"])
    kept = O.select(list(O.JOBS) + list(O.DEEP_JOBS), None,
                    ["EQUS.SUMMARY:statistics"])
    assert not any(j.schema == "statistics" for j in kept)


def test_a_schema_pattern_does_not_leak_across_datasets():
    kept = O.select(O.JOBS, None, ["EQUS.MINI:ohlcv-1m"])
    assert any(j.dataset == "EQUS.SUMMARY" for j in kept)
    assert not any(j.dataset == "EQUS.MINI" and j.schema == "ohlcv-1m"
                   for j in kept)


def test_only_and_skip_compose():
    kept = O.select(O.JOBS, ["EQUS.MINI"], ["EQUS.MINI:ohlcv-1m"])
    assert [f"{j.dataset}:{j.schema}" for j in kept] == ["EQUS.MINI:definition"]


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


def test_the_deep_flag_describes_every_job_it_gates():
    """--deep gated one job when it was written and gates two now. Help text
    that names only the first is how someone opts into 2.4 TB believing they
    asked for minute bars."""
    import argparse, io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with pytest.raises(SystemExit):
            O.main(["--help"])
    help_text = " ".join(buf.getvalue().split())
    for j in O.DEEP_JOBS:
        assert f"{j.dataset}:{j.schema}" in help_text, (
            f"--deep pulls {j.label} but its help text never names it")


def test_a_pair_jobs_lookback_reaches_the_fetcher(monkeypatch):
    """databento_fetch defaults to a 5-day lookback, so each request spans six
    days. Right for quotes; wrong for a schema whose content is one session's
    running total, where it multiplies the pull sixfold for nothing."""
    import common
    seen = {}

    class Spy:
        @staticmethod
        def main(argv):
            seen["argv"] = argv
            return 0

    monkeypatch.setattr(common, "databento_fetch", Spy, raising=False)
    job = O.PairJob("EQUS.SUMMARY", "statistics", "p.json", "2024-07-01",
                    "x" * 50, lookback=0)
    O._run(job, "databento", confirm=False, max_cost=5.0)
    assert "--lookback" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--lookback") + 1] == "0"


def test_a_pair_job_without_a_lookback_leaves_the_fetchers_default_alone():
    """Only the jobs that need a different window say so. The quote job has
    been pulled already at the default and must not silently change."""
    quotes = [j for j in O.PAIR_JOBS if j.schema == "tbbo"]
    assert quotes and all(j.lookback is None for j in quotes)


def test_the_statistics_pair_job_starts_no_earlier_than_its_dataset():
    """EQUS.SUMMARY begins 2024-07-01. The screened pair list reaches back to
    2023-03-28 from EQUS.MINI, and every request before the dataset's start
    would fail -- hundreds of them, overnight, unattended."""
    for j in O.PAIR_JOBS:
        if j.dataset == "EQUS.SUMMARY":
            assert j.after and j.after >= "2024-07-01", (
                f"{j.label} reaches back before EQUS.SUMMARY exists")


# --- counting what was written ----------------------------------------------

def test_both_runners_success_wordings_are_counted():
    """databento_universe says 'wrote N chunk(s)', databento_fetch says
    'wrote N file(s)'. The original pattern matched only the first, so both
    pair jobs reported 0 after writing 548 and 125 files respectively."""
    assert O._written("wrote 548 file(s) to E:/Databento/") == 548
    assert O._written("wrote 43 chunk(s)") == 43


def test_an_unparsed_count_is_none_and_renders_as_a_question_mark():
    """None is deliberately not 0. A count that could not be parsed is a
    MISSING measurement, and printing a missing measurement as a number is how
    a successful run comes to look like an empty one -- '0 chunk(s) ok' reads
    as 'ran fine, had nothing to do', which is a conclusion, and it was wrong."""
    assert O._written("finished, no idea how many") is None
    assert O._count(None) == "?"
    assert O._count(0) == "0"
    assert O._count(1234) == "1,234"
