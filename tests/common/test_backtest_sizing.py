#!/usr/bin/env python3
"""Running a strategy at somebody else's size, and only from the right bars.

Two failures are being guarded here, and both produce a complete, plausible
set of results rather than an error:

  * a size-matched run that quietly falls back to MAX_SHARES=100 on some or all
    rows, and is filed as size-matched anyway;
  * an offline run over a Databento (raw) cache that fetches a miss from IB and
    gets a SPLIT-ADJUSTED frame, leaving the output half of each basis with
    nothing on disk saying which trades came from where.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from common import backtest as B


def summary(tmp_path, rows, fields=None):
    fields = fields or ["symbol", "date", "shares", "max_position"]
    p = tmp_path / "summary.csv"
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return p


# --- reading the sizes ------------------------------------------------------

def test_size_comes_from_max_position_not_from_shares(tmp_path):
    """`shares` is every share transacted in BOTH directions -- a day that
    bought and sold 1,000 shares four times reports 8,000. Handing that to a
    strategy would fund a position eight times larger than the account ever
    held, and the resulting P/L would look like a strategy result."""
    p = summary(tmp_path, [{"symbol": "AAA", "date": "2026-03-16",
                            "shares": 8000, "max_position": 1000}])
    assert B.load_sizes(p) == {"AAA|2026-03-16": 1000}


def test_a_summary_without_max_position_is_refused(tmp_path, capsys):
    """The older summary format had no max_position. Silently sizing every day
    at the strategy default would be the exact failure this flag exists to
    prevent."""
    p = summary(tmp_path, [{"symbol": "AAA", "date": "2026-03-16",
                            "shares": 8000}],
                fields=["symbol", "date", "shares"])
    with pytest.raises(SystemExit) as e:
        B.load_sizes(p)
    assert "max_position" in str(e.value)


def test_zero_and_unparseable_sizes_are_dropped_not_zeroed(tmp_path):
    """A 0 would reach backtest_session as entry_shares=0, which sizes every
    entry out of existence and reports a day with no trades -- indistinguishable
    from a day the strategy declined."""
    p = summary(tmp_path, [
        {"symbol": "AAA", "date": "2026-03-16", "shares": 1, "max_position": 0},
        {"symbol": "BBB", "date": "2026-03-16", "shares": 1, "max_position": ""},
        {"symbol": "CCC", "date": "2026-03-16", "shares": 1, "max_position": 700},
    ])
    assert B.load_sizes(p) == {"CCC|2026-03-16": 700}


# --- what the strategy is actually asked for --------------------------------

class _IB:
    def disconnect(self):  # pragma: no cover -- offline never calls it
        raise AssertionError("offline must not touch IB")


def runner(tmp_path, strategy, **kw):
    return B.Runner(_IB(), tmp_path / "out", tmp_path / "cache",
                    tmp_path / "state", strategy, **kw)


def test_every_backtestable_strategy_accepts_a_size(tmp_path):
    """If one of them stops accepting entry_shares, the comparison quietly
    becomes 'three strategies at your size and one at 100 shares'."""
    for name in sorted(B.STRATEGY_MODULES):
        r = runner(tmp_path, name)
        assert r.takes_entry_shares, f"{name} cannot be size-matched"


def test_exit_mode_support_is_asked_not_discovered_by_catching_TypeError(tmp_path):
    """The old code ran backtest_session(), caught TypeError, and re-ran
    without the flag. That catches a TypeError raised INSIDE the strategy just
    as happily as a wrong-kwarg one, and then silently re-runs with different
    settings than were requested."""
    assert runner(tmp_path, "vw9_5m").takes_exit_mode is True
    assert runner(tmp_path, "mcl").takes_exit_mode is False
    assert runner(tmp_path, "mc5").takes_exit_mode is False


# --- offline must never reach IB -------------------------------------------

def test_offline_reports_a_cache_miss_rather_than_fetching(tmp_path):
    """bar_cache_db holds RAW Databento bars; IB's history is split-ADJUSTED.
    A single fetched frame landing in that tree makes the run part raw and part
    adjusted, and it does not fail -- it just produces different numbers."""
    r = runner(tmp_path, "mcl", offline=True)
    df, err = r._offline_bars("AAA", "2026-03-16")
    assert df is None
    assert err == "not in cache"


def test_offline_is_off_by_default(tmp_path):
    assert runner(tmp_path, "mcl").offline is False
    assert runner(tmp_path, "mcl").sizes is None
