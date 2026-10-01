#!/usr/bin/env python3
"""The clone: rules clone R, model clone M (+ gradient-boosting M-GB), and the fidelity scoring. REGISTERED_chartmark_clone.md
sec 8 + Amendment 2 (PRE-RUN). LABELS AND CHART FEATURES ONLY -- no outcome, exit or P&L is read here.

Pure functions on a DataFrame with the columns of features.FEATURE_COLUMNS plus
    y       1 = Ben took the candidate, 0 = skipped
    reason  the skip reason key ('1'..'7'), '' for a take
so everything is testable on synthetic data.

Interpretations fixed in Amendment 2 (I14-I22), before any fit:
  I14  Rule threshold search: candidate thresholds are the midpoints between consecutive distinct observed values of the
       feature over (that reason's skips + all takes) in the training fold, plus one beyond each end. J = share of that
       reason's skips on which the rule fires - share of the training takes on which it fires (NaN never fires, NaNs stay in
       the denominators). Best J wins; ties: fewer takes caught, then the smaller threshold.
  I15  A reason's rule is built only when the reason has >= 15 uses in the training fold; where it maps to several features
       the one with the highest J is kept (ties: the earlier in the registered list); a rule whose best J <= 0 is dropped.
  I16  Rule for reason 1 may also be 'F1 = -1' (no threshold). Reason 6 = (weekday, hour of bar j) cells with >= 3 uses of
       reason 6 in the training fold. Reasons 5 and 2 use the registered single/dual features. Reason 7 is not coded.
  I17  M: standardised F1-F11, F13-F15 (training-fold median imputed, then mean/sd) + one-hot F12 session (4) and weekday (7);
       L2 logistic regression (lbfgs); C and the take-probability threshold chosen by inner 5-fold CV out-of-fold F2 score
       (C ties -> the smaller C; threshold grid 0.05..0.95 step 0.01, ties -> the smaller threshold).
  I18  M-GB: HistGradientBoostingClassifier(max_depth=3, max_iter=100, early_stopping=False, random_state=0) on the raw
       F1-F11, F13-F15, F12 session and weekday (ordinal), NaN native; threshold by the same inner-CV F2 rule.
  I19  Outer CV: 5 repeats x stratified 5-fold, random_state = crc32('W15-0050-cv') + repeat; inner CV random_state =
       crc32('W15-0050-cv-inner') + 1000*repeat + 10*outer_fold + (inner index). Metrics are computed per repeat on the pooled
       out-of-fold predictions; the headline is their mean over the 5 repeats (the range is reported).
  I20  The recall bar = min(0.75, Ben's repeat consistency on takes); the precision bar = 0.50.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from strategy.chartmark_clone import spec as S

# reason -> candidate rules in registered order: (feature, op); op gt: fires when x > theta, lt: x < theta, eq: x == theta
RULE_MAP = {
    "1": [("F1", "eq"), ("F2", "lt")],
    "2": [("F7", "gt"), ("F8", "gt")],
    "3": [("F9", "gt"), ("F10", "gt"), ("F11", "lt")],
    "4": [("F4", "lt"), ("F5", "lt")],
    "5": [("F6", "gt")],
}
MODEL_NUM = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F13", "F14", "F15"]
GB_COLS = MODEL_NUM + ["F12_session", "F12_weekday"]
N_SESSION, N_WEEKDAY = 4, 7
THRESHOLD_GRID = np.round(np.arange(0.05, 0.9501, 0.01), 2)


# ------------------------------------------------------------------------------------------------ rules clone R
def _fires(rule: dict, X: pd.DataFrame) -> np.ndarray:
    if rule["kind"] == "cells":
        cells = {(int(w), int(h)) for w, h in rule["cells"]}
        return np.array([(int(w), int(h)) in cells for w, h in zip(X["F12_weekday"], X["F12_hour"])], bool)
    x = X[rule["feature"]].to_numpy(float)
    with np.errstate(invalid="ignore"):
        if rule["op"] == "gt":
            return x > rule["threshold"]
        if rule["op"] == "lt":
            return x < rule["threshold"]
        return x == rule["threshold"]


def _best_threshold(x_skip: np.ndarray, x_take: np.ndarray, op: str, n_skip: int, n_take: int):
    """(theta, J, share of skips caught, share of takes caught) -- I14."""
    pooled = np.unique(np.concatenate([x_skip[~np.isnan(x_skip)], x_take[~np.isnan(x_take)]]))
    if len(pooled) == 0:
        return None
    th = np.concatenate([[pooled[0] - 1.0], (pooled[:-1] + pooled[1:]) / 2.0, [pooled[-1] + 1.0]])
    s = np.sort(x_skip[~np.isnan(x_skip)])
    t = np.sort(x_take[~np.isnan(x_take)])
    if op == "gt":
        caught_s = len(s) - np.searchsorted(s, th, side="right")
        caught_t = len(t) - np.searchsorted(t, th, side="right")
    else:
        caught_s = np.searchsorted(s, th, side="left")
        caught_t = np.searchsorted(t, th, side="left")
    ps, pt = caught_s / n_skip, caught_t / max(n_take, 1)
    j = ps - pt
    order = np.lexsort((th, pt, -j))                   # best J, then fewer takes caught, then the smaller theta
    i = int(order[0])
    return float(th[i]), float(j[i]), float(ps[i]), float(pt[i])


def fit_rules(train: pd.DataFrame, min_uses: int = S.RULE_MIN_USES) -> tuple[list[dict], dict]:
    """Rules clone R on a training set. Returns (rules, notes); notes lists every reason and why it has no rule."""
    takes = train[train["y"] == 1]
    n_take = len(takes)
    rules, notes = [], {}
    for reason in ("1", "2", "3", "4", "5", "6", "7"):
        sk = train[(train["y"] == 0) & (train["reason"] == reason)]
        n = len(sk)
        if reason == "7":
            notes[reason] = f"not coded ({n} uses)"
            continue
        if n < min_uses:
            notes[reason] = f"no rule: {n} uses < {min_uses}"
            continue
        if reason == "6":
            cnt = sk.groupby(["F12_weekday", "F12_hour"]).size()
            cells = [[int(w), int(h)] for (w, h), c in cnt.items() if c >= S.EVENT_CELL_MIN]
            if not cells:
                notes[reason] = f"no rule: no weekday-hour cell with >= {S.EVENT_CELL_MIN} uses"
                continue
            rule = dict(reason=reason, kind="cells", feature="F12", op="in", threshold=None, cells=cells)
            ps = float(_fires(rule, sk).mean())
            pt = float(_fires(rule, takes).mean()) if n_take else 0.0
            rule.update(J=ps - pt, n_uses=n, skips_caught=ps, takes_caught=pt)
            rules.append(rule)
            notes[reason] = f"rule built ({n} uses)"
            continue
        best = None
        for feat, op in RULE_MAP[reason]:
            if op == "eq":
                th = -1.0
                fx_s = (sk[feat].to_numpy(float) == th)
                fx_t = (takes[feat].to_numpy(float) == th)
                ps, pt = float(fx_s.sum()) / n, float(fx_t.sum()) / max(n_take, 1)
                cand = (th, ps - pt, ps, pt)
            else:
                cand = _best_threshold(sk[feat].to_numpy(float), takes[feat].to_numpy(float), op, n, n_take)
            if cand is None:
                continue
            if best is None or cand[1] > best[1][1] + 1e-12:
                best = ((feat, op), cand)
        if best is None or best[1][1] <= 0:
            notes[reason] = f"rule dropped: best J <= 0 ({n} uses)"
            continue
        (feat, op), (th, j, ps, pt) = best
        rules.append(dict(reason=reason, kind="threshold", feature=feat, op=op, threshold=th, J=j, n_uses=n,
                          skips_caught=ps, takes_caught=pt))
        notes[reason] = f"rule built ({n} uses): {feat} {op} {th:.4g}, J {j:.3f}"
    return rules, notes


def predict_rules(rules: list[dict], X: pd.DataFrame) -> np.ndarray:
    """1 = take: the clone takes a candidate only if no rule fires."""
    fire = np.zeros(len(X), bool)
    for r in rules:
        fire |= _fires(r, X)
    return (~fire).astype(int)


def rules_fire_detail(rules: list[dict], X: pd.DataFrame) -> dict[str, np.ndarray]:
    return {r["reason"]: _fires(r, X) for r in rules}


# ------------------------------------------------------------------------------------------------ model clone M
def _design(X: pd.DataFrame, st: dict) -> np.ndarray:
    a = X[MODEL_NUM].to_numpy(float)
    a = np.where(np.isnan(a), np.asarray(st["median"]), a)
    a = (a - np.asarray(st["mean"])) / np.asarray(st["sd"])
    sess = np.eye(N_SESSION)[X["F12_session"].to_numpy(int)]
    wday = np.eye(N_WEEKDAY)[X["F12_weekday"].to_numpy(int)]
    return np.hstack([a, sess, wday])


def fit_logit(train: pd.DataFrame, C: float) -> dict:
    a = train[MODEL_NUM].to_numpy(float)
    med = np.array([np.nanmedian(a[:, k]) if (~np.isnan(a[:, k])).any() else 0.0 for k in range(a.shape[1])])
    filled = np.where(np.isnan(a), med, a)
    mu, sd = filled.mean(0), filled.std(0)
    sd = np.where(sd > 0, sd, 1.0)
    st = dict(median=med.tolist(), mean=mu.tolist(), sd=sd.tolist())
    lr = LogisticRegression(C=C, max_iter=5000, solver="lbfgs")
    lr.fit(_design(train, st), train["y"].to_numpy(int))
    return dict(kind="logit", C=float(C), coef=lr.coef_[0].tolist(), intercept=float(lr.intercept_[0]), **st)


def proba_logit(model: dict, X: pd.DataFrame) -> np.ndarray:
    z = _design(X, model) @ np.asarray(model["coef"]) + model["intercept"]
    return 1.0 / (1.0 + np.exp(-z))


def fit_gb(train: pd.DataFrame):
    gb = HistGradientBoostingClassifier(max_depth=3, max_iter=100, early_stopping=False, random_state=0)
    gb.fit(train[GB_COLS].to_numpy(float), train["y"].to_numpy(int))
    return gb


def proba_gb(gb, X: pd.DataFrame) -> np.ndarray:
    return gb.predict_proba(X[GB_COLS].to_numpy(float))[:, 1]


def f2_score(y: np.ndarray, pred: np.ndarray) -> float:
    tp = float(((pred == 1) & (y == 1)).sum())
    fp = float(((pred == 1) & (y == 0)).sum())
    fn = float(((pred == 0) & (y == 1)).sum())
    if tp == 0:
        return 0.0
    p, r = tp / (tp + fp), tp / (tp + fn)
    return 5 * p * r / (4 * p + r)


def best_threshold_f2(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    """The take-probability threshold maximising F2 (recall weighted twice as heavily as precision); ties -> smaller."""
    scores = np.array([f2_score(y, (p >= t).astype(int)) for t in THRESHOLD_GRID])
    i = int(np.argmax(scores))
    return float(THRESHOLD_GRID[i]), float(scores[i])


def _inner_seed(rep: int, fold: int, k: int) -> int:
    return zlib.crc32(b"W15-0050-cv-inner") + 1000 * rep + 10 * fold + k


def inner_oof(train: pd.DataFrame, kind: str, C: float | None, rep: int, fold: int) -> np.ndarray:
    y = train["y"].to_numpy(int)
    skf = StratifiedKFold(S.INNER_FOLDS, shuffle=True, random_state=_inner_seed(rep, fold, 0))
    oof = np.zeros(len(train))
    for tr, te in skf.split(train, y):
        a, b = train.iloc[tr], train.iloc[te]
        oof[te] = proba_logit(fit_logit(a, C), b) if kind == "logit" else proba_gb(fit_gb(a), b)
    return oof


def fit_model(train: pd.DataFrame, kind: str, rep: int = 0, fold: int = 0) -> dict:
    """Choose C (logit only) and the threshold by inner CV on `train`, then refit on all of `train`."""
    y = train["y"].to_numpy(int)
    if kind == "logit":
        best = None
        for C in S.LOGIT_C_GRID:
            thr, f2 = best_threshold_f2(y, inner_oof(train, "logit", C, rep, fold))
            if best is None or f2 > best[2] + 1e-12:
                best = (C, thr, f2)
        C, thr, f2 = best
        m = fit_logit(train, C)
    else:
        thr, f2 = best_threshold_f2(y, inner_oof(train, "gb", None, rep, fold))
        m = dict(kind="gb", model=fit_gb(train))
    m.update(threshold=thr, inner_f2=f2)
    return m


def predict_model(m: dict, X: pd.DataFrame) -> np.ndarray:
    p = proba_logit(m, X) if m["kind"] == "logit" else proba_gb(m["model"], X)
    return (p >= m["threshold"]).astype(int)


# ------------------------------------------------------------------------------------------------ fidelity
def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    n = len(y)
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    return dict(tp=tp, fp=fp, fn=fn, tn=tn,
                recall=tp / (tp + fn) if tp + fn else float("nan"),
                precision=tp / (tp + fp) if tp + fp else float("nan"),
                agreement=po, kappa=(po - pe) / (1 - pe) if pe < 1 else float("nan"),
                clone_take_rate=(tp + fp) / n)


def recall_bar(consistency: float) -> float:
    """I20: if Ben's own repeat consistency on takes is below 75%, a clone is held to that instead."""
    return min(S.FIDELITY_RECALL, consistency)


def meets_bar(recall: float, precision: float, consistency: float) -> bool:
    return bool(recall >= recall_bar(consistency) and precision >= S.FIDELITY_PRECISION)


def cv_predictions(df: pd.DataFrame, repeats: int = S.CV_REPEATS, with_models: bool = True) -> dict[str, np.ndarray]:
    """Out-of-fold take predictions for R (and M, M-GB), shape (repeats, n)."""
    y = df["y"].to_numpy(int)
    out = {"R": np.zeros((repeats, len(df)), int)}
    if with_models:
        out["M"] = np.zeros((repeats, len(df)), int)
        out["M-GB"] = np.zeros((repeats, len(df)), int)
    for r in range(repeats):
        skf = StratifiedKFold(S.CV_FOLDS, shuffle=True, random_state=S.CV_SEED_WORD + r)
        for f, (tr, te) in enumerate(skf.split(df, y)):
            train, test = df.iloc[tr], df.iloc[te]
            rules, _ = fit_rules(train)
            out["R"][r, te] = predict_rules(rules, test)
            if with_models:
                out["M"][r, te] = predict_model(fit_model(train, "logit", r, f), test)
                out["M-GB"][r, te] = predict_model(fit_model(train, "gb", r, f), test)
    return out


def summarise(df: pd.DataFrame, preds: np.ndarray) -> dict:
    """Per-repeat metrics on the pooled out-of-fold predictions; headline = mean over repeats; range reported."""
    y = df["y"].to_numpy(int)
    per = [metrics(y, p) for p in preds]
    keys = ("recall", "precision", "agreement", "kappa", "clone_take_rate")
    mean = {k: float(np.mean([m[k] for m in per])) for k in keys}
    lo = {k: float(np.min([m[k] for m in per])) for k in keys}
    hi = {k: float(np.max([m[k] for m in per])) for k in keys}
    conf = {k: float(np.mean([m[k] for m in per])) for k in ("tp", "fp", "fn", "tn")}
    return dict(mean=mean, lo=lo, hi=hi, confusion_mean=conf, per_repeat=per)


def reason_catch(df: pd.DataFrame, preds: np.ndarray) -> dict[str, float]:
    """Share of Ben's skips for each reason that the clone also skipped, averaged over repeats (out of fold)."""
    out = {}
    for reason in sorted(set(df["reason"]) - {""}):
        m = (df["y"].to_numpy() == 0) & (df["reason"].to_numpy() == reason)
        if m.sum():
            out[reason] = float(np.mean([(p[m] == 0).mean() for p in preds]))
    return out


# ------------------------------------------------------------------------------------------------ Ben's own consistency
def repeat_consistency(first: dict[str, str], repeats: list[tuple[str, str]]) -> dict:
    """first: candidate -> first label; repeats: (candidate, label on the repeat). Labels only."""
    tk = [(c, l) for c, l in repeats if first.get(c) == "TAKE"]
    sk = [(c, l) for c, l in repeats if first.get(c) == "SKIP"]
    t_again = sum(l == "TAKE" for _, l in tk)
    s_again = sum(l == "SKIP" for _, l in sk)
    n = len(tk) + len(sk)
    return dict(n_repeats=n, n_first_take=len(tk), take_again=t_again,
                take_consistency=t_again / len(tk) if tk else float("nan"),
                n_first_skip=len(sk), skip_again=s_again,
                skip_consistency=s_again / len(sk) if sk else float("nan"),
                agreement=(t_again + s_again) / n if n else float("nan"))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return float(c - h), float(c + h)
