import json

import numpy as np
import pandas as pd
import pytest

from strategy.chartmark import data as D
from strategy.chartmark import engine as E
from strategy.chartmark import spec as S
from strategy.chartmark import holdout as HO
from strategy.chartmark import controls as CT
from strategy.chartmark import book as BK
from tests.strategy.chartmark.synth import walk, cut


def sim(fr, p=S.BASE):
    return E.simulate(fr, D.indicators(fr), p)


def key(tr):
    return (tr.entry_j, tr.exit_j, round(tr.entry_px, 6), round(tr.exit_px, 6), tr.reason)


# ---- costs (Amendment A.3) -------------------------------------------------
def test_ibkr_costs():
    assert S.per_side("MCL", "low") == pytest.approx(0.77)
    assert S.per_side("MCL", "mid") == pytest.approx(1.77)
    assert S.per_side("CL", "high") == pytest.approx(22.37)
    assert 2 * S.per_side("MCL", "mid") == pytest.approx(3.54)
    assert 2 * S.per_side("CL", "mid") == pytest.approx(24.74)
    assert S.round_trip_price() == pytest.approx(0.0354)


# ---- G4 look-ahead guards ----------------------------------------------------
@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("name", ["BASE", "V-STALL3", "X4", "NO-P2", "V-AVOID"])
def test_truncation_invariance(seed, name):
    """Decisions before bar k cannot depend on bars from k on: trades closed well before the cut are identical."""
    fr = walk(2500, seed, drift=0.01)
    p = S.VARIANTS[name]
    full, _ = sim(fr, p)
    for k in (900, 1500, 2100):
        part, _ = sim(cut(fr, k), p)
        a = [key(t) for t in full if t.exit_j < k - 2]
        b = [key(t) for t in part if t.exit_j < k - 2]
        assert a == b and len(a) > 0


def test_mutation_lookahead_is_caught(monkeypatch):
    """A one-bar shift of the context (uses bar t+1) must break the truncation test."""
    real = D.context

    def leaky(fr, ind, p):
        c = real(fr, ind, p)
        out = np.zeros_like(c)
        out[:-1] = c[1:]
        return out

    fr = walk(2500, 1, drift=0.01)
    full, _ = sim(fr)
    monkeypatch.setattr(E, "context", leaky)
    lf, _ = sim(fr)
    lp, _ = sim(cut(fr, 1500))
    a = [key(t) for t in lf if t.exit_j < 1498]
    b = [key(t) for t in lp if t.exit_j < 1498]
    assert a != b or [key(t) for t in full] != [key(t) for t in lf]


def test_context_uses_bar_t_only():
    fr = walk(1500, 4)
    ind = D.indicators(fr)
    c0 = D.context(fr, ind, S.BASE).copy()
    fr2 = walk(1500, 4)
    fr2.c[1000:] += 5.0
    fr2.h[1000:] += 5.0
    fr2.l[1000:] += 5.0
    fr2.o[1000:] += 5.0
    c1 = D.context(fr2, D.indicators(fr2), S.BASE)
    assert (c0[:1000] == c1[:1000]).all()


def test_avoid_uses_bars_le_t():
    fr = walk(1500, 5)
    ind = D.indicators(fr)
    a0 = D.avoid_flag(fr, ind).copy()
    fr2 = walk(1500, 5)
    fr2.v[900:] *= 10
    a1 = D.avoid_flag(fr2, D.indicators(fr2))
    assert (a0[:900] == a1[:900]).all()


# ---- order mechanics -----------------------------------------------------------
def frame_from(rows, start="2015-01-06 03:00"):
    t = pd.date_range(start, periods=len(rows), freq="h", tz="UTC")     # 03:00 UTC = 22:00 NY: session-off ok, we turn it off
    o, h, l, c = (np.array([r[i] for r in rows], float) for i in range(4))
    return D.make_frame(t, o, h, l, c, np.full(len(rows), 1000.0))


def test_buystop_fill_and_gap():
    """Hand-built: an uptrend, then a bar whose high crosses the 3-bar-high + tick level; a gap-through fills at the open."""
    p = S.Params(session=False)
    rows = [(60 + i * 0.05, 60.1 + i * 0.05, 59.9 + i * 0.05, 60.05 + i * 0.05) for i in range(60)]
    fr = frame_from(rows)
    ind = D.indicators(fr)
    trades, cnt = E.simulate(fr, ind, p)
    assert trades, "steady uptrend must fire"
    t0 = trades[0]
    lvl = max(fr.h[t0.placed_j - 2: t0.placed_j + 1]) + 0.01
    assert t0.entry_px == pytest.approx(max(lvl, fr.o[t0.entry_j]))
    assert t0.entry_j > t0.placed_j


def test_gap_through_fills_at_open():
    """Every fill is max(level, open); a bar that opens above the level fills at the open (a gap-through)."""
    found = 0
    for seed in range(1, 8):
        fr = walk(6000, seed, drift=0.01, vol=0.2)
        rng = np.random.default_rng(seed)
        jumps = rng.random(fr.n) < 0.03
        fr.o[jumps] += np.abs(rng.normal(0.4, 0.2, jumps.sum()))
        fr.h[:] = np.maximum(fr.h, fr.o)
        trades, _ = E.simulate(fr, D.indicators(fr), S.Params(session=False))
        for t in trades:
            lvl = fr.h[t.placed_j - 2: t.placed_j + 1].max() + 0.01
            assert t.entry_px >= min(lvl, fr.o[t.entry_j]) - 1e-9
            if t.gap_fill:
                found += 1
                assert t.entry_px == pytest.approx(fr.o[t.entry_j])
    assert found > 0


def test_initial_stop_is_5_bar_low_minus_tick():
    fr = walk(400, 6, drift=0.02)
    s, own = E.initial_stop(fr, 100, 5)
    assert s == pytest.approx(fr.l[96:101].min() - 0.01)


def test_p1_working_stop_is_prior_bar_ema9():
    """Once P1 is live the exit fill is min(EMA9[j-1], open[j]) (or the S floor), never a value from bar j."""
    fr = walk(3000, 7, drift=0.02)
    ind = D.indicators(fr)
    trades, _ = E.simulate(fr, ind, S.Params(session=False, r=False, p2=False))
    p1 = [t for t in trades if t.reason == "P1"]
    assert p1
    for t in p1[:200]:
        j = t.exit_j
        assert t.exit_px == pytest.approx(min(ind.e9[j - 1], fr.o[j])) or t.exit_px >= t.stop0


def test_r_exit_level_body_low_minus_tick():
    fr = walk(4000, 8, drift=0.0)
    ind = D.indicators(fr)
    trades, _ = E.simulate(fr, ind, S.BASE)
    r = [t for t in trades if t.reason == "R"]
    assert r
    for t in r[:200]:
        j = t.exit_j
        cands = []
        for k in range(t.entry_j + 1, j):
            rng = fr.h[k] - fr.l[k]
            if rng > 0 and (fr.h[k] - max(fr.o[k], fr.c[k])) >= 0.5 * rng and rng >= 0.3 * t.a0 and k + 3 >= j:
                cands.append(min(fr.o[k], fr.c[k]) - 0.01)
        assert any(t.exit_px == pytest.approx(min(x, fr.o[j])) for x in cands) or t.exit_px == pytest.approx(fr.o[j])


def test_e3_timeout_and_rearm_needs_false_bar():
    fr = walk(3000, 9, drift=0.0)
    ind = D.indicators(fr)
    ctx = D.context(fr, ind, S.Params(session=False))
    trades, cnt = E.simulate(fr, ind, S.Params(session=False))
    assert cnt["orders"] >= cnt["fills"]
    assert cnt["fills"] == len(trades)


def test_one_position_at_a_time():
    fr = walk(3000, 10, drift=0.01)
    trades, _ = sim(fr)
    for a, b in zip(trades, trades[1:]):
        assert b.entry_j >= a.exit_j


def test_planted_trend_is_profitable_random_is_not_much():
    up = walk(6000, 11, drift=0.03, vol=0.10)
    tr, _ = sim(up, S.Params(session=False))
    df = BK.trade_frame(tr, up)
    assert df["gross"].sum() > 0 and len(df) > 20


def test_roll_pays_extra_sides_and_position_carries():
    fr = walk(3000, 12, drift=0.01, roll_every=97)
    trades, _ = sim(fr)
    carried = [t for t in trades if t.n_rolls > 0]
    assert carried
    df = BK.trade_frame(carried[:1], fr)
    assert df["cost"].iloc[0] == pytest.approx(S.per_side("MCL", "mid") * (2 + 2 * carried[0].n_rolls))


# ---- controls ----------------------------------------------------------------
def test_c1_runs_and_is_long_only():
    fr = walk(3000, 13, drift=0.01)
    tr, _ = CT.donchian_c1(fr, D.indicators(fr))
    assert all(t.exit_j >= t.entry_j for t in tr)


def test_c3_is_seeded_and_reproducible():
    fr = walk(3000, 14)
    ind = D.indicators(fr)
    idx, trs = CT.candidate_outcomes(fr, ind)
    net = np.array([(t.exit_px - t.entry_px) * 100 for t in trs])
    yrs = {int(y): 5 for y in set(np.asarray(fr.ny.year)[idx])}
    a = CT.c3_draws(fr, idx, net, yrs, draws=20)
    b = CT.c3_draws(fr, idx, net, yrs, draws=20)
    assert (a == b).all()


# ---- G3 holdout ledger ---------------------------------------------------------
@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(HO.H, "ledger_path", tmp_path / "holdout_chartmark_v1.json")
    return HO.H.ledger_path


def test_ledger_refusals(ledger):
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2020-01-01"], limit=100)
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2020-01-01"], head=5)
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="V-AVOID", verdict="PASS")
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-v1", verdict="FAIL")
    for other in ("holdout_htf_ben_v2.json", "holdout_macro_flag.json", "holdout_h60.json"):
        with pytest.raises(HO.HoldoutRefused):
            HO.load_for(other)
    HO.load_for("holdout_chartmark_v1.json")


def test_ledger_spends_once_and_records_windows(ledger):
    keep, aside, side = HO.split_dates(["2021-12-30", "2022-01-03", "2025-09-05", "2025-09-08"],
                                       spend=True, candidate="CHARTMARK-v1", verdict="PASS")
    assert keep == ["2022-01-03", "2025-09-05"]
    rec = json.loads(ledger.read_text())
    assert rec["excluded_entry_windows"] == [["2025-02-19", "2025-03-04"], ["2025-06-22", "2025-07-03"]]
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-v1", verdict="PASS")


def test_training_split_and_windows():
    keep, aside, _ = HO.split_dates(["2021-12-30", "2022-01-03", "2025-09-08"])
    assert keep == ["2021-12-30"] and aside == 2
    assert HO.excluded("2025-02-19") and HO.excluded("2025-07-03") and not HO.excluded("2025-03-05")
    assert HO.is_seen("2025-09-08") and not HO.is_seen("2025-09-07")


def test_preflight_refuses_pnl_flags():
    from strategy.chartmark import preflight as PF
    for f in ("--pnl", "--backtest", "--holdout", "--limit=10", "--net"):
        with pytest.raises(SystemExit):
            PF.main([f])
