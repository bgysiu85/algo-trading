#!/usr/bin/env python3
"""
monday_sync.py -- mirror the Algo Trading task board into monday.com through its API.

WHY A SCRIPT AND NOT ONLY THE CLAUDE CONNECTOR
----------------------------------------------
monday.com allows 1,000 API calls a day on the Free plan, and the Claude connector
(MCP) draws from the same allowance. This script packs up to 10 changes into each
call, so the first load of ~72 cards costs about 40 calls (mostly setting up columns
and groups, once) and a re-run with nothing changed costs 4 -- leaving the rest of the
day's allowance for chats.

WHAT IT DOES
------------
Reads a board export (algo_board_YYYYMMDD.json in "Claude outputs\\boards\\", written by a Claude chat from the Notion
Command Centre, which stays the source of truth) and makes monday.com match it:

  * one board, "Algo Trading"            (your existing one; created if missing)
  * one group per workstream             (created if missing)
  * one item per card, "AT-n · ..."      (created, or updated in place -- the Task ID
                                          column is how a card is recognised, so it is
                                          safe to run as often as you like)
  * the card's Notes posted to the item's Updates tab (only the new dated lines when
    a note is added; the whole Notes once on any item that has no update yet)
  * columns: Status, Assignee (who is looking after it now), Claude Session (who raised it), Priority, Type, Target date, Done on, Task ID,
    Workstreams, Blocked by, Source doc, Notes, Notion link, ClickUp link, Sync rev
    (created if missing; labels are added as needed)

It never deletes an item. It only writes the columns listed above -- your own columns
(the built-in Owner person column, anything you add) are left alone. Fields it manages
are overwritten from the board on every run: edit them in Notion, not in monday.

A card is only re-sent when something about it changed (the "Sync rev" column holds a
fingerprint), so re-running costs almost nothing.

FREE PLAN LIMITS THIS RESPECTS
------------------------------
3 boards (this uses 1), 200 items (warns from 180), 1,000 API calls a day (report shows
the count). Timeline/Gantt/Calendar views and automations need a paid plan; table and
kanban views work on Free -- group the kanban by Status, Owner chat or Priority.

TOKEN
-----
Read through common/secrets_util.py (the repo's one credential resolver) from
MONDAY_API_TOKEN, which may hold the literal token or an op:// reference. If the
variable is not set, the default reference op://Trading/Monday.com/api_token is used.
The token is never printed; only a masked form is.

USAGE (from PowerShell, in D:\\Trading)
------------------------------------
    Set-Location D:\\Trading
    .\\.venv\\Scripts\\python.exe -m boards.monday_sync check
    .\\.venv\\Scripts\\python.exe -m boards.monday_sync sync --dry-run
    .\\.venv\\Scripts\\python.exe -m boards.monday_sync sync

Options for sync: --board PATH (default: newest algo_board_*.json in "Claude outputs\\boards\\"),
--board-name NAME (default "Algo Trading"), --tidy (delete empty groups that are not
workstreams, e.g. the "To-Do" / "Completed" groups monday adds to a new board).

Every run writes a report to var\\boards\\monday_sync_YYYYMMDD_HHMMSS.txt, and a
successful sync writes var\\boards\\monday_map.json (card id -> monday item id and link).

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
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

API_URL = "https://api.monday.com/v2"
API_VERSION = "2025-04"
ENV_TOKEN = "MONDAY_API_TOKEN"
DEFAULT_REF = "op://Trading/Monday.com/api_token"
DEFAULT_BOARD = "Algo Trading"
BATCH = 10                 # mutations per API call
FREE_ITEM_LIMIT = 200
ITEM_NAME_MAX = 255

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REPO_GUESSES = [REPO, Path(r"D:\Trading")]
# Board exports are written by a Claude chat and delivered like any other file it
# makes, so they arrive in "Claude outputs". The clickup\ folder is where the first
# export went on 2026-09-19 and is still read so nothing has to be moved by hand.
EXPORT_DIRS = [REPO / "Claude outputs" / "boards", REPO / "Claude outputs" / "clickup"]
# Maps and run reports are machine-local output: var\ is gitignored.
STATE_DIR = REPO / "var" / "boards"
# ClickUp links for the ClickUp column: the current map, else where the first sync
# wrote it (beside the old copy of clickup_sync.py).
CLICKUP_MAPS = [STATE_DIR / "clickup_map.json", REPO / "Claude outputs" / "clickup" / "clickup_map.json"]

BOARD_STATUSES = ["Waiting on Ben", "Next up", "In progress", "Blocked",
                  "Backlog", "Done", "Dropped"]

# key -> (title, monday column type, other titles accepted as the same column)
COLUMNS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "status":     ("Status", "status", ()),
    "priority":   ("Priority", "status", ()),
    "assignee":   ("Assignee", "status", ()),
    # Who raised the task. Ben renamed this column "Claude Session" on 2026-09-19 and
    # keeps monday's built-in "Owner" people column for when Claude has its own monday
    # user (AT-82). Earlier names are still matched so an older board is not duplicated.
    "owner":      ("Claude Session", "status", ("Owner chat", "Owner")),
    "type":       ("Type", "dropdown", ()),
    "target":     ("Target date", "date", ("Due date",)),
    "done_on":    ("Done on", "date", ()),
    "task_id":    ("Task ID", "text", ()),
    "workstreams": ("Workstreams", "dropdown", ()),
    "blocked_by": ("Blocked by", "text", ()),
    "source":     ("Source doc", "text", ()),
    "notes":      ("Notes", "long_text", ()),
    "notion":     ("Notion", "link", ()),
    "clickup":    ("ClickUp", "link", ()),
    "rev":        ("Sync rev", "text", ()),
}
READ_KEYS = ("task_id", "rev", "notes")   # the only columns read back from monday


# --------------------------------------------------------------------------- output

class Log:
    """Prints and keeps every line so the run can be written to a report file."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, msg: str = "") -> None:
        self.lines.append(msg)
        try:
            print(msg)
        except UnicodeEncodeError:
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
    """Accept op:\\\\Vault\\Item\\field and op:/Vault/... as well as op://Vault/Item/field."""
    raw = raw.strip().strip('"').strip("'")
    if raw.lower().startswith("op:") and not raw.startswith("op://"):
        return "op://" + raw[3:].replace("\\", "/").lstrip("/")
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
        token = su.resolve(ENV_TOKEN, "monday.com API token")
        via = "common/secrets_util.py"
    else:
        ref = os.environ[ENV_TOKEN]
        token = _op_read(ref) if ref.startswith("op://") else ref
        via = "built-in op read"
    if not token:
        sys.exit(f"No monday.com token found (checked {ENV_TOKEN} and {DEFAULT_REF}).")
    if token.startswith("op:"):
        sys.exit("The token still looks like a 1Password reference -- it was not resolved. "
                 "Check the reference is op://Vault/Item/field.")
    log(f"token   : {mask(token)} via {via}")
    return token


# --------------------------------------------------------------------------- HTTP / GraphQL

class ApiError(RuntimeError):
    def __init__(self, msg: str, status: int = 0, code: str = ""):
        super().__init__(msg)
        self.status = status
        self.code = code


class DailyLimit(ApiError):
    pass


Transport = Callable[[str, dict, bytes], "tuple[int, dict, bytes]"]


def urllib_transport(url: str, headers: dict, data: bytes):
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()) if e.headers else {}, e.read()


def _error_code(err: dict) -> str:
    ext = err.get("extensions") or {}
    return str(ext.get("code") or err.get("error_code") or "")


class GraphQL:
    """POSTs GraphQL to monday. Paces itself, waits out rate/complexity limits, counts calls.

    `run` returns (data, errors). Errors that concern one aliased mutation in a batch are
    returned, not raised, so the other mutations in the batch still count.
    """

    def __init__(self, token: str, transport: Transport = urllib_transport,
                 min_interval: float = 0.4, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.time):
        self.token = token
        self.transport = transport
        self.min_interval = min_interval
        self.sleep = sleep
        self.clock = clock
        self._last = float("-inf")
        self.calls = 0

    def run(self, query: str, variables: Optional[dict] = None) -> tuple[dict, list]:
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        headers = {"Authorization": self.token, "Content-Type": "application/json",
                   "Accept": "application/json", "API-Version": API_VERSION}
        for attempt in range(6):
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = self.clock()
            self.calls += 1
            status, hdrs, raw = self.transport(API_URL, headers, body)
            text = raw.decode("utf-8", "replace") if raw else ""
            try:
                payload = json.loads(text) if text.strip() else {}
            except json.JSONDecodeError:
                payload = {}
            errors = payload.get("errors") or []
            if payload.get("error_code") or payload.get("error_message"):
                errors = errors + [{"message": payload.get("error_message", ""),
                                    "extensions": {"code": payload.get("error_code", "")}}]
            codes = {_error_code(e) for e in errors}
            if "DAILY_LIMIT_EXCEEDED" in codes or "DailyLimitExceeded" in codes:
                raise DailyLimit("monday.com daily API limit reached (1,000 calls a day on "
                                 "Free, shared with the Claude connector). Try again tomorrow.",
                                 status, "DAILY_LIMIT_EXCEEDED")
            if status == 429 or codes & {"RATE_LIMIT_EXCEEDED", "ComplexityException",
                                         "COMPLEXITY_BUDGET_EXHAUSTED",
                                         "maxConcurrencyExceeded"}:
                self.sleep(self._retry_after(hdrs, errors))
                continue
            if status >= 500 and attempt < 3:
                self.sleep(2.0 * (attempt + 1))
                continue
            if status == 401 or status == 403 or codes & {"UNAUTHORIZED", "USER_UNAUTHORIZED"}:
                raise ApiError(f"HTTP {status}: monday rejected the token -- "
                               f"{text[:300]}", status, "UNAUTHORIZED")
            if status >= 400:
                raise ApiError(f"HTTP {status}: {text[:400]}", status)
            data = payload.get("data")
            if data is None and errors:
                raise ApiError("; ".join(e.get("message", "?") for e in errors)[:600], status,
                               next(iter(codes), ""))
            return data or {}, errors
        raise ApiError("rate limited six times in a row", 429)

    def _retry_after(self, hdrs: dict, errors: list) -> float:
        low = {k.lower(): v for k, v in hdrs.items()}
        if "retry-after" in low:
            try:
                return max(1.0, min(65.0, float(low["retry-after"])))
            except ValueError:
                pass
        for e in errors:
            ext = e.get("extensions") or {}
            for k in ("retry_in_seconds", "reset_in_x_seconds"):
                if k in ext:
                    try:
                        return max(1.0, min(65.0, float(ext[k])))
                    except (TypeError, ValueError):
                        pass
            m = re.search(r"reset in (\d+) seconds", e.get("message", ""))
            if m:
                return max(1.0, min(65.0, float(m.group(1))))
        return 20.0


# --------------------------------------------------------------------------- monday operations

ITEM_FIELDS = "id name group { id } updates(limit: 1) { id } column_values(ids: $cols) { id text }"


class Monday:
    """The handful of monday.com operations the sync needs. Swapped for a fake in tests.

    Writes are batched: create_items / update_items / move_items take lists and send
    BATCH aliased mutations per call. In dry-run mode no write is sent; each one is
    recorded in `skipped_writes` and a placeholder id is returned.
    """

    def __init__(self, gql: GraphQL, dry_run: bool = False):
        self.gql = gql
        self.dry_run = dry_run
        self.writes = 0
        self.skipped_writes: list[str] = []

    @property
    def calls(self) -> int:
        return self.gql.calls

    # -- reads
    def me(self) -> dict:
        data, _ = self.gql.run("query { me { id name account { id name slug tier } } }")
        return data.get("me") or {}

    def boards(self) -> list[dict]:
        out, page = [], 1
        while True:
            data, _ = self.gql.run(
                "query ($p: Int!) { boards(limit: 100, page: $p, state: active) "
                "{ id name board_kind items_count workspace { id name } } }", {"p": page})
            got = data.get("boards") or []
            out += got
            if len(got) < 100:
                return out
            page += 1

    def board(self, board_id: str) -> dict:
        data, _ = self.gql.run(
            "query ($b: [ID!]) { boards(ids: $b) { id name items_count "
            "columns { id title type } groups { id title } } }", {"b": [board_id]})
        got = data.get("boards") or []
        if not got:
            raise ApiError(f"board {board_id} not found")
        return got[0]

    def items(self, board_id: str, column_ids: list[str]) -> list[dict]:
        data, _ = self.gql.run(
            "query ($b: [ID!], $cols: [String!]) { boards(ids: $b) { items_page(limit: 500) "
            "{ cursor items { " + ITEM_FIELDS + " } } } }",
            {"b": [board_id], "cols": column_ids})
        page = ((data.get("boards") or [{}])[0] or {}).get("items_page") or {}
        items, cursor = list(page.get("items") or []), page.get("cursor")
        while cursor:
            data, _ = self.gql.run(
                "query ($c: String!, $cols: [String!]) { next_items_page(limit: 500, cursor: $c) "
                "{ cursor items { " + ITEM_FIELDS + " } } }", {"c": cursor, "cols": column_ids})
            page = data.get("next_items_page") or {}
            items += page.get("items") or []
            cursor = page.get("cursor")
        return items

    # -- structure writes (few, one call each)
    def _write(self, label: str, query: str, variables: dict, pick: Callable[[dict], str]) -> str:
        if self.dry_run:
            self.skipped_writes.append(label)
            return f"dry-{len(self.skipped_writes)}"
        self.writes += 1
        data, errors = self.gql.run(query, variables)
        try:
            return str(pick(data))
        except (KeyError, TypeError):
            raise ApiError(f"{label} failed: " + "; ".join(e.get("message", "?") for e in errors))

    def create_board(self, name: str, workspace_id: Optional[str]) -> str:
        q = ("mutation ($n: String!, $w: ID) { create_board(board_name: $n, board_kind: public, "
             "workspace_id: $w) { id } }")
        return self._write(f"create board '{name}'", q, {"n": name, "w": workspace_id},
                           lambda d: d["create_board"]["id"])

    def create_column(self, board_id: str, title: str, ctype: str) -> str:
        q = ("mutation ($b: ID!, $t: String!) { create_column(board_id: $b, title: $t, "
             f"column_type: {ctype}) {{ id }} }}")
        return self._write(f"create column '{title}' ({ctype})", q, {"b": board_id, "t": title},
                           lambda d: d["create_column"]["id"])

    def create_group(self, board_id: str, title: str) -> str:
        q = ("mutation ($b: ID!, $t: String!) { create_group(board_id: $b, group_name: $t) { id } }")
        return self._write(f"create group '{title}'", q, {"b": board_id, "t": title},
                           lambda d: d["create_group"]["id"])

    def delete_group(self, board_id: str, group_id: str, title: str) -> str:
        q = "mutation ($b: ID!, $g: String!) { delete_group(board_id: $b, group_id: $g) { id } }"
        return self._write(f"delete empty group '{title}'", q, {"b": board_id, "g": group_id},
                           lambda d: d["delete_group"]["id"])

    # -- item writes (batched)
    def _batch(self, ops: list[dict], build: Callable[[int, dict], tuple[str, str, dict]],
               field: str) -> dict:
        """ops: [{'key': AT-n, ...}]. Returns {key: id or ApiError}."""
        results: dict = {}
        for start in range(0, len(ops), BATCH):
            chunk = ops[start:start + BATCH]
            if self.dry_run:
                for op in chunk:
                    self.skipped_writes.append(f"{field} {op['key']}")
                    results[op["key"]] = f"dry-{op['key']}"
                continue
            decls, parts, variables = [], [], {}
            for i, op in enumerate(chunk):
                d, body, v = build(i, op)
                decls.append(d)
                parts.append(f"a{i}: {body} {{ id }}")
                variables.update(v)
            query = "mutation (" + ", ".join(decls) + ") { " + " ".join(parts) + " }"
            self.writes += len(chunk)
            try:
                data, errors = self.gql.run(query, variables)
            except ApiError as e:
                if isinstance(e, DailyLimit):
                    raise
                for op in chunk:
                    results[op["key"]] = e
                continue
            by_alias: dict[str, list[str]] = {}
            for err in errors:
                path = err.get("path") or []
                if path:
                    by_alias.setdefault(str(path[0]), []).append(err.get("message", "?"))
            for i, op in enumerate(chunk):
                node = (data or {}).get(f"a{i}")
                if node and node.get("id"):
                    results[op["key"]] = str(node["id"])
                else:
                    msg = "; ".join(by_alias.get(f"a{i}", [])) or \
                          "; ".join(e.get("message", "?") for e in errors) or "no id returned"
                    results[op["key"]] = ApiError(msg)
        return results

    def create_items(self, board_id: str, ops: list[dict]) -> dict:
        """ops: {'key', 'group_id', 'name', 'values'}."""
        def build(i, op):
            return (f"$n{i}: String!, $g{i}: String, $v{i}: JSON",
                    f"create_item(board_id: $b, group_id: $g{i}, item_name: $n{i}, "
                    f"column_values: $v{i}, create_labels_if_missing: true)",
                    {"b": board_id, f"n{i}": op["name"], f"g{i}": op["group_id"],
                     f"v{i}": json.dumps(op["values"], ensure_ascii=False)})
        return self._batch(ops, _with_board(build), "create_item")

    def update_items(self, board_id: str, ops: list[dict]) -> dict:
        """ops: {'key', 'item_id', 'values'} -- values may include 'name'."""
        def build(i, op):
            return (f"$i{i}: ID!, $v{i}: JSON!",
                    f"change_multiple_column_values(board_id: $b, item_id: $i{i}, "
                    f"column_values: $v{i}, create_labels_if_missing: true)",
                    {"b": board_id, f"i{i}": op["item_id"],
                     f"v{i}": json.dumps(op["values"], ensure_ascii=False)})
        return self._batch(ops, _with_board(build), "update_item")

    def post_updates(self, ops: list[dict]) -> dict:
        """ops: {'key', 'item_id', 'body'} -- body is HTML. Posts to the item's Updates tab."""
        def build(i, op):
            return (f"$i{i}: ID!, $u{i}: String!",
                    f"create_update(item_id: $i{i}, body: $u{i})",
                    {f"i{i}": op["item_id"], f"u{i}": op["body"]})
        return self._batch(ops, build, "post_update")

    def move_items(self, ops: list[dict]) -> dict:
        """ops: {'key', 'item_id', 'group_id'}."""
        def build(i, op):
            return (f"$i{i}: ID!, $g{i}: String!",
                    f"move_item_to_group(item_id: $i{i}, group_id: $g{i})",
                    {f"i{i}": op["item_id"], f"g{i}": op["group_id"]})
        return self._batch(ops, build, "move_item")


def _with_board(build):
    """Declare $b: ID! once per batch for builders that use it."""
    def wrapped(i, op):
        decl, body, v = build(i, op)
        if i == 0:
            decl = "$b: ID!, " + decl
        return decl, body, v
    return wrapped


# --------------------------------------------------------------------------- board export

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
        if t["status"] not in BOARD_STATUSES:
            sys.exit(f"{t['id']}: unknown status '{t['status']}'")
    return board


def newest_board(folders: list[Path]) -> Optional[Path]:
    found = []
    for f in folders:
        if f.exists():
            found += list(f.glob("algo_board_*.json"))
    # newest by the date in the name, then by modification time
    found.sort(key=lambda p: (p.name, p.stat().st_mtime))
    return found[-1] if found else None


def load_clickup_links(path: Path) -> dict:
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
        return {k: v.get("url") for k, v in (m.get("tasks") or {}).items() if v.get("url")}
    except (OSError, ValueError, AttributeError):
        return {}


def plain(text: Optional[str]) -> str:
    """monday text columns do not render markdown: drop the backticks."""
    return (text or "").replace("`", "").strip()


def item_name(t: dict) -> str:
    name = f"{t['id']} · {t['name']}"
    return name if len(name) <= ITEM_NAME_MAX else name[:ITEM_NAME_MAX - 1] + "…"


def revision(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:10]


def update_html(text: str) -> str:
    """Notes text -> the HTML monday's Updates tab renders: one paragraph per line, the
    dated prefix of each note ('2026-09-19 -- ...' / '2026-09-19 14:30 -- ...') in bold."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        m = re.match(r"^(\d{4}-\d{2}-\d{2}(?: \d{1,2}:\d{2})?\s*[\u2014-]+)(.*)$", esc)
        out.append(f"<p><b>{m.group(1)}</b>{m.group(2)}</p>" if m else f"<p>{esc}</p>")
    return "".join(out)


def new_note_text(new: str, old: str) -> str:
    """The part of the Notes that is new since monday last saw them.

    Chats add each note as a dated line at the TOP and keep the earlier ones, so the
    usual change is `new == <added lines> + old`: post only the added lines. Anything
    else (an edit in the middle, a rewrite) posts the whole Notes, so nothing is lost."""
    new, old = (new or "").strip(), (old or "").strip()
    if not new or new == old:
        return ""
    if old and new.endswith(old):
        return new[: len(new) - len(old)].strip()
    return new


def assignee_of(t: dict) -> Optional[str]:
    """Who is looking after the card now. Exports written before the Assignee field
    existed (2026-09-19 afternoon) only had `owner`, which then meant the same thing."""
    return t.get("assignee") or t.get("owner")


def card_values(t: dict, col: dict, clickup_url: Optional[str]) -> dict:
    """Column values for one card, keyed by monday column id (without Sync rev)."""
    v = {
        col["status"]: {"label": t["status"]},
        col["priority"]: {"label": t["priority"]} if t.get("priority") else None,
        col["assignee"]: {"label": assignee_of(t)} if assignee_of(t) else None,
        col["owner"]: {"label": t["owner"]} if t.get("owner") else None,
        col["type"]: {"labels": [t["type"]]} if t.get("type") else None,
        col["target"]: {"date": t["target_date"]} if t.get("target_date") else None,
        col["done_on"]: {"date": t["done_on"]} if t.get("done_on") else None,
        col["task_id"]: t["id"],
        col["workstreams"]: {"labels": list(t["workstreams"])},
        col["blocked_by"]: ", ".join(t.get("blocked_by") or []),
        col["source"]: plain(t.get("source_doc")),
        col["notes"]: {"text": plain(t.get("notes"))},
        col["notion"]: ({"url": t["notion_url"], "text": f"{t['id']} in Notion"}
                        if t.get("notion_url") else None),
        col["clickup"]: ({"url": clickup_url, "text": f"{t['id']} in ClickUp"}
                         if clickup_url else None),
    }
    return v


# --------------------------------------------------------------------------- the sync

class Syncer:
    def __init__(self, api: Monday, log: Log, board_name: str = DEFAULT_BOARD,
                 clickup_links: Optional[dict] = None, tidy: bool = False):
        self.api = api
        self.log = log
        self.board_name = board_name
        self.clickup_links = clickup_links or {}
        self.tidy = tidy
        self.counts = {"created": 0, "updated": 0, "moved": 0, "unchanged": 0,
                       "notes_posted": 0, "failed": 0}
        self.failures: list[str] = []

    # -- structure
    def find_board(self) -> Optional[dict]:
        matches = [b for b in self.api.boards()
                   if b["name"].strip().lower() == self.board_name.lower()]
        if len(matches) > 1:
            self.log(f"board   : {len(matches)} boards named '{self.board_name}' -- using the "
                     f"oldest ({matches[-1]['id']})")
            return sorted(matches, key=lambda b: int(b["id"]))[0]
        return matches[0] if matches else None

    def ensure_board(self) -> dict:
        found = self.find_board()
        if found:
            self.log(f"board   : '{found['name']}' ({found['id']})")
            if str(found["id"]).startswith("dry-"):
                return {"id": found["id"], "name": self.board_name, "columns": [], "groups": []}
            return self.api.board(str(found["id"]))
        bid = self.api.create_board(self.board_name, None)
        self.log(f"board   : created '{self.board_name}' ({bid})")
        if bid.startswith("dry-"):
            return {"id": bid, "name": self.board_name, "columns": [], "groups": []}
        return self.api.board(bid)

    def ensure_columns(self, board: dict) -> dict:
        cols = board.get("columns") or []
        out = {}
        for key, (title, ctype, aliases) in COLUMNS.items():
            titles = {title.lower(), *(a.lower() for a in aliases)}
            hit = next((c for c in cols if c["title"].strip().lower() == title.lower()
                        and c["type"] == ctype), None)
            if hit is None:
                hit = next((c for c in cols if c["title"].strip().lower() in titles
                            and c["type"] == ctype), None)
            if hit is not None:
                out[key] = hit["id"]
                continue
            clash = next((c for c in cols if c["title"].strip().lower() == title.lower()), None)
            use_title = title if clash is None else (aliases[0] if aliases else f"{title} (sync)")
            out[key] = self.api.create_column(str(board["id"]), use_title, ctype)
            self.log(f"column  : created '{use_title}' ({ctype})")
        return out

    def ensure_groups(self, board: dict, workstreams: list[str]) -> dict:
        groups = {g["title"].strip(): g["id"] for g in board.get("groups") or []}
        # monday adds a new group at the top, so create the missing ones last-first to
        # end up in workstream order.
        for ws in reversed(workstreams):
            if ws not in groups:
                groups[ws] = self.api.create_group(str(board["id"]), ws)
                self.log(f"group   : created '{ws}'")
        return {ws: groups[ws] for ws in workstreams}

    # -- items
    def sync(self, export: dict) -> dict:
        tasks = export["tasks"]
        ws_names = [w["name"] for w in export["workstreams"]]
        if len(tasks) > FREE_ITEM_LIMIT - 20:
            self.log(f"warning : {len(tasks)} cards -- the Free plan stops at {FREE_ITEM_LIMIT} items")
        board = self.ensure_board()
        bid = str(board["id"])
        col = self.ensure_columns(board)
        grp = self.ensure_groups(board, ws_names)

        existing: dict[str, dict] = {}
        if not bid.startswith("dry-"):
            read_ids = [col[k] for k in READ_KEYS if not col[k].startswith("dry-")]
            for it in self.api.items(bid, read_ids):
                vals = {c["id"]: (c.get("text") or "") for c in it.get("column_values") or []}
                tid = vals.get(col["task_id"], "").strip()
                if not tid:
                    m = re.match(r"^\s*(AT-\d+)\b", it.get("name", ""))
                    tid = m.group(1) if m else ""
                if tid and tid not in existing:
                    existing[tid] = {"id": str(it["id"]), "group": (it.get("group") or {}).get("id"),
                                     "rev": vals.get(col["rev"], "").strip(),
                                     "notes": vals.get(col["notes"], ""),
                                     "has_update": bool(it.get("updates"))}
        self.log(f"items   : {len(existing)} cards already on the board")

        creates, updates, moves, notes = [], [], [], []
        for t in tasks:
            gid = grp[t["workstreams"][0]]
            values = card_values(t, col, self.clickup_links.get(t["id"]))
            name = item_name(t)
            rev = revision({"name": name, "group": t["workstreams"][0],
                            "values": {k: values[col[k]] for k in COLUMNS if k != "rev"}})
            values[col["rev"]] = rev
            cur = existing.get(t["id"])
            text = plain(t.get("notes"))
            if cur is None:
                if text:
                    notes.append((t["id"], text))
                creates.append({"key": t["id"], "group_id": gid, "name": name,
                                "values": {k: v for k, v in values.items() if v is not None}})
                continue
            # Notes go to the item's Updates tab: only what is new since monday last saw
            # them, or all of them on an item that has no update yet (the backfill).
            post = text if (text and not cur["has_update"]) else new_note_text(text, cur["notes"])
            if post:
                notes.append((t["id"], post))
            if cur["group"] != gid:
                moves.append({"key": t["id"], "item_id": cur["id"], "group_id": gid})
            if cur["rev"] != rev:
                updates.append({"key": t["id"], "item_id": cur["id"],
                                "values": {"name": name, **{k: ("" if v is None else v)
                                                            for k, v in values.items()}}})
            elif cur["group"] == gid:
                self.counts["unchanged"] += 1

        ids = {k: v["id"] for k, v in existing.items()}
        for key, res in self.api.create_items(bid, creates).items():
            self._tally(key, res, "created", "create", ids)
        for key, res in self.api.move_items(moves).items():
            self._tally(key, res, "moved", "move", ids)
        for key, res in self.api.update_items(bid, updates).items():
            self._tally(key, res, "updated", "update", ids)
        posts = [{"key": k, "item_id": ids[k], "body": update_html(txt)} for k, txt in notes if k in ids]
        for key, res in self.api.post_updates(posts).items():
            self._tally(key, res, "notes_posted", "post notes", ids)

        if self.tidy and not bid.startswith("dry-"):
            self._tidy(board, set(grp.values()))

        slug = None
        try:
            slug = (self.api.me().get("account") or {}).get("slug")
        except ApiError:
            pass
        base = f"https://{slug}.monday.com" if slug else "https://monday.com"
        return {
            "board_id": bid,
            "board_url": f"{base}/boards/{bid}",
            "columns": col,
            "groups": grp,
            "tasks": {k: {"id": v, "url": f"{base}/boards/{bid}/pulses/{v}"}
                      for k, v in sorted(ids.items(), key=lambda kv: int(kv[0].split("-")[1]))},
        }

    def _tally(self, key: str, res, ok_count: str, verb: str, ids: dict) -> None:
        if isinstance(res, Exception):
            self.counts["failed"] += 1
            self.failures.append(f"{key}: {verb} failed -- {res}")
            self.log(f"FAILED  : {key} {verb} -- {res}")
        else:
            self.counts[ok_count] += 1
            ids.setdefault(key, res)

    def _tidy(self, board: dict, keep: set) -> None:
        board_now = self.api.board(str(board["id"]))
        items = self.api.items(str(board["id"]), [])
        used = {(it.get("group") or {}).get("id") for it in items}
        for g in board_now.get("groups") or []:
            if g["id"] not in keep and g["id"] not in used:
                self.api.delete_group(str(board["id"]), g["id"], g["title"])
                self.log(f"tidy    : deleted empty group '{g['title']}'")


# --------------------------------------------------------------------------- commands

def cmd_check(api: Monday, log: Log, board_name: str) -> int:
    me = api.me()
    acct = me.get("account") or {}
    log(f"user    : {me.get('name')} ({me.get('id')})")
    log(f"account : {acct.get('name')} -- slug '{acct.get('slug')}', tier '{acct.get('tier')}'")
    boards = api.boards()
    log(f"boards  : {len(boards)} active (Free plan allows 3)")
    for b in boards:
        log(f"          {b['id']}  {b['name']}  ({b.get('items_count', '?')} items, "
            f"workspace {(b.get('workspace') or {}).get('name', '?')})")
    s = Syncer(api, log, board_name)
    found = s.find_board()
    if found:
        board = api.board(str(found["id"]))
        titles = {c["title"].lower() for c in board.get("columns") or []}
        missing = [t for k, (t, _, al) in COLUMNS.items()
                   if t.lower() not in titles and not any(a.lower() in titles for a in al)]
        log(f"target  : '{board['name']}' ({board['id']}) -- {board.get('items_count', '?')} items, "
            f"{len(board.get('groups') or [])} groups")
        log("columns : " + (("sync will add " + ", ".join(missing)) if missing else "all present"))
    else:
        log(f"target  : no board named '{board_name}' -- sync will create it")
    log(f"api     : {api.calls} calls used by this check")
    return 0


def cmd_sync(api: Monday, log: Log, board_path: Path, board_name: str, out_dir: Path,
             tidy: bool) -> int:
    export = load_board(board_path)
    log(f"export  : {board_path} -- {len(export['tasks'])} cards, "
        f"{len(export['workstreams'])} workstreams (exported {export.get('exported', '?')})")
    links, src = {}, None
    for cand in CLICKUP_MAPS:
        links = load_clickup_links(cand)
        if links:
            src = cand
            break
    log(f"clickup : {len(links)} links from {src}" if links
        else "clickup : no clickup_map.json found -- ClickUp column left empty")
    s = Syncer(api, log, board_name, links, tidy)
    result = s.sync(export)
    log("")
    log("result  : " + ", ".join(f"{k} {v}" for k, v in s.counts.items()))
    log(f"api     : {api.calls} calls ({api.writes} changes sent)")
    if api.dry_run:
        log(f"DRY RUN : nothing was changed. {len(api.skipped_writes)} changes would have been sent.")
        for w in api.skipped_writes[:15]:
            log(f"          {w}")
        if len(api.skipped_writes) > 15:
            log(f"          ... and {len(api.skipped_writes) - 15} more")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        map_path = out_dir / "monday_map.json"
        map_path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
        log(f"board   : {result['board_url']}")
        log(f"map     : {map_path}")
    if s.failures:
        log("")
        log(f"{len(s.failures)} card(s) failed; re-running sync retries them.")
        return 2
    return 0


def main(argv: Optional[list] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Mirror the Algo Trading board into monday.com.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="test the token and show the account, boards and columns")
    sp = sub.add_parser("sync", help="create or update the board, groups and items from an export")
    sp.add_argument("--board", type=Path,
                    help="board export (default: newest algo_board_*.json in Claude outputs\\boards)")
    sp.add_argument("--dry-run", action="store_true", help="read only; list what would change")
    sp.add_argument("--tidy", action="store_true",
                    help="delete empty groups that are not workstreams (e.g. To-Do, Completed)")
    for p in sub.choices.values():
        p.add_argument("--board-name", default=DEFAULT_BOARD,
                       help=f"monday board name (default '{DEFAULT_BOARD}')")
    args = ap.parse_args(argv)

    log = Log()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log(f"monday_sync {args.cmd} -- {stamp}")
    code = 1
    try:
        token = resolve_token(log)
        api = Monday(GraphQL(token), dry_run=getattr(args, "dry_run", False))
        if args.cmd == "check":
            code = cmd_check(api, log, args.board_name)
        else:
            path = args.board or newest_board(EXPORT_DIRS)
            if not path or not path.exists():
                sys.exit("No board export found. Put algo_board_YYYYMMDD.json in "
                         f"{EXPORT_DIRS[0]} or pass --board.")
            code = cmd_sync(api, log, path, args.board_name, STATE_DIR, args.tidy)
    except ApiError as e:
        log(f"ERROR   : {e}")
        if e.code == "UNAUTHORIZED":
            log("          Check the 1Password item holds your personal API token "
                "(monday: avatar > Developers > My access tokens).")
    finally:
        report = STATE_DIR / f"monday_sync_{stamp}.txt"
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            log.write(report)
            print(f"report  : {report}")
        except OSError:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
