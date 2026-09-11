#!/usr/bin/env python3
"""The live screen, run forward through a session, over the whole archive.

    python -m common.screen_sim --limit 5          # time it first
    python -m common.screen_sim --out var/state/screen_pairs_pit.json

WHAT THIS FINISHES
------------------
`PROGRAM_INDEX` §7 item 1, open since 2026-09-08 and the item that gates every
other result here. `screener_simulation_scope.md` §6 lists six steps: the
pre-market pull (done -- 550 window slices at 04:00-09:30 ET, 2024-07-01 ->
2026-09-09) and `screen_at` (done, 2026-09-10) were the first four. **This is
steps 5 and 6**: re-screen on a cadence through the session, and emit the
universe that comes out.

The measurement it feeds is `scope` §5:

    stage-2 survivors (today's daily bar)   H0 +$4.72/trade
    stage-2 rejects                         H0 -$9.81/trade
    THE SIMULATED LIVE SCREEN                   <- this

Land near +$4.72 and the screen was doing the work. Land near -$9.81 and the
+$4.72 was the leak, and with it every P/L figure this project has produced.

THE FIELD THAT MAKES THIS HONEST: first_seen
---------------------------------------------
A symbol-day is not a universe entry. **A name that first clears the screen at
07:20 could not have been traded at 04:00**, and a pairs file that carries only
(symbol, date) re-introduces exactly the look-ahead this module exists to
remove -- the backtest would arm it from the open because it eventually
qualified.

So the output is (symbol, date, **first_seen**, first_rank, best_rank), and
`first_seen` is a hard floor on entry. The runner that consumes it must not
enter before it. That is the difference between simulating the screen and
simulating knowing which names the screen would pick.

THE CADENCE, AND WHY ONE MINUTE IS NOT A COMPROMISE
----------------------------------------------------
`tv_feed.DEFAULT_INTERVAL` is 10 seconds, because TradingView's columns update
continuously. **Ours cannot.** The archive is 1-minute bars, so the screened
columns change only when a bar closes, and screening twice inside one minute
returns the identical answer by construction. One minute is therefore the
finest resolution that carries information, not a concession to runtime.

Coarser is available (`--cadence`) and biases in a known direction: a name is
noticed no earlier than the first tick after it qualifies, so a coarse cadence
makes entries LATER and the result more conservative, never less.

THE FAST PATH, AND THE REFERENCE IT MUST REPRODUCE
---------------------------------------------------
Calling `screen_at` at each of 330 ticks re-groups a growing window every time:
O(ticks x rows) per session, and there are 550 sessions. This module instead
accumulates volume and last-close per symbol in ONE pass and screens the
accumulated frame.

That is an optimisation of the thing whose correctness the whole result rests
on, so it is not trusted: `reference_at()` calls `screen_at` on the raw bars,
`sample_agreement()` compares the two at sampled ticks, and a test asserts they
agree exactly -- the same rule `common/harness.py` was validated under against
`mc5.py` trade-for-trade. The fast path is also **not allowed to see a bar
before it closes**: `ts_event` is the interval START, so a bar is visible at t
only when `ts_event + 60s <= t`, which is `screen_at`'s own convention.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.screen_at import (CHANGE_EPS, ScreenConfig, session_open_utc)
from common.report_io import emit

ET = ZoneInfo("America/New_York")

# One minute. See the docstring -- finer than the bar interval cannot change
# the answer, so this is the information limit and not a runtime compromise.
DEFAULT_CADENCE_S = 60

# The window the archive slices carry, and the window the live feed runs in.
SCREEN_START = "04:00"
SCREEN_END = "09:30"


def prior_closes(daily: pd.DataFrame) -> pd.DataFrame:
    """symbol, date -> the PREVIOUS session's close.

    `tv_screener`'s `premarket_change` is measured against the previous REGULAR
    close, which is what a daily bar's close is. A per-symbol shift, so a name's
    first day in the archive has no prior close and is dropped downstream rather
    than being handed a 0% change.
    """
    d = daily[["symbol", "date", "close"]].copy().sort_values(["symbol", "date"])
    d["prior_close"] = d.groupby("symbol")["close"].shift(1)
    return d[d["prior_close"].notna() & (d["prior_close"] > 0)]


def accumulate(bars: pd.DataFrame, cfg: ScreenConfig) -> pd.DataFrame:
    """Per (symbol, bar) running volume and last close, in one pass.

    The frame returned carries `visible_at` -- the moment the bar has CLOSED and
    may legitimately be read. Screening at t is then a selection on
    `visible_at <= t` rather than a re-aggregation, which is what makes 330
    ticks affordable.
    """
    if bars.empty:
        return bars.assign(visible_at=pd.Series(dtype="datetime64[ns, UTC]"),
                           cum_volume=pd.Series(dtype=float))
    b = bars[["symbol", "close", "volume"]].copy()
    b = b.sort_index(kind="mergesort")
    b["visible_at"] = b.index + timedelta(seconds=cfg.bar_seconds)
    b["cum_volume"] = b.groupby("symbol")["volume"].cumsum()
    return b


def screen_accumulated(acc: pd.DataFrame, prior_close: pd.Series,
                       t: pd.Timestamp, cfg: ScreenConfig) -> pd.DataFrame:
    """`screen_at`'s three clauses against the accumulated frame.

    Reproduces `screen_at` exactly, including the epsilon on the COMPUTED
    change, the inclusive price bounds, the tape-scaled volume threshold, the
    symbol tie-break and the top-N cap. A test pins the equivalence; this
    docstring is not the guarantee.
    """
    if acc.empty:
        return pd.DataFrame(columns=["symbol", "premarket_close",
                                     "premarket_volume", "premarket_change",
                                     "rank"])
    open_utc = session_open_utc(t, cfg)
    vis = acc[(acc["visible_at"] <= t) & (acc.index >= open_utc)]
    if vis.empty:
        return pd.DataFrame(columns=["symbol", "premarket_close",
                                     "premarket_volume", "premarket_change",
                                     "rank"])
    # LAST by time, not by row order: the archive is concatenated from chunks
    # and a positional `last()` would silently depend on how it was stitched.
    g = vis.groupby("symbol", sort=True)
    f = pd.DataFrame({
        "premarket_close": g["close"].last(),
        "premarket_volume": g["cum_volume"].last(),
    }).reset_index()
    f["prior_close"] = f["symbol"].map(prior_close)
    f = f[f["prior_close"].notna() & (f["prior_close"] > 0)]
    if f.empty:
        return f.assign(rank=pd.Series(dtype=int))
    f["premarket_change"] = (f["premarket_close"] / f["prior_close"] - 1.0) * 100.0
    lo, hi = cfg.price_range
    keep = ((f["premarket_change"] >= cfg.change_min - CHANGE_EPS)
            & (f["premarket_close"] >= lo) & (f["premarket_close"] <= hi)
            & (f["premarket_volume"] >= cfg.volume_min_on_tape))
    out = (f[keep]
           .sort_values(["premarket_change", "symbol"], ascending=[False, True])
           .head(cfg.max_symbols).reset_index(drop=True))
    out["rank"] = range(1, len(out) + 1)
    return out


def ticks(date_et, cfg: ScreenConfig, cadence_s: int) -> list[pd.Timestamp]:
    """Cadence moments through the pre-market window, in UTC.

    The first tick is one bar AFTER the open: at 04:00 itself nothing has
    closed, so a screen there is guaranteed empty and would only add a row of
    zeros to every report.
    """
    start = pd.Timestamp(datetime.combine(date_et, cfg.session_open, tzinfo=ET)
                         ).tz_convert("UTC")
    end_h, end_m = (int(x) for x in SCREEN_END.split(":"))
    end = pd.Timestamp(datetime.combine(
        date_et, datetime.min.time().replace(hour=end_h, minute=end_m),
        tzinfo=ET)).tz_convert("UTC")
    out, t = [], start + timedelta(seconds=cfg.bar_seconds)
    while t <= end:
        out.append(t)
        t = t + timedelta(seconds=cadence_s)
    return out


def _utc_ns(idx: pd.DatetimeIndex):
    """A tz-aware index as int64 nanoseconds since the epoch.

    The unit is FORCED rather than inherited. `DatetimeIndex.asi8` hands back
    the index's own resolution, and the Databento archive indexes in
    microseconds while `pd.Timestamp.value` is always nanoseconds -- mixing the
    two is a silent factor of 1000. See the note in `sweep`.
    """
    return (idx.tz_convert("UTC").tz_localize(None)
            .to_numpy(dtype="datetime64[ns]").astype("int64"))


def sweep(bars: pd.DataFrame, prior_close: pd.Series, date_et,
          cfg: ScreenConfig, cadence_s: int):
    """Yield (tick, selection) forward through the session, touching each bar ONCE.

    `screen_accumulated` re-groups a growing window at every tick: O(ticks x
    rows), which measured 3.3s on an 86k-row session and projected to half an
    hour over the archive. The screened columns are cumulative, so a forward
    sweep that carries last-close and running volume per symbol computes the
    same thing in one pass.

    State lives in NUMPY ARRAYS indexed by symbol code rather than in a dict of
    Series, because the cost was never the arithmetic -- it was rebuilding a
    DataFrame 330 times a session.

    `pd.factorize(sort=True)` makes the codes alphabetical, so the symbol
    tie-break that `screen_at` spells as a secondary sort key is just the code
    here. That equivalence is not obvious and is exactly the kind of thing that
    silently reorders a top-40 cut, so `sample_agreement` checks this function
    against `screen_at` rather than the docstring asserting it.
    """
    import numpy as np

    cols = ["symbol", "premarket_close", "premarket_volume",
            "premarket_change", "rank"]
    empty = pd.DataFrame(columns=cols)
    tick_list = ticks(date_et, cfg, cadence_s)
    if bars.empty:
        for t in tick_list:
            yield t, empty
        return

    open_utc = session_open_utc(tick_list[0], cfg)
    b = bars[bars.index >= open_utc]
    if b.empty:
        for t in tick_list:
            yield t, empty
        return

    codes, uniques = pd.factorize(b["symbol"], sort=True)
    n = len(uniques)
    prior = pd.Series(uniques).map(prior_close).to_numpy(dtype=float)
    # A name with no prior regular close has no change to compute; NaN here
    # fails every comparison below, which is the drop, silently but correctly.
    # INTEGER NANOSECONDS, BOTH SIDES, AND THE UNIT FORCED.
    #
    # `.asi8` returns the index's own unit, and the archive's index is
    # datetime64[**us**] -- while `Timestamp.value` is always nanoseconds. The
    # first version of this compared one against the other: a 1000x mismatch
    # that made every bar of the session visible at 04:01, so the simulation
    # read the whole morning at the open. It produced a plausible-looking
    # universe rather than an error, and only the agreement check against
    # `screen_at` found it.
    #
    # So the conversion is explicit: to UTC, drop the tz (already UTC, so
    # nothing is assumed), then force datetime64[ns].
    visible_ns = (_utc_ns(b.index + timedelta(seconds=cfg.bar_seconds)))
    order = np.argsort(visible_ns, kind="mergesort")
    vis_sorted = visible_ns[order]
    code_sorted = codes[order]
    close_sorted = b["close"].to_numpy(dtype=float)[order]
    vol_sorted = b["volume"].to_numpy(dtype=float)[order]

    last_close = np.full(n, np.nan)
    cum_vol = np.zeros(n)
    lo, hi = cfg.price_range
    vmin = cfg.volume_min_on_tape
    i, total = 0, len(vis_sorted)

    for t in tick_list:
        tv = _utc_ns(pd.DatetimeIndex([t]))[0]
        while i < total and vis_sorted[i] <= tv:
            c = code_sorted[i]
            last_close[c] = close_sorted[i]
            cum_vol[c] += vol_sorted[i]
            i += 1
        with np.errstate(invalid="ignore"):
            change = (last_close / prior - 1.0) * 100.0
            keep = ((change >= cfg.change_min - CHANGE_EPS)
                    & (last_close >= lo) & (last_close <= hi)
                    & (cum_vol >= vmin))
        idx = np.flatnonzero(keep)
        if idx.size == 0:
            yield t, empty
            continue
        # lexsort's LAST key is primary: change descending, then code ascending
        # -- and codes are alphabetical, which is screen_at's symbol tie-break.
        idx = idx[np.lexsort((idx, -change[idx]))][:cfg.max_symbols]
        yield t, pd.DataFrame({
            "symbol": uniques[idx],
            "premarket_close": last_close[idx],
            "premarket_volume": cum_vol[idx],
            "premarket_change": change[idx],
            "rank": range(1, len(idx) + 1),
        })


def session_universe(bars: pd.DataFrame, prior_close: pd.Series, date_et,
                     cfg: ScreenConfig = ScreenConfig(),
                     cadence_s: int = DEFAULT_CADENCE_S) -> pd.DataFrame:
    """One session's point-in-time universe.

    Returns one row per symbol that EVER cleared the screen, carrying the tick
    it first did (`first_seen`), its rank then, its best rank, and how many
    ticks it held a place. `first_seen` is the entry floor -- see the module
    docstring.
    """
    first: dict[str, dict] = {}
    for t, sel in sweep(bars, prior_close, date_et, cfg, cadence_s):
        for sym, rank in zip(sel["symbol"], sel["rank"]):
            rec = first.get(sym)
            if rec is None:
                first[sym] = {"symbol": sym, "first_seen": t,
                              "first_rank": int(rank), "best_rank": int(rank),
                              "ticks_on": 1}
            else:
                rec["best_rank"] = min(rec["best_rank"], int(rank))
                rec["ticks_on"] += 1
    if not first:
        return pd.DataFrame(columns=["symbol", "first_seen", "first_rank",
                                     "best_rank", "ticks_on"])
    return (pd.DataFrame(list(first.values()))
            .sort_values(["first_seen", "first_rank"])
            .reset_index(drop=True))


# --- the reference, and the agreement check that licenses the fast path -----

def reference_at(bars: pd.DataFrame, prior_close: pd.Series, t, cfg):
    """`screen_at` itself, on the raw bars. The thing the fast path must equal."""
    from common.screen_at import screen_at
    return screen_at(bars, prior_close, t, cfg)


def sample_agreement(bars: pd.DataFrame, prior_close: pd.Series, date_et,
                     cfg: ScreenConfig = ScreenConfig(),
                     every: int = 30, cadence_s: int = DEFAULT_CADENCE_S):
    """(ticks compared, ticks that disagreed, first disagreement).

    The fast path is an optimisation of the one computation this whole result
    rests on, so it is checked against `screen_at` rather than argued about --
    the rule `common/harness.py` was validated under against `mc5.py`.
    """
    checked = bad = 0
    first_bad = None
    for i, (t, a) in enumerate(sweep(bars, prior_close, date_et, cfg,
                                     cadence_s)):
        if i % every:
            continue
        checked += 1
        b = reference_at(bars, prior_close, t, cfg)
        same = (list(a["symbol"]) == list(b["symbol"])
                and list(a.get("rank", [])) == list(b.get("rank", [])))
        if not same:
            bad += 1
            if first_bad is None:
                first_bad = (t, list(a["symbol"])[:8], list(b["symbol"])[:8])
    return checked, bad, first_bad


# --- the archive walk --------------------------------------------------------

def window_slices(archive: Path, dataset: str) -> list[Path]:
    """The 04:00-09:30 pre-market pulls, in date order.

    Named `<date>_0400_0930.dbn.zst` by `databento_universe --window`. The
    full-day dailies sit in the same directory and are NOT these; matching on
    the suffix rather than on a date glob is what keeps them apart.
    """
    d = archive / dataset / "ohlcv-1m"
    return sorted(d.glob("*_0400_0930.dbn.zst"))


def date_of(path: Path) -> str:
    return path.name[:10]


def render(rows, sessions, cfg, cadence_s, agree, elapsed, no_prior) -> list[str]:
    per = [len(r["universe"]) for r in rows]
    per_sorted = sorted(per)
    total = sum(per)
    L = ["THE LIVE SCREEN, SIMULATED FORWARD", "",
         f"  {sessions} sessions, cadence {cadence_s}s, "
         f"{SCREEN_START}-{SCREEN_END} ET",
         f"  clauses imported from tv_screener: change >= {cfg.change_min:.0f}%, "
         f"price in [{cfg.price_range[0]:.2f}, {cfg.price_range[1]:.2f}], "
         f"volume >= {cfg.volume_min:,}",
         f"  volume threshold scaled to our tape at capture "
         f"{cfg.capture:.3f}: {cfg.volume_min_on_tape:,}",
         f"  top {cfg.max_symbols} by pre-market change, ties by symbol",
         f"  elapsed {elapsed:.1f}s", "",
         "THE UNIVERSE", "",
         f"  symbol-days                 {total:,}",
         f"  per session   mean          {total / sessions if sessions else 0:.1f}",
         f"                median        {per_sorted[len(per_sorted) // 2] if per_sorted else 0}",
         f"                p90           {per_sorted[int(0.9 * len(per_sorted))] if per_sorted else 0}",
         f"                max           {max(per) if per else 0}",
         f"  sessions with none          {sum(1 for n in per if n == 0)}",
         f"  names dropped, no prior close   {no_prior:,}", ""]

    seen = [r for row in rows for r in row["universe"]]
    if seen:
        et = [pd.Timestamp(r["first_seen"]).tz_convert(ET) for r in seen]
        hours = pd.Series([t.hour for t in et]).value_counts().sort_index()
        L += ["WHEN A NAME FIRST CLEARS THE SCREEN", "",
              "  This is the entry floor. A name first seen at 07:20 could not",
              "  have been traded at 04:00, and a universe file without this",
              "  column re-introduces the look-ahead this exercise removes.", ""]
        for h, n in hours.items():
            L.append(f"    {h:02d}:00   {n:>6}   {100.0 * n / len(seen):>5.1f}%  "
                     + "#" * int(40.0 * n / max(hours)))
        L.append("")

    checked, bad, first_bad = agree
    L += ["THE FAST PATH AGAINST `screen_at`", "",
          f"  ticks compared   {checked}",
          f"  disagreements    {bad}", ""]
    if bad:
        L += ["  THE FAST PATH DOES NOT REPRODUCE THE REFERENCE. Every number",
              "  above is void -- this module accumulates volume in one pass as",
              "  an optimisation of `screen_at`, and an optimisation that",
              "  disagrees with what it optimises is not an optimisation.",
              f"  First: {first_bad}", ""]
    else:
        L += ["  Exact, at every sampled tick. The accumulated path is",
              "  `screen_at` with the grouping done once.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not TradingView's data. It reproduces their COLUMNS from one",
          "  Databento dataset at a measured 55.2% capture, so even a perfect",
          "  reimplementation ranks a slightly different list. It answers",
          "  'is the +$4.72 a look-ahead artefact' and not 'would this exact",
          "  watchlist have appeared on Ben's screen that morning'.",
          "",
          "  Not a result. It is a UNIVERSE. The measurement is H0 and MCL run",
          "  on it, against the +$4.72 / -$9.81 brackets.",
          "",
          "  Not float-filtered or RVOL-filtered. Neither is in the shipped",
          "  screen's FILTERS -- `screen.py`'s stage2 applies an RVOL clause the",
          "  live screen does not have, which is one of the drifts this",
          "  replaces."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--daily-dataset", default="XNAS.BASIC",
                   help="where the prior REGULAR closes come from")
    p.add_argument("--cadence", type=int, default=DEFAULT_CADENCE_S)
    p.add_argument("--capture", type=float, default=None,
                   help="override the tape capture ratio; the default is the "
                        "measured p50 and the sensitivity is p10/p90")
    p.add_argument("--limit", type=int, default=None,
                   help="first N sessions only -- TIME IT before committing "
                        "to the whole archive")
    p.add_argument("--out", default="var/state/screen_pairs_pit.json")
    p.add_argument("--report", default="var/reports/screen_sim.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import daily_frame, read_dbn

    archive = Path(a.archive) if a.archive else default_archive()
    cfg = ScreenConfig()
    if a.capture is not None:
        cfg = replace(cfg, capture=a.capture)

    slices = window_slices(archive, a.dataset)
    if not slices:
        sys.exit(
            f"no pre-market window slices under {archive}/{a.dataset}/ohlcv-1m.\n"
            "  They are named <date>_0400_0930.dbn.zst and are produced by:\n"
            "    python -m common.databento_universe --schema ohlcv-1m "
            "--window 04:00-09:30 --confirm")
    if a.limit:
        slices = slices[:a.limit]

    daily = daily_frame(archive, a.daily_dataset)
    if daily.empty:
        sys.exit(f"no daily bars under {archive}/{a.daily_dataset} -- the "
                 "prior REGULAR close is what premarket_change measures "
                 "against and there is no substitute for it")
    pc = prior_closes(daily)
    by_date = {d: g.set_index("symbol")["prior_close"]
               for d, g in pc.groupby("date")}

    t0 = time.time()
    rows, no_prior, agree = [], 0, (0, 0, None)
    for i, path in enumerate(slices):
        date_str = date_of(path)
        prior = by_date.get(date_str)
        if prior is None:
            no_prior += 1
            continue
        try:
            bars = read_dbn(path)
        except Exception as e:                              # noqa: BLE001
            print(f"  {date_str}: unreadable ({type(e).__name__}: {e})")
            continue
        if bars.empty:
            continue
        d_et = datetime.strptime(date_str, "%Y-%m-%d").date()
        uni = session_universe(bars, prior, d_et, cfg, a.cadence)
        rows.append({"date": date_str,
                     "universe": [
                         {"symbol": r.symbol,
                          "first_seen": r.first_seen.isoformat(),
                          "first_rank": int(r.first_rank),
                          "best_rank": int(r.best_rank),
                          "ticks_on": int(r.ticks_on)}
                         for r in uni.itertuples()]})
        # The agreement check runs on the FIRST readable session only: it is
        # O(ticks x rows) by construction, which is the cost the fast path
        # exists to avoid. One session is enough to catch a divergence in the
        # clauses; it is not a sampling estimate and is not presented as one.
        if agree[0] == 0:
            agree = sample_agreement(bars, prior, d_et, cfg,
                                     cadence_s=a.cadence)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(slices)}  {date_str}  "
                  f"{sum(len(r['universe']) for r in rows):,} symbol-days")

    pairs = [{"symbol": u["symbol"], "date": r["date"],
              "first_seen": u["first_seen"], "first_rank": u["first_rank"],
              "best_rank": u["best_rank"], "ticks_on": u["ticks_on"]}
             for r in rows for u in r["universe"]]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pairs, indent=1))
    print(f"\nwrote {len(pairs):,} symbol-days to {out}")

    emit("\n".join(render(rows, len(rows), cfg, a.cadence, agree,
                          time.time() - t0, no_prior)),
         a.report,
         header=f"common.screen_sim  archive={archive}/{a.dataset}  "
                f"cadence={a.cadence}s  capture={cfg.capture:.3f}"
                + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
