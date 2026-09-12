#!/usr/bin/env python3
"""How often do MCL's two volume conditions lock each other out?

    python -m common.volume_interlock
    python -m common.volume_interlock --pairs var/state/traded_pairs.json

THE QUESTION, AND WHY IT IS NOT THE SCREEN'S QUESTION
------------------------------------------------------
On 2026-09-11 MCL declined TNON at 07:35 -- the bar that opened a 13-minute,
15% run -- and the sole blocker was `c_floor`. The bar after it was blocked by
`c_vol`, and so was every bar until the move was over. The two conditions read
the SAME number in opposite directions:

    c_vol     this bar's volume >= 3 x prev_vol       wants prev_vol SMALL
    c_floor   prev_vol          >= 0.5 x trail_avg    wants prev_vol LARGE

Both hold only inside

    0.5 x trail_avg  <=  prev_vol  <=  volume / 3

which is non-empty only when `volume >= 1.5 x trail_avg`, and which narrows as
the trailing average rises through a session. A burst bar has a quiet
predecessor, so it clears the multiple and fails the floor; every bar after it
has a loud predecessor, so it clears the floor and fails the multiple.

**That is one name on one day.** `tnon_no_entry_20260911.md` section 5 specified
the counting that turns it into a rate, and this is it.

THIS DOES NOT DEPEND ON THE SCREEN
-----------------------------------
Every other open question in this project is waiting on the `prior_close`
repair, because it changes WHICH symbol-days the universe contains. This one
does not: the interlock is a property of how two conditions interact WITHIN a
symbol-day, so it is measured per bar on cached bars and the population only
has to be a reasonable sample of the names MCL trades. The pairs file is
stated in the report so the population is never implicit.

THE THREE NUMBERS, AND WHAT EACH CAN AND CANNOT SHOW
------------------------------------------------------
    1. WINDOW EMPTY      bars where volume < 1.5 x trail_avg, among bars that
                         pass every NON-volume condition. On these no
                         prev_vol could have satisfied both, so the interlock
                         is arithmetic rather than bad luck.

    2. THE HAND-OFF      bar N clears c_vol and fails c_floor, and bar N+1
                         does the reverse. This is the shape that costs a RUN
                         rather than a bar, and it is what happened to TNON.

    3. HEADROOM          the distribution of volume / trail_avg on bars where
                         the other three conditions hold. 1.5 is where the
                         window opens; how far above it the mass sits says
                         whether the interlock binds often or rarely.

None of the three says a trade would have been profitable. A bar where four of
five conditions held is a bar where the rule said no, and what the entry would
have been worth is a separate, registered question for `pit_delta`. This
module measures FREQUENCY and nothing else -- deliberately, because the prior
on mechanic changes in this project is poor and a frequency that turns out to
be low ends the line of enquiry cheaply.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from common.report_fmt import acct
from common.report_io import emit

# Where the joint window opens: volume >= OPENS_AT x trail_avg. Derived, not
# chosen -- it falls out of VOL_MULTIPLE and FLOOR_FRACTION, and a test pins
# that it still does if either constant moves.
def opens_at(mcl) -> float:
    return mcl.VOL_MULTIPLE * mcl.FLOOR_FRACTION


def per_session(sig: pd.DataFrame, mcl) -> dict:
    """One symbol-day's bars -> the three counts.

    `sig` is `mcl.signals()` output, which already carries c_macd / c_mfi /
    c_rsi / c_vol / c_floor / prev_vol / trail_avg per bar. Recomputing the
    conditions here would be a second implementation of the entry rule, and
    the two would agree until one of them changed.
    """
    need = ["c_macd", "c_mfi", "c_rsi", "c_vol", "c_floor", "prev_vol",
            "trail_avg", "volume"]
    missing = [c for c in need if c not in sig.columns]
    if missing:
        raise ValueError(f"signals() did not emit {', '.join(missing)}")

    others = sig["c_macd"] & sig["c_mfi"] & sig["c_rsi"]
    # Only bars where a trailing average EXISTS can be judged: early in a
    # session trail_avg is NaN and c_floor is False for a reason that has
    # nothing to do with the interlock. Counting those would inflate every
    # figure here with warm-up.
    warm = sig["trail_avg"].notna() & (sig["trail_avg"] > 0)
    base = others & warm

    ratio = sig["volume"] / sig["trail_avg"]
    empty = base & (ratio < opens_at(mcl))

    # The hand-off: N clears the multiple and fails the floor, N+1 the reverse.
    # Measured on ALL bars, not only those passing the other conditions --
    # the shape is about the two volume rules, and requiring the indicators to
    # agree on BOTH bars would count a different, rarer thing.
    a = sig["c_vol"] & ~sig["c_floor"]
    b = (~sig["c_vol"] & sig["c_floor"]).shift(-1, fill_value=False)
    handoff = a & b & warm

    return {
        "bars": int(len(sig)),
        "judgeable": int(base.sum()),
        "window_empty": int(empty.sum()),
        "handoff": int(handoff.sum()),
        "entries": int(sig["entry"].sum()) if "entry" in sig else 0,
        "ratios": [float(x) for x in ratio[base].dropna()],
    }


def render(rows: list[dict], pairs_path: str, mcl, skipped: int,
           elapsed: float) -> list[str]:
    n_sd = len(rows)
    bars = sum(r["bars"] for r in rows)
    judge = sum(r["judgeable"] for r in rows)
    empty = sum(r["window_empty"] for r in rows)
    hand = sum(r["handoff"] for r in rows)
    entries = sum(r["entries"] for r in rows)
    ratios = sorted(x for r in rows for x in r["ratios"])
    gate = opens_at(mcl)

    L = ["DO MCL'S TWO VOLUME CONDITIONS LOCK EACH OTHER OUT?", "",
         f"  {n_sd:,} symbol-day(s) from {pairs_path}",
         f"  {bars:,} bars, {entries:,} entry signal(s)",
         f"  c_vol needs volume >= {mcl.VOL_MULTIPLE:g}x prev_vol; c_floor "
         f"needs prev_vol >= {mcl.FLOOR_FRACTION:g}x trail_avg",
         f"  so both can hold only when volume >= {gate:g}x trail_avg",
         f"  elapsed {elapsed:.1f}s", ""]
    if skipped:
        L += [f"  {skipped:,} symbol-day(s) had no cached bars and were NOT "
              "tested", ""]

    if not judge:
        return L + [
            "NOTHING JUDGEABLE", "",
            "  No bar passed the three non-volume conditions with a trailing",
            "  average defined. That is not a finding about the interlock --",
            "  it is a population with nothing in it. Check the pairs file",
            "  and the cache window before reading anything into this.", ""]

    L += ["1. IS THE WINDOW ARITHMETICALLY EMPTY?", "",
          "  Among bars passing MACD, MFI and RSI with a trailing average:", "",
          f"  {'judgeable bars':<34}{judge:>10,}",
          f"  {'of those, window EMPTY':<34}{empty:>10,}   "
          f"{empty / judge * 100:.1f}%", "",
          "  On an empty-window bar NO prev_vol could have satisfied both",
          "  conditions. The block is arithmetic, not timing.", ""]

    L += ["2. THE HAND-OFF", "",
          "  Bar N clears the multiple and fails the floor; bar N+1 does the",
          "  reverse. This is what cost TNON its 13-minute run.", "",
          f"  {'hand-off bars':<34}{hand:>10,}",
          f"  {'per symbol-day':<34}{hand / n_sd:>10.2f}",
          f"  {'symbol-days with at least one':<34}"
          f"{sum(1 for r in rows if r['handoff']):>10,}   "
          f"{sum(1 for r in rows if r['handoff']) / n_sd * 100:.1f}%", ""]

    L += ["3. HEADROOM  (volume / trail_avg on judgeable bars)", ""]
    q = [0.10, 0.25, 0.50, 0.75, 0.90]
    for p in q:
        v = ratios[min(int(p * len(ratios)), len(ratios) - 1)]
        mark = "  <- the window opens here" if p == 0.50 else ""
        L.append(f"  p{int(p * 100):<3}{acct(v, 10)}x{mark}")
    above = sum(1 for x in ratios if x >= gate)
    L += ["",
          f"  {above:,} of {len(ratios):,} judgeable bars ({above / len(ratios) * 100:.1f}%) "
          f"clear {gate:g}x", ""]

    L += ["WHAT THIS DOES NOT SAY", "",
          "  It does not say a trade would have been profitable. A bar where",
          "  four of five conditions held is a bar where the rule said no,",
          "  and what the entry would have been worth is a separate question",
          "  for `pit_delta`, registered with its predicted failure first.",
          "",
          "  It does not say the interlock is a defect. Both conditions were",
          "  chosen deliberately; a rule that declines bursts out of nowhere",
          "  may be declining exactly what it should.",
          "",
          "  It is one strategy on one cache window. The population is named",
          "  above rather than assumed, and a different pairs file is a",
          "  different measurement."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default="var/state/traded_pairs.json")
    p.add_argument("--cache", default=None,
                   help="bar cache root (default: the MCL backtest window)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default="var/reports/volume_interlock.txt")
    return p


def main(argv=None) -> int:
    import time
    a = build_parser().parse_args(argv)
    from common.cache_io import load_cached_bars, load_pairs, window_dir
    from strategy.mcl import mcl as MCL

    pairs = load_pairs(Path(a.pairs))
    if not pairs:
        sys.exit(f"{a.pairs} lists no US-equity symbol-days")
    if a.limit:
        pairs = pairs[:a.limit]

    cache = Path(a.cache) if a.cache else window_dir(
        Path("var/cache"), "1 D", "09:30")

    t0 = time.time()
    rows, skipped = [], 0
    for p in pairs:
        bars = load_cached_bars(cache, p["symbol"], p["date"])
        if bars is None or len(bars) < MCL.MIN_BARS_REQUIRED:
            skipped += 1
            continue
        try:
            sig = MCL.signals(bars)
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        r = per_session(sig, MCL)
        r["symbol"], r["date"] = p["symbol"], p["date"]
        rows.append(r)

    if not rows:
        sys.exit(f"no cached bars for any of {len(pairs)} symbol-day(s) under "
                 f"{cache}/. Build the cache first, or pass --cache.")

    emit("\n".join(render(rows, a.pairs, MCL, skipped, time.time() - t0)),
         a.out, header=f"common.volume_interlock  pairs={a.pairs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
