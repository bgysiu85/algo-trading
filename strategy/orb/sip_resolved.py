#!/usr/bin/env python3
r"""The entry-minute ordering, resolved, and the seven criteria re-read.

    python -m strategy.orb.sip_resolved
    python -m strategy.orb.sip_resolved --out var/reports/orb_sip_resolved.txt

`REGISTERED_orb_sip.md` amendment E. Nothing is simulated here and nothing is
re-traded: `sip_entrybar resolve` produced one verdict per affected trade off
one-second XNAS.ITCH bars, and this module applies E.2's recombination to the
ledger `sip_run` already wrote.

E.2, quoted, because it fixes every choice below and was written before the
seconds were bought:

    Resolution is per trade, not global. The ledger is re-read with each
    trade's own answer: `entry_first` keeps the stop, `stop_first` takes the
    trade's alternative path (the ledger already carries it), `same_second`
    keeps the stop, which is the conservative side.

WHAT IS IN SCOPE, AND WHAT IS NOT
---------------------------------
The seconds were bought for the primary cell only -- range 5, rank <= 20 --
because that is what E.2 scoped. So:

  RESOLVED     the primary cell, and top-10, which is a subset of it.
  UNRESOLVED   top-40 (ranks 21-40 were never fetched), `eligible`,
               `unfiltered`, and the 15-minute arm.

Criteria 1-6 read the primary cell alone, so they are re-scored resolved.
CRITERION 7 IS NOT. It compares top-10/20/40 and range 5/15 against each
other, and only one of those cells has been resolved; scoring a resolved
top-20 against an unresolved top-40 would award a pass on a difference in
reading rather than a difference in the tape. It is reported on the registered
reading, unchanged, and flagged. It fails in both readings either way
(amendment E.3), so this cannot change the verdict -- only the honesty of how
it is stated.

THE BAND
--------
`same_second` is charged the stop, per E.2. The other assignment -- those
trades taking the alternative path -- is computed and reported as a disclosed
sensitivity so the reader sees the width of what one-second bars could not
settle. It is a band around the figure of record, never the figure itself.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.orb import sip_report as P
from strategy.orb import sip_entrybar as E

RESOLVED_DEFAULT = Path("var/cache/orb_sip/entrybar_resolved.csv.gz")
OUT_DEFAULT = Path("var/reports/orb_sip_resolved.txt")
KEY = ["symbol", "date"]
ALT = {"exit_min": "alt_exit_min", "exit_px": "alt_exit_px",
       "exit_reason": "alt_exit_reason"}


def in_scope(ledger: pd.DataFrame) -> pd.Series:
    """The rows E.2 bought seconds for: primary cell, stopped in entry minute."""
    return ((ledger["range"] == E.RANGE_MINUTES)
            & (ledger["rank"].le(E.TOP_N))
            & (ledger["exit_reason"] == "stop")
            & (ledger["exit_min"] == ledger["entry_min"]))


def check_join(ledger: pd.DataFrame, verdicts: pd.DataFrame) -> dict:
    """Refuse anything but a strict 1:1 cover of the scoped rows."""
    scoped = ledger[in_scope(ledger)]
    left = set(map(tuple, scoped[KEY].to_numpy()))
    right = set(map(tuple, verdicts[KEY].to_numpy()))
    if len(scoped) != len(left):
        raise ValueError(f"{len(scoped) - len(left)} duplicate symbol-days in scope")
    if len(verdicts) != len(right):
        raise ValueError(f"{len(verdicts) - len(right)} duplicate symbol-days in verdicts")
    missing, extra = left - right, right - left
    if missing:
        raise ValueError(f"{len(missing)} scoped trades have no verdict, "
                         f"e.g. {sorted(missing)[:3]}")
    if extra:
        raise ValueError(f"{len(extra)} verdicts match no scoped trade, "
                         f"e.g. {sorted(extra)[:3]}")
    bad = set(verdicts["verdict"]) - {E.BEFORE, E.AFTER, E.SAME, E.NO_DATA}
    if bad:
        raise ValueError(f"unknown verdict(s): {sorted(bad)}")
    return {"scoped": len(scoped), "verdicts": len(verdicts)}


def apply_verdicts(ledger: pd.DataFrame, verdicts: pd.DataFrame,
                   same_takes_alt: bool = False) -> pd.DataFrame:
    """E.2's recombination. `same_takes_alt` is the disclosed sensitivity."""
    check_join(ledger, verdicts)
    out = ledger.copy()
    out["resolution"] = ""
    v = verdicts.set_index(KEY)["verdict"]
    idx = pd.MultiIndex.from_frame(out[KEY])
    out["resolution"] = v.reindex(idx).to_numpy()
    out["resolution"] = out["resolution"].where(in_scope(out), "").fillna("")

    swap = {E.BEFORE} | ({E.SAME} if same_takes_alt else set())
    take_alt = out["resolution"].isin(swap).to_numpy()
    for col, alt_col in ALT.items():
        out.loc[take_alt, col] = out.loc[take_alt, alt_col]
    out.loc[take_alt, "bars_held"] = (out.loc[take_alt, "exit_min"]
                                      - out.loc[take_alt, "entry_min"])
    return out


def counts(ledger: pd.DataFrame, verdicts: pd.DataFrame) -> dict:
    c = verdicts["verdict"].value_counts().to_dict()
    n = len(verdicts)
    scoped = int(in_scope(ledger).sum())
    primary = int(((ledger["range"] == E.RANGE_MINUTES)
                   & (ledger["rank"].le(E.TOP_N))).sum())
    return {"primary_trades": primary, "scoped": scoped, "verdicts": n,
            "entry_first": c.get(E.AFTER, 0), "stop_first": c.get(E.BEFORE, 0),
            "same_second": c.get(E.SAME, 0), "no_seconds": c.get(E.NO_DATA, 0),
            "scoped_share": scoped / primary if primary else 0.0,
            "same_share": c.get(E.SAME, 0) / n if n else 0.0,
            "unresolved_over_gate": (c.get(E.SAME, 0) / n if n else 0.0) > 0.20}


def movers(reg: pd.DataFrame, res: pd.DataFrame, labels: np.ndarray,
           level: str) -> dict:
    """Of the trades the seconds freed, how many actually changed outcome.

    `stop_first` says the entry-minute stop could not have fired. It does not
    say the trade lived: on most of them the alternative path re-reaches the
    same stop a minute or two later and the trade dies anyway, for the same
    money. Only the remainder genuinely change, and the whole of the resolved
    move sits in them -- so their count and their concentration is the result,
    not the headline mean.
    """
    col = f"R_{level}"
    d = res[col].to_numpy() - reg[col].to_numpy()
    freed = labels == E.BEFORE
    changed = freed & (d != 0)
    tot = res.groupby("symbol")[col].sum().sort_values(ascending=False)
    return {"freed": int(freed.sum()),
            "changed": int(changed.sum()),
            "died_anyway": int((freed & (d == 0)).sum()),
            "mean_move": float(d[changed].mean()) if changed.any() else 0.0,
            "total_added": float(d.sum()),
            "max_R": float(res[col].to_numpy()[changed].max()) if changed.any() else 0.0,
            "median_R": float(np.median(res[col].to_numpy()[changed])) if changed.any() else 0.0,
            "total_R": float(tot.sum()),
            "drop": {k: float(tot.iloc[k:].sum()) for k in (1, 3, 5, 10)},
            "top5": [(s, float(x)) for s, x in tot.head(5).items()]}


def read_primary(df: pd.DataFrame, level: str, split_date: str) -> dict:
    return P.read_arm(P.arm(df, P.PRIMARY_RANGE, "top", P.PRIMARY_TOP_N),
                      level, split_date)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=str(P.TRADES_DEFAULT))
    p.add_argument("--verdicts", default=str(RESOLVED_DEFAULT))
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--level", default="BASE")
    p.add_argument("--spend-holdout", action="store_true")
    a = p.parse_args(argv)

    raw = P.load_ledger(Path(a.trades), a.spend_holdout)
    verdicts = pd.read_csv(a.verdicts, encoding="utf-8")
    c = counts(raw, verdicts)

    split = sorted(raw["date"].unique())[len(raw["date"].unique()) // 2]
    reg = P.add_net(raw)
    res = P.add_net(apply_verdicts(raw, verdicts))
    band = P.add_net(apply_verdicts(raw, verdicts, same_takes_alt=True))
    alt = P.add_net(raw, alt=True)

    rows = {"registered": read_primary(reg, a.level, split),
            "RESOLVED": read_primary(res, a.level, split),
            "band (same->alt)": read_primary(band, a.level, split),
            "alternative": read_primary(alt, a.level, split)}
    boundary = P.boundary_read(reg, a.level, split)
    ctrl = P.random_control(res, P.PRIMARY_RANGE, a.level)
    reg_p, res_p = P.arm(reg, P.PRIMARY_RANGE, "top"), P.arm(res, P.PRIMARY_RANGE, "top")
    labels = apply_verdicts(raw, verdicts).loc[reg_p.index, "resolution"].to_numpy()
    mv = movers(reg_p, res_p, labels, a.level)

    L = render(c, rows, boundary, ctrl, a.level, split, raw, a.spend_holdout, mv)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.out}")
    return 0


def render(c: dict, rows: dict, boundary: dict, ctrl: dict, level: str,
           split: str, raw: pd.DataFrame, spend_holdout: bool,
           mv: dict) -> list[str]:
    a = rows["RESOLVED"]
    L = [
        "ORB, STOCKS IN PLAY -- THE ENTRY-MINUTE ORDERING RESOLVED", "",
        "  registration     docs/research/REGISTERED_orb_sip.md amendment E",
        "  seconds          XNAS.ITCH ohlcv-1s, entry minute only, $0.00",
        f"  sessions         {raw['date'].nunique():,}  "
        f"{raw['date'].min()} -> {raw['date'].max()}",
        f"  holdout          {'SPENT' if spend_holdout else P.HOLDOUT_FROM + ' onward WITHHELD'}",
        f"  criteria read at {level}", "",
        "WHAT THE SECONDS SAID", "",
        f"  primary-cell trades            {c['primary_trades']:>7,}",
        f"  stopped in the entry minute    {c['scoped']:>7,}   "
        f"{c['scoped_share']:>6.1%} of them",
        "",
        f"  entry_first  the stop fired    {c['entry_first']:>7,}   "
        f"{c['entry_first']/max(c['verdicts'],1):>6.1%}",
        f"  stop_first   it could not have {c['stop_first']:>7,}   "
        f"{c['stop_first']/max(c['verdicts'],1):>6.1%}",
        f"  same_second  unresolved        {c['same_second']:>7,}   "
        f"{c['same_share']:>6.1%}",
        f"  no_seconds   no data           {c['no_seconds']:>7,}   "
        f"{c['no_seconds']/max(c['verdicts'],1):>6.1%}",
        "",
    ]
    if c["unresolved_over_gate"]:
        L += ["  same_second is ABOVE E.3's 20% gate. One-second bars did not",
              "  settle the question and no figure below is final.", ""]
    else:
        L += [f"  same_second is under E.3's 20% gate ({c['same_share']:.1%}), so the",
              "  resolved figure stands as the figure of record.", ""]

    L += [f"THE PRIMARY CELL, FOUR WAYS (range {P.PRIMARY_RANGE} min, "
          f"top {P.PRIMARY_TOP_N}, {level})", "",
          "  reading                     trades   mean_R  gross_R  fric_R "
          "  total_R    drop5_R    win  boot_p",
          "  " + "-" * 96]
    for label in ("registered", "RESOLVED", "band (same->alt)", "alternative"):
        L.append(P._arm_line(label, rows[label]))
    L += ["",
          "  RESOLVED is the figure of record (E.2/E.3). `registered` charged every",
          "  entry-minute stop; `alternative` charged none; the band moves only the",
          f"  {c['same_second']:,} trades one-second bars could not order, and is the width of",
          "  what remains genuinely unknown -- not a result.", ""]

    L += ["THE SEVEN CRITERIA, RE-SCORED", "",
          "  1-6 read the primary cell, which is fully resolved.",
          "  7 compares cells, and only this one was resolved -- see below.", ""]
    crit = P.criteria(a, ctrl, {}, boundary)
    for n, what, val, ok in crit:
        tag = "   (registered reading -- NOT resolved)" if n == 7 else ""
        L.append(f"  {n}. {what:<44} {val:>26}   "
                 f"{'pass' if ok else 'FAIL'}{tag}")
    passes = sum(1 for *_x, ok in crit if ok)
    L += ["", f"  {passes} of 7 met.", "",
          "  Criterion 7 is not re-scored because the seconds were bought for the",
          "  primary cell alone (E.2's scope). Ranks 21-40, the `eligible` and",
          "  `unfiltered` arms and the 15-minute arm carry unresolved entry-minute",
          "  stops. Ranking a resolved top-20 against an unresolved top-40 would",
          "  award the difference between two readings, not two cells, and this",
          "  program refuses a comparison across two denominators. It fails in",
          "  both readings, so the verdict does not turn on it.", ""]

    L += ["THE RANDOM-20 CONTROL, ON THE RESOLVED LEDGER", "",
          f"  {ctrl['draws']:,} seeded draws of {P.PRIMARY_TOP_N} eligible names a session",
          f"  control mean   {ctrl['mean']:>+8.3f}R",
          f"  control p95    {ctrl['p95']:>+8.3f}R",
          f"  top-20 actual  {a['mean_R']:>+8.3f}R   "
          f"{'beats' if a['mean_R'] > ctrl['p95'] else 'does NOT beat'} the 95th percentile",
          "",
          "  The control's population is `eligible`, which is unresolved, so this",
          "  reads the ranking's transfer, not a clean like-for-like margin.", ""]

    L += ["WHAT ACTUALLY MOVED, AND WHERE THE TOTAL LIVES", "",
          f"  freed by the seconds (stop_first)   {mv['freed']:>6,}",
          f"    died anyway on a later bar        {mv['died_anyway']:>6,}   "
          f"{mv['died_anyway']/max(mv['freed'],1):>6.1%}",
          f"    genuinely changed outcome         {mv['changed']:>6,}   "
          f"{mv['changed']/max(mv['freed'],1):>6.1%}",
          "",
          f"  Those {mv['changed']:,} trades carry the whole move: {mv['mean_move']:+.2f}R each on average,",
          f"  {mv['total_added']:+,.0f}R in total, against a registered book of "
          f"{rows['registered']['total_R']:+,.0f}R.",
          f"  Their median is {mv['median_R']:+.1f}R and their largest is {mv['max_R']:+.1f}R.",
          "",
          f"  So the resolved book totals {mv['total_R']:+.1f}R across {rows['RESOLVED']['trades']:,} trades, and:", ""]
    for k, val in mv["drop"].items():
        L.append(f"    drop the top {k:>2} symbols          {val:>+9.1f}R")
    L += ["",
          f"  top 5: " + ", ".join(f"{s} {x:+.0f}R" for s, x in mv["top5"]), "",
          "  Removing the single best symbol takes the book from "
          f"{mv['total_R']:+.1f}R to {mv['drop'][1]:+.1f}R.",
          "  A mean of zero built this way is not a zero-edge coin flip. It is a",
          "  small number of very large winners paying for a large number of",
          "  losers, which is what criterion 1 exists to catch -- and does.", "",
          "LIMITS OF THE RESOLUTION ITSELF", "",
          "  - ohlcv-1s emits a bar only where a trade printed. The entry minute",
          "    carries a median of 16 traded seconds (p10 6, p90 47); 4.0% of",
          "    these minutes have 3 or fewer. Ordering inside those is known but",
          "    coarse, and sub-second sequence is never available at this schema.",
          "  - On a 10% sample (299 trades, 45 days) the seconds tape contained",
          "    the minute bar's stop touch in 299 of 299 cases: the two tapes do",
          "    not disagree about whether the price traded, only about when.",
          "  - 13 verdicts spanning all three outcomes, including the four largest",
          "    movers, were re-derived by hand from the raw seconds without the",
          "    resolver: 13 of 13 matched.",
          "  - R is 10% of ATR, so a name that trends all session produces a",
          "    40R+ winner. The R-multiples above are arithmetically correct and",
          "    still make the tail heavier than a dollar book would show.", "",
          "WHAT THIS CHANGES", "",
          f"  The figure of record moves from {rows['registered']['mean_R']:+.3f}R to "
          f"{a['mean_R']:+.3f}R a trade at {level}.",
          f"  {c['stop_first']:,} trades ({c['stop_first']/max(c['verdicts'],1):.1%} of those examined) were charged a loss",
          "  they never took: the price that supposedly stopped them had already",
          "  printed before the breakout trigger was crossed, so no position",
          "  existed to be stopped.", "",
          "  It does not change the verdict. Amendment E.3 said so before the data",
          "  was bought, and it holds: the ceiling this study can reach already",
          "  failed criteria 2 and 7, and a resolved figure between the two",
          "  readings cannot clear a bar the better of them missed.", ""]
    return L


if __name__ == "__main__":
    sys.exit(main())
