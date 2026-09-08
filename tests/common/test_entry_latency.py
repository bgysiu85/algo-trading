#!/usr/bin/env python3
"""The entry-latency measurement says what it says it says.

Ben's observation (2026-09-08): MCL fills at the close of the bar that made
the move. Before an entry rule is built on that, the numbers have to be right
on a bar where the answer is known by hand -- and the measurement has to be
made on winners too, or it is a description of losers.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import entry_latency as EL

ET = ZoneInfo("America/New_York")


def bars(ohlc, start="2026-01-07 04:00"):
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(ohlc))]).tz_convert("UTC")
    df = pd.DataFrame(ohlc, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 1000
    return df


def test_the_arithmetic_on_a_bar_worked_by_hand():
    """Session opens 5.00. Signal bar (index 2): open 5.20, high 5.60,
    low 5.10, close 5.55. Engine buys 5.55 + 0.01 = 5.56. Next two bars reach
    5.70 high and 5.30 low; exit at 5.40 on bar 4."""
    df = bars([
        (5.00, 5.05, 4.95, 5.02),
        (5.02, 5.25, 5.00, 5.20),     # prior bar: high 5.25
        (5.20, 5.60, 5.10, 5.55),     # signal bar
        (5.55, 5.70, 5.50, 5.60),
        (5.60, 5.62, 5.30, 5.40),     # exit bar
    ])
    t = {"symbol": "T", "date": "2026-01-07",
         "entry_time": str(df.index[2]), "exit_time": str(df.index[4]),
         "entry_price": 5.56, "exit_price": 5.40, "qty": 100,
         "bars_held": 2, "net": -17.0}
    r = EL.measure(t, df)
    assert r is not None
    assert r.fill_pos == pytest.approx((5.56 - 5.10) / (5.60 - 5.10), abs=1e-4)
    assert r.bar_move_pct == pytest.approx((5.55 - 5.20) / 5.20 * 100, abs=1e-3)
    assert r.runup_pct == pytest.approx((5.55 - 5.00) / 5.00 * 100, abs=1e-3)
    assert r.mfe_pct == pytest.approx((5.70 - 5.56) / 5.56 * 100, abs=1e-3)
    assert r.mae_pct == pytest.approx((5.30 - 5.56) / 5.56 * 100, abs=1e-3)
    assert r.realised_pct == pytest.approx((5.40 - 5.56) / 5.56 * 100, abs=1e-3)
    assert r.bar_cost == pytest.approx((5.56 - 5.20) * 100, abs=0.01)
    assert r.prev_high == 5.25
    assert r.prev_high_cost == pytest.approx((5.56 - 5.25) * 100, abs=0.01)
    assert r.winner is False


def test_mfe_excludes_the_signal_bar_itself():
    """The signal bar's own high happened BEFORE the fill at its close.
    Counting it as post-entry excursion would credit the trade with a move
    it never held -- the same lookahead the peak-seeding fix removed."""
    df = bars([
        (5.00, 5.05, 4.95, 5.02),
        (5.02, 9.00, 5.00, 5.20),     # signal bar with an absurd high
        (5.20, 5.30, 5.10, 5.25),
    ])
    t = {"symbol": "T", "date": "2026-01-07",
         "entry_time": str(df.index[1]), "exit_time": str(df.index[2]),
         "entry_price": 5.21, "exit_price": 5.25, "qty": 100,
         "bars_held": 1, "net": 3.0}
    r = EL.measure(t, df)
    assert r.mfe_pct == pytest.approx((5.30 - 5.21) / 5.21 * 100, abs=1e-3)


def test_prev_high_cost_only_when_the_bar_cleared_it():
    """A resting stop at the prior high fills only if this bar traded above
    it. A signal bar that stayed below the prior high offers nothing."""
    df = bars([
        (5.00, 6.00, 4.95, 5.02),     # prior high 6.00
        (5.02, 5.50, 5.00, 5.40),     # signal bar never reaches 6.00
        (5.40, 5.45, 5.30, 5.35),
    ])
    t = {"symbol": "T", "date": "2026-01-07",
         "entry_time": str(df.index[1]), "exit_time": str(df.index[2]),
         "entry_price": 5.41, "exit_price": 5.35, "qty": 100,
         "bars_held": 1, "net": -7.0}
    assert EL.measure(t, df).prev_high_cost is None


def test_a_trade_whose_bar_is_not_in_the_cache_is_counted_not_skipped():
    df = bars([(5.0, 5.1, 4.9, 5.0)] * 3)
    t = {"symbol": "T", "date": "2026-01-07",
         "entry_time": "2026-01-07 12:00:00+00:00",
         "exit_time": "2026-01-07 12:05:00+00:00",
         "entry_price": 5.0, "exit_price": 5.0, "qty": 100,
         "bars_held": 1, "net": 0.0}
    assert EL.measure(t, df) is None
    out = "\n".join(EL.render([], missing=1, source="x"))
    assert "signal bar not found in cache: 1" in out


def test_the_report_shows_winners_and_losers_separately():
    """The whole point. A report that pooled them would let the losers'
    pattern be read as the strategy's."""
    df = bars([(5.0, 5.1, 4.9, 5.0), (5.0, 5.3, 4.95, 5.25), (5.25, 5.5, 5.2, 5.4),
               (5.4, 5.45, 5.0, 5.05)])
    rows = []
    for net, exit_px in ((10.0, 5.40), (-20.0, 5.05)):
        t = {"symbol": "T", "date": "2026-01-07",
             "entry_time": str(df.index[1]), "exit_time": str(df.index[3]),
             "entry_price": 5.26, "exit_price": exit_px, "qty": 100,
             "bars_held": 2, "net": net}
        rows.append(EL.measure(t, df))
    out = "\n".join(EL.render(rows, 0, "x"))
    assert "WINNERS  (1 trades" in out and "LOSERS  (1 trades" in out
    assert "ALL  (2 trades" in out


# --- end to end, on real MCL trades from real bars -------------------------------

REPO = Path(__file__).resolve().parents[2]
BARS_CANDIDATES = [REPO / "bar_cache_db" / "3d_to_2000",
                   Path("/mnt/user-data/uploads/Trading/bar_cache_db/3d_to_2000")]
CASES = [("AAL", "2024-12-05"), ("AAOZ", "2026-08-06"), ("AAOZ", "2026-08-07"),
         ("ABAT", "2026-06-08"), ("ABCL", "2025-06-10"), ("ABCL", "2026-08-10")]


def test_the_cli_runs_on_real_mcl_trades(tmp_path):
    """Generate MCL trades from cached bars with the engine itself, then
    measure them. If the signal bar cannot be found for a trade the engine
    just produced, the timestamp convention is wrong and every number is."""
    from dataclasses import asdict
    from strategy.mcl import mcl
    cache = next((c for c in BARS_CANDIDATES if c.is_dir()), None)
    if cache is None:
        pytest.skip("no bar cache -- the end-to-end check is NOT running here")
    trades = []
    for sym, day in CASES:
        p = cache / f"{sym}_{day}.csv.gz"
        if not p.exists():
            continue
        df = pd.read_csv(p, index_col=0, parse_dates=True)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        for t in mcl.backtest_session(df, date.fromisoformat(day), ET):
            d = asdict(t); d["symbol"] = sym; trades.append(d)
    if not trades:
        pytest.skip("MCL produced no trades on the cached cases")

    tpath = tmp_path / "trades.csv"
    with open(tpath, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trades[0].keys()))
        w.writeheader(); w.writerows(trades)
    out = tmp_path / "r.txt"
    rc = subprocess.run([sys.executable, "-m", "common.entry_latency",
                         "--trades", str(tpath), "--cache", str(cache.parent),
                         "--out", str(out), "--csv", str(tmp_path / "r.csv")],
                        capture_output=True, text=True, cwd=REPO)
    assert rc.returncode == 0, rc.stderr[-800:]
    text = out.read_text()
    assert f"trades measured   {len(trades):,}" in text
    assert "signal bar not found in cache: 0" in text, \
        "the engine's own trades did not match its own bars"


def test_a_5_minute_strategy_is_measured_against_5_minute_bars(tmp_path):
    """The first MC5 run compared a 5-minute fill with a 1-minute bar and
    reported fill positions of 7.85x the range. The signal bar has to be the
    bar the strategy actually saw."""
    from dataclasses import asdict
    from strategy.mc5 import mc5
    cache = next((c for c in BARS_CANDIDATES if c.is_dir()), None)
    if cache is None:
        pytest.skip("no bar cache")
    trades = []
    for sym, day in CASES:
        p = cache / f"{sym}_{day}.csv.gz"
        if not p.exists():
            continue
        df = pd.read_csv(p, index_col=0, parse_dates=True)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        for t in mc5.backtest_session(df, date.fromisoformat(day), ET):
            d = asdict(t); d["symbol"] = sym; trades.append(d)
    if not trades:
        pytest.skip("MC5 produced no trades on the cached cases")
    tpath = tmp_path / "t.csv"
    with open(tpath, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trades[0].keys()))
        w.writeheader(); w.writerows(trades)
    out = tmp_path / "r.txt"
    rc = subprocess.run([sys.executable, "-m", "common.entry_latency",
                         "--trades", str(tpath), "--cache", str(cache.parent),
                         "--bar-minutes", "5", "--out", str(out),
                         "--csv", str(tmp_path / "r.csv")],
                        capture_output=True, text=True, cwd=REPO)
    assert rc.returncode == 0, rc.stderr[-800:]
    text = out.read_text()
    assert "signal bar not found in cache: 0" in text, \
        "MC5's own 5-minute signal bars must all be found at 5 minutes"
    # Every fill sits within a plausible distance of its own bar: the +1 tick
    # can push it just above the high, never several ranges above it.
    import csv as _csv
    rows = list(_csv.DictReader(open(tmp_path / "r.csv")))
    for r in rows:
        if r["fill_pos"]:
            assert -0.5 <= float(r["fill_pos"]) <= 1.5, r
