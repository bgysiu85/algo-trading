#!/usr/bin/env python3
"""Did the 5% trailing stop sell into noise? Two questions, kept separate.

    python -m common.stop_timing

BEN'S QUESTION: after a trailing-stop exit, does price rally back within the
next 2-5 bars, and how much was left on the table?

That is worth measuring, but on its own it cannot answer "is the stop too
tight", for a reason that has to be stated up front: **price recovering after
a stop is the normal case, not evidence of a mistake.** A stop fires on a
decline; declines in a noisy series are frequently followed by a bounce. If
50% of exits are followed by a higher price within five bars, that is roughly
what a coin would do. The number only becomes informative when compared
against something.

So this module reports two things and never conflates them:

  PART 1  descriptive -- how often, and how much. Including a NULL: the same
          measurement taken from random in-trade bars rather than exit bars.
          If the exit bars look like the random bars, the stop is not selling
          into anything special.

  PART 2  decisional -- do rules that avoid the give-back actually earn more?
          Three candidates, each compared not only against the shipped 5%
          intrabar trail but against a WIDER INTRABAR TRAIL that concedes the
          same amount of room. Both alternatives are strictly looser than the
          default, so beating 5% proves nothing on its own; they have to beat
          the cheap way of being looser.
"""
from __future__ import annotations

import random
import statistics
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import load_sessions, LIVE
from common.commissions import order_cost
from common.scale_grid import prepare, SLIP_PER_SHARE
from common.trail_study import paired_bootstrap
from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")
TRAIL = 5.0
LOOKAHEAD = (1, 2, 3, 5, 10)
RESAMPLES = 10_000


# --------------------------------------------------------------- part 1

def stop_events(sess, trail_pct=TRAIL):
    """Replay one session and record every trailing-stop exit with the bars
    that followed it. Deliberately a plain re-implementation of the exit rule
    rather than a call into backtest_session(), because what is needed is the
    exit BAR INDEX and the forward window, which a Trade does not carry."""
    _sym, entry, _o, high, low, close, keep = sess
    out, in_trade_bars = [], []
    pos = None
    last_k = len(keep) - 1
    for k, i in enumerate(keep):
        if pos is None:
            if entry[i]:
                px = close[i] + S.SLIPPAGE_TICKS * S.TICK
                if S.ENFORCE_PRICE_BAND and not (S.PRICE_MIN <= px <= S.PRICE_MAX):
                    continue
                q = S.size_for(px)
                if q >= 1:
                    pos = [q, px, max(px, high[i])]
            continue
        in_trade_bars.append((k, i, close[i]))
        trail = pos[2] * (1.0 - trail_pct / 100.0)
        if low[i] <= trail:
            px_out = trail - S.SLIPPAGE_TICKS * S.TICK
            fwd = [(high[j], close[j]) for j in keep[k + 1:k + 1 + max(LOOKAHEAD)]]
            out.append(dict(qty=pos[0], entry=pos[1], exit=px_out, fwd=fwd,
                            profitable=px_out > pos[1]))
            pos = None
        elif k == last_k:
            pos = None
        else:
            pos[2] = max(pos[2], high[i])
    return out, in_trade_bars


def describe(events, label):
    print(f"\n{label}: {len(events):,} trailing-stop exits")
    print(f"  {'bars':>5} {'high > exit':>12} {'median max':>11} "
          f"{'mean max':>10} {'$ left (hindsight)':>19} {'close > exit':>13}")
    for n in LOOKAHEAD:
        rows = [e for e in events if len(e["fwd"]) >= n]
        if not rows:
            continue
        gains, dollars, closes = [], 0.0, 0
        for e in rows:
            mx = max(h for h, _c in e["fwd"][:n])
            gains.append(100.0 * (mx - e["exit"]) / e["exit"])
            dollars += max(0.0, mx - e["exit"]) * e["qty"]
            if e["fwd"][n - 1][1] > e["exit"]:
                closes += 1
        above = sum(1 for g in gains if g > 0)
        print(f"  {n:>5} {100*above/len(rows):>11.0f}% "
              f"{statistics.median(gains):>10.2f}% "
              f"{statistics.mean(gains):>9.2f}% "
              f"${dollars:>18,.0f} {100*closes/len(rows):>12.0f}%")


def null_model(prepared, events_n, seed=20260905):
    """The control. Take the same forward-looking measurement from RANDOM
    in-trade bars instead of exit bars. If the exit bars are no different,
    the stop is not selling into anything a wider stop would rescue."""
    rng = random.Random(seed)
    pool = []
    for sess in prepared:
        _e, bars = stop_events(sess)
        _sym, _en, _o, high, _low, close, keep = sess
        for k, i, c in bars:
            fwd = [(high[j], close[j]) for j in keep[k + 1:k + 1 + max(LOOKAHEAD)]]
            if fwd:
                pool.append(dict(qty=100, entry=c, exit=c, fwd=fwd,
                                 profitable=True))
    rng.shuffle(pool)
    return pool[:events_n]


# --------------------------------------------------------------- part 2

def run(sessions, **kw):
    per_sym, n = {}, 0
    for symbol, date_str, df in sessions:
        for t in S.backtest_session(
                df, datetime.strptime(date_str, "%Y-%m-%d").date(), ET,
                **LIVE, **kw):
            per_sym[symbol] = per_sym.get(symbol, 0.0) + \
                t.net - t.shares_traded * SLIP_PER_SHARE
            n += 1
    return per_sym, n


def total(d):
    return sum(d.values())


def drop_top(d, k):
    return sum(sorted(d.values(), reverse=True)[k:])


def compare(sessions, base, base_n, label, **kw):
    cand, n = run(sessions, **kw)
    syms = sorted(set(base) | set(cand))
    b = {s: base.get(s, 0.0) for s in syms}
    c = {s: cand.get(s, 0.0) for s in syms}
    tot, lo, hi, p = paired_bootstrap(b, c, RESAMPLES)
    delta = {s: c[s] - b[s] for s in syms}
    print(f"  {label:<34} {n:>5} tr  ${total(cand):>8,.0f}  {tot:>+8,.0f}  "
          f"[{lo:>+7,.0f},{hi:>+7,.0f}] {p:>5.1f}%  {drop_top(delta,5):>+8,.0f}")
    return cand


def main() -> int:
    sessions = load_sessions(Path("bar_cache"))
    prepared = prepare(sessions)

    print("=" * 78)
    print("PART 1 -- what actually happens after a 5% trailing-stop exit")
    print("=" * 78)
    events = []
    for sess in prepared:
        e, _ = stop_events(sess)
        events.extend(e)
    describe(events, "ALL trailing-stop exits")
    describe([e for e in events if not e["profitable"]],
             "  of those, the ones that exited at a LOSS")
    describe([e for e in events if e["profitable"]],
             "  of those, the ones that exited in PROFIT")
    describe(null_model(prepared, len(events)),
             "NULL: the same measurement from random in-trade bars")

    print("\n" + "=" * 78)
    print("PART 2 -- do rules that avoid the give-back earn more?")
    print("=" * 78)
    base, base_n = run(sessions, trail_pct=TRAIL)
    print(f"\n  baseline: 5% intrabar trail, {base_n} trades, "
          f"${total(base):,.0f}, drop5 ${drop_top(base,5):,.0f}\n")
    print(f"  {'rule':<34} {'trades':>8}  {'net':>9}  {'delta':>8}  "
          f"{'95% CI':>17} {'P(>0)':>6}  {'drop5 of delta':>8}")

    print("\n  -- the cheap way to concede room: just widen the trail --")
    for t in (6.0, 7.0, 8.0, 10.0):
        compare(sessions, base, base_n, f"{t:g}% intrabar trail", trail_pct=t)

    print("\n  -- ignore the wick: require a CLOSE below the level --")
    for t in (5.0, 6.0, 8.0):
        compare(sessions, base, base_n, f"{t:g}% trail, on the close",
                trail_pct=t, trail_on_close=True)

    print("\n  -- breach, then confirm N bars later --")
    for n in (1, 2, 3, 5):
        compare(sessions, base, base_n, f"5% trail, confirm after {n} bar(s)",
                trail_pct=TRAIL, trail_confirm_bars=n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
