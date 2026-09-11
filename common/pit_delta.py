#!/usr/bin/env python3
"""Does the intraday floor change a DELTA, or only a level?

    python -m common.pit_delta --strategy mcl --variant ladder

THE CLAIM THIS TESTS, AND WHY IT IS NOT OBVIOUSLY TRUE
-------------------------------------------------------
`HANDOVER_20260911.md` §4 says every published MCL/MC5 figure measured on an
unfloored run "is overstated by $6.84-$11.99/trade", and concludes that the four
rejected mechanics -- the ladder, Cameron's partial, Cameron's breakeven stop,
the dip entry -- should be re-run floored before their rejections are trusted.

The conclusion may well be right. The stated reason is not. **$6.84 is the gap
between two LEVELS** -- the unfloored and floored point-in-time arms -- and every
one of those four mechanics was scored as a DIFFERENCE between two exit rules
**on the same trades**. Both arms of such a comparison carry identical entry
timing, so a common level offset cancels in the subtraction. A delta cannot be
"overstated by $6.84", and adjusting one by that figure would produce a number
that is wrong in a new way.

What IS true is narrower and has no known sign. The floor does not shift a
level, it changes the POPULATION: it removes 39-40% of the trades and leaves the
survivors with different post-entry paths, and an exit mechanic's value is
entirely a function of the post-entry path. So the rejections were measured on
trades that could not have existed -- which is a real reason to distrust them,
but a rejected mechanic could come back better or worse, and nothing in the
level gap says which.

That distinction decides what to do. An offset could be applied on paper to all
four. A population change can only be answered by re-running, so the question
worth asking first is whether re-running changes anything at all.

WHAT THIS RUNS
--------------
One mechanic, as a delta, twice over the same point-in-time universe:

    unfloored:  base(no floor)  vs  variant(no floor)   ->  delta_unfloored
    floored:    base(floored)   vs  variant(floored)    ->  delta_floored

Everything else is held: same tape, same slices, same dates, same universe, same
friction ladder, same drop-top-5 by symbol, same derived halves. The only thing
that moves between the two deltas is the floor.

PRE-REGISTERED, BEFORE THE FIRST RUN (2026-09-11)
--------------------------------------------------
`MATERIAL` is $0.50/trade, set here rather than after seeing the output, and
chosen as roughly a third of the smallest delta this project has ever acted on.

  * |delta_floored - delta_unfloored| < $0.50 and no sign change
        -> the floor does not move this delta. The ladder's rejection stands as
           measured, the other three probably do too, and re-running all four is
           not the priority `HANDOVER` §5 item 3 makes it.
  * the difference exceeds $0.50, or either delta changes sign
        -> the population change reaches the deltas. All four rejections are
           unsafe and must be re-run floored before being treated as settled.

One mechanic cannot prove the other three, and the report says so. It can show
that the effect exists, which is what decides whether spending four runs is
worth it.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import deque
from dataclasses import asdict
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common import profit_ladder as PL
from common.cache_io import BACKTEST_SESSIONS
from common.pit_h0 import DROP, FRICTIONS, first_seen_time, halves_split, score
from common.pit_strategy import (QTY, build_frame, engine, load_pit,
                                 needed_symbols)
from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")
WARMUP_SESSIONS = max(0, BACKTEST_SESSIONS - 1)

# Pre-registered 2026-09-11, before the first run. See the module docstring.
MATERIAL = 0.50

# Below this an arm gets no verdict, matching pit_strategy.
MIN_TRADES = 30


def variant_kwargs(name: str) -> tuple[dict, dict, str]:
    """(base kwargs, variant kwargs, what the comparison is).

    The ladder is first because it is the cleanest of the four: a pure exit
    overlay with no entry component, and a rejection that was crisp -- -$1,612
    against a linear control that landed within $13 of it. A mechanic whose
    delta was already near zero is also the one where a population change has
    the most room to matter.
    """
    if name == "ladder":
        return ({}, {"ladder": PL.LadderConfig()},
                "Ben's compounding ladder against no ladder")
    if name == "ladder_linear":
        return ({"ladder": PL.LadderConfig()},
                {"ladder": PL.LadderConfig(linear=True)},
                "the linear control against Ben's compounding ladder")
    if name == "cameron_partial":
        return ({}, {"scale_out_pct": 50.0, "partial_trail_pct": 2.5},
                "Cameron's partial at 2.5% against no partial")
    # Cameron's BREAKEVEN STOP is deliberately absent. It is not a single
    # kwarg on backtest_session, and a variant that differed from its base by
    # nothing would run base against base and report a delta of exactly 0.00 --
    # which renders as "NOT MATERIAL", the same words a real null produces. A
    # missing variant must fail loudly; it must not quietly pass.
    sys.exit(f"unknown variant {name!r} -- expected ladder, ladder_linear or "
             "cameron_partial")


def run_day(frame: pd.DataFrame, day: str, universe: list[dict], *, mod,
            extra: dict, base: dict, var: dict) -> dict[str, list[dict]]:
    """One session, four runs: {base,variant} x {unfloored,floored}.

    All four come from the SAME frame inside one call, so a session the engine
    cannot run is dropped from all four together. Dropping it from three would
    leave the deltas computed over different session sets -- which is the exact
    failure this module exists to detect, appearing inside the detector.
    """
    d = _date.fromisoformat(day)
    out: dict[str, list[dict]] = {k: [] for k in
                                  ("base_free", "var_free", "base_held",
                                   "var_held")}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec["first_seen"]:
            continue
        nb = first_seen_time(rec)
        try:
            runs = {
                "base_free": mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                  **extra, **base),
                "var_free": mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 **extra, **var),
                "base_held": mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                  not_before=nb, **extra,
                                                  **base),
                "var_held": mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=nb, **extra, **var),
            }
        except Exception:                                   # noqa: BLE001
            continue
        for k, trades in runs.items():
            for t in trades:
                row = asdict(t)
                row.update(symbol=rec["symbol"], date=day)
                out[k].append(row)
    return out


def delta(a: list[dict], b: list[dict], split: str, friction: float) -> dict:
    """b minus a, per trade and in total, with both sides' counts.

    Per-trade AND total, because the two answer different questions and this
    project has already been caught quoting one as the other: a mechanic that
    changes the NUMBER of trades moves the per-trade figure without moving any
    money. Where the counts differ the report says so rather than hiding it in
    a single number.
    """
    sa, sb = score(a, split, friction), score(b, split, friction)
    return {"base": sa, "var": sb,
            "per": sb["per"] - sa["per"],
            "net": sb["net"] - sa["net"],
            "same_n": sa["n"] == sb["n"]}


def render(name: str, variant: str, what: str, arms: dict, split: str,
           n_days: int, offered: int, elapsed: float) -> list[str]:
    L = [f"DOES THE INTRADAY FLOOR MOVE A DELTA?  {name.upper()} / {variant}",
         "",
         f"  {what}",
         f"  {n_days} sessions, {offered:,} symbol-days offered, "
         f"{QTY} shares",
         f"  halves split at {split} (derived)",
         f"  elapsed {elapsed:.1f}s", "",
         f"  PRE-REGISTERED {MATERIAL:.2f}/trade as material, before this ran.",
         "  Below it with no sign change, the floor does not reach this delta",
         "  and the other three rejections probably stand. Above it, or a sign",
         "  change, and all four must be re-run floored.", ""]

    rows = {}
    for label, a, b in (("UNFLOORED", "base_free", "var_free"),
                        ("FLOORED", "base_held", "var_held")):
        L += [f"{label}", ""]
        L.append(f"  {'friction':<10}{'base n':>8}{'var n':>8}"
                 f"{'base/trade':>12}{'var/trade':>12}{'delta':>10}"
                 f"{'delta net':>12}")
        for fl, fv in FRICTIONS:
            d = delta(arms[a], arms[b], split, fv)
            rows[(label, fl)] = d
            L.append(f"  {fl:<10}{d['base']['n']:>8}{d['var']['n']:>8}"
                     f"${acct(d['base']['per'], 11)}${acct(d['var']['per'], 11)}"
                     f"{acct(d['per'], 10)}${acct(d['net'], 11, 0)}")
        L.append("")

    u = rows[("UNFLOORED", "$4.26")]
    f = rows[("FLOORED", "$4.26")]
    moved = f["per"] - u["per"]

    L += ["THE ANSWER, at $4.26", "",
          f"  delta unfloored   {acct(u['per'], 8)}/trade over "
          f"{u['var']['n']:,} variant trades",
          f"  delta floored     {acct(f['per'], 8)}/trade over "
          f"{f['var']['n']:,}",
          f"  the floor moved it{acct(moved, 8)}", ""]

    # A MECHANIC THAT NEVER FIRED. Exactly-zero deltas on both arms with
    # matching trade counts do not mean "the floor does not reach this delta" --
    # they mean base and variant ran the same trades, because the mechanic's
    # trigger was never reached on this data. Both produce the words NOT
    # MATERIAL, and only one of them is a finding. Caught at runtime as well as
    # at the variant table, because a ladder whose rungs sit 10% above entry can
    # simply never be touched.
    inert = (u["per"] == 0.0 and f["per"] == 0.0
             and u["net"] == 0.0 and f["net"] == 0.0
             and u["same_n"] and f["same_n"])
    if inert:
        L += ["  THE MECHANIC NEVER FIRED. Base and variant produced identical",
              "  trades on both arms, so this run compares a rule against",
              "  itself and says nothing about the floor. Check the variant's",
              "  trigger against this universe's price range before reading",
              "  any of it as a null.", ""]
        return L + notes(u, f)

    if min(u["var"]["n"], f["var"]["n"]) < MIN_TRADES:
        L += [f"  NO VERDICT -- fewer than {MIN_TRADES} trades on one side. A",
              "  difference read off a handful of trades is a difference",
              "  between a handful of trades.", ""]
        return L + notes(u, f)

    flipped = (u["per"] > 0) != (f["per"] > 0)
    if flipped:
        L += ["  THE DELTA CHANGES SIGN. The floor does not merely shift this",
              "  mechanic's value, it reverses it. Every rejection measured on",
              "  an unfloored run is unsafe and all four must be re-run before",
              "  any of them is treated as settled.", ""]
    elif abs(moved) >= MATERIAL:
        L += ["  MATERIAL. The population change reaches the delta, so the",
              "  four rejections were measured on trades that could not have",
              "  existed and the mechanics have to be re-run floored. Note",
              "  the direction is NOT the level gap: a mechanic can come back",
              "  better as easily as worse.", ""]
    else:
        L += ["  NOT MATERIAL. The floor moves the level a long way and this",
              "  delta barely at all, which is what a delta between two exit",
              "  rules on the same trades should do -- the entry timing is",
              "  common to both sides and cancels. `HANDOVER` §4's inference",
              "  from the level gap to the deltas does not hold here.", ""]
    return L + notes(u, f)


def notes(u: dict, f: dict) -> list[str]:
    L = ["WHAT ONE MECHANIC CAN AND CANNOT SETTLE", "",
         "  It cannot prove the other three. It can show whether the effect",
         "  exists at all, which is what decides whether four runs are worth",
         "  spending. A null here is weaker evidence than a positive: three",
         "  mechanics untested is three mechanics untested.", ""]
    if not (u["same_n"] and f["same_n"]):
        L += ["  THE TWO SIDES DO NOT HOLD THE SAME TRADE COUNT.", "",
              f"    unfloored  base {u['base']['n']:,} vs variant "
              f"{u['var']['n']:,}",
              f"    floored    base {f['base']['n']:,} vs variant "
              f"{f['var']['n']:,}", "",
              "  This mechanic changes how many trades happen, so its",
              "  per-trade delta moves without any money moving. Read the",
              "  `delta net` column beside it.", ""]
    L += ["  Not the published ladder result. That ran on the IB `bar_cache`",
          "  over the stage-2 universe; this runs on the Databento slices over",
          "  the point-in-time universe. The two DELTAS are the comparable",
          "  quantity here, not either level.", "",
          "  Not out of sample. `holdout.json` has NOT been spent."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--strategy", default="mcl")
    p.add_argument("--variant", default="ladder",
                   help="ladder, ladder_linear or cameron_partial")
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
    base, var, what = variant_kwargs(a.variant.strip().lower())
    out_path = a.out or f"var/reports/pit_delta_{name}_{a.variant}.txt"

    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    pit = load_pit(Path(a.pairs))
    days = sorted(d for d in pit if d in slices)
    if a.limit:
        days = days[:a.limit]
    universe = {d: v for d, v in pit.items() if d in set(days)}
    want = needed_symbols([universe], days, WARMUP_SESSIONS)

    t0 = time.time()
    arms: dict[str, list[dict]] = {k: [] for k in
                                   ("base_free", "var_free", "base_held",
                                    "var_held")}
    offered = 0
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
        if not recs:
            continue
        offered += len(recs)
        got = run_day(build_frame(cache, day), day, recs, mod=mod, extra=extra,
                      base=base, var=var)
        for k, v in got.items():
            arms[k] += v
        if i % 25 == 0:
            print(f"  {i}/{len(days)}  {day}  "
                  f"{len(arms['var_held']):,} floored variant trades")

    split = halves_split([t["date"] for t in arms["var_held"]]
                         or [t["date"] for t in arms["var_free"]])
    emit("\n".join(render(name, a.variant, what, arms, split, len(days),
                          offered, time.time() - t0)),
         out_path,
         header=f"common.pit_delta  strategy={name}  variant={a.variant}"
                + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
