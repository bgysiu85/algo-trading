#!/usr/bin/env python3
"""Which print is the REGULAR-session close?

    python -m common.regular_close                 # validate against known truth
    python -m common.regular_close --emit          # write var/state/regular_close.json

WHAT IS WRONG, AND HOW IT WAS PINNED DOWN
------------------------------------------
`prior_closes()` reads Databento's `ohlcv-1d` close. That schema aggregates the
WHOLE feed, so its close is the last print of the EXTENDED day (20:00 ET).
TradingView's `premarket_change` -- the clause the live screen actually applies
-- divides by the official 16:00 REGULAR close. Two closes that look comparable
and are not.

ACVA, 2026-09-10, is the proof, and the LOW is what makes it proof:

                     high      low    close
    ours            11.31     7.00    10.38
    the market       7.39     7.00     7.22

The low agrees to the cent and the high is 53% higher. A wrong bar does not
reproduce one endpoint exactly; a bar covering EXTRA HOURS does, because the
regular session set the low and the after-hours session set the high and the
close.

The error is one-directional -- a name that runs after hours gets an inflated
divisor, which DEFLATES its computed premarket change -- which is exactly the
16-missed-against-2 shape `screen_validate` found.

WHY THIS MODULE EXISTS RATHER THAN A ONE-LINE FIX
--------------------------------------------------
The repair needs a 16:00 close the archive does not carry, so it needs a pull.
Before spending one across 552 sessions, the CONSTRUCTION has to be right, and
there is a real ambiguity in it: the closing cross prints AT 16:00:00.000 and
is usually the largest trade of the day. A bar convention of [start, start+1m)
puts it in the 16:00 bar, not the 15:59 bar. Guess wrong and every close is the
last continuous print instead of the official one -- a small, plausible,
systematic error, which is the kind this project keeps shipping.

So each candidate is scored against closes taken from TradingView by hand.

THE TRAP IN THAT SCORING, AND THE GUARD FOR IT
------------------------------------------------
On a day with no after-hours activity the extended close and the regular close
are THE SAME NUMBER, so every candidate matches and the row proves nothing.
ACVA's 09-08 and 09-09 are exactly that. A scorer that counted them would
report a near-perfect match for whichever construction it tried first.

A row is therefore DISCRIMINATING only when our own `ohlcv-1d` close already
disagrees with the truth. Non-discriminating rows are printed, counted, and
excluded from the verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")
CLOSE_T = dtime(16, 0)

# Regular-session closes read from TradingView by hand, 2026-09-12. The
# exchange is recorded because two of these are NOT Nasdaq-listed and the
# archive is XNAS.BASIC -- a cross-listed name reaches this tape only through
# Nasdaq-venue prints, which is its own question and is noted in the report.
TRUTH = [
    ("2026-09-08", "ACVA", "NYSE", 7.03),
    ("2026-09-09", "ACVA", "NYSE", 7.37),
    ("2026-09-10", "ACVA", "NYSE", 7.22),
    ("2026-09-11", "ACVA", "NYSE", 10.41),
    ("2026-09-08", "ISPC", "NASDAQ", 1.59),
    ("2026-09-09", "ISPC", "NASDAQ", 1.55),
    ("2026-09-10", "ISPC", "NASDAQ", 1.50),
    ("2026-09-11", "ISPC", "NASDAQ", 1.47),
    ("2026-09-09", "TPET", "AMEX", 1.81),
    ("2026-09-10", "TPET", "AMEX", 2.02),
    ("2026-09-11", "TPET", "AMEX", 1.88),
]

TOL = 0.005          # half a cent: a match is a match to the printed cent


def candidates(rows: pd.DataFrame) -> dict[str, float | None]:
    """Every defensible reading of "the close", from one symbol-day's minutes.

    `rows` is indexed by bar START in UTC, as the archive stores it.
    """
    if rows.empty:
        return {}
    local = rows.tz_convert(ET) if rows.index.tz is not None else rows
    t = local.index.time
    at_or_before = local[[x <= CLOSE_T for x in t]]
    strictly_before = local[[x < CLOSE_T for x in t]]
    at_close = local[[x == CLOSE_T for x in t]]
    return {
        # The bar STARTING at 15:59 -- the last one that closes at or before
        # 16:00 under a [start, start+1m) convention. This is the last
        # continuous print and EXCLUDES the closing cross.
        "last_bar_before_1600": (float(strictly_before["close"].iloc[-1])
                                 if not strictly_before.empty else None),
        # The bar STARTING at 16:00, which under the same convention is where
        # a 16:00:00.000 auction print lands.
        "bar_at_1600": (float(at_close["close"].iloc[0])
                        if not at_close.empty else None),
        # Whichever of those is later -- the reading that takes the auction
        # when it exists and falls back when it does not.
        "last_bar_at_or_before_1600": (float(at_or_before["close"].iloc[-1])
                                       if not at_or_before.empty else None),
    }


def score(got: list[dict]) -> dict[str, dict]:
    """Per-candidate hit rate, counting ONLY discriminating rows."""
    names = ["last_bar_before_1600", "bar_at_1600",
             "last_bar_at_or_before_1600"]
    out = {}
    for n in names:
        disc = [g for g in got if g["discriminating"]]
        hit = [g for g in disc
               if g["cand"].get(n) is not None
               and abs(g["cand"][n] - g["truth"]) <= TOL]
        miss = [g for g in disc if g not in hit]
        out[n] = {"hit": len(hit), "of": len(disc), "misses": miss}
    return out


def render(got: list[dict], sc: dict, missing: list[str],
           dataset: str = "XNAS.BASIC",
           daily_dataset: str = "XNAS.BASIC") -> list[str]:
    disc = [g for g in got if g["discriminating"]]
    L = ["WHICH PRINT IS THE REGULAR-SESSION CLOSE?", "",
         f"  minute bars from {dataset}; the close currently in use is "
         f"{daily_dataset} ohlcv-1d",
         f"  {len(got)} truth row(s) from TradingView, "
         f"{len(disc)} of them DISCRIMINATING",
         "  a row discriminates only when our ohlcv-1d close already",
         "  disagrees with the truth -- on a quiet after-hours day every",
         "  candidate matches and the row proves nothing", ""]
    if missing:
        L += ["  NOT TESTED (no minute bars in the archive for these):", ""]
        L += [f"    {m}" for m in missing]
        L += [""]

    if not disc:
        return L + [
            "NO DISCRIMINATING ROW", "",
            "  Every truth row agrees with our daily close already, so this",
            "  run cannot distinguish the candidates. That is NOT evidence",
            "  that the daily close is right -- it is evidence that these",
            "  particular names were quiet after hours. Pull a session where",
            "  a name ran post-close and re-run.", ""]

    L += ["PER ROW", "",
          f"  {'date':<12}{'symbol':<7}{'ours(1d)':>10}{'truth':>8}"
          f"{'bef 16:00':>11}{'at 16:00':>10}{'at-or-bef':>11}   "]
    for g in sorted(got, key=lambda g: (g["date"], g["symbol"])):
        c = g["cand"]
        def f(v):
            return acct(v, 10) if v is not None else f"{'-':>10}"
        mark = "" if g["discriminating"] else "   (not discriminating)"
        L.append(f"  {g['date']:<12}{g['symbol']:<7}{acct(g['daily'], 10)}"
                 f"{acct(g['truth'], 8)}{f(c.get('last_bar_before_1600'))[-11:]}"
                 f"{f(c.get('bar_at_1600'))}"
                 f"{f(c.get('last_bar_at_or_before_1600'))[-11:]}{mark}")

    L += ["", "SCORE, on discriminating rows only", ""]
    for n, s in sc.items():
        L.append(f"  {n:<30} {s['hit']}/{s['of']}")

    winners = [n for n, s in sc.items() if s["of"] and s["hit"] == s["of"]]
    L += ["", "VERDICT", ""]
    if len(winners) == 1:
        L += [f"  {winners[0]}", "",
              "  This construction reproduces every discriminating truth row.",
              "  It is safe to build `prior_close` from -- after the pull, and",
              "  after `screen_validate` is re-run, not before."]
    elif len(winners) > 1:
        L += [f"  AMBIGUOUS -- {len(winners)} candidates are perfect: "
              f"{', '.join(winners)}", "",
              "  They did not differ on any row tested. Do NOT pick one."]
        if set(winners) == {"bar_at_1600", "last_bar_at_or_before_1600"}:
            L += ["",
                  "  These two are IDENTICAL BY CONSTRUCTION whenever a 16:00",
                  "  bar exists -- the fallback only differs when the name did",
                  "  not print in the closing minute at all. Tying here says",
                  "  nothing about which is right; it says every name in the",
                  "  sample traded at the close.",
                  "",
                  "  To separate them, add a THIN name that did not print at",
                  "  16:00. To rule out the auction question instead, add a",
                  "  name whose closing cross moved the price away from the",
                  "  last continuous print."]
        else:
            L += ["",
                  "  Add a row where they disagree before choosing."]
    else:
        L += ["  NONE of the candidates reproduces the truth.", "",
              "  The extended-hours explanation may be right and the",
              "  construction wrong, or the explanation may be wrong. Either",
              "  way this does not authorise the 552-session pull.", ""]
        for n, s in sc.items():
            if s["misses"]:
                g = s["misses"][0]
                L.append(f"    {n}: first miss {g['symbol']} {g['date']} "
                         f"got {acct(g['cand'].get(n) or float('nan'), 1).strip()}"
                         f", truth {acct(g['truth'], 1).strip()}")

    L += ["", "WHAT THIS IS NOT", "",
          "  Not a repair. Nothing here rewrites prior_close, and --emit only",
          "  writes the closes for the sessions actually pulled.",
          "",
          "  Not a claim about any OTHER dataset. ACVA is NYSE and TPET is",
          "  AMEX, and an official close is set by the LISTING venue's closing",
          "  auction -- which a Nasdaq-only tape does not carry at all. So a",
          "  failure here may mean the construction is wrong OR that this",
          "  dataset cannot answer the question. Re-run with --dataset on a",
          "  consolidated feed before blaming the construction; if only the",
          "  Nasdaq-listed rows match, that IS the answer and the repair needs",
          "  a consolidated source.",
          "",
          "  Not out of sample. These eleven rows were read while chasing this",
          "  defect. A construction validated on them is validated on the",
          "  evidence that produced the hypothesis."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC",
                   help="the dataset the MINUTE bars come from. Worth varying: "
                        "XNAS.BASIC is Nasdaq-only, and an official close for "
                        "a NYSE- or AMEX-listed name is set by THAT venue's "
                        "closing auction, which this tape does not carry.")
    p.add_argument("--daily-dataset", default="XNAS.BASIC",
                   help="the dataset whose ohlcv-1d close is the one in USE -- "
                        "the source of the defect. Held fixed while --dataset "
                        "varies, because whether a row discriminates is a fact "
                        "about the close we currently divide by, not about the "
                        "candidate being tested.")
    p.add_argument("--window", default="15:55-16:05",
                   help="the ET window pulled by databento_universe --window")
    p.add_argument("--emit", action="store_true",
                   help="write var/state/regular_close.json for the sessions "
                        "present, using the winning construction")
    p.add_argument("--out", default=None,
                   help="default: var/reports/regular_close_<dataset>.txt, so "
                        "two datasets do not clobber each other")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import daily_frame, read_dbn

    archive = Path(a.archive) if a.archive else default_archive()
    d = archive / a.dataset / "ohlcv-1m"
    lo, hi = a.window.replace(":", "").split("-")
    slices = {p.name[:10]: p for p in sorted(d.glob(f"*_{lo}_{hi}.dbn.zst"))}
    if not slices:
        sys.exit(
            f"no {a.window} ET slices in {d}/.\n"
            "Pull them first:\n"
            f"  python -m common.databento_universe --schema ohlcv-1m "
            f"--window {a.window} --start 2026-09-08 --end 2026-09-12\n"
            "It prints the cost and does nothing without --confirm.")

    daily = daily_frame(archive, a.daily_dataset)
    dkey = {(r.date, r.symbol): float(r.close) for r in daily.itertuples()} \
        if not daily.empty else {}

    got, missing = [], []
    cache: dict[str, pd.DataFrame] = {}
    for day, sym, _exch, truth in TRUTH:
        p = slices.get(day)
        if p is None:
            missing.append(f"{day} {sym}: no {a.window} slice")
            continue
        if day not in cache:
            cache[day] = read_dbn(p)
        bars = cache[day]
        rows = bars[bars["symbol"] == sym] if not bars.empty else bars
        if rows.empty:
            missing.append(f"{day} {sym}: not on this tape in that window")
            continue
        dly = dkey.get((day, sym))
        if dly is None:
            missing.append(f"{day} {sym}: no daily bar to compare against")
            continue
        got.append({"date": day, "symbol": sym, "truth": truth, "daily": dly,
                    "cand": candidates(rows.sort_index(kind="mergesort")),
                    "discriminating": abs(dly - truth) > TOL})

    sc = score(got)
    out = a.out or ("var/reports/regular_close_"
                    f"{a.dataset.replace('.', '_')}.txt")
    emit("\n".join(render(got, sc, missing, a.dataset, a.daily_dataset)), out,
         header=f"common.regular_close  minutes={a.dataset} "
                f"daily={a.daily_dataset} window={a.window}")

    if a.emit:
        winners = [n for n, s in sc.items() if s["of"] and s["hit"] == s["of"]]
        if len(winners) != 1:
            print("  --emit refused: the verdict is not a single construction")
            return 1
        n = winners[0]
        out: dict[str, dict[str, float]] = {}
        for day, p in slices.items():
            bars = cache.get(day) or read_dbn(p)
            if bars.empty:
                continue
            for sym, g in bars.groupby("symbol"):
                v = candidates(g.sort_index(kind="mergesort")).get(n)
                if v is not None:
                    out.setdefault(day, {})[str(sym)] = v
        path = Path("var/state/regular_close.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"construction": n, "closes": out},
                                   indent=1))
        print(f"  wrote {path} using {n} "
              f"({sum(len(v) for v in out.values()):,} symbol-days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
