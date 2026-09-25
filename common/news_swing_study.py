#!/usr/bin/env python3
r"""W07-0011 subitem 4 -- the Step-1 (no-AI) bucket report and §11.4 pass
bar, `docs/research/REGISTERED_swing_v0.md` §11.3-§11.4.

    python -m common.news_swing_study
    python -m common.news_swing_study --picks var/reports/swing_v0_picks.csv \
        --filings var/edgar/swing_news_filings.csv \
        --headlines var/news/swing_alpaca_headlines.csv

Reads SWING-v0's own picks (§11's PICK_FIELDS contract, `news_swing_tag.
load_picks_csv`), tags each with `news_swing_tag.tag_picks`, and reports
ALL / NEWS / NO NEWS per §11.3: trades, winners, gross $, costs, net $,
market-relative net $, full sample + both halves (median entry date, the
same cut convention §3 item 2 uses) + 2x-cost stress, share of picks per
bucket, sample trades. Negatives in brackets throughout (project convention).

THE LOPSIDED-SPLIT RULE COMES FIRST (§11.3): if either bucket holds under
10% of picks, this module reports "too lopsided to read" and does NOT score
§11.4 -- the split is still printed, never silently dropped.

WHAT §11.4's PASS BAR NEEDS THAT THIS MODULE DOES NOT HAVE
--------------------------------------------------------------
§11.4 item 1 (NO-NEWS net/trade beats ALL net/trade, full sample and both
halves) and item 3 (NO-NEWS keeps >= 40% of trades) are computable straight
from the tagged picks and ARE scored below. §11.4 item 2 -- "a NO-NEWS-only
version of the deployed cell passes §4 items 1-4 and 8 on its own" -- needs
SWING-v0's OWN §4 battery (the random-decile control, the cluster-by-month
bootstrap, drop-top-3, 2x-stress, the top-20-of-best-trades check), which
requires re-running the engine on the NO-NEWS-only population, not just
re-slicing this study's totals. This module reports that item as NOT
EVALUATED HERE and names what it needs, rather than approximating it from
figures this pass does not have -- the same discipline `news_study.hn2_
cell_block` uses for H-N2's paired-delta simulation it also cannot compute
from its own population alone.
"""
from __future__ import annotations

import argparse

from common.news_swing_pull import (DEFAULT_PICKS_CSV, SWING_FILINGS_CSV,
                                    SWING_HEADLINES_CSV, load_swing_headlines_csv)
from common.news_pull import load_filings_csv
from common.news_swing_tag import NEWS, NO_NEWS, load_picks_csv, tag_picks
from common.report_io import emit

REGISTERED = "docs/research/REGISTERED_swing_v0.md"
LOPSIDED_MIN_SHARE = 0.10       # §11.3: under 10% in either bucket
MIN_TRADES_KEPT_SHARE = 0.40    # §11.4 item 3
SAMPLE_TRADES_N = 5


def money(x) -> str:
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


# --- buckets -------------------------------------------------------------------

def bucket_split(tagged: list[dict]) -> dict[str, list[dict]]:
    return {"ALL": tagged,
           NEWS: [r for r in tagged if r["news_tag"] == NEWS],
           NO_NEWS: [r for r in tagged if r["news_tag"] == NO_NEWS]}


def lopsided(tagged: list[dict]) -> bool:
    """§11.3: either bucket under 10% of picks. Undefined (True, refuse to
    score) on an empty population -- there is nothing to split."""
    n = len(tagged)
    if n == 0:
        return True
    news_share = sum(1 for r in tagged if r["news_tag"] == NEWS) / n
    return news_share < LOPSIDED_MIN_SHARE or (1 - news_share) < LOPSIDED_MIN_SHARE


def median_cut(rows: list[dict]) -> str:
    dates = sorted({r["entry_date"] for r in rows})
    return dates[len(dates) // 2] if dates else ""


def halves(rows: list[dict], cut: str) -> tuple[list[dict], list[dict]]:
    return ([r for r in rows if r["entry_date"] < cut],
           [r for r in rows if r["entry_date"] >= cut])


# --- per-bucket stats, §11.3's own line items ---------------------------------

def bucket_stats(rows: list[dict]) -> dict:
    n = len(rows)
    winners = sum(1 for r in rows if r["net"] > 0)
    gross = sum(r["gross"] for r in rows)
    cost = sum(r["cost"] for r in rows)
    net = sum(r["net"] for r in rows)
    net_2x = sum(r["net_2x_stress"] for r in rows)
    mkt_rel = sum(r["mkt_rel_net"] for r in rows)
    return {"n": n, "winners": winners, "gross": gross, "cost": cost, "net": net,
           "net_2x_stress": net_2x, "mkt_rel_net": mkt_rel,
           "net_per_trade": net / n if n else None,
           "mkt_rel_per_trade": mkt_rel / n if n else None}


def bucket_block(name: str, rows: list[dict], share_of_all: float) -> list[str]:
    s = bucket_stats(rows)
    L = [f"{name}  --  {s['n']:,} trades  ({share_of_all:.1%} of all picks)", ""]
    if s["n"] == 0:
        return L + ["  (no picks in this bucket)", ""]
    L += [f"  winners            {s['winners']:,} of {s['n']:,}",
         f"  gross $            {money(s['gross'])}",
         f"  costs $            {money(s['cost'])}",
         f"  net $              {money(s['net'])}   (per trade {money(s['net_per_trade'])})",
         f"  net $ (2x stress)  {money(s['net_2x_stress'])}",
         f"  mkt-relative net $ {money(s['mkt_rel_net'])}   "
         f"(per trade {money(s['mkt_rel_per_trade'])})", ""]
    sample = rows[:SAMPLE_TRADES_N]
    if sample:
        L.append(f"  first {len(sample)} trades:")
        for r in sample:
            trig = f"  <- {r['news_trigger']}" if r.get("news_trigger") else ""
            L.append(f"    {r['symbol']:<6} {r['entry_date']} {r['entry_et']} ET  "
                     f"net {money(r['net']):>10}{trig}")
        L.append("")
    return L


# --- §11.4 pass bar -----------------------------------------------------------

def pass_bar(buckets: dict[str, list[dict]], cut: str) -> tuple[str, list[str]]:
    """Returns (verdict, explanation lines). verdict is one of
    'TOO LOPSIDED' | 'PASSES STEP 1' | 'FAILS STEP 1'. Item 2 of §11.4 is
    reported, never scored, per the module docstring."""
    all_rows, news_rows, no_news_rows = buckets["ALL"], buckets[NEWS], buckets[NO_NEWS]
    L = ["§11.4 PASS BAR", ""]

    all_stats = bucket_stats(all_rows)
    nn_stats = bucket_stats(no_news_rows)
    item1_full = (nn_stats["net_per_trade"] is not None and all_stats["net_per_trade"]
                 is not None and nn_stats["net_per_trade"] > all_stats["net_per_trade"])

    a_early, a_late = halves(all_rows, cut)
    nn_early, nn_late = halves(no_news_rows, cut)
    es_all, es_nn = bucket_stats(a_early), bucket_stats(nn_early)
    ls_all, ls_nn = bucket_stats(a_late), bucket_stats(nn_late)
    item1_early = (es_nn["net_per_trade"] is not None and es_all["net_per_trade"] is not None
                  and es_nn["net_per_trade"] > es_all["net_per_trade"])
    item1_late = (ls_nn["net_per_trade"] is not None and ls_all["net_per_trade"] is not None
                 and ls_nn["net_per_trade"] > ls_all["net_per_trade"])
    item1 = item1_full and item1_early and item1_late
    L.append(f"  1. NO-NEWS net/trade > ALL net/trade -- full {money(nn_stats['net_per_trade'] or 0)} "
             f"vs {money(all_stats['net_per_trade'] or 0)}   early {'OK' if item1_early else 'FAIL'}"
             f"   late {'OK' if item1_late else 'FAIL'}   -> {'PASSES' if item1 else 'FAILS'}")

    L.append("  2. NO-NEWS-only cell clears §4 items 1-4 and 8 on its own -- "
             "NOT EVALUATED HERE. Needs SWING-v0's own §4 battery (random-decile "
             "control, cluster-by-month bootstrap, drop-top-3, 2x-cost stress, "
             "top-20-of-best-trades check) re-run on the NO-NEWS-only population "
             "through the engine, once W07-0010 exists -- this module only tags "
             "and totals picks it is handed, it does not re-run the backtest.")

    item3_share = (nn_stats["n"] / all_stats["n"]) if all_stats["n"] else 0.0
    item3 = item3_share >= MIN_TRADES_KEPT_SHARE
    L.append(f"  3. NO-NEWS keeps >= {MIN_TRADES_KEPT_SHARE:.0%} of trades -- "
             f"{item3_share:.1%}   -> {'PASSES' if item3 else 'FAILS'}")

    verdict = "PASSES STEP 1" if (item1 and item3) else "FAILS STEP 1"
    L += ["", f"  VERDICT: {verdict} (item 2 not scored here -- see above)",
         "  If FAILS: W07-0011 closes with this result, no AI spend happens (§11.4).",
         "  If PASSES: item 2's holdout/battery run + §11.5 (Step 2, AI classifier, "
         "needs Ben's priced spend approval) are next.", ""]
    return verdict, L


# --- render --------------------------------------------------------------------

def render(tagged: list[dict], cut: str) -> list[str]:
    buckets = bucket_split(tagged)
    n = len(tagged)
    L = ["W07-0011 STEP 1 -- NEWS / NO-NEWS SPLIT ON SWING-v0 PICKS", "",
        f"  registered  {REGISTERED} §11",
        f"  population  {n:,} SWING-v0 picks (deployed cell: K=5, midday, N-ensemble)",
        f"  halves cut at {cut}", ""]

    if lopsided(tagged):
        share_news = (len(buckets[NEWS]) / n) if n else 0.0
        L += ["TOO LOPSIDED TO READ (§11.3)", "",
             f"  NEWS {share_news:.1%} of picks, NO NEWS {1 - share_news:.1%} -- one "
             f"bucket is under {LOPSIDED_MIN_SHARE:.0%}.",
             "  The split is reported below, but is NOT scored against §11.4 -- "
             "W07-0011 closes on this finding.", ""]
        for name in ("ALL", NEWS, NO_NEWS):
            L += bucket_block(name, buckets[name], len(buckets[name]) / n if n else 0.0)
        return L

    L.append("FULL SAMPLE")
    L.append("")
    for name in ("ALL", NEWS, NO_NEWS):
        L += bucket_block(name, buckets[name], len(buckets[name]) / n if n else 0.0)

    early, late = halves(tagged, cut)
    for label, rows in (("EARLY HALF", early), ("LATE HALF", late)):
        L.append(label)
        L.append("")
        bb = bucket_split(rows)
        m = len(rows)
        for name in ("ALL", NEWS, NO_NEWS):
            L += bucket_block(name, bb[name], len(bb[name]) / m if m else 0.0)

    _, bar_lines = pass_bar(buckets, cut)
    L += bar_lines

    L += ["WHAT THIS IS NOT", "",
         "  NOT STEP 2. The AI classifier (§11.5) has not run -- this is the "
         "plain-rule split only.",
         "  NOT A NEW ENGINE RUN. Trusts the `net` / `net_2x_stress` / "
         "`mkt_rel_net` figures the picks CSV already carries; this module "
         "computes no P&L of its own.",
         "  NOT THE HOLDOUT. holdout_swing.json is untouched by this module.", ""]
    return L


# --- cli ------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--picks", default=DEFAULT_PICKS_CSV)
    p.add_argument("--filings", default=SWING_FILINGS_CSV)
    p.add_argument("--headlines", default=SWING_HEADLINES_CSV)
    p.add_argument("--out", default="var/reports/news_swing_study.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    picks = load_picks_csv(a.picks)   # exits with a clear W07-0010 message if missing
    filings = load_filings_csv(a.filings)
    headlines = load_swing_headlines_csv(a.headlines)
    if not filings and not headlines:
        print("WARNING: no swing filings/headlines cache found -- every pick "
             "will read as NO NEWS. Run common.news_swing_pull first.", flush=True)
    tagged = tag_picks(picks, filings, headlines)
    cut = median_cut(tagged)
    body = render(tagged, cut)
    emit("\n".join(body), a.out,
        header=f"common.news_swing_study picks={a.picks} filings={a.filings} "
              f"headlines={a.headlines} registered={REGISTERED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
