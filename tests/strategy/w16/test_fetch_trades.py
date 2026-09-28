"""strategy.w16.fetch_trades -- the spending guards and day-window logic,
pinned (W16-0009 subitem 1). Modelled on tests/strategy/w16/test_fetch.py.

A fake client stands in for databento, so these tests never reach the
vendor and never need the key.
"""
from __future__ import annotations

import json

import pytest

from strategy.w16 import fetch_trades as F


class _Data:
    def __init__(self, log):
        self.log = log

    def to_file(self, path):
        self.log.append(("to_file", str(path)))
        with open(path, "wb") as fh:
            fh.write(b"DBN-fake")


class _Meta:
    def __init__(self, cost, log, no_session=(), dataset_end="2026-09-26T00:00:00Z",
                 partial_day=None, partial_end=None):
        self.cost, self.log, self.no_session = cost, log, set(no_session)
        self.dataset_end = dataset_end
        self.partial_day, self.partial_end = partial_day, partial_end

    def get_dataset_range(self, dataset):
        self.log.append(("range", dataset))
        end = self.partial_end or self.dataset_end
        return {"start": "2010-06-06T00:00:00Z", "end": end}

    def get_cost(self, **kw):
        day = kw["start"][:10]
        self.log.append(("cost", kw))
        if day in self.no_session:
            raise RuntimeError(
                "422 symbology_invalid_request -- None of the symbols "
                "could be resolved")
        if self.partial_day and day == self.partial_day and kw["end"] > self.partial_end:
            raise RuntimeError(
                "422 data_end_after_available_end\nThe dataset GLBX.MDP3 has "
                f"data available up to '{self.partial_end[:10]} "
                f"{self.partial_end[11:19]}+00:00'. The `end` in the query "
                f"('{kw['end'][:10]} {kw['end'][11:19]}+00:00') is after the "
                "available range. Try requesting with an earlier `end`.")
        return self.cost

    def get_billable_size(self, **kw):
        return 1_000_000


class _TS:
    def __init__(self, log):
        self.log = log

    def get_range(self, **kw):
        self.log.append(("get_range", kw))
        return _Data(self.log)


class FakeClient:
    def __init__(self, cost=1.0, no_session=(), dataset_end="2026-09-26T00:00:00Z",
                 partial_day=None, partial_end=None):
        self.log = []
        self.metadata = _Meta(cost, self.log, no_session, dataset_end,
                              partial_day, partial_end)
        self.timeseries = _TS(self.log)

    def calls(self, name):
        return [c for c in self.log if c[0] == name]


WEEK = ["--archive", None, "--start", "2026-09-07", "--end", "2026-09-13"]
# 2026-09-07 Mon .. 2026-09-13 Sun: 7 calendar days, one Saturday (09-12)
# excluded by trading_days() -> 6 requested days.


def _week_argv(tmp_path, *extra):
    argv = ["--archive", str(tmp_path), "--start", "2026-09-07",
            "--end", "2026-09-13"]
    return argv + list(extra)


def test_trading_days_excludes_saturday_only():
    days = F.trading_days("2026-09-07", "2026-09-13")
    assert days == ["2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10",
                    "2026-09-11", "2026-09-13"]
    assert "2026-09-12" not in days               # the Saturday


def test_default_window_is_365_days_ending_at_end():
    assert F.default_window("2026-09-26") == "2025-09-27"
    assert F.WINDOW_DAYS == 365


def test_estimate_only_never_downloads(tmp_path):
    c = FakeClient()
    assert F.main(_week_argv(tmp_path), client=c) == 0
    assert c.calls("cost"), "it must price"
    assert not c.calls("get_range"), "no --confirm means no download"
    assert not any(F.day_path(tmp_path, d).exists()
                   for d in F.trading_days("2026-09-07", "2026-09-13"))


def test_confirm_downloads_all_six_days_and_writes_manifest(tmp_path):
    c = FakeClient(cost=0.5)
    assert F.main(_week_argv(tmp_path, "--confirm"), client=c) == 0
    assert len(c.calls("get_range")) == 6
    for d in F.trading_days("2026-09-07", "2026-09-13"):
        p = F.day_path(tmp_path, d)
        assert p.exists() and p.read_bytes() == b"DBN-fake"
        assert not p.with_name(p.name + ".part").exists()
    m = json.loads(F.manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert set(m["symbols"]) == {"ES.v.0", "NQ.v.0"}
    assert m["schema"] == "trades"
    assert m["start"] == "2026-09-07" and m["end"] == "2026-09-13"
    assert m["board"] == "W16-0009"
    assert len(m["files_pulled"]) == 6
    assert m["no_session"] == []


def test_over_max_cost_aborts_even_with_confirm(tmp_path):
    c = FakeClient(cost=10.0)  # 6 days x $10 = $60 > default $50 ceiling
    assert F.main(_week_argv(tmp_path, "--confirm"), client=c) == 2
    assert not c.calls("get_range")
    assert not any(F.day_path(tmp_path, d).exists()
                   for d in F.trading_days("2026-09-07", "2026-09-13"))


def test_default_max_cost_is_fifty_per_w16_0009():
    assert F.MAX_COST == 50.00


def test_max_cost_is_a_ceiling_not_a_floor(tmp_path):
    c = FakeClient(cost=8.32)  # 6 x 8.32 = 49.92, just under 50
    assert F.main(_week_argv(tmp_path, "--confirm"), client=c) == 0
    assert len(c.calls("get_range")) == 6


def test_days_already_on_disk_are_never_repriced_or_rebought(tmp_path):
    for d in F.trading_days("2026-09-07", "2026-09-13"):
        p = F.day_path(tmp_path, d)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"already")
    c = FakeClient()
    assert F.main(_week_argv(tmp_path, "--confirm"), client=c) == 0
    assert c.log == [], "nothing may be priced or bought when every day exists"
    for d in F.trading_days("2026-09-07", "2026-09-13"):
        assert F.day_path(tmp_path, d).read_bytes() == b"already"


def test_partial_disk_only_prices_and_buys_the_missing_days(tmp_path):
    have = F.day_path(tmp_path, "2026-09-08")
    have.parent.mkdir(parents=True, exist_ok=True)
    have.write_bytes(b"already")
    c = FakeClient(cost=0.5)
    assert F.main(_week_argv(tmp_path, "--confirm"), client=c) == 0
    assert len(c.calls("cost")) == 5
    assert len(c.calls("get_range")) == 5
    assert have.read_bytes() == b"already"


def test_no_session_day_is_skipped_not_aborted(tmp_path):
    c = FakeClient(cost=0.5, no_session=("2026-09-11",))
    assert F.main(_week_argv(tmp_path, "--confirm"), client=c) == 0
    assert len(c.calls("get_range")) == 5, "the no-session day is never bought"
    assert not F.day_path(tmp_path, "2026-09-11").exists()
    m = json.loads(F.manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert m["no_session"] == ["2026-09-11"]
    assert len(m["files_pulled"]) == 5


def test_request_scope_is_pinned(tmp_path):
    """The scope that makes the price small and the symbols right. Widen
    any of it (parent symbol, ALL_SYMBOLS, a calendar rank, a different
    schema, per-root instead of combined) and this fails before the vendor
    does."""
    c = FakeClient()
    F.main(_week_argv(tmp_path), client=c)
    kws = [k for _, k in c.calls("cost")]
    assert len(kws) == 6
    for k in kws:
        assert k["dataset"] == "GLBX.MDP3"
        assert k["schema"] == "trades"
        assert k["stype_in"] == "continuous"
        assert sorted(k["symbols"]) == ["ES.v.0", "NQ.v.0"], (
            "one combined request per day, not one per root")
    starts = {k["start"][:10] for k in kws}
    assert starts == {"2026-09-07", "2026-09-08", "2026-09-09",
                      "2026-09-10", "2026-09-11", "2026-09-13"}


def test_files_land_under_their_own_w16_trades_subtree(tmp_path):
    for d in F.trading_days("2026-09-07", "2026-09-13"):
        p = F.day_path(tmp_path, d)
        assert p.parent.name == "w16_trades"
        assert p.parent.parent.name == "GLBX.MDP3"
        assert p.name == f"{d}.dbn.zst"


def test_failed_download_leaves_no_file_that_looks_complete(tmp_path):
    c = FakeClient()

    def boom(**kw):
        raise RuntimeError("400 bad request db-" + "x" * 30)
    c.timeseries.get_range = boom
    assert F.main(_week_argv(tmp_path, "--confirm"), client=c) == 1
    assert not any(F.day_path(tmp_path, d).exists()
                   for d in F.trading_days("2026-09-07", "2026-09-13"))


def test_failed_day_is_scrubbed_and_others_still_complete(tmp_path):
    c = FakeClient()
    real_get_range = c.timeseries.get_range

    def flaky(**kw):
        if kw["start"][:10] == "2026-09-09":
            raise RuntimeError("400 bad request db-" + "x" * 30)
        return real_get_range(**kw)
    c.timeseries.get_range = flaky
    rc = F.main(_week_argv(tmp_path, "--confirm"), client=c)
    assert rc == 1
    m = json.loads(F.manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert "x" * 30 not in json.dumps(m), "key-shaped text must be scrubbed"
    assert len(m["files_pulled"]) == 5
    assert m["files_failed"] == ["2026-09-09"]
    assert not F.day_path(tmp_path, "2026-09-09").exists()
    assert F.day_path(tmp_path, "2026-09-08").exists()


def test_end_defaults_to_dataset_end_when_start_given(tmp_path):
    c = FakeClient()
    argv = ["--archive", str(tmp_path), "--start", "2026-09-07"]
    F.main(argv, client=c)
    assert c.calls("range"), "no --end means the dataset range is looked up"


def test_start_defaults_to_window_before_explicit_end(tmp_path):
    c = FakeClient()
    argv = ["--archive", str(tmp_path), "--end", "2026-09-13",
            "--window-days", "3"]
    F.main(argv, client=c)
    kws = [k for _, k in c.calls("cost")]
    starts = sorted({k["start"][:10] for k in kws})
    # window-days=3 back from 2026-09-13 -> 2026-09-11 (Sat 09-12 excluded)
    assert starts == ["2026-09-11", "2026-09-13"]


# --- "today" is always a partial day (2026-09-28 live bug) -----------------
#
# The window's last day always first asks for the whole UTC day, through
# the NEXT day's 00:00Z. When that last day IS the dataset's most recent
# (still in progress) day, Databento rejects it: 422
# data_end_after_available_end. Live, 2026-09-28: pricing failed on
# 2026-09-28 -- range end 2026-09-29T00:00:00Z is after the dataset's real
# end, 2026-09-28T11:10:00Z.

def test_partial_last_day_is_repriced_capped_at_the_dataset_end(tmp_path):
    c = FakeClient(cost=0.5, partial_day="2026-09-13",
                    partial_end="2026-09-13T15:30:00Z")
    assert F.main(_week_argv(tmp_path, "--confirm"), client=c) == 0
    kws = [k for _, k in c.calls("cost")]
    partial = [k for k in kws if k["start"][:10] == "2026-09-13"]
    assert len(partial) == 2, "the first (rejected) try, then the capped retry"
    assert partial[0]["end"] == "2026-09-14T00:00:00Z"     # day+1 midnight, rejected
    assert partial[1]["end"] == "2026-09-13T15:30:00Z"     # capped, accepted
    assert len(c.calls("get_range")) == 6
    assert F.day_path(tmp_path, "2026-09-13").exists()
    m = json.loads(F.manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert m["no_session"] == []
    assert len(m["files_pulled"]) == 6


def test_dataset_range_is_looked_up_only_once_for_the_whole_run(tmp_path):
    c = FakeClient(cost=0.5, partial_day="2026-09-13",
                    partial_end="2026-09-13T15:30:00Z")
    F.main(_week_argv(tmp_path, "--confirm"), client=c)
    assert len(c.calls("range")) == 1, "the precise cap is fetched lazily, once"


def test_day_not_yet_started_in_the_dataset_is_treated_as_no_session(tmp_path):
    """The window's last day has just turned over UTC-wise but the dataset
    hasn't captured any of it yet -- nothing to buy this run."""
    c = FakeClient(cost=0.5, partial_day="2026-09-13",
                    partial_end="2026-09-13T00:00:00Z")
    assert F.main(_week_argv(tmp_path, "--confirm"), client=c) == 0
    assert not F.day_path(tmp_path, "2026-09-13").exists()
    assert len(c.calls("get_range")) == 5
    m = json.loads(F.manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert m["no_session"] == ["2026-09-13"]


def test_normal_run_never_pays_for_the_precise_range_lookup(tmp_path):
    """No day in the window is "today", so the cheap date-only lookup used
    for --end and the window default is all that's ever needed."""
    c = FakeClient(cost=0.5)
    F.main(_week_argv(tmp_path, "--confirm"), client=c)
    assert not c.calls("range"), (
        "an explicit --start/--end needs no dataset lookup at all when "
        "nothing hits the partial-day error")
