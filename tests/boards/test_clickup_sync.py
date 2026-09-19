"""Tests for clickup_sync.py against an in-memory fake of the ClickUp REST API."""
import json
import re
import urllib.parse
from pathlib import Path

import pytest

from boards import clickup_sync as cs

BOARD = Path(__file__).resolve().parent / "fixtures" / "algo_board_20260919.json"
DEFAULT_STATUSES = [{"status": "to do", "type": "open"}, {"status": "in progress", "type": "custom"},
                    {"status": "complete", "type": "closed"}]
CUSTOM = [{"status": s, "type": "open"} for s in
          ("waiting on ben", "next up", "in progress", "blocked", "backlog")] + \
         [{"status": "done", "type": "done"}, {"status": "dropped", "type": "closed"}]


class FakeClickUp:
    def __init__(self, statuses=None, rate_limit_first=0):
        self.team = {"id": "900", "name": "Workspace"}
        self.spaces = {"1": {"id": "1", "name": "Space", "statuses": list(DEFAULT_STATUSES)}}
        self.lists, self.tags, self.tasks = {}, {}, {}
        self.new_statuses = statuses or DEFAULT_STATUSES
        self.seq = 1000
        self.log = []
        self.rate_limit_first = rate_limit_first
        self.page_size = 30

    def nid(self):
        self.seq += 1
        return str(self.seq)

    def __call__(self, method, url, headers, data):
        assert headers["Authorization"] == "pk_test"
        if self.rate_limit_first:
            self.rate_limit_first -= 1
            return 429, {"Retry-After": "2"}, b"{}"
        u = urllib.parse.urlparse(url)
        path, q = u.path, urllib.parse.parse_qs(u.query)
        body = json.loads(data) if data else None
        self.log.append((method, path))
        out = self.route(method, path, q, body)
        return 200, {}, json.dumps(out).encode()

    def route(self, m, p, q, b):
        if p.endswith("/api/v2/user"):
            return {"user": {"username": "Ben"}}
        if p.endswith("/api/v2/team"):
            return {"teams": [self.team]}
        mm = re.search(r"/team/900/space$", p)
        if mm and m == "GET":
            return {"spaces": list(self.spaces.values())}
        if mm and m == "POST":
            sid = self.nid()
            self.spaces[sid] = {"id": sid, "name": b["name"], "statuses": list(self.new_statuses)}
            return self.spaces[sid]
        mm = re.search(r"/space/(\d+)/list$", p)
        if mm:
            if m == "GET":
                return {"lists": [l for l in self.lists.values() if l["space"] == mm.group(1)]}
            lid = self.nid()
            self.lists[lid] = {"id": lid, "name": b["name"], "space": mm.group(1)}
            return self.lists[lid]
        mm = re.search(r"/space/(\d+)/tag$", p)
        if mm:
            if m == "GET":
                return {"tags": [{"name": n} for n in self.tags.get(mm.group(1), [])]}
            self.tags.setdefault(mm.group(1), []).append(b["tag"]["name"])
            return {}
        if re.search(r"/team/900/task$", p):
            sid = q["space_ids[]"][0]
            page = int(q["page"][0])
            mine = [t for t in self.tasks.values() if self.lists[t["list"]["id"]]["space"] == sid]
            chunk = mine[page * self.page_size:(page + 1) * self.page_size]
            return {"tasks": chunk, "last_page": (page + 1) * self.page_size >= len(mine)}
        mm = re.search(r"/list/(\d+)/task$", p)
        if mm and m == "POST":
            tid = "t" + self.nid()
            self.tasks[tid] = {"id": tid, "name": b["name"], "list": {"id": mm.group(1)},
                               "status": {"status": b["status"]}, "priority": b.get("priority"),
                               "due_date": b.get("due_date"), "text_content": b["markdown_content"],
                               "tags": [{"name": x} for x in b.get("tags", [])], "dependencies": []}
            return self.tasks[tid]
        mm = re.search(r"/task/(t\d+)$", p)
        if mm and m == "PUT":
            t = self.tasks[mm.group(1)]
            t.update({"name": b["name"], "status": {"status": b["status"]}, "priority": b["priority"],
                      "due_date": b.get("due_date"), "text_content": b["markdown_content"]})
            return t
        mm = re.search(r"/task/(t\d+)/tag/(.+)$", p)
        if mm:
            t = self.tasks[mm.group(1)]
            name = urllib.parse.unquote(mm.group(2))
            if m == "POST":
                t["tags"].append({"name": name})
            else:
                t["tags"] = [x for x in t["tags"] if x["name"] != name]
            return {}
        mm = re.search(r"/task/(t\d+)/dependency$", p)
        if mm:
            t = self.tasks[mm.group(1)]
            if m == "POST":
                t["dependencies"].append({"task_id": t["id"], "depends_on": b["depends_on"], "type": 1})
            else:
                dep = q["depends_on"][0]
                t["dependencies"] = [d for d in t["dependencies"] if d["depends_on"] != dep]
            return {}
        raise AssertionError(f"unrouted {m} {p}")

    def writes(self):
        return [x for x in self.log if x[0] != "GET"]


def run(fake, board=None, dry=False):
    log = cs.Log()
    api = cs.ClickUp("pk_test", transport=fake, min_interval=0, sleep=lambda s: None, dry_run=dry)
    s = cs.Syncer(api, log)
    res = s.sync(board or cs.load_board(BOARD))
    return s, res, api, log


def by_card(fake):
    return {cs.CARD_ID.match(t["name"]).group(1): t for t in fake.tasks.values()}


def test_normalise_ref():
    assert cs.normalise_ref(r"op:\\Trading\Clickup\api_token") == "op://Trading/Clickup/api_token"
    assert cs.normalise_ref("op:/Trading/Clickup/api_token") == "op://Trading/Clickup/api_token"
    assert cs.normalise_ref("op://Trading/Clickup/api_token") == "op://Trading/Clickup/api_token"
    assert cs.normalise_ref("pk_123") == "pk_123"


def test_first_sync_builds_everything_with_fallback_statuses():
    fake = FakeClickUp()
    s, res, api, _ = run(fake)
    board = cs.load_board(BOARD)
    assert s.counts["space"] == 1 and s.counts["lists"] == 12 and s.counts["created"] == 72
    assert len(fake.tasks) == 72
    n_deps = sum(len(t["blocked_by"]) for t in board["tasks"])
    assert s.counts["deps_added"] == n_deps == 17
    cards = by_card(fake)
    # Waiting on Ben -> default open status + stand-in tag
    at1 = cards["AT-1"]
    assert at1["status"]["status"] == "to do"
    assert {"ben", "waiting-on-ben"} <= {x["name"] for x in at1["tags"]}
    assert at1["priority"] == 1
    assert at1["name"].startswith("AT-1 · Decide: sign the TradingView")
    # Done -> the space's closed status, no stand-in tag
    assert cards["AT-57"]["status"]["status"] == "complete"
    assert "sync-rev:" in cards["AT-57"]["text_content"]
    # home list is the first workstream
    lst = fake.lists[cards["AT-15"]["list"]["id"]]["name"]
    assert lst == "Live paper trader (MCL + MC5)"
    assert "Also in workstream:** Trader portal" in cards["AT-15"]["text_content"]
    # dependency direction: AT-14 waits on AT-13
    assert cards["AT-14"]["dependencies"][0]["depends_on"] == cards["AT-13"]["id"]
    # backslashes survive into the description
    assert r"D:\Trading\Claude outputs" in cards["AT-8"]["text_content"]
    assert set(res["tasks"]) == {f"AT-{i}" for i in range(1, 73)}
    assert res["missing_statuses"]


def test_second_sync_writes_nothing():
    fake = FakeClickUp()
    run(fake)
    before = len(fake.writes())
    s, _, _, _ = run(fake)
    assert len(fake.writes()) == before
    assert s.counts["unchanged"] == 72 and s.counts["created"] == 0


def test_paging_finds_every_existing_task():
    fake = FakeClickUp()
    fake.page_size = 7
    run(fake)
    s, _, _, _ = run(fake)
    assert s.counts["created"] == 0 and len(fake.tasks) == 72


def test_changed_card_updates_status_tags_and_dependency():
    fake = FakeClickUp()
    run(fake)
    board = cs.load_board(BOARD)
    for t in board["tasks"]:
        if t["id"] == "AT-14":
            t["status"], t["blocked_by"] = "In progress", []
    s, _, _, _ = run(fake, board)
    assert s.counts["updated"] == 1 and s.counts["unchanged"] == 71
    at14 = by_card(fake)["AT-14"]
    assert at14["status"]["status"] == "in progress"
    assert "blocked" not in {x["name"] for x in at14["tags"]}
    assert at14["dependencies"] == [] and s.counts["deps_removed"] == 1


def test_custom_statuses_used_when_present_and_standins_removed():
    fake = FakeClickUp()
    run(fake)                              # created with fallback statuses
    sid = [k for k, v in fake.spaces.items() if v["name"] == "Algo Trading"][0]
    fake.spaces[sid]["statuses"] = list(CUSTOM)   # Ben adds statuses in the UI
    s, res, _, _ = run(fake)
    assert res["missing_statuses"] == []
    cards = by_card(fake)
    assert cards["AT-1"]["status"]["status"] == "waiting on ben"
    assert cards["AT-7"]["status"]["status"] == "blocked"
    assert cards["AT-57"]["status"]["status"] == "done"
    for t in cards.values():
        assert not ({x["name"] for x in t["tags"]} & set(cs.FALLBACK_TAG.values())), t["name"]


def test_existing_other_space_is_left_alone_and_own_tags_kept():
    fake = FakeClickUp()
    run(fake)
    t = by_card(fake)["AT-3"]
    t["tags"].append({"name": "my-own-tag"})
    board = cs.load_board(BOARD)
    for x in board["tasks"]:
        if x["id"] == "AT-3":
            x["owner"] = "TSMOM chat"
    run(fake, board)
    names = {x["name"] for x in by_card(fake)["AT-3"]["tags"]}
    assert "my-own-tag" in names and "tsmom-chat" in names and "ben" not in names
    assert fake.spaces["1"]["name"] == "Space"


def test_dry_run_sends_no_writes():
    fake = FakeClickUp()
    s, _, api, _ = run(fake, dry=True)
    assert fake.writes() == []
    assert len(api.skipped_writes) > 72
    assert s.counts["created"] == 72


def test_rate_limit_is_waited_out():
    fake = FakeClickUp(rate_limit_first=2)
    slept = []
    api = cs.ClickUp("pk_test", transport=fake, min_interval=0, sleep=slept.append)
    assert api.request("GET", "/team")["teams"][0]["id"] == "900"
    assert slept == [2.0, 2.0]


def test_pacing_keeps_under_limit():
    fake = FakeClickUp()
    now = [0.0]
    slept = []
    def sleep(s):
        slept.append(s)
        now[0] += s
    api = cs.ClickUp("pk_test", transport=fake, min_interval=0.65, sleep=sleep, clock=lambda: now[0])
    for _ in range(5):
        api.request("GET", "/team")
    assert len(slept) == 4 and all(abs(s - 0.65) < 1e-9 for s in slept)


def test_board_validation_rejects_bad_dependency(tmp_path):
    board = json.loads(BOARD.read_text(encoding="utf-8"))
    board["tasks"][0]["blocked_by"] = ["AT-999"]
    p = tmp_path / "b.json"
    p.write_text(json.dumps(board), encoding="utf-8")
    with pytest.raises(SystemExit):
        cs.load_board(p)


def test_http_error_raises_with_status():
    def bad(method, url, headers, data):
        return 401, {}, b'{"err":"Token invalid"}'
    api = cs.ClickUp("pk_test", transport=bad, min_interval=0, sleep=lambda s: None)
    with pytest.raises(cs.ApiError) as e:
        api.request("GET", "/team")
    assert e.value.status == 401


def test_token_via_default_reference(monkeypatch):
    monkeypatch.delenv(cs.ENV_TOKEN, raising=False)
    monkeypatch.setattr(cs, "_load_secrets_util", lambda: None)
    seen = []
    monkeypatch.setattr(cs, "_op_read", lambda ref: seen.append(ref) or "pk_abcdefghijkl")
    tok = cs.resolve_token(cs.Log())
    assert tok == "pk_abcdefghijkl" and seen == ["op://Trading/Clickup/api_token"]


def test_token_windows_style_reference_is_fixed(monkeypatch):
    monkeypatch.setenv(cs.ENV_TOKEN, r"op:\\Trading\Clickup\api_token")
    monkeypatch.setattr(cs, "_load_secrets_util", lambda: None)
    seen = []
    monkeypatch.setattr(cs, "_op_read", lambda ref: seen.append(ref) or "pk_abcdefghijkl")
    cs.resolve_token(cs.Log())
    assert seen == ["op://Trading/Clickup/api_token"]
