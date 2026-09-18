#!/usr/bin/env python3
"""The pull estimates before it spends, and never spends without --confirm.

This is the one TSMOM module that can transfer billable data. Everything below
exercises the guards against a fake client, so the suite never touches the
vendor. `tests/strategy/test_tsmom_data_price.py` guards the opposite property
for the estimator: that it has no download path at all.
"""
from __future__ import annotations

import json

import pytest

import common.tsmom_fetch as F


class _FakeData:
    def __init__(self, sink):
        self.sink = sink

    def to_file(self, path):
        self.sink.append(str(path))
        path.write_bytes(b"dbn")


class _FakeTimeseries:
    def __init__(self):
        self.downloads = []

    def get_range(self, **kw):
        return _FakeData(self.downloads)


class _FakeMeta:
    def __init__(self, usd=0.01, nbytes=1000):
        self.usd, self.nbytes, self.calls = usd, nbytes, []

    def get_cost(self, **kw):
        self.calls.append(kw)
        return self.usd

    def get_billable_size(self, **kw):
        return self.nbytes

    def get_dataset_range(self, **kw):
        return {"start": "2010-06-06", "end": "2026-09-17"}


class _FakeClient:
    def __init__(self, usd=0.01):
        self.metadata = _FakeMeta(usd)
        self.timeseries = _FakeTimeseries()


@pytest.fixture
def run(tmp_path, monkeypatch):
    """main() against a fake client, a temp archive, and a resolved key."""
    def _run(argv, usd=0.01):
        client = _FakeClient(usd)
        monkeypatch.setattr(F, "require_databento",
                            lambda: type("m", (), {"Historical": lambda *_: client}))
        monkeypatch.setattr("common.secrets_util.resolve", lambda *a, **k: "db-" + "x" * 20)
        rc = F.main(["--archive", str(tmp_path), "--roots", "ES", "GC"] + argv)
        return rc, client, tmp_path
    return _run


def test_without_confirm_it_estimates_and_downloads_nothing(run):
    rc, client, arch = run([])
    assert rc == 0
    assert client.timeseries.downloads == [], (
        "a run without --confirm transferred data. The whole contract of this "
        "module is that the number comes before the spend.")
    assert not any(arch.rglob("*.dbn.zst"))


def test_with_confirm_it_downloads(run):
    rc, client, arch = run(["--confirm"])
    assert rc == 0
    assert client.timeseries.downloads, "--confirm downloaded nothing"
    assert list(arch.rglob("*.dbn.zst"))


def test_max_cost_aborts_before_any_download(run):
    """A large estimate means the scope moved, not that the data got expensive.

    The $1,500 ALL_SYMBOLS quote is why this fails closed rather than printing
    the number calmly next to a prompt.
    """
    rc, client, _ = run(["--confirm", "--max-cost", "0.05"], usd=1.00)
    assert rc == 2
    assert client.timeseries.downloads == [], (
        "the cost ceiling was exceeded and data was downloaded anyway")


def test_files_already_on_disk_are_skipped_and_are_not_in_the_estimate(run):
    """Billing is on retrieval, so the estimate must cover only what would run.

    An estimate that quotes the whole pull while intending to download a tenth
    of it teaches the reader to ignore estimates.
    """
    rc, client, arch = run(["--confirm"])
    first_calls = len(client.metadata.calls)
    first_downloads = len(client.timeseries.downloads)
    assert first_downloads

    rc2, client2, _ = run(["--confirm"])
    assert rc2 == 0
    assert client2.timeseries.downloads == [], (
        "a second run re-downloaded files already on disk -- re-running is "
        "supposed to be free by construction")
    assert len(client2.metadata.calls) < first_calls, (
        "the second run priced jobs it was going to skip, so its printed "
        "estimate describes work that will not happen")


def test_a_pricing_failure_downloads_nothing(tmp_path, monkeypatch):
    # NOTE the explicit --archive. The first version of this test omitted it and
    # fell through to default_archive(), writing 191 files into `databento/` at
    # the repo root -- which is gitignored, so nothing reached a commit, and
    # which then made the NEXT run of this test see a complete archive and skip
    # everything. A test that writes outside tmp_path is a test that passes or
    # fails depending on what an earlier test did.
    def boom(**kw):
        raise RuntimeError("db-SECRETKEYSECRETKEYSECRET leaked in an error")
    client = _FakeClient()
    client.metadata.get_cost = boom
    monkeypatch.setattr(F, "require_databento",
                        lambda: type("m", (), {"Historical": lambda *_: client}))
    monkeypatch.setattr("common.secrets_util.resolve", lambda *a, **k: "db-" + "x" * 20)
    with pytest.raises(SystemExit) as e:
        F.main(["--confirm", "--roots", "ES", "--archive", str(tmp_path)])
    assert "nothing downloaded" in str(e.value)
    assert client.timeseries.downloads == []
    assert "SECRETKEY" not in str(e.value), (
        "a key reached an error message -- a Telegram token once leaked out of "
        "common/notify.py's exception handler")


def test_the_key_is_resolved_through_secrets_util():
    """One resolver. tsmom_data_price shipped a second one and produced a 401
    that read like a revoked subscription; it was an unresolved op:// reference.
    """
    src = (F.__file__).replace(".pyc", ".py")
    text = open(src, encoding="utf-8").read()
    assert "secrets_util" in text
    assert 'os.environ.get("DATABENTO_API_KEY")' not in text
    assert 'os.environ["DATABENTO_API_KEY"]' not in text


def test_no_monthly_sample_lands_on_a_weekend():
    """The defect that stopped the first live run.

    55 of 190 samples took the 15th unconditionally and landed on a Saturday or
    Sunday. A one-day window over a non-session day resolves nothing, and the
    vendor answers 422 symbology_invalid_request -- which reads like a wrong
    symbol or a wrong scope and is neither. The docstring and the registration
    both already claimed the grid stepped off non-sessions; nothing did.
    """
    from datetime import date as _d

    days = F.definition_days("2010-06-06", "2026-09-17")
    weekend = [x for x in days if _d.fromisoformat(x).weekday() >= 5]
    assert weekend == [], f"{len(weekend)} samples on a weekend, e.g. {weekend[:3]}"
    # stepped BACK, so the sample stays in its own month
    for x in days:
        assert _d.fromisoformat(x).day <= 15, x
        assert x[:7] == (x[:8] + "15")[:7]


def test_a_holiday_is_retried_forward_and_a_run_of_them_is_reported():
    """Weekends are known in advance; holidays are not.

    An unresolvable day moves rather than aborting -- but it is reported, because
    a run that quietly drops a few months is indistinguishable from one that
    drops a year.
    """
    class _HolidayMeta(_FakeMeta):
        def __init__(self, dead):
            super().__init__()
            self.dead = dead

        def get_cost(self, **kw):
            if kw.get("start") in self.dead:
                raise RuntimeError("422 symbology_invalid_request: None of the "
                                   "symbols could be resolved")
            return super().get_cost(**kw)

    client = _FakeClient()
    client.metadata = _HolidayMeta({"2011-07-15"})       # one holiday
    jobs, usd, _, _ = F.plan(client, {"ES": ""}, F.Path("/nonexistent"),
                             "2010-06-06", "2026-09-17")
    got = {kw["start"] for _, sc, _, kw in jobs if sc == F.DEF_SCHEMA}
    assert "2011-07-15" not in got
    assert "2011-07-16" in got, "the holiday was not retried forward"
    assert len(got) == len(F.definition_days("2010-06-06", "2026-09-17"))


def test_a_non_symbology_failure_still_aborts_and_names_the_job():
    """A blanket retry would turn a mis-scoped request into a slow one instead
    of a loud one. And the first version's error named no job at all, which is
    why the live 422 could not be diagnosed from its own output."""
    class _BrokenMeta(_FakeMeta):
        def get_cost(self, **kw):
            raise RuntimeError("500 internal error")

    client = _FakeClient()
    client.metadata = _BrokenMeta()
    with pytest.raises(SystemExit) as e:
        F.plan(client, {"ES": ""}, F.Path("/nonexistent"), "2010-06-06", "2026-09-17")
    msg = str(e.value)
    assert "nothing downloaded" in msg
    assert "ES" in msg and F.BAR_SCHEMA in msg, (
        "the error does not name the failing job -- which is exactly why the "
        "live 422 on 2026-09-18 could not be diagnosed from its own output")
    assert "continuous" in msg


def test_a_non_symbology_failure_on_a_DEFINITION_job_aborts(capsys):
    """The retry must be narrow, and this is the test that proves it is.

    Mutation-testing caught the gap: the earlier version of this check failed
    every call including the BAR jobs, which abort unconditionally -- so
    widening _is_symbology_miss to `return True` changed nothing observable and
    the mutation survived. Bars must succeed here so the definition path is the
    one under test.
    """
    class _DefBreaks(_FakeMeta):
        def get_cost(self, **kw):
            if kw.get("schema") == F.DEF_SCHEMA:
                raise RuntimeError("500 internal server error")
            return super().get_cost(**kw)

    client = _FakeClient()
    client.metadata = _DefBreaks()
    with pytest.raises(SystemExit) as e:
        F.plan(client, {"ES": ""}, F.Path("/nonexistent"), "2010-06-06", "2026-09-17")
    msg = str(e.value)
    assert "nothing downloaded" in msg and F.DEF_SCHEMA in msg, (
        "a 500 on a definition job was retried away as though it were a "
        "holiday -- a blanket retry turns a mis-scoped request into a slow one "
        "instead of a loud one")


def test_unplaced_months_are_reported_and_a_run_of_them_aborts(capsys):
    """A run that quietly drops a few months is indistinguishable from one that
    drops a year, so the count is printed and 2% stops the run."""
    class _DeadRange(_FakeMeta):
        def __init__(self, dead_from, dead_to):
            super().__init__()
            self.lo, self.hi = dead_from, dead_to

        def get_cost(self, **kw):
            if kw.get("schema") == F.DEF_SCHEMA and self.lo <= kw["start"] <= self.hi:
                raise RuntimeError("422 symbology_invalid_request: None of the "
                                   "symbols could be resolved")
            return super().get_cost(**kw)

    # One month unplaceable: reported, run continues.
    client = _FakeClient()
    client.metadata = _DeadRange("2011-07-01", "2011-07-31")
    jobs, _, _, _ = F.plan(client, {"ES": ""}, F.Path("/nonexistent"),
                           "2010-06-06", "2026-09-17")
    out = capsys.readouterr().out
    assert "WARNING" in out and "1 month(s)" in out and "2011-07" in out, (
        "an unplaceable month was skipped silently")
    assert jobs

    # A year of them: above the registered 2%, so the run stops.
    client2 = _FakeClient()
    client2.metadata = _DeadRange("2013-01-01", "2014-12-31")
    with pytest.raises(SystemExit) as e:
        F.plan(client2, {"ES": ""}, F.Path("/nonexistent"),
               "2010-06-06", "2026-09-17")
    assert "ABORT" in str(e.value) and "nothing downloaded" in str(e.value)


def test_the_definition_grid_is_monthly_deterministic_and_capped():
    days = F.definition_days("2010-06-06", "2026-09-17")
    assert days == F.definition_days("2010-06-06", "2026-09-17"), "not deterministic"
    assert len(days) <= F.DEFINITION_SAMPLES
    months = {d[:7] for d in days}
    assert len(months) == len(days), "two samples landed in one month"
    assert days == sorted(days)
    assert all("2010-06-06" <= d <= "2026-09-17" for d in days)
    # The grid the estimate was priced on. If this drifts, the $3.65 in
    # REGISTERED_tsmom section 0.1 stops describing the pull.
    assert 180 <= len(days) <= 190, f"{len(days)} samples, not ~190"


def test_every_definition_request_asks_for_exactly_one_session():
    """start == end is an EMPTY range and returns 422.

    common.tsmom_data_price's --diagnose shipped with that bug and the 422 read
    like a scoping failure.
    """
    client = _FakeClient()
    jobs, _, _, _ = F.plan(client, {"ES": ""}, F.Path("/nonexistent"),
                           "2010-06-06", "2026-09-17")
    defs = [kw for _, sc, _, kw in jobs if sc == F.DEF_SCHEMA]
    assert defs
    for kw in defs:
        assert kw["start"] < kw["end"], kw
        from datetime import date as _d
        assert (_d.fromisoformat(kw["end"]) - _d.fromisoformat(kw["start"])).days == 1


def test_bars_come_from_continuous_front_and_next(run):
    client = _FakeClient()
    jobs, _, _, _ = F.plan(client, {"CL": ""}, F.Path("/nonexistent"),
                           "2010-06-06", "2026-09-17")
    bars = [kw for _, sc, _, kw in jobs if sc == F.BAR_SCHEMA]
    assert len(bars) == 1
    assert bars[0]["stype_in"] == "continuous"
    assert bars[0]["symbols"] == "CL.c.0,CL.c.1", (
        "amendment A buys the front contract and the next one -- c.2 and beyond "
        "are the deferred months that made the first scoping $21 of bars")


def test_the_manifest_records_what_a_report_has_to_read_back(run):
    """A report names its tape and refuses the wrong one, and it cannot do that
    unless the archive says what it is. The ORB pre-flight asserted its caveat
    instead of reading it and two tests pinned the bug."""
    rc, _, arch = run(["--confirm"])
    m = json.loads((arch / F.DATASET / "manifest_tsmom.json").read_text(encoding="utf-8"))
    assert m["dataset"] == "GLBX.MDP3"
    assert "continuous" in m["schemas"][F.BAR_SCHEMA]
    assert "REGISTERED_tsmom_fetch" in m["registration"]
    assert "amendment A" in m["scope_amendment"]
    assert m["pulls"][-1]["jobs_run"] >= 1


def test_unknown_roots_are_refused(tmp_path):
    # --archive is passed even though this raises long before anything is
    # written: the guard below is strict on purpose, and an exemption for
    # "this one cannot reach the write" is how the next one slips through.
    with pytest.raises(SystemExit) as e:
        F.main(["--roots", "ES", "WHEAT", "--archive", str(tmp_path)])
    assert "WHEAT" in str(e.value)


def test_no_test_in_this_file_writes_outside_tmp_path():
    """Every main() call here passes --archive.

    Without it, default_archive() resolves to `databento/` at the repo root and
    the test writes a real archive tree there. It is gitignored, so the damage
    is invisible to git and shows up instead as a LATER test skipping work it
    meant to do.
    """
    import ast

    src = ast.parse(open(__file__, encoding="utf-8").read())
    bad = []
    for node in ast.walk(src):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "main"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "F"):
            argv = node.args[0] if node.args else None
            flat = ast.dump(argv) if argv is not None else ""
            if "--archive" not in flat:
                bad.append(node.lineno)
    assert bad == [], (
        f"F.main called without --archive at line(s) {bad} -- that writes into "
        "the repo's default archive path")
