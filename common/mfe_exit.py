#!/usr/bin/env python3
"""Is the exit the problem, or is R = 0.58 an entry problem?

    python -m common.mfe_exit --strategy mcl

WHAT THIS DECIDES
-----------------
`win_rate_and_r.md` §2 puts the whole deficit on the REWARD side, and
`exit_candidates_20260911.md` queues three exit experiments behind one
measurement: how far does a trade keep going after we get out? If exits cluster
far below the eventual session high, the reward side is being left on the table.
If they do not, every exit candidate in that document is a distraction and the
deficit is an ENTRY problem.

Run this before the other two. It has no parameters, so there is nothing in it
to tune towards an answer.

THE CEILING IS THE TEST, AND IT NEEDS NO THRESHOLD
---------------------------------------------------
The obvious design is to pick a number of cents and call a gap above it
"material". That number would be chosen by me, after seeing the data, and it is
exactly the kind of knob this measurement is supposed to avoid.

So the test is a bound instead. **Sell every trade at the highest price available
after its entry** -- perfect foresight, the best exit that could ever exist on
these entries -- and compute R. The entries are untouched, so the comparison
isolates the exit completely:

  * If R at the ceiling is still below what the win rate requires, **no exit
    rule can close the gap**. Not the QS exit, not the re-entry exit, not a
    partial. The entries do not contain enough favourable movement to be worth
    1.05R, and the exit queue can be dropped without running it.
  * If R at the ceiling clears the requirement, the exit is worth attacking, and
    the capture ratio says how much of the ceiling a real rule would have to
    reach.

The required R is derived from the run's OWN win rate -- `(1 - w) / w`, the
break-even ratio -- and not quoted from a doc. The published 1.05 belongs to a
48.7% win rate on the stage-2 universe; the point-in-time arm wins about 21% of
the time, where break-even needs R near 3.6. Importing the old figure would
compare two universes, which is the defect this whole line of work exists to
stop repeating.

FORWARD-ONLY, AND BOTH ENDS ARE CONSERVATIVE
---------------------------------------------
Every excursion is measured over bars STRICTLY AFTER the reference bar:

  * the ceiling looks from the bar after entry, because the entry fills at its
    own bar's close and that bar's high has already happened;
  * MFE-after-exit looks from the bar after the exit, because where price went
    inside the exit bar after the fill is not observable at minute granularity.

Both choices understate the opportunity. That is the right direction for a test
whose null is "the exit is fine": it cannot manufacture a gap that is not there.
"""
from __future__ import annotations

import argparse
import time
from collections import deque
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.cache_io import BACKTEST_SESSIONS
from common.pit_h0 import FRICTIONS, first_seen_time, halves_split
from common.pit_strategy import (QTY, build_frame, engine, load_pit,
                                 needed_symbols)
from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")
WARMUP_SESSIONS = max(0, BACKTEST_SESSIONS - 1)
MIN_TRADES = 30


def session_bars(df: pd.DataFrame, day: str, mod) -> pd.DataFrame:
    """The target session's bars, bounded exactly as the engine bounds them.

    Imported from the strategy rather than restated. An excursion measured over
    a wider window than the strategy could trade would count movement on the
    warm-up day as opportunity the exit missed -- which is how the dip study
    first reported signals a median 245 bars 'earlier' than they were.
    """
    local = df.index.tz_convert(ET)
    m = ((local.date == _date.fromisoformat(day))
         & (local.time >= mod.SESSION_START) & (local.time < mod.SESSION_END))
    return df[m]


def excursion(bars: pd.DataFrame, trade) -> dict | None:
    """One trade's exit quality, per share.

    `ceiling` is the best price available AFTER the entry bar -- the perfect
    exit. `after` is what was still available after the actual exit bar.
    """
    entry_t = pd.Timestamp(trade.entry_time)
    exit_t = pd.Timestamp(trade.exit_time)
    post_entry = bars[bars.index > entry_t]
    if post_entry.empty:
        # Entered on the session's last bar. There was no opportunity to
        # capture and no exit decision to judge, so it is excluded rather than
        # scored as a perfect exit -- which is what a 0/0 capture ratio would
        # silently become.
        return None
    post_exit = bars[bars.index > exit_t]
    ceiling_px = float(post_entry["high"].max())
    after_px = float(post_exit["high"].max()) if not post_exit.empty \
        else float(trade.exit_price)
    return {
        "symbol": trade.symbol, "date": trade.date, "qty": trade.qty,
        "entry_px": float(trade.entry_price), "exit_px": float(trade.exit_price),
        "ceiling_px": ceiling_px, "after_px": after_px,
        "bars_held": int(trade.bars_held), "reason": trade.reason,
        "net": float(trade.net), "commission": float(trade.commission),
        # per share
        "captured": float(trade.exit_price) - float(trade.entry_price),
        "total_mfe": ceiling_px - float(trade.entry_price),
        "left": max(0.0, after_px - float(trade.exit_price)),
    }


def run_day(frame: pd.DataFrame, day: str, universe: list[dict], *, mod,
            extra: dict) -> list[dict]:
    d = _date.fromisoformat(day)
    out: list[dict] = []
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec["first_seen"]:
            continue
        try:
            trades = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                          not_before=first_seen_time(rec),
                                          **extra)
        except Exception:                                   # noqa: BLE001
            continue
        if not trades:
            continue
        bars = session_bars(df, day, mod)
        for t in trades:
            t.symbol, t.date = rec["symbol"], day
            row = excursion(bars, t)
            if row:
                out.append(row)
    return out


# --- scoring -----------------------------------------------------------------

def pct(values, p):
    v = sorted(values)
    return v[min(len(v) - 1, max(0, int(p * (len(v) - 1))))] if v else 0.0


def r_stats(nets: list[float]) -> dict:
    """Win rate, average win, average loss and R -- always together.

    `win_rate_and_r.md` §6: ten docs in this project state a win rate with no
    paired reward figure, which makes R unrecoverable from them. This function
    exists so that cannot happen again here.
    """
    wins = [n for n in nets if n > 0]
    losses = [-n for n in nets if n <= 0]
    w = len(wins) / len(nets) if nets else 0.0
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(losses) / len(losses) if losses else 0.0
    return {"n": len(nets), "win": w, "avg_win": aw, "avg_loss": al,
            "r": (aw / al) if al else 0.0,
            # break-even reward:risk at this win rate
            "r_req": ((1 - w) / w) if w else float("inf"),
            "net": sum(nets), "per": (sum(nets) / len(nets)) if nets else 0.0}


def ceiling_nets(rows: list[dict], friction: float) -> list[float]:
    """Each trade's net if it had been sold at the post-entry high.

    The same entries, the same share count, the same commission the real trade
    paid and the same friction. Only the exit price moves, which is what makes
    this a bound on the exit rather than a different strategy.
    """
    return [(r["ceiling_px"] - r["entry_px"]) * r["qty"] - r["commission"]
            - friction for r in rows]


def render(name: str, rows: list[dict], split: str, n_days: int,
           elapsed: float) -> list[str]:
    L = [f"MFE AFTER EXIT -- IS THE EXIT THE PROBLEM?  {name.upper()}", "",
         f"  {n_days} sessions, point-in-time universe, every entry floored at",
         f"  its own first_seen, {QTY} shares",
         f"  halves split at {split} (derived)",
         f"  elapsed {elapsed:.1f}s", "",
         "  NO PARAMETERS. The test is a bound: sell every trade at the highest",
         "  price available after its entry -- perfect foresight, the best exit",
         "  that could exist on these entries -- and compare R against what this",
         "  run's own win rate requires to break even. If the CEILING misses,",
         "  no exit rule can close the gap and the exit queue is a distraction.",
         ""]

    if len(rows) < MIN_TRADES:
        return L + ["NO VERDICT", "",
                    f"  {len(rows)} trades, below the {MIN_TRADES} floor.", ""]

    for fl, fv in FRICTIONS:
        real = r_stats([r["net"] - fv for r in rows])
        ceil = r_stats(ceiling_nets(rows, fv))
        if fl == "$4.26":
            headline = (real, ceil)
        L += [f"{fl} FRICTION", "",
              f"  {'':<10}{'n':>7}{'win%':>8}{'avg win':>10}{'avg loss':>10}"
              f"{'R':>8}{'R needed':>10}{'per trade':>12}",
              f"  {'actual':<10}{real['n']:>7}{100 * real['win']:>7.1f}%"
              f"${acct(real['avg_win'], 9)}${acct(real['avg_loss'], 9)}"
              f"{acct(real['r'], 8)}{acct(real['r_req'], 10)}"
              f"${acct(real['per'], 11)}",
              f"  {'ceiling':<10}{ceil['n']:>7}{100 * ceil['win']:>7.1f}%"
              f"${acct(ceil['avg_win'], 9)}${acct(ceil['avg_loss'], 9)}"
              f"{acct(ceil['r'], 8)}{acct(ceil['r_req'], 10)}"
              f"${acct(ceil['per'], 11)}", ""]

    real, ceil = headline
    L += ["THE ANSWER, at $4.26", "",
          f"  actual    R {acct(real['r'], 6)}  against "
          f"{acct(real['r_req'], 6)} needed at a "
          f"{100 * real['win']:.1f}% win rate",
          f"  ceiling   R {acct(ceil['r'], 6)}  against "
          f"{acct(ceil['r_req'], 6)} needed at a "
          f"{100 * ceil['win']:.1f}% win rate",
          f"  ceiling per trade {acct(ceil['per'], 9)}", ""]

    # A DEGENERATE R IS NOT A SMALL R. With no losers, `avg_loss` is 0 and R
    # reads 0.00 while the required R also reads 0.00 -- so the comparison below
    # would resolve to "worth attacking" on an arm where R does not exist. With
    # no winners, R is 0 against an infinite requirement and would resolve the
    # other way. Neither is a measurement, and both look exactly like one.
    degenerate = [lbl for lbl, s in (("actual", real), ("ceiling", ceil))
                  if s["avg_win"] == 0.0 or s["avg_loss"] == 0.0]
    if degenerate:
        L += [f"  NO VERDICT -- R does not exist on the {', '.join(degenerate)}"
              " arm.",
              "  It has no winners or no losers, so the reward:risk ratio has a",
              "  zero on one side and reads as 0.00 against a requirement that",
              "  is also degenerate. Read the per-trade column instead:",
              f"    actual {acct(real['per'], 9)}   "
              f"ceiling {acct(ceil['per'], 9)}", ""]
    elif ceil["r"] < ceil["r_req"]:
        L += ["  THE EXIT IS NOT THE PROBLEM. Even a perfect exit -- selling",
              "  every trade at the highest price it ever reached after entry --",
              "  does not reach the reward:risk this win rate needs to break",
              "  even. No exit rule can close that, because no exit rule can",
              "  beat perfect foresight. R is an ENTRY problem and the three",
              "  exit candidates should be dropped rather than run.", ""]
    elif ceil["per"] <= 0:
        L += ["  THE EXIT IS NOT THE PROBLEM, AND NEITHER IS R. A perfect exit",
              "  clears the reward:risk bar and STILL loses money per trade.",
              "  The entries do not contain enough favourable movement to pay",
              "  for themselves at any exit.", ""]
    else:
        L += ["  THE EXIT IS WORTH ATTACKING. A perfect exit clears the bar and",
              "  makes money, so the favourable movement exists and the current",
              "  rule is not capturing it. How much of the ceiling a real rule",
              "  would have to reach is the capture ratio below -- and a",
              "  perfect exit is not available, so read the ceiling as the",
              "  furthest any candidate could possibly get.", ""]

    # capture and what is left behind
    capt = [r["captured"] / r["total_mfe"] for r in rows if r["total_mfe"] > 0]
    left = [r["left"] for r in rows]
    winners = [r for r in rows if r["net"] > 0]
    losers = [r for r in rows if r["net"] <= 0]
    L += ["HOW MUCH OF THE MOVE IS CAPTURED", "",
          f"  trades with any favourable movement   {len(capt):,} of "
          f"{len(rows):,}",
          f"  capture ratio, exit vs post-entry high",
          f"    p10 {acct(pct(capt, .1), 7)}   p50 {acct(pct(capt, .5), 7)}"
          f"   p90 {acct(pct(capt, .9), 7)}", "",
          f"  left on the table after the exit, $/share",
          f"    p10 {acct(pct(left, .1), 7)}   p50 {acct(pct(left, .5), 7)}"
          f"   p90 {acct(pct(left, .9), 7)}",
          f"    mean {acct(sum(left) / len(left), 7)}"
          f"   = {acct(sum(left) / len(left) * QTY, 7)} per trade on "
          f"{QTY} shares", ""]

    L += ["HOLD TIME BY OUTCOME", "",
          "  Garvey & Murphy (FAJ 2004) found 15 profitable professionals held",
          "  losers 268s against winners 166s. The same asymmetry here would",
          "  point at the stop rather than the target.", "",
          f"  winners  {len(winners):,} trades, median "
          f"{pct([r['bars_held'] for r in winners], .5):.0f} bars",
          f"  losers   {len(losers):,} trades, median "
          f"{pct([r['bars_held'] for r in losers], .5):.0f} bars", ""]

    by_reason: dict[str, list[float]] = {}
    for r in rows:
        by_reason.setdefault(r["reason"], []).append(r["left"])
    L += ["WHAT IS LEFT BEHIND, BY EXIT REASON", "",
          f"  {'reason':<18}{'n':>7}{'median left':>14}{'mean left':>12}"]
    for reason, v in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        L.append(f"  {reason:<18}{len(v):>7}${acct(pct(v, .5), 13)}"
                 f"${acct(sum(v) / len(v), 11)}")

    return L + ["", "WHAT THIS IS NOT", "",
                "  Not a strategy. The ceiling uses perfect foresight and is a",
                "  BOUND, not a rule anyone could trade.",
                "",
                "  Not conservative in the flattering direction. Both",
                "  excursions look only at bars STRICTLY AFTER their reference",
                "  bar, so both understate the opportunity -- which cannot",
                "  manufacture a gap that is not there.",
                "",
                "  Not the published exit results. Those ran on `bar_cache_xnas`",
                "  over the stage-2 universe, unfloored. This is the",
                "  point-in-time universe with every entry floored.",
                "",
                "  Not out of sample. `holdout.json` has NOT been spent."]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--strategy", default="mcl")
    p.add_argument("--pairs", default="var/state/screen_pairs_pit.json")
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import read_dbn
    from common.screen_sim import window_slices, date_of

    name = a.strategy.strip().lower()
    mod, extra = engine(name)
    out_path = a.out or f"var/reports/mfe_exit_{name}.txt"

    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    pit = load_pit(Path(a.pairs))
    days = sorted(d for d in pit if d in slices)
    if a.limit:
        days = days[:a.limit]
    universe = {d: v for d, v in pit.items() if d in set(days)}
    want = needed_symbols([universe], days, WARMUP_SESSIONS)

    t0 = time.time()
    rows: list[dict] = []
    cache: deque = deque(maxlen=WARMUP_SESSIONS + 1)
    for i, day in enumerate(days, 1):
        try:
            bars = read_dbn(slices[day])
        except Exception as e:                              # noqa: BLE001
            print(f"  {day}: unreadable ({type(e).__name__}: {e})")
            cache.clear()
            continue
        cache.append((day, bars[bars["symbol"].isin(want.get(day, set()))]))
        recs = universe.get(day)
        if recs:
            rows += run_day(build_frame(cache, day), day, recs, mod=mod,
                            extra=extra)
        if i % 25 == 0:
            print(f"  {i}/{len(days)}  {day}  {len(rows):,} trades")

    split = halves_split([r["date"] for r in rows])
    emit("\n".join(render(name, rows, split, len(days), time.time() - t0)),
         out_path,
         header=f"common.mfe_exit  strategy={name}"
                + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
