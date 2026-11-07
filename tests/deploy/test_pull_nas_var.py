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


HEADER = ("ts_et,strategy,symbol,action,reason,ref_close,ref_kind,bid,ask,spread,spread_pct,limit_sent,qty,"
          "fill_price,filled_qty,status,slippage_vs_ref,seconds_to_fill,entry_price,exit_price,trade_pnl,"
          "trade_pct,hold_minutes,reject_reason,macd,macd_sig,mfi,rsi,vol,prev_vol,trail_avg,trail_pct,"
          "ref_drift_pct,exec_id\n")


def _config_row(dry: bool) -> str:
    return (f"2026-11-02 01:00:10,,,CONFIG,session_open,,,,,,,,,,,APPLIED,,,,,,,,"
            f"max_positions=3 cap_scope=strategy strategies=MCL+MC5 dry_run={dry} bridge=off,,,,,,,,,,\n")


def _buy_row(status: str) -> str:
    return (f"2026-11-02 04:06:00,MC5,CLRO,BUY,entry_signal,5.85,signal_close,5.74,5.78,0.04,0.69,5.8,100,"
            f"5.8,100,{status},0.05,,,,,,,,0.009,-0.009,,68.2,774865,,,5.0,-1.5,\n")


def test_promote_skips_a_dry_session_file_marked_by_its_config_row(dirs):
    src, dest, fills = dirs
    _w(src / "fills" / "mcl_fills_20261102.csv", HEADER + _config_row(True))
    out = []
    assert P.run(src, dest, promote=True, local_fills=fills, out=out.append) == 0
    assert not (fills / "mcl_fills_20261102.csv").exists()
    assert (dest / "fills" / "mcl_fills_20261102.csv").exists()          # still mirrored
    assert any("SKIPPED" in l and "mcl_fills_20261102.csv (dry)" in l for l in out)
    assert any("promote  0 new fill file(s)" in l for l in out)


def test_promote_skips_a_file_whose_order_rows_are_dry(dirs):
    src, dest, fills = dirs
    _w(src / "fills" / "a.csv", HEADER + _buy_row("DRY_RUN"))
    P.run(src, dest, promote=True, local_fills=fills, out=lambda s: None)
    assert not (fills / "a.csv").exists()


def test_promote_still_copies_a_paper_session_file(dirs):
    src, dest, fills = dirs
    _w(src / "fills" / "mcl_fills_20261109.csv", HEADER + _config_row(False) + _buy_row("FILLED"))
    out = []
    assert P.run(src, dest, promote=True, local_fills=fills, out=out.append) == 0
    assert (fills / "mcl_fills_20261109.csv").exists()
    assert not any("SKIPPED" in l for l in out)


def test_promote_skips_a_file_that_mixes_dry_and_paper_rows(dirs):
    src, dest, fills = dirs
    _w(src / "fills" / "mixed.csv", HEADER + _config_row(True) + _config_row(False) + _buy_row("FILLED"))
    P.run(src, dest, promote=True, local_fills=fills, out=lambda s: None)
    assert not (fills / "mixed.csv").exists()


def test_a_skipped_dry_file_is_not_reported_as_a_conflict(dirs):
    """Shadow-run days: the PC copy and the NAS copy differ. Dry files are out of scope, so no CONFLICT."""
    src, dest, fills = dirs
    _w(src / "fills" / "d.csv", HEADER + _config_row(True))
    _w(fills / "d.csv", "pc\n")
    out = []
    assert P.run(src, dest, promote=True, local_fills=fills, out=out.append) == 0
    assert (fills / "d.csv").read_text() == "pc\n"
    assert not any("CONFLICT" in l for l in out)


def test_an_unreadable_file_is_skipped_not_promoted(dirs):
    src, dest, fills = dirs
    bad = src / "fills" / "bad.csv"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"\xff\xfe\x00\x80 not utf-8\n")
    out = []
    assert P.run(src, dest, promote=True, local_fills=fills, out=out.append) == 0
    assert not (fills / "bad.csv").exists()
    assert any("bad.csv (unreadable)" in l for l in out)


def test_dry_session_reason_unit(tmp_path):
    assert P.dry_session_reason(_w(tmp_path / "x.csv", HEADER + _config_row(True))) == "dry"
    assert P.dry_session_reason(_w(tmp_path / "y.csv", HEADER + _config_row(False))) is None
    assert P.dry_session_reason(_w(tmp_path / "z.csv", "")) is None
