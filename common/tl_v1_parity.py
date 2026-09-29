#!/usr/bin/env python3
"""G3 of REGISTERED_tl_v1.md sec 5.1: Pine <-> Python parity -- W15-0019
subitem 3.

    python -m common.tl_v1_parity --tv-csv <path to Ben's TradingView export>

BEN'S HALF (never done by a chat -- pine/TL_v1.pine is delivered as a file
for a reason, sec 5.1's own words): paste pine/TL_v1.pine into TradingView
himself, put it on CL1!, Daily, back-adjustment OFF, pivLen (L=R) left at its
default 5 (the pre-flight's reported neighbour, sec 5.2 table 2), range
2015-01-01..2019-12-31 (inside training, sec 6 -- the holdout, 2022-01-03
on, is never touched by this comparison). Then TradingView's own "Export
chart data" (chart menu, NOT the Data Window, which cannot be saved to a
file) with "Resistance (her line)" and "Support (her line)" included --
these are the two plot() series pine/TL_v1.pine draws; nothing else about
the indicator (touch counts, A+ flags, the stats table) is a plot() series,
so nothing else round-trips through an export.

THIS HALF: loads the same window from the Databento archive through
strategy.tl_v0.bars.load_market (the same loader, roll rule and holdout cut
already used everywhere else on this board), runs it through
common/tl_v1_lines.py's build_series() on the RAW OHLC columns (ro/rh/rl/rc)
-- NOT the difference-back-adjusted "signal series" (open/high/low/close)
the real W15-0020 backtest uses -- because REGISTERED_tl_v1.md sec 5.1 G3
explicitly says this comparison is run "back-adjustment off", to match what
a raw TradingView export can actually be checked against. Diffs the two line
series bar-for-bar on the shared dates. A bar counts as matched when
both sides agree the line is off (both NaN) or agree it is on and the two
values sit within --tol of each other (default 0.01, i.e. one cent on most
CL price scales -- generous next to a 0.10xATR buffer already built into
the line's own validity test).

FOLLOWS THE TL-BOUNCE PRECEDENT for closing a G3 (REGISTERED_tl_bounce.md
Amendment 1): mismatches are not required to be zero, but each one must be
explained. TradingView's CL1! continuous contract and the Databento
archive's held_id-based roll convention have already been shown (TL-bounce)
to roll on different days -- so before treating any mismatch here as a bug,
the report buckets mismatch dates by calendar month so a chat or Ben can
eyeball whether they cluster the same way TL-bounce's did (typically the
first few sessions of a contract month). This script does not itself decide
that; sec 5.1 G3 is only closed once that explanation (or another one) is
written into the registration, same as TL-bounce's Amendment 1.
"""
from __future__ import annotations
import argparse
import sys

import numpy as np
import pandas as pd

from common.tl_v0_lines import atr14, find_pivots
from common.tl_v1_lines import build_series
from common.report_io import emit

ARCHIVE_DEFAULT = r"E:\Databento\GLBX.MDP3"
ROOT_DEFAULT = "CL"
PIVLEN_DEFAULT = 5
START_DEFAULT = "2015-01-01"
END_DEFAULT = "2019-12-31"
TOL_DEFAULT = 0.01


def _find_col(columns, *needles: str) -> str | None:
    for c in columns:
        lc = str(c).lower()
        if all(needle in lc for needle in needles):
            return c
    return None


def _parse_tv_time(raw_time: pd.Series) -> pd.Series:
    """TradingView's export offers 'UNIX timestamp' (bare seconds-since-epoch
    integers) or a formatted date/time string, chosen in the export dialog.
    pandas' default to_datetime() treats a bare integer column as
    NANOSECONDS since epoch, not seconds -- silently landing every row at
    1970-01-01 instead of raising. Detect the numeric case explicitly and
    parse it with unit='s' so that mistake can't happen quietly again."""
    numeric = pd.to_numeric(raw_time, errors="coerce")
    if numeric.notna().all():
        return pd.to_datetime(numeric, unit="s", utc=True, errors="coerce")
    return pd.to_datetime(raw_time, utc=True, errors="coerce")


def load_tv_export(csv_path: str) -> pd.DataFrame:
    """Ben's TradingView 'Export chart data' CSV. Column names vary slightly
    by TradingView version, so this matches loosely rather than by exact
    header text: a time/date column, and the two plot() series by the
    words in their titles (see pine/TL_v1.pine's plot(...) calls)."""
    raw = pd.read_csv(csv_path)
    time_col = _find_col(raw.columns, "time") or _find_col(raw.columns, "date")
    res_col = _find_col(raw.columns, "resistance")
    sup_col = _find_col(raw.columns, "support")
    missing = [n for n, c in (("time/date", time_col), ("Resistance", res_col),
                               ("Support", sup_col)) if c is None]
    if missing:
        raise SystemExit(
            f"tv-csv is missing column(s) {missing} -- got columns {list(raw.columns)}. "
            "Re-export with 'Resistance (her line)' and 'Support (her line)' both visible.")
    ts = _parse_tv_time(raw[time_col])
    out = pd.DataFrame({
        "date": ts.dt.tz_localize(None).dt.normalize(),
        "tv_resV": pd.to_numeric(raw[res_col], errors="coerce"),
        "tv_supV": pd.to_numeric(raw[sup_col], errors="coerce"),
    })
    return out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def python_side(archive: str, root: str, pivlen: int) -> pd.DataFrame:
    """REGISTERED_tl_v1.md sec 5.1 G3 says 'CL1! daily, 2015-2019,
    back-adjustment OFF'. strategy/tl_v0/bars.py's frame carries both series:
    open/high/low/close is the difference-back-adjusted SIGNAL series the
    real W15-0020 backtest will use (deliberately, to keep roll-day gaps from
    corrupting pivot/ATR detection across the full 2010-2021 training run) --
    but that is not what G3 asks for, and not what a raw TradingView export
    can be checked against. ro/rh/rl/rc are the RAW OHLC of the held
    contract, matching Ben's back-adjustment-OFF chart bar for bar. G3 uses
    the raw columns; W15-0020 will still use the adjusted ones (unchanged)."""
    from strategy.tl_v0.bars import load_market
    from strategy.tl_v0.spec import MARKETS
    m = MARKETS[root]
    mb, _c0 = load_market(archive, m)
    frame = mb.frame
    o, h, lo, c = (frame[k].to_numpy(dtype=float) for k in ("ro", "rh", "rl", "rc"))
    n = len(c)
    atr = atr14(h, lo, c)
    ph = find_pivots(h, pivlen, "high")
    pl = find_pivots(lo, pivlen, "low")
    res_out = build_series(n, ph, c, atr, "res")
    sup_out = build_series(n, pl, c, atr, "sup")
    return pd.DataFrame({
        "date": frame["date"].dt.normalize(),
        "py_resV": res_out["line"],
        "py_supV": sup_out["line"],
    })


def diff(tv: pd.DataFrame, py: pd.DataFrame, start: str, end: str, tol: float) -> pd.DataFrame:
    merged = tv.merge(py, on="date", how="inner")
    merged = merged[(merged["date"] >= start) & (merged["date"] <= end)].reset_index(drop=True)
    if merged.empty:
        tv_lo, tv_hi = (str(tv["date"].min().date()), str(tv["date"].max().date())) if len(tv) else ("(empty)", "(empty)")
        py_lo, py_hi = (str(py["date"].min().date()), str(py["date"].max().date())) if len(py) else ("(empty)", "(empty)")
        raise SystemExit(
            f"no overlapping dates between the tv-csv and the Python side in [{start}, {end}].\n"
            f"  tv-csv covers:      {tv_lo} .. {tv_hi}  ({len(tv)} rows)\n"
            f"  python side covers: {py_lo} .. {py_hi}  ({len(py)} rows)\n"
            "TradingView's chart-data export only includes bars already loaded into that\n"
            "chart -- a fresh daily chart usually starts with only the last year or two in\n"
            "memory. Scroll/drag the chart back until 2015 is visible (or zoom all the way\n"
            "out) so those bars actually load, THEN re-export.")

    def _state(row, side):
        tv_v, py_v = row[f"tv_{side}V"], row[f"py_{side}V"]
        tv_on, py_on = not pd.isna(tv_v), not pd.isna(py_v)
        if not tv_on and not py_on:
            return "match_off", np.nan
        if tv_on != py_on:
            return "state_mismatch", np.nan
        d = abs(tv_v - py_v)
        return ("match_on" if d <= tol else "value_mismatch"), d

    for side in ("res", "sup"):
        states, deltas = zip(*(_state(r, side) for _, r in merged.iterrows()))
        merged[f"{side}_state"] = states
        merged[f"{side}_delta"] = deltas
    return merged


def build_report(merged: pd.DataFrame, root: str, pivlen: int, start: str, end: str,
                  tol: float, tv_csv: str) -> str:
    lines = []
    def p(s=""):
        lines.append(s)

    p("TL-v1 G3 PARITY -- REGISTERED_tl_v1.md sec 5.1 gate G3 (W15-0019 subitem 3)")
    p(f"market={root}  pivLen(L=R)={pivlen}  window=[{start}, {end}]  tol={tol}")
    p(f"tv-csv: {tv_csv}")
    p(f"bars compared: {len(merged)}")
    p("")
    p("=" * 78); p("1. MATCH RATE, BOTH LINES"); p("=" * 78)
    for side, label in (("res", "Resistance"), ("sup", "Support")):
        counts = merged[f"{side}_state"].value_counts()
        total = len(merged)
        on_total = counts.get("match_on", 0) + counts.get("value_mismatch", 0)
        p(f"{label}:")
        p(f"  both off (line not armed either side): {counts.get('match_off', 0)}")
        p(f"  on/off state mismatch (armed one side, not the other): {counts.get('state_mismatch', 0)}")
        p(f"  both on, value matches (<= tol):        {counts.get('match_on', 0)} / {on_total}")
        p(f"  both on, value mismatch (> tol):         {counts.get('value_mismatch', 0)} / {on_total}")
        bad = counts.get("state_mismatch", 0) + counts.get("value_mismatch", 0)
        p(f"  overall mismatch rate: {bad}/{total} = {bad / total:.1%}" if total else "  n/a")
        p("")

    p("=" * 78); p("2. MISMATCH DATES BY CALENDAR MONTH (roll-timing clustering check)"); p("=" * 78)
    p("TL-bounce's own G3 (Amendment 1) found its mismatches clustered around contract")
    p("rolls -- TradingView's CL1! and the Databento archive's held_id convention roll")
    p("on different days. Check the busiest month(s) below against known CL roll dates")
    p("before treating any of this as a Pine or Python logic bug.")
    any_mismatch = False
    for side in ("res", "sup"):
        bad = merged[merged[f"{side}_state"].isin(["state_mismatch", "value_mismatch"])]
        if bad.empty:
            continue
        any_mismatch = True
        by_month = bad["date"].dt.to_period("M").value_counts().sort_index()
        p(f"{side}: {len(bad)} mismatched bars, by month:")
        p(by_month.to_string())
        p("")
    if not any_mismatch:
        p("No mismatches on either line -- nothing to cluster.")

    p("=" * 78); p("3. FIRST 50 MISMATCHED BARS (either line), for manual inspection"); p("=" * 78)
    bad_rows = merged[
        merged["res_state"].isin(["state_mismatch", "value_mismatch"]) |
        merged["sup_state"].isin(["state_mismatch", "value_mismatch"])
    ]
    if bad_rows.empty:
        p("(none)")
    else:
        cols = ["date", "tv_resV", "py_resV", "res_state", "res_delta",
                "tv_supV", "py_supV", "sup_state", "sup_delta"]
        p(bad_rows[cols].head(50).to_string(index=False))

    p("")
    p("=" * 78); p("4. G3 VERDICT (fill in after reading sec 2, then write into the registration)")
    p("=" * 78)
    p("[ ] Zero mismatches -- G3 clears outright.")
    p("[ ] Mismatches present but cluster on/around contract-roll dates, same shape as")
    p("    TL-bounce's Amendment 1 -- G3 closes on that explanation, same as TL-bounce.")
    p("[ ] Mismatches present and do NOT explain by roll timing -- treat as a real bug,")
    p("    G3 stays open, do not run W15-0020.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tv-csv", required=True, help="Ben's TradingView chart-data export")
    ap.add_argument("--archive", default=ARCHIVE_DEFAULT)
    ap.add_argument("--root", default=ROOT_DEFAULT)
    ap.add_argument("--pivlen", type=int, default=PIVLEN_DEFAULT)
    ap.add_argument("--start", default=START_DEFAULT)
    ap.add_argument("--end", default=END_DEFAULT)
    ap.add_argument("--tol", type=float, default=TOL_DEFAULT)
    ap.add_argument("--report", default="var/reports/tl_v1_g3_parity.txt")
    ap.add_argument("--csv-out", default="var/reports/tl_v1_g3_parity_bars.csv")
    a = ap.parse_args(argv)

    tv = load_tv_export(a.tv_csv)
    py = python_side(a.archive, a.root, a.pivlen)
    merged = diff(tv, py, a.start, a.end, a.tol)
    merged.to_csv(a.csv_out, index=False)
    text = build_report(merged, a.root, a.pivlen, a.start, a.end, a.tol, a.tv_csv)
    emit(text, a.report, header="common.tl_v1_parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
