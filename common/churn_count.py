#!/usr/bin/env python3
"""How much of the live loss is sub-minute churn, and was 2026-09-11 typical?

    python -m common.churn_count

WHAT THIS IS FOR
-----------------
On 2026-09-11 the entry dedupe keyed on the frame's last 1-minute row while
MC5's signal was computed on a 5-minute bucket, so one signal could enter five
times (fixed 2026-09-12, `tests/brokers/test_entry_dedup.py`). That session:

    19 of 48 entries (40%) reused an already-traded signal bar
    18 of 48 round trips held under one minute, and lost 137.67 of the
    session's 156.91

**One session is one session.** The claim that reused signals are a material
share of the live loss rests on a single day, and the other fill logs have
been sitting on disk the whole time. This counts all of them.

THE THREE MEASURES, AND WHY THEY ARE SEPARATE
-----------------------------------------------
    REUSED SIGNAL   an entry whose (strategy, symbol, signal close, macd,
                    macd_sig, rsi, vol) fingerprint has already opened a trade.
                    This is the bug's direct signature.

    INSTANT RE-ENTRY  a buy within RAPID_S of selling the SAME name. This
                    catches the same behaviour from the outside, and it would
                    still fire if the bug had some other cause.

    SUB-MINUTE      a round trip held under a minute. The consequence, and the
                    only one of the three that needs no theory about why.

They are reported separately and never summed. A trade can be all three, and
adding them would trible-count it into a number larger than the session.

WHAT THIS CANNOT SAY
---------------------
It cannot say the fix earns the money back. These sessions ran the broken
guard, so removing their churn from the history is a counterfactual, not a
measurement -- the trades that did NOT happen have no prices. The honest claim
is bounded: this is what the affected trades cost, not what their absence
would have returned.

It also cannot attribute a session's whole result to the bug. MCL never had it
and lost money on its own in most of these sessions; that is printed beside
MC5 rather than folded in.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from common.report_fmt import acct
from common.report_io import emit

RAPID_S = 5.0            # a buy this soon after selling the same name
SUB_MINUTE = 1.0

FINGERPRINT = ["strategy", "symbol", "ref_close", "macd", "macd_sig", "rsi",
               "vol"]


def round_trips(f: pd.DataFrame) -> pd.DataFrame:
    """Pair each SELL carrying a P/L with the BUY that opened it.

    Walked in FILE ORDER per (strategy, symbol). A re-sort on the timestamp
    would reorder a sell and the buy that follows it in the same second, and
    those same-second pairs are exactly the rows under investigation.
    """
    rows = []
    for (st, sym), g in f.groupby(["strategy", "symbol"], sort=False):
        open_row = None
        last_sell_ts = None
        for r in g.itertuples():
            if r.action == "BUY":
                open_row = r
            elif r.action == "SELL":
                if open_row is not None and pd.notna(r.trade_pnl):
                    since = (None if last_sell_ts is None else
                             (open_row.ts_et - last_sell_ts).total_seconds())
                    rows.append({
                        "strategy": st, "symbol": sym,
                        "open_ts": open_row.ts_et, "close_ts": r.ts_et,
                        "pnl": float(r.trade_pnl),
                        "hold": float(r.hold_minutes),
                        "since_prev_exit_s": since,
                        "fp": "|".join(str(getattr(open_row, k))
                                       for k in FINGERPRINT)})
                    open_row = None
                last_sell_ts = r.ts_et
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["reused"] = out.fp.duplicated(keep="first")
    out["instant"] = (out.since_prev_exit_s.notna()
                      & (out.since_prev_exit_s <= RAPID_S))
    out["sub_minute"] = out.hold < SUB_MINUTE
    return out


# Everything round_trips() reads. Checked up front so a missing column is a
# named refusal instead of a KeyError from inside a groupby six frames down.
REQUIRED = ["ts_et", "symbol", "action", "status", "trade_pnl", "hold_minutes"]


def load(path: Path) -> tuple[pd.DataFrame, str | None]:
    """(filled rows, the strategy label if it had to be DERIVED).

    The logs from before the multi-strategy work -- 2026-09-02, -03, -08 --
    have no `strategy` column at all, because there was only MCL. The label is
    taken from the filename prefix for those, and the caller is told, because
    a derived label that prints identically to a recorded one is the mistake
    this project keeps making.

    The prefix is used ONLY when the column is absent, never as a fallback for
    a file that has it: `mcl_fills_20260911.csv` is named for MCL and is full
    of MC5 rows, so the name is evidence about the ERA and not about any row.
    """
    d = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in d.columns]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column(s)")
    d["ts_et"] = pd.to_datetime(d["ts_et"])
    derived = None
    if "strategy" not in d.columns:
        derived = path.name.split("_", 1)[0].upper()
        d["strategy"] = derived
    for c in FINGERPRINT:
        if c not in d.columns:
            d[c] = pd.NA
    return d[d.status == "FILLED"].copy(), derived


def section(t: pd.DataFrame, flag: str, label: str) -> list[str]:
    L = [f"  {label}", ""]
    if t.empty:
        return L + ["    no trades", ""]
    for k in (True, False):
        g = t[t[flag] == k]
        name = "yes" if k else "no"
        if g.empty:
            L.append(f"    {name:<4} n=  0")
            continue
        L.append(f"    {name:<4} n={len(g):>3}   net{acct(g.pnl.sum(), 10)}"
                 f"   per trade{acct(g.pnl.mean(), 8)}"
                 f"   win {g.pnl.gt(0).mean() * 100:>4.0f}%"
                 f"   med hold {g.hold.median():>5.1f}m")
    return L + [""]


def render(per: list[dict], t: pd.DataFrame, files: list[str],
           elapsed: float, derived: list[str] | None = None,
           refused: list[dict] | None = None) -> list[str]:
    L = ["SUB-MINUTE CHURN IN THE LIVE RECORD", "",
         f"  {len(files)} session(s): {', '.join(files)}",
         f"  {len(t):,} round trip(s), net {acct(t.pnl.sum(), 1).strip()}",
         f"  a reused signal bar is the 2026-09-11 dedupe bug's signature; an",
         f"  instant re-entry is a buy within {RAPID_S:.0f}s of selling the "
         "same name",
         f"  elapsed {elapsed:.1f}s", ""]

    L += ["PER SESSION", "",
          f"  {'session':<12}{'trades':>8}{'net':>11}{'reused':>9}"
          f"{'instant':>9}{'<1 min':>8}{'net <1m':>11}   by strategy"]
    for p in per:
        L.append(f"  {p['date']:<12}{p['n']:>8}{acct(p['net'], 11)}"
                 f"{p['reused']:>9}{p['instant']:>9}{p['sub']:>8}"
                 f"{acct(p['sub_net'], 11)}   {p['by_strat']}")

    L += ["", "POOLED, BY MEASURE", ""]
    L += section(t, "reused", "entry REUSED an already-traded signal bar")
    L += section(t, "instant", f"entry within {RAPID_S:.0f}s of exiting the "
                               "same name")
    L += section(t, "sub_minute", "round trip held under one minute")

    L += ["  These overlap and are NEVER summed. A trade can be all three,",
          "  and adding them would count it three times into a figure larger",
          "  than the sessions it came from.", ""]

    L += ["BY STRATEGY", "",
          f"  {'strategy':<10}{'trades':>8}{'net':>11}{'reused':>9}"
          f"{'med hold':>10}{'win':>7}"]
    for st, g in t.groupby("strategy"):
        L.append(f"  {st:<10}{len(g):>8}{acct(g.pnl.sum(), 11)}"
                 f"{int(g.reused.sum()):>9}{g.hold.median():>9.1f}m"
                 f"{g.pnl.gt(0).mean() * 100:>6.0f}%")

    share = t.reused.mean() if len(t) else 0.0
    L += ["", "WAS 2026-09-11 TYPICAL?", "",
          f"  reused-signal share pooled: {share:.0%}",
          "  per session, above. A single session at 40% against a pooled",
          "  figure far below it means the bug's cost was concentrated, not",
          "  routine -- and the headline should be re-stated accordingly.", ""]

    if derived:
        L += ["HOW THE STRATEGY WAS LABELLED", "",
              "  These session(s) predate the strategy column and were",
              "  labelled from the FILENAME, not from the rows:", ""]
        L += [f"    {d}" for d in derived]
        L += ["",
              "  They are from the single-strategy era, so the label is sound",
              "  -- but it is DERIVED, and a derived label that prints like a",
              "  recorded one is how this project has been caught before.",
              "",
              "  They are also a CONTROL. MCL's signal bar is the frame's last",
              "  row, so the old guard worked for it: these sessions should",
              "  show ZERO reused signal bars. If they do not, the dedupe bug",
              "  was not what this report says it was.", ""]

    if refused:
        L += ["REFUSED", ""]
        L += [f"  {r['file']}: {r['why']}" for r in refused]
        L += ["",
              "  A refused log is NOT a clean one. It was not counted at all.",
              ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not an estimate of what the fix earns. Every session here ran",
          "  the broken guard, so removing these trades is a counterfactual:",
          "  the trades that would have happened instead have no prices. This",
          "  is what the affected trades COST, not what their absence returns.",
          "",
          "  Not an attribution of the whole loss. MCL never had the bug and",
          "  is printed separately rather than folded in.",
          "",
          "  Not a claim about fills. Slippage, the concurrency cap and the",
          "  exit mechanic are all live in these numbers and none of them is",
          "  held constant here."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--fills", default="var/fills")
    p.add_argument("--out", default="var/reports/churn_count.txt")
    return p


def main(argv=None) -> int:
    import time
    a = build_parser().parse_args(argv)
    t0 = time.time()

    paths = sorted(Path(a.fills).glob("*_fills_2*.csv"))
    paths = [p for p in paths if "_pre" not in p.name]
    if not paths:
        sys.exit(f"no fill logs in {a.fills}")

    per, frames, names, derived_from_name, refused = [], [], [], [], []
    for p in paths:
        try:
            f, derived = load(p)
        except (ValueError, pd.errors.EmptyDataError, KeyError) as e:
            refused.append({"file": p.name, "why": str(e)})
            continue
        t = round_trips(f)
        if t.empty:
            continue
        day = p.stem.split("_")[-1]
        day = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        t = t.assign(session=day)
        by = ", ".join(f"{s}:{acct(g.pnl.sum(), 1).strip()}"
                       for s, g in t.groupby("strategy"))
        if derived:
            derived_from_name.append(f"{day} ({derived})")
        per.append({"date": day, "n": len(t), "net": t.pnl.sum(),
                    "reused": int(t.reused.sum()),
                    "instant": int(t.instant.sum()),
                    "sub": int(t.sub_minute.sum()),
                    "sub_net": t[t.sub_minute].pnl.sum(),
                    "by_strat": by})
        frames.append(t)
        names.append(day)

    if not frames:
        sys.exit("no round trips found in any fill log")
    allt = pd.concat(frames, ignore_index=True)
    emit("\n".join(render(per, allt, names, time.time() - t0,
                          derived_from_name, refused)),
         a.out, header="common.churn_count")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
