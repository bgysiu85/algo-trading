"""WICK-REV runner: G2 refuses outcomes, G4 holdout, end-to-end report (W15-0063 sec 7-8)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from strategy.futbt.holdout import HoldoutRefused
from strategy.wick_rev import holdout as HO
from strategy.wick_rev import report as R
from strategy.wick_rev import run as RUN
from strategy.wick_rev import signals as G
from strategy.wick_rev import spec as S
from strategy.wick_rev import study, trades
from tests.strategy.wick_rev.synth import random_walk, raw_bars


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(HO.H, "ledger_path", tmp_path / "ledger.json")
    return tmp_path / "ledger.json"


def test_preflight_never_calls_the_race_or_the_trade_simulation(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("G2 must not read outcomes")
    monkeypatch.setattr(G, "race", boom)
    monkeypatch.setattr(trades, "simulate", boom)
    monkeypatch.setattr(study, "analyse", boom)
    text = RUN.mode_preflight({("MNQ", "1H"): random_walk(2500, seed=3)}, "synthetic")
    assert "G2 COUNT-ONLY" in text and "No race outcome" in text and "NET" not in text and "P(rev)" not in text


def test_full_report_has_every_section_and_negatives_in_brackets():
    res = study.analyse(random_walk(5000, seed=9))
    text = R.combo_report(res, window="synthetic")
    for need in ("READING:", "k = 1.0 x ATR", "k = 0.5 x ATR", "k = 1.5 x ATR", "Spearman rho", "DOLLARS",
                 "primary group:", "classic shape:", "sample trades", "excess reversals by year", "99.5% CI"):
        assert need in text, need
    assert "($" in text                                     # a losing random-walk strategy prints bracketed negatives
    assert R.usd(-1234.4) == "($1,234)" and R.usd(5) == "$5" and R.pts(-0.0123) == "(1.23)"


def test_mcl_30m_is_reported_only_with_no_pass_fail():
    res = study.analyse(random_walk(3000, seed=2, market="MCL", tf="30m"), reported_only=True)
    assert all(sd["reading"]["verdict"] == "REPORTED ONLY" for sd in res["sides"].values())


def test_too_few_signals_is_not_read_rather_than_failed():
    res = study.analyse(random_walk(900, seed=5))
    assert {sd["reading"]["verdict"] for sd in res["sides"].values()} <= {"NOT READ"}


def test_a_planted_effect_shows_an_edge_and_a_null_does_not():
    # planted: after a long upper wick in an up context, the next bar plunges
    rng = np.random.default_rng(3)
    n = 30000
    s = random_walk(n, seed=21, step=1.0)
    f = G.features(s)
    idx = G.signal_indices(f, 1, primary_only=True)
    idx = idx[(idx > 300) & (idx < n - 30) & (rng.random(len(idx)) < 0.8)]
    for t in idx.tolist():                      # plant: the bar after a long upper wick plunges through 1 x ATR
        s.l[t + 1] = min(s.l[t + 1], s.c[t] - 3 * f.atr[t])
    res = study.analyse(s)
    g = res["sides"][1]["by_k"][1.0]["primary"]
    base = res["sides"][1]["by_k"][1.0]["all"]
    assert g["p_rev"] > base["p_rev"] + 0.05
    assert res["sides"][1]["by_k"][1.0]["primary"]["edge"]["lo995"] > 0           # the planted effect is visible
    null = study.analyse(random_walk(n, seed=22))
    assert null["sides"][1]["reading"]["verdict"] in ("NO EDGE", "NOT READ")


def test_make_series_cuts_by_session_before_building(monkeypatch):
    idx = pd.date_range("2021-12-27 18:00", periods=24 * 10, freq="h", tz="America/New_York").tz_convert("UTC")
    n = len(idx)
    v = np.arange(n, dtype=float)
    src = raw_bars(idx, v, v + 1, v - 1, v + 0.5)
    s = RUN.make_series(src, "MCL", "1H", start="2021-12-27", end="2021-12-31")
    assert s.session.max() <= np.datetime64("2021-12-31")
    all_ = RUN.make_series(src, "MCL", "1H", start="2021-12-27", end="2030-01-01")
    assert all_.n > s.n


def test_train_writes_a_verdict_file_the_holdout_reads(tmp_path):
    series = {("MNQ", "1H"): random_walk(2500, seed=1)}
    vp = tmp_path / "v.json"
    text = RUN.mode_train(series, vp)
    j = json.loads(vp.read_text(encoding="utf-8"))
    assert set(j["verdicts"]) == {"MNQ-1H-up", "MNQ-1H-down"} and "none" in text


def test_holdout_is_not_spent_when_nothing_shows_an_edge(tmp_path, ledger):
    vp = tmp_path / "v.json"
    vp.write_text(json.dumps({"verdicts": {"MNQ-1H-up": {"shows_edge": False}}}), encoding="utf-8")
    with pytest.raises(RUN.Refused):
        RUN.mode_holdout({}, {}, vp)
    assert not ledger.exists()


def test_holdout_spends_once_and_scores_only_the_listed_directions(tmp_path, ledger):
    vp = tmp_path / "v.json"
    vp.write_text(json.dumps({"verdicts": {"MNQ-1H-up": {"shows_edge": True}, "MNQ-1H-down": {"shows_edge": False}}}),
                  encoding="utf-8")
    hold = {("MNQ", "1H"): random_walk(2500, seed=4), ("MNQ", "4H"): random_walk(2500, seed=5, tf="4H")}
    text = RUN.mode_holdout(hold, {}, vp)
    assert ledger.exists() and json.loads(ledger.read_text(encoding="utf-8"))["candidate"] == "WICK-REV"
    assert "up->down" in text and "down->up" not in text and "MNQ 4H" not in text
    with pytest.raises(HoldoutRefused):                      # second spend refused
        RUN.mode_holdout(hold, {}, vp)


def test_holdout_refuses_narrowing_and_other_lines_ledgers(ledger):
    for argv in (["--mode", "holdout", "--combos", "MNQ:1H"], ["--mode", "holdout", "--limit", "5"]):
        with pytest.raises(RUN.Refused):
            RUN.main(argv)
    with pytest.raises(HoldoutRefused):
        HO.H.split_dates(["2022-01-03"], limit=3)
    for other in ("holdout_chartmark_v2.json", "holdout_tl_v2.json", "holdout_w16_dvp.json", "holdout_htf_ben_v2.json"):
        with pytest.raises(HoldoutRefused):
            HO.H.load_for(other)
    assert S.LEDGER == "holdout_w15_0063.json"


def test_other_futbt_holdouts_refuse_this_ledger_by_name():
    from strategy.crudele_3s import holdout as CH
    with pytest.raises(HoldoutRefused):
        CH.load_for("holdout_w15_0063.json")


def test_training_window_keeps_2021_12_31_and_drops_2022_01_03(ledger):
    keep, aside, _ = HO.split_dates(["2021-12-30", "2021-12-31", "2022-01-03", "2025-09-22", "2025-09-23"])
    assert keep == ["2021-12-30", "2021-12-31"] and aside == 3
    # mutation: a lock one year late would let 2022 into training - the assertion above is what catches it
    HO.H.lock_from = "2023-01-01"
    try:
        keep2, _, _ = HO.split_dates(["2021-12-31", "2022-01-03"])
        assert keep2 != ["2021-12-31"]
    finally:
        HO.H.lock_from = "2022-01-01"
