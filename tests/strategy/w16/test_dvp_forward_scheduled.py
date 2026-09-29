#!/usr/bin/env python3
"""W16-0014's Task Scheduler wrapper: runs dvp_forward --confirm unattended,
then commits+pushes the ledger only if it actually changed. Every scenario
here fakes both moving parts (F.main and the module's own _git helper) so
no real subprocess, git repo or network call ever happens."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import strategy.w16.dvp_forward_scheduled as S


@pytest.fixture(autouse=True)
def _log_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "LOG_PATH", tmp_path / "w16_0014_weekly_log.txt")


def _proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_git(sequence):
    """Returns a stand-in for S._git that pops one canned result per call,
    and records the argv it was called with."""
    calls = []

    def _git(args):
        calls.append(list(args))
        return sequence[len(calls) - 1]

    return _git, calls


def test_ledger_unchanged_does_nothing_beyond_status(monkeypatch):
    monkeypatch.setattr(S.F, "main", lambda argv: 0)
    fake_git, calls = _fake_git([_proc(stdout="")])  # git status: clean
    monkeypatch.setattr(S, "_git", fake_git)

    rc = S.main()

    assert rc == 0
    assert len(calls) == 1
    assert calls[0][:2] == ["status", "--porcelain"]
    log = S.LOG_PATH.read_text(encoding="utf-8")
    assert "scheduled run starting" in log
    assert "ledger unchanged" in log
    assert "scheduled run finished" in log


def test_ledger_changed_adds_commits_and_pushes(monkeypatch):
    monkeypatch.setattr(S.F, "main", lambda argv: 0)
    fake_git, calls = _fake_git([
        _proc(stdout=" M w16_dvp_forward_ledger.json\n"),  # status: dirty
        _proc(),                                            # add
        _proc(stdout="[main abc1234] W16-0014...\n"),        # commit
        _proc(stdout="done\n"),                              # push
    ])
    monkeypatch.setattr(S, "_git", fake_git)

    rc = S.main()

    assert rc == 0
    assert [c[0] for c in calls] == ["status", "add", "commit", "push"]
    assert calls[1] == ["add", S.LEDGER_NAME]
    assert calls[2][0] == "commit"
    assert "-m" in calls[2]
    msg = calls[2][calls[2].index("-m") + 1]
    assert "W16-0014" in msg and "scheduled" in msg
    log = S.LOG_PATH.read_text(encoding="utf-8")
    assert "commit: rc=0" in log
    assert "push: rc=0" in log


def test_git_status_failure_stops_before_any_commit(monkeypatch):
    monkeypatch.setattr(S.F, "main", lambda argv: 0)
    fake_git, calls = _fake_git([_proc(returncode=1, stderr="not a git repo")])
    monkeypatch.setattr(S, "_git", fake_git)

    rc = S.main()

    assert rc == 1
    assert len(calls) == 1
    assert "git status failed" in S.LOG_PATH.read_text(encoding="utf-8")


def test_git_add_failure_returns_1_and_does_not_commit(monkeypatch):
    monkeypatch.setattr(S.F, "main", lambda argv: 0)
    fake_git, calls = _fake_git([
        _proc(stdout=" M w16_dvp_forward_ledger.json\n"),
        _proc(returncode=1, stderr="add exploded"),
    ])
    monkeypatch.setattr(S, "_git", fake_git)

    rc = S.main()

    assert rc == 1
    assert [c[0] for c in calls] == ["status", "add"]
    assert "git add failed" in S.LOG_PATH.read_text(encoding="utf-8")


def test_git_commit_failure_returns_1_and_does_not_push(monkeypatch):
    monkeypatch.setattr(S.F, "main", lambda argv: 0)
    fake_git, calls = _fake_git([
        _proc(stdout=" M w16_dvp_forward_ledger.json\n"),
        _proc(),
        _proc(returncode=1, stderr="nothing to commit"),
    ])
    monkeypatch.setattr(S, "_git", fake_git)

    rc = S.main()

    assert rc == 1
    assert [c[0] for c in calls] == ["status", "add", "commit"]
    assert "commit failed" in S.LOG_PATH.read_text(encoding="utf-8")


def test_git_push_failure_returns_1_even_though_commit_landed(monkeypatch):
    monkeypatch.setattr(S.F, "main", lambda argv: 0)
    fake_git, calls = _fake_git([
        _proc(stdout=" M w16_dvp_forward_ledger.json\n"),
        _proc(),
        _proc(stdout="[main abc1234] ...\n"),
        _proc(returncode=1, stderr="could not resolve host"),
    ])
    monkeypatch.setattr(S, "_git", fake_git)

    rc = S.main()

    assert rc == 1
    assert [c[0] for c in calls] == ["status", "add", "commit", "push"]
    log = S.LOG_PATH.read_text(encoding="utf-8")
    assert "push: rc=1" in log
    assert "could not resolve host" in log


def test_systemexit_with_int_code_from_main_is_caught_and_propagated(monkeypatch):
    def _boom(argv):
        raise SystemExit(3)
    monkeypatch.setattr(S.F, "main", _boom)
    fake_git, calls = _fake_git([_proc(stdout="")])
    monkeypatch.setattr(S, "_git", fake_git)

    rc = S.main()

    assert rc == 3
    assert "dvp_forward aborted" in S.LOG_PATH.read_text(encoding="utf-8")


def test_systemexit_with_non_int_code_defaults_to_1(monkeypatch):
    def _boom(argv):
        raise SystemExit("some message, not a code")
    monkeypatch.setattr(S.F, "main", _boom)
    fake_git, calls = _fake_git([_proc(stdout="")])
    monkeypatch.setattr(S, "_git", fake_git)

    rc = S.main()

    assert rc == 1


def test_confirm_flag_is_what_gets_passed_to_dvp_forward(monkeypatch):
    seen = []
    def _spy(argv):
        seen.append(list(argv))
        return 0
    monkeypatch.setattr(S.F, "main", _spy)
    fake_git, _ = _fake_git([_proc(stdout="")])
    monkeypatch.setattr(S, "_git", fake_git)

    S.main()

    assert seen == [["--confirm"]]


def test_log_lines_are_timestamped(monkeypatch):
    monkeypatch.setattr(S.F, "main", lambda argv: 0)
    fake_git, _ = _fake_git([_proc(stdout="")])
    monkeypatch.setattr(S, "_git", fake_git)

    S.main()

    lines = [l for l in S.LOG_PATH.read_text(encoding="utf-8").splitlines() if l]
    assert lines
    for line in lines:
        # "YYYY-MM-DDTHH:MM:SS  <message>" -- just check the ISO date prefix
        assert line[:4].isdigit() and line[4] == "-"
