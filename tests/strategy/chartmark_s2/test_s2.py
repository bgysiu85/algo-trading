import json
import os
from pathlib import Path

import numpy as np
import pytest

from strategy.chartmark import data as LD
from strategy.chartmark_s import data as D1
from strategy.chartmark_s import engine as E1
from strategy.chartmark_s import spec as S1
from strategy.chartmark_s2 import data as D
from strategy.chartmark_s2 import engine as E
from strategy.chartmark_s2 import holdout as HO
from strategy.chartmark_s2 import parity as PA
from strategy.chartmark_s2 import preflight as PF
from strategy.chartmark_s2 import spec as S
from tests.strategy.chartmark.synth import cut, walk

TK = 0.01


def sim(fr, p=S.BASE):
    return E.simulate(fr, D.indicators(fr), p)


def key(tr):
    return (tr.entry_j, tr.exit_j, round(tr.entry_px, 6), round(tr.exit_px, 6), tr.reason, tr.tier)


def frames():
    return [walk(6000, s, drift=d, vol=0.2) for s, d in ((1, -0.005), (2, 0.0), (3, -0.01))]


# ---- tier definitions, one condition at a time (sec 2.1) ------------------------------------------
def hand(e9, e21, hist, c, h):
    n = len(c)
    fr = LD.make_frame(np.arange(n) * 3600 + 1.7e9, c, h, c, c, np.ones(n))
    nn = np.full(n, np.nan)
    ind = D.Ind(nn, np.asarray(e9, float), np.asarray(e21, float), np.asarray(hist, float), np.zeros(n, int), nn)
    return fr, ind


def test_tier_a_is_ema9_below_ema21():
    fr, ind = hand([10, 10, 10], [11, 10, 9], [1, 1, 1], [12, 12, 12], [12, 12, 12])
    tr = D.tier_array(fr, ind)
    assert list(tr) == [S.TIER_A, 0, 0]          # strict "<" (K1); equal or above is not Tier A


@pytest.mark.parametrize("what,c_prev,h,c_now,hist,expect", [
    ("all four true", 9.5, 10.0, 9.9, -0.1, S.TIER_B),
    ("B1 fails: prior close above EMA9", 10.5, 10.0, 9.9, -0.1, 0),
    ("B1 fails: prior close equal to EMA9", 10.0, 10.0, 9.9, -0.1, 0),
    ("B2 fails: high below EMA9 - 2 ticks", 9.5, 9.97, 9.5, -0.1, 0),
    ("B2 edge: high exactly EMA9 - 2 ticks", 9.5, 9.98, 9.5, -0.1, S.TIER_B),
    ("B3 fails: closes at EMA9", 9.5, 10.2, 10.0, -0.1, 0),
    ("B3 fails: closes above EMA9", 9.5, 10.2, 10.1, -0.1, 0),
    ("B4 fails: histogram zero", 9.5, 10.0, 9.9, 0.0, 0),
    ("B4 fails: histogram positive", 9.5, 10.0, 9.9, 0.2, 0),
])
def test_tier_b_each_condition(what, c_prev, h, c_now, hist, expect):
    # EMA9 = 10 and EMA21 = 9 on both bars (EMA9 above EMA21, so not Tier A)
    fr, ind = hand([10, 10], [9, 9], [-1, hist], [c_prev, c_now], [c_prev, h])
    assert D.tier_array(fr, ind)[1] == expect, what


def test_tier_b_needs_the_prior_bar_and_ema9_ge_ema21():
    fr, ind = hand([10], [9], [-1], [9.9], [10.0])
    assert D.tier_array(fr, ind)[0] == 0                                  # K2: no bar t-1
    fr, ind = hand([10, 10], [10, 10], [-1, -1], [9.5, 9.9], [9.5, 10.0])
    assert D.tier_array(fr, ind)[1] == S.TIER_B                           # EMA9 == EMA21 is Tier B (K1)


def test_tiers_are_exclusive_and_variants_partition_the_base():
    for fr in frames():
        ind = D.indicators(fr)
        a, _ = D.context_tiers(fr, ind, S.VARIANTS["V-A"])
        b, _ = D.context_tiers(fr, ind, S.VARIANTS["V-B"])
        base, tier = D.context_tiers(fr, ind, S.BASE)
        assert (a | b == base).all() and not (a & b).any()
        assert set(np.unique(tier)) <= {0, 1, 2} and ((tier > 0) == base).all()
        assert (tier[a] == S.TIER_A).all() and (tier[b] == S.TIER_B).all()
        assert a.sum() > 0 and b.sum() > 0


def test_x2_and_x3_are_gone():
    """v1's X2 (EMA9 >= EMA21 - 0.25 ATR) and X3 (histogram falling) must not gate v2: a Tier A bar with a RISING histogram counts."""
    fr = walk(6000, 1, drift=-0.005, vol=0.2)
    ind = D.indicators(fr)
    ctx, tier = D.context_tiers(fr, ind, S.BASE)
    rising = np.zeros(fr.n, bool)
    rising[1:] = ind.hist[1:] > ind.hist[:-1]
    assert (ctx & (tier == S.TIER_A) & rising).any()


# ---- G4 look-ahead guards ---------------------------------------------------------------------------
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


def test_context_uses_bar_t_and_t_minus_1_only():
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


def test_b1_reads_the_prior_bar_and_nothing_later():
    """Moving bar t-1's close across EMA9 flips B1 at t; moving bar t+1 never changes tier at t."""
    e9, e21 = [10, 10, 10], [9, 9, 9]
    fr, ind = hand(e9, e21, [-1, -1, -1], [9.5, 9.9, 9.0], [9.5, 10.0, 9.0])
    assert D.tier_array(fr, ind)[1] == S.TIER_B
    fr, ind = hand(e9, e21, [-1, -1, -1], [10.5, 9.9, 9.0], [10.5, 10.0, 9.0])
    assert D.tier_array(fr, ind)[1] == 0
    fr, ind = hand(e9, e21, [-1, -1, -1], [9.5, 9.9, 99.0], [9.5, 10.0, 99.0])
    assert D.tier_array(fr, ind)[1] == S.TIER_B


def test_mutation_lookahead_is_caught(monkeypatch):
    real = E.context_tiers

    def leaky(fr, ind, p):
        c, t = real(fr, ind, p)
        c2, t2 = np.zeros_like(c), np.zeros_like(t)
        c2[:-1], t2[:-1] = c[1:], t[1:]
        return c2, t2

    fr = walk(3000, 1, drift=-0.005, vol=0.2)
    full, _ = sim(fr)
    monkeypatch.setattr(E, "context_tiers", leaky)
    lf, _ = sim(fr)
    lp, _ = sim(cut(fr, 1700))
    a = [key(t) for t in lf if t.exit_j < 1698]
    b = [key(t) for t in lp if t.exit_j < 1698]
    assert a != b or [key(t) for t in full] != [key(t) for t in lf]


def test_mutation_b1_dropped_is_caught(monkeypatch):
    """If B1 were dropped the tier-B population would change (this is what the G6 mismatch on 11 Sep turns on)."""
    fr = walk(6000, 1, drift=-0.005, vol=0.2)
    ind = D.indicators(fr)
    before = int((D.tier_array(fr, ind, "B") > 0).sum())
    ind2 = D.indicators(fr)
    c = fr.c.copy()
    fr2 = LD.make_frame(fr.t, fr.o, fr.h, fr.l, c, fr.v, fr.roll_after)
    with np.errstate(invalid="ignore"):
        no_b1 = (~(ind2.e9 < ind2.e21)) & (fr2.h >= ind2.e9 - 0.02) & (fr2.c < ind2.e9) & (ind2.hist < 0)
    assert int(no_b1.sum()) > before


def test_exit_levels_use_the_bar_before(monkeypatch):
    fr = walk(3000, 2, drift=-0.005, vol=0.2)
    ind = D.indicators(fr)
    base, _ = E.simulate(fr, ind)
    ind2 = D.indicators(fr)
    ind2.e9 = np.roll(ind2.e9, -1)
    ind2._cache.clear()
    lk, _ = E.simulate(fr, ind2)
    assert [key(t) for t in base] != [key(t) for t in lk]


# ---- the order machine and exits are v1's, unchanged --------------------------------------------------
@pytest.mark.parametrize("fr", frames())
def test_engine_reproduces_v1_when_given_v1_context(fr, monkeypatch):
    from strategy.chartmark_s import engine as V1
    ind = D.indicators(fr)
    p1 = S1.BASE
    ref, rc = V1.simulate(fr, ind, p1)
    ctx1 = D1.context(fr, ind, p1)
    monkeypatch.setattr(E, "context_tiers", lambda fr_, ind_, p_: (ctx1, np.where(ctx1, 1, 0).astype(np.int8)))
    got, gc = E.simulate(fr, ind, S.BASE)
    assert [(t.entry_j, t.exit_j, t.entry_px, t.exit_px, t.reason, t.phase, t.placed_j) for t in ref] == \
           [(t.entry_j, t.exit_j, t.entry_px, t.exit_px, t.reason, t.phase, t.placed_j) for t in got]
    assert {k: rc[k] for k in ("orders", "fills", "timeouts", "ctx_cancels", "roll_cancels", "resets", "gap_fills", "reentries")} == \
           {k: gc[k] for k in ("orders", "fills", "timeouts", "ctx_cancels", "roll_cancels", "resets", "gap_fills", "reentries")}


@pytest.mark.parametrize("fr", frames())
def test_entry_fill_backstop_and_tier_tag(fr):
    ind = D.indicators(fr)
    ctx, tier = D.context_tiers(fr, ind, S.BASE)
    trades, cnt = E.simulate(fr, ind)
    assert trades and cnt["fills"] == len(trades)
    for t in trades[:500]:
        lvl = fr.l[t.entry_j - 1] - TK
        assert t.entry_px == pytest.approx(min(lvl, fr.o[t.entry_j]))
        assert fr.l[t.entry_j] <= lvl
        assert t.stop0 == pytest.approx(fr.h[t.entry_j - 19: t.entry_j + 1].max() + TK)
        assert t.a0 == pytest.approx(ind.atr[t.entry_j - 1])
        assert ctx[t.entry_j - 1]                                          # the last context bar held
        assert t.tier == tier[t.entry_j - 1] and t.tier in (1, 2)          # K4
        assert (t.tier == 1) == bool(ind.e9[t.entry_j - 1] < ind.e21[t.entry_j - 1])
    assert sum(cnt["orders_by_tier"].values()) == cnt["orders"]
    assert sum(cnt["fills_by_tier"].values()) == cnt["fills"]


def test_variants_v_a_and_v_b_fill_only_their_tier():
    for fr in frames():
        ind = D.indicators(fr)
        ta, _ = E.simulate(fr, ind, S.VARIANTS["V-A"])
        tb, _ = E.simulate(fr, ind, S.VARIANTS["V-B"])
        assert ta and tb
        assert {t.tier for t in ta} == {1} and {t.tier for t in tb} == {2}


def test_a_tier_b_order_lives_one_bar_unless_context_repeats():
    fr = walk(6000, 3, drift=-0.01, vol=0.2)
    ind = D.indicators(fr)
    ctx, tier = D.context_tiers(fr, ind, S.VARIANTS["V-B"])
    trades, cnt = E.simulate(fr, ind, S.VARIANTS["V-B"])
    for t in trades:
        # every bar between placement and the fill bar (exclusive of the fill bar) must hold a Tier B context
        assert all(ctx[k] for k in range(t.placed_j, t.entry_j))


def test_one_position_and_reentry_from_exit_bar():
    fr = walk(6000, 1, drift=-0.005, vol=0.2)
    trades, _ = sim(fr)
    for a, b in zip(trades, trades[1:]):
        assert b.entry_j >= a.exit_j
        assert b.placed_j >= a.exit_j


def test_variants_change_only_what_they_say():
    fr = walk(6000, 1, drift=-0.005, vol=0.2)
    ind = D.indicators(fr)
    base_ctx, _ = D.context_tiers(fr, ind, S.BASE)
    for name in ("V-RANGE", "V-SESSION", "V-AVOID"):
        c, _ = D.context_tiers(fr, ind, S.VARIANTS[name])
        assert (c & ~base_ctx).sum() == 0 and c.sum() < base_ctx.sum()
    assert S.VARIANTS["V-A"].tiers == "A" and S.VARIANTS["V-B"].tiers == "B"
    assert "V-WIDE" not in S.VARIANTS and "V-CLOSE9" not in S.VARIANTS      # K5


# ---- costs (v1's, IBKR) --------------------------------------------------------------------------------
def test_costs_are_v1s():
    for sym in ("MCL", "CL"):
        for lv in S.LEVELS:
            assert S.per_side(sym, lv) == S1.per_side(sym, lv)
    assert S.per_side("MCL", "low") == pytest.approx(0.77) and S.per_side("MCL", "mid") == pytest.approx(1.77)


# ---- G3 holdout ledger -----------------------------------------------------------------------------------
@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(HO.H, "ledger_path", tmp_path / "holdout_chartmark_short_v2.json")
    return HO.H.ledger_path


def test_ledger_refusals(ledger):
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2020-01-01"], limit=100)
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2020-01-01"], head=5)
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="V-A", verdict="PASS")
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-S-v1", verdict="PASS")
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-S-v2", verdict="FAIL")
    for other in ("holdout_chartmark_short_v1.json", "holdout_chartmark_v1.json", "holdout_chartmark_v2.json",
                  "holdout_macro_flag.json", "holdout_h60.json", "holdout_htf_ben_v2.json"):
        with pytest.raises(HO.HoldoutRefused):
            HO.load_for(other)
    HO.load_for("holdout_chartmark_short_v2.json")


def test_other_ledgers_refuse_the_v2_ledger():
    from strategy.chartmark import holdout as LH
    from strategy.chartmark_s import holdout as V1H
    for H in (LH, V1H):
        with pytest.raises(H.HoldoutRefused):
            H.load_for("holdout_chartmark_short_v2.json")


def test_ledger_spends_once_and_records_windows(ledger):
    keep, aside, side = HO.split_dates(["2021-12-30", "2022-01-03", "2025-09-05", "2025-09-08"],
                                       spend=True, candidate="CHARTMARK-S-v2", verdict="PASS")
    assert keep == ["2022-01-03", "2025-09-05"]
    rec = json.loads(ledger.read_text())
    assert rec["candidate"] == "CHARTMARK-S-v2"
    assert rec["excluded_entry_windows"] == [["2025-02-19", "2025-03-04"], ["2025-06-22", "2025-07-03"]]
    with pytest.raises(HO.HoldoutRefused):
        HO.split_dates(["2023-01-01"], spend=True, candidate="CHARTMARK-S-v2", verdict="PASS")


def test_training_split_and_windows():
    keep, aside, _ = HO.split_dates(["2021-12-30", "2022-01-03", "2025-09-08"])
    assert keep == ["2021-12-30"] and aside == 2
    assert HO.excluded("2025-02-19") and HO.excluded("2025-07-03") and not HO.excluded("2025-03-05")
    assert HO.is_seen("2025-09-08") and not HO.is_seen("2025-09-07")


def test_the_real_ledger_is_unspent():
    assert not (Path(__file__).resolve().parents[3] / "holdout_chartmark_short_v2.json").exists()


# ---- G2 pre-flight is count-only ---------------------------------------------------------------------------
def test_preflight_refuses_pnl_flags():
    for f in ("--pnl", "--backtest", "--holdout", "--limit=10", "--net", "--markets=CL"):
        with pytest.raises(SystemExit):
            PF.main([f])


def test_preflight_report_has_counts_by_tier_and_no_money():
    fr = walk(6000, 1, drift=-0.005, vol=0.2)
    ind = D.indicators(fr)
    blocks = {n: PF.counts_table(fr, *E.simulate(fr, ind, p)) for n, p in S.VARIANTS.items()}
    txt = PF.report(fr, blocks, PF.context_share(fr, ind), "test")
    for word in ("Tier A", "Tier B", "STOP RULE", "Context bars", "== V-A", "== V-B", "BASE per year"):
        assert word in txt
    body = txt.replace("no price or P&L is reported here", "")       # the header's own disclaimer
    for bad in ("$", "net ", "gross", "P&L", "profit", "win rate", "exit price"):
        assert bad not in body
    b = blocks["BASE"]
    assert b["by_tier"]["A"]["fills"] + b["by_tier"]["B"]["fills"] == b["n"]
    assert sum(r["A"] + r["B"] for r in b["per_year"].values()) == b["n"]


def test_preflight_stop_rule_text():
    fr = walk(600, 1, vol=0.05)
    ind = D.indicators(fr)
    blocks = {n: PF.counts_table(fr, *E.simulate(fr, ind, p)) for n, p in S.VARIANTS.items()}
    assert "UNDERPOWERED" in PF.report(fr, blocks, PF.context_share(fr, ind), "t")


# ---- G6 fidelity (seen window) -----------------------------------------------------------------------------
def test_fills_near_is_plus_minus_one_bar():
    import pandas as pd
    ny = pd.DatetimeIndex(pd.date_range("2026-09-09 20:00", periods=6, freq="h"))
    tr = [E.TradeT(3, 4, 96.25, 96.0, 97, 0.7, "P0", 0, 0, 2, tier=2)]      # entry_j 3 -> 23:00
    assert PA.fills_near(ny, tr, pd.Timestamp("2026-09-09 22:00"))
    assert PA.fills_near(ny, tr, pd.Timestamp("2026-09-10 00:00"))
    assert not PA.fills_near(ny, tr, pd.Timestamp("2026-09-09 21:00"))


def test_g6_marks_are_the_registered_ones():
    assert PA.REJECTED == ("08 Sep 08:00", "08 Sep 22:00", "09 Sep 00:00", "09 Sep 13:00", "09 Sep 20:00",
                           "10 Sep 19:00", "10 Sep 21:00", "14 Sep 01:00")
    assert PA.ACCEPT_1 == ("09 Sep 22:00", 96.25, 0.02)
    assert PA.ACCEPT_2[:2] == ("11 Sep 01:00", 102.09)


def test_g6_runs_on_the_seen_bars_and_reports_all_ten_marks():
    out = Path(os.environ.get("CHARTMARK_OUT", r"D:\Trading\Claude outputs"))
    csv = out / "w15_0032_cl1_1h_bars_indicators.csv"
    if not csv.exists():
        pytest.skip("seen-window bars not on this machine")
    txt, ok = PA.run(csv, log=lambda *_: None)
    for s in PA.REJECTED + (PA.ACCEPT_1[0], PA.ACCEPT_2[0]):
        assert s in txt
    assert isinstance(ok, bool) and ("G6 fidelity: PASS" in txt) == ok
    body = txt.replace("Counts only, no P&L.", "")
    assert "gross" not in body and "$" not in body and "net " not in body and "exit price" not in body
