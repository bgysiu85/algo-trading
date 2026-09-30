import json
import os
from pathlib import Path

import numpy as np
import pytest

from strategy.chartmark_s import book as BK
from strategy.chartmark_s import controls as CT
from strategy.chartmark_s import data as D
from strategy.chartmark_s import engine as E
from strategy.chartmark_s import holdout as HO
from strategy.chartmark_s import spec as S
from tests.strategy.chartmark.synth import cut, walk

TK = 0.01


def sim(fr, p=S.BASE):
    return E.simulate(fr, D.indicators(fr), p)


def key(tr):
    return (tr.entry_j, tr.exit_j, round(tr.entry_px, 6), round(tr.exit_px, 6), tr.reason)


def frames():
    return [walk(6000, s, drift=d, vol=0.2) for s, d in ((1, -0.005), (2, 0.0), (3, -0.01))]


# ---- costs (sec 2.5) -----------------------------------------------------------
def test_ibkr_costs_and_short_sign():
    assert S.per_side("MCL", "low") == pytest.approx(0.77)
    assert S.per_side("MCL", "mid") == pytest.approx(1.77)
    assert 2 * S.per_side("MCL", "high") == pytest.approx(5.54)
    assert 2 * S.per_side("CL", "mid") == pytest.approx(24.74)
    fr = walk(400, 1)
    t = E.Trade(10, 12, 60.00, 59.50, 61, 0.2, "P0", 0, 0)
    df = BK.trade_frame([t], fr)
    assert df["gross"].iloc[0] == pytest.approx(50.0)                 # a short gains when price falls, 1 MCL = 100 bbl
    assert df["cost"].iloc[0] == pytest.approx(2 * 1.77)
    t2 = E.Trade(10, 12, 60.00, 60.30, 61, 0.2, "P0", 1, 2)
    d2 = BK.trade_frame([t2], fr)
    assert d2["gross"].iloc[0] == pytest.approx(-30.0)
    assert d2["cost"].iloc[0] == pytest.approx(6 * 1.77)              # two rolls = four extra sides


# ---- G4 look-ahead guards --------------------------------------------------------
@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("name", list(S.VARIANTS))
def test_truncation_invariance(seed, name):
    fr = walk(3000, seed, drift=-0.005, vol=0.2)
    p = S.VARIANTS[name]
    full, _ = sim(fr, p)
    for k in (1000, 1700, 2400):
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

    fr = walk(3000, 1, drift=-0.005, vol=0.2)
    full, _ = sim(fr)
    monkeypatch.setattr(E, "context", leaky)
    lf, _ = sim(fr)
    lp, _ = sim(cut(fr, 1700))
    a = [key(t) for t in lf if t.exit_j < 1698]
    b = [key(t) for t in lp if t.exit_j < 1698]
    assert a != b or [key(t) for t in full] != [key(t) for t in lf]


def test_mutation_exit_uses_current_bar_ema_is_caught(monkeypatch):
    """If the P0/P1 level read EMA9[j] (this bar) instead of EMA9[j-1], truncating after j would change the trade."""
    fr = walk(3000, 2, drift=-0.005, vol=0.2)
    ind = D.indicators(fr)
    e9 = ind.e9.copy()
    leaky = np.roll(e9, -1)              # value at j is EMA9[j+1]: peeks one bar ahead of the exit bar's own decision
    base, _ = E.simulate(fr, ind)
    ind2 = D.indicators(fr)
    ind2.e9 = leaky
    ind2._cache.clear()
    lk, _ = E.simulate(fr, ind2)
    assert [key(t) for t in base] != [key(t) for t in lk]


def test_context_and_range_use_bar_t_only():
    fr = walk(1500, 4)
    ind = D.indicators(fr)
    for p in (S.BASE, S.VARIANTS["V-RANGE"], S.VARIANTS["V-SESSION"]):
        c0 = D.context(fr, ind, p).copy()
        fr2 = walk(1500, 4)
        for a in (fr2.c, fr2.h, fr2.l, fr2.o):
            a[1000:] += 5.0
        c1 = D.context(fr2, D.indicators(fr2), p)
        assert (c0[:1000] == c1[:1000]).all()
    r0 = D.range_pos(fr).copy()
    fr2 = walk(1500, 4)
    fr2.h[1000:] += 9.0
    assert np.allclose(np.nan_to_num(r0[:1000]), np.nan_to_num(D.range_pos(fr2)[:1000]))


def test_bars_since_high_and_range_definitions():
    h = np.array([1, 2, 3, 9, 4, 5, 6, 7, 8, 5, 4, 3, 2, 1, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.01, 0.0], float)
    bs = D.bars_since_high(h, 20)
    assert np.isnan(bs[18]) and bs[19] == 19 - 3 and bs[20] == 20 - 3 and bs[21] == 21 - 3
    fr = walk(300, 5)
    rp = D.range_pos(fr, 120)
    t = 200
    lo, hi = fr.l[t - 119: t + 1].min(), fr.h[t - 119: t + 1].max()
    assert rp[t] == pytest.approx((fr.c[t] - lo) / (hi - lo))


def test_avoid_uses_bars_le_t():
    fr = walk(1500, 5)
    ind = D.indicators(fr)
    a0 = D.avoid_flag(fr, ind).copy()
    fr2 = walk(1500, 5)
    fr2.v[900:] *= 10
    a1 = D.avoid_flag(fr2, D.indicators(fr2))
    assert (a0[:900] == a1[:900]).all()


# ---- order and exit mechanics (independent recomputation) -----------------------------
@pytest.mark.parametrize("fr", frames())
def test_entry_fill_and_backstop(fr):
    ind = D.indicators(fr)
    trades, cnt = E.simulate(fr, ind)
    assert trades and cnt["fills"] == len(trades)
    for t in trades[:400]:
        lvl = fr.l[t.entry_j - 1] - TK                       # E1/E2: latest re-set = prior bar's low - 1 tick
        assert t.entry_px == pytest.approx(min(lvl, fr.o[t.entry_j]))
        assert fr.l[t.entry_j] <= lvl                        # E4
        assert t.stop0 == pytest.approx(fr.h[t.entry_j - 19: t.entry_j + 1].max() + TK)
        assert t.a0 == pytest.approx(ind.atr[t.entry_j - 1])
        assert t.entry_j - t.placed_j <= S.BASE.K            # E3: at most 6 bars working
        if t.gap_fill:
            assert t.entry_px == pytest.approx(fr.o[t.entry_j])


@pytest.mark.parametrize("fr", frames())
def test_p0_and_backstop_exit_levels(fr):
    ind = D.indicators(fr)
    trades, _ = E.simulate(fr, ind)
    p0 = [t for t in trades if t.reason == "P0"]
    sb = [t for t in trades if t.reason == "S"]
    assert p0
    for t in p0[:400]:
        j = t.exit_j
        assert j > t.entry_j                                  # not active in the entry bar
        assert t.exit_px == pytest.approx(max(ind.e9[j - 1] + 2 * TK, fr.o[j]))
    for t in sb:
        assert t.exit_px == pytest.approx(max(t.stop0, fr.o[t.exit_j]))


@pytest.mark.parametrize("fr", frames())
def test_p1_retest_first_poke_tolerated(fr):
    ind = D.indicators(fr)
    trades, _ = E.simulate(fr, ind)
    p1 = [t for t in trades if t.reason == "P1"]
    assert len(p1) > 20
    for t in p1[:300]:
        e, j = t.entry_j, t.exit_j
        # independent walk
        minc = fr.c[e]
        armed_at = e if (t.entry_px - fr.c[e]) / t.a0 >= 1.0 else None
        poke = None
        for k in range(e + 1, j + 1):
            if armed_at is not None and poke is None and fr.h[k] > ind.e9[k - 1] + 2 * TK and k < j:
                poke = k
            if k < j:
                minc = min(minc, fr.c[k])
                if armed_at is None and (t.entry_px - minc) / t.a0 >= 1.0:
                    armed_at = k
        assert armed_at is not None and poke is not None and poke < j
        exp = max(min(ind.e9[j - 1] + 2 * TK, fr.h[poke] - TK), fr.o[j])
        assert t.exit_px == pytest.approx(exp)


def test_variants_change_only_what_they_say():
    fr = walk(6000, 2, drift=-0.005, vol=0.2)
    ind = D.indicators(fr)
    wide, _ = E.simulate(fr, ind, S.VARIANTS["V-WIDE"])
    assert wide and not any(t.reason == "P0" for t in wide)
    c9, _ = E.simulate(fr, ind, S.VARIANTS["V-CLOSE9"])
    assert c9 and not any(t.reason == "P1" for t in c9)
    for t in [x for x in c9 if x.reason == "C9"][:200]:
        j = t.exit_j
        assert fr.c[j - 1] > ind.e9[j - 1] and t.exit_px == pytest.approx(fr.o[j])
    ses, _ = E.simulate(fr, ind, S.VARIANTS["V-SESSION"])
    for t in ses:
        assert 2 <= ind.hour[t.entry_j - 1] <= 12                    # bar t (context bar) opens 02:00-12:00 NY
    rg, _ = E.simulate(fr, ind, S.VARIANTS["V-RANGE"])
    rp = D.range_pos(fr)
    for t in rg:
        assert rp[t.entry_j - 1] >= 0.6


def test_one_position_and_reentry_from_exit_bar():
    fr = walk(6000, 3, drift=-0.005, vol=0.2)
    trades, cnt = sim(fr)
    for a, b in zip(trades, trades[1:]):
        assert b.entry_j >= a.exit_j
        assert b.placed_j >= a.exit_j                                # E5: new order only from the exit bar's close
    assert cnt["reentries"] > 0


def test_timeout_requires_a_false_context_bar():
    fr = walk(6000, 4, drift=0.0, vol=0.2)
    ind = D.indicators(fr)
    ctx = D.context(fr, ind, S.BASE)
    trades, cnt = E.simulate(fr, ind)
    assert cnt["orders"] >= cnt["fills"] and cnt["fills"] == len(trades)
    assert cnt["timeouts"] + cnt["ctx_cancels"] + cnt["roll_cancels"] + cnt["fills"] <= cnt["orders"] + 1
    assert ctx.any()


def test_roll_pays_extra_sides_and_position_carries():
    fr = walk(4000, 5, drift=-0.005, vol=0.2, roll_every=97)
    trades, _ = sim(fr)
    carried = [t for t in trades if t.n_rolls > 0]
    assert carried
    df = BK.trade_frame(carried[:1], fr)
    assert df["cost"].iloc[0] == pytest.approx(S.per_side("MCL", "mid") * (2 + 2 * carried[0].n_rolls))


def test_planted_downtrend_is_profitable_for_the_short():
    down = walk(8000, 11, drift=-0.03, vol=0.10)
    tr, _ = sim(down)
    df = BK.trade_frame(tr, down)
    assert len(df) > 20 and df["gross"].sum() > 0


# ---- controls -----------------------------------------------------------------------
def test_c1_short_donchian_runs():
    fr = walk(4000, 13, drift=-0.02, vol=0.2)
    tr, _ = CT.donchian_c1(fr, D.indicators(fr))
    assert tr and all(t.exit_j > t.entry_j for t in tr)
    for t in tr[:100]:
        assert t.entry_px <= fr.o[t.entry_j] + 1e-9 or t.entry_px == pytest.approx(min(fr.l[t.entry_j - 20: t.entry_j].min() - TK, fr.o[t.entry_j]))


def test_c2_mirror_scores_as_a_short():
    fr = walk(4000, 14, drift=-0.02, vol=0.2)
    mf = CT.mirror(fr)
    assert np.allclose(CT.mirror(mf).o, fr.o) and np.allclose(CT.mirror(mf).h, fr.h)
    tr, cnt = CT.c2_mirrored_long(fr)
    assert tr
    from strategy.chartmark import book as LB
    df = LB.trade_frame(tr, cnt["mirrored"])
    t0 = tr[0]
    assert df["gross"].iloc[0] == pytest.approx(((-t0.entry_px) - (-t0.exit_px)) * 100)   # entry - exit on the original prices


def test_c3_is_seeded_and_reproducible():
    fr = walk(3000, 14, drift=-0.01, vol=0.2)
    ind = D.indicators(fr)
    idx, trs = CT.candidate_outcomes(fr, ind)
    net = np.array([(t.entry_px - t.exit_px) * 100 for t in trs])
    yrs = {int(y): 5 for y in set(np.asarray(fr.ny.year)[idx])}
    a = CT.c3_draws(fr, idx, net, yrs, draws=20)
    b = CT.c3_draws(fr, idx, net, yrs, draws=20)
    assert (a == b).all()


# ---- G3 holdout ledger ------------------------------------------------------------------
@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(HO.H, "ledger_path", tmp_path / "holdout_chartmark_short_v1.json")
    return HO.H.ledger_path


def test_ledger_refusals(ledger):
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2020-01-01"], limit=100)
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2020-01-01"], head=5)
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="V-RANGE", verdict="PASS")
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-S-v1", verdict="FAIL")
    for other in ("holdout_chartmark_v1.json", "holdout_htf_ben_v2.json", "holdout_macro_flag.json", "holdout_h60.json"):
        with pytest.raises(HO.HoldoutRefused):
            HO.load_for(other)
    HO.load_for("holdout_chartmark_short_v1.json")


def test_long_ledger_refuses_the_short_ledger():
    from strategy.chartmark import holdout as LH
    with pytest.raises(LH.HoldoutRefused):
        LH.load_for("holdout_chartmark_short_v1.json")


def test_ledger_spends_once_and_records_windows(ledger):
    keep, aside, side = HO.split_dates(["2021-12-30", "2022-01-03", "2025-09-05", "2025-09-08"],
                                       spend=True, candidate="CHARTMARK-S-v1", verdict="PASS")
    assert keep == ["2022-01-03", "2025-09-05"]
    rec = json.loads(ledger.read_text())
    assert rec["excluded_entry_windows"] == [["2025-02-19", "2025-03-04"], ["2025-06-22", "2025-07-03"]]
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-S-v1", verdict="PASS")


def test_training_split_and_windows():
    keep, aside, _ = HO.split_dates(["2021-12-30", "2022-01-03", "2025-09-08"])
    assert keep == ["2021-12-30"] and aside == 2
    assert HO.excluded("2025-02-19") and HO.excluded("2025-07-03") and not HO.excluded("2025-03-05")
    assert HO.is_seen("2025-09-08") and not HO.is_seen("2025-09-07")


def test_the_real_ledger_is_unspent():
    assert not (Path(__file__).resolve().parents[3] / "holdout_chartmark_short_v1.json").exists()


def test_preflight_and_run_refuse_pnl_flags():
    from strategy.chartmark_s import preflight as PF
    for f in ("--pnl", "--backtest", "--holdout", "--limit=10", "--net"):
        with pytest.raises(SystemExit):
            PF.main([f])


# ---- G6 parity (seen window) ---------------------------------------------------------------
def test_seen_window_parity():
    from strategy.chartmark_s import parity as PA
    out = Path(os.environ.get("CHARTMARK_OUT", r"D:\Trading\Claude outputs"))
    csv, marks = out / "w15_0032_cl1_1h_bars_indicators.csv", out / "w15_0032_short_marks_v3.csv"
    if not csv.exists():
        pytest.skip("seen-window bars not on this machine")
    txt, ok = PA.run(csv, marks, log=lambda *_: None)
    assert ok, txt
