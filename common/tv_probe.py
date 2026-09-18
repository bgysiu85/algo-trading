#!/usr/bin/env python3
"""Measure the feed's two defects instead of inferring them. READ ONLY.

    python -m common.tv_probe                       # 04:00-04:35 ET, 10s polls
    python -m common.tv_probe --minutes 45
    python -m common.tv_probe --replay var/reports/tv_probe.csv   # re-read only

REGISTERED_feed_freshness.md §5. Three questions, one morning, no money:

  5.1  IS THERE A COLUMN THAT DATES THE ROW?
       The shipped gate infers freshness from movement, because nothing
       observed so far dates a row. If TradingView carries an update-time
       column the inference can be replaced by an exact test. The names below
       are GUESSES -- tv_screener's docstring records how much of that mapping
       took guessing, and the server has a documented habit of accepting a
       thing it then does not do. So this asks, and reports what came back.

  5.2  OBSERVE THE ROLL DIRECTLY.
       Every poll, every row's premarket_volume, to CSV. Today the 04:00
       carry-over is inferred from four blocked stamps between 04:00:05 and
       04:00:26. After one morning it is measured: per name, the poll at which
       its volume first moved.

  5.3  PRICE THE DELAY.
       With TV_SESSIONID set IN THE ENVIRONMENT, each poll runs the same query
       twice -- once with the session cookie, once without -- and the report
       gives, per name, the difference in the minute each arm first returned
       it. The registered reading is the MEDIAN across names; the registered
       prediction is 10-20 minutes, against the +15.6 median the blocked stamps
       gave from the other direction. A reading near zero means the delay is
       not the endpoint, and sends the 15-minute finding back to be explained.

WHY THE COOKIE IS AN ENVIRONMENT VARIABLE AND NEVER A FLAG
----------------------------------------------------------
The same rule DATABENTO_API_KEY carries: a flag puts the secret in shell
history. It is read from the environment, never logged, never written to the
CSV or the report, and the report says only whether an authenticated arm ran.

WHAT THIS CANNOT DO
-------------------
It never takes the writer lock, never writes watchlist.txt, and cannot move the
trader. It is safe to run beside a live feed. It does add a second (or third)
request per poll to the same endpoint, so it is bounded by --minutes and is not
something to leave running for five hours.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from common import report_io
from common.tv_feed import ENDPOINT, REQUEST_TIMEOUT, tv_payload
from common.tv_screener import CHANGE_COLUMN, COLUMNS, MARKET, VOLUME_COLUMN

LOG = logging.getLogger("tv_probe")
ET = ZoneInfo("America/New_York")

OUT_CSV = Path("var/reports/tv_probe.csv")
OUT_TXT = Path("var/reports/tv_probe.txt")

COOKIE_ENV = "TV_SESSIONID"

# GUESSES, and labelled as such. Every one of these is a column name that MIGHT
# date a row; none is documented for this endpoint. The probe's whole job here
# is to replace the guessing with an answer, so a name that comes back empty is
# a result, not a failure.
CANDIDATE_TIME_COLUMNS = (
    "update_mode",
    "update_time",
    "last_bar_update_time",
    "time",
    "premarket_time",
    "premarket_volume_time",
    "pricescale_update_time",
)


def _scan(payload: dict, cookie: str | None = None) -> dict:
    """One POST. `cookie` is the raw sessionid value and is never logged."""
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    if cookie:
        headers["Cookie"] = f"sessionid={cookie}"
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
        return json.load(r)


def columns_payload(extra: tuple[str, ...]) -> dict:
    """The shipped query with candidate columns appended.

    Appended rather than substituted so the row set is IDENTICAL to the feed's:
    a probe that screens differently is measuring a different screen.
    """
    p = tv_payload()
    p["columns"] = list(COLUMNS) + [c for c in extra if c not in COLUMNS]
    return p


def read_columns(body: dict, extra: tuple[str, ...]) -> dict[str, object]:
    """candidate -> a sample value, or None when the server returned nothing.

    A column TradingView does not know is not an error: it comes back null on
    every row, or the row is short. Both read as absent here.
    """
    names = list(COLUMNS) + [c for c in extra if c not in COLUMNS]
    out: dict[str, object] = {c: None for c in extra}
    for item in (body.get("data") or []):
        vals = item.get("d") or []
        row = dict(zip(names, vals))
        for c in extra:
            if out[c] is None and row.get(c) is not None:
                out[c] = row[c]
    return out


def rows_of(body: dict) -> list[dict]:
    out = []
    for item in (body.get("data") or []):
        row = dict(zip(COLUMNS, item.get("d") or []))
        row["ticker"] = item.get("s", "").split(":")[-1]
        out.append(row)
    return out


def append_rows(path: Path, poll_et: str, arm: str, rows: list[dict]) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["poll_et", "arm", "ticker", VOLUME_COLUMN,
                        CHANGE_COLUMN, "premarket_close"])
        for r in rows:
            w.writerow([poll_et, arm, r.get("ticker"), r.get(VOLUME_COLUMN),
                        r.get(CHANGE_COLUMN), r.get("premarket_close")])


def summarise(records: list[dict]) -> dict:
    """The three readings, off the CSV alone so a run can be re-read later.

    `records` are CSV rows: poll_et, arm, ticker, premarket_volume, ...
    """
    first_seen: dict[tuple[str, str], str] = {}
    first_vol: dict[tuple[str, str], str] = {}
    first_move: dict[tuple[str, str], str] = {}
    for r in records:
        key = (r["arm"], r["ticker"])
        first_seen.setdefault(key, r["poll_et"])
        v = r.get(VOLUME_COLUMN)
        if v in (None, ""):
            continue
        if key not in first_vol:
            first_vol[key] = v
        elif key not in first_move and v != first_vol[key]:
            first_move[key] = r["poll_et"]

    def _dt(s):
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

    # 5.2 -- how long each name sat on a number that never moved.
    holds = []
    for (arm, t), seen in sorted(first_seen.items()):
        if arm != "plain":
            continue
        moved = first_move.get((arm, t))
        holds.append({"ticker": t, "first_seen": seen, "first_moved": moved,
                      "held_s": (_dt(moved) - _dt(seen)).total_seconds()
                      if moved else None})

    # 5.3 -- authenticated minus unauthenticated, per name, in minutes.
    deltas = []
    for (arm, t), seen in first_seen.items():
        if arm != "auth":
            continue
        plain = first_seen.get(("plain", t))
        if plain:
            deltas.append({"ticker": t,
                           "minutes": (_dt(plain) - _dt(seen)).total_seconds() / 60.0})
    auth_only = sorted(t for (arm, t) in first_seen
                       if arm == "auth" and ("plain", t) not in first_seen)
    return {"holds": holds, "deltas": sorted(deltas, key=lambda d: -d["minutes"]),
            "auth_only": auth_only,
            "median_minutes": statistics.median([d["minutes"] for d in deltas])
            if deltas else None}


def render(summary: dict, columns: dict[str, object] | None, polls: int,
           authed: bool) -> list[str]:
    L: list[str] = []
    L.append("THE FEED PROBE: HOW STALE IS THE FIRST POLL, AND HOW LATE IS THE TAPE?")
    L.append("")
    L.append("  registered  docs/research/REGISTERED_feed_freshness.md (H-F1) §5")
    L.append(f"  endpoint    {ENDPOINT}   market {MARKET}")
    L.append(f"  polls       {polls}   authenticated arm: "
             f"{'yes' if authed else f'NO ({COOKIE_ENV} not set)'}")
    L.append("")

    L.append("5.1  DOES ANY COLUMN DATE THE ROW?")
    L.append("")
    if columns is None:
        L.append("     not probed on this run")
    else:
        for c, v in columns.items():
            L.append(f"     {c:<28} {'absent' if v is None else repr(v)[:40]}")
        got = [c for c, v in columns.items() if v is not None]
        L.append("")
        L.append("     " + ("a column came back with values -- the gate's inference "
                            f"can become an exact test: {', '.join(got)}"
                            if got else
                            "none of the candidates returned a value. The gate's "
                            "wait-for-movement rule stays the only test available."))
    L.append("")

    L.append("5.2  THE ROLL, OBSERVED (unauthenticated arm)")
    L.append("")
    L.append("     ticker      first seen   first moved   held")
    stuck = 0
    for h in summary["holds"]:
        if h["first_moved"] is None:
            stuck += 1
            L.append(f"     {h['ticker']:<11} {h['first_seen'][-8:]}     "
                     f"{'never':<12}  --")
        else:
            L.append(f"     {h['ticker']:<11} {h['first_seen'][-8:]}     "
                     f"{h['first_moved'][-8:]:<12}  {h['held_s']:.0f}s")
    L.append("")
    L.append(f"     {stuck} name(s) never moved inside the probe window. On the "
             "04:00 poll those")
    L.append("     are the carry-over: a row that never moves is a row that "
             "describes yesterday.")
    L.append("")

    L.append("5.3  AUTHENTICATED AGAINST NOT")
    L.append("")
    if not authed:
        L.append(f"     not run -- {COOKIE_ENV} was not set in the environment.")
        L.append("     Without it this probe cannot price the 15-minute delay, only")
        L.append("     the roll.")
    elif not summary["deltas"]:
        L.append("     no name was returned by both arms -- nothing to compare.")
    else:
        L.append("     ticker      authenticated leads by")
        for d in summary["deltas"]:
            L.append(f"     {d['ticker']:<11} {d['minutes']:+.1f} min")
        L.append("")
        L.append(f"     MEDIAN {summary['median_minutes']:+.1f} minutes across "
                 f"{len(summary['deltas'])} name(s)")
        L.append("     registered prediction: 10-20 minutes. A reading near zero "
                 "means the")
        L.append("     delay is NOT the endpoint and the 15-minute finding needs "
                 "another explanation.")
        if summary["auth_only"]:
            L.append("")
            L.append("     returned ONLY by the authenticated arm inside the window: "
                     + ", ".join(summary["auth_only"]))
    L.append("")
    L.append("WHAT THIS IS NOT")
    L.append("")
    L.append("  NOT A CHANGE. This probe is read-only: it never takes the writer")
    L.append("  lock and never writes watchlist.txt. No feed behaviour changes on")
    L.append("  the strength of it without its own commit.")
    L.append("  NOT A SCREEN. The row set is the shipped screen's, unmodified --")
    L.append("  candidate columns are APPENDED, never substituted.")
    return L


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="measure the feed's staleness and lag")
    ap.add_argument("--minutes", type=float, default=35.0,
                    help="how long to poll for (default 35, from 04:00)")
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--csv", type=Path, default=OUT_CSV)
    ap.add_argument("--out", type=Path, default=OUT_TXT)
    ap.add_argument("--replay", type=Path, default=None,
                    help="re-read an existing CSV and re-render; no network")
    ap.add_argument("--no-columns", action="store_true",
                    help="skip the 5.1 column probe")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    if a.replay:
        with a.replay.open(encoding="utf-8") as fh:
            records = list(csv.DictReader(fh))
        body = render(summarise(records), None, polls=0,
                      authed=any(r["arm"] == "auth" for r in records))
        report_io.emit("\n".join(body), a.out,
                       header=f"common.tv_probe --replay {a.replay}")
        return 0

    cookie = os.environ.get(COOKIE_ENV) or None
    if not cookie:
        LOG.warning("%s is not set -- the authenticated arm will not run, and "
                    "§5.3 cannot be read this morning.", COOKIE_ENV)

    columns = None
    if not a.no_columns:
        try:
            columns = read_columns(_scan(columns_payload(CANDIDATE_TIME_COLUMNS)),
                                   CANDIDATE_TIME_COLUMNS)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError) as e:
            LOG.warning("column probe failed (%s: %s)", type(e).__name__, e)

    if a.csv.exists():
        a.csv.unlink()
    stop = datetime.now(ET) + timedelta(minutes=a.minutes)
    polls = 0
    while datetime.now(ET) < stop:
        now = datetime.now(ET)
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        for arm, ck in (("plain", None), ("auth", cookie)):
            if arm == "auth" and not cookie:
                continue
            try:
                append_rows(a.csv, stamp, arm, rows_of(_scan(tv_payload(), ck)))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                    json.JSONDecodeError) as e:
                LOG.warning("%s arm failed (%s: %s)", arm, type(e).__name__, e)
        polls += 1
        if polls % 6 == 0:
            LOG.info("%d polls, %s remaining", polls, stop - datetime.now(ET))
        time.sleep(a.interval)

    with a.csv.open(encoding="utf-8") as fh:
        records = list(csv.DictReader(fh))
    report_io.emit(
        "\n".join(render(summarise(records), columns, polls, bool(cookie))),
        a.out, header=f"common.tv_probe --minutes {a.minutes} "
                      f"--interval {a.interval}")
    LOG.info("wrote %s and %s", a.out, a.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
