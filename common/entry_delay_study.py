#!/usr/bin/env python3
"""What does the live entry delay cost, measured over the whole cache?

    python -m common.entry_delay_study

BEN, 2026-09-09
---------------
"How is the entry not an issue? Had we gone in earlier, we would capture more
of the move."

He was told the exit mattered more, on the strength of ONE session -- six
trades in which the entry figure was a single bad fill netted against four that
flattered it. That cannot rank anything. This does the measurement instead.

WHAT THE DELAY IS
-----------------
Measured live the same morning, on three signals out of three: the order leaves
SIXTY SECONDS after the signal bar closes.

    signal bar 07:26 closed 07:27:00 -> order 07:28:00     WYHG
    signal bar 08:59 closed 09:00:00 -> order 09:01:00     LABT
    signal bar 09:25 closed 09:26:00 -> order 09:27:00     LABT

One of those minutes is the bar closing and is unavoidable. The second is ours,
and the price paid therefore belongs to the NEXT bar. Every backtest figure
this project has published assumes a fill at the signal bar's close.

WHAT IS AND IS NOT ANSWERED
---------------------------
An earlier entry does not buy a longer ride. The trail is seeded at the entry
price but the PEAK is set by the market, so a trade entered a minute sooner
exits at the same place having paid less. The prize is the price gap, not the
move -- which bounds it, and is worth knowing before anyone spends a week on it.

CONTROLS. Both halves, split once at bar_cache's calendar midpoint and never
moved; and drop-top-3 within each variant, because P/L here is concentrated
enough that three trades are routinely the whole result. Read those two columns
before the headline.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import LIVE, MEASURED_FRICTION, load_sessions
from common.report_io import emit
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")

# The calendar midpoint of bar_cache's dates, taken once and hard-coded. NOT
# the median of the TRADES: that moves when the entry rule moves, which would
# make the control a function of the thing under test.
SPLIT = "2026-03-20"
QTY = 100


def run(sessions, delay: int) -> list[tuple]:
    out = []
    for sym, d, df in sessions:
        try:
            for t in MCL.backtest_session(
                    df, datetime.strptime(d, "%Y-%m-%d").date(), ET,
                    entry_delay_bars=delay, entry_shares=QTY, **LIVE):
                out.append((sym, d, t))
        except Exception:                                     # noqa: BLE001
            # A session too short for the warm-up raises rather than returning
            # nothing. Skipping it here keeps the two variants over the SAME
            # set of sessions, which is the only way the difference means
            # anything.
            pass
    return out


def summarise(tag: str, trades: list[tuple], drop: int = 3) -> dict:
    """`real` is net of commission AND the measured $4.26/RT friction, because
    a comparison of two fill assumptions that ignores fill cost is comparing
    two fictions."""
    real = [t.net - MEASURED_FRICTION for _, _, t in trades]
    net = sum(real)
    top = sorted(real, reverse=True)[:drop]
    return {
        "tag": tag, "n": len(trades), "net": net,
        "per": net / len(trades) if trades else 0.0,
        "dropped": net - sum(top),
        "early": sum(r for (_, d, _), r in zip(trades, real) if d < SPLIT),
        "late": sum(r for (_, d, _), r in zip(trades, real) if d >= SPLIT),
    }


def pair(base: list[tuple], late: list[tuple]) -> list[tuple]:
    """Trades that exited on the SAME bar under both fill assumptions.

    Only these are comparable one-for-one. A delayed entry that changes the
    exit is a different trade, not a worse fill on the same one, and averaging
    the two kinds together answers neither question.
    """
    by = {}
    for sym, d, t in base:
        by.setdefault((sym, d, t.exit_time), []).append(t)
    out = []
    for sym, d, t in late:
        bucket = by.get((sym, d, t.exit_time))
        if bucket:
            out.append((bucket.pop(0), t))
    return out


def render(base, late, n_sessions: int) -> list[str]:
    rows = [summarise("entry at signal close", base),
            summarise("entry one bar later", late)]
    L = ["ENTRY DELAY -- what the live minute costs", "",
         f"  {n_sessions} cached sessions, MCL live config, {QTY} shares flat",
         f"  net after tiered commission and the measured "
         f"${MEASURED_FRICTION}/RT friction",
         f"  halves split at {SPLIT}, chosen once. Drop-top-3 within each "
         "variant.", "",
         "  Measured live 2026-09-09: the order leaves 60s after the signal",
         "  bar closes, three signals out of three, so the price paid belongs",
         "  to the next bar.", "",
         f"  {'variant':<24}{'trades':>7}{'net':>10}{'per trade':>11}"
         f"{'drop top 3':>12}{'early':>10}{'late':>10}"]
    for r in rows:
        L.append(f"  {r['tag']:<24}{r['n']:>7}${r['net']:>9,.0f}"
                 f"${r['per']:>10.2f}${r['dropped']:>11,.0f}"
                 f"${r['early']:>9,.0f}${r['late']:>9,.0f}")

    cost = rows[1]["net"] - rows[0]["net"]
    de = rows[1]["early"] - rows[0]["early"]
    dl = rows[1]["late"] - rows[0]["late"]
    L += ["",
          f"  COST OF THE MINUTE   ${cost:>9,.0f} over the whole cache, "
          f"${cost / max(1, rows[0]['n']):.2f} per trade",
          f"  early half ${de:>9,.0f}    late half ${dl:>9,.0f}"]
    if de * dl < 0:
        L += ["  THE SIGN FLIPS BETWEEN HALVES. That is not a stable effect,",
              "  whatever the total says."]

    both = pair(base, late)
    if both:
        diffs = sorted(t.net - b.net for b, t in both)
        worse = sum(1 for x in diffs if x < -0.005)
        better = sum(1 for x in diffs if x > 0.005)
        L += ["",
              f"  of {len(both)} trades that exited on the SAME bar either way:",
              f"    worse with the delay {worse}   better {better}   "
              f"unchanged {len(diffs) - worse - better}",
              f"    median ${diffs[len(diffs) // 2]:.2f}   "
              f"worst ${diffs[0]:.2f}   best ${diffs[-1]:.2f}",
              "",
              "  The MEDIAN is the honest per-trade figure. The total is",
              "  dominated by a handful of trades where a minute happened to",
              "  land well or badly on a fast bar."]

    if min(r["dropped"] for r in rows) < 0:
        L += ["",
              "  BOTH VARIANTS ARE NEGATIVE AFTER DROP-TOP-3. Whatever this",
              "  measures, it is an optimisation inside a strategy with no",
              "  demonstrated edge, and it should not be quoted as one."]

    L += ["",
          "  WHAT THIS DOES NOT SAY. An earlier entry does not buy a longer",
          "  ride: the trail is seeded at the entry price but the peak is set",
          "  by the market, so the trade exits in the same place having paid",
          "  less. The prize is the price gap, not the move."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--delay", type=int, default=1,
                   help="bars of delay to price. 1 is the measured live "
                        "behaviour; 0 reproduces the published backtest")
    p.add_argument("--out", default="var/reports/entry_delay.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    sessions = load_sessions(Path(a.cache))
    emit("\n".join(render(run(sessions, 0), run(sessions, a.delay),
                          len(sessions))),
         a.out, header=f"common.entry_delay_study  cache={a.cache} "
                       f"delay={a.delay}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
