"""Holdout locks, pre-flight no-P&L guarantee, runner refusals (W15-0022 subitem 5)."""
from __future__ import annotations

import json

import pytest

from strategy.breit_cap import holdout as BH
from strategy.breit_cap import preflight as BPF
from strategy.crudele_3s import holdout as CH
from strategy.crudele_3s import preflight as CPF
from strategy.crudele_3s import run as CRUN
from strategy.breit_cap import run as BRUN
from strategy.futbt import loading as LD
from strategy.futbt.holdout import Holdout, HoldoutRefused
from tests.strategy.futbt.synth import frame_from_close, squeeze_breakout_path

DATES = ["2021-12-30", "2021-12-31", "2022-01-03", "2025-09-22", "2025-09-23"]


def _h(tmp_path):
    h = Holdout("T", "holdout_crudele_3s.json", "CRUDELE-3S", "REG")
    h.ledger_path = tmp_path / "ledger.json"
    return h


def test_training_excludes_locked():
    keep, aside, _ = CH.split_dates(DATES)
    assert keep == DATES[:2] and aside == 3


def test_limit_and_narrowing_refused():
    with pytest.raises(HoldoutRefused):
        CH.split_dates(DATES, limit=5)
    with pytest.raises(HoldoutRefused):
        CH.split_dates(DATES, markets=["CL"])


def test_other_lines_refused():
    with pytest.raises(HoldoutRefused):
        CH.load_for("holdout_w16_dvp.json")
    with pytest.raises(HoldoutRefused):
        CH.load_for("holdout_breit_cap.json")


def test_spend_once_and_needs_pass(tmp_path):
    h = _h(tmp_path)
    with pytest.raises(HoldoutRefused):
        h.split_dates(DATES, spend=True, candidate="CRUDELE-3S", verdict="FAIL")
    with pytest.raises(HoldoutRefused):
        h.split_dates(DATES, spend=True, candidate="OTHER", verdict="PASS")
    keep, _, _ = h.split_dates(DATES, spend=True, candidate="CRUDELE-3S", verdict="PASS")
    assert keep == ["2022-01-03", "2025-09-22"]
    assert json.loads(h.ledger_path.read_text())["candidate"] == "CRUDELE-3S"
    with pytest.raises(HoldoutRefused):
        h.split_dates(DATES, spend=True, candidate="CRUDELE-3S", verdict="PASS")


def test_seen_window():
    keep, label = CH.seen_dates(DATES)
    assert keep == ["2025-09-23"] and "not evidence" in label


def test_breit_wrapper_candidates():
    assert BH.H.candidate == "BREIT-CAP"


def _frames():
    fr = frame_from_close(squeeze_breakout_path(), start="2012-01-02")
    return {"SYN": fr}


def _no_pnl(obj):
    bad = ("exit_px", "gross", "net", "pnl", "reason_px", "exit_price")
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert not any(b in str(k).lower() for b in bad), k
            _no_pnl(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _no_pnl(v)


def test_crudele_preflight_counts_only():
    rep = CPF.run_all(_frames(), log=lambda *_: None)
    clean = CPF._clean(rep)
    _no_pnl(clean)
    assert "entries" not in clean["markets"]["SYN"]
    txt = CPF.render(clean)
    assert "NO EXIT PRICE" in txt.upper() or "no exit price" in txt


def test_breit_preflight_counts_only():
    frs = _frames()
    reps = BPF.run_all(frs, log=lambda *_: None)
    summ = BPF.summarize(reps, cl4h_key=None)
    _no_pnl(summ)
    txt = BPF.render(reps, summ, BPF.check_volume(frs))
    assert "P&L" in txt


def test_breit_volume_check_flags_missing():
    fr = frame_from_close(squeeze_breakout_path(), vol=[0.0] * 400)
    fr2 = frame_from_close(squeeze_breakout_path())
    v = BPF.check_volume({"BAD": fr, "OK": fr2})
    assert v["failing"] == ["BAD"]


@pytest.mark.parametrize("run", [CRUN, BRUN])
@pytest.mark.parametrize("flag", ["--limit=5", "--holdout", "--backtest", "--pnl"])
def test_runners_refuse_pnl_flags(run, flag):
    with pytest.raises(SystemExit) as e:
        run.main(["--preflight", flag])
    assert e.value.code == 2


def test_unknown_market_rejected():
    with pytest.raises(SystemExit):
        CRUN.main(["--preflight", "--markets", "ZZ"])


def test_cl4h_cut_keeps_only_training_sessions():
    import pandas as pd
    idx = pd.date_range("2021-12-29 00:00", "2022-01-05 23:00", freq="h", tz="America/New_York")
    df = pd.DataFrame({"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 1.0}, index=idx)
    out = LD.cut_1h_to_training(df)
    assert len(out) and out.index.max() < pd.Timestamp("2022-01-01", tz="America/New_York") + pd.Timedelta(hours=18)


def test_rng_for_is_seeded_and_market_specific():
    from strategy.futbt.controls import rng_for
    a = rng_for(3, "CL").random(4)
    assert (a == rng_for(3, "CL").random(4)).all()
    assert (a != rng_for(3, "GC").random(4)).any()
    assert (a != rng_for(4, "CL").random(4)).any()
