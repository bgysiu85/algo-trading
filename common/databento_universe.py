#!/usr/bin/env python3
"""Pull the WHOLE US equity universe at daily resolution, in monthly chunks.

    $env:DATABENTO_API_KEY = "..."
    python -m common.databento_universe                        # estimate only
    python -m common.databento_universe --confirm              # download
    python -m common.databento_universe --start 2018-05-01 --dataset XNAS.ITCH

WHY DAILY FIRST
---------------
The instinct is to pull minute bars for everything and backtest it. Eight years
x ~11,000 symbols is on the order of 40 million symbol-days; at even 10ms per
session that is weeks of CPU, and the data is hundreds of GB.

It is also the wrong shape. The strategies here do not trade 11,000 names -- a
screen picks 20-60 a day and they trade those. So the cheap step is to pull ONE
BAR PER SYMBOL PER DAY (about 56 bytes), reconstruct the screen from it, and
then pull minute bars only for the few thousand symbol-days that survive. That
is roughly a thousandfold reduction in both data and compute.

And it is more correct. PROGRAM_INDEX section 4 and
claude/session_aware_screening.md section 3 both record the same gap: every
backtest in this project so far was HANDED its universe from a hindsight pair
list, and the screener was never simulated. This is the file that changes that.

CHUNKED BY MONTH, AND WHY
-------------------------
One request for 3.4 years of ALL_SYMBOLS returns a single enormous file that
cannot be resumed, cannot be partially re-fetched when one month is degraded,
and holds the whole job hostage to one network error. Monthly chunks are
resumable by construction (the skip-if-present guard works per file), and a
degraded month can be re-pulled alone.

Chunks never overlap. common/dbn_io.daily_frame() warns loudly on duplicate
symbol-date rows precisely because an overlapping chunking scheme would double
volume and silently corrupt every relative-volume figure downstream.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import json

from common.databento_fetch import (_key, _scrub, conditions, write_manifest,
                                    default_archive, require_databento)
from common.databento_probe import day_bounds
from common.dbn_io import symbology_path

# EQUS.MINI reaches back to 2023-03-28 and is a blended tape rather than one
# venue's book. The 2018 datasets are individual venue feeds and would have to
# be unioned by hand -- correct consolidated OHLC across ten publishers is a
# real piece of work, and getting it wrong yields plausible wrong bars rather
# than an error. Start here; treat the deep history as a later regime test.
ET = ZoneInfo("America/New_York")
DEFAULT_DATASET = "EQUS.MINI"
DEFAULT_START = "2023-03-28"


def month_chunks(start: str, end: str) -> list[tuple[str, str, str]]:
    """[(label, start, end_exclusive)] one per calendar month, non-overlapping."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    out, cur = [], date(s.year, s.month, 1)
    while cur < e:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        lo, hi = max(cur, s), min(nxt, e)
        if lo < hi:
            out.append((f"{cur:%Y-%m}", lo.isoformat(), hi.isoformat()))
        cur = nxt
    return out


def day_chunks(start: str, end: str, window: str) -> list[tuple[str, str, str]]:
    """[(label, start, end_exclusive)] one per WEEKDAY, covering `window` in ET.

    Month chunks cannot express a time of day: a request from 04:00 on the 1st
    to 09:30 on the 31st spans everything in between, which for ohlcv-1m is the
    whole 24-hour tape and many times the data the screener simulation needs.

    THE LABEL CARRIES THE WINDOW, and that is not cosmetic. Chunks are skipped
    when the file already exists, so a later pull with a different window would
    otherwise silently reuse bars covering different hours -- a corruption that
    produces a plausible screen rather than an error.

    Weekends are dropped because they are empty and every chunk costs a metadata
    round trip. Holidays are NOT dropped here: they cannot be known from the
    calendar alone, and they fall out for free as a zero billable size, which
    the caller already asks for.
    """
    tag = window.replace(":", "").replace("-", "_")
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    out, cur = [], s
    while cur < e:
        if cur.weekday() < 5:
            lo, hi = day_bounds(cur.isoformat(), window)
            out.append((f"{cur:%Y-%m-%d}_{tag}", lo, hi))
        cur += timedelta(days=1)
    return out


def chunk_path(root: Path, dataset: str, schema: str, label: str) -> Path:
    return root / dataset / schema / f"{label}.dbn.zst"


def chunk_last_bar(path: Path) -> str | None:
    """The ET date of the last bar in a chunk, or None if it cannot be read.

    None on any failure, deliberately: this decides whether to RE-BUY a chunk,
    and an unreadable file must not be re-purchased on the strength of a
    parsing error.
    """
    try:
        from common.dbn_io import read_dbn
        df = read_dbn(path)
        if df.empty:
            return None
        return str(df.index.max().tz_convert(ET).date())
    except Exception:                                       # noqa: BLE001
        return None


def chunk_ends_before(path: Path, want_end: str) -> bool:
    """Is this chunk short of the window it claims to cover?

    A PARTIAL CHUNK IS NOT A PRESENT CHUNK. Month chunks fetched mid-month are
    frozen at the day they were pulled, and a skip-if-present guard then
    preserves that truncation forever: every later run reports success while
    the data stops short of where it should.

    That is not hypothetical. `XNAS.BASIC/ohlcv-1d/2026-09.dbn.zst` was pulled
    on the 5th, held four sessions, and was skipped by every run afterwards.
    `screen_sim` then dropped four sessions for having no prior REGULAR close
    while the minute slices for exactly those sessions sat on disk, and the
    check that needed them reported "outside the archive window".

    The comparison allows two days of slack, because the true last session
    before `want_end` depends on market holidays this function cannot know. A
    chunk inside that slack is treated as complete; the cost of being wrong is
    one re-priced chunk, which the estimate gate then shows before anything is
    bought.
    """
    last = chunk_last_bar(path)
    if last is None:
        return False
    want = date.fromisoformat(want_end[:10])
    return (want - date.fromisoformat(last)).days > 2


def save_symbology(client, path: Path) -> bool:
    """Resolve instrument_id -> ticker for one chunk and archive it beside it.

    An ALL_SYMBOLS pull embeds no symbol mapping -- nothing was named in the
    request, so there is nothing to embed. Without this the bars are keyed by an
    integer that means nothing outside one dataset, and to_df(map_symbols=True)
    hands back symbol=None for every row WITHOUT failing. That produced a
    screen report reading "864 symbol-days, 0 distinct symbols" and exit 0.

    Resolved once here and written to disk, so every later analysis is offline
    and reproducible. The mapping is part of the archive, not a runtime lookup:
    instrument ids are reused over time, and a resolution done next year would
    not necessarily answer the same question as one done today.
    """
    db = require_databento()

    out = symbology_path(path)
    if out.exists():
        return False
    store = db.DBNStore.from_file(str(path))
    js = store.request_symbology(client)
    out.write_text(json.dumps(js), encoding="utf-8")
    return True


def clamp_to_dataset(client, dataset: str, start: str, end: str):
    """Trim the requested window to what the dataset actually holds.

    Without this the default --end (today) fails on EVERY run: historical data
    lands T+1, so "today" is always past the available end and the final chunk
    dies with 422 data_end_after_available_end. That is a whole month silently
    missing from an otherwise successful pull -- the run reports 42 of 43
    chunks written and looks fine.

    Clamping is reported, never silent. A window that was quietly shortened is
    how a backtest ends up with a coverage hole nobody put in the notes.

    THE END IT RETURNS IS EXCLUSIVE, because that is what both chunkers take:
    `day_chunks` and `month_chunks` both walk `while cur < e`. The first
    version clamped to `avail_end` itself, which is the last date that HAS
    data -- so asking for the newest available session produced start == end,
    ZERO chunks, and a report reading "to download 0 / $0.0000" that is
    indistinguishable from "everything is already on disk". The dataset's most
    recent day was unreachable and the tool said nothing.

    Over-running by a day is the safe direction and that is why it is chosen:
    a day past the end costs one free metadata call and falls out as `empty
    (holiday/no data)`, which the caller already handles. A day short is a
    silent hole.
    """
    notes: list[str] = []
    try:
        r = client.metadata.get_dataset_range(dataset)
    except Exception as e:  # noqa: BLE001
        notes.append(f"dataset range lookup failed, using dates as given: {_scrub(e)}")
        return start, end, notes

    avail_start = str(r.get("start", r.get("start_date", "")))[:10]
    avail_end = str(r.get("end", r.get("end_date", "")))[:10]

    if avail_start and start < avail_start:
        notes.append(f"start {start} is before {dataset} begins -> {avail_start}")
        start = avail_start
    if avail_end and end > avail_end:
        # +1 day: `end` is exclusive to the chunkers, and avail_end is the last
        # day WITH data. Clamping to avail_end itself drops it.
        nxt = (date.fromisoformat(avail_end) + timedelta(days=1)).isoformat()
        notes.append(f"end {end} is after {dataset} ends "
                     f"({avail_end}) -> {nxt} exclusive")
        end = nxt
    return start, end, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull the full universe, daily bars")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--schema", default="ohlcv-1d")
    ap.add_argument("--window", default=None,
                    help="HH:MM-HH:MM in ET, e.g. 04:00-09:30. Switches "
                         "chunking from monthly to per-weekday and pulls only "
                         "that slice of each day -- what the screener "
                         "simulation needs. Without it a minute schema would "
                         "pull the whole 24-hour tape.")
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--archive", default=str(default_archive()),
                    help="archive root (default: %(default)s)")
    ap.add_argument("--refresh-partial", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="re-fetch a chunk on disk whose last bar falls short "
                         "of the window it claims to cover. On by default: a "
                         "month chunk pulled mid-month is frozen there, and "
                         "skip-if-present hides it forever.")
    ap.add_argument("--max-cost", type=float, default=5.00)
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--resymbolize", action="store_true",
                    help="fetch and archive the symbology for chunks already "
                         "on disk, without re-downloading any bars")
    a = ap.parse_args(argv)

    db = require_databento()

    root = Path(a.archive)
    client_probe = db.Historical(_key())

    if a.resymbolize:
        d = root / a.dataset / a.schema
        files = sorted(d.glob("*.dbn.zst"))
        if not files:
            sys.exit(f"no chunks in {d}/")
        done = skipped = failed = 0
        for f in files:
            try:
                if save_symbology(client_probe, f):
                    done += 1
                    print(f"  {f.name}  -> {symbology_path(f).name}")
                else:
                    skipped += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  {f.name}  FAILED: {_scrub(e)}")
        print(f"\nresolved {done}, already present {skipped}, failed {failed}")
        return 0 if not failed else 1
    a.start, a.end, clamped = clamp_to_dataset(client_probe, a.dataset,
                                               a.start, a.end)
    for line in clamped:
        print(f"  {line}")
    if clamped:
        print()

    if a.window:
        chunks = day_chunks(a.start, a.end, a.window)
        kind = f"weekday chunk(s) covering {a.window} ET"
    else:
        chunks = month_chunks(a.start, a.end)
        kind = "monthly chunk(s)"
    if not chunks:
        # A REQUEST THAT COVERS NOTHING IS NOT A SUCCESSFUL NO-OP. Without
        # this, an empty chunk list prints the same "to download 0 /
        # $0.0000" as a pull whose files are all already on disk, and the run
        # exits 0. The two look identical and mean opposite things.
        sys.exit(f"\nNOTHING TO DO: {a.start} -> {a.end} (end exclusive) "
                 f"covers no weekday chunk.\n"
                 f"  `--end` is EXCLUSIVE. To pull a single day D, pass "
                 f"--start D --end D+1.\n"
                 f"  A same-day start and end covers zero days, which is not "
                 f"the same as having nothing left to fetch.")
    print(f"{a.dataset}  {a.schema}  {a.start} -> {a.end}   "
          f"{len(chunks)} {kind}\narchive {root}/\n")

    client = client_probe
    todo, usd, nbytes, skipped, empty, short = [], 0.0, 0, 0, 0, []
    for label, lo, hi in chunks:
        out = chunk_path(root, a.dataset, a.schema, label)
        if out.exists():
            if a.refresh_partial and chunk_ends_before(out, hi):
                short.append((label, chunk_last_bar(out)))
            else:
                skipped += 1
                continue
        kw = dict(dataset=a.dataset, schema=a.schema, symbols="ALL_SYMBOLS",
                  stype_in="raw_symbol", start=lo, end=hi)
        try:
            c = float(client.metadata.get_cost(**kw))
            b = int(client.metadata.get_billable_size(**kw))
        except Exception as e:  # noqa: BLE001
            print(f"  {label}  ESTIMATE FAILED: {_scrub(e)}")
            continue
        if b == 0:
            # A market holiday inside a weekday chunk, or a symbol-day the
            # dataset simply does not cover. Downloading it produces an empty
            # file that then fails symbology resolution and lands in the
            # archive looking like a real but empty session.
            empty += 1
            continue
        usd += c
        nbytes += b
        todo.append((label, lo, hi, out, c, b))
        if not a.window:
            print(f"  {label}  {b/1e6:>9.1f} MB   ${c:>8.4f}")

    if short:
        print("\nPARTIAL CHUNKS ON DISK -- these will be RE-FETCHED:\n")
        for label, last in short:
            print(f"  {label}  last bar {last}")
        print("\n  A chunk fetched mid-period is frozen where it was pulled,"
              "\n  and skip-if-present then preserves that truncation forever."
              "\n  Pass --no-refresh-partial to keep them as they are.")
    print(f"\nalready on disk, skipped : {skipped}")
    print(f"partial, to re-fetch     : {len(short)}")
    print(f"empty (holiday/no data)  : {empty}")
    print(f"to download              : {len(todo)}")
    print(f"ESTIMATED SIZE           : {nbytes/1e6:,.1f} MB")
    print(f"ESTIMATED COST           : ${usd:,.4f}")

    if not todo:
        return 0
    if usd > a.max_cost:
        sys.exit(f"\nABORTED: ${usd:,.2f} exceeds --max-cost ${a.max_cost:,.2f}.")
    if not a.confirm:
        print("\nDry run. Re-run with --confirm to download.")
        return 0

    print()
    refetched = {lbl for lbl, _ in short}
    entries, written = {}, 0
    for label, lo, hi, out, _c, _b in todo:
        if label in refetched:
            # save_symbology() early-returns when the sidecar exists, so a
            # re-fetched chunk would keep the SHORT chunk's mapping and every
            # newly-arrived instrument id would resolve to symbol=None -- the
            # exact failure that docstring warns about, reintroduced by the
            # fix for a different one.
            symbology_path(out).unlink(missing_ok=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".partial")
        try:
            client.timeseries.get_range(
                dataset=a.dataset, schema=a.schema, symbols="ALL_SYMBOLS",
                stype_in="raw_symbol", start=lo, end=hi, path=str(tmp))
        except Exception as e:  # noqa: BLE001
            print(f"  {label}  FAILED: {_scrub(e)}")
            tmp.unlink(missing_ok=True)
            continue
        tmp.replace(out)
        written += 1
        try:
            save_symbology(client, out)
        except Exception as e:  # noqa: BLE001
            print(f"  {label}  SYMBOLOGY FAILED: {_scrub(e)}  "
                  "-- run --resymbolize before analysing")
        # Per-day conditions for the whole month, so a degraded session inside
        # an otherwise fine chunk is still recorded.
        # Date-only: with --window these bounds are UTC timestamps, and
        # get_dataset_condition takes dates.
        cond = conditions(client, a.dataset, [lo[:10], hi[:10]])
        bad = sorted(d for d, c in cond.items() if c not in ("available", ""))
        entries[f"{a.schema}/{label}"] = {
            "chunk": label, "schema": a.schema, "start": lo, "end": hi,
            "bytes": out.stat().st_size, "degraded_days": bad,
        }
        flag = f"  [{len(bad)} degraded day(s)]" if bad else ""
        print(f"  {label}  -> {out}  ({out.stat().st_size/1e6:.1f} MB){flag}")

    if entries:
        print(f"\nmanifest: {write_manifest(root, a.dataset, entries)}")
    print(f"wrote {written} chunk(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
