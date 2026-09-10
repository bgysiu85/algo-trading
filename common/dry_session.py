#!/usr/bin/env python3
"""Replay cached sessions through the REAL trader, in dry-run, no IB.

    python -m common.dry_session --strategy mcl mc5 --limit 20
    python -m common.dry_session --strategy mcl --limit 20   # the control

Stage 5 of claude/multi_strategy_trader_spec.md, and the gate before a second
strategy is allowed near a live session.

WHAT IT IS FOR
--------------
Stages 1-4 tested the pieces. This tests the thing: the actual
MCLPaperTrader, its actual step_symbol, its actual concurrency cap and fill
log, driven minute by minute over bars that really happened. The only parts
replaced are the broker and the clock.

TWO QUESTIONS, AND THEY ARE DIFFERENT
-------------------------------------
1. **Does the cap hold across strategies?** Two strategies on one account must
   never have more than MAX_CONCURRENT_POSITIONS open between them. Checked on
   every step, not at the end -- a run that ends flat can still have breached
   it in the middle, and the end state would look perfect.

2. **Did adding a strategy change the first one?** MCL's decisions in a
   two-strategy run must be identical to MCL's decisions alone: same symbols,
   same minutes, same prices. THIS IS THE ONE THAT MATTERS. MCL is the
   strategy with live paper history; if running MC5 alongside it perturbs it,
   every session recorded from then on is measuring something else, and the
   comparison against everything before it quietly breaks.

   The two runs will NOT always agree, and that is not a bug: the cap is
   shared, so MC5 can legitimately take the last slot and deny MCL a trade.
   The report separates those from any other difference, because "denied by
   the cap" is a design consequence and anything else is a defect.

WHAT IT CANNOT SEE
------------------
Fills. Dry-run assumes the marketable limit fills at its own price, which is
the same assumption the backtest makes and the one the live sessions exist to
measure. Nothing here says anything about slippage; it says what the trader
DECIDES, which is the part that has to be right before it is allowed to decide
it with two strategies.

It also cannot see IB pacing, market-data limits, or a rejected order -- the
broker is a stub. Those are live-only facts.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from brokers.ibkr import trader as T
from common import strategy_adapter as SA
from common.analysis import load_sessions
from common.report_io import emit

ET = ZoneInfo("America/New_York")

# How far past the last session end to keep stepping, so a position still
# open at the bell takes its window_close exit rather than being left open
# and silently excluded from the comparison.
TAIL = timedelta(minutes=10)


class _Quote:
    """A two-sided quote built from the bar, so the trailing stop has
    something to read. Deliberately symmetric and tight: this module is not
    trying to model the spread -- common/execution_cost_measured.md does that
    on real quotes -- it is trying to let the decision logic run."""

    def __init__(self):
        self.bid = self.ask = float("nan")

    def at(self, price: float):
        self.bid, self.ask = price, price
        return self


class _NoBroker:
    """Every IB call the dry-run path can reach, and nothing else.

    placeOrder is absent on purpose. If the dry-run branch ever stopped
    short-circuiting, this would raise AttributeError rather than quietly
    doing nothing -- a stub that silently accepts orders would let a live-order
    bug pass a dry run.
    """

    def __init__(self):
        self.errorEvent = _Event()

    def positions(self):
        return []


class _Event:
    def __iadd__(self, _fn):
        return self

    def __isub__(self, _fn):
        return self


def open_positions(states) -> int:
    """How many positions are open ACROSS every strategy.

    A function rather than a comprehension inline in the loop, because the
    thing being asserted is that it counts across strategies -- and a version
    that counted only one would never be caught by a replay, since the trader
    enforces the cap and so no breach ever occurs to detect. A detector can
    only be tested by handing it a breach.
    """
    return sum(1 for s in states if s.position is not None)


def replay(sessions, strategies, on_step=None, max_positions=None):
    """Step every session minute by minute. Returns (decisions, breaches).

    `decisions` is one row per fill-log entry that represents an action, keyed
    so two runs can be compared directly.
    """
    adapters = SA.build_all(strategies)
    decisions: list[tuple] = []
    breaches: list[str] = []
    reasons: Counter = Counter()

    for symbol, date_str, df in sessions:
        log = _Recorder(decisions, symbol)
        tr = T.MCLPaperTrader(_NoBroker(), Path("var/watchlist.txt"), log,
                              dry_run=True, tg=T.notify.Notifier(),
                              strategies=adapters,
                              max_positions=max_positions)
        tr.equity = 22_290.96
        feed = tr.feed_for(symbol)
        feed.contract = object()
        quote = _Quote()
        feed.ticker = quote
        feed.min_tick = 0.01
        states = []
        for a in adapters:
            st = T.SymbolState(symbol=symbol, feed=feed, strategy=a)
            tr.states[(a.name, symbol)] = st
            states.append(st)

        # ONLY the minutes any strategy could act in, plus a short tail so the
        # window_close exit fires. Stepping the whole cached frame -- three
        # days of warm-up -- costs about 4x the time and cannot change a
        # decision: entries are gated on in_session, and a position can only
        # be open because an entry was taken inside one. The FRAME handed to
        # each step is still the full prefix, so every indicator is warmed
        # exactly as it would be live.
        start = min(a.session_start for a in adapters)
        end = max(a.session_end for a in adapters)
        tail = (datetime.combine(datetime.today(), end)
                + TAIL).time()
        local = df.index.tz_convert(ET)
        steps = [i for i, t in enumerate(local)
                 if start <= t.time() < tail]
        for i in steps:
            now_et = local[i].to_pydatetime()
            window = df.iloc[: i + 1]
            quote.at(float(df["close"].iloc[i]))
            # The trader's own cache/pacing is bypassed on purpose: this is a
            # replay, so "the bars available now" is exactly the prefix.
            log.now = now_et.strftime("%Y-%m-%d %H:%M")
            tr.bars = lambda _st, _w=window: asyncio.sleep(0, result=_w)
            for st in states:
                asyncio.run(tr.step_symbol(st, now_et))
            open_now = open_positions(tr.states.values())
            # Against tr.max_positions, NOT the module constant. At cap 3 the
            # constant would flag every legitimate third position as a breach
            # -- a detector failing in the alarming direction, which is how a
            # working session gets abandoned the night it matters.
            if open_now > tr.max_positions:
                breaches.append(
                    f"{symbol} {now_et:%Y-%m-%d %H:%M} — {open_now} open "
                    f"(cap {tr.max_positions})")
            if on_step:
                on_step(tr, now_et)
        for row in log.rows:
            reasons[row[3]] += 1   # row[3] is the STATUS field
    return decisions, breaches, reasons


class _Recorder:
    """A FillLog that keeps rows in memory instead of writing a CSV."""

    def __init__(self, sink: list, symbol: str):
        self.sink = sink
        self.symbol = symbol
        self.rows: list[tuple] = []
        # The SIMULATED minute, set by replay() before each step.
        #
        # Not the row's own ts_et: the trader stamps that with now_et_str(),
        # the real wall clock at write time, which is right in a live session
        # and useless here -- two replays run seconds apart produce rows that
        # differ in every timestamp and therefore compare as 100% changed. The
        # first run of this comparison reported 21 of 32 MCL rows "only in the
        # solo run" for exactly that reason, and every one of them was
        # identical in substance.
        self.now = ""

    def write(self, **row):
        rec = (row.get("strategy", ""), row.get("symbol", self.symbol),
               self.now, row.get("status", ""),
               row.get("action", ""), row.get("reason", ""),
               round(float(row["fill_price"]), 4)
               if row.get("fill_price") is not None else None)
        self.rows.append(rec)
        self.sink.append(rec)

    def close(self):
        pass


def compare(alone: list, together: list, name: str):
    """MCL's rows from a solo run against its rows from a joint run."""
    a = [r for r in alone if r[0] == name]
    b = [r for r in together if r[0] == name]
    only_alone = [r for r in a if r not in b]
    only_together = [r for r in b if r not in a]
    return a, b, only_alone, only_together


def render(strategies, n_sessions, joint, breaches, reasons,
           solo=None, name="MCL", cap=None) -> list[str]:
    cap = T.MAX_CONCURRENT_POSITIONS if cap is None else cap
    L = ["DRY SESSION -- the real trader, recorded bars, no broker", "",
         f"  strategies   {', '.join(strategies)}",
         f"  sessions     {n_sessions}",
         f"  cap          {cap} across all strategies"
         + ("" if cap == T.MAX_CONCURRENT_POSITIONS
            else f"   [OVERRIDDEN from the default "
                 f"{T.MAX_CONCURRENT_POSITIONS}]"),
         "",
         "  Decisions only. Dry-run assumes the marketable limit fills at its",
         "  own price, so nothing here measures slippage -- that is what the",
         "  live sessions are for.", ""]

    L += ["THE CAP", ""]
    if breaches:
        L += [f"  BREACHED on {len(breaches)} step(s):"]
        L += [f"    {b}" for b in breaches[:20]]
        L += ["", "  This is a defect, not a tuning question: the account is",
              "  shared and the cap is what bounds exposure across strategies.",
              ""]
    else:
        L += ["  held on every step of every session.", ""]

    L += ["WHAT EACH STRATEGY DID", ""]
    by_strat: Counter = Counter()
    for r in joint:
        if r[3] in ("DRY_RUN",):
            by_strat[(r[0], r[4])] += 1
    for (strat, action), n in sorted(by_strat.items()):
        L.append(f"  {strat:<6} {action:<5} {n:>5}")
    if not by_strat:
        L.append("  no fills at all -- check the sessions and the warm-up")
    L.append("")
    skipped = {k: v for k, v in reasons.items() if k}
    if skipped:
        L += ["  fill-log rows by status", ""]
        for status, n in sorted(skipped.items(), key=lambda kv: -kv[1]):
            L.append(f"    {status:<24} {n:>5}")
        L.append("")

    if solo is not None:
        a, b, only_a, only_b = compare(solo, joint, name)
        L += [f"DID ADDING A STRATEGY CHANGE {name}?", "",
              f"  {name} alone     {len(a):>5} rows",
              f"  {name} alongside {len(b):>5} rows", ""]
        if not only_a and not only_b:
            L += ["  IDENTICAL. Same symbols, same minutes, same prices.", ""]
        else:
            L += [f"  {len(only_a)} row(s) only in the solo run, "
                  f"{len(only_b)} only in the joint run:", ""]
            for r in (only_a + only_b)[:20]:
                L.append(f"    {r}")
            L += ["",
                  "  A row lost to SKIPPED_CONCURRENCY_CAP is a DESIGN",
                  "  CONSEQUENCE -- the cap is shared, so the other strategy",
                  "  legitimately took the slot. Anything else is a defect: it",
                  "  means adding a strategy moved the first one's decisions,",
                  "  and every paper session recorded from then on is",
                  "  measuring something the earlier ones were not.", ""]

    L += ["WHAT THIS CANNOT SEE", "",
          "  Fills, IB pacing, market-data limits, a rejected order. The",
          "  broker is a stub; those are live-only facts."]
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", default="bar_cache")
    ap.add_argument("--strategy", nargs="+", default=["mcl", "mc5"])
    ap.add_argument("--limit", type=int, default=20,
                    help="sessions to replay; every minute of each is stepped "
                         "for every strategy, so this is the slow dial")
    ap.add_argument("--compare-with", default="mcl",
                    help="also run this strategy ALONE and diff its decisions; "
                         "empty to skip")
    ap.add_argument("--max-positions", type=int, default=None,
                    help="cap across all strategies; None uses the trader's "
                         "default. Set it to whatever the live session will "
                         "run at -- a dry run at a different cap is not a "
                         "rehearsal of that session.")
    ap.add_argument("--out", default="var/reports/dry_session.txt")
    a = ap.parse_args(argv)

    sessions = load_sessions(Path(a.cache))[: a.limit]
    if not sessions:
        sys.exit(f"no sessions in {a.cache}")

    joint, breaches, reasons = replay(sessions, a.strategy,
                                      max_positions=a.max_positions)
    solo = None
    if a.compare_with and a.compare_with in a.strategy and len(a.strategy) > 1:
        # The SOLO run must use the SAME cap. Comparing a capped
        # joint run against an uncapped solo one would attribute the
        # cap's effect to the added strategy.
        solo, _b, _r = replay(sessions, [a.compare_with],
                              max_positions=a.max_positions)

    name = SA.build(a.compare_with).name if a.compare_with else "MCL"
    emit("\n".join(render(a.strategy, len(sessions), joint, breaches,
                          reasons, solo, name,
                          cap=a.max_positions)), a.out,
         header=f"common.dry_session  cache={a.cache}  "
                f"strategies={','.join(a.strategy)}  sessions={len(sessions)}")
    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
