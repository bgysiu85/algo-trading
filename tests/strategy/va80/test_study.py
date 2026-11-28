"""VA80 study layer (W15-0041): IBKR costs (G5), book statistics, C-RT / C-ND scoring, the seven criteria, the 27-cell
grid, reported variants, report writers and the --run path. No real data: hand-built numbers and synthetic sessions."""
import json
import re

import numpy as np
import pytest

from strategy.va80 import costs as C
from strategy.va80 import engine as E
from strategy.va80 import report as RP
from strategy.va80 import run as RUN
from strategy.va80 import spec as S
from strategy.va80 import study as ST
from strategy.va80 import variants as V
from tests.strategy.va80 import synth as Y

T = 0.25


def _store(*sessions):
    st = E.Store({})
    for s in sessions:
        st._s[s.date] = s
    return st


def _t(date, side, entry, exit_px, why, **k):
    """A hand-built trade record (as engine.trade_record) with its single leg."""
    pts = side * (exit_px - entry)
    d = {"date": date, "side": side, "val": 100.0, "vah": 110.0, "entry_minute": 600, "entry_px": entry,
         "target": 100.0, "stop": 112.0, "exit_minute": 700, "exit_px": exit_px, "exit_reason": why,
         "gross_points": pts}
    d.update(k)
    return d


# ------------------------------------------------------------------ G5: IBKR costs (Amendment 2)
def test_amendment2_fee_table_is_pinned():
    assert C.FEE_PER_SIDE == {"MES": 0.62, "MNQ": 0.62, "ES": 2.26, "NQ": 2.26}
    assert C.POINT_VALUE == {"MES": 5.0, "MNQ": 2.0, "ES": 50.0, "NQ": 20.0}
    assert C.TICK_VALUE == {"MES": 1.25, "MNQ": 0.50, "ES": 12.50, "NQ": 5.00}
    for v in C.TICK_VALUE:
        assert C.TICK_VALUE[v] == C.POINT_VALUE[v] * S.TICK
    assert C.LEVEL_TICKS == {"low": 0, "mid": 1, "high": 2}


def test_side_costs_match_the_amendment_levels():
    # Amendment 2: low / mid / high per side
    assert [round(C.side_cost("MES", lv, "market_or_stop"), 2) for lv in ("low", "mid", "high")] == [0.62, 1.87, 3.12]
    assert [round(C.side_cost("MNQ", lv, "market_or_stop"), 2) for lv in ("low", "mid", "high")] == [0.62, 1.12, 1.62]
    assert [round(C.side_cost("ES", lv, "market_or_stop"), 2) for lv in ("low", "mid", "high")] == [2.26, 14.76, 27.26]
    assert [round(C.side_cost("NQ", lv, "market_or_stop"), 2) for lv in ("low", "mid", "high")] == [2.26, 7.26, 12.26]
    # a resting target limit fill pays the fee and no ticks, at every level
    for v in C.FEE_PER_SIDE:
        for lv in C.LEVEL_TICKS:
            assert C.side_cost(v, lv, "target") == C.FEE_PER_SIDE[v]
    with pytest.raises(ValueError):
        C.side_cost("MES", "mid", "market")
    with pytest.raises(KeyError):
        C.side_cost("MES", "extreme", "target")


def test_round_trip_costs_by_exit_kind():
    # "Round trip 1 MES at mid = $3.74 (2 x $1.87)" for a market / stop exit; target exit pays no ticks on the way out
    assert round(C.trade_cost("MES", "mid", S.STOP), 2) == 3.74
    assert round(C.trade_cost("MES", "mid", S.TIME), 2) == 3.74
    assert round(C.trade_cost("MES", "mid", S.TARGET), 2) == round(1.87 + 0.62, 2)
    assert round(C.trade_cost("MES", "low", S.STOP), 2) == 1.24 == round(C.trade_cost("MES", "low", S.TARGET), 2)
    assert round(C.trade_cost("ES", "high", S.STOP), 2) == round(2 * 27.26, 2)
    assert round(C.trade_cost("MES", "mid", S.STOP, weight=0.5), 3) == round(3.74 / 2, 3)
    assert C.exit_kind(S.TARGET) == "target" and C.exit_kind(S.STOP) == C.exit_kind(S.TIME) == "market_or_stop"


def test_price_trade_dollars_and_legs():
    t = _t("2019-03-05", S.SHORT, 108.0, 100.0, S.TARGET)                       # +8 points
    p = C.price_trade(t, "MES", "mid")
    assert p["gross"] == 40.0 and round(p["cost"], 2) == 2.49 and round(p["net"], 2) == 37.51
    lose = _t("2019-03-06", S.LONG, 105.0, 101.0, S.STOP)                       # -4 points
    q = C.price_trade(lose, "MES", "mid")
    assert q["gross"] == -20.0 and round(q["net"], 2) == round(-20 - 3.74, 2)
    # two half legs: half to a target at 106, half stopped at 112 (short from 108)
    two = _t("2019-03-07", S.SHORT, 108.0, 100.0, S.TARGET,
             legs=[(0.5, 2.0, S.TARGET), (0.5, -4.0, S.STOP)])
    r = C.price_trade(two, "MES", "mid")
    assert r["gross"] == 0.5 * 2 * 5 + 0.5 * -4 * 5
    assert round(r["cost"], 3) == round(0.5 * 2.49 + 0.5 * 3.74, 3)


# ------------------------------------------------------------------ book statistics
def test_book_stats_known_sequence():
    trades = [_t("2019-01-02", 1, 100, 110, S.TARGET), _t("2019-01-03", 1, 100, 96, S.STOP),
              _t("2020-01-02", -1, 100, 108, S.STOP), _t("2020-01-03", -1, 100, 97, S.TARGET)]
    df = ST.price_book(trades, "MES", "low")
    s = ST.book_stats(df)
    assert s["trades"] == 4 and s["wins"] == 2 and s["losses"] == 2 and s["win_pct"] == 50.0
    assert s["exits"] == {"target": 2, "stop": 2, "time": 0}
    gross = (10 - 4 - 8 + 3) * 5
    assert s["gross"] == gross and round(s["costs"], 2) == round(4 * 1.24, 2) and round(s["net"], 2) == round(gross - 4 * 1.24, 2)
    # closed-trade equity in date order: +48.76, +28.76, -11.24..., worst peak-to-trough = 60 + 2*1.24 ... computed below
    nets = df["net"].to_numpy()
    eq = np.cumsum(nets)
    assert round(s["max_dd"], 6) == round(float((np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()), 6)
    assert round(s["mean_win"], 2) == round(np.mean([n for n in nets if n > 0]), 2)
    assert round(s["mean_loss"], 2) == round(np.mean([n for n in nets if n < 0]), 2)
    by = ST.by_year(df)
    assert set(by["net"]) == {2019, 2020} and round(sum(by["net"].values()), 6) == round(s["net"], 6)
    sd = ST.by_side(df)
    assert sd["long"]["trades"] == 2 and sd["short"]["trades"] == 2


def test_max_drawdown_edge_cases():
    assert ST.max_drawdown(np.array([])) == 0.0
    assert ST.max_drawdown(np.array([5.0, 5.0])) == 0.0
    assert ST.max_drawdown(np.array([-3.0, -4.0])) == 7.0                        # the start counts as the first peak
    assert ST.max_drawdown(np.array([10.0, -4.0, -8.0, 3.0])) == 12.0


def test_distances_in_points():
    ts = [_t("2019-01-02", S.SHORT, 108.0, 100.0, S.TARGET, target=100.0, stop=110.0),
          _t("2019-01-03", S.LONG, 102.0, 110.0, S.TARGET, target=110.0, stop=100.0)]
    d = ST.distances(ts)
    assert d["target"]["p50"] == 8.0 and d["stop"]["p50"] == 2.0 and d["target"]["p10"] <= d["target"]["p90"]


def test_halves_split_at_the_median_entry_date_and_empty_half_fails():
    trades = [_t(f"2019-01-0{i}", 1, 100, 101 if i != 4 else 98, S.TARGET if i != 4 else S.STOP) for i in range(2, 8)]
    df = ST.price_book(trades, "MES", "mid")
    h = ST.halves(df)
    assert h["median_date"] == "2019-01-05"                                      # sorted dates [len//2]
    assert h["early_n"] == 4 and h["late_n"] == 2                                # early = date <= median
    assert round(h["early"] + h["late"], 6) == round(df["net"].sum(), 6)
    same = ST.price_book([_t("2019-01-02", 1, 100, 101, S.TARGET)] * 3, "MES", "mid")
    h2 = ST.halves(same)
    assert h2["late_n"] == 0 and h2["both_positive"] is False                    # an empty half fails
    assert ST.halves(ST.price_book([], "MES", "mid"))["both_positive"] is False


def test_sample_trades_spread_over_the_years():
    trades = [_t(f"{2010 + i // 40}-{1 + (i % 40) // 4:02d}-{1 + i % 4:02d}", 1, 100, 101, S.TARGET) for i in range(560)]
    df = ST.price_book(trades, "MES", "mid")
    s = ST.sample_trades(df, 15)
    assert len(s) == 15 and list(s["date"]) == sorted(s["date"]) and s["year"].nunique() >= 12
    assert len(ST.sample_trades(df.iloc[:5], 15)) == 5


# ------------------------------------------------------------------ the seven criteria
def _crit(**kw):
    base = dict(net_mid=500.0, net_high=100.0, crt_p95=200.0, halves={"early": 300.0, "late": 200.0, "both_positive": True},
                year_nets={2010: 100.0, 2011: 150.0, 2012: 250.0}, cells_positive=20, n_trades=555)
    base.update(kw)
    return ST.criteria(**base)


def test_criteria_all_pass_and_each_one_fails_on_its_own():
    ok = _crit()
    assert ok["verdict"] == "PASS" and all(c[1] for c in ok["crit"].values()) and ok["closed"] is False
    cases = {1: dict(net_mid=-1.0), 2: dict(crt_p95=600.0), 3: dict(halves={"early": 600.0, "late": -100.0, "both_positive": False}),
             4: dict(net_high=-0.01), 5: dict(year_nets={2010: 400.0, 2011: 50.0, 2012: 50.0}), 6: dict(cells_positive=17)}
    for k, kw in cases.items():
        r = _crit(**kw)
        assert r["crit"][k][1] is False and r["verdict"] == "FAIL", k
        assert [i for i, c in r["crit"].items() if not c[1]][0] == k or k in (1,)      # the named one is among the failures
    assert _crit(crt_p95=600.0)["closed"] is True and _crit(cells_positive=17)["closed"] is False   # failing 2 closes the study
    assert _crit(cells_positive=18)["crit"][6][1] is True and _crit(net_high=0.0)["crit"][4][1] is False   # strictly > 0


def test_criterion_5_year_share_boundary_and_non_positive_net():
    assert _crit(net_mid=500.0, year_nets={2010: 250.0, 2011: 250.0})["crit"][5][1] is True     # exactly 50% is not "more than"
    assert _crit(net_mid=500.0, year_nets={2010: 251.0, 2011: 249.0})["crit"][5][1] is False
    assert _crit(net_mid=-5.0, year_nets={2010: -5.0})["crit"][5][1] is False


def test_fewer_than_200_trades_is_not_read_not_failed():
    r = _crit(n_trades=199)
    assert r["verdict"] == "NOT READ" and r["crit"][7][1] is False
    assert _crit(n_trades=200)["verdict"] == "PASS" and _crit(n_trades=200)["crit"][7][1] is True
    # NOT READ wins over FAIL, so a thin book is never reported as a failure of the rule
    assert _crit(n_trades=50, net_mid=-10.0)["verdict"] == "NOT READ"


# ------------------------------------------------------------------ controls netted with the same costs
def test_draw_net_matches_price_book_for_the_same_fills():
    trades = [_t("2019-01-02", 1, 100, 110, S.TARGET), _t("2019-01-03", 1, 100, 96, S.STOP),
              _t("2019-01-04", -1, 100, 108, S.TIME), _t("2019-01-07", -1, 100, 97, S.TARGET)]
    draws = {"n": np.array([4.0]), "gross_pts": np.array([sum(t["gross_points"] for t in trades)]),
             "n_target": np.array([2.0]), "n_other": np.array([2.0])}
    for lv in ("low", "mid", "high"):
        for veh in ("MES", "ES"):
            want = ST.price_book(trades, veh, lv)["net"].sum()
            assert round(float(ST.draw_net(draws, veh, lv)[0]), 6) == round(float(want), 6)


def test_outcome_of_edge_stop_neither_and_rotated():
    s_edge = Y.path_sess(knots=((570, 105.0), (700, 105.0), (701, 99.0), (959, 99.0)))
    s_stop = Y.path_sess(knots=((570, 105.0), (700, 105.0), (701, 113.0), (959, 113.0)))
    s_none = Y.path_sess(knots=((570, 105.0), (959, 105.0)))
    base = {"rotated": False, "j": 100, "side": S.SHORT, "target": 100.0, "stop": 112.0}
    assert ST.outcome_of(s_edge, base) == "edge" and ST.outcome_of(s_stop, base) == "stop" and ST.outcome_of(s_none, base) == "neither"
    assert ST.outcome_of(s_stop, dict(base, rotated=True)) == "edge"             # the far edge had already traded: reached by definition
    # a TOUCH of the edge counts for the 80% check (a fill needs one tick through; the claim does not)
    touch = Y.path_sess(knots=((570, 105.0), (700, 105.0), (701, 100.0), (959, 100.0)))
    assert ST.outcome_of(touch, base) == "edge"


def test_claim_shares_and_reproduction_threshold():
    c = ST.claim_shares({"edge": 7, "stop": 2, "neither": 1})
    assert c["n"] == 10 and c["edge_pct"] == 70.0 and c["stop_pct"] == 20.0 and c["neither_pct"] == 10.0 and c["reproduced"] is True
    assert ST.claim_shares({"edge": 69, "stop": 20, "neither": 11})["reproduced"] is False
    assert ST.claim_shares({"edge": 0, "stop": 0, "neither": 0})["reproduced"] is False


# ------------------------------------------------------------------ variants (reported, unranked)
def _synthetic(n=40, seed=3):
    days = Y.xnys_days("2019-03-04", n)
    frames = Y.rth_frames(days, seed=seed, gap_sd=12.0, vol=1.2)
    return E.Store(frames), days


def test_iter_setups_reproduces_engine_evaluate():
    store, days = _synthetic()
    base = E.evaluate(store, days)
    got = {d: (status, st) for d, status, st in V.iter_setups(store, days)}
    for r in base:
        status, pack = got[r["date"]]
        assert status == r["status"]
        if status == "ok":
            st = pack[4]
            assert (st["trigger"], st.get("rotated", False), st.get("side", 0)) == (r["trigger"], r["rotated"], r["side"])


def test_primary_trades_equal_engine_trades():
    store, days = _synthetic(60, seed=5)
    want = [r["trade"] for r in E.evaluate(store, days, want_exit=True) if r["trade"]]
    got = V.primary_trades(store, days)
    assert [(t["date"], t["side"], t["exit_reason"], round(t["gross_points"], 6)) for t in got] == \
           [(t["date"], t["side"], t["exit_reason"], round(t["gross_points"], 6)) for t in want]
    assert all(t["legs"] == [(1.0, t["gross_points"], t["exit_reason"])] for t in got)


def test_reclaim_trigger_is_the_first_one_minute_close_back_inside():
    val, vah = 100.0, 110.0
    # opens above 110, closes back inside at minute 580 (10:00 is 600: bar index 10), entry at the next bar's open
    s = Y.path_sess(knots=((570, 113.0), (579, 113.0), (580, 109.0), (959, 105.0)))
    st = V.reclaim_setup(s, val, vah)
    i = int(np.flatnonzero((s.c >= val) & (s.c <= vah))[0])
    assert st["trigger"] and st["j"] == i + 1 and st["side"] == S.SHORT and st["entry_px"] == float(s.o[i + 1])
    assert st["rotated"] is False and st["target"] == val and st["stop"] == float(s.h[:i + 1].max() + T)
    # inside open -> no setup; never back inside -> none; first back-inside after 15:00 -> none
    assert V.reclaim_setup(Y.path_sess(knots=((570, 105.0), (959, 105.0))), val, vah)["trigger"] is False
    assert V.reclaim_setup(Y.path_sess(knots=((570, 113.0), (959, 113.0))), val, vah)["trigger"] is False
    late = Y.path_sess(knots=((570, 113.0), (899, 113.0), (905, 109.0), (959, 109.0)))
    assert V.reclaim_setup(late, val, vah)["trigger"] is False


def test_reclaim_tail_agrees_with_the_engine_setup_for_the_same_entry_bar():
    val, vah = 100.0, 110.0
    s = Y.path_sess(knots=((570, 113.0), (599, 108.0), (959, 104.0)))
    prim = E.setup(s, val, vah)
    assert prim["trigger"]
    again = V.finish_setup(s, val, vah, prim["open"], prim["j"])
    for k in ("trigger", "j", "side", "rotated", "entry_px", "target", "stop"):
        assert again[k] == prim[k]


def test_no_stop_variant_only_ends_by_target_or_time():
    store, days = _synthetic(120, seed=8)
    base = V.primary_trades(store, days)
    ns = V.nostop_trades(store, days)
    assert len(ns) == len(base) and {t["exit_reason"] for t in ns} <= {S.TARGET, S.TIME}
    by = {t["date"]: t for t in base}
    for t in ns:
        if by[t["date"]]["exit_reason"] == S.TARGET:                              # a trade that won before its stop is unchanged
            assert t["exit_reason"] == S.TARGET and round(t["gross_points"], 9) == round(by[t["date"]]["gross_points"], 9)


def test_poc_half_legs_hand_built():
    # short from 108, far edge (VAL) 100, stop 112, POC 105: half out at 105 once it trades through by a tick (104.75)
    path = Y.path_sess(knots=((570, 108.0), (650, 108.0), (700, 104.0), (800, 104.0), (801, 113.0), (959, 113.0)))
    j = 100
    legs = V.poc_legs(path, j, S.SHORT, 108.0, 105.0, 100.0, 112.0)
    assert [l[0] for l in legs] == [0.5, 0.5]
    assert legs[0][2] == S.TARGET and round(legs[0][1], 6) == 3.0                 # (108 - 105)
    assert legs[1][2] == S.STOP and round(legs[1][1], 6) == -4.0                  # stopped at 112 -> -4
    # POC not between the entry and the far edge: both halves go to the far edge, equal to the plain trade
    same = V.poc_legs(path, j, S.SHORT, 108.0, 109.0, 100.0, 112.0)
    plain = E.walk_exit(path, j, S.SHORT, 100.0, 112.0)
    assert same[0][2] == same[1][2] == plain[2] and round(sum(w * g for w, g, _ in same), 9) == round(S.SHORT * (plain[1] - 108.0), 9)


def test_poc_half_trades_total_weight_one_and_same_entries():
    store, days = _synthetic(120, seed=9)
    base, ph = V.primary_trades(store, days), V.poc_half_trades(store, days)
    assert [(t["date"], t["side"]) for t in ph] == [(t["date"], t["side"]) for t in base]
    assert all(abs(sum(l[0] for l in t["legs"]) - 1.0) < 1e-12 for t in ph)


# ------------------------------------------------------------------ analyse, reports, --run (synthetic)
@pytest.fixture(scope="module")
def result():
    es, days = _synthetic(160, seed=21)
    nq, _ = _synthetic(160, seed=22)
    return ST.analyse({"ES": (es, days), "NQ": (nq, days)}, draws=40, log=lambda *_: None)


def test_analyse_shape_and_internal_consistency(result):
    r = result["ES"]
    assert set(r["book"]) == {"low", "mid", "high"} and r["trades"] == r["book"]["mid"]["trades"]
    cells = r["grid"]["cells"]
    assert len(cells) == 27 and r["grid"]["positive"] == sum(1 for c in cells.values() if c["net_mid"] > 0)
    centre = cells[S.CENTRE]                                                    # the grid's centre IS the primary
    assert centre["trades"] == r["trades"] and round(centre["net_mid"], 6) == round(r["book"]["mid"]["net"], 6)
    assert len(r["crt"]["net_mid"]) == 40 and set(r["crt"]["summary"]) == {"p5", "p50", "p95", "p99"}
    assert 0.0 <= r["crt"]["va80_pct"] <= 100.0 and len(r["cnd"]["net_mid"]) == 40
    from strategy.va80 import controls as K
    assert r["crt"]["va80_pct"] == K.percentile_of(r["book"]["mid"]["net"], r["crt"]["net_mid"])      # scored at mid
    assert r["cnd"]["va80_pct"] == K.percentile_of(r["book"]["mid"]["net"], r["cnd"]["net_mid"])
    assert r["crt"]["summary"] == K.summary(r["crt"]["net_mid"])
    assert r["crit"]["crit"][2][1] == (r["book"]["mid"]["net"] > r["crt"]["summary"]["p95"])
    assert ST.money(r["crt"]["summary"]["p95"]) in r["crit"]["crit"][2][2]                           # the p95, not p50 / p99
    assert r["crit"]["crit"][4][1] == (r["book"]["high"]["net"] > 0) and r["crit"]["crit"][6][1] == (r["grid"]["positive"] >= 18)
    assert r["verdict"] == "NOT READ" and r["crit"]["crit"][7][1] is False       # 160 synthetic sessions: far below 200 trades
    assert r["full"]["mid"]["trades"] == r["trades"]
    assert {"reclaim", "one_bracket", "no_stop", "poc_half"} <= set(r["variants"])
    assert r["variants"]["one_bracket"]["trades"] == cells[(1, 30, 0.70)]["trades"]
    assert r["claim"]["all"]["n"] == r["counts"]["triggers"]
    assert r["claim"]["all"]["n"] == r["claim"]["rotated"] + r["claim"]["trades"]["n"]
    assert result["NQ"]["book"]["mid"]["trades"] >= 0 and "crt" not in result["NQ"] and result["NQ"]["vehicle"] == "MNQ"
    assert isinstance(r["skipped_dates"], list)


def test_analyse_is_deterministic():
    es, days = _synthetic(60, seed=4)
    a = ST.analyse({"ES": (es, days)}, draws=10, log=lambda *_: None)["ES"]
    b = ST.analyse({"ES": (E.Store(dict(es.frames)), days)}, draws=10, log=lambda *_: None)["ES"]
    assert np.array_equal(a["crt"]["net_mid"], b["crt"]["net_mid"]) and a["book"]["mid"]["net"] == b["book"]["mid"]["net"]


def test_reports_negative_money_is_bracketed_and_red_in_html(result):
    txt, md, html = RP.render_txt(result), RP.render_md(result), RP.render_html(result)
    for body in (txt, md):
        assert not re.search(r"-\$\d", body) and not re.search(r"\$-\d", body)       # never a minus sign on a dollar amount
    assert re.search(r"\(\$\d", txt) or "$" in txt
    assert "<html" in html.lower() and 'class="neg"' in html
    for m in re.finditer(r"<td[^>]*>(\(\$?[\d,.]+%?\))</td>", html):                   # every bracketed number cell is red
        assert "neg" in m.group(0)
    assert not re.search(r"<td[^>]*>-[\d$]", html)
    for needle in ("NOT READ", "C-RT", "neighbour", "IBKR", "80% check", "Seven criteria"):
        assert needle.lower() in txt.lower(), needle
    assert "REGISTERED_va80" in txt and "Amendment" in txt


def test_json_round_trips_and_has_no_nan(result):
    js = RP.to_json(result)
    back = json.loads(js)
    assert back["ES"]["verdict"] == "NOT READ" and "NaN" not in js
    assert len(back["ES"]["crt"]["net_mid"]) == 40


def test_write_all_four_files(result, tmp_path):
    paths = RP.write_all(result, tmp_path / "w15_0025_va80_run_20261121.txt", inputs={"ES_session_frames": "abc"})
    assert sorted(p.suffix for p in paths) == [".html", ".json", ".md", ".txt"]
    for p in paths:
        assert p.stat().st_size > 500
    assert "abc" in (tmp_path / "w15_0025_va80_run_20261121.json").read_text(encoding="utf-8")


def test_run_refuses_without_a_cleared_preflight_and_writes_reports_when_cleared(tmp_path):
    days = Y.xnys_days("2019-03-04", 90)
    frames = {r: Y.rth_frames(days, seed=30 + i, gap_sd=12.0, vol=1.2) for i, r in enumerate(("ES", "NQ"))}
    load = lambda r: Y.one_min_frame(frames[r])
    from strategy.w16.preflight import session_frames
    out = tmp_path / "w15_0025_va80_run_20261121.txt"
    with pytest.raises(SystemExit, match="no pre-flight"):
        RUN.run_study(load, session_frames, out, draws=5, file_hashes={"ES_1m_file": "x", "NQ_1m_file": "y"}, log=lambda *_: None)
    reps, hashes = RUN.run_preflight(load, session_frames)
    full = dict(hashes, ES_1m_file="x", NQ_1m_file="y")
    RUN.write_preflight(tmp_path / "w15_0025_va80_preflight_20261121.txt", reps, full)
    with pytest.raises(SystemExit, match="pre-flight stopped"):
        RUN.run_study(load, session_frames, out, draws=5, file_hashes={"ES_1m_file": "x", "NQ_1m_file": "y"}, log=lambda *_: None)
    pj = tmp_path / "w15_0025_va80_preflight_20261121.json"
    pj.write_text(json.dumps(dict(json.loads(pj.read_text(encoding="utf-8")), stop=False)), encoding="utf-8")
    with pytest.raises(SystemExit, match="different inputs"):
        RUN.run_study(load, session_frames, out, draws=5, file_hashes={"ES_1m_file": "CHANGED", "NQ_1m_file": "y"}, log=lambda *_: None)
    paths = RUN.run_study(load, session_frames, out, draws=5, file_hashes={"ES_1m_file": "x", "NQ_1m_file": "y"}, log=lambda *_: None)
    assert out.exists() and out.with_suffix(".html").exists() and out.with_suffix(".json").exists() and out.with_suffix(".md").exists()
    assert paths[0] == out
    assert "TRAINING SIDE ONLY" in out.read_text(encoding="utf-8")


def test_run_path_has_no_holdout_and_never_imports_the_holdout_spend():
    src = open(RUN.__file__, encoding="utf-8").read() + open(ST.__file__, encoding="utf-8").read()
    assert "spend=True" not in src and "spend_holdout" not in src
    assert "study module" not in src.split("def main")[1]                        # the old "not built yet" stop is gone


# ------------------------------------------------------------------ edges the mutation pass found
def test_criterion_2_is_strictly_greater_and_zero_net_is_neither_win_nor_loss():
    assert _crit(net_mid=200.0, crt_p95=200.0)["crit"][2][1] is False
    assert _crit(net_mid=200.01, crt_p95=200.0)["crit"][2][1] is True
    import pandas as pd
    df = pd.DataFrame({"gross": [0.0, 5.0, -5.0], "cost": [0.0, 0.0, 0.0], "net": [0.0, 5.0, -5.0],
                       "reason": ["time", "target", "stop"]})
    s = ST.book_stats(df)
    assert s["wins"] == 1 and s["losses"] == 1 and s["trades"] == 3 and round(s["win_pct"], 6) == round(100 / 3, 6)


def test_analyse_wiring_of_high_friction_cnd_sessions_and_zero_cells(result):
    r = result["ES"]
    assert r["crit"]["crit"][4][2] == ST.money(r["book"]["high"]["net"])
    assert r["crit"]["crit"][1][2] == ST.money(r["book"]["mid"]["net"])
    assert r["cnd"]["sessions"] == int(r["counts"]["yearly"].loc["total", "open_inside"])
    es, days = _synthetic(10, seed=2)
    small = ST.analyse({"ES": (es, days)}, draws=3, log=lambda *_: None)["ES"]
    cells = small["grid"]["cells"]
    zero = [c for c, v in cells.items() if v["trades"] == 0]
    assert zero and all(cells[c]["net_mid"] == 0.0 for c in zero)
    assert small["grid"]["positive"] == sum(1 for v in cells.values() if v["net_mid"] > 0)
