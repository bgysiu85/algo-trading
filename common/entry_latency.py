#!/usr/bin/env python3
"""Where in the signal bar does the fill sit, and what happens after it?

    python -m common.entry_latency --trades var/reports/screened/backtest_trades_mcl.csv \
        --cache bar_cache_db --out var/reports/entry_latency_mcl.txt \
        --csv var/reports/entry_latency_mcl.csv

BEN'S OBSERVATION, 2026-09-08
-----------------------------
Inspecting MCL's losing trades: the entry fills at the close of the bar that
made the move -- "the symbol increased by 60c to over $1 and then the trade was
entered. By then, the next bar we already see the price start to come down."

It fits the numbers. MCL's out-of-sample gross edge is +$0.85/trade, and
buying the top of the signal bar would produce exactly that: winners keep
going, losers mean-revert from the next bar, and the average is nothing.

But it was observed on the LOSERS. The winners also entered at bar close after
a move -- and kept going. So this measures the same things on every trade,
winners and losers side by side, before anyone builds an entry rule on it.

WHAT IS MEASURED, PER TRADE
---------------------------
The SIGNAL BAR is the bar whose close the engine bought (entry_time is that
bar's timestamp; the fill is close + 1 tick).

  fill_pos          (entry - bar low) / (bar high - bar low). 1.0 = bought the
                    top of the bar's range, 0.0 = the bottom. ABOVE 1.0 is
                    possible and means the +1 tick slippage put the fill above
                    the bar's own high -- the engine paid more than any print
                    in that minute.
  bar_move_pct      the signal bar's own move, (close - open) / open.
  runup_pct         how far the name had already moved this session BEFORE
                    the signal bar closed: (bar close - session open) / open.
  mfe_pct           post-entry maximum favourable excursion: the highest high
                    from the NEXT bar to the exit bar, relative to entry.
  mae_pct           the same for the lowest low.
  realised_pct      (exit - entry) / entry -- what the trade actually kept.

  bar_cost          per trade, in dollars: what the signal bar itself cost.
                    (entry - bar open) x qty. This is the money left in the
                    bar; an intrabar entry could recover at most this.
  prev_high_cost    (entry - prior bar's high) x qty, only where the signal
                    bar traded above the prior bar's high. What a resting
                    stop at the prior high would have saved, IF it filled at
                    the level. An upper bound: at the prior bar's close nobody
                    knew this bar would signal, so a resting order would also
                    have fired on bars that did not.

THE COMPARISON THAT DECIDES IT
------------------------------
bar_move_pct against mfe_pct. If the signal bar's move routinely exceeds what
the trade captures after entry, the hypothesis holds ON AVERAGE and an
intrabar entry has room to work. If it holds only for losers, then "the move
was gone by the fill" is a description of losing trades, not a defect in the
entry, and moving the entry earlier admits more of them.

Nothing here is a strategy or a P/L. It is a pre-flight in the same sense as
strategy/orb/preflight.py: it sets or kills a hypothesis before the hypothesis
is written.
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.cache_io import load_cached_bars
from common.report_io import emit

ET = ZoneInfo("America/New_York")
SESSION_START = (4, 0)


@dataclass
class Row:
    symbol: str
    date: str
    entry_time: str
    net: float
    winner: bool
    qty: int
    entry_price: float
    exit_price: float
    bars_held: int
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    fill_pos: float | None
    bar_move_pct: float
    runup_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    realised_pct: float
    bar_cost: float
    prev_high: float | None
    prev_high_cost: float | None


def _pct(a: float, b: float) -> float:
    return (a - b) / b * 100.0 if b else 0.0


def measure(trade: dict, bars: pd.DataFrame) -> Row | None:
    """One trade against the bars it was generated on. None if the signal bar
    cannot be found -- which means the trades and the cache disagree, and
    that is reported as a count rather than silently skipped."""
    et = pd.Timestamp(trade["entry_time"])
    if et.tzinfo is None:
        et = et.tz_localize("UTC")
    xt = pd.Timestamp(trade["exit_time"])
    if xt.tzinfo is None:
        xt = xt.tz_localize("UTC")
    if et not in bars.index:
        return None
    i = bars.index.get_loc(et)
    bar = bars.iloc[i]
    entry = float(trade["entry_price"])
    exit_px = float(trade["exit_price"])
    qty = int(trade["qty"])

    o, h, l, c = (float(bar["open"]), float(bar["high"]),
                  float(bar["low"]), float(bar["close"]))
    rng = h - l
    fill_pos = (entry - l) / rng if rng > 0 else None

    # Session open: the first bar of this session date at or after 04:00 ET.
    local = bars.index.tz_convert(ET)
    day = et.tz_convert(ET).date()
    sess = bars[(local.date == day)
                & ((local.hour * 60 + local.minute)
                   >= SESSION_START[0] * 60 + SESSION_START[1])]
    runup = _pct(c, float(sess["open"].iloc[0])) if len(sess) else None

    # Post-entry, from the NEXT bar to the exit bar inclusive.
    after = bars.iloc[i + 1:]
    after = after[after.index <= xt]
    mfe = _pct(float(after["high"].max()), entry) if len(after) else None
    mae = _pct(float(after["low"].min()), entry) if len(after) else None

    prev_high = float(bars.iloc[i - 1]["high"]) if i > 0 else None
    prev_high_cost = ((entry - prev_high) * qty
                      if prev_high is not None and h > prev_high else None)

    net = float(trade["net"])
    return Row(symbol=trade["symbol"], date=trade["date"],
               entry_time=str(trade["entry_time"]), net=net, winner=net > 0,
               qty=qty, entry_price=entry, exit_price=exit_px,
               bars_held=int(trade["bars_held"]),
               bar_open=o, bar_high=h, bar_low=l, bar_close=c,
               fill_pos=None if fill_pos is None else round(fill_pos, 4),
               bar_move_pct=round(_pct(c, o), 4),
               runup_pct=None if runup is None else round(runup, 4),
               mfe_pct=None if mfe is None else round(mfe, 4),
               mae_pct=None if mae is None else round(mae, 4),
               realised_pct=round(_pct(exit_px, entry), 4),
               bar_cost=round((entry - o) * qty, 2),
               prev_high=prev_high,
               prev_high_cost=(None if prev_high_cost is None
                               else round(prev_high_cost, 2)))


def _q(vals, p):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    vals = sorted(vals)
    k = (len(vals) - 1) * p
    f, cidx = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[f] + (vals[cidx] - vals[f]) * (k - f)


def _f(v, w=8, d=2):
    return f"{'-':>{w}}" if v is None else f"{v:>{w}.{d}f}"


def _dist(name, vals):
    return (f"  {name:<20} p10 {_f(_q(vals, .10))}  p50 {_f(_q(vals, .50))}  "
            f"p90 {_f(_q(vals, .90))}  mean {_f(statistics.fmean([v for v in vals if v is not None]) if any(v is not None for v in vals) else None)}")


def render(rows: list[Row], missing: int, source: str) -> list[str]:
    L = ["ENTRY LATENCY -- where the fill sits in the signal bar, and what follows",
         "",
         f"  trades measured   {len(rows):,}   (signal bar not found in cache: {missing:,})",
         f"  trades            {source}",
         "",
         "  Nothing here is a P/L or a strategy. Winners and losers are shown",
         "  side by side on purpose: the observation that prompted this was made",
         "  on losers alone, and the winners entered the same way.", ""]
    if not rows:
        return L + ["  no trades could be matched to bars -- wrong cache?"]

    def section(tag, rs):
        if not rs:
            return [f"{tag}: none", ""]
        return [
            f"{tag}  ({len(rs):,} trades, ${sum(r.net for r in rs):+,.2f} net)",
            "",
            _dist("fill position 0..1", [r.fill_pos for r in rs]),
            _dist("signal-bar move %", [r.bar_move_pct for r in rs]),
            _dist("run-up before %", [r.runup_pct for r in rs]),
            _dist("post-entry MFE %", [r.mfe_pct for r in rs]),
            _dist("post-entry MAE %", [r.mae_pct for r in rs]),
            _dist("realised %", [r.realised_pct for r in rs]),
            "",
            f"  signal-bar move exceeded post-entry MFE on "
            f"{sum(1 for r in rs if r.mfe_pct is not None and r.bar_move_pct > r.mfe_pct):,} "
            f"of {sum(1 for r in rs if r.mfe_pct is not None):,}",
            f"  fill in top quarter of bar (>= 0.75) on "
            f"{sum(1 for r in rs if r.fill_pos is not None and r.fill_pos >= 0.75):,}",
            ""]

    win = [r for r in rows if r.winner]
    lose = [r for r in rows if not r.winner]
    L += section("ALL", rows) + section("WINNERS", win) + section("LOSERS", lose)

    bar_cost = sum(r.bar_cost for r in rows)
    ph = [r for r in rows if r.prev_high_cost is not None]
    ph_cost = sum(r.prev_high_cost for r in ph)
    net = sum(r.net for r in rows)
    L += ["WHAT THE SIGNAL BAR COST, IN DOLLARS", "",
          f"  net of all trades                       ${net:+,.2f}",
          f"  entry minus signal-bar OPEN, summed     ${bar_cost:+,.2f}   "
          "(upper bound: nobody fills the open)",
          f"  entry minus PRIOR BAR HIGH, summed      ${ph_cost:+,.2f}   "
          f"on {len(ph):,} trades whose bar cleared it",
          "",
          "  The prior-high figure is what a resting stop at the previous bar's",
          "  high would have saved IF it filled at the level -- and it is an",
          "  upper bound twice over: the level is not always offered, and at the",
          "  prior bar's close nobody knew this bar would signal, so the same",
          "  resting order fires on bars that never do. It says how much is",
          "  there, not how much is recoverable.",
          "",
          "READ IT THIS WAY", "",
          "  If 'signal-bar move exceeded post-entry MFE' holds for winners AND",
          "  fill is late on average and an intrabar entry has room to work --",
          "  register one and test it on the criteria.",
          "  If it holds only for losers, 'the move was gone by the fill' is a",
          "  description of losing trades, not a defect in the entry, and an",
          "  earlier entry admits more of them.",
          "",
          "  This does not say what the entry rule should be. Any rule derived",
          "  by reading these trades has to be registered and tested out of",
          "  sample, or it is fitted to them."]
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--trades", required=True, help="engine trade CSV")
    ap.add_argument("--cache", required=True,
                    help="the cache the trades were GENERATED on")
    ap.add_argument("--window", default="3d_to_2000")
    ap.add_argument("--out", default="var/reports/entry_latency.txt")
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
    cache_hits: dict[tuple, pd.DataFrame | None] = {}
    for t in trades:
        key = (t["symbol"], t["date"])
        if key not in cache_hits:
            cache_hits[key] = load_cached_bars(cache, *key)
        bars = cache_hits[key]
        if bars is None or bars.empty:
            missing += 1
            continue
        r = measure(t, bars)
        if r is None:
            missing += 1
            continue
        rows.append(r)

    if a.csv and rows:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()))
            w.writeheader()
            for r in rows:
                w.writerow(asdict(r))
        print(f"wrote {a.csv}")

    emit("\n".join(render(rows, missing, a.trades)), a.out,
         header=f"common.entry_latency  cache={cache}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
