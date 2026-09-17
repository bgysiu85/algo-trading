#!/usr/bin/env python3
"""strategy/orb/pit_bars.py: fetch the PIT bars without deleting the others.

The failure this guards is silent in both directions. databento_fetch
REPLACES a day's file, so asking for only the missing names deletes the
survivors from the archive; and it SKIPS a file whose manifest row has no
symbol list, so the missing names are never fetched at all.
"""
from __future__ import annotations

import json
from pathlib import Path

from strategy.orb import pit_bars as P


class Files:
    """A fake archive: date -> symbol set, or absent."""

    def __init__(self, tmp: Path, days: dict):
        self.tmp, self.days = tmp, days
        for d in days:
            (tmp / f"{d}.dbn.zst").write_bytes(b"x")

    def path(self, day):
        return self.tmp / f"{day}.dbn.zst"

    def read(self, path):
        return set(self.days[path.name[:10]])


def test_the_request_keeps_every_symbol_the_file_already_holds(tmp_path):
    fs = Files(tmp_path, {"2025-03-07": {"SURV1", "SURV2", "REJ1"}})
    p = P.plan({"2025-03-07": {"PIT1", "PIT2"}}, fs.path, fs.read)
    e = p["2025-03-07"]
    assert set(e["request"]) == {"SURV1", "SURV2", "REJ1", "PIT1", "PIT2"}
    assert e["added"] == ["PIT1", "PIT2"]
    assert set(e["before"]) <= set(e["request"])


def test_a_date_with_no_file_asks_only_for_what_it_needs(tmp_path):
    fs = Files(tmp_path, {})
    p = P.plan({"2026-09-08": {"A"}}, fs.path, fs.read)
    assert p["2026-09-08"] == {"before": [], "request": ["A"], "added": ["A"]}


def test_a_name_already_in_the_file_is_not_counted_as_added(tmp_path):
    """9 dates had a missing cache file for a name the archive file holds --
    the cache build called those short windows, not absent bars."""
    fs = Files(tmp_path, {"2025-01-02": {"A", "B"}})
    p = P.plan({"2025-01-02": {"B", "C"}}, fs.path, fs.read)
    assert p["2025-01-02"]["added"] == ["C"]


def test_the_pairs_file_is_the_union_in_fetch_format(tmp_path):
    fs = Files(tmp_path, {"2025-03-07": {"S"}})
    rows = P.pairs_of(P.plan({"2025-03-07": {"P"}}, fs.path, fs.read))
    assert rows == [{"symbol": "P", "date": "2025-03-07"},
                    {"symbol": "S", "date": "2025-03-07"}]


def test_missing_by_date_reads_the_cache_names(tmp_path):
    (tmp_path / "A_2025-01-02.csv.gz").write_bytes(b"")
    m = P.missing_by_date([{"symbol": "A", "date": "2025-01-02"},
                           {"symbol": "B", "date": "2025-01-02"}], tmp_path)
    assert m == {"2025-01-02": {"B"}}


def test_unverified_rows_get_the_file_symbols_and_recorded_rows_are_left(tmp_path):
    fs = Files(tmp_path, {"2024-07-08": {"X", "Y"}, "2025-03-07": {"S"}})
    p = P.plan({"2024-07-08": {"P"}, "2025-03-07": {"Q"}}, fs.path, fs.read)
    manifest = {
        "ohlcv-1m/2024-07-08": {"date": "2024-07-08", "symbols_unverified": True},
        "ohlcv-1m/2025-03-07": {"date": "2025-03-07", "symbols": ["S"]},
    }
    ent = P.manifest_backfill(manifest, p)
    assert list(ent) == ["ohlcv-1m/2024-07-08"]
    row = ent["ohlcv-1m/2024-07-08"]
    assert row["symbols"] == ["X", "Y"], "the FILE's symbols, not the request"
    assert "symbols_unverified" not in row and row["symbols_from_file_metadata"]


def test_the_backfilled_row_makes_databento_fetch_ask_again(tmp_path):
    """The point of the backfill: covered() must return False for a date whose
    file lacks the PIT name, which it cannot do on a row with no list."""
    from common.databento_fetch import covered
    fs = Files(tmp_path, {"2024-07-08": {"X"}})
    p = P.plan({"2024-07-08": {"P"}}, fs.path, fs.read)
    before = {}
    assert covered(before, "ohlcv-1m", "2024-07-08", p["2024-07-08"]["request"])
    m = {k: set(v["symbols"]) for k, v in P.manifest_backfill(
             {"ohlcv-1m/2024-07-08": {"date": "2024-07-08"}}, p).items()}
    assert not covered(m, "ohlcv-1m", "2024-07-08", p["2024-07-08"]["request"])


def test_verify_refuses_a_fetch_that_dropped_a_symbol(tmp_path):
    snap = {"2025-03-07": {"before": ["S1", "S2"], "request": ["P", "S1", "S2"],
                           "added": ["P"]}}
    good = Files(tmp_path, {"2025-03-07": {"S1", "S2", "P"}})
    assert P.verify(snap, good.path, good.read)["lost"] == {}
    bad = Files(tmp_path, {"2025-03-07": {"P"}})
    r = P.verify(snap, bad.path, bad.read)
    assert r["lost"] == {"2025-03-07": ["S1", "S2"]}


def test_verify_reports_an_added_name_the_fetch_did_not_bring(tmp_path):
    snap = {"2025-03-07": {"before": ["S"], "request": ["P", "S"], "added": ["P"]}}
    fs = Files(tmp_path, {"2025-03-07": {"S"}})
    assert P.verify(snap, fs.path, fs.read)["unfetched"] == {"2025-03-07": ["P"]}


def test_main_refuses_to_proceed_while_rows_are_unverified(tmp_path, monkeypatch):
    arch = tmp_path / "arch"
    day = arch / "XNAS.BASIC" / "ohlcv-1m"
    day.mkdir(parents=True)
    (day / "2024-07-08.dbn.zst").write_bytes(b"x")
    (arch / "XNAS.BASIC" / "manifest.json").write_text(json.dumps(
        {"ohlcv-1m/2024-07-08": {"date": "2024-07-08"}}), encoding="utf-8")
    monkeypatch.setattr(P, "dbn_symbols", lambda path: {"X"})
    pairs = tmp_path / "pit.json"
    pairs.write_text(json.dumps([{"symbol": "P", "date": "2024-07-08"}]),
                     encoding="utf-8")
    cache = tmp_path / "cache"; cache.mkdir()
    args = ["plan", "--archive", str(arch), "--pairs", str(pairs),
            "--cache", str(cache), "--out", str(tmp_path / "o.json"),
            "--snapshot", str(tmp_path / "s.json")]
    assert P.main(args) == 1
    assert P.main(args + ["--write-manifest"]) == 0
    m = json.loads((arch / "XNAS.BASIC" / "manifest.json").read_text(encoding="utf-8"))
    assert m["ohlcv-1m/2024-07-08"]["symbols"] == ["X"]
    assert list((arch / "XNAS.BASIC").glob("manifest.*.bak.json"))
    assert P.main(args) == 0, "once recorded, nothing is unverified"
