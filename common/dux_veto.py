#!/usr/bin/env python3
r"""W03-0012 -- the three Dux long-side veto tags, on their own registration.

    python -m common.dux_veto --jobs 8                       # Tag G only
    python -m common.dux_veto --jobs 8 --tags G,B,R           # all three tags
    python -m common.dux_veto --jobs 8 --tags B,R \
        --daily-dataset XNAS.ITCH                              # override the daily-bar dataset

Registered in docs/research/REGISTERED_dux_veto.md before this file existed.
Ben's decision (W11-0032 option A, recorded on board item W03-0012): tag
MCL/MC5 longs against Steven Dux's three short setups, veto style (checked
last, refuse-and-log, same model as the drift guard / spread gate), no new
data, no shorting.

ALL THREE TAGS RUN AGAINST THE REAL ARCHIVE
--------------------------------------------
TAG G ("crowded gap-up") reads only the entry session's own XNAS.ITCH
pre-market bars (already owned, full point-in-time universe) and
`var/state/regular_close.json`'s previous-close (already owned, whole tape).

TAG B ("overhead dollar block") and TAG R ("day after first red day") both
need a DAILY OHLCV history, up to 252 trading sessions deep, per symbol.
Per Ben's decision on W03-0012 subitem 3 ("let's go with databento",
REGISTERED_dux_veto.md sec 10): that history comes from
`common.dbn_io.daily_frame` (already-owned Databento `ohlcv-1d` bars,
default dataset XNAS.ITCH, overridable with `--daily-dataset`), which are
NOT split-adjusted as printed. `common.split_guard` detects and rescales
splits with a price+volume dual-signal heuristic (19/19 fixture tests
passing) before `tag_dollar_block`/`tag_post_first_red_day` ever see the
bars -- see `_trailing_window` below and sec 10 for the exact rule and its
named residual risk. A symbol-day with too little daily history reads
TAG_B/R = False (sec 2's own documented limitation, not a pull failure);
the real run reports actual coverage rather than assuming it either way.
"""
from __future__ import annotations

import argparse
import bisect
import sys
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import gate_study as G
from common.running_up import session_slice
from common.entry_shares import MEASURED_FRICTION, QTY
from common.report_io import emit
from common.split_guard import DailyBar, adjust_for_splits

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
DATASET = "XNAS.ITCH"
REGISTERED = "docs/research/REGISTERED_dux_veto.md"

# --- Tag G: crowded gap-up -- Ben's numbers, verbatim, §2 -------------------------
TAG_G_GAP_PCT = 100.0            # gap_pct >= this
TAG_G_PREMKT_VOL = 50_000_000.0  # premkt_vol > this (strict)

# --- Tag B: overhead dollar block -- §2 -------------------------------------------
# Also the daily-history lookback depth used for Tag R's query (see
# `_trailing_window`'s own docstring) -- a practical compute bound, not a
# change to either tag's registered rule.
TAG_B_LOOKBACK = 252             # trading sessions before the entry date
TAG_B_SPIKE_RANGE_PCT = 100.0    # (high - low) / low >= this to count as a "spike" day
TAG_B_DOLLAR_BLOCK = 140_000_000.0   # dollar_block >= this
TAG_B_BAND_PCT = 5.0             # entry running-high within +/- this % of trapped_level
TAG_B_SENSITIVITY = (130_000_000.0, 140_000_000.0, 150_000_000.0)  # reported, never scored

# --- Tag R: day after first red day -- §2 -----------------------------------------
TAG_R_MIN_RUN = 3                # a run of >= 3 green days ...
TAG_R_MIN_RUN_RANGE_PCT = 300.0  # ... needs >= this cumulative range ...
TAG_R_SHORT_RUN = 2              # ... OR a run of exactly 2 green days ...
TAG_R_SHORT_RUN_RANGE_PCT = 1000.0  # ... needs >= this cumulative range
TAG_R_GIVEBACK_SKIP_PCT = 50.0   # skip (no tag) if giveback > this

STRATS = (("MCL", "mcl"), ("MC5", "mc5"))


def _f(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return x


# =============================== TAG G ============================================

def tag_crowded_gap(df: pd.DataFrame, ts, prev_close: float | None) -> tuple[bool, float, float]:
    """Ben's "crowded gap-up", §2. (tagged, gap_pct, premkt_vol).

    `gap_pct` is the RUNNING HIGH since 04:00 through and including the entry
    bar against the previous regular-session close -- not the entry bar's own
    close -- because a name whose morning pop has already stalled by the time
    MCL/MC5 signals is still "crowded" in Dux's sense; using the entry bar's
    own price would silently exclude the fade cases his setup targets (see
    the registration §2, Tag G).

    `premkt_vol` is the session's OWN cumulative XNAS.ITCH volume from 04:00
    through the entry bar's close -- `session_slice` already restricts to
    that session and excludes the warm-up days `build_frame` prepends.

    NaN-safe: with no history or a missing/non-positive previous close,
    returns (False, nan, nan) rather than raising -- a symbol-day this tag
    cannot evaluate is untagged, never silently "tagged".
    """
    hist = session_slice(df, pd.Timestamp(ts))
    if hist.empty or prev_close is None or not (prev_close == prev_close) or prev_close <= 0:
        return False, float("nan"), float("nan")
    running_high = float(hist["high"].max())
    premkt_vol = float(hist["volume"].sum())
    gap_pct = (running_high - prev_close) / prev_close * 100.0
    tagged = (gap_pct >= TAG_G_GAP_PCT) and (premkt_vol > TAG_G_PREMKT_VOL)
    return bool(tagged), gap_pct, premkt_vol


def _session_running_high(df: pd.DataFrame, ts) -> float | None:
    """The running high since 04:00 through and including bar `ts` -- the
    same "running high" both Tag G and Tag B key off (§2: "entry-bar running
    high-since-04:00"). None when there is no pre-market history yet at
    `ts`. Deliberately NOT sharing code with `tag_crowded_gap` (a small,
    G1-gated, already-unit-tested function this change leaves untouched);
    this is the run_day-side equivalent for Tag B's per-bar check."""
    hist = session_slice(df, pd.Timestamp(ts))
    if hist.empty:
        return None
    return float(hist["high"].max())


# =============================== TAG B ============================================

def _spike_day(daily: list[DailyBar]) -> DailyBar | None:
    """The session with the largest (close x volume) among "spike" days --
    (high - low) / low >= TAG_B_SPIKE_RANGE_PCT/100 -- or None if there is
    none in the window. `daily` is assumed already restricted to the
    lookback window and to sessions strictly before the entry date; this
    function does no date filtering of its own."""
    spikes = [b for b in daily if b.low > 0
              and (b.high - b.low) / b.low * 100.0 >= TAG_B_SPIKE_RANGE_PCT]
    if not spikes:
        return None
    return max(spikes, key=lambda b: b.close * b.volume)


def _spike_metrics(daily: list[DailyBar]) -> tuple[float, float] | None:
    """(dollar_block, trapped_level) for `daily`'s own spike day, or None if
    there is none in the window. This is the DAY-INDEPENDENT half of Tag B
    -- it does not vary bar to bar within the entry session, so `run_day`
    computes it ONCE per symbol-day rather than re-scanning the whole daily
    window on every bar; `tag_dollar_block` below still computes it fresh
    each call, for its own fixture-test simplicity, via the same helper."""
    spike = _spike_day(daily)
    if spike is None:
        return None
    return spike.close * spike.volume, spike.close


def _dollar_block_tagged(metrics: tuple[float, float] | None, entry_running_high: float,
                         threshold: float = TAG_B_DOLLAR_BLOCK,
                         band_pct: float = TAG_B_BAND_PCT) -> bool:
    """The threshold+band half of Tag B, given `metrics` from
    `_spike_metrics` (or None, meaning no spike day at all). Factored out of
    `tag_dollar_block` so `run_day` can cheaply re-evaluate it at every bar
    of a session (running high changes bar to bar) and at every sensitivity
    threshold (§4 item 7) without re-finding the spike day each time."""
    if metrics is None:
        return False
    dollar_block, trapped_level = metrics
    if trapped_level <= 0:
        return False
    within_band = abs(entry_running_high - trapped_level) / trapped_level * 100.0 <= band_pct
    return bool(dollar_block >= threshold and within_band)


def tag_dollar_block(daily: list[DailyBar], entry_running_high: float,
                     threshold: float = TAG_B_DOLLAR_BLOCK,
                     band_pct: float = TAG_B_BAND_PCT) -> tuple[bool, float | None, float | None]:
    """Ben's "overhead dollar block", §2. (tagged, dollar_block, trapped_level).

    `daily` must already be the trailing TAG_B_LOOKBACK sessions (or the
    symbol's full history if shorter) strictly before the entry date --
    `_trailing_window` below is responsible for that slicing (and for the
    split-guard adjustment) so this function stays pure arithmetic and
    stays trivially fixture-testable.

    No spike day in the window -> (False, None, None), no further
    computation (§2: "IF no such session exists in the lookback window:
    TAG_B = False"). Unchanged behaviour from before this module's Tag B/R
    wiring -- only refactored internally (via `_spike_metrics` /
    `_dollar_block_tagged`) to let `run_day` reuse its two halves
    separately; every G1 fixture test still exercises this exact function.
    """
    metrics = _spike_metrics(daily)
    if metrics is None:
        return False, None, None
    dollar_block, trapped_level = metrics
    tagged = _dollar_block_tagged(metrics, entry_running_high, threshold, band_pct)
    return tagged, dollar_block, trapped_level


def dollar_block_sensitivity(daily: list[DailyBar], entry_running_high: float) -> dict[float, bool]:
    """§7: $130M / $140M (registered) / $150M, reported and never scored."""
    return {t: tag_dollar_block(daily, entry_running_high, threshold=t)[0]
            for t in TAG_B_SENSITIVITY}


# =============================== TAG R ============================================

def _is_run_day(daily: list[DailyBar], j: int) -> bool:
    """Day j qualifies for a green run on its OWN: green against j-1 AND
    j's dollar volume strictly higher than j-1's (§2, both clauses apply to
    every day in the run individually, not just the run as a whole)."""
    if j < 1:
        return False
    a, b = daily[j], daily[j - 1]
    return (a.close > b.close) and (a.close * a.volume > b.close * b.volume)


def _green_run_ending_at(daily: list[DailyBar], idx: int) -> tuple[int, int] | None:
    """The maximal run of consecutive days satisfying `_is_run_day` that
    ends at `daily[idx]` inclusive. Returns (start_idx, end_idx), or None if
    `daily[idx]` does not itself qualify (no run at all). `pre_run_close` is
    then `daily[start_idx - 1].close` -- the session immediately before the
    run, which need not itself be green."""
    if not _is_run_day(daily, idx):
        return None
    start = idx
    while _is_run_day(daily, start - 1):
        start -= 1
    return start, idx


def tag_post_first_red_day(daily: list[DailyBar], entry_date: str) -> tuple[bool, dict]:
    """Ben's "day after first red day", §2. `daily` must be sorted ascending
    by date and cover at least the run plus the one session immediately
    before it (the "pre-run close"); `entry_date` is the date MCL/MC5
    signals on. Returns (tagged, detail) -- detail always has the keys used
    below, None where not applicable, so a caller can report why a
    borderline case did or did not fire without re-deriving it.

    Reads the LAST row of `daily` as the candidate "first red day" -- i.e.
    `daily` must end on the session immediately before `entry_date`, and
    this function does not itself check that `entry_date` is the very next
    TRADING session after it (it has no trading calendar to check against);
    `entry_date` is accepted and echoed into `detail` purely so a caller can
    log/assert contiguity itself, never consulted in the arithmetic below --
    a caller that hands in a `daily` slice with a gap (a halt, a mis-stepped
    date) gets a wrong answer silently, same as any other pure function
    given the wrong input; `_trailing_window` is responsible for that
    slicing (it ends exactly on the session before `entry_date`, by
    construction).
    """
    empty = {"entry_date": str(entry_date), "run_start": None, "run_end": None,
             "run_len": None, "run_range_pct": None, "giveback_pct": None,
             "pre_run_close": None, "peak_close": None, "first_red_close": None,
             "first_red_date": None}
    if len(daily) < 2:
        return False, empty
    red = daily[-1]
    prev = daily[-2]
    if not (red.close < prev.close):
        return False, empty  # the day before entry was not itself red
    run = _green_run_ending_at(daily, len(daily) - 2)
    if run is None:
        return False, empty
    start, end = run
    run_len = end - start + 1
    pre_run_close = daily[start - 1].close
    peak_close = daily[end].close
    if pre_run_close <= 0:
        return False, empty
    run_range_pct = (peak_close - pre_run_close) / pre_run_close * 100.0
    qualifies = ((run_len >= TAG_R_MIN_RUN and run_range_pct >= TAG_R_MIN_RUN_RANGE_PCT)
                or (run_len == TAG_R_SHORT_RUN and run_range_pct >= TAG_R_SHORT_RUN_RANGE_PCT))
    detail = {"entry_date": str(entry_date), "run_start": daily[start].date,
              "run_end": daily[end].date, "run_len": run_len,
              "run_range_pct": run_range_pct, "pre_run_close": pre_run_close,
              "peak_close": peak_close, "first_red_close": red.close,
              "first_red_date": red.date, "giveback_pct": None}
    if not qualifies:
        return False, detail
    span = peak_close - pre_run_close
    giveback_pct = ((peak_close - red.low) / span * 100.0) if span > 0 else float("inf")
    detail["giveback_pct"] = giveback_pct
    if giveback_pct > TAG_R_GIVEBACK_SKIP_PCT:
        return False, detail  # §2: "SKIP (no tag) if giveback > 50%"
    return True, detail


# =============================== daily-bar loading (Tag B/R) ======================

def load_daily_bars(archive: Path, dataset: str,
                    symbols: set[str] | None = None) -> dict[str, list[DailyBar]]:
    """Every ohlcv-1d bar in `archive/dataset`, as {symbol: [DailyBar...]}
    each sorted ascending by date -- RAW, not yet split-guard-adjusted
    (adjustment happens per query window in `_trailing_window`: sec 10
    "the window is exactly what the caller queried", never the whole tape
    at once). `symbols`, when given, restricts the result to the PIT
    universe this study actually tags rather than the whole archive,
    keeping what gets pickled into every worker task bounded -- same
    "pass a big read-only dict into every task" pattern this module
    already uses for `prevclose`."""
    from common.dbn_io import daily_frame
    df = daily_frame(archive, dataset)
    if df.empty:
        return {}
    if symbols is not None:
        df = df[df["symbol"].isin(symbols)]
    out: dict[str, list[DailyBar]] = {}
    for sym, grp in df.groupby("symbol", sort=False):
        grp = grp.sort_values("date")
        out[sym] = [DailyBar(r.date, close=float(r.close), volume=float(r.volume),
                             high=float(r.high), low=float(r.low))
                    for r in grp.itertuples(index=False)]
    return out


def _trailing_window(bars: list[DailyBar], entry_date: str,
                     lookback: int = TAG_B_LOOKBACK) -> list[DailyBar]:
    """The trailing up-to-`lookback` RAW sessions in `bars` (sorted
    ascending) strictly before `entry_date`, split-guard-adjusted to the
    scale of the session immediately before entry (the window's own last
    bar). Never reaches past entry (so a LATER split never contaminates an
    earlier entry's read) and never reaches past `lookback` sessions back
    (§2's own bound for Tag B; reused here for Tag R's daily-history query
    too as a practical compute bound, not a change to Tag R's rule -- a
    qualifying run must sit immediately adjacent to the first-red-day,
    which must itself be the session right before entry, so 252 sessions
    is generous headroom for any realistic run length).

    `bars` dates are ISO strings (YYYY-MM-DD), which sort lexicographically
    the same as chronologically -- `bisect` works directly on them, no date
    parsing needed.

    Empty in, empty out -- an unavailable or too-short history reads as "no
    window", which both tag functions already treat as untagged (§2:
    "reads TAG_B/R = False... documented as a limitation")."""
    if not bars:
        return []
    dates = [b.date for b in bars]
    i = bisect.bisect_left(dates, entry_date)  # first index >= entry_date
    window = bars[max(0, i - lookback):i]
    return adjust_for_splits(window) if window else []


# =============================== the study runner =================================

def load_prev_closes(path: str = "var/state/regular_close.json") -> pd.DataFrame:
    from common.screen_sim import load_repaired
    rep = load_repaired(Path(path))
    if rep is None:
        raise SystemExit(f"{path} is not there. Emit it first:\n"
                          "  python -m common.regular_close --dataset XNAS.BASIC --emit")
    return rep


def prev_close_lookup(rep: pd.DataFrame, session_days: list[str]) -> dict[tuple[str, str], float]:
    """(symbol, day) -> the close on the PREVIOUS session in `session_days`
    (the archive's own trading calendar, so a market holiday is never
    mistaken for "no prior close"). A symbol with no print on that prior
    date has no entry and `tag_crowded_gap` reads it as untaggable (NaN),
    never as a false positive or negative."""
    by_date = {d: g.set_index("symbol")["close"] for d, g in rep.groupby("date")}
    days = sorted(session_days)
    prev_of = {d: days[i - 1] for i, d in enumerate(days) if i > 0}
    out: dict[tuple[str, str], float] = {}
    for day in days:
        pd_ = prev_of.get(day)
        if pd_ is None or pd_ not in by_date:
            continue
        for sym, close in by_date[pd_].items():
            out[(sym, day)] = float(close)
    return out


def books_and_pairs(tags: list[str]) -> tuple[tuple, tuple]:
    """BOOKS/PAIRED for exactly the requested `tags` (a non-empty ordered
    subset of "G", "B", "R"): each strategy's own untagged baseline once,
    plus one gated variant per requested tag. Entries are
    (name, engine_key, gate_tag) with gate_tag None for the baseline --
    `run_day` looks the per-bar/per-day gate mask up by that tag letter.
    §6's multiplicity rule (three tags = three separate families) is why
    this builds one paired (baseline, gated) tuple per tag rather than a
    single combined gate."""
    books = []
    paired = []
    for strat, eng in STRATS:
        books.append((strat, eng, None))
        for t in tags:
            name = f"{strat}-dux{t}"
            books.append((name, eng, t))
            paired.append((strat, name))
    return tuple(books), tuple(paired)


def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe, prevclose, tags, daily_by_symbol = args
    books_spec, paired_spec = books_and_pairs(tags)
    engines = {name: engine(name) for name in ("mcl", "mc5")}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)

    res = {
        "books": {name: [] for name, _, _ in books_spec},
        "symdays": 0, "errors": 0, "error_days": [],
        "tag_fired_symdays": {t: 0 for t in tags},
        "refused": {g: [] for _, g in paired_spec},
        "binding": {g: [0, 0, {}] for _, g in paired_spec},
        "coverage": {t: [0, 0] for t in tags if t in ("B", "R")},  # [have_history, checked]
        "b_sensitivity_symdays": {t: 0 for t in TAG_B_SENSITIVITY} if "B" in tags else {},
        "overlap": {},
    }

    for rec in universe:
        if not rec.get("first_seen"):
            continue
        s = rec["symbol"]
        df = frame[frame["symbol"] == s]
        if df.empty:
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        prevc = prevclose.get((s, day))

        try:
            idx = df.index
            gates: dict[str, pd.Series] = {}

            if "G" in tags:
                # One gate mask for the WHOLE session: the tag is evaluated
                # once per bar (the running high/volume both grow
                # monotonically through the session) -- same "checked last,
                # on a fresh read" model as the drift/spread guards, off
                # closed bars only.
                vals = np.ones(len(idx), dtype=bool)
                for i, ts in enumerate(idx):
                    tagged, _, _ = tag_crowded_gap(df, ts, prevc)
                    vals[i] = not tagged
                gates["G"] = pd.Series(vals, index=idx)
                if not vals.all():
                    res["tag_fired_symdays"]["G"] += 1

            if "B" in tags:
                window = _trailing_window(daily_by_symbol.get(s, []), day)
                res["coverage"]["B"][1] += 1
                if window:
                    res["coverage"]["B"][0] += 1
                metrics = _spike_metrics(window) if window else None
                vals = np.ones(len(idx), dtype=bool)
                sens_fired = {t: False for t in TAG_B_SENSITIVITY}
                for i, ts in enumerate(idx):
                    rh = _session_running_high(df, ts)
                    if rh is None:
                        continue
                    vals[i] = not _dollar_block_tagged(metrics, rh)
                    for t in TAG_B_SENSITIVITY:
                        if not sens_fired[t] and _dollar_block_tagged(metrics, rh, threshold=t):
                            sens_fired[t] = True
                gates["B"] = pd.Series(vals, index=idx)
                if not vals.all():
                    res["tag_fired_symdays"]["B"] += 1
                for t, fired in sens_fired.items():
                    if fired:
                        res["b_sensitivity_symdays"][t] += 1

            if "R" in tags:
                # Day-level tag, not bar-level: §2's rule depends only on
                # the prior sessions' closes, never on where in today's
                # session the entry bar falls, so the mask is constant
                # across the whole day.
                window = _trailing_window(daily_by_symbol.get(s, []), day)
                res["coverage"]["R"][1] += 1
                if len(window) >= 2:
                    res["coverage"]["R"][0] += 1
                tagged_r, _detail = tag_post_first_red_day(window, day) if window else (False, {})
                gates["R"] = pd.Series(np.full(len(idx), not tagged_r, dtype=bool), index=idx)
                if tagged_r:
                    res["tag_fired_symdays"]["R"] += 1

            got = {}
            for name, eng, gate_tag in books_spec:
                mod, extra = engines[eng]
                g = gates.get(gate_tag) if gate_tag else None
                got[name] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=floor, entry_gate=g,
                                                 **extra)
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{s} {day}: {type(e).__name__}: {e}")
            continue

        res["symdays"] += 1
        for name, trades in got.items():
            res["books"][name] += [G.trade_row(t, s, day, k)
                                   for k, t in enumerate(trades, 1)]

        for base_name, gname in paired_spec:
            gate_tag = gname.rsplit("-dux", 1)[1]
            gate = gates.get(gate_tag)
            b = res["binding"][gname]
            for t in got[base_name]:
                ts = pd.Timestamp(f"{day} {t.entry_time}", tz=ET) \
                    if isinstance(t.entry_time, str) else t.entry_time
                # "could" == the gate actually was False at this exact
                # entry bar (entry_gates.py's own convention: could ==
                # len(refused)) -- NOT every baseline trade regardless of
                # the gate (Tag G's own earlier reporting-only bug, fixed
                # before this wiring; see the module's git history).
                allowed = bool(gate.reindex([ts], method="ffill").fillna(True).iloc[0]) \
                    if gate is not None else True
                b[1] += 1
                if not allowed:
                    b[0] += 1
                    res["refused"][gname].append(G.trade_row(t, s, day, 0))

        # Overlap (§4 item 6): among this symbol-day's baseline trades, how
        # many entry bars were refused by more than one of the requested
        # tags at once -- a tag's own gate mask doesn't depend on which
        # strategy is asking, so this is computed once per baseline trade
        # rather than per (strategy, tag) pair.
        if len(tags) > 1 and gates:
            for base_strat, _ in STRATS:
                for t in got.get(base_strat, []):
                    ts = pd.Timestamp(f"{day} {t.entry_time}", tz=ET) \
                        if isinstance(t.entry_time, str) else t.entry_time
                    fired = [letter for letter, gate in gates.items()
                            if not bool(gate.reindex([ts], method="ffill").fillna(True).iloc[0])]
                    if len(fired) > 1:
                        key = "+".join(sorted(fired))
                        res["overlap"][key] = res["overlap"].get(key, 0) + 1

    return day, res, ""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--daily-dataset", default=DATASET,
                   help="Databento dataset ohlcv-1d daily bars are read from for tags B/R "
                        "(split-guard-adjusted per REGISTERED_dux_veto.md sec 10); "
                        "defaults to the same value as --dataset")
    p.add_argument("--regular-close", default="var/state/regular_close.json")
    p.add_argument("--tags", default="G",
                   help="comma-separated subset of G,B,R to run (default: G only)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/dux_veto.txt")
    p.add_argument("--csv", default="var/reports/dux_veto_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    tags = [t.strip().upper() for t in a.tags.split(",") if t.strip()]
    bad = [t for t in tags if t not in ("G", "B", "R")]
    if bad:
        sys.exit(f"--tags: unknown tag(s) {bad} -- must be a subset of G,B,R")
    if not tags:
        sys.exit("--tags: at least one of G,B,R is required")
    archive = Path(a.archive) if a.archive else default_archive()

    rep = load_prev_closes(a.regular_close)
    all_tasks, by_date = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    session_days = sorted(by_date)
    prevclose = prev_close_lookup(rep, session_days)

    daily_by_symbol: dict[str, list[DailyBar]] = {}
    if "B" in tags or "R" in tags:
        universe_symbols = {rec["symbol"] for recs in by_date.values() for rec in recs
                            if rec.get("first_seen")}
        print(f"loading daily bars: {a.daily_dataset} ohlcv-1d "
              f"({len(universe_symbols):,} symbols in the PIT universe)...", flush=True)
        daily_by_symbol = load_daily_bars(archive, a.daily_dataset, universe_symbols)
        have = sum(1 for sym in universe_symbols if daily_by_symbol.get(sym))
        print(f"  {have:,} of {len(universe_symbols):,} universe symbols have SOME daily "
              f"history in {a.daily_dataset} -- per-entry-date coverage (the trailing "
              f"{TAG_B_LOOKBACK}-session window) is reported below; a symbol can appear here "
              "and still be short of that window for an early entry date.", flush=True)

    tasks = [(p, d, u, prevclose, tags, daily_by_symbol) for p, d, u in all_tasks]
    jobs = G.jobs_from(a.jobs)

    got, elapsed = G.run_sessions(run_day, tasks, jobs, f"dux_veto (tags {','.join(tags)})")

    books_spec, paired_spec = books_and_pairs(tags)
    books = {name: [] for name, _, _ in books_spec}
    refused = {g: [] for _, g in paired_spec}
    binding = {g: [0, 0, {}] for _, g in paired_spec}
    symdays, errors, error_days = 0, 0, []
    tag_fired_symdays = {t: 0 for t in tags}
    coverage = {t: [0, 0] for t in tags if t in ("B", "R")}
    b_sensitivity_symdays = {t: 0 for t in TAG_B_SENSITIVITY} if "B" in tags else {}
    overlap: dict[str, int] = {}
    run_days = sorted(got)
    for day in run_days:
        r = got[day]
        for name in books:
            books[name] += r["books"][name]
        for name in refused:
            refused[name] += r["refused"][name]
            b, rb = binding[name], r["binding"][name]
            b[0] += rb[0]
            b[1] += rb[1]
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]
        for t in tags:
            tag_fired_symdays[t] += r["tag_fired_symdays"].get(t, 0)
        for t in coverage:
            have, total = r["coverage"].get(t, [0, 0])
            coverage[t][0] += have
            coverage[t][1] += total
        for t, n in r.get("b_sensitivity_symdays", {}).items():
            b_sensitivity_symdays[t] = b_sensitivity_symdays.get(t, 0) + n
        for k, n in r.get("overlap", {}).items():
            overlap[k] = overlap.get(k, 0) + n

    for gname in binding:
        gate_tag = gname.rsplit("-dux", 1)[1]
        binding[gname][2] = {"tag_fired_symdays": tag_fired_symdays[gate_tag]}

    preamble: list[str] = [""]
    if "G" in tags:
        preamble.append(
            f"Tag G: refuse a BUY when gap_pct >= {TAG_G_GAP_PCT:.1f}% (running high since "
            f"04:00 vs previous regular close) AND premkt_vol > {TAG_G_PREMKT_VOL:,.0f} shares.")
    if "B" in tags:
        preamble.append(
            f"Tag B: refuse a BUY when the trailing {TAG_B_LOOKBACK}-session split-guard-"
            f"adjusted {a.daily_dataset} daily bars show a >=100% range spike day whose "
            f"dollar_block (close x volume) >= ${TAG_B_DOLLAR_BLOCK:,.0f}, AND the entry bar's "
            f"running high since 04:00 is within +/-{TAG_B_BAND_PCT:.0f}% of that spike day's "
            "close (REGISTERED_dux_veto.md sec 10).")
    if "R" in tags:
        preamble.append(
            "Tag R: refuse a BUY on the session immediately after a qualifying green run's "
            f"first red day (run len >= {TAG_R_MIN_RUN:g} & cumulative range >= "
            f"{TAG_R_MIN_RUN_RANGE_PCT:.0f}%, or run len == {TAG_R_SHORT_RUN:g} & range >= "
            f"{TAG_R_SHORT_RUN_RANGE_PCT:.0f}%), skipped if giveback > "
            f"{TAG_R_GIVEBACK_SKIP_PCT:.0f}%; same split-guard-adjusted daily-bar source as "
            "Tag B.")
    for t in tags:
        fired_pct = 100.0 * tag_fired_symdays[t] / symdays if symdays else 0.0
        preamble.append(
            f"TAG {t} fired (was True on at least one bar, or the whole day for R) on "
            f"{tag_fired_symdays[t]:,} of {symdays:,} symbol-days ({fired_pct:.2f}%) -- "
            "independent of whether a strategy actually signalled there; the COULD-HAVE-BOUND "
            "and VERDICT sections below narrow that to entries the tag actually hit.")
    for t in coverage:
        have, total = coverage[t]
        cov_pct = 100.0 * have / total if total else 0.0
        preamble.append(
            f"TAG {t} daily-history coverage: {have:,} of {total:,} symbol-days ({cov_pct:.2f}%) "
            f"had a non-empty trailing daily window in {a.daily_dataset}; the rest read "
            f"TAG {t} = False for lack of history (sec 2's documented limitation, not by itself "
            "a pull failure -- price a --daily-dataset pull via common.databento_fetch if this "
            "coverage is too thin to trust).")
    if b_sensitivity_symdays:
        parts = "  ".join(f"${t / 1e6:,.0f}M: {n:,}" for t, n in sorted(b_sensitivity_symdays.items()))
        preamble.append(
            f"TAG B sensitivity (sec 4 item 7, reported and never scored) -- symbol-days where "
            f"Tag B would have fired on at least one bar, at each threshold: {parts}.")
    if overlap:
        parts = "  ".join(f"{k}: {n:,}" for k, n in sorted(overlap.items()))
        preamble.append(
            f"TAG overlap (sec 4 item 6) -- baseline trades whose entry bar was refused by more "
            f"than one requested tag at once: {parts}. Overlap against the existing drift guard "
            "/ spread gate is not computed here -- would need those gates' own refusal logs "
            "cross-referenced by entry key, a separate pass if wanted.")
    preamble.append("")

    body = G.render(
        f"W03-0012: DUX TAG(S) {'+'.join(tags)} AS A LONG-SIDE VETO",
        REGISTERED, books, paired_spec, (), symdays, errors, run_days,
        elapsed, jobs, refused, binding, error_days,
        preamble=preamble,
        universe=a.pairs, dataset=a.dataset)
    emit("\n".join(body), a.out,
         header=f"common.dux_veto (tags {','.join(tags)}) pairs={a.pairs} dataset={a.dataset} "
                f"daily_dataset={a.daily_dataset} sessions={len(run_days)} symbol_days={symdays} "
                f"qty={QTY} registered={REGISTERED}")
    G.write_csv(a.csv, books)
    G.write_meta(a.csv, run_days, symdays,
                 run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else ""),
                 {"pairs": a.pairs, "dataset": a.dataset, "daily_dataset": a.daily_dataset,
                  "registered": REGISTERED, "tags_run": tags})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
