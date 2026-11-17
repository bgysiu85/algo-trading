"""W18-0003: send queued desk messages to Telegram, then mark them .sent.

Run every 5 minutes from a DSM Task Scheduler entry (as root), Python 3 standard library only:
    /usr/bin/python3 /volume1/docker/desk-sched/send_outbox.py
Two queues:
  * /volume1/docker/desk-sched/outbox  (root-owned; alerts from run_prepare_all.sh)  - trusted
  * /volume1/docker/desk/var/outbox    (the PC uploads its run summary here as the claude user) - UNTRUSTED:
    symlinks and non-regular files are skipped, files are opened with O_NOFOLLOW and cut at 3500 bytes, so the
    claude user cannot make root read some other file (a symlink to a root-only file) and send it to Telegram.
Uses TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from the reminders sync's env file (no new secret). W18-0012: if
/volume1/docker/desk-sched/desk.env (root, 600) sets DESK_TELEGRAM_CHAT_ID, desk messages go to that chat (the
"AI Desk" Telegram group, same bot) instead of the reminders chat.
Check the chat once with:  sudo /usr/bin/python3 /volume1/docker/desk-sched/send_outbox.py --test A file is sent once
(renamed to .sent after a 2xx answer); a failed send is retried next run and given up after 6 hours (.stale).
Half-uploaded files end in .part and are ignored. Sent and stale files are deleted after 14 days.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCHED = Path(os.environ.get("SCHED_DIR", "/volume1/docker/desk-sched"))
DESK = Path(os.environ.get("DESK_DIR", "/volume1/docker/desk"))
ENV_FILE = Path(os.environ.get("REMINDERS_ENV", "/volume1/docker/reminders/reminders.env"))
DESK_ENV_FILE = Path(os.environ.get("DESK_ENV", str(SCHED / "desk.env")))
STALE_S = 6 * 3600
KEEP_S = 14 * 86400
MAX_BYTES = 3500


def read_env(path: Path) -> dict:
    out = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def read_regular(p: Path) -> str | None:
    """Text of a regular file, never following a symlink; None if it is anything else."""
    try:
        fd = os.open(str(p), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        return os.read(fd, MAX_BYTES).decode("utf-8", errors="replace").strip()
    finally:
        os.close(fd)


def send_telegram(token: str, chat: str, text: str, urlopen=urllib.request.urlopen) -> bool:
    if not token or not chat:
        return False
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=10) as r:
            return 200 <= getattr(r, "status", 200) < 300
    except Exception:                                   # noqa: BLE001 - best effort, retried next run
        return False


def desk_env(reminders: dict, desk: dict) -> dict:
    """Bot token from the reminders env; chat = DESK_TELEGRAM_CHAT_ID when desk.env sets one, else the reminders chat."""
    out = dict(reminders)
    chat = desk.get("DESK_TELEGRAM_CHAT_ID", "").strip()
    if chat:
        out["TELEGRAM_CHAT_ID"] = chat
    return out


def send_test(env: dict, urlopen=urllib.request.urlopen) -> tuple[bool, str]:
    """Send one test line to the desk chat; return (ok, Telegram's own description). Never prints the token."""
    token, chat = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False, "missing TELEGRAM_BOT_TOKEN or chat id"
    text = "AI Desk test from the NAS, " + time.strftime("%F %T")
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=10) as r:
            return True, f"sent to chat {chat}"
    except urllib.error.HTTPError as e:                 # e.g. 400 "Bad Request: chat not found"
        try:
            desc = json.loads(e.read().decode("utf-8", "replace")).get("description", "")
        except Exception:                               # noqa: BLE001
            desc = ""
        return False, f"chat {chat}: HTTP {e.code} {desc}".strip()
    except Exception as e:                              # noqa: BLE001
        return False, f"chat {chat}: {type(e).__name__}"


def run(outbox: Path, env: dict, now: float | None = None, urlopen=urllib.request.urlopen) -> dict:
    now = time.time() if now is None else now
    res = {"sent": [], "retry": [], "stale": [], "deleted": [], "skipped": []}
    if not outbox.is_dir():
        return res
    for p in sorted(outbox.glob("*.txt")):
        text = read_regular(p)
        if text is None:                                # symlink, directory, device: never read, never sent
            res["skipped"].append(p.name)
            continue
        if text and send_telegram(env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", ""), text, urlopen):
            p.rename(p.with_suffix(".sent"))
            res["sent"].append(p.name)
        elif now - p.lstat().st_mtime > STALE_S:
            p.rename(p.with_suffix(".stale"))
            res["stale"].append(p.name)
        else:
            res["retry"].append(p.name)
    for p in list(outbox.glob("*.sent")) + list(outbox.glob("*.stale")):
        if now - p.lstat().st_mtime > KEEP_S:
            p.unlink()
            res["deleted"].append(p.name)
    return res


def main() -> int:
    env = desk_env(read_env(ENV_FILE), read_env(DESK_ENV_FILE))
    if "--test" in sys.argv[1:]:
        ok, msg = send_test(env)
        print(("OK " if ok else "FAILED ") + msg)
        return 0 if ok else 1
    retry = False
    for box in (SCHED / "outbox", DESK / "var" / "outbox"):
        res = run(box, env)
        if any(res.values()):
            print(time.strftime("%F %T"), box, json.dumps(res))
        retry = retry or bool(res["retry"])
    return 1 if retry else 0


if __name__ == "__main__":
    sys.exit(main())
