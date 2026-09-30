from pathlib import Path

import numpy as np
import pytest

from strategy.chartmark_s3 import controls as CT
from strategy.chartmark_s3 import data as D
from strategy.chartmark_s3 import engine as E
from strategy.chartmark_s3 import run as R
from strategy.chartmark_s3 import spec as S
from tests.strategy.chartmark.synth import walk


@pytest.fixture(scope="module")
def res(tmp_path_factory):
    fr = walk(9000, 1, drift=-0.004, vol=0.2, start="2010-06-07 00:00")
    out = tmp_path_factory.mktemp("out")
    r = R.run_frames(fr, out, "t", draws=20, log=lambda *_: None)
    r["_out"] = out
    r["_fr"] = fr
    return r


def test_report_carries_the_waiver_headline_and_all_sections(res):
    txt = R.report(res)
    assert R.WAIVER in txt.splitlines()[2]
    for w in ("VERDICT", "HEADLINE", "BY TIER", "SEC 4 CRITERIA", "BASE per year", "CONTROLS", "C1 Donchian", "C3 random",
              "REFERENCE, CHARTMARK-S v1 base", "V-B1", "V-A ", "V-B ", "NEIGHBOUR GRID", "CAVEATS"):
        assert w in txt
    assert "C2" not in txt.split("CONTROLS")[1].split("VARIANTS")[0].replace("REFERENCE", "")


def test_outputs_written_and_json_has_waiver(res):
    import json
    out = res["_out"]
    js = json.loads((out / "w15_0042_chartmark_short_v3_backtest_t.json").read_text())
    assert js["waiver"] == R.WAIVER and set(js["tiers"]) == {"A", "B"}
    assert (out / "w15_0042_chartmark_short_v3_trades_base_t.csv").exists()


def test_tier_rows_sum_to_the_base(res):
    t = res["tiers"]
    b = res["V"]["BASE"]["MCL_mid"]
    assert t["A"]["fills"] + t["B"]["fills"] == b["n"]
    assert t["A"]["net_mid"] + t["B"]["net_mid"] == pytest.approx(b["net"])
    assert sum(y["fills"] for y in res["years"]) == b["n"]
    assert sum(y["net_mid"] for y in res["years"]) == pytest.approx(b["net"])


def test_grid_has_27_cells_and_variants_are_the_registered_set(res):
    assert len(res["grid"]) == 27
    assert list(res["V"]) == ["BASE", "V-A", "V-B", "V-B1", "V-RANGE", "V-SESSION", "V-AVOID"]


def test_c3_is_seeded_and_uses_the_v3_constant(res):
    fr = res["_fr"]
    ind = D.indicators(fr)
    idx, cand = CT.candidate_outcomes(fr, ind, S.BASE)
    net = np.array([(t.entry_px - t.exit_px) * 100 for t in cand])
    py = {2010: 30, 2011: 20}
    a = CT.c3_draws(fr, idx, net, py, 50)
    b = CT.c3_draws(fr, idx, net, py, 50)
    assert (a == b).all() and a.std() > 0
    import inspect
    assert 'b"CL-S3"' in inspect.getsource(CT.c3_draws)


def test_stop_rule_refuses_an_underpowered_base(tmp_path):
    fr = walk(500, 1, vol=0.05, start="2010-06-07 00:00")
    with pytest.raises(SystemExit) as e:
        R.run_frames(fr, tmp_path, "t", draws=5, log=lambda *_: None, write=False)
    assert "STOP RULE" in str(e.value)


def test_run_refuses_holdout_limit_and_pnl_flags():
    for f in ("--holdout", "--limit=10", "--spend", "--seen", "--markets=CL"):
        with pytest.raises(SystemExit):
            R.main([f])


def test_run_uses_the_training_loader_and_no_ledger():
    import inspect
    src = inspect.getsource(R)
    assert "split_dates" not in src and "ledger" not in src.lower() and "load_for" not in src
    assert "load_training_frame" in inspect.getsource(R.run)
