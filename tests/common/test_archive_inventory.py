#!/usr/bin/env python3
"""The archive's own account of itself, checked against the disk.

A downloader's summary is written by the code whose behaviour is in question.
These tests pin the cases where the two would disagree.
"""
from __future__ import annotations

from pathlib import Path

from common import archive_inventory as A


def chunk(root: Path, dataset: str, schema: str, day: str, size: int = 100):
    p = root / dataset / schema / f"{day}.dbn.zst"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    return p


def test_counts_and_date_span_come_from_the_files_themselves(tmp_path):
    chunk(tmp_path, "EQUS.SUMMARY", "statistics", "2024-07-01", 10)
    chunk(tmp_path, "EQUS.SUMMARY", "statistics", "2026-09-04", 30)
    rows, _, _ = A.scan(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["files"] == 2 and r["bytes"] == 40
    assert r["first"] == "2024-07-01" and r["last"] == "2026-09-04"


def test_an_empty_schema_directory_is_reported_not_omitted(tmp_path):
    """The whole point is telling 'downloaded nothing' apart from 'the counter
    did not match'. A schema folder that exists and holds no chunks is the
    first of those, and must appear rather than vanishing from the table."""
    (tmp_path / "EQUS.SUMMARY" / "statistics").mkdir(parents=True)
    rows, _, _ = A.scan(tmp_path)
    assert len(rows) == 1 and rows[0]["files"] == 0
    out = A.render(tmp_path, rows, [], [], 100.0)
    assert "EMPTY" in out


def test_interrupted_transfers_are_surfaced(tmp_path):
    """Downloads rename only on success, so a .partial is a transfer that died
    mid-flight -- invisible to a plain file count."""
    chunk(tmp_path, "EQUS.MINI", "ohlcv-1m", "2026-01")
    p = tmp_path / "EQUS.MINI" / "ohlcv-1m" / "2026-02.dbn.zst.partial"
    p.write_bytes(b"half")
    rows, partials, _ = A.scan(tmp_path)
    assert rows[0]["files"] == 1              # the partial is not counted
    assert len(partials) == 1
    assert "INTERRUPTED" in A.render(tmp_path, rows, partials, [], 100.0)


def test_zero_byte_files_are_surfaced_separately(tmp_path):
    """A zero-byte file satisfies every 'already on disk, skip it' check in the
    fetcher, so it would be skipped forever and the day never re-fetched."""
    chunk(tmp_path, "EQUS.MINI", "ohlcv-1m", "2026-01", 0)
    rows, _, empties = A.scan(tmp_path)
    assert rows[0]["files"] == 0
    assert len(empties) == 1
    assert "ZERO-BYTE" in A.render(tmp_path, rows, [], empties, 100.0)


def test_a_clean_archive_exits_zero_and_a_dirty_one_does_not(tmp_path, capsys):
    chunk(tmp_path, "EQUS.MINI", "ohlcv-1m", "2026-01")
    assert A.main(["--archive", str(tmp_path),
                   "--report", str(tmp_path / "r.txt")]) == 0
    (tmp_path / "EQUS.MINI" / "ohlcv-1m" / "x.dbn.zst.partial").write_bytes(b"h")
    assert A.main(["--archive", str(tmp_path),
                   "--report", str(tmp_path / "r.txt")]) == 1


def test_a_missing_archive_says_so_rather_than_reporting_an_empty_one(tmp_path):
    """An archive that is not there and an archive that is empty look identical
    in a table of zeroes, and only one of them means the pointer is wrong."""
    import pytest
    with pytest.raises(SystemExit, match="does not exist"):
        A.main(["--archive", str(tmp_path / "nope")])


def test_symbology_sidecars_are_not_counted_as_chunks(tmp_path):
    """ohlcv-1d directories hold a .symbology.json beside every chunk. Counting
    those would double every figure in the table."""
    chunk(tmp_path, "EQUS.MINI", "ohlcv-1d", "2026-01")
    (tmp_path / "EQUS.MINI" / "ohlcv-1d" / "2026-01.symbology.json").write_text("{}")
    rows, _, _ = A.scan(tmp_path)
    assert rows[0]["files"] == 1
