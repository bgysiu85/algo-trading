#!/usr/bin/env python3
"""What is running, and where it writes.

A frozen production copy runs the sessions while development continues in the
working tree (Ben, 2026-09-11). That shape creates two hazards, and both are
INVISIBLE while they are hurting you:

  1. `session_lock.LOCK_PATH` is a RELATIVE path, so two trees resolve two
     different lock files and the lock stops protecting the shared IB account.
     The supported fix is a Windows junction — which fails silently if it is
     missing, wrong, or replaced by an ordinary folder during a copy.
  2. A production tree with uncommitted edits looks exactly like a production
     tree. Code cannot be read for frozen-ness.

`test_two_trees_with_separate_var_are_caught` and
`test_a_junction_counts_as_shared_because_the_path_is_RESOLVED` are the
headline tests.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from common import provenance as P
from common import session_lock


# --- the hazard the whole module exists for ---------------------------------

def test_the_session_lock_is_cwd_relative_which_is_why_this_module_exists():
    """If this ever becomes absolute, the junction requirement goes away and
    this module's main warning should be rewritten. Pinning it here means the
    docs and the code cannot drift apart silently."""
    assert not session_lock.LOCK_PATH.is_absolute()
    assert str(session_lock.LOCK_PATH).replace("\\", "/") \
        == "var/state/session.lock"


def test_two_trees_with_separate_var_are_caught(tmp_path, monkeypatch):
    """THE ONE THAT MATTERS. Production in D:\\TradingProd and development in
    D:\\Trading, each with its own var/, means two session locks — and nothing
    stops two live sessions on one IB account."""
    prod = tmp_path / "TradingProd"
    dev = tmp_path / "Trading"
    (prod / "var").mkdir(parents=True)
    (dev / "var").mkdir(parents=True)
    monkeypatch.chdir(prod)
    ok, why = P.shared_var(dev / "var")
    assert not ok
    assert "its own session lock" in why


def test_a_junction_counts_as_shared_because_the_path_is_RESOLVED(tmp_path,
                                                                  monkeypatch):
    """A junction or symlink IS the supported way to run two trees against one
    ledger. Comparing the configured strings would call a correct junction a
    mismatch and a broken one fine — exactly backwards."""
    dev = tmp_path / "Trading"
    (dev / "var").mkdir(parents=True)
    prod = tmp_path / "TradingProd"
    prod.mkdir()
    try:
        (prod / "var").symlink_to(dev / "var", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform will not create a directory symlink here")
    monkeypatch.chdir(prod)
    ok, why = P.shared_var(dev / "var")
    assert ok, why


def test_a_missing_var_is_reported_and_not_treated_as_shared(tmp_path,
                                                             monkeypatch):
    dev = tmp_path / "Trading"
    (dev / "var").mkdir(parents=True)
    prod = tmp_path / "TradingProd"
    prod.mkdir()
    monkeypatch.chdir(prod)
    ok, why = P.shared_var(dev / "var")
    assert not ok and "does not exist" in why


def test_an_absent_expected_target_is_not_silently_ok(tmp_path, monkeypatch):
    """Pointing the check at a path that does not exist must fail loudly. A
    typo'd expectation that passed would be worse than no check."""
    prod = tmp_path / "TradingProd"
    (prod / "var").mkdir(parents=True)
    monkeypatch.chdir(prod)
    ok, why = P.shared_var(tmp_path / "nope" / "var")
    assert not ok and "expected shared var" in why


def test_the_comparison_is_case_insensitive(tmp_path, monkeypatch):
    """Windows paths are, and D:\\Trading\\var and d:\\trading\\var are one
    directory. A case-sensitive check would report a false mismatch on the
    platform this actually runs on."""
    dev = tmp_path / "Trading"
    (dev / "var").mkdir(parents=True)
    monkeypatch.chdir(dev)
    ok, _ = P.shared_var(str(dev / "var").swapcase()
                         if os.path.normcase("A") == os.path.normcase("a")
                         else dev / "var")
    # On a case-insensitive filesystem the swapcased path resolves to the same
    # directory; on a case-sensitive one the swapcase would be a different
    # path, so the test only asserts the platform's own rule.
    assert ok or os.path.normcase("A") != os.path.normcase("a")


# --- var/ is CWD-relative, the tree is FILE-relative -------------------------

def test_var_follows_the_working_directory_and_the_tree_does_not(tmp_path,
                                                                 monkeypatch):
    """The two answers a two-tree setup needs are different questions: WHERE
    WILL THIS WRITE (cwd) and WHICH CODE IS THIS (the file's own location). A
    module that answered both the same way would be useless for either."""
    elsewhere = tmp_path / "somewhere"
    (elsewhere / "var").mkdir(parents=True)
    monkeypatch.chdir(elsewhere)
    p = P.read()
    assert Path(p.var_path) == (elsewhere / "var").resolve()
    assert Path(p.tree) == P.TREE, "the tree moved with the cwd"


def test_the_tree_is_the_repo_root_not_the_common_package():
    assert (P.TREE / "common" / "provenance.py").exists()
    assert (P.TREE / "main.py").exists()


# --- git, and its absence ----------------------------------------------------

def test_a_tree_with_no_git_reports_that_rather_than_raising(tmp_path,
                                                             monkeypatch):
    """A production copy may be a clone, a worktree, or a plain folder copy
    with no .git at all. All three are legitimate, so no-git is a state to
    report and not an error — and it must not read as 'clean'."""
    bare = tmp_path / "copied"
    (bare / "var").mkdir(parents=True)
    monkeypatch.chdir(bare)
    p = P.read(tree=bare)
    assert p.commit == "" and p.described == ""
    assert p.dirty is False
    assert "no git in this tree" in "\n".join(P.render(p))


def test_dirty_is_only_asserted_when_git_actually_answered():
    """`git status --porcelain` returns "" for a clean tree AND for no git at
    all. Reading the empty string as clean would report an unknown tree as
    frozen, which is the wrong direction to be wrong in."""
    import inspect
    src = inspect.getsource(P.read)
    assert "have_git" in src
    assert "bool(have_git and status)" in src


def test_the_real_repo_reports_a_commit():
    """Vacuous-guard: if git were unavailable in this environment every test
    above would pass without exercising anything."""
    p = P.read()
    if not p.commit:
        pytest.skip("no git available in this environment")
    assert len(p.commit) >= 6


# --- the one-line form, which is what a session header can carry ------------

def test_the_line_names_the_version_and_the_var_it_will_write_to():
    p = P.read()
    line = p.as_line()
    assert "var=" in line and "tree=" in line


def test_a_dirty_tree_says_so_in_the_line_and_in_the_report():
    """The point of a frozen copy is that it is frozen, and an edit made in the
    wrong window is undetectable by reading the code."""
    p = P.Provenance(tree="/x", cwd="/x", commit="abc1234",
                     described="prod-20260911-2-gabc1234-dirty", branch="main",
                     dirty=True, var_path="/x/var", var_exists=True)
    assert "DIRTY" in p.as_line()
    out = "\n".join(P.render(p))
    assert "NOT frozen" in out and "exists on no" in out


def test_a_clean_tree_carries_no_warning():
    p = P.Provenance(tree="/x", cwd="/x", commit="abc1234",
                     described="prod-20260911", branch="main", dirty=False,
                     var_path="/x/var", var_exists=True)
    assert "DIRTY" not in p.as_line()
    assert "NOT frozen" not in "\n".join(P.render(p))


# --- the CLI -----------------------------------------------------------------

def test_the_check_exits_nonzero_on_a_split_var(tmp_path, monkeypatch, capsys):
    """So a wrapper can refuse to start a session on it. This module reports;
    the exit code is what lets something else act."""
    prod = tmp_path / "TradingProd"
    dev = tmp_path / "Trading"
    (prod / "var").mkdir(parents=True)
    (dev / "var").mkdir(parents=True)
    monkeypatch.chdir(prod)
    rc = P.main(["--expect-shared-var", str(dev / "var")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "WRONG" in out and "same IB account" in out


def test_the_check_exits_zero_when_var_is_the_expected_one(tmp_path,
                                                           monkeypatch, capsys):
    dev = tmp_path / "Trading"
    (dev / "var").mkdir(parents=True)
    monkeypatch.chdir(dev)
    assert P.main(["--expect-shared-var", str(dev / "var")]) == 0
    assert "OK" in capsys.readouterr().out


def test_plain_invocation_never_fails(tmp_path, monkeypatch):
    """It is the first thing anyone will run in a new production copy, quite
    possibly before var/ exists. Reporting that is the job; raising is not."""
    empty = tmp_path / "fresh"
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert P.main([]) == 0


# --- wired into the session, which is the only place it matters -------------

def test_the_lock_records_which_tree_holds_it(tmp_path):
    """With two trees, 'a live session is already running' is half an answer.
    The useful half is WHERE, because that is what tells Ben whether to stop it
    or whether he is about to start a second one from the wrong window."""
    lock = tmp_path / "session.lock"
    with session_lock.held("paper", "mcl", path=lock,
                           tree="D:\\TradingProd", version="prod-20260911",
                           dirty=False, var="D:\\Trading\\var") as info:
        assert info["tree"] == "D:\\TradingProd"
        desc = session_lock.describe(session_lock.read(lock))
    assert "running from D:\\TradingProd" in desc
    assert "prod-20260911" in desc


def test_describe_still_works_on_a_lock_written_before_this(tmp_path):
    """Locks on disk right now have no `tree`. Reading one must not raise —
    the first thing this change could break is the guard it is decorating."""
    desc = session_lock.describe({"mode": "paper", "strategy": "mcl",
                                  "pid": 1, "started_at": "2026-09-10"})
    assert "paper session" in desc and "running from" not in desc


def test_main_stamps_the_session_and_puts_it_in_the_lock():
    """A stamp that is computed and not recorded is decoration."""
    import inspect
    import main as M
    src = inspect.getsource(M)
    assert "provenance.read()" in src
    assert "tree=prov.tree" in src and "version=prov.described" in src


def test_main_warns_when_the_trading_tree_is_dirty():
    import inspect
    import main as M
    # The warning wraps across two source lines, so assert on a contiguous
    # fragment rather than the sentence — the first version of this test
    # failed on its own line break.
    src = inspect.getsource(M)
    assert "uncommitted changes" in src and "frozen copy." in src
