#!/usr/bin/env python3
"""
clickup_sync.py -- mirror the Algo Trading task board into ClickUp through the REST API.

WHY A SCRIPT AND NOT ONLY THE CLAUDE CONNECTOR
----------------------------------------------
ClickUp's MCP connector (what a Claude chat uses) is capped per day: 100 calls on the
Free Forever plan, 300 on Unlimited. The REST API this script uses has no daily cap --
100 requests a minute per token -- so bulk work (the first load, re-syncing after a
busy day) goes through here, and chats use the connector only for small edits.

WHAT IT DOES
------------
Reads a board export (algo_board_YYYYMMDD.json in "Claude outputs\\boards\\", written by a Claude chat from the Notion
Command Centre, which stays the source of truth) and makes ClickUp match it:

  * one Space, "Algo Trading"               (created if missing)
  * one List per workstream                 (created if missing)
  * one task per card, named "AT-n · ..."   (created, or updated in place -- the AT-n
                                             prefix is how a card is recognised, so it
                                             is safe to run as often as you like)
  * status, priority, due date, owner tag, description with the source doc and a
    link back to the Notion card
  * "waiting on" dependencies between tasks

It never deletes a task. Tags and dependencies it did not create are left alone.
Fields it manages (name, description, status, priority, due date, owner tag) are
overwritten from the board on every run -- edit those in Notion, not in ClickUp.

STATUSES
--------
ClickUp's API cannot create custom statuses (an open ClickUp feature request), so the
script uses these if you have added them to the space in ClickUp:
    waiting on ben, next up, in progress, blocked, backlog      (open)
    done, dropped                                               (closed)
and otherwise falls back to the space's own statuses (to do / in progress / complete)
plus a tag such as "waiting-on-ben" so nothing is lost. `check` lists what is missing.

TOKEN
-----
Read through common/secrets_util.py (the repo's one credential resolver) from
CLICKUP_API_TOKEN, which may hold the literal token or an op:// reference. If the
variable is not set, the default reference op://Trading/Clickup/api_token is used.
The token is never printed; only a masked form is.

USAGE (from PowerShell, in D:\\Trading)
------------------------------------
    Set-Location D:\\Trading
    .\\.venv\\Scripts\\python.exe -m boards.clickup_sync check
    .\\.venv\\Scripts\\python.exe -m boards.clickup_sync sync --dry-run
    .\\.venv\\Scripts\\python.exe -m boards.clickup_sync sync

The board export is the newest algo_board_YYYYMMDD.json in "Claude outputs\\boards\\"
(or --board PATH). Every run writes a report to var\\boards\\clickup_sync_YYYYMMDD_HHMMSS.txt,
and a successful sync writes var\\boards\\clickup_map.json (card id -> ClickUp task id
and link).

Standard library only. No pip install needed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

API_V2 = "https://api.clickup.com/api/v2"
API_V3 = "https://api.clickup.com/api/v3"
ENV_TOKEN = "CLICKUP_API_TOKEN"
ENV_TEAM = "CLICKUP_TEAM_ID"
DEFAULT_REF = "op://Trading/Clickup/api_token"
DEFAULT_SPACE = "Algo Trading"

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REPO_GUESSES = [REPO, Path(r"D:\Trading")]
# Board exports are written by a Claude chat and delivered like any other file it
# makes, so they arrive in "Claude outputs". The clickup\ folder is where the first
# export went on 2026-09-19 and is still read so nothing has to be moved by hand.
EXPORT_DIRS = [REPO / "Claude outputs" / "boards", REPO / "Claude outputs" / "clickup"]
# Maps and run reports are machine-local output: var\ is gitignored.
STATE_DIR = REPO / "var" / "boards"

CARD_ID = re.compile(r"^\s*(AT-\d+)\b")
REV_MARK = re.compile(r"sync-rev:([0-9a-f]{10})")

# Board status -> the ClickUp status name we would like to use.
WANTED_STATUS = {
    "Waiting on Ben": "waiting on ben",
    "Next up": "next up",
    "In progress": "in progress",
    "Blocked": "blocked",
    "Backlog": "backlog",
    "Done": "done",
    "Dropped": "dropped",
}
CLOSED_BOARD_STATUSES = {"Done", "Dropped"}
# Tag carried when the wanted status does not exist in the space.
FALLBACK_TAG = {
    "Waiting on Ben": "waiting-on-ben",
    "Next up": "next-up",
    "In progress": "in-progress",
    "Blocked": "blocked",
    "Backlog": "backlog",
    "Dropped": "dropped",
}
# ClickUp priority: 1 urgent, 2 high, 3 normal, 4 low.
PRIORITY = {"P1 · now": 1, "P2 · soon": 2, "P3 · later": 4}
OWNER_TAG = {
    "Ben": "ben",
    "Build & test chat": "build-chat",
    "Live analysis chat": "live-chat",
    "Research & spec chat": "research-chat",
    "Portal chat": "portal-chat",
    "MCL chat": "mcl-chat",
    "ORB chat": "orb-chat",
    "TSMOM chat": "tsmom-chat",
    "Swing chat": "swing-chat",
    "Any chat": "any-chat",
}
TAG_COLOUR = {"ben": "#e5484d"}
MANAGED_TAGS = set(OWNER_TAG.values()) | set(FALLBACK_TAG.values())

SPACE_FEATURES = {
    "due_dates": {"enabled": True, "start_date": False,
                  "remap_due_dates": False, "remap_closed_due_date": False},
    "time_tracking": {"enabled": False},
    "tags": {"enabled": True},
    "time_estimates": {"enabled": False},
    "checklists": {"enabled": True},
    "custom_fields": {"enabled": True},
    "remap_dependencies": {"enabled": True},
    "dependency_warning": {"enabled": True},
    "portfolios": {"enabled": False},
}


# --------------------------------------------------------------------------- output

class Log:
    """Prints and keeps every line so the run can be written to a report file."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, msg: str = "") -> None:
        self.lines.append(msg)
        try:
            print(msg)
        except UnicodeEncodeError:  # a cp1252 console that could not be reconfigured
            print(msg.encode("ascii", "replace").decode("ascii"))

    def write(self, path: Path) -> None:
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def mask(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]} ({len(value)} chars)"


# --------------------------------------------------------------------------- token

def normalise_ref(raw: str) -> str:
    """Accept the forms people actually type for a 1Password reference.

    op://Trading/Clickup/api_token      correct
    op:\\\\Trading\\Clickup\\api_token      Windows-style slashes
    op:/Trading/Clickup/api_token       one slash short
    """
    raw = raw.strip().strip('"').strip("'")
    if raw.lower().startswith("op:") and not raw.startswith("op://"):
        rest = raw[3:].replace("\\", "/").lstrip("/")
        return "op://" + rest
    return raw


def _load_secrets_util():
    for root in REPO_GUESSES:
        if (root / "common" / "secrets_util.py").exists():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            try:
                from common import secrets_util  # type: ignore
                return secrets_util
            except Exception:
                return None
    return None


def _op_read(ref: str) -> str:
    """Fallback when the repo's resolver cannot be imported."""
    try:
        out = subprocess.run(["op", "read", ref], capture_output=True, text=True, timeout=25)
    except FileNotFoundError:
        sys.exit("1Password CLI ('op') not found on PATH. Install it, or set "
                 f"{ENV_TOKEN} to the token itself.")
    except subprocess.TimeoutExpired:
        sys.exit("`op read` timed out -- 1Password is probably locked and waiting for you.")
    if out.returncode != 0:
        sys.exit(f"`op read` failed for {ref}:\n  {out.stderr.strip()}")
    return out.stdout.strip()


def resolve_token(log: Log) -> str:
    raw = os.environ.get(ENV_TOKEN, "").strip()
    if not raw:
        os.environ[ENV_TOKEN] = DEFAULT_REF
        log(f"token   : {ENV_TOKEN} not set -- using {DEFAULT_REF}")
    else:
        fixed = normalise_ref(raw)
        if fixed != raw:
            log(f"token   : reference rewritten to {fixed} (op:// needs forward slashes)")
            os.environ[ENV_TOKEN] = fixed
    su = _load_secrets_util()
    if su is not None and hasattr(su, "resolve"):
        token = su.resolve(ENV_TOKEN, "ClickUp API token")
        via = "common/secrets_util.py"
    else:
        ref = os.environ[ENV_TOKEN]
        token = _op_read(ref) if ref.startswith("op://") else ref
        via = "built-in op read"
    if not token:
        sys.exit(f"No ClickUp token found (checked {ENV_TOKEN} and {DEFAULT_REF}).")
    if token.startswith("op:"):
        sys.exit("The token still looks like a 1Password reference -- it was not resolved. "
                 "Check the reference is op://Vault/Item/field.")
    log(f"token   : {mask(token)} via {via}")
    if not token.startswith("pk_"):
        log("          warning: ClickUp personal tokens normally start with 'pk_'")
    return token


# --------------------------------------------------------------------------- HTTP

class ApiError(RuntimeError):
    def __init__(self, status: int, method: str, url: str, body: str):
        super().__init__(f"{method} {url} -> HTTP {status}: {body[:400]}")
        self.status = status


Transport = Callable[[str, str, dict, Optional[bytes]], "tuple[int, dict, bytes]"]


def urllib_transport(method: str, url: str, headers: dict, data: Optional[bytes]):
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()) if e.headers else {}, e.read()


class ClickUp:
    """Thin client. Paces itself under the 100-requests-a-minute limit and waits out a 429."""

    def __init__(self, token: str, transport: Transport = urllib_transport,
                 min_interval: float = 0.65, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.time, dry_run: bool = False):
        self.token = token
        self.transport = transport
        self.min_interval = min_interval
        self.sleep = sleep
        self.clock = clock
        self.dry_run = dry_run
        self._last = float("-inf")
        self.calls = 0
        self.writes = 0
        self.skipped_writes: list[str] = []

    def request(self, method: str, path: str, body: Optional[dict] = None,
                query: Optional[list] = None, base: str = API_V2):
        url = base + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        if method != "GET":
            if self.dry_run:
                self.skipped_writes.append(f"{method} {path}")
                return {}
            self.writes += 1
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Authorization": self.token, "Content-Type": "application/json",
                   "Accept": "application/json"}
        for attempt in range(6):
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = self.clock()
            self.calls += 1
            status, hdrs, raw = self.transport(method, url, headers, data)
            if status == 429:
                self.sleep(self._retry_after(hdrs))
                continue
            if status >= 500 and attempt < 3:
                self.sleep(2.0 * (attempt + 1))
                continue
            text = raw.decode("utf-8", "replace") if raw else ""
            if status >= 400:
                raise ApiError(status, method, path, text)
            return json.loads(text) if text.strip() else {}
        raise ApiError(429, method, path, "rate limited six times in a row")

    def _retry_after(self, hdrs: dict) -> float:
        low = {k.lower(): v for k, v in hdrs.items()}
        if "retry-after" in low:
            try:
                return max(1.0, float(low["retry-after"]))
            except ValueError:
                pass
        if "x-ratelimit-reset" in low:
            try:
                return max(1.0, min(65.0, float(low["x-ratelimit-reset"]) - self.clock() + 1))
            except ValueError:
                pass
        return 30.0


# --------------------------------------------------------------------------- board

def load_board(path: Path) -> dict:
    board = json.loads(path.read_text(encoding="utf-8"))
    for key in ("workstreams", "tasks"):
        if key not in board:
            sys.exit(f"{path.name}: missing '{key}' -- not a board export")
    ids = [t["id"] for t in board["tasks"]]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        sys.exit(f"{path.name}: duplicate card ids {sorted(dupes)}")
    names = {w["name"] for w in board["workstreams"]}
    for t in board["tasks"]:
        if not t.get("workstreams"):
            sys.exit(f"{t['id']}: no workstream")
        for w in t["workstreams"]:
            if w not in names:
                sys.exit(f"{t['id']}: unknown workstream '{w}'")
        for b in t.get("blocked_by", []):
            if b not in ids:
                sys.exit(f"{t['id']}: blocked_by {b} is not on the board")
        if t["status"] not in WANTED_STATUS:
            sys.exit(f"{t['id']}: unknown status '{t['status']}'")
    return board


def newest_board(folders) -> Optional[Path]:
    """Newest export by the date in its name, across the export folders."""
    if isinstance(folders, Path):
        folders = [folders]
    found = [p for f in folders if f.exists() for p in f.glob("algo_board_*.json")]
    found.sort(key=lambda p: (p.name, p.stat().st_mtime))
    return found[-1] if found else None


def task_name(t: dict) -> str:
    return f"{t['id']} · {t['name']}"


def due_ms(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
    return str(int(d.timestamp() * 1000))


# --------------------------------------------------------------------------- statuses

class StatusMap:
    def __init__(self, space_statuses: list[dict]):
        self.by_name = {s["status"].lower(): s for s in space_statuses}
        opens = [s for s in space_statuses if s.get("type") == "open"]
        closeds = [s for s in space_statuses if s.get("type") in ("closed", "done")]
        self.open_default = (opens[0]["status"] if opens
                             else (space_statuses[0]["status"] if space_statuses else "to do"))
        self.closed_default = (closeds[-1]["status"] if closeds else "complete")

    def missing(self) -> list[str]:
        return [v for v in WANTED_STATUS.values() if v not in self.by_name]

    def resolve(self, board_status: str) -> tuple[str, Optional[str]]:
        """Return (ClickUp status, fallback tag or None)."""
        wanted = WANTED_STATUS[board_status]
        if wanted in self.by_name:
            return self.by_name[wanted]["status"], None
        if board_status in CLOSED_BOARD_STATUSES:
            base = self.closed_default
        elif board_status == "In progress" and "in progress" in self.by_name:
            base = self.by_name["in progress"]["status"]
        else:
            base = self.open_default
        return base, FALLBACK_TAG.get(board_status)


# --------------------------------------------------------------------------- description

def description(t: dict, primary_ws: str, rev: str) -> str:
    lines = [
        f"**Owner:** {t['owner']} · **Type:** {t['type']} · **Priority:** {t['priority']}",
        f"**Source doc:** {t.get('source_doc') or '—'}",
    ]
    if t.get("blocked_by"):
        lines.append(f"**Blocked by:** {', '.join(t['blocked_by'])}")
    others = [w for w in t["workstreams"] if w != primary_ws]
    if others:
        lines.append(f"**Also in workstream:** {', '.join(others)}")
    if t.get("done_on"):
        lines.append(f"**Done on:** {t['done_on']}")
    if t.get("notion_url"):
        lines.append(f"**Notion card:** [{t['id']}]({t['notion_url']})")
    if t.get("notes"):
        lines += ["", t["notes"]]
    lines += ["", f"_Mirrored from the Notion Command Centre by clickup_sync.py · sync-rev:{rev}_"]
    return "\n".join(lines)


def revision(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:10]


# --------------------------------------------------------------------------- the sync

class Syncer:
    def __init__(self, api: ClickUp, log: Log, space_name: str = DEFAULT_SPACE):
        self.api = api
        self.log = log
        self.space_name = space_name
        self.team_id = ""
        self.space: dict = {}
        self.counts = {k: 0 for k in ("space", "lists", "tags", "created", "updated",
                                      "unchanged", "moved", "deps_added", "deps_removed")}

    # -- discovery
    def pick_team(self) -> str:
        teams = self.api.request("GET", "/team").get("teams", [])
        if not teams:
            sys.exit("The token can see no ClickUp workspace.")
        want = os.environ.get(ENV_TEAM, "").strip()
        if want:
            match = [t for t in teams if str(t["id"]) == want]
            if not match:
                sys.exit(f"{ENV_TEAM}={want} is not one of: "
                         + ", ".join(f"{t['id']} ({t['name']})" for t in teams))
            team = match[0]
        elif len(teams) == 1:
            team = teams[0]
        else:
            sys.exit("Several workspaces are visible; set CLICKUP_TEAM_ID to one of: "
                     + ", ".join(f"{t['id']} ({t['name']})" for t in teams))
        self.team_id = str(team["id"])
        self.log(f"workspace: {team['name']} ({self.team_id})")
        return self.team_id

    def find_space(self) -> Optional[dict]:
        spaces = self.api.request("GET", f"/team/{self.team_id}/space",
                                  query=[("archived", "false")]).get("spaces", [])
        for s in spaces:
            if s["name"].strip().lower() == self.space_name.lower():
                return s
        return None

    # -- structure
    def ensure_space(self) -> dict:
        space = self.find_space()
        if space:
            self.log(f"space   : '{space['name']}' exists ({space['id']})")
        else:
            self.log(f"space   : creating '{self.space_name}'")
            space = self.api.request("POST", f"/team/{self.team_id}/space", {
                "name": self.space_name, "multiple_assignees": False, "features": SPACE_FEATURES})
            self.counts["space"] += 1
            if not space:  # dry run
                space = {"id": "(new space)", "name": self.space_name, "statuses": []}
        self.space = space
        return space

    def ensure_lists(self, workstreams: list[dict]) -> dict[str, str]:
        existing = {}
        if not str(self.space["id"]).startswith("("):
            for lst in self.api.request("GET", f"/space/{self.space['id']}/list",
                                        query=[("archived", "false")]).get("lists", []):
                existing[lst["name"].strip()] = str(lst["id"])
        out = {}
        for w in workstreams:
            if w["name"] in existing:
                out[w["name"]] = existing[w["name"]]
                continue
            content = f"{w['state']} · led by {w['lead']}"
            if w.get("notion_url"):
                content += f"\nNotion: {w['notion_url']}"
            made = self.api.request("POST", f"/space/{self.space['id']}/list",
                                    {"name": w["name"], "content": content})
            self.counts["lists"] += 1
            out[w["name"]] = str(made.get("id", f"(new list: {w['name']})"))
            self.log(f"list    : created '{w['name']}'")
        return out

    def ensure_tags(self, needed: set[str]) -> None:
        have = set()
        if not str(self.space["id"]).startswith("("):
            tags = self.api.request("GET", f"/space/{self.space['id']}/tag").get("tags", [])
            have = {t["name"].lower() for t in tags}
        for name in sorted(needed - have):
            self.api.request("POST", f"/space/{self.space['id']}/tag", {
                "tag": {"name": name, "tag_fg": "#ffffff",
                        "tag_bg": TAG_COLOUR.get(name, "#6e56cf")}})
            self.counts["tags"] += 1

    def existing_tasks(self) -> dict[str, dict]:
        found: dict[str, dict] = {}
        if str(self.space["id"]).startswith("("):
            return found
        page = 0
        while True:
            res = self.api.request("GET", f"/team/{self.team_id}/task", query=[
                ("space_ids[]", self.space["id"]), ("include_closed", "true"),
                ("subtasks", "true"), ("page", str(page))])
            for t in res.get("tasks", []):
                m = CARD_ID.match(t.get("name", ""))
                if m and m.group(1) not in found:
                    found[m.group(1)] = t
            if res.get("last_page", True) or not res.get("tasks"):
                break
            page += 1
        return found

    # -- tasks
    def sync(self, board: dict) -> dict:
        self.pick_team()
        self.ensure_space()
        smap = StatusMap(self.space.get("statuses", []))
        missing = smap.missing()
        if missing:
            self.log("statuses: not in the space yet, using fallback + tag for: " + ", ".join(missing))
        else:
            self.log("statuses: all seven custom statuses present")
        lists = self.ensure_lists(board["workstreams"])

        plans = []
        needed_tags: set[str] = set()
        for t in board["tasks"]:
            status, ftag = smap.resolve(t["status"])
            tags = sorted({OWNER_TAG.get(t["owner"], "any-chat")} | ({ftag} if ftag else set()))
            needed_tags |= set(tags)
            primary = t["workstreams"][0]
            payload = {"name": task_name(t), "status": status, "priority": PRIORITY.get(t["priority"]),
                       "due": due_ms(t.get("target_date")), "tags": tags, "list": primary,
                       "t": {k: t.get(k) for k in ("owner", "type", "priority", "source_doc",
                                                   "notes", "blocked_by", "done_on", "notion_url",
                                                   "workstreams")}}
            rev = revision(payload)
            plans.append((t, status, tags, primary, rev))
        self.ensure_tags(needed_tags)

        existing = self.existing_tasks()
        cu_id: dict[str, str] = {k: str(v["id"]) for k, v in existing.items()}
        for t, status, tags, primary, rev in plans:
            body = {"name": task_name(t), "markdown_content": description(t, primary, rev),
                    "status": status, "priority": PRIORITY.get(t["priority"])}
            due = due_ms(t.get("target_date"))
            cur = existing.get(t["id"])
            if cur is None:
                body.update({"tags": tags, "notify_all": False})
                if due:
                    body.update({"due_date": int(due), "due_date_time": False})
                made = self.api.request("POST", f"/list/{lists[primary]}/task", body)
                cu_id[t["id"]] = str(made.get("id", f"(new {t['id']})"))
                self.counts["created"] += 1
                continue
            self._reconcile_list(t, cur, lists[primary])
            text = (cur.get("text_content") or "") + (cur.get("description") or "")
            m = REV_MARK.search(text)
            if m and m.group(1) == rev:
                self.counts["unchanged"] += 1
                continue
            body["due_date"] = int(due) if due else None
            body["due_date_time"] = False
            self.api.request("PUT", f"/task/{cur['id']}", body)
            have = {x["name"].lower() for x in cur.get("tags", [])}
            for tg in sorted(set(tags) - have):
                self.api.request("POST", f"/task/{cur['id']}/tag/{urllib.parse.quote(tg)}")
            for tg in sorted((have & MANAGED_TAGS) - set(tags)):
                self.api.request("DELETE", f"/task/{cur['id']}/tag/{urllib.parse.quote(tg)}")
            self.counts["updated"] += 1

        self._sync_dependencies(board, existing, cu_id)
        return {"team_id": self.team_id, "space_id": str(self.space["id"]), "lists": lists,
                "tasks": {k: {"id": v, "url": f"https://app.clickup.com/t/{v}"}
                          for k, v in sorted(cu_id.items(), key=lambda kv: int(kv[0][3:]))},
                "missing_statuses": missing}

    def _reconcile_list(self, t: dict, cur: dict, want_list: str) -> None:
        have_list = str((cur.get("list") or {}).get("id", ""))
        if not have_list or have_list == want_list or want_list.startswith("("):
            return
        try:
            self.api.request("PUT", f"/workspaces/{self.team_id}/tasks/{cur['id']}/home_list/{want_list}",
                             base=API_V3)
            self.counts["moved"] += 1
        except ApiError as e:
            self.log(f"warning : could not move {t['id']} to its workstream list ({e.status}); "
                     "move it by hand in ClickUp")

    def _sync_dependencies(self, board: dict, existing: dict, cu_id: dict) -> None:
        ours = set(cu_id.values())
        for t in board["tasks"]:
            me = cu_id.get(t["id"], "")
            want = {cu_id[b] for b in t.get("blocked_by", []) if b in cu_id}
            have = set()
            cur = existing.get(t["id"])
            if cur:
                for d in cur.get("dependencies", []) or []:
                    if str(d.get("task_id")) == str(cur["id"]) and d.get("depends_on"):
                        have.add(str(d["depends_on"]))
            for dep in sorted(want - have):
                self.api.request("POST", f"/task/{me}/dependency", {"depends_on": dep})
                self.counts["deps_added"] += 1
            for dep in sorted((have & ours) - want):
                self.api.request("DELETE", f"/task/{me}/dependency",
                                 query=[("depends_on", dep)])
                self.counts["deps_removed"] += 1


# --------------------------------------------------------------------------- commands

STATUS_HELP = """\
To get the board's own statuses in ClickUp (optional -- the sync works without them):
  1. In ClickUp, hover the 'Algo Trading' space in the sidebar, click the ... menu,
     then 'Space settings' (or 'Edit statuses').
  2. Under Not started / Active add:  waiting on ben, next up, in progress, blocked, backlog
     Under Closed/Done add:            done, dropped
  3. Save, then run the sync again. Cards move onto the new statuses and the stand-in
     tags (waiting-on-ben, blocked, ...) are removed."""


def cmd_check(api: ClickUp, log: Log, space_name: str) -> int:
    me = api.request("GET", "/user").get("user", {})
    log(f"user    : {me.get('username') or me.get('email') or me.get('id')}")
    s = Syncer(api, log, space_name)
    s.pick_team()
    space = s.find_space()
    if not space:
        log(f"space   : '{space_name}' does not exist yet -- `sync` will create it")
        return 0
    log(f"space   : '{space['name']}' ({space['id']})")
    smap = StatusMap(space.get("statuses", []))
    log("statuses: " + ", ".join(f"{x['status']} [{x.get('type')}]" for x in space.get("statuses", [])))
    miss = smap.missing()
    if miss:
        log("missing : " + ", ".join(miss))
        log(STATUS_HELP)
    else:
        log("statuses: all seven board statuses present")
    return 0


def cmd_sync(api: ClickUp, log: Log, board_path: Path, space_name: str, out_dir: Path) -> int:
    board = load_board(board_path)
    log(f"board   : {board_path.name} -- {len(board['tasks'])} cards, "
        f"{len(board['workstreams'])} workstreams (exported {board.get('exported', '?')})")
    s = Syncer(api, log, space_name)
    result = s.sync(board)
    c = s.counts
    log("")
    log("result  : " + ", ".join(f"{k} {v}" for k, v in c.items()))
    log(f"api     : {api.calls} requests, {api.writes} writes")
    if api.dry_run:
        log(f"DRY RUN : nothing was changed. {len(api.skipped_writes)} writes would have been sent.")
        for w in api.skipped_writes[:15]:
            log(f"          {w}")
        if len(api.skipped_writes) > 15:
            log(f"          ... and {len(api.skipped_writes) - 15} more")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        map_path = out_dir / "clickup_map.json"
        map_path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
        log(f"map     : {map_path}")
    if result["missing_statuses"]:
        log("")
        log(STATUS_HELP)
    return 0


def main(argv: Optional[list] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Mirror the Algo Trading board into ClickUp.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="test the token and show the workspace, space and statuses")
    sp = sub.add_parser("sync", help="create or update the space, lists and tasks from a board export")
    sp.add_argument("--board", type=Path, help="board export (default: newest algo_board_*.json here)")
    sp.add_argument("--dry-run", action="store_true", help="read only; list what would change")
    for p in sub.choices.values():
        p.add_argument("--space", default=DEFAULT_SPACE, help=f"space name (default '{DEFAULT_SPACE}')")
    args = ap.parse_args(argv)

    log = Log()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log(f"clickup_sync {args.cmd} -- {stamp}")
    code = 1
    try:
        token = resolve_token(log)
        api = ClickUp(token, dry_run=getattr(args, "dry_run", False))
        if args.cmd == "check":
            code = cmd_check(api, log, args.space)
        else:
            board = args.board or newest_board(EXPORT_DIRS)
            if not board or not board.exists():
                sys.exit("No board export found. Put algo_board_YYYYMMDD.json in "
                         f"{EXPORT_DIRS[0]} or pass --board.")
            code = cmd_sync(api, log, board, args.space, STATE_DIR)
    except ApiError as e:
        log(f"ERROR   : {e}")
        if e.status == 401:
            log("          ClickUp rejected the token. Check the 1Password item holds the "
                "personal token (Settings > Apps > API Token, starts pk_).")
    finally:
        report = STATE_DIR / f"clickup_sync_{stamp}.txt"
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            log.write(report)
            print(f"report  : {report}")
        except OSError:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
