import json

import numpy as np
import pytest

from strategy.chartmark import data as D
from strategy.chartmark_v2 import engine as E
from strategy.chartmark_v2 import select_s as SS
from strategy.chartmark_v2 import spec as S
from tests.strategy.chartmark.synth import walk


def frame(n=9000, seed=5):
    return walk(n, seed, drift=0.002, start="2015-05-04 00:00", roll_every=1500)   # runs into 2016


def fake_pf(out, eligible=("K1", "K2", "K3", "K4")):
    blocks = {k: dict(eligible=(k in eligible)) for k in S.CANDIDATES}
    (out / "w15_0036_v2_preflight_20260930.json").write_text(json.dumps(blocks), encoding="utf-8")


def test_cut_frame_ends_at_dev_last_and_clears_last_roll():
    fr = frame()
    assert fr.ny[-1].strftime("%Y-%m-%d") >= "2016-01-01"
    c = SS.cut_frame(fr)
    assert c.ny[-1].strftime("%Y-%m-%d") <= S.DEV_LAST < fr.ny[-1].strftime("%Y-%m-%d")
    assert c.n < fr.n and not c.roll_after[-1]
    nxt = fr.ny[c.n].strftime("%Y-%m-%d")
    assert nxt > S.DEV_LAST                       # the first dropped bar is the first bar after the cut date


def test_nothing_after_the_cut_can_change_the_selection():
    fr = frame()
    mut = D.make_frame(fr.t, fr.o.copy(), fr.h.copy(), fr.l.copy(), fr.c.copy(), fr.v, fr.roll_after, "mut")
    k = SS.cut_frame(fr).n
    for arr in (mut.o, mut.h, mut.l, mut.c):
        arr[k:] += 25.0                            # wreck every bar from 2016 on
    outs = []
    for f in (fr, mut):
        c = SS.cut_frame(f)
        ind = D.indicators(c)
        pre = E.precompute(c, ind)
        outs.append({n: SS.evaluate_candidate(c, ind, n, pre) for n in S.CANDIDATES})
    for n in S.CANDIDATES:
        assert outs[0][n]["mid"] == outs[1][n]["mid"] and outs[0][n]["n"] == outs[1][n]["n"]


def _r(net, dd, n=100):
    return dict(n=n, mid=dict(net=net, dd=dd))


def test_choose_highest_net_then_smaller_drawdown_and_drops():
    pool = list(S.CANDIDATES)
    res = {"K1": _r(500.0, 300.0), "K2": _r(900.0, 400.0), "K3": _r(900.0, 250.0), "K4": _r(1500.0, 100.0, n=74)}
    w, dropped = SS.choose(res, pool)
    assert w == "K3" and dropped == ["K4"]                       # tie on net -> smaller drawdown; K4 has 74 trades
    assert SS.choose(res, ["K1", "K2"])[0] == "K2"               # K3 outside the pre-flight pool
    assert SS.choose({k: _r(1.0, 1.0, n=10) for k in pool}, pool)[0] is None
    # a losing pool still has a winner (least bad) -- the criterion is the highest net, and step C decides
    assert SS.choose({k: _r(-100.0 * (i + 1), 1.0) for i, k in enumerate(pool)}, pool)[0] == "K1"


def test_run_writes_selection_once_and_uses_dev_window_only(tmp_path, monkeypatch):
    fr = frame()
    monkeypatch.setattr(SS, "load_training_frame", lambda arch: fr)
    monkeypatch.setattr(S, "MIN_TRADES_WINDOW", 1)
    fake_pf(tmp_path)
    sel_path = tmp_path / "selection_chartmark_v2.json"
    sel = SS.run("unused", tmp_path, "20260930", selection_path=sel_path, log=lambda *_: None)
    assert sel["winner"] in S.CANDIDATES and sel_path.exists()
    saved = json.loads(sel_path.read_text())
    assert saved["window"] == [S.DEV_FIRST, S.DEV_LAST] and set(saved["nets_mid_1mcl"]) == set(S.CANDIDATES)
    assert saved["last_bar_used"][:10] <= S.DEV_LAST and saved["git_commit"] and saved["timestamp_utc"]
    txt = (tmp_path / "w15_0036_v2_stepS_20260930.txt").read_text(encoding="utf-8")
    assert "WINNER" in txt and "Nothing from 2016-01-01 on was computed" in txt
    with pytest.raises(SystemExit, match="REFUSED"):              # a second selection is refused
        SS.run("unused", tmp_path, "20260930", selection_path=sel_path, log=lambda *_: None)


def test_run_refuses_without_preflight_and_writes_no_selection_when_not_read(tmp_path, monkeypatch):
    fr = frame()
    monkeypatch.setattr(SS, "load_training_frame", lambda arch: fr)
    sel_path = tmp_path / "selection_chartmark_v2.json"
    with pytest.raises(SystemExit, match="pre-flight"):
        SS.run("unused", tmp_path, "x", selection_path=sel_path, log=lambda *_: None)
    fake_pf(tmp_path, eligible=())                                # empty pool -> NOT READ
    sel = SS.run("unused", tmp_path, "x", selection_path=sel_path, log=lambda *_: None)
    assert sel["winner"] is None and not sel_path.exists()


def test_main_refuses_pnl_holdout_and_confirmation_flags():
    for flag in ("--holdout", "--limit=3", "--seen", "--confirm", "--markets=CL", "--candidate=K1", "--variants", "--grid"):
        assert SS.main([flag]) == 2
