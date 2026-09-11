#!/usr/bin/env python3
"""MCL and MC5 on the point-in-time universe -- and against the leaky one.

    python -m common.pit_strategy --strategy mcl
    python -m common.pit_strategy --strategy mc5

WHY THIS EXISTS
---------------
`pit_h0` settled the control. H0 -- "buy the screen and trail 8%" -- makes
+$4.72/trade on the stage-2 universe and **-$14.64** on a universe that could
actually have been assembled at 04:30, which is worse than the set stage 2 threw
away. The published +$4.72 was the look-ahead.

That recasts the standing finding, and the recasting is the point of this
module. "Every entry rule we tested made H0 worse" was measured against a
control that was itself an artefact. Whether MCL's rules beat H0 at **-$14.64**
has never been asked, and it is a completely different question from whether
they beat it at +$4.72.

THREE ARMS, AND THE FIRST ONE IS WHAT MAKES THE OTHERS READABLE
---------------------------------------------------------------
`pit_h0` could not separate the leak from the tape: its bracket was built on
EQUS.SUMMARY with daily RVOL/range clauses while its own result came from
XNAS.BASIC with pre-market clauses, so three things differed at once and only
one of them was leakage. This runs all three arms **on the same tape, the same
window slices and the same dates**, so the universe is the only thing that
moves:

  **STAGE-2 (leaky)**   names from `screen_pairs.json`, no entry floor. The
                        universe every published figure in this project came
                        from, re-run here rather than quoted.

  **POINT-IN-TIME**     names from `screen_pairs_pit.json`, every entry floored
                        at that name's own `first_seen`. The honest number, and
                        the only tradeable one.

  **EARLY NAMES ONLY**  the point-in-time subset with `first_seen <= 04:30`,
                        same floor. Isolates whether the names the screen
                        surfaces early behave differently from the ones it
                        surfaces at 08:00.

STAGE-2 minus POINT-IN-TIME is the leak, priced, with the tape held constant.
That subtraction is the deliverable.

THIS DOES NOT REPRODUCE THE PUBLISHED MCL BACKTEST, AND MUST NOT BE READ AS IF
IT DID
------------------------------------------------------------------------------
The published runs load a 2-session frame from the IB `bar_cache`, whose
sessions end at 20:00. These load the 04:00-09:30 Databento slices `screen_sim`
screened, so the warm-up is the prior pre-market rather than the prior regular
session. MACD is an EMA with unbounded memory and the 60-bar volume average
lands on different minutes, so indicator values at 04:00 differ and the trades
will not match trade-for-trade.

That is a feature here and a trap anywhere else. Screening a name on one tape
and trading it on another is the defect `pit_h0` was careful to avoid, so the
arms must share this tape; but it means the STAGE-2 arm is a **fresh control
run**, not a reproduction of `screened_universe_results.md`. Compare arms within
one run of this module. Do not compare either arm to a published figure.

WHAT WOULD MAKE THIS WRONG
--------------------------
**A floor that never fires.** If `not_before` silently did nothing, the
point-in-time arm would quietly become the leaky arm and the leak would price at
zero -- a control whose failure looks exactly like a clean result. So the report
prints `entries suppressed by the floor` and refuses a verdict when the
point-in-time arm shows none, and `test_the_floor_actually_suppresses_entries`
asserts it on a frame built to fire early.

**Too few trades.** MCL's own signal has to fire inside a universe with a median
of 8 names a session, and the EARLY arm draws on a median of one. A thin
positive is not an edge; `MIN_TRADES` gates the verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import date as _date, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.analysis import LIVE
from common.cache_io import BACKTEST_SESSIONS
from common.pit_h0 import DROP, FRICTIONS, first_seen_time, halves_split, score
from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")

QTY = 100
ENTRY_FLOOR_ARM = dtime(4, 30)   # what "early" means, matching H0's entry time

# H0 on these same two universes, from var/reports/pit_h0.txt generated
# 2026-09-11. Quoted so the strategy arms can be read against their own control
# instead of against a bracket from a different tape.
#
# NET AND OFFERED, not per-trade, because the per-trade figure alone cannot be
# compared safely -- see `beats_control()`. `H0_PIT_OFFERED` is also the staleness
# guard: if this run's universe does not offer exactly that many symbol-days, the
# reference belongs to a different universe file and the report says so instead
# of quietly comparing two things.
H0_PIT_NET = -72_086.0        # AS SCREENED, at $4.26
H0_PIT_TRADES = 4_568
H0_PIT_OFFERED = 4_997
H0_KNOWABLE_NET = -10_440.0   # KNOWABLE AT 04:30, at $4.26
H0_KNOWABLE_TRADES = 713
H0_KNOWABLE_OFFERED = 789
H0_REFERENCE_SOURCE = "var/reports/pit_h0.txt, 2026-09-11"

# The warm-up the published backtests use, imported rather than restated: 2
# sessions total means the target day plus one prior. If cache_io changes, this
# changes with it.
WARMUP_SESSIONS = max(0, BACKTEST_SESSIONS - 1)

# Below this the arm gets no verdict. MCL fires on a minority of the names in a
# universe that already has a median of 8 a session, so a handful of trades is
# the expected outcome for the EARLY arm rather than a surprising one.
MIN_TRADES = 30


def engine(name: str):
    """The strategy module and the kwargs its published configuration uses.

    MCL's `LIVE` (use_apex=False, require_macd_pos=True) is imported from
    common.analysis, which is where every other study reads it from. MC5 takes
    its own defaults.
    """
    if name == "mcl":
        from strategy.mcl import mcl as M
        return M, dict(LIVE)
    if name == "mc5":
        from strategy.mc5 import mc5 as M
        return M, {}
    if name == "h0":
        # The CONTROL, run through the same machinery as the rules it controls.
        # `pit_h0` has no stage-2 arm and no unfloored arm, so it could never
        # split its own leak; this is what settles pit_h0_result §6 rather than
        # leaving it flagged. See strategy/premkt/h0_engine.py.
        from strategy.premkt import h0_engine as M
        return M, {}
    sys.exit(f"unknown strategy {name!r} -- expected mcl, mc5 or h0")


# --- universes ---------------------------------------------------------------

def load_pit(path: Path) -> dict[str, list[dict]]:
    rows = json.loads(Path(path).read_text())
    if not rows:
        sys.exit(f"{path} is empty -- run `python -m common.screen_sim` first")
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["date"]].append(r)
    return dict(out)


def load_stage2(path: Path, dates: set[str]) -> dict[str, list[dict]]:
    """The leaky universe, restricted to the dates the simulation covers.

    `screen_pairs.json` spans back to 2023 and carries no `first_seen` -- it
    cannot, the whole point of it is that it was chosen with the day already
    over. The records are given `first_seen=None` so the arm shares one code
    path with the others and the absence is explicit rather than implied by a
    missing key.
    """
    rows = json.loads(Path(path).read_text())
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["date"] in dates:
            out[r["date"]].append({"symbol": r["symbol"], "date": r["date"],
                                   "first_seen": None})
    return dict(out)


def beats_control(net: float, trades: int, offered: int,
                  h0_net: float, h0_trades: int,
                  h0_offered: int) -> tuple[float, float, bool]:
    """Does the strategy beat H0? Returns (per-trade edge, per-day edge, agree).

    TWO DENOMINATORS, AND THEY CAN DISAGREE. H0 takes at most one trade per
    symbol-day; a strategy takes as many as it likes, so per-trade and
    per-opportunity are different questions and the strategy's own selectivity
    is what separates them. A rule that trades half as often looks better per
    trade almost by construction; a rule that trades MORE often can look better
    per trade while losing more money per opportunity.

    That is not hypothetical. On the 2026-09-11 run MC5 came out +1.53/trade
    against H0 and -1.11 per symbol-day -- a sign flip hidden entirely in the
    choice of denominator, and the first version of this report printed only
    the flattering one. When they disagree there is no verdict to draw, and
    `agree` says so.
    """
    per_trade = (net / trades if trades else 0.0) - (h0_net / h0_trades
                                                     if h0_trades else 0.0)
    per_day = (net / offered if offered else 0.0) - (h0_net / h0_offered
                                                     if h0_offered else 0.0)
    return per_trade, per_day, (per_trade > 0) == (per_day > 0)


def is_early(rec: dict) -> bool:
    return bool(rec["first_seen"]) and first_seen_time(rec) <= ENTRY_FLOOR_ARM


def early_only(universe: dict[str, list[dict]]) -> dict[str, list[dict]]:
    out = {}
    for d, recs in universe.items():
        keep = [r for r in recs if is_early(r)]
        if keep:
            out[d] = keep
    return out


def early_trades(pit_rows: list[dict]) -> list[dict]:
    """The EARLY arm, DERIVED from the point-in-time arm rather than re-run.

    The early universe is a strict subset of the point-in-time one, evaluated
    on the same frame with the same per-name floor by a deterministic engine,
    so re-running it could only ever reproduce the same trades at twice the
    cost -- and would introduce the possibility of the two disagreeing, which
    is a failure mode with no upside. Filtering cannot drift.
    """
    return [r for r in pit_rows
            if r["first_seen"]
            and pd.Timestamp(r["first_seen"]).tz_convert(ET).time()
            <= ENTRY_FLOOR_ARM]


# --- running -----------------------------------------------------------------

def run_day(frame: pd.DataFrame, day: str, universe: list[dict], *,
            mod, extra: dict, floor: bool) -> tuple[list[dict], int, int]:
    """One session. Returns (floored rows, UNFLOORED rows, bites, with-bars).

    The unfloored rows were already being computed to count the bites and were
    previously thrown away. Keeping them splits the leak in two -- the universe
    was chosen with the day known, AND names were bought before the screen would
    have shown them -- where the first version of this reported their sum as one
    number and called it "the look-ahead alone".

    THE THIRD RETURN IS NOT BOOKKEEPING. The stage-2 universe was built on
    EQUS.SUMMARY and is being replayed here on XNAS.BASIC; any of its names
    that is not on this tape silently vanishes. If that attrition is heavy and
    unequal between the arms, the leak subtraction is comparing two different
    subsamples while looking exactly like a like-for-like -- so the report
    prints offered and with-bars side by side and the reader can see it.

    THE SECOND ENGINE CALL IS THE CONTROL, not diagnostics, and it is why the
    floored arms cost twice what the leaky one does. An unwired `not_before`
    and a strategy that simply never enters before its name is screened produce
    the identical trade list; without running the unfloored version there is
    nothing that can tell them apart, and a floor that silently did nothing
    would price the leak at zero and read as a clean result.

    The metric is `the unfloored run's FIRST entry landed before first_seen`,
    counted per symbol-day. A raw trade-count difference would be ambiguous:
    killing an early entry can free the strategy to take a later one it would
    otherwise have been in a position for, so the count can stay equal or even
    rise while the floor is working perfectly.
    """
    d = _date.fromisoformat(day)
    out: list[dict] = []
    unfloored: list[dict] = []
    bit = 0
    with_bars = 0
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty:
            continue
        with_bars += 1
        nb = first_seen_time(rec) if (floor and rec["first_seen"]) else None
        try:
            if nb is None:
                trades = free = mod.backtest_session(df, d, ET,
                                                     entry_shares=QTY, **extra)
            else:
                free = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                            **extra)
                trades = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                              not_before=nb, **extra)
                if free and min(pd.Timestamp(t.entry_time).tz_convert(ET).time()
                                for t in free) < nb:
                    bit += 1
        except Exception:                                   # noqa: BLE001
            # A session the engine cannot run is dropped, as in every other
            # study here. Both calls are inside the guard together, so they can
            # never disagree about whether the session existed.
            continue
        for src, dst in ((trades, out), (free, unfloored)):
            for t in src:
                row = asdict(t)
                row.update(symbol=rec["symbol"], date=day,
                           first_seen=rec["first_seen"])
                dst.append(row)
    return out, unfloored, bit, with_bars


def needed_symbols(universes: list[dict[str, list[dict]]], days: list[str],
                   warmup: int) -> dict[str, set[str]]:
    """For each slice date, the symbols any arm will want from it.

    A slice is read once and kept only for the names some target day needs --
    its own, or one of the next `warmup` days that will use it for warm-up.
    Without this the cache holds every symbol on the tape for three whole
    sessions, which is hundreds of megabytes for the sake of a few dozen names.
    """
    want: dict[str, set[str]] = defaultdict(set)
    pos = {d: i for i, d in enumerate(days)}
    for uni in universes:
        for d, recs in uni.items():
            i = pos.get(d)
            if i is None:
                continue
            syms = {r["symbol"] for r in recs}
            for j in range(max(0, i - warmup), i + 1):
                want[days[j]] |= syms
    return want


def build_frame(cache: deque, day: str) -> pd.DataFrame:
    """The target day's slice with the warm-up slices in front of it.

    Concatenated in date order and NOT re-indexed. The gap between one
    session's 09:30 and the next session's 04:00 is real and the indicators are
    positional, so a continuous index would be a lie that changed nothing;
    leaving the gap keeps the timestamps true for the session mask, which is
    what bounds entries to `day`.
    """
    parts = [f for _, f in cache]
    return pd.concat(parts).sort_index() if len(parts) > 1 else parts[-1]


# --- reporting ---------------------------------------------------------------

def arm_rows(trades: list[dict], split: str) -> list[str]:
    L = [f"  {'friction':<10}{'trades':>8}{'net':>12}{'per':>9}"
         f"{'win%':>7}{'drop-top-5':>12}{'early':>9}{'late':>9}"]
    for fl, fv in FRICTIONS:
        s = score(trades, split, fv)
        # n/a rather than 0.00 when there are DROP or fewer distinct symbols:
        # the drop then removes the entire arm, and a printed zero would read
        # as "the top names cancelled out" instead of "there was nothing to
        # drop". See the note on pit_h0.score.
        drop = (f"${acct(s['dropped'], 11, 0)}" if s["syms"] > DROP
                else f"{'n/a':>12}")
        L.append(f"  {fl:<10}{s['n']:>8}${acct(s['net'], 11, 0)}"
                 f"${acct(s['per'], 8)}{s['win']:>6.1f}%{drop}"
                 f"${acct(s['early'], 8)}${acct(s['late'], 8)}")
    return L


def tail(name: str, arms: dict, split: str) -> list[str]:
    """The closing sections, shared by every exit path from `render`.

    Factored out because the H0 run returns early -- a control has no control
    to be compared against -- and the caveats are exactly the part that must
    not be dropped from a short report. A reader who sees three arms and no
    "not the published backtest" note is the reader who quotes one against a
    figure from a doc.
    """
    L = ["SIGN STABILITY ACROSS THE FRICTION RANGE", ""]
    for key, label in (("stage2", "STAGE-2"), ("pit", "POINT-IN-TIME"),
                       ("early", "EARLY ONLY")):
        s = {score(arms[key], split, fv)["net"] > 0 for _, fv in FRICTIONS}
        L.append(f"  {label:<16}"
                 f"{'STABLE' if len(s) == 1 else 'FLIPS'} across $1.00-$8.92")

    return L + ["", "WHAT THIS IS NOT", "",
                "  Not out of sample. `holdout.json` was cut over the SCREENED",
                "  universe on 2026-09-07 and is clean for a screen built "
                "after it.",
                "  It has NOT been spent here.",
                "",
                "  Not the published backtest. Different warm-up, different "
                "tape.",
                "  The arms are comparable to each other and to nothing else.",
                "",
                "  Not TradingView's data. The universe reproduces their "
                "columns",
                "  from one Databento dataset at a measured 55.2% capture."]


def render(name: str, arms: dict, suppressed: dict, counts: dict,
           with_bars: dict, split: str, n_days: int, warmup_missing: int,
           elapsed: float, traded_early: int = 0) -> list[str]:
    L = [f"{name.upper()} ON THE POINT-IN-TIME UNIVERSE", "",
         f"  {n_days} sessions, {WARMUP_SESSIONS} session(s) of warm-up, "
         f"{QTY} shares, friction charged per round trip",
         f"  halves split at {split} (derived)",
         f"  elapsed {elapsed:.1f}s"]
    if warmup_missing:
        L.append(f"  {warmup_missing} session(s) ran with less warm-up than "
                 f"asked (no prior slice in the archive)")
    L += ["",
          "  All three arms use THE SAME TAPE, slices and dates, so the",
          "  universe is the only thing that differs between them. None of",
          "  them reproduces the published backtest -- that one warms up on",
          "  the IB cache's 20:00 sessions. Compare arms here to each other,",
          "  never to a figure from a doc.", ""]

    for key, label, note in (
            ("stage2", "STAGE-2 (leaky)",
             "chosen with the session's own daily bar -- the universe every "
             "published figure came from"),
            ("pit", "POINT-IN-TIME",
             "every entry floored at that name's own first_seen -- the "
             "tradeable rule"),
            ("early", "EARLY NAMES ONLY",
             "the point-in-time subset first seen by 04:30, same floor")):
        off, seen = counts[key], with_bars[key]
        pct = f" ({100.0 * seen / off:.0f}%)" if off else ""
        head = (f"  {off:,} symbol-days offered, {seen:,} had bars on this "
                f"tape{pct}")
        if key == "early":
            # Named separately from the coverage line because it is a HIT RATE,
            # not tape coverage, and conflating the two is the error this
            # section was rewritten to remove.
            head += (f"\n  {traded_early:,} of them produced at least one "
                     f"trade")
        L += [label, "", f"  {note}", head, ""] + arm_rows(arms[key], split)
        L += [""]

    ran = with_bars["pit"] or 1
    L += ["IS THE FLOOR CONNECTED TO ANYTHING", "",
          "  symbol-days where the UNFLOORED run's first entry landed before",
          "  that name's own first_seen -- i.e. where the floor bit:",
          "",
          f"    {suppressed['pit']:,} of {with_bars['pit']:,} run "
          f"({100.0 * suppressed['pit'] / ran:.1f}%)", ""]
    if not suppressed["pit"]:
        L += ["  ZERO. Either the floor is not wired up or this strategy never",
              "  enters before its name is screened. Those two produce the",
              "  same trade list and only one of them is a result, so NO",
              "  VERDICT is drawn below. Check `not_before` reaches",
              "  backtest_session before reading anything above.", ""]
        return L + tail(name, arms, split)
    L += ["  Non-zero, so the floor is doing work and the point-in-time arm",
          "  is a different measurement from the leaky one rather than the",
          "  same one relabelled. This percentage is also the look-ahead's",
          "  footprint INSIDE the day, as distinct from the one in the",
          "  universe: it is how often the old runs bought a name before the",
          "  screen would have shown it.", ""]

    s2 = score(arms["stage2"], split, 4.26)
    pit = score(arms["pit"], split, 4.26)
    early = score(arms["early"], split, 4.26)

    L += ["WHAT THE LOOK-AHEAD WAS WORTH, at $4.26 and one tape", ""]
    if s2["n"] < MIN_TRADES or pit["n"] < MIN_TRADES:
        L += [f"  NO VERDICT -- stage-2 n={s2['n']}, point-in-time n={pit['n']},"
              f" and the floor for a verdict is {MIN_TRADES}.",
              "  A difference read off a handful of trades is a difference",
              "  between a handful of trades.", ""]
    else:
        uf = score(arms.get("pit_unfloored", []), split, 4.26)
        L += [f"  STAGE-2                    {acct(s2['per'], 8)}/trade over "
              f"{s2['n']:,}",
              f"  POINT-IN-TIME, no floor    {acct(uf['per'], 8)}/trade over "
              f"{uf['n']:,}",
              f"  POINT-IN-TIME, floored     {acct(pit['per'], 8)}/trade over "
              f"{pit['n']:,}", ""]
        if uf["n"]:
            L += [f"    universe leak  {acct(s2['per'] - uf['per'], 8)}   "
                  f"which names, chosen with the day known",
                  f"    intraday leak  {acct(uf['per'] - pit['per'], 8)}   "
                  f"bought before the screen would have shown them",
                  f"    total          {acct(s2['per'] - pit['per'], 8)}", ""]
        else:
            L += [f"  the leak       {acct(s2['per'] - pit['per'], 8)}/trade",
                  ""]
        L += ["  Everything else is held constant -- same tape, same slices,",
              "  same dates -- so these are the look-ahead alone, which is the",
              "  number `pit_h0` could not isolate because its bracket came",
              "  from a different tape. They are TWO leaks and are reported as",
              "  two: a universe chosen with hindsight is a different mistake",
              "  from buying a name before it was on the list, and they are",
              "  fixed in different places.", ""]
        keep = [(100.0 * with_bars[k] / counts[k]) if counts[k] else 0.0
                for k in ("stage2", "pit")]
        if abs(keep[0] - keep[1]) > 10.0:
            L += ["  CAVEAT, and it weakens the subtraction: the two arms kept",
                  f"  very different shares of what they were offered "
                  f"({keep[0]:.0f}% vs {keep[1]:.0f}%).",
                  "  The stage-2 universe was built on EQUS.SUMMARY and its",
                  "  missing names are not missing at random, so part of this",
                  "  difference is which names survived the tape rather than",
                  "  the look-ahead. Read it as an upper bound.", ""]

    if name == "h0":
        # Comparing the control to itself is not a weak measurement, it is a
        # tautology, and a tautology rendered in the same table as a real
        # comparison is how a reader ends up quoting one as the other.
        L += ["NO CONTROL COMPARISON", "",
              "  This run IS the control. H0 against H0 is +0.00 by",
              "  construction and the section is omitted rather than printed",
              "  as a result. Read the three arms above and the leak split;",
              "  the comparison lives in the MCL and MC5 reports.", ""]
        return L + tail(name, arms, split)

    h0_trade = H0_PIT_NET / H0_PIT_TRADES
    h0_day = H0_PIT_NET / H0_PIT_OFFERED
    L += ["DO THE RULES BEAT THEIR OWN CONTROL", "",
          f"  H0 on this universe, as screened   {acct(h0_trade, 9)}/trade   "
          f"{acct(h0_day, 9)}/symbol-day",
          f"  ({H0_REFERENCE_SOURCE})"]
    if counts["pit"] != H0_PIT_OFFERED:
        L += ["",
              f"  STALE REFERENCE: H0 was scored over {H0_PIT_OFFERED:,} "
              f"symbol-days and this run",
              f"  offered {counts['pit']:,}. The universe file has changed, so "
              "the comparison below",
              "  is between two different universes. Re-run "
              "`python -m common.pit_h0`",
              "  and update the H0_* constants before quoting any of it."]
    L.append("")
    if pit["n"] >= MIN_TRADES:
        per_trade, per_day, agree = beats_control(
            pit["net"], pit["n"], counts["pit"],
            H0_PIT_NET, H0_PIT_TRADES, H0_PIT_OFFERED)
        L += [f"  {name.upper()} POINT-IN-TIME      "
              f"{acct(pit['per'], 9)}/trade   "
              f"{acct(pit['net'] / (counts['pit'] or 1), 9)}/symbol-day",
              f"  vs H0                       {acct(per_trade, 9)}        "
              f"{acct(per_day, 9)}",
              f"  ({pit['n'] / (counts['pit'] or 1):.2f} trades per symbol-day "
              f"against H0's {H0_PIT_TRADES / H0_PIT_OFFERED:.2f})", ""]
        if not agree:
            L += ["  NO VERDICT -- THE TWO DENOMINATORS DISAGREE. Per trade "
                  "and per",
                  "  opportunity give opposite answers, and which one flatters "
                  "the",
                  "  strategy is decided by how often it chooses to trade "
                  "rather than",
                  "  by how well it trades. A rule taking fewer, larger bets "
                  "looks",
                  "  better per trade by construction; one taking more looks "
                  "worse.",
                  "  Neither figure may be quoted alone.", ""]
        elif per_trade > 0 and pit["per"] > 0:
            L += ["  The rules beat the control on BOTH denominators and clear",
                  "  zero. This is the first time that has been true on an",
                  "  honest universe, so it wants the holdout spent on it "
                  "before",
                  "  it is believed -- not another in-sample variation.", ""]
        elif per_trade > 0:
            L += ["  The rules beat the control on both denominators and still",
                  "  lose money. Selection is doing something real; it is not",
                  "  doing enough. A better entry on a universe with no edge in",
                  "  it is still a loss.", ""]
        else:
            L += ["  The rules do NOT beat the control, on either denominator.",
                  "  On the honest universe the signal is worth less than "
                  "buying",
                  "  the screen outright -- the same verdict the old universe",
                  "  gave, which was simply being read against an inflated",
                  "  control.", ""]
    if early["n"] >= MIN_TRADES and pit["n"] >= MIN_TRADES:
        L += ["DO THE EARLY NAMES BEHAVE DIFFERENTLY", "",
              f"  EARLY ONLY     {acct(early['per'], 8)}/trade over "
              f"{early['n']:,}",
              f"  ALL NAMES      {acct(pit['per'], 8)}/trade over "
              f"{pit['n']:,}",
              f"  difference     {acct(early['per'] - pit['per'], 8)}", "",
              "  H0 found the late qualifiers worth $(1.14), i.e. nothing. If",
              "  this differs, the strategy is selecting on something the",
              "  screen's ordering already carries.", ""]

    return L + tail(name, arms, split)


# --- driver ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--strategy", default="mcl",
                   help="mcl or mc5 (one name; run again for the other)")
    p.add_argument("--pairs", default="var/state/screen_pairs_pit.json")
    p.add_argument("--stage2", default="var/state/screen_pairs.json")
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import read_dbn
    from common.screen_sim import window_slices, date_of

    name = a.strategy.strip().lower()
    mod, extra = engine(name)
    out_path = a.out or f"var/reports/pit_{name}.txt"

    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    pit = load_pit(Path(a.pairs))
    days = sorted(d for d in pit if d in slices)
    if a.limit:
        days = days[:a.limit]
    day_set = set(days)

    # Only two universes are RUN. `early` is derived from `pit` afterwards --
    # see early_trades() for why re-running a strict subset is worse than
    # filtering it.
    universes = {"pit": {d: v for d, v in pit.items() if d in day_set},
                 "stage2": load_stage2(Path(a.stage2), day_set)}
    want = needed_symbols(list(universes.values()), days, WARMUP_SESSIONS)

    t0 = time.time()
    arms: dict[str, list[dict]] = {k: [] for k in universes}
    arms["pit_unfloored"] = []
    suppressed = {k: 0 for k in universes}
    counts = {k: 0 for k in universes}
    with_bars = {k: 0 for k in universes}
    early_offered = 0
    cache: deque = deque(maxlen=WARMUP_SESSIONS + 1)
    warmup_missing = 0

    for i, day in enumerate(days, 1):
        try:
            bars = read_dbn(slices[day])
        except Exception as e:                              # noqa: BLE001
            print(f"  {day}: unreadable ({type(e).__name__}: {e})")
            cache.clear()
            continue
        keep = want.get(day, set())
        cache.append((day, bars[bars["symbol"].isin(keep)]))
        if len(cache) < WARMUP_SESSIONS + 1:
            warmup_missing += 1
        frame = build_frame(cache, day)
        for key, uni in universes.items():
            recs = uni.get(day)
            if not recs:
                continue
            counts[key] += len(recs)
            rows, free, bit, seen = run_day(frame, day, recs, mod=mod,
                                            extra=extra,
                                            floor=(key != "stage2"))
            arms[key] += rows
            suppressed[key] += bit
            with_bars[key] += seen
            if key == "pit":
                arms["pit_unfloored"] += free
        early_offered += sum(1 for r in pit.get(day, ()) if is_early(r))
        if i % 25 == 0:
            print(f"  {i}/{len(days)}  {day}  "
                  f"pit {len(arms['pit']):,} / stage2 {len(arms['stage2']):,}")

    arms["early"] = early_trades(arms["pit"])
    counts["early"] = early_offered
    suppressed["early"] = None      # derived: it has no separate run to count
    # THE EARLY ARM IS A SUBSET OF `pit`, WHICH HAD BARS FOR EVERYTHING IT WAS
    # OFFERED, so its with-bars count is its offered count. The first version
    # put the number of symbol-days that produced TRADES here instead, and
    # printed it in the same column, under the same words, as the other arms'
    # bar coverage. It read as 71% tape attrition inside a subset of an arm
    # showing 100% -- an impossible number that nothing flagged, because a hit
    # rate and a coverage rate are both plausible percentages.
    with_bars["early"] = early_offered
    traded_early = len({(t["symbol"], t["date"]) for t in arms["early"]})

    split = halves_split([t["date"] for t in arms["pit"]]
                         or [t["date"] for t in arms["stage2"]])
    emit("\n".join(render(name, arms, suppressed, counts, with_bars, split,
                          len(days), warmup_missing, time.time() - t0,
                          traded_early=traded_early)),
         out_path,
         header=f"common.pit_strategy  strategy={name}  pairs={a.pairs}"
                + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
