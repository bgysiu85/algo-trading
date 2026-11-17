#!/usr/bin/env python3
r"""W15-0069 step 5b -- move the W16-0014 weekly task to Sunday 10:00 Sydney and add the
missing W15-0037 weekly task, both cloned from the W16-0014 task that already works.

    D:\Trading\.venv\Scripts\python.exe tools\w15_0069_schedule_tasks.py            (dry run: shows the plan)
    D:\Trading\.venv\Scripts\python.exe tools\w15_0069_schedule_tasks.py --apply    (registers both tasks)

Why clone: the W16-0014 task ran unattended on 14 Nov with exit 0 and pushed its ledger, so its
user, logon type and environment already reach Databento and GitHub. The W15-0037 task gets the
same settings; only the module in its arguments and its time differ.

Times (Sydney local, as Task Scheduler shows them):
  W16-0014  Sunday 10:00  (Saturday 23:00 UTC; Databento's dataset end lags ~8 h, so a Saturday
                           run only defers the last day -- handover_w15_0069_forward_runs_20261110)
  W15-0037  Sunday 10:30  (30 min later so the two wrappers never run git commit/push at once,
                           which could leave .git/index.lock behind)

Safety: refuses (changes nothing) if the source task stores a password (LogonType Password),
because re-registering it would need that password. Writes the XML it registers and a short
report to D:\Trading\Claude outputs so Claude can read the result.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
ET.register_namespace("", NS)
Q = lambda tag: f"{{{NS}}}{tag}"  # noqa: E731

SOURCE_TASK = "W16-0014 DVP-F1 weekly scorer"
NEW_TASK = "W15-0037 CHARTMARK-v2 weekly scorer"
W16_MODULE = "strategy.w16.dvp_forward_scheduled"
W15_MODULE = "strategy.chartmark_v2.forward_scheduled"
W16_TIME = dt.time(10, 0)
W15_TIME = dt.time(10, 30)
OUT_DIR = Path(r"D:\Trading\Claude outputs")
REPORT = OUT_DIR / "w15_0069_schedule_result.txt"


class Refused(Exception):
    pass


def next_sunday(today: dt.date) -> dt.date:
    days = (6 - today.weekday()) % 7 or 7  # Monday=0 ... Sunday=6; always a future Sunday
    return today + dt.timedelta(days=days)


def decode_xml(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8", "mbcs" if sys.platform == "win32" else "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise Refused("could not decode the task XML")


def _parse(xml_text: str) -> ET.Element:
    # ElementTree refuses a str that still carries an encoding declaration of UTF-16
    if xml_text.lstrip().startswith("<?xml"):
        xml_text = xml_text[xml_text.index("?>") + 2:]
    return ET.fromstring(xml_text.strip())


def check_source(root: ET.Element, expected_module: str) -> None:
    logon = root.find(f"{Q('Principals')}/{Q('Principal')}/{Q('LogonType')}")
    if logon is not None and logon.text == "Password":
        raise Refused("the W16-0014 task stores a password (LogonType Password); re-registering it would "
                      "need that password. Nothing changed -- tell Claude.")
    args = root.find(f"{Q('Actions')}/{Q('Exec')}/{Q('Arguments')}")
    if args is None or expected_module not in (args.text or ""):
        raise Refused(f"the source task's arguments do not run {expected_module}; nothing changed.")
    if root.find(f"{Q('Triggers')}/{Q('CalendarTrigger')}") is None:
        raise Refused("the source task has no calendar trigger; nothing changed.")


def retime(root: ET.Element, day: dt.date, at: dt.time) -> ET.Element:
    """Return a copy whose only trigger is weekly, Sunday, at `at` local time, starting `day`."""
    new = _parse(ET.tostring(root, encoding="unicode"))
    triggers = new.find(Q("Triggers"))
    old = triggers.find(Q("CalendarTrigger"))
    enabled = old.find(Q("Enabled"))
    for child in list(triggers):
        triggers.remove(child)
    trig = ET.SubElement(triggers, Q("CalendarTrigger"))
    ET.SubElement(trig, Q("StartBoundary")).text = dt.datetime.combine(day, at).isoformat()  # no offset = local time
    ET.SubElement(trig, Q("Enabled")).text = enabled.text if enabled is not None else "true"
    week = ET.SubElement(trig, Q("ScheduleByWeek"))
    dow = ET.SubElement(week, Q("DaysOfWeek"))
    ET.SubElement(dow, Q("Sunday"))
    ET.SubElement(week, Q("WeeksInterval")).text = "1"
    return new


def make_w15(w16_retimed: ET.Element, day: dt.date) -> ET.Element:
    new = retime(w16_retimed, day, W15_TIME)
    args = new.find(f"{Q('Actions')}/{Q('Exec')}/{Q('Arguments')}")
    args.text = (args.text or "").replace(W16_MODULE, W15_MODULE)
    info = new.find(Q("RegistrationInfo"))
    if info is not None:
        for tag in ("URI", "Date"):
            el = info.find(Q(tag))
            if el is not None:
                info.remove(el)
        desc = info.find(Q("Description"))
        if desc is None:
            desc = ET.SubElement(info, Q("Description"))
        desc.text = "W15-0037 CHARTMARK-v2 weekly forward scorer (W15-0069). Cloned from the W16-0014 task."
    return new


def to_xml_bytes(root: ET.Element) -> bytes:
    body = ET.tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-16"?>\n' + body).encode("utf-16")


def describe(root: ET.Element) -> str:
    sb = root.find(f"{Q('Triggers')}/{Q('CalendarTrigger')}/{Q('StartBoundary')}").text
    days = [c.tag.split("}")[1] for c in root.find(f"{Q('Triggers')}/{Q('CalendarTrigger')}/{Q('ScheduleByWeek')}/{Q('DaysOfWeek')}")]
    args = root.find(f"{Q('Actions')}/{Q('Exec')}/{Q('Arguments')}").text
    return f"weekly {','.join(days)} from {sb}; args: {args}"


def schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--apply", action="store_true", help="register the tasks (default: dry run)")
    a = ap.parse_args(argv)
    lines: list[str] = [f"W15-0069 step 5b -- {'APPLY' if a.apply else 'DRY RUN'} at {dt.datetime.now():%Y-%m-%d %H:%M:%S}"]
    rc = 0
    try:
        q = schtasks("/Query", "/TN", SOURCE_TASK, "/XML", "ONE")
        if q.returncode != 0:
            raise Refused(f"could not read task '{SOURCE_TASK}': {decode_xml(q.stderr or q.stdout).strip()}")
        src = _parse(decode_xml(q.stdout))
        check_source(src, W16_MODULE)
        day = next_sunday(dt.date.today())
        w16 = retime(src, day, W16_TIME)
        w15 = make_w15(w16, day)
        lines.append(f"{SOURCE_TASK}: {describe(w16)}")
        lines.append(f"{NEW_TASK}: {describe(w15)}")
        for name, root, fname in ((SOURCE_TASK, w16, "w15_0069_task_w16.xml"), (NEW_TASK, w15, "w15_0069_task_w15.xml")):
            path = OUT_DIR / fname
            path.write_bytes(to_xml_bytes(root))
            if a.apply:
                r = schtasks("/Create", "/TN", name, "/XML", str(path), "/F")
                msg = decode_xml(r.stdout or r.stderr).strip()
                lines.append(f"register '{name}': rc={r.returncode} {msg}")
                if r.returncode != 0:
                    rc = 1
                    break
        if a.apply and rc == 0:
            for name in (SOURCE_TASK, NEW_TASK):
                r = schtasks("/Query", "/TN", name, "/V", "/FO", "LIST")
                keep = [ln for ln in decode_xml(r.stdout).splitlines()
                        if ln.split(":")[0].strip() in ("TaskName", "Next Run Time", "Status", "Task To Run", "Run As User", "Days", "Start Time")]
                lines.extend(keep)
        elif not a.apply:
            lines.append("Nothing changed. Run again with --apply to register.")
    except Refused as e:
        lines.append(f"REFUSED: {e}")
        rc = 2
    text = "\n".join(lines)
    print(text)
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
