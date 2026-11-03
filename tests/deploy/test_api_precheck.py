"""Tests for deploy/nas_trader/api_precheck.py and api_precheck.sh (W10-0013 sub 16).

Nothing here touches IBKR, Telegram or Docker: a fake IB stands in for ib_async.IB and a fake `notify` for Telegram.
Each verdict is proved both ways, so a check that always says PASS (or always FAIL) would fail here. The 1 Nov
incident is replayed: the connect call RETURNS, but error 10141 arrived while connecting, and that must be a FAIL.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader"
_spec = importlib.util.spec_from_file_location("api_precheck", DEPLOY / "api_precheck.py")
pre = importlib.util.module_from_spec(_spec)
sys.modules["api_precheck"] = pre          # @dataclass looks the module up here
_spec.loader.exec_module(pre)
SH = (DEPLOY / "api_precheck.sh").read_text(encoding="utf-8")


class Event(list):
    def __iadd__(self, h):
        self.append(h)
        return self

    def emit(self, *args):
        for h in list(self):
            h(*args)


class FakeIB:
    def __init__(self, accounts=("DUM215828",), connect_error=None, errors_on_connect=(), server_time="now",
                 time_error=None):
        self.accounts = list(accounts)
        self.connect_error = connect_error
        self.errors_on_connect = list(errors_on_connect)     # [(code, text)] emitted during connect
        self.server_time = datetime.now(timezone.utc) if server_time == "now" else server_time
        self.time_error = time_error
        self.errorEvent = Event()
        self.connected = None
        self.disconnected = False

    def connect(self, host, port, clientId, timeout, readonly):
        self.connected = (host, port, clientId, readonly)
        for code, text in self.errors_on_connect:
            self.errorEvent.emit(-1, code, text, None)
        if self.connect_error:
            raise self.connect_error

    def disconnect(self):
        self.disconnected = True

    def managedAccounts(self):
        return self.accounts

    def reqCurrentTime(self):
        if self.time_error:
            raise self.time_error
        return self.server_time


def run_main(argv, ibs, notify=None):
    """Run main() handing out the fakes in order. Returns (exit code, output text, messages sent, sleeps)."""
    lines, sent, sleeps = [], [], []
    it = iter(ibs)

    def fake_notify(token, chat, text):
        sent.append((token, chat, text))
        return True

    code = pre.main(argv, ib_factory=lambda: next(it), sleep=sleeps.append, out=lines.append,
                    notify=notify or fake_notify, env={"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "chat"})
    return code, "\n".join(lines), sent, sleeps


# ---------------------------------------------------------------- refusals
@pytest.mark.parametrize("port", [4001, 4003, 7496, 7498])
def test_live_ports_are_refused_without_connecting(port):
    code, text, sent, _ = run_main(["--port", str(port)], [])        # an empty factory would raise if it were asked
    assert code == 2 and "REFUSED" in text and "LIVE" in text and not sent


def test_unknown_port_is_refused():
    assert run_main(["--port", "5555"], [])[0] == 2


# ---------------------------------------------------------------- the verdicts
def test_healthy_gateway_passes_quietly_by_default():
    ib = FakeIB()
    code, text, sent, _ = run_main([], [ib])
    assert code == 0 and "PRECHECK PASS" in text
    assert ib.connected == ("127.0.0.1", 4002, 95, True)          # read-only, client id 95
    assert ib.disconnected
    assert sent == []                                              # no message on a pass unless asked


def test_notify_ok_sends_a_short_ok_message():
    code, _, sent, _ = run_main(["--notify-ok", "--label", "before the window"], [FakeIB()])
    assert code == 0 and len(sent) == 1
    assert "OK" in sent[0][2] and "before the window" in sent[0][2] and "FAILED" not in sent[0][2]


def test_1_nov_replay_connect_returns_but_10141_arrived_is_a_fail():
    ib = FakeIB(errors_on_connect=[(10141, "Paper trading disclaimer must first be accepted for API connection")])
    code, text, sent, _ = run_main(["--attempts", "1"], [ib])
    assert code == 1 and "PRECHECK FAIL" in text
    assert len(sent) == 1 and "10141" in sent[0][2] and "disclaimer" in sent[0][2]
    assert "docker restart trader-ib-gateway" in sent[0][2]        # the message carries the fix
    assert ib.disconnected


def test_10141_alongside_a_connect_exception_is_still_named():
    ib = FakeIB(errors_on_connect=[(10141, "x")], connect_error=TimeoutError())
    code, _, sent, _ = run_main(["--attempts", "1"], [ib])
    assert code == 1 and "10141" in sent[0][2]


def test_refused_connection_and_timeout_are_explained_differently():
    refused = run_main(["--attempts", "1"], [FakeIB(connect_error=ConnectionRefusedError())])[2][0][2]
    timeout = run_main(["--attempts", "1"], [FakeIB(connect_error=TimeoutError())])[2][0][2]
    assert "not up" in refused and "never answered" in timeout and refused != timeout


def test_no_accounts_is_a_fail():
    code, _, sent, _ = run_main(["--attempts", "1"], [FakeIB(accounts=())])
    assert code == 1 and "no accounts" in sent[0][2]


def test_a_non_paper_account_is_a_fail():
    code, _, sent, _ = run_main(["--attempts", "1"], [FakeIB(accounts=("DUM215828", "U1234567"))])
    assert code == 1 and "U1234567" in sent[0][2] and "STOP" in sent[0][2]


def test_no_server_time_answer_is_a_fail():
    assert run_main(["--attempts", "1"], [FakeIB(time_error=TimeoutError())])[0] == 1
    assert run_main(["--attempts", "1"], [FakeIB(server_time=None)])[0] == 1


# ---------------------------------------------------------------- retries and messages
def test_a_gateway_that_recovers_between_attempts_passes_without_any_message():
    code, text, sent, sleeps = run_main(
        ["--attempts", "3", "--gap", "7"],
        [FakeIB(connect_error=ConnectionRefusedError()), FakeIB(connect_error=TimeoutError()), FakeIB()])
    assert code == 0 and sent == [] and sleeps == [7, 7]
    assert "attempt 3/3: PASS" in text


def test_all_attempts_failing_sends_exactly_one_message_and_no_sleep_after_the_last():
    code, _, sent, sleeps = run_main(["--attempts", "3", "--gap", "5"], [FakeIB(connect_error=ConnectionRefusedError()) for _ in range(3)])
    assert code == 1 and len(sent) == 1 and sleeps == [5, 5]
    assert "3 attempt(s)" in sent[0][2]


def test_no_notify_flag_sends_nothing_even_on_failure():
    code, _, sent, _ = run_main(["--attempts", "1", "--no-notify"], [FakeIB(connect_error=ConnectionRefusedError())])
    assert code == 1 and sent == []


def test_a_telegram_failure_never_changes_the_exit_code():
    ok = run_main(["--attempts", "1", "--notify-ok"], [FakeIB()], notify=lambda *a: False)
    bad = run_main(["--attempts", "1"], [FakeIB(connect_error=ConnectionRefusedError())], notify=lambda *a: False)
    assert ok[0] == 0 and bad[0] == 1 and "NOT sent" in bad[1]


def test_note_is_appended_to_the_message():
    _, _, sent, _ = run_main(["--attempts", "1", "--note", "After one automatic Gateway restart."],
                             [FakeIB(connect_error=ConnectionRefusedError())])
    assert "After one automatic Gateway restart." in sent[0][2]


def test_send_telegram_without_token_or_chat_does_nothing_and_swallows_errors():
    assert pre.send_telegram("", "c", "x") is False
    assert pre.send_telegram("t", "", "x") is False

    def boom(*a, **k):
        raise OSError("no route")
    assert pre.send_telegram("t", "c", "x", urlopen=boom) is False


# ---------------------------------------------------------------- the DSM wrapper (text rules)
def test_wrapper_runs_in_the_gateway_network_and_publishes_nothing():
    assert "--network \"container:$GATEWAY\"" in SH and "GATEWAY=trader-ib-gateway" in SH
    assert not re.search(r"(^|\s)(-p|--publish)(\s|=)", SH), "no port may be published"
    assert "network_mode" not in SH and "--network host" not in SH and "--privileged" not in SH


def test_wrapper_passes_only_the_two_telegram_values_not_the_whole_env_file():
    assert "--env-file" not in SH
    assert "-e TELEGRAM_BOT_TOKEN" in SH and "-e TELEGRAM_CHAT_ID" in SH
    assert "TWS_PASSWORD" not in SH and "VNC_SERVER_PASSWORD" not in SH


def test_wrapper_restarts_only_in_check_restart_mode_and_never_under_a_running_trader():
    restarts = [m.start() for m in re.finditer(r'^\s*docker restart "', SH, re.M)]     # the command, not log text
    assert len(restarts) == 1, "exactly one restart command"
    body = SH[:restarts[0]]
    assert 'if [ "$MODE" = "check" ]' in body and "exit $rc" in body      # plain check exits before reaching the restart
    guard = re.search(r"docker inspect -f '\{\{\.State\.Running\}\}' trader-trader", body)
    assert guard, "the running-trader guard must come before the restart"
    assert "exit 1" in body[guard.end():], "a running trader must end the script (alert only) before the restart"


def test_wrapper_never_places_orders_or_touches_the_trader_container():
    assert "docker stop" not in SH and "docker rm" not in SH and "docker kill" not in SH
    assert "TRADER_MODE" not in SH


def test_wrapper_script_is_valid_bash():
    import shutil
    import subprocess
    if sys.platform == "win32":
        pytest.skip("on Windows 'bash' can be the WSL stub with no distribution installed; this runs in the cloud / Linux")
    if not shutil.which("bash"):
        pytest.skip("bash not available")
    r = subprocess.run(["bash", "-n", str(DEPLOY / "api_precheck.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_script_uses_a_client_id_nobody_else_uses():
    assert pre.CLIENT_ID == 95
    others = {17, 55, 62, 63, 77, 88, 91, 93, 94}
    assert pre.CLIENT_ID not in others


# ---------------------------------------------------------------- the DSM wrapper, run for real against a fake `docker`
import os
import stat
import subprocess

FAKE_DOCKER = """#!/bin/bash
echo "$*" >> "$FAKE_DIR/calls.log"
case "$1" in
  run) n=$(cat "$FAKE_DIR/n" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$FAKE_DIR/n"
       rc=$(echo "$FAKE_RC" | cut -d, -f$n); exit "${rc:-0}";;
  inspect) echo "$FAKE_RUNNING"; exit 0;;
  restart) exit 0;;
esac
exit 0
"""


def run_wrapper(tmp_path, mode, rcs, trader_running="false"):
    """Run api_precheck.sh with a fake docker first on PATH. Returns (exit code, list of docker calls)."""
    if sys.platform == "win32":
        pytest.skip("bash behaviour tests run in the cloud / Linux, not on Windows")
    fake_dir = tmp_path / "fake"
    fake_dir.mkdir()
    docker = fake_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    trader = tmp_path / "trader"
    trader.mkdir()
    (trader / ".env").write_text("TWS_PASSWORD='secret-pw'\nTELEGRAM_BOT_TOKEN='tok123'\nTELEGRAM_CHAT_ID=42\n", encoding="utf-8")
    env = dict(os.environ, PATH=f"{fake_dir}{os.pathsep}{os.environ['PATH']}", FAKE_DIR=str(fake_dir), FAKE_RC=rcs,
               FAKE_RUNNING=trader_running, TRADER_DIR=str(trader), PRECHECK_WAIT_S="0")
    r = subprocess.run(["bash", str(DEPLOY / "api_precheck.sh"), mode], env=env, capture_output=True, text=True, timeout=60)
    calls = (fake_dir / "calls.log").read_text(encoding="utf-8").splitlines() if (fake_dir / "calls.log").exists() else []
    return r.returncode, calls, r.stdout


def kinds(calls, word):
    return [c for c in calls if c.split()[0] == word]


def test_wrapper_check_pass_runs_once_asks_for_an_ok_message_and_never_restarts(tmp_path):
    rc, calls, _ = run_wrapper(tmp_path, "check", "0")
    assert rc == 0 and len(kinds(calls, "run")) == 1 and not kinds(calls, "restart")
    assert "--notify-ok" in kinds(calls, "run")[0]


def test_wrapper_check_fail_exits_1_and_never_restarts_or_inspects(tmp_path):
    rc, calls, _ = run_wrapper(tmp_path, "check", "1")
    assert rc == 1 and not kinds(calls, "restart") and not kinds(calls, "inspect")


def test_wrapper_check_restart_with_a_healthy_gateway_does_not_restart(tmp_path):
    rc, calls, _ = run_wrapper(tmp_path, "check-restart", "0,0")
    assert rc == 0 and not kinds(calls, "restart")
    assert "--no-notify" in kinds(calls, "run")[0]


def test_wrapper_check_restart_never_restarts_under_a_running_trader(tmp_path):
    rc, calls, _ = run_wrapper(tmp_path, "check-restart", "1,1", trader_running="true")
    assert rc == 1 and not kinds(calls, "restart")
    assert "NOT restarted" in kinds(calls, "run")[-1]


def test_wrapper_check_restart_restarts_exactly_once_then_passes(tmp_path):
    rc, calls, _ = run_wrapper(tmp_path, "check-restart", "1,0")
    assert rc == 0 and len(kinds(calls, "restart")) == 1 and kinds(calls, "restart")[0] == "restart trader-ib-gateway"
    assert "After one automatic Gateway restart." in kinds(calls, "run")[-1]
    assert calls.index(kinds(calls, "restart")[0]) < calls.index(kinds(calls, "run")[-1])


def test_wrapper_check_restart_still_failing_after_the_restart_exits_1_after_one_restart_only(tmp_path):
    rc, calls, _ = run_wrapper(tmp_path, "check-restart", "1,1")
    assert rc == 1 and len(kinds(calls, "restart")) == 1


def test_wrapper_never_puts_secret_values_on_the_command_line(tmp_path):
    _, calls, _ = run_wrapper(tmp_path, "check-restart", "1,0")
    text = "\n".join(calls)
    assert "tok123" not in text and "secret-pw" not in text and "--env-file" not in text
    assert "-e TELEGRAM_BOT_TOKEN" in text


def test_wrapper_rejects_an_unknown_mode(tmp_path):
    rc, calls, _ = run_wrapper(tmp_path, "restart-now", "0")
    assert rc == 2 and not calls


def test_wrapper_passes_extra_arguments_through_to_the_check(tmp_path):
    if sys.platform == "win32":
        pytest.skip("bash behaviour tests run in the cloud / Linux, not on Windows")
    # run_wrapper has no extra-args parameter, so build the call here with the same fake docker
    fake_dir = tmp_path / "fake"
    fake_dir.mkdir()
    (fake_dir / "docker").write_text(FAKE_DOCKER, encoding="utf-8")
    (fake_dir / "docker").chmod(0o755)
    trader = tmp_path / "trader"
    trader.mkdir()
    env = dict(os.environ, PATH=f"{fake_dir}{os.pathsep}{os.environ['PATH']}", FAKE_DIR=str(fake_dir), FAKE_RC="1",
               FAKE_RUNNING="false", TRADER_DIR=str(trader), PRECHECK_WAIT_S="0")
    r = subprocess.run(["bash", str(DEPLOY / "api_precheck.sh"), "check", "--port", "7497", "--attempts", "1", "--label", "TEST - ignore"],
                       env=env, capture_output=True, text=True, timeout=60)
    calls = (fake_dir / "calls.log").read_text(encoding="utf-8")
    assert r.returncode == 1 and "--port 7497 --attempts 1 --label TEST - ignore" in calls
