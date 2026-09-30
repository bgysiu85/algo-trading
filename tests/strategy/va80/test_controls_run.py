"""VA80: C-RT / C-ND, the 27-cell grid, the ledger (G3), the count-only pre-flight and the runner's refusals."""
import json
import zlib

import numpy as np
import pandas as pd
import pytest

from strategy.otf_gate import ledger as L
from strategy.va80 import controls as K
from strategy.va80 import engine as E
from strategy.va80 import grid as GR
from strategy.va80 import holdout as HO
from strategy.va80 import preflight as PF
from strategy.va80 import run as RUN
from strategy.va80 import spec as S
from tests.strategy.va80 import synth as Y

VAL, VAH = 100.0, 110.0
T = 0.25


def _store(*sessions):
    st = E.Store({})
    for s in sessions:
        st._s[s.date] = s
    return st


# ------------------------------------------------------------------ candidates
def _sess():
    # inside the value area all day except a spike out at 12:00-12:29 and a dip to the far edge at 13:00
    knots = ((570, 112.0), (599, 108.0), (719, 108.0), (720, 111.0), (749, 108.0), (959, 104.0))
    return Y.path_sess(knots=knots)


def test_candidates_need_prior_close_inside_a_10_to_15_start_and_the_edge_untouched():
    s = _sess()
    c = K.candidates(s, S.SHORT, VAL, VAH)
    m = s.minute[c]
    assert m.min() >= 600 and m.max() <= 900
    assert (s.c[c - 1] >= VAL).all() and (s.c[c - 1] <= VAH).all()
    assert not np.isin(s.minute[c], [721]).any()                              # bar 720 closed at 111 (outside): 721 excluded
    prior_out = np.flatnonzero((s.c > VAH) | (s.c < VAL)) + 1                 # bars right after an outside close: excluded
    assert not np.intersect1d(c, prior_out).any()
    # once the far edge has traded, no later bar is a candidate
    touch = Y.path_sess(knots=((570, 112.0), (599, 108.0), (659, 108.0), (660, 99.0), (661, 108.0), (959, 108.0)))
    ct = K.candidates(touch, S.SHORT, VAL, VAH)
    assert ct.size and touch.minute[ct].max() == 660          # the 11:00 bar opens BEFORE the dip; 11:01 on is excluded
    assert not (touch.minute[ct] > 660).any()
    calm = Y.path_sess(knots=((570, 105.0), (659, 105.0), (660, 99.0), (661, 105.0), (959, 105.0)))
    assert calm.minute[K.candidates(calm, S.SHORT, VAL, VAH)].max() == 660          # VAL traded at 11:00 -> no later short
    assert calm.minute[K.candidates(calm, S.LONG, VAL, VAH)].max() == 900           # VAH never traded -> long allowed to 15:00


def test_edge_outcome_stop_wins_ties():
    s = _sess()
    assert K.edge_outcome(s, 100, S.SHORT, 90.0, 150.0) == "neither"
    assert K.edge_outcome(s, 100, S.SHORT, 111.0, 150.0) == "edge"           # the low is already at/below 111 on bar 100
    o = Y.path_sess(knots=((570, 105.0), (959, 105.0)), overrides={700: (105.0, 113.0, 99.0, 105.0)})
    assert K.edge_outcome(o, 100, S.SHORT, 100.0, 112.25) == "stop"           # both in one bar: the stop counts first


# ------------------------------------------------------------------ C-RT / C-ND
def _trade_sessions(n=6, seed=2):
    days = Y.xnys_days("2019-03-04", n)
    frames = Y.rth_frames(days, seed=seed)
    return E.Store(frames), days


def test_crt_is_reproducible_uses_the_registered_seed_and_the_same_side():
    store, days = _trade_sessions(30, seed=5)
    trades = []
    for r in E.evaluate(store, days, want_exit=True):
        if r["trade"]:
            t = r["trade"]
            trades.append({"date": t["date"], "side": t["side"], "val": t["val"], "vah": t["vah"]})
    if not trades:
        pytest.skip("no VA80 trade in this synthetic sample")
    a, b = K.run_crt(store, trades, draws=20), K.run_crt(store, trades, draws=20)
    assert all(np.array_equal(a[k], b[k]) for k in a)
    # the registered seed layout, replicated by hand for the first three draws of the first trade session
    t = trades[0]
    sess = store.sess(t["date"])
    c = K.candidates(sess, t["side"], t["val"], t["vah"])
    if len(c) and len(trades) == 1:
        for d in range(3):
            i = int(c[np.random.default_rng([zlib.crc32(str(d).encode()), zlib.crc32(t["date"].encode()), 80]).integers(len(c))])
            tgt, stp = K.levels(sess, i, t["side"], t["val"], t["vah"])
            px = E.walk_exit(sess, i, t["side"], tgt, stp)[1]
            one = K.run_crt(store, [t], draws=3)
            assert one["gross_pts"][d] == pytest.approx(t["side"] * (px - float(sess.o[i])))
    assert (a["n"] + a["unused"] == len(trades)).all()
    assert (a["n_target"] + a["n_other"] == a["n"]).all() and (a["n_edge"] + a["n_stop"] + a["n_neither"] == a["n"]).all()


def test_crt_entry_uses_the_va80_target_and_stop_rule_at_the_random_bar():
    s = _sess()
    store = _store(s)
    tr = [{"date": s.date, "side": S.SHORT, "val": VAL, "vah": VAH}]
    out = K.run_crt(store, tr, draws=30)
    c = K.candidates(s, S.SHORT, VAL, VAH)
    assert (out["n"] == 1).all()
    got = {round(g, 6) for g in out["gross_pts"]}
    want = set()
    for i in c:
        tgt, stp = K.levels(s, int(i), S.SHORT, VAL, VAH)
        assert tgt == VAL and stp == float(s.h[:i].max()) + T             # bars strictly before the entry bar
        k, px, why = E.walk_exit(s, int(i), S.SHORT, tgt, stp)
        want.add(round(S.SHORT * (px - float(s.o[i])), 6))
    assert got <= want


def test_crt_seed_layout_pins_the_pick_for_a_single_session():
    s = _sess()
    store = _store(s)
    tr = {"date": s.date, "side": S.SHORT, "val": VAL, "vah": VAH}
    c = K.candidates(s, S.SHORT, VAL, VAH)
    out = K.run_crt(store, [tr], draws=6)
    for d in range(6):
        i = int(c[np.random.default_rng([zlib.crc32(str(d).encode()), zlib.crc32(s.date.encode()), 80]).integers(len(c))])
        tgt, stp = K.levels(s, i, S.SHORT, VAL, VAH)
        px = E.walk_exit(s, i, S.SHORT, tgt, stp)[1]
        assert out["gross_pts"][d] == pytest.approx(S.SHORT * (px - float(s.o[i])))


def test_levels_use_only_bars_before_the_random_entry_bar():
    s = Y.path_sess(knots=((570, 105.0), (959, 105.0)), overrides={700: (105.0, 109.5, 105.0, 105.0)})
    i = 700 - 570
    tgt, stp = K.levels(s, i, S.SHORT, VAL, VAH)
    assert tgt == VAL and stp == 105.0 + T                       # the entry bar's own 109.5 high is not in the stop
    tgt, stp = K.levels(s, i + 1, S.SHORT, VAL, VAH)
    assert stp == 109.5 + T                                      # one bar later it is


def test_crt_session_without_a_candidate_is_counted_unused():
    s = Y.path_sess(knots=((570, 112.0), (959, 112.0)))                    # never closes inside the value area
    out = K.run_crt(_store(s), [{"date": s.date, "side": S.SHORT, "val": VAL, "vah": VAH}], draws=5)
    assert (out["n"] == 0).all() and (out["unused"] == 1).all()


def test_cnd_draws_the_side_first_and_uses_the_edge_on_that_side():
    s = _sess()
    s2 = Y.path_sess(date="2019-03-06", knots=((570, 105.0), (700, 108.0), (959, 104.0)))
    store = _store(s2)
    out = K.run_cnd(store, [{"date": s2.date, "val": VAL, "vah": VAH}], draws=12)
    for d in range(12):
        rng = np.random.default_rng([zlib.crc32(str(d).encode()), zlib.crc32(s2.date.encode()), 80])
        side = S.LONG if int(rng.integers(2)) == 1 else S.SHORT
        c = K.candidates(s2, side, VAL, VAH)
        assert (out["n"][d] == 1) == bool(len(c))
    tgt, stp = K.levels(s2, 100, S.LONG, VAL, VAH)
    assert tgt == VAH and stp == float(s2.l[:100].min()) - T


def test_percentile_and_summary():
    assert K.percentile_of(2.0, np.array([1.0, 2.0, 2.0, 3.0])) == 100 * (1 / 4 + 0.5 * 2 / 4)
    assert set(K.summary(np.arange(100.0))) == {"p5", "p50", "p95", "p99"}


# ------------------------------------------------------------------ grid
def test_grid_has_27_distinct_cells_and_the_centre_is_the_primary():
    assert len(GR.CELLS) == 27 == len(set(GR.CELLS))
    assert S.CENTRE == (2, 30, 0.70) and S.CENTRE in GR.CELLS
    assert {c[0] for c in GR.CELLS} == {1, 2, 3} and {c[1] for c in GR.CELLS} == {15, 30, 60}
    assert {c[2] for c in GR.CELLS} == {0.60, 0.70, 0.80}
    store, days = _trade_sessions(10, seed=4)
    primary = E.evaluate(store, days)
    centre = E.evaluate(store, days, GR.params(S.CENTRE))
    assert [(r["trigger"], r["rotated"], r["side"]) for r in primary] == [(r["trigger"], r["rotated"], r["side"]) for r in centre]
    cells = GR.run_grid(store, days)
    assert len(cells) == 27
    one, three = GR.counts(cells[(1, 30, 0.70)])["triggers"], GR.counts(cells[(3, 30, 0.70)])["triggers"]
    assert one >= three                                                     # a stricter acceptance can only trigger less


# ------------------------------------------------------------------ G3 ledger
def _ledger(tmp_path):
    return L.Ledger("VA80", "holdout_va80.json", "REGISTERED_va80.md", HO.H.hosts, root=tmp_path)


def test_va80_windows_and_own_ledger_name(tmp_path):
    Ld = _ledger(tmp_path)
    assert HO.H.ledger_name == "holdout_va80.json"
    assert Ld.classify("ES", "2023-12-29") == "train" and Ld.classify("ES", "2023-12-30") == "gap"
    assert Ld.classify("ES", "2024-01-02") == "holdout" and Ld.classify("ES", "2030-01-01") == "holdout"
    keep, n, _ = Ld.split_dates("ES", ["2023-12-28", "2023-12-29", "2024-01-02"])
    assert keep == ["2023-12-28", "2023-12-29"] and n == 1


def test_va80_refuses_other_ledgers_and_narrowing_and_wrong_candidates(tmp_path):
    Ld = _ledger(tmp_path)
    for name in ("holdout_w16_sb.json", "holdout_otf_gate.json", "holdout_macro_flag.json", "holdout.json", "holdout_h60.json"):
        with pytest.raises(L.HoldoutRefused):
            Ld.load_for(name)
    Ld.load_for("holdout_va80.json")
    with pytest.raises(L.HoldoutRefused):
        Ld.split_dates("ES", ["2020-01-02"], limit=100)
    with pytest.raises(L.HoldoutRefused):
        Ld.split_dates("NQ", ["2020-01-02"])                                # NQ is reported, has no ledger key
    for bad in ({"candidate": "VA80-NQ", "verdict": "PASS"}, {"candidate": "VA80"}, {"candidate": "VA80", "verdict": "FAIL"}):
        with pytest.raises(L.HoldoutRefused):
            Ld.split_dates("ES", ["2024-02-01"], spend=True, **bad)
    assert not Ld.ledger_path.exists()
    Ld.split_dates("ES", ["2024-02-01"], spend=True, candidate="VA80", verdict="PASS")
    with pytest.raises(L.HoldoutRefused, match="already spent"):
        Ld.split_dates("ES", ["2024-02-01"], spend=True, candidate="VA80", verdict="PASS")


# ------------------------------------------------------------------ pre-flight and runner
def _loader(dates_by_root):
    frames = {r: Y.rth_frames(d, seed=10 + i) for i, (r, d) in enumerate(dates_by_root.items())}
    return (lambda r: Y.one_min_frame(frames[r])), frames


def _session_frames():
    from strategy.w16.preflight import session_frames
    return session_frames


def test_training_cut_happens_before_any_session_is_built(monkeypatch):
    days = ["2023-12-27", "2023-12-28", "2023-12-29", "2024-01-02", "2024-01-03"]
    frames = Y.rth_frames(days, seed=3)
    seen = {}
    real = RUN.HOLD.split_dates

    def spy(host, dates, **k):
        seen.setdefault("calls", []).append((host, len(list(dates))))
        return real(host, dates, **k)
    monkeypatch.setattr(RUN.HOLD, "split_dates", spy)
    got = {}

    def frames_fn(df):
        from strategy.w16.readback import local_naive_et
        got["last_day"] = local_naive_et(df.index).strftime("%Y-%m-%d").max()
        return _session_frames()(df)
    store, fr, dd = RUN.build_store(Y.one_min_frame(frames), frames_fn)
    assert got["last_day"] == "2023-12-29"                         # no locked bar reached the session builder
    assert sorted(fr) == days[:3] and dd[-1] == "2023-12-29" and seen["calls"][0][0] == "ES"


def test_preflight_end_to_end_counts_only_and_stop_rule(tmp_path):
    days = Y.xnys_days("2019-03-04", 80)
    load, _ = _loader({"ES": days, "NQ": days})
    reps, hashes = RUN.run_preflight(load, _session_frames())
    es = reps["ES"]
    assert es["sessions"] == 80 and es["triggers"] > 0 and es["stop"] is True and es["trades_below_floor"] is True
    y = es["yearly"].loc["total"]
    assert y["sessions"] == y["skip_data"] + y["skip_roll"] + y["open_above"] + y["open_below"] + y["open_inside"]
    assert y["triggers"] == y["rotated"] + y["trades_long"] + y["trades_short"]
    assert len(es["grid"]) == 27
    text = RUN.write_preflight(tmp_path / "w15_0025_va80_preflight_20260930.txt", reps, dict(hashes, ES_1m_file="x"))
    assert "STOP" in text and "no outcome" in text.lower() and "far-edge rate" in text
    for banned in ("net", "win", "gross"):
        assert banned not in text.lower().replace("no outcome, far-edge rate or p&l", "")
    js = json.loads((tmp_path / "w15_0025_va80_preflight_20260930.json").read_text(encoding="utf-8"))
    assert js["stop"] is True and "ES_session_frames" in js["inputs_sha256"]


def test_require_preflight_refusals(tmp_path):
    days = Y.xnys_days("2019-03-04", 30)
    load, _ = _loader({"ES": days, "NQ": days})
    reps, hashes = RUN.run_preflight(load, _session_frames())
    RUN.write_preflight(tmp_path / "w15_0025_va80_preflight_20260930.txt", reps, hashes)
    with pytest.raises(SystemExit, match="pre-flight stopped"):
        RUN.require_preflight(tmp_path, hashes)
    with pytest.raises(SystemExit, match="different inputs"):
        RUN.require_preflight(tmp_path, dict(hashes, ES_session_frames="0"))
    with pytest.raises(SystemExit, match="no pre-flight"):
        RUN.require_preflight(tmp_path / "none", hashes)
    p = tmp_path / "w15_0025_va80_preflight_20260930.json"
    js = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps(dict(js, stop=False)), encoding="utf-8")
    assert RUN.require_preflight(tmp_path, hashes)["triggers"] == js["triggers"]


def test_runner_refuses_narrowing_flags_and_has_no_such_option(capsys):
    for flag in ("--holdout", "--limit=5", "--spend", "--seen", "--markets=ES", "--window", "--cells", "--variant=x"):
        assert RUN.main(["--preflight", flag]) == 2
    assert "REFUSED" in capsys.readouterr().err
    src = open(RUN.__file__, encoding="utf-8").read()
    for flag in ("--holdout", "--spend", "--limit", "--cells"):
        assert f'add_argument("{flag}"' not in src
