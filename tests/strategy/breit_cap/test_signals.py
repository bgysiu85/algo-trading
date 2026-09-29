"""BREIT-CAP runs, grade and orders (G4 look-ahead). Each test breaks when the rule it names breaks."""
from __future__ import annotations

import numpy as np
import pytest

from strategy.breit_cap import spec as S
from strategy.breit_cap import signals as SG
from strategy.futbt.core import Frame
from tests.strategy.futbt.synth import frame_from_close

W = 300          # warm-up bars


def run_frame(k=5, step=1.2, up=False, seed=2, vol=None, tail=6, gap_bar=None):
    """quiet warm-up, then an origin bar and a run of k bars each holding the prior bar's high (down)
    or low (up), then `tail` flat bars."""
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.normal(0, 0.15, W))
    o = list(np.r_[base[0], base[:-1]])
    c = list(base)
    h = [max(a, b) + 0.2 for a, b in zip(o, c)]
    l = [min(a, b) - 0.2 for a, b in zip(o, c)]
    sgn = 1 if up else -1
    top = c[-1]
    # origin bar: the extreme in the opposite direction
    O_hi, O_lo = top + 0.4, top - 0.4
    o.append(top); c.append(top + sgn * 0.1); h.append(O_hi); l.append(O_lo)
    for i in range(k):
        pc = c[-1]
        cc = pc + sgn * step
        if not up:
            hh = h[-1] - 0.3                       # holds the prior high
            ll = cc - 0.3
            oo = min(pc, hh - 0.05)
        else:
            ll = l[-1] + 0.3                       # holds the prior low (higher low)
            hh = cc + 0.3
            oo = max(pc, ll + 0.05)
        o.append(oo); c.append(cc); h.append(hh); l.append(ll)
    for i in range(tail):
        o.append(c[-1]); c.append(c[-1]); h.append(c[-1] + 0.2); l.append(c[-1] - 0.2)
    n = len(c)
    fr = frame_from_close(c, mult=1.0, tick_usd=0.01, opens=o, highs=h, lows=l, vol=vol)
    return fr


def test_a_qualified_down_run_places_a_buy_stop_and_the_stop_at_the_lows_of_the_move():
    fr = run_frame(k=5)
    sg = SG.compute(fr)
    t = W + 5                                          # the 5th run bar
    assert sg.ok[0, t] and not sg.ok[1, t]
    assert sg.k[0, t] == 5 and sg.run_id[0, t] == W + 1
    assert sg.entry[0, t] == pytest.approx(fr.h[t] + fr.tick)
    assert sg.stop[0, t] == pytest.approx(fr.l[W + 1:t + 1].min() - fr.tick)
    atr_O = sg.atr[W]
    assert sg.d_atr[0, t] == pytest.approx((fr.h[W] - fr.l[W + 1:t + 1].min()) / atr_O)
    assert sg.d_atr[0, t] >= S.Q2_ATR
    # nothing before the 4th run bar (k < 4)
    assert not sg.ok[0, W:W + 4].any()
    assert sg.ok[0, W + 4]                              # k = 4 is enough


def test_the_short_side_is_the_mirror():
    fr = run_frame(k=5, up=True)
    sg = SG.compute(fr)
    t = W + 5
    assert sg.ok[1, t] and not sg.ok[0, t]
    assert sg.entry[1, t] == pytest.approx(fr.l[t] - fr.tick)
    assert sg.stop[1, t] == pytest.approx(fr.h[W + 1:t + 1].max() + fr.tick)


def test_a_bar_that_does_not_hold_the_prior_high_ends_the_run():
    fr = run_frame(k=6, tail=0)
    h = fr.h.copy()
    h[W + 4] = h[W + 3] + 0.5                           # a higher high inside the run
    f2 = Frame("SYN", fr.o, h, fr.l, fr.c, fr.vol, fr.rc, fr.roll_after, fr.dates, fr.mult, fr.tick_usd)
    sg = SG.compute(f2)
    assert not sg.ok[0, W + 4]                          # the break bar is not part of a run
    assert sg.k[0, W + 6] <= 2 or not sg.ok[0, W + 6]   # what is left (2 bars) is below k_min


def test_q2_size_and_q3_stretch_filters_and_their_counters():
    fr = run_frame(k=5, step=0.15)                      # a shallow drift: fails Q2
    sg = SG.compute(fr)
    assert not sg.ok[:, W:].any() and sg.counts["runs_fail_q2_long"] >= 1
    fr2 = run_frame(k=5)
    sg3 = SG.compute(fr2, S.PRIMARY.with_(q3_sd=9.0))    # no close can be 9 SD outside: fails Q3
    assert not sg3.ok[:, W:].any() and sg3.counts["runs_fail_q3_long"] >= 1
    unf = SG.compute(fr, S.C2_UNFILTERED)                # the unfiltered control takes it
    assert unf.ok[0, W:].any()


def test_atr_is_measured_at_the_origin_not_after_the_move_inflates_it():
    fr = run_frame(k=5)
    sg = SG.compute(fr)
    t = W + 5
    assert sg.atr[t] > 1.5 * sg.atr[W]                  # the move inflates ATR ...
    assert sg.d_atr[0, t] == pytest.approx((fr.h[W] - fr.l[W + 1:t + 1].min()) / sg.atr[W])   # ... D uses ATR[O]


# --- grade ------------------------------------------------------------------------------------------
def test_grade_speed_long_run_and_volume_factors():
    vol = np.full(W + 12, 1000.0)
    fr = run_frame(k=6, vol=vol)
    g0 = SG.compute(fr).grade[0, W + 6]
    vol2 = vol.copy()
    vol2[W + 5] = 5000.0                               # a spike inside the last 3 run bars
    fr2 = run_frame(k=6, vol=vol2)
    g1 = SG.compute(fr2).grade[0, W + 6]
    assert g1 == g0 + 1
    vol3 = vol.copy()
    vol3[W + 3] = 5000.0                               # a spike OUTSIDE the last 3 bars: no credit
    assert SG.compute(run_frame(k=6, vol=vol3)).grade[0, W + 6] == g0
    nan_vol = np.full(W + 12, np.nan)
    assert np.isfinite(SG.compute(run_frame(k=6, vol=nan_vol)).grade[0, W + 6])      # NaN volume -> "no"
    assert SG.compute(run_frame(k=5)).grade[0, W + 5] <= SG.compute(fr).grade[0, W + 6]   # k >= 6 counts


def test_zigzag_counts_down_legs_with_the_atr_reversal():
    h = np.array([10, 9.5, 8.5, 8.9, 9.6, 8.7, 7.0, 7.2, 8.4, 7.4, 5.5, 5.6.__float__()])
    l = h - 0.4
    # leg 1: 10 -> ~8.1 (>= 1 down); bounce to 9.6 (>= 1 off the low 8.1); leg 2 down to ~6.6; bounce 8.4; leg 3 ...
    assert SG.zigzag_legs(h, l, 0, len(h) - 1, 1.0) == 3
    assert SG.zigzag_legs(h, l, 0, 2, 1.0) == 1                    # only the first leg exists yet
    assert SG.zigzag_legs(h, l, 0, len(h) - 1, 50.0) == 0          # nothing reverses that far


def test_grade_risk_bands_and_short_half():
    assert [S.grade_risk(g) for g in range(6)] == [0.005, 0.005, 0.01, 0.01, 0.02, 0.02]


def test_volume_coverage_check_g1():
    v = np.r_[np.full(99, 5.0), 0.0]
    assert SG.volume_coverage(v) == pytest.approx(0.99)
    assert SG.volume_coverage(np.full(10, np.nan)) == 0.0


# --- G4: look-ahead ---------------------------------------------------------------------------------
FIELDS = ("ok", "entry", "stop", "grade", "k", "d_atr", "run_id", "tgt50", "mid", "atr")


def _cut(fr, m):
    return Frame(fr.market, fr.o[:m], fr.h[:m], fr.l[:m], fr.c[:m], fr.vol[:m], fr.rc[:m],
                 fr.roll_after[:m], fr.dates[:m], fr.mult, fr.tick_usd)


def first_divergence(fr, params=S.PRIMARY, cuts=(W + 3, W + 4, W + 5, W + 6, W + 8)):
    full = SG.compute(fr, params)
    for m in cuts:
        part = SG.compute(_cut(fr, m), params)
        for f in FIELDS:
            a, b = np.asarray(getattr(part, f), float), np.asarray(getattr(full, f), float)
            if not np.array_equal(a[..., :m], b[..., :m], equal_nan=True):
                return f, m
    return None


def test_runs_and_grade_use_only_bars_up_to_t():
    vol = np.full(W + 12, 1000.0)
    vol[W + 5] = 5000.0
    assert first_divergence(run_frame(k=6, vol=vol)) is None
    assert first_divergence(run_frame(k=6, up=True, vol=vol)) is None


def test_the_causality_check_catches_a_one_bar_look_ahead(monkeypatch):
    """Mutation: the run's origin ATR read one bar late (atr[O+1], which the move has started to inflate)."""
    fr = run_frame(k=6)
    assert first_divergence(fr) is None
    orig = Frame.atr

    def peeking(self):
        a = orig(self)
        return np.r_[a[1:], a[-1]]
    monkeypatch.setattr(Frame, "atr", peeking)
    assert first_divergence(fr) is not None
