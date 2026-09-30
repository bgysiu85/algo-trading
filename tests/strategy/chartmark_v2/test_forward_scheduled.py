"""W15-0037's Task Scheduler wrapper: runs forward --confirm unattended, commits + pushes the ledger only if it changed. Both moving
parts (F.main and the module's own _git) are faked: no subprocess, git repo or network call happens."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import strategy.chartmark_v2.forward_scheduled as S


@pytest.fixture(autouse=True)
def _log_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "LOG_PATH", tmp_path / "w15_0037_weekly_log.txt")


def _proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_git(sequence):
    calls = []

    def _git(args):
        calls.append(list(args))
        return sequence[len(calls) - 1]

    return _git, calls


def test_ledger_name_is_the_registered_file_and_main_is_called_with_confirm(monkeypatch):
    seen = []
    monkeypatch.setattr(S.F, "main", lambda argv: seen.append(argv) or 0)
    fake, calls = _fake_git([_proc(stdout="")])
    monkeypatch.setattr(S, "_git", fake)
    assert S.LEDGER_NAME == "forward_chartmark_v2.json" and S.main() == 0
    assert seen == [["--confirm"]] and len(calls) == 1 and calls[0][:2] == ["status", "--porcelain"]
    assert "ledger unchanged" in S.LOG_PATH.read_text(encoding="utf-8")


def test_ledger_changed_adds_only_the_ledger_commits_and_pushes(monkeypatch):
    monkeypatch.setattr(S.F, "main", lambda argv: 0)
    fake, calls = _fake_git([_proc(stdout=" M forward_chartmark_v2.json\n"), _proc(), _proc(stdout="[main abc1234]\n"), _proc(stdout="ok\n")])
    monkeypatch.setattr(S, "_git", fake)
    assert S.main() == 0
    assert [c[0] for c in calls] == ["status", "add", "commit", "push"]
    assert calls[1] == ["add", "forward_chartmark_v2.json"]
    msg = calls[2][calls[2].index("-m") + 1]
    assert "W15-0037" in msg and "scheduled" in msg


@pytest.mark.parametrize("fail_at,expect", [(0, ["status"]), (1, ["status", "add"]), (2, ["status", "add", "commit"]),
                                              (3, ["status", "add", "commit", "push"])])
def test_any_git_failure_returns_1_and_stops_the_chain(monkeypatch, fail_at, expect):
    monkeypatch.setattr(S.F, "main", lambda argv: 0)
    seq = [_proc(stdout=" M forward_chartmark_v2.json\n"), _proc(), _proc(), _proc()]
    seq[fail_at] = _proc(returncode=1, stderr="boom")
    fake, calls = _fake_git(seq)
    monkeypatch.setattr(S, "_git", fake)
    assert S.main() == 1
    assert [c[0] for c in calls] == expect


def test_a_refusal_or_a_stop_code_from_the_scorer_is_propagated_and_the_ledger_is_still_committed_if_it_changed(monkeypatch):
    def boom(argv):
        raise SystemExit("REFUSED (G-freeze): changed")
    monkeypatch.setattr(S.F, "main", boom)
    fake, _ = _fake_git([_proc(stdout="")])
    monkeypatch.setattr(S, "_git", fake)
    assert S.main() == 1
    assert "aborted" in S.LOG_PATH.read_text(encoding="utf-8")
    monkeypatch.setattr(S.F, "main", lambda argv: 3)
    fake, _ = _fake_git([_proc(stdout=" M forward_chartmark_v2.json\n"), _proc(), _proc(), _proc()])
    monkeypatch.setattr(S, "_git", fake)
    assert S.main() == 3
