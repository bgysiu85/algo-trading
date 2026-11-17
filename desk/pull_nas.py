r"""W18-0003: copy a day's prepared data from the NAS to this PC, and push a Telegram message outbox file back.

    .\.venv\Scripts\python.exe -m desk.pull_nas [--date 2026-11-10]

The NAS (a root DSM task, deploy/nas_desk/run_prepare_all.sh) writes
/volume1/docker/desk/var/desk_runs/<US date>/<TICKER>/ ; this copies that day folder into var/desk_runs/.
Uses the `claude` SSH key (read/write /volume1/docker only). Windows scp needs -O for this NAS.
Never strips the environment (a stripped SYSTEMROOT breaks sockets on Windows, WinError 10106).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from desk import config as cfgmod

_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+\.txt$")      # goes into a remote shell command: plain names only
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15"]


def nas_cfg(cfg: dict) -> dict:
    n = {"host": "192.168.1.109", "user": "claude",
         "key": r"D:\Trading\Claude outputs\.ssh\nas_claude_ed25519",
         "remote_runs": "/volume1/docker/desk/var/desk_runs", "remote_outbox": "/volume1/docker/desk/var/outbox"}
    n.update(cfg.get("nas", {}))
    return n


def scp_pull_cmd(cfg: dict, date: str, key: str | None = None, dest: Path | None = None) -> list[str]:
    n = nas_cfg(cfg)
    dest = dest or cfgmod.runs_dir(cfg)
    return ["scp", "-O", "-r", "-i", key or n["key"], *SSH_OPTS,
            f"{n['user']}@{n['host']}:{n['remote_runs']}/{cfgmod.norm_date(date)}", str(dest)]


def pull(cfg: dict, date: str, key: str | None = None, dest: Path | None = None, run=subprocess.run) -> int:
    cmd = scp_pull_cmd(cfg, date, key, dest)
    r = run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"PULL FAILED for {date}: {(r.stderr or r.stdout).strip()[-400:]}")
        print("The NAS prepare job may not have run for this US date (DSM Task Scheduler 'desk prepare'), "
              "or the NAS / SSH key is unreachable.")
        return 2
    print(f"PULLED {date} from the NAS into {dest or cfgmod.runs_dir(cfg)}")
    return 0


def push_outbox(cfg: dict, text: str, name: str, key: str | None = None, run=subprocess.run,
                tmp_dir: Path | None = None) -> int:
    """Upload text as <name>.part, then rename to <name>, so the NAS sender never reads a half file."""
    n = nas_cfg(cfg)
    if not _NAME_RE.match(name) or name.startswith("."):
        raise ValueError(f"outbox name must be a plain *.txt file name: {name!r}")
    tmp = Path(tmp_dir or cfgmod.runs_dir(cfg)) / f"_outbox_{name}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    base = ["-i", key or n["key"], *SSH_OPTS]
    remote = f"{n['remote_outbox']}/{name}"
    up = run(["scp", "-O", *base, str(tmp), f"{n['user']}@{n['host']}:{remote}.part"],
             capture_output=True, text=True, timeout=120)
    if up.returncode != 0:
        print(f"OUTBOX UPLOAD FAILED: {(up.stderr or up.stdout).strip()[-300:]}")
        return 2
    mv = run(["ssh", *base, f"{n['user']}@{n['host']}", f"mv '{remote}.part' '{remote}'"],
             capture_output=True, text=True, timeout=60)
    if mv.returncode != 0:
        print(f"OUTBOX RENAME FAILED: {(mv.stderr or mv.stdout).strip()[-300:]}")
        return 2
    print(f"OUTBOX {name} queued for Telegram")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=None)
    ap.add_argument("--key", default=None)
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = cfgmod.load_config(a.config)
    date = cfgmod.norm_date(a.date) if a.date else cfgmod.default_run_date()
    return pull(cfg, date, a.key)


if __name__ == "__main__":
    sys.exit(main())
