"""TL-v2 engine plumbing (W15-0030): how a retest entry reaches the unchanged simulator, the
look-ahead guard on the real TL-v1 line/gate/weekly arrays, and the run end to end on synthetic
markets. Each test breaks when the rule it names breaks."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.tl_v0 import bars as B
from strategy.tl_v0.sim import simulate
from strategy.tl_v0.spec import MARKETS, PIVOT_SIZES
from strategy.tl_v1.signals import MarketCtx, gate_for
from strategy.tl_v2 import engine as E
from strategy.tl_v2.signals import retest_signals, size_entry, to_sim_input, v2_input
from tests.strategy.tl_v0.synth import ROOT, contracts_and_rows
from tests.strategy.tl_v0.test_sim import mk

FLAT = dict(o=[10] * 10, h=[10.5] * 10, l=[9.5] * 10, c=[10] * 10,
            init_long=[9.0] * 10, init_short=[11.0] * 10)


def _bools(n, at):
    a = np.zeros(n, bool)
    a[list(at)] = True
    return a


def _feed(raw_up=(), raw_dn=(), ent_up=(), ent_dn=(), htf=1, **kw):
    base = mk(htf=htf, **{**FLAT, **kw})
    n = len(base.c)
    return to_sim_input(base, _bools(n, raw_up), _bools(n, raw_dn), _bools(n, ent_up), _bools(n, ent_dn))


def _sim(x, rule="reverse", risk=100.0, integer=False, mult=1.0):
    return simulate(x, rule=rule, mult=mult, risk_usd=risk, integer=integer)


def test_a_raw_break_never_enters_only_the_retest_bar_does():
    r = _sim(_feed(raw_up=[2]))
    assert r.trades == [] and r.counts.entries == 0 and r.counts.not_aplus == 1
    r = _sim(_feed(raw_up=[2], ent_up=[4]))                  # the retest bar is the trigger
    assert len(r.trades) == 1 and r.trades[0].entry_j == 5 and r.trades[0].direction == 1


def test_the_fill_is_the_next_open_and_the_stop_is_the_one_known_at_the_retest_bar():
    o = [10, 10, 10, 10, 10.6, 10.8, 10, 10, 10, 10]
    il = [9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0]
    il[4] = 9.5                                              # the stop AT the retest bar
    r = _sim(_feed(raw_up=[2], ent_up=[4], o=o, init_long=il))
    t = r.trades[0]
    assert t.entry_j == 5 and t.entry_px == 10.8 and t.stop_init == 9.5


def test_the_weekly_filter_is_not_reapplied_at_the_retest_bar():
    """sec 2.1: E2 was applied at the break bar t. The weekly state can have flipped by bar s."""
    htf = [1, 1, 1, 1, -1, -1, -1, -1, -1, -1]              # short weekly on the retest bar 4
    r = _sim(_feed(raw_up=[2], ent_up=[4], htf=htf))
    assert len(r.trades) == 1 and r.trades[0].direction == 1
    # mutation: a plain qualified break at 4 with the same weekly state is blocked
    x = _feed(raw_up=[4], htf=htf)
    assert _sim(x).trades == []


def test_an_opposite_raw_break_exits_and_never_reverses_off_the_raw_break():
    r = _sim(_feed(raw_up=[1], ent_up=[2], raw_dn=[5], htf=1))
    assert [t.reason for t in r.trades] == ["flat_blocked"] and r.counts.reversals == 0
    assert r.counts.reversal_blocked_flat == 1


def test_after_a_raw_exit_the_next_retest_entry_takes_the_market_again():
    r = _sim(_feed(raw_up=[1], ent_up=[2], raw_dn=[4], ent_dn=[7]))
    assert [t.direction for t in r.trades] == [1, -1]
    assert r.trades[0].reason == "flat_blocked" and r.trades[1].entry_j == 8


def test_a_second_retest_entry_in_the_same_direction_is_ignored_while_in_position():
    r = _sim(_feed(raw_up=[1], ent_up=[2, 6]))
    assert len(r.trades) == 1 and r.counts.ignored_in_position >= 1


@pytest.mark.parametrize("d", [1, -1])
def test_size_entry_agrees_with_the_simulator(d):
    n = 10
    o = [10, 10, 10, 10, 10.4, 10.4, 10, 10, 10, 10]
    o = [x if d == 1 else 20 - x for x in o]                # the mirror image for the short
    kw = dict(o=o, h=[max(x, 10) + 0.5 for x in o], l=[min(x, 10) - 0.5 for x in o], c=[10.0] * n,
              init_long=[9.0] * n, init_short=[11.0] * n)
    x = _feed(raw_up=[1] if d == 1 else [], raw_dn=[1] if d == -1 else [],
              ent_up=[3] if d == 1 else [], ent_dn=[3] if d == -1 else [], **kw)
    for risk in (0.5, 30.0, 100.0, 1000.0):
        r = _sim(x, risk=risk, integer=True, mult=1.0)
        z = size_entry(x, 3, d, mult=1.0, risk_usd=risk)
        got = r.trades[0].qty if r.trades else 0
        assert z["contracts"] == int(got), (risk, z, got)
        assert (z["status"] == "sizeable") == bool(r.trades)


def test_size_entry_reports_no_stop_and_void():
    x = _feed(ent_up=[3], init_long=[10.5] * 10)              # stop above the signal close
    assert size_entry(x, 3, 1, mult=1, risk_usd=100)["status"] == "no_stop"
    o = [10, 10, 10, 10, 8.5, 10, 10, 10, 10, 10]
    x = _feed(ent_up=[3], o=o)                                # next open already through the stop
    assert size_entry(x, 3, 1, mult=1, risk_usd=100)["status"] == "void"


# ---- synthetic markets ------------------------------------------------------------------------------

def _loader(name, seed=3, n=1400):
    rows, con, _ = contracts_and_rows(n=n, start="2015-01-05", seed=seed, carry=1.5)
    mb = B.build_bars(rows, con, ROOT, name)
    return mb


@pytest.fixture(scope="module")
def cl():
    mb = _loader("CL")
    return mb, MarketCtx(mb, MARKETS["CL"])


@pytest.fixture(scope="module")
def cl_run(cl):
    mb, ctx = cl
    run, _ = E.run_market(mb, MARKETS["CL"], ctx)
    return run


def test_retest_entries_are_a_subset_of_qualified_breaks_and_start_after_them(cl):
    _, ctx = cl
    total = 0
    for R in PIVOT_SIZES:
        s = retest_signals(ctx, R)
        ev = s.scan.events
        ent = ev[ev["outcome"] == "entry"]
        total += len(ent)
        assert ((ent["s"] > ent["t"]) & (ent["s"] - ent["t"] <= 10)).all()
        for _, e in ent.iterrows():
            q = s.qual_up_w if e["direction"] == 1 else s.qual_dn_w
            assert q[int(e["t"])]                                    # the break was A+ and weekly-ok at t
        assert int(s.scan.ent_up.sum() + s.scan.ent_dn.sum()) == len(ent)
        g = gate_for(ctx, R)
        assert (s.qual_up_w <= g.qual_up).all() and (s.qual_dn_w <= g.qual_dn).all()
    assert total > 0, "the synthetic market must produce at least one retest entry for these tests to bite"


def test_the_window_variant_agrees_with_the_primary_on_every_break_both_of_them_took_up(cl):
    """N = 20 is N = 10 with a longer wait. For a break that starts a setup in BOTH runs the walk is
    identical up to t + 10, so a primary entry is the same entry, and a primary timeout can only turn
    into a later entry or a failure. (The COUNT of entries can still be lower at N = 20: a setup that
    stays pending longer blocks a later same-side break, rule C1.)"""
    _, ctx = cl
    seen = 0
    for R in PIVOT_SIZES:
        a = retest_signals(ctx, R, N=10).scan.events
        b = retest_signals(ctx, R, N=20).scan.events
        m = a[a["outcome"] != "ignored_pending"].merge(
            b[b["outcome"] != "ignored_pending"], on=["t", "direction"], suffixes=("_10", "_20"))
        for _, e in m.iterrows():
            seen += 1
            if e["outcome_10"] == "entry":
                assert e["outcome_20"] == "entry" and e["s_20"] == e["s_10"]
            if e["outcome_10"] == "no_retest":
                assert not (e["outcome_20"] == "entry" and e["s_20"] <= e["t"] + 10)
    assert seen > 0


def test_the_sr_variant_only_ever_filters_the_primary_entries(cl):
    _, ctx = cl
    for R in PIVOT_SIZES:
        a = retest_signals(ctx, R, N=10)
        assert (a.scan.sr_up <= a.scan.ent_up).all() and (a.scan.sr_dn <= a.scan.ent_dn).all()
        x, _ = v2_input(ctx, R, sr=True)
        assert (x.qual_up <= a.scan.ent_up).all() and (x.qual_dn <= a.scan.ent_dn).all()


def test_look_ahead_guard_prefix_invariance_on_the_real_line_gate_and_weekly_arrays(cl):
    """G4: cut the market at bar k and recompute. Every retest signal at a bar < k - 1 must be
    identical; the frozen line, T1/T2 and the A+/weekly gate use nothing after the bar they act on.
    A3's percentile is pinned to the full-sample value (it is a training-side constant by
    registration; its own guard is TL-v1's)."""
    mb, ctx = cl
    for k in (700, 1000, 1300):
        frame = mb.frame.iloc[:k].reset_index(drop=True)
        sub = MarketCtx(B.MarketBars("CL", frame, mb.schedule, {}), MARKETS["CL"])
        sub.er_thr = dict(ctx.er_thr)
        for R in PIVOT_SIZES:
            full = retest_signals(ctx, R)
            cut = retest_signals(sub, R)
            assert np.array_equal(full.scan.ent_up[:k - 1], cut.scan.ent_up[:k - 1]), (k, R)
            assert np.array_equal(full.scan.ent_dn[:k - 1], cut.scan.ent_dn[:k - 1]), (k, R)
            assert np.array_equal(full.qual_up_w[:k - 1], cut.qual_up_w[:k - 1]), (k, R)


def test_the_guard_can_fail_a_signal_that_reads_the_next_bar_differs(cl):
    """Mutation check for the guard above: recompute on a market whose LATER bars are altered and
    show a signal that used them WOULD move. Altering bars after k changes the raw arrays there."""
    mb, ctx = cl
    k = 1000
    frame = mb.frame.copy()
    for col in ("open", "high", "low", "close"):
        frame.loc[k:, col] = frame.loc[k:, col] * 1.4 + 3.0
    alt = MarketCtx(B.MarketBars("CL", frame, mb.schedule, {}), MARKETS["CL"])
    alt.er_thr = dict(ctx.er_thr)
    moved = False
    for R in PIVOT_SIZES:
        full = retest_signals(ctx, R)
        chg = retest_signals(alt, R)
        assert np.array_equal(full.scan.ent_up[:k - 1], chg.scan.ent_up[:k - 1])       # before: unchanged
        moved |= not np.array_equal(full.scan.ent_up[k - 1:], chg.scan.ent_up[k - 1:])
        moved |= not np.array_equal(full.scan.ent_dn[k - 1:], chg.scan.ent_dn[k - 1:])
    assert moved, "altering the later bars changed nothing after k: this fixture cannot detect a leak"


def test_engine_walks_every_spec_and_sizing(cl_run):
    c = cl_run.counts
    assert set(c["spec"]) == {"v2", "v2-SR", "v2-N20", "C1"}
    v2 = c[c["spec"] == "v2"]
    assert set(zip(v2["sizing"], v2["equity"])) == set(E.SIZINGS)


def test_no_trade_enters_before_a_retest_and_every_entry_has_a_qualified_break_behind_it(cl, cl_run):
    _, ctx = cl
    t = cl_run.trades
    v2 = t[(t["spec"] == "v2") & (t["sizing"] == "frac") & (t["share"] == "alone")]
    assert len(v2) > 0
    for R, g in v2.groupby("R"):
        s = retest_signals(ctx, int(R))
        ent_bars = set(np.nonzero(s.scan.ent_up | s.scan.ent_dn)[0])
        assert set(g["entry_j"] - 1) <= ent_bars                     # filled at the open AFTER a retest bar


def test_engine_events_carry_the_registered_outcomes(cl_run):
    ev = cl_run.events
    assert set(ev["outcome"]) <= {"entry", "failed", "no_retest", "open_at_end", "ignored_pending"}
    assert set(ev["spec"]) == {"v2", "v2-N20"}
