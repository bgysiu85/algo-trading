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


@pytest.fixture(autouse=True)
def a_machine_that_already_has_bundles_lying_around(tmp_path_factory,
                                                    monkeypatch):
    """Run every test on a machine that ALREADY has stray bundles.

    Six tests here passed in an empty sandbox and failed on Ben's, where 25
    real bundles sit in the directories this module searches by design. The
    tests were asserting on the absence of files elsewhere on the machine --
    a condition no real machine satisfies.

    So the fixture plants decoys in the places SEARCH looks. A test that
    forgets to scope its search now fails HERE, the way it would there.
    """
    home = tmp_path_factory.mktemp("home")
    (home / "Downloads").mkdir()
    (home / "Downloads" / "algo-trading-20260101a.bundle").write_bytes(b"decoy")
    work = tmp_path_factory.mktemp("cwd")
    (work / "Claude outputs").mkdir()
    (work / "Claude outputs" / "algo-trading-20260101b.bundle").write_bytes(b"d")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(work)
    return home


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
    assert F.candidates([tmp_path], search=[])[0] == new.resolve()


def test_the_name_decides_nothing_the_mtime_does(tmp_path):
    """Bundle names are alphabetical within a day and roll over at 'z' to 'aa',
    which does NOT sort after 'z'. Sorting by name would have picked ab over ad
    today. The file's own timestamp cannot be fooled that way."""
    now = time.time()
    old = touch(tmp_path / "algo-trading-20260907z.bundle", now - 600)
    new = touch(tmp_path / "algo-trading-20260907ab.bundle", now)
    got = F.candidates([tmp_path], search=[])
    assert got[0] == new.resolve() and got[1] == old.resolve()


def test_other_files_are_ignored(tmp_path):
    touch(tmp_path / "notes.txt")
    touch(tmp_path / "something-else.bundle")
    assert F.candidates([tmp_path], search=[]) == []


def test_the_same_file_reached_two_ways_is_listed_once(tmp_path):
    b = touch(tmp_path / "algo-trading-20260907a.bundle")
    assert F.candidates([tmp_path, tmp_path], search=[]) == [b.resolve()]


def test_a_missing_directory_is_not_an_error(tmp_path):
    assert F.candidates([tmp_path / "nope"], search=[]) == []


def test_nothing_found_lists_where_it_looked(tmp_path, capsys):
    rc = F.main(["--dir", str(tmp_path), "--only"])
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


def test_the_claude_outputs_folder_is_searched_first(tmp_path, monkeypatch):
    """That folder is where files from a Claude session are put, and it is
    already gitignored. If it stops being searched, every handover goes back to
    someone typing a path with a space in it."""
    assert F.SEARCH[0].lower() == "claude outputs"
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "Claude outputs"
    d.mkdir()
    b = touch(d / "algo-trading-20260907a.bundle")
    # SEARCH is scoped to the two spellings: the real list also reaches
    # ~/Downloads, and a test must not depend on what is sitting there.
    only = F.SEARCH[:2]
    assert F.candidates(search=only)[0] == b.resolve()


def test_the_two_spellings_are_not_two_results(tmp_path, monkeypatch):
    """Windows treats them as one directory, Linux as two. Listing both must
    not make one file look like two bundles."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Claude outputs").mkdir()
    touch(tmp_path / "Claude outputs" / "algo-trading-20260907a.bundle")
    assert len(F.candidates(search=F.SEARCH[:2])) == 1


# --- what counts as "too dirty to merge" ------------------------------------
#
# On 2026-09-08 a merge was refused with "you have uncommitted changes: ??
# bar_cache_xnas/" and the instruction to commit or stash it. That directory is
# 28k generated bar files. Committing it would put machine-local derived data
# in the repo; stashing it does nothing, because `git stash` leaves untracked
# files alone by default. The advice was unfollowable and the refusal was
# unnecessary -- an untracked file cannot break a merge unless the merge would
# overwrite it, and git detects that case itself.

def _repo(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v], check=True)
    (tmp_path / "tracked.txt").write_text("one\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"],
                   check=True)
    return tmp_path


def test_an_untracked_build_output_does_not_block_the_merge(tmp_path,
                                                            monkeypatch):
    repo = _repo(tmp_path / "r")
    (repo / "bar_cache_xnas").mkdir()
    (repo / "bar_cache_xnas" / "AAA_2026-01-07.csv.gz").write_bytes(b"x")
    monkeypatch.chdir(repo)
    assert F.dirty() == []


def test_an_uncommitted_edit_to_a_tracked_file_still_blocks_it(tmp_path,
                                                               monkeypatch):
    """The refusal exists for THIS case and must survive the fix: a merge onto
    uncommitted edits fails halfway and leaves a state that needs git knowledge
    to get out of."""
    repo = _repo(tmp_path / "r")
    (repo / "tracked.txt").write_text("two\n")
    monkeypatch.chdir(repo)
    assert F.dirty() == [" M tracked.txt"]


def test_a_staged_addition_still_blocks_it(tmp_path, monkeypatch):
    import subprocess
    repo = _repo(tmp_path / "r")
    (repo / "new.txt").write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "new.txt"], check=True)
    monkeypatch.chdir(repo)
    assert F.dirty() == ["A  new.txt"]


# --- the cache roots the repo must never swallow ----------------------------

def test_every_databento_cache_root_is_ignored():
    """`--out bar_cache_xnas` created an untracked directory of ~28k generated
    files in the repo because only `bar_cache_db/` was named. The pattern has
    to cover the root a future tape will use, before that root exists."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    # Trailing slashes are required, not cosmetic: the pattern ends in "/" so
    # it matches directories only, and check-ignore cannot tell what a path
    # that does not exist yet would be without them.
    for name in ("bar_cache_db/", "bar_cache_xnas/", "bar_cache_arcx/",
                 "bar_cache_db/3d_to_2000/AAA_2026-01-07.csv.gz"):
        r = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", name])
        assert r.returncode == 0, f"{name} is NOT gitignored"


def test_the_ib_cache_is_ignored_under_its_own_rule():
    """bar_cache/ holds SPLIT-ADJUSTED IB bars. It is covered by its own line,
    not by the databento glob -- the two price bases stay distinguishable in
    the ignore file as well as on disk."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run(["git", "-C", str(root), "check-ignore", "-v", "bar_cache/"],
                       text=True, capture_output=True)
    assert r.returncode == 0
    assert "bar_cache_*/" not in r.stdout
