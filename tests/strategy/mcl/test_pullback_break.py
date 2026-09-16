#!/usr/bin/env python3
"""MCL-PB v2 against its registration, clause by clause.

`MCL.signals` is replaced with a hand-built frame so MACD can be forced on the
exact bar a test needs. The replacement is seen by MCL's own engine too, which
is the point: the exit under test is the published one, not a copy.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mcl import mcl as MCL
from strategy.mcl import pullback_break as PB

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 11)


def frame(bars, macd_closed=(), start=dtime(4, 0)):
    """bars = [(o, h, l, c)]; macd_closed = rows where macd <= signal."""
    t0 = datetime.combine(DAY, start, tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(bars))])
    d = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    d["volume"] = 10_000
    d["macd"], d["macd_sig"] = 1.0, 0.0
    for r in macd_closed:
        d.iloc[r, d.columns.get_loc("macd")] = -1.0
    d["entry"] = False
    d["exit_sig"] = False
    return d


@pytest.fixture
def patched(monkeypatch):
    holder = {}
    monkeypatch.setattr(MCL, "signals",
                        lambda df, require_macd_pos=None: holder["sig"].copy())

    def run(sig, **kw):
        holder["sig"] = sig
        return PB.backtest_session_detail(
            sig[["open", "high", "low", "close", "volume"]], DAY, ET,
            entry_shares=100, **kw)
    return run


G = (5.00, 5.02, 4.99, 5.01)            # a quiet green bar
R = (5.01, 5.02, 4.98, 4.99)            # a quiet red bar


def test_peak_two_reds_break(patched):
    sig = frame([G,
                 (5.00, 5.10, 5.00, 5.08),   # 1 peak 5.10 (green)
                 (5.07, 5.08, 5.04, 5.05),   # 2 red
                 (5.05, 5.07, 5.03, 5.04),   # 3 red -> armed
                 (5.05, 5.15, 5.04, 5.14),   # 4 breaks 5.11
                 (5.14, 5.15, 5.13, 5.14), G])
    r = patched(sig)
    (t,) = r.trades
    assert pd.Timestamp(t.entry_time) == sig.index[4]
    assert t.entry_price == pytest.approx(5.12)
    s = [x for x in r.setups if x.outcome == PB.TRIGGERED][0]
    assert s.peak == pytest.approx(5.10) and s.reds == 2 and s.armed_at == 3


def test_one_red_bar_is_not_a_pullback(patched):
    sig = frame([G, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.04, 5.05),
                 (5.05, 5.15, 5.04, 5.14), (5.14, 5.15, 5.13, 5.14), G])
    assert patched(sig).trades == []


def test_a_red_peak_bar_counts_as_the_first_red(patched):
    """AEHL 09:13: the bar that made the high closed red; 09:14 red; 09:16 broke."""
    sig = frame([G,
                 (5.09, 5.10, 5.00, 5.02),   # 1 peak 5.10, red
                 (5.03, 5.06, 5.01, 5.02),   # 2 red -> armed
                 (5.03, 5.08, 5.02, 5.06),   # 3 green, no break
                 (5.06, 5.15, 5.05, 5.14),   # 4 breaks
                 (5.14, 5.15, 5.13, 5.14), G])
    (t,) = patched(sig).trades
    assert pd.Timestamp(t.entry_time) == sig.index[4]


def test_a_doji_is_not_red(patched):
    sig = frame([G, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.04, 5.05),
                 (5.05, 5.08, 5.04, 5.05),   # doji: would be the 2nd red
                 (5.05, 5.15, 5.04, 5.14), (5.14, 5.15, 5.13, 5.14), G])
    assert patched(sig).trades == []


def test_macd_closed_on_the_completed_bar_refuses_and_the_break_is_the_new_peak(patched):
    sig = frame([G,
                 (5.00, 5.10, 5.00, 5.08),   # 1 peak
                 (5.07, 5.08, 5.04, 5.05),   # 2 red
                 (5.05, 5.07, 5.03, 5.04),   # 3 red, MACD closed
                 (5.05, 5.15, 5.04, 5.14),   # 4 break refused -> peak 5.15
                 (5.13, 5.14, 5.10, 5.11),   # 5 red
                 (5.11, 5.12, 5.08, 5.09),   # 6 red -> armed
                 (5.10, 5.20, 5.09, 5.19),   # 7 breaks 5.16
                 (5.19, 5.20, 5.18, 5.19), G], macd_closed=[3])
    r = patched(sig)
    (t,) = r.trades
    assert pd.Timestamp(t.entry_time) == sig.index[7]
    assert t.entry_price == pytest.approx(5.17)
    assert [s.outcome for s in r.setups][0] == PB.REFUSED_MACD


def test_macd_is_read_on_the_completed_bar_not_the_break_bar(patched):
    sig = frame([G, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.04, 5.05),
                 (5.05, 5.07, 5.03, 5.04), (5.05, 5.15, 5.04, 5.14),
                 (5.14, 5.15, 5.13, 5.14), G], macd_closed=[4])
    assert len(patched(sig).trades) == 1


def test_no_depth_cancel_a_deep_pullback_still_breaks(patched):
    """AEHL 07:59: 20% below the peak, then through it."""
    sig = frame([G, (5.00, 6.00, 5.00, 5.90), (5.80, 5.85, 5.00, 5.10),
                 (5.10, 5.12, 4.70, 4.80), (4.80, 4.90, 4.75, 4.85),
                 (4.90, 6.10, 4.88, 6.05), (6.05, 6.06, 6.0, 6.02), G])
    (t,) = patched(sig).trades
    assert t.entry_price == pytest.approx(6.02)


def test_time_limit_expires_the_peak(patched):
    bars = [G, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.04, 5.05), (5.05, 5.07, 5.03, 5.04)]
    bars += [(5.04, 5.05, 5.03, 5.04)] * 58          # rows 4..61, quiet, no break
    bars += [(5.05, 5.15, 5.04, 5.14), (5.14, 5.15, 5.13, 5.14), G]   # break at row 62: 61 bars after
    r = patched(frame(bars))
    assert r.trades == []
    assert [s.outcome for s in r.setups][0] == PB.EXPIRED


def test_break_within_the_limit_fires(patched):
    bars = [G, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.04, 5.05), (5.05, 5.07, 5.03, 5.04)]
    bars += [(5.04, 5.05, 5.03, 5.04)] * 57          # rows 4..60
    bars += [(5.05, 5.15, 5.04, 5.14), (5.14, 5.15, 5.13, 5.14), G]   # break at row 61
    assert len(patched(frame(bars)).trades) == 1


def test_never_on_the_final_session_bar(patched):
    sig = frame([G, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.04, 5.05),
                 (5.05, 5.07, 5.03, 5.04), (5.05, 5.15, 5.04, 5.14)])
    r = patched(sig)
    assert r.trades == [] and PB.WINDOW in [x.outcome for x in r.setups]


def test_the_floor_blocks_the_trigger_but_the_peak_is_still_built(patched):
    sig = frame([G, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.04, 5.05),
                 (5.05, 5.07, 5.03, 5.04), (5.05, 5.15, 5.04, 5.14),
                 (5.13, 5.14, 5.10, 5.11), (5.11, 5.12, 5.08, 5.09),
                 (5.10, 5.20, 5.09, 5.19), (5.19, 5.20, 5.18, 5.19), G])
    r = patched(sig, not_before=dtime(4, 5))
    (t,) = r.trades
    assert pd.Timestamp(t.entry_time) == sig.index[7]      # the second break
    assert t.entry_price == pytest.approx(5.17)             # measured off peak 5.15


def test_the_peak_made_inside_a_trade_is_the_next_setups_peak(patched):
    bars = [G,
            (5.00, 5.10, 5.00, 5.08),   # 1 peak
            (5.07, 5.08, 5.04, 5.05),   # 2 red
            (5.05, 5.07, 5.03, 5.04),   # 3 red -> armed
            (5.05, 5.15, 5.04, 5.14),   # 4 buy 5.12; in trade
            (5.14, 5.40, 5.13, 5.38),   # 5 new peak 5.40 inside the trade
            (5.38, 5.39, 5.30, 5.31),   # 6 red
            (5.31, 5.32, 5.05, 5.06),   # 7 red; trail 5.13 -> out
            (5.06, 5.45, 5.05, 5.44),   # 8 breaks 5.41 -> buy 5.42
            (5.44, 5.45, 5.43, 5.44), G]
    r = patched(frame(bars))
    assert [t.entry_price for t in r.trades] == pytest.approx([5.12, 5.42])
    assert r.trades[0].reason == "trailing_stop"


def test_no_trigger_on_the_exit_bar_itself(patched):
    bars = [G, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.04, 5.05),
            (5.05, 5.07, 5.03, 5.04), (5.05, 5.15, 5.04, 5.14),   # 4 buy
            (5.14, 5.40, 5.13, 5.38),   # 5 peak 5.40 in trade
            (5.38, 5.39, 5.30, 5.31),   # 6 red
            (5.31, 5.32, 5.15, 5.20),   # 7 red -> armed
            (5.20, 5.45, 5.05, 5.06),   # 8 trail hit AND through 5.41 -- no entry
            (5.06, 5.10, 5.05, 5.08), G]
    r = patched(frame(bars))
    assert len(r.trades) == 1 and r.trades[0].reason == "trailing_stop"


def test_target_cents_reaches_the_engine(patched):
    sig = frame([G, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.04, 5.05),
                 (5.05, 5.07, 5.03, 5.04), (5.05, 5.15, 5.04, 5.14),
                 (5.14, 5.30, 5.13, 5.28), (5.28, 5.29, 5.27, 5.28), G])
    (t,) = patched(sig, target_cents=0.10).trades
    assert t.reason == "target" and t.exit_price == pytest.approx(5.22)


def test_engine_owned_kwargs_are_refused():
    with pytest.raises(TypeError):
        PB.backtest_session_detail(frame([G]), DAY, ET, entry_bars=None)


def test_band_refusal_is_recorded(patched):
    bars = [(1.50, 1.51, 1.49, 1.50), (1.40, 1.60, 1.40, 1.55), (1.55, 1.56, 1.50, 1.52),
            (1.52, 1.53, 1.49, 1.50), (1.51, 1.70, 1.50, 1.69), (1.69, 1.70, 1.68, 1.69), G]
    r = patched(frame(bars))
    assert r.trades == [] and PB.BAND in [s.outcome for s in r.setups]


def test_two_levels_live_at_once_the_AEHL_shape(patched):
    """A 6.79 top, a pullback whose bounce tops at 6.20, then 6.21 is bought
    (07:33) and, after that trade, 6.80 is bought (07:58)."""
    bars = [G,
            (6.00, 6.79, 6.00, 6.70),   # 1 outer top
            (6.70, 6.72, 6.10, 6.15),   # 2 red
            (6.15, 6.16, 5.80, 5.90),   # 3 red -> level 6.79
            (5.90, 6.05, 5.85, 6.00),   # 4 up: candidate 6.05
            (6.02, 6.20, 6.00, 6.10),   # 5 inner top 6.20
            (6.10, 6.12, 5.95, 5.98),   # 6 red
            (5.98, 6.00, 5.90, 5.93),   # 7 red -> level 6.20
            (5.95, 6.50, 5.94, 6.45),   # 8 breaks 6.21 -> buy 6.22; peak 6.50 in trade
            (6.45, 6.46, 6.30, 6.32),   # 9 red
            (6.32, 6.33, 6.10, 6.12),   # 10 red; trail 6.175 hit -> out; level 6.50
            (6.12, 6.20, 6.10, 6.18),
            (6.18, 7.20, 6.15, 7.10),   # 12 through 6.51 AND 6.80: one buy at 6.52
            (7.10, 7.15, 7.05, 7.12), G]
    r = patched(frame(bars))
    assert [t.entry_price for t in r.trades] == pytest.approx([6.22, 6.52])
    ends = {(s.peak, s.outcome) for s in r.setups}
    assert (6.79, PB.REFUSED_BUSY) in ends       # crossed on the bar that bought 6.51


def test_a_lower_high_in_a_decline_is_not_a_swing_high(patched):
    """After the 6.79 top: 6.10, 6.02, 5.95 -- lower highs, each followed by red
    bars. None is a level; the first break of any of them is not a trade."""
    bars = [G,
            (6.00, 6.79, 6.00, 6.70),
            (6.70, 6.72, 6.10, 6.15), (6.15, 6.16, 5.80, 5.90),   # level 6.79
            (5.95, 6.10, 5.70, 5.75),   # 4 lower high, red
            (5.75, 6.02, 5.60, 5.65),   # 5 lower high, red
            (5.65, 5.95, 5.50, 5.55),   # 6 lower high, red
            (5.55, 6.15, 5.54, 6.12),   # 7 through 6.11 and 6.03 -- nothing live there
            (6.12, 6.14, 6.10, 6.13), G]
    r = patched(frame(bars))
    assert r.trades == []
    assert all(s.peak == pytest.approx(6.79) for s in r.setups)
