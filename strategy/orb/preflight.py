#!/usr/bin/env python3
"""ORB pre-flight: measurements that can kill the strategy before it is written.

    python -m strategy.orb.preflight \
        --pairs var/state/screen_pairs_consolidated.json var/state/screen_rejects.json \
        --cache bar_cache_db --out var/reports/orb_preflight.txt \
        --csv var/reports/orb_preflight.csv

NO ENTRY LOGIC, NO P/L, NO STRATEGY. `orb_strategy_spec.md` section 10 lists
five measurements that each cost almost nothing and each can invalidate ORB on
its own. Running them first is the point: fifteen of ORB's twenty parameters are
uncalibrated guesses, and every one that gets set from data here is one that
does not get set from a result later.

WHAT IS MEASURED, AND WHICH SPEC SECTION IT ANSWERS
---------------------------------------------------
10.1  The range itself, at ORB_MINUTES of 5, 15 and 30. Width as a fraction of
      price, and how often the MIN_RANGE_PCT / MAX_RANGE_PCT guards would fire.
      If those guards exclude a third of sessions, they are doing the
      strategy's job rather than guarding it, and their defaults are wrong.

10.2  Whether an RTH screen at the end of the range would have selected the
      symbol-day at all. See THE PART THAT CANNOT BE MEASURED below -- this is
      where the honest answer is "partly".

10.3  Trigger counts before any gate: upside break, downside break, both,
      neither. Plus how many triggers close within 0.1% of the level, which is
      what sets ENTRY_BUFFER_PCT, and how many are followed by a qualifying
      retest, which sizes the three RETEST_MODE cells before they are run.

10.4  The R distribution per stop mode, as a fraction of price. This is VW9's
      unresolved question asked in advance: its structure stop produced a
      median R of 9.4% of price and p90 of 20.7%, which is unusable, and
      nobody knew until after the study. `opposite` may be eliminated here
      before it is ever run.

10.5  Time to resolution -- bars from the trigger to the first touch of each
      candidate target. Sets TIME_STOP_BARS if anything does.

THE LEAK CUT, WHICH IS NOT IN THE ORIGINAL SPEC
-----------------------------------------------
Section 10.2b, added 2026-09-07. The screened universe was selected by a stage 2
that reads the session's own daily bar -- including the day's RANGE. ORB trades
a break that CONTRIBUTES to that range, so its exposure to that leak is
structurally larger than a pre-market strategy's, and no RTH strategy has ever
been tested against the rejects here.

That cut usually needs a strategy and a P/L. It does not need one yet: the
TRIGGER RATE is computable with no entry logic at all, and if survivors and
rejects trigger at similar rates then stage 2 was not selecting on the thing
ORB trades. Running it now, before any exit rule exists to be tuned, is
strictly better than running it afterwards.

THE PART THAT CANNOT BE MEASURED FROM THIS CACHE, AND IS NOT FUDGED
-------------------------------------------------------------------
Section 3.1's RTH screen wants `relative_volume_10d_calc >= 5.0`. RVOL at 09:45
compares today's volume so far against the average volume by the same time over
the previous ten sessions. Each bar_cache_db file holds THREE sessions. Ten-day
intraday volume is not in the cache and is not derivable from it.

So this reports `change_from_open`, the price band, and the opening range's own
volume -- and reports RVOL as NOT COMPUTABLE rather than substituting a
two-session approximation and calling it RVOL. A screen simulated on three of
its four rules is not the screen, and the difference would be invisible in
every number downstream of it.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import date as _date, time as dtime
from pathlib import Path

import pandas as pd

from common.indicators import resample_bars

ET = "America/New_York"

RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)

# Spec section 8. Every one of these is a guess until this module replaces it,
# which is why they are read from here rather than hard-coded downstream.
ORB_MINUTES = (5, 15, 30)
TRIGGER_BAR_MINUTES = 5
MIN_RANGE_BARS_FRAC = 10 / 15        # 10 of the 15 one-minute bars
MIN_RANGE_PCT = 0.5
MAX_RANGE_PCT = 25.0
NEAR_LEVEL_PCT = 0.1                 # sets ENTRY_BUFFER_PCT
RETEST_MAX_BARS = 6
ZONE_LO, ZONE_HI = 0.38, 0.62        # V4's retest zone
STOP_RANGE_FRAC = 0.5
ORB_MIN_MOVE_PCT = 5.0               # the RTH screen's change_from_open
PRICE_MIN, PRICE_MAX = 2.0, 20.0


@dataclass
class DayRow:
    symbol: str
    date: str
    population: str
    orb_minutes: int
    status: str = ""                 # OK | NO_RTH | FEW_BARS | TOO_NARROW | TOO_WIDE
    range_bars: int = 0
    # The WHOLE session's RTH bar count, recorded even when the range is
    # rejected. Without it, FEW_BARS cannot be told apart from NO DATA -- a
    # symbol-day with 2 opening bars and 300 RTH bars is a thin open on a name
    # that traded all day; one with 2 and 2 is a hole in the cache. Those are
    # different problems with different fixes and the first run of this module
    # could not distinguish them.
    rth_bars: int = 0
    orb_high: float | None = None
    orb_low: float | None = None
    width_pct: float | None = None
    orb_volume: float | None = None
    # 10.2 -- the RTH screen, as far as it goes
    price_at_range_end: float | None = None
    change_from_open_pct: float | None = None
    in_price_band: bool | None = None
    passes_rth_move: bool | None = None
    # 10.3 -- triggers
    up_trigger: bool = False
    down_trigger: bool = False
    up_trigger_bar: int | None = None       # trigger bars after the range
    up_close_over_pct: float | None = None  # how far beyond the level it closed
    near_level: bool | None = None
    retest_touch: bool = False
    retest_zone: bool = False
    # 10.4 -- R as a fraction of price, per stop mode
    entry_px: float | None = None
    r_structure_pct: float | None = None
    r_opposite_pct: float | None = None
    r_rangefrac_pct: float | None = None
    # 10.5
    bars_to_2r: int | None = None
    bars_to_stop: int | None = None


def load_bars(cache: Path, symbol: str, day: str) -> pd.DataFrame | None:
    p = cache / f"{symbol}_{day}.csv.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt") as fh:
        df = pd.read_csv(fh, index_col=0, parse_dates=True)
    if df.empty:
        return None
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def rth_session(df: pd.DataFrame, day: str) -> pd.DataFrame:
    """One session's RTH minute bars, 09:30 to 16:00 ET."""
    et = df.index.tz_convert(ET)
    want = _date.fromisoformat(day)
    m = ((et.date == want) & (et.time >= RTH_OPEN) & (et.time < RTH_CLOSE))
    out = df[m].copy()
    out.index = out.index.tz_convert(ET)
    return out


def measure_day(sess: pd.DataFrame, symbol: str, day: str, population: str,
                minutes: int) -> DayRow:
    row = DayRow(symbol=symbol, date=day, population=population,
                 orb_minutes=minutes)
    row.rth_bars = len(sess)
    if sess.empty:
        row.status = "NO_RTH"
        return row

    end = dtime((9 * 60 + 30 + minutes) // 60, (9 * 60 + 30 + minutes) % 60)
    opening = sess[[t.time() < end for t in sess.index]]
    row.range_bars = len(opening)
    if row.range_bars < int(minutes * MIN_RANGE_BARS_FRAC):
        # A range built from a handful of bars is not the first N minutes of
        # trading, it is whatever printed. Skipped and COUNTED -- silently
        # trading a partial range is how a plausible wrong answer happens.
        row.status = "FEW_BARS"
        return row

    hi, lo = float(opening["high"].max()), float(opening["low"].min())
    row.orb_high, row.orb_low = hi, lo
    row.orb_volume = float(opening["volume"].sum())
    if lo <= 0:
        row.status = "FEW_BARS"
        return row
    row.width_pct = (hi - lo) / lo * 100.0

    # 10.2, as far as the cache allows. See the module docstring.
    o = float(opening["open"].iloc[0])
    last = float(opening["close"].iloc[-1])
    row.price_at_range_end = last
    row.change_from_open_pct = (last - o) / o * 100.0 if o else None
    row.in_price_band = PRICE_MIN <= last <= PRICE_MAX
    row.passes_rth_move = (row.change_from_open_pct is not None
                           and row.change_from_open_pct > ORB_MIN_MOVE_PCT)

    if row.width_pct < MIN_RANGE_PCT:
        row.status = "TOO_NARROW"
        return row
    if row.width_pct > MAX_RANGE_PCT:
        row.status = "TOO_WIDE"
        return row
    row.status = "OK"

    after = sess[[t.time() >= end for t in sess.index]]
    if after.empty:
        return row
    bars = resample_bars(after, TRIGGER_BAR_MINUTES)
    if bars.empty:
        return row

    # PYTHON floats, not numpy scalars. A numpy bool reaches the CSV looking
    # correct and reaches a SQL Boolean column as an unbindable type, and the
    # `is True` that catches it is not an idiom anyone writes by default.
    closes = [float(v) for v in bars["close"]]
    highs = [float(v) for v in bars["high"]]
    lows = [float(v) for v in bars["low"]]

    for i, c in enumerate(closes):
        if c > hi:
            row.up_trigger = True
            row.up_trigger_bar = i
            row.up_close_over_pct = (c - hi) / hi * 100.0
            row.near_level = bool(row.up_close_over_pct <= NEAR_LEVEL_PCT)
            break
    for c in closes:
        if c < lo:
            row.down_trigger = True
            break

    if not row.up_trigger:
        return row

    i = row.up_trigger_bar
    # Entry is the NEXT bar's open -- the trigger close is a price that has
    # already gone. No slippage here: this is a measurement of structure, not
    # a P/L, and adding a fill assumption would smuggle one in.
    if i + 1 >= len(bars):
        return row
    entry = float(bars["open"].iloc[i + 1])
    row.entry_px = entry

    trig_low = float(bars["low"].iloc[i])
    for name, stop in (("structure", trig_low), ("opposite", lo),
                       ("rangefrac", entry - STOP_RANGE_FRAC * (hi - lo))):
        r = entry - stop
        setattr(row, f"r_{name}_pct", (r / entry * 100.0) if entry else None)

    # 10.3 retest, and 10.5 time to resolution, both measured off the
    # structure stop because that is the spec's baseline.
    win = range(i + 1, min(i + 1 + RETEST_MAX_BARS, len(bars)))
    for j in win:
        if lows[j] <= hi:
            row.retest_touch = True
        if lows[j] <= lo + ZONE_HI * (hi - lo):
            row.retest_zone = True

    r = entry - trig_low
    if r > 0:
        target = entry + 2.0 * r
        for j in range(i + 1, len(bars)):
            if row.bars_to_2r is None and highs[j] >= target:
                row.bars_to_2r = j - i
            if row.bars_to_stop is None and lows[j] <= trig_low:
                row.bars_to_stop = j - i
            if row.bars_to_2r is not None and row.bars_to_stop is not None:
                break
    return row


def pct(vals, q):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return statistics.quantiles(vals, n=100)[q - 1] if len(vals) > 1 else vals[0]


def cache_tape(cache: Path) -> str:
    """Which tape produced this cache, read off its SOURCE.txt.

    WHY THIS IS NOT A CONSTANT. Until 2026-09-08 section 10.1b opened with a
    hardcoded paragraph asserting the bars came from EQUS.MINI and that a low
    bar count was therefore a tape artifact rather than a liquidity fact. The
    first XNAS.BASIC run printed that paragraph verbatim over XNAS.BASIC
    numbers -- a report describing a tape it had not read, telling the reader
    to dismiss the very counts that had just been fixed.

    The dataset is on disk beside the bars (common/bar_cache_build.py writes
    SOURCE.txt precisely so a cache says what it is). Read it. An unreadable
    marker returns "" and the report says it does not know, which is the only
    honest third option.
    """
    marker = cache.parent / "SOURCE.txt"
    if not marker.exists():
        marker = cache / "SOURCE.txt"
    try:
        first = marker.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return ""
    parts = first.split()
    # "databento XNAS.BASIC ohlcv-1m"
    return parts[1] if len(parts) >= 2 and parts[0] == "databento" else ""


def _tape_caveat(tape: str) -> list[str]:
    """The 10.1b preamble, which depends entirely on which tape was read."""
    if tape == "EQUS.MINI":
        return [
            "  READ THE TAPE CAVEAT BELOW BEFORE THE COUNTS. These bars are",
            "  EQUS.MINI, whose measured capture of the consolidated tape is a",
            "  MEDIAN 4.8% at 16:00 and 1.5% by 09:30 (var/reports/",
            "  capture_ratio.txt, capture_intraday.txt). A name that traded",
            "  every minute of the session appears here with roughly 19 bars of",
            "  390. So a LOW BAR COUNT IS THE EXPECTED APPEARANCE OF AN ORDINARY",
            "  NAME ON THIS TAPE, and none of the rows below can be read as a",
            "  fact about liquidity.", ""]
    if not tape:
        return [
            "  TAPE UNKNOWN. No readable SOURCE.txt beside this cache, so this",
            "  report cannot say which tape produced the bars -- and whether a",
            "  low bar count means a thin name or a thin tape depends entirely",
            "  on that. Treat every count below as uninterpreted until the cache",
            "  is identified.", ""]
    return [
            f"  TAPE: {tape}, which carries the FINRA TRF prints. Unlike",
            "  EQUS.MINI (a median 4.8% of the consolidated tape at 16:00, 1.5%",
            "  by 09:30), a low bar count here IS a fact about the name rather",
            "  than an artifact of the feed, so the rows below can be read as",
            "  liquidity.",
            "",
            "  NOT COMPARABLE to any earlier run of this report built on",
            "  EQUS.MINI. The counts moved because the tape changed; nothing",
            "  about the market or the universe did.", ""]


def render(rows: list[DayRow], tape: str = "") -> list[str]:
    L = ["ORB PRE-FLIGHT -- measurements before any entry logic exists", "",
         "  No strategy, no P/L. Each section can invalidate ORB on its own.",
         ""]

    by_min = {}
    for r in rows:
        by_min.setdefault(r.orb_minutes, []).append(r)

    L += ["10.1  THE RANGE, BY ORB_MINUTES", "",
          f"  {'mins':>5} {'days':>8} {'OK':>8} {'few bars':>9} "
          f"{'narrow':>8} {'wide':>7} {'width% p10':>11} {'p50':>8} {'p90':>8}",
          "  " + "-" * 78]
    for m in sorted(by_min):
        rs = by_min[m]
        ok = [r for r in rs if r.status == "OK"]
        w = [r.width_pct for r in rs if r.width_pct is not None]
        L.append(
            f"  {m:>5} {len(rs):>8,} {len(ok):>8,} "
            f"{sum(1 for r in rs if r.status == 'FEW_BARS'):>9,} "
            f"{sum(1 for r in rs if r.status == 'TOO_NARROW'):>8,} "
            f"{sum(1 for r in rs if r.status == 'TOO_WIDE'):>7,} "
            f"{_f(pct(w, 10)):>11} {_f(pct(w, 50)):>8} {_f(pct(w, 90)):>8}")
    for m in sorted(by_min):
        rs = by_min[m]
        excl = sum(1 for r in rs if r.status in ("TOO_NARROW", "TOO_WIDE"))
        if rs and excl / len(rs) > 1 / 3:
            L += ["", f"  ^^ at {m} minutes the range guards exclude "
                      f"{excl/len(rs)*100:.0f}% of symbol-days. Above about a",
                  "     third they are doing the strategy's job rather than "
                  "guarding it,",
                  "     and their defaults are wrong (spec 10.1)."]

    base = by_min.get(15, [])
    ok = [r for r in base if r.status == "OK"]

    # 10.1b. The first run of this module excluded 67% of symbol-days as
    # FEW_BARS and could not say why, which made every number after it
    # unreadable: a 27% subset selected by an unknown mechanism is not a
    # sample of the universe.
    few = [r for r in base if r.status == "FEW_BARS"]
    if few or base:
        L += ["", "10.1b  WHY THE RANGE IS UNUSABLE (15-minute range)", ""]
        L += _tape_caveat(tape)
        empty = [r for r in base if r.rth_bars == 0]
        sparse = [r for r in few if r.rth_bars >= 100]
        thin = [r for r in few if 0 < r.rth_bars < 100]
        thin_note = ("-> indistinguishable: 4.8% of a full day looks like this"
                     if tape == "EQUS.MINI" else "-> genuinely thin all day")
        L += [f"  no RTH bars at all                {len(empty):>8,}   "
              "-> nothing published on this tape",
              f"  few opening bars, >=100 RTH bars  {len(sparse):>8,}   "
              "-> visible all day, invisible at the open",
              f"  few opening bars, <100 RTH bars   {len(thin):>8,}   "
              f"{thin_note}",
              ""]
        if few:
            rb = [r.range_bars for r in few]
            L += [f"  opening bars among the excluded: p10 {_f(pct(rb, 10), 0)}"
                  f"  p50 {_f(pct(rb, 50), 0)}  p90 {_f(pct(rb, 90), 0)} of 15",
                  ""]
        # The threshold is a guess (spec section 8). Show what it costs.
        L += ["  usable ranges at other MIN_RANGE_BARS settings:", ""]
        for k in (3, 5, 8, 10, 12):
            n = sum(1 for r in base if r.range_bars >= k)
            L.append(f"    >= {k:>2} of 15 bars   {n:>8,}  "
                     f"({n/len(base)*100:>5.1f}% of symbol-days)")
        # The verdict depends on the shape of the curve above, so DERIVE it
        # rather than asserting it. The hardcoded version said "even >= 3 of 15
        # leaves most symbol-days out" -- true on EQUS.MINI, false on a fuller
        # tape, and it was printed either way.
        at3 = sum(1 for r in base if r.range_bars >= 3) / len(base)
        at10 = sum(1 for r in base if r.range_bars >= 10) / len(base)
        L += ["", "  MIN_RANGE_BARS is 10 of 15 and was never measured."]
        if at3 < 0.667:
            L += ["  Even >= 3 of 15 leaves most symbol-days out, so the",
                  "  threshold is not what excludes them -- the tape is. No",
                  "  setting of this parameter rescues an opening range built",
                  "  from one print.", "",
                  "  WHAT THIS MEANS FOR ORB, PLAINLY: an opening range is a",
                  "  HIGH and a LOW over fifteen minutes. Computed from a tape",
                  "  that publishes about one print per fifteen minutes at the",
                  "  open, it is not a measurement of anything. This is not a",
                  "  strategy result and it does not reject ORB -- it says ORB",
                  "  cannot be evaluated on these bars. The fix is a fuller",
                  "  tape: XNAS.BASIC carries the FINRA TRF prints, is tier L0",
                  "  (free to retrieve), and its history begins 2024-07-01,",
                  "  which is exactly where the screened universe begins."]
        else:
            L += [f"  {at3*100:.1f}% of symbol-days have >= 3 of 15 opening bars"
                  f" and {at10*100:.1f}% have",
                  "  >= 10, so the curve is steep across that span and the",
                  "  threshold IS the choice -- it decides how much of the",
                  "  universe ORB gives up, and it is still a guess. Set it from",
                  "  the width and trigger numbers, not from a default.", "",
                  "  The range is measurable on this tape. That answers 10.1b",
                  "  and nothing else: a measurable range is a precondition for",
                  "  evaluating ORB, not evidence for it."]

    L += ["", "10.2  THE RTH SCREEN AT THE RANGE END (15-minute range)", ""]
    if ok:
        band = sum(1 for r in ok if r.in_price_band)
        mv = sum(1 for r in ok if r.passes_rth_move)
        both = sum(1 for r in ok if r.in_price_band and r.passes_rth_move)
        L += [f"  symbol-days with a usable range   {len(ok):>8,}",
              f"  inside the $2-20 band             {band:>8,}  "
              f"({band/len(ok)*100:.1f}%)",
              f"  change_from_open > {ORB_MIN_MOVE_PCT:.0f}%             "
              f"{mv:>8,}  ({mv/len(ok)*100:.1f}%)",
              f"  both                              {both:>8,}  "
              f"({both/len(ok)*100:.1f}%)"]
    L += ["",
          "  RVOL: NOT COMPUTABLE from this cache, and not approximated.",
          "  relative_volume_10d_calc needs ten sessions of intraday volume by",
          "  time of day; each cache file holds three. A screen simulated on",
          "  three of its four rules is not the screen, and substituting a",
          "  two-session stand-in would make the gap invisible in every number",
          "  downstream. To close this, load bar_minute for the full history",
          "  and compute the baseline there."]

    L += ["", "10.3  TRIGGERS, BEFORE ANY GATE (15-minute range)", ""]
    if ok:
        up = [r for r in ok if r.up_trigger]
        both_t = sum(1 for r in ok if r.up_trigger and r.down_trigger)
        neither = sum(1 for r in ok if not r.up_trigger and not r.down_trigger)
        L += [f"  upside close beyond the high      {len(up):>8,}  "
              f"({len(up)/len(ok)*100:.1f}%)",
              f"  downside close beyond the low     "
              f"{sum(1 for r in ok if r.down_trigger):>8,}",
              f"  both sides                        {both_t:>8,}",
              f"  neither                           {neither:>8,}"]
        if up:
            near = sum(1 for r in up if r.near_level)
            L += ["",
                  f"  closed within {NEAR_LEVEL_PCT}% of the level      "
                  f"{near:>8,}  ({near/len(up)*100:.1f}%)   "
                  "-> sets ENTRY_BUFFER_PCT",
                  f"  retest touched the level          "
                  f"{sum(1 for r in up if r.retest_touch):>8,}",
                  f"  retest reached the 38-62% zone    "
                  f"{sum(1 for r in up if r.retest_zone):>8,}"]

    L += ["", "10.2b  THE LEAK CUT -- trigger rate, survivors vs rejected", "",
          "  Stage 2 selected this universe using the session's own daily bar,",
          "  including the day's RANGE -- and ORB trades a break that",
          "  contributes to that range. No entry logic is needed to ask",
          "  whether the two populations break out at similar rates.", ""]
    for pop in ("survivors", "rejected"):
        rs = [r for r in base if r.population == pop and r.status == "OK"]
        if not rs:
            L.append(f"  {pop:<12} no evaluable symbol-day")
            continue
        u = sum(1 for r in rs if r.up_trigger)
        L.append(f"  {pop:<12} {len(rs):>7,} usable ranges   "
                 f"{u:>6,} upside triggers   {u/len(rs)*100:>5.1f}%")
    sr = [r for r in base if r.population == "survivors" and r.status == "OK"]
    rr = [r for r in base if r.population == "rejected" and r.status == "OK"]
    if sr and rr:
        a = sum(1 for r in sr if r.up_trigger) / len(sr)
        b = sum(1 for r in rr if r.up_trigger) / len(rr)
        if a > 0:
            L += ["", f"  rejected-day trigger rate is {b/a*100:.0f}% of the "
                      "survivors'"]
            L += (["  Stage 2 barely changes how often a break happens, so it "
                   "is not",
                   "  selecting on the event ORB trades."] if b / a > 0.6 else
                  ["  STAGE 2 IS SELECTING ON THE BREAK ITSELF. It kept the "
                   "days that",
                   "  broke out and discarded the days that did not -- using "
                   "the whole",
                   "  session's range to do it. Any ORB result on this universe "
                   "inherits",
                   "  that, and it is a larger leak than the pre-market "
                   "strategies faced."])

    L += ["", "10.4  R AS A PERCENTAGE OF PRICE, PER STOP MODE", "",
          "  VW9's structure stop had a median R of 9.4% of price and p90 of",
          "  20.7%, which is unusable -- discovered after the study. Asked here",
          "  in advance.", "",
          f"  {'mode':<12} {'n':>7} {'p50':>8} {'p90':>8}",
          "  " + "-" * 38]
    trig = [r for r in ok if r.entry_px]
    for name in ("structure", "opposite", "rangefrac"):
        vals = [getattr(r, f"r_{name}_pct") for r in trig]
        vals = [v for v in vals if v is not None and v > 0]
        L.append(f"  {name:<12} {len(vals):>7,} {_f(pct(vals, 50)):>8} "
                 f"{_f(pct(vals, 90)):>8}")
    med = pct([r.r_opposite_pct for r in trig
               if r.r_opposite_pct and r.r_opposite_pct > 0], 50)
    if med and med > 12.0:
        L += ["", f"  ^^ `opposite` has a median R of {med:.1f}% of price, "
                  "above the spec's",
              "     MAX_R_PCT of 12%. One loss erases many wins and a size cap",
              "     does not fix it. Eliminate the mode rather than cap it."]

    L += ["", "10.5  TIME TO RESOLUTION (trigger bars, 5-minute)", ""]
    t2 = [r.bars_to_2r for r in trig if r.bars_to_2r is not None]
    ts = [r.bars_to_stop for r in trig if r.bars_to_stop is not None]
    L += [f"  reached 2R                        {len(t2):>8,}   "
          f"median {_f(pct(t2, 50))} bars",
          f"  hit the structure stop            {len(ts):>8,}   "
          f"median {_f(pct(ts, 50))} bars"]

    L += ["", "WHAT THIS DOES NOT ANSWER", "",
          "  Nothing here is a P/L and nothing here is an edge. These are",
          "  structural facts about the universe that set five of ORB's",
          "  uncalibrated parameters from data rather than from a result. The",
          "  go/no-go in orb_strategy_spec.md section 11 is unchanged and",
          "  unmet."]
    return L


def _f(v, nd=2):
    return "-" if v is None else f"{v:,.{nd}f}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ORB pre-flight measurements")
    ap.add_argument("--pairs", nargs="+", required=True,
                    help="survivors first, then rejects")
    ap.add_argument("--cache", default="bar_cache_db")
    ap.add_argument("--window", default="3d_to_2000")
    ap.add_argument("--minutes", nargs="+", type=int, default=list(ORB_MINUTES))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default="var/reports/orb_preflight.txt")
    ap.add_argument("--csv", default="var/reports/orb_preflight.csv")
    a = ap.parse_args(argv)

    root = Path(a.cache)
    cache = root if root.name == a.window else root / a.window
    if not cache.is_dir():
        sys.exit(f"no bar cache at {cache}")

    pops = []
    for i, p in enumerate(a.pairs):
        label = "survivors" if i == 0 else "rejected"
        pops.append((label, json.loads(Path(p).read_text())))

    rows: list[DayRow] = []
    seen = 0
    for label, pairs in pops:
        if a.limit:
            pairs = pairs[: a.limit]
        for k, pr in enumerate(pairs, 1):
            sym, day = pr["symbol"], pr["date"]
            df = load_bars(cache, sym, day)
            if df is None:
                continue
            sess = rth_session(df, day)
            for m in a.minutes:
                rows.append(measure_day(sess, sym, day, label, m))
            seen += 1
            if k % 2000 == 0:
                print(f"  {label}: {k:,}/{len(pairs):,}")
    print(f"{seen:,} symbol-days with bars, {len(rows):,} rows")

    if a.csv:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(asdict(DayRow("", "", "", 0))))
            w.writeheader()
            for r in rows:
                w.writerow(asdict(r))
        print(f"wrote {a.csv}")

    tape = cache_tape(cache)
    print(f"tape: {tape or 'UNKNOWN (no readable SOURCE.txt)'}")

    from common.report_io import emit
    emit("\n".join(render(rows, tape)), a.out,
         header=f"strategy.orb.preflight  cache={cache}  tape={tape or 'UNKNOWN'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
