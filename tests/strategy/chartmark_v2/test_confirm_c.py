import json

import numpy as np
import pandas as pd
import pytest

from strategy.chartmark import data as D
from strategy.chartmark_v2 import confirm_c as CC
from strategy.chartmark_v2 import engine as E
from strategy.chartmark_v2 import spec as S
from tests.strategy.chartmark.synth import walk


def frame(n=9000, seed=5):
    return walk(n, seed, drift=0.002, start="2015-05-04 00:00", roll_every=1500)      # runs into 2016


def write_sel(path, winner="K1", **over):
    sel = dict(winner=winner, dropped=[], window=[S.DEV_FIRST, S.DEV_LAST],
               nets_mid_1mcl={k: -100.0 for k in S.CANDIDATES}, trades={k: 100 for k in S.CANDIDATES},
               params={k: dict(prev_high=p.prev_high, theta=p.theta) for k, p in S.CANDIDATES.items()},
               last_bar_used="2015-12-31 16:00:00-05:00")
    sel.update(over)
    path.write_text(json.dumps(sel), encoding="utf-8")
    return sel


def test_refuses_missing_selection_unknown_winner_changed_params_and_non_dev_selection(tmp_path):
    p = tmp_path / "selection_chartmark_v2.json"
    with pytest.raises(SystemExit, match="missing"):
        CC.load_selection(p)
    write_sel(p, winner="K9")
    with pytest.raises(SystemExit, match="registered candidates"):
        CC.load_selection(p)
    sel = write_sel(p)
    sel["params"]["K1"]["theta"] = 0.04
    p.write_text(json.dumps(sel))
    with pytest.raises(SystemExit, match="differ"):
        CC.load_selection(p)
    write_sel(p, last_bar_used="2016-01-04 10:00:00-05:00")
    with pytest.raises(SystemExit, match="development-window"):
        CC.load_selection(p)
    write_sel(p, winner="K3")
    w, prm, _ = CC.load_selection(p)
    assert w == "K3" and prm == S.K3


def test_window_start_is_first_2016_bar_and_refuses_a_bar_after_the_window():
    fr = frame()
    s = CC.window_start(fr)
    assert fr.ny[s].strftime("%Y-%m-%d") >= S.CONF_FIRST > fr.ny[s - 1].strftime("%Y-%m-%d")
    late = walk(9000, 5, start="2021-06-01 00:00")                 # runs past 2021-12-31
    with pytest.raises(SystemExit, match="after the confirmation window"):
        CC.window_start(late)


def test_main_refuses_holdout_candidate_window_and_narrowing_flags():
    for flag in ("--holdout", "--limit=3", "--seen", "--candidate=K3", "--winner=K2", "--window=2010", "--from=2016-03-01",
                 "--draws=10", "--variants", "--grid", "--force", "--select", "--dev"):
        assert CC.main([flag]) == 2


def test_engine_and_controls_take_no_trade_before_the_window():
    fr = frame()
    start = CC.window_start(fr)
    ind = D.indicators(fr)
    tr, _ = E.simulate(fr, ind, S.K1, start=start)
    assert tr and all(t.entry_j > start for t in tr)
    c1 = CC.donchian_c1(fr, start)
    assert c1 and all(t.entry_j > start for t in c1)
    idx, net = CC.c3_candidates(fr, ind, S.K1, start)
    assert len(idx) == len(net) and idx.min() >= start


def test_donchian_c1_has_no_session_filter_and_fills_at_level_or_open():
    fr = frame()
    tr = CC.donchian_c1(fr, 0)
    hours = {int(fr.ny[t.placed_j].hour) for t in tr}
    assert len(hours) > 8                                          # entries armed in every part of the day
    for t in tr:
        assert t.entry_px >= fr.h[t.placed_j - 19: t.placed_j + 1].max() + S.TICK - 1e-9


def test_c3_draws_are_deterministic_and_use_the_registered_seed():
    fr = frame()
    ind = D.indicators(fr)
    start = CC.window_start(fr)
    idx, net = CC.c3_candidates(fr, ind, S.K1, start)
    py = {2016: 5}
    a, b = CC.c3_draws(fr, idx, net, py, 30), CC.c3_draws(fr, idx, net, py, 30)
    assert np.array_equal(a, b) and a.std() > 0
    from zlib import crc32
    rng = np.random.default_rng([crc32(b"0"), crc32(b"CL-v2"), 5])
    pool = net[np.asarray(fr.ny.year)[idx] == 2016]
    assert a[0] == pytest.approx(float(pool[rng.integers(0, len(pool), size=5)].sum()))


def _df(nets, years, start="2016-01-04"):
    t = pd.date_range(start, periods=len(nets), freq="7D")
    return pd.DataFrame(dict(entry_t=t, exit_t=t + pd.Timedelta(days=1), year=years, net=nets, gross=nets, cost=0.0))


def test_criteria_and_verdict_logic():
    yrs = [2016, 2017, 2018, 2019, 2020, 2021] * 4
    good = _df([100.0] * 24, yrs)
    high = _df([80.0] * 24, yrs)
    c1 = _df([1.0, -3.0] * 12, yrs)
    rows = CC.evaluate(good, high, c1, c3_p99=500.0, n_grid_pos=20)
    assert [r["n"] for r in rows] == list(range(1, 10))
    assert all(r["ok"] for r in rows[:4] + rows[6:8]) and rows[8]["ok"] is False           # 24 trades < 75
    assert CC.verdict(rows).startswith("NOT READ")
    big = _df([100.0] * 80, yrs * 3 + [2016] * 8)
    rows = CC.evaluate(big, _df([80.0] * 80, yrs * 3 + [2016] * 8), _df([1.0, -3.0] * 40, yrs * 3 + [2016] * 8), 500.0, 20)
    assert CC.verdict(rows).startswith("PASS")
    rows = CC.evaluate(big, big, _df([1.0, -3.0] * 40, yrs * 3 + [2016] * 8), 50000.0, 20)       # below C3 p99
    assert rows[5]["ok"] is False and "closes the study" in CC.verdict(rows)
    rows = CC.evaluate(big, big, _df([1.0, -3.0] * 40, yrs * 3 + [2016] * 8), 500.0, 17)         # 17 of 27
    assert rows[7]["ok"] is False and CC.verdict(rows) == "FAIL"
    loser = _df([-5.0] * 80, yrs * 3 + [2016] * 8)
    rows = CC.evaluate(loser, loser, big, 100.0, 0)
    assert not rows[0]["ok"] and not rows[1]["ok"] and not rows[6]["ok"]
    lopsided = _df([1000.0] + [-1.0] * 79, [2016] + yrs * 3 + [2017] * 7)
    rows = CC.evaluate(lopsided, lopsided, _df([1.0, -3.0] * 40, yrs * 3 + [2016] * 8), 0.0, 27)
    assert rows[6]["ok"] is False and rows[2]["ok"] is False                                 # one year carries the net


def test_run_end_to_end_writes_outputs_ledger_once_and_reads_nothing_after_2021(tmp_path, monkeypatch):
    fr = frame()
    sel_path, led = tmp_path / "selection_chartmark_v2.json", tmp_path / "confirmation_chartmark_v2.json"
    write_sel(sel_path)
    with pytest.raises(SystemExit, match="missing"):
        CC.run("x", tmp_path, "t", selection_path=tmp_path / "none.json", ledger_path=led, frame=fr, log=lambda *_: None)
    res = CC.run("x", tmp_path, "t", selection_path=sel_path, ledger_path=led, draws=40, frame=fr, log=lambda *_: None)
    assert res["winner"] == "K1" and len(res["crit"]) == 9 and len(res["grid"]) == 27 and len(res["V"]) == 9
    assert all(str(fr.ny[t.entry_j].date()) >= S.CONF_FIRST for t in res["trades"])
    txt = (tmp_path / "w15_0036_v2_stepC_t.txt").read_text(encoding="utf-8")
    assert "VERDICT" in txt and "AMENDMENT 4.3 CRITERIA" in txt and "No bar from 2022 on was read" in txt
    assert json.loads(led.read_text())["winner"] == "K1" and "NOT spent" in led.read_text()
    assert (tmp_path / "w15_0036_v2_stepC_t.json").exists() and (tmp_path / "w15_0036_v2_stepC_trades_t.csv").exists()
    with pytest.raises(SystemExit, match="REFUSED"):
        CC.run("x", tmp_path, "t", selection_path=sel_path, ledger_path=led, draws=40, frame=fr, log=lambda *_: None)


def test_module_has_no_holdout_path():
    src = open(CC.__file__, encoding="utf-8").read()
    assert "chartmark_v2.holdout" not in src and "import holdout" not in src and "H.spend" not in src
