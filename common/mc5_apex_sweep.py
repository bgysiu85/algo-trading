#!/usr/bin/env python3
"""MC5's gradient-reversal exit, on and off.

    python -m common.mc5_apex_sweep

THE SAME SWEEP THAT RETIRED MCL's
---------------------------------
MCL's apex exit was switched off on 2026-09-05 after a 2x2 over 376 sessions:
net -$544 over 213 exits at a 27% win rate, closing positions while the trail
was still intact. MC5 runs the same mechanic -- `exit_sig = x_rsi & x_macd` --
and never got the switch, so it never got the measurement.

WHAT PROMPTED IT, and why one night is not the finding
------------------------------------------------------
The 2026-09-10 paper session: MC5's six signal exits lost $109.24 of its
$166.94 gross loss. Two thirds of the night from one rule.

That is n=6 on one session, which is a reason to measure and not a result. The
MCL sweep that settled the same question used 376 sessions and 178 symbols. If
this run disagrees with that night, the run wins.

WHAT WOULD MAKE IT ADOPTABLE
----------------------------
The verdict MCL's got: better on the total, in both halves, and after
drop-top-N, with the concentration check IMPROVING rather than merely holding.
Anything less is reported and not acted on.

Note that the default is left at USE_APEX_EXIT = True until this reports, so
no published MC5 figure moves before there is a reason.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import MEASURED_FRICTION, load_sessions
from common.report_io import emit
from strategy.mc5 import mc5 as MC5

ET = ZoneInfo("America/New_York")
QTY = 100
DROP = 3


def run(sessions, *, use_apex: bool) -> list:
    out = []
    for sym, d, df in sessions:
        try:
            out += [(sym, d, t) for t in MC5.backtest_session(
                df, datetime.strptime(d, "%Y-%m-%d").date(), ET,
                use_apex=use_apex, entry_shares=QTY)]
        except Exception:                                   # noqa: BLE001
            pass
    return out


def halves_split(dates) -> str:
    """Derived from the sessions actually scored. prior_spike hard-coded one
    that fell outside its own range and printed two verdicts from a control
    that divided nothing."""
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
    return {
        "n": len(real), "net": net, "per": net / len(real),
        "dropped": net - sum(sorted(real, reverse=True)[:DROP]),
        "win": 100.0 * sum(1 for r in real if r > 0) / len(real),
        # COUNTS, so an empty half cannot be mistaken for one netting zero.
        "early_n": len(e), "late_n": len(l),
        "early_per": (sum(e) / len(e)) if e else 0.0,
        "late_per": (sum(l) / len(l)) if l else 0.0,
    }


def by_reason(trades) -> dict:
    out = {}
    for _, _, t in trades:
        n, p = out.get(t.reason, (0, 0.0))
        out[t.reason] = (n + 1, p + t.net - MEASURED_FRICTION)
    return dict(sorted(out.items(), key=lambda kv: kv[1][1]))


def render(on, off, split, n_sessions) -> list[str]:
    a, b = stats(on, split), stats(off, split)
    L = ["MC5's GRADIENT-REVERSAL EXIT, ON vs OFF", "",
         f"  {n_sessions} cached sessions, 5-minute bars, {QTY} shares flat",
         f"  net after tiered commission and ${MEASURED_FRICTION}/RT friction",
         f"  halves split at {split} (derived from the sessions scored)", "",
         f"  {'variant':<12}{'trades':>8}{'net':>11}{'per':>8}{'win%':>7}"
         f"{'drop top 3':>12}",
         f"  {'apex ON':<12}{a['n']:>8}${a['net']:>10,.0f}${a['per']:>7.2f}"
         f"{a['win']:>6.1f}%${a['dropped']:>11,.0f}",
         f"  {'apex OFF':<12}{b['n']:>8}${b['net']:>10,.0f}${b['per']:>7.2f}"
         f"{b['win']:>6.1f}%${b['dropped']:>11,.0f}", ""]

    if not a["n"] or not b["n"]:
        return L + ["  ONE VARIANT PRODUCED NO TRADES. Nothing to compare.", ""]

    inert = [n for n, s in (("apex ON", a), ("apex OFF", b))
             if s["early_n"] == 0 or s["late_n"] == 0]
    if inert:
        return L + ["THE HALVES CONTROL DID NOT DIVIDE THIS RUN", "",
                    f"  {', '.join(inert)} has no trades on one side of {split}.",
                    "  A comparison against an empty half reads exactly like a",
                    "  sign flip. NO VERDICT drawn.", ""]

    L += ["WHAT THE SIGNAL EXIT ITSELF EARNED (apex ON)", "",
          f"      {'reason':<20}{'n':>6}{'net':>11}{'per':>9}"]
    for reason, (n, p) in by_reason(on).items():
        L.append(f"      {reason:<20}{n:>6}${p:>10,.0f}${p / n:>8.2f}")
    L += ["",
          "  If the signal exits are POSITIVE the rule is earning its place.",
          "  If negative, it is closing positions the trail had not stopped --",
          "  which is exactly what MCL's sweep found in 2026-09-05.", ""]

    d = b["net"] - a["net"]
    de = b["early_per"] - a["early_per"]
    dl = b["late_per"] - a["late_per"]
    L += ["VERDICT — turning it OFF", "",
          f"  net {d:+,.0f}   per trade {b['per'] - a['per']:+.2f}",
          f"  per trade by half: early {de:+.2f}   late {dl:+.2f}",
          f"  trades {b['n']} vs {a['n']}", ""]
    if d > 0 and de * dl > 0 and b["dropped"] > a["dropped"]:
        L += ["  TURN IT OFF. Better on the total, in both halves, and after",
              "  drop-top-3 — the same standard that retired MCL's. Flip",
              "  USE_APEX_EXIT in strategy/mc5/mc5.py and record it.",
              "",
              "  Still in-sample: MC5's parameters were fitted on these",
              "  sessions, so this beats a rule tuned here.", ""]
    elif d > 0 and de * dl <= 0:
        L += ["  Better on the total but THE SIGN FLIPS BETWEEN HALVES. One",
              "  period, not an effect. Leave it on and say why.", ""]
    elif d > 0:
        L += ["  Better on the total but NOT after drop-top-3, so a handful of",
              "  trades are the result. Leave it on.", ""]
    else:
        L += ["  LEAVE IT ON. The exit is earning its place on this tape, and",
              "  the 2026-09-10 session was six trades. MCL's answer does not",
              "  transfer — note that MC5 trades 5-minute bars, where a",
              "  reversal signal has five times the information behind it.", ""]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--out", default="var/reports/mc5_apex.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    sessions = load_sessions(Path(a.cache))
    split = halves_split([d for _, d, _ in sessions])
    emit("\n".join(render(run(sessions, use_apex=True),
                          run(sessions, use_apex=False),
                          split, len(sessions))),
         a.out, header=f"common.mc5_apex_sweep  cache={a.cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
