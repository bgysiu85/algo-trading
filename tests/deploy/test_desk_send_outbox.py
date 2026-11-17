"""deploy/nas_desk/send_outbox.py (W18-0003): fake Telegram, temp outbox. No network."""
import importlib.util
import os
import time
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "nas_desk" / "send_outbox.py"
spec = importlib.util.spec_from_file_location("send_outbox", SCRIPT)
so = importlib.util.module_from_spec(spec)
spec.loader.exec_module(so)

ENV = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}


def ok_urlopen(sent):
    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def f(req, timeout=0):
        sent.append(req.data)
        return R()
    return f


def boom(req, timeout=0):
    raise OSError("offline")


def test_sends_once_and_marks_sent(tmp_path):
    (tmp_path / "desk_2026-11-10.txt").write_text("Desk summary", encoding="utf-8")
    sent = []
    r = so.run(tmp_path, ENV, urlopen=ok_urlopen(sent))
    assert r["sent"] == ["desk_2026-11-10.txt"] and len(sent) == 1
    assert (tmp_path / "desk_2026-11-10.sent").exists()
    assert so.run(tmp_path, ENV, urlopen=ok_urlopen(sent))["sent"] == [] and len(sent) == 1


def test_part_files_are_ignored_and_failures_retry_then_go_stale(tmp_path):
    (tmp_path / "x.txt.part").write_text("half", encoding="utf-8")
    p = tmp_path / "a.txt"
    p.write_text("hi", encoding="utf-8")
    r = so.run(tmp_path, ENV, urlopen=boom)
    assert r["retry"] == ["a.txt"] and (tmp_path / "x.txt.part").exists()
    r = so.run(tmp_path, ENV, now=p.stat().st_mtime + so.STALE_S + 5, urlopen=boom)
    assert r["stale"] == ["a.txt"] and (tmp_path / "a.stale").exists()


def test_missing_credentials_never_send(tmp_path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    sent = []
    assert so.run(tmp_path, {}, urlopen=ok_urlopen(sent))["retry"] == ["a.txt"] and not sent


def test_old_sent_files_are_deleted(tmp_path):
    p = tmp_path / "old.sent"
    p.write_text("x", encoding="utf-8")
    old = time.time() - so.KEEP_S - 100
    os.utime(p, (old, old))
    assert so.run(tmp_path, ENV, urlopen=boom)["deleted"] == ["old.sent"]


def test_read_env_handles_quotes_and_comments(tmp_path):
    f = tmp_path / "e.env"
    f.write_text("# c\nTELEGRAM_BOT_TOKEN='abc'\nTELEGRAM_CHAT_ID=\"7\"\nJUNK\n", encoding="utf-8")
    assert so.read_env(f) == {"TELEGRAM_BOT_TOKEN": "abc", "TELEGRAM_CHAT_ID": "7"}
    assert so.read_env(tmp_path / "missing") == {}


def test_a_symlink_to_a_secret_is_never_read_or_sent(tmp_path):
    secret = tmp_path / "secret_root_only"
    secret.write_text("TOKEN=hunter2", encoding="utf-8")
    box = tmp_path / "outbox"
    box.mkdir()
    (box / "evil.txt").symlink_to(secret)
    sent = []
    r = so.run(box, ENV, urlopen=ok_urlopen(sent))
    assert r["skipped"] == ["evil.txt"] and not sent and r["sent"] == []


def test_long_files_are_cut_at_the_cap(tmp_path):
    (tmp_path / "big.txt").write_text("x" * 9000, encoding="utf-8")
    sent = []
    so.run(tmp_path, ENV, urlopen=ok_urlopen(sent))
    import json as _j
    assert len(_j.loads(sent[0])["text"]) == so.MAX_BYTES


def test_the_root_script_writes_only_into_its_own_root_folder():
    sh = (SCRIPT.parent / "run_prepare_all.sh").read_text(encoding="utf-8")
    assert 'LOG="$SCHED/prepare_all.log"' in sh and '"$SCHED/outbox/' in sh
    assert "chown" not in sh and "_prepared.txt" not in sh      # no root writes into the claude-owned desk folder
    assert "^[A-Z][A-Z0-9.-]{0,9}$" in sh


def test_the_root_script_runs_the_macro_step_best_effort_with_the_same_safe_flags():
    # W18-0006: a failed macro file alerts but never stops the stock data; no PC/live port; nothing written by root outside $SCHED
    sh = (SCRIPT.parent / "run_prepare_all.sh").read_text(encoding="utf-8")
    assert "python -m desk.macro --date" in sh and "SKIP_MACRO" in sh
    macro = sh[sh.index("W18-0006"):sh.index("ok=0; failed")]
    assert "--network container:trader-ib-gateway" in macro and "--user 1043:100" in macro
    assert 'macro_failed=1' in macro and "exit" not in macro          # never stops the ticker loop
    assert "macro closes failed" in sh


# --- W18-0012: desk messages to the "AI Desk" Telegram group -------------------------------------------------

def test_desk_chat_from_desk_env_overrides_the_reminders_chat_but_keeps_the_token():
    env = so.desk_env({"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"},
                      {"SEC_CONTACT": "x@y", "DESK_TELEGRAM_CHAT_ID": "-5475374837"})
    assert env == {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "-5475374837"}


def test_no_desk_chat_falls_back_to_the_reminders_chat():
    rem = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}
    assert so.desk_env(rem, {"SEC_CONTACT": "x@y"}) == rem
    assert so.desk_env(rem, {"DESK_TELEGRAM_CHAT_ID": "  "}) == rem


def test_run_sends_to_the_desk_chat(tmp_path):
    import json as _j
    (tmp_path / "desk_2026-11-13.txt").write_text("Desk summary", encoding="utf-8")
    sent = []
    env = so.desk_env(ENV, {"DESK_TELEGRAM_CHAT_ID": "-5475374837"})
    so.run(tmp_path, env, urlopen=ok_urlopen(sent))
    assert _j.loads(sent[0])["chat_id"] == "-5475374837"


def test_send_test_reports_telegrams_reason_and_never_the_token():
    import io
    import urllib.error
    def chat_not_found(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {},
                                     io.BytesIO(b'{"ok":false,"description":"Bad Request: chat not found"}'))
    ok, msg = so.send_test({"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "-1"}, urlopen=chat_not_found)
    assert not ok and "chat not found" in msg and "secret-token" not in msg
    ok, msg = so.send_test({"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "-1"}, urlopen=ok_urlopen([]))
    assert ok and "secret-token" not in msg
    assert so.send_test({}, urlopen=ok_urlopen([]))[0] is False
