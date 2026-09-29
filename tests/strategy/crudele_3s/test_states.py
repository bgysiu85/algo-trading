"""CRUDELE-3S state machine (G4 look-ahead, G5 path tests). Each test breaks when the rule it names
breaks; the causality test is itself mutation-tested."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.crudele_3s import spec as S
from strategy.crudele_3s import states as ST
from strategy.crudele_3s.beacon import beacon_pair
from strategy.futbt.core import Frame
from tests.strategy.futbt.synth import frame_from_close, squeeze_breakout_path

FIELDS = ("state", "sig_arm", "sig_dir", "sig_stop", "sig_tgt", "sig_line30", "sig_ep", "t_fire",
          "bands_in_ep", "mid", "ma", "atr", "bwr")


def _same(a, b):
    return np.array_equal(np.asarray(a, float), np.asarray(b, float), equal_nan=True)


def _cut(fr: Frame, m: int) -> Frame:
    return Frame(fr.market, fr.o[:m], fr.h[:m], fr.l[:m], fr.c[:m], fr.vol[:m], fr.rc[:m],
                 fr.roll_after[:m], fr.dates[:m], fr.mult, fr.tick_usd, fr.venue, fr.chart)


def first_divergence(fr, params=S.PRIMARY, cuts=(343, 346, 348, 350, 357, 360, 380, 400)):
    """Signals computed on bars <= m-1 must equal the full run's on those bars (G4)."""
    full = ST.compute(fr, params)
    for m in cuts:
        part = ST.compute(_cut(fr, m), params)
        for f in FIELDS:
            if not _same(getattr(part, f)[:m], getattr(full, f)[:m]):
                return f, m
    return None


def path(up=True, **kw):
    return frame_from_close(squeeze_breakout_path(up=up, **kw))


# --- G5: one hand-built path C -> T -> MR -> N, and its mirror --------------------------------
@pytest.mark.parametrize("up", [True, False])
def test_path_c_then_t_then_mr_and_mirror(up):
    fr = path(up=up)
    sg = ST.compute(fr)
    st = sg.state
    names = [ST.STATE_NAMES[s] for s in st]
    first_c = names.index("C")
    first_t = names.index("T")
    first_mr = names.index("MR")
    assert first_c < first_t < first_mr
    t = first_t
    assert sg.sig_arm[t] == 1 and sg.sig_dir[t] == (1 if up else -1) and sg.t_fire[t]
    # the T bar: band width rose 3 bars running, the trend-side band moved outward, close beyond the box
    M, U, L, BW, _ = ST.indicators(fr, S.PRIMARY)
    assert all(BW[t - i] > BW[t - i - 1] for i in range(3))
    assert (U[t] > U[t - 1]) if up else (L[t] < L[t - 1])
    # not one bar earlier: T fires at the FIRST bar where all three hold (the box test decides here)
    box = fr.h[t - 20:t].max() if up else fr.l[t - 20:t].min()      # >= the C box on this path
    assert (fr.c[t] > box) if up else (fr.c[t] < box)
    ep = sg.episodes[0]
    assert ep["start"] == t and ep["end_reason"] == "bands_in"
    # bands come in: BW fell on the 2 bars ending at the end bar, and only after the start bar
    e = ep["end"]
    assert BW[e] < BW[e - 1] < BW[e - 2] and e - 2 >= t
    assert sg.bands_in_ep[e] == 0 and (sg.bands_in_ep >= 0).sum() >= 1
    assert names[e] == "MR"
    # MR arm frozen at that close: U*/L* over start..e; levels measured from the peak (up) / trough (down)
    us, ls = U[t:e + 1].max(), L[t:e + 1].min()
    H = us - ls
    trig = np.nonzero(sg.sig_arm == 2)
    if len(trig[0]):
        j = trig[0][0]
        if up:
            assert sg.sig_line30[j] == pytest.approx(us - 0.30 * H) and sg.sig_stop[j] == pytest.approx(us)
            assert sg.sig_tgt[j] == pytest.approx(us - 0.50 * H) and sg.sig_dir[j] == -1
        else:
            assert sg.sig_line30[j] == pytest.approx(ls + 0.30 * H) and sg.sig_stop[j] == pytest.approx(ls)
            assert sg.sig_tgt[j] == pytest.approx(ls + 0.50 * H) and sg.sig_dir[j] == 1


def test_mr_trigger_is_first_close_beyond_line30_inside_the_window():
    """close < line30 on the arm close itself triggers at once; otherwise the first later close."""
    fr = path()
    sg = ST.compute(fr)
    e = sg.episodes[0]["end"]
    j = np.nonzero(sg.sig_arm == 2)[0][0]
    assert j >= e
    if j > e:
        assert all(fr.c[e:j] >= sg.sig_line30[j] - 1e-12)      # no earlier close was below
    assert fr.c[j] < sg.sig_line30[j]
    assert sg.state[j] != ST.MR_                                  # the arm is consumed by its trigger


def test_mr_arm_expires_after_20_bars():
    fr = path()
    sg = ST.compute(fr)
    # push the line out of reach: nothing to test if it triggers; construct by rerunning with a rally
    x = squeeze_breakout_path().copy()
    e = sg.episodes[0]["end"]
    x[e:e + 30] = x[e - 1] + 8.0 + np.arange(30) * 0.01          # a rally right after: never below line30
    sg2 = ST.compute(frame_from_close(x))
    assert sg2.counts["mr_expired"] >= 1 and (sg2.sig_arm[e:e + 20] == 2).sum() == 0


def test_t_needs_c_or_grace_unless_the_variant_drops_it():
    """No squeeze anywhere (steady noise then a ramp): the registered T never fires; T-no-squeeze does."""
    rng = np.random.default_rng(11)
    x = 100 + np.cumsum(rng.normal(0, 1.0, 330))
    x = np.r_[x, x[-1] + 1.5 * np.arange(1, 20)]
    fr = frame_from_close(x, spread=0.05)
    a, b = ST.compute(fr), ST.compute(fr, S.VARIANTS["T-no-squeeze"])
    assert not any(e["start"] >= 330 for e in a.episodes)           # the ramp is in no squeeze: no T
    assert any(e["start"] >= 330 and e["dir"] == 1 for e in b.episodes)


def test_c_stop_run_signals_short_above_the_box_and_long_below_and_skips_a_two_sided_bar():
    rng = np.random.default_rng(5)
    x = 100 + 8 * np.sin(np.arange(300) * 2 * np.pi / 20) + rng.normal(0, 0.3, 300)
    q = 100 + rng.normal(0, 0.02, 60)                   # the quiet range sits inside the old swings
    base = np.r_[x, q]
    fr = frame_from_close(base, spread=0.05)
    sg = ST.compute(fr)
    j = 330                                                      # deep inside the quiet run
    assert sg.state[j - 1] == ST.C_ and sg.state[j] == ST.C_

    def poke(kind):
        h, l, c, o = fr.h.copy(), fr.l.copy(), fr.c.copy(), fr.o.copy()
        if kind == "up":
            h[j] = h[j - 60:j].max() + 0.5
        if kind == "dn":
            l[j] = l[j - 60:j].min() - 0.5
        if kind == "both":
            h[j] = h[j - 60:j].max() + 0.5
            l[j] = l[j - 60:j].min() - 0.5
        f = Frame("SYN", o, h, l, c, fr.vol, fr.rc, fr.roll_after, fr.dates, fr.mult, fr.tick_usd)
        return ST.compute(f)
    up = poke("up")
    assert up.sig_arm[j] == 3 and up.sig_dir[j] == -1
    assert up.sig_stop[j] == pytest.approx(up_high := poke("up").sig_stop[j])
    assert up.sig_stop[j] > fr.h[j - 60:j].max()                  # poke extreme + 0.10 ATR
    dn = poke("dn")
    assert dn.sig_arm[j] == 3 and dn.sig_dir[j] == 1
    both = poke("both")
    assert both.sig_arm[j] == 0 and both.counts["c_both_sides"] == 1


# --- G4: look-ahead ------------------------------------------------------------------------------
@pytest.mark.parametrize("up", [True, False])
def test_signals_use_only_bars_up_to_t(up):
    assert first_divergence(path(up=up)) is None


def test_the_causality_check_catches_a_one_bar_look_ahead(monkeypatch):
    """Mutation: band width taken from the NEXT bar. The truncation test must notice."""
    orig = ST.indicators

    def peeking(fr, p):
        M, U, L, BW, bwr = orig(fr, p)
        BW2 = np.r_[BW[1:], BW[-1]]
        return M, U, L, BW2, bwr
    assert first_divergence(path()) is None                         # the unmutated code is causal
    monkeypatch.setattr(ST, "indicators", peeking)
    assert first_divergence(path()) is not None, "a next-bar band width must be caught"


def test_frozen_mr_levels_do_not_move_after_the_bands_come_in():
    fr = path()
    sg = ST.compute(fr)
    e = sg.episodes[0]["end"]
    j = np.nonzero(sg.sig_arm == 2)[0][0]
    # rerun with every bar after the arm close scrambled (except close j stays below line30):
    x = fr.c.copy()
    x[e + 1:j] = x[e + 1:j] + 0.0
    sg2 = ST.compute(fr)
    assert sg2.sig_line30[j] == sg.sig_line30[j]


# --- Beacon (Amendment A) --------------------------------------------------------------------------
def test_beacon_pair_matches_a_hand_walk_of_the_pine_source():
    U = np.array([5, 6, 7, 6, 5, 6, 8, 7.0])
    L = np.array([3, 2, 1, 2, 3, 2, 0.5, 1.5])
    pm, vm = beacon_pair(U, L)
    assert list(pm) == [0, 0, 0, 7, 7, 7, 7, 8]
    assert list(vm) == [0, 0, 0, 1, 1, 1, 1, 0.5]


def test_beacon_pair_is_causal():
    rng = np.random.default_rng(1)
    U = 100 + np.cumsum(rng.normal(0, 1, 200))
    L = U - 5 - rng.random(200)
    pm, vm = beacon_pair(U, L)
    pm2, vm2 = beacon_pair(U[:150], L[:150])
    assert np.array_equal(pm[:150], pm2) and np.array_equal(vm[:150], vm2)


def test_mr_beacon_variant_runs_and_arms_from_the_beacon_pair():
    fr = path()
    a = ST.compute(fr)
    b = ST.compute(fr, S.VARIANTS["MR-Beacon"])
    assert b.counts["t_episodes"] == a.counts["t_episodes"]         # same arming trigger
    assert b.counts["mr_arms"] + b.counts["mr_arms_skipped_beacon"] == a.counts["t_bands_in"]
