#!/usr/bin/env python3
r"""The live screen, run forward through the WHOLE day -- 04:00 to 20:00 ET.

    python -m common.screen_day --dataset XNAS.ITCH \
        --capture-ladder var/reports/itch_capture.json \
        --out var/state/screen_pairs_pit_itch_day.json

Registered in docs/research/REGISTERED_mc5_full_day.md (§2, amendment A) before
this file existed. `screen_sim` stops at 09:30 because every column the live
screen reads is a `premarket_*` one. This module keeps the same three clauses
running through regular hours and after-hours, against the reference each block
actually has:

    block   window        change is measured against        volume accumulates from
    PRE     04:00-09:30   the prior REGULAR close           04:00
    RTH     09:30-16:00   the prior REGULAR close           09:30
    POST    16:00-20:00   TODAY's regular close             16:00

The PRE block is `screen_sim` unchanged, and that is asserted rather than
claimed: `pre_matches_screen_sim` runs both over the same session and requires
tick-for-tick equality, the same way `screen_sim.sample_agreement` licenses its
own fast path against `screen_at`.

WHAT A NAME'S `first_seen` MEANS HERE
-------------------------------------
The same thing it means in `screen_sim`: the first cadence tick at which the
name cleared the screen, and a hard floor on entry. A name that first clears at
14:05 could not have been traded at 04:05. Ben's choice, recorded in the
registration: ONE top-40 list all day, and **a name is never dropped** once it
has appeared -- so the universe file's `first_seen` is all the trader needs and
the row also carries which block surfaced it.

THE VOLUME THRESHOLD AFTER 09:30 IS AN ASSUMPTION, NOT A MEASUREMENT
--------------------------------------------------------------------
`itch_capture` measured XNAS.ITCH's share of consolidated volume per ET
half-hour from 04:30 to 09:30 only. `ScreenConfig.capture_at` carries the last
step forward, so RTH and POST screen at the 09:30 capture. That is a choice,
it is almost certainly too low for regular hours (Nasdaq's share of a name's
volume rises when the SIP is fully live), and too low means the threshold is
too easy and the RTH universe is too BIG -- the conservative direction for a
study asking whether trading later helps. It is printed in the report beside
every count, and `itch_capture` is where a measurement would come from.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.report_io import emit
from common.screen_at import CHANGE_EPS, ScreenConfig
from common.screen_sim import (DEFAULT_CADENCE_S, date_of, load_repaired, prior_closes,
                               relaxation_banner, source_mix)

ET = ZoneInfo("America/New_York")

# (name, start, end, which reference close, the slice suffix it is pulled in)
BLOCKS = (("PRE", dtime(4, 0), dtime(9, 30), "prior", "0400_0930"),
          ("RTH", dtime(9, 30), dtime(16, 0), "prior", "0930_1600"),
          ("POST", dtime(16, 0), dtime(20, 0), "today", "1600_2000"))

DECIDING_OUT = "var/state/screen_pairs_pit.json"
DEFAULT_OUT = "var/state/screen_pairs_pit_itch_day.json"


# --- the archive -----------------------------------------------------------------

def day_slices(archive: Path, dataset: str) -> dict[str, dict[str, Path]]:
    """date -> {block: path}, only for dates that have ALL THREE windows.

    A date with the pre-market pull and no regular-hours one would silently
    produce a PRE-only universe that looks like a full day's. Incomplete dates
    are returned separately by `incomplete_dates` and named in the report.
    """
    d = archive / dataset / "ohlcv-1m"
    got: dict[str, dict[str, Path]] = {}
    for _name, _s, _e, _ref, suffix in BLOCKS:
        for p in sorted(d.glob(f"*_{suffix}.dbn.zst")):
            got.setdefault(date_of(p), {})[suffix] = p
    return got


def complete(got: dict[str, dict[str, Path]]) -> tuple[list[str], list[str]]:
    want = {suffix for *_r, suffix in BLOCKS}
    full = sorted(k for k, v in got.items() if set(v) >= want)
    partial = sorted(k for k, v in got.items() if set(v) < want)
    return full, partial


# --- the sweep, per block --------------------------------------------------------

def block_bounds(date_et, start: dtime, end: dtime) -> tuple[pd.Timestamp, pd.Timestamp]:
    a = pd.Timestamp(datetime.combine(date_et, start, tzinfo=ET)).tz_convert("UTC")
    b = pd.Timestamp(datetime.combine(date_et, end, tzinfo=ET)).tz_convert("UTC")
    return a, b


def block_ticks(date_et, start: dtime, end: dtime, cfg: ScreenConfig,
                cadence_s: int) -> list[pd.Timestamp]:
    """Cadence moments inside one block, in UTC.

    The first tick is one bar AFTER the block opens -- at the open itself
    nothing has closed inside the block, exactly as `screen_sim.ticks` argues
    for 04:00. The last tick is the block's end, which is the next block's
    start: a name that only clears on the 15:59 bar is seen at 16:00, in RTH,
    and RTH's reference is what it was screened against.
    """
    a, b = block_bounds(date_et, start, end)
    out, t = [], a + timedelta(seconds=cfg.bar_seconds)
    while t <= b:
        out.append(t)
        t = t + timedelta(seconds=cadence_s)
    return out


def _utc_ns(idx: pd.DatetimeIndex):
    """See screen_sim._utc_ns: the unit is forced, because the archive indexes
    in MICROseconds and Timestamp.value is nanoseconds."""
    return (idx.tz_convert("UTC").tz_localize(None)
            .to_numpy(dtype="datetime64[ns]").astype("int64"))


COLS = ["symbol", "premarket_close", "premarket_volume", "premarket_change", "rank"]


def sweep_block(bars: pd.DataFrame, ref_close: pd.Series, date_et, cfg: ScreenConfig,
                cadence_s: int, start: dtime, end: dtime):
    """Yield (tick, selection) through ONE block. `screen_sim.sweep`'s algorithm
    with the window and the reference close made parameters.

    Volume accumulates from the block's own start, so a name that traded 400k
    shares in the morning starts RTH at zero -- which is what the live columns
    do: `premarket_volume` is cumulative since 04:00 and the regular-session
    `volume` column is cumulative since 09:30.
    """
    empty = pd.DataFrame(columns=COLS)
    tick_list = block_ticks(date_et, start, end, cfg, cadence_s)
    if bars.empty or not tick_list:
        for t in tick_list:
            yield t, empty
        return
    lo_utc, hi_utc = block_bounds(date_et, start, end)
    b = bars[(bars.index >= lo_utc) & (bars.index < hi_utc)]
    if b.empty:
        for t in tick_list:
            yield t, empty
        return

    codes, uniques = pd.factorize(b["symbol"], sort=True)
    n = len(uniques)
    ref = pd.Series(uniques).map(ref_close).to_numpy(dtype=float)
    visible_ns = _utc_ns(b.index + timedelta(seconds=cfg.bar_seconds))
    order = np.argsort(visible_ns, kind="mergesort")
    vis_sorted = visible_ns[order]
    code_sorted = codes[order]
    close_sorted = b["close"].to_numpy(dtype=float)[order]
    vol_sorted = b["volume"].to_numpy(dtype=float)[order]

    last_close = np.full(n, np.nan)
    cum_vol = np.zeros(n)
    lo, hi = cfg.price_range
    i, total = 0, len(vis_sorted)
    from common.screen import is_test_symbol
    is_test = np.array([is_test_symbol(s) for s in uniques])

    for t in tick_list:
        vmin = cfg.volume_min_at(t)
        tv = _utc_ns(pd.DatetimeIndex([t]))[0]
        while i < total and vis_sorted[i] <= tv:
            c = code_sorted[i]
            last_close[c] = close_sorted[i]
            cum_vol[c] += vol_sorted[i]
            i += 1
        with np.errstate(invalid="ignore"):
            change = (last_close / ref - 1.0) * 100.0
            keep = ((change >= cfg.change_min - CHANGE_EPS)
                    & (last_close >= lo) & (last_close <= hi)
                    & (cum_vol >= vmin) & ~is_test)
        idx = np.flatnonzero(keep)
        if idx.size == 0:
            yield t, empty
            continue
        idx = idx[np.lexsort((idx, -change[idx]))][:cfg.max_symbols]
        yield t, pd.DataFrame({
            "symbol": uniques[idx],
            "premarket_close": last_close[idx],
            "premarket_volume": cum_vol[idx],
            "premarket_change": change[idx],
            "rank": range(1, len(idx) + 1),
        })


def session_universe_day(bars_by_block: dict[str, pd.DataFrame], prior: pd.Series,
                         today: pd.Series, date_et, cfg: ScreenConfig = ScreenConfig(),
                         cadence_s: int = DEFAULT_CADENCE_S) -> pd.DataFrame:
    """One session's point-in-time universe over the whole day.

    One row per symbol that EVER cleared the screen, carrying the tick it first
    did (`first_seen`), the BLOCK it first did it in, its rank then, its best
    rank across the day, and how many ticks it held a place. Ben's rule: a name
    is never dropped, so `ticks_on` counts places held and nothing is removed.
    """
    first: dict[str, dict] = {}
    for name, start, end, ref_kind, suffix in BLOCKS:
        ref = prior if ref_kind == "prior" else today
        for t, sel in sweep_block(bars_by_block.get(suffix, pd.DataFrame()), ref,
                                  date_et, cfg, cadence_s, start, end):
            for sym, rank in zip(sel["symbol"], sel["rank"]):
                rec = first.get(sym)
                if rec is None:
                    first[sym] = {"symbol": sym, "first_seen": t, "block": name,
                                  "first_rank": int(rank), "best_rank": int(rank),
                                  "ticks_on": 1}
                else:
                    rec["best_rank"] = min(rec["best_rank"], int(rank))
                    rec["ticks_on"] += 1
    if not first:
        return pd.DataFrame(columns=["symbol", "first_seen", "block", "first_rank",
                                     "best_rank", "ticks_on"])
    return (pd.DataFrame(list(first.values()))
            .sort_values(["first_seen", "first_rank"])
            .reset_index(drop=True))


# --- the control: PRE must be screen_sim ----------------------------------------

def pre_matches_screen_sim(bars_pre: pd.DataFrame, prior: pd.Series, date_et,
                           cfg: ScreenConfig = ScreenConfig(),
                           cadence_s: int = DEFAULT_CADENCE_S):
    """(ticks compared, ticks that disagreed, first disagreement).

    THIS IS THE CONTROL FOR THE WHOLE MODULE. `sweep_block` is a second
    implementation of a computation every point-in-time figure rests on, so it
    is not argued about: over the PRE block it must equal `screen_sim.sweep`
    tick for tick, symbol for symbol, rank for rank.
    """
    from common.screen_sim import sweep as pre_sweep

    mine = list(sweep_block(bars_pre, prior, date_et, cfg, cadence_s,
                            BLOCKS[0][1], BLOCKS[0][2]))
    theirs = list(pre_sweep(bars_pre, prior, date_et, cfg, cadence_s))
    checked = bad = 0
    first_bad = None
    for (ta, a), (tb, b) in zip(mine, theirs):
        checked += 1
        same = (ta == tb and list(a["symbol"]) == list(b["symbol"])
                and list(a.get("rank", [])) == list(b.get("rank", [])))
        if not same:
            bad += 1
            if first_bad is None:
                first_bad = (ta, list(a["symbol"])[:8], list(b["symbol"])[:8])
    if len(mine) != len(theirs):
        bad += 1
        first_bad = first_bad or ("tick count", len(mine), len(theirs))
    return checked, bad, first_bad


# --- report ----------------------------------------------------------------------

def block_counts(rows) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        for u in r["universe"]:
            out[u["block"]] = out.get(u["block"], 0) + 1
    return out


def render(rows, cfg, cadence_s, agree, elapsed, partial, no_prior, no_today,
           mix, rep, ladders, dataset) -> list[str]:
    per = sorted(len(r["universe"]) for r in rows)
    counts = block_counts(rows)
    total = sum(counts.values())
    L = ["THE LIVE SCREEN, SIMULATED FORWARD THROUGH THE WHOLE DAY", "",
         f"  registered  docs/research/REGISTERED_mc5_full_day.md",
         f"  {len(rows)} sessions, cadence {cadence_s}s, 04:00-20:00 ET, {dataset}",
         f"  clauses imported from tv_screener: change >= {cfg.change_min:.0f}%, "
         f"price in [{cfg.price_range[0]:.2f}, {cfg.price_range[1]:.2f}], "
         f"volume >= {cfg.volume_min:,}",
         f"  top {cfg.max_symbols} by change at each tick; a name is never dropped",
         f"  elapsed {elapsed:.1f}s", "",
         "THE BLOCKS", "",
         "  block  window        change measured against   volume from",
         "  PRE    04:00-09:30   the prior regular close    04:00",
         "  RTH    09:30-16:00   the prior regular close    09:30",
         "  POST   16:00-20:00   TODAY's regular close      16:00", ""]
    if ladders:
        L += ["  THE VOLUME THRESHOLD AFTER 09:30 IS CARRIED, NOT MEASURED.",
              "  itch_capture measured 04:30-09:30 only; RTH and POST screen at the",
              "  09:30 step. Too low a capture means too EASY a threshold and too big",
              "  a universe after 09:30 -- conservative for this study, and stated",
              "  rather than hidden.", ""]
    L += ["THE UNIVERSE", "",
          f"  {total:,} symbol-days over {len(rows)} sessions"]
    for name, *_ in BLOCKS:
        c = counts.get(name, 0)
        L.append(f"    first seen in {name:<5} {c:>7,}  "
                 f"{100 * c / total if total else 0:5.1f}%")
    if per:
        L += [f"  per session  min {per[0]}  p50 {per[len(per) // 2]}  max {per[-1]}",
              f"  sessions with none: {sum(1 for x in per if x == 0)}"]
    L += [""]
    checked, bad, first_bad = agree
    L += ["THE CONTROL: THE PRE BLOCK IS screen_sim", "",
          f"  {checked} ticks compared, {bad} disagreement(s)"]
    if bad:
        L += [f"  FIRST DISAGREEMENT: {first_bad}",
              "  *** THE PRE BLOCK DOES NOT REPRODUCE screen_sim. NOTHING HERE IS USABLE. ***"]
    else:
        L += ["  the PRE block reproduces screen_sim tick for tick on the session checked"]
    L += [""]
    if partial:
        L += [f"  {len(partial)} date(s) dropped for missing a window slice:",
              "    " + ", ".join(partial[:12]) + (" ..." if len(partial) > 12 else ""), ""]
    if no_prior:
        L += [f"  {len(no_prior)} date(s) had no prior-close row at all", ""]
    if no_today:
        L += [f"  {len(no_today)} date(s) had no repaired 16:00 close, so POST "
              f"screened nothing there:", "    " + ", ".join(no_today[:12])
              + (" ..." if len(no_today) > 12 else ""), ""]
    if mix:
        L += ["THE PRIOR CLOSE THIS RAN AGAINST", "",
              "  " + "  ".join(f"{k}={v:,}" for k, v in sorted(mix.items()))]
        L += relaxation_banner(rep) + [""]
    return L


# --- cli --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.ITCH")
    p.add_argument("--daily-dataset", default="XNAS.BASIC",
                   help="where the daily bars for the prior close come from")
    p.add_argument("--cadence", type=int, default=DEFAULT_CADENCE_S)
    p.add_argument("--capture-ladder", default=None, metavar="ITCH_CAPTURE.json")
    p.add_argument("--ladder-cut", default="2026-03-30")
    p.add_argument("--limit", type=int, default=None,
                   help="first N sessions only -- TIME IT first; a full-day "
                        "session is ~25x the bars of a pre-market one")
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--report", default="var/reports/screen_day.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import daily_frame, read_dbn

    if Path(a.out.replace("\\", "/")) == Path(DECIDING_OUT):
        sys.exit(f"--out {DECIDING_OUT}: that file is the pre-market universe every "
                 "published point-in-time figure was decided on. Name another.")
    archive = Path(a.archive) if a.archive else default_archive()
    cfg = ScreenConfig()
    ladders = None
    if a.capture_ladder:
        from common.screen_at import ladder_from_json
        ladders = {reg: ladder_from_json(a.capture_ladder, reg)
                   for reg in ("before", "after")}

    got = day_slices(archive, a.dataset)
    full, partial = complete(got)
    if not full:
        sys.exit(f"no complete days under {archive}/{a.dataset}/ohlcv-1m -- a day "
                 "needs all three of " + ", ".join(s for *_r, s in BLOCKS))
    if a.limit:
        full = full[:a.limit]

    daily = daily_frame(archive, a.daily_dataset)
    if daily.empty:
        sys.exit(f"no daily bars under {archive}/{a.daily_dataset}")
    rep = load_repaired()
    if rep is None:
        sys.exit("var/state/regular_close.json is not there; POST needs today's "
                 "regular close and PRE/RTH need the repaired prior one")
    pc = prior_closes(daily, rep)
    mix = source_mix(pc)
    prior_by_date = {d: g.set_index("symbol")["prior_close"] for d, g in pc.groupby("date")}
    today_by_date = {d: g.set_index("symbol")["close"] for d, g in rep.groupby("date")}
    src_by_date = {d: g.set_index("symbol")["prior_source"] for d, g in pc.groupby("date")}

    t0 = time.time()
    rows, no_prior, no_today, agree = [], [], [], (0, 0, None)
    for i, date_str in enumerate(full):
        prior = prior_by_date.get(date_str)
        if prior is None:
            no_prior.append(date_str)
            continue
        today = today_by_date.get(date_str)
        if today is None:
            no_today.append(date_str)
            today = pd.Series(dtype=float)
        if ladders is not None:
            cfg = replace(cfg, ladder=ladders["before" if date_str < a.ladder_cut
                                              else "after"])
        bars: dict[str, pd.DataFrame] = {}
        try:
            for *_r, suffix in BLOCKS:
                bars[suffix] = read_dbn(got[date_str][suffix])
        except Exception as e:                              # noqa: BLE001
            print(f"  {date_str}: unreadable ({type(e).__name__}: {e})", flush=True)
            continue
        d_et = datetime.strptime(date_str, "%Y-%m-%d").date()
        uni = session_universe_day(bars, prior, today, d_et, cfg, a.cadence)
        rows.append({"date": date_str,
                     "universe": [{"symbol": r.symbol,
                                   "first_seen": r.first_seen.isoformat(),
                                   "block": r.block,
                                   "first_rank": int(r.first_rank),
                                   "best_rank": int(r.best_rank),
                                   "ticks_on": int(r.ticks_on)}
                                  for r in uni.itertuples()]})
        if agree[0] == 0:
            agree = pre_matches_screen_sim(bars[BLOCKS[0][4]], prior, d_et, cfg,
                                           a.cadence)
            if agree[1]:
                sys.exit(f"the PRE block does not reproduce screen_sim on {date_str}: "
                         f"{agree[2]}")
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(full)}  {date_str}  "
                  f"{sum(len(r['universe']) for r in rows):,} symbol-days", flush=True)

    pairs = [{"symbol": u["symbol"], "date": r["date"], "first_seen": u["first_seen"],
              "block": u["block"], "first_rank": u["first_rank"],
              "best_rank": u["best_rank"], "ticks_on": u["ticks_on"],
              "prior_source": str(src_by_date.get(r["date"], {}).get(u["symbol"], "unknown"))}
             for r in rows for u in r["universe"]]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pairs, indent=1), encoding="utf-8")
    print(f"\nwrote {len(pairs):,} symbol-days to {out}")
    emit("\n".join(render(rows, cfg, a.cadence, agree, time.time() - t0, partial,
                          no_prior, no_today, mix, rep, ladders, a.dataset)),
         a.report,
         header=f"common.screen_day  archive={archive}/{a.dataset}  cadence={a.cadence}s"
                + (f"  capture_ladder={a.capture_ladder} cut={a.ladder_cut}" if ladders else "")
                + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
