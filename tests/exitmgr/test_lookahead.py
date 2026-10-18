"""G4: every rule uses bars <= j-1 for what works in bar j, and bars <= j at the close of j.

Truncation invariance: replace EVERY bar after k with garbage, rebuild the indicators and the support line from the changed series,
and the levels working in bars <= k+1 and every close-of-bar decision at bars <= k must not move. Then a one-bar-shifted (leaky)
version of each component is shown to FAIL the same check, so the test cannot pass by testing nothing."""
import numpy as np
import pytest

from exitmgr import lines as LN
from exitmgr import rules as R
from strategy.chartmark import data as D
from strategy.chartmark import engine as E
from strategy.chartmark import spec as V1
from strategy.chartmark.data import make_frame
from tests.strategy.chartmark.synth import walk

ALL = ("B-STOP", "B-V1", "R-BEN", "R-MOM", "X-ALERT-touch", "X-ALERT-close", "X-JUMP", "R-BEN-EMA", "R-MOM+BEN", "X-JUMP-1R-half")


def prep(fr):
    ind = D.indicators(fr)
    for k in ("atr", "e9", "e21", "hist"):
        setattr(fr, k, getattr(ind, k))
    return ind


def proj_of(fr, ind, L=5, buf=0.10):
    return LN.track(fr.l, fr.c, ind.atr, L, buf)[2]


def garbage_after(fr, k, seed, mode=None):
    rng = np.random.default_rng(seed)
    n = fr.n
    m = n - k - 1
    c = rng.uniform(35, 85, m)
    o = rng.uniform(35, 85, m)
    if mode == "bear":                            # every future bar red: gives a leaky M1 something to see
        o = c + rng.uniform(0.5, 5, m)
    elif mode == "bull":                          # every future bar far higher: gives a leaky swing-low / ratchet something to see
        c, o = rng.uniform(95, 120, m), rng.uniform(95, 120, m)
    h = np.maximum(o, c) + rng.uniform(0, 4, m)
    l = np.minimum(o, c) - rng.uniform(0, 4, m)
    cat = lambda a, b: np.concatenate([a[: k + 1], b])
    return make_frame(fr.t, cat(fr.o, o), cat(fr.h, h), cat(fr.l, l), cat(fr.c, c), cat(fr.v, rng.integers(500, 3000, m)), fr.roll_after, "mut")


def trace(builder, fr, entries, k, proj):
    out = []
    for x in entries:
        if x.e >= k - 3:
            continue
        comps = builder(fr, x, proj)
        for c in comps:
            c.start()
        rec = []
        for j in range(x.e + 1, k + 2):
            rec.append(("L", j, sorted(lv for c in comps for lv in c.levels(j))))
            if j <= k:
                rec.append(("C", j, [c.on_close(j) for c in comps]))
        out.append(rec)
    return out


def real(rule):
    return lambda fr, x, proj: R.build(rule, fr, x.e, x.entry_px, x.a0, x.s0, 0.01, R.BASE, proj)


def world(seed=3, n=3500):
    fr = walk(n=n, seed=seed, drift=0.01, vol=0.2)
    ind = prep(fr)
    trades, _ = E.simulate(fr, ind, V1.BASE)
    from strategy.exit_cmp.entries import Entry
    entries = [Entry(t.entry_j, t.entry_px, t.a0, t.stop0, t.placed_j, t.gap_fill, t.stop_from_entry_bar) for t in trades]
    assert len(entries) > 15
    return fr, ind, entries


@pytest.mark.parametrize("rule", ALL)
@pytest.mark.parametrize("k", [900, 2000])
def test_future_bars_cannot_change_a_decision(rule, k):
    fr, ind, entries = world()
    fb = garbage_after(fr, k, seed=k)
    indb = prep(fb)
    for name in ("atr", "e9", "e21", "hist"):                    # the indicators themselves are causal
        a, b = getattr(ind, name)[: k + 1], getattr(indb, name)[: k + 1]
        assert np.array_equal(a, b, equal_nan=True), name
    ta = trace(real(rule), fr, entries, k, proj_of(fr, ind))
    tb = trace(real(rule), fb, entries, k, proj_of(fb, indb))
    assert len(ta) > 5 and ta == tb


# ---- one-bar-shifted components must be caught -------------------------------------------------------------------
class LeakRatchet(R.Ratchet):
    def on_close(self, j):
        self.hh = max(self.hh, self.b.h[j + 1])
        self._eval()


class LeakRed(R.RedRun):
    def on_close(self, j):
        return super().on_close(j + 1)


class LeakAlert(R.AlertTouch):
    def levels(self, j):
        return super().levels(j + 1)               # reads proj[j]: the line including a pivot confirmed AT bar j


class LeakJump(R.Jump):
    def on_close(self, j):
        return super().on_close(j + 1)


class LeakReversal(R.Reversal):
    def on_close(self, j):
        return super().on_close(j + 1)


def leaky(kind):
    def build(fr, x, proj):
        a = (fr, x.e, x.entry_px, x.a0, x.s0, 0.01)
        cls = {"ratchet": lambda: [R.Floor(*a), LeakRatchet(*a, arm=0.2, frac=0.5)],
               "red": lambda: [R.Floor(*a), LeakRed(*a, run=3)],
               "alert": lambda: [R.Floor(*a), LeakAlert(*a, proj=proj)],
               "jump": lambda: [R.Floor(*a), LeakJump(*a, arm=1.0, L=2)],
               "reversal": lambda: [R.Floor(*a), LeakReversal(*a, tag="M2")]}[kind]
        return cls()
    return build


@pytest.mark.parametrize("kind", ["ratchet", "red", "alert", "jump", "reversal"])
def test_the_check_catches_a_one_bar_leak(kind):
    fr, ind, entries = world(seed=5)
    caught = False
    for k in range(300, 3300, 50):
        if caught:
            break
        for mode in (None, "bear", "bull"):
            fb = garbage_after(fr, k, seed=k, mode=mode)
            indb = prep(fb)
            ta = trace(leaky(kind), fr, entries, k, proj_of(fr, ind))
            tb = trace(leaky(kind), fb, entries, k, proj_of(fb, indb))
            caught |= ta != tb
    assert caught, f"a {kind} component that peeks one bar ahead was NOT detected"
