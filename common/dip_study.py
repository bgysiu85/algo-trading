#!/usr/bin/env python3
"""Where do dip signals fall relative to MCL's entries?

    python -m common.dip_study
    python -m common.dip_study --cache bar_cache_xnas

A MEASUREMENT, NOT A STRATEGY, AND THAT IS DELIBERATE
------------------------------------------------------
`warrior_4_reversal.md` §5 item 2 gives the instruction this follows:

> "Build the trigger as a measurement first: on the existing bar cache, flag
>  every bar meeting the conditions, and check where those flags fall relative
>  to MCL's own exits and relative to the session high. That answers 'is this
>  the top?' without a strategy."

The same argument applies on the entry side, with more force. The two dip
videos `warrior_4` §6 names are **not transcribed**, so there is no stated
dip-buy rule to implement — `dip_entry.py` is built from the shape the census
names and the mechanics four other documents give. Shipping a second engine off
that would be building a strategy from an inference and then scoring it.

WHAT IS ACTUALLY COMPARED
-------------------------
For every session in the cache, MCL's own entry and the dip signals on the same
bars, in three buckets:

    BOTH      the dip fired and MCL entered — how much earlier, at what price
    DIP ONLY  the dip fired and MCL never entered — trades MCL does not take
    MCL ONLY  MCL entered with no dip signal — the setups this would miss

**DIP ONLY is the question.** A better fill on the shared setups is arithmetic:
buy the pullback instead of the breakout and the price is lower every time. The
open question is what the extra trades are worth, because those are the ones
the confirmation entry refused and dip buying would take.

WHY MFE AND MAE AND NOT P/L
---------------------------
Scoring these with an exit model would put the exit inside the answer, and the
exit is the project's largest open question (`HANDOVER_TO_BUILD` §5). MFE and
MAE need no exit rule at all.

They are reported together and never apart. **MFE alone rewards an earlier
entry for being earlier** — there is more session in front of it, so it wins by
construction. MAE is the offsetting cost and, for an entry that buys into a
falling pullback, it is where the entire risk of the idea sits. The ratio is
the comparable quantity because it is invariant to the entry price, which is
exactly the thing that differs mechanically between the two entries.

WHAT WOULD MAKE THIS WORTH BUILDING INTO A STRATEGY
-----------------------------------------------------
Not a better MFE. That is free. It needs:

  - DIP ONLY to carry an MFE/MAE ratio at least as good as MCL's own entries,
    in BOTH halves. Those are the added trades and they have to stand alone.
  - the paired advantage on BOTH to exceed the mechanical fill difference,
    which is computed and printed so the two cannot be confused.
  - the signal to be EARLIER often enough to matter. A dip that fires after
    MCL's entry is not an earlier entry, it is a re-entry, and it is counted
    separately for that reason.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common import dip_entry as DE
from common import holdout as HO
from common.analysis import LIVE, load_sessions
from common.report_io import emit
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
QTY = 100


def session_rows(sym, d, df, cfg):
    """One session's comparison: MCL's first entry against the first dip."""
    try:
        trades = MCL.backtest_session(
            df, datetime.strptime(d, "%Y-%m-%d").date(), ET,
            entry_shares=QTY, **LIVE)
    except Exception:                                       # noqa: BLE001
        # A session the engine cannot run is dropped, as everywhere else. The
        # entry MAPPING below is deliberately outside this guard: a mapping
        # failure is a bug in this module and must not be absorbed as "that
        # session had no trades".
        return None

    # MCL's entries are positions here; Trade.entry_time is a STRING, not a
    # Timestamp. The first version of this keyed the map by Timestamp and
    # matched NOTHING -- 71 real trades mapped to zero, the baseline bucket
    # came out empty, and the report drew a positive verdict against it.
    # Hence `strict_positions`: it raises rather than returning a short list,
    # because a silently-empty baseline is indistinguishable from a baseline
    # that lost nothing.
    mcl = strict_positions(df, trades)

    # THE SESSION BOUND, and it is not optional. `load_sessions` hands back a
    # THREE-DAY frame so the indicators can warm up, and MCL trades only the
    # 04:00-09:30 window of the LAST day. An unbounded detector fired on the
    # warm-up days: the first run reported dips a median of 245 bars -- four
    # hours, i.e. a previous session -- "earlier" than MCL's entry, and scored
    # their forward excursion over everything that happened afterwards. That is
    # not an earlier entry into the same setup, it is a different day's trade
    # holding a look-ahead window.
    lo, hi = session_bounds(df, d)
    dips = DE.find_dips(df, cfg, lo=lo, hi=hi)
    return {"symbol": sym, "date": d, "n_bars": hi,
            "mcl": mcl, "dips": dips, "df": df}


def session_bounds(df, date_str: str) -> tuple[int, int]:
    """The half-open [lo, hi) positions of MCL's own window on `date_str`.

    Imported from the strategy rather than restated: SESSION_START and
    SESSION_END are MCL's, and a second copy here would let the two drift and
    silently compare different windows.
    """
    local = df.index.tz_convert(ET)
    day = pd.Timestamp(date_str).date()
    hit = [i for i, ts in enumerate(local)
           if ts.date() == day
           and MCL.SESSION_START <= ts.time() <= MCL.SESSION_END]
    if not hit:
        return 0, 0
    return hit[0], hit[-1] + 1


def strict_positions(df, trades) -> list[tuple[int, float]]:
    """Each trade's entry as a bar POSITION, or an exception.

    Exact timestamps only -- a trade whose entry is not on a bar of this frame
    is a bug, not a rounding question, and snapping it to the nearest bar would
    move the comparison by up to a minute in whichever direction flatters the
    answer. But a MISS is raised rather than dropped: dropping is how a total
    mapping failure became an empty bucket that read as a clean win.
    """
    pos = {ts: i for i, ts in enumerate(df.index)}
    out = []
    for t in trades:
        key = pd.Timestamp(t.entry_time)
        key = key.tz_localize("UTC") if key.tz is None else key.tz_convert("UTC")
        if key not in pos:
            raise KeyError(
                f"{t.entry_time!r} is not a bar of this frame "
                f"({df.index[0]} .. {df.index[-1]}). The entry mapping is "
                "broken; an empty MCL bucket would read as a dip-buy win.")
        out.append((pos[key], float(t.entry_price)))
    return out


def stat(vals):
    if not vals:
        return {"n": 0, "mean": 0.0, "med": 0.0}
    s = sorted(vals)
    return {"n": len(vals), "mean": sum(vals) / len(vals),
            "med": s[len(s) // 2]}


def ratio(mfe, mae) -> float:
    """MFE over MAE, with a floor on the denominator.

    A zero MAE is a real reading -- price never traded below the entry -- and
    dividing by it would produce an infinity that dominates any mean. The floor
    is one tick on a $5 stock, so the best case reads as a large number rather
    than an undefined one.
    """
    return mfe / max(mae, 0.002)


def collect(rows, cfg):
    """The three buckets, plus the timing and fill comparisons."""
    both, dip_only, mcl_only = [], [], []
    earlier, later, fill_edge = [], [], []
    for r in rows:
        if r is None:
            continue
        df, n = r["df"], r["n_bars"]
        first_mcl = r["mcl"][0] if r["mcl"] else None
        first_dip = r["dips"][0] if r["dips"] else None

        if first_dip is not None:
            i, px = first_dip.i, first_dip.price
            mfe, mae = DE.excursions(df, i, px, n)
            rec = {"date": r["date"], "mfe": mfe, "mae": mae,
                   "ratio": ratio(mfe, mae), "retained": first_dip.retained}
            (both if first_mcl else dip_only).append(rec)
        if first_mcl is not None and first_dip is None:
            # MCL ONLY. When both fired, MCL's side of the pair is collected by
            # `paired_mcl` instead, so a session never lands in two buckets.
            i, px = first_mcl
            mfe, mae = DE.excursions(df, i, px, n)
            mcl_only.append({"date": r["date"], "mfe": mfe, "mae": mae,
                             "ratio": ratio(mfe, mae)})

        if first_mcl and first_dip:
            gap = first_mcl[0] - first_dip.i
            (earlier if gap > 0 else later).append(abs(gap))
            # The mechanical fill difference, as a fraction of MCL's entry.
            # Printed so it can never be mistaken for an edge.
            fill_edge.append((first_mcl[1] - first_dip.price) / first_mcl[1])
    return {"both": both, "dip_only": dip_only, "mcl_only": mcl_only,
            "earlier": earlier, "later": later, "fill_edge": fill_edge}


def paired_mcl(rows, n_key="both"):
    """MCL's own excursions on the sessions where BOTH fired.

    The paired control. Comparing the dip bucket against MCL's average over ALL
    sessions would compare two different session sets, and the dip detector
    selects sessions that had an impulse -- which are not a random sample of
    sessions.
    """
    out = []
    for r in rows:
        if r is None or not r["mcl"] or not r["dips"]:
            continue
        i, px = r["mcl"][0]
        mfe, mae = DE.excursions(r["df"], i, px, r["n_bars"])
        out.append({"date": r["date"], "mfe": mfe, "mae": mae,
                    "ratio": ratio(mfe, mae)})
    return out


def halves_split(dates) -> str:
    ds = sorted(set(dates))
    return ds[len(ds) // 2] if ds else ""


def line(name, recs, split):
    s = stat([r["ratio"] for r in recs])
    mfe = stat([r["mfe"] for r in recs])
    mae = stat([r["mae"] for r in recs])
    e = stat([r["ratio"] for r in recs if r["date"] < split])
    l = stat([r["ratio"] for r in recs if r["date"] >= split])
    return (f"  {name:<22}{s['n']:>7}{mfe['med']:>10.1%}{mae['med']:>10.1%}"
            f"{s['med']:>10.2f}{e['med']:>10.2f}{l['med']:>10.2f}")


def render(g, mcl_paired, n_sessions, side, cfg) -> list[str]:
    dates = [r["date"] for r in g["both"] + g["dip_only"] + g["mcl_only"]]
    split = halves_split(dates)
    L = ["DIP ENTRIES vs MCL's CONFIRMATION ENTRY — a measurement", "",
         f"  {n_sessions} cached sessions, {side}",
         f"  impulse >= {cfg.impulse_min:.0%}, pullback >= {cfg.dip_min:.0%}, "
         f"holding >= {cfg.hold_min:.0%} of the impulse",
         "  every parameter derived from TRAIL_PCT or the hold-50% rule; "
         "none swept",
         f"  halves split at {split} (derived)", "",
         "  MFE and MAE are forward excursions from the bar AFTER the signal,",
         "  as fractions of the entry price. No exit model is involved, so",
         "  none of this depends on the exit question being settled.", "",
         f"  {'bucket':<22}{'n':>7}{'MFE':>10}{'MAE':>10}"
         f"{'MFE/MAE':>10}{'early':>10}{'late':>10}",
         line("BOTH fired (dip)", g["both"], split),
         line("BOTH fired (MCL)", mcl_paired, split),
         line("DIP ONLY", g["dip_only"], split),
         line("MCL ONLY", g["mcl_only"], split), ""]

    if not g["both"] and not g["dip_only"]:
        return L + ["NO DIP SIGNALS FIRED", "",
                    "  Either the cache holds no impulses of this size or the",
                    "  detector is wrong. Check the impulse rate before",
                    "  concluding anything about the setup.", ""]

    fe = stat(g["fill_edge"])
    L += ["THE MECHANICAL PART — what is free, and therefore not evidence", "",
          f"  median fill difference   {fe['med']:+.1%}   "
          f"(dip entry below MCL's, on {fe['n']} paired sessions)",
          f"  dip fired EARLIER        {len(g['earlier'])} sessions   "
          f"median {stat(g['earlier'])['med']:.0f} bars",
          f"  dip fired LATER          {len(g['later'])} sessions   "
          f"median {stat(g['later'])['med']:.0f} bars", "",
          "  A dip that fires AFTER MCL's entry is not an earlier entry. It is",
          "  a re-entry into a position MCL already holds, and it is counted",
          "  separately for that reason.", ""]

    if len(g["later"]) > len(g["earlier"]):
        L += ["  THE SIGNAL IS MOSTLY LATE. Whatever the excursion table says,",
              "  this is not the earlier entry the four convergent findings",
              "  argued for -- it is a different setup that happens to fire on",
              "  the same names. Read the rest with that in mind.", ""]

    d = stat([r["ratio"] for r in g["dip_only"]])
    m = stat([r["ratio"] for r in g["mcl_only"] + mcl_paired])
    de = stat([r["ratio"] for r in g["dip_only"] if r["date"] < split])
    dl = stat([r["ratio"] for r in g["dip_only"] if r["date"] >= split])

    L += ["THE QUESTION — what the ADDED trades are worth", "",
          f"  DIP ONLY      n={d['n']:<5} median MFE/MAE {d['med']:.2f}",
          f"  MCL's entries n={m['n']:<5} median MFE/MAE {m['med']:.2f}",
          f"  DIP ONLY by half: early {de['med']:.2f} (n={de['n']})   "
          f"late {dl['med']:.2f} (n={dl['n']})", ""]

    if not m["n"]:
        # THE EMPTY BASELINE. MCL's median ratio is 0.00 when it has no trades
        # here, and every positive dip reading clears it -- so the strongest
        # possible verdict prints off a baseline that does not exist. This
        # happened: `Trade.entry_time` is a string, the position map was keyed
        # by Timestamp, 71 real trades mapped to none, and the report said the
        # added trades stood on their own.
        L += ["  NO BASELINE. MCL has no entries in this run, so there is",
              "  nothing to compare the added trades against. A median of 0.00",
              "  is beaten by any positive reading, which is why this refuses",
              "  rather than reporting the comparison. Check the entry mapping",
              "  before reading anything above as a result.", ""]
    elif d["n"] < 15:
        L += ["  TOO FEW ADDED TRADES for a verdict. Under fifteen, the median",
              "  moves with any one session. Reported, not concluded.", ""]
    elif not de["n"] or not dl["n"]:
        # THE CONTROL THAT DID NOT DIVIDE. An empty half has a median of zero,
        # which fails the both-halves test for the same reason a genuinely bad
        # half does -- and the two must not print the same verdict. This branch
        # exists because the first version of this function did not have it and
        # scored an undivided run as a refutation.
        L += ["  THE HALVES CONTROL DID NOT DIVIDE THIS RUN", "",
              f"  DIP ONLY has no trades on one side of {split} "
              f"(early {de['n']}, late {dl['n']}). An empty half has a median",
              "  of zero and fails the test for the same reason a bad half",
              "  does. NO VERDICT drawn.", ""]
    elif d["med"] >= m["med"] and de["med"] >= m["med"] and dl["med"] >= m["med"]:
        L += ["  THE ADDED TRADES STAND ON THEIR OWN, in both halves. That is",
              "  the condition for building this into a strategy rather than",
              "  leaving it as a measurement. The next step is an entry mode in",
              "  the harness, NOT a second engine: `PROGRAM_INDEX.md` §7 item 3",
              "  already licenses an intrabar-entry hypothesis and this is it.",
              "",
              "  Still in-sample, and there is no stated dip-buy rule behind",
              "  the detector -- the two source videos are untranscribed. That",
              "  gap should close before this is sized.", ""]
    else:
        L += ["  THE ADDED TRADES DO NOT STAND ON THEIR OWN.", "",
              "  This is the outcome the fill trap predicts and it is the",
              "  reason the study is built this way: the shared setups would",
              "  have shown a clean win from the better price alone. What the",
              "  numbers say is that buying into the pullback picks up setups",
              "  the confirmation entry was right to refuse.", "",
              "  What it does NOT say is that dip buying is worthless. The",
              "  census has it at 129 mentions and a 0.7 red-day lift, and",
              "  `warrior_4` §6 says the two videos that state the actual rule",
              "  are UNTRANSCRIBED. A detector inferred from four adjacent",
              "  findings failing is evidence about the inference.", ""]

    L += ["WHAT IS NOT IN HERE", "",
          "  His stop. Three of his setups land on 10-20c and that stop was",
          "  measured and rejected on 2026-09-10 on the price band. Putting it",
          "  back inside a test of the ENTRY would confound the two.",
          "",
          "  His level-2 trigger (`warrior_1` §3b). We have no level 2 in the",
          "  backtest and a proxy would be a fifth parameter.",
          "",
          "  P/L. Scoring these needs an exit model, and the exit is the",
          "  project's largest open question. MFE and MAE need none."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--spend-holdout", action="store_true",
                   help="read the LOCKED sessions instead of the training "
                        "ones. One-way: a holdout read casually is not one.")
    p.add_argument("--out", default="var/reports/dip_entry.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    cfg = DE.DipConfig()
    sessions = load_sessions(Path(a.cache))
    sessions, set_aside, side = HO.split_sessions(sessions, a.spend_holdout)
    if not sessions:
        sys.exit(f"no sessions on the {side} side of {a.cache}")
    rows = [session_rows(s, d, df, cfg) for s, d, df in sessions]
    g = collect(rows, cfg)
    emit("\n".join(render(g, paired_mcl(rows), len(sessions), side, cfg)),
         a.out, header=f"common.dip_study  cache={a.cache}  side={side}"
                       + (f"  ({set_aside} set aside)" if set_aside else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
