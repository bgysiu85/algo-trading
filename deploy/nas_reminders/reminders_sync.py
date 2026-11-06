"""W11-0041 sub 9: monday Reminders board -> Synology Calendar tasks (iPhone Reminders), tick -> monday Done, Telegram backup.

Run every 5 minutes from a DSM Task Scheduler entry (see REMINDERS-SETUP.md). Python 3 standard library only.

One run does, in order:
  1. reads the monday Reminders calendar feed (an ICS URL; no monday API call);
  2. lists the tasks in the Synology task list 'monday reminders' (CalDAV REPORT);
  3. TICKS: a task Ben completed on his phone -> sets that item's Status = Done on the Reminders board and posts ONE
     Update on the item its Task link points at ("Ben ticked reminder '...' at HH:MM Sydney"). If that link is a STEP
     (a subitem), the step's Status is also set to Done. A link to a normal task never has its Status changed;
  4. SYNC: one VTODO per feed event (DUE = Remind at, one VALARM at DUE). New -> create, time/title changed -> replace,
     left the feed -> delete. A repeat run with nothing changed sends nothing;
  5. TELEGRAM: one message when a reminder falls due (never twice, not if already ticked);
  6. once an hour (and after a tick) reads the board through the monday API, to learn the item ids and to complete
     the task of a reminder someone set Done in monday. About 24 + a few API calls a day.

Safety rules the code keeps:
  * a failed feed fetch or a failed task listing NEVER deletes or ticks anything (an error is not an empty list);
  * it only ever touches the one task list it is configured for, never Ben's own tasks;
  * secrets come from the env file (mode 600), never from the repo or the command line;
  * it never touches the trader or Gateway containers or the trader .env;
  * if it keeps failing (6 runs in a row) it says so once on Telegram, and once more when it recovers.

Command line:
  reminders_sync.py                 normal run (what the DSM task does)
  reminders_sync.py --check         read-only: feed, CalDAV login, task lists, monday token; changes nothing
  reminders_sync.py --create-list   create the 'monday reminders' task list over CalDAV (once), then exit
  reminders_sync.py --dump "My Task"  print the raw VTODOs of one task list (to see what Synology writes)
  reminders_sync.py --dry-run       a normal run that only prints what it would change
Exit code 0 = fine, 1 = something failed this run, 2 = bad setup.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

try:                                    # the NAS's python may be 3.8 (no zoneinfo): a Sydney rule stands in
    from zoneinfo import ZoneInfo
except ImportError:                     # pragma: no cover - depends on the interpreter
    ZoneInfo = None                     # type: ignore[assignment]

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ENV = os.path.join(HERE, "reminders.env")
DEFAULT_STATE = os.path.join(HERE, "reminders_state.json")
DEFAULT_LOG = os.path.join(HERE, "reminders.log")

BOARD_ID_DEFAULT = 5032297480
COL_STATUS = "color_mm8t5gct"
COL_TASK_ID = "text_mm8t151n"
COL_TASK_LINK = "link_mm8tgpxg"
COL_REMIND_AT = "date_mm8thmd3"

# The four monday boards that hold subitems (steps). A reminder whose Task link points at one of their items is
# a reminder for that STEP: ticking it also sets the step's Status = Done (Ben, 2026-11-06). A link to a normal task
# item only gets the one Update; the task's own Status is never changed from here.
SUBITEM_BOARDS = {"5031415830", "5032254265", "5032254259", "5032254131"}
SUBITEM_STATUS_COL = "status"

LATE_GRACE = timedelta(minutes=15)       # a reminder this late is still created (and sent); older ones are skipped
TELEGRAM_STALE = timedelta(hours=6)      # never send a "due" message for something longer overdue than this
BOARD_REFRESH_S = 3600                   # API read of the board at most this often (apart from after a tick)
FAIL_ALERT_AFTER = 6                     # consecutive failing runs before one Telegram alarm (6 x 5 min = 30 min)
KEEP_TICKED = timedelta(days=7)          # a ticked task is removed from the list this long after it was due
SENT_KEEP = timedelta(days=30)           # state entries of vanished reminders are forgotten after this

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}


class SetupError(Exception):
    """Something Ben must fix by hand (missing env value, no task list). Exit code 2."""


# ======================================================================================= time helpers
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def local_to_utc(naive: datetime, tzname: str):
    """A wall-clock time in `tzname` -> aware UTC. Australia/Sydney also works with no tz data on the box."""
    if tzname.upper() in ("UTC", "Z", "GMT"):
        return naive.replace(tzinfo=timezone.utc)
    if ZoneInfo is not None:
        try:
            return naive.replace(tzinfo=ZoneInfo(tzname)).astimezone(timezone.utc)
        except Exception:                                             # noqa: BLE001 - unknown name or no tzdata
            pass
    if tzname == "Australia/Sydney":
        for hours in (11, 10):
            cand = (naive - timedelta(hours=hours)).replace(tzinfo=timezone.utc)
            if sydney_offset(cand) == timedelta(hours=hours):
                return cand
        return (naive - timedelta(hours=10)).replace(tzinfo=timezone.utc)
    return None


def parse_ics_dt(value: str, tzid: str | None = None, floating_tz: str = "Australia/Sydney"):
    """'20261105T013000Z' -> UTC; 'TZID=X:...' -> that zone; a floating time (no Z, no TZID) -> `floating_tz`.
    monday writes its Remind at times as floating Sydney wall-clock time (measured 2026-11-06: read as UTC they came out
    exactly 11 hours late). A date-only value returns None."""
    v = value.strip()
    if re.fullmatch(r"\d{8}", v):
        return None                                                   # all-day: has no time to alert at
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", v)
    if not m:
        return None
    naive = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    if m.group(3) == "Z":
        return naive.replace(tzinfo=timezone.utc)
    return local_to_utc(naive, tzid or floating_tz)


def _first_sunday(year: int, month: int) -> datetime:
    d = datetime(year, month, 1)
    return d + timedelta(days=(6 - d.weekday()) % 7)


def sydney_offset(utc_dt: datetime) -> timedelta:
    """Australia/Sydney offset without tz data: AEDT (+11) from first Sunday of October 02:00 standard time
    until first Sunday of April 03:00 daylight time, otherwise AEST (+10)."""
    u = utc_dt.astimezone(timezone.utc).replace(tzinfo=None)
    y = u.year
    dst_start = _first_sunday(y, 10) + timedelta(hours=2) - timedelta(hours=10)    # 02:00 AEST in UTC
    dst_end = _first_sunday(y, 4) + timedelta(hours=3) - timedelta(hours=11)       # 03:00 AEDT in UTC
    return timedelta(hours=11) if (u >= dst_start or u < dst_end) else timedelta(hours=10)


def to_sydney(dt: datetime) -> datetime:
    if ZoneInfo is not None:
        try:
            return dt.astimezone(ZoneInfo("Australia/Sydney"))
        except Exception:                                             # noqa: BLE001 - no tzdata on the box
            pass
    off = sydney_offset(dt)
    return dt.astimezone(timezone(off))


def sydney_hhmm(dt: datetime) -> str:
    return to_sydney(dt).strftime("%H:%M")


def sydney_stamp(dt: datetime) -> str:
    return to_sydney(dt).strftime("%a %d %b %H:%M")


# ======================================================================================= ICS
def unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def ics_unescape(s: str) -> str:
    return (s.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


def ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets, never splitting a UTF-8 character."""
    out: list[str] = []
    cur = b""
    first = True
    for ch in line:
        b = ch.encode("utf-8")
        limit = 75 if first else 74
        if len(cur) + len(b) > limit:
            out.append(cur.decode("utf-8"))
            cur, first = b, False
        else:
            cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def parse_prop(line: str):
    """'DTSTART;TZID=X:2026...' -> ('DTSTART', {'TZID': 'X'}, '2026...')"""
    if ":" not in line:
        return None
    head, value = line.split(":", 1)
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def clean_title(summary: str) -> str:
    """monday titles its calendar events 'Reminders: <item name> (Remind at)'; the phone reminder shows the item name."""
    s = summary.strip()
    s = re.sub(r"^\s*Reminders\s*:\s*", "", s)
    s = re.sub(r"\s*\(\s*Remind at\s*\)\s*$", "", s)
    return s.strip()


def parse_feed(text: str, floating_tz: str = "") -> list[dict]:
    """Feed events -> [{'uid','title','due'(UTC datetime)}]. Raises ValueError if it is not a calendar at all, so a
    server error page can never look like 'every reminder was deleted'. Cancelled and date-only events are skipped."""
    if "BEGIN:VCALENDAR" not in text:
        raise ValueError("the feed did not return a calendar (no BEGIN:VCALENDAR)")
    events, cur = [], None
    zone = floating_tz                                        # '' = use X-WR-TIMEZONE if the feed names one, else Sydney
    alarm = False
    for line in unfold(text):
        if cur is None and not floating_tz and line.upper().startswith("X-WR-TIMEZONE"):
            p = parse_prop(line)
            if p and p[2].strip():
                zone = p[2].strip()
        if line == "BEGIN:VALARM":
            alarm = True
            continue
        if line == "END:VALARM":
            alarm = False
            continue
        if alarm:
            continue                                      # an alarm has its own UID/TRIGGER/DESCRIPTION: not the event's
        if line == "BEGIN:VEVENT":
            cur = {"uid": None, "summary": "", "dtstart": None, "status": "", "raw": ""}
        elif line == "END:VEVENT" and cur is not None:
            if cur["uid"] and cur["dtstart"] and cur["status"].upper() != "CANCELLED":
                events.append({"uid": cur["uid"], "title": clean_title(cur["summary"]), "due": cur["dtstart"],
                               "raw": cur["raw"]})
            cur = None
        elif cur is not None:
            p = parse_prop(line)
            if not p:
                continue
            name, params, value = p
            if name == "UID":
                cur["uid"] = value.strip()
            elif name == "SUMMARY":
                cur["summary"] = ics_unescape(value)
            elif name == "STATUS":
                cur["status"] = value.strip()
            elif name == "DTSTART":
                cur["raw"] = line
                cur["dtstart"] = parse_ics_dt(value, params.get("TZID"), zone or "Australia/Sydney")
    return events


def task_uid(feed_uid: str) -> str:
    return "mrem-" + hashlib.sha1(feed_uid.encode("utf-8")).hexdigest()[:24]


def build_vtodo(uid: str, title: str, due: datetime, now: datetime, completed_at: datetime | None = None) -> str:
    """One task with DUE = Remind at and an absolute alert at DUE (what iPhone Reminders shows as 'alert at time')."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Ben//monday-reminders//EN", "BEGIN:VTODO",
             f"UID:{uid}", f"DTSTAMP:{fmt_utc(now)}", f"SUMMARY:{ics_escape(title)}", f"DUE:{fmt_utc(due)}"]
    if completed_at is not None:
        lines += ["STATUS:COMPLETED", f"COMPLETED:{fmt_utc(completed_at)}", "PERCENT-COMPLETE:100"]
    else:
        lines.append("STATUS:NEEDS-ACTION")
    lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Reminder", f"TRIGGER;VALUE=DATE-TIME:{fmt_utc(due)}",
              "END:VALARM", "END:VTODO", "END:VCALENDAR"]
    return "\r\n".join(fold(x) for x in lines) + "\r\n"


def parse_vtodos(ical: str) -> list[dict]:
    """VTODOs in one calendar-data blob -> [{'uid','summary','completed'(bool),'completed_at'(datetime|None),'due'}]"""
    out, cur = [], None
    alarm = False
    for line in unfold(ical):
        # The iPhone adds a VALARM to the task it rewrites, and that alarm has its OWN "UID:" line. Read as the task's
        # UID it made a ticked task look gone (2026-11-06 18:35). Lines inside a VALARM are never the task's.
        if line == "BEGIN:VALARM":
            alarm = True
            continue
        if line == "END:VALARM":
            alarm = False
            continue
        if alarm:
            continue
        if line == "BEGIN:VTODO":
            cur = {"uid": "", "summary": "", "status": "", "completed_at": None, "percent": None, "due": None}
        elif line == "END:VTODO" and cur is not None:
            done = cur["status"].upper() == "COMPLETED" or cur["completed_at"] is not None or cur["percent"] == 100
            out.append({"uid": cur["uid"], "summary": cur["summary"], "completed": done,
                        "completed_at": cur["completed_at"], "due": cur["due"]})
            cur = None
        elif cur is not None:
            p = parse_prop(line)
            if not p:
                continue
            name, params, value = p
            if name == "UID":
                cur["uid"] = value.strip()
            elif name == "SUMMARY":
                cur["summary"] = ics_unescape(value)
            elif name == "STATUS":
                cur["status"] = value.strip()
            elif name == "COMPLETED":
                cur["completed_at"] = parse_ics_dt(value, params.get("TZID"))
            elif name == "PERCENT-COMPLETE":
                try:
                    cur["percent"] = int(value.strip())
                except ValueError:
                    pass
            elif name == "DUE":
                cur["due"] = parse_ics_dt(value, params.get("TZID"))
    return out


# ======================================================================================= HTTP / CalDAV
class DavError(Exception):
    def __init__(self, status: int, what: str):
        super().__init__(f"{what}: HTTP {status}")
        self.status = status


class Dav:
    """Small CalDAV client over http.client. `connect_host` lets the NAS connect to 127.0.0.1 while the certificate is
    still checked against the public name (no dependence on the router looping traffic back)."""

    def __init__(self, base_url: str, user: str, password: str, connect_host: str = "", timeout: float = 20.0,
                 transport=None):
        self.base = base_url
        self.parsed = urllib.parse.urlsplit(base_url)
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        self.connect_host = connect_host
        self.timeout = timeout
        self.transport = transport            # tests replace the network with this

    def url(self, path_or_url: str) -> str:
        return urllib.parse.urljoin(self.base, path_or_url)

    def request(self, method: str, path_or_url: str, body: bytes | None = None, headers: dict | None = None):
        url = self.url(path_or_url)
        h = {"Authorization": self.auth, "User-Agent": "monday-reminders/1"}
        h.update(headers or {})
        if self.transport is not None:
            return self.transport(method, url, h, body)
        u = urllib.parse.urlsplit(url)
        host, port = u.hostname, u.port or (443 if u.scheme == "https" else 80)
        if u.scheme == "https":
            conn = _HTTPSConn(host, port, timeout=self.timeout, connect_host=self.connect_host or host,
                              context=ssl.create_default_context())
        else:
            conn = http.client.HTTPConnection(self.connect_host or host, port, timeout=self.timeout)
        try:
            conn.request(method, (u.path or "/") + (("?" + u.query) if u.query else ""), body=body, headers=h)
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()


class _HTTPSConn(http.client.HTTPSConnection):
    def __init__(self, host, port, connect_host, **kw):
        super().__init__(host, port, **kw)
        self._connect_host = connect_host

    def connect(self):                                                # connect to one address, verify another name
        sock = socket.create_connection((self._connect_host, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _xml(body: bytes):
    return ET.fromstring(body)


def _text(el, path):
    f = el.find(path, NS)
    return (f.text or "").strip() if f is not None else ""


PROPFIND_HOME = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
                 b'<d:current-user-principal/><c:calendar-home-set/></d:prop></d:propfind>')
PROPFIND_COLLECTIONS = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
                        b'<d:resourcetype/><d:displayname/><c:supported-calendar-component-set/></d:prop></d:propfind>')
REPORT_TODOS = (b'<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                b'<d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
                b'<c:comp-filter name="VTODO"/></c:comp-filter></c:filter></c:calendar-query>')


def discover_home(dav: Dav) -> str:
    """Base URL -> the user's calendar-home-set URL."""
    hdr = {"Depth": "0", "Content-Type": "application/xml; charset=utf-8"}
    status, _, body = dav.request("PROPFIND", dav.base, PROPFIND_HOME, hdr)
    if status == 401:
        raise SetupError("CalDAV login refused (401): check CALDAV_USER / CALDAV_PASSWORD in the env file")
    if status not in (200, 207):
        raise DavError(status, "PROPFIND on the CalDAV base URL")
    root = _xml(body)
    home = root.find(".//c:calendar-home-set/d:href", NS)
    if home is not None and (home.text or "").strip():
        return dav.url(home.text.strip())
    princ = root.find(".//d:current-user-principal/d:href", NS)
    if princ is not None and (princ.text or "").strip():
        status, _, body = dav.request("PROPFIND", princ.text.strip(), PROPFIND_HOME, hdr)
        if status in (200, 207):
            h2 = _xml(body).find(".//c:calendar-home-set/d:href", NS)
            if h2 is not None and (h2.text or "").strip():
                return dav.url(h2.text.strip())
    return dav.base                                           # some servers serve the collections at the base itself


def list_collections(dav: Dav, home: str) -> list[dict]:
    status, _, body = dav.request("PROPFIND", home, PROPFIND_COLLECTIONS,
                                  {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
    if status not in (200, 207):
        raise DavError(status, "PROPFIND on the calendar home")
    out = []
    for resp in _xml(body).findall("d:response", NS):
        href = _text(resp, "d:href")
        is_cal = resp.find(".//d:resourcetype/c:calendar", NS) is not None
        comps = [c.get("name", "").upper() for c in resp.findall(".//c:supported-calendar-component-set/c:comp", NS)]
        out.append({"href": dav.url(href), "name": _text(resp, ".//d:displayname"), "is_calendar": is_cal,
                    "components": comps})
    return [c for c in out if c["is_calendar"]]


def find_task_list(dav: Dav, list_name: str) -> str | None:
    home = discover_home(dav)
    for c in list_collections(dav, home):
        if c["name"] == list_name and (not c["components"] or "VTODO" in c["components"]):
            return c["href"]
    return None


def create_task_list(dav: Dav, list_name: str) -> str:
    home = discover_home(dav)
    slug = re.sub(r"[^a-z0-9]+", "-", list_name.lower()).strip("-") or "tasks"
    url = home.rstrip("/") + "/" + slug + "/"
    body = ('<?xml version="1.0" encoding="utf-8"?><c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            f'<d:set><d:prop><d:displayname>{list_name}</d:displayname>'
            '<c:supported-calendar-component-set><c:comp name="VTODO"/></c:supported-calendar-component-set>'
            '</d:prop></d:set></c:mkcalendar>').encode("utf-8")
    status, _, _ = dav.request("MKCALENDAR", url, body, {"Content-Type": "application/xml; charset=utf-8"})
    if status not in (200, 201):
        raise SetupError(f"The server would not create the task list over CalDAV (HTTP {status}). Create it by hand: "
                         f"Synology Calendar, signed in as the calendar-monday user, Tasks, new task list named exactly "
                         f"'{list_name}'.")
    return url


def report_tasks(dav: Dav, list_url: str) -> list[dict]:
    """Every VTODO in the list: [{'href','etag','uid','summary','completed','completed_at','due'}]. Raises on failure."""
    status, _, body = dav.request("REPORT", list_url, REPORT_TODOS,
                                  {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
    if status not in (200, 207):
        raise DavError(status, "REPORT (list tasks)")
    out = []
    for resp in _xml(body).findall("d:response", NS):
        data = _text(resp, ".//c:calendar-data")
        for t in parse_vtodos(data):
            t["href"] = dav.url(_text(resp, "d:href"))
            out.append(t)
    return out


def put_task(dav: Dav, list_url: str, uid: str, ical: str) -> str:
    href = list_url.rstrip("/") + "/" + uid + ".ics"
    status, _, _ = dav.request("PUT", href, ical.encode("utf-8"), {"Content-Type": "text/calendar; charset=utf-8"})
    if status not in (200, 201, 204):
        raise DavError(status, f"PUT task {uid}")
    return href


def delete_task(dav: Dav, href: str) -> None:
    status, _, _ = dav.request("DELETE", href)
    if status not in (200, 202, 204, 404):                    # 404 = already gone, which is what we wanted
        raise DavError(status, "DELETE task")


# ======================================================================================= monday, Telegram, feed
def normalize_feed_url(url: str) -> str:
    """monday hands out 'webcal://...' links (an iPhone shortcut for https). The same address over https is what we fetch."""
    u = url.strip()
    return "https://" + u[len("webcal://"):] if u.lower().startswith("webcal://") else u


def fetch_feed(url: str, urlopen=urllib.request.urlopen) -> str:
    req = urllib.request.Request(normalize_feed_url(url), headers={"User-Agent": "monday-reminders/1"})
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


class Monday:
    def __init__(self, token: str, board_id: int, urlopen=urllib.request.urlopen):
        self.token, self.board_id, self.urlopen = token, board_id, urlopen
        self.calls = 0

    def gql(self, query: str, variables: dict | None = None) -> dict:
        self.calls += 1
        req = urllib.request.Request(
            "https://api.monday.com/v2", data=json.dumps({"query": query, "variables": variables or {}}).encode(),
            headers={"Authorization": self.token, "Content-Type": "application/json", "API-Version": "2024-10"})
        with self.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("errors"):
            raise RuntimeError("monday API: " + json.dumps(data["errors"])[:300])
        return data["data"]

    def read_board(self) -> list[dict]:
        """All reminder items: [{'id','name','done'(bool),'task_id','task_item_id'}]"""
        q = ("query($b:[ID!]){boards(ids:$b){items_page(limit:500){items{id name column_values(ids:[\""
             + COL_STATUS + "\",\"" + COL_TASK_ID + "\",\"" + COL_TASK_LINK + "\"]){id text value}}}}}")
        data = self.gql(q, {"b": [str(self.board_id)]})
        items = []
        for it in data["boards"][0]["items_page"]["items"]:
            cols = {c["id"]: c for c in it["column_values"]}
            link = cols.get(COL_TASK_LINK, {})
            url = ""
            try:
                url = json.loads(link.get("value") or "{}").get("url", "")
            except ValueError:
                pass
            m = re.search(r"/boards/(\d+)/pulses/(\d+)", url or link.get("text", "") or "")
            items.append({"id": it["id"], "name": it["name"].strip(),
                          "done": (cols.get(COL_STATUS, {}).get("text") or "").strip().lower() == "done",
                          "task_id": (cols.get(COL_TASK_ID, {}).get("text") or "").strip(),
                          "task_board_id": m.group(1) if m else "",
                          "task_item_id": m.group(2) if m else ""})
        return items

    def set_status_done(self, board_id: str, item_id: str, column: str) -> None:
        self.gql("mutation($b:ID!,$i:ID!,$v:JSON!){change_multiple_column_values(board_id:$b,item_id:$i,column_values:$v){id}}",
                 {"b": str(board_id), "i": str(item_id), "v": json.dumps({column: {"label": "Done"}})})

    def set_done(self, item_id: str) -> None:
        """The reminder item itself."""
        self.set_status_done(self.board_id, item_id, COL_STATUS)

    def post_update(self, item_id: str, text: str) -> None:
        self.gql("mutation($i:ID!,$t:String!){create_update(item_id:$i,body:$t){id}}",
                 {"i": str(item_id), "t": text})


def send_telegram(token: str, chat: str, text: str, urlopen=urllib.request.urlopen) -> bool:
    """Best effort (same shape as api_precheck.py). A failure to message never changes what the sync does."""
    if not token or not chat:
        return False
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=10) as r:
            return 200 <= getattr(r, "status", 200) < 300
    except Exception:                                             # noqa: BLE001
        return False


# ======================================================================================= config, state, log
def load_env(path: str, environ=os.environ) -> dict:
    cfg: dict = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                cfg[k.strip()] = v
    for k in ("REMINDERS_FEED_URL", "MONDAY_API_TOKEN", "CALDAV_URL", "CALDAV_USER", "CALDAV_PASSWORD",
              "CALDAV_CONNECT_HOST", "CALDAV_TASK_LIST", "FEED_TIMEZONE", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "REMINDERS_BOARD_ID"):
        if environ.get(k):
            cfg[k] = environ[k]
    cfg.setdefault("CALDAV_URL", "https://siuds.synology.me:38443/caldav/")
    cfg.setdefault("CALDAV_USER", "calendar-monday")
    cfg.setdefault("CALDAV_TASK_LIST", "monday reminders")
    cfg.setdefault("REMINDERS_BOARD_ID", str(BOARD_ID_DEFAULT))
    return cfg


def require(cfg: dict, keys: list[str]) -> None:
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        raise SetupError("missing in the env file: " + ", ".join(missing))


def new_state() -> dict:
    return {"version": 1, "task_list_url": "", "entries": {}, "last_board_read": 0.0, "fail_count": 0, "alerted": False,
            "board": {}}


def load_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
        base = new_state()
        base.update(s)
        return base
    except FileNotFoundError:
        return new_state()
    except ValueError:
        raise SetupError(f"{path} is not valid JSON; move it aside (the script then starts clean and will re-check the list)")


def save_state(path: str, state: dict) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".state-", dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


class Log:
    def __init__(self, path: str | None, echo=print, max_bytes: int = 1_000_000):
        self.path, self.echo, self.max_bytes = path, echo, max_bytes

    def __call__(self, msg: str) -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
        self.echo(line)
        if self.path:
            try:
                if os.path.exists(self.path) and os.path.getsize(self.path) > self.max_bytes:
                    os.replace(self.path, self.path + ".1")
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


# ======================================================================================= the run
class Clients:
    """Everything the run talks to; tests pass fakes."""

    def __init__(self, dav: Dav, monday: Monday, fetch, telegram):
        self.dav, self.monday, self.fetch, self.telegram = dav, monday, fetch, telegram


def board_refresh(cl: Clients, state: dict, now: datetime, log) -> None:
    items = cl.monday.read_board()
    state["board"] = {i["name"]: i for i in items}
    state["last_board_read"] = now.timestamp()
    log(f"board read: {len(items)} reminder items")


def add_missing_tasks(cl, state, tasks_by_uid, log) -> None:
    """A task absent from the REPORT list may only be hidden (Synology may leave ticked tasks out of the list): ask the
    server for that one resource. 200 = it exists (and may be completed), 404 = really gone. Mutates tasks_by_uid."""
    for e in state["entries"].values():
        if e.get("ticked") or e.get("deleted") or e.get("dismissed") or e.get("monday_done") or not e.get("href"):
            continue
        if e["task_uid"] in tasks_by_uid or not e.get("created_ok"):
            continue
        try:
            status, _, body = cl.dav.request("GET", e["href"])
        except Exception as ex:                                    # noqa: BLE001 - leave it; never infer from an error
            log(f"  GET {e['href']} failed ({ex}); leaving '{e['title']}' alone this run")
            tasks_by_uid[e["task_uid"]] = {"uid": e["task_uid"], "completed": False, "completed_at": None, "summary": e["title"]}
            continue
        if status == 200:
            found = [t for t in parse_vtodos(body.decode("utf-8", "replace")) if t["uid"] == e["task_uid"]]
            if found:
                log(f"  '{e['title']}' is not in the list but exists on the server (completed={found[0]['completed']})")
                tasks_by_uid[e["task_uid"]] = found[0]
        elif status != 404:                                        # 5xx, 401 ...: an error is not "gone"
            log(f"  GET {e['href']} -> HTTP {status}; leaving '{e['title']}' alone this run")
            tasks_by_uid[e["task_uid"]] = {"uid": e["task_uid"], "completed": False, "completed_at": None, "summary": e["title"]}


def process_ticks(cl, state, tasks_by_uid, now, log, dry, cfg_tg=("", "")) -> int:
    """Completed on the phone -> monday Done + one Update on the Wxx task. Returns how many were ticked."""
    n = 0
    for fuid, e in state["entries"].items():
        if e.get("ticked") or e.get("monday_done"):
            continue                          # a 'dismissed' or 'deleted' entry whose task is still on the server and completed counts
        t = tasks_by_uid.get(e["task_uid"])
        if t is None or not t["completed"]:
            continue
        when = t["completed_at"] or now
        log(f"TICK '{e['title']}' completed on the phone at {sydney_hhmm(when)} Sydney")
        if dry:
            n += 1
            continue
        try:
            board_refresh(cl, state, now, log)                     # fresh ids, one call
            item = state["board"].get(e["title"])
            if item is None:
                log(f"  tick NOT sent: no item named '{e['title']}' on the Reminders board; will retry next run")
                continue
            is_step = item.get("task_board_id") in SUBITEM_BOARDS
            if item["task_item_id"] and not e.get("update_posted"):         # note first, then status (board rule 4)
                text = f"Ben ticked reminder '{e['title']}' at {sydney_hhmm(when)} Sydney"
                cl.monday.post_update(item["task_item_id"], text + (" - this step is marked Done." if is_step else ""))
                e["update_posted"] = True
            elif not item["task_item_id"]:
                log("  no Task link on the reminder item: Done set, no Update posted")
            if is_step and not e.get("step_done") and not e.get("step_error"):
                try:
                    cl.monday.set_status_done(item["task_board_id"], item["task_item_id"], SUBITEM_STATUS_COL)
                    e["step_done"] = True
                    log(f"  step {item['task_item_id']} marked Done")
                except Exception as ex:                                    # noqa: BLE001 - say so once, never loop on it
                    e["step_error"] = str(ex)[:200]
                    log(f"  step NOT marked Done (will not retry): {ex}")
                    cl.telegram(cfg_tg[0], cfg_tg[1], f"Reminders sync: ticked '{e['title']}' but could not mark its step "
                                f"Done on monday ({str(ex)[:120]}). Mark it by hand.")
            if not item["done"]:
                cl.monday.set_done(item["id"])
            e["ticked"] = True
            e["ticked_at"] = _ts(when)
            n += 1
        except Exception as ex:                                    # noqa: BLE001 - retried on the next run
            log(f"  tick FAILED (will retry): {ex}")
    return n


def process_sync(cl, state, events, tasks_by_uid, now, log, dry) -> None:
    ents = state["entries"]
    seen = set()
    for ev in events:
        fuid = ev["uid"]
        seen.add(fuid)
        digest = hashlib.sha1(f"{ev['title']}|{fmt_utc(ev['due'])}".encode("utf-8")).hexdigest()
        e = ents.get(fuid)
        if e is None:
            if ev["due"] < now - LATE_GRACE:
                continue                                           # an old reminder: nothing to alert about
            board = state["board"].get(ev["title"])
            if board and board["done"]:
                continue
            e = {"task_uid": task_uid(fuid), "title": ev["title"], "due": _ts(ev["due"]), "digest": "", "href": "",
                 "ticked": False, "sent": False, "monday_done": False, "deleted": False, "first_seen": _ts(now)}
            ents[fuid] = e
        if e.get("ticked") or e.get("dismissed") or e.get("monday_done"):
            continue                                               # finished: never reopen it
        if e["digest"] == digest and e["href"]:
            if e["task_uid"] in tasks_by_uid:
                e["missing"] = 0
            elif e.get("created_ok"):
                # One miss proves nothing: on 2026-11-06 a ticked task was missing from the list for one run (the phone's
                # change was being written) and was wrongly called dismissed. Two misses in a row, with the direct lookup
                # also saying 404 both times, is what counts.
                e["missing"] = e.get("missing", 0) + 1
                if e["missing"] >= 2:
                    log(f"DISMISSED on the phone (task gone twice in a row, not ticked): '{e['title']}'")
                    e["dismissed"] = True
                else:
                    log(f"task '{e['title']}' not seen this run (1 of 2 before it counts as dismissed)")
            continue
        log(f"{'CREATE' if not e['href'] else 'UPDATE'} task '{ev['title']}' due {sydney_stamp(ev['due'])} Sydney")
        if dry:
            continue
        try:
            e["href"] = put_task(cl.dav, state["task_list_url"], e["task_uid"], build_vtodo(e["task_uid"], ev["title"], ev["due"], now))
            e.update(title=ev["title"], due=_ts(ev["due"]), digest=digest, created_ok=True)
            if e.get("sent") and ev["due"] > now:
                e["sent"] = False                                  # moved later: tell again at the new time
        except Exception as ex:                                    # noqa: BLE001
            log(f"  PUT FAILED (will retry): {ex}")
    for fuid, e in list(ents.items()):
        if fuid in seen or e.get("deleted"):
            continue
        if e.get("ticked"):
            continue
        if e["href"] and not e.get("dismissed"):
            log(f"DELETE task '{e['title']}' (left the feed)")
            if not dry:
                try:
                    delete_task(cl.dav, e["href"])
                except Exception as ex:                            # noqa: BLE001
                    log(f"  DELETE FAILED (will retry): {ex}")
                    continue
        e["deleted"] = True
        e["deleted_at"] = _ts(now)
    # housekeeping: ticked tasks leave the phone's list a week after they were due; old records are forgotten
    for fuid, e in list(ents.items()):
        due = _dt(e["due"])
        if e.get("ticked") and e["href"] and not e.get("cleared") and due < now - KEEP_TICKED:
            log(f"CLEAN '{e['title']}' (ticked, due over a week ago)")
            if not dry:
                try:
                    delete_task(cl.dav, e["href"])
                    e["cleared"] = True
                except Exception as ex:                            # noqa: BLE001
                    log(f"  CLEAN FAILED: {ex}")
        if due < now - SENT_KEEP and (e.get("deleted") or e.get("cleared") or e.get("dismissed") or e.get("monday_done")):
            ents.pop(fuid, None)


def process_monday_done(cl, state, tasks_by_uid, now, log, dry) -> None:
    """A reminder someone set Done in monday: complete its phone task so it stops showing and never alerts."""
    for fuid, e in state["entries"].items():
        if e.get("ticked") or e.get("monday_done") or e.get("deleted") or e.get("dismissed") or not e["href"]:
            continue
        b = state["board"].get(e["title"])
        if b and b["done"]:
            log(f"COMPLETE task '{e['title']}' (set Done in monday)")
            if dry:
                continue
            try:
                put_task(cl.dav, state["task_list_url"], e["task_uid"], build_vtodo(e["task_uid"], e["title"], _dt(e["due"]), now, completed_at=now))
                e["monday_done"] = True
            except Exception as ex:                                # noqa: BLE001
                log(f"  COMPLETE FAILED (will retry): {ex}")


def process_telegram(cl, state, cfg, now, log, dry) -> None:
    for fuid, e in state["entries"].items():
        if e.get("sent") or e.get("ticked") or e.get("monday_done") or e.get("deleted") or e.get("dismissed"):
            continue
        due = _dt(e["due"])
        if due > now or due < now - TELEGRAM_STALE:
            continue
        text = f"Reminder: {e['title']} (due {sydney_stamp(due)} Sydney)"
        log(f"TELEGRAM '{e['title']}'")
        if dry:
            continue
        ok = cl.telegram(cfg.get("TELEGRAM_BOT_TOKEN", ""), cfg.get("TELEGRAM_CHAT_ID", ""), text)
        if not ok:
            log("  telegram NOT sent (no token/chat id, or Telegram unreachable); will not retry this reminder")
        e["sent"] = True


def health(cl, cfg, state, ok: bool, what: str, log, dry) -> None:
    if ok:
        if state.get("alerted") and not dry:
            cl.telegram(cfg.get("TELEGRAM_BOT_TOKEN", ""), cfg.get("TELEGRAM_CHAT_ID", ""),
                        "Reminders sync: working again.")
        state["fail_count"], state["alerted"] = 0, False
        return
    state["fail_count"] = state.get("fail_count", 0) + 1
    if state["fail_count"] >= FAIL_ALERT_AFTER and not state.get("alerted") and not dry:
        sent = cl.telegram(cfg.get("TELEGRAM_BOT_TOKEN", ""), cfg.get("TELEGRAM_CHAT_ID", ""),
                           f"Reminders sync has failed {state['fail_count']} runs in a row ({what}). "
                           "New iPhone reminders will not appear until it is fixed. Check reminders.log on the NAS.")
        state["alerted"] = True
        log(f"alarm sent: {sent}")


def run(cfg: dict, state: dict, cl: Clients, now: datetime, log, dry: bool = False) -> int:
    """One sync run. Mutates `state` (the caller saves it). Returns 0 or 1."""
    problems: list[str] = []
    # 1. feed
    events = None
    try:
        events = parse_feed(cl.fetch(cfg["REMINDERS_FEED_URL"]), cfg.get("FEED_TIMEZONE", ""))
    except Exception as ex:                                        # noqa: BLE001
        problems.append(f"feed: {ex}")
        log(f"FEED FAILED (nothing is deleted this run): {ex}")
    # 2. task list
    tasks = None
    try:
        if not state["task_list_url"]:
            url = find_task_list(cl.dav, cfg["CALDAV_TASK_LIST"])
            if not url:
                raise SetupError(f"task list '{cfg['CALDAV_TASK_LIST']}' not found: run with --create-list once")
            state["task_list_url"] = url
        try:
            tasks = report_tasks(cl.dav, state["task_list_url"])
        except DavError as ex:
            if ex.status == 404:                                   # the list was moved or recreated: look again next run
                state["task_list_url"] = ""
            raise
    except SetupError:
        raise
    except Exception as ex:                                        # noqa: BLE001
        problems.append(f"calendar: {ex}")
        log(f"CALENDAR FAILED (no ticks, no changes this run): {ex}")
    tasks_by_uid = {t["uid"]: t for t in tasks} if tasks is not None else None
    # 3. ticks
    if tasks_by_uid is not None:
        add_missing_tasks(cl, state, tasks_by_uid, log)
        process_ticks(cl, state, tasks_by_uid, now, log, dry,
                      (cfg.get("TELEGRAM_BOT_TOKEN", ""), cfg.get("TELEGRAM_CHAT_ID", "")))
    # 4. hourly board read
    if not dry and now.timestamp() - state.get("last_board_read", 0) >= BOARD_REFRESH_S and events is not None:
        try:
            board_refresh(cl, state, now, log)
        except Exception as ex:                                    # noqa: BLE001
            problems.append(f"monday: {ex}")
            log(f"BOARD READ FAILED: {ex}")
    # 5. sync + monday-done
    if events is not None and tasks_by_uid is not None:
        process_sync(cl, state, events, tasks_by_uid, now, log, dry)
        process_monday_done(cl, state, tasks_by_uid, now, log, dry)
    # 6. telegram backup (needs only the feed's earlier state, so it works even when the calendar is down)
    process_telegram(cl, state, cfg, now, log, dry)
    health(cl, cfg, state, not problems, "; ".join(problems), log, dry)
    return 1 if problems else 0


# ======================================================================================= check / create / dump
def do_check(cfg, cl: Clients, out=print) -> int:
    bad = 0
    try:
        events = parse_feed(cl.fetch(cfg["REMINDERS_FEED_URL"]), cfg.get("FEED_TIMEZONE", ""))
        out(f"PASS feed: {len(events)} events (times below are what the script will alert at; compare with monday's Remind at)")
        for ev in sorted(events, key=lambda e: e["due"])[-5:]:
            out(f"       {sydney_stamp(ev['due'])} Sydney  {ev['title']}\n         feed says: {ev.get('raw', '')}")
    except Exception as ex:                                        # noqa: BLE001
        bad += 1
        out(f"FAIL feed: {ex}")
    try:
        home = discover_home(cl.dav)
        cols = list_collections(cl.dav, home)
        out(f"PASS CalDAV login; home {home}")
        for c in cols:
            out(f"       '{c['name']}'  {','.join(c['components']) or '?'}  {c['href']}")
        want = cfg["CALDAV_TASK_LIST"]
        if any(c["name"] == want for c in cols):
            out(f"PASS task list '{want}' exists")
        else:
            bad += 1
            out(f"FAIL task list '{want}' not found: run  reminders_sync.py --create-list")
    except Exception as ex:                                        # noqa: BLE001
        bad += 1
        out(f"FAIL CalDAV: {ex}")
    try:
        n = len(cl.monday.read_board())
        out(f"PASS monday API token: {n} reminder items on the board")
    except Exception as ex:                                        # noqa: BLE001
        bad += 1
        out(f"FAIL monday API: {ex}")
    out("telegram: " + ("token and chat id present" if cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID")
                        else "NOT configured (backup message will not be sent)"))
    return 1 if bad else 0


PROPFIND_ETAGS = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/><d:resourcetype/></d:prop></d:propfind>')


def do_dump_raw(cfg, cl: Clients, name: str, out=print) -> int:
    """Read-only: every resource Synology holds in one list (PROPFIND, not REPORT) with its raw text, plus what REPORT
    returns, to learn what Synology does with a task once it is ticked."""
    home = discover_home(cl.dav)
    for c in list_collections(cl.dav, home):
        if c["name"] != name:
            continue
        status, _, body = cl.dav.request("PROPFIND", c["href"], PROPFIND_ETAGS,
                                         {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
        out(f"PROPFIND {c['href']} -> HTTP {status}")
        hrefs = [_text(r, "d:href") for r in _xml(body).findall("d:response", NS)] if status in (200, 207) else []
        for h in hrefs:
            if not h.endswith(".ics"):
                continue
            st, _, raw = cl.dav.request("GET", h)
            out(f"--- GET {h} -> HTTP {st}")
            out(raw.decode("utf-8", "replace").strip())
        try:
            rep = report_tasks(cl.dav, c["href"])
            out(f"REPORT returns {len(rep)} task(s): " + ", ".join(f"{t['summary'][:40]!r} completed={t['completed']}" for t in rep))
        except Exception as ex:                                    # noqa: BLE001
            out(f"REPORT failed: {ex}")
        return 0
    out(f"no list named '{name}'")
    return 1


def do_dump(cfg, cl: Clients, name: str, out=print) -> int:
    home = discover_home(cl.dav)
    for c in list_collections(cl.dav, home):
        if c["name"] == name:
            for t in report_tasks(cl.dav, c["href"]):
                out(f"--- {t['href']}\n    summary={t['summary']!r} completed={t['completed']} due={t['due']}")
            return 0
    out(f"no list named '{name}'")
    return 1


# ======================================================================================= main
def build_clients(cfg) -> Clients:
    return Clients(Dav(cfg["CALDAV_URL"], cfg["CALDAV_USER"], cfg["CALDAV_PASSWORD"], cfg.get("CALDAV_CONNECT_HOST", "")),
                   Monday(cfg["MONDAY_API_TOKEN"], int(cfg["REMINDERS_BOARD_ID"])), fetch_feed, send_telegram)


def main(argv=None, clients=None, now=None, environ=os.environ, out=print) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env", default=DEFAULT_ENV)
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--create-list", action="store_true")
    ap.add_argument("--dump", metavar="LIST")
    ap.add_argument("--dump-raw", metavar="LIST", help="read-only: raw text of every resource in a list, and what REPORT returns")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    log = Log(a.log, echo=out)
    try:
        cfg = load_env(a.env, environ)
        require(cfg, ["REMINDERS_FEED_URL", "MONDAY_API_TOKEN", "CALDAV_PASSWORD"])
        cl = clients or build_clients(cfg)
        if a.check:
            return do_check(cfg, cl, out)
        if a.dump:
            return do_dump(cfg, cl, a.dump, out)
        if a.dump_raw:
            return do_dump_raw(cfg, cl, a.dump_raw, out)
        if a.create_list:
            if find_task_list(cl.dav, cfg["CALDAV_TASK_LIST"]):
                out(f"task list '{cfg['CALDAV_TASK_LIST']}' already exists; nothing to do")
                return 0
            out("created: " + create_task_list(cl.dav, cfg["CALDAV_TASK_LIST"]))
            return 0
        lock = _lock(a.state)
        if lock is None:
            log("another run is still going; skipping this one")
            return 0
        try:
            state = load_state(a.state)
            rc = run(cfg, state, cl, now or utc_now(), log, a.dry_run)
            if not a.dry_run:
                save_state(a.state, state)
            return rc
        finally:
            _unlock(lock)
    except SetupError as ex:
        log(f"SETUP: {ex}")
        return 2


def _lock(state_path: str):
    try:
        import fcntl
    except ImportError:                                            # pragma: no cover - Windows: no lock, tests only
        return object()
    f = open(state_path + ".lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def _unlock(f) -> None:
    try:
        f.close()
    except AttributeError:                                         # pragma: no cover
        pass


if __name__ == "__main__":
    sys.exit(main())
