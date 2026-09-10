#!/usr/bin/env python3
"""A maximum hold time against MCL's trailing stop.

    python -m common.hold_cap_study

THE PROPOSAL
------------
Ben, 2026-09-10: *"I would like to consider an addition to the exit strategy
where the position should not be held for more than 5 mins."*

MCL currently has two exits: a 5% trail from the peak, and the 09:30 window
close. Nothing bounds how long a position stays open. When the apex exit was
retired on 2026-09-05 the note in `mcl.py` recorded what that costs:

    holds stretch. Median stays at 2 bars but p90 goes 4 -> 24 and the maximum
    is 238, so a position open for hours is normal rather than a hung order.
    The 5% trail is then the ONLY protection.

So the median trade is untouched by a 5-bar cap and the tail is entirely
rewritten by it. That is the shape of the question.

WHAT THE ANSWER PROBABLY IS, WRITTEN DOWN BEFORE THE RUN
--------------------------------------------------------
Stating the prediction first, because a result that matches an unstated
expectation is indistinguishable from one that was steered to it.

**This should lose money, and the mechanism is not subtle.** A 5% trail cuts a
loser fast -- the position is closed as soon as price gives back 5% of its peak,
which on a name moving enough to trigger MCL happens in a few bars. A winner is
precisely the trade that does NOT give back 5%, so it is the trade that runs
long. A cap on hold time therefore truncates the right tail while leaving the
left tail almost untouched.

MCL's entire measured result on `bar_cache` is +$161 over 485 trades and it goes
NEGATIVE at drop-top-3. A strategy whose edge lives in a handful of long winners
is the worst possible candidate for a time cap.

**If the run disagrees with that, the run is the evidence and this paragraph is
not.** It is written to make the disagreement visible, not to pre-empt it.

PINNED BEFORE RUNNING
---------------------
5 bars is the PRIMARY -- it is what Ben asked for, and it is primary for that
reason rather than because it wins. 3, 10, 15 and 30 are a BOUNDARY CHECK, not
a menu: if the best cell sits at an edge of that range then the range is in the
wrong place and none of them should be adopted.

The cap is measured ALONGSIDE the trail, not instead of it. The trail still
fires first when both would trigger on the same bar. This isolates one variable;
swapping the trail out at the same time would leave two changes and no
attribution.

WHERE THE ANSWER LIVES
----------------------
Not in the total. Three tables decide it:

  BY EXIT REASON   what the cap actually replaced. If the trades it closes were
                   heading for a trailing stop anyway, the cap is a relabelling
                   and should show near zero. The number that matters is what
                   the `hold_cap` exits WOULD have made under the baseline.

  BY BARS HELD     the baseline's own P/L bucketed by how long the trade ran.
                   This says directly whether long holds are where the money is,
                   and it is computable without the cap at all.

  PAIRED           the same trade under both rules. Totals across variants can
                   differ because the variants took different NUMBERS of trades;
                   pairing removes that.

Controls: both halves at the calendar midpoint of the sessions actually scored
(derived, never hard-coded -- `prior_spike` drew two confident verdicts from a
hard-coded split that put every trade in one half), and drop-top-3 within each
variant.

ONE INTERACTION THAT MUST BE READ ALONGSIDE
-------------------------------------------
Live entries land a minute after the signal bar closes (`entry_delay_study`:
that minute is worth $148/yr at 100 shares, 92% of MCL's marginal result). This
backtest enters at the signal close, so a 5-bar cap here is a 4-bar cap on the
position the live trader would actually hold. `--entry-delay 1` runs the same
sweep on delayed entries; if the two disagree, the cap is interacting with the
latency rather than with the market.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import LIVE, MEASURED_FRICTION, load_sessions
from common.report_io import emit
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
QTY = 100

PRIMARY_BARS = 5                       # what Ben asked for
BOUNDARY_BARS = (3, 10, 15, 30)        # the range around it, not a menu
HOLD_BUCKETS = (0, 1, 2, 3, 5, 10, 20, 60, 10_000)


def run(sessions, *, cap: int | None, entry_delay: int = 0) -> list:
    """One variant over the whole cache. cap=None is MCL as it stands."""
    out = []
    for sym, d, df in sessions:
        try:
            out += [(sym, d, t) for t in MCL.backtest_session(
                df, datetime.strptime(d, "%Y-%m-%d").date(), ET,
                max_hold_bars=cap, entry_delay_bars=entry_delay,
                entry_shares=QTY, **LIVE)]
        except Exception:                                   # noqa: BLE001
            # A session too short for the warm-up raises. Skipping keeps every
            # variant over the SAME sessions, which is the only way the
            # differences mean anything.
            pass
    return out


def halves_split(dates: list[str]) -> str:
    """Calendar midpoint of the sessions ACTUALLY SCORED.

    Derived rather than pinned. On 2026-09-10 `prior_spike` hard-coded a split
    that fell outside the range being scored, so every `late` figure was 0.00
    and `(x) * (0) = 0` printed as 'the sign flips between halves' -- two
    confident verdicts from a control that had divided nothing.
    """
    ds = sorted(set(dates))
    return ds[len(ds) // 2] if ds else ""


def stats(trades, split: str, drop: int = 3) -> dict:
    real = [t.net - MEASURED_FRICTION for _, _, t in trades]
    if not real:
        return {"n": 0, "net": 0.0, "per": 0.0, "dropped": 0.0, "win": 0.0,
                "early": 0.0, "late": 0.0, "early_n": 0, "late_n": 0,
                "early_per": 0.0, "late_per": 0.0, "bars": 0.0}
    net = sum(real)
    e = [r for (_, d, _), r in zip(trades, real) if d < split]
    l = [r for (_, d, _), r in zip(trades, real) if d >= split]
    return {
        "n": len(real), "net": net, "per": net / len(real),
        "dropped": net - sum(sorted(real, reverse=True)[:drop]),
        "win": 100.0 * sum(1 for r in real if r > 0) / len(real),
        "early": sum(e), "late": sum(l),
        # COUNTS, not just sums. A half-total of 0.0 is ambiguous between "no
        # trades this half" and "trades netting exactly zero", and the
        # emptiness check must not rest on a value a real half can produce.
        "early_n": len(e), "late_n": len(l),
        "early_per": (sum(e) / len(e)) if e else 0.0,
        "late_per": (sum(l) / len(l)) if l else 0.0,
        "bars": sum(t.bars_held for _, _, t in trades) / len(real),
    }


def by_reason(trades) -> dict[str, dict]:
    out: dict[str, list] = {}
    for row in trades:
        out.setdefault(row[2].reason, []).append(row)
    return {k: {"n": len(v),
                "net": sum(t.net - MEASURED_FRICTION for _, _, t in v)}
            for k, v in sorted(out.items())}


def by_hold(trades) -> list[tuple[str, int, float, float]]:
    """The baseline's P/L by how long the trade ran.

    THE TABLE THAT ANSWERS THE QUESTION WITHOUT THE CAP. If the money is in
    trades held 20+ bars, a 5-bar cap cannot help however the totals land.
    """
    out, lo = [], HOLD_BUCKETS[0]
    for hi in HOLD_BUCKETS[1:]:
        sel = [t for _, _, t in trades if lo <= t.bars_held < hi]
        if sel:
            net = sum(t.net - MEASURED_FRICTION for t in sel)
            label = f"{lo}-{hi - 1}" if hi < 10_000 else f"{lo}+"
            out.append((label, len(sel), net, net / len(sel)))
        lo = hi
    return out


def paired(base, capped) -> dict:
    """Same symbol, same date, same entry time, under both rules.

    Totals across variants can differ because the variants took different
    NUMBERS of trades -- a capped run frees the slot earlier and may enter
    again. Pairing on the entry removes that and compares like with like.
    """
    b = {(s, d, t.entry_time): t for s, d, t in base}
    c = {(s, d, t.entry_time): t for s, d, t in capped}
    keys = sorted(set(b) & set(c))
    if not keys:
        return {"n": 0}
    deltas = [c[k].net - b[k].net for k in keys]
    deltas.sort()
    mid = len(deltas) // 2
    return {"n": len(keys), "total": sum(deltas),
            "median": (deltas[mid] if len(deltas) % 2
                       else (deltas[mid - 1] + deltas[mid]) / 2),
            "worse": sum(1 for d in deltas if d < 0),
            "better": sum(1 for d in deltas if d > 0),
            "same": sum(1 for d in deltas if d == 0)}


def render(variants, split, n_sessions, entry_delay) -> list[str]:
    base_name = "no cap"
    rows = [(name, tr, stats(tr, split)) for name, tr in variants]
    got = {name: s for name, _, s in rows}
    base_trades = dict((n, t) for n, t, _ in rows)[base_name]

    L = ["A MAXIMUM HOLD TIME vs MCL's TRAILING STOP", "",
         f"  {n_sessions} cached sessions, MCL live config, {QTY} shares flat",
         f"  net after tiered commission and ${MEASURED_FRICTION}/RT friction",
         f"  halves split at {split} (derived from the sessions scored)",
         f"  entry delay {entry_delay} bar(s)",
         "",
         f"  {PRIMARY_BARS} bars is PINNED as the primary -- it is what was",
         "  asked for, not what won. 3/10/15/30 are a boundary check on the",
         "  range around it, not a menu to pick from.", "",
         f"  {'variant':<14}{'trades':>7}{'net':>10}{'per':>8}{'win%':>7}"
         f"{'avg bars':>10}{'drop top 3':>12}{'early':>10}{'late':>10}"]
    for name, _, s in rows:
        L.append(f"  {name:<14}{s['n']:>7}${s['net']:>9,.0f}${s['per']:>7.2f}"
                 f"{s['win']:>6.1f}%{s['bars']:>10.1f}${s['dropped']:>11,.0f}"
                 f"${s['early']:>9,.0f}${s['late']:>9,.0f}")
    L.append("")

    inert = [n for n, s in got.items()
             if s["n"] and (s["early_n"] == 0 or s["late_n"] == 0)]
    if inert:
        L += ["THE HALVES CONTROL DID NOT DIVIDE THIS RUN", "",
              f"  {', '.join(inert)} has no trades on one side of {split}.",
              "  A comparison against an empty half reads in the output exactly",
              "  like a sign flip. NO VERDICT is drawn -- totals stand, the",
              "  controls do not.", ""]
        return L

    L += ["WHERE THE BASELINE's MONEY IS, BY HOW LONG THE TRADE RAN", "",
          "  Computable without the cap at all. If the net sits in the long",
          "  buckets, no time cap can help however the totals land.", "",
          f"      {'bars held':<12}{'n':>6}{'net':>11}{'per':>9}"]
    for label, n, net, per in by_hold(base_trades):
        L.append(f"      {label:<12}{n:>6}${net:>10,.0f}${per:>8.2f}")
    L.append("")

    prim = f"{PRIMARY_BARS} bars"
    if prim in dict((n, t) for n, t, _ in rows):
        capped = dict((n, t) for n, t, _ in rows)[prim]
        L += [f"WHAT THE {PRIMARY_BARS}-BAR CAP REPLACED", "",
              f"      {'exit reason':<16}{'n':>6}{'net':>11}"]
        for reason, d in by_reason(capped).items():
            L.append(f"      {reason:<16}{d['n']:>6}${d['net']:>10,.0f}")
        L.append("")
        p = paired(base_trades, capped)
        if p["n"]:
            L += [f"  PAIRED on the same entry -- {p['n']} trade(s) in both",
                  f"      total   ${p['total']:>+10,.0f}",
                  f"      median  ${p['median']:>+10.2f}",
                  f"      worse {p['worse']}   better {p['better']}   "
                  f"unchanged {p['same']}", ""]

    b, c = got.get(base_name), got.get(prim)
    if b and c and b["n"] and c["n"]:
        d = c["net"] - b["net"]
        de, dl = c["early_per"] - b["early_per"], c["late_per"] - b["late_per"]
        L += [f"VERDICT on the {PRIMARY_BARS}-bar cap", "",
              f"  net {d:+,.0f}   per trade {c['per'] - b['per']:+.2f}",
              f"  per trade by half: early {de:+.2f}   late {dl:+.2f}",
              f"  win rate {c['win']:.1f}% vs {b['win']:.1f}%", ""]
        if d > 0 and de * dl > 0 and c["dropped"] > b["dropped"]:
            L += ["  BETTER on the total, in both halves, and after",
                  "  drop-top-3. That is the strongest form this project's",
                  "  standards allow in-sample -- and it is still in-sample:",
                  "  MCL was fitted on these very sessions.", ""]
        elif d > 0 and de * dl <= 0:
            L += ["  Better on the total but THE SIGN FLIPS BETWEEN HALVES.",
                  "  One period, not an effect.", ""]
        elif d > 0:
            L += ["  Better on the total but NOT after drop-top-3, so a",
                  "  handful of trades are the result. Not adoptable.", ""]
        else:
            L += ["  WORSE. The cap costs money on this tape. The trailing",
                  "  stop already closes losers quickly, so a time limit",
                  "  mostly truncates winners -- which is what the bars-held",
                  "  table above should show directly.", ""]

    caps = [(n, s) for n, s in got.items() if n != base_name]
    if len(caps) >= 3:
        best = max(caps, key=lambda kv: kv[1]["net"])
        edges = (f"{BOUNDARY_BARS[0]} bars", f"{BOUNDARY_BARS[-1]} bars")
        if best[0] in edges:
            L += [f"  BOUNDARY CHECK FAILED: {best[0]} is the best cell and it",
                  "  sits at an edge of the tested range, so the range is in",
                  "  the wrong place and none of these should be adopted.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not out of sample. MCL's parameters were fitted on these",
          "  sessions, so a cap that wins has beaten a rule tuned here and",
          "  has not been shown to generalise.",
          "",
          "  Not the live position either. Live entries land a minute after",
          "  the signal bar closes, so a 5-bar cap here is a 4-bar cap on the",
          "  position actually held. Re-run with --entry-delay 1; if the two",
          "  disagree the cap is interacting with the latency, not the market."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--entry-delay", type=int, default=0)
    p.add_argument("--out", default="var/reports/hold_cap.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    sessions = load_sessions(Path(a.cache))
    split = halves_split([d for _, d, _ in sessions])
    variants = [("no cap", run(sessions, cap=None, entry_delay=a.entry_delay))]
    for n in sorted({PRIMARY_BARS, *BOUNDARY_BARS}):
        variants.append((f"{n} bars",
                         run(sessions, cap=n, entry_delay=a.entry_delay)))
    emit("\n".join(render(variants, split, len(sessions), a.entry_delay)),
         a.out, header=f"common.hold_cap_study  cache={a.cache} "
                       f"entry_delay={a.entry_delay}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
