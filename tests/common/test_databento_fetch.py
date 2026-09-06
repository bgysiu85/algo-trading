#!/usr/bin/env python3
"""Guards on a tool that can spend money.

The reason these exist: the same date range priced at $1,500 with
symbols="ALL_SYMBOLS" and under a cent scoped to the two tickers actually
wanted. Nothing here touches the network -- these pin the filtering, the
archive layout and the spend guards, which is where a mis-specified request
turns into a bill.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common import databento_fetch as F


def pairs_file(tmp_path, pairs):
    p = tmp_path / "pairs.json"
    json.dump([{"symbol": s, "date": d} for s, d in pairs], open(p, "w"))
    return p


def test_pairs_load_deduped_and_sorted(tmp_path):
    p = pairs_file(tmp_path, [("B", "2025-06-04"), ("A", "2025-06-04"),
                              ("A", "2025-06-04")])
    assert F.load_pairs(p) == [("A", "2025-06-04"), ("B", "2025-06-04")]


def test_before_and_after_are_half_open_and_do_not_overlap(tmp_path):
    """--before X and --after X must partition, not double-count. Fetching a
    day twice is a real cost, and dropping one is a silent hole."""
    ps = [("A", "2025-09-05"), ("B", "2025-09-06"), ("C", "2025-09-07")]
    before = F.filter_pairs(ps, before="2025-09-06")
    after = F.filter_pairs(ps, after="2025-09-06")
    assert before == [("A", "2025-09-05")]
    assert after == [("B", "2025-09-06"), ("C", "2025-09-07")]
    assert set(before) | set(after) == set(ps)
    assert not (set(before) & set(after))


def test_missing_from_cache_reads_the_real_filenames(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "AAA_2025-06-04.csv.gz").write_bytes(b"")
    got = F.filter_pairs([("AAA", "2025-06-04"), ("BBB", "2025-06-04")],
                         missing_from_cache=str(cache))
    assert got == [("BBB", "2025-06-04")]


def test_symbols_are_grouped_per_date(tmp_path):
    """One request per date carrying every symbol wanted that day. Requesting
    each symbol-day separately multiplies the request count by ~3 for no extra
    data and runs into rate limits."""
    g = F.group_by_date([("B", "2025-06-04"), ("A", "2025-06-04"),
                         ("C", "2025-06-06")])
    assert g == {"2025-06-04": ["A", "B"], "2025-06-06": ["C"]}


def test_archive_path_is_stable(tmp_path):
    """The skip-if-present guard is only as good as this being deterministic.
    If the path ever changes shape, every previously bought file is re-bought."""
    p = F.archive_path(Path("databento"), "EQUS.ALL", "tbbo", "2025-06-04")
    assert p == Path("databento/EQUS.ALL/tbbo/2025-06-04.dbn.zst")


def test_a_key_is_never_echoed(monkeypatch):
    monkeypatch.setenv("DATABENTO_API_KEY", "db-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
    assert F._key().startswith("db-")
    leaked = "HTTP 401 for key db-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 at /v0/x"
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in F._scrub(leaked)
    assert "<redacted>" in F._scrub(leaked)


def test_no_key_exits_rather_than_calling_with_an_empty_one(monkeypatch):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        F._key()


class FakeMeta:
    def __init__(self, usd, size):
        self.usd, self.size = usd, size

    def get_cost(self, **kw):
        return self.usd

    def get_billable_size(self, **kw):
        return self.size


class FakeClient:
    def __init__(self, usd=0.01, size=60_900):
        self.metadata = FakeMeta(usd, size)


def test_plan_skips_files_already_on_disk_and_charges_nothing_for_them(tmp_path):
    """Re-running must be free. If this regresses, every re-run re-buys the
    whole archive and the bill scales with how often the tool is used."""
    root = tmp_path / "archive"
    got = F.archive_path(root, "EQUS.ALL", "tbbo", "2025-06-04")
    got.parent.mkdir(parents=True)
    got.write_bytes(b"already here")

    groups = {"2025-06-04": ["APLD", "QIPT"], "2025-06-06": ["APLD"]}
    jobs, usd, size = F.plan(FakeClient(), groups, "EQUS.ALL", ["tbbo"], root, 5)

    skipped = [j for j in jobs if j[8]]
    todo = [j for j in jobs if not j[8]]
    assert len(skipped) == 1 and len(todo) == 1
    assert usd == pytest.approx(0.01)      # only the one not on disk
    assert size == 60_900


def test_plan_pulls_warm_up_days_before_the_session(tmp_path):
    """A symbol-day is not one calendar day. MCL needs two sessions ending
    09:30, so a single-day window would return bars the backtest cannot use and
    the error would show up as 'too short for full warm-up' skips, not as a
    fetch failure."""
    jobs, _, _ = F.plan(FakeClient(), {"2025-06-09": ["APLD"]},
                        "EQUS.ALL", ["ohlcv-1m"], tmp_path, 5)
    _day, _syms, _schema, start, end, *_ = jobs[0]
    assert start == "2025-06-04"
    assert end == "2025-06-10"             # end is exclusive, so day + 1


# --- data quality -----------------------------------------------------------

class FakeMetaCond(FakeMeta):
    def __init__(self, usd, size, rows):
        super().__init__(usd, size)
        self.rows = rows

    def get_dataset_condition(self, **kw):
        return self.rows


class FakeClientCond(FakeClient):
    def __init__(self, rows):
        self.metadata = FakeMetaCond(0.01, 100, rows)


def test_degraded_days_are_surfaced_not_just_warned_about(tmp_path):
    """Databento emits a BentoWarning to stderr and hands over the file anyway.

    Two of the first eight days pulled came back 'degraded'. On a 587-day pull
    those warnings scroll past, and afterwards a degraded file is byte-for-byte
    indistinguishable from a clean one -- a thin pre-market session and a
    session that was not properly captured look the same in the bars.
    """
    rows = [{"date": "2025-06-04", "condition": "degraded"},
            {"date": "2025-06-06", "condition": "available"}]
    got = F.conditions(FakeClientCond(rows), "EQUS.MINI",
                       ["2025-06-04", "2025-06-06"])
    assert got == {"2025-06-04": "degraded", "2025-06-06": "available"}
    assert [d for d, c in got.items() if c != "available"] == ["2025-06-04"]


def test_a_condition_lookup_failure_does_not_abort_the_fetch(tmp_path):
    """Quality metadata is a nice-to-have; losing it must not cost the data."""
    class Broken(FakeClient):
        def __init__(self):
            super().__init__()
            self.metadata.get_dataset_condition = self._boom

        @staticmethod
        def _boom(**kw):
            raise RuntimeError("503")

    assert F.conditions(Broken(), "EQUS.MINI", ["2025-06-04"]) == {}


def test_manifest_merges_and_never_drops_earlier_entries(tmp_path):
    """The archive is built incrementally over months. If a later pull
    overwrote the manifest, the record of which days were degraded when they
    were captured would be lost -- and that record is the only thing that makes
    bought data trustworthy after the plan window has rolled past it."""
    root = tmp_path / "arch"
    F.write_manifest(root, "EQUS.MINI",
                     {"tbbo/2025-06-04": {"condition": "degraded"}})
    F.write_manifest(root, "EQUS.MINI",
                     {"tbbo/2025-06-06": {"condition": "available"}})
    m = json.load(open(F.manifest_path(root, "EQUS.MINI")))
    assert set(m) == {"tbbo/2025-06-04", "tbbo/2025-06-06"}
    assert m["tbbo/2025-06-04"]["condition"] == "degraded"


def test_a_corrupt_manifest_is_replaced_not_fatal(tmp_path):
    root = tmp_path / "arch"
    p = F.manifest_path(root, "EQUS.MINI")
    p.parent.mkdir(parents=True)
    p.write_text("{ not json")
    F.write_manifest(root, "EQUS.MINI", {"tbbo/2025-06-04": {"condition": "ok"}})
    assert json.load(open(p))["tbbo/2025-06-04"]["condition"] == "ok"
