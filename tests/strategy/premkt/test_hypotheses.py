#!/usr/bin/env python3
"""The three registered signals do what the registration says, and no more.

docs/premarket_hypotheses_20260908.md fixes every rule. These tests hold the
code to the text: where the code and the document disagree, the document
wins and the code is wrong. Each test names the clause it enforces.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from strategy.premkt import hypotheses as H
from strategy.premkt import run as R

ET = ZoneInfo("America/New_York")
DAY = date(2026, 1, 7)


def session(closes, volumes=None, start="04:00", day=DAY, highs=None):
    """1-minute bars from `start` ET on `day`, one per element."""
    n = len(closes)
    t0 = pd.Timestamp(f"{day} {start}", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)]).tz_convert("UTC")
    closes = np.asarray(closes, dtype=float)
    highs = closes * 1.001 if highs is None else np.asarray(highs, dtype=float)
    vols = np.full(n, 1000.0) if volumes is None else np.asarray(volumes, dtype=float)
    return pd.DataFrame({"open": closes, "high": highs, "low": closes * 0.999,
                         "close": closes, "volume": vols}, index=idx)


# --- H0: "the first bar at or after 04:30 ET" ---------------------------------------

def test_h0_marks_exactly_the_first_bar_at_or_after_0430():
    df = session([5.0] * 60)                         # 04:00 .. 04:59
    out = H.signal_h0(df, DAY, ET)
    hit = np.flatnonzero(out["entry"].to_numpy())
    assert list(hit) == [30], "04:30 is bar index 30"


def test_h0_marks_nothing_if_the_session_has_no_bar_after_0430():
    df = session([5.0] * 20)                         # ends 04:19
    assert not H.signal_h0(df, DAY, ET)["entry"].any()


def test_h0_does_not_skip_to_a_later_in_band_bar():
    """The registered rule is THE FIRST bar at/after 04:30, in band or not.
    If it is $25, there is no H0 trade that day -- the harness's band check
    then rejects the fill, and no later bar may be substituted."""
    closes = [5.0] * 30 + [25.0] + [5.0] * 29
    out = H.signal_h0(session(closes), DAY, ET)
    assert list(np.flatnonzero(out["entry"].to_numpy())) == [30]


def test_h0_ignores_yesterdays_bars():
    """The cache holds three sessions. Only DAY's bars count."""
    yday = session([5.0] * 60, day=DAY - timedelta(days=1))
    today = session([5.0] * 60)
    out = H.signal_h0(pd.concat([yday, today]), DAY, ET)
    hit = np.flatnonzero(out["entry"].to_numpy())
    assert list(hit) == [60 + 30]


# --- H1: "close > max(high of all prior bars this session) and volume >= 2x" --------

def test_h1_needs_fifteen_prior_bars():
    closes = [5.0 + 0.01 * i for i in range(40)]     # every bar a new high
    vols = [1000.0] * 40
    vols[10] = 5000.0                                # 2x at bar 10: too early
    vols[20] = 5000.0                                # 2x at bar 20: allowed
    out = H.signal_h1(session(closes, vols), DAY, ET)
    hit = list(np.flatnonzero(out["entry"].to_numpy()))
    assert 10 not in hit, "bar 10 has only 10 prior bars, below the 15 required"
    assert 20 in hit


def test_h1_requires_a_new_session_high_not_just_volume():
    closes = [5.0] * 40
    vols = [1000.0] * 40
    vols[20] = 5000.0
    out = H.signal_h1(session(closes, vols), DAY, ET)
    assert not out["entry"].any(), "flat price is not a new high"


def test_h1_the_bar_is_not_its_own_reference():
    """close > PRIOR highs, volume >= 2x PRIOR mean. A bar that is the only
    big-volume bar must still qualify; including itself in the mean would
    raise the threshold it is measured against."""
    closes = [5.0] * 20 + [5.10]
    vols = [1000.0] * 20 + [2000.0]                  # exactly 2x the prior mean
    out = H.signal_h1(session(closes, vols), DAY, ET)
    assert bool(out["entry"].iloc[-1])


def test_h1_session_high_restarts_each_session():
    """Yesterday closed at $9. Today opens at $5 and makes new highs of ITS
    OWN session. Those are H1 entries; yesterday's $9 is not a ceiling."""
    yday = session([9.0] * 60, day=DAY - timedelta(days=1))
    closes = [5.0 + 0.01 * i for i in range(40)]
    vols = [1000.0] * 40
    vols[20] = 5000.0
    out = H.signal_h1(pd.concat([yday, session(closes, vols)]), DAY, ET)
    assert bool(out["entry"].iloc[60 + 20])


# --- H2: "range 04:00-04:29, >= 10 bars, first break after 04:30 on 2x volume" ------

def test_h2_breaks_the_range_high_on_volume_after_0430():
    closes = [5.0] * 30 + [5.0] * 5 + [5.20] + [5.0] * 24
    vols = [1000.0] * 30 + [1000.0] * 5 + [2500.0] + [1000.0] * 24
    out = H.signal_h2(session(closes, vols), DAY, ET)
    assert list(np.flatnonzero(out["entry"].to_numpy())) == [35]


def test_h2_marks_only_the_first_break():
    closes = [5.0] * 30 + [5.20, 5.0, 5.30] + [5.0] * 27
    vols = [1000.0] * 30 + [2500.0, 1000.0, 2500.0] + [1000.0] * 27
    out = H.signal_h2(session(closes, vols), DAY, ET)
    assert list(np.flatnonzero(out["entry"].to_numpy())) == [30]


def test_h2_needs_ten_range_bars():
    closes = [5.0] * 5 + [5.20] + [5.0] * 10        # starts 04:25: 5 range bars
    vols = [1000.0] * 5 + [2500.0] + [1000.0] * 10
    out = H.signal_h2(session(closes, vols, start="04:25"), DAY, ET)
    assert not out["entry"].any()


def test_h2_a_break_inside_the_range_window_does_not_count():
    """A bar at 04:20 above the running high is part of the range, not a
    break of it -- the range is not defined until 04:30."""
    closes = [5.0] * 20 + [5.50] + [5.0] * 39
    vols = [1000.0] * 20 + [9000.0] + [1000.0] * 39
    out = H.signal_h2(session(closes, vols), DAY, ET)
    assert not out["entry"].any()


def test_h2_volume_is_against_the_range_mean_not_the_prior_bar():
    closes = [5.0] * 30 + [5.20] + [5.0] * 29
    vols = [1000.0] * 29 + [8000.0] + [2500.0] + [1000.0] * 29
    # range mean = (29*1000 + 8000)/30 = 1233; 2500 >= 2x1233 -> entry
    out = H.signal_h2(session(closes, vols), DAY, ET)
    assert bool(out["entry"].iloc[30])


# --- the shared exit -------------------------------------------------------------------

def test_the_rules_are_the_registered_ones():
    r = H.rules()
    assert r.exits.trail_pct == 8.0
    assert r.exits.use_exit_signal is False, "there is no exit signal, by design"
    assert r.exits.target_r is None and r.exits.stop_pct is None
    assert r.max_entries_per_session == 1
    assert (r.price_min, r.price_max, r.enforce_price_band) == (2.0, 20.0, True)
    assert r.commission_plan == "ibkr_tiered"
    assert r.gap_fills and not r.seed_peak_with_bar_high and r.stop_wins_ties


def test_the_registered_constants_have_not_moved():
    """If any of these change, docs/premarket_hypotheses_20260908.md is no
    longer what is being run, and that is the one thing the registration
    forbids."""
    assert (H.VOL_MULT, H.H1_MIN_PRIOR_BARS, H.H2_MIN_RANGE_BARS) == (2.0, 15, 10)
    assert H.TRAIL_PRIMARY == 8.0 and set(H.TRAILS_ROBUSTNESS) == {5.0, 12.0}
    assert H.ENTRY_SHARES == 100 and H.FRICTION_PER_RT == 4.26


# --- scoring -----------------------------------------------------------------------

def _trade(sym, day, net):
    return {"symbol": sym, "date": day, "net": net}


def test_score_charges_friction_on_every_trade():
    s = R.score([_trade("A", "2025-01-01", 10.0), _trade("B", "2025-06-01", 10.0)],
                split="2025-04-08")
    assert s["net"] == pytest.approx(20.0 - 2 * H.FRICTION_PER_RT)
    assert s["early"] == pytest.approx(10.0 - H.FRICTION_PER_RT)
    assert s["late"] == pytest.approx(10.0 - H.FRICTION_PER_RT)


def test_drop_top_removes_whole_symbols_not_trades():
    trades = [_trade("A", "2025-01-01", 100.0), _trade("A", "2025-01-02", 100.0),
              _trade("B", "2025-01-01", 5.0), _trade("C", "2025-01-01", 5.0)]
    s = R.score(trades, "2025-04-08")
    f = H.FRICTION_PER_RT
    assert s["drop_top"][1] == pytest.approx((5 - f) + (5 - f))


def test_criterion_7_is_the_sign_at_the_primary_trail():
    good = {"net": 100.0, "net_per_trade": 1.0, "drop_top": {5: 50.0},
            "early": 50.0, "late": 50.0, "trades": 300, "symbols": 150}
    b0 = {"net_per_trade": 0.5, "drop_top": {5: 10.0}}
    rej = {"trades": 0, "net_per_trade": 0.0}
    robust_ok = {5.0: {"net": 20.0}, 12.0: {"net": 30.0}}
    robust_bad = {5.0: {"net": -20.0}, 12.0: {"net": 30.0}}
    assert dict((c[0][0], c[1]) for c in R.criteria(good, b0, rej, robust_ok))["7"]
    assert not dict((c[0][0], c[1]) for c in R.criteria(good, b0, rej, robust_bad))["7"]


def test_criterion_5_rejects_the_mirror_image():
    s = {"net": 100.0, "net_per_trade": 1.0, "drop_top": {5: 50.0},
         "early": 50.0, "late": 50.0, "trades": 300, "symbols": 150}
    b0 = {"net_per_trade": 0.5, "drop_top": {5: 10.0}}
    bad_rej = {"trades": 100, "net_per_trade": -3.0}
    ok_rej = {"trades": 100, "net_per_trade": 0.5}
    thin = {"trades": 5, "net_per_trade": -9.0}
    c = lambda rej: dict((x[0][0], x[1]) for x in R.criteria(s, b0, rej, {}))["5"]
    assert not c(bad_rej), "profitable on kept days, losing on discarded ones"
    assert c(ok_rej)
    assert c(thin), "too few rejected trades is inconclusive, not a rejection"


# --- the holdout guard -----------------------------------------------------------

def test_the_holdout_can_only_be_spent_once(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "SPENT_PATH", tmp_path / "spent.json")
    R.check_holdout_guard("H1", 8.0)          # unspent: fine
    R.mark_holdout_spent("H1", 8.0)
    R.check_holdout_guard("H1", 8.0)          # exact repeat: allowed
    with pytest.raises(SystemExit, match="REFUSING"):
        R.check_holdout_guard("H2", 8.0)
    with pytest.raises(SystemExit, match="REFUSING"):
        R.check_holdout_guard("H1", 5.0)


def test_training_never_includes_a_locked_date():
    rec = {"lock_from": "2026-01-12", "both_halves_split": "2025-04-08"}
    pairs = [("A", "2025-01-01"), ("A", "2026-01-09"), ("A", "2026-01-12"),
             ("A", "2026-03-01")]
    train = R.select_set(pairs, rec, "training")
    locked = R.select_set(pairs, rec, "locked")
    assert all(d < "2026-01-12" for _, d in train)
    assert all(d >= "2026-01-12" for _, d in locked)
    assert len(train) + len(locked) == len(pairs)


def test_a_repeat_run_does_not_rewrite_the_audit_record(tmp_path, monkeypatch):
    """The first run's timestamp is when the holdout was first seen. A repeat
    is allowed; moving that timestamp is not."""
    monkeypatch.setattr(R, "SPENT_PATH", tmp_path / "spent.json")
    R.mark_holdout_spent("H1", 8.0)
    first = (tmp_path / "spent.json").read_text()
    R.mark_holdout_spent("H1", 8.0)
    assert (tmp_path / "spent.json").read_text() == first
