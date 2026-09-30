"""G2 -- OTF-G v1 count-only pre-flight (REGISTERED_otf_gate.md sec 5). No P&L is loaded.

H-A reads market, spec, share, sizing, equity, direction, entry_date, entry_j from the host books (never a
gross / net / exit column: books.read_books(with_pnl=False)). H-B reads B1's entry times and sides only
(books.b1_entry never walks a stop or target). Prints the state census and kept / removed counts per host x
market x direction x year, plus the G4/G6 data checks. Stop rule: fewer than 60 kept H-A trades AND fewer than
150 kept H-B trades -> STOP, back to Ben before any P&L is read.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.otf_gate import gate as G
from strategy.otf_gate import otf
from strategy.otf_gate import spec as S


def sha256(path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------ census
def census(stack: otf.Stack) -> dict:
    """Per timeframe: share of bars UP / DOWN / BAL, mean run length (bars) of each, and the shares by year."""
    out = {}
    for name, tf in (("M", stack.M), ("W", stack.W), ("D", stack.D)):
        st = tf.state
        n = len(st)
        share = {lab: float((st == code).mean()) if n else float("nan")
                 for lab, code in (("UP", S.UP), ("DOWN", S.DOWN), ("BAL", S.BAL))}
        runs = {"UP": [], "DOWN": [], "BAL": []}
        if n:
            start = 0
            for i in range(1, n + 1):
                if i == n or st[i] != st[start]:
                    runs[{S.UP: "UP", S.DOWN: "DOWN", S.BAL: "BAL"}[int(st[start])]].append(i - start)
                    start = i
        mean_run = {k: (float(np.mean(v)) if v else float("nan")) for k, v in runs.items()}
        yrs = pd.DatetimeIndex(tf.bars["last_date"]).year
        by_year = {}
        for y in sorted(set(yrs)):
            m = yrs == y
            by_year[int(y)] = {lab: float((st[m] == code).mean())
                               for lab, code in (("UP", S.UP), ("DOWN", S.DOWN), ("BAL", S.BAL))}
        out[name] = {"bars": int(n), "share": share, "mean_run": mean_run, "by_year": by_year}
    return out


# ------------------------------------------------------------------ joins
def _join(trades: pd.DataFrame, stacks: dict, date_col: str, market_col: str = "market",
          stacks_dalton: dict | None = None) -> pd.DataFrame:
    """Add d, w, m (+ naive) and every variant's keep-flag to each trade. `trades` has market, direction, date_col."""
    parts = []
    for mk, g in trades.groupby(market_col, sort=False):
        x = g.join(stacks[mk].states_at(g[date_col]).set_axis(g.index))
        sl = stacks[mk].states_at(g[date_col], live=True).set_axis(g.index)
        x["ld"], x["lw"], x["lm"] = sl["d"], sl["w"], sl["m"]
        if stacks_dalton is not None:
            sd = stacks_dalton[mk].states_at(g[date_col]).set_axis(g.index)
            x["dd"], x["dw"], x["dm"] = sd["d"], sd["w"], sd["m"]
        parts.append(x)
    x = pd.concat(parts).sort_index() if parts else trades.copy()
    if not len(x):
        return x
    sgn = x["direction"].to_numpy()
    x["keep"] = G.keep_mask(x, sgn, "strict")
    x["reason"] = G.removal_reason(x, sgn)
    for v in ("soft", "day_week", "opposite", "naive"):
        x[f"keep_{v}"] = G.keep_mask(x, sgn, v)
    x["keep_live"] = G.keep_mask(x.assign(d=x["ld"], w=x["lw"], m=x["lm"]), sgn, "strict")
    if stacks_dalton is not None:
        x["keep_dalton"] = G.keep_mask(x.assign(d=x["dd"], w=x["dw"], m=x["dm"]), sgn, "strict")
    return x


def _counts(x: pd.DataFrame, date_col: str) -> pd.DataFrame:
    if not len(x):
        return pd.DataFrame(columns=["market", "direction", "year", "n", "kept"])
    y = pd.DatetimeIndex(x[date_col]).year
    g = x.assign(year=y).groupby(["market", "direction", "year"])
    return g.agg(n=("keep", "size"), kept=("keep", "sum")).reset_index()


VARIANT_COLS = ("keep_soft", "keep_day_week", "keep_live", "keep_dalton", "keep_naive", "keep_opposite")


def host_report(x: pd.DataFrame, date_col: str, min_kept: int) -> dict:
    kept = int(x["keep"].sum()) if len(x) else 0
    return {"trades": int(len(x)), "kept": kept, "kept_share": (kept / len(x)) if len(x) else float("nan"),
            "min_kept": min_kept, "not_read": kept < min_kept,
            "reasons": {r: int((x["reason"] == r).sum()) for r in G.REASONS} if len(x) else {},
            "by_market_direction": {f"{m}|{d}": [int(len(g)), int(g['keep'].sum())]
                                    for (m, d), g in x.groupby(["market", "direction"])} if len(x) else {},
            "variants": {c: int(x[c].sum()) for c in VARIANT_COLS if c in x.columns},
            "counts": _counts(x, date_col)}


# ------------------------------------------------------------------ H-A
def run_ha(books: pd.DataFrame, daily: dict, sessions: dict | None = None, expected_trades: int = S.HA_TRADES) -> dict:
    from strategy.otf_gate import books as BK
    from strategy.otf_gate.holdout import H as HOLD
    host = BK.host_a(books)
    BK.check_count(host, expected_trades)
    if sessions is not None:
        BK.check_convention(host, sessions)
    # every host entry must be a training day (G3)
    _, n_locked, _ = HOLD.split_dates("H-A", [d.strftime("%Y-%m-%d") for d in host["entry_date"]])
    if n_locked:
        raise SystemExit(f"REFUSED: {n_locked} H-A trades enter after the training end.")
    stacks = {m: otf.Stack(daily[m]) for m in sorted(host["market"].unique())}
    dalton = {m: otf.Stack(daily[m], rule="dalton") for m in stacks}
    x = _join(host, stacks, "entry_date", stacks_dalton=dalton)
    rep = host_report(x, "entry_date", S.MIN_KEPT_A)
    rep["census"] = {m: census(s) for m, s in stacks.items()}
    return rep


# ------------------------------------------------------------------ H-B
def run_hb(entries: dict, daily: dict, b1_counts: dict, checks: dict) -> dict:
    """entries: root -> DataFrame(date, market, direction, fill_time); daily: root -> rebuilt CME daily bars;
    checks: root -> {"sessions": session_check(...), "switches": DataFrame}."""
    from strategy.otf_gate.holdout import H as HOLD
    tr = pd.concat([e.assign(market=r) for r, e in entries.items() if len(e)]) if any(len(e) for e in entries.values()) \
        else pd.DataFrame(columns=["date", "market", "direction", "fill_time"])
    tr = tr.reset_index(drop=True)
    if len(tr):
        _, n_locked, _ = HOLD.split_dates("H-B", [d.strftime("%Y-%m-%d") for d in tr["date"]])
        if n_locked:
            raise SystemExit(f"REFUSED: {n_locked} H-B entries fall after the training end.")
    stacks = {r: otf.Stack(daily[r]) for r in daily}
    dalton = {r: otf.Stack(daily[r], rule="dalton") for r in daily}
    x = _join(tr, stacks, "date", stacks_dalton=dalton) if len(tr) else tr
    rep = host_report(x, "date", S.MIN_KEPT_B)
    rep["b1_counts"] = b1_counts
    rep["checks"] = checks
    rep["census"] = {r: census(s) for r, s in stacks.items()}
    rep["_stacks"] = stacks
    return rep


def agreement(stack_a: otf.Stack, stack_b: otf.Stack, dates) -> dict:
    """G6: share of dates on which two stacks give the same M/W/D triple (reported, not a stop)."""
    a, b = stack_a.states_at(dates), stack_b.states_at(dates)
    ok = ((a[["d", "w", "m"]] != S.UNDEF) & (b[["d", "w", "m"]] != S.UNDEF)).all(axis=1)
    out = {"dates": int(ok.sum())}
    for k in ("d", "w", "m"):
        out[k] = float((a.loc[ok, k] == b.loc[ok, k]).mean()) if ok.any() else float("nan")
    out["all"] = float(((a.loc[ok, ["d", "w", "m"]].to_numpy() == b.loc[ok, ["d", "w", "m"]].to_numpy()).all(axis=1)).mean()) if ok.any() else float("nan")
    return out


def stop(rep_a: dict, rep_b: dict) -> bool:
    return rep_a["kept"] < S.MIN_KEPT_A and rep_b["kept"] < S.MIN_KEPT_B


# ------------------------------------------------------------------ text
def _pct(x):
    return "  n/a " if x != x else f"{100 * x:5.1f}%"


def _census_text(title: str, cen: dict) -> list:
    L = [f"  {title}"]
    for tf in ("M", "W", "D"):
        c = cen[tf]
        L.append(f"    {tf}: {c['bars']:>5} bars   UP {_pct(c['share']['UP'])}  DOWN {_pct(c['share']['DOWN'])}  "
                 f"BAL {_pct(c['share']['BAL'])}   mean run (bars): UP {c['mean_run']['UP']:.1f}  "
                 f"DOWN {c['mean_run']['DOWN']:.1f}  BAL {c['mean_run']['BAL']:.1f}")
    return L


def _host_text(name: str, rep: dict) -> list:
    L = [f"{name}: {rep['trades']} host trades -> KEPT {rep['kept']} ({_pct(rep['kept_share'])})   "
         f"floor {rep['min_kept']}  -> " + ("BELOW THE FLOOR: NOT READ for this host" if rep["not_read"]
                                          else "at or above the floor")]
    L.append("  removed by reason (primary, first match): " + "   ".join(f"{k} {rep['reasons'].get(k, 0)}" for k in G.REASONS))
    L.append("  kept / trades by market|direction: " + "   ".join(
        f"{k}: {v[1]}/{v[0]}" for k, v in sorted(rep["by_market_direction"].items())))
    L.append("  COUNT-ONLY VARIANTS (unique trades kept; reported, never ranked): " + "   ".join(
        f"{k[5:]} {v}" for k, v in rep["variants"].items()))
    c = rep["counts"]
    if len(c):
        pv = c.pivot_table(index=["market", "direction"], columns="year", values="kept", fill_value=0, aggfunc="sum")
        pn = c.pivot_table(index=["market", "direction"], columns="year", values="n", fill_value=0, aggfunc="sum")
        L.append("  KEPT by market x direction x year (host trades in the table below):")
        L.append("    " + pv.assign(total=pv.sum(axis=1)).to_string().replace("\n", "\n    "))
        L.append("  HOST trades by market x direction x year:")
        L.append("    " + pn.assign(total=pn.sum(axis=1)).to_string().replace("\n", "\n    "))
    return L


def render(rep_a: dict, rep_b: dict, *, agree=None, scoped: bool = False) -> str:
    L = ["OTF-G v1 G2 PRE-FLIGHT -- REGISTERED_otf_gate.md sec 5 (W15-0025 sub 3/4)",
         "TRAINING SIDE ONLY, COUNTS ONLY: no gross / net / exit column is loaded; no outcome is computed."]
    if scoped:
        L.append("SCOPED RUN: NOT THE REGISTERED PRE-FLIGHT.")
    L.append("")
    stopped = stop(rep_a, rep_b)
    L.append(f"STOP RULE: kept H-A {rep_a['kept']} (< {S.MIN_KEPT_A}?) AND kept H-B {rep_b['kept']} (< {S.MIN_KEPT_B}?) -> "
             + ("BOTH BELOW -- STOP. Report to Ben; the counts are the finding. No P&L run." if stopped
                else "at least one host at or above its floor: the training run may proceed (Ben to say go)."))
    L.append("")
    L += _host_text("H-A  C1 Donchian 20/10 frac $22,129", rep_a)
    L.append("")
    L += _host_text("H-B  B1 ORB, ES + NQ (1 MES / 1 MNQ)", rep_b)
    L.append("")
    b = rep_b["b1_counts"]
    for r, c in b.items():
        L.append(f"  B1 {r}: sessions {c['sessions']}, skipped {c['skipped']}, no trigger {c['no_trigger']}, "
                 f"voided {c['voided']}, entries {c['entries']}")
    L.append("")
    L.append("G6 -- H-B DAILY BAR CHECK (rebuilt CME sessions vs XNYS trading days; missing > 1% in a year = STOP):")
    for r, ch in rep_b["checks"].items():
        sc = ch["sessions"]
        L.append(f"  {r}: {'STOP' if sc['stop'] else 'ok'}   extra CME-only days {sc['extra_cme_days']}   "
                 + "  ".join(f"{y}: {v['missing']}/{v['xnys_days']}" for y, v in sc["years"].items()))
        sw = ch["switches"]
        L.append(f"    roll switches: {len(sw)}; max minutes apart {float(sw['minutes'].max()) if len(sw) else 0:.0f}; "
                 f"all within {S.HB_MAX_SWITCH_MINUTES} min: {bool(sw['ok'].all()) if len(sw) else True}")
        if len(sw):
            L.append("    " + sw[["time_old", "time_new", "minutes", "gap"]].head(60).to_string(index=False).replace("\n", "\n    "))
    if agree:
        L.append("")
        L.append("G6 -- ES OTF state agreement, H-B rebuilt series vs H-A ES series (different day boundaries; reported, not a stop): "
                 f"{agree['dates']} common dates, daily {_pct(agree['d'])}, weekly {_pct(agree['w'])}, "
                 f"monthly {_pct(agree['m'])}, all three {_pct(agree['all'])}")
    L.append("")
    L.append("STATE CENSUS (claim check, not scored; Imre's 'balance ~ 70%' beside it):")
    for m, c in rep_a["census"].items():
        L += _census_text(f"H-A {m}", c)
    for r, c in rep_b["census"].items():
        L += _census_text(f"H-B {r}", c)
    return "\n".join(L) + "\n"


def clean(rep_a: dict, rep_b: dict, inputs: dict) -> dict:
    def strip(r):
        d = {k: v for k, v in r.items() if k not in ("counts", "census", "checks", "_stacks", "b1_counts")}
        d["counts"] = r["counts"].to_dict(orient="records")
        return d
    return {"kept_a": rep_a["kept"], "kept_b": rep_b["kept"], "stop": bool(stop(rep_a, rep_b)),
            "not_read_a": bool(rep_a["not_read"]), "not_read_b": bool(rep_b["not_read"]),
            "H-A": strip(rep_a), "H-B": strip(rep_b), "b1_counts": rep_b["b1_counts"], "inputs_sha256": inputs}
