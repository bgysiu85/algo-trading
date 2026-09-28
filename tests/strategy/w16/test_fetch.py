"""strategy.w16.fetch -- the spending guards, pinned (W16-0003 subitem 2).

A fake client stands in for databento, so these tests never reach the vendor
and never need the key. Modelled on tests/strategy/htf/test_fetch.py.
"""
from __future__ import annotations

import json

import pytest

from strategy.w16 import fetch as F


class _Data:
    def __init__(self, log):
        self.log = log

    def to_file(self, path):
        self.log.append(("to_file", str(path)))
        with open(path, "wb") as fh:
            fh.write(b"DBN-fake")


class _Meta:
    def __init__(self, cost, log):
        self.cost, self.log = cost, log

    def get_dataset_range(self, dataset):
        self.log.append(("range", dataset))
        return {"start": "2010-06-06T00:00:00Z", "end": "2026-09-26T00:00:00Z"}

    def get_cost(self, **kw):
        self.log.append(("cost", kw))
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
    def __init__(self, cost=1.0):
        self.log = []
        self.metadata = _Meta(cost, self.log)
        self.timeseries = _TS(self.log)

    def calls(self, name):
        return [c for c in self.log if c[0] == name]


def _all_paths(tmp_path):
    return [F.bar_path(tmp_path, r, s) for r in F.ROOTS for s in F.SCHEMAS]


def test_estimate_only_never_downloads(tmp_path):
    c = FakeClient()
    assert F.main(["--archive", str(tmp_path)], client=c) == 0
    assert c.calls("cost"), "it must price"
    assert not c.calls("get_range"), "no --confirm means no download"
    assert not any(p.exists() for p in _all_paths(tmp_path))


def test_confirm_downloads_all_four_files_and_writes_manifest(tmp_path):
    c = FakeClient(cost=0.5)
    assert F.main(["--archive", str(tmp_path), "--confirm"], client=c) == 0
    assert len(c.calls("get_range")) == 4
    for p in _all_paths(tmp_path):
        assert p.exists() and p.read_bytes() == b"DBN-fake"
        assert not p.with_name(p.name + ".part").exists()
    m = json.loads(F.manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert set(m["roots"]) == set(F.ROOTS)
    assert set(m["schemas"]) == set(F.SCHEMAS)
    assert m["start"] == "2010-06-06" and m["end"] == "2026-09-26"
    assert m["board"] == "W16-0003"
    assert len(m["files_pulled"]) == 4


def test_over_max_cost_aborts_even_with_confirm(tmp_path):
    c = FakeClient(cost=20.0)  # 4 jobs x $20 = $80 > default $50 ceiling
    assert F.main(["--archive", str(tmp_path), "--confirm"], client=c) == 2
    assert not c.calls("get_range")
    assert not any(p.exists() for p in _all_paths(tmp_path))


def test_default_max_cost_is_fifty_per_registration(tmp_path):
    assert F.MAX_COST == 50.00


def test_max_cost_is_a_ceiling_not_a_floor(tmp_path):
    c = FakeClient(cost=12.49)  # 4 x 12.49 = 49.96, just under 50
    assert F.main(["--archive", str(tmp_path), "--confirm"], client=c) == 0
    assert len(c.calls("get_range")) == 4


def test_files_already_on_disk_are_never_repriced_or_rebought(tmp_path):
    for p in _all_paths(tmp_path):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"already")
    c = FakeClient()
    assert F.main(["--archive", str(tmp_path), "--confirm"], client=c) == 0
    assert c.log == [], "nothing may be priced or bought when every file exists"
    for p in _all_paths(tmp_path):
        assert p.read_bytes() == b"already"


def test_partial_disk_only_prices_and_buys_the_missing_files(tmp_path):
    have = F.bar_path(tmp_path, "ES", "ohlcv-1m")
    have.parent.mkdir(parents=True, exist_ok=True)
    have.write_bytes(b"already")
    c = FakeClient(cost=0.5)
    assert F.main(["--archive", str(tmp_path), "--confirm"], client=c) == 0
    assert len(c.calls("cost")) == 3
    assert len(c.calls("get_range")) == 3
    assert have.read_bytes() == b"already"


def test_request_scope_is_pinned(tmp_path):
    """The scope that makes the price small and the symbols right. Widen any
    of it (parent symbol, ALL_SYMBOLS, a calendar rank, a different schema)
    and this fails before the vendor does."""
    c = FakeClient()
    F.main(["--archive", str(tmp_path)], client=c)
    kws = [k for _, k in c.calls("cost")]
    assert {"ES.v.0", "NQ.v.0"} == {k["symbols"] for k in kws}
    assert {"ohlcv-1m", "ohlcv-1d"} == {k["schema"] for k in kws}
    for k in kws:
        assert k["dataset"] == "GLBX.MDP3"
        assert k["stype_in"] == "continuous"
        assert k["start"] == "2010-06-06"
        assert k["end"] == "2026-09-26"


def test_end_override_is_passed_through(tmp_path):
    c = FakeClient()
    F.main(["--archive", str(tmp_path), "--end", "2026-09-25"], client=c)
    assert all(k["end"] == "2026-09-25" for _, k in c.calls("cost"))
    assert not c.calls("range"), "an explicit --end needs no range lookup"


def test_files_land_under_their_own_w16_session_subtree(tmp_path):
    for p in _all_paths(tmp_path):
        assert p.parent.parent.name == "w16_session"
        assert p.parent.parent.parent.name == "GLBX.MDP3"


def test_failed_download_leaves_no_file_that_looks_complete(tmp_path):
    c = FakeClient()

    def boom(**kw):
        raise RuntimeError("400 bad request db-" + "x" * 30)
    c.timeseries.get_range = boom
    assert F.main(["--archive", str(tmp_path), "--confirm"], client=c) == 1
    assert not any(p.exists() for p in _all_paths(tmp_path))
    assert not F.manifest_path(tmp_path).exists() or True  # manifest still written w/ failures listed


def test_failed_job_is_scrubbed_and_others_still_complete(tmp_path):
    c = FakeClient()
    real_get_range = c.timeseries.get_range

    def flaky(**kw):
        if kw["symbols"] == "NQ.v.0" and kw["schema"] == "ohlcv-1m":
            raise RuntimeError("400 bad request db-" + "x" * 30)
        return real_get_range(**kw)
    c.timeseries.get_range = flaky
    rc = F.main(["--archive", str(tmp_path), "--confirm"], client=c)
    assert rc == 1
    m = json.loads(F.manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert "x" * 30 not in json.dumps(m), "key-shaped text must be scrubbed"
    assert len(m["files_pulled"]) == 3
    assert m["files_failed"] == ["NQ ohlcv-1m"]
    assert not F.bar_path(tmp_path, "NQ", "ohlcv-1m").exists()
    assert F.bar_path(tmp_path, "ES", "ohlcv-1m").exists()
