#!/usr/bin/env python3
"""Which entry condition blocked a trade, bar by bar.

    python -m common.why_no_entry --symbol TNON --date 2026-09-11 \
                                  --strategy mcl --from 07:20 --to 07:55

WHY THIS EXISTS
---------------
"There was an obvious move and we did not take it" is the most common question
a live session produces, and until now answering it meant reasoning from the
fill log -- which records what the strategy DID and is silent about what it
declined. The fills cannot distinguish a signal that never fired from a signal
that fired and was refused by the position cap, and those have opposite fixes.

This reads the bars the strategy would have seen, runs its OWN `signals()`, and
names the condition that was False. No reimplementation: a condition column is
whatever the strategy module computed, so this cannot drift from the engine.

WHAT IT WILL NOT TELL YOU, AND THE DISTINCTION MATTERS
------------------------------------------------------
**A near miss is not a foregone trade.** A bar where four of five conditions
held is a bar where the rule said no. Whether a trade would have happened had
the fifth held also depends on state this module cannot see:

  * whether the strategy was already in a position on that symbol;
  * whether the shared concurrency cap was full at that minute -- live, 29% of
    buy attempts were refused by it;
  * whether the broker would have accepted the order at all (2 of 8 watchlist
    names on 2026-09-11 were refused as closing-only).

So the output says which condition was the SOLE blocker and how often, and
never says "it would have traded". Cross-check the fill log for the cap.

**A condition that fails alongside three others tells you nothing about
itself.** A bar failing four conditions is not evidence against any one of
them. Only the sole-blocker count is diagnostic, and it is reported separately
from the raw block count for exactly that reason.

WARM-UP IS CHECKED, NOT ASSUMED
-------------------------------
MCL's volume floor is a 60-bar shifted mean and its MACD is an EMA. Handed a
single session, the first hour of conditions is computed from a cold start and
`c_floor` is NaN -- which renders as False and would be reported as the blocker
on every early bar, confidently and wrongly. So the frame must carry a prior
session, and if it does not this refuses to draw conclusions rather than
printing a plausible table.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.cache_io import SHARED_DURATION, SHARED_END_HHMM, window_dir
from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")

# MCL's longest lookback is the 60-bar volume average; MACD's slow EMA is 26.
# A session with fewer prior bars than this cannot produce trustworthy
# conditions on its early bars.
MIN_WARMUP_BARS = 60


def engine(name: str):
    if name == "mcl":
        from strategy.mcl import mcl as M
        return M, ("c_macd", "c_mfi", "c_rsi", "c_vol", "c_floor")
    if name == "mc5":
        from strategy.mc5 import mc5 as M
        return M, ("c_rsi", "c_ema", "c_macd")
    sys.exit(f"unknown strategy {name!r} -- expected mcl or mc5")


def explain(name: str) -> dict[str, str]:
    """One line per condition, in the rule's own terms."""
    from strategy.mcl import mcl as MCL
    if name == "mcl":
        return {
            "c_macd": f"MACD above its signal AND above zero",
            "c_mfi": f"MFI rising over {MCL.TREND_LOOKBACK} bars",
            "c_rsi": f"RSI rising over {MCL.TREND_LOOKBACK} bars",
            "c_vol": f"this bar's volume >= {MCL.VOL_MULTIPLE:g}x the PREVIOUS "
                     f"bar's",
            "c_floor": f"the previous bar's volume >= "
                       f"{MCL.FLOOR_FRACTION:g} x the {MCL.FLOOR_AVG_LEN}-bar "
                       f"average",
        }
    from strategy.mc5 import mc5 as MC5
    return {
        "c_rsi": f"RSI rate-of-change >= {MC5.ENTRY_RSI_ROC_PCT:g}%",
        "c_ema": "fast EMA above slow EMA",
        "c_macd": "MACD above its signal",
    }


def load_bars(symbol: str, day: str, cache: Path, csv: str | None):
    """The bars, plus how many of them precede the session under test."""
    if csv:
        df = pd.read_csv(csv, index_col=0, parse_dates=[0])
    else:
        from common.cache_io import load_cached_bars
        d = window_dir(cache, SHARED_DURATION, SHARED_END_HHMM)
        df = load_cached_bars(d, symbol, day)
        if df is None:
            sys.exit(
                f"no cached bars for {symbol} {day} under {d}.\n"
                f"Fetch them first:\n"
                f'  python -c "import json,pathlib; '
                f"pathlib.Path('var/state/one_pair.json').write_text("
                f"json.dumps([{{'symbol':'{symbol}','date':'{day}'}}]))\"\n"
                f"  python -m common.data_ib --pairs var/state/one_pair.json")
    df.index = (df.index.tz_localize("UTC") if df.index.tz is None
                else df.index.tz_convert("UTC"))
    df = df.sort_index()
    local = df.index.tz_convert(ET)
    target = _date.fromisoformat(day)
    return df, int((local.date < target).sum())


def rows(sig: pd.DataFrame, day: str, mod, conds: tuple[str, ...],
         lo: dtime, hi: dtime) -> list[dict]:
    local = sig.index.tz_convert(ET)
    m = ((local.date == _date.fromisoformat(day))
         & (local.time >= mod.SESSION_START) & (local.time < mod.SESSION_END))
    out = []
    for i, keep in enumerate(m):
        if not keep:
            continue
        r = sig.iloc[i]
        failed = [c for c in conds if not bool(r.get(c, False))]
        t = local[i].time()
        out.append({"i": i, "t": local[i], "in_window": lo <= t <= hi,
                    "failed": failed, "entry": bool(r.get("entry", False)),
                    "close": float(r["close"]), "volume": float(r["volume"])})
    return out


def render(name: str, symbol: str, day: str, recs: list[dict],
           conds: tuple[str, ...], warmup: int, lo: dtime, hi: dtime,
           mod) -> list[str]:
    why = explain(name)
    L = [f"WHY NO ENTRY -- {name.upper()} on {symbol}, {day}", "",
         f"  {len(recs)} in-session bars, {mod.SESSION_START}-{mod.SESSION_END} ET",
         f"  {warmup} bars of warm-up before the session", ""]

    if warmup < MIN_WARMUP_BARS:
        return L + [
            "REFUSING TO DIAGNOSE", "",
            f"  Only {warmup} bars precede this session, against the "
            f"{MIN_WARMUP_BARS} the",
            "  longest lookback needs. The early conditions would be computed",
            "  from a cold start -- the volume floor is NaN, which renders as",
            "  False and would be named as the blocker on every early bar,",
            "  confidently and wrongly.",
            "",
            "  Re-fetch with a prior session in the frame and run this again."]

    fired = [r for r in recs if r["entry"]]
    L += [f"  entry signal fired on {len(fired)} bar(s)"
          + (": " + ", ".join(r["t"].strftime("%H:%M") for r in fired[:8])
             if fired else ""), ""]

    # --- the window ---------------------------------------------------------
    win = [r for r in recs if r["in_window"]]
    L += [f"THE WINDOW {lo.strftime('%H:%M')}-{hi.strftime('%H:%M')} ET", ""]
    if not win:
        L += ["  No in-session bars in that window.", ""]
    else:
        L.append(f"  {'time':<7}{'close':>9}{'volume':>12}   blocked by")
        for r in win:
            what = ("ENTRY" if r["entry"]
                    else ", ".join(r["failed"]) if r["failed"] else "-")
            L.append(f"  {r['t'].strftime('%H:%M'):<7}"
                     f"{acct(r['close'], 9)}{r['volume']:>12,.0f}   {what}")
        L.append("")

    # --- who blocked, over the whole session --------------------------------
    blocked = [r for r in recs if not r["entry"]]
    sole: dict[str, int] = {c: 0 for c in conds}
    anyb: dict[str, int] = {c: 0 for c in conds}
    for r in blocked:
        for c in r["failed"]:
            anyb[c] += 1
        if len(r["failed"]) == 1:
            sole[r["failed"][0]] += 1
    n_sole = sum(sole.values())

    L += ["WHO BLOCKED IT, OVER THE WHOLE SESSION", "",
          f"  {len(blocked):,} bars without an entry signal, of which "
          f"{n_sole:,} failed exactly one condition.", "",
          f"  {'condition':<10}{'SOLE blocker':>14}{'blocked at all':>16}   "
          f"the rule"]
    for c in conds:
        L.append(f"  {c:<10}{sole[c]:>14,}{anyb[c]:>16,}   {why[c]}")
    L += ["",
          "  Only the SOLE-blocker column is diagnostic. A bar that failed",
          "  four conditions is not evidence against any one of them, which is",
          "  why the two columns are reported separately.", ""]

    if n_sole:
        top = max(sole, key=lambda c: sole[c])
        if sole[top]:
            L += [f"  The single condition standing alone most often is "
                  f"**{top}** "
                  f"({sole[top]:,} bars): {why[top]}.", ""]

    L += ["WHAT THIS DOES NOT SAY", "",
          "  It does not say a trade would have happened. A bar where four of",
          "  five conditions held is a bar where the rule said no, and whether",
          "  an entry would have followed also depends on state this module",
          "  cannot see: whether the strategy was already in that symbol,",
          "  whether the shared position cap was full that minute, and whether",
          "  the broker would have accepted the order. Check the fill log for",
          "  the cap -- live, 29% of buy attempts were refused by it.", "",
          "  It does not model the entry the live trader would have got. The",
          "  signal is evaluated on the bar's close; the order leaves after it."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--symbol", required=True)
    p.add_argument("--date", required=True, metavar="YYYY-MM-DD")
    p.add_argument("--strategy", default="mcl")
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--csv", default=None,
                   help="read bars from this CSV instead of the cache")
    p.add_argument("--from", dest="lo", default="04:00", metavar="HH:MM")
    p.add_argument("--to", dest="hi", default="09:30", metavar="HH:MM")
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    name = a.strategy.strip().lower()
    mod, conds = engine(name)
    lo = datetime.strptime(a.lo, "%H:%M").time()
    hi = datetime.strptime(a.hi, "%H:%M").time()
    out = a.out or f"var/reports/why_no_entry_{name}_{a.symbol}_{a.date}.txt"

    df, warmup = load_bars(a.symbol, a.date, Path(a.cache), a.csv)
    sig = (mod.signals(df, require_macd_pos=True) if name == "mcl"
           else mod.signals(mod.to_5m(df) if not mod._looks_5m(df) else df))
    recs = rows(sig, a.date, mod, conds, lo, hi)
    emit("\n".join(render(name, a.symbol, a.date, recs, conds, warmup, lo, hi,
                          mod)),
         out, header=f"common.why_no_entry  {name} {a.symbol} {a.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
