#!/usr/bin/env python3
"""How far does price move in our favour AFTER we enter, and is it enough?

    python -m common.entry_excursion --strategy mcl

THE DISAGREEMENT THIS SETTLES
-----------------------------
Ben, 2026-09-14: *"Only the right entry can give you the right exit. No matter
how great your exit strategy is, if the entry is bad, we will not be
profitable."*

Three measurements already support the first half of that. `entry_features`
found 0 of 11 families separating MCL's 482 entries; `run_signal` puts the base
rate for an 8%-in-15 run at 0.108% with a best non-tautological predictor of
1.94x; `universe_lift` finds the best entry feature worth 2.34x against the
screen's 1.35x. We have not identified a good entry, and that is measured rather
than argued.

What is NOT measured is the step after it. `mfe_exit_mcl.txt` found the median
MCL trade exits BELOW its entry despite having traded above it -- so the
post-entry high is above the entry on the median trade, which is not what an
entry that finds nothing produces. But nobody has asked HOW FAR above. That
single distribution decides the argument:

    median in-trade MFE well above friction -> price does move our way, and the
        exit is squandering it. Exit work is worth doing.
    median in-trade MFE at or below friction -> there is nothing for any exit to
        capture, the entry finds noise, and every exit candidate in
        `exit_candidates_20260911.md` is a distraction.

PRE-REGISTERED, BEFORE THE FIRST RUN (2026-09-14)
--------------------------------------------------
The bar is friction, not a number chosen to be clearable. A trade whose best
moment never covered its own round trip could not have been profitable under ANY
exit rule, because an exit can only ever capture what the excursion offered.

  * `NEVER COVERED FRICTION` share <= 50% and median in-trade MFE >= 2x friction
        -> THE EXIT IS WORTH ATTACKING. The median trade had more than twice its
           costs available at its peak and gave it back.
  * `NEVER COVERED FRICTION` share > 50%, or median in-trade MFE < friction
        -> THE ENTRY IS THE PROBLEM. A perfect exit does not rescue the median
           trade. Ben is right and the exit candidates are dropped.
  * anything between -> NO VERDICT, and the report says which side it leans.

TWO WINDOWS, AND CONFLATING THEM IS THE TRAP
---------------------------------------------
**IN-TRADE** is entry bar + 1 to the exit bar. It is what a better exit could
have taken while holding the entry AND the hold time fixed, and it is the one
the pre-registration is written against.

**TO SESSION END** runs to the last bar of the session. It includes everything
that happened after we were already out, which is `mfe_exit_mcl.txt`'s question,
and it produced a ceiling of +$115.94/trade that the doc itself called
"technically true and not very informative". Both are printed; only the first
answers "is there something here to capture".

WHAT WOULD MAKE THIS WRONG
--------------------------
**Counting the entry bar's own high.** `dip_entry.excursions` starts at bar i+1
for exactly this reason, and it is imported rather than reimplemented. Within a
bar, OHLCV cannot say whether the high came before or after our fill, so
including bar i would credit the entry with a move that had already happened.
Excluding it makes every figure here a LOWER BOUND on both excursions, which is
stated wherever they are quoted.

**Comparing dollars per share against a per-trade friction.** $4.26 is a round
trip on 100 shares -- $0.0426 a share. Reading a $0.41/share excursion against
$4.26 understates it by a hundred times, and reading it the other way overstates
it by as much. Every figure here is per 100-share trade, with the per-share
value printed beside it and never mixed into a comparison.

**Reading the perfect-exit bound as a strategy.** Exiting every trade at its own
MFE frees the slot earlier, and the engine may then enter again -- so the bound
holds the trade SET fixed while changing when trades end, which no real rule
does. It is an upper bound on per-trade improvement, not a P/L.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.dip_entry import excursions
from common.pit_h0 import DROP, FRICTIONS, first_seen_time, load_pit
from common.pit_strategy import WARMUP_SESSIONS
from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")

QTY = 100
MEASURED_FRICTION = 4.26

# Pre-registered above, before the first run.
COVER_SHARE_BAR = 0.50          # share of trades never covering friction
MFE_MULTIPLE_BAR = 2.0          # median in-trade MFE, as a multiple of friction


def locate(idx: pd.DatetimeIndex, stamp: str) -> int | None:
    """Position of a trade's bar in the session frame it was cut from.

    Returned as None rather than 0 when absent. `searchsorted` on a missing
    stamp yields an insertion point that is a perfectly plausible index, so a
    mismatch between the engine's frame and this one would silently measure the
    excursion of a different bar.
    """
    t = pd.Timestamp(stamp)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    pos = idx.searchsorted(t.tz_convert("UTC"))
    if pos >= len(idx) or idx[pos] != t.tz_convert("UTC"):
        return None
    return int(pos)


def measure(df: pd.DataFrame, trade) -> dict | None:
    """One trade's excursions, in dollars on the traded size.

    `df` must be the SAME frame the engine ran on, sliced to this symbol.
    """
    i = locate(df.index, trade.entry_time)
    j = locate(df.index, trade.exit_time)
    if i is None or j is None or trade.entry_price <= 0:
        return None
    qty = trade.qty or QTY
    # end is exclusive in `excursions`, and the exit bar itself is part of the
    # trade -- price traded at that bar while the position was still open.
    mfe_in, mae_in = excursions(df, i, trade.entry_price, end=j + 1)
    mfe_end, mae_end = excursions(df, i, trade.entry_price, end=len(df))
    px = trade.entry_price
    return {"symbol": trade.symbol, "date": trade.date,
            "net": float(trade.net), "bars_held": int(trade.bars_held),
            "entry_price": px, "qty": qty,
            "mfe_in": mfe_in * px * qty, "mae_in": mae_in * px * qty,
            "mfe_end": mfe_end * px * qty,
            "mfe_in_share": mfe_in * px, "mae_in_share": mae_in * px}


def pct(vals: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(vals, dtype=float), q)) if vals \
        else float("nan")


def dist(rows: list[dict], key: str) -> dict:
    v = [r[key] for r in rows]
    return {"n": len(v), "p10": pct(v, 10), "p25": pct(v, 25),
            "p50": pct(v, 50), "p75": pct(v, 75), "p90": pct(v, 90),
            "mean": float(np.mean(v)) if v else float("nan")}


def never_covered(rows: list[dict], friction: float) -> int:
    """Trades whose best in-trade moment never covered their own round trip.

    These could not have been profitable under any exit rule. An exit can only
    take what the excursion offered, so this count is the floor on how much of
    the book is beyond the reach of exit work entirely.
    """
    return sum(1 for r in rows if r["mfe_in"] <= friction)


def perfect_exit(rows: list[dict], friction: float) -> dict:
    """Every trade exited at its own in-trade MFE. An UPPER BOUND, not a rule.

    Exiting earlier frees the slot and the engine may enter again, so this holds
    the trade set fixed while changing when trades end -- which no real rule
    does. Reported beside the actual net so the size of the gap is visible
    rather than the bound alone, which is the number that invites being quoted.
    """
    if not rows:
        return {"n": 0}
    actual = sum(r["net"] - friction for r in rows)
    ideal = sum(r["mfe_in"] - friction for r in rows)
    by_sym: dict[str, float] = defaultdict(float)
    for r in rows:
        by_sym[r["symbol"]] += r["mfe_in"] - friction
    dropped = ideal - sum(sorted(by_sym.values(), reverse=True)[:DROP])
    return {"n": len(rows), "actual": actual, "ideal": ideal,
            "actual_per": actual / len(rows), "ideal_per": ideal / len(rows),
            "dropped": dropped, "syms": len(by_sym)}


def halves(rows: list[dict], split: str, key: str) -> tuple[float, float]:
    e = [r[key] for r in rows if r["date"] < split]
    l = [r[key] for r in rows if r["date"] >= split]
    return (pct(e, 50), pct(l, 50))


def verdict(rows: list[dict], friction: float) -> tuple[str, list[str]]:
    """The pre-registered decision, applied without looking first."""
    if not rows:
        return "NO VERDICT", ["  No trades."]
    share = never_covered(rows, friction) / len(rows)
    med = pct([r["mfe_in"] for r in rows], 50)
    if share <= COVER_SHARE_BAR and med >= MFE_MULTIPLE_BAR * friction:
        return "THE EXIT IS WORTH ATTACKING", [
            f"  {100 * (1 - share):.1f}% of trades had more than their own",
            f"  round trip available at some point, and the median trade had",
            f"  ${med:,.2f} against ${friction:.2f} of friction -- "
            f"{med / friction:.1f}x.",
            "",
            "  Price does move our way after entry. Something is there to be",
            "  captured and the current exit is not capturing it."]
    if share > COVER_SHARE_BAR or med < friction:
        return "THE ENTRY IS THE PROBLEM", [
            f"  {100 * share:.1f}% of trades never covered their own round trip",
            f"  at any moment while open, and the median trade's best moment "
            f"was",
            f"  ${med:,.2f} against ${friction:.2f} of friction.",
            "",
            "  A perfect exit does not rescue the median trade, because there",
            "  was nothing at its peak to take. No exit rule reaches this.",
            "  The exit candidates are dropped and the entry is the problem."]
    return "NO VERDICT", [
        f"  {100 * share:.1f}% never covered friction (bar: "
        f"{100 * COVER_SHARE_BAR:.0f}%) and the median in-trade",
        f"  MFE is ${med:,.2f}, {med / friction:.1f}x friction (bar: "
        f"{MFE_MULTIPLE_BAR:.0f}x).",
        "",
        "  Between the pre-registered bounds. The report refuses rather than",
        "  picking the reading that suits the next piece of work."]


def render(rows: list[dict], name: str, n_days: int, n_universe: int,
           split: str, elapsed: float, jobs: int, made: int | None = None,
           warm_short: int = 0) -> list[str]:
    L = [f"{name.upper()}: HOW FAR PRICE MOVES IN OUR FAVOUR AFTER ENTRY", "",
         f"  {n_days} sessions, {n_universe:,} point-in-time symbol-days, "
         f"{len(rows):,} trades",
         f"  every entry floored at its own first_seen; {QTY} shares",
         f"  {WARMUP_SESSIONS} session(s) of warm-up, as pit_strategy builds "
         f"it -- MACD is an EMA with",
         "  unbounded memory, so a frame without the prior slice is a "
         "different population",
         f"  halves split at {split} (derived)",
         f"  elapsed {elapsed:.1f}s on {jobs} worker(s)", ""]
    if warm_short:
        L.append(f"  {warm_short} session(s) ran with less warm-up than asked "
                 "(no prior slice)")
    if made is not None and made != len(rows):
        # A trade whose bar cannot be located is dropped. Silently dropping a
        # share of the book is how a biased subsample gets reported as the book.
        lost = made - len(rows)
        L += [f"  *** {lost:,} of {made:,} trades "
              f"({100 * lost / max(made, 1):.1f}%) COULD NOT BE LOCATED",
              "      in their own frame and are excluded. Read nothing below "
              "until that is zero."]
    L += ["",
         "  EXCURSIONS START AT THE BAR AFTER ENTRY. Within a bar, OHLCV",
         "  cannot say whether the high came before or after the fill, so the",
         "  entry bar is excluded and every figure below is a LOWER BOUND.", ""]

    if not rows:
        return L + ["NO TRADES. Nothing to measure.", ""]

    L += ["IN-TRADE, PER 100-SHARE TRADE", "",
          "  what a better exit could have taken, holding the entry and the",
          "  hold time fixed", "",
          f"  {'':<14}{'p10':>10}{'p25':>10}{'p50':>10}{'p75':>10}{'p90':>10}"
          f"{'mean':>10}"]
    for key, label in (("mfe_in", "MFE (up)"), ("mae_in", "MAE (down)")):
        d = dist(rows, key)
        L.append(f"  {label:<14}" + "".join(
            f"${acct(d[k], 9)}" for k in ("p10", "p25", "p50", "p75", "p90",
                                          "mean")))
    d = dist(rows, "mfe_in_share")
    L += ["",
          f"  the same MFE per SHARE: p50 ${d['p50']:.4f}  "
          f"mean ${d['mean']:.4f}",
          f"  (friction is ${MEASURED_FRICTION:.2f} a round trip on {QTY} "
          f"shares, ${MEASURED_FRICTION / QTY:.4f} a share -- the two are",
          "   never compared without being put on the same footing first)", ""]

    L += ["COULD THE TRADE EVER HAVE PAID FOR ITSELF", ""]
    for label, f in FRICTIONS:
        n = never_covered(rows, f)
        L.append(f"  friction {label:<8}{n:>7,} of {len(rows):,} trades "
                 f"({100 * n / len(rows):>5.1f}%) never covered it")
    L += ["",
          "  A trade whose best moment never reached its own round trip could",
          "  not have been profitable under ANY exit rule. This is the share",
          "  of the book that exit work cannot reach at all.", ""]

    pe = perfect_exit(rows, MEASURED_FRICTION)
    drop = (f"${acct(pe['dropped'], 11, 0)}" if pe["syms"] > DROP
            else f"{'n/a':>12}")
    L += ["THE CEILING ON EXIT WORK, at $4.26", "",
          f"  actual                  {acct(pe['actual_per'], 9)}/trade   "
          f"${acct(pe['actual'], 11, 0)}",
          f"  every trade at its MFE  {acct(pe['ideal_per'], 9)}/trade   "
          f"${acct(pe['ideal'], 11, 0)}",
          f"  the gap                 {acct(pe['ideal_per'] - pe['actual_per'], 9)}"
          f"/trade",
          f"  ideal, drop-top-5                      {drop}", "",
          "  AN UPPER BOUND, NOT A RULE. Exiting at the MFE frees the slot",
          "  earlier and the engine may enter again, so this holds the trade",
          "  SET fixed while changing when trades end. No real exit does that,",
          "  and nothing reaches this number. It bounds what is available.", ""]

    em, lm = halves(rows, split, "mfe_in")
    L += ["BOTH HALVES", "",
          f"  median in-trade MFE   early ${em:,.2f}   late ${lm:,.2f}", ""]
    if min(em, lm) <= 0 < max(em, lm):
        L += ["  THE HALVES DISAGREE IN SIGN. No verdict is quoted from a",
              "  figure whose two halves point opposite ways.", ""]

    v, why = verdict(rows, MEASURED_FRICTION)
    L += [v, ""] + why + [""]

    L += ["WHAT THIS IS NOT", "",
          "  Not a measure of the entry's SELECTIVITY. It says how far price",
          "  moved after the entries MCL took, not whether a different rule",
          "  would have found better ones.",
          "",
          "  Not out of sample. `holdout.json` has not been spent here.",
          "",
          "  Not the published backtest. Same tape and warm-up as",
          "  `pit_strategy`, so read it against that and against nothing else."]
    return L


def run_day(args: tuple) -> tuple:
    """One session's trades and their excursions. Module-level and picklable.

    THE FRAME MUST MATCH `pit_strategy`'s. The first version of this module read
    a single day's slice; pit_strategy prepends `WARMUP_SESSIONS` prior slices,
    and MACD is an EMA with unbounded memory. That produced 3,521 trades against
    pit_strategy's 3,955 -- an 11% different population -- under a report that
    said "same tape and warm-up as pit_strategy". A caveat asserting a
    comparability that does not hold is worse than no caveat.

    Each worker is handed its own day's paths INCLUDING the warm-up ones and
    builds the frame itself, so the sessions stay independent and the deque walk
    that pit_strategy does sequentially is not needed here.
    """
    from common.dbn_io import read_dbn
    from common.pit_strategy import build_frame, engine

    paths, day, universe, strategy = args
    mod, extra = engine(strategy)
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, [], 0, 0, 0, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, [], 0, 0, 0, ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)
    out: list[dict] = []
    made = 0
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        try:
            trades = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                          not_before=first_seen_time(rec),
                                          **extra)
        except Exception:                                   # noqa: BLE001
            continue
        made += len(trades)
        for t in trades:
            m = measure(df, t)
            if m is not None:
                out.append(m)
    # made vs len(out): a trade whose bar cannot be located is dropped, and a
    # silent 11% drop is how a biased subsample gets reported as the book.
    return day, out, len(universe), made, len(parts) - 1, ""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--strategy", default="mcl", choices=["mcl", "mc5"])
    p.add_argument("--pairs", default="var/state/screen_pairs_pit.json")
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.screen_sim import window_slices, date_of

    archive = Path(a.archive) if a.archive else default_archive()
    by_date = load_pit(Path(a.pairs))
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    # Each task carries its own warm-up paths, so a worker builds the same
    # frame pit_strategy's sequential deque walk would have handed it.
    have = sorted(slices)
    pos = {d: i for i, d in enumerate(have)}
    tasks = []
    for d in days:
        if d not in slices:
            continue
        i = pos[d]
        tasks.append(([str(slices[x])
                       for x in have[max(0, i - WARMUP_SESSIONS):i + 1]],
                      d, by_date[d], a.strategy))
    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"  {a.strategy} excursions over {len(tasks):,} session(s) on "
          f"{jobs} worker(s)", flush=True)

    t0 = time.time()
    got: dict[str, tuple[list, int, int, int]] = {}

    def take(res, k):
        day, rows, nu, made, warm, err = res
        if err:
            print(f"  {day}: {err}", flush=True)
        else:
            got[day] = (rows, nu, made, warm)
        if k % 25 == 0 or k == len(tasks):
            el = time.time() - t0
            eta = (len(tasks) - k) / (k / el) / 60.0 if el and k else 0.0
            n = sum(len(v[0]) for v in got.values())
            print(f"    [{k:>4}/{len(tasks)}] {day}  {n:>7,} trades  "
                  f"{el / 60:>5.1f} min  ~{eta:>5.1f} min left", flush=True)

    if jobs == 1:
        for k, t in enumerate(tasks, 1):
            take(run_day(t), k)
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for k, r in enumerate(ex.map(run_day, tasks, chunksize=4), 1):
                take(r, k)

    # Day order, not completion order: this module sums floats, and a total
    # that moved when --jobs changed would not be a measurement.
    rows: list[dict] = []
    n_universe = made = warm_short = 0
    for day in sorted(got):
        r, nu, mk, warm = got[day]
        rows += r
        n_universe += nu
        made += mk
        warm_short += 1 if warm < WARMUP_SESSIONS else 0

    ds = sorted({r["date"] for r in rows})
    split = ds[len(ds) // 2] if ds else ""
    out = a.out or f"var/reports/entry_excursion_{a.strategy}.txt"
    emit("\n".join(render(rows, a.strategy, len(days), n_universe, split,
                          time.time() - t0, jobs, made=made,
                          warm_short=warm_short)),
         out, header=f"common.entry_excursion  strategy={a.strategy}  "
                     f"pairs={a.pairs}"
                     + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
