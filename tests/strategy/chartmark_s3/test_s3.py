import json
import os
from pathlib import Path

import numpy as np
import pytest

from strategy.chartmark import data as LD
from strategy.chartmark_s2 import data as D2
from strategy.chartmark_s2 import engine as E2
from strategy.chartmark_s2 import spec as S2
from strategy.chartmark_s3 import data as D
from strategy.chartmark_s3 import engine as E
from strategy.chartmark_s3 import holdout as HO
from strategy.chartmark_s3 import parity as PA
from strategy.chartmark_s3 import preflight as PF
from strategy.chartmark_s3 import spec as S
from tests.strategy.chartmark.synth import cut, walk


def frames():
    return [walk(6000, s, drift=d, vol=0.2) for s, d in ((1, -0.005), (2, 0.0), (3, -0.01))]


def key(t):
    return (t.entry_j, t.exit_j, round(t.entry_px, 6), round(t.exit_px, 6), t.reason, t.tier)


def hand(e9, e21, hist, c, h):
    n = len(c)
    fr = LD.make_frame(np.arange(n) * 3600 + 1.7e9, c, h, c, c, np.ones(n))
    nn = np.full(n, np.nan)
    ind = D.Ind(nn, np.asarray(e9, float), np.asarray(e21, float), np.asarray(hist, float), np.zeros(n, int), nn)
    return fr, ind


# ---- Tier B without B1 (sec 2.1) ---------------------------------------------------------------------
def test_b1_is_removed_prior_close_above_ema9_still_tier_b():
    # EMA9 = 10, EMA21 = 9 both bars; the bar before closed ABOVE EMA9 (v2 would say no)
    fr, ind = hand([10, 10], [9, 9], [-1, -0.1], [10.5, 9.9], [10.5, 10.0])
    assert D.tier_array(fr, ind)[1] == S.TIER_B
    assert D2.tier_array(fr, ind)[1] == 0                                # v2's rule rejects the same bar
    assert D.tier_array(fr, ind, "AB", b1=True)[1] == 0                  # V-B1 restores it


@pytest.mark.parametrize("h,c_now,hist,expect", [
    (10.0, 9.9, -0.1, S.TIER_B), (9.98, 9.5, -0.1, S.TIER_B), (9.97, 9.5, -0.1, 0),
    (10.2, 10.0, -0.1, 0), (10.2, 10.1, -0.1, 0), (10.0, 9.9, 0.0, 0), (10.0, 9.9, 0.2, 0)])
def test_remaining_b_conditions(h, c_now, hist, expect):
    fr, ind = hand([10, 10], [9, 9], [-1, hist], [9.5, c_now], [9.5, h])
    assert D.tier_array(fr, ind)[1] == expect


def test_tier_b_can_fire_on_the_first_bar_and_ignores_the_next_bar():
    fr, ind = hand([10], [9], [-1], [9.9], [10.0])
    assert D.tier_array(fr, ind)[0] == S.TIER_B                          # no bar t-1 is needed any more
    fr, ind = hand([10, 10, 10], [9, 9, 9], [-1, -1, -1], [9.5, 9.9, 99.0], [9.5, 10.0, 99.0])
    assert D.tier_array(fr, ind)[1] == S.TIER_B


def test_v3_tier_b_is_a_superset_of_v2s_and_v_b1_equals_v2():
    for fr in frames():
        ind = D.indicators(fr)
        c3, t3 = D.context_tiers(fr, ind, S.VARIANTS["V-B"])
        c2, t2 = D2.context_tiers(fr, ind, S2.VARIANTS["V-B"])
        assert (c2 & ~c3).sum() == 0 and c3.sum() > c2.sum()
        cb1, tb1 = D.context_tiers(fr, ind, S.VARIANTS["V-B1"])
        c2b, t2b = D2.context_tiers(fr, ind, S2.BASE)
        assert (cb1 == c2b).all() and (tb1 == t2b).all()                 # V-B1 is v2's base, exactly


def test_v_b1_trades_equal_v2_base_trades():
    fr = frames()[0]
    ind = D.indicators(fr)
    a, _ = E.simulate(fr, ind, S.VARIANTS["V-B1"])
    b, _ = E2.simulate(fr, ind, S2.BASE)
    assert [key(t) for t in a] == [key(t) for t in b] and len(a) > 100


def test_tiers_partition_and_v_a_equals_v2_v_a():
    for fr in frames():
        ind = D.indicators(fr)
        a, _ = D.context_tiers(fr, ind, S.VARIANTS["V-A"])
        b, _ = D.context_tiers(fr, ind, S.VARIANTS["V-B"])
        base, tier = D.context_tiers(fr, ind, S.BASE)
        assert (a | b == base).all() and not (a & b).any()
        a2, _ = D2.context_tiers(fr, ind, S2.VARIANTS["V-A"])
        assert (a == a2).all()


# ---- G4 look-ahead ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("name", list(S.VARIANTS))
def test_truncation_invariance(seed, name):
    fr = walk(3000, seed, drift=-0.005, vol=0.2)
    p = S.VARIANTS[name]
    full, _ = E.simulate(fr, D.indicators(fr), p)
    for k in (1000, 1700, 2400):
        part, _ = E.simulate(cut(fr, k), D.indicators(cut(fr, k)), p)
        a = [key(t) for t in full if t.exit_j < k - 2]
        b = [key(t) for t in part if t.exit_j < k - 2]
        assert a == b and len(a) > 0


def test_context_uses_bar_t_only():
    fr = walk(1500, 4, drift=-0.005, vol=0.2)
    ind = D.indicators(fr)
    for p in S.VARIANTS.values():
        c0, t0 = D.context_tiers(fr, ind, p)
        c0, t0 = c0.copy(), t0.copy()
        fr2 = walk(1500, 4, drift=-0.005, vol=0.2)
        for a in (fr2.c, fr2.h, fr2.l, fr2.o):
            a[1000:] += 5.0
        c1, t1 = D.context_tiers(fr2, D.indicators(fr2), p)
        assert (c0[:1000] == c1[:1000]).all() and (t0[:1000] == t1[:1000]).all()


def test_mutation_lookahead_is_caught(monkeypatch):
    real = D.context_tiers

    def leaky(fr, ind, p):
        c, t = real(fr, ind, p)
        c2, t2 = np.zeros_like(c), np.zeros_like(t)
        c2[:-1], t2[:-1] = c[1:], t[1:]
        return c2, t2

    fr = walk(3000, 1, drift=-0.005, vol=0.2)
    full, _ = E.simulate(fr, D.indicators(fr))
    monkeypatch.setattr(E, "context_tiers", leaky)
    lf, _ = E.simulate(fr, D.indicators(fr))
    lp, _ = E.simulate(cut(fr, 1700), D.indicators(cut(fr, 1700)))
    a = [key(t) for t in lf if t.exit_j < 1698]
    b = [key(t) for t in lp if t.exit_j < 1698]
    assert a != b or [key(t) for t in full] != [key(t) for t in lf]


# ---- engine mechanics and tier tags --------------------------------------------------------------------------
@pytest.mark.parametrize("fr", frames())
def test_fill_backstop_and_tier_tag(fr):
    ind = D.indicators(fr)
    ctx, tier = D.context_tiers(fr, ind, S.BASE)
    trades, cnt = E.simulate(fr, ind)
    assert trades and cnt["fills"] == len(trades)
    for t in trades[:500]:
        lvl = fr.l[t.entry_j - 1] - 0.01
        assert t.entry_px == pytest.approx(min(lvl, fr.o[t.entry_j]))
        assert t.stop0 == pytest.approx(fr.h[t.entry_j - 19: t.entry_j + 1].max() + 0.01)
        assert ctx[t.entry_j - 1] and t.tier == tier[t.entry_j - 1]
    assert sum(cnt["orders_by_tier"].values()) == cnt["orders"]
    assert sum(cnt["fills_by_tier"].values()) == cnt["fills"]


def test_v_a_and_v_b_fill_only_their_tier():
    for fr in frames():
        ind = D.indicators(fr)
        ta, _ = E.simulate(fr, ind, S.VARIANTS["V-A"])
        tb, _ = E.simulate(fr, ind, S.VARIANTS["V-B"])
        assert {t.tier for t in ta} == {1} and {t.tier for t in tb} == {2}


def test_v2_default_engine_is_unchanged_by_the_ctx_hook():
    fr = frames()[0]
    ind = D.indicators(fr)
    a, _ = E2.simulate(fr, ind, S2.BASE)
    b, _ = E2.simulate(fr, ind, S2.BASE, ctx_fn=D2.context_tiers)
    assert [key(t) for t in a] == [key(t) for t in b]


def test_costs_are_shared():
    assert S.per_side("MCL", "mid") == pytest.approx(1.77) and S.per_side("CL", "mid") == pytest.approx(12.37)


# ---- G3 ledger ----------------------------------------------------------------------------------------------------
@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(HO.H, "ledger_path", tmp_path / "holdout_chartmark_short_v3.json")
    return HO.H.ledger_path


def test_ledger_refusals(ledger):
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2020-01-01"], limit=100)
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="V-B1", verdict="PASS")
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-S-v2", verdict="PASS")
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-S-v3", verdict="FAIL")
    for other in ("holdout_chartmark_short_v1.json", "holdout_chartmark_short_v2.json", "holdout_chartmark_v2.json",
                  "holdout_macro_flag.json", "holdout_h60.json"):
        with pytest.raises(HO.HoldoutRefused):
            HO.load_for(other)
    HO.load_for("holdout_chartmark_short_v3.json")


def test_other_ledgers_refuse_the_v3_ledger():
    from strategy.chartmark import holdout as LH
    from strategy.chartmark_s import holdout as H1
    from strategy.chartmark_s2 import holdout as H2
    for H in (LH, H1, H2):
        with pytest.raises(H.HoldoutRefused):
            H.load_for("holdout_chartmark_short_v3.json")


def test_ledger_spends_once_and_records_windows(ledger):
    keep, _, _ = HO.split_dates(["2021-12-30", "2022-01-03", "2025-09-05", "2025-09-08"],
                                spend=True, candidate="CHARTMARK-S-v3", verdict="PASS")
    assert keep == ["2022-01-03", "2025-09-05"]
    assert json.loads(ledger.read_text())["excluded_entry_windows"] == [["2025-02-19", "2025-03-04"], ["2025-06-22", "2025-07-03"]]
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-S-v3", verdict="PASS")


def test_the_real_ledger_is_unspent():
    assert not (Path(__file__).resolve().parents[3] / "holdout_chartmark_short_v3.json").exists()


# ---- G2 count-only -----------------------------------------------------------------------------------------------------
def test_preflight_refuses_pnl_flags():
    for f in ("--pnl", "--backtest", "--holdout", "--limit=10", "--net", "--markets=CL"):
        with pytest.raises(SystemExit):
            PF.main([f])


def test_preflight_report_counts_only_and_names_v3():
    from strategy.chartmark_s2 import preflight as P2
    fr = walk(6000, 1, drift=-0.005, vol=0.2)
    ind = D.indicators(fr)
    blocks = {n: P2.counts_table(fr, *E.simulate(fr, ind, p)) for n, p in S.VARIANTS.items()}
    txt = PF.report(fr, blocks, P2.context_share(fr, ind, S.BASE, ctx_fn=D.context_tiers), "t")
    assert txt.startswith("CHARTMARK-S v3 G2") and "== V-B1" in txt and "4,300-6,000" in txt
    body = txt.replace("no price or P&L is reported here", "")
    for bad in ("$", "net ", "gross", "P&L", "profit", "exit price"):
        assert bad not in body


# ---- G6 ------------------------------------------------------------------------------------------------------------------
def test_g6_uses_the_same_marks_as_v2():
    from strategy.chartmark_s2 import parity as P2
    assert PA.REJECTED == P2.REJECTED and PA.ACCEPT_1 == P2.ACCEPT_1 and PA.ACCEPT_2 == P2.ACCEPT_2


def test_g6_runs_on_the_seen_bars_and_names_v3():
    out = Path(os.environ.get("CHARTMARK_OUT", r"D:\Trading\Claude outputs"))
    csv = out / "w15_0032_cl1_1h_bars_indicators.csv"
    if not csv.exists():
        pytest.skip("seen-window bars not on this machine")
    txt, ok = PA.run(csv, log=lambda *_: None)
    assert txt.startswith("CHARTMARK-S v3 G6") and ("G6 fidelity: PASS" in txt) == ok
    for s in PA.REJECTED + (PA.ACCEPT_1[0], PA.ACCEPT_2[0]):
        assert s in txt
