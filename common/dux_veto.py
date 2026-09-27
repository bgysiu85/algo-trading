#!/usr/bin/env python3
r"""W03-0012 -- the three Dux long-side veto tags, on their own registration.

    python -m common.dux_veto --jobs 8                  # Tag G only (unblocked)
    python -m common.dux_veto --jobs 8 --tags G,B,R \
        --daily-source <path>                            # once Ben picks a daily source

Registered in docs/research/REGISTERED_dux_veto.md before this file existed.
Ben's decision (W11-0032 option A, recorded on board item W03-0012): tag
MCL/MC5 longs against Steven Dux's three short setups, veto style (checked
last, refuse-and-log, same model as the drift guard / spread gate), no new
data, no shorting.

WHICH TAGS CAN ACTUALLY RUN RIGHT NOW
--------------------------------------
TAG G ("crowded gap-up") is UNBLOCKED: it reads only the entry session's own
XNAS.ITCH pre-market bars (already owned, full point-in-time universe) and
`var/state/regular_close.json`'s previous-close (already owned, whole tape).
`tag_crowded_gap` below is exercised end to end by `run_day`/`main` against
the real archive.

TAG B ("overhead dollar block") and TAG R ("day after first red day") both
need a DAILY, SPLIT-ADJUSTED OHLCV history, 252 trading sessions deep, per
symbol -- and this project does not currently own that at PIT-universe scale:

  * `bar_cache/3d_to_2000` is IB minute bars, THREE sessions deep, for 443
    (symbol, entry-date) pairs -- an old, small subset, not a 252-session
    daily archive over the PIT universe.
  * Databento's daily bars exist (the whole tape) but are explicitly NOT
    split-adjusted (PROGRAM_INDEX §5: "A 1-for-10 reverse split prints as a
    ~900% overnight gain") -- exactly the artefact `tag_dollar_block` and
    `tag_post_first_red_day` would misread as a Dux "spike day" or a
    green-day run. Using them un-adjusted risks the VW9 class of bug
    (PROGRAM_INDEX §1: "a strategy without the price band trades the
    adjustment factor").

So `tag_dollar_block` and `tag_post_first_red_day` are written and
unit-tested here against synthetic fixtures (G1: every boundary value the
registration names, exactly), but this module's CLI REFUSES to run them
against the real book without an explicit `--daily-source` naming a
split-adjusted daily loader -- see `load_daily_bars` and the PRE-RUN
amendment posted on W03-0012 for the options put to Ben. Running blind on
raw dailies would produce a plausible-looking, silently wrong number, which
is exactly the failure mode PROGRAM_INDEX §4 exists to keep out.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import gate_study as G
from common.running_up import session_slice
from common.entry_shares import MEASURED_FRICTION, QTY
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
DATASET = "XNAS.ITCH"
REGISTERED = "docs/research/REGISTERED_dux_veto.md"

# --- Tag G: crowded gap-up -- Ben's numbers, verbatim, §2 -------------------------
TAG_G_GAP_PCT = 100.0            # gap_pct >= this
TAG_G_PREMKT_VOL = 50_000_000.0  # premkt_vol > this (strict)

# --- Tag B: overhead dollar block -- §2 -------------------------------------------
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


# =============================== TAG B ============================================

@dataclass(frozen=True)
class DailyBar:
    date: str
    close: float
    volume: float
    high: float
    low: float


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


def tag_dollar_block(daily: list[DailyBar], entry_running_high: float,
                     threshold: float = TAG_B_DOLLAR_BLOCK,
                     band_pct: float = TAG_B_BAND_PCT) -> tuple[bool, float | None, float | None]:
    """Ben's "overhead dollar block", §2. (tagged, dollar_block, trapped_level).

    `daily` must already be the trailing TAG_B_LOOKBACK sessions (or the
    symbol's full history if shorter) strictly before the entry date --
    `load_daily_bars` below is responsible for that slicing so this function
    stays pure arithmetic and stays trivially fixture-testable.

    No spike day in the window -> (False, None, None), no further
    computation (§2: "IF no such session exists in the lookback window:
    TAG_B = False").
    """
    spike = _spike_day(daily)
    if spike is None:
        return False, None, None
    dollar_block = spike.close * spike.volume
    trapped_level = spike.close
    if trapped_level <= 0:
        return False, dollar_block, trapped_level
    within_band = abs(entry_running_high - trapped_level) / trapped_level * 100.0 <= band_pct
    tagged = (dollar_block >= threshold) and within_band
    return bool(tagged), dollar_block, trapped_level


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
    given the wrong input; `load_daily_bars` is responsible for that slicing.
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


# =============================== the study runner (Tag G only, for now) ===========

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


BOOKS = (
    ("MCL", "mcl", False), ("MCL-duxG", "mcl", True),
    ("MC5", "mc5", False), ("MC5-duxG", "mc5", True),
)
PAIRED = (("MCL", "MCL-duxG"), ("MC5", "MC5-duxG"))


def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe, prevclose = args
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

    res = {"books": {name: [] for name, _, _ in BOOKS}, "symdays": 0, "errors": 0,
           "error_days": [], "tag_g_rows": [],
           "refused": {g: [] for _, g in PAIRED},
           "binding": {g: [0, 0, {}] for _, g in PAIRED}}

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
            gate = None
            # One gate mask for the WHOLE session: the tag is evaluated once
            # per bar (the running high/volume both grow monotonically
            # through the session) and the series is monotone non-increasing
            # once it fires, matching how the drift/spread guards are
            # checked "last, on a fresh read" -- but here computed off closed
            # bars only, same as every other gate in this codebase.
            idx = df.index
            vals = np.ones(len(idx), dtype=bool)
            for i, ts in enumerate(idx):
                tagged, _, _ = tag_crowded_gap(df, ts, prevc)
                vals[i] = not tagged
            gate = pd.Series(vals, index=idx)

            got = {}
            for name, eng, gated in BOOKS:
                mod, extra = engines[eng]
                g = gate if gated else None
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

        for base_name, gname in PAIRED:
            eng = "mcl" if base_name == "MCL" else "mc5"
            b = res["binding"][gname]
            for t in got[base_name]:
                ts = pd.Timestamp(f"{day} {t.entry_time}", tz=ET) \
                    if isinstance(t.entry_time, str) else t.entry_time
                allowed = bool(gate.reindex([ts], method="ffill").fillna(True).iloc[0])
                b[1] += 1
                b[0] += 1
                if not allowed:
                    res["refused"][gname].append(G.trade_row(t, s, day, 0))
    return day, res, ""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--regular-close", default="var/state/regular_close.json")
    p.add_argument("--tags", default="G",
                   help="comma-separated subset of G,B,R to run; only G runs "
                        "without --daily-source (see the module docstring)")
    p.add_argument("--daily-source", default=None,
                   help="split-adjusted daily-bar loader for tags B/R; not yet "
                        "chosen -- see the PRE-RUN amendment on W03-0012")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/dux_veto.txt")
    p.add_argument("--csv", default="var/reports/dux_veto_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    tags = [t.strip().upper() for t in a.tags.split(",") if t.strip()]
    if any(t in ("B", "R") for t in tags) and not a.daily_source:
        sys.exit(
            "tags B and R need a split-adjusted daily-bar source this project "
            "does not yet own at PIT-universe scale (see the module docstring "
            "and the PRE-RUN amendment posted on W03-0012). Pass "
            "--daily-source once Ben has decided one, or run --tags G alone.")
    archive = Path(a.archive) if a.archive else default_archive()

    rep = load_prev_closes(a.regular_close)
    all_tasks, by_date = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    session_days = sorted(by_date)
    prevclose = prev_close_lookup(rep, session_days)
    tasks = [(p, d, u, prevclose) for p, d, u in all_tasks]
    jobs = G.jobs_from(a.jobs)

    got, elapsed = G.run_sessions(run_day, tasks, jobs, "dux_veto (Tag G)")

    books = {name: [] for name, _, _ in BOOKS}
    refused = {g: [] for _, g in PAIRED}
    binding = {g: [0, 0, {}] for _, g in PAIRED}
    symdays, errors, error_days = 0, 0, []
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

    body = G.render(
        "W03-0012: DUX TAG G (\"crowded gap-up\") AS A LONG-SIDE VETO",
        REGISTERED, books, PAIRED, (), symdays, errors, run_days,
        elapsed, jobs, refused, binding, error_days,
        preamble=[
            "",
            f"Tag G: refuse a BUY when gap_pct >= {TAG_G_GAP_PCT:.1f}% (running high "
            f"since 04:00 vs previous regular close) AND premkt_vol > "
            f"{TAG_G_PREMKT_VOL:,.0f} shares.",
            "Tags B and R are NOT run here -- see the module docstring and the "
            "PRE-RUN amendment on W03-0012 (no owned split-adjusted daily history).",
            "",
        ],
        universe=a.pairs, dataset=a.dataset)
    emit("\n".join(body), a.out,
         header=f"common.dux_veto (Tag G) pairs={a.pairs} dataset={a.dataset} "
                f"sessions={len(run_days)} symbol_days={symdays} qty={QTY} "
                f"registered={REGISTERED}")
    G.write_csv(a.csv, books)
    G.write_meta(a.csv, run_days, symdays,
                 run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else ""),
                 {"pairs": a.pairs, "dataset": a.dataset, "registered": REGISTERED,
                  "tags_run": ["G"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
