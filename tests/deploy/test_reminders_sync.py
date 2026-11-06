"""deploy/nas_reminders/reminders_sync.py (W11-0041 sub 9): fake feed, fake CalDAV store, fake monday, fake Telegram. No network."""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "nas_reminders" / "reminders_sync.py"
spec = importlib.util.spec_from_file_location("reminders_sync", SCRIPT)
rs = importlib.util.module_from_spec(spec)
sys.modules["reminders_sync"] = rs
spec.loader.exec_module(rs)

NOW = datetime(2026, 11, 6, 6, 0, tzinfo=timezone.utc)          # 17:00 Sydney (AEDT)
LIST = "monday reminders"


# ----------------------------------------------------------------------------------------------- fakes
def ics(events: list[tuple[str, str, datetime]]) -> str:
    out = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for uid, summary, due in events:
        out += ["BEGIN:VEVENT", f"UID:{uid}", f"SUMMARY:Reminders: {summary} (Remind at)",
                f"DTSTART:{rs.fmt_utc(due)}", f"DTEND:{rs.fmt_utc(due + timedelta(hours=1))}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out)


class FakeCalDav:
    """Just enough CalDAV: one task list. `fail` makes every call return 500."""

    def __init__(self, has_list=True, allow_mkcalendar=True):
        self.tasks: dict[str, str] = {}                           # href -> ical
        self.has_list, self.allow_mk = has_list, allow_mkcalendar
        self.calls: list[tuple[str, str]] = []
        self.fail = False
        self.hide_completed = False

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        path = url.split("//", 1)[1].split("/", 1)[1]
        path = "/" + path
        if self.fail:
            return 500, {}, b""
        if method == "PROPFIND" and headers.get("Depth") == "0":
            return 207, {}, (b'<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response>'
                             b'<d:href>/caldav/</d:href><d:propstat><d:prop><d:current-user-principal><d:href>/caldav/calendar-monday/'
                             b'</d:href></d:current-user-principal><c:calendar-home-set><d:href>/caldav/calendar-monday/</d:href>'
                             b'</c:calendar-home-set></d:prop></d:propstat></d:response></d:multistatus>')
        if method == "PROPFIND":
            lists = [("my-task", "My Task")] + ([("monday-reminders", LIST)] if self.has_list else [])
            rows = "".join(
                f'<d:response><d:href>/caldav/calendar-monday/{slug}/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/>'
                f'<c:calendar/></d:resourcetype><d:displayname>{name}</d:displayname><c:supported-calendar-component-set>'
                f'<c:comp name="VTODO"/></c:supported-calendar-component-set></d:prop></d:propstat></d:response>'
                for slug, name in lists)
            return 207, {}, ('<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">' + rows +
                             '</d:multistatus>').encode()
        if method == "MKCALENDAR":
            if not self.allow_mk:
                return 403, {}, b""
            self.has_list = True
            return 201, {}, b""
        if method == "GET":
            return (200, {}, self.tasks[path].encode()) if path in self.tasks else (404, {}, b"")
        if method == "REPORT":
            hide = self.hide_completed
            rows = "".join(f'<d:response><d:href>{h}</d:href><d:propstat><d:prop><c:calendar-data>{escape(ical)}</c:calendar-data>'
                           f'</d:prop></d:propstat></d:response>' for h, ical in self.tasks.items()
                           if not (hide and "STATUS:COMPLETED" in ical))
            return 207, {}, ('<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">' + rows +
                             '</d:multistatus>').encode()
        if method == "PUT":
            self.tasks[path] = body.decode()
            return 201, {}, b""
        if method == "DELETE":
            self.tasks.pop(path, None)
            return 204, {}, b""
        return 405, {}, b""

    def puts(self):
        return [c for c in self.calls if c[0] == "PUT"]

    def tick(self, title: str, at: datetime):
        """What the iPhone does when Ben ticks a task."""
        for h, ical in self.tasks.items():
            if f"SUMMARY:{title}" in ical:
                self.tasks[h] = ical.replace("STATUS:NEEDS-ACTION", f"STATUS:COMPLETED\r\nCOMPLETED:{rs.fmt_utc(at)}")
                return
        raise AssertionError("no such task: " + title)


class FakeMonday:
    def __init__(self, items=None):
        self.items = items or []
        self.calls: list[tuple] = []
        self.fail = False
        self.step_fail = False

    def read_board(self):
        self.calls.append(("read",))
        if self.fail:
            raise RuntimeError("monday down")
        return [dict(i) for i in self.items]

    def set_done(self, item_id):
        self.calls.append(("done", item_id))
        for i in self.items:
            if i["id"] == item_id:
                i["done"] = True

    def set_status_done(self, board_id, item_id, column):
        self.calls.append(("step", board_id, item_id, column))
        if self.step_fail:
            raise RuntimeError("column not found")

    def post_update(self, item_id, text):
        self.calls.append(("update", item_id, text))


def item(name, id_="1", task_item="900", done=False, board="5031413876"):
    return {"id": id_, "name": name, "done": done, "task_id": "W11-0041", "task_item_id": task_item,
            "task_board_id": board}


class Rig:
    def __init__(self, tmp_path, events, monday_items=None, has_list=True):
        self.feed_text = ics(events)
        self.feed_fail = False
        self.dav_store = FakeCalDav(has_list=has_list)
        self.dav = rs.Dav("https://siuds.synology.me:38443/caldav/", "calendar-monday", "pw", transport=self.dav_store)
        self.monday = FakeMonday(monday_items if monday_items is not None else [item("W11-0041 · call Ben")])
        self.telegrams: list[str] = []
        self.cfg = {"REMINDERS_FEED_URL": "http://feed", "CALDAV_TASK_LIST": LIST, "TELEGRAM_BOT_TOKEN": "t",
                    "TELEGRAM_CHAT_ID": "c"}
        self.state = rs.new_state()
        self.logs: list[str] = []

        def fetch(url):
            if self.feed_fail:
                raise OSError("feed down")
            return self.feed_text

        def tg(token, chat, text):
            self.telegrams.append(text)
            return True

        self.cl = rs.Clients(self.dav, self.monday, fetch, tg)

    def run(self, now=NOW, dry=False):
        return rs.run(self.cfg, self.state, self.cl, now, self.logs.append, dry)


T1 = "W11-0041 · call Ben (after 09:30 New York)"
DUE = NOW + timedelta(hours=1)


# ----------------------------------------------------------------------------------------------- ICS
def test_feed_titles_lose_monday_decoration_and_unusable_events_are_skipped():
    text = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:a\r\nSUMMARY:Reminders: W15-0001 · do\\, then this (Remind at)\r\n"
            "DTSTART:20261105T013000Z\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:b\r\nSUMMARY:cancelled\r\nSTATUS:CANCELLED\r\n"
            "DTSTART:20261105T013000Z\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:c\r\nSUMMARY:all day\r\nDTSTART;VALUE=DATE:20261105\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n")
    ev = rs.parse_feed(text)
    assert [(e["uid"], e["title"]) for e in ev] == [("a", "W15-0001 · do, then this")]
    assert ev[0]["due"] == datetime(2026, 11, 5, 1, 30, tzinfo=timezone.utc)


def test_folded_summary_lines_are_joined():
    text = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:a\r\nSUMMARY:Reminders: one\r\n  two (Remind at)\r\nDTSTART:20261105T013000Z\r\nEND:VEVENT\r\nEND:VCALENDAR"
    assert rs.parse_feed(text)[0]["title"] == "one two"


def test_a_page_that_is_not_a_calendar_raises_rather_than_looking_empty():
    with pytest.raises(ValueError):
        rs.parse_feed("<html>502 Bad Gateway</html>")


def test_vtodo_has_due_and_one_absolute_alert_at_due_and_lines_fold_at_75_octets():
    title = "W11-0041 · " + "é" * 90
    v = rs.build_vtodo("mrem-x", title, DUE, NOW)
    assert f"DUE:{rs.fmt_utc(DUE)}" in v and f"TRIGGER;VALUE=DATE-TIME:{rs.fmt_utc(DUE)}" in v
    assert v.count("BEGIN:VALARM") == 1 and "STATUS:NEEDS-ACTION" in v
    assert all(len(line.encode()) <= 75 for line in v.split("\r\n"))
    assert rs.parse_vtodos(v.replace("\r\n ", "\r\n "))[0]["summary"] == title      # round-trips through fold/unfold


def test_completed_vtodo_is_read_as_completed_by_status_or_by_completed_stamp():
    base = "BEGIN:VCALENDAR\r\nBEGIN:VTODO\r\nUID:u\r\nSUMMARY:s\r\n{}END:VTODO\r\nEND:VCALENDAR"
    assert rs.parse_vtodos(base.format("STATUS:COMPLETED\r\n"))[0]["completed"]
    assert rs.parse_vtodos(base.format("COMPLETED:20261105T020000Z\r\n"))[0]["completed"]
    assert not rs.parse_vtodos(base.format("STATUS:NEEDS-ACTION\r\n"))[0]["completed"]


def test_sydney_rule_matches_the_two_offsets_either_side_of_the_october_change():
    assert rs.sydney_offset(datetime(2026, 9, 30, 12, tzinfo=timezone.utc)) == timedelta(hours=10)
    assert rs.sydney_offset(datetime(2026, 10, 10, 12, tzinfo=timezone.utc)) == timedelta(hours=11)
    assert rs.sydney_offset(datetime(2027, 5, 1, 12, tzinfo=timezone.utc)) == timedelta(hours=10)


# ----------------------------------------------------------------------------------------------- sync
def test_first_run_creates_one_task_and_a_second_run_changes_nothing(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    assert r.run() == 0
    assert len(r.dav_store.puts()) == 1
    ical = next(iter(r.dav_store.tasks.values()))
    assert "SUMMARY:W11-0041 · call Ben (after 09:30 New York)" in ical
    before = list(r.dav_store.calls)
    assert r.run(NOW + timedelta(minutes=5)) == 0
    assert [c for c in r.dav_store.calls[len(before):] if c[0] in ("PUT", "DELETE")] == []


def test_a_changed_time_replaces_the_task_and_a_removed_reminder_deletes_it(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run()
    r.feed_text = ics([("u1", T1, DUE + timedelta(hours=2))])
    r.run(NOW + timedelta(minutes=5))
    assert len(r.dav_store.puts()) == 2 and len(r.dav_store.tasks) == 1
    assert rs.fmt_utc(DUE + timedelta(hours=2)) in next(iter(r.dav_store.tasks.values()))
    r.feed_text = ics([])
    r.run(NOW + timedelta(minutes=10))
    assert r.dav_store.tasks == {}


def test_an_old_reminder_already_in_the_feed_is_not_turned_into_a_task(tmp_path):
    r = Rig(tmp_path, [("old", "W11-0041 · TEST", NOW - timedelta(days=1))])
    r.run()
    assert r.dav_store.puts() == [] and r.telegrams == []


def test_a_failed_feed_never_deletes_anything(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run()
    r.feed_fail = True
    assert r.run(NOW + timedelta(minutes=5)) == 1
    assert len(r.dav_store.tasks) == 1 and not any(c[0] == "DELETE" for c in r.dav_store.calls)


def test_a_failed_task_listing_does_not_tick_or_dismiss_or_recreate(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run()
    r.dav_store.fail = True
    assert r.run(NOW + timedelta(minutes=5)) == 1
    assert r.monday.calls == [("read",)] or r.monday.calls == []       # only the hourly read at most
    assert not any(e.get("dismissed") for e in r.state["entries"].values())


def test_missing_task_list_stops_with_a_setup_error_that_names_the_fix(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], has_list=False)
    with pytest.raises(rs.SetupError, match="--create-list"):
        r.run()


def test_task_deleted_on_the_phone_is_not_recreated(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run()
    r.dav_store.tasks.clear()
    r.run(NOW + timedelta(minutes=5))
    r.run(NOW + timedelta(minutes=10))
    assert len(r.dav_store.puts()) == 1


def test_dry_run_prints_changes_but_makes_none(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run(dry=True)
    assert r.dav_store.puts() == [] and any("CREATE" in line for line in r.logs)


# ----------------------------------------------------------------------------------------------- ticks
def test_tick_sets_done_and_posts_one_update_with_sydney_time_then_stays_quiet(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="777")])
    r.run()
    r.dav_store.tick(T1, datetime(2026, 11, 6, 6, 30, tzinfo=timezone.utc))      # 17:30 Sydney
    r.run(NOW + timedelta(minutes=30))
    assert ("done", "55") in r.monday.calls
    ups = [c for c in r.monday.calls if c[0] == "update"]
    assert ups == [("update", "777", f"Ben ticked reminder '{T1}' at 17:30 Sydney")]
    n = len(r.monday.calls)
    r.run(NOW + timedelta(minutes=35))
    assert len(r.monday.calls) == n                                   # nothing more: no repeat Update, no extra reads


def test_tick_with_no_matching_item_is_retried_not_lost(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [])
    r.run()
    r.dav_store.tick(T1, NOW)
    r.run(NOW + timedelta(minutes=5))
    assert not next(iter(r.state["entries"].values())).get("ticked")
    r.monday.items = [item(T1, id_="9")]
    r.run(NOW + timedelta(minutes=10))
    assert ("done", "9") in r.monday.calls


def test_a_failing_monday_does_not_lose_the_tick(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="9")])
    r.run()
    r.dav_store.tick(T1, NOW)
    r.monday.fail = True
    r.run(NOW + timedelta(minutes=5))
    r.monday.fail = False
    r.run(NOW + timedelta(minutes=10))
    assert ("done", "9") in r.monday.calls


def test_the_wxx_task_status_is_never_touched(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="777")])
    r.run()
    r.dav_store.tick(T1, NOW)
    r.run(NOW + timedelta(minutes=5))
    assert all(c[1] != "777" or c[0] == "update" for c in r.monday.calls if len(c) > 1)


def test_a_reminder_set_done_in_monday_completes_its_phone_task_after_the_hourly_read(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55")])
    r.run()
    r.monday.items[0]["done"] = True
    r.run(NOW + timedelta(hours=1, minutes=1))
    assert "STATUS:COMPLETED" in next(iter(r.dav_store.tasks.values()))
    assert r.telegrams == []


def test_board_api_is_read_about_once_an_hour_not_every_run(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    for i in range(12):                                               # one hour of 5-minute runs
        r.run(NOW + timedelta(minutes=5 * i))
    assert len([c for c in r.monday.calls if c == ("read",)]) <= 2


# ----------------------------------------------------------------------------------------------- telegram
def test_telegram_goes_once_when_due_and_not_before(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run()
    r.run(DUE - timedelta(minutes=1))
    assert r.telegrams == []
    r.run(DUE + timedelta(minutes=1))
    r.run(DUE + timedelta(minutes=6))
    assert len(r.telegrams) == 1 and T1 in r.telegrams[0]


def test_no_telegram_for_a_reminder_already_ticked(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1)])
    r.run()
    r.dav_store.tick(T1, DUE - timedelta(minutes=3))
    r.run(DUE - timedelta(minutes=2))
    r.run(DUE + timedelta(minutes=1))
    assert r.telegrams == []


def test_an_old_reminder_seen_for_the_first_time_sends_no_telegram(tmp_path):
    r = Rig(tmp_path, [("u1", T1, NOW - timedelta(hours=3))])
    r.run()
    assert r.telegrams == []


def test_telegram_still_goes_when_the_calendar_is_down(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run()
    r.dav_store.fail = True
    r.run(DUE + timedelta(minutes=1))
    assert len(r.telegrams) == 1


# ----------------------------------------------------------------------------------------------- health
def test_six_failing_runs_alarm_once_and_recovery_says_so(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.feed_fail = True
    for i in range(8):
        r.run(NOW + timedelta(minutes=5 * i))
    assert len([t for t in r.telegrams if "failed" in t]) == 1
    r.feed_fail = False
    r.run(NOW + timedelta(minutes=60))
    assert any("working again" in t for t in r.telegrams)


# ----------------------------------------------------------------------------------------------- CalDAV discovery
def test_task_list_is_found_by_name_and_my_task_is_left_alone(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run()
    assert r.state["task_list_url"].endswith("/monday-reminders/")
    assert all("/my-task/" not in c[1] for c in r.dav_store.calls if c[0] in ("PUT", "DELETE"))


def test_create_list_makes_it_or_tells_ben_the_manual_step():
    d = FakeCalDav(has_list=False)
    dav = rs.Dav("https://x/caldav/", "u", "p", transport=d)
    assert rs.create_task_list(dav, LIST).endswith("/monday-reminders/")
    d2 = FakeCalDav(has_list=False, allow_mkcalendar=False)
    with pytest.raises(rs.SetupError, match="Create it by hand"):
        rs.create_task_list(rs.Dav("https://x/caldav/", "u", "p", transport=d2), LIST)


# ----------------------------------------------------------------------------------------------- real HTTP layer
def test_dav_sends_basic_auth_and_a_body_over_a_real_socket():
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_PUT(self):                                              # noqa: N802
            seen["auth"] = self.headers.get("Authorization")
            seen["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(201)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        dav = rs.Dav(f"http://127.0.0.1:{srv.server_port}/caldav/", "calendar-monday", "pw")
        status, _, _ = dav.request("PUT", "/caldav/x.ics", b"hello")
    finally:
        srv.shutdown()
    assert status == 201 and seen["body"] == b"hello"
    assert seen["auth"] == "Basic Y2FsZW5kYXItbW9uZGF5OnB3"


# ----------------------------------------------------------------------------------------------- config and main
def test_env_file_parsing_and_defaults(tmp_path):
    f = tmp_path / "r.env"
    f.write_text("# c\nREMINDERS_FEED_URL='https://x/y.ics'\nMONDAY_API_TOKEN=tok\nCALDAV_PASSWORD=\"p w\"\n", encoding="utf-8")
    cfg = rs.load_env(str(f), environ={})
    assert cfg["REMINDERS_FEED_URL"] == "https://x/y.ics" and cfg["CALDAV_PASSWORD"] == "p w"
    assert cfg["CALDAV_USER"] == "calendar-monday" and cfg["CALDAV_TASK_LIST"] == LIST
    assert cfg["CALDAV_URL"].endswith(":38443/caldav/") and cfg["REMINDERS_BOARD_ID"] == "5032297480"


def test_main_missing_secrets_exit_2_and_names_them(tmp_path):
    out: list[str] = []
    rc = rs.main(["--env", str(tmp_path / "none.env"), "--state", str(tmp_path / "s.json"), "--log", ""], environ={}, out=out.append)
    assert rc == 2 and "MONDAY_API_TOKEN" in " ".join(out)


def test_main_runs_end_to_end_and_saves_state_without_secrets(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    env = tmp_path / "r.env"
    env.write_text("REMINDERS_FEED_URL=http://feed\nMONDAY_API_TOKEN=SECRET-TOKEN\nCALDAV_PASSWORD=SECRET-PW\n", encoding="utf-8")
    st = tmp_path / "s.json"
    rc = rs.main(["--env", str(env), "--state", str(st), "--log", str(tmp_path / "l.log")], clients=r.cl, now=NOW,
                 environ={}, out=lambda *_: None)
    assert rc == 0 and len(r.dav_store.tasks) == 1
    saved = st.read_text(encoding="utf-8")
    assert "SECRET" not in saved and json.loads(saved)["entries"]
    assert "SECRET" not in (tmp_path / "l.log").read_text(encoding="utf-8")


def test_check_mode_changes_nothing(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    out: list[str] = []
    assert rs.do_check({**r.cfg, "CALDAV_TASK_LIST": LIST}, r.cl, out.append) == 0
    assert r.dav_store.puts() == [] and any("PASS task list" in line for line in out)


# ----------------------------------------------------------------------------------------------- the install files
FILES = SCRIPT.parent


def test_the_env_example_holds_no_real_secrets_and_the_helper_sets_mode_600():
    ex = (FILES / "reminders.env.example").read_text(encoding="utf-8")
    assert "<monday personal API token>" in ex and "38443" in ex and "CALDAV_CONNECT_HOST" in ex
    helper = (FILES / "make_reminders_env.sh").read_text(encoding="utf-8")
    assert "chmod 600" in helper and "read -r -s" in helper


def test_setup_guide_states_the_limits_the_mode_600_and_the_never_touch_rules():
    g = (FILES / "REMINDERS-SETUP.md").read_text(encoding="utf-8")
    for must in ("never talked to", "mode 600", "38443", "Inbox", "--check", "--create-list", "Task Scheduler"):
        assert must.lower() in g.lower(), must
    assert "nas_trader" not in (FILES / "run_reminders.sh").read_text(encoding="utf-8")


def test_script_is_python38_safe_no_match_statement_or_union_types_evaluated_at_runtime():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "from __future__ import annotations" in src
    assert "\nmatch " not in src and " removeprefix(" not in src and " removesuffix(" not in src


def test_webcal_feed_links_are_fetched_over_https():
    assert rs.normalize_feed_url("webcal://ben.monday.com/x.ics?a=1") == "https://ben.monday.com/x.ics?a=1"
    assert rs.normalize_feed_url("https://a/b.ics") == "https://a/b.ics"
    seen = []

    class R:
        def read(self):
            return b"BEGIN:VCALENDAR"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    rs.fetch_feed("webcal://h/x.ics", urlopen=lambda req, timeout: (seen.append(req.full_url), R())[1])
    assert seen == ["https://h/x.ics"]


def test_env_helper_accepts_webcal_and_converts_it():
    helper = (FILES / "make_reminders_env.sh").read_text(encoding="utf-8")
    assert "webcal://*)" in helper and 'F="https://${F#webcal://}"' in helper


def test_env_helper_writes_through_sudo_and_never_claims_success_after_a_failed_write():
    h = (FILES / "make_reminders_env.sh").read_text(encoding="utf-8")
    assert 'sudo mv "$TMP" "$OUT"' in h and "chown root:root" in h and "Nothing written" in h
    assert h.index("Could not write") < h.index("Written $OUT")
    assert "$OUT.new" not in h


# ----------------------------------------------------------------------------------------------- monday's floating times
def feed_with(dtstart_line: str, header: str = "") -> str:
    return (f"BEGIN:VCALENDAR\r\n{header}BEGIN:VEVENT\r\nUID:a\r\nSUMMARY:Reminders: x (Remind at)\r\n{dtstart_line}\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n")


def test_floating_feed_times_are_sydney_wall_clock_not_utc():
    """Measured 2026-11-06: the TEST item (12:30 Sydney) and W17-0046 (Sat 09:15 Sydney) both came out 11 h late as UTC."""
    ev = rs.parse_feed(feed_with("DTSTART:20261105T123000"))[0]
    assert ev["due"] == datetime(2026, 11, 5, 1, 30, tzinfo=timezone.utc) and rs.sydney_hhmm(ev["due"]) == "12:30"
    ev = rs.parse_feed(feed_with("DTSTART:20261107T091500"))[0]
    assert ev["due"] == datetime(2026, 11, 6, 22, 15, tzinfo=timezone.utc) and rs.sydney_stamp(ev["due"]) == "Sat 07 Nov 09:15"
    assert ev["raw"] == "DTSTART:20261107T091500"


def test_z_and_tzid_times_are_unchanged_and_feed_timezone_overrides_the_default():
    assert rs.parse_feed(feed_with("DTSTART:20261105T013000Z"))[0]["due"] == datetime(2026, 11, 5, 1, 30, tzinfo=timezone.utc)
    assert rs.parse_feed(feed_with("DTSTART:20261105T123000"), "UTC")[0]["due"] == datetime(2026, 11, 5, 12, 30, tzinfo=timezone.utc)
    ev = rs.parse_feed(feed_with("DTSTART:20261105T123000", "X-WR-TIMEZONE:UTC\r\n"))[0]
    assert ev["due"] == datetime(2026, 11, 5, 12, 30, tzinfo=timezone.utc)


def test_sydney_wall_clock_conversion_works_without_tz_data_either_side_of_the_change(monkeypatch):
    monkeypatch.setattr(rs, "ZoneInfo", None)                           # a NAS Python with no zoneinfo
    assert rs.local_to_utc(datetime(2026, 11, 5, 12, 30), "Australia/Sydney") == datetime(2026, 11, 5, 1, 30, tzinfo=timezone.utc)
    assert rs.local_to_utc(datetime(2026, 7, 1, 12, 0), "Australia/Sydney") == datetime(2026, 7, 1, 2, 0, tzinfo=timezone.utc)
    assert rs.local_to_utc(datetime(2026, 11, 5, 12, 30), "Nowhere/Land") is None


# ----------------------------------------------------------------------------------------------- reminder linked to a STEP
def test_ticking_a_reminder_linked_to_a_subitem_marks_that_step_done_after_the_update(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="888", board="5031415830")])
    r.run()
    r.dav_store.tick(T1, datetime(2026, 11, 6, 6, 30, tzinfo=timezone.utc))
    r.run(NOW + timedelta(minutes=30))
    kinds = [c[0] for c in r.monday.calls if c[0] in ("update", "step", "done")]
    assert kinds == ["update", "step", "done"]                        # note first, then the step, then the reminder
    assert ("step", "5031415830", "888", "status") in r.monday.calls
    assert "this step is marked Done" in [c for c in r.monday.calls if c[0] == "update"][0][2]
    n = len(r.monday.calls)
    r.run(NOW + timedelta(minutes=35))
    assert len(r.monday.calls) == n


def test_a_link_to_a_normal_task_never_changes_that_tasks_status(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="777", board="5031413876")])
    r.run()
    r.dav_store.tick(T1, NOW)
    r.run(NOW + timedelta(minutes=5))
    assert not any(c[0] == "step" for c in r.monday.calls) and ("done", "55") in r.monday.calls


def test_a_step_that_cannot_be_marked_done_is_reported_once_and_not_retried(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="888", board="5031415830")])
    r.run()
    r.monday.step_fail = True
    r.dav_store.tick(T1, NOW)
    r.run(NOW + timedelta(minutes=5))
    r.run(NOW + timedelta(minutes=10))
    assert len([c for c in r.monday.calls if c[0] == "step"]) == 1
    assert len([t for t in r.telegrams if "could not mark" in t]) == 1
    assert ("done", "55") in r.monday.calls                            # the reminder itself is still closed


def test_read_board_extracts_board_and_item_id_from_the_task_link():
    items = {"boards": [{"items_page": {"items": [{"id": "1", "name": "n", "column_values": [
        {"id": rs.COL_TASK_LINK, "text": "x", "value": json.dumps({"url": "https://ben-siu.monday.com/boards/5031415830/pulses/2899930378", "text": "s"})},
        {"id": rs.COL_STATUS, "text": "", "value": None}, {"id": rs.COL_TASK_ID, "text": "W11-0041", "value": None}]}]}}]}
    m = rs.Monday("tok", 5032297480)
    m.gql = lambda q, v=None: items
    got = m.read_board()[0]
    assert (got["task_board_id"], got["task_item_id"], got["done"]) == ("5031415830", "2899930378", False)


def test_dump_raw_prints_every_resource_and_what_report_returns_and_changes_nothing(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run()
    base = r.dav_store.__call__
    store = r.dav_store

    def with_propfind_list(method, url, headers, body):
        if method == "PROPFIND" and headers.get("Depth") == "1" and url.endswith("/monday-reminders/"):
            rows = "".join(f"<d:response><d:href>{h}</d:href></d:response>" for h in store.tasks)
            return 207, {}, ('<d:multistatus xmlns:d="DAV:">' + rows + "</d:multistatus>").encode()
        if method == "GET":
            return 200, {}, store.tasks[url.split("//", 1)[1].split("/", 1)[1].join(["/", ""])].encode()
        return base(method, url, headers, body)

    cl = rs.Clients(rs.Dav("https://x/caldav/", "u", "p", transport=with_propfind_list), r.monday, r.cl.fetch, r.cl.telegram)
    out: list[str] = []
    before = dict(store.tasks)
    assert rs.do_dump_raw(r.cfg, cl, LIST, out.append) == 0
    text = "\n".join(out)
    assert "BEGIN:VTODO" in text and "REPORT returns 1 task" in text and store.tasks == before


def test_a_ticked_task_that_the_list_hides_is_still_seen_as_ticked(tmp_path):
    """2026-11-06 18:35: after the tick the task was no longer in the list and the first version called that 'dismissed'."""
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="777")])
    r.run()
    r.dav_store.hide_completed = True
    r.dav_store.tick(T1, NOW)
    r.run(NOW + timedelta(minutes=5))
    e = next(iter(r.state["entries"].values()))
    assert e.get("ticked") and not e.get("dismissed") and ("done", "55") in r.monday.calls


def test_a_task_really_gone_from_the_server_is_dismissed_and_a_server_error_is_not(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)])
    r.run()
    r.dav_store.tasks.clear()
    r.run(NOW + timedelta(minutes=5))
    r.run(NOW + timedelta(minutes=10))
    assert next(iter(r.state["entries"].values())).get("dismissed")
    r2 = Rig(tmp_path, [("u1", T1, DUE)])
    r2.run()
    href = next(iter(r2.dav_store.tasks))
    orig = r2.dav_store.__call__
    r2.dav.transport = lambda m, u, h, b: (503, {}, b"") if m == "GET" else orig(m, u, h, b)
    r2.dav_store.tasks.pop(href)                                   # missing from the list AND the GET errors
    r2.run(NOW + timedelta(minutes=5))
    r2.run(NOW + timedelta(minutes=10))
    assert not next(iter(r2.state["entries"].values())).get("dismissed")


def test_one_missed_look_is_not_a_dismissal_and_a_task_that_comes_back_ticked_still_ticks(tmp_path):
    """2026-11-06 18:35: the ticked test task was missing for one run, was called dismissed, and the tick was lost."""
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="777")])
    r.run()
    saved = dict(r.dav_store.tasks)
    r.dav_store.tasks.clear()                                         # one run where the list does not show it
    r.run(NOW + timedelta(minutes=5))
    e = next(iter(r.state["entries"].values()))
    assert not e.get("dismissed") and e.get("missing") == 1
    r.dav_store.tasks.update(saved)
    r.dav_store.tick(T1, NOW + timedelta(minutes=6))
    r.run(NOW + timedelta(minutes=10))
    assert e.get("ticked") and ("done", "55") in r.monday.calls


def test_a_wrongly_dismissed_task_that_is_in_the_list_completed_is_ticked(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="777")])
    r.run()
    next(iter(r.state["entries"].values()))["dismissed"] = True      # the state the NAS is in right now
    r.dav_store.tick(T1, NOW)
    r.run(NOW + timedelta(minutes=5))
    assert next(iter(r.state["entries"].values())).get("ticked") and ("done", "55") in r.monday.calls


def test_an_entry_flagged_dismissed_and_deleted_whose_task_is_completed_on_the_server_still_ticks(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="777")])
    r.run()
    e = next(iter(r.state["entries"].values()))
    e["dismissed"] = e["deleted"] = True                              # a reminder that left the feed after the wrong dismissal
    r.dav_store.tick(T1, NOW)
    r.run(NOW + timedelta(minutes=5))
    assert e.get("ticked") and ("done", "55") in r.monday.calls
    assert not any(c[0] == "DELETE" for c in r.dav_store.calls)       # and the task was not deleted before the tick was read


# What the iPhone really wrote back after Ben ticked the LIVE TEST task (from --dump-raw on the NAS, 2026-11-06 19:08).
IPHONE_TICKED = (
    "BEGIN:VCALENDAR\r\nCALSCALE:GREGORIAN\r\nPRODID:-//Apple Inc.//iOS 27.2//EN\r\nVERSION:2.0\r\nBEGIN:VTODO\r\n"
    "COMPLETED:20261106T073028Z\r\nCREATED:20261106T070139Z\r\nDTSTAMP:20261106T073029Z\r\nDTSTART:20261106T073000Z\r\n"
    "DUE:20261106T073000Z\r\nLAST-MODIFIED:20261106T073028Z\r\nPERCENT-COMPLETE:100\r\nSTATUS:COMPLETED\r\n"
    "SUMMARY:W11-0041 · LIVE TEST: tick me when the alert shows (18:30 Sydney\r\n )\r\n"
    "UID:mrem-c3f1cb60c92a1b9a4f4b8fdf\r\nX-APPLE-SORT-ORDER:815641299\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\n"
    "DESCRIPTION:Reminder\r\nTRIGGER;VALUE=DATE-TIME:20261106T073000Z\r\nUID:50662E46-472E-4779-B28F-6C3CE2263563\r\n"
    "X-WR-ALARMUID:50662E46-472E-4779-B28F-6C3CE2263563\r\nEND:VALARM\r\nEND:VTODO\r\nEND:VCALENDAR\r\n")


def test_the_real_iphone_rewrite_keeps_the_tasks_uid_not_the_alarms():
    t = rs.parse_vtodos(IPHONE_TICKED)[0]
    assert t["uid"] == "mrem-c3f1cb60c92a1b9a4f4b8fdf" and t["completed"]
    assert t["completed_at"] == datetime(2026, 11, 6, 7, 30, 28, tzinfo=timezone.utc)
    assert t["summary"].endswith("Sydney)")


def test_an_alarm_inside_a_feed_event_does_not_replace_the_events_uid_or_title():
    text = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:real\r\nSUMMARY:Reminders: x (Remind at)\r\nDTSTART:20261105T123000\r\n"
            "BEGIN:VALARM\r\nUID:alarm\r\nDESCRIPTION:other\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR")
    ev = rs.parse_feed(text)
    assert [(e["uid"], e["title"]) for e in ev] == [("real", "x")]


def test_a_task_rewritten_the_way_the_iphone_does_it_is_ticked_end_to_end(tmp_path):
    r = Rig(tmp_path, [("u1", T1, DUE)], [item(T1, id_="55", task_item="888", board="5031415830")])
    r.run()
    href = next(iter(r.dav_store.tasks))
    uid = next(iter(r.state["entries"].values()))["task_uid"]
    r.dav_store.tasks[href] = (IPHONE_TICKED.replace("mrem-c3f1cb60c92a1b9a4f4b8fdf", uid)
                               .replace("W11-0041 · LIVE TEST: tick me when the alert shows (18:30 Sydney\r\n )", T1))
    r.run(NOW + timedelta(minutes=5))
    e = next(iter(r.state["entries"].values()))
    assert e.get("ticked") and not e.get("dismissed")
    assert [c[0] for c in r.monday.calls if c[0] in ("update", "step", "done")] == ["update", "step", "done"]
    assert "at 18:30 Sydney" in [c for c in r.monday.calls if c[0] == "update"][0][2]
