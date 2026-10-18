"""Sub 5: the gated engine, the one-run runner, the criteria and H1 -- all on synthetic bars. No real outcome is read here."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from strategy.chartmark import engine as E
from strategy.chartmark import spec as S1
from strategy.chartmark.data import indicators
from strategy.chartmark_clone import clone as CL
from strategy.chartmark_clone import gated as G
from strategy.chartmark_clone import outcome as O
from strategy.chartmark_clone import spec as S
from strategy.chartmark_clone.chartdata import build_chart_data
from tests.strategy.chartmark.synth import cut, walk


@pytest.fixture(scope="module")
def bars():
    out = []
    for seed, roll in ((1, None), (2, 700), (3, 450)):
        fr = walk(6000, seed, drift=0.01, start="2015-01-05 00:00", roll_every=roll)
        out.append((fr, indicators(fr)))
    return out


def test_always_take_reproduces_v1_and_always_skip_gives_nothing(bars):
    for fr, ind in bars:
        ref, _ = E.simulate(fr, ind, S1.BASE)
        assert len(ref) > 20
        tk, c = G.simulate_gated(fr, ind, S1.BASE, G.AlwaysTake())
        assert tk == ref and c["would_be"] == c["takes"] == len(ref) and c["skips"] == 0
        none, _ = G.simulate_gated(fr, ind, S1.BASE, None)
        assert none == ref
        sk, c2 = G.simulate_gated(fr, ind, S1.BASE, G.AlwaysSkip())
        assert sk == [] and c2["skips"] == c2["would_be"] >= len(ref)


def test_grid_cells_also_reproduce_v1(bars):
    fr, ind = bars[0]
    for L in S1.GRID_E1:
        for sl in S1.GRID_STOP:
            p = replace(S1.BASE, e1_lookback=L, stop_lookback=sl, p1_arm=0.75)
            assert G.simulate_gated(fr, ind, p, G.AlwaysTake())[0] == E.simulate(fr, ind, p)[0]


def test_the_gate_is_asked_only_at_touches_with_the_decision_bar_before(bars):
    fr, ind = bars[0]
    calls = []

    def spy(t_dec, level, j):
        calls.append((t_dec, level, j))
        return len(calls) % 2 == 1                       # alternate take / skip

    tr, c = G.simulate_gated(fr, ind, S1.BASE, spy)
    assert calls and len(calls) == c["would_be"] == c["takes"] + c["skips"]
    for t_dec, level, j in calls:
        assert j == t_dec + 1 and fr.h[j] >= level
    assert len(tr) == c["takes"]


def test_a_skip_leaves_the_order_working_and_it_is_asked_again(bars):
    fr, ind = bars[0]
    ref, _ = E.simulate(fr, ind, S1.BASE)
    first_touch = {}

    def skip_first_touch_only(t_dec, level, j):
        seen = first_touch.setdefault("n", 0)
        first_touch["n"] = seen + 1
        return seen != 0

    tr, c = G.simulate_gated(fr, ind, S1.BASE, skip_first_touch_only)
    assert c["skips"] == 1 and c["takes"] >= 1
    assert tr[0].entry_j >= ref[0].entry_j              # the first fill can only come later, never earlier


def test_causality_the_gated_engine_on_a_cut_frame_agrees_before_the_cut(bars):
    fr, ind = bars[0]

    def gate_factory(f):
        return lambda t_dec, level, j: bool(f.c[t_dec] > f.o[t_dec])     # reads bars <= t_dec only

    full, _ = G.simulate_gated(fr, ind, S1.BASE, gate_factory(fr))
    for k in (2500, 4100):
        f2 = cut(fr, k)
        part, _ = G.simulate_gated(f2, indicators(f2), S1.BASE, gate_factory(f2))
        a = [G.trade_key(t) for t in full if t.exit_j < k - 3]
        b = [G.trade_key(t) for t in part if t.exit_j < k - 3]
        assert a == b and len(a) > 5


def test_v2_exits_on_v1_entries(bars):
    fr, ind = bars[0]
    tr, c = G.simulate_gated(fr, ind, S1.BASE, G.AlwaysTake(), exits="v2")
    assert len(tr) > 10 and c["takes"] == len(tr)
    for t in tr:
        assert t.exit_j >= t.entry_j and t.reason in {"BACKSTOP", "BACKSTOP-fillbar", "EMA21", "data_end"}
        if t.reason == "BACKSTOP-fillbar":
            assert t.exit_j == t.entry_j and t.exit_px == pytest.approx(t.entry_px - 0.60)
        if t.reason == "BACKSTOP":
            assert t.exit_px <= t.entry_px - 0.60 + 1e-9
    assert all(a.exit_j <= b.entry_j for a, b in zip(tr, tr[1:]))            # one position at a time
    with pytest.raises(ValueError):
        G.simulate_gated(fr, ind, S1.BASE, G.AlwaysTake(), exits="v3")


def test_random_gate_is_deterministic_and_p_extremes_match_always_take_skip(bars):
    fr, ind = bars[1]
    years = np.asarray(fr.ny.year)
    ref, _ = E.simulate(fr, ind, S1.BASE)

    def run(p, seed):
        rng = np.random.default_rng([seed, 7])
        return G.simulate_gated(fr, ind, S1.BASE, G.RandomGate({2015: p}, years, rng, p))[0]

    assert run(1.0, 1) == ref and run(0.0, 1) == []
    a, b, c = run(0.5, 1), run(0.5, 1), run(0.5, 2)
    assert a == b and a != c


def _fake_frozen(rng):
    n = 120
    tr = pd.DataFrame({k: rng.normal(size=n) for k in CL.MODEL_NUM})
    tr["F12_session"] = rng.integers(0, 4, n)
    tr["F12_weekday"] = rng.integers(0, 5, n)
    tr["y"] = (rng.random(n) < 0.4).astype(int)
    m = CL.fit_logit(tr, 0.1)
    m["threshold"] = 0.35
    rules = [dict(reason="3", kind="threshold", feature="F10", op="gt", threshold=0.95),
             dict(reason="4", kind="threshold", feature="F5", op="lt", threshold=0.0)]
    return dict(R=dict(rules=rules), M=m, M_GB=dict(threshold=0.3))


def test_clone_gate_matches_the_labelling_features_and_is_memoised(bars):
    fr, ind = bars[0]
    cd = build_chart_data(fr)
    frozen = _fake_frozen(np.random.default_rng(0))
    for kind in ("R", "M"):
        g = G.CloneGate(cd, kind, frozen)
        tr, c = G.simulate_gated(fr, ind, S1.BASE, g)
        assert c["would_be"] > 0 and c["takes"] + c["skips"] == c["would_be"]
        n_calls = g.calls
        tr2, _ = G.simulate_gated(fr, ind, S1.BASE, g)          # memo: no new feature computation, same trades
        assert tr2 == tr and g.calls == n_calls
    with pytest.raises(ValueError):
        G.CloneGate(cd, "X", frozen)


def test_run_study_smoke_on_synthetic_bars(bars):
    fr, ind = bars[0]
    cd = build_chart_data(fr)
    frozen = _fake_frozen(np.random.default_rng(0))
    man_ids = set(fr.ny[t.entry_j].tz_localize(None).strftime("%Y-%m-%d %H:%M:%S") for t in E.simulate(fr, ind, S1.BASE)[0])
    r = O.run_study(fr, ind, cd, frozen, None, man_ids, None, draws=6, h1_draws=50, log=lambda *_: None)
    assert len(r["grid"]) == 27 and [c["n"] for c in r["crit"]] == list(range(1, 11))
    assert r["verdict"] and r["c3"]["draws"] == 6 and r["pool_overlap"] + r["pool_new"] == len(r["trH"])
    assert set(r["var"]) >= {"V-OTHER (M logistic)", "V-EXIT2 (R gate, v2 exits)", "V-NOFAMOUS (R gate)"}
    prov = dict(run_utc="t", head="h" * 40, frozen_sha="f" * 64, labels_sha="l" * 64, reg_sha="r" * 64, gated_sha="g" * 64, outcome_sha="o" * 64)
    g6res = O.g6(fr, ind, man_ids, log=lambda *_: None)
    assert g6res["ok"] is False                                # synthetic pool is not 2,670 trades: G6 must say so
    text = O.report(r, dict(g6res), prov)
    assert "VERDICT" in text and "NEIGHBOUR GRID" in text and "SAMPLE OF 20 REAL TRADES" in text
    O.payload(r, g6res, prov)


# ------------------------------------------------------------------------------------------------ criteria
def _df(nets_by_year, per_year=20, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for y, tot in nets_by_year.items():
        for k in range(per_year):
            t = pd.Timestamp(f"{y}-01-05") + pd.Timedelta(days=int(k) * 2)
            net = tot / per_year + rng.normal(0, 0.01)
            rows.append(dict(entry_t=t, exit_t=t + pd.Timedelta(hours=5), year=y, gross=net + 1.54, cost=1.54, net=net))
    return pd.DataFrame(rows)


def _c1():
    return _df({y: -1.0 for y in range(2010, 2022)}, 5, seed=3)


YEARS = list(range(2010, 2022))


def test_criteria_all_pass_and_the_verdict_reads_ten_of_ten():
    d = _df({y: 100.0 for y in YEARS})
    rows = O.evaluate(d, d, c1_mid=_c1(), c3_p99=500.0, n_grid_pos=20)
    assert all(r["ok"] for r in rows) and O.verdict(rows) == "PASS (ten of ten)"


def test_concentration_only_failure_is_pass_except_concentration():
    nets = {y: 10.0 for y in YEARS}
    nets[2014] = 400.0
    d = _df(nets)
    rows = O.evaluate(d, d, c1_mid=_c1(), c3_p99=0.0, n_grid_pos=27)
    by = {r["n"]: r["ok"] for r in rows}
    assert by[8] is False and all(v for k, v in by.items() if k != 8)
    assert O.verdict(rows).startswith("PASS except concentration")


def test_failing_c1_or_c3_closes_the_study_and_few_trades_is_not_read():
    d = _df({y: 100.0 for y in YEARS})
    assert O.verdict(O.evaluate(d, d, c1_mid=_c1(), c3_p99=10_000.0, n_grid_pos=27)).startswith("FAIL (criterion 6 or 7")
    big_c1 = _df({y: 500.0 for y in YEARS}, 5, seed=3)
    assert O.verdict(O.evaluate(d, d, c1_mid=big_c1, c3_p99=0.0, n_grid_pos=27)).startswith("FAIL (criterion 6 or 7")
    few = _df({2010: 5.0, 2011: 5.0}, per_year=10)
    assert O.verdict(O.evaluate(few, few, c1_mid=_c1(), c3_p99=0.0, n_grid_pos=27)).startswith("NOT READ")


def test_halves_are_calendar_halves_and_the_high_friction_leg_counts():
    d = _df({y: (100.0 if y <= 2015 else -30.0) for y in YEARS})
    rows = {r["n"]: r for r in O.evaluate(d, d, c1_mid=_c1(), c3_p99=0.0, n_grid_pos=27)}
    h1, h2 = rows[3]["value"]
    assert h1 > 0 > h2 and rows[3]["ok"] is False
    neg = _df({y: -5.0 for y in YEARS})
    assert O.evaluate(d, neg, c1_mid=_c1(), c3_p99=0.0, n_grid_pos=27)[1]["ok"] is False


# ------------------------------------------------------------------------------------------------ H1
def test_h1_percentiles_rank_a_good_selector_high_and_a_bad_one_low():
    rng = np.random.default_rng(5)
    n = 200
    nets = rng.normal(0, 10, n)
    ids = [f"2015-01-{1 + i % 28:02d} {i % 24:02d}:00:00#{i}" for i in range(n)]
    lab = pd.DataFrame({"candidate_id": ids, "y": (nets > np.percentile(nets, 70)).astype(int)})
    for k in CL.MODEL_NUM + ["F12_session", "F12_weekday", "F12_hour"]:
        lab[k] = 0.0
    rules = [dict(reason="3", kind="threshold", feature="F10", op="gt", threshold=0.95)]      # F10 = 0 -> clone takes everything
    out = O.h1(lab, dict(zip(ids, nets)), rules, draws=2000)
    assert out["ben"]["pctile"] > 0.99 and out["ben"]["avg_take"] > out["ben"]["avg_skip"]
    assert out["clone"]["k"] == n and out["clone"]["total"] == pytest.approx(nets.sum())
    lab["y"] = (nets < np.percentile(nets, 30)).astype(int)
    assert O.h1(lab, dict(zip(ids, nets)), rules, draws=2000)["ben"]["pctile"] < 0.01
    with pytest.raises(O.OutcomeRefused):
        O.h1(lab, {}, rules, draws=10)


# ------------------------------------------------------------------------------------------------ one run only
def test_the_ledger_lock_refuses_a_second_run_and_records_a_retry(tmp_path):
    led = dict(outcome_run_done=False)
    out = O.start_lock(tmp_path, dict(led), False)
    assert out["outcome_run_started_utc"]
    on_disk = (tmp_path / S.LEDGER_FILE).read_text(encoding="utf-8")
    assert "outcome_run_started_utc" in on_disk
    with pytest.raises(O.OutcomeRefused):
        O.start_lock(tmp_path, dict(out), False)                 # started and not done: refused
    again = O.start_lock(tmp_path, dict(out), True)              # explicit retry after a crash: recorded
    assert len(again["outcome_run_retries"]) == 1
    with pytest.raises(O.OutcomeRefused):
        O.start_lock(tmp_path, dict(outcome_run_done=True, outcome_run_started_utc="x"), True)
    with pytest.raises(O.OutcomeRefused):
        O.start_lock(tmp_path, dict(outcome_run_done=False), True)       # nothing to retry


def test_verify_refuses_a_tampered_frozen_file(tmp_path):
    from tests.strategy.chartmark_clone.helpers import built
    res, fr, out, cache = built(tmp_path)
    (out / S.FROZEN_FILE).write_text("{}", encoding="utf-8")
    with pytest.raises(Exception):
        O.verify(out, cache, check_git=False)


def test_no_outcome_file_is_named_by_the_sub_5_modules():
    for mod in (G, O):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert S.TRADES_CSV_NAME not in src and "trades_base" not in src and "read_entry_times" not in src
