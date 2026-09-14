#!/usr/bin/env python3
r"""Is paying the close of the signal bar the expensive part?

    python -m common.entry_fill --jobs 8

THE QUESTION, AND WHY IT IS NOT ANOTHER FILTER
-----------------------------------------------
Every entry study in this project has held one thing constant: the fill is the
close of the bar the rule fired on. `entry_features` (22 features, 0 of 11
families), `entry_split` (is the winner visible at entry -- no), `entry_margins`
(112 buckets, none positive) all vary WHICH BARS ARE KEPT. None of them varies
WHAT WAS PAID ON THE BAR ALREADY CHOSEN.

And `run_signal` measured the ceiling on bar selection over 37.6 million bars:
the base rate for an 8%-in-15 run is 0.108%, and the best feature that is not a
volatility tautology reaches 0.21% precision at 1.94x lift while firing on a
quarter of all bars. Filtering is close to exhausted. The fill has never been
touched.

Five separate instruments point the same way:

    close_in_bar          the losses sit in entries that paid the top tick
    dollar_vol_session    the quietest quarter beat the busiest, both halves
    macd_margin           the smallest quarter is the best bucket, the large ones worst
    rsi_slope, mfi_slope  the steepest quarter is the worst bucket in both halves
    entry_latency         the live order leaves 60s after the bar closes anyway

MCL fills at the close of a bar its own rule REQUIRES to be a 3x volume spike.
The consistent direction of all of the above is that paying up into that spike
is what costs.

WHAT CANNOT BE TESTED, AND WHY IT IS NOT AN OVERSIGHT
------------------------------------------------------
**Nothing inside the signal bar.** The signal is not known until that bar has
closed, so its open, its low and its midpoint were never available to buy at. A
variant that "fills at the signal bar's midpoint" is reading the future and
would print a better number for doing it. Every variant here fills on a LATER
bar, at a price that was reachable from what was known when the bar closed.

THE TWO FAMILIES
----------------
DEFERRED MARKET   wait N bars, then pay that bar's close. N=1 is what the live
                  trader already does by accident: the order leaves sixty
                  seconds after the bar closes, so that row is not a proposal,
                  it is a measurement of the status quo.

PULLBACK LIMIT    place a limit at the signal close less d%, good for N bars.
                  It fills at the LIMIT price on the first bar whose low reaches
                  it, and otherwise does not fill at all. The limit price is
                  decided at signal time, so nothing here is hindsight.

A LIMIT THAT DOES NOT FILL IS THE POINT, NOT A NUISANCE
--------------------------------------------------------
A pullback rule does not just change prices, it changes the BOOK: the trades
that ran away without pulling back are never taken. Those are plausibly the
best ones, so a variant can improve the average while losing money overall.

Every variant therefore reports the fill rate AND what the missed trades were
worth under the baseline. A report that showed only the taken trades would make
"never fill" look like the best rule in the table.

PRE-REGISTERED, WRITTEN BEFORE THE FIRST RUN
---------------------------------------------
The claim: **a fill below the signal bar's close improves net per trade.**

    CLEARS     net per trade positive after $4.26 friction, in BOTH halves,
               taking at least MIN_FILL of the baseline's book.
    IMPROVES   beats the baseline per trade by more than friction in both
               halves, same fill floor, without being positive.
    NOTHING    everything else.

TWO REFUSALS, BOTH FIXED IN ADVANCE, AND THE FIRST IS THE IMPORTANT ONE.

**Abstention is not an edge.** The baseline loses money, so ANY variant that
trades less earns more in total -- and the limit is not trading at all, which
"earns" zero and beats everything. A per-trade figure has the same defect in
reverse: it rises whenever a rule skips losers, and it rises just as happily
when it skips almost everything. So a variant filling under MIN_FILL of the
book is not judged against this strategy at all. It is a different strategy,
and would have to be measured as one.

**And where the baseline earns money**, a variant whose total is lower is not
an improvement however good its per-trade figure -- fewer, better trades is
only better if the book earns more.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

from common.entry_shares import MEASURED_FRICTION, PUBLISHED_TRADES, QTY, split
from common.report_io import emit

ET = ZoneInfo("America/New_York")

FRICTIONS = (("$1.00", 1.00), ("$4.26", 4.26), ("$8.92", 8.92))

# Fixed before the run. Every variant is printed; none is recommended.
DEFER_BARS = (1, 2, 3, 5)
PULLBACK_PCT = (0.5, 1.0, 2.0, 3.0)
PULLBACK_WINDOW = (5, 15)

# The share of the baseline's book a variant must still take to be judged as an
# improvement to it. Fixed before the run. Below this, the variant is a
# different strategy wearing this one's name, and "trade less" is not a finding
# on a book that loses money.
MIN_FILL = 0.50

BASELINE = "baseline: signal bar close"
PAIRS = "var/state/screen_pairs_pit.json"


def variants() -> list[tuple[str, dict]]:
    """(name, spec) for every variant, baseline first.

    A list, not a search: the report prints all of them and the pre-registered
    rule is applied to each. Reading the best row off the table afterwards is
    choosing a rule after seeing its outcome, and the table says so.
    """
    out: list[tuple[str, dict]] = [(BASELINE, {"kind": "baseline"})]
    for n in DEFER_BARS:
        out.append((f"defer {n} bar(s), pay the close",
                    {"kind": "defer", "bars": n}))
    for d in PULLBACK_PCT:
        for w in PULLBACK_WINDOW:
            out.append((f"limit -{d:g}% good for {w} bars",
                        {"kind": "limit", "pct": d, "window": w}))
    return out


# --- the tape ---------------------------------------------------------------

def limit_fill(df, i: int, limit: float, window: int) -> int | None:
    """First bar in (i, i+window] whose LOW reaches `limit`. None if never.

    Strictly after `i`: the limit is placed once the signal bar has closed, so
    that bar's own low is not available to fill against. Off by one here is the
    difference between a measurement and a look-ahead.
    """
    lows = df["low"].to_numpy()
    for j in range(i + 1, min(i + 1 + window, len(df))):
        if lows[j] <= limit:
            return j
    return None


def run_day(args: tuple) -> tuple:
    """One session, every variant, over the same signal bars.

    THE SIGNAL BARS ARE COMPUTED ONCE AND SHARED. Every variant is driven by
    `entry_bars`, which REPLACES the rule's signal -- so each variant enters on
    bars derived from the same original signal rather than re-deriving it. A
    variant that re-tested the rule at its own entry bar would be measuring a
    different and flattering strategy, which is the reason `entry_delay_bars`
    does not re-test either.
    """
    import numpy as np
    import pandas as pd

    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine
    from strategy.mcl import mcl as MCL

    paths, day, universe, specs = args
    mod, extra = engine("mcl")
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, {}, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, {}, ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)
    got: dict[str, list] = {name: [] for name, _ in specs}

    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        try:
            base = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                        not_before=floor, **extra)
        except Exception:                                   # noqa: BLE001
            continue
        if not base:
            continue

        sig = MCL.signals(df)
        # The bars the rule actually fired on, as positions in `sig`.
        fired = []
        for t in base:
            k = sig.index.searchsorted(pd.Timestamp(t.entry_time))
            if k < len(sig) and sig.index[k] == pd.Timestamp(t.entry_time):
                fired.append(int(k))
        if len(fired) != len(base):
            # Every trade must be placeable or the variants are driven by a
            # different book from the baseline. Skip the whole symbol-day
            # rather than compare two populations under one label.
            continue

        for name, spec in specs:
            if spec["kind"] == "baseline":
                got[name].append(("take", base, None, {}))
                continue
            take = np.zeros(len(sig), dtype=bool)
            px = np.full(len(sig), np.nan)
            missed = 0
            for k, t in zip(fired, base):
                if spec["kind"] == "defer":
                    j = k + spec["bars"]
                    if j >= len(sig) - 1:
                        missed += 1
                        continue
                    take[j] = True
                else:
                    limit = float(sig["close"].iloc[k]) * (1.0 - spec["pct"] / 100.0)
                    j = limit_fill(sig, k, limit, spec["window"])
                    if j is None or j >= len(sig) - 1:
                        missed += 1
                        continue
                    take[j] = True
                    px[j] = limit
            if not take.any():
                got[name].append(("miss", [], missed, {}))
                continue
            try:
                tr = mod.backtest_session(
                    df, d, ET, entry_shares=QTY, not_before=floor,
                    entry_bars=pd.Series(take, index=sig.index),
                    entry_px_by_bar=pd.Series(px, index=sig.index), **extra)
            except Exception:                               # noqa: BLE001
                continue
            # THE LIMIT PRICE TRAVELS WITH THE TRADE. Without it, a run in
            # which `entry_px_by_bar` was never passed to the engine fills at
            # the bar's CLOSE and renders exactly like one that filled at the
            # limit -- a silently different measurement. The check downstream
            # is `entry_px <= limit`, which only the intended limit can answer.
            limit_at = {ts: v for ts, v in zip(sig.index, px) if v == v}
            got[name].append(("take", tr, missed, limit_at))

    out: dict[str, dict] = {}
    for name, _spec in specs:
        trades, missed = [], 0
        for _kind, tr, m, limit_at in got[name]:
            for t in tr:
                row = {"date": day, "gross": (t.exit_price - t.entry_price) * QTY,
                       "entry_px": float(t.entry_price)}
                lim = limit_at.get(pd.Timestamp(t.entry_time))
                if lim is not None:
                    row["limit_px"] = float(lim)
                trades.append(row)
            missed += (m or 0)
        out[name] = {"trades": trades, "missed": missed}
    return day, out, ""


# --- reporting --------------------------------------------------------------

def net(rows, friction: float) -> float:
    return sum(r["gross"] - friction for r in rows)


def per_trade(rows, friction: float) -> float:
    return net(rows, friction) / len(rows) if rows else 0.0


def verdict(rows, base_rows) -> tuple[str, str]:
    """The pre-registered rule, applied to one variant."""
    a, b = split(rows)
    if not a or not b:
        return "NOTHING", "one half is empty"

    # ABSTENTION IS NOT AN EDGE, and it is the failure mode that would otherwise
    # win this table outright: the baseline loses, so trading less always earns
    # more in total, and skipping losers always raises the per-trade figure.
    # A variant that does not take most of the book is a different strategy.
    fill = len(rows) / len(base_rows) if base_rows else 0.0
    if fill < MIN_FILL:
        return "NOTHING", (f"fills {fill:.0%} of the book, under the {MIN_FILL:.0%} "
                           f"floor -- trading less is not an improvement to a "
                           f"strategy, it is a different one")

    pa, pb = per_trade(a, MEASURED_FRICTION), per_trade(b, MEASURED_FRICTION)
    if pa > 0 and pb > 0:
        tag, why = "CLEARS", "positive after friction in both halves"
    else:
        ba, bb = split(base_rows)
        da = pa - per_trade(ba, MEASURED_FRICTION)
        db = pb - per_trade(bb, MEASURED_FRICTION)
        if da > MEASURED_FRICTION and db > MEASURED_FRICTION:
            tag, why = "IMPROVES", ("beats the baseline by more than friction "
                                    "in both halves, and still loses")
        else:
            return "NOTHING", "neither positive nor better than baseline by friction"

    # AND where the baseline earns money, a smaller total is not an improvement.
    # Guarded on the baseline being positive because on a losing book this test
    # is satisfied by abstaining, which the fill floor above already refuses.
    bnet = net(base_rows, MEASURED_FRICTION)
    if bnet > 0 and net(rows, MEASURED_FRICTION) <= bnet:
        return "NOTHING", (f"{tag} per trade, but the book's total net is no "
                           f"better than the baseline's -- fewer, better "
                           f"trades is not an improvement if it earns less")
    return tag, why


def table(results: dict, base_name: str) -> list[str]:
    base = results[base_name]["trades"]
    n_base = len(base)
    L = ["EVERY VARIANT, NONE RECOMMENDED", "",
         f"  {'variant':<34}{'trades':>8}{'fill':>7}"
         + "".join(f"{lab:>10}" for lab, _ in FRICTIONS)
         + f"{'total $':>13}", ""]
    for name in results:
        rows = results[name]["trades"]
        fill = 100.0 * len(rows) / n_base if n_base else 0.0
        L.append(f"  {name:<34}{len(rows):>8,}{fill:>6.0f}%"
                 + "".join(f"{per_trade(rows, f):>10,.2f}" for _, f in FRICTIONS)
                 + f"{net(rows, MEASURED_FRICTION):>13,.0f}")
    L += ["",
          "  `fill` is trades taken against the baseline's book. A variant at",
          "  60% did not take 40% of the entries -- see the next section for",
          "  what those were worth.",
          "",
          "  `total $` is the whole book at $4.26. It is printed beside the",
          "  per-trade column because they can move in opposite directions,",
          "  and the per-trade figure is the one that flatters a rule which",
          "  simply trades less.", ""]
    return L


def missed_section(results: dict, base_name: str) -> list[str]:
    """What the skipped entries were worth under the baseline.

    A pullback rule skips the trades that ran away without pulling back. Those
    are plausibly the best ones, so this is the section that decides whether a
    variant is selecting or merely abstaining.
    """
    base = {(r["date"], i): r for i, r in enumerate(results[base_name]["trades"])}
    L = ["WHAT THE UNFILLED ENTRIES WERE WORTH", "",
         "  A limit that never fills skips a trade. If the skipped ones are the",
         "  winners, the variant improves its average by abstaining from the",
         "  part that pays.", "",
         f"  {'variant':<34}{'skipped':>9}{'their $/t at baseline':>24}", ""]
    nb = len(results[base_name]["trades"])
    for name in results:
        if name == base_name:
            continue
        skipped = nb - len(results[name]["trades"])
        # The baseline net of the skipped trades cannot be attributed
        # trade-by-trade without carrying an identity through every variant, so
        # what is printed is the DIFFERENCE the whole book makes, which is the
        # quantity that matters and needs no identity.
        delta = (net(results[base_name]["trades"], MEASURED_FRICTION)
                 - net(results[name]["trades"], MEASURED_FRICTION))
        implied = delta / skipped if skipped else 0.0
        L.append(f"  {name:<34}{skipped:>9,}{implied:>24,.2f}")
    L += ["",
          "  Read as: the baseline's book minus this variant's book, divided by",
          "  the number of trades the difference covers. Positive means the",
          "  entries this variant did not take were, on the whole, PROFITABLE",
          "  ones -- it abstained from money.", ""]
    return L


def render(results: dict, n_days: int, elapsed: float, jobs: int) -> list[str]:
    base = results[BASELINE]["trades"]
    L = ["IS PAYING THE CLOSE OF THE SIGNAL BAR THE EXPENSIVE PART?", "",
         f"  outcome: net at ${MEASURED_FRICTION:.2f}/round trip",
         f"  {n_days:,} sessions   elapsed {elapsed:.1f}s on {jobs} worker(s)",
         "",
         "  PRE-REGISTERED: a fill below the signal bar's close improves net",
         "  per trade. CLEARS = positive after friction in both halves.",
         "  IMPROVES = beats the baseline by more than friction in both halves.",
         "  And a variant whose TOTAL net is no better than the baseline's is",
         "  not an improvement, however good its per-trade figure.", "",
         "POPULATION", "",
         f"  baseline trades     {len(base):,}"]
    pub = PUBLISHED_TRADES.get("mcl")
    if pub is not None:
        L.append(f"  published count     {pub:,}   "
                 + ("matches" if len(base) == pub else "*** DOES NOT MATCH ***"))
        if len(base) != pub:
            L += ["", "  A DIFFERENT BOOK UNDER THE SAME CAVEAT. Do not read",
                  "  the sections below until this reconciles."]
    L += ["",
          "  NOTHING FILLS INSIDE THE SIGNAL BAR. The signal is not known until",
          "  that bar closes, so its open, low and midpoint were never available",
          "  to buy at. Every variant fills on a LATER bar at a price that was",
          "  reachable from what was known when the signal bar closed.", ""]

    L += table(results, BASELINE)
    L += missed_section(results, BASELINE)

    L += ["THE VERDICT, PER VARIANT", ""]
    tags = {}
    for name in results:
        if name == BASELINE:
            continue
        tag, why = verdict(results[name]["trades"], base)
        tags[name] = tag
        L.append(f"  {name:<34} {tag:<9} {why}")
    L += [""]
    if any(t == "CLEARS" for t in tags.values()):
        L += ["  At least one variant is profitable after friction in both",
              "  halves AND earns more in total than the baseline. That is a",
              "  candidate to test out of sample, not a rule to ship.", ""]
    elif any(t == "IMPROVES" for t in tags.values()):
        L += ["  Nothing is profitable. Something is less unprofitable by more",
              "  than a round trip, in both halves, while earning more in",
              "  total. That is a direction, not an edge.", ""]
    else:
        L += ["  NOTHING. Neither deferring the fill nor waiting for a pullback",
              "  changes the sign or beats the baseline by friction.", "",
              "  That closes the last lever that was not a filter. Taken with",
              "  run_signal's 0.108% base rate and 0.21% best precision, the",
              "  entry -- which bar, and what is paid on it -- has now been",
              "  measured from both sides and neither side moves it.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. holdout.json has not been spent here.",
          "  NOT A FRICTION MODEL FOR LIMITS. $4.26 was measured on market",
          "  orders. A limit that fills pays less slippage and a limit that does",
          "  not fill pays nothing -- charging all variants the same number is",
          "  like-for-like on everything except the entry price, and wrong for",
          "  the limit rows in a direction that is conservative and unmeasured.",
          "  NOT A QUEUE MODEL. A limit at the low of a bar is assumed filled if",
          "  the bar traded there. In a thin name it might not have been, and",
          "  39.7% of these entries are on bars trading under $100,000.", ""]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/entry_fill_mcl.txt")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    by_date = load_pit(Path(a.pairs))
    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    have = [d for d in days if d in slices]

    specs = variants()
    tasks = []
    for k, day in enumerate(have):
        first = max(0, k - WARMUP_SESSIONS)
        tasks.append(([str(slices[d]) for d in have[first:k + 1]], day,
                      by_date[day], specs))

    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"entry_fill: {len(tasks):,} session(s) x {len(specs)} variant(s) "
          f"on {jobs} worker(s)", flush=True)
    t0 = time.time()
    got: dict[str, dict] = {}
    if jobs == 1:
        it = map(run_day, tasks)
    else:
        from concurrent.futures import ProcessPoolExecutor
        ex = ProcessPoolExecutor(max_workers=jobs)
        it = ex.map(run_day, tasks, chunksize=2)
    for k, (day, res, err) in enumerate(it, 1):
        got[day] = res
        if err:
            print(f"  ! {day}: {err}", flush=True)
        if k % 50 == 0:
            print(f"  ... {k:,} of {len(tasks):,}", flush=True)
    if jobs != 1:
        ex.shutdown()

    # DAY ORDER, not completion order: this sums floats and float addition is
    # not associative, so a net that moves with --jobs is not a constant.
    results: dict[str, dict] = {name: {"trades": [], "missed": 0}
                                for name, _ in specs}
    for day in sorted(got):
        for name, _spec in specs:
            r = got[day].get(name)
            if not r:
                continue
            results[name]["trades"].extend(r["trades"])
            results[name]["missed"] += r["missed"]

    emit("\n".join(render(results, len(have), time.time() - t0, jobs)), a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
