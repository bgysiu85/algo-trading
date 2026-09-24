"""strategy.h60.rules -- the seven ports (REGISTERED_h60_v0.md §3)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.h60 import rules as R
from tests.strategy.h60 import _synth as S


def arrays(closes, n_days=None, **kw):
    n_days = n_days or len(closes) // 7
    df = S.bars_from_closes("AAA", S.sessions(n_days), closes, **kw)
    return S.panel([df]).arrays("AAA")


# --------------------------------------------------------------------------
# imported, not copied
# --------------------------------------------------------------------------

def test_mcl60_calls_mcl_signals_at_run_time(monkeypatch):
    from strategy.mcl import mcl
    a = S.panel([S.random_walk("AAA", S.sessions(10))]).arrays("AAA")
    real = R.mcl60(a).entry
    assert np.array_equal(real, mcl.signals(a.frame())["entry"].to_numpy(bool))

    def fake(df, **kw):
        out = df.copy()
        out["entry"] = False
        out.iloc[5, out.columns.get_loc("entry")] = True
        return out
    monkeypatch.setattr(mcl, "signals", fake)
    assert list(np.flatnonzero(R.mcl60(a).entry)) == [5]


def test_mc5_60_calls_mc5_signals_at_run_time(monkeypatch):
    from strategy.mc5 import mc5
    a = S.panel([S.random_walk("AAA", S.sessions(10))]).arrays("AAA")
    assert np.array_equal(R.mc5_60(a).entry, mc5.signals(a.frame())["entry"].to_numpy(bool))
    monkeypatch.setattr(mc5, "signals", lambda df, **kw: df.assign(entry=True))
    assert R.mc5_60(a).entry.all()


def test_mcl_and_mc5_exit_is_the_published_five_percent_trail_only():
    a = S.panel([S.random_walk("AAA", S.sessions(10))]).arrays("AAA")
    for fn in (R.mcl60, R.mc5_60):
        spec = fn(a).spec
        assert spec.trail_pct == 5.0 and not spec.close_exit and not spec.fixed_stop
        assert spec.target_r is None and spec.cap_sessions == 5


# --------------------------------------------------------------------------
# ORB-60
# --------------------------------------------------------------------------

def orb_day(bars):
    """closes for one session after a flat warm day; range bar high/low ±1."""
    base = np.full(7, 100.0)
    return np.r_[base, np.asarray(bars, float)]


def test_orb_takes_the_first_close_above_the_first_hours_high_only():
    closes = orb_day([100, 100.5, 101.5, 102, 99, 103, 103])
    highs = np.r_[np.full(7, 100.0), [101.0, 100.6, 101.6, 102.1, 101, 103.1, 103.1]]
    lows = np.r_[np.full(7, 100.0), [99.0, 100.0, 100.4, 101.4, 98.9, 99.2, 102.9]]
    a = arrays(closes, highs=highs, lows=lows, opens=closes)
    out = R.orb60(a)
    assert list(np.flatnonzero(out.entry)) == [7 + 2]         # 11:30 bar, not 12:30
    assert out.stop([9], [101.5])[0] == 99.0                  # the range low
    assert out.spec.fixed_stop and out.spec.trail_pct == 5.0


def test_orb_never_signals_on_the_1530_bar_or_without_a_range_bar():
    closes = orb_day([100, 100, 100, 100, 100, 100, 105])
    highs = np.r_[np.full(7, 100.0), [101, 100, 100, 100, 100, 100, 105]]
    a = arrays(closes, highs=highs, lows=closes - 1, opens=closes)
    assert not R.orb60(a).entry.any()
    days = S.sessions(2)
    df = S.bars_from_closes("AAA", days, np.r_[np.full(7, 100.0), [100, 105, 106, 107, 108, 109, 110]])
    df = df[~((df["session"] == days[1]) & (df["bar"] == 0))]
    a = S.panel([df]).arrays("AAA")
    assert not R.orb60(a).entry.any()


# --------------------------------------------------------------------------
# DON-60
# --------------------------------------------------------------------------

def test_donchian_twenty_bar_break_and_ten_bar_exit():
    closes = np.r_[np.full(21, 100.0), 101.0, np.full(12, 101.0), 98.0]
    closes = np.r_[closes, np.full(35 - len(closes) % 7 if len(closes) % 7 else 0, 98.0)]
    a = arrays(closes, highs=closes, lows=closes, opens=closes)
    out = R.don60(a)
    assert list(np.flatnonzero(out.entry)) == [21]
    assert out.xsig[34] and not out.xsig[33]
    assert out.spec.close_exit and out.spec.trail_pct is None and not out.spec.fixed_stop


# --------------------------------------------------------------------------
# VW9-60
# --------------------------------------------------------------------------

def vw9_case(day2=(100.0, 99.0, 98.0, 97.6, 100.6, 100.8, 101.0), vol=1000.0):
    c0 = np.array([100, 101, 100, 101, 100, 101, 100] * 2, float)
    closes = np.r_[c0, np.asarray(day2, float)]
    opens = np.r_[100.0, closes[:-1]]
    hi = np.maximum(opens, closes) + 0.3
    lo = np.minimum(opens, closes) - 0.3
    return arrays(closes, n_days=3, opens=opens, highs=hi, lows=lo,
                  vols=np.full(len(closes), vol))


def test_vw9_vwap_anchors_at_each_0930_and_ema_atr_are_continuous():
    from common.indicators import atr, ema
    a = vw9_case()
    f = R.vw9_indicators(a)
    for st in (0, 7, 14):
        tp = (a.h[st] + a.l[st] + a.c[st]) / 3.0
        assert f["vwap"].iloc[st] == pytest.approx(tp)
    fr = a.frame()
    np.testing.assert_allclose(f["ema9"], ema(fr["close"], 9))
    np.testing.assert_allclose(f["atr14"], atr(fr["high"], fr["low"], fr["close"], 14))


def test_vw9_setup_a_enters_with_the_structure_stop():
    a = vw9_case()
    out = R.vw9_60(a)
    assert list(np.flatnonzero(out.entry)) == [18]
    assert out.diag["kind"][18] == "A"
    f = R.vw9_indicators(a)
    expected = min(a.l[16], a.l[17]) - 0.10 * f["atr14"].iloc[18]
    assert out.stop([18], [a.o[19]])[0] == pytest.approx(expected)
    assert out.session_cap == 4


def test_vw9_liquidity_gate_is_off_but_the_extension_gate_is_on():
    # $100k bars: the spec's $40k/min x 60 = $2.4m trigger gate would refuse,
    # and the port takes it -- the liquidity gate is off (§3.7)
    a = vw9_case(vol=1000.0)
    assert R.vw9_60(a).entry[18]
    # ...but the VWAP-maturity $ clause stays at its $50k default: $100 bars
    # never mature, so nothing can fire
    assert not R.vw9_60(vw9_case(vol=1.0)).entry.any()
    a = vw9_case(day2=(100.0, 99.0, 98.0, 97.6, 106.0, 106.0, 106.0))
    out = R.vw9_60(a)
    assert not out.entry[18] and out.diag["gate_blocked"]["ext"] == 1


def test_vw9_deployed_exit_is_fixed_2r_with_vwap_lost_and_the_rest_are_reported():
    a = vw9_case()
    d = R.vw9_60(a, "fixed_2r")
    assert d.spec.target_r == 2.0 and d.spec.fixed_stop and d.spec.close_exit
    f = R.vw9_indicators(a)
    assert np.array_equal(d.xsig, (f["close"] <= f["vwap"]).to_numpy())
    e = R.vw9_60(a, "ride_ema9")
    assert e.xsig.sum() >= d.xsig.sum() and e.spec.target_r is None
    assert R.vw9_60(a, "trail_atr").spec.trail_atr == 2.0
    assert R.vw9_60(a, "trail_pct").spec.trail_pct == 5.0
    with pytest.raises(ValueError):
        R.vw9_60(a, "nope")


def test_vw9_find_setups_is_still_apply_indicators_plus_track_setups():
    from strategy.vw9 import vw9
    a = S.panel([S.random_walk("AAA", S.sessions(4), vol=0.01)]).arrays("AAA")
    bars = a.frame()
    assert vw9.find_setups(bars) == vw9.track_setups(vw9.apply_indicators(bars))


# --------------------------------------------------------------------------
# TL-60
# --------------------------------------------------------------------------

def test_tl60_is_gated_on_g4(monkeypatch):
    a = S.panel([S.random_walk("AAA", S.sessions(10))]).arrays("AAA")
    # G4 cleared 2026-09-25 (W01-0006 Done; Ben on W14-0008: "Yes")
    assert R.TL_PARITY_PASSED is True
    assert R.tl60(a, "R5").entry.dtype == bool
    monkeypatch.setattr(R, "TL_PARITY_PASSED", False)
    with pytest.raises(R.NotRegistered, match="G4"):
        R.tl60(a, "R5")


def test_tl60_daily_filter_sees_only_completed_days(monkeypatch):
    import common.tl_v0_lines as L
    a = S.panel([S.random_walk("AAA", S.sessions(12))]).arrays("AAA")
    real_walk = L.walk_line_and_breaks

    def fake_walk(n, pivots, R_, closes, atr, kind):
        line, br = real_walk(n, pivots, R_, closes, atr, kind)
        br = np.zeros(n, bool)
        if kind == "high" and n == 12:        # the DAILY series: break on day 5
            br[5] = True
        return line, br
    monkeypatch.setattr(L, "walk_line_and_breaks", fake_walk)
    f = R.daily_filter(a, 3)
    assert not f[a.s == 5].any()               # the break's own day: not yet
    assert f[a.s == 6].all() and f[a.s == 11].all()


def test_tl60_stop_is_the_signal_bars_support_line_or_the_fallback():
    a = S.panel([S.random_walk("AAA", S.sessions(30), vol=0.01)]).arrays("AAA")
    out = R.tl60_unchecked(a, "R3")
    idx = np.arange(40, a.n - 1)
    st = out.stop(idx, a.o[idx + 1])
    has_line = ~np.isnan(out.ratchet[idx])
    np.testing.assert_allclose(st[has_line], out.ratchet[idx][has_line])
    assert out.spec.ratchet and out.spec.fixed_stop and out.spec.trail_pct is None


def test_tl60_pivot_sizes():
    a = S.panel([S.random_walk("AAA", S.sessions(10))]).arrays("AAA")
    with pytest.raises(ValueError):
        R.tl60_unchecked(a, "R4")


# --------------------------------------------------------------------------
# MR-60 and the registry
# --------------------------------------------------------------------------

def test_mr60_refuses_until_amendment_a():
    a = S.panel([S.random_walk("AAA", S.sessions(3))]).arrays("AAA")
    assert R.MR_AMENDMENT_A is False
    with pytest.raises(R.NotRegistered, match="amendment A"):
        R.mr60(a)


def test_priority_is_section_8s_order():
    assert R.PRIORITY == ("MR-60", "DON-60", "TL-60", "ORB-60", "VW9-60", "MC5-60", "MCL-60")


def test_one_scored_book_per_rule_set_and_tl_is_its_ensemble():
    books = R.books()
    scored = [b.rule for b in books if b.scored]
    assert sorted(scored) == sorted(set(R.PRIORITY) - {"TL-60"})
    sleeves = [b for b in books if b.name in R.ENSEMBLES["TL-60"]]
    assert len(sleeves) == 3
    assert sum(b.notional for b in sleeves) == pytest.approx(10_000.0)
    assert {b.variant for b in books if b.rule == "VW9-60" and b.scored} == {"fixed_2r"}
