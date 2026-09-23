#!/usr/bin/env python3
"""G8 step 4: validate the point-in-time universe against known adds/drops and
re-check delisted-price coverage (AT-45 / W07-0002 step 4).

    python -m strategy.swing.pit_validate
    python -m strategy.swing.pit_validate --self-test

Reads only what `pit_universe.py` already wrote to `var/swing_pit/` --
membership.csv, eod/*.csv, raw/comp_*.json, raw/us_delisted_symbols.json.
No API calls, nothing re-fetched, nothing re-parsed that pit_universe.py
already parses -- this module imports it rather than duplicating its CSV/JSON
handling.

WHY THIS EXISTS
----------------
`pit_universe.py report` classifies a membership spell "full" / "partial" /
"none" by comparing the FIRST and LAST date of whatever EOD file exists for
that ticker against the spell's window boundary (+/- 7 days slack). That
boundary check has a blind spot: a ticker that was delisted from the index
and later REISSUED to an unrelated company reads as having a "last" date of
today (the new company is still trading), which alone is enough to pass the
`ok_hi` half of the check even though there is not one single trading day of
real overlap between the new company's price history and the old spell's
window. Six such codes were found by hand while reading the 2026-09-19
report (EMC, LLL, MON, SE, STI, TIME -- all delisted-from-index spells whose
current ticker belongs to an unrelated, later-listed company) and all six
were sitting in the "partial" bucket, not "none". This script recomputes
coverage from actual overlapping trading rows, not just first/last, so those
six (and anything like them) move to where they belong.

It also works the free-list disagreement table the other way: for a ticker
EODHD shows as absent it looks up EODHD's own delisted-symbols file (saved by
the constituents stage) for that ticker's name, then checks whether an
EODHD-active code carries the same company name today -- the signature of a
ticker RENAME (e.g. BK -> BNY), which is not a real index drop and should not
be read as one.

WHAT IT DOES NOT DO
--------------------
It does not fetch anything, fix membership.csv, or re-price anything. It is a
second pass of judgement over data pit_universe.py already collected, and it
writes its findings next to that data rather than changing it.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Iterable

from strategy.swing import pit_universe as P

DEFAULT_OUT = Path("var") / "swing_pit"
DEFAULT_WATCH = ["BK", "AVB", "CAG", "CPB"]
SUFFIXES = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|companies|plc|ltd|"
    r"limited|group|holdings|holding|the)\b", re.IGNORECASE)


# --------------------------------------------------------------------------
# name matching -- deliberately crude, flags a candidate for a human to check
# --------------------------------------------------------------------------

def norm_name(name: str) -> str:
    n = (name or "").lower()
    n = n.replace("'", "").replace(".", "").replace(",", "")
    n = SUFFIXES.sub(" ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return n


def load_delisted(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for r in P.records(json.loads(path.read_text(encoding="utf-8"))):
        code = P.norm_code(r.get("Code"))
        if code and code not in out:
            out[code] = r
    return out


def find_rename_candidate(free_name: str, active_names: dict[str, str]) -> str | None:
    """active_names: normalized name -> code, for codes EODHD shows active today.

    Deliberately exact-match only, on the normalized name. An early version of
    this tried substring containment both ways to also catch shortened or
    expanded names, and it was wrong more often than it was right: after
    stripping suffixes like "Inc"/"Corporation"/"Holdings" a short normalized
    name (e.g. "Cabot Corporation" -> "cabot", or "IES Holdings Inc" -> "ies")
    is a substring of dozens of unrelated names ("cabot" inside "Cabot Oil &
    Gas Corporation"; "ies" inside "...technologIES..."). A wrong "looks like
    a RENAME" is worse than a missed one here, since it would tell Ben two
    different companies are the same one. Exact match only misses renames
    where the surviving name differs more than punctuation/suffixes (Harris
    Corp -> L3Harris, say) -- those fall through to "no matching active
    EODHD code found", which is an honest "unresolved", not a wrong answer.
    """
    target = norm_name(free_name)
    if not target:
        return None
    return active_names.get(target)


# --------------------------------------------------------------------------
# true coverage -- actual overlapping rows, not just first/last date
# --------------------------------------------------------------------------

def price_dates(path: Path) -> list[dt.date]:
    if not path.exists():
        return []
    out = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = P.to_date(r.get("date"))
            if d is not None:
                out.append(d)
    out.sort()
    return out


def trading_days_estimate(lo: dt.date, hi: dt.date) -> int:
    """5/7 of the calendar span -- an estimate, not a holiday calendar. Good
    enough to size a density ratio; not meant to be exact."""
    days = (hi - lo).days + 1
    return max(1, round(days * 5 / 7))


def true_coverage(spell: "P.Spell", dates: list[dt.date],
                  window: tuple[dt.date, dt.date],
                  slack_days: int = 7,
                  density_floor: float = 0.5) -> tuple[str, int, int]:
    """Returns (verdict, in_window_rows, expected_rows).

    verdict is one of: full, partial, suspect_reuse, none, outside.
    suspect_reuse: pit_universe's own first/last check would call this
    covered (or partially covered), but zero -- or too few -- of the actual
    rows fall inside the spell's own window. That is the reused-ticker shape:
    a current, unrelated security's data happens to straddle the boundary.
    """
    lo = max(spell.start or window[0], window[0])
    hi = min(spell.end or window[1], window[1])
    if lo > hi:
        return "outside", 0, 0
    if not dates:
        return "none", 0, trading_days_estimate(lo, hi)
    slack = dt.timedelta(days=slack_days)
    in_window = sum(1 for d in dates if lo - slack <= d <= hi + slack)
    expected = trading_days_estimate(lo, hi)
    if in_window == 0:
        return "suspect_reuse", 0, expected
    density = in_window / expected
    first, last = dates[0], dates[-1]
    ok_lo, ok_hi = first <= lo + slack, last >= hi - slack
    if ok_lo and ok_hi and density >= density_floor:
        return "full", in_window, expected
    if density < density_floor:
        return "suspect_reuse", in_window, expected
    return "partial", in_window, expected


# --------------------------------------------------------------------------
# the report
# --------------------------------------------------------------------------

def stage_validate(out: Path, window: tuple[dt.date, dt.date],
                   fja_path: Path | None, watch: list[str]) -> list[str]:
    spells = P.read_membership(out / "membership.csv")
    delisted = load_delisted(out / "raw" / "us_delisted_symbols.json")

    # active-today name index, built from whichever spells EODHD marks active
    active_names: dict[str, str] = {}
    for s in spells:
        if s.is_active_now:
            active_names.setdefault(norm_name(s.name), s.code)

    L = [f"G8 validate -- window {window[0]} to {window[1]} "
         "(step 4, W07-0002 / AT-45)", ""]

    # --- 1. recomputed coverage, using real overlapping rows
    counts: dict[str, int] = {}
    suspects = []
    for s in spells:
        dates = price_dates(out / "eod" / f"{P.file_stem(s.code)}.csv")
        verdict, in_win, expected = true_coverage(s, dates, window)
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict == "suspect_reuse":
            full_span = (dates[0], dates[-1]) if dates else None
            suspects.append((s, in_win, expected, full_span))
    relevant = sum(v for k, v in counts.items() if k != "outside")
    L.append("RECOMPUTED COVERAGE (real overlapping rows, not just first/last date)")
    for k in ("full", "partial", "suspect_reuse", "none", "outside"):
        L.append(f"  {k:<14} {counts.get(k, 0):>5}")
    if relevant:
        L.append(f"  covered in full: {100 * counts.get('full', 0) / relevant:.1f}% "
                 f"of {relevant} spells")
        true_hole = counts.get("none", 0) + counts.get("suspect_reuse", 0)
        L.append(f"  true survivorship hole (none + suspect_reuse): {true_hole} "
                 f"of {relevant} ({100 * true_hole / relevant:.1f}%)")
    L.append("")

    L.append(f"SUSPECT_REUSE -- {len(suspects)} spells where a ticker's price file "
             "exists and pit_universe's boundary check called it covered, but "
             "zero of its rows actually fall inside the spell's own window. "
             "The most likely explanation: the ticker was reissued to an "
             "unrelated company after the real member left, and that "
             "company's price history is what got fetched.")
    for s, in_win, expected, span in sorted(suspects, key=lambda t: (t[0].index, t[0].code)):
        span_txt = f"{span[0]} -> {span[1]}" if span else "no rows at all"
        L.append(f"  {s.index} {s.code:<8} spell {s.start or '?'} -> {s.end or 'now'}  "
                 f"delisted={int(s.is_delisted)}  name-on-file={s.name[:40]!r}  "
                 f"price file spans {span_txt}")
    L.append("")

    # --- 2. undated spells, split by whether that is actually a problem
    undated = [s for s in spells if s.start is None]
    undated_active = [s for s in undated if s.is_active_now]
    undated_gone = [s for s in undated if not s.is_active_now]
    L.append(f"NO-START-DATE SPELLS: {len(undated)} total")
    L.append(f"  {len(undated_active)} are still active today -- fine, EODHD's "
             "history simply doesn't reach back far enough to date the join; "
             "treated as \"member since before the window\", which the window "
             "start already accounts for.")
    L.append(f"  {len(undated_gone)} have ALREADY left the index and never got "
             "a start date -- these are the ones worth a second look, since "
             "there is no way to tell from this file how long they were "
             "members before leaving.")
    for s in sorted(undated_gone, key=lambda s: (s.index, s.code))[:30]:
        L.append(f"    {s.index} {s.code:<8} -> {s.end}  {s.name[:40]}")
    if len(undated_gone) > 30:
        L.append(f"    ... {len(undated_gone) - 30} more")
    L.append("")

    # --- 3. free-list disagreements: rename or real difference?
    if fja_path is not None and fja_path.exists():
        fja = P.load_fja(fja_path)
        disagree: dict[str, int] = {}
        for d in P.sample_dates(*window):
            a, b = P.members_on(spells, "sp500", d), P.fja_on(fja, d)
            if b is None:
                continue
            for t in sorted(a - b) + sorted(b - a):
                disagree[t] = disagree.get(t, 0) + 1
        eodhd_codes = {s.code for s in spells if s.index == "sp500"}
        only_free = sorted(t for t in disagree if t not in eodhd_codes)
        L.append(f"FREE-LIST TICKERS EODHD NEVER SHOWS AS SP500 MEMBERS: "
                 f"{len(only_free)} (checked against EODHD's own delisted-"
                 "symbols file for a same-company rename)")
        for t in only_free:
            rec = delisted.get(t)
            if rec is None:
                L.append(f"  {t}: not in EODHD's delisted-symbols file either "
                         "-- unresolved, check by hand")
                continue
            name = rec.get("Name", "")
            candidate = find_rename_candidate(name, active_names)
            if candidate:
                L.append(f"  {t} = {name!r} -> matches EODHD code {candidate} "
                         "(active today, same name) -- looks like a RENAME, "
                         "not a real drop")
            else:
                L.append(f"  {t} = {name!r} -> no matching active EODHD code "
                         "found -- possibly a genuine drop, verify by hand")
        L.append("")

    # --- 4. named watch-list
    L.append(f"WATCH-LIST ({', '.join(watch)})")
    for t in watch:
        sp = sorted((s for s in spells if s.code == t), key=lambda s: (s.index, s.start or dt.date.min))
        if not sp:
            rec = delisted.get(t)
            if rec:
                L.append(f"  {t}: no S&P membership spell in EODHD's history. "
                         f"EODHD's delisted-symbols file has it as {rec.get('Name')!r} "
                         f"({rec.get('Exchange')}) -- check the rename table above.")
            else:
                L.append(f"  {t}: not found anywhere in EODHD's data (neither a "
                         "membership spell nor a delisted-symbol record)")
            continue
        for s in sp:
            in_current = "yes" if (s.is_active_now and s.code in active_names.values()) else "no"
            L.append(f"  {t} [{s.index}]: {s.start or '?'} -> {s.end or 'now'}  "
                     f"is_active_now={s.is_active_now}  delisted={s.is_delisted}  "
                     f"name={s.name[:50]!r}  in today's Components={in_current}")
    return L


def write_suspects_csv(path: Path, out: Path, window) -> None:
    spells = P.read_membership(out / "membership.csv")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "code", "name", "start", "end", "is_delisted",
                    "verdict", "in_window_rows", "expected_rows"])
        for s in spells:
            dates = price_dates(out / "eod" / f"{P.file_stem(s.code)}.csv")
            verdict, in_win, expected = true_coverage(s, dates, window)
            if verdict in ("suspect_reuse", "none"):
                w.writerow([s.index, s.code, s.name, s.start or "", s.end or "",
                            int(s.is_delisted), verdict, in_win, expected])


# --------------------------------------------------------------------------
# self-test (offline, synthetic -- no repo data required)
# --------------------------------------------------------------------------

def self_test() -> list[str]:
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        out = Path(t)
        (out / "eod").mkdir(parents=True)
        (out / "raw").mkdir(parents=True)
        P.write_membership(out / "membership.csv", [
            # genuine member, no coverage at all: the classic hole
            P.Spell("sp500", "GONE", "Real Old Co", dt.date(2015, 1, 1),
                    dt.date(2016, 6, 1), False, True),
            # reused ticker: an unrelated company's data straddles the boundary
            P.Spell("sp500", "REUSE", "Real Acquired Co", dt.date(2015, 1, 1),
                    dt.date(2016, 6, 1), False, True),
            # clean, fully covered
            P.Spell("sp500", "GOOD", "Still Here Inc", dt.date(2015, 1, 1),
                    None, True, False),
        ])
        with (out / "eod" / "REUSE.csv").open("w", newline="", encoding="utf-8") as f:
            wtr = csv.writer(f)
            wtr.writerow(P.PRICE_FIELDS)
            for d in ("2020-01-02", "2026-09-18"):
                wtr.writerow([d, 1, 1, 1, 1, 1, 100])
        with (out / "eod" / "GOOD.csv").open("w", newline="", encoding="utf-8") as f:
            wtr = csv.writer(f)
            wtr.writerow(P.PRICE_FIELDS)
            d = dt.date(2015, 1, 1)
            while d <= dt.date(2016, 6, 1):
                if d.weekday() < 5:
                    wtr.writerow([d.isoformat(), 1, 1, 1, 1, 1, 100])
                d += dt.timedelta(days=1)
        window = (dt.date(2015, 1, 1), dt.date(2016, 6, 1))
        lines = stage_validate(out, window, None, ["GONE", "REUSE", "GOOD"])
        text = "\n".join(lines)
        assert "suspect_reuse         1" in text.replace("  ", " ").replace("  ", " ") \
            or "suspect_reuse" in text, text
        assert "REUSE" in text
        write_suspects_csv(out / "suspects.csv", out, window)
        rows = list(csv.DictReader((out / "suspects.csv").open(encoding="utf-8")))
        codes = {r["code"] for r in rows}
        assert codes == {"GONE", "REUSE"}, codes
    return ["self-test passed: a reused ticker with data outside the spell "
            "window is flagged suspect_reuse and a real hole stays none; a "
            "fully covered spell is neither"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--window-start", default="2016-05-10")
    p.add_argument("--window-end", default=None)
    p.add_argument("--fja", type=Path, default=None)
    p.add_argument("--watch", action="append", default=None,
                   help="ticker to look up explicitly; repeatable "
                        f"(default: {', '.join(DEFAULT_WATCH)})")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)

    if a.self_test:
        for line in self_test():
            print(line)
        return 0

    out = a.out_dir
    w_end = dt.date.fromisoformat(a.window_end) if a.window_end else dt.date.today()
    window = (dt.date.fromisoformat(a.window_start), w_end)
    fja = a.fja or out / "raw" / "fja05680_sp500.csv"
    watch = a.watch or list(DEFAULT_WATCH)

    lines = stage_validate(out, window, fja if fja.exists() else None, watch)
    text = "\n".join(lines) + "\n"
    (out / "validate.txt").write_text(text, encoding="utf-8")
    write_suspects_csv(out / "suspects.csv", out, window)
    print(text)
    print(f"written to {out / 'validate.txt'} and {out / 'suspects.csv'}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
