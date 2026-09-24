"""strategy.htf.fetch -- the spending guards, pinned (W15-0002).

A fake client stands in for databento, so these tests never reach the vendor and
never need the key. Each guard has a test that fails if the guard is removed.
"""
from __future__ import annotations

import json

import pytest

from strategy.htf import fetch as F


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
        return {"start": "2010-06-06T00:00:00Z", "end": "2026-09-25T00:00:00Z"}

    def get_cost(self, **kw):
        self.log.append(("cost", kw))
        return self.cost

    def get_billable_size(self, **kw):
        return 12_345_678


class _TS:
    def __init__(self, log):
        self.log = log

    def get_range(self, **kw):
        self.log.append(("get_range", kw))
        return _Data(self.log)


class FakeClient:
    def __init__(self, cost=0.42):
        self.log = []
        self.metadata = _Meta(cost, self.log)
        self.timeseries = _TS(self.log)

    def calls(self, name):
        return [c for c in self.log if c[0] == name]


def test_estimate_only_never_downloads(tmp_path):
    c = FakeClient()
    assert F.main(["--archive", str(tmp_path)], client=c) == 0
    assert c.calls("cost"), "it must price"
    assert not c.calls("get_range"), "no --confirm means no download"
    assert not F.bar_path(tmp_path).exists()


def test_confirm_downloads_once_and_writes_manifest(tmp_path):
    c = FakeClient()
    assert F.main(["--archive", str(tmp_path), "--confirm"], client=c) == 0
    assert len(c.calls("get_range")) == 1
    out = F.bar_path(tmp_path)
    assert out.exists() and out.read_bytes() == b"DBN-fake"
    assert not out.with_name(out.name + ".part").exists()
    m = json.loads(F.manifest_path(tmp_path).read_text())
    assert m["symbols"] == "CL.c.0,CL.c.1" and m["schema"] == "ohlcv-1h"
    assert m["start"] == "2010-06-06" and m["end"] == "2026-09-25"
    assert m["board"] == "W15-0002"


def test_over_max_cost_aborts_even_with_confirm(tmp_path):
    c = FakeClient(cost=9.99)
    assert F.main(["--archive", str(tmp_path), "--confirm"], client=c) == 2
    assert not c.calls("get_range")
    assert not F.bar_path(tmp_path).exists()


def test_max_cost_is_a_ceiling_not_a_floor(tmp_path):
    c = FakeClient(cost=4.99)
    assert F.main(["--archive", str(tmp_path), "--confirm", "--max-cost", "5"],
                  client=c) == 0
    assert len(c.calls("get_range")) == 1


def test_file_on_disk_is_never_repriced_or_rebought(tmp_path):
    out = F.bar_path(tmp_path)
    out.parent.mkdir(parents=True)
    out.write_bytes(b"already")
    c = FakeClient()
    assert F.main(["--archive", str(tmp_path), "--confirm"], client=c) == 0
    assert c.log == [], "nothing may be priced or bought when the file exists"
    assert out.read_bytes() == b"already"


def test_request_scope_is_pinned(tmp_path):
    """The scope that makes the price small. Widen any of it (parent symbol,
    ALL_SYMBOLS, a different schema) and this fails before the vendor does."""
    c = FakeClient()
    F.main(["--archive", str(tmp_path)], client=c)
    kw = c.calls("cost")[0][1]
    assert kw == {"dataset": "GLBX.MDP3", "schema": "ohlcv-1h",
                  "symbols": "CL.c.0,CL.c.1", "stype_in": "continuous",
                  "start": "2010-06-06", "end": "2026-09-25"}


def test_end_override_is_passed_through(tmp_path):
    c = FakeClient()
    F.main(["--archive", str(tmp_path), "--end", "2026-09-24"], client=c)
    assert c.calls("cost")[0][1]["end"] == "2026-09-24"
    assert not c.calls("range"), "an explicit --end needs no range lookup"


def test_target_is_beside_not_inside_the_daily_tree(tmp_path):
    p = F.bar_path(tmp_path)
    assert p.parent.name == "ohlcv-1h" and p.parent.parent.name == "GLBX.MDP3"
    assert "ohlcv-1d" not in str(p)


def test_failed_download_leaves_no_file_that_looks_complete(tmp_path):
    c = FakeClient()

    def boom(**kw):
        raise RuntimeError("400 bad request db-" + "x" * 30)
    c.timeseries.get_range = boom
    with pytest.raises(SystemExit) as e:
        F.main(["--archive", str(tmp_path), "--confirm"], client=c)
    assert "x" * 30 not in str(e.value), "key-shaped text must be scrubbed"
    assert not F.bar_path(tmp_path).exists()


def test_interrupted_write_never_takes_the_real_name(tmp_path):
    """A download that dies half-way through writing must not leave a file at
    the real path -- the 'already on disk' check would then skip it forever."""
    c = FakeClient()

    class HalfData:
        def to_file(self, path):
            with open(path, "wb") as fh:
                fh.write(b"DBN-half")
            raise ConnectionResetError("connection reset mid-transfer")
    c.timeseries.get_range = lambda **kw: HalfData()
    with pytest.raises(SystemExit):
        F.main(["--archive", str(tmp_path), "--confirm"], client=c)
    assert not F.bar_path(tmp_path).exists()
