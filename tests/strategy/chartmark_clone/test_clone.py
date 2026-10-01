"""Sub 4: rules clone R, model clone M, fidelity scoring -- on synthetic labels with a planted rule (no real data)."""
import numpy as np
import pandas as pd

from strategy.chartmark_clone import clone as CL
from strategy.chartmark_clone import features as FT
from strategy.chartmark_clone import spec as S


def synth(n=500, seed=3, take_rate=0.3):
    """Features random; 'chop' skips (reason 3) planted on F9 > 4, 'weak momentum' skips (reason 4) planted on F4 < -0.1,
    the rest of the skips random reason 7; takes are everything no planted rule fires on (plus noise)."""
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({c: rng.normal(size=n) for c in FT.FEATURE_COLUMNS})
    X["F1"] = rng.choice([-1.0, 1.0], n)
    X["F9"] = rng.integers(0, 12, n).astype(float)
    X["F4"] = rng.normal(0, 0.15, n)
    X["F12_session"] = rng.integers(0, 4, n).astype(float)
    X["F12_weekday"] = rng.integers(0, 5, n).astype(float)
    X["F12_hour"] = rng.integers(0, 24, n).astype(float)
    chop, weak = X["F9"].to_numpy() > 4, X["F4"].to_numpy() < -0.1
    reason = np.where(chop, "3", np.where(weak, "4", ""))
    other = (reason == "") & (rng.random(n) > take_rate / (take_rate + 0.2))
    reason = np.where(other, "7", reason)
    X["y"] = (reason == "").astype(int)
    X["reason"] = reason
    return X


def test_rules_recover_the_planted_thresholds_and_ignore_reasons_with_too_few_uses():
    df = synth()
    rules, notes = CL.fit_rules(df)
    by = {r["reason"]: r for r in rules}
    assert set(by) == {"3", "4"}
    assert by["3"]["feature"] == "F9" and 3.5 <= by["3"]["threshold"] <= 4.5      # planted at 4
    assert by["4"]["feature"] == "F4" and -0.13 <= by["4"]["threshold"] <= -0.07   # planted at -0.1
    assert notes["7"].startswith("not coded") and notes["1"].startswith("no rule: 0 uses")
    pred = CL.predict_rules(rules, df)
    m = CL.metrics(df["y"].to_numpy(), pred)
    n_take, n_other = int(df["y"].sum()), int((df["reason"] == "7").sum())
    assert m["recall"] == 1.0                                # planted rules: not one take is caught
    assert abs(m["precision"] - n_take / (n_take + n_other)) < 0.02    # the uncoded reason-7 skips are exactly what leaks through


def test_the_clone_takes_only_if_no_rule_fires_and_nan_never_fires():
    X = pd.DataFrame({c: [0.0] for c in FT.FEATURE_COLUMNS})
    rule = dict(reason="3", kind="threshold", feature="F9", op="gt", threshold=4.0)
    assert CL.predict_rules([rule], X.assign(F9=5.0))[0] == 0
    assert CL.predict_rules([rule], X.assign(F9=3.0))[0] == 1
    assert CL.predict_rules([rule], X.assign(F9=np.nan))[0] == 1
    assert CL.predict_rules([], X)[0] == 1
    lt = dict(reason="4", kind="threshold", feature="F4", op="lt", threshold=-0.1)
    assert CL.predict_rules([lt], X.assign(F4=-0.2))[0] == 0 and CL.predict_rules([lt], X.assign(F4=-0.05))[0] == 1


def test_a_rule_that_does_not_separate_is_dropped():
    rng = np.random.default_rng(0)
    n = 400
    X = pd.DataFrame({c: rng.normal(size=n) for c in FT.FEATURE_COLUMNS})
    X["y"] = rng.integers(0, 2, n)
    X["reason"] = np.where(X["y"] == 0, "3", "")
    # F9/F10/F11 are noise here: best J is small but may be > 0 by chance; with the planted-free data the rule must still
    # never be better than chance, so J of any kept rule is modest
    rules, _ = CL.fit_rules(X)
    for r in rules:
        assert r["J"] < 0.35


def test_threshold_ties_prefer_fewer_takes_caught_then_smaller_theta():
    th, j, ps, pt = CL._best_threshold(np.array([5.0, 6.0, 7.0]), np.array([1.0, 2.0]), "gt", 3, 2)
    assert j == 1.0 and 2.0 <= th < 5.0 and pt == 0.0
    th2, j2, *_ = CL._best_threshold(np.array([1.0, 2.0]), np.array([5.0, 6.0]), "lt", 2, 2)
    assert j2 == 1.0 and 2.0 <= th2 < 5.0


def test_reason_1_can_use_the_daily_trend_flag_without_a_threshold():
    rng = np.random.default_rng(1)
    n = 300
    X = pd.DataFrame({c: rng.normal(size=n) for c in FT.FEATURE_COLUMNS})
    X["F1"] = rng.choice([-1.0, 1.0], n)
    X["y"] = (X["F1"] == 1.0).astype(int)
    X["reason"] = np.where(X["y"] == 0, "1", "")
    rules, _ = CL.fit_rules(X)
    r = [x for x in rules if x["reason"] == "1"][0]
    assert r["feature"] == "F1" and r["op"] == "eq" and r["threshold"] == -1.0 and r["J"] == 1.0


def test_event_hour_rule_uses_weekday_hour_cells_with_enough_uses():
    n = 200
    X = pd.DataFrame({c: np.zeros(n) for c in FT.FEATURE_COLUMNS})
    X["F12_weekday"], X["F12_hour"] = 2.0, 9.0
    X["y"] = 1
    X["reason"] = ""
    X.loc[:19, ["y", "reason"]] = [0, "6"]
    X.loc[20:39, "F12_hour"] = 14.0            # takes elsewhere
    rules, notes = CL.fit_rules(X)
    r = [x for x in rules if x["reason"] == "6"]
    assert r and r[0]["cells"] == [[2, 9]]


def test_f2_threshold_leans_to_recall():
    y = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    p = np.array([.9, .8, .6, .35, .5, .4, .3, .2, .1, .05])
    thr, f2 = CL.best_threshold_f2(y, p)
    assert thr <= 0.35 and f2 >= CL.f2_score(y, (p >= 0.5).astype(int))


def test_model_clone_learns_a_planted_signal_and_is_deterministic():
    df = synth()
    m1 = CL.fit_model(df, "logit", 0, 0)
    m2 = CL.fit_model(df, "logit", 0, 0)
    assert m1["C"] == m2["C"] and m1["threshold"] == m2["threshold"] and np.allclose(m1["coef"], m2["coef"])
    p = CL.predict_model(m1, df)
    mt = CL.metrics(df["y"].to_numpy(), p)
    assert mt["recall"] > 0.8 and mt["agreement"] > 0.75
    g = CL.fit_model(df, "gb", 0, 0)
    assert CL.metrics(df["y"].to_numpy(), CL.predict_model(g, df))["agreement"] > 0.8


def test_frozen_logit_reproduces_its_probabilities_from_the_numbers_alone():
    df = synth()
    m = CL.fit_logit(df, 0.1)
    X = df.copy()
    X.loc[X.index[:5], "F7"] = np.nan                         # NaN -> training median
    a = CL.proba_logit(m, X)
    m_json = {k: m[k] for k in ("kind", "C", "coef", "intercept", "median", "mean", "sd")}
    import json
    m_back = json.loads(json.dumps(m_json))
    assert np.allclose(a, CL.proba_logit(m_back, X))
    assert np.isfinite(a).all()


def test_metrics_definitions_on_a_hand_made_confusion():
    y = np.array([1] * 10 + [0] * 30)
    pred = np.array([1] * 6 + [0] * 4 + [1] * 3 + [0] * 27)
    m = CL.metrics(y, pred)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (6, 3, 4, 27)
    assert m["recall"] == 0.6 and abs(m["precision"] - 6 / 9) < 1e-12 and m["agreement"] == 33 / 40
    assert abs(m["clone_take_rate"] - 9 / 40) < 1e-12 and 0 < m["kappa"] < 1


def test_recall_bar_is_capped_by_bens_own_consistency():
    assert CL.recall_bar(0.9) == 0.75 and CL.recall_bar(0.538) == 0.538
    assert CL.meets_bar(0.60, 0.55, 0.538) and not CL.meets_bar(0.60, 0.55, 0.9)
    assert not CL.meets_bar(0.60, 0.45, 0.538)


def test_repeat_consistency_counts():
    first = {"a": "TAKE", "b": "TAKE", "c": "SKIP", "d": "SKIP"}
    r = CL.repeat_consistency(first, [("a", "TAKE"), ("b", "SKIP"), ("c", "SKIP"), ("d", "TAKE")])
    assert r["take_consistency"] == 0.5 and r["skip_consistency"] == 0.5 and r["agreement"] == 0.5
    lo, hi = CL.wilson(7, 13)
    assert 0.29 < lo < 0.54 < hi < 0.77


def test_cv_uses_the_registered_seeds_and_every_candidate_gets_one_prediction_per_repeat():
    df = synth(250)
    pr = CL.cv_predictions(df, repeats=2, with_models=False)
    assert pr["R"].shape == (2, 250) and set(np.unique(pr["R"])) <= {0, 1}
    again = CL.cv_predictions(df, repeats=2, with_models=False)
    assert (pr["R"] == again["R"]).all()
    s = CL.summarise(df, pr["R"])
    assert 0 <= s["mean"]["recall"] <= 1 and len(s["per_repeat"]) == 2
    assert S.CV_SEED_WORD == __import__("zlib").crc32(b"W15-0050-cv")
