#!/usr/bin/env python3
r"""How far did the losers actually go against us, and where did they end?

    python -m strategy.orb.sip_excursion --jobs 8

`REGISTERED_orb_sip.md` amendment F. DESCRIPTIVE ONLY. This module measures
excursions and reports distributions. It simulates no stop width, produces no
net P/L, and therefore offers nothing to select on -- which is the whole point
of running it before any variant is registered (F.0).

THE QUESTION
------------
Friction is 0.350R against a gross of 0.351R, and it is that large because R is
about 9c while a round trip costs about 3c. Widening the stop shrinks friction
as a share of the bet -- but at constant dollar risk it shrinks gross by the
same factor, so it can only help through ONE channel: trades stopped out that
would otherwise have gone on to work.

So: among the losers, how many went less than 2R against us, recovered, and
closed the session in profit -- in that order?

THE ORDER MATTERS, AND IS WHY `mae_before_mfe` EXISTS
-----------------------------------------------------
A trade that ran first, then gave it all back and closed green would show a
tolerable MAE and a positive close while being nothing a wider stop rescued --
it was never in danger before it was already winning. Counting it would inflate
the answer in exactly the direction that argues for more work. F.2 requires the
adverse extreme to precede the favourable one.

Minute bars carry no intra-bar order. A single bar holding both extremes is
counted AGAINST the favourable case, as everywhere else in this registration.
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.orb import sip as S
from strategy.orb import sip_report as P
from strategy.orb import sip_resolved as R
from strategy.orb.sip_summary import day_file

PRICE_DATASET = "XNAS.ITCH"
OUT_DEFAULT = Path("var/cache/orb_sip/excursion.csv.gz")
REPORT_DEFAULT = Path("var/reports/orb_sip_excursion.txt")
RESCUE_MAE = 2.0        # F.3
RESCUE_MIN_SHARE = 0.25  # F.3
WIDTHS = (1.5, 2.0, 2.5, 3.0)   # F.3.1
WIDTH_COVER = 0.60               # F.3.1
# NOTE, recorded rather than hidden: F.3 defines rescuable as MAE < 2.0R, so
# every rescuable trade is inside k = 2.0 by construction and cover[2.0] is
# always 1.0. F.3.1's "if no k reaches 60%" branch is therefore unreachable
# whenever any rescuable trade exists, and the chosen width can only be 1.5 or
# 2.0. The branch is implemented as registered; this note says why it cannot
# fire, so nobody later reads its absence as a result.
COLS = ["symbol", "date", "mae_r", "mfe_r", "end_r", "mae_before_mfe", "bars"]


def excursion(minute, high, low, close, side: int, entry_min: int,
              entry_px: float, r: float) -> tuple | None:
    """One trade, from its ENTRY bar to the last RTH bar of the session.

    The registered stop is ignored -- this asks what the price did, not what
    the strategy did. Bars before the entry are excluded: a position that does
    not exist cannot be run against.
    """
    m = np.asarray(minute)
    keep = (m >= entry_min) & (m <= S.LAST_BAR_MIN)
    if not keep.any() or r <= 0:
        return None
    h = np.asarray(high, float)[keep]
    l = np.asarray(low, float)[keep]
    c = np.asarray(close, float)[keep]

    adverse = (entry_px - l) if side == S.LONG else (h - entry_px)
    favour = (h - entry_px) if side == S.LONG else (entry_px - l)
    mae = float(np.max(adverse)) / r
    mfe = float(np.max(favour)) / r
    end_r = float((c[-1] - entry_px) * side) / r

    i_mae = int(np.argmax(adverse))
    i_mfe = int(np.argmax(favour))
    # a bar holding both extremes is counted against the favourable case
    before = i_mae < i_mfe
    return mae, mfe, end_r, bool(before), int(keep.sum())


def _one(args):
    archive, day, rows_json = args
    from common.dbn_io import read_dbn
    rows = pd.read_json(rows_json, orient="records")
    try:
        bars = read_dbn(day_file(Path(archive), PRICE_DATASET, day))
    except Exception:  # noqa: BLE001
        return []
    et = bars.index.tz_convert("America/New_York")
    bars = bars.assign(minute=(et.hour * 60 + et.minute).to_numpy())
    out = []
    for sym, g in bars.groupby("symbol", sort=False):
        hit = rows[rows["symbol"] == sym]
        if hit.empty:
            continue
        g = g.sort_values("minute")
        for t in hit.itertuples():
            e = excursion(g["minute"].to_numpy(), g["high"], g["low"],
                          g["close"], int(t.side), int(t.entry_min),
                          float(t.entry_px), float(t.r))
            if e is not None:
                out.append((sym, day, *e))
    return out


def measure(ledger: pd.DataFrame, archive: Path, jobs: int, tmp: Path) -> pd.DataFrame:
    tmp.mkdir(parents=True, exist_ok=True)
    work = []
    for day, g in ledger.groupby("date", sort=True):
        f = tmp / f"{day}.json"
        g[["symbol", "side", "entry_min", "entry_px", "r"]].to_json(
            f, orient="records")
        work.append((str(archive), day, str(f)))
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            parts = list(ex.map(_one, work))
    else:
        parts = [_one(w) for w in work]
    return pd.DataFrame([x for p in parts for x in p], columns=COLS)


def rescuable(d: pd.DataFrame) -> pd.Series:
    """F.3: went less than 2R against us, recovered, and in that order."""
    return ((d["mae_r"] < RESCUE_MAE) & (d["end_r"] > 0)
            & d["mae_before_mfe"].astype(bool))


def verdict(losers: pd.DataFrame) -> dict:
    """F.3 and F.3.1, applied exactly as registered."""
    n = len(losers)
    res = rescuable(losers)
    share = float(res.mean()) if n else 0.0
    go = share >= RESCUE_MIN_SHARE
    chosen, cover = None, {}
    sub = losers[res]
    for k in WIDTHS:
        cover[k] = float((sub["mae_r"] < k).mean()) if len(sub) else 0.0
        # below the gate F.3 closes ORB outright, so no width is chosen at all
        if go and chosen is None and cover[k] >= WIDTH_COVER:
            chosen = k
    return {"losers": n, "rescuable": int(res.sum()), "share": share,
            "gate": RESCUE_MIN_SHARE, "proceed": bool(go),
            "cover": cover, "width": chosen,
            # F.3.1: no width reaching the cover bar also closes ORB
            "closes": (not go) or chosen is None}


def render(d: pd.DataFrame, losers: pd.DataFrame, v: dict) -> list[str]:
    def q(s, p):
        return float(np.percentile(s, p)) if len(s) else float("nan")
    L = ["ORB, STOCKS IN PLAY -- EXCURSIONS (amendment F)", "",
         "  registration   docs/research/REGISTERED_orb_sip.md amendment F,",
         "                 committed before this ran",
         "  scope          primary cell, range 5, rank <= 20, holdout withheld",
         "  bars           XNAS.ITCH ohlcv-1m already on disk; nothing bought",
         "  measured       entry bar -> last RTH bar, registered stop ignored",
         "", "  DESCRIPTIVE ONLY. No stop width is simulated and no net P/L",
         "  appears below, so there is nothing here to select on (F.0).", "",
         f"  trades measured   {len(d):>7,}",
         f"  losing trades     {len(losers):>7,}   "
         f"{len(losers)/max(len(d),1):.1%}", "",
         "HOW FAR THE LOSERS WENT AGAINST US (multiples of the trade's risk)", ""]
    for name, s in (("all trades", d["mae_r"]), ("losers only", losers["mae_r"])):
        L.append(f"  {name:<14} median {q(s,50):>6.2f}R   p75 {q(s,75):>6.2f}R   "
                 f"p90 {q(s,90):>6.2f}R   p99 {q(s,99):>7.2f}R")
    L += ["", "  share of losers whose worst point stayed inside:", ""]
    for k in (1.0, 1.5, 2.0, 3.0, 5.0):
        L.append(f"    {k:>4.1f}R   {float((losers['mae_r'] < k).mean()):>6.1%}")

    L += ["", "WHERE THE LOSERS ENDED THE SESSION", "",
          f"  closed in profit had we never been stopped   "
          f"{float((losers['end_r'] > 0).mean()):>6.1%}",
          f"  ...and went less than {RESCUE_MAE:.0f}R against us first      "
          f"{float(((losers['end_r'] > 0) & (losers['mae_r'] < RESCUE_MAE)).mean()):>6.1%}",
          f"  ...and in that order (adverse extreme first)  "
          f"{v['share']:>6.1%}   <- F.3's RESCUABLE", "",
          "  The order test removes trades that ran first and gave it back:",
          "  those were never rescued by a wider stop, they were already",
          "  winning and then were not.", ""]

    L += ["F.3, APPLIED AS REGISTERED", "",
          f"  rescuable losers     {v['rescuable']:>7,} of {v['losers']:,}"
          f"   = {v['share']:.1%}",
          f"  the registered gate  {v['gate']:.0%}", ""]
    if v["proceed"]:
        L += ["  AT OR ABOVE THE GATE. One stop width may be registered,",
              "  chosen by F.3.1's rule and not by performance:", ""]
        for k, c in v["cover"].items():
            mark = "  <- chosen" if v["width"] == k else ""
            L.append(f"    k = {k:>3.1f}   covers {c:>6.1%} of rescuable losers"
                     f"   (bar {WIDTH_COVER:.0%}){mark}")
        if v["width"] is None:
            L += ["", "  No width reaches the 60% bar. F.3.1 closes ORB."]
    else:
        L += ["  BELOW THE GATE. The stop is doing its job: a wider one loses",
              "  more slowly on the way to the same place. F.3 closes ORB",
              "  permanently -- no variant registered, no data bought, the",
              "  holdout stays locked.", ""]
    L += ["", f"  F.4 predicted rescuable would land below {RESCUE_MIN_SHARE:.0%} "
          f"and ORB would close.",
          f"  That prediction is {'WRONG' if v['proceed'] else 'correct'}"
          f", and is recorded either way.", ""]
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=str(P.TRADES_DEFAULT))
    p.add_argument("--verdicts", default=str(R.RESOLVED_DEFAULT))
    p.add_argument("--archive", default=None)
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--report", default=str(REPORT_DEFAULT))
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = p.parse_args(argv)

    raw = P.load_ledger(Path(a.trades))
    res = P.add_net(R.apply_verdicts(raw, pd.read_csv(a.verdicts, encoding="utf-8")))
    prim = P.arm(res, P.PRIMARY_RANGE, "top", P.PRIMARY_TOP_N)

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()
    d = measure(prim, archive, a.jobs, Path(a.out).parent / "_excursion")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(a.out, index=False, encoding="utf-8", compression="gzip")

    lose = prim[prim["R_BASE"] <= 0][["symbol", "date"]]
    losers = d.merge(lose, on=["symbol", "date"])
    v = verdict(losers)
    L = render(d, losers, v)
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
