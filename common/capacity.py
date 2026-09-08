#!/usr/bin/env python3
"""How large an order can these names actually absorb?

    python -m common.capacity --trades var/reports/screened/backtest_trades_mcl.csv \
        --cache bar_cache_xnas --day-volume var/reports/day_dollar_volume.csv \
        --out var/reports/capacity_mcl.txt --csv var/reports/capacity_mcl.csv

WHY THIS EXISTS
---------------
common/portfolio.py names capacity as the thing it cannot see:

    "Sizing from capital means 1,500 shares of a $2 stock where the old model
     bought 100. The fill model prices all of them identically, which is false
     for a sub-20m-float small cap in pre-market. Every capital-sized number is
     optimistic by an unmeasured amount that GROWS with size."

common/compound_sim.py caps a position at a share of the symbol-DAY's dollar
volume, which is the right idea at the wrong resolution: the order is not
spread over a day, it is one fill in one minute, and in pre-market that minute
can be three prints.

WHAT IS MEASURED, AND WHAT IS ASSUMED
-------------------------------------
MEASURED: the volume of the minute the fill happens in, on both sides of every
trade the engine took. That is a fact about the tape.

ASSUMED: that trading some fraction of a minute's volume is tolerable. Nothing
here models impact -- no square-root law, no spread widening, no queue. The
participation caps below (1%, 5%, 10%) are conventions, not findings. What the
report gives you is the size that corresponds to each, so that a decision about
impact can be made explicitly rather than smuggled in.

Participation is also measured against a minute that ALREADY CONTAINS our own
100-share fill. At 100 shares that is noise. At the sizes this report prices it
is not, and the true participation of a large order is higher than the number
here -- the tape would have to make room for it.

THE TWO MINUTES THAT MATTER ARE NOT THE SAME MINUTE
---------------------------------------------------
Entries fire on a volume surge, which is the condition. Exits fire on a
trailing stop, which is a falling market and frequently a thinner one. The
binding constraint is the WORSE of the two, and this reports them separately so
that it is visible rather than averaged away.

THE TAPE DECIDES THIS COMPLETELY
--------------------------------
Capacity scales linearly with the volume the cache reports. EQUS.MINI publishes
a median 4.8% of the consolidated tape at 16:00 and 1.5% by 09:30, so a
capacity number measured on it is roughly twenty times too small. Pass
--day-volume and the report states the cache's own capture against the daily
bars, measured rather than assumed, and every number is scaled by nothing --
the ratio is printed so the reader can scale it themselves, because a
correction applied silently is a correction nobody can check.
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from common.cache_io import load_cached_bars
from common.report_io import emit

# Conventions, not findings. See the module docstring.
PARTICIPATION = (1.0, 5.0, 10.0)


@dataclass
class Row:
    symbol: str
    date: str
    entry_time: str
    exit_time: str
    reason: str
    qty: int
    entry_price: float
    net: float
    entry_minute_volume: float | None
    exit_minute_volume: float | None
    entry_window_volume: float | None
    exit_window_volume: float | None
    binding_volume: float | None
    binding_side: str


def _fill_minute(bars: pd.DataFrame, start: pd.Timestamp, minutes: int):
    """Volume of the minute the fill happens in, and of the whole signal bar.

    A close-fill lands in the LAST minute of the strategy's bar that actually
    printed. For a 1-minute strategy the two are the same number; for a
    5-minute one they differ by up to 5x, and the window figure is the
    optimistic reading -- an order does not get to use liquidity from four
    minutes it was not present for.
    """
    end = start + pd.Timedelta(minutes=minutes)
    win = bars[(bars.index >= start) & (bars.index < end)]
    win = win[win["volume"] > 0]
    if win.empty:
        return None, None
    return float(win["volume"].iloc[-1]), float(win["volume"].sum())


def measure(trade: dict, bars: pd.DataFrame, minutes: int) -> Row | None:
    et = pd.Timestamp(trade["entry_time"])
    xt = pd.Timestamp(trade["exit_time"])
    if et.tzinfo is None:
        et = et.tz_localize("UTC")
    if xt.tzinfo is None:
        xt = xt.tz_localize("UTC")

    e_min, e_win = _fill_minute(bars, et, minutes)
    x_min, x_win = _fill_minute(bars, xt, minutes)
    if e_min is None and x_min is None:
        return None

    sides = [v for v in (e_min, x_min) if v is not None]
    binding = min(sides)
    side = "entry" if e_min is not None and binding == e_min else "exit"

    return Row(
        symbol=trade["symbol"], date=trade["date"],
        entry_time=str(trade["entry_time"]), exit_time=str(trade["exit_time"]),
        reason=trade.get("reason", ""), qty=int(trade["qty"]),
        entry_price=float(trade["entry_price"]), net=float(trade["net"]),
        entry_minute_volume=e_min, exit_minute_volume=x_min,
        entry_window_volume=e_win, exit_window_volume=x_win,
        binding_volume=binding, binding_side=side)


def size_at(row: Row, pct: float, equity_pct: float):
    """What one position may be, at a participation cap of `pct` percent.

    Pulled out of the renderer deliberately. While this arithmetic lived
    inside render() the only way to test it was to grep the report text, and a
    mutation that made the cap 100x too generous passed every test -- the
    numbers were still present in the output, just wrong.

    Returns (shares, position dollars, the account that position implies).
    """
    if row.binding_volume is None:
        return None, None, None
    shares = row.binding_volume * pct / 100.0
    notional = shares * row.entry_price
    return shares, notional, notional / (equity_pct / 100.0)


# --- quantiles ---------------------------------------------------------------

def _q(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * p
    f = int(k)
    return vals[f] + (vals[min(f + 1, len(vals) - 1)] - vals[f]) * (k - f)


def _n(v, w=11, d=0):
    return f"{'-':>{w}}" if v is None else f"{v:>{w},.{d}f}"


def _dist(name, vals, d=0):
    return (f"  {name:<26} p10 {_n(_q(vals, .10), 11, d)}  "
            f"p50 {_n(_q(vals, .50), 11, d)}  p90 {_n(_q(vals, .90), 11, d)}")


# --- tape capture control ----------------------------------------------------

def capture_ratios(rows: list[Row], cache: Path, day_volume: Path) -> list[float]:
    """Cache volume for each traded session against its daily bar.

    This is the control on the measurement rather than part of it: if the cache
    holds a fifth of the tape, every capacity figure below is a fifth of the
    truth, and nothing else in the report would say so.
    """
    day: dict[tuple[str, str], float] = {}
    with open(day_volume, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                day[(r["symbol"], r["date"])] = float(r["volume"])
            except (KeyError, ValueError):
                continue
    out = []
    for key in sorted({(r.symbol, r.date) for r in rows}):
        total = day.get(key)
        if not total:
            continue
        bars = load_cached_bars(cache, *key)
        if bars is None or bars.empty:
            continue
        local = bars.index.tz_convert("America/New_York")
        same = bars[local.date == pd.Timestamp(key[1]).date()]
        if same.empty:
            continue
        out.append(float(same["volume"].sum()) / total)
    return out


# --- report ------------------------------------------------------------------

def render(rows: list[Row], missing: int, source: str, minutes: int,
           equity_pct: float, ratios: list[float] | None) -> list[str]:
    L = ["CAPACITY -- how large an order the traded minutes can absorb",
         "",
         f"  trades measured   {len(rows):,}   "
         f"(neither fill minute found in cache: {missing:,})",
         f"  trades            {source}",
         f"  strategy bar      {minutes} minute(s)",
         "",
         "  Volume is measured. Impact is NOT modelled. The participation caps",
         "  below are conventions; the report prices them so the choice is",
         "  explicit.", ""]
    if not rows:
        return L + ["  no trades could be matched to bars -- wrong cache?"]

    if ratios:
        p50 = _q(ratios, .50)
        L += ["TAPE CAPTURE -- the control on everything below", "",
              f"  cache volume / daily-bar volume, over {len(ratios):,} "
              "traded sessions",
              f"    p10 {_q(ratios, .10):.3f}   p50 {p50:.3f}   "
              f"p90 {_q(ratios, .90):.3f}",
              "",
              f"  Every share and dollar figure below is scaled by this. At "
              f"p50 {p50:.2f} the",
              f"  cache carries {p50 * 100:.0f}% of the consolidated tape, so "
              f"true capacity is about",
              f"  {1 / p50:.1f}x what is printed. The correction is NOT applied "
              "-- apply it yourself,",
              "  or re-run on a fuller tape.", ""]
    else:
        L += ["TAPE CAPTURE -- NOT MEASURED", "",
              "  --day-volume was not given, so the cache's share of the",
              "  consolidated tape is unknown and every figure below is a lower",
              "  bound by an unknown factor. On EQUS.MINI that factor is about",
              "  20x. Do not quote these numbers without it.", ""]

    L += ["THE MINUTES WE ACTUALLY TRADE IN", "",
          _dist("entry minute, shares", [r.entry_minute_volume for r in rows]),
          _dist("exit minute, shares", [r.exit_minute_volume for r in rows]),
          _dist("binding side, shares", [r.binding_volume for r in rows]),
          "",
          _dist("entry minute, dollars",
                [None if r.entry_minute_volume is None
                 else r.entry_minute_volume * r.entry_price for r in rows]),
          _dist("exit minute, dollars",
                [None if r.exit_minute_volume is None
                 else r.exit_minute_volume * r.entry_price for r in rows]),
          ""]
    n_exit = sum(1 for r in rows if r.binding_side == "exit")
    L += [f"  the EXIT minute is the thinner of the two on {n_exit:,} of "
          f"{len(rows):,} trades",
          "", ]
    if minutes > 1:
        L += [_dist("entry 5-bar window, shares",
                    [r.entry_window_volume for r in rows]),
              "  (the window is the optimistic reading: an order does not get",
              "   liquidity from minutes it was not present for)", ""]

    L += ["WHAT SIZE FITS, AT EACH PARTICIPATION CAP", "",
          "  shares and dollars a single position could take on the BINDING",
          "  minute, and the account that position implies at "
          f"{equity_pct:.0f}% of equity", ""]
    for p in PARTICIPATION:
        sized = [size_at(r, p, equity_pct) for r in rows]
        shares = [s[0] for s in sized]
        notional = [s[1] for s in sized]
        equity = [s[2] for s in sized]
        over = sum(1 for s, r in zip(shares, rows)
                   if s is not None and r.qty > s)
        L += [f"  cap {p:g}% of the minute",
              _dist("    shares", shares),
              _dist("    position dollars", notional),
              _dist("    implied account", equity),
              f"      the {rows[0].qty}-share position already exceeds this cap "
              f"on {over:,} of {len(rows):,} trades",
              ""]

    L += ["READ IT THIS WAY", "",
          "  The p10 row is the number that matters if the strategy has to be",
          "  able to take MOST of its trades: at that account size, a tenth of",
          "  them are already too big for the minute they fill in. The p50 row",
          "  is the size at which half of them are.",
          "",
          "  Nothing here says the edge survives to that size -- it says the",
          "  TAPE does not, which binds first and binds regardless of which",
          "  strategy eventually has an edge. A capacity ceiling is a property",
          "  of the universe, not of the rules.",
          "",
          "  What would make this sharper, in order: a fuller tape (the capture",
          "  ratio above), quote depth rather than trade volume at the fill",
          "  minute, and a measured impact curve from Ben's own larger fills.",
          "  None of the three is assumed here."]
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--trades", required=True, help="engine trade CSV")
    ap.add_argument("--cache", required=True,
                    help="the cache the trades were GENERATED on")
    ap.add_argument("--window", default="3d_to_2000")
    ap.add_argument("--bar-minutes", type=int, default=1,
                    help="the strategy's bar size (MC5 is 5)")
    ap.add_argument("--equity-pct", type=float, default=40.0,
                    help="MAX_EQUITY_PCT -- what one position may take")
    ap.add_argument("--day-volume", default=None,
                    help="day_dollar_volume.csv, for the tape-capture control")
    ap.add_argument("--out", default="var/reports/capacity.txt")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args(argv)

    cache = Path(a.cache)
    cache = cache if cache.name == a.window else cache / a.window
    if not cache.is_dir():
        sys.exit(f"no bar cache at {cache}")

    with open(a.trades, newline="") as fh:
        trades = list(csv.DictReader(fh))

    rows: list[Row] = []
    missing = 0
    loaded: dict[tuple, pd.DataFrame | None] = {}
    for t in trades:
        key = (t["symbol"], t["date"])
        if key not in loaded:
            loaded[key] = load_cached_bars(cache, *key)
        bars = loaded[key]
        if bars is None or bars.empty:
            missing += 1
            continue
        r = measure(t, bars, a.bar_minutes)
        if r is None:
            missing += 1
            continue
        rows.append(r)

    ratios = None
    if a.day_volume and rows:
        ratios = capture_ratios(rows, cache, Path(a.day_volume))

    if a.csv and rows:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()))
            w.writeheader()
            for r in rows:
                w.writerow(asdict(r))
        print(f"wrote {a.csv}")

    if missing > len(rows) * 0.05:
        print(f"\nWARNING: {missing:,} of {missing + len(rows):,} trades had "
              "neither fill minute in the cache. If this strategy trades a bar "
              f"size other than {a.bar_minutes} minute(s), pass --bar-minutes.")

    emit("\n".join(render(rows, missing, a.trades, a.bar_minutes,
                          a.equity_pct, ratios)), a.out,
         header=f"common.capacity  cache={cache}  bar={a.bar_minutes}m  "
                f"equity_pct={a.equity_pct:g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
