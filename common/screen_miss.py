#!/usr/bin/env python3
"""Why did the simulated screen miss the names the live screen surfaced?

    python -m common.screen_miss

THE QUESTION THIS ANSWERS INSTEAD OF THE ONE I NEARLY ASKED
------------------------------------------------------------
`screen_validate` found the simulation surfacing **22 of 38** live names, and
the misses are one-directional -- 16 missed against 2 sim-only -- so the
simulation is under-producing rather than mis-ordering. The obvious next step
was to measure the tape's capture ratio on the missed names and infer a cause
from it.

Inference is unnecessary. The screen is three clauses and a cap, and every input
is on disk, so each missed name can simply be asked **which clause it failed and
by how much**. That distinguishes the candidate causes directly rather than
through a proxy:

    NOT ON THIS TAPE   the name never prints on XNAS.BASIC. No threshold can
                       fix this one, and it is the cause a capture measurement
                       would have been least likely to surface.
    NO PRIOR CLOSE     no previous regular close, so premarket_change is
                       undefined and the name is dropped before any clause.
    VOLUME             it cleared change and price but never reached the
                       tape-scaled volume floor -- the capture hypothesis, and
                       the report prints the shortfall so the size of the
                       mis-scaling is visible rather than assumed.
    CHANGE             it never reached +20% on this tape's prints.
    PRICE              outside the band at the moments it was otherwise
                       eligible.
    RANK ONLY          it passed ALL THREE clauses at some tick and still did
                       not appear -- so it was pushed out by the top-40 cap.
                       This is not a miss of the same kind, and lumping it in
                       with the others would overstate the clause failures.

THE CLAUSES MUST HOLD AT THE SAME TICK
---------------------------------------
A name can reach +25% at 04:10 and the volume floor at 08:40 and never once
satisfy both together. Reporting per-clause maxima alone would call that name
eligible and blame the cap. So `worst_clause` is decided on the SIMULTANEOUS
test, tick by tick, exactly as `screen_accumulated` applies it -- and the
per-clause bests are printed beside it as context, never as the verdict.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.report_fmt import acct
from common.report_io import emit
from common.screen_sim import (SCREEN_END, SCREEN_START, ScreenConfig,
                               accumulate, date_of, load_repaired, prior_closes,
                               source_mix, ticks,
                               window_slices)
from common.screen_validate import collect, load_sim

ET = ZoneInfo("America/New_York")

NOT_ON_TAPE = "NOT ON THIS TAPE"
NO_PRIOR = "NO PRIOR CLOSE"
RANK_ONLY = "RANK ONLY"


def diagnose(acc: pd.DataFrame, symbol: str, prior: float | None,
             date_et, cfg: ScreenConfig, cadence_s: int) -> dict:
    """Which clause kept one name out, and by how much.

    `acc` is the whole session's accumulated frame; the symbol is selected here
    so the caller reads each slice once for many names.
    """
    rows = acc[acc["symbol"] == symbol]
    if rows.empty:
        return {"symbol": symbol, "why": NOT_ON_TAPE}
    if prior is None or not (prior > 0):
        return {"symbol": symbol, "why": NO_PRIOR}

    lo, hi = cfg.price_range
    need = cfg.volume_min_on_tape
    best = {"change": float("-inf"), "volume": 0.0, "close_at_best": float("nan")}
    ever_all = False
    # The simultaneous test, tick by tick. `visible_at <= t` is the same
    # blindness rule screen_accumulated applies: a bar counts only once closed.
    for t in ticks(date_et, cfg, cadence_s):
        seen = rows[rows["visible_at"] <= t]
        if seen.empty:
            continue
        last = float(seen["close"].iloc[-1])
        vol = float(seen["cum_volume"].iloc[-1])
        change = (last / prior - 1.0) * 100.0
        if change > best["change"]:
            best.update(change=change, close_at_best=last)
        best["volume"] = max(best["volume"], vol)
        if (change >= cfg.change_min and lo <= last <= hi and vol >= need):
            ever_all = True
            break

    if ever_all:
        return {"symbol": symbol, "why": RANK_ONLY, **best}

    # Nothing simultaneous. Name the clause that never came closest to holding,
    # using the best each managed on its own -- context, not the verdict.
    fails = []
    if best["change"] < cfg.change_min:
        fails.append("CHANGE")
    if best["volume"] < need:
        fails.append("VOLUME")
    if not (lo <= best["close_at_best"] <= hi):
        fails.append("PRICE")
    if not fails:
        # Every clause was met at some point, never together.
        fails = ["NEVER SIMULTANEOUS"]
    return {"symbol": symbol, "why": "+".join(fails), **best}


def render(rows: list[dict], cfg: ScreenConfig, n_sessions: int,
           elapsed: float) -> list[str]:
    L = ["WHY THE SIMULATED SCREEN MISSED THEM", "",
         f"  {len(rows)} live names the simulation never surfaced, over "
         f"{n_sessions} session(s)",
         f"  clauses: change >= {cfg.change_min:.0f}%, price in "
         f"[{cfg.price_range[0]:.2f}, {cfg.price_range[1]:.2f}], "
         f"volume >= {cfg.volume_min_on_tape:,} on this tape",
         f"  (that floor is {cfg.volume_min:,} consolidated, scaled by a "
         f"measured capture of {cfg.capture:.3f})",
         f"  elapsed {elapsed:.1f}s", ""]

    if not rows:
        return L + ["Nothing to diagnose -- the simulation surfaced every live "
                    "name.", ""]

    L += ["PER NAME", "",
          f"  {'date':<12}{'symbol':<8}{'best change':>13}{'best volume':>14}"
          f"{'close':>9}   why"]
    for r in sorted(rows, key=lambda r: (r["date"], r["symbol"])):
        # A name with no bars at all carries no bests. Missing and
        # negative-infinity both render as a dash rather than as a figure --
        # printing 0 or -inf here would put a number in a column that has no
        # measurement behind it.
        c, v = r.get("change"), r.get("volume")
        px_v = r.get("close_at_best")
        ch = (acct(c, 12) + "%" if c is not None and c != float("-inf")
              else f"{'-':>13}")
        vol = f"{v:>14,.0f}" if v is not None else f"{'-':>14}"
        px = (acct(px_v, 9) if px_v is not None and px_v == px_v
              else f"{'-':>9}")
        L.append(f"  {r['date']:<12}{r['symbol']:<8}{ch}{vol}{px}   {r['why']}")

    counts = Counter(r["why"] for r in rows)
    L += ["", "WHY, COUNTED", ""]
    for why, n in counts.most_common():
        L.append(f"  {n:>3}   {why}")

    L += ["", "WHAT EACH ONE MEANS FOR THE 58%", ""]
    if counts.get(NOT_ON_TAPE):
        L += [f"  {counts[NOT_ON_TAPE]} name(s) NEVER PRINT on this tape. No",
              "  threshold change reaches these -- the dataset does not carry",
              "  them, and a capture measurement would not have found it.", ""]
    vol_only = sum(n for w, n in counts.items() if w == "VOLUME")
    if vol_only:
        short = [r for r in rows if r["why"] == "VOLUME"]
        med = sorted(r["volume"] / cfg.volume_min_on_tape for r in short)
        L += [f"  {vol_only} name(s) failed ONLY the volume floor. Median best",
              f"  volume was {med[len(med) // 2]:.0%} of the scaled threshold.",
              "",
              "  This is the capture hypothesis, and the ratio above is its",
              "  size. If these names reach the floor at a capture materially",
              "  below the population's, the threshold is mis-scaled for",
              "  exactly the universe this screen is for -- and",
              "  `screen_at.capture_sensitivity()` already re-runs the screen",
              "  at p10/p50/p90 to price that.", ""]
    if counts.get("CHANGE") or counts.get("CHANGE+VOLUME"):
        L += ["  Names failing CHANGE never reached the threshold on this",
              "  tape's prints. A thin tape can miss the print that takes a",
              "  name over the line, which is a different defect from a",
              "  mis-scaled volume floor and is not fixed by re-scaling.", ""]
    if counts.get(RANK_ONLY):
        L += [f"  {counts[RANK_ONLY]} name(s) passed ALL THREE clauses and were",
              "  still absent -- pushed out by the top-40 cap. These are not",
              "  clause failures and must not be counted as evidence about the",
              "  threshold.", ""]
    if counts.get("NEVER SIMULTANEOUS"):
        L += [f"  {counts['NEVER SIMULTANEOUS']} name(s) met every clause at",
              "  some point and never all at once. Per-clause maxima would",
              "  have called these eligible and blamed the cap.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not a measure of the live screen's correctness. TradingView's",
          "  premarket_volume is its own consolidation; these names were on",
          "  the real watchlist by definition.",
          "",
          "  Not a fix. It says which clause to attack and how far short each",
          "  name fell. Re-scaling the threshold is a change to the SIMULATED",
          "  screen and must be registered and re-validated, not tuned until",
          "  the agreement number improves."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--daily-dataset", default="XNAS.BASIC")
    p.add_argument("--watchlists", default="var/archive")
    p.add_argument("--pairs", default="var/state/screen_pairs_pit.json")
    p.add_argument("--cadence", type=int, default=60)
    p.add_argument("--prior-close", default="repaired",
                   choices=["daily", "repaired", "require"],
                   help="must match whatever screen_sim was run with. Two "
                        "modules disagreeing about which close they divide by "
                        "is the same defect one level up.")
    p.add_argument("--out", default="var/reports/screen_miss.txt")
    return p


def main(argv=None) -> int:
    import time
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import daily_frame, read_dbn

    archive = Path(a.archive) if a.archive else default_archive()
    cfg = ScreenConfig()

    sim = load_sim(Path(a.pairs))
    rows, _skipped = collect(Path(a.watchlists), sim)
    if not rows:
        sys.exit("no comparable session -- run `python -m common.screen_validate` "
                 "first and read why.")
    want: dict[str, list[str]] = {r["date"]: r["missed"] for r in rows
                                  if r["missed"]}
    if not want:
        emit("\n".join(render([], cfg, len(rows), 0.0)), a.out,
             header="common.screen_miss")
        return 0

    daily = daily_frame(archive, a.daily_dataset)
    rep = None if a.prior_close == "daily" else load_repaired()
    if a.prior_close != "daily" and rep is None:
        sys.exit("var/state/regular_close.json is not there. Emit it first "
                 "with common.regular_close --emit, or pass --prior-close "
                 "daily to use the DEFECTIVE close on purpose.")
    pc = prior_closes(daily, rep, require_repaired=a.prior_close == "require")
    print(f"  prior close: mode={a.prior_close}  " +
          "  ".join(f"{k}={v:,}" for k, v in sorted(source_mix(pc).items())),
          flush=True)
    by_date = {d: g.set_index("symbol")["prior_close"]
               for d, g in pc.groupby("date")}
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}

    t0 = time.time()
    out: list[dict] = []
    for day, names in sorted(want.items()):
        path = slices.get(day)
        if path is None:
            for s in names:
                out.append({"date": day, "symbol": s, "why": NOT_ON_TAPE})
            continue
        bars = read_dbn(path)
        acc = accumulate(bars, cfg)
        prior = by_date.get(day)
        d_et = datetime.strptime(day, "%Y-%m-%d").date()
        for s in names:
            p = None if prior is None else prior.get(s)
            rec = diagnose(acc, s, p, d_et, cfg, a.cadence)
            rec["date"] = day
            out.append(rec)

    emit("\n".join(render(out, cfg, len(rows), time.time() - t0)), a.out,
         header=f"common.screen_miss  dataset={a.dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
