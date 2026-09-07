#!/usr/bin/env python3
"""Did the trades that followed the rules make more money than the ones that did not?

    python -m common.rules_vs_pnl --dataset EQUS.SUMMARY

THE QUESTION
------------
The rebuilt screen surfaces 367 of 587 traded symbol-days (63%), and RVOL alone
rejects 175 of them. Ben's own reading is that a portion of his selection falls
outside his stated rules -- so the gap is not a screen defect to be tuned away.

Which turns recall into the wrong question and this into the right one:

    the account is down $114,982.92 net over those 587 symbol-days.
    WHERE did that come from -- the trades that met the rules, or the ones
    that did not?

If the conforming trades did better, the rules have demonstrable value and the
discretion is what costs money. If they did the same or worse, the rules are
not the edge and a backtest that enforces them is not measuring the thing worth
measuring. Either answer changes what to build next; the current state, where
nobody has checked, does not.

WHY RECALL IS NOT THE OBJECTIVE
--------------------------------
PROGRAM_INDEX section 4 already records the standard: recall against a LOSING
sample is a diagnostic, not an objective. A screen tuned until it reproduces
every one of these trades would be tuned to reproduce a $114,982.92 loss.
This module exists to use that sample the only way it can honestly be used --
as a comparison BETWEEN its own parts.

THE THRESHOLDS, NOT THE CAPPED LIST
------------------------------------
Conformance is judged on stage1 AND stage2, not on membership of the capped
60-a-day candidate list. The cap is a budget for buying minute bars, not a
trading rule, and a trade excluded by it followed the rules perfectly well.
Judging against the capped list would mark those non-conforming and quietly
move P/L across the line for a reason that has nothing to do with the rules.
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

import pandas as pd

from common import flex
from common.databento_fetch import default_archive
from common.dbn_io import daily_frame
from common.report_io import emit
from common.screen import Config, features, is_test_symbol, stage1, stage2

RULES = ["prior-close sanity", "liquidity floor", "RVOL", "day range"]


def rule_flags(row, cfg: Config) -> dict:
    """Which individual rules a symbol-day passed. Independent, not sequential:
    a pair can fail several, and knowing WHICH is the point."""
    return {
        "prior-close sanity": bool(cfg.price_min <= row["prior_close"] <= cfg.price_max),
        "liquidity floor": bool(row["prior_avg_dollar_vol"] >= cfg.min_avg_dollar_vol),
        "RVOL": bool(row["rvol"] >= cfg.min_rvol),
        "day range": bool(row["range_pct"] >= cfg.min_range_pct),
    }


def join(days, feats: pd.DataFrame, cfg: Config) -> tuple[list[dict], list[dict]]:
    """Attach conformance to each traded symbol-day. Returns (rows, excluded).

    A traded symbol-day the screen cannot evaluate is EXCLUDED, never
    "non-conforming". Those are different claims -- "the rules said no" versus
    "we could not ask" -- and folding the second into the first loads every gap
    onto the discretion side of the comparison.

    The exclusions are then split by REASON, because the two are not the same
    finding at all:

      TOO NEW   the symbol has fewer than three prior sessions, so a 10-day
                average and an RVOL are undefined. The screen is structurally
                blind to these, by construction, forever.
      ABSENT    no bar in this dataset at all -- a coverage gap.

    The first version reported both as "no daily bar ... most likely before its
    start date". On the real data all seven were PRESENT, every one traded on
    its first or second day of existence, and the stated explanation was simply
    wrong. A new-listing blind spot and a date-range gap need different
    responses, and lumping them hid a category worth $14,151 of losses.
    """
    idx = {(r.symbol, r.date): r for r in feats.itertuples(index=False)}
    first_bar: dict[str, str] = {}
    for r in feats.itertuples(index=False):
        d = first_bar.get(r.symbol)
        if d is None or r.date < d:
            first_bar[r.symbol] = r.date

    rows, excluded = [], []
    for (sym, date), sd in sorted(days.items()):
        r = idx.get((sym, date))
        if r is None:
            excluded.append({"symbol": sym, "date": date, "net_pnl": sd.net_pnl,
                             "reason": "ABSENT", "first_bar": "", "prior": None})
            continue
        if pd.isna(r.prior_avg_dollar_vol) or pd.isna(r.rvol):
            prior = sum(1 for (s, d2) in idx if s == sym and d2 < date)
            excluded.append({"symbol": sym, "date": date, "net_pnl": sd.net_pnl,
                             "reason": "TOO NEW", "prior": prior,
                             "first_bar": first_bar.get(sym, "")})
            continue
        flags = rule_flags(r._asdict(), cfg)
        rows.append({
            "symbol": sym, "date": date,
            "net_pnl": sd.net_pnl, "gross_pnl": sd.gross_pnl,
            "commission": sd.commission, "executions": sd.executions,
            "max_position": sd.max_position,
            "rvol": float(r.rvol) if pd.notna(r.rvol) else None,
            "prior_avg_dollar_vol": float(r.prior_avg_dollar_vol)
            if pd.notna(r.prior_avg_dollar_vol) else None,
            "conforms": all(flags.values()),
            **{f"pass_{k}": v for k, v in flags.items()},
        })
    return rows, excluded


def drop_top(values, n: int) -> float:
    """Total after removing the n largest winners. A split that survives only
    because of two names is a fact about those names."""
    return sum(sorted(values, reverse=True)[n:])


def summarise(vals) -> dict:
    return {
        "n": len(vals),
        "total": sum(vals),
        "mean": st.mean(vals) if vals else 0.0,
        "median": st.median(vals) if vals else 0.0,
        "win_rate": (sum(1 for v in vals if v > 0) / len(vals)) if vals else 0.0,
        "drop1": drop_top(vals, 1),
        "drop3": drop_top(vals, 3),
        "drop5": drop_top(vals, 5),
    }


def render(rows, excluded, cfg: Config, dataset: str) -> str:
    L = [f"RULE-CONFORMING vs NON-CONFORMING TRADES  ({dataset})", "",
         "  Recall is NOT the objective here. This sample is a LOSS, and a",
         "  screen tuned to reproduce all of it would be tuned to reproduce",
         "  the loss. The only honest use of it is comparing its own parts.", ""]

    if not rows:
        L += ["NO TRADED SYMBOL-DAYS MATCHED A DAILY BAR.",
              "Check that the dataset's date range covers the trade history."]
        return "\n".join(L)

    conf = [r["net_pnl"] for r in rows if r["conforms"]]
    non = [r["net_pnl"] for r in rows if not r["conforms"]]
    a, b = summarise(conf), summarise(non)

    L += [f"  traded symbol-days matched   {len(rows):,}",
          f"  excluded, not evaluable      {len(excluded):,}"
          f"   net ${sum(e['net_pnl'] for e in excluded):,.2f}", ""]
    L += ["THE SPLIT", "",
          f"  {'':<22} {'CONFORMING':>16} {'NON-CONFORMING':>18}",
          "  " + "-" * 58,
          f"  {'symbol-days':<22} {a['n']:>16,} {b['n']:>18,}",
          f"  {'net P/L':<22} {a['total']:>16,.2f} {b['total']:>18,.2f}",
          f"  {'mean per symbol-day':<22} {a['mean']:>16,.2f} {b['mean']:>18,.2f}",
          f"  {'median':<22} {a['median']:>16,.2f} {b['median']:>18,.2f}",
          f"  {'profitable share':<22} {100*a['win_rate']:>15.1f}% "
          f"{100*b['win_rate']:>17.1f}%", "",
          f"  {'net, drop top 1':<22} {a['drop1']:>16,.2f} {b['drop1']:>18,.2f}",
          f"  {'net, drop top 3':<22} {a['drop3']:>16,.2f} {b['drop3']:>18,.2f}",
          f"  {'net, drop top 5':<22} {a['drop5']:>16,.2f} {b['drop5']:>18,.2f}", ""]

    # The comparison that matters. THE VERDICT MUST CONSULT DROP-TOP, not just
    # the level: the first version of this report printed "the rules look like
    # the better half" from the totals alone, while its own drop-top-1 row
    # showed the ranking reversing on the removal of ONE trade. Worse, the
    # "check the drop-top rows" caution was attached only to the unfavourable
    # branch -- so the comfortable answer was the one that escaped scrutiny.
    # PROGRAM_INDEX section 4 puts drop-top-N first for exactly this reason.
    thin = a["n"] < 30 or b["n"] < 30
    if thin:
        L += ["  TOO FEW ON ONE SIDE to compare means. Report the totals and",
              "  stop; a difference in means on this sample would be noise.",
              ""]

    if not thin:
        d = a["mean"] - b["mean"]
        lead_level = a["total"] - b["total"]
        lead_drop1 = a["drop1"] - b["drop1"]
        lead_drop3 = a["drop3"] - b["drop3"]
        L += [f"  Conforming trades averaged ${d:+,.2f} per symbol-day more "
              "than", "  non-conforming ones.",
              f"  Conforming lead on the total:  ${lead_level:+,.2f}",
              f"                    drop top 1:  ${lead_drop1:+,.2f}",
              f"                    drop top 3:  ${lead_drop3:+,.2f}", ""]

        if (lead_level > 0) != (lead_drop1 > 0):
            L += ["  THE RANKING REVERSES ON ONE TRADE. Removing the single "
                  "best", "  symbol-day flips which half looks better, so the "
                  "level comparison",
                  "  is a fact about that trade and not about the rules.",
                  "  Do NOT enforce or relax anything on this evidence.", "",
                  "  The robust statistics are what is left:",
                  f"    median      conforming ${a['median']:,.2f} vs "
                  f"non-conforming ${b['median']:,.2f}",
                  f"    profitable  {100*a['win_rate']:.1f}% vs "
                  f"{100*b['win_rate']:.1f}%"]
        elif lead_level > 0 and lead_drop3 > 0:
            L += ["  THE RULES LOOK LIKE THE BETTER HALF, and it survives "
                  "dropping", "  the top 3. That is an argument for enforcing "
                  "them, not for",
                  "  widening the screen to admit what they reject."]
        elif lead_level < 0 and lead_drop3 < 0:
            L += ["  THE RULES LOOK LIKE THE WORSE HALF, and it survives "
                  "dropping", "  the top 3. Enforcing them in a backtest would "
                  "be selecting the",
                  "  losing subset, and the rules are not the edge assumed."]
        else:
            L += ["  NO STABLE SEPARATION. The direction depends on how many "
                  "top", "  trades are removed, so the sample cannot answer "
                  "this."]
        L.append("")

    # Both halves can lose. A verdict about which is BETTER says nothing about
    # whether either is worth trading, and the ranking language above invites
    # exactly that misreading.
    if a["total"] < 0 and b["total"] < 0:
        L += [f"  Note that BOTH halves lost money: conforming ${a['total']:,.2f}"
              f" over {a['n']:,} symbol-days",
              f"  (${a['mean']:,.2f} each). 'Better half' is a ranking, not a "
              "case for the rules", "  being profitable.", ""]

    L += ["WHICH RULE REJECTS THE MONEY", "",
          f"  {'rule':<22} {'failed':>7} {'their net P/L':>16} "
          f"{'mean':>12}", "  " + "-" * 60]
    for rule in RULES:
        bad = [r["net_pnl"] for r in rows if not r[f"pass_{rule}"]]
        if not bad:
            L.append(f"  {rule:<22} {0:>7}")
            continue
        L.append(f"  {rule:<22} {len(bad):>7} {sum(bad):>16,.2f} "
                 f"{st.mean(bad):>12,.2f}")
    L += ["", "  A rule whose rejects were PROFITABLE is costing money. One",
          "  whose rejects lost money is doing its job. Rules are independent",
          "  here, so a symbol-day can appear on several rows."]

    if excluded:
        L += ["", "EXCLUDED, AND WHY", ""]
        for reason, note in (
            ("TOO NEW", "fewer than 3 prior sessions, so a 10-day average and "
                        "an RVOL do not exist"),
            ("ABSENT", "no bar in this dataset at all"),
        ):
            grp = [e for e in excluded if e["reason"] == reason]
            if not grp:
                continue
            tot = sum(e["net_pnl"] for e in grp)
            L += [f"  {reason}  --  {note}",
                  f"  {len(grp)} symbol-days, net ${tot:,.2f}", ""]
            for e in sorted(grp, key=lambda x: x["net_pnl"]):
                pri = "" if e["prior"] is None else f"  {e['prior']} prior session(s)"
                fb = f"  first bar {e['first_bar']}" if e["first_bar"] else ""
                L.append(f"    {e['symbol']:<8} {e['date']}  "
                         f"${e['net_pnl']:>12,.2f}{pri}{fb}")
            L.append("")
            if reason == "TOO NEW":
                L += ["  These are not a coverage gap and not rule-breaking.",
                      "  The screen CANNOT evaluate a name on its first or",
                      "  second session -- RVOL needs a prior average, and one",
                      "  does not exist yet. It is a permanent structural blind",
                      "  spot, and on this sample it is a LOSING one. A system",
                      "  built from these rules needs an explicit policy on new",
                      "  listings rather than an accidental silence.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rule conformance against real P/L")
    ap.add_argument("--flex", nargs="+", required=True,
                    help="IBKR Flex trade report(s)")
    ap.add_argument("--archive", default=str(default_archive()))
    ap.add_argument("--dataset", default="EQUS.SUMMARY")
    ap.add_argument("--min-avg-dollar-vol", type=float)
    ap.add_argument("--min-rvol", type=float)
    ap.add_argument("--report", default="var/reports/rules_vs_pnl.txt")
    ap.add_argument("--csv", default="var/reports/rules_vs_pnl.csv")
    a = ap.parse_args(argv)

    cfg = Config()
    if a.min_avg_dollar_vol is not None:
        cfg.min_avg_dollar_vol = a.min_avg_dollar_vol
    if a.min_rvol is not None:
        cfg.min_rvol = a.min_rvol

    execs = flex.load_many(a.flex)
    days = flex.symbol_days(execs)
    days = {k: v for k, v in days.items() if not is_test_symbol(k[0])}
    print(f"{len(days):,} traded symbol-days from {len(execs):,} executions")

    daily = daily_frame(a.archive, a.dataset)
    if daily.empty:
        sys.exit(f"no daily bars in {a.archive}/{a.dataset}/ohlcv-1d/")
    feats = features(daily, cfg)
    # Deliberately NOT dropping rows whose prior average is NaN. Those are the
    # names too new to evaluate, and filtering them here is what made them
    # arrive as an unexplained "no daily bar" instead of a named category.
    print(f"{len(feats):,} symbol-days of features "
          f"({feats['prior_avg_dollar_vol'].isna().sum():,} too new to score)")

    rows, excluded = join(days, feats, cfg)
    if rows:
        out = Path(a.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"per-symbol-day rows written to {out}")

    emit(render(rows, excluded, cfg, a.dataset), a.report,
         header=f"common.rules_vs_pnl  dataset={a.dataset}  "
                f"min_rvol={cfg.min_rvol}  "
                f"min_avg_dollar_vol={cfg.min_avg_dollar_vol:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
