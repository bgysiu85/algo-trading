#!/usr/bin/env python3
"""Price, then pull, ES/NQ tick trades (aggressor side) for W16 order-flow
work. THIS MODULE CAN SPEND.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.fetch_trades            # estimate, then STOP
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.fetch_trades --confirm  # estimate, then spend

Board W16-0009 subitem 1 (Ben: "Pull 12 months now" -- Databento GLBX.MDP3
order-flow data, Standard plan). Every print in a `trades` record carries
its own aggressor side, which `ohlcv-1m` (bought by `strategy.w16.fetch`)
does not -- this is what unlocks delta, big-trade prints (per-print size,
not per-participant -- that needs MBO) and per-bar volume-at-price. Source:
W16-0009 Notes and `claude/w11_0034_iqcapital_review_RESULT_20260928.md`.

WHY A SEPARATE MODULE FROM strategy.w16.fetch
------------------------------------------------
`fetch.py` buys ONE file per (root, schema) for the whole 2010-06-06..today
range -- fine for `ohlcv-1m`/`ohlcv-1d`, which are small. A year of ES+NQ
tick prints is not, and Databento's Standard plan only carries the LAST 12
MONTHS of L1 (trades/TBBO/MBP-1) besides -- the window rolls forward every
day. So this pulls one file PER DAY: a re-run only prices and buys the days
still missing, the same "billing is on retrieval" discipline `fetch.py` and
`common.databento_fetch` already follow, at day instead of whole-range
granularity.

WHY BOTH ROOTS IN ONE DAILY FILE
-----------------------------------
ES.v.0 and NQ.v.0 trades for the same UTC day are priced and pulled
together (one `get_cost` / `get_range` call, not two) -- half the metadata
round trips of a per-root split. `strategy.w16.readback` (subitem 4) tells
them apart the same way any other multi-symbol Databento file is read: by
the record's own `symbol` / `instrument_id`.

WINDOW
------
Default window is the dataset's own end date, back `WINDOW_DAYS` (365)
days -- override with --start / --end / --window-days for a narrower
re-check. Saturdays (no GLBX session at all) are never even priced. Any
OTHER day priced but reported as having no session to sell (a full holiday
closure) is skipped and listed, not an abort -- see `_is_no_session`; every
other pricing failure still aborts the run.

"TODAY" IS ALWAYS A PARTIAL DAY. The dataset's end is a TIMESTAMP
("2026-09-28 11:10:00+00:00"), not a midnight boundary, and Databento
rejects a query `end` after it (`data_end_after_available_end`) -- the
window's last day naturally asks for the whole day, through the NEXT day's
00:00Z, which is after that timestamp every single run. First seen live,
2026-09-28 (Ben): `pricing failed on 2026-09-28 ... 422
data_end_after_available_end`. `_is_end_after_available` catches exactly
that error and re-prices the offending day capped at the dataset's real
end instead of day+1's midnight; if nothing is left after the cap (the day
just opened and has 0 seconds of data so far), the day is treated as
`no_session` for this run and simply re-picked up next time.

SPENDING GUARDS (same shape as strategy.w16.fetch)
----------------------------------------------------
  * estimate first, always, for every day not already on disk, printed as
    one total before anything downloads;
  * nothing downloads without --confirm;
  * --max-cost (default $50.00, W16-0009's own ceiling: "Price with
    get_cost first; >$50 -> stop and ask Ben") ABORTS;
  * a day already on disk is never re-requested.

It does not read the prints. `strategy.w16.readback` (subitem 4) does that:
per-minute trade volume vs the owned `ohlcv-1m` (>=99% agreement), aggressor
side present, day coverage.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from common.tsmom_data_price import DATASET, require_databento
from common.tsmom_fetch import (_is_symbology_miss, _key, _price, _retry,
                                _scrub, default_archive)
from strategy.w16.fetch import ROOTS, dataset_end

SYMBOLS = tuple(f"{r}.v.0" for r in ROOTS)
SCHEMA = "trades"
STYPE_IN = "continuous"
WINDOW_DAYS = 365              # Standard plan's rolling L1 retention
MAX_COST = 50.00               # W16-0009 Notes: "Price ... >$50 -> stop and ask Ben"
ARCHIVE_SUBDIR = "w16_trades"
BOARD = "W16-0009"
REGISTRATION = "docs/research/REGISTERED_w16_session_baselines.md"
PLAN_TICK = 25


def day_path(root_dir: Path, day: str) -> Path:
    return Path(root_dir) / DATASET / ARCHIVE_SUBDIR / f"{day}.dbn.zst"


def manifest_path(root_dir: Path) -> Path:
    return Path(root_dir) / DATASET / ARCHIVE_SUBDIR / "manifest_w16_trades.json"


def request(day: str, cap: str | None = None) -> dict:
    """The one request shape, in one place, so a test can pin its scope.

    `cap` (an exact 'YYYY-MM-DDTHH:MM:SSZ' timestamp, not a date) clips the
    end to the dataset's real availability instead of day+1's midnight --
    see `_is_end_after_available`. Plain string comparison is safe because
    both sides are always this one zero-padded, second-precision, 'Z'-suffixed
    shape."""
    nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    end = f"{nxt}T00:00:00Z"
    if cap is not None and cap < end:
        end = cap
    return dict(dataset=DATASET, schema=SCHEMA, symbols=list(SYMBOLS),
                stype_in=STYPE_IN, start=f"{day}T00:00:00Z", end=end)


def _parse_ts(v) -> datetime:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _dataset_end_precise(client) -> str:
    """The dataset's actual end TIMESTAMP (not truncated to a date) --
    Databento rejects a query `end` after this, and "today" is always a
    partial day. Fetched lazily, only once actually needed (see `plan`), so
    a run that touches no "today" day never pays for the extra call."""
    try:
        rng = client.metadata.get_dataset_range(dataset=DATASET)
    except Exception as e:                       # noqa: BLE001
        raise SystemExit(f"dataset range lookup failed: {_scrub(e)}")
    v = rng.get("end") or rng.get("end_date")
    if v is None:
        raise SystemExit("dataset range lookup returned no end")
    return _parse_ts(v).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_end_after_available(e: Exception) -> bool:
    """The window's last day asked for the whole day (through the NEXT
    day's midnight) and the dataset's real end is earlier than that --
    "today" is always a partial day. Narrow on purpose, same reasoning as
    `_is_no_session`: every other pricing failure still aborts the run."""
    return "data_end_after_available_end" in str(e)


def trading_days(start: str, end: str) -> list[str]:
    """Every calendar day in [start, end] except Saturday -- GLBX has no
    session at all that day, so it is never even priced. Other closures
    (Christmas, ...) ARE priced; see `_is_no_session`."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    out, d = [], s
    while d <= e:
        if d.weekday() != 5:          # Mon=0 .. Sat=5 .. Sun=6
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def default_window(end: str, window_days: int = WINDOW_DAYS) -> str:
    return (date.fromisoformat(end) - timedelta(days=window_days - 1)).isoformat()


def _is_no_session(e: Exception) -> bool:
    """A full holiday closure, as opposed to a request that is actually
    wrong. Reuses `common.tsmom_fetch`'s own narrow check -- every OTHER
    pricing failure still aborts the run."""
    return _is_symbology_miss(e)


def plan(client, root_dir: Path, days: list[str]):
    """Every day that would actually run, what it costs, and which days
    Databento reports as having nothing to sell (skipped, not an abort)."""
    jobs, have, no_session = [], 0, []
    usd, nbytes = 0.0, 0
    cap = None                    # the dataset's precise end; fetched once, lazily
    for day in days:
        out = day_path(root_dir, day)
        if out.exists():
            have += 1
            continue
        kw = request(day)
        try:
            u, n = _retry(lambda kw=kw: _price(client, kw))
        except Exception as e:                       # noqa: BLE001
            if _is_no_session(e):
                no_session.append(day)
                continue
            if _is_end_after_available(e):
                if cap is None:
                    cap = _dataset_end_precise(client)
                kw = request(day, cap=cap)
                if kw["start"] >= kw["end"]:
                    # The day has opened but the dataset has not caught up
                    # to even one second of it yet -- nothing to buy THIS
                    # run; the next run (dataset end has moved on) picks it
                    # straight back up, same as any other missing day.
                    no_session.append(day)
                    continue
                try:
                    u, n = _retry(lambda kw=kw: _price(client, kw))
                except Exception as e2:               # noqa: BLE001
                    raise SystemExit(
                        f"pricing failed on {day} (capped at the dataset's "
                        f"real end {cap}) -- nothing downloaded: {_scrub(e2)}")
            else:
                raise SystemExit(
                    f"pricing failed on {day} -- nothing downloaded: {_scrub(e)}")
        jobs.append((day, out, kw))
        usd += u
        nbytes += n
    return jobs, usd, nbytes, have, no_session


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser(
        description="Price, then pull, ES+NQ trades (order flow) for "
                    "W16-0009. CAN SPEND.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--start", help="override (default: --end minus --window-days)")
    ap.add_argument("--end", help="override (default: the dataset's end)")
    ap.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    ap.add_argument("--max-cost", type=float, default=MAX_COST)
    ap.add_argument("--confirm", action="store_true",
                    help="actually download. Without it, this only estimates.")
    a = ap.parse_args(argv)

    root_dir = a.archive or default_archive()
    print(f"dataset   {DATASET}\nschema    {SCHEMA}\n"
          f"symbols   {' '.join(SYMBOLS)} ({STYPE_IN})\n"
          f"target    {Path(root_dir) / DATASET / ARCHIVE_SUBDIR}/")

    if client is None:
        databento = require_databento()
        client = databento.Historical(_key())

    end = a.end or dataset_end(client)
    start = a.start or default_window(end, a.window_days)
    print(f"range     {start} .. {end}  ({a.window_days}-day rolling window)\n")

    days = trading_days(start, end)
    jobs, usd, nbytes, have, no_session = plan(client, root_dir, days)
    print(f"{len(jobs)} day(s) to price/pull, {have} already on disk and "
          f"skipped, {len(no_session)} day(s) with no session reported by "
          "Databento")
    if no_session:
        print(f"  no session: {', '.join(no_session)}")
    print(f"estimate  ${usd:.2f}   {nbytes:,} bytes ({nbytes / 2**20:.1f} MiB)\n")

    if not jobs:
        print("Nothing to do. Nothing charged.")
        return 0

    if usd > a.max_cost:
        print(f"ABORT: ${usd:.2f} exceeds --max-cost ${a.max_cost:.2f}.")
        print("W16-0009: \"Price with get_cost first; >$50 -> stop and ask "
              "Ben\". An estimate this large usually means the window")
        print("widened (a bad --start/--end/--window-days), not that ES/NQ "
              "tick prints got expensive. Nothing downloaded.")
        return 2

    if not a.confirm:
        print("ESTIMATE ONLY. Nothing downloaded, nothing charged.")
        print("Post this total on W16-0009 subitem 2 and re-run with "
              "--confirm to spend it.")
        return 0

    print(f"SPENDING ${usd:.2f}. Downloading {len(jobs)} day(s) -- this can "
          "take a while.\n")
    done, failed = [], []
    for i, (day, out, kw) in enumerate(jobs, start=1):
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        try:
            data = _retry(lambda kw=kw: client.timeseries.get_range(**kw))
            data.to_file(tmp)
        except Exception as e:                       # noqa: BLE001
            failed.append((day, _scrub(e)[:80]))
            if tmp.exists():
                tmp.unlink()
            continue
        # Only a finished download takes the real name, so an interrupted
        # pull can never be mistaken for a complete one by the "already on
        # disk" check (strategy.w16.fetch's own guard, same reasoning here).
        tmp.replace(out)
        done.append((day, out))
        if PLAN_TICK and (i % PLAN_TICK == 0 or i == len(jobs)):
            print(f"  {i}/{len(jobs)}  {day} -> {out}")

    if failed:
        print(f"\n{len(failed)} day(s) FAILED, nothing kept for them:")
        for d, msg in failed:
            print(f"  {d}  {msg}")

    rec = {
        "pulled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset": DATASET, "schema": SCHEMA, "symbols": list(SYMBOLS),
        "stype_in": STYPE_IN, "start": start, "end": end,
        "window_days": a.window_days,
        "estimated_usd": round(usd, 4), "estimated_bytes": nbytes,
        "no_session": no_session,
        "files_pulled": [str(p) for _, p in done],
        "files_failed": [d for d, _ in failed],
        "registration": REGISTRATION, "board": BOARD,
    }
    mp = manifest_path(root_dir)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(f"\n{len(done)}/{len(jobs)} succeeded.\nmanifest  {mp}")

    if failed:
        print("INCOMPLETE. Re-run: finished days are on disk and free to "
              "skip.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
