#!/usr/bin/env python3
"""G8: build a point-in-time S&P 500 / S&P 400 universe from EODHD.

    $env:EODHD_API_KEY = op read "op://Trading/EODHD/api-token"
    python -m strategy.swing.pit_universe constituents
    python -m strategy.swing.pit_universe prices
    python -m strategy.swing.pit_universe report
    python -m strategy.swing.pit_universe --self-test

WHAT IT IS FOR
--------------
`swing_preflight_20260914.md` criterion G8: index constituents AS OF EACH DATE,
never today's list used as history. The pre-flight's own 36 names are 100%
survivors. This tool produces the two things a survivorship-free test needs:

  1. membership.csv  -- one row per (index, ticker, start, end) spell
  2. eod/<code>.csv  -- daily prices for every ticker that was ever a member,
                        including the ones that have since been delisted

THREE STAGES, EACH RESUMABLE, EACH SAVING WHAT IT FETCHED BEFORE USING IT
-------------------------------------------------------------------------
  constituents  index list + one constituents call per index. The raw JSON is
                written to raw/ first, then parsed. A parsing bug never costs a
                download.
  prices        one EOD call per ticker. A ticker whose file already exists is
                skipped, so an interrupted run continues where it stopped.
                Tickers that return nothing go to prices_missing.csv, with the
                reason, rather than disappearing.
  report        coverage of every membership spell by price data, members per
                index on sample dates, and a comparison against the free
                fja05680 S&P 500 list. It spends no API calls.

THE KEY
-------
Read from EODHD_API_KEY and nowhere else. There is deliberately no --key flag:
a flag puts the key in PowerShell history. The key is scrubbed from every
message this tool prints, because a URL in an exception is how keys escape.

WHAT IT COSTS
-------------
Nothing beyond the subscription Ben already bought (AT-100). API calls: about
3 for constituents and one per ticker for prices -- roughly 1,000-1,500 in all,
against a 100,000-a-day allowance.

NO REPO IMPORTS
---------------
Same convention as the rest of strategy/swing/: standard library only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

API = "https://eodhd.com/api"
ENV_KEY = "EODHD_API_KEY"
DEFAULT_OUT = Path("var") / "swing_pit"
DEFAULT_INDICES = {"sp500": "GSPC.INDX", "sp400": "MID.INDX"}
DEFAULT_PRICE_START = "2015-01-01"
FJA_URL = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
           "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv")
MEMBERSHIP_FIELDS = ["index", "code", "name", "start", "end",
                     "is_active_now", "is_delisted"]


class Refused(SystemExit):
    """A stop with a reason, not a crash."""


# --------------------------------------------------------------------------
# the key, and keeping it out of everything we print
# --------------------------------------------------------------------------

def api_key(env: dict | None = None) -> str:
    env = os.environ if env is None else env
    key = (env.get(ENV_KEY) or "").strip()
    if not key:
        raise Refused(
            f"{ENV_KEY} is not set. In the same PowerShell window, first run:\n"
            f'  $env:{ENV_KEY} = op read "op://Trading/EODHD/api-token"')
    if key.startswith("op://"):
        raise Refused(f"{ENV_KEY} holds an op:// reference, not the key. "
                      "Wrap it in `op read \"...\"` so 1Password resolves it.")
    return key


def scrub(text: str, key: str) -> str:
    if key:
        text = text.replace(key, "***")
        text = text.replace(urllib.parse.quote(key, safe=""), "***")
    return text


# --------------------------------------------------------------------------
# HTTP, injectable so the tests never touch the network
# --------------------------------------------------------------------------

Fetch = Callable[[str, dict], object]


class NotFound(Exception):
    pass


def http_fetch_factory(key: str, pause: float = 0.05,
                       retries: int = 4) -> Fetch:
    def fetch(path: str, params: dict) -> object:
        q = dict(params)
        q["api_token"] = key
        q.setdefault("fmt", "json")
        url = f"{API}/{path.lstrip('/')}?{urllib.parse.urlencode(q)}"
        delay = 2.0
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    body = r.read().decode("utf-8")
                time.sleep(pause)
                return json.loads(body) if body.strip() else None
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise NotFound(path) from None
                if e.code in (401, 403):
                    raise Refused(
                        f"EODHD refused the key for {path} (HTTP {e.code}). "
                        "Check the subscription covers this endpoint.") from None
                if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError(scrub(f"HTTP {e.code} on {path}", key)) from None
            except urllib.error.URLError as e:
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError(scrub(f"network error on {path}: {e.reason}",
                                         key)) from None
        raise RuntimeError(f"gave up on {path}")
    return fetch


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def to_date(v) -> dt.date | None:
    if v in (None, "", "null", "0000-00-00"):
        return None
    return dt.date.fromisoformat(str(v)[:10])


def as_bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes")
    return bool(v)


def records(obj) -> list[dict]:
    """EODHD returns collections either as a list or as {"0": {...}, ...}."""
    if obj is None:
        return []
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict)]
    if isinstance(obj, dict):
        return [r for r in obj.values() if isinstance(r, dict)]
    return []


def eod_symbol(code: str) -> str:
    """EODHD writes class shares with a hyphen: BRK.B -> BRK-B.US."""
    code = code.strip().upper()
    if code.endswith(".US"):
        code = code[:-3]
    return code.replace(".", "-") + ".US"


def file_stem(code: str) -> str:
    return code.strip().upper().replace(".", "-").replace("/", "-")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# membership
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Spell:
    index: str
    code: str
    name: str
    start: dt.date | None
    end: dt.date | None
    is_active_now: bool
    is_delisted: bool

    def covers(self, day: dt.date) -> bool:
        if self.start is not None and day < self.start:
            return False
        if self.end is not None and day > self.end:
            return False
        return True


def norm_code(v) -> str:
    code = str(v or "").strip().upper()
    return code[:-3] if code.endswith(".US") else code


def parse_constituents(index: str, payload: dict) -> list[Spell]:
    if not isinstance(payload, dict):
        raise Refused(f"{index}: constituents response is not an object")
    hist = records(payload.get("HistoricalTickerComponents"))
    if not hist:
        raise Refused(
            f"{index}: no HistoricalTickerComponents in the response. The raw "
            "JSON is saved under raw/ -- the field layout may have changed.")
    out = []
    for r in hist:
        code = norm_code(r.get("Code"))
        if not code:
            continue
        out.append(Spell(index=index, code=code,
                         name=str(r.get("Name") or "").strip(),
                         start=to_date(r.get("StartDate")),
                         end=to_date(r.get("EndDate")),
                         is_active_now=as_bool(r.get("IsActiveNow")),
                         is_delisted=as_bool(r.get("IsDelisted"))))
    # Current members missing from the history block would be survivors the
    # history cannot see; add them as open-ended spells and let the report
    # count them.
    have = {s.code for s in out if s.is_active_now}
    for r in records(payload.get("Components")):
        code = norm_code(r.get("Code"))
        if code and code not in have:
            out.append(Spell(index, code, str(r.get("Name") or ""), None, None,
                             True, False))
    return out


def write_membership(path: Path, spells: Iterable[Spell]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(MEMBERSHIP_FIELDS)
        for s in sorted(spells, key=lambda s: (s.index, s.code,
                                                s.start or dt.date.min)):
            w.writerow([s.index, s.code, s.name,
                        s.start.isoformat() if s.start else "",
                        s.end.isoformat() if s.end else "",
                        int(s.is_active_now), int(s.is_delisted)])
            n += 1
    return n


def read_membership(path: Path) -> list[Spell]:
    if not path.exists():
        raise Refused(f"{path} does not exist. Run the constituents stage first.")
    out = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append(Spell(r["index"], r["code"], r["name"],
                             to_date(r["start"]), to_date(r["end"]),
                             r["is_active_now"] == "1", r["is_delisted"] == "1"))
    return out


def members_on(spells: Iterable[Spell], index: str, day: dt.date) -> set[str]:
    return {s.code for s in spells if s.index == index and s.covers(day)}


# --------------------------------------------------------------------------
# stage 1: constituents
# --------------------------------------------------------------------------

def stage_constituents(fetch: Fetch, out: Path,
                       indices: dict[str, str]) -> list[str]:
    lines = []
    listing = fetch("mp/unicornbay/spglobal/list", {})
    write_json(out / "raw" / "index_list.json", listing)
    ids = {str(r.get("ID") or r.get("Code") or "") for r in records(listing)}
    spells: list[Spell] = []
    for name, idx in indices.items():
        if ids and idx not in ids:
            near = sorted(i for i in ids if "400" in i or "500" in i or
                          "MID" in i.upper() or "GSPC" in i.upper())
            raise Refused(f"{name}: index id {idx!r} is not in EODHD's list. "
                          f"Candidates: {near[:20]}. Pass --index {name}=<ID>.")
        payload = fetch(f"mp/unicornbay/spglobal/comp/{idx}", {})
        write_json(out / "raw" / f"comp_{name}.json", payload)
        got = parse_constituents(name, payload)
        spells.extend(got)
        starts = [s.start for s in got if s.start]
        lines.append(f"{name} ({idx}): {len(got)} spells, "
                     f"{len({s.code for s in got})} tickers, "
                     f"{sum(s.is_active_now for s in got)} current, "
                     f"{sum(s.is_delisted for s in got)} delisted, "
                     f"earliest start {min(starts) if starts else 'none'}")
    n = write_membership(out / "membership.csv", spells)
    lines.append(f"wrote {n} rows to {out / 'membership.csv'}")
    try:
        sym = fetch("exchange-symbol-list/US", {"delisted": 1})
        write_json(out / "raw" / "us_delisted_symbols.json", sym)
        lines.append(f"saved {len(records(sym))} delisted US symbols "
                     "(used by the report to explain missing prices)")
    except (NotFound, RuntimeError) as e:
        lines.append(f"delisted symbol list not saved: {e}")
    return lines


# --------------------------------------------------------------------------
# stage 2: prices
# --------------------------------------------------------------------------

PRICE_FIELDS = ["date", "open", "high", "low", "close", "adjusted_close", "volume"]


def stage_prices(fetch: Fetch, out: Path, start: str, end: str | None = None,
                 refresh: bool = False, limit: int | None = None,
                 log: Callable[[str], None] = print) -> dict:
    spells = read_membership(out / "membership.csv")
    codes = sorted({s.code for s in spells})
    if limit:
        codes = codes[:limit]
    eod_dir = out / "eod"
    eod_dir.mkdir(parents=True, exist_ok=True)
    missing_path = out / "prices_missing.csv"
    missing = {}
    if missing_path.exists() and not refresh:
        with missing_path.open(newline="", encoding="utf-8") as f:
            missing = {r["code"]: r["reason"] for r in csv.DictReader(f)}
    stats = {"tickers": len(codes), "fetched": 0, "skipped": 0, "missing": 0}
    for i, code in enumerate(codes, 1):
        path = eod_dir / f"{file_stem(code)}.csv"
        if (path.exists() or code in missing) and not refresh:
            stats["skipped"] += 1
            continue
        params = {"from": start}
        if end:
            params["to"] = end
        try:
            rows = records(fetch(f"eod/{eod_symbol(code)}", params))
        except NotFound:
            rows, reason = [], "404 not found"
        else:
            reason = "empty response"
        if not rows:
            missing[code] = reason
            stats["missing"] += 1
        else:
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=PRICE_FIELDS,
                                   extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            stats["fetched"] += 1
        if i % 50 == 0:
            log(f"  {i}/{len(codes)}  fetched {stats['fetched']}  "
                f"missing {stats['missing']}  skipped {stats['skipped']}")
        with missing_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["code", "eod_symbol", "reason"])
            for c in sorted(missing):
                w.writerow([c, eod_symbol(c), missing[c]])
    return stats


# --------------------------------------------------------------------------
# stage 3: report (no API calls)
# --------------------------------------------------------------------------

def price_span(path: Path) -> tuple[dt.date, dt.date, int] | None:
    if not path.exists():
        return None
    first = last = None
    n = 0
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = to_date(r.get("date"))
            if d is None:
                continue
            first = d if first is None or d < first else first
            last = d if last is None or d > last else last
            n += 1
    return (first, last, n) if n else None


def classify_spell(s: Spell, span, window: tuple[dt.date, dt.date],
                   slack_days: int = 7) -> str:
    """full / partial / none / outside, for the part of the spell inside the window."""
    lo = max(s.start or window[0], window[0])
    hi = min(s.end or window[1], window[1])
    if lo > hi:
        return "outside"
    if span is None:
        return "none"
    first, last, _ = span
    slack = dt.timedelta(days=slack_days)
    ok_lo = first <= lo + slack
    ok_hi = last >= hi - slack
    return "full" if ok_lo and ok_hi else "partial"


def load_fja(path: Path) -> list[tuple[dt.date, set[str]]]:
    out = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0] == "date":
                continue
            out.append((dt.date.fromisoformat(row[0]),
                        {t.strip().upper() for t in row[1].split(",") if t.strip()}))
    out.sort()
    return out


def fja_on(fja, day: dt.date) -> set[str] | None:
    prior = [s for d, s in fja if d <= day]
    return prior[-1] if prior else None


def sample_dates(start: dt.date, end: dt.date) -> list[dt.date]:
    out, y = [], start.year
    while True:
        for m in (1, 7):
            d = dt.date(y, m, 15)
            if start <= d <= end:
                out.append(d)
        y += 1
        if dt.date(y, 1, 1) > end:
            return out


def stage_report(out: Path, window: tuple[dt.date, dt.date],
                 fja_path: Path | None) -> list[str]:
    spells = read_membership(out / "membership.csv")
    L = [f"G8 point-in-time universe -- window {window[0]} to {window[1]}", ""]

    # --- membership sanity
    L.append("MEMBERS PER INDEX ON SAMPLE DATES (expect ~500 / ~400)")
    indices = sorted({s.index for s in spells})
    dates = sample_dates(*window)
    L.append("  date        " + "  ".join(f"{i:>6}" for i in indices))
    for d in dates:
        L.append(f"  {d}  " + "  ".join(
            f"{len(members_on(spells, i, d)):>6}" for i in indices))
    undated = [s for s in spells if s.start is None]
    if undated:
        L.append(f"  !! {len(undated)} spells have no start date "
                 "(treated as members since before the window)")
    L.append("")

    # --- price coverage
    counts: dict[str, int] = {}
    gaps = []
    for s in spells:
        c = classify_spell(s, price_span(out / "eod" / f"{file_stem(s.code)}.csv"),
                           window)
        counts[c] = counts.get(c, 0) + 1
        if c in ("none", "partial"):
            gaps.append((s, c))
    relevant = sum(v for k, v in counts.items() if k != "outside")
    L.append("PRICE COVERAGE OF EACH MEMBERSHIP SPELL, INSIDE THE WINDOW")
    for k in ("full", "partial", "none", "outside"):
        L.append(f"  {k:<8} {counts.get(k, 0):>5}")
    if relevant:
        L.append(f"  covered in full: {100 * counts.get('full', 0) / relevant:.1f}% "
                 f"of {relevant} spells")
    delisted_gone = [s for s, c in gaps if c == "none" and s.is_delisted]
    L.append(f"  spells with NO prices that belong to delisted names: "
             f"{len(delisted_gone)}  <- these are the survivorship hole")
    for s, c in sorted(gaps, key=lambda g: (g[1], g[0].index, g[0].code))[:60]:
        L.append(f"    {c:<8} {s.index} {s.code:<8} {s.start or '?'} -> "
                 f"{s.end or 'now'}  delisted={int(s.is_delisted)}  {s.name[:40]}")
    if len(gaps) > 60:
        L.append(f"    ... {len(gaps) - 60} more in coverage_gaps.csv")
    with (out / "coverage_gaps.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["coverage"] + MEMBERSHIP_FIELDS)
        for s, c in gaps:
            w.writerow([c, s.index, s.code, s.name, s.start or "", s.end or "",
                        int(s.is_active_now), int(s.is_delisted)])
    L.append("")

    # --- cross-check against the free list
    if fja_path is not None and fja_path.exists() and "sp500" in indices:
        fja = load_fja(fja_path)
        L.append(f"S&P 500 vs the free fja05680 list ({fja_path.name}, "
                 f"last row {fja[-1][0] if fja else 'none'})")
        L.append("  date        eodhd   free  only_eodhd  only_free")
        disagree: dict[str, int] = {}
        for d in dates:
            a, b = members_on(spells, "sp500", d), fja_on(fja, d)
            if b is None:
                continue
            only_a, only_b = sorted(a - b), sorted(b - a)
            for t in only_a + only_b:
                disagree[t] = disagree.get(t, 0) + 1
            L.append(f"  {d}  {len(a):>5}  {len(b):>5}  {len(only_a):>10}  "
                     f"{len(only_b):>9}")
        worst = sorted(disagree.items(), key=lambda kv: -kv[1])[:25]
        L.append("  tickers disagreeing most often (renames show up here too):")
        L.append("    " + ", ".join(f"{t}({n})" for t, n in worst))
        for t in ("BK", "AVB", "CAG", "CPB"):
            sp = [s for s in spells if s.index == "sp500" and s.code == t]
            L.append(f"  check {t}: eodhd spells "
                     + "; ".join(f"{s.start}->{s.end or 'now'}" for s in sp)
                     if sp else f"  check {t}: not in eodhd sp500 history")
    else:
        L.append("S&P 500 cross-check skipped (no free list available)")
    return L


# --------------------------------------------------------------------------
# self-test (offline)
# --------------------------------------------------------------------------

def self_test() -> list[str]:
    import tempfile
    payload = {
        "General": {"Code": "GSPC"},
        "Components": {"0": {"Code": "AAA", "Name": "A"}},
        "HistoricalTickerComponents": {
            "0": {"Code": "AAA", "Name": "A", "StartDate": "2010-01-01",
                  "EndDate": None, "IsActiveNow": 1, "IsDelisted": 0},
            "1": {"Code": "ZZZ", "Name": "Z", "StartDate": "2012-01-01",
                  "EndDate": "2019-06-30", "IsActiveNow": 0, "IsDelisted": 1}}}

    def fake(path, params):
        if path.endswith("list"):
            return [{"ID": "GSPC.INDX"}]
        if "comp/" in path:
            return payload
        if path.startswith("exchange-symbol-list"):
            return [{"Code": "ZZZ"}]
        if path == "eod/AAA.US":
            return [{"date": "2015-01-02", "close": 1},
                    {"date": "2026-09-18", "close": 2}]
        raise NotFound(path)

    with tempfile.TemporaryDirectory() as t:
        out = Path(t)
        stage_constituents(fake, out, {"sp500": "GSPC.INDX"})
        st = stage_prices(fake, out, "2015-01-01", log=lambda m: None)
        rep = stage_report(out, (dt.date(2016, 5, 10), dt.date(2026, 9, 18)), None)
    assert st == {"tickers": 2, "fetched": 1, "skipped": 0, "missing": 1}, st
    hole = [l for l in rep if "survivorship hole" in l]
    assert hole and ": 1  <-" in hole[0], hole
    return ["self-test passed: constituents parsed, prices fetched, the "
            "delisted name with no prices was counted, not dropped"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_indices(items: list[str] | None) -> dict[str, str]:
    idx = dict(DEFAULT_INDICES)
    for it in items or []:
        if "=" not in it:
            raise Refused(f"--index takes name=ID, got {it!r}")
        k, v = it.split("=", 1)
        idx[k.strip()] = v.strip()
    return idx


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("stage", nargs="?",
                   choices=["constituents", "prices", "report", "all"])
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--index", action="append",
                   help="override an index id, e.g. sp400=MID.INDX")
    p.add_argument("--start", default=DEFAULT_PRICE_START,
                   help="first price date to fetch")
    p.add_argument("--refresh", action="store_true",
                   help="re-fetch tickers already on disk")
    p.add_argument("--limit", type=int, help="prices: first N tickers only")
    p.add_argument("--window-start", default="2016-05-10")
    p.add_argument("--window-end", default=None)
    p.add_argument("--fja", type=Path, default=None,
                   help="free S&P 500 list CSV; downloaded to raw/ if omitted")
    p.add_argument("--no-compare", action="store_true")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)

    if a.self_test:
        for line in self_test():
            print(line)
        return 0
    if not a.stage:
        p.error("choose a stage: constituents, prices, report or all")

    out = a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    stages = ["constituents", "prices", "report"] if a.stage == "all" else [a.stage]
    key = api_key() if any(s != "report" for s in stages) else ""
    fetch = http_fetch_factory(key) if key else None
    try:
        for stage in stages:
            print(f"== {stage}")
            if stage == "constituents":
                for line in stage_constituents(fetch, out, parse_indices(a.index)):
                    print(line)
            elif stage == "prices":
                st = stage_prices(fetch, out, a.start, refresh=a.refresh,
                                  limit=a.limit)
                print(f"prices: {st}")
            else:
                w_end = (dt.date.fromisoformat(a.window_end) if a.window_end
                         else dt.date.today())
                fja = None if a.no_compare else (a.fja or out / "raw" / "fja05680_sp500.csv")
                if fja is not None and not fja.exists() and a.fja is None:
                    try:
                        with urllib.request.urlopen(FJA_URL, timeout=60) as r:
                            fja.parent.mkdir(parents=True, exist_ok=True)
                            fja.write_bytes(r.read())
                    except (urllib.error.URLError, OSError) as e:
                        print(f"could not download the free list: {e}")
                        fja = None
                lines = stage_report(out, (dt.date.fromisoformat(a.window_start),
                                           w_end), fja)
                text = "\n".join(lines) + "\n"
                (out / "report.txt").write_text(text, encoding="utf-8")
                print(text)
                print(f"written to {out / 'report.txt'}")
    except RuntimeError as e:
        print(f"STOPPED: {scrub(str(e), key)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
