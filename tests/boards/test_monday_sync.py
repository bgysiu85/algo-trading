"""Tests for boards/monday_sync.py -- no network: an in-memory monday board and a fake HTTP layer."""
import json
import unittest
from pathlib import Path

from boards import monday_sync as ms

HERE = Path(__file__).resolve().parent
EXPORT = HERE / "fixtures" / "algo_board_20260919.json"


class FakeMonday:
    """In-memory monday board with the same surface as monday_sync.Monday."""

    def __init__(self, with_template_board=True, dry_run=False, fail_keys=()):
        self.dry_run = dry_run
        self.calls = 0
        self.writes = 0
        self.skipped_writes = []
        self.fail_keys = set(fail_keys)
        self._n = 1000
        self.boards_ = {}
        if with_template_board:
            self.boards_["5031413876"] = {
                "id": "5031413876", "name": "Algo Trading",
                "columns": [{"id": "name", "title": "Name", "type": "name"},
                            {"id": "project_owner", "title": "Owner", "type": "people"},
                            {"id": "project_status", "title": "Status", "type": "status"},
                            {"id": "date", "title": "Due date", "type": "date"}],
                "groups": [{"id": "g_todo", "title": "To-Do"}, {"id": "g_done", "title": "Completed"}],
                "items": {}}

    def _id(self):
        self._n += 1
        return str(self._n)

    def _w(self, label, n=1):
        if self.dry_run:
            self.skipped_writes.append(label)
            return False
        self.writes += n
        return True

    # reads
    def me(self):
        self.calls += 1
        return {"id": "1", "name": "Ben", "account": {"slug": "ben-siu", "tier": "free", "name": "x"}}

    def boards(self):
        self.calls += 1
        return [{"id": b["id"], "name": b["name"], "items_count": len(b["items"])}
                for b in self.boards_.values()]

    def board(self, bid):
        self.calls += 1
        b = self.boards_[bid]
        return {"id": bid, "name": b["name"], "items_count": len(b["items"]),
                "columns": [dict(c) for c in b["columns"]], "groups": [dict(g) for g in b["groups"]]}

    def items(self, bid, cols):
        self.calls += 1
        out = []
        for iid, it in self.boards_[bid]["items"].items():
            cv = [{"id": c, "text": self._text(it["values"].get(c))} for c in cols]
            out.append({"id": iid, "name": it["name"], "group": {"id": it["group"]},
                        "updates": [{"id": "u"}] if it.get("updates") else [],
                        "column_values": cv})
        return out

    @staticmethod
    def _text(v):
        if v is None or v == "":
            return ""
        if isinstance(v, dict) and set(v) == {"text"}:      # long_text reads back as its text
            return v["text"]
        return v if isinstance(v, str) else json.dumps(v)

    # structure
    def create_board(self, name, ws):
        self.calls += 1
        if not self._w(f"create board {name}"):
            return "dry-board"
        bid = self._id()
        self.boards_[bid] = {"id": bid, "name": name, "columns": [{"id": "name", "title": "Name",
                             "type": "name"}], "groups": [], "items": {}}
        return bid

    def create_column(self, bid, title, ctype):
        self.calls += 1
        if not self._w(f"create column {title}"):
            return f"dry-col-{title}"
        cid = f"c_{title.lower().replace(' ', '_')}"
        self.boards_[bid]["columns"].append({"id": cid, "title": title, "type": ctype})
        return cid

    def create_group(self, bid, title):
        self.calls += 1
        if not self._w(f"create group {title}"):
            return f"dry-grp-{title}"
        gid = f"g{self._id()}"
        self.boards_[bid]["groups"].insert(0, {"id": gid, "title": title})
        return gid

    def delete_group(self, bid, gid, title):
        self.calls += 1
        if self._w(f"delete group {title}"):
            self.boards_[bid]["groups"] = [g for g in self.boards_[bid]["groups"] if g["id"] != gid]
        return gid

    # batched items
    def _batch(self, ops, fn, label):
        res = {}
        for i in range(0, len(ops), ms.BATCH):
            chunk = ops[i:i + ms.BATCH]
            if self.dry_run:
                for op in chunk:
                    self.skipped_writes.append(f"{label} {op['key']}")
                    res[op["key"]] = f"dry-{op['key']}"
                continue
            self.calls += 1
            self.writes += len(chunk)
            for op in chunk:
                if op["key"] in self.fail_keys:
                    res[op["key"]] = ms.ApiError("boom")
                else:
                    res[op["key"]] = fn(op)
        return res

    def create_items(self, bid, ops):
        def fn(op):
            iid = self._id()
            self.boards_[bid]["items"][iid] = {"name": op["name"], "group": op["group_id"],
                                               "values": dict(op["values"])}
            return iid
        return self._batch(ops, fn, "create_item")

    def update_items(self, bid, ops):
        def fn(op):
            it = self.boards_[bid]["items"][op["item_id"]]
            vals = dict(op["values"])
            if "name" in vals:
                it["name"] = vals.pop("name")
            it["values"].update(vals)
            return op["item_id"]
        return self._batch(ops, fn, "update_item")

    def post_updates(self, ops):
        def fn(op):
            for b in self.boards_.values():
                if op["item_id"] in b["items"]:
                    b["items"][op["item_id"]].setdefault("updates", []).append(op["body"])
            return "upd-" + op["item_id"]
        return self._batch(ops, fn, "post_update")

    def move_items(self, ops):
        def fn(op):
            for b in self.boards_.values():
                if op["item_id"] in b["items"]:
                    b["items"][op["item_id"]]["group"] = op["group_id"]
            return op["item_id"]
        return self._batch(ops, fn, "move_item")


def export():
    return ms.load_board(EXPORT)


class Silent(ms.Log):
    def __call__(self, msg=""):
        self.lines.append(msg)


class TestSync(unittest.TestCase):
    def setUp(self):
        self.ex = export()
        self.n = len(self.ex["tasks"])

    def run_sync(self, api, **kw):
        s = ms.Syncer(api, Silent(), **kw)
        return s, s.sync(self.ex)

    def test_export_shape(self):
        self.assertEqual(self.n, 72)
        self.assertEqual(len(self.ex["workstreams"]), 12)

    def test_first_sync_uses_existing_board_and_creates_everything(self):
        api = FakeMonday()
        s, res = self.run_sync(api)
        b = api.boards_["5031413876"]
        self.assertEqual(res["board_id"], "5031413876")
        self.assertEqual(len(b["items"]), 72)
        self.assertEqual(s.counts["created"], 72)
        self.assertEqual(s.counts["failed"], 0)
        # existing Status / Due date columns reused, not duplicated
        self.assertEqual(res["columns"]["status"], "project_status")
        self.assertEqual(res["columns"]["target"], "date")
        titles = [c["title"] for c in b["columns"]]
        self.assertEqual(len(titles), len(set(titles)))
        # groups in workstream order at the top, template groups still below
        ws = [w["name"] for w in self.ex["workstreams"]]
        self.assertEqual([g["title"] for g in b["groups"]][:12], ws)
        self.assertIn("AT-1", res["tasks"])
        self.assertTrue(res["tasks"]["AT-1"]["url"].startswith("https://ben-siu.monday.com/boards/5031413876/pulses/"))

    def test_item_calls_are_batched(self):
        api = FakeMonday()
        self.run_sync(api)
        # 72 creates and ~66 note posts at 10 per call = ~15 calls; the one-off column and
        # group set-up is most of the rest. The whole first run stays well under 50.
        self.assertLess(api.calls, 50)

    def test_second_run_changes_nothing(self):
        api = FakeMonday()
        self.run_sync(api)
        before = api.writes
        s, _ = self.run_sync(api)
        self.assertEqual(api.writes, before)
        self.assertEqual(s.counts["unchanged"], 72)
        self.assertEqual(s.counts["created"] + s.counts["updated"] + s.counts["moved"], 0)

    def test_changed_card_is_updated_only(self):
        api = FakeMonday()
        self.run_sync(api)
        self.ex["tasks"][0]["status"] = "Done"
        self.ex["tasks"][0]["done_on"] = "2026-09-19"
        s, res = self.run_sync(api)
        self.assertEqual(s.counts["updated"], 1)
        self.assertEqual(s.counts["unchanged"], 71)
        item = api.boards_["5031413876"]["items"][res["tasks"]["AT-1"]["id"]]
        self.assertEqual(item["values"]["project_status"], {"label": "Done"})

    def test_cleared_field_sends_empty_string(self):
        api = FakeMonday()
        _, res = self.run_sync(api)
        t = self.ex["tasks"][0]
        self.assertTrue(t["target_date"])
        t["target_date"] = None
        self.run_sync(api)
        item = api.boards_["5031413876"]["items"][res["tasks"]["AT-1"]["id"]]
        self.assertEqual(item["values"]["date"], "")

    def test_workstream_change_moves_item(self):
        api = FakeMonday()
        _, res = self.run_sync(api)
        self.ex["tasks"][0]["workstreams"] = ["Program admin"]
        s, res2 = self.run_sync(api)
        self.assertEqual(s.counts["moved"], 1)
        item = api.boards_["5031413876"]["items"][res["tasks"]["AT-1"]["id"]]
        self.assertEqual(item["group"], res2["groups"]["Program admin"])

    def test_match_by_name_prefix_when_task_id_blank(self):
        api = FakeMonday()
        _, res = self.run_sync(api)
        col = res["columns"]
        for it in api.boards_["5031413876"]["items"].values():
            it["values"][col["task_id"]] = ""
        s, _ = self.run_sync(api)
        self.assertEqual(s.counts["created"], 0)
        self.assertEqual(len(api.boards_["5031413876"]["items"]), 72)

    def test_dry_run_changes_nothing(self):
        api = FakeMonday(dry_run=True)
        s, _ = self.run_sync(api)
        self.assertEqual(api.writes, 0)
        self.assertEqual(api.boards_["5031413876"]["items"], {})
        self.assertGreaterEqual(len(api.skipped_writes), 72)

    def test_creates_board_when_missing(self):
        api = FakeMonday(with_template_board=False)
        _, res = self.run_sync(api)
        self.assertEqual(len(api.boards_), 1)
        self.assertEqual(len(api.boards_[res["board_id"]]["items"]), 72)

    def test_dry_run_with_no_board(self):
        api = FakeMonday(with_template_board=False, dry_run=True)
        s, _ = self.run_sync(api)
        self.assertEqual(api.boards_, {})
        self.assertEqual(s.counts["failed"], 0)

    def test_failure_is_reported_and_retried(self):
        api = FakeMonday(fail_keys={"AT-5"})
        s, res = self.run_sync(api)
        self.assertEqual(s.counts["failed"], 1)
        self.assertNotIn("AT-5", res["tasks"])
        api.fail_keys = set()
        s2, res2 = self.run_sync(api)
        self.assertEqual(s2.counts["created"], 1)
        self.assertIn("AT-5", res2["tasks"])

    def test_tidy_removes_only_empty_non_workstream_groups(self):
        api = FakeMonday()
        self.run_sync(api, tidy=True)
        titles = [g["title"] for g in api.boards_["5031413876"]["groups"]]
        self.assertNotIn("To-Do", titles)
        self.assertNotIn("Completed", titles)
        self.assertEqual(len(titles), 12)

    def test_clickup_links_and_values(self):
        api = FakeMonday()
        _, res = self.run_sync(api, clickup_links={"AT-1": "https://app.clickup.com/t/abc"})
        col = res["columns"]
        v = api.boards_["5031413876"]["items"][res["tasks"]["AT-1"]["id"]]["values"]
        self.assertEqual(v[col["clickup"]]["url"], "https://app.clickup.com/t/abc")
        self.assertEqual(v[col["task_id"]], "AT-1")
        self.assertNotIn("`", v[col["source"]])
        self.assertEqual(v[col["workstreams"]], {"labels": ["Live watchlist feed (TradingView)"]})
        self.assertEqual(v[col["priority"]], {"label": "P1 · now"})

    def test_blocked_by_text(self):
        api = FakeMonday()
        _, res = self.run_sync(api)
        col = res["columns"]
        with_deps = [t for t in self.ex["tasks"] if t["blocked_by"]]
        self.assertTrue(with_deps)
        t = with_deps[0]
        v = api.boards_["5031413876"]["items"][res["tasks"][t["id"]]["id"]]["values"]
        self.assertEqual(v[col["blocked_by"]], ", ".join(t["blocked_by"]))


def make_transport(responses, seen):
    """responses: list of (status, headers, payload-dict)."""
    def t(url, headers, data):
        seen.append(json.loads(data))
        status, hdrs, payload = responses.pop(0)
        return status, hdrs, json.dumps(payload).encode()
    return t


class TestGraphQL(unittest.TestCase):
    def gql(self, responses, seen):
        slept = []
        g = ms.GraphQL("tok", transport=make_transport(responses, seen), sleep=slept.append,
                       clock=lambda: 0.0, min_interval=0)
        return g, slept

    def test_batch_query_shape_and_partial_error(self):
        seen = []
        ops = [{"key": f"AT-{i}", "group_id": "g1", "name": f"AT-{i} · x", "values": {"t": "x"}}
               for i in range(1, 13)]
        resp1 = {"data": {f"a{i}": {"id": str(100 + i)} for i in range(10)}}
        resp1["data"]["a3"] = None
        resp1["errors"] = [{"message": "bad label", "path": ["a3"]}]
        resp2 = {"data": {"a0": {"id": "200"}, "a1": {"id": "201"}}}
        g, _ = self.gql([(200, {}, resp1), (200, {}, resp2)], seen)
        res = ms.Monday(g).create_items("55", ops)
        self.assertEqual(len(seen), 2)                       # 12 items -> 2 calls
        q = seen[0]["query"]
        self.assertEqual(q.count("$b: ID!"), 1)
        self.assertEqual(q.count("create_item("), 10)
        self.assertEqual(seen[0]["variables"]["b"], "55")
        self.assertIsInstance(res["AT-4"], ms.ApiError)
        self.assertIn("bad label", str(res["AT-4"]))
        self.assertEqual(res["AT-1"], "100")
        self.assertEqual(res["AT-12"], "201")
        # column values travel as a JSON string variable, unicode intact
        self.assertEqual(json.loads(seen[0]["variables"]["v0"]), {"t": "x"})

    def test_retry_on_429_and_complexity(self):
        seen = []
        g, slept = self.gql([
            (429, {"Retry-After": "7"}, {"errors": [{"message": "rate"}]}),
            (200, {}, {"errors": [{"message": "Complexity budget exhausted",
                                   "extensions": {"code": "COMPLEXITY_BUDGET_EXHAUSTED",
                                                  "retry_in_seconds": 12}}]}),
            (200, {}, {"data": {"me": {"id": "1"}}}),
        ], seen)
        data, _ = g.run("query { me { id } }")
        self.assertEqual(data["me"]["id"], "1")
        self.assertEqual(slept, [7.0, 12.0])
        self.assertEqual(g.calls, 3)

    def test_daily_limit_stops(self):
        seen = []
        g, _ = self.gql([(200, {}, {"errors": [{"message": "Daily limit exceeded",
                                                "extensions": {"code": "DAILY_LIMIT_EXCEEDED"}}]})],
                        seen)
        with self.assertRaises(ms.DailyLimit):
            g.run("query { me { id } }")

    def test_unauthorized(self):
        seen = []
        g, _ = self.gql([(401, {}, {"error_message": "Not Authenticated"})], seen)
        with self.assertRaises(ms.ApiError) as cm:
            g.run("query { me { id } }")
        self.assertEqual(cm.exception.code, "UNAUTHORIZED")

    def test_headers(self):
        captured = {}

        def t(url, headers, data):
            captured.update(headers)
            return 200, {}, b'{"data": {}}'
        ms.GraphQL("secret-token", transport=t, sleep=lambda s: None).run("query { me { id } }")
        self.assertEqual(captured["Authorization"], "secret-token")
        self.assertEqual(captured["API-Version"], ms.API_VERSION)

    def test_dry_run_monday_sends_nothing(self):
        seen = []
        g, _ = self.gql([], seen)
        m = ms.Monday(g, dry_run=True)
        m.create_column("1", "Priority", "status")
        m.create_items("1", [{"key": "AT-1", "group_id": "g", "name": "n", "values": {}}])
        self.assertEqual(seen, [])
        self.assertEqual(len(m.skipped_writes), 2)


class TestHelpers(unittest.TestCase):
    def test_normalise_ref(self):
        self.assertEqual(ms.normalise_ref(r"op:\\Trading\Monday.com\api_token"),
                         "op://Trading/Monday.com/api_token")
        self.assertEqual(ms.normalise_ref("op://Trading/Monday.com/api_token"),
                         "op://Trading/Monday.com/api_token")

    def test_mask(self):
        self.assertNotIn("abcdefghijkl", ms.mask("abcdefghijklmnop"))

    def test_item_name_limit(self):
        t = {"id": "AT-9", "name": "x" * 400}
        self.assertLessEqual(len(ms.item_name(t)), 255)


if __name__ == "__main__":
    unittest.main()


def _item(api, res, key):
    return api.boards_["5031413876"]["items"][res["tasks"][key]["id"]]


class TestNotesAsUpdates:
    """Ben, 2026-09-19: on monday he reads a card's notes on the item's Updates tab."""

    def setup_method(self):
        self.ex = export()

    def run_sync(self, api):
        s = ms.Syncer(api, Silent())
        return s, s.sync(self.ex)

    def test_first_sync_posts_each_cards_notes_once(self):
        api = FakeMonday()
        s, res = self.run_sync(api)
        with_notes = [t for t in self.ex["tasks"] if (t.get("notes") or "").strip()]
        assert s.counts["notes_posted"] == len(with_notes) > 0
        t = with_notes[0]
        ups = _item(api, res, t["id"]).get("updates", [])
        assert len(ups) == 1 and ups[0].startswith("<p>")

    def test_rerun_posts_nothing(self):
        api = FakeMonday()
        self.run_sync(api)
        s, _ = self.run_sync(api)
        assert s.counts["notes_posted"] == 0

    def test_added_note_posts_only_the_new_line(self):
        api = FakeMonday()
        _, res = self.run_sync(api)
        t = next(t for t in self.ex["tasks"] if (t.get("notes") or "").strip())
        t["notes"] = "2026-09-20 \u2014 Decided: go ahead.\n\n" + t["notes"]
        s, _ = self.run_sync(api)
        assert s.counts["notes_posted"] == 1
        last = _item(api, res, t["id"])["updates"][-1]
        assert last == "<p><b>2026-09-20 \u2014</b> Decided: go ahead.</p>"

    def test_backfill_items_that_have_no_update(self):
        api = FakeMonday()
        _, res = self.run_sync(api)
        for it in api.boards_["5031413876"]["items"].values():   # as loaded before this change
            it.pop("updates", None)
        s, _ = self.run_sync(api)
        with_notes = [t for t in self.ex["tasks"] if (t.get("notes") or "").strip()]
        assert s.counts["notes_posted"] == len(with_notes)
        s2, _ = self.run_sync(api)
        assert s2.counts["notes_posted"] == 0

    def test_dry_run_posts_nothing(self):
        api = FakeMonday(dry_run=True)
        self.run_sync(api)
        assert all(not it.get("updates") for it in api.boards_["5031413876"]["items"].values())

    def test_new_note_text_rules(self):
        assert ms.new_note_text("b\na", "a") == "b"
        assert ms.new_note_text("same", "same") == ""
        assert ms.new_note_text("rewritten", "old") == "rewritten"
        assert ms.new_note_text("", "old") == ""

    def test_update_html_escapes_and_bolds_the_date(self):
        h = ms.update_html("2026-09-19 14:30 \u2014 a < b & c\nplain line")
        assert h == "<p><b>2026-09-19 14:30 \u2014</b> a &lt; b &amp; c</p><p>plain line</p>"


class TestPostUpdatesQuery:
    def test_batch_shape(self):
        seen = []

        def t(url, headers, data):
            seen.append(json.loads(data))
            return 200, {}, json.dumps({"data": {"a0": {"id": "9"}}}).encode()
        g = ms.GraphQL("tok", transport=t, sleep=lambda s: None, min_interval=0)
        res = ms.Monday(g).post_updates([{"key": "AT-1", "item_id": "123", "body": "<p>x</p>"}])
        assert res == {"AT-1": "9"}
        q = seen[0]["query"]
        assert "create_update(item_id: $i0, body: $u0)" in q and "$u0: String!" in q
        assert seen[0]["variables"] == {"i0": "123", "u0": "<p>x</p>"}


class TestAssignee:
    """Ben, 2026-09-19: Assignee = who is looking after the task now (changes with the
    status); Owner = who raised it."""

    def test_assignee_column_set_and_separate_from_owner(self):
        ex = export()
        t = ex["tasks"][0]
        t["owner"], t["assignee"] = "Portal chat", "Ben"
        api = FakeMonday()
        s = ms.Syncer(api, Silent())
        res = s.sync(ex)
        col = res["columns"]
        v = _item(api, res, t["id"])["values"]
        assert v[col["assignee"]] == {"label": "Ben"}
        assert v[col["owner"]] == {"label": "Portal chat"}
        titles = [c["title"] for c in api.boards_["5031413876"]["columns"]]
        assert "Assignee" in titles and "Owner chat" in titles

    def test_reassigning_updates_the_item(self):
        ex = export()
        api = FakeMonday()
        ms.Syncer(api, Silent()).sync(ex)
        ex["tasks"][0]["assignee"] = "Build & test chat"
        s = ms.Syncer(api, Silent())
        res = s.sync(ex)
        assert s.counts["updated"] == 1
        assert _item(api, res, ex["tasks"][0]["id"])["values"][res["columns"]["assignee"]] == \
            {"label": "Build & test chat"}

    def test_old_export_without_assignee_falls_back_to_owner(self):
        t = {"owner": "MCL chat"}
        assert ms.assignee_of(t) == "MCL chat"


def test_owner_column_named_owner_is_used_once_the_people_column_is_gone():
    api = FakeMonday()
    b = api.boards_["5031413876"]
    b["columns"] = [c for c in b["columns"] if c["id"] != "project_owner"]
    b["columns"].append({"id": "own1", "title": "Owner", "type": "status"})
    res = ms.Syncer(api, Silent()).sync(export())
    assert res["columns"]["owner"] == "own1"
    assert "Owner chat" not in [c["title"] for c in b["columns"]]


def test_renamed_owner_chat_column_still_matched():
    api = FakeMonday()
    api.boards_["5031413876"]["columns"].append({"id": "oc", "title": "Owner chat", "type": "status"})
    res = ms.Syncer(api, Silent()).sync(export())
    assert res["columns"]["owner"] == "oc"
