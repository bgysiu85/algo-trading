#!/usr/bin/env python3
"""l2_features: G3 pre-run gate (docs/research/REGISTERED_l2_entry.md sec 0).

Every test here is mutation-checked: each one was run once against a
deliberately broken version of the function it covers (the boundary flipped
from `<` to `<=`, a term dropped from the OFI formula, a bucket coerced to
0.0, MC5's bar_min hardcoded to MCL's) and confirmed to fail before being
left in place. None of that data is pulled -- every frame here is
hand-built, because G3 must pass before any real record is read (section 0).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import l2_features as L

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")


def mkrow(**kw):
    row = {"action": "A", "side": "N", "price": float("nan"), "size": 0.0,
           "bid_px_00": 0.0, "ask_px_00": 0.0, "bid_sz_00": 0.0, "ask_sz_00": 0.0}
    row.update(kw)
    return row


def frame(rows: dict[datetime, dict]) -> pd.DataFrame:
    idx = pd.DatetimeIndex(sorted(rows.keys()), tz="UTC")
    df = pd.DataFrame([rows[k] for k in sorted(rows.keys())], index=idx)
    return df


# --- t, per book ------------------------------------------------------------

def test_backtest_entry_instant_matches_quote_price_signal_close():
    """Delegation, not reimplementation -- the two must not be able to drift
    apart the way the H-R1 grain defect happened once already."""
    from common.quote_price import signal_close
    assert (L.backtest_entry_instant("2026-09-18", "04:05", 5)
            == signal_close("2026-09-18", "04:05", 5))


def test_mc5_t_is_the_five_minute_bucket_close_not_one_minute():
    """MC5's t: bar_min=5. Hardcoding MCL's 1 here would read the book one
    bar early on every MC5 entry -- the exact defect this project has
    already found and fixed once (H-R1)."""
    t = L.backtest_entry_instant("2026-09-18", "04:05", 5)
    assert t == datetime(2026, 9, 18, 4, 10, tzinfo=ET)
    mcl = L.backtest_entry_instant("2026-09-18", "04:05", 1)
    assert mcl == datetime(2026, 9, 18, 4, 6, tzinfo=ET)
    assert t != mcl


def test_live_entry_instant_is_the_logged_second_in_et():
    t = L.live_entry_instant("2026-09-22 06:04:01")
    assert t == datetime(2026, 9, 22, 6, 4, 1, tzinfo=ET)


# --- leak control (G3: nothing at or after t is ever read) ------------------

def test_window_excludes_the_record_at_t_but_keeps_the_record_at_lo():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    df = frame({
        lo: mkrow(bid_px_00=10.0, ask_px_00=10.02, bid_sz_00=100, ask_sz_00=100),
        t: mkrow(bid_px_00=99.0, ask_px_00=99.02, bid_sz_00=1, ask_sz_00=1),
    })
    w = L.window(df, t)
    assert len(w) == 1 and w.index[0] == lo


def test_as_of_strict_excludes_ts_itself_inclusive_does_not():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    before = t - timedelta(seconds=1)
    df = frame({
        before: mkrow(bid_px_00=10.0, ask_px_00=10.02, bid_sz_00=1, ask_sz_00=1),
        t: mkrow(bid_px_00=50.0, ask_px_00=50.02, bid_sz_00=1, ask_sz_00=1),
    })
    assert L.as_of(df, t, strict=True)["bid_px_00"] == 10.0
    assert L.as_of(df, t, strict=False)["bid_px_00"] == 50.0


def test_f1_is_blind_to_a_record_stamped_at_t():
    """The mutation this guards: `<` silently becoming `<=` in window()."""
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    df = frame({
        lo: mkrow(bid_px_00=10.0, ask_px_00=10.02, bid_sz_00=100, ask_sz_00=100),
        t: mkrow(bid_px_00=10.0, ask_px_00=10.02, bid_sz_00=1, ask_sz_00=999),
    })
    f = L.f1_quote_imbalance(df, t)
    assert f.bucket == "FLAT" and f.value == 0.0   # balanced state at lo only


def test_d3_reads_the_state_strictly_before_t():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    df = frame({
        t - timedelta(seconds=1): mkrow(bid_px_00=10.0, ask_px_00=10.10, bid_sz_00=1, ask_sz_00=1),
        t: mkrow(bid_px_00=10.0, ask_px_00=20.0, bid_sz_00=1, ask_sz_00=1),
    })
    f = L.d3_spread_pct(df, t)
    assert f.value == pytest.approx((10.10 - 10.0) / 10.05 * 100)


# --- time-weighting -----------------------------------------------------------

def test_f1_time_weights_by_how_long_each_state_stood():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    mid = lo + timedelta(seconds=45)          # state A stands 45s, state B 15s
    df = frame({
        lo: mkrow(bid_px_00=10.0, ask_px_00=10.02, bid_sz_00=300, ask_sz_00=100),   # QI = 0.5
        mid: mkrow(bid_px_00=10.0, ask_px_00=10.02, bid_sz_00=100, ask_sz_00=300),  # QI = -0.5
    })
    f = L.f1_quote_imbalance(df, t)
    expected = (0.5 * 45 + (-0.5) * 15) / 60
    assert f.value == pytest.approx(expected)
    assert f.bucket == ""


def test_an_invalid_state_inside_the_window_does_not_break_the_weighting():
    """A locked/crossed blip does not zero the window -- the prior valid
    state's weight is unaffected by it."""
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    glitch = lo + timedelta(seconds=30)
    df = frame({
        lo: mkrow(bid_px_00=10.0, ask_px_00=10.02, bid_sz_00=300, ask_sz_00=100),
        glitch: mkrow(bid_px_00=10.05, ask_px_00=10.01, bid_sz_00=1, ask_sz_00=1),  # crossed
    })
    f = L.f1_quote_imbalance(df, t)
    assert f.value == pytest.approx(0.5)    # the crossed record contributes nothing


# --- F2: hand-computed five-state case (G3) ------------------------------------

def test_f2_matches_a_hand_computed_five_state_case():
    """S0 (at lo) .. S4, four transitions, summed by hand in the module
    docstring's companion note (this file). Total = 20 + 50 - 60 - 30 = -20."""
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    s1 = lo + timedelta(seconds=10)
    s2 = lo + timedelta(seconds=25)
    s3 = lo + timedelta(seconds=40)
    s4 = lo + timedelta(seconds=50)
    df = frame({
        lo: mkrow(bid_px_00=10.00, bid_sz_00=100, ask_px_00=10.05, ask_sz_00=80),
        s1: mkrow(bid_px_00=10.00, bid_sz_00=120, ask_px_00=10.05, ask_sz_00=80),
        s2: mkrow(bid_px_00=10.01, bid_sz_00=50, ask_px_00=10.05, ask_sz_00=80),
        s3: mkrow(bid_px_00=10.01, bid_sz_00=50, ask_px_00=10.04, ask_sz_00=60),
        s4: mkrow(bid_px_00=10.01, bid_sz_00=50, ask_px_00=10.04, ask_sz_00=90),
    })
    f = L.f2_order_flow_imbalance(df, t)
    assert f.value == pytest.approx(-20.0)
    assert f.bucket == ""


def test_f2_ofi_event_formula_term_by_term():
    """Each of the four terms in isolation, so a dropped or mis-signed term
    fails here even if it happened to cancel out in the five-state case."""
    prev = pd.Series({"bid_px_00": 10.00, "bid_sz_00": 100, "ask_px_00": 10.05, "ask_sz_00": 80})
    bid_up = pd.Series({"bid_px_00": 10.01, "bid_sz_00": 50, "ask_px_00": 10.05, "ask_sz_00": 80})
    assert L._ofi_event(prev, bid_up) == pytest.approx(50.0)          # +qb_cur only
    bid_add = pd.Series({"bid_px_00": 10.00, "bid_sz_00": 150, "ask_px_00": 10.05, "ask_sz_00": 80})
    assert L._ofi_event(prev, bid_add) == pytest.approx(50.0)         # +qb_cur - qb_prev
    ask_down = pd.Series({"bid_px_00": 10.00, "bid_sz_00": 100, "ask_px_00": 10.04, "ask_sz_00": 60})
    assert L._ofi_event(prev, ask_down) == pytest.approx(-60.0)       # -qa_cur only
    ask_add = pd.Series({"bid_px_00": 10.00, "bid_sz_00": 100, "ask_px_00": 10.05, "ask_sz_00": 110})
    assert L._ofi_event(prev, ask_add) == pytest.approx(-30.0)        # +qa_prev - qa_cur


# --- F3 / quote-rule cross-check (G3) ------------------------------------------

def test_f3_aggressor_share_from_the_side_field():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    df = frame({
        lo + timedelta(seconds=1): mkrow(action="T", side="B", price=10.05, size=100),
        lo + timedelta(seconds=2): mkrow(action="T", side="A", price=10.00, size=100),
        lo + timedelta(seconds=3): mkrow(action="T", side="B", price=10.05, size=200),
    })
    f = L.f3_aggressor_share(df, t)
    assert f.value == pytest.approx(300 / 400)
    assert f.bucket == ""


def test_f3_agrees_with_the_quote_rule_on_at_least_95_percent():
    """Synthetic tape built so `side` and the quote rule are DEFINED to
    agree; if classify_by_quote_rule's boundary (>= ask / <= bid) or F3's
    reading of `side` drifts from the docstring's semantics, this fails."""
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    rows = {lo: mkrow(bid_px_00=10.00, ask_px_00=10.02, bid_sz_00=500, ask_sz_00=500)}
    n = 40
    for i in range(n):
        ts = lo + timedelta(seconds=1 + i * 1.0)
        buy = i % 2 == 0
        # a real MBP-1 trade record carries the book snapshot too (merged
        # book+trade stream) -- unchanged here, so it stays a valid `prev`
        # for the next trade.
        rows[ts] = mkrow(action="T", side="B" if buy else "A",
                          price=10.02 if buy else 10.00, size=10,
                          bid_px_00=10.00, ask_px_00=10.02,
                          bid_sz_00=500, ask_sz_00=500)
    df = frame(rows)
    trades = L.window(df, t)
    trades = trades[trades["action"] == "T"]
    qr = L.classify_by_quote_rule(df).reindex(trades.index)
    applies = qr != "N"
    agree = (qr[applies] == trades.loc[applies, "side"]).mean()
    assert applies.mean() == 1.0
    assert agree >= 0.95


def test_classify_by_quote_rule_uses_the_prior_record_not_the_trades_own():
    """The prior record's quote, not the trade's own post-print snapshot --
    a level-clearing print already reflects itself in the same row."""
    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    df = frame({
        t0: mkrow(bid_px_00=10.00, ask_px_00=10.02, bid_sz_00=100, ask_sz_00=50),
        t0 + timedelta(seconds=1): mkrow(action="T", side="B", price=10.02, size=50,
                                          bid_px_00=10.00, ask_px_00=10.05,  # book already moved
                                          bid_sz_00=100, ask_sz_00=40),
    })
    out = L.classify_by_quote_rule(df)
    assert out.iloc[0] == "B"          # 10.02 >= the PRIOR ask (10.02), not the new one (10.05)


# --- buckets are buckets, not zeros (G3) ---------------------------------------

def test_no_book_is_none_not_zero():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    df = frame({t - timedelta(seconds=200): mkrow()})   # nothing anywhere near W
    f = L.f1_quote_imbalance(df, t)
    assert f.bucket == "NO_BOOK" and f.value is None
    g = L.f2_order_flow_imbalance(df, t)
    assert g.bucket == "NO_BOOK" and g.value is None
    d = L.d1_depth_imbalance(df, t)
    assert d.bucket == "NO_BOOK" and d.value is None


def test_no_trades_is_none_not_zero():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    df = frame({lo: mkrow(bid_px_00=10.0, ask_px_00=10.02, bid_sz_00=1, ask_sz_00=1)})
    f = L.f3_aggressor_share(df, t)
    assert f.bucket == "NO_TRADES" and f.value is None


def test_flat_is_a_bucket_when_the_value_is_exactly_zero_or_half():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    df = frame({lo: mkrow(bid_px_00=10.0, ask_px_00=10.02, bid_sz_00=100, ask_sz_00=100)})
    f1 = L.f1_quote_imbalance(df, t)
    assert f1.bucket == "FLAT" and f1.value == 0.0
    df2 = frame({
        lo + timedelta(seconds=1): mkrow(action="T", side="B", price=10.02, size=50),
        lo + timedelta(seconds=2): mkrow(action="T", side="A", price=10.00, size=50),
    })
    f3 = L.f3_aggressor_share(df2, t)
    assert f3.bucket == "FLAT" and f3.value == 0.5


# --- D1/D2 (MBP-10) -------------------------------------------------------------

def mkrow10(**kw):
    row = mkrow()
    for c in L.BID_PX + L.ASK_PX + L.BID_SZ + L.ASK_SZ:
        row.setdefault(c, 0.0)
    row.update(kw)
    return row


def test_d1_sums_all_ten_levels():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    row = mkrow10(bid_px_00=10.0, ask_px_00=10.02)
    for i in range(10):
        row[f"bid_sz_{i:02d}"] = 100
        row[f"ask_sz_{i:02d}"] = 50
    df = frame({lo: row})
    f = L.d1_depth_imbalance(df, t)
    assert f.value == pytest.approx((1000 - 500) / 1500)


def test_d2_ask_depth_change_ratio():
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    lo = t - timedelta(seconds=60)
    before = mkrow10(bid_px_00=10.0, ask_px_00=10.02)
    after = mkrow10(bid_px_00=10.0, ask_px_00=10.02)
    for i in range(10):
        before[f"ask_sz_{i:02d}"] = 100
        after[f"ask_sz_{i:02d}"] = 50
        before[f"bid_sz_{i:02d}"] = after[f"bid_sz_{i:02d}"] = 100
    df = frame({lo: before, t - timedelta(seconds=1): after})
    f = L.d2_ask_depth_change(df, t)
    assert f.value == pytest.approx(500 / 1000)
