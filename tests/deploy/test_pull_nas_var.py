"""The NAS -> ProArt copy. Its job is to never lose or corrupt the fill record."""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy" / "nas_trader"))
import pull_nas_var as P  # noqa: E402


def _w(p: Path, text: str, mtime: float | None = None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if mtime:
        os.utime(p, (mtime, mtime))
    return p


@pytest.fixture
def dirs(tmp_path):
    src, dest, fills = tmp_path / "nas" / "var", tmp_path / "mirror", tmp_path / "var" / "fills"
    src.mkdir(parents=True)
    return src, dest, fills


def test_new_files_are_copied_and_unchanged_ones_skipped(dirs):
    src, dest, _ = dirs
    _w(src / "fills" / "mcl_fills_20261029.csv", "a,b\n1,2\n")
    out = []
    assert P.run(src, dest, out=out.append) == 0
    assert (dest / "fills" / "mcl_fills_20261029.csv").read_text() == "a,b\n1,2\n"
    out.clear()
    P.run(src, dest, out=out.append)
    assert any("copied    0" in l and "unchanged    1" in l for l in out)


def test_a_growing_file_is_recopied(dirs):
    src, dest, _ = dirs
    f = _w(src / "fills" / "x.csv", "1\n", mtime=1_000_000)
    P.run(src, dest, out=lambda s: None)
    _w(src / "fills" / "x.csv", "1\n2\n", mtime=1_000_100)
    P.run(src, dest, out=lambda s: None)
    assert (dest / "fills" / "x.csv").read_text() == "1\n2\n"


def test_nothing_is_ever_deleted_at_the_destination(dirs):
    src, dest, _ = dirs
    f = _w(src / "fills" / "old.csv", "keep me\n")
    P.run(src, dest, out=lambda s: None)
    f.unlink()
    P.run(src, dest, out=lambda s: None)
    assert (dest / "fills" / "old.csv").read_text() == "keep me\n"


def test_the_source_is_never_written(dirs):
    src, dest, _ = dirs
    _w(src / "fills" / "a.csv", "1\n")
    before = sorted((p.name, p.stat().st_mtime) for p in src.rglob("*"))
    P.run(src, dest, promote=True, local_fills=dest.parent / "lf", out=lambda s: None)
    assert sorted((p.name, p.stat().st_mtime) for p in src.rglob("*")) == before


def test_no_part_files_are_left_or_copied(dirs):
    src, dest, _ = dirs
    _w(src / "fills" / "a.csv", "1\n")
    _w(src / "fills" / "b.csv.part", "half")
    P.run(src, dest, out=lambda s: None)
    assert not list(dest.rglob("*.part"))
    assert not (dest / "fills" / "b.csv.part").exists()


def test_unreachable_source_exits_2_and_writes_nothing(tmp_path):
    out = []
    assert P.run(tmp_path / "nope", tmp_path / "mirror", out=out.append) == 2
    assert "CANNOT REACH" in out[0] and not (tmp_path / "mirror").exists()


def test_dry_run_writes_nothing(dirs):
    src, dest, _ = dirs
    _w(src / "fills" / "a.csv", "1\n")
    P.run(src, dest, dry_run=True, out=lambda s: None)
    assert not dest.exists()


def test_promote_copies_only_what_var_fills_lacks(dirs):
    src, dest, fills = dirs
    _w(src / "fills" / "mcl_fills_20261029.csv", "nas\n")
    assert P.run(src, dest, promote=True, local_fills=fills, out=lambda s: None) == 0
    assert (fills / "mcl_fills_20261029.csv").read_text() == "nas\n"


def test_promote_never_overwrites_a_different_local_file(dirs):
    """The shadow run: the PC and the NAS both wrote today's file."""
    src, dest, fills = dirs
    _w(src / "fills" / "mcl_fills_20261029.csv", "nas\n")
    _w(fills / "mcl_fills_20261029.csv", "pc\n")
    out = []
    assert P.run(src, dest, promote=True, local_fills=fills, out=out.append) == 1
    assert (fills / "mcl_fills_20261029.csv").read_text() == "pc\n"
    assert any("CONFLICT mcl_fills_20261029.csv" in l for l in out)


def test_promote_identical_local_file_is_not_a_conflict(dirs):
    src, dest, fills = dirs
    _w(src / "fills" / "a.csv", "same\n")
    _w(fills / "a.csv", "same\n")
    assert P.run(src, dest, promote=True, local_fills=fills, out=lambda s: None) == 0


def test_without_promote_var_fills_is_untouched(dirs):
    src, dest, fills = dirs
    _w(src / "fills" / "a.csv", "1\n")
    P.run(src, dest, out=lambda s: None)
    assert not fills.exists()


def test_main_needs_a_source(capsys):
    assert P.main([], {}) == 2
    assert "no source" in capsys.readouterr().err


def test_main_reads_the_source_from_the_environment(dirs, monkeypatch, tmp_path):
    src, dest, _ = dirs
    _w(src / "fills" / "a.csv", "1\n")
    assert P.main(["--dest", str(dest), "--log", str(tmp_path / "p.log")], {P.SOURCE_ENV: str(src)}) == 0
    assert (dest / "fills" / "a.csv").exists()


def test_main_appends_to_the_log_file(dirs, tmp_path):
    src, dest, _ = dirs
    _w(src / "fills" / "a.csv", "1\n")
    log = tmp_path / "logs" / "pull.log"
    assert P.main(["--dest", str(dest), "--log", str(log)], {P.SOURCE_ENV: str(src)}) == 0
    assert "copied" in log.read_text(encoding="utf-8")
    P.main(["--dest", str(dest), "--log", str(log)], {P.SOURCE_ENV: str(src)})
    assert log.read_text(encoding="utf-8").count("->") == 2, "appends, does not overwrite"


def test_an_unwritable_log_does_not_stop_the_copy(dirs, tmp_path):
    src, dest, _ = dirs
    _w(src / "fills" / "a.csv", "1\n")
    blocker = _w(tmp_path / "afile", "x")
    assert P.main(["--dest", str(dest), "--log", str(blocker / "sub" / "p.log")], {P.SOURCE_ENV: str(src)}) == 0
    assert (dest / "fills" / "a.csv").exists()
