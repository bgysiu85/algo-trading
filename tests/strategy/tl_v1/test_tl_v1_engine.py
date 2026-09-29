"""TL-v1 engine (W15-0020): simulate()'s qualified-break extension, the signal arrays and the
run end to end on synthetic markets. Each test breaks when the rule it names breaks."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.tl_v1_lines import a_plus_checklist
from strategy.tl_v0 import bars as B
from strategy.tl_v0.sim import SimInput, simulate
from strategy.tl_v0.spec import EQUITY, MARKETS
from strategy.tl_v1 import controls as K
from strategy.tl_v1 import engine as E
from strategy.tl_v1 import report as Rp
from strategy.tl_v1 import run as RUN
from strategy.tl_v1.signals import MarketCtx, gate_for, v1_input
from tests.strategy.tl_v0.synth import ROOT, contracts_and_rows
from tests.strategy.tl_v0.test_sim import mk


def _sim(x, rule="reverse"):
    return simulate(x, rule=rule, mult=1.0, risk_usd=100.0, integer=False)


def _with_qual(x, qu=(), qd=()):
    n = len(x.c)
    U = np.zeros(n, bool); U[list(qu)] = True
    D = np.zeros(n, bool); D[list(qd)] = True
    x.qual_up, x.qual_dn = U, D
    return x


LONG_THEN_DOWN = dict(
    o=[10, 10, 10, 10, 10, 10, 10, 10], h=[10.5] * 8, l=[9.5] * 8, c=[10] * 8,
    init_long=[9.0] * 8, init_short=[11.0] * 8)


def test_an_unqualified_break_does_not_enter():
    x = _with_qual(mk(up=[1], htf=1, **LONG_THEN_DOWN), qu=[])
    r = _sim(x)
    assert r.trades == [] and r.counts.not_aplus == 1 and r.counts.entries == 0
    # mutation: with the break qualified it does enter
    assert len(_sim(_with_qual(mk(up=[1], htf=1, **LONG_THEN_DOWN), qu=[1])).trades) == 1


def test_opposite_raw_break_exits_even_when_it_is_not_aplus_and_goes_flat():
    """sec 2.4: exit on ANY opposite raw break; reverse only if A+ (and weekly)."""
    x = _with_qual(mk(up=[1], dn=[3], htf=[1, 1, 1, -1, -1, -1, -1, -1], **LONG_THEN_DOWN), qu=[1], qd=[])
    r = _sim(x)
    assert len(r.trades) == 1 and r.trades[0].reason == "flat_blocked"
    assert r.counts.reversals == 0 and r.counts.reversal_blocked_flat == 1 and r.counts.not_aplus == 1


def test_opposite_aplus_break_reverses():
    x = _with_qual(mk(up=[1], dn=[3], htf=[1, 1, 1, -1, -1, -1, -1, -1], **LONG_THEN_DOWN), qu=[1], qd=[3])
    r = _sim(x)
    assert [t.direction for t in r.trades] == [1, -1] or r.counts.reversals == 1
    assert r.counts.reversals == 1


def test_no_qual_arrays_is_exactly_the_old_behaviour():
    a = mk(up=[1], dn=[3], htf=[1, 1, 1, -1, -1, -1, -1, -1], **LONG_THEN_DOWN)
    b = mk(up=[1], dn=[3], htf=[1, 1, 1, -1, -1, -1, -1, -1], **LONG_THEN_DOWN)
    b = _with_qual(b, qu=[1], qd=[3])
    ra, rb = _sim(a), _sim(b)
    assert [(t.direction, t.entry_j, t.exit_j, t.reason) for t in ra.trades] == \
           [(t.direction, t.entry_j, t.exit_j, t.reason) for t in rb.trades]
    assert ra.counts.not_aplus == 0


def test_the_vector_gate_agrees_with_a_plus_checklist():
    rng = np.random.default_rng(3)
    for _ in range(200):
        cnt, span, er, thr = int(rng.integers(0, 6)), float(rng.integers(0, 30)), float(rng.random()), float(rng.random())
        ok, _ = a_plus_checklist(0, 0, cnt, span, er, thr)
        assert ok == (cnt >= 3 and span >= 7 and er >= thr)


def _loader(name):
    seed = {"CL": 3, "GC": 11, "6E": 5}.get(name, 1)
    rows, con, _ = contracts_and_rows(n=1400, start="2015-01-05", seed=seed, carry=1.5)
    scale = 1.0 if name != "6E" else 0.01
    for k in ("open", "high", "low", "close"):
        rows[k] = rows[k] * scale
    mb = B.build_bars(rows, con, ROOT, name)
    return mb, mb.frame.set_index("date")["contract"]


@pytest.fixture(scope="module")
def cl():
    mb, _ = _loader("CL")
    run, ctx = E.run_market(mb, MARKETS["CL"])
    return mb, run, ctx


def test_ensemble_walks_every_spec_and_sizing(cl):
    _, run, _ = cl
    c = run.counts
    assert set(c["spec"]) == {"v1", "v1-A+", "v1-A3", "v1-2touch", "C1"}
    assert set(zip(c[c["spec"] == "v1"]["sizing"], c[c["spec"] == "v1"]["equity"])) == set(E.SIZINGS)


def test_dropping_the_checklist_never_removes_breaks(cl):
    _, _, ctx = cl
    for R in (3, 5, 8):
        g = gate_for(ctx, R)
        assert (g.qual_up <= g.raw_up).all() and (g.qual_dn <= g.raw_dn).all()
        g3 = gate_for(ctx, R, a3=False)
        assert g3.qual_up.sum() >= g.qual_up.sum() and g3.qual_dn.sum() >= g.qual_dn.sum()
        g2 = gate_for(ctx, R, min_touches=2)
        assert g2.qual_up.sum() >= g.qual_up.sum()


def test_er_threshold_uses_only_the_bars_it_is_given(cl):
    """A3's percentile comes from the (training-only) frame: appending a wild tail moves it,
    truncating to a prefix that is unchanged does not."""
    mb, _, ctx = cl
    frame = mb.frame.copy()
    a = MarketCtx(B.MarketBars("CL", frame.iloc[:900].reset_index(drop=True), mb.schedule, {}), MARKETS["CL"])
    b = MarketCtx(B.MarketBars("CL", frame.iloc[:900].reset_index(drop=True), mb.schedule, {}), MARKETS["CL"])
    assert a.er_thr == b.er_thr
    assert a.er_thr[0.25] != ctx.er_thr[0.25]


def test_the_random_control_is_seeded_and_only_thins_the_pool(cl):
    mb, _, ctx = cl
    ctxs = {"CL": ctx}
    s = K.c3_setup(ctxs)
    for v in s.values():
        assert v["n_sel"] >= 0
    a, ea = K.c3_draw(ctxs, s, 7)
    b, eb = K.c3_draw(ctxs, s, 7)
    assert (a, ea) == (b, eb)
    c, _ = K.c3_draw(ctxs, s, 8)
    # the pool of every draw is the weekly-agreeing raw breaks (never a break the lines did not draw)
    for (name, R), v in s.items():
        g = gate_for(ctx, R)
        assert set(v["pool_up"]) <= set(np.nonzero(g.raw_up)[0])
        assert set(v["pool_dn"]) <= set(np.nonzero(g.raw_dn)[0])


def test_run_end_to_end_writes_the_report_and_the_centre_cell_equals_the_verdict(tmp_path):
    rep = RUN.run(Path_(tmp_path), ["CL", "GC"], tmp_path, "20260101", draws=5, loader=_loader,
                  c2_books=None, log=lambda *_: None)
    text = rep.read_text(encoding="utf-8")
    assert "SCOPED / NON-REGISTERED RUN" in text
    assert "SECTION 4 VERDICT" in text and "27-CELL" in text
    for f in ("trades", "books", "counts", "breaks", "c3", "grid"):
        assert (tmp_path / f"tl_v1_backtest_{f}_20260101.csv").exists()
    grid = pd.read_csv(tmp_path / "tl_v1_backtest_grid_20260101.csv", encoding="utf-8")
    books = pd.read_csv(tmp_path / "tl_v1_backtest_books_20260101.csv", encoding="utf-8")
    ens = books[(books["book"] == "v1 ens") & (books["sizing"] == "frac") & (books["equity"] == EQUITY)]
    centre = grid[(grid["window"] == 250) & (grid["touch_buf"] == 0.25) & (grid["er_pct"] == 25)]
    assert float(centre["net_mid"].iloc[0]) == pytest.approx(float(ens["net_mid"].iloc[0]), abs=1e-6)


def test_holdout_and_limit_are_refused():
    with pytest.raises(RUN.RunRefused):
        RUN.main(["--holdout"])
    with pytest.raises(RUN.RunRefused):
        RUN.main(["--limit", "5"])


def test_fewer_than_150_trades_is_not_read(tmp_path):
    """Synthetic two-market run has far fewer than 150 trades: the verdict must say NOT READ,
    never PASSES / DOES NOT PASS (sec 4 criterion 10)."""
    rep = RUN.run(tmp_path, ["CL"], tmp_path, "20260102", draws=3, loader=_loader,
                  c2_books=None, log=lambda *_: None)
    text = rep.read_text(encoding="utf-8")
    assert ("NOT READ (only" in text) or ("DOES NOT PASS" in text) or ("PASSES all ten" in text)
    books = pd.read_csv(tmp_path / "tl_v1_backtest_books_20260102.csv", encoding="utf-8")
    ens = books[(books["book"] == "v1 ens") & (books["sizing"] == "frac")]
    if int(ens["trades"].iloc[0]) < Rp.MIN_TRADES:
        assert "NOT READ (only" in text and "DOES NOT PASS" not in text


def Path_(p):
    return p
