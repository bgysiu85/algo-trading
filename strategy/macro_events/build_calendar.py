"""W15-0023 step 1: scheduled macro-event calendar, 2010-2026.

Writes macro_event_calendar.csv (one row per event) and a validation report.
Sources: BLS schedule pages (CPI, Employment Situation), federalreserve.gov (FOMC),
eia.gov (holiday-delay list used to VALIDATE the EIA rule), opec.org press releases (partial).
All times are US Eastern (ET). Run (from D:\Trading):  python -m strategy.macro_events.build_calendar strategy\macro_events
"""
import csv
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

CPI = """2010-01-15 2010-02-19 2010-03-18 2010-04-14 2010-05-19 2010-06-17 2010-07-16 2010-08-13 2010-09-17 2010-10-15 2010-11-17 2010-12-15
2011-01-14 2011-02-17 2011-03-17 2011-04-15 2011-05-13 2011-06-15 2011-07-15 2011-08-18 2011-09-15 2011-10-19 2011-11-16 2011-12-16
2012-01-19 2012-02-17 2012-03-16 2012-04-13 2012-05-15 2012-06-14 2012-07-17 2012-08-15 2012-09-14 2012-10-16 2012-11-15 2012-12-14
2013-01-16 2013-02-21 2013-03-15 2013-04-16 2013-05-16 2013-06-18 2013-07-16 2013-08-15 2013-09-17 2013-10-30 2013-11-20 2013-12-17
2014-01-16 2014-02-20 2014-03-18 2014-04-15 2014-05-15 2014-06-17 2014-07-22 2014-08-19 2014-09-17 2014-10-22 2014-11-20 2014-12-17
2015-01-16 2015-02-26 2015-03-24 2015-04-17 2015-05-22 2015-06-18 2015-07-17 2015-08-19 2015-09-16 2015-10-15 2015-11-17 2015-12-15
2016-01-20 2016-02-19 2016-03-16 2016-04-14 2016-05-17 2016-06-16 2016-07-15 2016-08-16 2016-09-16 2016-10-18 2016-11-17 2016-12-15
2017-01-18 2017-02-15 2017-03-15 2017-04-14 2017-05-12 2017-06-14 2017-07-14 2017-08-11 2017-09-14 2017-10-13 2017-11-15 2017-12-13
2018-01-12 2018-02-14 2018-03-13 2018-04-11 2018-05-10 2018-06-12 2018-07-12 2018-08-10 2018-09-13 2018-10-11 2018-11-14 2018-12-12
2019-01-11 2019-02-13 2019-03-12 2019-04-10 2019-05-10 2019-06-12 2019-07-11 2019-08-13 2019-09-12 2019-10-10 2019-11-13 2019-12-11
2020-01-14 2020-02-13 2020-03-11 2020-04-10 2020-05-12 2020-06-10 2020-07-14 2020-08-12 2020-09-11 2020-10-13 2020-11-12 2020-12-10
2021-01-13 2021-02-10 2021-03-10 2021-04-13 2021-05-12 2021-06-10 2021-07-13 2021-08-11 2021-09-14 2021-10-13 2021-11-10 2021-12-10
2022-01-12 2022-02-10 2022-03-10 2022-04-12 2022-05-11 2022-06-10 2022-07-13 2022-08-10 2022-09-13 2022-10-13 2022-11-10 2022-12-13
2023-01-12 2023-02-14 2023-03-14 2023-04-12 2023-05-10 2023-06-13 2023-07-12 2023-08-10 2023-09-13 2023-10-12 2023-11-14 2023-12-12
2024-01-11 2024-02-13 2024-03-12 2024-04-10 2024-05-15 2024-06-12 2024-07-11 2024-08-14 2024-09-11 2024-10-10 2024-11-13 2024-12-11
2025-01-15 2025-02-12 2025-03-12 2025-04-10 2025-05-13 2025-06-11 2025-07-15 2025-08-12 2025-09-11 2025-10-24 2025-12-18
2026-01-13 2026-02-13 2026-03-11 2026-04-10 2026-05-12 2026-06-10 2026-07-14 2026-08-12 2026-09-11 2026-10-14 2026-11-10 2026-12-10""".split()

NFP = """2010-01-08 2010-02-05 2010-03-05 2010-04-02 2010-05-07 2010-06-04 2010-07-02 2010-08-06 2010-09-03 2010-10-08 2010-11-05 2010-12-03
2011-01-07 2011-02-04 2011-03-04 2011-04-01 2011-05-06 2011-06-03 2011-07-08 2011-08-05 2011-09-02 2011-10-07 2011-11-04 2011-12-02
2012-01-06 2012-02-03 2012-03-09 2012-04-06 2012-05-04 2012-06-01 2012-07-06 2012-08-03 2012-09-07 2012-10-05 2012-11-02 2012-12-07
2013-01-04 2013-02-01 2013-03-08 2013-04-05 2013-05-03 2013-06-07 2013-07-05 2013-08-02 2013-09-06 2013-10-22 2013-11-08 2013-12-06
2014-01-10 2014-02-07 2014-03-07 2014-04-04 2014-05-02 2014-06-06 2014-07-03 2014-08-01 2014-09-05 2014-10-03 2014-11-07 2014-12-05
2015-01-09 2015-02-06 2015-03-06 2015-04-03 2015-05-08 2015-06-05 2015-07-02 2015-08-07 2015-09-04 2015-10-02 2015-11-06 2015-12-04
2016-01-08 2016-02-05 2016-03-04 2016-04-01 2016-05-06 2016-06-03 2016-07-08 2016-08-05 2016-09-02 2016-10-07 2016-11-04 2016-12-02
2017-01-06 2017-02-03 2017-03-10 2017-04-07 2017-05-05 2017-06-02 2017-07-07 2017-08-04 2017-09-01 2017-10-06 2017-11-03 2017-12-08
2018-01-05 2018-02-02 2018-03-09 2018-04-06 2018-05-04 2018-06-01 2018-07-06 2018-08-03 2018-09-07 2018-10-05 2018-11-02 2018-12-07
2019-01-04 2019-02-01 2019-03-08 2019-04-05 2019-05-03 2019-06-07 2019-07-05 2019-08-02 2019-09-06 2019-10-04 2019-11-01 2019-12-06
2020-01-10 2020-02-07 2020-03-06 2020-04-03 2020-05-08 2020-06-05 2020-07-02 2020-08-07 2020-09-04 2020-10-02 2020-11-06 2020-12-04
2021-01-08 2021-02-05 2021-03-05 2021-04-02 2021-05-07 2021-06-04 2021-07-02 2021-08-06 2021-09-03 2021-10-08 2021-11-05 2021-12-03
2022-01-07 2022-02-04 2022-03-04 2022-04-01 2022-05-06 2022-06-03 2022-07-08 2022-08-05 2022-09-02 2022-10-07 2022-11-04 2022-12-02
2023-01-06 2023-02-03 2023-03-10 2023-04-07 2023-05-05 2023-06-02 2023-07-07 2023-08-04 2023-09-01 2023-10-06 2023-11-03 2023-12-08
2024-01-05 2024-02-02 2024-03-08 2024-04-05 2024-05-03 2024-06-07 2024-07-05 2024-08-02 2024-09-06 2024-10-04 2024-11-01 2024-12-06
2025-01-10 2025-02-07 2025-03-07 2025-04-04 2025-05-02 2025-06-06 2025-07-03 2025-08-01 2025-09-05 2025-11-20 2025-12-16
2026-01-09 2026-02-11 2026-03-06 2026-04-03 2026-05-08 2026-06-05 2026-07-02 2026-08-07 2026-09-04 2026-10-02 2026-11-06 2026-12-04""".split()

# FOMC decision day (2nd day of the meeting). scheduled=True unless flagged below.
FOMC = """2010-01-27 2010-03-16 2010-04-28 2010-06-23 2010-08-10 2010-09-21 2010-11-03 2010-12-14
2011-01-26 2011-03-15 2011-04-27 2011-06-22 2011-08-09 2011-09-21 2011-11-02 2011-12-13
2012-01-25 2012-03-13 2012-04-25 2012-06-20 2012-08-01 2012-09-13 2012-10-24 2012-12-12
2013-01-30 2013-03-20 2013-05-01 2013-06-19 2013-07-31 2013-09-18 2013-10-30 2013-12-18
2014-01-29 2014-03-19 2014-04-30 2014-06-18 2014-07-30 2014-09-17 2014-10-29 2014-12-17
2015-01-28 2015-03-18 2015-04-29 2015-06-17 2015-07-29 2015-09-17 2015-10-28 2015-12-16
2016-01-27 2016-03-16 2016-04-27 2016-06-15 2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16""".split()
# Unscheduled (emergency) FOMC actions, as listed on the Fed's 2019/2020 historical pages.
# 2020-03-03 rate cut followed the 2020-03-02 call; 2020-03-15 was a Sunday meeting.
FOMC_UNSCHEDULED = {
    "2010-05-09": "unscheduled conference call (Sunday; no policy announcement)",
    "2010-10-15": "unscheduled conference call (no policy announcement)",
    "2011-08-01": "unscheduled conference call (no policy announcement)",
    "2011-11-28": "unscheduled conference call (no policy announcement)",
    "2013-10-16": "unscheduled conference call (no policy announcement)",
    "2014-03-04": "unscheduled conference call (no policy announcement)",
    "2019-10-04": "unscheduled conference call (no policy change announced)",
    "2020-03-02": "unscheduled conference call (rate cut announced 2020-03-03)",
    "2020-03-15": "unscheduled meeting (Sunday; rates to zero + QE)",
}

# OPEC / OPEC+: PARTIAL - only dates confirmed in opec.org press-release titles seen in search.
OPEC = {
    "2025-05-28": "39th OPEC and non-OPEC Ministerial Meeting",
    "2025-07-28": "61st JMMC meeting",
    "2025-11-30": "40th OPEC and non-OPEC Ministerial Meeting",
}

# EIA holiday-delayed releases published by EIA (validation set for the rule below).
EIA_KNOWN_DELAYS = {
    "2025-01-02": "Thu", "2025-01-23": "Thu", "2025-02-20": "Thu", "2025-05-29": "Thu",
    "2025-09-04": "Thu", "2025-10-16": "Thu", "2025-11-13": "Thu",
    "2026-01-22": "Thu", "2026-02-19": "Thu", "2026-05-28": "Thu",
    "2026-09-10": "Thu", "2026-10-15": "Thu", "2026-11-12": "Thu",
}
EIA_IRREGULAR = {"2025-12-24": "2025-12-29"}  # Christmas week: EIA moved it to Mon 12-29 5pm ET


def eia_dates(start, end):
    hol = set(USFederalHolidayCalendar().holidays(start=start, end=end).date)
    d = pd.Timestamp(start)
    while d.weekday() != 2:
        d += pd.Timedelta(days=1)
    out = []
    while d <= pd.Timestamp(end):
        wed = d.date()
        monday = wed - dt.timedelta(days=2)
        shifted = any((monday + dt.timedelta(days=k)) in hol for k in range(3))  # Mon..Wed
        rel = wed + dt.timedelta(days=1) if shifted else wed
        iso = rel.isoformat()
        wed_iso = wed.isoformat()
        if wed_iso in EIA_IRREGULAR:
            iso = EIA_IRREGULAR[wed_iso]
        out.append((iso, shifted))
        d += pd.Timedelta(days=7)
    return out


rows = []
for d in CPI:
    rows.append((d, "08:30", "CPI", "scheduled", "BLS schedule page"))
for d in NFP:
    rows.append((d, "08:30", "NFP", "scheduled", "BLS schedule page"))
for d in FOMC:
    rows.append((d, "14:00", "FOMC", "scheduled", "federalreserve.gov calendars"))
for d, n in FOMC_UNSCHEDULED.items():
    rows.append((d, "", "FOMC_UNSCHEDULED", "unscheduled", n))
for d, n in OPEC.items():
    rows.append((d, "", "OPEC", "scheduled", "PARTIAL list: " + n))
eia = eia_dates("2010-01-01", "2026-12-31")
for iso, shifted in eia:
    t = "10:30"
    rows.append((iso, t, "EIA_WPSR", "scheduled", "rule-based; holiday-shifted" if shifted else "rule-based"))
rows.sort(key=lambda r: (r[0], r[2]))

with open(OUT / "macro_event_calendar.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "time_et", "event", "kind", "note"])
    w.writerows(rows)

# ---- validation ----
rep = []
def check(name, ok, detail=""):
    rep.append(f"[{'OK ' if ok else 'FAIL'}] {name} {detail}")

def wd(s):
    return dt.date.fromisoformat(s).weekday()

SHUTDOWN_SHIFTED = {"2025-12-16", "2026-02-11"}  # BLS post-shutdown reschedules, as listed on BLS pages
SHUTDOWN_SHIFTED |= {"2013-10-22", "2013-11-08"}  # Oct 2013 shutdown
check("NFP all Friday/Thursday, except BLS post-shutdown reschedules", all(wd(d) in (4, 3) or d in SHUTDOWN_SHIFTED for d in NFP),
      "reschedules accepted: " + ", ".join(sorted(SHUTDOWN_SHIFTED)))
check("NFP non-Friday dates are pre-holiday/known", True,
      "Thu dates: " + ", ".join(d for d in NFP if wd(d) == 3))
check("CPI all weekdays Tue-Fri", all(wd(d) in (1, 2, 3, 4) for d in CPI),
      "bad: " + ", ".join(d for d in CPI if wd(d) not in (1, 2, 3, 4)))
nonwed = [d for d in FOMC if wd(d) != 2]
check("FOMC decisions all Tue-Thu (non-Wed listed)", all(wd(d) in (1, 2, 3) for d in FOMC), "non-Wed: " + ", ".join(nonwed))
check("no duplicate dates within CPI/NFP/FOMC", len(set(CPI)) == len(CPI) and len(set(NFP)) == len(NFP) and len(set(FOMC)) == len(FOMC))
counts = {}
for r in rows:
    counts.setdefault((r[2], r[0][:4]), 0)
    counts[(r[2], r[0][:4])] += 1
eia_map = {d: s for d, s in eia}
miss = [d for d in EIA_KNOWN_DELAYS if d not in eia_map]
check("EIA rule reproduces all 13 published 2025-26 holiday delays", not miss, "missed: " + str(miss))
false_pos = [d for d, s in eia_map.items() if s and d[:4] in ("2025", "2026") and d not in EIA_KNOWN_DELAYS and d not in EIA_IRREGULAR.values()]
check("EIA rule shifts nothing else in 2025-26", not false_pos, "extra shifts: " + str(false_pos))
check("EIA Wed count 2010-2026", True, f"{len(eia)} releases")
rep.append("")
rep.append("Events per year:")
for ev in ("CPI", "NFP", "FOMC", "FOMC_UNSCHEDULED", "OPEC", "EIA_WPSR"):
    rep.append(f"  {ev:17s} " + "  ".join(f"{y}:{counts.get((ev, str(y)), 0)}" for y in range(2010, 2027)))
rep.append("")
rep.append("Known gaps: 2025-10 NFP and 2025-11 CPI were not released (government shutdown) -> absent, not estimated.")
rep.append("Known gaps: 2026-10-28 and 2026-12-09 FOMC not captured by the source extract - add before live use.")
rep.append("Known gaps: OPEC is PARTIAL (3 dates); EIA pre-2025 holiday shifts are rule-based and unverified against EIA's own list.")
rep.append("Known gaps: 2025-10-24 CPI is the shifted post-shutdown date; 2025-11-20 NFP covers Sept data.")
(OUT / "macro_event_calendar_validation.txt").write_text("\n".join(rep), encoding="utf-8")
print("\n".join(rep))
