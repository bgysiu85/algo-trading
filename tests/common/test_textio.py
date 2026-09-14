#!/usr/bin/env python3
r"""Two generations of fill log in one directory, and every reader of both.

`FillLog` opened the log with no `encoding=` and used the locale default --
cp1252 on Ben's machine. One non-ASCII byte in `reject_reason` made the FILE
undecodable to every UTF-8 reader from that byte onward. The writer was fixed
on 2026-09-14.

FIXING THE WRITER DOES NOT FIX THE CORPUS. Every log already on disk is cp1252
and every new one is UTF-8, so `var/fills/` now holds both under one naming
convention, and there is no single encoding that reads both. That is what these
tests are about: not "does it read UTF-8", but "does it read the directory".
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from common import textio as T

# An em dash, which is what a CONFIG row put into reject_reason and the byte
# that surfaced this. 0x97 in cp1252; 0xE2 0x80 0x94 in UTF-8.
DASH = "—"
HEADER = "ts_et,symbol,status,reject_reason"
ROW = f"2026-09-14 06:21:00,WYHG,REJECTED,trail 5.0 {DASH} 9.0"


def log(tmp_path, encoding, name="mcl_fills_20260914.csv") -> Path:
    p = tmp_path / name
    p.write_bytes(f"{HEADER}\n{ROW}\n".encode(encoding))
    return p


# --- the decoder ------------------------------------------------------------

def test_a_utf8_file_reads_as_utf8(tmp_path):
    rows, enc = T.read_csv(log(tmp_path, "utf-8"))
    assert enc == T.PREFERRED
    assert rows[0]["reject_reason"].endswith(f"5.0 {DASH} 9.0")


def test_a_cp1252_file_reads_as_cp1252(tmp_path):
    rows, enc = T.read_csv(log(tmp_path, "cp1252"))
    assert enc == T.LEGACY
    assert rows[0]["reject_reason"].endswith(f"5.0 {DASH} 9.0")


def test_utf8_is_tried_first_and_that_ordering_is_the_whole_trick(tmp_path):
    r"""cp1252 decodes almost any byte sequence, so trying IT first would
    always succeed and would turn every UTF-8 file into mojibake. UTF-8
    validates, so a cp1252 file fails it and the fallback is reached. The two
    orders are not symmetric and this is the asymmetry."""
    raw = f"{HEADER}\n{ROW}\n".encode("utf-8")
    assert raw.decode(T.LEGACY) != raw.decode("utf-8"), (
        "the fixture no longer distinguishes the two orders")
    text, enc = T.decode(raw)
    assert enc == T.PREFERRED and DASH in text


def test_a_bom_is_stripped_not_read_as_a_column_name(tmp_path):
    """Excel writes one, and Ben opens these in Excel. A BOM left on the front
    turns `ts_et` into `﻿ts_et` and every lookup by name misses."""
    p = tmp_path / "f.csv"
    p.write_bytes(f"{HEADER}\n{ROW}\n".encode("utf-8-sig"))
    rows, _ = T.read_csv(p)
    assert "ts_et" in rows[0]


def test_an_ascii_file_is_identical_either_way(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text("a,b\n1,2\n")
    assert T.read_csv(p)[0] == [{"a": "1", "b": "2"}]


def test_the_encoding_is_returned_not_only_applied(tmp_path):
    """A caller that needs to say which generation it read can say so rather
    than infer it -- the distinction this project keeps losing."""
    assert T.read_text(log(tmp_path, "cp1252"))[1] == T.LEGACY
    assert T.read_text(log(tmp_path, "utf-8"))[1] == T.PREFERRED


def test_a_header_can_be_read_without_the_body(tmp_path):
    fields, enc = T.read_header(log(tmp_path, "cp1252"))
    assert fields == HEADER.split(",") and enc == T.LEGACY


def test_an_empty_file_yields_no_header_rather_than_raising(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_bytes(b"")
    assert T.read_header(p)[0] == []


# --- what the naive readers did, kept as the evidence -----------------------

def test_strict_utf8_raises_on_the_legacy_generation(tmp_path):
    """`churn_count` (pandas defaults to UTF-8 whatever the locale) and
    `tv_reconcile` were both strict. This is what they did to every log
    written before 2026-09-14."""
    with pytest.raises(UnicodeDecodeError):
        log(tmp_path, "cp1252").read_bytes().decode("utf-8")


def test_cp1252_mojibakes_the_new_generation_without_raising(tmp_path):
    """And this is the other half, which is worse: `friction` and
    `db_load.load_paper_fills` used the LOCALE default, so on Ben's machine
    the new logs come back wrong with nothing raised at all."""
    got = log(tmp_path, "utf-8").read_bytes().decode("cp1252")
    assert DASH not in got and "â" in got


# --- every reader, over a directory holding BOTH generations ----------------

FULL = ("ts_et,strategy,symbol,action,status,reason,ref_close,ref_kind,"
        "slippage_vs_ref,filled_qty,qty,trade_pnl,hold_minutes,reject_reason")


def full_log(tmp_path, encoding, day="20260914", extra=""):
    p = tmp_path / f"mcl_fills_{day}{extra}.csv"
    body = (f"{FULL}\n"
            f"{day[:4]}-{day[4:6]}-{day[6:]} 06:21:00,MCL,WYHG,BUY,FILLED,"
            f"entry_signal,5.21,signal_close,-0.01,100,100,,,in {DASH} out\n"
            f"{day[:4]}-{day[4:6]}-{day[6:]} 06:23:00,MCL,WYHG,SELL,FILLED,"
            f"trailing_stop,5.30,bar_close,-0.02,100,100,-3.5,2.0,\n")
    p.write_bytes(body.encode(encoding))
    return p


def mixed_dir(tmp_path):
    """The directory as it now is: one generation each, side by side."""
    d = tmp_path / "fills"
    d.mkdir()
    full_log(d, "cp1252", "20260913")
    full_log(d, "utf-8", "20260914")
    return d


def test_friction_reads_a_directory_holding_both_generations(tmp_path):
    from common import friction
    by_session = friction.load(None, mixed_dir(tmp_path))
    assert sorted(by_session) == ["20260913", "20260914"]
    for day, rows in by_session.items():
        assert rows, f"{day} loaded no usable rows"


def test_churn_count_reads_both_generations(tmp_path):
    from common import churn_count
    d = mixed_dir(tmp_path)
    for p in sorted(d.glob("*.csv")):
        got, _derived = churn_count.load(p)
        assert len(got) == 2, f"{p.name} did not load"


def test_tv_reconcile_reads_both_generations(tmp_path):
    from common import tv_reconcile
    d = mixed_dir(tmp_path)
    for p in sorted(d.glob("*.csv")):
        assert len(tv_reconcile.load_fills(p)) == 2, f"{p.name} did not load"


def test_the_database_loader_reads_both_generations(tmp_path):
    from sqlalchemy import create_engine, func, select

    from common import db as D
    from common import db_load as L
    eng = create_engine("sqlite://")
    D.META.create_all(eng)
    d = mixed_dir(tmp_path)
    with eng.begin() as c:
        n, days = L.load_paper_fills(c, sorted(d.glob("*.csv")))
    assert days == ["2026-09-13", "2026-09-14"]
    assert n == 4
    with eng.connect() as c:
        got = c.execute(select(D.paper_fill.c.reject_reason)
                        .where(D.paper_fill.c.action == "BUY")).scalars().all()
    assert all(DASH in g for g in got), (
        "an em dash reached the database as mojibake -- a CSV can be re-read, "
        "a loaded row cannot be un-corrupted")


def test_the_readers_do_not_open_text_without_naming_an_encoding():
    r"""THE GUARD FOR THE CLASS, NOT THE INSTANCE.

    Every one of these four found the same defect independently, and the next
    reader written will too unless the omission is visible. `open()` with no
    `encoding=` is a silent dependency on the machine's locale, and this
    project runs the same file on a cp1252 box and a utf-8 one.
    """
    import ast
    for name in ("friction", "churn_count", "tv_reconcile", "db_load",
                 "textio"):
        src = Path(f"common/{name}.py")
        tree = ast.parse(src.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            fname = (f.id if isinstance(f, ast.Name)
                     else f.attr if isinstance(f, ast.Attribute) else "")
            if fname != "open":
                continue
            kw = {k.arg for k in node.keywords}
            if "encoding" in kw:
                continue
            mode = ""
            if isinstance(f, ast.Attribute) and node.args:
                a = node.args[0]
                mode = a.value if isinstance(a, ast.Constant) else ""
            elif len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            assert "b" in str(mode), (
                f"common/{name}.py line {node.lineno}: open() in text mode "
                f"with no encoding= -- it will use the machine's locale")


def test_pandas_read_csv_is_not_handed_a_path_in_the_fill_readers():
    r"""pandas ignores the locale and defaults to UTF-8, so `read_csv(path)` is
    the strict-UTF-8 half of this defect with no `encoding=` to notice.

    Checked on the PARSED CALL, not on the source text. The first version of
    this test looked for the substring `pd.read_csv(path)` and failed on the
    comment that explains why the call is not there -- a guard that cannot
    tell code from prose about code, which is the third time that shape has
    turned up in this repo.
    """
    import ast
    tree = ast.parse(Path("common/churn_count.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "read_csv"):
            arg = node.args[0] if node.args else None
            assert not (isinstance(arg, ast.Name) and arg.id == "path"), (
                f"line {node.lineno}: pandas is being handed the path, so it "
                f"decodes as strict UTF-8 and raises on every legacy log")
