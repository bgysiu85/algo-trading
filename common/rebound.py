#!/usr/bin/env python3
r"""H-R1 -- when a position goes under, does it come back?

    python -m common.rebound --jobs 8

Registered in docs/research/REGISTERED_rebound.md before this file existed.

BEN'S QUESTION, 2026-09-17, as he asked it: "How often does an open position
drop below the entry price and rebound to a profitable position? I have watched
a profitable trade become a loss because of the stop trailing rule allowing the
position to drop below entry price."

AND THE ONE H-P1 LEFT. On 2,904 one-bar trades, 94% of MC5's instant deaths and
82% of MCL's are the trailing stop FIRING -- filling at a median -5.23% against
a stop set at -5%, with under 1% landing more than half a point below it. They
are stop-hits, not gaps. So the deficit may be a stop-WIDTH problem rather than
an entry problem, and nothing here measures what the price did AFTER the stop.

A CENSUS, NOT A RULE
--------------------
No threshold, no verdict, no holdout, nothing to tune toward an answer. The
pre-flight barred money outright because a P&L column would have turned it into
a threshold search; here the question IS about price, so percent excursions are
the subject matter. What stays barred is strategy P&L, book comparisons and
verdict vocabulary -- tests/common/test_rebound.py enforces it.

WHAT IT CANNOT DO, AND THE REPORT SAYS SO ITSELF
------------------------------------------------
It cannot price a wider stop. A wider trail changes the PATH and not just the
exit -- the trail tracks a peak, so widening it moves where it sits at every
later bar -- and a position held longer consumes bars the strategy would have
re-entered on, which is the signal-ordinal rule. Only a TRAIL_PCT re-run turns
this into dollars. The census's whole job is to decide whether that re-run is
worth registering.

NOT A REBUILD OF mfe_exit
-------------------------
That module measures only the HIGH after exit, on the superseded BASIC universe,
with an 8% trail. The LOW is the half that decides whether holding longer would
have recovered or deepened -- which is the entire question. `session_bars` is
imported from it rather than restated, so the two cannot disagree about which
bars a session contains, and a test pins this module's high-side numbers against
`mfe_exit.excursion` on the same trade.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import gate_study as G
from common.entry_shares import QTY
from common.first_entry_skip import _et
from common.mfe_exit import session_bars
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
DATASET = "XNAS.ITCH"
REGISTERED = "docs/research/REGISTERED_rebound.md"

# $4.26 per 100 shares. "Back to entry" is not "back to a profit", and the
# difference is the whole of what a round trip costs.
FRICTION_PER_SHARE = G.MEASURED_FRICTION / QTY
TRAIL_PCT = 5.0            # described in the report; never a parameter here
BOOKS = (("MCL", "mcl"), ("MC5", "mc5"))

# THE EXIT VOCABULARY IS THE STRATEGIES' OWN, and §2.3 is the whole point of
# this census, so it may not be selected by a substring that a rename could
# quietly empty. `strategy/mcl/mcl.py` and `strategy/mc5/mc5.py` both label the
# trailing stop `trailing_stop` and the session-end exit `window_close`; a test
# asserts both literals still appear in both modules, so a rename fails loudly
# here instead of reporting an empty cut as "no trades".
TRAIL_REASON = "trailing_stop"
CLOSE_REASON = "window_close"

def engine_bar_minutes(mod, df) -> int:
    """The grain THIS engine will act on for THIS frame, read off the engine's
    OWN constant and its OWN predicate rather than restated here.

    MCL has no `BAR_MINUTES` and trades the 1-minute tape directly. MC5 carries
    `BAR_MINUTES = 5` and resamples -- **except** when `_looks_5m` says the
    frame already looks 5-minute, which happens on a name so thinly traded that
    its 1-minute bars are more than five minutes apart on the median. There the
    engine uses the frame unresampled, so its bars ARE the tape's bars and the
    offset is zero.

    That case is rare -- 3 of 6,460 MC5 entries on the 2026-09-18 run -- and it
    is exactly why this is derived instead of assumed: a constant in this module
    would have been right 99.95% of the time and silently wrong on the rest, and
    "silently wrong on a few" is how the four-minute shift got shipped in the
    first place.
    """
    n = int(getattr(mod, "BAR_MINUTES", 1))
    if n <= 1:
        return 1
    looks = getattr(mod, "_looks_5m", None)
    return 1 if (looks is not None and bool(looks(df))) else n

# §2.4 (AMENDMENT C, PRE-RUN). Three further falls below the EXIT price,
# declared here before the run and bracketing the shipped 5% trail: half of it,
# it, and double it. All three are reported, none is selected among, and none
# is a candidate for anything -- the point is the ORDER of events, not a value.
# "Did the price get back to entry BEFORE it fell another W%" is a fact about
# the observed path; it is still NOT a price on a wider stop (§3), because a
# wider trail changes where the stop sits at every later bar.
DROPS = (2.5, 5.0, 10.0)


def _seq_key(w: float) -> str:
    return "seq_" + f"{w:g}".replace(".", "_")


def _pct(a: float, b: float) -> float:
    """(a / b - 1) * 100, or NaN when b is not a usable denominator."""
    if b is None or b <= 0 or (isinstance(b, float) and math.isnan(b)):
        return float("nan")
    return (float(a) / float(b) - 1.0) * 100.0


def excursion(bars: pd.DataFrame, trade, bar_minutes: int = 1) -> dict | None:
    """One trade's path, inside its life and after its exit.

    STRICTLY AFTER the reference bar on both sides, the convention `mfe_exit`
    set and for its reasons: the entry fills at its own bar's close, so that
    bar's high has already happened; and where the price went inside the exit
    bar after the fill is not observable at minute granularity. Both choices
    understate, which is the safe direction for a census whose interesting
    outcome is "there was a lot of recovery available".

    `bar_minutes` IS THE GRAIN THE ENGINE TRADED, AND IT IS NOT ALWAYS THE
    TAPE'S. MC5 acts on 5-minute bars while the excursions are read off the
    1-minute tape, and a bar is stamped with its START -- so an MC5 trade
    stamped 09:25 actually fills at that bar's CLOSE, four one-minute bars
    later. Measured against the stamp, those four minutes are counted as
    "after the exit" when they happened BEFORE the fill, and the entry side is
    shifted the same way. The first run of this census did exactly that on
    every MC5 trade; §5's boundary check is what caught it, on 679 window_close
    exits that had tape after them when by construction they cannot.

    So both boundaries are moved to the LAST TAPE BAR of the engine's bar.
    `bar_minutes=1` leaves a 1-minute engine bit-identical.
    """
    off = pd.Timedelta(minutes=int(bar_minutes) - 1)
    entry_t = pd.Timestamp(trade.entry_time) + off
    exit_t = pd.Timestamp(trade.exit_time) + off
    entry_px = float(trade.entry_price)
    exit_px = float(trade.exit_price)

    inside = bars[(bars.index > entry_t) & (bars.index <= exit_t)]
    after = bars[bars.index > exit_t]
    if inside.empty and after.empty:
        # Entered and exited on the session's last bar: no path to describe,
        # and a zero excursion here would read as "it never moved".
        return None

    row = {
        "book": None, "symbol": trade.symbol, "date": trade.date,
        "entry_et": _et(trade.entry_time), "exit_et": _et(trade.exit_time),
        "reason": trade.reason, "bars_held": int(trade.bars_held),
        "bar_min": int(bar_minutes),
        "entry_px": entry_px, "exit_px": exit_px,
        "exit_pct": _pct(exit_px, entry_px),
        "won": bool(float(trade.net) > 0.0),
    }

    # --- inside the trade: Ben's question -------------------------------------
    if inside.empty:
        row.update(mae_pct=float("nan"), went_under=False,
                   back_to_entry=False, back_to_profit=False,
                   bars_to_recover=float("nan"))
    else:
        low = float(inside["low"].min())
        row["mae_pct"] = _pct(low, entry_px)
        under = inside[inside["low"] < entry_px]
        row["went_under"] = bool(not under.empty)
        if under.empty:
            row.update(back_to_entry=False, back_to_profit=False,
                       bars_to_recover=float("nan"))
        else:
            # AFTER it first went under -- a high that happened before the dip
            # is not a recovery from it.
            first_under = under.index[0]
            later = inside[inside.index > first_under]
            hi = float(later["high"].max()) if not later.empty else float("nan")
            row["back_to_entry"] = bool(hi == hi and hi > entry_px)
            row["back_to_profit"] = bool(hi == hi
                                         and hi > entry_px + FRICTION_PER_SHARE)
            rec = later[later["high"] > entry_px] if not later.empty else later
            row["bars_to_recover"] = (float(len(inside[
                (inside.index > first_under) & (inside.index <= rec.index[0])]))
                if not rec.empty else float("nan"))

    # --- after the exit: what H-P1 needs --------------------------------------
    if after.empty:
        # window_close leaves nothing after it, by construction. A non-zero
        # value here would mean the session window is wrong (registration §5).
        row.update(post_hi_pct=float("nan"), post_lo_pct=float("nan"),
                   post_hi_vs_exit=float("nan"), post_lo_vs_exit=float("nan"),
                   recovered_entry=False, recovered_profit=False,
                   bars_to_entry=float("nan"), post_bars=0,
                   **{_seq_key(w): "neither" for w in DROPS})
    else:
        hi, lo = float(after["high"].max()), float(after["low"].min())
        row.update(post_hi_pct=_pct(hi, entry_px), post_lo_pct=_pct(lo, entry_px),
                   post_hi_vs_exit=_pct(hi, exit_px),
                   post_lo_vs_exit=_pct(lo, exit_px),
                   recovered_entry=bool(hi > entry_px),
                   recovered_profit=bool(hi > entry_px + FRICTION_PER_SHARE),
                   post_bars=int(len(after)))
        back = after[after["high"] > entry_px]
        row["bars_to_entry"] = (float(len(after[after.index <= back.index[0]]))
                                if not back.empty else float("nan"))
        # §2.4 -- WHICH CAME FIRST. The max high and the min low say both
        # happened; they do not say in what order, and the order is the whole
        # question. See `seq_block`.
        t_back = back.index[0] if not back.empty else None
        for w in DROPS:
            dn = after[after["low"] <= exit_px * (1.0 - w / 100.0)]
            t_dn = dn.index[0] if not dn.empty else None
            row[_seq_key(w)] = (
                "back" if t_back is not None and (t_dn is None or t_back < t_dn)
                else "drop" if t_dn is not None else "neither")
    return row


# --- one session --------------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
    engines = {name: engine(name) for name in ("mcl", "mc5")}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)

    # `raw` counts every trade the engines produced, BEFORE the last-bar
    # exclusion. The population check has to reconcile against the published
    # book, and reconciling a already-filtered count would print
    # *** DOES NOT MATCH *** on every run and teach everyone to ignore it.
    res = {"rows": [], "symdays": 0, "errors": 0, "error_days": [],
           "raw": {"MCL": 0, "MC5": 0}}
    for rec in universe:
        if not rec.get("first_seen"):
            continue
        s = rec["symbol"]
        df = frame[frame["symbol"] == s]
        if df.empty:
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        try:
            got = {}
            for name, eng in BOOKS:
                mod, extra = engines[eng]
                got[name] = (mod, mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                       not_before=floor, **extra))
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{s} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for name, (mod, trades) in got.items():
            bars = session_bars(df, day, mod)
            bm = engine_bar_minutes(mod, df)
            res["raw"][name] += len(trades)
            for t in trades:
                t.symbol, t.date = s, day
                row = excursion(bars, t, bm)
                if row:
                    row["book"] = name
                    res["rows"].append(row)
    return day, res, ""


# --- reading ------------------------------------------------------------------------

def _f(rows, key):
    v = np.array([r[key] for r in rows], dtype=float)
    return v[~np.isnan(v)]


def _q(v, p):
    return float(np.percentile(v, p)) if len(v) else float("nan")


def share(rows, key) -> float:
    return 100.0 * sum(1 for r in rows if r[key]) / len(rows) if rows else float("nan")


def inside_block(rows: list[dict]) -> list[str]:
    """§2.1 -- Ben's question, as he asked it."""
    L = ["INSIDE THE TRADE: DOES A POSITION THAT GOES UNDER COME BACK?", "",
         "  Read on the 1-MINUTE tape for both books, from the minute after the",
         "  entry bar's close to the exit bar's close. 'Came back' looks",
         "  only at bars after the position FIRST went under -- a high before the",
         "  dip is not a recovery from it. 'To a profit' clears entry plus the",
         f"  measured friction (${FRICTION_PER_SHARE:.4f}/share).", ""]
    for name, _ in BOOKS:
        b = [r for r in rows if r["book"] == name]
        if not b:
            L += [f"  {name}  no trades", ""]
            continue
        under = [r for r in b if r["went_under"]]
        L.append(f"  {name}   {len(b):,} trades")
        L.append(f"    went under entry at any point      {share(b, 'went_under'):5.1f}%"
                 f"   ({len(under):,})")
        if under:
            L.append(f"    of those, traded above entry again {share(under, 'back_to_entry'):5.1f}%")
            L.append(f"    of those, cleared entry + friction {share(under, 'back_to_profit'):5.1f}%")
            rec = _f(under, "bars_to_recover")
            if len(rec):
                L.append(f"    minutes to recover                 "
                         f"p50 {_q(rec, 50):.0f}   p90 {_q(rec, 90):.0f}")
            mae = _f(under, "mae_pct")
            L.append(f"    how far under it went              "
                     f"p50 {_q(mae, 50):+.2f}%   p10 {_q(mae, 10):+.2f}%")
        # The population Ben described is a trade that was UP first and then
        # became a loss. Split it out rather than folding it in.
        for tag, sub in (("winners", [r for r in b if r["won"]]),
                         ("losers", [r for r in b if not r["won"]])):
            if not sub:
                continue
            dipped = [r for r in sub if r["went_under"]]
            line = (f"    {tag:<8} {len(sub):>6,}   went under "
                    f"{share(sub, 'went_under'):5.1f}%")
            if dipped:
                line += f"   came back {share(dipped, 'back_to_entry'):5.1f}%"
            L.append(line)
        L.append("")
    return L


def entries_block(rows: list[dict], symdays: int) -> list[str]:
    """AMENDMENT A (PRE-RUN). Ben's question: MC5 is on 5-minute bars -- 66 in a
    session against MCL's 330 -- so why does it take 65% more trades? Either it
    finds an entry on more symbol-days or it re-enters more often within one,
    and those are different things. Counts only; no P&L, and the two books are
    printed separately rather than ranked."""
    L = ["ENTRIES PER SYMBOL-DAY (AMENDMENT A)", "",
         "  Counted on the trades in this census. A symbol-day is one ticker on",
         "  one session; the universe holds "
         f"{symdays:,} of them that produced bars.", ""]
    for name, _ in BOOKS:
        b = [r for r in rows if r["book"] == name]
        if not b:
            L += [f"  {name}   no trades", ""]
            continue
        per = Counter((r["symbol"], r["date"]) for r in b)
        v = np.array(sorted(per.values()), dtype=float)
        touched = len(per)
        L += [f"  {name}   {len(b):,} entries on {touched:,} symbol-days"
              + (f"   {100.0 * touched / symdays:.1f}% of the universe"
                 if symdays else ""),
              f"        entries per symbol-day it traded   mean {v.mean():.2f}"
              f"   p50 {_q(v, 50):.0f}   p90 {_q(v, 90):.0f}   max {v.max():.0f}",
              ""]
    L += ["  Read this beside the timeframe rather than instead of it: a book",
          "  can carry more trades by reaching more days or by re-entering more",
          "  often on the same day, and only the second is churn.", ""]
    return L


def grain_block(rows: list[dict]) -> list[str]:
    """SCORED. Every excursion here is read off the 1-minute tape, and each
    trade's boundaries are moved to the end of the bar THAT trade's engine
    acted on -- taken from the engine itself (`engine_bar_minutes`), never
    assumed. The claim that leaves is checkable: a trade recorded as acting on
    N-minute bars must have an entry minute on an N-minute boundary. If it does
    not, the offset applied to it was wrong and its numbers are shifted by up to
    N-1 minutes with nothing else looking amiss -- which is what the first run
    of this census did to every MC5 trade.
    """
    L = ["GRAIN CHECK: WAS EACH TRADE MOVED BY ITS OWN ENGINE'S BAR?", "",
         "  Excursions are read on the 1-minute tape. A 5-minute bar is stamped",
         "  with its START, so a trade fills at the END of the bar it names and",
         "  both boundaries are moved there. The grain is read off the engine",
         "  for each symbol and session, because a name thin enough that its",
         "  1-minute bars already look 5-minute is traded UNRESAMPLED and",
         "  must not be moved at all.", ""]
    for name, _ in BOOKS:
        b = [r for r in rows if r["book"] == name]
        if not b:
            L += [f"  {name}   no trades", ""]
            continue
        grains = Counter(int(r.get("bar_min", 1)) for r in b)
        L.append(f"  {name}   " + "   ".join(
            f"{c:,} trades on {g}-minute bars" for g, c in sorted(grains.items())))
        off = [r for r in b
               if int(r.get("bar_min", 1)) > 1
               and int(r["entry_et"].split(":")[1]) % int(r["bar_min"])]
        if off:
            L.append(f"    {len(off):,} of {len(b):,} MOVED BY A BAR THEY ARE NOT ON"
                     " -- those trades are shifted; the rest are not:")
            L += [f"      {r['symbol']:<6} {r['date']}  {r['entry_et']} ET  "
                  f"moved as {r['bar_min']}-minute" for r in off[:5]]
        else:
            L.append("    every trade sits on the boundary of the bar it was "
                     "moved by")
        L.append("")
    return L


def window_block(rows: list[dict]) -> list[str]:
    """§5, SCORED, not decorative.

    A `window_close` exit happens on the session's last tradable bar, so there
    is nothing after it by construction. Any post-exit bar on one of those
    trades means `session_bars` and the engine disagree about where the session
    ends -- and if they disagree there, every number in §2.2 is measured over
    the wrong window. `mfe_exit` ran this check and it caught nothing; it is
    here because a silent window bug would be invisible in the results and
    fatal to them.
    """
    closers = [r for r in rows if r["reason"] == CLOSE_REASON]
    bad = [r for r in closers if r["post_bars"] > 0]
    L = ["BOUNDARY CHECK (§5): DOES THE SESSION END WHERE THE ENGINE THINKS?", "",
         f"  {len(closers):,} trades exited at {CLOSE_REASON}. Bars after the "
         f"exit on those: {len(bad):,}."]
    if not closers:
        L += ["  NO TRADES EXITED AT THE WINDOW. The check did not run, which is",
              "  itself wrong -- both books close out at the window every session.",
              "  Treat §2.2 as unverified.", ""]
    elif bad:
        L += ["  WINDOW MISMATCH. session_bars extends past where the engine",
              "  stopped trading, so every post-exit reading below is measured",
              "  over too wide a window. The first few:"]
        L += [f"    {r['symbol']:<6} {r['date']}  exit {r['exit_et']} ET  "
              f"{r['post_bars']} bar(s) after" for r in bad[:10]] + [""]
    else:
        L += ["  Clean: the window the excursions are measured over is the one",
              "  the engines traded.", ""]
    return L


def after_block(rows: list[dict], title: str, note: str) -> list[str]:
    """§2.2 / §2.3 -- what the price did after the exit."""
    L = [title, "", note, ""]
    for name, _ in BOOKS:
        b = [r for r in rows if r["book"] == name and r["post_bars"] > 0]
        if not b:
            L += [f"  {name}  no trades with tape after the exit", ""]
            continue
        hi, lo = _f(b, "post_hi_vs_exit"), _f(b, "post_lo_vs_exit")
        L.append(f"  {name}   {len(b):,} trades with tape left in the session")
        L.append(f"    price came back to ENTRY           {share(b, 'recovered_entry'):5.1f}%")
        L.append(f"    ... and to entry + friction        {share(b, 'recovered_profit'):5.1f}%")
        bte = _f(b, "bars_to_entry")
        if len(bte):
            L.append(f"    minutes until it did               "
                     f"p50 {_q(bte, 50):.0f}   p90 {_q(bte, 90):.0f}")
        L.append(f"    highest after the exit, vs exit    "
                 f"p50 {_q(hi, 50):+.2f}%   p90 {_q(hi, 90):+.2f}%")
        L.append(f"    LOWEST after the exit, vs exit     "
                 f"p50 {_q(lo, 50):+.2f}%   p10 {_q(lo, 10):+.2f}%")
        # The symmetry question, stated as counts rather than as a verdict.
        up = sum(1 for r in b if r["post_hi_vs_exit"] == r["post_hi_vs_exit"]
                 and r["post_hi_vs_exit"] >= TRAIL_PCT)
        dn = sum(1 for r in b if r["post_lo_vs_exit"] == r["post_lo_vs_exit"]
                 and r["post_lo_vs_exit"] <= -TRAIL_PCT)
        L.append(f"    rose {TRAIL_PCT:.0f}%+ after the exit        {100.0 * up / len(b):5.1f}%"
                 f"   ({up:,})")
        L.append(f"    fell {TRAIL_PCT:.0f}%+ further after it      {100.0 * dn / len(b):5.1f}%"
                 f"   ({dn:,})")
        L.append("")
    return L


def seq_block(rows: list[dict], title: str) -> list[str]:
    """§2.4, AMENDMENT C (PRE-RUN). WHICH CAME FIRST.

    §2.2 reports the highest and the lowest price after the exit, and on these
    names both are usually large -- the same trade goes well above and well
    below. A maximum and a minimum say both happened; they do not say in what
    ORDER, and the order is the whole question. A position given more room
    recovers only if the recovery arrives BEFORE the further fall does.

    So: after the exit, did the price trade back above entry before it fell a
    further W% below the exit? Three W's, declared before the run, bracketing
    the shipped 5% trail. Reported for all three, chosen among for none.

    STILL NOT A PRICE ON A WIDER STOP (§3). A wider trail tracks the peak, so
    it sits somewhere else at every later bar and the position's path is not
    this one. This bounds the opportunity's SHAPE; only a TRAIL_PCT re-run
    turns it into dollars.
    """
    L = [title, "", "  After the exit: did price get back above ENTRY before it fell a",
         "  further W% below the EXIT? 'neither' = it did neither before the",
         "  session ended. Order, not magnitude -- §2.2 has the magnitudes.", ""]
    for name, _ in BOOKS:
        b = [r for r in rows if r["book"] == name and r["post_bars"] > 0]
        if not b:
            L += [f"  {name}  no trades with tape after the exit", ""]
            continue
        L.append(f"  {name}   {len(b):,} trades")
        for w in DROPS:
            c = Counter(r.get(_seq_key(w), "neither") for r in b)
            n = len(b)
            L.append(f"    a further {w:>4.1f}% down   "
                     f"back to entry first {100.0 * c['back'] / n:5.1f}%   "
                     f"fell first {100.0 * c['drop'] / n:5.1f}%   "
                     f"neither {100.0 * c['neither'] / n:5.1f}%")
        L.append("")
    return L


def render(rows, days, symdays, elapsed, jobs, pairs, dataset, errors,
           error_days, raw=None) -> list[str]:
    L = ["THE REBOUND CENSUS: WHEN A POSITION GOES UNDER, DOES IT COME BACK?", "",
         f"  registered  {REGISTERED}",
         f"  universe    {pairs}   bars {dataset}",
         f"  {len(days):,} sessions   {symdays:,} symbol-days   "
         f"{len(rows):,} trades",
         f"  {QTY} shares   elapsed {elapsed:.1f}s on {jobs} worker(s)",
         "  DESCRIPTIVE: no rule, no threshold, no verdict, no P&L.", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped:"]
        L += [f"    {e}" for e in error_days[:10]] + [""]

    raw = raw or {}
    L += ["POPULATION CHECK", ""]
    for name, _ in BOOKS:
        n = sum(1 for r in rows if r["book"] == name)
        got = raw.get(name)
        L.append(f"  {name}   {got if got is None else format(got, ',')} trades"
                 f"   {n:,} with a path to describe"
                 + ("" if got is None else f"   {got - n:,} excluded"))
    # Reconciled on the RAW count. A trade entered on the session's last bar
    # has no path to describe and is dropped from the census, but it was still
    # a trade the book took, and the published figure counts it.
    L += G.population_lines(raw.get("MCL", sum(1 for r in rows
                                               if r["book"] == "MCL")), pairs)
    L += ["", "  Excluded = entered AND exited on the session's last bar: no bar",
          "  after the entry and none after the exit, so there is no path to",
          "  measure. Counted as zero excursion it would read as 'it never",
          "  moved', which is the one thing it does not say.", ""]

    L += entries_block(rows, symdays)

    L += grain_block(rows)

    L += window_block(rows)

    L += inside_block(rows)

    L += after_block(
        rows, "AFTER THE EXIT: ALL TRADES",
        "  From the minute after the exit bar's close to the session's last\n"
        "  minute. The LOW is the\n"
        "  half mfe_exit never measured, and it is the half that says whether\n"
        "  holding on would have recovered or deepened.")

    one_bar = [r for r in rows
               if r["bars_held"] <= 1 and r["reason"] == TRAIL_REASON]
    note = ("  The population H-P1 identified -- 94% of MC5's instant deaths and\n"
            "  82% of MCL's, filling at a median -5.23% against a stop at -5%.\n"
            "  THIS is the cut that decides what gets registered next.")
    if not one_bar:
        L += ["AFTER THE EXIT: THE ONE-BAR TRAILING-STOP EXITS (§2.3)", "",
              "  EMPTY. No trade in either book held one bar and exited at",
              f"  {TRAIL_REASON!r}, which contradicts H-P1's 492 and 2,412. The",
              "  exit vocabulary has moved and this census's headline cut is",
              "  measuring nothing. Do not read the blocks above as answering",
              "  the stop-width question.", ""]
    else:
        L += after_block(one_bar,
                         "AFTER THE EXIT: THE ONE-BAR TRAILING-STOP EXITS (§2.3)",
                         note)

    L += seq_block(rows, "WHICH CAME FIRST, ALL TRADES (§2.4)")
    if one_bar:
        L += seq_block(one_bar,
                       "WHICH CAME FIRST, THE ONE-BAR TRAILING-STOP EXITS (§2.4)")

    L += ["WHAT THIS IS NOT", "",
          "  NOT A PRICE ON A WIDER STOP. A wider trail changes the PATH, not",
          "  just the exit -- it tracks a peak, so widening it moves where it",
          "  sits at every later bar -- and a position held longer consumes bars",
          "  the strategy would have re-entered on. Only a TRAIL_PCT re-run turns",
          "  any of this into dollars.",
          "  NOT A RULE. Every quantity here is outcome-dependent by",
          "  construction, which is fine for a census and disqualifying for a",
          "  gate. Nothing in this report may become an entry or exit condition",
          "  without its own registration.",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.",
          "  NOT BEYOND THE SESSION. Both books exit at window_close, so a",
          "  recovery after 09:30 is not one they could have taken.", ""]
    return L


# --- cli ----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/rebound.txt")
    p.add_argument("--csv", default="var/reports/rebound_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "rebound")

    rows, symdays, errors, error_days = [], 0, 0, []
    raw = {"MCL": 0, "MC5": 0}
    days = sorted(got)
    for day in days:
        r = got[day]
        rows += r["rows"]
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]
        for name in raw:
            raw[name] += r.get("raw", {}).get(name, 0)

    emit("\n".join(render(rows, days, symdays, elapsed, jobs, a.pairs,
                          a.dataset, errors, error_days, raw)), a.out,
         header=f"common.rebound pairs={a.pairs} dataset={a.dataset} "
                f"sessions={len(days)} trades={len(rows)} "
                f"DESCRIPTIVE-NO-RULE-NO-PNL registered={REGISTERED}")
    if rows:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        cols = list(rows[0].keys())
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
