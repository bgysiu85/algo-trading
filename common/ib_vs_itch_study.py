#!/usr/bin/env python3
r"""W02-0016 -- IB 1-minute bars vs ITCH bars on the live symbol-days,
signal-by-signal. DESCRIPTIVE, NOT REGISTERED (Ben's decision A on W02-0016,
2026-09-23): live-vs-backtest P/L gaps are mostly "different trades", not
execution (mcl_vs_mc5_live_RESULT.md). Live runs on IB 1-minute bars; the
backtest runs on the ITCH tape. This asks WHY the trades differ: do the two
feeds disagree on the BARS themselves (data divergence), or do they carry the
same bars into a different signal (timing/logic divergence)?

    python -m common.ib_vs_itch_study --pairs-only
        writes var/state/ib_vs_itch_pairs.json -- the symbol-days needing a
        fresh IB pull. No IB connection needed for this step.

    (Ben, IB Gateway paper running)
    python -m common.data_ib --pairs var/state/ib_vs_itch_pairs.json

    python -m common.ib_vs_itch_study
        the study itself, once the IB bars above are cached.

INPUTS
------
var/reports/live_vs_sim_trades.csv   -- W02-0002's matched/live-only/sim-only
                                         join (mcl_vs_mc5_live_RESULT.md).
                                         This study reads every "live-only"
                                         and "matched" row: the ones where
                                         live took a trade at all.
var/state/screen_pairs_pit_itch_ext3.json -- first_seen, for the same
                                         `not_before` floor the registered
                                         study used (feed_delay.delayed_floor).
bar_cache/3d_to_2000/<SYM>_<DATE>.csv.gz      IB bars (common/data_ib.py)
bar_cache_xnas/3d_to_2000/<SYM>_<DATE>.csv.gz ITCH bars, already cached from
                                         the W02-0002 screen run.

METHOD
------
For each (strategy, symbol, date) needing a look: run the SAME published
strategy code (common.pit_strategy.engine, the identical entry rule the live
trader and the backtest both use) once on the IB bar series and once on the
ITCH bar series for that symbol-day, with the identical `not_before` floor
(delayed_floor, the feed-matched offset: +15 before 2026-09-21, +0 from).
Compare the two runs' entries to each other and to the logged live/sim entry
times.

CAVEAT, stated plainly: this does not reproduce the registered population's
per-trade numbers -- it hands both engines the full cached superset (up to 3
sessions of warm-up) rather than the registered pipeline's own day-by-day
warm-up construction. That is deliberate: the two feeds get IDENTICAL warm-up
length here, which is what makes the IB-vs-ITCH comparison itself fair. It is
not a substitute for live_vs_sim.py's own numbers.

A symbol-day is classified from the bar-level diff plus the two entry lists:
    "bars diverge"                   close prices differ >1% on a bar both
                                      feeds have, or one feed is missing >3
                                      bars the other has, in the compared
                                      window
    "bars agree, signal timing diverges"   bars line up; the two engines
                                      still picked different entry bars (or
                                      one entered and the other didn't)
    "bars and signal agree"          same entries from both feeds -- the
                                      live/sim gap for this symbol-day is NOT
                                      a bar-data or entry-logic story
    "no overlapping bars"            feeds don't share a single timestamp
    "PENDING_IB_PULL"                IB bars not cached yet
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date as _date
from pathlib import Path

import pandas as pd
from zoneinfo import ZoneInfo

from common.cache_io import (SHARED_DURATION, SHARED_END_HHMM,
                             load_cached_bars, window_dir)
from common.entry_shares import QTY
from common.feed_delay import delayed_floor
from common.first_entry_skip import trade_row
from common.pit_strategy import engine

ET = ZoneInfo("America/New_York")
IB_CACHE_ROOT = Path("bar_cache")
ITCH_CACHE_ROOT = Path("bar_cache_xnas")
TRADES_CSV = Path("var/reports/live_vs_sim_trades.csv")
UNIVERSE_JSON = Path("var/state/screen_pairs_pit_itch_ext3.json")
PAIRS_OUT = Path("var/state/ib_vs_itch_pairs.json")
REPORT_TXT = Path("var/reports/ib_vs_itch_study.txt")
REPORT_CSV = Path("var/reports/ib_vs_itch_study_symdays.csv")

SIGNED_IN_FROM = "2026-09-21"     # feed_delay.SIGNED_IN_FROM
DELAY = 15                        # feed_delay.DELAY
BAR_COLS = ["open", "high", "low", "close", "volume"]
MATERIAL_PCT = 0.01               # >1% close delta on a shared bar
MATERIAL_MISSING = 3              # kept for reference, no longer used to classify
MATERIAL_FLAT_SHARE = 0.15         # >15% of overlap bars: IB flat, ITCH traded


def feed_offset(day: str) -> int:
    return DELAY if day < SIGNED_IN_FROM else 0


def needed_symdays() -> dict[tuple[str, str, str], list[dict]]:
    """(strategy, symbol, date) -> the live_vs_sim_trades.csv rows for it.
    live-only and matched only -- those are where live actually traded."""
    need: dict[tuple[str, str, str], list[dict]] = {}
    with open(TRADES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["kind"] in ("live-only", "matched"):
                key = (r["strategy"], r["symbol"], r["date"])
                need.setdefault(key, []).append(r)
    return need


def load_universe() -> dict[tuple[str, str], dict]:
    rows = json.loads(UNIVERSE_JSON.read_text(encoding="utf-8"))
    return {(r["symbol"], r["date"]): r for r in rows}


def cache_dir(root: Path) -> Path:
    return window_dir(root, SHARED_DURATION, SHARED_END_HHMM)


def write_pairs_file(need: dict) -> list[tuple[str, str]]:
    pairs = sorted({(sym, d) for (_, sym, d) in need}, key=lambda x: (x[1], x[0]))
    PAIRS_OUT.parent.mkdir(parents=True, exist_ok=True)
    PAIRS_OUT.write_text(
        json.dumps([{"symbol": s, "date": d} for s, d in pairs], indent=1),
        encoding="utf-8")
    return pairs


def run_entries(df: pd.DataFrame | None, strategy: str, day: str, floor) -> list[dict]:
    if df is None or df.empty:
        return []
    mod, extra = engine(strategy)
    trades = mod.backtest_session(df, _date.fromisoformat(day), ET,
                                  entry_shares=QTY, not_before=floor, **extra)
    return [trade_row(t, "", day, k) for k, t in enumerate(trades, 1)]


def bar_diff(ib_df: pd.DataFrame | None, itch_df: pd.DataFrame | None) -> dict | None:
    """CORRECTED 2026-09-24 -- the first version outer-joined and called any
    IB-only or ITCH-only minute "material divergence". That is wrong: IB's
    reqHistoricalData fills every quiet minute with a flat, ZERO-VOLUME bar
    (last close carried forward, barCount=0); ITCH's tick-built bars simply
    don't exist for a minute nothing traded. Across a 15-symbol-day sample
    30-52% of IB's bars are these zero-volume fills. Counting that as
    "divergence" made every single symbol-day read "bars diverge" -- an
    artifact of bar-construction convention, not a feed disagreement, and it
    buried the real, much smaller price gap underneath it (median close delta
    on genuinely overlapping bars was 0.05%, not the 4-37% the old max-based
    figure reported, itself one outlier bar).

    Three things are reported now, on the INNER join (timestamps both have):
    - price delta (median/mean/max) on bars where BOTH sides show a trade
      (ib volume > 0) -- the real "do the feeds disagree on price" question.
    - `ib_flat_itch_traded`: bars where IB shows NO trade (volume 0) but ITCH
      does. This is the mechanism that actually matters for the strategy:
      MCL/MC5's volume-surge and MFI conditions read zero on an IB bar where
      ITCH saw real volume, which can suppress or delay a signal on IB's feed
      that ITCH's tape would have taken.
    - bar coverage counts (ib_only / itch_only), kept as a plain fact, not a
      verdict driver.
    """
    if ib_df is None or itch_df is None:
        return None
    a = ib_df[BAR_COLS].copy()
    b = itch_df[BAR_COLS].copy()
    a.index = pd.to_datetime(a.index, utc=True)
    b.index = pd.to_datetime(b.index, utc=True)
    j = a.join(b, how="outer", lsuffix="_ib", rsuffix="_itch")
    both = j.dropna(subset=["close_ib", "close_itch"])
    ib_only = int(j["close_itch"].isna().sum())
    itch_only = int(j["close_ib"].isna().sum())
    if both.empty:
        return {"bars_both": 0, "bars_both_traded": 0, "ib_flat_itch_traded": 0,
                "ib_only_bars": ib_only, "itch_only_bars": itch_only,
                "median_close_delta_pct": None, "mean_close_delta_pct": None,
                "max_close_delta_pct": None}
    ib_traded = both["volume_ib"] > 0
    ib_flat_itch_traded = int((~ib_traded).sum())
    traded = both[ib_traded]
    if traded.empty:
        med = mean = mx = None
    else:
        delta = (traded["close_ib"] - traded["close_itch"]).abs()
        pct = (delta / traded["close_itch"].replace(0, pd.NA)).abs().dropna()
        med = float(pct.median()) if not pct.empty else None
        mean = float(pct.mean()) if not pct.empty else None
        mx = float(pct.max()) if not pct.empty else None
    return {"bars_both": int(len(both)), "bars_both_traded": int(traded.shape[0]),
            "ib_flat_itch_traded": ib_flat_itch_traded,
            "ib_only_bars": ib_only, "itch_only_bars": itch_only,
            "median_close_delta_pct": med, "mean_close_delta_pct": mean,
            "max_close_delta_pct": mx}


def classify(diff: dict | None, ib_entries: list[dict], itch_entries: list[dict]) -> str:
    """CORRECTED 2026-09-24 -- price divergence now reads the MEDIAN delta on
    bars both feeds actually traded (see bar_diff), not the max over an
    outer join that mostly counted IB's zero-volume fills. A large
    `ib_flat_itch_traded` share is reported as its own verdict, because it is
    plausibly the real mechanism, not folded silently into "bars diverge"."""
    if diff is None:
        return "PENDING_IB_PULL"
    if diff["bars_both"] == 0:
        return "no overlapping bars"
    price_material = (diff["median_close_delta_pct"] or 0) > MATERIAL_PCT
    ib_et = [e["entry_et"] for e in ib_entries]
    itch_et = [e["entry_et"] for e in itch_entries]
    signal_diverges = ib_et != itch_et
    flat_share = (diff["ib_flat_itch_traded"] / diff["bars_both"]) if diff["bars_both"] else 0
    if price_material:
        return "bars diverge (price)"
    if flat_share > MATERIAL_FLAT_SHARE and signal_diverges:
        return "IB shows no trade where ITCH does, signal timing diverges"
    if signal_diverges:
        return "bars agree, signal timing diverges (other cause)"
    return "bars and signal agree"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs-only", action="store_true",
                    help="write the IB pull pairs file and exit")
    args = ap.parse_args()

    need = needed_symdays()
    pairs = write_pairs_file(need)
    print(f"{len(pairs)} symbol-days needed -- pairs file: {PAIRS_OUT}")
    if args.pairs_only:
        return 0

    universe = load_universe()
    ib_dir = cache_dir(IB_CACHE_ROOT)
    itch_dir = cache_dir(ITCH_CACHE_ROOT)

    rows = []
    for (strategy, sym, day), logged in sorted(need.items()):
        rec = universe.get((sym, day))
        seen_et = None
        floor = None
        if rec and rec.get("first_seen"):
            seen_et = pd.Timestamp(rec["first_seen"]).tz_convert(ET).time()
            floor = delayed_floor(seen_et, feed_offset(day), _date.fromisoformat(day))

        ib_df = load_cached_bars(ib_dir, sym, day)
        itch_df = load_cached_bars(itch_dir, sym, day)
        diff = bar_diff(ib_df, itch_df)
        ib_entries = run_entries(ib_df, strategy, day, floor)
        itch_entries = run_entries(itch_df, strategy, day, floor)
        verdict = classify(diff, ib_entries, itch_entries)

        rows.append({
            "strategy": strategy, "symbol": sym, "date": day,
            "in_sim_universe": bool(rec), "first_seen_et": str(seen_et or ""),
            "logged_live_entries": ";".join(r["live_entry"] for r in logged if r["live_entry"]),
            "logged_sim_entries": ";".join(r["sim_entry"] for r in logged if r["sim_entry"]),
            "ib_entries": ";".join(e["entry_et"] for e in ib_entries),
            "itch_entries": ";".join(e["entry_et"] for e in itch_entries),
            "bars_both": diff["bars_both"] if diff else "",
            "bars_both_traded": diff["bars_both_traded"] if diff else "",
            "ib_flat_itch_traded": diff["ib_flat_itch_traded"] if diff else "",
            "ib_only_bars": diff["ib_only_bars"] if diff else "",
            "itch_only_bars": diff["itch_only_bars"] if diff else "",
            "median_close_delta_pct": round(diff["median_close_delta_pct"] * 100, 3)
                if diff and diff["median_close_delta_pct"] is not None else "",
            "max_close_delta_pct": round(diff["max_close_delta_pct"] * 100, 3)
                if diff and diff["max_close_delta_pct"] is not None else "",
            "verdict": verdict,
        })

    REPORT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    counts = Counter(r["verdict"] for r in rows)
    lines = [
        "W02-0016 -- IB bars vs ITCH bars on the live symbol-days, signal-by-signal",
        "Descriptive, not registered. See module docstring for method and caveat.",
        f"symbol-days: {len(rows)}",
        "",
        "verdict counts:",
    ]
    for k, v in counts.most_common():
        lines.append(f"  {k:<36}{v:>4}")
    lines.append("")
    lines.append(f"full rows: {REPORT_CSV}")
    REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
