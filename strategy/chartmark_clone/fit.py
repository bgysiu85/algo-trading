#!/usr/bin/env python3
"""CHARTMARK-CLONE sub 4: fit the clone on Ben's labels, score fidelity, freeze. REGISTERED_chartmark_clone.md sec 8 + Amendment 2.
LABELS AND CHART FEATURES ONLY -- no price outcome, exit or P&L is read, and the v1 trades file is never opened.

    python -m strategy.chartmark_clone.fit              fidelity report only (prints; writes and changes nothing)
    python -m strategy.chartmark_clone.fit --freeze     the same, then refit on all labels and write the frozen clone,
                                                         the feature table, the report and the ledger hashes (once)

Order (registered, fixed): R is scored first; R meets the bar -> R is the clone; R misses -> M; M misses too -> M marked
'fidelity not met'. M and M-GB are always fitted and frozen beside it (V-OTHER / M-GB variants of sec 9.4)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.chartmark_clone import clone as CL
from strategy.chartmark_clone import features as FT
from strategy.chartmark_clone import ledger as LG
from strategy.chartmark_clone import qorder as QO
from strategy.chartmark_clone import spec as S
from strategy.chartmark_clone.chartdata import build_chart_data
from strategy.chartmark_clone.labels import LabelStore

REPO = Path(__file__).resolve().parents[2]
OUT = Path(r"D:\Trading\Claude outputs")
CACHE = REPO / "var" / S.FRAME_CACHE_FILE
CODE_FILES = ("features.py", "daily.py", "chartdata.py", "clone.py", "fit.py", "spec.py")
RESULTS_FILE = f"clone_fit_results_{S.ID}.json"


class FitError(RuntimeError):
    pass


def br(x: float, d: int = 3) -> str:
    """Negative numbers in brackets (Ben's convention)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"({abs(x):.{d}f})" if x < 0 else f"{x:.{d}f}"


def pct(x: float, d: int = 1) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"({abs(x) * 100:.{d}f}%)" if x < 0 else f"{x * 100:.{d}f}%"


# ------------------------------------------------------------------------------------------------ data
def load_labelled(out_dir: Path, cache: Path) -> dict:
    """Validated labels (the LabelStore refuses a file that does not match the queue) joined to the chart features."""
    out_dir = Path(out_dir)
    fr = LG.load_frame_cache(cache)
    led = LG.check_inputs(out_dir, fr)
    man = pd.read_csv(out_dir / S.MANIFEST_FILE, dtype={"candidate_id": str, "decision_t": str})
    q = pd.read_csv(out_dir / S.QUEUE_FILE, dtype={"candidate_id": str, "key": str})
    items = QO.schedule(q)
    store = LabelStore(out_dir / S.LABELS_FILE, items, "fit")           # validates order, queue match and UNDO rows
    rows = pd.DataFrame(store.effective)
    if rows.empty:
        raise FitError("no labels")
    firsts = rows[rows["is_repeat"] != "1"].copy()
    reps = rows[rows["is_repeat"] == "1"].copy()
    if firsts["candidate_id"].duplicated().any():
        raise FitError("a candidate has two first labels")
    cd = build_chart_data(fr)
    ft = FT.feature_table(cd, man)
    df = firsts.merge(ft, on="candidate_id", how="left", validate="one_to_one")
    df["y"] = (df["label"] == "TAKE").astype(int)
    df["reason"] = np.where(df["y"] == 0, df["skip_reason"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True), "")
    df["year"] = pd.to_datetime(df["candidate_id"]).dt.year
    df = df.merge(man[["candidate_id", "decision_idx"]], on="candidate_id", how="left")
    df = df.sort_values("seq", key=lambda s: s.astype(int)).reset_index(drop=True)
    return dict(df=df, reps=reps, led=led, man=man, ft=ft, store=store)


def label_stats(df: pd.DataFrame, reps: pd.DataFrame) -> dict:
    """Everything that can be said from labels and chart features alone (registered, sec 8.3 last bullet)."""
    d = df.copy()
    d["seq_i"] = d["seq"].astype(int)
    out = {}
    out["n_unique"], out["n_takes"] = len(d), int(d["y"].sum())
    out["take_rate"] = float(d["y"].mean())
    out["by_year"] = {int(k): dict(n=int(len(g)), take_rate=float(g["y"].mean())) for k, g in d.groupby("year")}
    out["by_trend"] = {("up" if k > 0 else "down"): dict(n=int(len(g)), take_rate=float(g["y"].mean()))
                       for k, g in d.groupby("F1")}
    names = FT.SESSION_NAMES
    out["by_session"] = {names[int(k)]: dict(n=int(len(g)), take_rate=float(g["y"].mean())) for k, g in d.groupby("F12_session")}
    out["by_block"] = {int(k): dict(n=int(len(g)), take_rate=float(g["y"].mean()), median_ms=float(pd.to_numeric(g["ms_to_decide"]).median()))
                       for k, g in d.groupby(d["seq_i"] // 100)}
    dt = pd.to_datetime(d["candidate_id"])
    famous = np.zeros(len(d), bool)
    for a, b in S.FAMOUS_WINDOWS:
        famous |= ((dt >= pd.Timestamp(a)) & (dt <= pd.Timestamp(b) + pd.Timedelta(days=1))).to_numpy()
    out["famous"] = dict(n=int(famous.sum()), take_rate=float(d["y"][famous].mean()) if famous.any() else float("nan"),
                         rest_n=int((~famous).sum()), rest_take_rate=float(d["y"][~famous].mean()))
    out["skip_reasons"] = {k: int(v) for k, v in d.loc[d["y"] == 0, "reason"].value_counts().sort_index().items()}
    out["take_reasons"] = {str(k): int(v) for k, v in d.loc[d["y"] == 1, "take_reason"].fillna("").value_counts().items()}
    n_skip = int((d["y"] == 0).sum())
    out["reason7_share"] = out["skip_reasons"].get("7", 0) / n_skip if n_skip else float("nan")
    note7 = d.loc[(d["y"] == 0) & (d["reason"] == "7"), "note"].fillna("").str.lower()
    out["reason7_wait_notes"] = int(note7.str.contains("wait").sum())
    out["median_ms"] = float(pd.to_numeric(d["ms_to_decide"]).median())
    out["sittings"] = sorted(set(d["sitting_id"]))
    med = d.groupby("y")[[c for c in FT.FEATURES]].median()
    out["feature_medians"] = {("take" if k == 1 else "skip"): {c: float(v) for c, v in row.items()} for k, row in med.iterrows()}
    first = dict(zip(d["candidate_id"], d["label"]))
    rc = CL.repeat_consistency(first, list(zip(reps["candidate_id"], reps["label"])))
    rc["take_ci"] = CL.wilson(rc["take_again"], rc["n_first_take"])
    out["consistency"] = rc
    return out


# ------------------------------------------------------------------------------------------------ the fit
def run_cv(df: pd.DataFrame, consistency: float) -> dict:
    preds = CL.cv_predictions(df)
    res = {}
    for name, p in preds.items():
        s = CL.summarise(df, p)
        s["meets_bar"] = CL.meets_bar(s["mean"]["recall"], s["mean"]["precision"], consistency)
        s["catch_by_reason"] = CL.reason_catch(df, p)
        res[name] = s
    return res


def choose(cv: dict) -> tuple[str, bool]:
    """Registered order: R if it meets the bar; else M (met or marked 'fidelity not met')."""
    if cv["R"]["meets_bar"]:
        return "R", True
    return "M", bool(cv["M"]["meets_bar"])


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def freeze(df: pd.DataFrame, cv: dict, stats: dict, load: dict, out_dir: Path, report_text: str,
           base_commit: str | None = None) -> dict:
    out_dir = Path(out_dir)
    led = LG.read_ledger(out_dir)
    if led.get("clone_frozen_sha256"):
        raise FitError("the clone is already frozen (ledger has clone_frozen_sha256): it is never refitted.")
    rules, notes = CL.fit_rules(df)
    m = CL.fit_model(df, "logit", S.CV_REPEATS, 0)
    g = CL.fit_model(df, "gb", S.CV_REPEATS, 0)
    gb_p = CL.proba_gb(g["model"], df)
    which, met = choose(cv)
    labels_sha = LG.sha256_file(out_dir / S.LABELS_FILE)
    tab = df[["candidate_id", "seq", "label", "skip_reason", "take_reason"] + FT.FEATURE_COLUMNS]
    tab_path = out_dir / S.FEATURE_TABLE_FILE
    tab.to_csv(tab_path, index=False, lineterminator="\n", encoding="utf-8", float_format="%.17g")
    frozen = dict(
        study=S.STUDY, frozen_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        clone_type=which, fidelity_met=met, recall_bar=CL.recall_bar(stats["consistency"]["take_consistency"]),
        precision_bar=S.FIDELITY_PRECISION, ben_take_consistency=stats["consistency"]["take_consistency"],
        n_unique=stats["n_unique"], n_takes=stats["n_takes"],
        cv_headline={k: cv[k]["mean"] for k in cv}, cv_meets_bar={k: cv[k]["meets_bar"] for k in cv},
        R=dict(rules=rules, notes=notes, rule_semantics="take iff no rule fires; NaN never fires; hour/weekday = bar j open, New York"),
        M=dict(kind="logit", C=m["C"], threshold=m["threshold"], intercept=m["intercept"], coef=m["coef"],
               median=m["median"], mean=m["mean"], sd=m["sd"], feature_order=CL.MODEL_NUM,
               onehot=["F12_session 0..3", "F12_weekday 0..6"], inner_f2=m["inner_f2"]),
        M_GB=dict(recipe="HistGradientBoostingClassifier(max_depth=3, max_iter=100, early_stopping=False, random_state=0) "
                         "refit on clone_features_w15_0050.csv (read with float_precision='round_trip') with columns " + ",".join(CL.GB_COLS),
                  threshold=g["threshold"], inner_f2=g["inner_f2"],
                  train_proba_sha256=sha_text(",".join(f"{x:.6f}" for x in gb_p)), cols=CL.GB_COLS),
        feature_table=dict(file=S.FEATURE_TABLE_FILE, sha256=LG.sha256_file(tab_path)),
        code_sha256={f: LG.sha256_file(Path(__file__).with_name(f)) for f in CODE_FILES},
        labels_sha256=labels_sha, queue_sha256=led["queue_sha256"], manifest_sha256=led["manifest_sha256"],
        frame_content_sha256=led["frame_content_sha256"], git_base_commit=base_commit or LG.git_commit(REPO),
        library_versions=_versions(), report_sha256=sha_text(report_text))
    path = out_dir / S.FROZEN_FILE
    if path.exists():
        raise FitError(f"{path} already exists")
    path.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    LG.mark_frozen(out_dir, labels_sha, LG.sha256_file(path))
    return frozen


def _versions() -> dict:
    import sklearn
    return dict(numpy=np.__version__, pandas=pd.__version__, sklearn=sklearn.__version__, python=sys.version.split()[0])


# ------------------------------------------------------------------------------------------------ report
def report(stats: dict, cv: dict, which: str, met: bool, rules_all: list[dict], notes_all: dict) -> str:
    c = stats["consistency"]
    bar_r = CL.recall_bar(c["take_consistency"])
    L = [f"{S.STUDY} -- sub 4 fit and fidelity report (labels and chart features only; no price outcome, exit or P&L)", ""]
    L += ["1. THE LABELS",
          f"   unique candidates labelled {stats['n_unique']} (registered minimum 500); takes {stats['n_takes']} "
          f"(minimum 60); take rate {pct(stats['take_rate'])}; sittings {', '.join(stats['sittings'])}",
          f"   skip reasons used: {stats['skip_reasons']}   (reason 7 = {pct(stats['reason7_share'])} of skips; "
          f"limit 25% -> {'OK' if stats['reason7_share'] <= 0.25 else 'selection partly outside the list'})",
          f"   of the reason-7 notes, {stats['reason7_wait_notes']} say he would wait for more bars before entering",
          f"   take reasons used: {stats['take_reasons']}",
          f"   median decision time {stats['median_ms'] / 1000:.1f} s", ""]
    L += ["2. BEN'S OWN CONSISTENCY (the ceiling for any clone)",
          f"   {c['n_repeats']} repeat presentations (unmarked on screen); takes he took again: {c['take_again']} of {c['n_first_take']} "
          f"= {pct(c['take_consistency'])} (95% interval {pct(c['take_ci'][0])} to {pct(c['take_ci'][1])}); "
          f"skips he skipped again: {c['skip_again']} of {c['n_first_skip']} = {pct(c['skip_consistency'])}; "
          f"overall agreement {pct(c['agreement'])}",
          f"   registered: recall bar = min(75%, consistency) = {pct(bar_r)}; precision bar = {pct(S.FIDELITY_PRECISION, 0)}", ""]
    L += ["3. FIDELITY (5 x repeated stratified 5-fold CV, out-of-fold; mean over repeats [range])",
          f"   always-take reference: recall 100.0%, precision {pct(stats['take_rate'])} (the base rate)"]
    for name in ("R", "M", "M-GB"):
        s = cv[name]
        m, lo, hi = s["mean"], s["lo"], s["hi"]
        cf = s["confusion_mean"]
        L.append(f"   {name:5s} take-recall {pct(m['recall'])} [{pct(lo['recall'])}..{pct(hi['recall'])}]   "
                 f"take-precision {pct(m['precision'])} [{pct(lo['precision'])}..{pct(hi['precision'])}]   "
                 f"agreement {pct(m['agreement'])}   kappa {br(m['kappa'])}   clone take rate {pct(m['clone_take_rate'])}   "
                 f"bar {'MET' if s['meets_bar'] else 'NOT met'}")
        L.append(f"         confusion (mean): both take {cf['tp']:.1f} | clone takes, Ben skipped {cf['fp']:.1f} | "
                 f"clone skips, Ben took {cf['fn']:.1f} | both skip {cf['tn']:.1f}")
        L.append("         share of Ben's skips of each reason that the clone also skips: " +
                 ", ".join(f"reason {k}: {pct(v)}" for k, v in s["catch_by_reason"].items()))
    L += ["", "   sensitivity (reported, not a criterion): against the UNCAPPED 75% recall bar -> " +
          "; ".join(f"{n} {'met' if CL.meets_bar(cv[n]['mean']['recall'], cv[n]['mean']['precision'], 1.0) else 'NOT met'}"
                    for n in ("R", "M", "M-GB")) +
          f".  Against the 95% interval's upper end of Ben's consistency ({pct(c['take_ci'][1])}) the bar would be "
          f"{pct(CL.recall_bar(c['take_ci'][1]))}."]
    L += ["", f"4. THE CLONE (registered order R -> M): {which}"
          + ("" if met else "   *** FIDELITY NOT MET -- the backtest still runs (sub 5); the deployment decision carries this mark ***"),
          "   rules fitted on all labels (R):"]
    for k in ("1", "2", "3", "4", "5", "6", "7"):
        L.append(f"     reason {k}: {notes_all.get(k, '')}")
    for r in rules_all:
        if r["kind"] == "cells":
            L.append(f"     RULE {r['reason']}: weekday-hour cells {r['cells']}  (catches {pct(r['skips_caught'])} of those skips, "
                     f"{pct(r['takes_caught'])} of takes)")
        else:
            sym = {"gt": ">", "lt": "<", "eq": "=="}[r["op"]]
            L.append(f"     RULE {r['reason']}: skip when {r['feature']} {sym} {br(r['threshold'], 4)}   "
                     f"catches {pct(r['skips_caught'])} of reason-{r['reason']} skips and {pct(r['takes_caught'])} of Ben's takes "
                     f"(J {br(r['J'])})")
    L += ["", "5. WHAT THE LABELS SAY (labels only)",
          "   take rate by year: " + ", ".join(f"{y}: {pct(v['take_rate'], 0)} (n {v['n']})" for y, v in stats["by_year"].items()),
          "   by daily trend: " + ", ".join(f"{k}: {pct(v['take_rate'])} (n {v['n']})" for k, v in stats["by_trend"].items()),
          "   by session of the order bar: " + ", ".join(f"{k}: {pct(v['take_rate'])} (n {v['n']})" for k, v in stats["by_session"].items()),
          "   by position in the queue (blocks of 100 = fatigue drift): " +
          ", ".join(f"{k * 100}+: {pct(v['take_rate'], 0)}" for k, v in stats["by_block"].items()),
          f"   famous windows (2014 collapse, 2020 crash): take rate {pct(stats['famous']['take_rate'])} on {stats['famous']['n']} "
          f"vs {pct(stats['famous']['rest_take_rate'])} on the other {stats['famous']['rest_n']}",
          "   median chart feature, takes vs skips:"]
    for f in FT.FEATURES:
        L.append(f"     {f:4s} take {br(stats['feature_medians']['take'][f], 3):>9s}   skip {br(stats['feature_medians']['skip'][f], 3):>9s}")
    sr = stats["skip_reasons"]
    top = sorted(sr, key=lambda k: -sr[k])
    L += ["", "5b. REGISTERED PREDICTIONS (sec 16) vs WHAT HAPPENED",
          f"   Ben takes 8-20% of candidates: actual {pct(stats['take_rate'])} -> {'inside' if 0.08 <= stats['take_rate'] <= 0.20 else 'OUTSIDE'}",
          f"   consistency on repeated takes 60-80%: actual {pct(c['take_consistency'])} -> "
          f"{'inside' if 0.6 <= c['take_consistency'] <= 0.8 else 'OUTSIDE'} (13 observations)",
          f"   rules clone meets the fidelity bar (about 40%): R {'met' if cv['R']['meets_bar'] else 'did not meet'} the registered bar",
          f"   most-used skip reasons 3 (chop) and 1 (against the daily trend): actual order {', '.join(top[:3])} "
          f"(reason 1 used {sr.get('1', 0)} times)"]
    L += ["", "6. CAVEATS",
          "   - 13 repeated takes make the consistency ceiling rough (see its interval); with the cap at the point estimate the bar is soft.",
          "   - F10 (share of recent bars below the 20-bar volume average) is mostly a time-of-day proxy, because the average mixes day and night hours.",
          "   - Reasons used fewer than 15 times get no rule (registered); reason 7 is not coded.",
          "   - Labels are Ben on historical charts with the date, year and instrument hidden; the famous-window split above is the leakage check.",
          "   - Nothing here says whether the clone's picks make money. That is sub 5, one run, after this freeze."]
    return "\n".join(L) + "\n"


def run(out_dir: Path, cache: Path, do_freeze: bool, log=print, base_commit: str | None = None) -> dict:
    ld = load_labelled(out_dir, cache)
    df, reps = ld["df"], ld["reps"]
    p = ld["store"].progress()
    if not p["enough"]:
        raise FitError(f"the registered stop rule is not met yet ({p}) -- labels first.")
    stats = label_stats(df, reps)
    consistency = stats["consistency"]["take_consistency"]
    cv = run_cv(df, consistency)
    which, met = choose(cv)
    rules_all, notes_all = CL.fit_rules(df)
    text = report(stats, cv, which, met, rules_all, notes_all)
    log(text)
    res = dict(stats=stats, cv={k: {kk: vv for kk, vv in v.items() if kk != "per_repeat"} for k, v in cv.items()},
               cv_per_repeat={k: v["per_repeat"] for k, v in cv.items()}, which=which, fidelity_met=met,
               rules=rules_all, notes=notes_all)
    if do_freeze:
        out_dir = Path(out_dir)
        (out_dir / S.FIT_REPORT_FILE).write_text(text, encoding="utf-8")
        fz = freeze(df, cv, stats, ld, out_dir, text, base_commit)
        (out_dir / RESULTS_FILE).write_text(json.dumps(res, indent=2, default=float) + "\n", encoding="utf-8")
        res["frozen"] = fz
        log(f"FROZEN: {S.FROZEN_FILE}  type {fz['clone_type']}  fidelity_met {fz['fidelity_met']}  labels_sha256 {fz['labels_sha256']}")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CHARTMARK-CLONE fit (labels only)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--base-commit", default=None, help="git HEAD to record in the frozen file (default: ask git)")
    ap.add_argument("--freeze", action="store_true", help="refit on all labels, write the frozen clone, update the ledger (once)")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    run(Path(a.out), Path(a.cache), a.freeze, base_commit=a.base_commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
