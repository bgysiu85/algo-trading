#!/usr/bin/env python3
"""How much of a screened backtest is the screen's own look-ahead?

    python -m common.leak_control --strategy mcl mc5 vw9_5m \
        --survivors var/state/screen_pairs_consolidated.json \
        --rejects var/state/screen_rejects.json \
        --reports var/reports/screened --states var/state/screened

THE QUESTION
------------
common/screen.py splits its rules on purpose. Stage 1 -- a prior-close band and
a trailing 10-day dollar-volume floor -- is decidable at 03:59 on the morning in
question. Stage 2 -- today's RVOL and today's range -- is not: it uses the
session's own daily bar, which is not known until 20:00.

Stage 2 exists to decide which minute bars are worth buying, and as a budget it
is fine. As soon as a backtest runs over its survivors, though, it becomes a
selection rule that read the answer first, and the P/L it produces describes
"days that turned out active". That number is large, clean, and not a strategy
result. claude/session_aware_screening.md and PROGRAM_INDEX section 4 have both
said so since before there was a screen.

THE MEASUREMENT
---------------
Run the same strategies over a sample of stage-1 passers that stage 2 REJECTED,
drawn with the survivors' own date distribution, and compare:

    entries per evaluable symbol-day, survivors vs rejects
    net P/L per evaluable symbol-day, survivors vs rejects

If a strategy takes (almost) no entries on the rejected days, stage 2 is mostly
discarding days it would have skipped anyway, and the leak is small: the filter
is agreeing with the strategy rather than informing it.

If it takes a similar rate of entries on rejected days and loses money on them,
then stage 2 was doing the selecting, and the survivors' P/L is the leak.

WHAT A PASS DOES NOT PROVE
---------------------------
A low reject entry rate bounds the leak from the ENTRY side only. It says the
strategy would rarely have been in those names. It does not say the surviving
days' P/L is achievable -- position sizing, fills and the 60-a-day cap are all
still ahead of it. This is one control, not a clearance.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common.day_compare import read_state, read_trades


def population(pairs_path: Path) -> set[tuple[str, str]]:
    return {(p["symbol"], p["date"]) for p in json.load(open(pairs_path))}


def measure(reports: Path, states: Path, name: str, keys: set) -> dict:
    """Entries and P/L over the symbol-days of one population.

    Evaluable days only. A day with no bars is not evidence either way, and
    counting it as "no entry" would make any strategy look clean in exact
    proportion to how much data was missing.
    """
    blocks, _scaled = read_trades(reports / f"backtest_trades_{name}.csv")
    state = read_state(states / f"backtest_state_{name}.json")
    evaluable = [k for k, v in state.items()
                 if k in keys and v in ("TRADED", "NO TRADES")]
    trades = sum(blocks[k].trades for k in evaluable if k in blocks)
    net = sum(blocks[k].net for k in evaluable if k in blocks)
    with_any = sum(1 for k in evaluable if k in blocks and blocks[k].trades)
    return {"days": len(evaluable), "trades": trades, "net": net,
            "days_with_a_trade": with_any,
            "entries_per_day": trades / len(evaluable) if evaluable else 0.0,
            "share_of_days_traded": with_any / len(evaluable) if evaluable else 0.0,
            "net_per_day": net / len(evaluable) if evaluable else 0.0,
            # PER TRADE, not per day. The rate test below asks whether the
            # strategy would have BEEN in those names; this asks whether the
            # days stage 2 discarded were different in KIND. They are different
            # questions and on 2026-09-07 they gave different answers.
            "net_per_trade": (net / trades) if trades else None}


# A rejected-day entry rate at or below this share of the survivors' rate is
# reported as a small leak. It is a JUDGEMENT, not a measurement, and it is
# named here so it can be argued with rather than buried in an if.
SMALL_LEAK_RATIO = 0.25

# Below this many rejected-day trades, the per-trade comparison is a signal
# rather than a measurement and is reported as such. MC5's was n = 92 on
# 2026-09-07 -- enough to be worth saying out loud, not enough to conclude on.
QUALITY_MIN_TRADES = 30


def verdict(surv: dict, rej: dict) -> list[str]:
    if not surv["days"] or not rej["days"]:
        return ["  NOT MEASURABLE -- one of the two populations had no "
                "evaluable day."]
    if surv["entries_per_day"] <= 0:
        return ["  The strategy took no entries on the SURVIVORS either, so "
                "there is nothing for stage 2 to have leaked into."]
    ratio = rej["entries_per_day"] / surv["entries_per_day"]
    L = [f"  rejected-day entry rate is {ratio*100:.0f}% of the survivors'"]
    if ratio <= SMALL_LEAK_RATIO:
        L += ["  SMALL LEAK on the entry side. Stage 2 is mostly discarding "
              "days the",
              "  strategy would have skipped anyway -- the filter agrees with "
              "it rather",
              "  than informing it."]
    else:
        L += ["  THE LEAK IS LOAD-BEARING. The strategy enters at a comparable "
              "rate on",
              "  days stage 2 threw away, so what stage 2 removed was not "
              "'days the",
              "  strategy would skip' -- it was selection, done with the "
              "session's own",
              "  bar. Treat the survivors' P/L as a description of days that "
              "turned out",
              "  active, not as a result."]
    if rej["net_per_day"] < 0 and ratio > SMALL_LEAK_RATIO:
        L += [f"  Those rejected-day entries also LOST money "
              f"(${rej['net_per_day']:,.2f} per day),",
              "  which is the shape of a filter that was picking winners."]
    return L + quality_verdict(surv, rej)


def quality_verdict(surv: dict, rej: dict) -> list[str]:
    """The cut the entry-rate test does not make.

    ADDED 2026-09-07, because the rate test passed MC5 and this one did not.
    The rate test asks whether the strategy would have BEEN in the names stage
    2 discarded. It says nothing about whether those days were different in
    KIND -- and MC5 made +$1.11 a trade on survivors while losing $7.21 a trade
    on rejects. A filter that only removed days the strategy skips would not
    produce that gap; a filter that is selecting the days the strategy works on
    would.

    Computed by hand in a chat window the first time, which is exactly how a
    finding gets lost. It lives in the tool now.
    """
    a, b = surv.get("net_per_trade"), rej.get("net_per_trade")
    if a is None or b is None:
        return []
    L = ["",
         f"  per trade: survivors ${a:+,.2f}   rejected ${b:+,.2f}   "
         f"(n={rej['trades']:,})"]
    if rej["trades"] < QUALITY_MIN_TRADES:
        return L + [f"  Too few rejected-day trades (<{QUALITY_MIN_TRADES}) to "
                    "read anything into the gap."]
    if a > 0 and b < 0:
        L += ["  WARNING: profitable on the days stage 2 KEPT, unprofitable on "
              "the days",
              "  it THREW AWAY. That is the shape of stage 2 selecting the days "
              "the",
              "  strategy works on rather than merely agreeing with it -- and "
              "stage 2 is",
              "  the half that reads the session's own bar. The entry-rate test "
              "above",
              "  does not detect this and passing it is not a defence."]
    elif b >= a:
        L += ["  The rejected days were no worse per trade, so stage 2 was not "
              "selecting",
              "  on outcome. This is the stronger of the two passes."]
    return L


def render(rows: dict) -> list[str]:
    L = ["LEAKAGE CONTROL: stage 2 uses the session's own daily bar", "",
         "  Stage 1 is decidable at 03:59. Stage 2 is not. A backtest over",
         "  stage-2 survivors has read the answer first, so the question is",
         "  how much of its result that explains.", ""]
    for name, (surv, rej) in rows.items():
        L += [f"{name.upper()}", "",
              f"  {'':<12} {'days':>7} {'trades':>8} {'entries/day':>12} "
              f"{'days traded':>12} {'net/day':>11}",
              "  " + "-" * 66]
        for label, m in (("survivors", surv), ("rejected", rej)):
            L.append(f"  {label:<12} {m['days']:>7,} {m['trades']:>8,} "
                     f"{m['entries_per_day']:>12.3f} "
                     f"{m['share_of_days_traded']*100:>11.1f}% "
                     f"{m['net_per_day']:>11,.2f}")
        L += [""] + verdict(surv, rej) + [""]
    L += ["WHAT A PASS DOES NOT PROVE", "",
          "  A low rejected-day entry rate bounds the leak from the ENTRY side",
          "  only. Position sizing, fills and the per-day candidate cap are all",
          "  still ahead of any of these numbers. One control, not a",
          "  clearance."]
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure the stage-2 look-ahead")
    ap.add_argument("--strategy", nargs="+", default=["mcl", "mc5", "vw9_5m"])
    ap.add_argument("--survivors", required=True)
    ap.add_argument("--rejects", required=True)
    ap.add_argument("--reports", default="var/reports/screened")
    ap.add_argument("--states", default="var/state/screened")
    ap.add_argument("--out", default="var/reports/leak_control.txt")
    ap.add_argument("--csv", default="var/reports/leak_control.csv",
                    help="machine-readable form, for common.db_load --leak")
    a = ap.parse_args(argv)

    surv_keys = population(Path(a.survivors))
    rej_keys = population(Path(a.rejects))
    overlap = surv_keys & rej_keys
    if overlap:
        sys.exit(f"{len(overlap)} symbol-day(s) are in BOTH lists. The control "
                 "compares two disjoint populations; an overlap would put the "
                 "same day on both sides and flatten the difference.")

    rows = {}
    for n in a.strategy:
        rows[n] = (measure(Path(a.reports), Path(a.states), n, surv_keys),
                   measure(Path(a.reports), Path(a.states), n, rej_keys))

    if a.csv:
        # The verdict is prose and belongs in the report. The MEASUREMENTS
        # belong somewhere they can be compared against a later run -- which
        # a text file cannot do, and which is the whole reason the database
        # exists.
        import csv as _csv
        cols = ["strategy", "population", "days", "trades", "days_with_a_trade",
                "net", "entries_per_day", "share_of_days_traded",
                "net_per_day", "net_per_trade"]
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(a.csv, "w", newline="") as fh:
            w = _csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for name, (surv, rej) in rows.items():
                for pop, m in (("survivors", surv), ("rejected", rej)):
                    w.writerow({"strategy": name, "population": pop,
                                **{k: m.get(k) for k in cols[2:]}})
        print(f"wrote {a.csv}  ({len(rows) * 2} rows)")

    from common.report_io import emit
    emit("\n".join(render(rows)), a.out, header="common.leak_control")
    return 0


if __name__ == "__main__":
    sys.exit(main())
