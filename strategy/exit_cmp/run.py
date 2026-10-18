#!/usr/bin/env python3
"""EXIT-CMP: the ONE outcome run. W15-0053 sub 2 builds it; Ben runs it (sub 3). REGISTERED_exit_cmp.md sec 9-11.

    python -m strategy.exit_cmp.run [--retry-after-crash]

Training side only (2010-06 -> 2021-12). Refuses to start unless the pre-flight wrote the ledger, the registration / code / frame
still match it, and G2 parity passed; it records `outcome_started` before computing anything and refuses a second run.
Headline: FLAT, 1 MCL, IBKR mid, paired against B-STOP. 1 CL, low / high friction, HOLD, variants, slices and windows are
reported, never ranked, never headline. Nothing is ranked outside the sec 10 pass test."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from exitmgr import rules as R
from exitmgr import symbols as SY
from strategy.chartmark.data import indicators, load_training_frame
from strategy.exit_cmp import book as BKX
from strategy.exit_cmp import controls as CT
from strategy.exit_cmp import entries as EN
from strategy.exit_cmp import ledger as LG
from strategy.exit_cmp import score as SC
from strategy.exit_cmp import spec as S
from strategy.exit_cmp.walk import Study
from strategy.chartmark_clone.ledger import load_frame_cache
from strategy.futbt import runner_common as RC

SESSIONS = (("Asia/pre-London (02)", 2, 2), ("London (03-07)", 3, 7), ("US-AM (08-12)", 8, 12))


def money(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"(${abs(x):,.0f})" if x < 0 else f"${x:,.0f}"


def pct(x) -> str:
    return "n/a" if x is None or x != x else f"{100 * x:.1f}%"


def ben_takes(path: Path) -> set[str]:
    """Candidate ids Ben took (first label of each non-repeat candidate, UNDO'd decisions removed). Ids only."""
    df = pd.read_csv(path, dtype=str, usecols=["candidate_id", "label", "is_repeat", "seq"])
    undone = set(df.loc[df["label"] == "UNDO", "seq"])
    d = df[df["label"].isin(["TAKE", "SKIP"]) & (df["is_repeat"] == "0") & ~df["seq"].isin(undone)]
    first = d.drop_duplicates("candidate_id", keep="first")
    return set(first.loc[first["label"] == "TAKE", "candidate_id"])


class Book:
    """Trade frames cached by (rule, scenario, params, sym, level, qty)."""

    def __init__(self, st: Study):
        self.st, self._f = st, {}

    def frame(self, rid, scen, sym="MCL", level="mid", p=R.BASE, cap="default"):
        k = (rid, scen, p, sym, level, cap)
        if k not in self._f:
            ex = self.st.run(rid, scen, p, cap=cap)
            self._f[k] = BKX.trade_frame(self.st.fr, self.st.entries, ex, self.st.roll_cum, sym, level)
        return self._f[k]


def grid_cells(rid: str, bk: Book, base_net: pd.DataFrame) -> list[dict]:
    (d1, v1s), (d2, v2s) = S.GRIDS["X-ALERT-touch" if rid.startswith("X-ALERT") else rid]
    cells = []
    for v1, v2 in product(v1s, v2s):
        p = replace(S.BASE, **{d1: v1, d2: v2})
        D = float((bk.frame(rid, "FLAT", p=p)["net"].to_numpy() - base_net["net"].to_numpy()).sum())
        cells.append(dict(**{d1: v1, d2: v2}, D=D))
    return cells


def compute(st: Study, takes: set[str], log=print) -> dict:
    bk = Book(st)
    fr = st.fr
    entry_t = bk.frame(S.BASELINE, "FLAT")["entry_t"]
    res: dict = dict(rules={}, notes={})
    base = {sc: bk.frame(S.BASELINE, sc) for sc in S.SCENARIOS}
    base_high = bk.frame(S.BASELINE, "FLAT", level="high")
    all_ids = (S.BASELINE,) + S.SCORED + S.VARIANTS
    for rid in all_ids:
        r = res["rules"].setdefault(rid, {})
        for sc in S.SCENARIOS:
            r[sc] = {}
            for sym in ("MCL", "CL"):
                for lv in SY.LEVELS:
                    df = bk.frame(rid, sc, sym, lv)
                    s = SY.get(sym)
                    m = BKX.metrics(df, arm=S.BASE.ben_arm, point_usd=s.point_usd)
                    m["D"] = float(df["net"].sum() - bk.frame(S.BASELINE, sc, sym, lv)["net"].sum())
                    r[sc][f"{sym}-{lv}"] = m
        r["samples"] = BKX.sample_rows(bk.frame(rid, "FLAT"))
        ex = st.run(rid, "FLAT")
        r["triggers"] = {k: sum(k in x.fired for x in ex) for k in sorted({f for x in ex for f in x.fired})}
        r["stop_and_raise"] = int(sum(x.stop_and_raise_same_bar for x in ex))
    res["B-V1-HOLD"] = BKX.metrics(bk.frame(S.REFERENCE, "HOLD", cap=None), arm=S.BASE.ben_arm, point_usd=100.0)
    # ---- the pass test (FLAT, MCL, mid) ----
    for rid in S.SCORED:
        df_mid, df_high = bk.frame(rid, "FLAT"), bk.frame(rid, "FLAT", level="high")
        d_mid, d_high = SC.paired(df_mid, base["FLAT"]), SC.paired(df_high, base_high)
        ex = st.run(rid, "FLAT")
        ctl = CT.c_randx(st, rid, ex, "FLAT")
        cells = grid_cells(rid, bk, base["FLAT"])
        also = None
        if rid in S.GRID_ALSO:
            also = grid_cells(S.GRID_ALSO[rid], bk, base["FLAT"])
        crit = SC.criteria(rid, d_mid=d_mid, d_high=d_high, rule_net_mid=float(df_mid["net"].sum()), c_p99=ctl["p99"],
                           grid_positive=sum(c["D"] > 0 for c in cells), trigger_n=SC.trigger_count(rid, ex))
        res["rules"][rid]["test"] = dict(criteria=crit, control=ctl, grid=cells, grid_also=also,
                                         year_D=SC.year_d(d_mid), halves=SC.halves(d_mid))
        log(f"  {rid}: {crit['verdict']}")
    # ---- FLAT vs HOLD, slices, windows, sessions (reported) ----
    sl = {}
    ids = entry_t.dt.strftime("%Y-%m-%d %H:%M:%S")
    masks = {"Ben's takes": ids.isin(takes).to_numpy()}
    for name, (a, b) in S.WINDOWS.items():
        masks[name] = ((entry_t >= pd.Timestamp(a)) & (entry_t <= pd.Timestamp(b) + pd.Timedelta(days=1))).to_numpy()
    hrs = st.ind.hour[[x.e for x in st.entries]]
    for name, lo, hi in SESSIONS:
        masks[name] = (hrs >= lo) & (hrs <= hi)
    for name, m in masks.items():
        sl[name] = dict(n=int(m.sum()), rules={})
        for rid in all_ids:
            net = float(bk.frame(rid, "FLAT")["net"].to_numpy()[m].sum())
            bnet = float(base["FLAT"]["net"].to_numpy()[m].sum())
            sl[name]["rules"][rid] = dict(net=net, D=net - bnet)
    res["slices"] = sl
    res["takes_found"] = len(takes)
    res["s_over_emergency"] = int(sum((x.entry_px - x.s0) > S.EMERGENCY for x in st.entries))
    res["_book"] = bk
    return res


def render(res: dict, st: Study, led: dict, stamp: str) -> str:
    L = [f"{S.STUDY} -- OUTCOME RUN, training 2010-06 -> 2021-12 only (no holdout opened), {stamp}",
         f"entries: {len(st.entries)} CHARTMARK-v1 CL 1H long fills; ledger created {led['created_utc']}, git {led['git_commit'][:10]}; "
         f"registration sha256 {led['registration_sha256'][:16]}...",
         f"python {sys.version.split()[0]}, pandas {pd.__version__}, numpy {np.__version__}. Negative figures in brackets.", "",
         "HEADLINE = FLAT, 1 MCL, IBKR mid, paired against B-STOP. Everything else is reported, not ranked.", ""]
    L.append(f"{'rule':16s}{'trades':>7s}{'win/loss':>10s}{'gross':>11s}{'costs':>9s}{'net':>11s}{'D vs B-STOP':>13s}{'med bars':>9s}")
    for rid in (S.BASELINE,) + S.SCORED:
        m = res["rules"][rid]["FLAT"]["MCL-mid"]
        L.append(f"{rid:16s}{m['n']:7d}{str(m['wins']) + '/' + str(m['losses']):>10s}{money(m['gross']):>11s}{money(m['cost']):>9s}"
                 f"{money(m['net']):>11s}{money(m['D']):>13s}{m['median_bars']:9.1f}")
    L += ["", "== THE PASS TEST (sec 10), per rule set",
          "(Every rule set makes one entry and one exit per trade, so friction cancels in the paired D: criterion 2 can differ from "
          "criterion 1 only through roll sides.)", ""]
    for rid in S.SCORED:
        t = res["rules"][rid]["test"]
        c = t["criteria"]
        L.append(f"-- {rid}: {c['verdict']}   (trigger on {c['trigger_n']} of {len(st.entries)})")
        for n, name, val, ok in c["rows"]:
            if n == 5:
                v = pct(val)
            elif n == 7:
                v = f"{val[0]} supplies {pct(val[1])} of D"
            elif n in (3, 4, 6):
                v = f"{money(val[0])} | {money(val[1])}"
            else:
                v = money(val) if isinstance(val, float) else str(val)
            L.append(f"   {n}. {name}: {v}  ->  {'ok' if ok else ('NOT READ' if ok is None else 'FAIL')}")
        k = t["control"]
        L.append(f"   C-RANDX at its own holding times ({k['draws']} draws), net p5 {money(k['p5'])}  p50 {money(k['p50'])}  "
                 f"p95 {money(k['p95'])}  p99 {money(k['p99'])}; the rule's net {money(res['rules'][rid]['FLAT']['MCL-mid']['net'])}")
        L.append("   neighbour grid D by cell: " + "  ".join(
            "[" + ",".join(f"{v}" for kk, v in cell.items() if kk != "D") + f"] {money(cell['D'])}" for cell in t["grid"]))
        if t["grid_also"]:
            L.append("   (close variant, reported beside it): " + "  ".join(
                "[" + ",".join(f"{v}" for kk, v in cell.items() if kk != "D") + f"] {money(cell['D'])}" for cell in t["grid_also"]))
        L.append("   D by entry year: " + "  ".join(f"{y}:{money(v)}" for y, v in t["year_D"].items()))
        L.append("")
    L += ["== EVERY RULE SET (FLAT and HOLD), 1 MCL mid unless stated", ""]
    for rid in (S.BASELINE,) + S.SCORED + S.VARIANTS:
        for sc in S.SCENARIOS:
            r = res["rules"][rid][sc]
            m = r["MCL-mid"]
            L.append(f"[{rid} | {sc}] trades {m['n']}  wins {m['wins']} losses {m['losses']}  gross {money(m['gross'])}  costs "
                     f"{money(m['cost'])}  NET {money(m['net'])}  D {money(m['D'])}")
            L.append(f"    avg win {money(m['avg_win'])}  avg loss {money(m['avg_loss'])}  largest loss {money(m['largest_loss'])}  "
                     f"worst losing run {money(m['worst_run'])} ({m['loss_streak']} trades)  max drawdown {money(m['max_dd'])}  "
                     f"halves {money(m['half1'])} / {money(m['half2'])}")
            L.append(f"    exits {dict(sorted(m['exits'].items()))}  median bars {m['median_bars']:.1f}  give-back {m['give_back']} of "
                     f"{m['reached_arm']} that reached +$0.20 ({pct(m['give_back_share'])})  profit capture {pct(m['capture'])}  "
                     f"net/sd {m['net_per_sd']:.3f}  overlap {pct(m['overlap'])}  carried through a roll {m['rolls']}")
            L.append(f"    friction low / mid / high: {money(r['MCL-low']['net'])} / {money(r['MCL-mid']['net'])} / {money(r['MCL-high']['net'])}"
                     f"   D low / mid / high: {money(r['MCL-low']['D'])} / {money(r['MCL-mid']['D'])} / {money(r['MCL-high']['D'])}"
                     f"   1 CL mid: net {money(r['CL-mid']['net'])}  D {money(r['CL-mid']['D'])}")
        L.append(f"    triggers reached (FLAT): {res['rules'][rid]['triggers']}; exit bar also raised a ratchet / trail, stop counted first: "
                 f"{res['rules'][rid]['stop_and_raise']}")
        L.append("")
    v = res["B-V1-HOLD"]
    L += [f"B-V1 (parity reference, HOLD, v1 exits unchanged, 1 MCL mid): {v['n']} trades, net {money(v['net'])}", "",
          "== FLAT vs HOLD, paired (HOLD net minus FLAT net, 1 MCL mid)"]
    for rid in (S.BASELINE,) + S.SCORED:
        a, b = res["rules"][rid]["FLAT"]["MCL-mid"], res["rules"][rid]["HOLD"]["MCL-mid"]
        L.append(f"  {rid:16s} FLAT {money(a['net']):>10s}  HOLD {money(b['net']):>10s}  HOLD-FLAT {money(b['net'] - a['net']):>10s}   "
                 f"largest loss {money(a['largest_loss'])} / {money(b['largest_loss'])}   max drawdown {money(a['max_dd'])} / {money(b['max_dd'])}")
    L += ["", f"== SLICES AND WINDOWS (FLAT, 1 MCL mid; reported, not graded). Ben's takes found in the label file: "
              f"{res['takes_found']} (registered {S.BEN_TAKES_REGISTERED})"]
    for name, sl in res["slices"].items():
        L.append(f"  {name} ({sl['n']} entries): " + "  ".join(
            f"{rid} {money(x['net'])} (D {money(x['D'])})" for rid, x in sl["rules"].items() if rid in (S.BASELINE,) + S.SCORED))
    L += ["", f"entries whose S distance exceeds the ${S.EMERGENCY:.2f} emergency distance: {res['s_over_emergency']}",
          "", "== 20 REAL TRADES per rule set (FLAT, 1 MCL mid): entry / exit time and price, net"]
    for rid in (S.BASELINE,) + S.SCORED:
        L.append(f"-- {rid}")
        for s in res["rules"][rid]["samples"]:
            L.append(f"   {s['entry_t']} @ {s['entry_px']:.2f}  ->  {s['exit_t']} @ {s['exit_px']:.2f}  {s['reason']:8s} {money(s['net'])}")
    L += ["", "Registered NOT to be done: changing any threshold after this result; promoting a variant or a grid cell; quoting gross, a "
              "variant, the slice or one year as the headline; mining these trades for a new exit rule. Out-of-sample evidence is sub 5."]
    return "\n".join(L) + "\n"


def to_json(res: dict) -> dict:
    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items() if not str(k).startswith("_")}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        return o
    return clean(res)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("EXIT-CMP outcome run (one run)")
    ap.add_argument("--retry-after-crash", action="store_true")
    ap.add_argument("--labels")
    ap.add_argument("--frame-cache", help="load the training frame from this .npz instead of the archive")
    a = ap.parse_args(argv)
    out = Path(a.out)
    fr = load_frame_cache(Path(a.frame_cache)) if a.frame_cache else load_training_frame(RC.archive_path(a.archive))
    LG.verify(out, fr)
    ind = indicators(fr)
    entries = EN.entry_set(fr, ind)
    EN.check_registered(fr, entries)
    st = Study(fr, ind, entries)
    labels = Path(a.labels) if a.labels else out / S.LABELS_FILE
    takes = ben_takes(labels) if labels.exists() else set()
    led = LG.begin_outcome(out, a.retry_after_crash)       # the one-run lock, BEFORE any outcome exists
    print("outcome run started (ledger locked)")
    res = compute(st, takes)
    stamp = date.today().strftime("%Y%m%d")
    text = render(res, st, led, stamp)
    base = out / f"w15_0053_exit_cmp_outcome_{stamp}"
    txt, js, tr = base.with_suffix(".txt"), Path(str(base) + ".json"), Path(str(base) + "_trades.csv")
    txt.write_text(text, encoding="utf-8")
    js.write_text(json.dumps(to_json(res), indent=1, default=str), encoding="utf-8")
    bk: Book = res["_book"]
    rows = []
    for rid in (S.BASELINE,) + S.SCORED + S.VARIANTS:
        for sc in S.SCENARIOS:
            rows.append(bk.frame(rid, sc).drop(columns=["fired"]).assign(rule=rid, scenario=sc))
    pd.concat(rows).to_csv(tr, index=False, lineterminator="\n", encoding="utf-8")
    LG.finish_outcome(out, [txt.name, js.name, tr.name])
    print(text)
    print(f"written: {txt}\n         {js}\n         {tr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
