import importlib.util
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader" / "cutover_preflight.py"
_spec = importlib.util.spec_from_file_location("cutover_preflight", PATH)
cp = importlib.util.module_from_spec(_spec)
sys.modules["cutover_preflight"] = cp
_spec.loader.exec_module(cp)


def test_go_only_when_every_check_passes():
    assert cp.decide([("a", True, ""), ("b", True, "")])
    assert not cp.decide([("a", True, ""), ("b", False, "")])
    assert not cp.decide([])


def test_verdict_is_read_from_shadow_check_output():
    assert cp.parse_verdict("x\nVERDICT: PASS\n") == "PASS"
    assert cp.parse_verdict("VERDICT: NOT YET") == "NOT YET"
    assert cp.parse_verdict("nothing") == "UNKNOWN"


def test_the_script_never_writes_to_the_nas_or_logs_in():
    src = PATH.read_text(encoding="utf-8")
    for bad in ("sudo", "docker ", "sed -i", "tee ", " rm ", "chmod ", "IB("):
        assert bad not in src.split('"""', 2)[2], bad


def _run_with(monkeypatch, lock):
    """Run cp.run() with every outside call faked. lock: a JSON string, or an Exception to raise."""
    import json
    import types

    def fake_ssh(cmd):
        if "stat -c" in cmd:
            return "600\n"
        if "session.lock" in cmd:
            if isinstance(lock, Exception):
                raise lock
            return lock
        if "RELEASE.json" in cmd:
            return json.dumps({"commit": "666a822", "dirty": False})
        raise AssertionError(cmd)

    monkeypatch.setattr(cp, "_ssh", fake_ssh)
    monkeypatch.setattr(cp, "_ps", lambda c: "" if ("Get-Process" in c or "Get-NetTCP" in c) else "Ready")
    monkeypatch.setattr(cp.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout="VERDICT: PASS"))
    return cp.run("666a822")


def test_no_session_lock_means_not_in_session_and_the_release_check_still_runs(monkeypatch):
    checks = _run_with(monkeypatch, RuntimeError("cat: /x/session.lock: No such file or directory"))
    assert cp.decide(checks)
    names = [n for n, _, _ in checks]
    assert "release commit" in names
    assert "NAS reachable" not in names


def test_a_paper_mode_lock_is_a_no(monkeypatch):
    checks = _run_with(monkeypatch, '{"mode": "paper"}')
    assert not cp.decide(checks)
    assert ("NAS lock still dry", False, "lock mode paper") in checks


def test_a_real_ssh_failure_is_still_a_no(monkeypatch):
    checks = _run_with(monkeypatch, RuntimeError("ssh: connect to host 192.168.1.109 port 22: Connection timed out"))
    assert not cp.decide(checks)
    assert any(n == "NAS reachable" and not ok for n, ok, _ in checks)
