#!/usr/bin/env python3
r"""The ET block table on the point-in-time trade list -- descriptive.

    python -m common.time_of_day --csv var/reports/first_entry_skip_trades.csv

Registered as §4 of docs/research/REGISTERED_first_entry_skip.md, from
`handover_time_of_day_20260916.md`: the stale run (on the survivor-universe
book at (0.53)/trade) found four positive 30-minute blocks of which none
survived drop-top-3, and one standout cell, 07:45-08:00, at +$20.98/trade on
80 trades that drop-top-3 took from +1,678 to (537). This re-reads the same
table on the point-in-time books with the four checks that run lacked:
drop-top-3, both halves, the friction ladder, and the SESSION denominator.

It reads the CSV `common/first_entry_skip.py` wrote and that run's meta file,
so the halves are cut on the run's date and nothing is re-run. Timestamps in
that CSV are ET by construction (`entry_et`); this module refuses a CSV that
does not say so, because the stale run's column was UTC and reading it as ET
moved every conclusion four hours while still looking coherent.

THERE IS NO PASS BAR HERE. 07:45-08:00 and the 07:00-08:00 hour were named
before the numbers; the last block of the report says, in the registration's
words, whether the window is registrable as a hypothesis or the question
closes. Nothing else in the table is read as anything but description.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from datetime import time as dtime
from pathlib import Path

from common.entry_shares import MEASURED_FRICTION
from common.report_io import emit

FRICTIONS = (("$1.00", 1.00), ("$4.26", 4.26), ("$8.92", 8.92))
DROP = 3
REGISTERED = "docs/research/REGISTERED_first_entry_skip.md"
SESSION_START, SESSION_END = dtime(4, 0), dtime(9, 30)
BLOCK_MIN = 30               # the registered table; the named cell is read on its own
# Named in advance (registration §4). Not tuned, not moved.
NAMED_CELL = ("07:45", "08:00")
NAMED_HOUR = ("07:00", "08:00")
BOOKS = ("MCL", "MC5")


def blocks(minutes: int = BLOCK_MIN) -> list[tuple[str, str]]:
    """Half-open [start, end) blocks covering the session, as HH:MM strings.
    String comparison is correct for zero-padded HH:MM."""
    out, m = [], SESSION_START.hour * 60 + SESSION_START.minute
    end = SESSION_END.hour * 60 + SESSION_END.minute
    while m < end:
        n = min(m + minutes, end)
        out.append((f"{m // 60:02d}:{m % 60:02d}", f"{n // 60:02d}:{n % 60:02d}"))
        m = n
    return out


def in_block(r: dict, blk: tuple[str, str]) -> bool:
    return blk[0] <= r["entry_et"] < blk[1]


def net(rows, f: float) -> float:
    return sum(r["net"] - f for r in rows)


def per_trade(rows, f: float) -> float:
    return net(rows, f) / len(rows) if rows else 0.0


def drop_top(rows, f: float, n: int = DROP) -> float:
    vals = sorted((r["net"] - f for r in rows), reverse=True)
    return sum(vals[n:])


def halves(rows, cut: str) -> tuple[list, list]:
    return ([r for r in rows if r["date"] < cut], [r for r in rows if r["date"] >= cut])


def sessions(rows, f: float) -> dict:
    """The session denominator: net per session over sessions with at least
    one entry in the block, and what share of those sessions were positive."""
    per: dict[str, float] = {}
    for r in rows:
        per[r["date"]] = per.get(r["date"], 0.0) + (r["net"] - f)
    vals = list(per.values())
    return {"n": len(vals),
            "positive": sum(1 for v in vals if v > 0) / len(vals) if vals else 0.0,
            "mean": statistics.mean(vals) if vals else 0.0,
            "median": statistics.median(vals) if vals else 0.0}


def cell(rows, cut: str) -> dict:
    """Every number the table prints for one block, at every friction."""
    f = MEASURED_FRICTION
    a, b = halves(rows, cut)
    return {"trades": len(rows),
            "net": {lab: net(rows, fr) for lab, fr in FRICTIONS},
            "per_trade": per_trade(rows, f),
            "drop": drop_top(rows, f),
            "early": net(a, f), "late": net(b, f),
            "sess": sessions(rows, f)}


def named_reading(rows, cut: str) -> tuple[bool, list[str]]:
    """§4, verbatim: positive at all three frictions, in both halves, after
    drop-top-3, and a session median above zero. All four -> registrable as a
    hypothesis in a NEW registration; any fewer -> the question closes."""
    c = cell(rows, cut)
    checks = [(all(v > 0 for v in c["net"].values()), "positive at all three frictions"),
              (c["early"] > 0 and c["late"] > 0, "positive in both halves at $4.26"),
              (c["drop"] > 0, f"positive after drop-top-{DROP} at $4.26"),
              (c["sess"]["median"] > 0, "session median above zero at $4.26")]
    return all(ok for ok, _ in checks), [f"    {'holds' if ok else 'FAILS':<6} {lab}" for ok, lab in checks]


def money(x: float) -> str:
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def table(name: str, rows, cut: str) -> list[str]:
    L = [f"  {name}  -- entry bar, ET, {BLOCK_MIN}-minute blocks", "",
         f"  {'block (ET)':<13}{'trades':>7}{'net $1.00':>11}{'net $4.26':>11}{'net $8.92':>11}"
         f"{'per/t':>9}{'drop-3':>11}{'early':>11}{'late':>11}"
         f"{'sess':>6}{'pos%':>6}{'mean/s':>9}{'med/s':>9}", ""]
    for blk in blocks():
        sel = [r for r in rows if in_block(r, blk)]
        if not sel:
            L.append(f"  {blk[0]}-{blk[1]:<7}{0:>7}")
            continue
        c = cell(sel, cut)
        s = c["sess"]
        L.append(f"  {blk[0]}-{blk[1]:<7}{c['trades']:>7,}"
                 f"{money(c['net']['$1.00']):>11}{money(c['net']['$4.26']):>11}{money(c['net']['$8.92']):>11}"
                 f"{money(c['per_trade']):>9}{money(c['drop']):>11}{money(c['early']):>11}{money(c['late']):>11}"
                 f"{s['n']:>6,}{100 * s['positive']:>6.1f}{money(s['mean']):>9}{money(s['median']):>9}")
    L.append("")
    return L


def render(books: dict, meta: dict) -> list[str]:
    cut = meta["cut"]
    L = ["TIME OF DAY ON THE POINT-IN-TIME BOOKS -- DESCRIPTIVE", "",
         f"  registered  {REGISTERED} §4",
         f"  {len(meta['sessions']):,} sessions   {meta['symbol_days']:,} symbol-days   "
         f"halves cut at {cut}   timestamps {meta['timestamps']}",
         f"  friction per round trip; per/t, drop-{DROP}, halves and the session columns at $4.26",
         "  sess = sessions with an entry in the block; pos% = share of those positive", ""]
    for name in BOOKS:
        L += table(name, books.get(name, []), cut)

    mcl = books.get("MCL", [])
    L += [f"THE NAMED CELL, {NAMED_CELL[0]}-{NAMED_CELL[1]} ET, on MCL (registered before the numbers)", ""]
    sel = [r for r in mcl if in_block(r, NAMED_CELL)]
    c = cell(sel, cut)
    L += [f"  trades {c['trades']:,}   net {money(c['net']['$4.26'])} at $4.26   per trade {money(c['per_trade'])}"
          f"   drop-{DROP} {money(c['drop'])}   halves {money(c['early'])} / {money(c['late'])}"
          f"   sessions {c['sess']['n']:,} median {money(c['sess']['median'])}", ""]
    ok, lines = named_reading(sel, cut)
    L += lines
    L += ["",
          ("  REGISTRABLE: the window may be registered as a hypothesis, pre-committed, in a"
           " new document. Not a result." if ok else
           "  THE TIME-OF-DAY QUESTION CLOSES: the named cell does not hold on the"
           " point-in-time books, and the 07:00-window backlog item comes off."),
          ""]
    hr = [r for r in mcl if in_block(r, NAMED_HOUR)]
    h = cell(hr, cut)
    L += [f"  the hour {NAMED_HOUR[0]}-{NAMED_HOUR[1]}: trades {h['trades']:,}   net {money(h['net']['$4.26'])}"
          f"   sessions {h['sess']['n']:,}   {100 * h['sess']['positive']:.1f}% positive"
          f"   mean {money(h['sess']['mean'])}   median {money(h['sess']['median'])}  (context)", "",
          "WHAT THIS IS NOT", "",
          "  NOT A HYPOTHESIS TEST. One cell was named in advance and read against four",
          "  checks; every other row is description and none passes or fails anything.",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.", ""]
    return L


def read_csv(path: Path) -> dict:
    books: dict[str, list] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r["net"] = float(r["net"])
            books.setdefault(r["book"], []).append(r)
    return books


def read_meta(csv_path: Path) -> dict:
    p = csv_path.with_name(csv_path.stem + "_meta.json")
    meta = json.loads(p.read_text(encoding="utf-8"))
    if meta.get("timestamps") != "ET":
        raise SystemExit(f"{p}: timestamps are {meta.get('timestamps')!r}, not ET -- refusing "
                         "to bucket them (the stale run's column was UTC)")
    return meta


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--csv", default="var/reports/first_entry_skip_trades.csv")
    p.add_argument("--out", default="var/reports/time_of_day_pit.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    csv_path = Path(a.csv)
    meta = read_meta(csv_path)
    books = read_csv(csv_path)
    emit("\n".join(render(books, meta)), a.out,
         header=f"common.time_of_day csv={a.csv} sessions={len(meta['sessions'])} "
                f"symbol_days={meta['symbol_days']} cut={meta['cut']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
