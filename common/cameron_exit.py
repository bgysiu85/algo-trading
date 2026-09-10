#!/usr/bin/env python3
"""Cameron's exit against MCL's trail — a 2x2 that separates the two changes.

    python -m common.cameron_exit

THE QUESTION
------------
`warrior_0` §5.3, `warrior_1` §6 and `HANDOVER_TO_BUILD_20260910.md` all name
this as the largest untested gap in the spec set, and §0 of the handover says
why it outranks the other gaps: MCL is Ben's own version of this method, loosely
derived, so this is not two designs being compared. It is the intent, and MCL is
the drift.

    Cameron 2025   71.1% win, R 1.20, breakeven 45.5%, margin +25.6
    MCL            32.4% win, R 2.01, breakeven 33.2%, margin  -0.8

WHY A 2x2 AND NOT A COMPARISON
-------------------------------
His exit is TWO changes at once — take half at a target, and replace the trail
with a breakeven stop. Testing the combination alone would say whether it wins
and nothing about which half won, and one half is already measured:
`ladder_study` found selling half at +10% worth +$272 (+$106 after charging the
extra orders) on 2026-09-11, against a registered prediction that it would lose.

    |            | trail on remainder | breakeven on remainder |
    |------------|--------------------|------------------------|
    | no partial | MCL today          | stop change alone      |
    | half at 2R | the partial alone  | CAMERON'S EXIT         |

THE ONE THING THAT INVERTS THE NAIVE READING
---------------------------------------------
A breakeven stop sounds like risk reduction. It is the opposite for a winner.

Once a trade is up more than about 5.3%, the entry price sits BELOW a 5% trail
from the peak — so moving the stop to breakeven gives the remainder MORE room,
not less. Measured on a constructed fade: the trail exits at 4.4459 after 33
bars; breakeven holds to 4.0208 and 53 bars. On that trade the trail wins by
$21.

So the mechanic is not "lock in a profit". It is **take the certain half, then
give the rest a very wide stop and let it run or scratch.** That is what
produces a high win rate — a scratch is not a loss — and it is also why it can
lose to a trail on any name that fades slowly rather than running.

WHICH DOMINATES IS THE MEASUREMENT. Registering the expectation first: MCL's
trades are 10.9% reaching +10% and only 28.3% of those going on to +21%
(`ladder_study`), which says most names that reach the target fade rather than
run — and a fade is where the trail beats breakeven. **Expected sign: the
partial helps, the breakeven hurts, and the combination lands between them.**

WHAT THIS IS NOT HIS
--------------------
The 5% trail stays in force BEFORE the target. His initial stop is
min(structure, 10-20c), measured and rejected 2026-09-10 — substituting a
rejected stop into a test of the exit would confound the question with a settled
answer. Our stop until the target, his after it.

Rules 2 and 3 of warrior_0 §5.3 — the first-red-candle exit and selling into an
extension bar — are NOT implemented. Rule 2 needs its own registration; rule 3
needs a definition of "outsized" the source does not give.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common import target_exit as TE
from common.analysis import LIVE, MEASURED_FRICTION, load_sessions
from common.report_io import emit
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
QTY = 100
DROP = 3


def run(sessions, *, te) -> list:
    out = []
    for sym, d, df in sessions:
        try:
            out += [(sym, d, t) for t in MCL.backtest_session(
                df, datetime.strptime(d, "%Y-%m-%d").date(), ET,
                target_exit=te, entry_shares=QTY, **LIVE)]
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
                "scratch": 0.0, "early_n": 0, "late_n": 0,
                "early_per": 0.0, "late_per": 0.0, "bars": 0.0}
    e = [r for (_, d, _), r in zip(trades, real) if d < split]
    l = [r for (_, d, _), r in zip(trades, real) if d >= split]
    net = sum(real)
    return {
        "n": len(real), "net": net, "per": net / len(real),
        "dropped": net - sum(sorted(real, reverse=True)[:DROP]),
        "win": 100.0 * sum(1 for r in real if r > 0) / len(real),
        # A SCRATCH is the point of the breakeven stop -- the trade that used to
        # be a small loss and is now nearly nothing. Counted separately because
        # it moves the win rate without moving the money, and conflating the
        # two is how a 71% win rate gets quoted as an edge.
        "scratch": 100.0 * sum(1 for r in real if abs(r) <= MEASURED_FRICTION)
        / len(real),
        "early_n": len(e), "late_n": len(l),
        "early_per": (sum(e) / len(e)) if e else 0.0,
        "late_per": (sum(l) / len(l)) if l else 0.0,
        "bars": sum(t.bars_held for _, _, t in trades) / len(real),
    }


CELLS = [
    ("MCL today", None),
    ("stop change only", TE.TargetExit(take_frac=0.0, breakeven=True)),
    ("partial only", TE.TargetExit(breakeven=False)),
    ("CAMERON", TE.TargetExit()),
]


def render(got, split, n_sessions) -> list[str]:
    L = ["CAMERON'S EXIT vs MCL's TRAIL — a 2x2", "",
         f"  {n_sessions} cached sessions, {QTY} shares flat",
         f"  net after tiered commission and ${MEASURED_FRICTION}/RT friction",
         f"  halves split at {split} (derived)",
         f"  target {TE.TARGET_PCT:.0f}% = 2R against MCL's 5% trail, "
         f"derived per warrior_0 §5.2 — NOT chosen because it wins",
         f"  partial {TE.TAKE_FRAC:.0f}%; breakeven = stop at the entry price, "
         f"trail off", "",
         "  His CENT targets are not tested: they were scaled to the cent stop",
         "  rejected on 2026-09-10, and warrior_0 §5.2 says the target has to",
         "  be re-posed against a percentage stop before it can be answered.", "",
         f"  {'cell':<20}{'trades':>7}{'net':>10}{'per':>8}{'win%':>7}"
         f"{'scratch%':>10}{'avg bars':>10}{'drop top 3':>12}"]
    for name, _ in CELLS:
        s = got[name]
        L.append(f"  {name:<20}{s['n']:>7}${s['net']:>9,.0f}${s['per']:>7.2f}"
                 f"{s['win']:>6.1f}%{s['scratch']:>9.1f}%{s['bars']:>10.1f}"
                 f"${s['dropped']:>11,.0f}")
    L.append("")

    base = got["MCL today"]
    if not base["n"]:
        return L + ["  NO TRADES. Nothing to compare.", ""]
    inert = [k for k, s in got.items()
             if s["n"] and (s["early_n"] == 0 or s["late_n"] == 0)]
    if inert:
        return L + ["THE HALVES CONTROL DID NOT DIVIDE THIS RUN", "",
                    f"  {', '.join(inert)} has no trades on one side of "
                    f"{split}. NO VERDICT drawn.", ""]

    L += ["ATTRIBUTION — what each half of the change is worth", ""]
    for name in ("stop change only", "partial only", "CAMERON"):
        s = got[name]
        d = s["net"] - base["net"]
        de = s["early_per"] - base["early_per"]
        dl = s["late_per"] - base["late_per"]
        flag = "" if de * dl > 0 else "   [SIGN FLIPS BETWEEN HALVES]"
        L.append(f"  {name:<20}{d:>+9,.0f}   per trade "
                 f"{s['per'] - base['per']:+.2f}   "
                 f"win {s['win'] - base['win']:+.1f}pp{flag}")
    L.append("")

    cam = got["CAMERON"]
    d = cam["net"] - base["net"]
    de = cam["early_per"] - base["early_per"]
    dl = cam["late_per"] - base["late_per"]
    L += ["VERDICT on the full substitution", "",
          f"  net {d:+,.0f}   per trade {cam['per'] - base['per']:+.2f}",
          f"  win rate {cam['win']:.1f}% vs {base['win']:.1f}%  "
          f"({cam['win'] - base['win']:+.1f}pp)",
          f"  per trade by half: early {de:+.2f}   late {dl:+.2f}", ""]
    if d > 0 and de * dl > 0 and cam["dropped"] > base["dropped"]:
        L += ["  BETTER on the total, in both halves, and after drop-top-3.",
              "  Still in-sample, and holdout.json was cut over the SCREENED",
              "  universe so it does NOT apply to a bar_cache result — re-run",
              "  on bar_cache_xnas before spending it.", ""]
    elif d > 0:
        why = [] if de * dl > 0 else ["the sign flips between halves"]
        if cam["dropped"] <= base["dropped"]:
            why.append("it does not survive drop-top-3")
        L += [f"  Better on the total but {' and '.join(why)}.", ""]
    else:
        L += ["  WORSE on this tape. Read the attribution above before",
              "  concluding the exit is wrong: if the partial helps and the",
              "  breakeven hurts, the finding is about the STOP and not about",
              "  taking profit, and only one of the two needs discarding.", ""]

    if cam["win"] > base["win"] + 5 and d <= 0:
        L += ["  THE WIN RATE ROSE AND THE MONEY DID NOT.", "",
              "  That is the shape a breakeven stop produces by construction: a",
              "  trade that was a small loss becomes a scratch, which stops",
              "  counting against the win rate without adding anything. The",
              "  scratch% column is how much of the win-rate gain is that.",
              "  Cameron's 71.1% may contain the same effect; his self-reported",
              "  figures cannot distinguish a scratch from a win either.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not his method. The 5% trail is still in force BEFORE the target,",
          "  because his initial stop -- min(structure, 10-20c) -- was measured",
          "  and rejected on 2026-09-10 and putting it back would confound this",
          "  test with a settled question.",
          "",
          "  Not his full exit. Rules 2 and 3 of warrior_0 §5.3 -- exit on the",
          "  first red close before the partial, and sell into an extension bar",
          "  -- are not implemented.",
          "",
          "  Not out of sample. MCL was fitted on these sessions.",
          "",
          "  Not independent evidence. MCL was derived from this source, so the",
          "  spec is the intent rather than a second opinion."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--out", default="var/reports/cameron_exit.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    sessions = load_sessions(Path(a.cache))
    split = halves_split([d for _, d, _ in sessions])
    got = {name: stats(run(sessions, te=te), split) for name, te in CELLS}
    emit("\n".join(render(got, split, len(sessions))), a.out,
         header=f"common.cameron_exit  cache={a.cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
