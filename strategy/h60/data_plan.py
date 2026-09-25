#!/usr/bin/env python3
"""H60 data: price, then pull, Nasdaq ITCH 1-minute bars (09:30-16:00 ET) for
the point-in-time S&P 500 + 400 universe. W14-0002, `REGISTERED_h60_v0.md` §6.

    python -m strategy.h60.data_plan                         # price only (free)
    python -m strategy.h60.data_plan --pull                  # dry run of the pull
    python -m strategy.h60.data_plan --pull --max-cost 0 --confirm   # download

WHAT "PRICE" DOES, AND WHY IT IS PER YEAR
-----------------------------------------
Every call it makes is a free metadata call: the dataset's date range, the cost
and billable size of a year of `ohlcv-1m` and of `ohlcv-1h` for that year's
members, and the symbols Databento cannot resolve. A day-by-day plan (what
`common.databento_fetch` does) is ~4,000 round trips for this universe; a year
at a time is about fifty.

A year's cost can only be asked for WHOLE days, and the study wants 09:30-16:00.
So one sample day per year is priced both ways and the ratio scales the year.
The full-day figure is printed too: it is the ceiling, and it is what the
registration's fallback threshold (§2.2: $50 or 25 GB) is read against if the
ratio looks wrong.

WHERE THE BARS GO -- NOT THE EXISTING ARCHIVE
---------------------------------------------
`common.databento_fetch` keeps one file per dataset/schema/day under the
archive root, and a fetch scoped to a new list REPLACES that day's file.
`<archive>/XNAS.ITCH/ohlcv-1m/` is the pre-market archive every small-cap
result stands on. This module writes to `<archive>/H60/XNAS.ITCH/ohlcv-1m-rth/`
and refuses an archive root that is the shared one itself.

THE KEY
-------
DATABENTO_API_KEY only, resolved and scrubbed by `common.databento_fetch`
exactly as every other Databento tool here does. Never a flag, never printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from common.report_io import emit
from strategy.swing.pit_universe import Spell, read_membership

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc

DATASET = "XNAS.ITCH"
SCHEMA_1M = "ohlcv-1m"
SCHEMA_1H = "ohlcv-1h"
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
RTH_DIR = "ohlcv-1m-rth"          # never "ohlcv-1m": that name is the shared archive's
H60_SUBDIR = "H60"
DEFAULT_START = dt.date(2018, 5, 1)   # XNAS.ITCH's first date; the probe confirms
MAX_SYMBOLS_PER_REQUEST = 2000        # Databento's limit per request

# REGISTERED_h60_v0.md §2.2: above either, the grid falls back (amendment B).
FALLBACK_USD = 50.0
FALLBACK_BYTES = 25e9

MEMBERSHIP = Path("var/swing_pit/membership.csv")
SUSPECTS = Path("var/swing_pit/suspects.csv")
REPORT = Path("var/reports/h60_data_plan.txt")

_OLD = re.compile(r"_OLD\d*$")


class Refused(SystemExit):
    """A refusal with a reason, raised before anything is spent."""


# --------------------------------------------------------------------------
# universe
# --------------------------------------------------------------------------

def to_raw_symbol(code: str) -> str | None:
    """EODHD code -> Databento raw symbol. REGISTERED_h60_v0.md §2.1.

    `_OLD` / `_OLD1` / `_OLD2` mark a ticker EODHD has since reassigned; the
    old ticker is what traded then. `-` is EODHD's class separator (BRK-B);
    Nasdaq's is `.`. `--` is EODHD's placeholder for a temporary security.
    Renames and ticker reuse are NOT solved here -- §5.1 catches them.
    """
    c = (code or "").strip().upper()
    if not c or set(c) == {"-"}:
        return None
    return _OLD.sub("", c).replace("-", ".")


def _spell_key(index: str, code: str, start: str, end: str) -> tuple:
    return (index.strip(), code.strip(), (start or "").strip(), (end or "").strip())


def load_universe(membership: Path = MEMBERSHIP,
                  suspects: Path = SUSPECTS) -> list[Spell]:
    """The membership spells, minus the 35 G8-residual suspects Ben accepted
    on W07-0002. A spell is matched on (index, code, start, end), so a code
    with one bad spell keeps its good ones."""
    import csv
    spells = read_membership(Path(membership))
    if not Path(suspects).exists():
        raise Refused(f"{suspects} does not exist. The G8 residual must be "
                      "excluded (REGISTERED_h60_v0.md §2.1); refusing to price "
                      "a universe that still contains it.")
    with Path(suspects).open(newline="", encoding="utf-8") as f:
        bad = {_spell_key(r["index"], r["code"], r["start"], r["end"])
               for r in csv.DictReader(f)}

    def key(s: Spell) -> tuple:
        return _spell_key(s.index, s.code,
                          s.start.isoformat() if s.start else "",
                          s.end.isoformat() if s.end else "")

    kept = [s for s in spells if key(s) not in bad]
    dropped = len(spells) - len(kept)
    if dropped != len(bad):
        raise Refused(f"{len(bad)} suspect spells listed but {dropped} matched "
                      "the membership file -- the two files are not from the "
                      "same run.")
    return kept


def symbols_on(spells: list[Spell], day: dt.date) -> list[str]:
    """Raw symbols eligible on `day` (the hindsight guard is Spell.covers)."""
    out = {to_raw_symbol(s.code) for s in spells if s.covers(day)}
    out.discard(None)
    return sorted(out)


def symbols_between(spells: list[Spell], a: dt.date, b: dt.date) -> list[str]:
    """Raw symbols with a spell overlapping [a, b]."""
    out = set()
    for s in spells:
        if s.start is not None and s.start > b:
            continue
        if s.end is not None and s.end < a:
            continue
        r = to_raw_symbol(s.code)
        if r:
            out.add(r)
    return sorted(out)


def weekdays(a: dt.date, b: dt.date) -> list[dt.date]:
    """Candidate sessions in [a, b]. Exchange holidays are asked for and come
    back empty; the file is kept so a re-run does not ask again."""
    n = (b - a).days + 1
    return [a + dt.timedelta(days=i) for i in range(n)
            if (a + dt.timedelta(days=i)).weekday() < 5]


def rth_bounds(day: dt.date) -> tuple[str, str]:
    """[09:30, 16:00) ET on `day`, as UTC ISO strings. ET, converted here, so a
    DST week is never an hour out."""
    def z(t: dt.time) -> str:
        return (dt.datetime.combine(day, t, tzinfo=ET).astimezone(UTC)
                .strftime("%Y-%m-%dT%H:%M:%S"))
    return z(RTH_OPEN), z(RTH_CLOSE)


def chunks(xs: list[str], n: int = MAX_SYMBOLS_PER_REQUEST) -> list[list[str]]:
    return [xs[i:i + n] for i in range(0, len(xs), n)] or [[]]


# --------------------------------------------------------------------------
# pricing -- metadata calls only
# --------------------------------------------------------------------------

def dataset_range(client, dataset: str) -> tuple[dt.date, dt.date]:
    """(first, last) date the account can see. Newer clients return
    {'start': ..., 'end': ...}; older ones {'start_date', 'end_date'}."""
    r = client.metadata.get_dataset_range(dataset=dataset)
    a = r.get("start") or r.get("start_date")
    b = r.get("end") or r.get("end_date")
    if not a or not b:
        raise Refused(f"{dataset}: no date range returned ({r!r}). The account "
                      "may not be entitled to it; run common.databento_probe.")
    return dt.date.fromisoformat(str(a)[:10]), dt.date.fromisoformat(str(b)[:10])


def _ask(client, dataset, schema, symbols, start, end) -> tuple[float, int]:
    usd, nbytes = 0.0, 0
    for part in chunks(symbols):
        if not part:
            continue
        kw = dict(dataset=dataset, schema=schema, symbols=part,
                  stype_in="raw_symbol", start=start, end=end)
        usd += float(client.metadata.get_cost(**kw))
        nbytes += int(client.metadata.get_billable_size(**kw))
    return usd, nbytes


def unresolved(client, dataset, symbols, a: dt.date, b: dt.date) -> list[str]:
    out: list[str] = []
    for part in chunks(symbols):
        if not part:
            continue
        r = client.symbology.resolve(dataset=dataset, symbols=part,
                                     stype_in="raw_symbol",
                                     stype_out="instrument_id",
                                     start_date=a.isoformat(),
                                     end_date=(b + dt.timedelta(days=1)).isoformat())
        out += list(r.get("not_found") or [])
    return sorted(set(out))


def sample_day(a: dt.date, b: dt.date) -> dt.date:
    """A mid-period Wednesday: an ordinary session, not a Monday or a Friday."""
    mid = a + (b - a) / 2
    d = mid
    while d.weekday() != 2:
        d += dt.timedelta(days=1)
    if d > b:
        d = mid
        while d.weekday() != 2 and d >= a:
            d -= dt.timedelta(days=1)
    return d


@dataclass
class YearPlan:
    year: int
    first: dt.date
    last: dt.date
    symbols: int
    not_found: list[str]
    full_usd: float
    full_bytes: int
    rth_share: float
    h1_usd: float
    h1_bytes: int

    @property
    def rth_usd(self) -> float:
        return self.full_usd * self.rth_share

    @property
    def rth_bytes(self) -> float:
        return self.full_bytes * self.rth_share


def plan_year(client, dataset, spells, a: dt.date, b: dt.date) -> YearPlan:
    syms = symbols_between(spells, a, b)
    end = (b + dt.timedelta(days=1)).isoformat()
    full_usd, full_b = _ask(client, dataset, SCHEMA_1M, syms, a.isoformat(), end)
    h1_usd, h1_b = _ask(client, dataset, SCHEMA_1H, syms, a.isoformat(), end)
    d = sample_day(a, b)
    day_syms = symbols_on(spells, d)
    _u, day_full = _ask(client, dataset, SCHEMA_1M, day_syms, d.isoformat(),
                        (d + dt.timedelta(days=1)).isoformat())
    s, e = rth_bounds(d)
    _u, day_rth = _ask(client, dataset, SCHEMA_1M, day_syms, s, e)
    share = (day_rth / day_full) if day_full else 1.0
    return YearPlan(a.year, a, b, len(syms), unresolved(client, dataset, syms, a, b),
                    full_usd, full_b, min(max(share, 0.0), 1.0), h1_usd, h1_b)


def plan_all(client, dataset, spells, start: dt.date, end: dt.date) -> list[YearPlan]:
    out = []
    for y in range(start.year, end.year + 1):
        a = max(start, dt.date(y, 1, 1))
        b = min(end, dt.date(y, 12, 31))
        if a > b:
            continue
        print(f"  pricing {y} ...", flush=True)
        out.append(plan_year(client, dataset, spells, a, b))
    return out


def grid_verdict(plans: list[YearPlan]) -> str:
    usd = sum(p.rth_usd for p in plans)
    nb = sum(p.rth_bytes for p in plans)
    if usd > FALLBACK_USD or nb > FALLBACK_BYTES:
        return ("FALLBACK -- above $%.0f or %.0f GB: REGISTERED_h60_v0.md §2.2 "
                "amendment B applies (09:30-10:00 from 1-minute + clock-hour "
                "bars 10:00-16:00 from ohlcv-1h). Record it before any bar is "
                "read." % (FALLBACK_USD, FALLBACK_BYTES / 1e9))
    return ("PRIMARY -- 09:30-aligned 60-minute bars built from the 1-minute "
            "pull, as registered (§2.2).")


def gb(n: float) -> str:
    return f"{n / 1e9:,.2f}"


def report(dataset: str, rng: tuple[dt.date, dt.date], start: dt.date,
           end: dt.date, plans: list[YearPlan], n_spells: int) -> str:
    L = [f"H60 DATA PLAN  {dataset}  {start} -> {end}", "",
         f"dataset range on this account : {rng[0]} -> {rng[1]}",
         f"membership spells (suspects removed) : {n_spells}", "",
         "Cost and billable size, per year. 'RTH est.' = the whole-day 1-minute "
         "figure x the 09:30-16:00 share measured on one sample Wednesday.", "",
         f"{'year':<5} {'syms':>5} {'unres':>5} {'1m day GB':>10} {'1m day $':>10} "
         f"{'RTH share':>9} {'RTH est GB':>10} {'RTH est $':>10} "
         f"{'1h GB':>8} {'1h $':>9}"]
    for p in plans:
        L.append(f"{p.year:<5} {p.symbols:>5} {len(p.not_found):>5} "
                 f"{gb(p.full_bytes):>10} {p.full_usd:>10,.2f} "
                 f"{p.rth_share:>9.3f} {gb(p.rth_bytes):>10} {p.rth_usd:>10,.2f} "
                 f"{gb(p.h1_bytes):>8} {p.h1_usd:>9,.2f}")
    L.append(f"{'TOTAL':<5} {'':>5} {'':>5} "
             f"{gb(sum(p.full_bytes for p in plans)):>10} "
             f"{sum(p.full_usd for p in plans):>10,.2f} {'':>9} "
             f"{gb(sum(p.rth_bytes for p in plans)):>10} "
             f"{sum(p.rth_usd for p in plans):>10,.2f} "
             f"{gb(sum(p.h1_bytes for p in plans)):>8} "
             f"{sum(p.h1_usd for p in plans):>9,.2f}")
    L += ["", "GRID: " + grid_verdict(plans), "",
          "Symbols Databento could not resolve (by year) -- mostly renamed or "
          "delisted tickers; §5.1 of the registration decides what is excluded:"]
    for p in plans:
        names = ", ".join(p.not_found[:25]) + (" ..." if len(p.not_found) > 25 else "")
        L.append(f"  {p.year}: {len(p.not_found)}  {names}")
    L += ["", "Nothing has been downloaded. The pull is "
          "`python -m strategy.h60.data_plan --pull --max-cost <USD> --confirm`."]
    return "\n".join(L)


# --------------------------------------------------------------------------
# pulling
# --------------------------------------------------------------------------

def rth_root(h60_root: Path, dataset: str = DATASET) -> Path:
    """`h60_root` is already the H60 archive root -- e.g. guard_archive()'s
    return value, or run.py's archive_root(). It is NOT the shared Databento
    archive: --archive on this CLI and on strategy.h60.run both document
    themselves as taking the H60 root, and every real caller (main()'s pull,
    run.py's --build-cache) already has that root in hand by the time it
    needs the RTH directory. Appending H60_SUBDIR here on top of that would
    double it to <h60_root>/H60/<dataset>/<rth dir> -- exactly the defect
    W14-0004 hit (2192 real sessions were pulled to that doubled path before
    this was caught; see git history for the one-time move that fixed it)."""
    return Path(h60_root) / dataset / RTH_DIR


def guard_archive(archive: Path, shared: Path | None) -> Path:
    """Refuse the shared archive root itself. The H60 files go one level down
    (`H60/`), under a schema folder no other tool writes (`ohlcv-1m-rth`)."""
    a = Path(archive).resolve()
    if shared is not None and a == Path(shared).resolve():
        raise Refused(
            f"--archive {archive} is the shared Databento archive root. Pass "
            f"the H60 root instead, e.g. {Path(shared) / H60_SUBDIR}. "
            "REGISTERED_h60_v0.md §6.3.")
    if a.name.upper() == "XNAS.ITCH" or "ohlcv-1m" == a.name:
        raise Refused(f"--archive {archive} points inside a dataset folder. "
                      "Pass the H60 root.")
    return a


def pull(client, dataset: str, spells: list[Spell], days: list[dt.date],
         root: Path, *, sleep: float = 0.0) -> dict:
    """One request per session, 09:30-16:00 ET, that session's members only.
    Skips a day already on disk; writes to .partial and renames on success, so
    an interrupted run never leaves a truncated file that a re-run would skip."""
    out_dir = rth_root(root, dataset)
    out_dir.mkdir(parents=True, exist_ok=True)
    man_path = out_dir / "manifest.json"
    manifest = (json.loads(man_path.read_text(encoding="utf-8"))
                if man_path.exists() else {})
    done = skipped = failed = 0
    t0 = time.time()
    todo = [d for d in days if not (out_dir / f"{d}.dbn.zst").exists()]
    skipped = len(days) - len(todo)
    for i, d in enumerate(todo, start=1):
        syms = symbols_on(spells, d)
        if not syms:
            continue
        out = out_dir / f"{d}.dbn.zst"
        tmp = out.with_suffix(".partial")
        s, e = rth_bounds(d)
        try:
            if len(syms) > MAX_SYMBOLS_PER_REQUEST:
                raise Refused(f"{d}: {len(syms)} symbols exceeds one request")
            client.timeseries.get_range(dataset=dataset, schema=SCHEMA_1M,
                                        symbols=syms, stype_in="raw_symbol",
                                        start=s, end=e, path=str(tmp))
        except Refused:
            raise
        except Exception as ex:  # noqa: BLE001
            from common.databento_fetch import _scrub
            print(f"  {d} FAILED: {_scrub(ex)}", flush=True)
            tmp.unlink(missing_ok=True)
            failed += 1
            continue
        tmp.replace(out)
        manifest[str(d)] = {"symbols": len(syms), "bytes": out.stat().st_size,
                            "start": s, "end": e}
        done += 1
        if i % 20 == 0 or i == len(todo):
            man_path.write_text(json.dumps(manifest, indent=1, sort_keys=True),
                                encoding="utf-8")
            el = time.time() - t0
            print(f"  {i:>5}/{len(todo)}  {d}  {el/60:5.1f} min, "
                  f"~{el / i * (len(todo) - i) / 60:.0f} min left", flush=True)
        if sleep:
            time.sleep(sleep)
    man_path.write_text(json.dumps(manifest, indent=1, sort_keys=True),
                        encoding="utf-8")
    return {"written": done, "skipped": skipped, "failed": failed,
            "dir": str(out_dir)}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    from common.databento_fetch import _key, default_archive, require_databento

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--start", help="first session (default: the dataset's "
                    "first date, or 2018-05-01)")
    ap.add_argument("--end", help="last session (default: the dataset's last "
                    "complete date)")
    ap.add_argument("--membership", default=str(MEMBERSHIP))
    ap.add_argument("--suspects", default=str(SUSPECTS))
    ap.add_argument("--report", default=str(REPORT))
    ap.add_argument("--pull", action="store_true",
                    help="download after pricing (still needs --confirm)")
    ap.add_argument("--archive", help="H60 archive root (default: "
                    "<shared Databento archive>/H60)")
    ap.add_argument("--max-cost", type=float, default=0.0,
                    help="abort the pull if the RTH estimate exceeds this USD "
                         "(default 0: free only)")
    ap.add_argument("--confirm", action="store_true",
                    help="actually download; without it the pull is a dry run")
    a = ap.parse_args(argv)

    db = require_databento()
    spells = load_universe(Path(a.membership), Path(a.suspects))
    client = db.Historical(_key())
    rng = dataset_range(client, a.dataset)
    start = dt.date.fromisoformat(a.start) if a.start else max(rng[0], DEFAULT_START)
    end = dt.date.fromisoformat(a.end) if a.end else rng[1] - dt.timedelta(days=1)
    if start > end:
        raise Refused(f"--start {start} is after --end {end}")

    print(f"{a.dataset}: pricing {start} -> {end} for {len(spells)} spells "
          "(metadata calls only, free)\n", flush=True)
    plans = plan_all(client, a.dataset, spells, start, end)
    emit(report(a.dataset, rng, start, end, plans, len(spells)), a.report,
         header="strategy.h60.data_plan")

    if not a.pull:
        return 0
    shared = Path(default_archive())
    root = guard_archive(Path(a.archive) if a.archive else shared / H60_SUBDIR,
                         shared)
    usd = sum(p.rth_usd for p in plans)
    if usd > a.max_cost:
        raise Refused(f"\nABORTED: the RTH pull is estimated at ${usd:,.2f}, "
                      f"above --max-cost ${a.max_cost:,.2f}. Nothing was "
                      "downloaded. Raise the limit deliberately if Ben has "
                      "approved the spend.")
    days = weekdays(start, end)
    print(f"\nPULL {len(days)} weekdays into {rth_root(root, a.dataset)}")
    if not a.confirm:
        print("Dry run. Re-run with --confirm to download.")
        return 0
    res = pull(client, a.dataset, spells, days, root)
    print(f"\nwritten {res['written']}, already on disk {res['skipped']}, "
          f"failed {res['failed']}  ->  {res['dir']}")
    if res["failed"]:
        print("Re-run the same command: finished days are skipped, failed "
              "days are retried.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
