#!/usr/bin/env python3
"""The cross-source price check (gate G2) and the split finder.
W14-0003, REGISTERED_h60_v0.md §5.1.

Per membership code, the ratio of our 16:00 close (the last 60-minute bar's
close, Nasdaq prints) to EODHD's daily `close` (split-adjusted) is piecewise
constant, stepping only at splits:

    step        a day-over-day change in the ratio of more than 20% -- the
                first session on the new basis is the SPLIT DATE; a hold
                spanning it is voided (engine.voids_from_splits)
    bad day     between steps, a ratio more than 1% from its segment's median
    mapping     a code with bad days on more than 20% of its eligible
      failure   sessions is the wrong company under that ticker: excluded
                whole, and named
    STOP        bad symbol-days above 2% of all eligible symbol-days: the
                study stops and the data path is diagnosed first

ONE READING THE REGISTRATION DOES NOT SPELL OUT, TAKEN CONSERVATIVELY
--------------------------------------------------------------------
A single wrong day (ratio 1.00, 1.30, 1.00) is two >20% changes. Read
literally that is two "splits" and a one-day segment whose own median is
itself -- so the one bad day passes as good. A real split does not undo
itself. So a step that RETURNS to within 1% of its pre-step level within
REVERSAL_SESSIONS sessions is not a split: the days between are bad
symbol-days. Such reversals are counted and reported beside the splits.
This can only exclude more, never less.

UNVERIFIED DAYS
---------------
A symbol-day with no EODHD close, or whose last bar is not the session's last
slot (a missing 15:30 bar), cannot be checked. It is excluded from every book
and counted separately; it does not count toward the 2% stop, which is about
DISAGREEMENT between two sources, not coverage.
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from strategy.h60.panel import Panel

STEP = 0.20
BAD = 0.01
MAPPING_FAIL = 0.20
STOP_SHARE = 0.02
REVERSAL_SESSIONS = 5
EOD_DIR = Path("var/swing_pit/eod")


@dataclass
class XCheck:
    split_days: set = field(default_factory=set)      # {(symbol, s)}
    bad_days: set = field(default_factory=set)
    unverified_days: set = field(default_factory=set)
    excluded_codes: dict = field(default_factory=dict)  # code -> (symbol, bad share)
    excluded_code_days: set = field(default_factory=set)
    reversals: int = 0
    checked_days: int = 0
    eligible_days: int = 0

    @property
    def bad_share(self) -> float:
        return len(self.bad_days) / self.eligible_days if self.eligible_days else 0.0

    @property
    def stop(self) -> bool:
        return self.bad_share > STOP_SHARE

    @property
    def excluded_days(self) -> set:
        return self.bad_days | self.unverified_days | self.excluded_code_days


def file_stem(code: str) -> str:
    from strategy.swing.pit_universe import file_stem as fs
    return fs(code)


def load_eod(code: str, eod_dir: Path = EOD_DIR) -> dict:
    p = Path(eod_dir) / f"{file_stem(code)}.csv"
    if not p.exists():
        return {}
    out = {}
    with p.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out[dt.date.fromisoformat(r["date"][:10])] = float(r["close"])
            except (ValueError, KeyError, TypeError):
                continue
    return out


def classify(ratios: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """ratios: one code's ratio per checked session, in order. Returns
    (is_split_start, is_bad, reversals)."""
    n = len(ratios)
    split = np.zeros(n, bool)
    bad = np.zeros(n, bool)
    if n == 0:
        return split, bad, 0
    chg = np.r_[0.0, np.abs(ratios[1:] / ratios[:-1] - 1.0)]
    steps = list(np.flatnonzero(chg > STEP))
    reversals = 0
    used = set()
    for k in steps:
        if k in used:
            continue
        before = ratios[k - 1]
        back = [j for j in steps if k < j <= k + REVERSAL_SESSIONS and j not in used
                and abs(ratios[j] / before - 1.0) <= BAD]
        if back:
            j = back[0]
            bad[k:j] = True
            used.update({k, j})
            reversals += 1
        else:
            split[k] = True
    bounds = [0] + [k for k in range(n) if split[k]] + [n]
    for a, b in zip(bounds[:-1], bounds[1:]):
        seg = slice(a, b)
        ok = ~bad[seg]
        if not ok.any():
            continue
        med = np.median(ratios[seg][ok])
        bad[seg] |= np.abs(ratios[seg] / med - 1.0) > BAD
    return split, bad, reversals


def run(panel: Panel, eod_dir: Path = EOD_DIR, loader=None) -> XCheck:
    loader = loader or (lambda code: load_eod(code, eod_dir))
    out = XCheck()
    last_slot = panel.bars.groupby("s")["bar"].max().to_dict()
    eod_cache: dict = {}
    for sym in panel.symbols:
        a = panel.arrays(sym)
        ends = np.flatnonzero(a.last_of_session)
        for_code: dict = {}
        elig_by_code: dict = {}
        for j in ends:
            s = int(a.s[j])
            if not panel.elig[sym][s]:
                continue
            out.eligible_days += 1
            day = panel.sessions[s]
            code = panel.universe.code_on(sym, day)
            elig_by_code[code] = elig_by_code.get(code, 0) + 1
            if code not in eod_cache:
                eod_cache[code] = loader(code)
            eod = eod_cache[code].get(day)
            if eod is None or eod <= 0 or a.bar[j] != last_slot[s]:
                out.unverified_days.add((sym, s))
                continue
            for_code.setdefault(code, []).append((s, a.c[j] / eod))
        for code, rows in for_code.items():
            ss = np.array([r[0] for r in rows])
            rr = np.array([r[1] for r in rows])
            split, bad, rev = classify(rr)
            out.reversals += rev
            out.checked_days += len(rows)
            out.split_days |= {(sym, int(s)) for s in ss[split]}
            out.bad_days |= {(sym, int(s)) for s in ss[bad]}
            # §5.1: "bad days on more than 20% of its ELIGIBLE sessions" --
            # unverified days count in the denominator, not only checked ones
            n_elig = elig_by_code.get(code, len(rows))
            share = bad.sum() / n_elig if n_elig else 0.0
            if share > MAPPING_FAIL:
                out.excluded_codes[code] = (sym, float(share))
                out.excluded_code_days |= {(sym, int(s)) for s in ss}
    return out


def report(x: XCheck, panel: Panel) -> str:
    L = ["H60 CROSS-SOURCE PRICE CHECK -- REGISTERED_h60_v0.md §5.1 (gate G2)", "",
         f"eligible symbol-days          {x.eligible_days:>10,}",
         f"checked against EODHD         {x.checked_days:>10,}",
         f"unverified (no EODHD / no last bar)  {len(x.unverified_days):>6,}",
         f"splits found                  {len(x.split_days):>10,}",
         f"one-off excursions (not splits) {x.reversals:>8,}",
         f"bad symbol-days               {len(x.bad_days):>10,}  "
         f"= {x.bad_share:.3%} of eligible (stop above {STOP_SHARE:.0%})",
         f"codes excluded whole (> {MAPPING_FAIL:.0%} bad): {len(x.excluded_codes)}", ""]
    for code, (sym, share) in sorted(x.excluded_codes.items()):
        L.append(f"  {code:<12} as {sym:<8} {share:.1%} bad")
    by_year: dict = {}
    for sym, s in x.bad_days:
        y = panel.sessions[s].year
        by_year[y] = by_year.get(y, 0) + 1
    if by_year:
        L += ["", "bad symbol-days by year: " + ", ".join(f"{y}: {n}" for y, n in sorted(by_year.items()))]
    L += ["", "VERDICT: " + ("STOP -- the data path is diagnosed before any P&L exists."
                             if x.stop else "PASS -- G2 cleared.")]
    return "\n".join(L)
