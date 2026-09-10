#!/usr/bin/env python3
"""The take-profit ladder against holding, on MCL and MC5.

    python -m common.ladder_study --strategy mcl
    python -m common.ladder_study --strategy mc5

THE TABLE THAT ANSWERS THIS WITHOUT THE LADDER
-----------------------------------------------
Read §RUNG SURVIVAL first. It asks one question of the BASELINE trades and
needs no ladder to compute it:

    of the trades that ever reached +10%, how many went on to +21%?

That is the whole mechanic in one number. Sell half at +10% and you keep the
first 10% on those shares and forfeit everything above it. If most trades that
touch +10% carry on, the ladder is giving away the runners; if most give it
back, it is banking gains the trail would have surrendered.

A headline P/L can only tell you the net of those two. This table tells you
WHICH, and it cannot be fitted, because the ladder is not involved in it.

REGISTERED BEFORE THE RUN
-------------------------
`profit_ladder.py` records the expected sign as NEGATIVE, for the reason
`mcl_scale_out_decision.md` §4 gives: with size held constant, selling part of
a winner cannot earn more on a runner than holding it. `hold_cap_decision.md`
measured MCL's P/L by hold length and found its best bucket is 60+ bars at
+$36.33/trade -- the runners are the money.

The ladder is not a time cap, though, and that is why it is worth a run: it
never sells a loser early, so the left tail is untouched. If the tape says the
locked gains outweigh the forfeited upside, the tape wins over this paragraph.

CONTROLS
--------
Both halves at the derived midpoint of the sessions scored; drop-top-3 within
each variant; the trade count reported because the ladder frees the position
slot earlier and can change it; and the LINEAR ladder as a control, so a result
that only holds for the compounding form is visible as such.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common import profit_ladder as PL
from common.analysis import LIVE, MEASURED_FRICTION, load_sessions
from common import holdout as HO
from common.report_io import emit

ET = ZoneInfo("America/New_York")
QTY = 100
DROP = 3
# Where a trade's peak got to, as a multiple of entry. The rungs sit at 1.10,
# 1.21, 1.331 and 1.4641, so the buckets are cut to straddle them.
PEAK_BUCKETS = (1.0, 1.05, 1.10, 1.21, 1.331, 1.4641, 99.0)


def engine(name: str):
    if name == "mcl":
        from strategy.mcl import mcl as M
        return M, dict(LIVE)
    from strategy.mc5 import mc5 as M
    return M, {}


def run(sessions, mod, extra, *, ladder) -> list:
    out = []
    for sym, d, df in sessions:
        try:
            out += [(sym, d, t) for t in mod.backtest_session(
                df, datetime.strptime(d, "%Y-%m-%d").date(), ET,
                ladder=ladder, entry_shares=QTY, **extra)]
        except Exception:                                   # noqa: BLE001
            pass
    return out


def halves_split(dates) -> str:
    ds = sorted(set(dates))
    return ds[len(ds) // 2] if ds else ""


def stats(trades, split: str) -> dict:
    real = [t.net - MEASURED_FRICTION for _, _, t in trades]
    if not real:
        return {"n": 0, "net": 0.0, "per": 0.0, "dropped": 0.0, "win": 0.0,
                "early_n": 0, "late_n": 0, "early_per": 0.0, "late_per": 0.0}
    e = [r for (_, d, _), r in zip(trades, real) if d < split]
    l = [r for (_, d, _), r in zip(trades, real) if d >= split]
    net = sum(real)
    return {"n": len(real), "net": net, "per": net / len(real),
            "dropped": net - sum(sorted(real, reverse=True)[:DROP]),
            "win": 100.0 * sum(1 for r in real if r > 0) / len(real),
            "early_n": len(e), "late_n": len(l),
            "early_per": (sum(e) / len(e)) if e else 0.0,
            "late_per": (sum(l) / len(l)) if l else 0.0}


def rung_survival(base) -> list[str]:
    """How far the BASELINE trades ran, as a multiple of entry.

    Uses exit_price as the proxy for how far the trade got. That UNDERSTATES
    the peak on a trailing stop -- the trade reached higher before giving 5%
    back -- and the understatement is stated rather than corrected, because
    correcting it would need the intrabar peak, which the Trade record does not
    carry. Read the buckets as "where the trade ENDED", not "where it got to".
    """
    rows = [(t.exit_price / t.entry_price) for _, _, t in base
            if t.entry_price and t.entry_price > 0]
    if not rows:
        return ["  no trades", ""]
    L = ["RUNG SURVIVAL — where the baseline's trades ENDED, vs entry", "",
         "  exit_price / entry_price. On a trailing stop the trade reached",
         "  HIGHER than this before giving 5% back, so these buckets are a",
         "  lower bound on how many rungs were touched.", "",
         f"      {'band':<16}{'n':>7}{'share':>9}"]
    lo = PEAK_BUCKETS[0]
    for hi in PEAK_BUCKETS[1:]:
        sel = [r for r in rows if lo <= r < hi]
        label = f"{lo:.3f}-{hi:.3f}" if hi < 99 else f"{lo:.3f}+"
        L.append(f"      {label:<16}{len(sel):>7}{100 * len(sel) / len(rows):>8.1f}%")
        lo = hi
    reached = sum(1 for r in rows if r >= 1.10)
    past2 = sum(1 for r in rows if r >= 1.21)
    L += ["",
          f"  ended at or above the FIRST rung (+10%):  {reached} of {len(rows)}"
          f"  ({100 * reached / len(rows):.1f}%)",
          f"  ended at or above the SECOND rung (+21%): {past2}"
          + (f"  ({100 * past2 / max(reached, 1):.1f}% of those)" if reached else ""),
          ""]
    if reached == 0:
        L += ["  NO TRADE ENDED ABOVE THE FIRST RUNG. The ladder can only fire",
              "  intrabar on this tape, if at all, and any P/L difference below",
              "  is noise rather than the mechanic.", ""]
    return L


def render(name, base, lad, lin, split, n_sessions) -> list[str]:
    L = [f"TAKE-PROFIT LADDER vs HOLDING — {name.upper()}", "",
         f"  {n_sessions} cached sessions, {QTY} shares flat",
         f"  net after tiered commission and ${MEASURED_FRICTION}/RT friction",
         f"  halves split at {split} (derived)",
         f"  rungs: sell {PL.SELL_FRAC:.0f}% every +{PL.STEP_PCT:.0f}% "
         f"(compounding), whole remainder at or below {PL.FLOOR_SHARES} shares",
         f"  on 100 shares: 50 / 25 / 12 / 13 at +10.0% / +21.0% / +33.1% "
         f"/ +46.4%", ""]
    L += rung_survival(base)

    rows = [("hold (baseline)", base), ("ladder", lad),
            ("ladder, linear", lin)]
    L += [f"  {'variant':<18}{'trades':>8}{'net':>11}{'per':>8}{'win%':>7}"
          f"{'drop top 3':>12}"]
    got = {}
    for label, tr in rows:
        s = stats(tr, split)
        got[label] = s
        L.append(f"  {label:<18}{s['n']:>8}${s['net']:>10,.0f}${s['per']:>7.2f}"
                 f"{s['win']:>6.1f}%${s['dropped']:>11,.0f}")
    L.append("")

    a, b = got["hold (baseline)"], got["ladder"]
    if not a["n"] or not b["n"]:
        return L + ["  A VARIANT PRODUCED NO TRADES. Nothing to compare.", ""]
    inert = [k for k, s in got.items() if s["early_n"] == 0 or s["late_n"] == 0]
    if inert:
        return L + ["THE HALVES CONTROL DID NOT DIVIDE THIS RUN", "",
                    f"  {', '.join(inert)} has no trades on one side of "
                    f"{split}. NO VERDICT drawn.", ""]

    d = b["net"] - a["net"]
    de = b["early_per"] - a["early_per"]
    dl = b["late_per"] - a["late_per"]
    L += ["VERDICT on the ladder", "",
          f"  net {d:+,.0f}   per trade {b['per'] - a['per']:+.2f}",
          f"  per trade by half: early {de:+.2f}   late {dl:+.2f}",
          f"  win rate {b['win']:.1f}% vs {a['win']:.1f}%", ""]
    if d == 0:
        L += ["  IDENTICAL. The ladder never fired — see rung survival above.",
              "  That is a finding about this tape, not about the rule.", ""]
    elif d > 0 and de * dl > 0 and b["dropped"] > a["dropped"]:
        L += ["  BETTER on the total, in both halves, and after drop-top-3 —",
              "  and against a registered expectation that it would lose. That",
              "  is the strongest form available in-sample, and it is still",
              "  in-sample.", "",
              "  DO NOT SPEND THE HOLDOUT ON THIS FROM bar_cache. An earlier",
              "  version of this line said to, and it was wrong: holdout.json",
              "  was cut over the SCREENED universe, so a locked slice does not",
              "  apply to a bar_cache result. Spending it here is the",
              "  dataset-mixing error caught in consolidation_filter_test.md",
              "  and again in prior_spike_result.md. Re-run on bar_cache_xnas",
              "  first, where the holdout is meaningful.", ""]
    elif d > 0:
        why = [] if de * dl > 0 else ["the sign flips between halves"]
        if b["dropped"] <= a["dropped"]:
            why.append("it does not survive drop-top-3")
        L += [f"  Better on the total but {' and '.join(why)}. Not"
              f"  adoptable.", ""]
    else:
        L += ["  WORSE, as registered. Selling half a winner at +10% forfeits",
              "  the runners, and the runners are where the money is — see the",
              "  rung-survival table for how much of it was above the first",
              "  rung.", ""]

    c = got["ladder, linear"]
    L += ["  LINEAR CONTROL (rungs a flat 10% of entry, not compounding)",
          f"    net {c['net'] - a['net']:+,.0f} vs baseline "
          f"({d:+,.0f} for the compounding form)",
          "    A result that holds for one spelling of the rule and not the",
          "    other is a result about the spacing, not about taking profit.",
          ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not the scale-out rejected on 2026-09-05. That sold into a",
          "  PULLBACK and bought back; this sells into STRENGTH and does not.",
          "",
          "  Not out of sample. Both strategies were fitted on these sessions.",
          "",
          "  Not a live fill model. Each rung is an extra order, priced at the",
          "  bar close with one tick of slippage and a real per-order",
          "  commission — but whether a limit at that level fills at all, on a",
          "  pre-market small cap, is what the paper sessions are for."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--strategy", choices=["mcl", "mc5"], default="mcl")
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--spend-holdout", action="store_true",
                   help="read the LOCKED sessions instead of the "
                        "training ones. One-way: a holdout read "
                        "casually is not a holdout.")
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    out = a.out or f"var/reports/ladder_{a.strategy}.txt"
    mod, extra = engine(a.strategy)
    sessions = load_sessions(Path(a.cache))
    # THE HOLDOUT GUARD. Without it, pointing --cache at
    # bar_cache_xnas reads the LOCKED slice along with the
    # training one and spends the holdout while reporting an
    # ordinary-looking number. On bar_cache there is no
    # committed cut for that universe, so this is a no-op
    # there and the header says which side was taken.
    sessions, set_aside, side = HO.split_sessions(
        sessions, a.spend_holdout)
    if not sessions:
        sys.exit(f'no sessions on the {side} side of {a.cache}')
    split = halves_split([d for _, d, _ in sessions])
    emit("\n".join(render(
        a.strategy,
        run(sessions, mod, extra, ladder=None),
        run(sessions, mod, extra, ladder=PL.LadderConfig()),
        run(sessions, mod, extra, ladder=PL.LadderConfig(linear=True)),
        split, len(sessions))),
        out, header=f"common.ladder_study  strategy={a.strategy} "
                    f"cache={a.cache}  side={side}"
                    + (f"  ({set_aside} set aside)" if set_aside else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
