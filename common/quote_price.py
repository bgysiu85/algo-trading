#!/usr/bin/env python3
r"""Price, then pull, top-of-book quotes around every entry in both books.

    python -m common.quote_price                         # sample-price 4 candidates
    python -m common.quote_price --full --dataset XNAS.ITCH --schema mbp-1
    python -m common.quote_price --dataset XNAS.ITCH --schema mbp-1 --confirm

AT-24 / AT-74. Ben, 2026-09-19: "let's price and get the MBP-1 data".

WHY THIS EXISTS
---------------
The thin-tape pre-flight (H-T1) closed the volume floor and left one question
standing: was the money lost on thin bars lost to the SPREAD? The backtest
cannot say. It fills at the signal bar's close plus a tick and `ohlcv-1m`
carries no quotes. AEHL filled at the ask on a 10.47% spread live; the books
charge that bar the same as a 600,000-share one.

The answer needs the bid and ask at the moment each entry would have been
sent -- for all 10,370 entries in the published books, not the 180 live ones.

WHAT IS PRICED: WINDOWS, NOT DAYS
---------------------------------
Full-day top-of-book on a small cap is every quote change for sixteen hours.
The question needs a few minutes around each entry. So each symbol-day gets
ONE window, from BEFORE minutes ahead of its first signal-bar close to AFTER
minutes past its last. Defaults 10 and 5:

  * 10 minutes back, because on a dead pre-market name the quote standing at
    the close may have been set minutes earlier -- and an MBP-1 record carries
    the whole top of book after each event, so the last record at or before
    the close IS the quote at the close. No record in the ten minutes is itself
    the finding ("no quote moved"), recorded as such later, not papered over.
  * 5 minutes forward, so the study can see whether the spread at entry was a
    moment or a state.

The signal bar is stamped at its START (`thin_tape_entries.csv` writes
`entry_et` from the engine's bar index), so the close -- when the order goes
out -- is `entry_et + bar_min`. Getting that wrong prices the quote one bar
early on every MC5 entry: the H-R1 grain defect again.

WHICH TAPE: PRICE SEVERAL, BUY ONE
----------------------------------
"MBP-1" is a schema, and more than one dataset serves a top of book. They are
not the same book. XNAS.ITCH's is Nasdaq's own; EQUS.MINI's is a blend of
venues (and on 2026-09-06 read 2.7x wider than XNAS.BASIC's on the same
fills); XNAS.BASIC's consolidated schemas are the tape that friction work
trusted. Which is right is a question for the registration, not for this
tool. This tool puts the price of each beside the others so the choice is made
with the numbers in view.

Sample mode prices a fixed crc32 sample of symbol-days per candidate and
scales up. Pricing every window for four candidates is ~30,000 sequential
metadata calls; the sample answers "which is affordable" in a few minutes.
`--full` then prices every window for the one chosen, exactly, and `--confirm`
pulls it -- after pricing it in the same run, never on a stale figure.

THE ENTITLEMENT HAS AN EDGE, AND THIS REPORTS WHERE IT IS
---------------------------------------------------------
Ben's plan carries the last twelve months of L1. The books run back further
than that. `get_cost` is the only thing that knows the plan, so every figure
is split into windows that priced at $0 and windows that did not, with the
date where the paid ones stop. Nothing older than the entitlement is bought
by default: `--confirm` refuses a total above `--max-cost` (default $0.00 --
this pull is meant to be free, and if it is not, that is a decision for Ben).

SPENDING GUARDS (the house rules)
---------------------------------
  * every run prices before anything else and prints the total;
  * nothing downloads without --confirm;
  * --confirm re-prices every window in the same run and aborts above
    --max-cost;
  * windows already on disk are skipped, so a re-run is free;
  * the key comes from DATABENTO_API_KEY (via secrets_util, op:// resolved),
    is never an argument and is never printed.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from common.report_io import emit

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

ENTRIES = "var/reports/thin_tape_entries.csv"
REPORT = "var/reports/quote_price.txt"
BEFORE_MIN = 10
AFTER_MIN = 5
SAMPLE = 150
PLAN_DAYS = 365          # "last 12 months" of L1, as Ben's plan states it
TICK = 25                # progress line every N windows

CANDIDATES = (
    ("XNAS.ITCH", "mbp-1"),
    ("XNAS.BASIC", "cmbp-1"),
    ("XNAS.BASIC", "cbbo-1s"),
    ("EQUS.MINI", "mbp-1"),
)


@dataclass
class Window:
    symbol: str
    day: str
    start: datetime            # UTC
    end: datetime              # UTC
    entries: int = 0
    books: set = field(default_factory=set)

    @property
    def key(self) -> str:
        return f"{self.day} {self.symbol}"


# --- the windows --------------------------------------------------------------

def signal_close(day: str, entry_et: str, bar_min: int) -> datetime:
    """The moment the order goes out: the signal bar's START plus its length.

    `entry_et` is the bar's start stamp (the engine indexes bars by start), so
    adding `bar_min` is not optional -- without it every MC5 quote is read four
    minutes early, on a different bar.
    """
    hh, mm = (int(x) for x in entry_et.split(":"))
    d = date.fromisoformat(day)
    start = datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET)
    return start + timedelta(minutes=int(bar_min))


def load_entries(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        sys.exit(f"{p} not found. It is written by the thin-tape pass:\n"
                 "  python -m common.thin_tape --jobs 8\n"
                 "and holds every entry in both published books.")
    with open(p, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    need = {"book", "symbol", "date", "entry_et", "bar_min"}
    missing = need - set(rows[0].keys()) if rows else need
    if missing:
        sys.exit(f"{p} is missing columns {sorted(missing)}")
    return rows


def windows(rows: list[dict], before: int = BEFORE_MIN,
            after: int = AFTER_MIN) -> list[Window]:
    """One window per symbol-day, spanning every entry either book made there."""
    by = {}
    for r in rows:
        close = signal_close(r["date"], r["entry_et"], int(r["bar_min"]))
        k = (r["date"], r["symbol"])
        lo = close - timedelta(minutes=before)
        hi = close + timedelta(minutes=after)
        w = by.get(k)
        if w is None:
            w = by[k] = Window(r["symbol"], r["date"], lo, hi)
        w.start, w.end = min(w.start, lo), max(w.end, hi)
        w.entries += 1
        w.books.add(r["book"])
    out = sorted(by.values(), key=lambda w: (w.day, w.symbol))
    for w in out:
        w.start, w.end = w.start.astimezone(UTC), w.end.astimezone(UTC)
    return out


def sample(ws: list[Window], n: int) -> list[Window]:
    """A fixed, reproducible subset: crc32 of the key, lowest n."""
    if n <= 0 or n >= len(ws):
        return list(ws)
    return sorted(ws, key=lambda w: zlib.crc32(w.key.encode()))[:n]


def plan_edge(today: date, days: int = PLAN_DAYS) -> date:
    return today - timedelta(days=days)


# --- pricing ------------------------------------------------------------------

def request(dataset: str, schema: str, w: Window) -> dict:
    return dict(dataset=dataset, schema=schema, symbols=[w.symbol],
                stype_in="raw_symbol", start=w.start.isoformat(),
                end=w.end.isoformat())


@dataclass
class Priced:
    usd: float = 0.0
    nbytes: int = 0
    n: int = 0
    paid: int = 0
    failed: int = 0
    first_error: str = ""
    paid_days: list = field(default_factory=list)


def price(client, dataset: str, schema: str, ws: list[Window], *,
          scrub=lambda s: str(s), tick: int = TICK, label: str = "") -> Priced:
    out = Priced()
    t0 = time.time()
    for i, w in enumerate(ws, start=1):
        kw = request(dataset, schema, w)
        try:
            c = float(client.metadata.get_cost(**kw))
            b = int(client.metadata.get_billable_size(**kw))
        except Exception as e:                                  # noqa: BLE001
            out.failed += 1
            if not out.first_error:
                out.first_error = scrub(e)
            continue
        out.n += 1
        out.usd += c
        out.nbytes += b
        if c > 0:
            out.paid += 1
            out.paid_days.append(w.day)
        if tick and (i % tick == 0 or i == len(ws)):
            el = time.time() - t0
            eta = el / i * (len(ws) - i)
            print(f"  {label}{i:>6}/{len(ws)}  {out.nbytes/1e6:>9,.1f} MB  "
                  f"${out.usd:>9.4f}  ~{eta/60:.1f} min left", flush=True)
    return out


def scale(p: Priced, total: int) -> tuple[float, float]:
    """Projected (usd, bytes) for `total` windows from a priced sample."""
    if p.n == 0:
        return float("nan"), float("nan")
    return p.usd / p.n * total, p.nbytes / p.n * total


# --- the pull -----------------------------------------------------------------

def window_path(root: Path, dataset: str, schema: str, w: Window) -> Path:
    return root / dataset / schema / "windows" / w.day / f"{w.symbol}.dbn.zst"


def pull(client, dataset: str, schema: str, ws: list[Window], root: Path, *,
         scrub=lambda s: str(s), tick: int = TICK) -> tuple[int, int, list]:
    """Fetch every window not already on disk. Returns (got, skipped, errors)."""
    got = skipped = 0
    errors = []
    t0 = time.time()
    for i, w in enumerate(ws, start=1):
        out = window_path(root, dataset, schema, w)
        if out.exists() and out.stat().st_size > 0:
            skipped += 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".part")
        try:
            client.timeseries.get_range(path=str(tmp), **request(dataset, schema, w))
            tmp.replace(out)
            got += 1
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{w.key}: {scrub(e)}")
            try:
                tmp.unlink()
            except OSError:
                pass
        if tick and (i % tick == 0 or i == len(ws)):
            el = time.time() - t0
            eta = el / i * (len(ws) - i)
            print(f"  pulled {i:>6}/{len(ws)}  new {got}  on disk {skipped}  "
                  f"errors {len(errors)}  ~{eta/60:.1f} min left", flush=True)
    return got, skipped, errors


def write_manifest(root: Path, dataset: str, schema: str, ws: list[Window],
                   before: int, after: int) -> Path:
    p = root / dataset / schema / "windows" / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {"written": datetime.now(UTC).isoformat(), "before_min": before,
            "after_min": after, "source": ENTRIES,
            "windows": [{"day": w.day, "symbol": w.symbol,
                         "start": w.start.isoformat(), "end": w.end.isoformat(),
                         "entries": w.entries, "books": sorted(w.books)}
                        for w in ws]}
    p.write_text(json.dumps(body, indent=1), encoding="utf-8")
    return p


# --- the report ---------------------------------------------------------------

def money(x: float) -> str:
    if x != x:                                                  # nan
        return "n/a"
    return f"({abs(x):,.2f})" if x < 0 else f"${x:,.2f}"


def head(ws: list[Window], edge: date, before: int, after: int) -> list[str]:
    days = sorted({w.day for w in ws})
    inplan = [w for w in ws if date.fromisoformat(w.day) >= edge]
    books = defaultdict(int)
    for w in ws:
        for b in w.books:
            books[b] += 1
    span = sum((w.end - w.start).total_seconds() for w in ws) / 60
    return [
        "QUOTE PRICING -- TOP OF BOOK AROUND EVERY ENTRY (AT-24)", "",
        f"  windows      {len(ws):,} symbol-days, {sum(w.entries for w in ws):,} "
        f"entries, {len(days)} sessions",
        f"  by book      " + "  ".join(f"{b} {n:,}" for b, n in sorted(books.items())),
        f"  dates        {days[0] if days else '-'} .. {days[-1] if days else '-'}",
        f"  window       {before} min before the first signal-bar close to "
        f"{after} min after the last",
        f"  total span   {span:,.0f} minutes ({span/max(len(ws),1):.1f} per window)",
        f"  plan edge    {edge} (last {PLAN_DAYS} days): {len(inplan):,} windows "
        f"inside, {len(ws)-len(inplan):,} older", "",
    ]


def candidate_line(ds: str, sc: str, p: Priced, total: int) -> str:
    if p.n == 0:
        return (f"  {ds:<11} {sc:<8}  NOT PRICED -- {p.failed} failed. "
                f"First error: {p.first_error[:90]}")
    usd, nb = scale(p, total)
    return (f"  {ds:<11} {sc:<8}  sample {p.n:>4}  paid {p.paid:>4}  "
            f"projected {money(usd):>12}  {nb/1e9:>8.2f} GB")


# --- main ---------------------------------------------------------------------

def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--entries", default=ENTRIES)
    ap.add_argument("--dataset")
    ap.add_argument("--schema")
    ap.add_argument("--full", action="store_true",
                    help="price EVERY window for --dataset/--schema")
    ap.add_argument("--confirm", action="store_true",
                    help="price every window, then pull them (needs --dataset/--schema)")
    ap.add_argument("--in-plan-only", action=argparse.BooleanOptionalAction,
                    default=True, help="only windows inside the plan's 12 months")
    ap.add_argument("--sample", type=int, default=SAMPLE)
    ap.add_argument("--before", type=int, default=BEFORE_MIN)
    ap.add_argument("--after", type=int, default=AFTER_MIN)
    ap.add_argument("--max-cost", type=float, default=0.00)
    ap.add_argument("--archive", default=None)
    ap.add_argument("--report", default=REPORT)
    a = ap.parse_args(argv)
    if (a.full or a.confirm) and not (a.dataset and a.schema):
        ap.error("--full and --confirm need --dataset and --schema "
                 "(one tape, chosen from the sample run)")
    return a


def main(argv=None, *, client=None, today: date | None = None) -> int:
    a = parse(argv)
    from common import databento_fetch as F

    ws_all = windows(load_entries(a.entries), a.before, a.after)
    edge = plan_edge(today or date.today())
    ws = ([w for w in ws_all if date.fromisoformat(w.day) >= edge]
          if a.in_plan_only else ws_all)
    L = head(ws_all, edge, a.before, a.after)
    L.append(f"  priced       {len(ws):,} windows "
             f"({'inside the plan only' if a.in_plan_only else 'ALL dates'})")
    L.append("")
    if not ws:
        emit("\n".join(L + ["  Nothing to price."]), a.report)
        return 1

    if client is None:
        db = F.require_databento()
        client = db.Historical(F._key())
    scrub = F._scrub

    if not (a.full or a.confirm):
        L += [f"SAMPLE PRICING: {min(a.sample, len(ws))} windows per candidate, "
              f"scaled to {len(ws):,}", ""]
        sm = sample(ws, a.sample)
        for ds, sc in CANDIDATES:
            print(f"pricing {ds} {sc} ...", flush=True)
            p = price(client, ds, sc, sm, scrub=scrub, label=f"{sc:<8}")
            L.append(candidate_line(ds, sc, p, len(ws)))
        L += ["", "  A candidate that did not price is not offered on this plan or",
              "  under that name; the error says which. 'paid' counts sample",
              "  windows that priced above $0 -- inside the plan it should be 0.", "",
              "NEXT: choose one tape, then price it exactly and pull it:", "",
              "  python -m common.quote_price --full --dataset <DS> --schema <SC>",
              "  python -m common.quote_price --dataset <DS> --schema <SC> --confirm"]
        emit("\n".join(L), a.report)
        return 0

    print(f"pricing every window: {a.dataset} {a.schema} ...", flush=True)
    p = price(client, a.dataset, a.schema, ws, scrub=scrub)
    L += [f"EXACT PRICING: {a.dataset} {a.schema}", "",
          f"  priced       {p.n:,} of {len(ws):,} windows ({p.failed} failed)",
          f"  cost         {money(p.usd)}",
          f"  size         {p.nbytes/1e9:,.2f} GB",
          f"  paid windows {p.paid:,}" + (f"  (dates {min(p.paid_days)} .. "
                                         f"{max(p.paid_days)})" if p.paid_days else ""),
          ""]
    if p.failed:
        L.append(f"  first error: {p.first_error}")
        L.append("")
    if not a.confirm:
        L += ["Nothing downloaded. To pull exactly this:", "",
              f"  python -m common.quote_price --dataset {a.dataset} "
              f"--schema {a.schema} --confirm"]
        emit("\n".join(L), a.report)
        return 0
    if p.failed:
        emit("\n".join(L + ["REFUSED: some windows did not price, so the total "
                            "above is not the whole cost."]), a.report)
        return 2
    if p.usd > a.max_cost + 1e-9:
        emit("\n".join(L + [f"REFUSED: {money(p.usd)} is above --max-cost "
                            f"{money(a.max_cost)}. Nothing downloaded."]), a.report)
        return 2

    root = Path(a.archive) if a.archive else F.default_archive()
    got, skipped, errors = pull(client, a.dataset, a.schema, ws, root, scrub=scrub)
    man = write_manifest(root, a.dataset, a.schema, ws, a.before, a.after)
    L += ["PULLED", "",
          f"  new          {got:,}",
          f"  on disk      {skipped:,} (skipped, free)",
          f"  errors       {len(errors):,}",
          f"  archive      {root / a.dataset / a.schema / 'windows'}",
          f"  manifest     {man}", ""]
    L += [f"  {e}" for e in errors[:20]]
    emit("\n".join(L), a.report)
    return 0 if not errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
