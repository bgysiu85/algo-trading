#!/usr/bin/env python3
r"""Was the modelled fill ever available? The backtest against the real quote.

    python -m common.quote_fill --jobs 8

WHAT THIS CHECKS, AND WHY IT IS NOT ANOTHER STUDY
--------------------------------------------------
Every figure this project has published rests on one modelled fill:

    buy  at the signal bar's CLOSE + 1 tick
    sell at the exit bar's   CLOSE - 1 tick
    and $4.26 per round trip on 100 shares for everything else

The $4.26 was measured on ONE live session whose exit mix no longer exists.
The close-plus-a-tick was inherited from the Pine backtest. Neither has ever
been checked against what the market was actually showing at those moments --
and `entry_margins` has since established that **39.7% of entries fired on a
bar that traded under $100,000**, where a penny spread is not the default.

`tcbbo` is on disk already: every trade with the prevailing bid and ask
attached. So for each entry and each exit, there is a real quote to price
against. This is a VALIDITY CHECK on results already published, not a search
for a new edge -- and it can only move them in one direction or the other, not
leave them where they are.

THE THREE QUESTIONS
-------------------
1. WHAT WAS THE SPREAD? In cents and in basis points, at the entry bar. If the
   median is 4c on a $5 name, $4.26 per 100-share round trip is roughly ONE
   spread and the friction constant is about half of what it should be.

2. WAS THE MODELLED PRICE REACHABLE? A market buy pays the ASK. Where the
   model's close+1c sits BELOW the ask, it bought at a price nobody was
   offering. The same on the exit against the BID -- which is the one that
   matters, because a trailing stop fires into a falling bid.

3. WHAT IS THE BOOK WORTH REPRICED? Buy the ask, sell the bid, same trades,
   same exits. That number is the honest one, and if it is far from -$9.14 then
   every comparison made this week was made against the wrong baseline.

A STALE QUOTE IS ITS OWN ANSWER, AND IT IS NOT A MISSING ONE
-------------------------------------------------------------
`tcbbo` carries a quote only where a TRADE printed. On a dead pre-market minute
the last print can be twenty minutes old, and pricing a fill against a
twenty-minute-old quote produces a figure that is precise and meaningless.

So every match records the AGE of the quote it used, fresh and stale are
reported as separate strata, and a disagreement between them refuses a verdict
-- the same rule a halves disagreement gets. The stale rows are not dropped:
"no recent quote" is itself evidence about how thin these bars are, and
dropping them would quietly restrict this to the liquid half of a population
whose thinness is the thing under examination.
"""
from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

from common.entry_shares import MEASURED_FRICTION, PUBLISHED_TRADES, QTY, split
from common.report_io import emit

ET = ZoneInfo("America/New_York")

# A quote older than this is STALE: reported apart, never dropped, never
# averaged in with the fresh ones. 60s is `friction_quotes`' own tolerance and
# is reused so the two modules mean the same thing by the word.
FRESH_S = 60
# The outer bound on how far back a quote may be taken from at all. Beyond it
# there is no quote, rather than a bad one.
TOLERANCE_S = 1_800

DATASET = "XNAS.BASIC"
SCHEMA = "tcbbo"
PAIRS = "var/state/screen_pairs_pit.json"


# --- the tape ---------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    """One session's trades with their timestamps, and the quotes beside them.

    The trades come from the SAME engine call every other study uses. Nothing
    here re-derives a signal or an exit: a second implementation beside the
    question is how the live path and the backtest drifted apart for three days.
    """
    import numpy as np
    import pandas as pd

    from common.dbn_io import read_dbn
    from common.friction_quotes import quotes_for_date
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe, archive = args
    mod, extra = engine("mcl")
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, [], f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, [], ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)

    legs: list[dict] = []
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
        for n, t in enumerate(trades):
            # ONE ROW PER LEG, not per trade. A buy and a sell are priced
            # against different sides of the book, and folding them into one
            # row would force a choice of which side to keep.
            legs.append({"symbol": rec["symbol"], "date": day, "trade": n,
                         "side": "BUY", "ts": pd.Timestamp(t.entry_time),
                         "model_px": float(t.entry_price),
                         "gross": (t.exit_price - t.entry_price) * QTY})
            legs.append({"symbol": rec["symbol"], "date": day, "trade": n,
                         "side": "SELL", "ts": pd.Timestamp(t.exit_time),
                         "model_px": float(t.exit_price),
                         "gross": (t.exit_price - t.entry_price) * QTY})
    if not legs:
        return day, [], ""

    quotes = quotes_for_date(Path(archive), DATASET, day, SCHEMA)
    if quotes.empty:
        # NO QUOTE FILE IS NOT NO QUOTES. The session is reported as uncovered
        # rather than as a session whose fills all happened to be unpriceable.
        return day, [dict(r, covered=False) for r in legs], ""

    f = pd.DataFrame(legs)
    f["ts"] = f["ts"].astype("datetime64[ns, UTC]")
    q = quotes.copy()
    q["ts"] = q["ts"].astype("datetime64[ns, UTC]")
    q["quote_ts"] = q["ts"]
    m = pd.merge_asof(f.sort_values("ts"), q.sort_values("ts"), on="ts",
                      by="symbol", direction="backward",
                      tolerance=pd.Timedelta(seconds=TOLERANCE_S))
    out = []
    for r in m.to_dict("records"):
        row = {k: r[k] for k in ("symbol", "date", "trade", "side",
                                 "model_px", "gross")}
        if r.get("bid") is None or r["bid"] != r["bid"]:
            row["covered"] = False
        else:
            row.update(covered=True, bid=float(r["bid"]), ask=float(r["ask"]),
                       bid_sz=float(r.get("bid_sz") or 0.0),
                       ask_sz=float(r.get("ask_sz") or 0.0),
                       age_s=float((r["ts"] - r["quote_ts"]).total_seconds()))
        out.append(row)
    return day, out, ""


# --- derived ----------------------------------------------------------------

def enrich(rows: list[dict]) -> list[dict]:
    """Spread, staleness, and what the model paid against what was showing.

    `shortfall` is POSITIVE when the model got a better price than the book was
    offering -- a buy below the ask, or a sell above the bid. That sign
    convention is chosen so the flattering direction is the positive one and
    cannot be read as a cost by accident.
    """
    for r in rows:
        if not r.get("covered"):
            continue
        mid = (r["bid"] + r["ask"]) / 2.0
        r["mid"] = mid
        r["spread"] = r["ask"] - r["bid"]
        r["spread_bps"] = (r["spread"] / mid * 10_000.0) if mid else float("nan")
        r["fresh"] = r["age_s"] <= FRESH_S
        if r["side"] == "BUY":
            r["book_px"] = r["ask"]
            r["shortfall"] = r["ask"] - r["model_px"]
        else:
            r["book_px"] = r["bid"]
            r["shortfall"] = r["model_px"] - r["bid"]
    return rows


def pairs(rows: list[dict]) -> list[dict]:
    """Legs folded back into trades, keeping only trades with BOTH legs priced.

    A trade priced on one leg and modelled on the other is two price bases in
    one number, which is this project's most persistent defect wearing a new
    hat. Counted and excluded rather than half-repriced.
    """
    by: dict[tuple, dict] = defaultdict(dict)
    for r in rows:
        by[(r["date"], r["symbol"], r["trade"])][r["side"]] = r
    out = []
    for key, legs in by.items():
        b, s = legs.get("BUY"), legs.get("SELL")
        if not b or not s:
            continue
        if not (b.get("covered") and s.get("covered")):
            continue
        out.append({
            "date": key[0], "symbol": key[1],
            "gross": b["gross"],
            # Bought at the offer, sold at the bid: the price a market order
            # actually gets, on both sides.
            "book_gross": (s["bid"] - b["ask"]) * QTY,
            "entry_spread": b["spread"], "exit_spread": s["spread"],
            "entry_bps": b["spread_bps"], "exit_bps": s["spread_bps"],
            "fresh": bool(b["fresh"] and s["fresh"]),
            "give_up": (b["shortfall"] + s["shortfall"]) * QTY,
        })
    return out


# --- sections ---------------------------------------------------------------

def q(vals, p):
    return vals[min(len(vals) - 1, int(p * len(vals)))] if vals else float("nan")


def coverage(rows: list[dict], trades: list[dict], n_days: int,
             n_cov_days: int) -> list[str]:
    legs = len(rows)
    cov = sum(1 for r in rows if r.get("covered"))
    fresh = sum(1 for r in rows if r.get("covered") and r.get("fresh"))
    L = ["COVERAGE", "",
         f"  sessions run              {n_days:,}",
         f"  sessions with a quote file{n_cov_days:>8,}",
         f"  legs (2 per trade)        {legs:,}",
         f"  legs with a quote         {cov:,}"
         + (f"   {100.0*cov/legs:5.1f}%" if legs else ""),
         f"  of those, fresh (<={FRESH_S}s)  {fresh:,}"
         + (f"   {100.0*fresh/cov:5.1f}%" if cov else ""),
         f"  trades priced on BOTH legs{len(trades):>8,}", ""]
    pub = PUBLISHED_TRADES.get("mcl")
    if pub:
        L += [f"  published book            {pub:,}",
              "",
              "  This prices the subset with quotes on both sides. It is not",
              "  the whole book and is not claimed to be -- the figures below",
              "  describe the trades that could be priced, and the halves are",
              "  cut within THAT population rather than inherited.", ""]
    return L


def spread_section(trades: list[dict]) -> list[str]:
    ent = sorted(t["entry_spread"] for t in trades)
    ext = sorted(t["exit_spread"] for t in trades)
    ebp = sorted(t["entry_bps"] for t in trades)
    xbp = sorted(t["exit_bps"] for t in trades)
    L = ["WHAT THE SPREAD ACTUALLY WAS", "",
         f"  {'':<10}{'p10':>10}{'p25':>10}{'p50':>10}{'p75':>10}{'p90':>10}", ""]
    for lab, v in (("entry  c", ent), ("exit   c", ext)):
        L.append(f"  {lab:<10}" + "".join(f"{q(v, p)*100:>10,.1f}"
                                          for p in (.1, .25, .5, .75, .9)))
    for lab, v in (("entry bps", ebp), ("exit  bps", xbp)):
        L.append(f"  {lab:<10}" + "".join(f"{q(v, p):>10,.0f}"
                                          for p in (.1, .25, .5, .75, .9)))
    med = (q(ent, .5) + q(ext, .5)) * QTY
    L += ["",
          f"  ONE ROUND TRIP OF SPREAD, at the medians, on {QTY} shares:"
          f"  ${med:,.2f}",
          f"  the constant every backtest charges for ALL friction:"
          f"  ${MEASURED_FRICTION:,.2f}", ""]
    if med > MEASURED_FRICTION:
        L += [f"  *** CROSSING THE SPREAD ALONE COSTS MORE THAN THE WHOLE",
              f"      FRICTION ALLOWANCE. ${MEASURED_FRICTION:.2f} was measured on one",
              "      session and is charged for spread, commission and",
              "      slippage together. Every net in this project is therefore",
              "      optimistic, and the gap below says by how much. ***", ""]
    else:
        L += ["  The allowance covers the median spread. That does not make it",
              "  right -- it has to cover commission and slippage too -- but it",
              "  is not obviously too small.", ""]
    return L


def reachable_section(rows: list[dict]) -> list[str]:
    L = ["WAS THE MODELLED PRICE EVER SHOWING?", "",
         "  A market buy pays the ASK and a market sell hits the BID. Where the",
         "  model's price is better than that, it transacted at a price nobody",
         "  was quoting.", "",
         f"  {'side':<6}{'legs':>9}{'model better':>14}{'median gap c':>14}"
         f"{'p90 gap c':>12}", ""]
    for side in ("BUY", "SELL"):
        v = [r for r in rows if r.get("covered") and r["side"] == side]
        if not v:
            continue
        short = sorted(r["shortfall"] for r in v)
        better = sum(1 for x in short if x > 0)
        L.append(f"  {side:<6}{len(v):>9,}{100.0*better/len(v):>13.1f}%"
                 f"{q(short, .5)*100:>14,.2f}{q(short, .9)*100:>12,.2f}")
    L += ["",
          "  `model better` is the share of legs where the backtest's price",
          "  beat the book. A positive gap is money the model gave itself.", ""]
    return L


def repriced_section(trades: list[dict]) -> list[str]:
    """The book at the ask and the bid, against the book as published."""
    def pt(rows, key):
        return (sum(r[key] - MEASURED_FRICTION for r in rows) / len(rows)
                if rows else 0.0)

    L = ["THE SAME TRADES, PRICED AT THE BOOK", "",
         "  Bought at the offer, sold at the bid, same entries, same exits,",
         f"  same ${MEASURED_FRICTION:.2f} charged on top so the comparison moves only",
         "  the fill.", "",
         f"  {'stratum':<16}{'n':>8}{'as modelled':>14}{'at the book':>14}"
         f"{'difference':>13}", ""]
    strata = [("all priced", trades),
              ("fresh quotes", [t for t in trades if t["fresh"]]),
              ("stale quotes", [t for t in trades if not t["fresh"]])]
    got = {}
    for name, rows in strata:
        if not rows:
            L.append(f"  {name:<16}{0:>8}{'-':>14}{'-':>14}{'-':>13}")
            continue
        a, b = pt(rows, "gross"), pt(rows, "book_gross")
        got[name] = (a, b)
        L.append(f"  {name:<16}{len(rows):>8,}{a:>14,.2f}{b:>14,.2f}"
                 f"{b - a:>13,.2f}")
    L += [""]
    for name, rows in strata[:1]:
        a, b = split(rows)
        if a and b:
            L += [f"  both halves, all priced:  1st "
                  f"{pt(a, 'gross'):,.2f} -> {pt(a, 'book_gross'):,.2f}"
                  f"   2nd {pt(b, 'gross'):,.2f} -> {pt(b, 'book_gross'):,.2f}",
                  ""]
    if "fresh quotes" in got and "stale quotes" in got:
        df = got["fresh quotes"][1] - got["fresh quotes"][0]
        ds = got["stale quotes"][1] - got["stale quotes"][0]
        if (df > 0) != (ds > 0):
            L += ["  *** FRESH AND STALE DISAGREE ON THE SIGN OF THE",
                  "      CORRECTION. A stale quote is not evidence about this",
                  "      fill, and no verdict is issued while the two", "",
                  "      populations point opposite ways. ***", ""]
        else:
            L += [f"  fresh and stale agree in direction "
                  f"({df:+,.2f} and {ds:+,.2f} per trade), so the correction is",
                  "  not an artefact of pricing dead minutes against old quotes.",
                  ""]
    return L


def render(rows: list[dict], trades: list[dict], n_days: int, n_cov: int,
           elapsed: float, jobs: int) -> list[str]:
    L = ["WAS THE MODELLED FILL EVER AVAILABLE?", "",
         f"  {DATASET} {SCHEMA}   elapsed {elapsed:.1f}s on {jobs} worker(s)",
         "",
         "  A VALIDITY CHECK ON PUBLISHED RESULTS, not a search for an edge.",
         "  The modelled fill -- close +/- one tick, plus a flat",
         f"  ${MEASURED_FRICTION:.2f}/round trip measured on ONE session -- has never been",
         "  checked against what the market was showing at those moments.", ""]
    L += coverage(rows, trades, n_days, n_cov)
    if not trades:
        return L + ["NOTHING COULD BE PRICED.", "",
                    "  No trade had a quote on both legs. That is a fact about",
                    "  the archive, not about the strategy.", ""]
    L += spread_section(trades)
    L += reachable_section(rows)
    L += repriced_section(trades)
    L += ["WHAT THIS IS NOT", "",
          "  NOT THE WHOLE BOOK. Only the trades with a quote on both legs.",
          "  NOT A QUEUE MODEL. Paying the ask assumes the offer was big enough",
          "  for 100 shares. Where it was not, the true cost is worse than this,",
          "  never better -- so this correction is a FLOOR on the correction.",
          "  NOT A REASON TO RE-RUN EVERY STUDY. It says how far off the",
          "  baseline is; it does not change which lever moves it.",
          "  NOT OUT OF SAMPLE. holdout.json has not been spent here.", ""]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/quote_fill_mcl.txt")
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
    quote_days = {p.name[:10] for p in
                  (archive / DATASET / SCHEMA).glob("*.dbn.zst")}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    have = [d for d in days if d in slices]
    # ONLY THE SESSIONS WITH A QUOTE FILE. Running the rest would spend the
    # time to produce rows that can only be counted as uncovered.
    have = [d for d in have if d in quote_days]
    if not have:
        raise SystemExit(f"no session has a {SCHEMA} file under "
                         f"{archive / DATASET / SCHEMA}")

    all_days = [d for d in sorted(by_date) if d in slices]
    tasks = []
    for day in have:
        k = all_days.index(day)
        first = max(0, k - WARMUP_SESSIONS)
        tasks.append(([str(slices[d]) for d in all_days[first:k + 1]], day,
                      by_date[day], str(archive)))

    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"quote_fill: {len(tasks):,} session(s) with quotes on "
          f"{jobs} worker(s)", flush=True)
    t0 = time.time()
    got: dict[str, list] = {}
    if jobs == 1:
        it = map(run_day, tasks)
    else:
        from concurrent.futures import ProcessPoolExecutor
        ex = ProcessPoolExecutor(max_workers=jobs)
        it = ex.map(run_day, tasks, chunksize=1)
    for k, (day, res, err) in enumerate(it, 1):
        got[day] = res
        if err:
            print(f"  ! {day}: {err}", flush=True)
        if k % 25 == 0:
            print(f"  ... {k:,} of {len(tasks):,}", flush=True)
    if jobs != 1:
        ex.shutdown()

    rows: list[dict] = []
    for day in sorted(got):
        rows.extend(got[day])
    enrich(rows)
    emit("\n".join(render(rows, pairs(rows), len(tasks), len(got),
                          time.time() - t0, jobs)), a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
