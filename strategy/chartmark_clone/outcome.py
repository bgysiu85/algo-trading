#!/usr/bin/env python3
"""CHARTMARK-CLONE sub 5: THE ONE OUTCOME RUN. REGISTERED_chartmark_clone.md sec 9-11 (+ Amendment 3, PRE-RUN).

    python -m strategy.chartmark_clone.outcome --g6      gate G6 only: hashes + parity. Counts, no P&L, repeatable.
    python -m strategy.chartmark_clone.outcome --run     verify, G6, then the single outcome run (ledger-locked)

TRAINING WINDOW ONLY (2010-06 -> 2021-12-31): the frame cache holds nothing later and no holdout path exists here.
The run happens once: the ledger records outcome_run_started_utc before any number is computed and outcome_run_done
after the report is written; a second run is refused. A crash after the start refuses too, unless --retry-after-crash is
given (recorded in the ledger): a crash means no result was shown, a retry changes nothing registered.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from zlib import crc32

import numpy as np
import pandas as pd

from strategy.chartmark import book as BK
from strategy.chartmark import controls as CT
from strategy.chartmark import engine as E
from strategy.chartmark import spec as S1
from strategy.chartmark.data import indicators
from strategy.chartmark.run import exits as exits_of
from strategy.chartmark.run import money, summarize
from strategy.chartmark_clone import clone as CL
from strategy.chartmark_clone import fit as FIT
from strategy.chartmark_clone import gated as G
from strategy.chartmark_clone import ledger as LG
from strategy.chartmark_clone import spec as S
from strategy.chartmark_clone.chartdata import build_chart_data
from strategy.htf import book as HBK

REPO = Path(__file__).resolve().parents[2]
FIRST, LAST = "2010-06-06", "2021-12-31"
DRAWS_C3, DRAWS_H1 = 1000, 10000
OUT_STEM = "w15_0050_clone_backtest_20261001"
REG_DOC = REPO / "docs" / "research" / "REGISTERED_chartmark_clone.md"
COMMITTED_COPIES = REPO / "docs" / "research" / "clone_w15_0050"


class OutcomeRefused(RuntimeError):
    pass


def pts(x) -> str:
    return f"({abs(x):.2f})" if x < 0 else f"{x:.2f}"


def pct(x, d=1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100 * x:.{d}f}%"


def _git(*args) -> str:
    r = subprocess.run(["git", "--no-optional-locks", *args], cwd=str(REPO), capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise OutcomeRefused(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


# ------------------------------------------------------------------------------------------------ verification (no P&L)
def verify(out_dir: Path, cache: Path, *, check_git: bool = True) -> dict:
    """Sec 8.4 / G7: every frozen input equals what the ledger recorded; the frozen set is committed. Refuses on any miss."""
    out_dir = Path(out_dir)
    led = LG.read_ledger(out_dir)
    fz_path = out_dir / S.FROZEN_FILE
    fz = json.loads(fz_path.read_text(encoding="utf-8"))
    fr = LG.load_frame_cache(cache)
    checks = []

    def chk(name, ok, detail=""):
        checks.append(dict(check=name, ok=bool(ok), detail=detail))

    chk("frozen file SHA-256 = ledger clone_frozen_sha256", LG.sha256_file(fz_path) == led.get("clone_frozen_sha256"))
    chk("label file SHA-256 = ledger = frozen file", LG.sha256_file(out_dir / S.LABELS_FILE) == led.get("labels_sha256") == fz["labels_sha256"])
    chk("queue SHA-256 = ledger", LG.sha256_file(out_dir / S.QUEUE_FILE) == led["queue_sha256"] == fz["queue_sha256"])
    chk("manifest SHA-256 = ledger", LG.sha256_file(out_dir / S.MANIFEST_FILE) == led["manifest_sha256"] == fz["manifest_sha256"])
    chk("frame content SHA-256 = ledger", LG.frame_content_sha256(fr) == led["frame_content_sha256"] == fz["frame_content_sha256"])
    chk("feature table SHA-256 = frozen file", LG.sha256_file(out_dir / S.FEATURE_TABLE_FILE) == fz["feature_table"]["sha256"])
    for f, h in fz["code_sha256"].items():
        chk(f"code {f} SHA-256 = frozen file", LG.sha256_file(Path(__file__).with_name(f)) == h)
    chk("frame ends before 2022-01-01 (training window only)", fr.ny[-1] < pd.Timestamp("2022-01-01", tz=fr.ny.tz))
    chk("ledger: outcome run not yet done", not led.get("outcome_run_done"))
    head = ""
    if check_git:
        head = _git("rev-parse", "HEAD")
        copy = COMMITTED_COPIES / S.FROZEN_FILE
        chk("committed copy of the frozen file = ledger hash", copy.exists() and LG.sha256_file(copy) == led["clone_frozen_sha256"])
        tracked = [f"strategy/chartmark_clone/{f}" for f in fz["code_sha256"]] + [f"docs/research/clone_w15_0050/{S.FROZEN_FILE}"]
        dirty = _git("status", "--porcelain", "--", *tracked)
        chk("frozen code + frozen copy committed and unmodified", dirty == "", dirty)
        try:
            _git("merge-base", "--is-ancestor", fz["git_base_commit"], "HEAD")
            chk("frozen base commit is an ancestor of HEAD", True)
        except OutcomeRefused as exc:
            chk("frozen base commit is an ancestor of HEAD", False, str(exc))
        fz_commit = _git("log", "-1", "--format=%H", "--", f"docs/research/clone_w15_0050/{S.FROZEN_FILE}")
        chk("frozen copy has a commit", bool(fz_commit), fz_commit)
    bad = [c for c in checks if not c["ok"]]
    if bad:
        raise OutcomeRefused("verification failed: " + "; ".join(f"{c['check']} {c['detail']}" for c in bad))
    return dict(checks=checks, ledger=led, frozen=fz, frame=fr, head=head)


def refit_gb(frozen: dict, out_dir: Path):
    """M-GB: refit on the committed feature table (labels only) and check the frozen prediction hash. None if it differs."""
    tab = pd.read_csv(Path(out_dir) / S.FEATURE_TABLE_FILE, float_precision="round_trip")
    tab["y"] = (tab["label"] == "TAKE").astype(int)
    tab["reason"] = np.where(tab["y"] == 0, tab["skip_reason"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True), "")
    g = CL.fit_model(tab, "gb", S.CV_REPEATS, 0)
    h = FIT.sha_text(",".join(f"{x:.6f}" for x in CL.proba_gb(g["model"], tab)))
    ok = (h == frozen["M_GB"]["train_proba_sha256"]) and abs(g["threshold"] - frozen["M_GB"]["threshold"]) < 1e-12
    return (g["model"] if ok else None), ok


def g6(fr, ind, man_ids: set[str], log=print) -> dict:
    """Sec 11 G6. Always-take reproduces v1 trade for trade (2,670, same fill timestamps as the manifest); always-skip -> 0."""
    ref, _ = E.simulate(fr, ind, S1.BASE)
    tk, ctk = G.simulate_gated(fr, ind, S1.BASE, G.AlwaysTake())
    sk, csk = G.simulate_gated(fr, ind, S1.BASE, G.AlwaysSkip())
    ids = [fr.ny[t.entry_j].tz_localize(None).strftime("%Y-%m-%d %H:%M:%S") for t in tk]
    res = dict(v1_trades=len(ref), always_take_trades=len(tk), always_take_identical=(tk == ref),
               always_take_matches_manifest=(set(ids) == man_ids and len(ids) == len(set(ids))),
               pool_registered=S.POOL_N, always_skip_trades=len(sk), always_skip_asked=csk["would_be"],
               always_take_asked=ctk["would_be"])
    res["ok"] = bool(res["v1_trades"] == S.POOL_N == res["always_take_trades"] and res["always_take_identical"]
                     and res["always_take_matches_manifest"] and res["always_skip_trades"] == 0)
    log(f"G6: v1 {res['v1_trades']} trades; always-take {res['always_take_trades']} identical={res['always_take_identical']} "
        f"= manifest {res['always_take_matches_manifest']}; always-skip {res['always_skip_trades']} "
        f"(asked {res['always_skip_asked']} times) -> {'PASS' if res['ok'] else 'FAIL'}")
    return res


# ------------------------------------------------------------------------------------------------ criteria (sec 10)
def evaluate(df_mid: pd.DataFrame, df_high: pd.DataFrame, *, c1_mid: pd.DataFrame, c3_p99: float, n_grid_pos: int) -> list[dict]:
    n = len(df_mid)
    net = float(df_mid["net"].sum()) if n else 0.0
    yn = HBK.year_table(df_mid) if n else {}
    h1 = float(df_mid.loc[df_mid["year"] <= 2015, "net"].sum()) if n else 0.0
    h2 = float(df_mid.loc[df_mid["year"] >= 2016, "net"].sum()) if n else 0.0
    d1, d2 = (BK.drop_top(yn, 1), BK.drop_top(yn, 2)) if yn else (0.0, 0.0)
    boot = HBK.bootstrap_by_year(yn, n=2000, seed=0) if n else float("nan")
    _, share = HBK.top_year_share(yn)
    hn = float(df_high["net"].sum()) if len(df_high) else 0.0
    c1net = float(c1_mid["net"].sum()) if len(c1_mid) else 0.0
    r_h, r_c1 = BK.daily_vol_ratio(df_mid, FIRST, LAST), BK.daily_vol_ratio(c1_mid, FIRST, LAST)
    rows = [
        dict(n=1, name="Net > $0 at mid", value=net, ok=net > 0),
        dict(n=2, name="Net > $0 at high friction", value=hn, ok=hn > 0),
        dict(n=3, name="Both halves net > $0 (2010-06..2015-12 / 2016-01..2021-12)", value=(h1, h2), ok=h1 > 0 and h2 > 0),
        dict(n=4, name="Drop-top-1 and drop-top-2 years still > $0", value=(d1, d2), ok=d1 > 0 and d2 > 0),
        dict(n=5, name="Bootstrap by year (2,000): net > 0 in >= 95%", value=boot, ok=bool(boot >= 0.95)),
        dict(n=6, name="Beats C1 on net and on net / sd of daily net", value=(net, c1net, r_h, r_c1), ok=bool(net > c1net and r_h > r_c1)),
        dict(n=7, name="Beats the p99 of C3 (random gating at the clone's take rate) on net", value=(net, c3_p99), ok=bool(net > c3_p99)),
        dict(n=8, name="No single year > 50% of net", value=share, ok=bool(share <= 0.5 and net > 0)),
        dict(n=9, name=">= 18 of 27 grid cells net > $0", value=n_grid_pos, ok=n_grid_pos >= 18),
        dict(n=10, name=">= 100 trades", value=n, ok=n >= 100),
    ]
    return rows


def verdict(rows: list[dict]) -> str:
    by = {r["n"]: r["ok"] for r in rows}
    if by[10] is False:
        return "NOT READ (fewer than 100 trades)"
    if by[6] is False or by[7] is False:
        return "FAIL (criterion 6 or 7 closes the study)"
    if all(by.values()):
        return "PASS (ten of ten)"
    if [k for k, v in by.items() if not v] == [8]:
        return "PASS except concentration (criterion 8 only; holdout not spent; forward paper is Ben's choice)"
    return "FAIL"


# ------------------------------------------------------------------------------------------------ H1 / V-BENLAB
def _subset_percentile(nets: np.ndarray, k: int, total: float, draws: int, rng: np.random.Generator) -> dict:
    if k == 0 or k > len(nets):
        return dict(k=k, pctile=float("nan"), p5=float("nan"), p50=float("nan"), p95=float("nan"), total=total)
    idx = np.argsort(rng.random((draws, len(nets))), axis=1)[:, :k]
    s = nets[idx].sum(axis=1)
    return dict(k=k, total=float(total), pctile=float((s < total).mean() + 0.5 * (s == total).mean()),
                p5=float(np.percentile(s, 5)), p50=float(np.percentile(s, 50)), p95=float(np.percentile(s, 95)))


def h1(lab: pd.DataFrame, net_by_id: dict[str, float], rules: list[dict], draws: int = DRAWS_H1) -> dict:
    """Sec 9.2: Ben's takes and the clone's (R) picks on the unique labelled candidates, each as the v1 trade recorded."""
    missing = [c for c in lab["candidate_id"] if c not in net_by_id]
    if missing:
        raise OutcomeRefused(f"{len(missing)} labelled candidates have no v1 trade: {missing[:3]}")
    nets = np.array([net_by_id[c] for c in lab["candidate_id"]], float)
    y = lab["y"].to_numpy(int)
    clone_take = CL.predict_rules(rules, lab).astype(int)
    out = dict(n=len(lab), all_net=float(nets.sum()), all_avg=float(nets.mean()))
    for name, sel, seedw in (("ben", y == 1, b"ben"), ("clone", clone_take == 1, b"clone")):
        rng = np.random.default_rng([crc32(b"W15-0050-h1"), crc32(seedw)])
        r = _subset_percentile(nets, int(sel.sum()), float(nets[sel].sum()), draws, rng)
        r.update(avg_take=float(nets[sel].mean()) if sel.any() else float("nan"),
                 avg_skip=float(nets[~sel].mean()) if (~sel).any() else float("nan"),
                 skip_total=float(nets[~sel].sum()))
        out[name] = r
    both = (y == 1) & (clone_take == 1)
    out["both_take"] = int(both.sum())
    out["both_take_net"] = float(nets[both].sum())
    out["ben_only"] = int(((y == 1) & (clone_take == 0)).sum())
    out["ben_only_net"] = float(nets[(y == 1) & (clone_take == 0)].sum())
    out["clone_only"] = int(((y == 0) & (clone_take == 1)).sum())
    out["clone_only_net"] = float(nets[(y == 0) & (clone_take == 1)].sum())
    return out


# ------------------------------------------------------------------------------------------------ the study
def _bundle(trades, fr) -> dict:
    return {f"{sym}_{lv}": summarize(trades, fr, sym, lv) for sym in ("MCL", "CL") for lv in S1.LEVELS}


def _entry_ids(trades, fr) -> list[str]:
    return [fr.ny[t.entry_j].tz_localize(None).strftime("%Y-%m-%d %H:%M:%S") for t in trades]


def famous_mask(entry_t: pd.Series) -> pd.Series:
    m = pd.Series(False, index=entry_t.index)
    for a, b in S.FAMOUS_WINDOWS:
        m |= (entry_t >= pd.Timestamp(a)) & (entry_t < pd.Timestamp(b) + pd.Timedelta(days=1))
    return m


def run_study(fr, ind, cd, frozen: dict, gb, man_ids: set[str], lab: pd.DataFrame | None, *, draws: int = DRAWS_C3,
              h1_draws: int = DRAWS_H1, log=print) -> dict:
    p = S1.BASE
    res: dict = {}
    gate_r = G.CloneGate(cd, "R", frozen)
    # ---- ungated v1, the headline gated run, C1 ----
    tr0, cnt0 = E.simulate(fr, ind, p)
    trH, cH = G.simulate_gated(fr, ind, p, gate_r)
    V0, VH = _bundle(tr0, fr), _bundle(trH, fr)
    log(f"headline run: asked {cH['would_be']} times, took {cH['takes']}, skipped {cH['skips']}, trades {len(trH)}")
    c1_tr, _ = CT.donchian_c1(fr, ind)
    C1 = _bundle(c1_tr, fr)
    ids_H = _entry_ids(trH, fr)
    res.update(tr0=tr0, cnt0=cnt0, trH=trH, cH=cH, V0=V0, VH=VH, C1=C1, c1_n=len(c1_tr),
               pool_overlap=sum(i in man_ids for i in ids_H), pool_new=sum(i not in man_ids for i in ids_H))
    # ---- C3: random gating at the clone's own take rate by year ----
    years = np.asarray(fr.ny.year)
    p_y = {y: cH["take_year"].get(y, 0) / wb for y, wb in cH["wb_year"].items()}
    default_p = cH["takes"] / max(cH["would_be"], 1)
    N = len(trH)
    c3 = np.empty(draws)
    c3_n = np.empty(draws)
    for d in range(draws):
        rng = np.random.default_rng([crc32(str(d).encode()), crc32(b"CL-clone"), N])
        tr, _ = G.simulate_gated(fr, ind, p, G.RandomGate(p_y, years, rng, default_p))
        c3[d], c3_n[d] = G.net_mid_1mcl(tr), len(tr)
    base_net = VH["MCL_mid"]["net"]
    res.update(p_y=p_y, c3=dict(p5=float(np.percentile(c3, 5)), p50=float(np.percentile(c3, 50)), p95=float(np.percentile(c3, 95)),
                                p99=float(np.percentile(c3, 99)), mean_trades=float(c3_n.mean()), draws=draws,
                                rank=float((c3 < base_net).mean())))
    # ---- grid ----
    grid = []
    for L in S1.GRID_E1:
        for a in S1.GRID_P1:
            for sl in S1.GRID_STOP:
                tr, _ = G.simulate_gated(fr, ind, replace(p, e1_lookback=L, p1_arm=a, stop_lookback=sl), gate_r)
                grid.append(dict(e1=L, p1=a, stop=sl, n=len(tr), net=G.net_mid_1mcl(tr)))
    n_pos = sum(g["net"] > 0 for g in grid)
    res.update(grid=grid, n_pos=n_pos)
    # ---- criteria ----
    crit = evaluate(VH["MCL_mid"]["df"], VH["MCL_high"]["df"], c1_mid=C1["MCL_mid"]["df"], c3_p99=res["c3"]["p99"], n_grid_pos=n_pos)
    res.update(crit=crit, verdict=verdict(crit))
    # ---- variants (reported, never selectable) ----
    var = {}
    gate_m = G.CloneGate(cd, "M", frozen)
    tr, c = G.simulate_gated(fr, ind, p, gate_m)
    var["V-OTHER (M logistic)"] = dict(b=_bundle(tr, fr), c=c, trades=tr)
    if gb is not None:
        tr, c = G.simulate_gated(fr, ind, p, G.CloneGate(cd, "M-GB", frozen, gb))
        var["M-GB (boosting)"] = dict(b=_bundle(tr, fr), c=c, trades=tr)
    tr, c = G.simulate_gated(fr, ind, p, gate_r, exits="v2")
    var["V-EXIT2 (R gate, v2 exits)"] = dict(b=_bundle(tr, fr), c=c, trades=tr)
    dmid, dhigh = VH["MCL_mid"]["df"], VH["MCL_high"]["df"]
    keep_m, keep_h = ~famous_mask(dmid["entry_t"]), ~famous_mask(dhigh["entry_t"])
    var["V-NOFAMOUS (R gate)"] = dict(n=int(keep_m.sum()), excluded=int((~keep_m).sum()), net_mid=float(dmid.loc[keep_m, "net"].sum()),
                                      net_high=float(dhigh.loc[keep_h, "net"].sum()),
                                      gross=float(dmid.loc[keep_m, "gross"].sum()), cost=float(dmid.loc[keep_m, "cost"].sum()),
                                      ungated_n=int((~famous_mask(V0["MCL_mid"]["df"]["entry_t"])).sum()),
                                      ungated_net=float(V0["MCL_mid"]["df"].loc[~famous_mask(V0["MCL_mid"]["df"]["entry_t"]), "net"].sum()))
    res["var"] = var
    # ---- H1 / V-BENLAB ----
    if lab is not None:
        d0 = V0["MCL_mid"]["df"]
        net_by_id = dict(zip(d0["entry_t"].dt.strftime("%Y-%m-%d %H:%M:%S"), d0["net"]))
        res["h1"] = h1(lab, net_by_id, frozen["R"]["rules"], h1_draws)
    return res


# ------------------------------------------------------------------------------------------------ report
def _fmt(v):
    if isinstance(v, tuple):
        return "(" + ", ".join(money(x) if abs(x) > 5 else f"{x:.2f}" for x in v) + ")"
    if isinstance(v, (float, np.floating)):
        return f"{v:.3f}" if abs(v) < 5 else money(v)
    return str(v)


def _row(name, b, extra="") -> str:
    m = b["MCL_mid"]
    return (f"  {name:<30s} {m['n']:5d}  {m['wins']}/{m['losses']:<5}  {money(m['gross']):>10}  {money(m['cost']):>9}  {money(m['net']):>10}  "
            f"{money(b['MCL_low']['net']):>10}  {money(b['MCL_high']['net']):>10}  {money(b['CL_mid']['net']):>11}  {extra}")


def report(r: dict, g6res: dict, prov: dict) -> str:
    VH, V0, C1 = r["VH"], r["V0"], r["C1"]
    m, h, lo, cl = VH["MCL_mid"], VH["MCL_high"], VH["MCL_low"], VH["CL_mid"]
    cH, c3 = r["cH"], r["c3"]
    L = ["W15-0050 CHARTMARK-CLONE -- the one outcome run: frozen clone R gating CHARTMARK-v1 (long), CL 1H, training "
         f"{FIRST} .. {LAST}, run {prov['run_utc']}",
         "Registered: REGISTERED_chartmark_clone.md sec 9-11 + Amendment 3 (PRE-RUN). Costs IBKR (v1 Amendment A.3). 1 MCL headline, mid friction. Negatives in brackets.",
         "", f"VERDICT: {r['verdict']}", "",
         "PROVENANCE: repo HEAD " + prov["head"][:12] + f" | frozen clone sha256 {prov['frozen_sha'][:16]}.. | labels {prov['labels_sha'][:16]}.. | "
         f"registration doc sha256 {prov['reg_sha'][:16]}.. | code gated.py {prov['gated_sha'][:16]}.. outcome.py {prov['outcome_sha'][:16]}..", "",
         "G6 GATE PARITY (counts only, before any outcome): "
         f"v1 {g6res['v1_trades']} trades; always-take {g6res['always_take_trades']} trades, identical to v1 {g6res['always_take_identical']}, "
         f"fill times = manifest {g6res['always_take_matches_manifest']}; always-skip {g6res['always_skip_trades']} trades -> {'PASS' if g6res['ok'] else 'FAIL'}", ""]
    L += ["HEADLINE (frozen R gate on v1, 1 MCL, mid):",
          f"  gate asked {cH['would_be']} times (every touch of a working buy-stop), took {cH['takes']} ({pct(cH['takes'] / max(cH['would_be'], 1))}), skipped {cH['skips']}",
          f"  trades {m['n']}  wins {m['wins']}  losses {m['losses']}  gross {money(m['gross'])}  costs {money(m['cost'])}  net {money(m['net'])}",
          f"  avg win {money(m['avg_win'])}  avg loss {money(m['avg_loss'])}  largest loss {money(m['largest_loss'])}  worst losing run {m['streak']}  max drawdown {money(m['dd'])}",
          f"  net low / mid / high friction: {money(lo['net'])} / {money(m['net'])} / {money(h['net'])}   1 CL net low / mid / high: "
          f"{money(VH['CL_low']['net'])} / {money(cl['net'])} / {money(VH['CL_high']['net'])}",
          f"  halves (calendar) {money(float(m['df'].loc[m['df']['year'] <= 2015, 'net'].sum()))} / {money(float(m['df'].loc[m['df']['year'] >= 2016, 'net'].sum()))}",
          f"  trades that are among the 2,670 labelled v1 fills {r['pool_overlap']}; new (path-dependent) fills {r['pool_new']}", ""]
    L += ["SEC 10 CRITERIA (headline):"]
    for c in r["crit"]:
        ok = "PASS" if c["ok"] else "FAIL"
        L.append(f"  {c['n']:2d}. {c['name']:<72s} {ok:5s} {_fmt(c['value'])}")
    L += ["", "HEADLINE per year (1 MCL, mid): year / asked / took / skipped / trades / W-L / gross / costs / net",
          f"  {'year':>5} {'asked':>6} {'took':>5} {'skip':>5} {'trades':>6} {'W/L':>9} {'gross':>10} {'cost':>9} {'net':>10}"]
    df = m["df"]
    for y in sorted(set(cH["wb_year"]) | set(df["year"])):
        g = df[df["year"] == y]
        wb, tk = cH["wb_year"].get(y, 0), cH["take_year"].get(y, 0)
        L.append(f"  {y:>5} {wb:>6} {tk:>5} {wb - tk:>5} {len(g):>6} {int((g.net > 0).sum()):>4}/{int((g.net < 0).sum()):<4} "
                 f"{money(g.gross.sum()):>10} {money(g.cost.sum()):>9} {money(g.net.sum()):>10}")
    L += ["", "EXITS BY TYPE (headline): " + str(exits_of(r["trH"])),
          f"Reached P1 {sum(t.phase >= 1 for t in r['trH'])}/{m['n']}  P2 {sum(t.phase >= 2 for t in r['trH'])}/{m['n']}", ""]
    L += ["COMPARATORS (1 MCL, mid unless stated)      trades W/L  gross  costs  net  net(low)  net(high)  1 CL net(mid)",
          _row("CLONE R gate (headline)", VH),
          _row("CHARTMARK-v1 ungated", V0),
          _row("C1 Donchian 20/10 long", C1),
          f"  C3 random gating at the clone's take rate by year ({c3['draws']} draws, mean {c3['mean_trades']:.0f} trades): "
          f"p5 {money(c3['p5'])}  p50 {money(c3['p50'])}  p95 {money(c3['p95'])}  p99 {money(c3['p99'])}; the headline beats {100 * c3['rank']:.1f}% of draws",
          "  per-year take probability used by C3: " + ", ".join(f"{y}: {pct(v, 0)}" for y, v in sorted(r["p_y"].items())), ""]
    if "h1" in r:
        x = r["h1"]
        L += ["H1 / V-BENLAB -- labelled candidates only (reported, no pass/fail; each candidate = the v1 trade recorded, 1 MCL mid):",
              f"  all {x['n']} labelled candidates: net {money(x['all_net'])}, average {money(x['all_avg'])} per trade",
              f"  Ben's takes   : {x['ben']['k']} trades, net {money(x['ben']['total'])}, average {money(x['ben']['avg_take'])}; his skips average {money(x['ben']['avg_skip'])} "
              f"(net {money(x['ben']['skip_total'])}); random same-size subsets (10,000) p5 {money(x['ben']['p5'])} p50 {money(x['ben']['p50'])} p95 {money(x['ben']['p95'])}; Ben's takes sit at the {100 * x['ben']['pctile']:.1f}th percentile",
              f"  R clone picks : {x['clone']['k']} trades, net {money(x['clone']['total'])}, average {money(x['clone']['avg_take'])}; its skips average {money(x['clone']['avg_skip'])} "
              f"(net {money(x['clone']['skip_total'])}); random p5 {money(x['clone']['p5'])} p50 {money(x['clone']['p50'])} p95 {money(x['clone']['p95'])}; clone picks sit at the {100 * x['clone']['pctile']:.1f}th percentile (R was fitted on these labels: in-sample)",
              f"  overlap: both took {x['both_take']} (net {money(x['both_take_net'])}); Ben only {x['ben_only']} (net {money(x['ben_only_net'])}); clone only {x['clone_only']} (net {money(x['clone_only_net'])})", ""]
    L += ["VARIANTS (reported, never ranked, never headline; 1 MCL):  trades W/L gross costs net(mid) net(low) net(high) 1 CL net(mid)"]
    for k, v in r["var"].items():
        if "b" in v:
            L.append(_row(k, v["b"], f"asked {v['c']['would_be']} took {v['c']['takes']}  exits {exits_of(v['trades'])}"))
        else:
            L.append(f"  {k:<30s} {v['n']:5d} trades (excluded {v['excluded']})  gross {money(v['gross'])}  costs {money(v['cost'])}  net(mid) {money(v['net_mid'])}  net(high) {money(v['net_high'])}"
                     f"   ungated v1 on the same exclusion: {v['ungated_n']} trades, net {money(v['ungated_net'])}")
    if "M-GB (boosting)" not in r["var"]:
        L.append("  M-GB (boosting)                NOT RUN: the refit did not reproduce the frozen prediction hash in this environment")
    L += ["", f"NEIGHBOUR GRID (27 cells, frozen R gate, unranked): {r['n_pos']} of 27 net > $0 at mid.",
          "  cells (E1 lookback, P1 arm, stop lookback -> trades, net):"]
    for g in r["grid"]:
        L.append(f"   E1={g['e1']} P1={g['p1']:<4} S={g['stop']} -> {g['n']:5d}  {money(g['net'])}")
    n = len(df)
    pick = [int(i) for i in np.linspace(0, n - 1, min(20, n))] if n else []
    L += ["", "SAMPLE OF 20 REAL TRADES (headline, evenly spaced in time; 1 MCL, mid):",
          f"  {'entry':<17} {'exit':<17} {'entry px':>9} {'exit px':>9} {'reason':<8} {'net':>9}"]
    for i in pick:
        t = df.iloc[i]
        L.append(f"  {t.entry_t:%Y-%m-%d %H:%M}  {t.exit_t:%Y-%m-%d %H:%M}  {t.entry_px:>9.2f} {t.exit_px:>9.2f} {t.exit_reason:<8} {money(t.net):>9}")
    L += ["", "CAVEATS: 1H OHLC cannot show the path inside a bar. The gate is asked at every touch of a working buy-stop, so a skipped order stays "
          "working (until v1's own cancel/timeout) and is asked again at the next touch; the labels only ever showed first touches. "
          "The gated run creates fills that were never labelled. C3 trades are produced by the same gated engine with a random gate. "
          "The labelled-candidate comparison (H1/V-BENLAB) is in-sample for the clone. Nothing here spends the holdout."]
    return "\n".join(L) + "\n"


def _js(x):
    if isinstance(x, (tuple, list)):
        return [_js(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _js(v) for k, v in x.items()}
    if isinstance(x, (np.floating, float)):
        return float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def payload(r: dict, g6res: dict, prov: dict) -> dict:
    def sm(b):
        return {k: {q: _js(v[q]) for q in ("n", "wins", "losses", "gross", "cost", "net", "avg_win", "avg_loss", "largest_loss",
                                           "streak", "dd", "h1", "h2", "year_net")} for k, v in b.items()}
    out = dict(provenance=prov, g6=_js(g6res), verdict=r["verdict"], criteria=[{**c, "value": _js(c["value"])} for c in r["crit"]],
               headline=sm(r["VH"]), ungated=sm(r["V0"]), c1=sm(r["C1"]), c3=_js(r["c3"]), p_y=_js(r["p_y"]),
               gate=dict(asked=r["cH"]["would_be"], takes=r["cH"]["takes"], skips=r["cH"]["skips"],
                         wb_year=_js(r["cH"]["wb_year"]), take_year=_js(r["cH"]["take_year"])),
               pool_overlap=r["pool_overlap"], pool_new=r["pool_new"], exits=exits_of(r["trH"]),
               grid=_js(r["grid"]), n_pos=r["n_pos"], h1=_js(r.get("h1")),
               variants={k: ({"b": sm(v["b"]), "asked": v["c"]["would_be"], "takes": v["c"]["takes"], "exits": exits_of(v["trades"])}
                             if "b" in v else _js(v)) for k, v in r["var"].items()})
    return out


# ------------------------------------------------------------------------------------------------ ledger lock
def _ledger_write(out_dir: Path, led: dict) -> None:
    (Path(out_dir) / S.LEDGER_FILE).write_text(json.dumps(led, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def start_lock(out_dir: Path, led: dict, retry: bool) -> dict:
    """One run only: refuse when the ledger says the run already started (or finished); a retry after a crash is recorded."""
    if led.get("outcome_run_done"):
        raise OutcomeRefused("the ledger says the outcome run is done: it is never run twice.")
    if led.get("outcome_run_started_utc") and not retry:
        raise OutcomeRefused(f"the ledger says the outcome run started {led['outcome_run_started_utc']}: refusing a second run "
                             "(use --retry-after-crash only if it crashed before any result was written).")
    if retry:
        if led.get("outcome_run_started_utc") is None:
            raise OutcomeRefused("nothing to retry: the run never started")
        led.setdefault("outcome_run_retries", []).append(_now())
    led["outcome_run_started_utc"] = led.get("outcome_run_started_utc") or _now()
    _ledger_write(out_dir, led)
    return led


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CHARTMARK-CLONE sub 5: gate G6 and the one outcome run")
    ap.add_argument("--out", default=str(Path(r"D:\Trading\Claude outputs")))
    ap.add_argument("--cache", default=str(REPO / "var" / S.FRAME_CACHE_FILE))
    ap.add_argument("--g6", action="store_true", help="hashes + gate parity only (counts, no P&L)")
    ap.add_argument("--run", action="store_true", help="the one outcome run")
    ap.add_argument("--retry-after-crash", action="store_true")
    ap.add_argument("--draws", type=int, default=DRAWS_C3, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.g6 == a.run:
        ap.error("give exactly one of --g6 / --run")
    out_dir, cache = Path(a.out), Path(a.cache)
    ver = verify(out_dir, cache)
    for c in ver["checks"]:
        print(f"  [{'ok' if c['ok'] else 'XX'}] {c['check']}")
    fr = ver["frame"]
    ind = indicators(fr)
    man = pd.read_csv(out_dir / S.MANIFEST_FILE, dtype={"candidate_id": str, "decision_t": str})
    g6res = g6(fr, ind, set(man["candidate_id"]))
    if not g6res["ok"]:
        raise OutcomeRefused("G6 failed: the gated engine does not reproduce v1")
    if a.g6:
        return 0
    if a.draws != DRAWS_C3:
        raise OutcomeRefused("the draw count is registered (1,000); no override in the real run")
    led = start_lock(out_dir, ver["ledger"], a.retry_after_crash)      # recorded BEFORE any outcome number exists
    fz = ver["frozen"]
    cd = build_chart_data(fr)
    ld = FIT.load_labelled(out_dir, cache)
    gb, gb_ok = refit_gb(fz, out_dir)
    print(f"M-GB refit reproduces the frozen hash: {gb_ok}")
    res = run_study(fr, ind, cd, fz, gb, set(man["candidate_id"]), ld["df"], draws=DRAWS_C3, h1_draws=DRAWS_H1)
    prov = dict(run_utc=_now(), head=ver["head"], frozen_sha=led["clone_frozen_sha256"], labels_sha=led["labels_sha256"],
                reg_sha=LG.sha256_file(REG_DOC), gated_sha=LG.sha256_file(Path(__file__).with_name("gated.py")),
                outcome_sha=LG.sha256_file(Path(__file__)), library_versions=FIT._versions())
    text = report(res, g6res, prov)
    (out_dir / f"{OUT_STEM}.txt").write_text(text, encoding="utf-8")
    (out_dir / f"{OUT_STEM}.json").write_text(json.dumps(payload(res, g6res, prov), indent=1, default=str), encoding="utf-8")
    res["VH"]["MCL_mid"]["df"].to_csv(out_dir / f"{OUT_STEM}_trades_headline.csv", index=False)
    led = LG.read_ledger(out_dir)
    led.update(outcome_run_done=True, outcome_run_utc=prov["run_utc"], outcome_verdict=res["verdict"],
               outcome_report_sha256=LG.sha256_file(out_dir / f"{OUT_STEM}.txt"))
    _ledger_write(out_dir, led)
    print(text)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OutcomeRefused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        raise SystemExit(2)
