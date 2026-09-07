#!/usr/bin/env python3
"""Finding the downloaded bundle.

The path to a downloaded bundle has been guessed wrong twice, and both times
the error read `does not appear to be a git repository` -- which sounds like a
corrupt bundle rather than a missing file. These tests pin the parts that make
that impossible: pick the newest, say what was picked, and fail with the
directories that were actually searched.
"""
from __future__ import annotations

import time

import pytest

from common import fetch_bundle as F


def touch(p, mtime=None):
    p.write_bytes(b"x")
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))
    return p


def test_the_newest_bundle_wins(tmp_path):
    now = time.time()
    touch(tmp_path / "algo-trading-20260901a.bundle", now - 86_400)
    new = touch(tmp_path / "algo-trading-20260907z.bundle", now)
    assert F.candidates([tmp_path])[0] == new.resolve()


def test_the_name_decides_nothing_the_mtime_does(tmp_path):
    """Bundle names are alphabetical within a day and roll over at 'z' to 'aa',
    which does NOT sort after 'z'. Sorting by name would have picked ab over ad
    today. The file's own timestamp cannot be fooled that way."""
    now = time.time()
    old = touch(tmp_path / "algo-trading-20260907z.bundle", now - 600)
    new = touch(tmp_path / "algo-trading-20260907ab.bundle", now)
    got = F.candidates([tmp_path])
    assert got[0] == new.resolve() and got[1] == old.resolve()


def test_other_files_are_ignored(tmp_path):
    touch(tmp_path / "notes.txt")
    touch(tmp_path / "something-else.bundle")
    assert F.candidates([tmp_path]) == []


def test_the_same_file_reached_two_ways_is_listed_once(tmp_path):
    b = touch(tmp_path / "algo-trading-20260907a.bundle")
    assert F.candidates([tmp_path, tmp_path]) == [b.resolve()]


def test_a_missing_directory_is_not_an_error(tmp_path):
    assert F.candidates([tmp_path / "nope"]) == []


def test_nothing_found_lists_where_it_looked(tmp_path, capsys):
    rc = F.main(["--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert str(tmp_path) in out
    assert "Download the bundle from the chat first" in out


def test_an_explicit_file_that_is_absent_says_so(tmp_path, capsys):
    rc = F.main(["--file", str(tmp_path / "gone.bundle")])
    assert rc == 1 and "does not exist" in capsys.readouterr().out


def test_a_corrupt_bundle_is_refused_before_the_fetch(tmp_path, capsys):
    """`git bundle verify` distinguishes a truncated download from a bundle
    whose base commits are missing. Fetch alone reports both the same way."""
    bad = touch(tmp_path / "algo-trading-20260907a.bundle")
    rc = F.main(["--file", str(bad)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "did not verify" in out
    assert "download was incomplete" in out


def test_age_is_reported_in_units_a_person_reads(tmp_path):
    now = time.time()
    assert "minutes" in F.age(touch(tmp_path / "a.bundle", now - 300))
    assert "hours" in F.age(touch(tmp_path / "b.bundle", now - 7200))
    assert "days" in F.age(touch(tmp_path / "c.bundle", now - 86_400 * 3))


def test_a_dirty_tree_stops_the_merge_rather_than_half_doing_it(monkeypatch,
                                                                tmp_path,
                                                                capsys):
    """A merge onto uncommitted work fails halfway and leaves a state that
    needs git knowledge to escape. Refusing is kinder than starting."""
    b = touch(tmp_path / "algo-trading-20260907a.bundle")
    calls = []

    def fake_git(*args, **kw):
        calls.append(args)
        import subprocess
        rc = 0
        out = ""
        if args[0] == "status":
            out = " M common/thing.py\n"
        return subprocess.CompletedProcess(args, rc, out, "")

    monkeypatch.setattr(F, "git", fake_git)
    rc = F.main(["--file", str(b)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "NOT merging" in out and "common/thing.py" in out
    assert ("merge", "FETCH_HEAD") not in calls
