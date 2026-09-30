"""MFLAG-v1 training run (REGISTERED_macro_flag_v1.md sec 3-4). Reads the host books WITH P&L, so it only
runs after the count-only pre-flight cleared the 60-trade floor (run.py enforces that)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.macro_flag import books as BK
from strategy.macro_flag import controls as K
from strategy.macro_flag import flag as F
from strategy.macro_flag import spec as S


def money(x: float, d: int = 0) -> str:
    return f"(${abs(x):,.{d}f})" if x < 0 and round(abs(x), d) > 0 else f"${abs(x):,.{d}f}"


def _nets(h):
    return h[list(BK.PNL_COLS)].to_numpy(dtype=float)


def _evaluate(h, keys, sessions, calendar, cells, window, weight=1.0, draws=S.CR_DRAWS):
    hh = F.hits(keys, sessions, calendar, cells, window)
    mask = F.mask_from(h.index, hh)
    nets = _nets(h)
    delta = -weight * nets[mask].sum(axis=0)
    mk = h["market"].to_numpy()
    k = {m: int(mask[mk == m].sum()) for m in S.MARKETS}
    cr = weight * K.random_removal(nets, mk, k, draws) if mask.any() else np.zeros((draws, 3))
    return dict(hits=hh, mask=mask, n=int(mask.sum()), delta=delta, cr=cr,
                pct_mid=K.percentile_of(delta[1], cr[:, 1]) if mask.any() else float("nan"))


def analyse(books: pd.DataFrame, sessions: dict, calendar: dict, *, cr_draws=S.CR_DRAWS,
            perm_draws=S.PERM_DRAWS, log=print) -> dict:
    h = BK.host(books, BK.PRIMARY_HOST)
    F.assert_training(h)
    n0, net0 = BK.check_books_reproduce(h)                                      # G5
    F.check_convention(h, sessions)                                             # G4
    keys = h[["market", "entry_date"]]
    R = dict(host_n=n0, host_net_mid=net0)
    log("primary flag + C-R ...")
    P = _evaluate(h, keys, sessions, calendar, S.FLAG_CELLS, "primary", draws=cr_draws)
    R["primary"] = P
    nets, mk, mask = _nets(h), h["market"].to_numpy(), P["mask"]
    R["floor_ok"] = P["n"] >= S.MIN_FLAGGED
    fl = h.loc[mask]
    # criteria
    d_mid, d_high = P["delta"][1], P["delta"][2]
    med = fl["entry_date"].sort_values().iloc[len(fl) // 2] if len(fl) else None
    early = mask & (h["entry_date"] <= med).to_numpy() if med is not None else mask
    late = mask & ~early
    halves = (-nets[early, 1].sum(), -nets[late, 1].sum())
    contrib_m = pd.Series(-nets[mask, 1], index=fl["market"].to_numpy()).groupby(level=0).sum()
    contrib_y = pd.Series(-nets[mask, 1], index=fl["entry_date"].dt.year.to_numpy()).groupby(level=0).sum()
    top_m = (contrib_m.abs().max() / d_mid) if d_mid > 0 and len(contrib_m) else float("nan")
    top_y = (contrib_y.abs().max() / d_mid) if d_mid > 0 and len(contrib_y) else float("nan")
    log("placebo ...")
    PL = _evaluate(h, keys, sessions, calendar, S.placebo_cells(), "primary", draws=1)
    per_flag = d_mid / P["n"] if P["n"] else float("nan")
    per_pl = PL["delta"][1] / PL["n"] if PL["n"] else float("nan")
    log("criterion-7 permutation ...")
    obs, p7, _ = K.label_permutation_p(mask, nets[:, 1], mk, perm_draws)
    both = int((P["mask"] & PL["mask"]).sum())
    cr95 = K.cr_summary(P["cr"][:, 1])["p95"] if P["n"] else float("nan")
    crit = {
        1: ("Delta > $0 at mid", d_mid > 0, money(d_mid)),
        2: ("Delta beats the C-R p95", d_mid > cr95, f"{money(d_mid)} vs p95 {money(cr95)}"),
        3: ("Both halves delta > $0", halves[0] > 0 and halves[1] > 0, f"{money(halves[0])} / {money(halves[1])}"),
        4: ("Delta > $0 at high friction", d_high > 0, money(d_high)),
        5: ("No market or year > 50% of delta", bool(d_mid > 0 and top_m <= 0.5 and top_y <= 0.5),
            f"top market {top_m:.0%}, top year {top_y:.0%}" if d_mid > 0 else "delta not positive"),
        6: ("Delta per skipped > placebo per skipped", per_flag > per_pl,
            f"{money(per_flag, 2)} vs {money(per_pl, 2)} (placebo n={PL['n']})"),
        7: ("Flagged mean net < unflagged mean net (perm p < 0.05)", bool(p7 < 0.05), f"p = {p7:.4f}"),
        8: ("At least 60 flagged trades", R["floor_ok"], str(P["n"])),
    }
    R.update(crit=crit, halves=halves, med_date=med, placebo=PL, perm=(obs, p7), overlap_flag_placebo=both,
             contrib_m=contrib_m, contrib_y=contrib_y, cr=K.cr_summary(P["cr"][:, 1]) if P["n"] else {})
    if not R["floor_ok"]:
        R["verdict"] = "NOT READ (fewer than 60 flagged trades; not a failure)"
    elif all(v[1] for v in crit.values()):
        R["verdict"] = "PASS (eligible to spend the holdout, once, with Ben's go)"
    elif not (crit[2][1] and crit[6][1]):
        R["verdict"] = "FAIL -- criterion 2 or 6 failed: the study closes"
    else:
        R["verdict"] = "FAIL"
    # reported variants (never ranked, cannot spend the holdout)
    log("reported variants ...")
    var = {}
    for name, cells, win, w in (
            ("W1 only", S.FLAG_CELLS, "w1", 1.0), ("W2 only", S.FLAG_CELLS, "w2", 1.0),
            ("Half size", S.FLAG_CELLS, "primary", 0.5), ("NFP cells alone", S.per_event_cells("NFP"), "primary", 1.0),
            ("FOMC cells alone", S.per_event_cells("FOMC"), "primary", 1.0),
            ("No map (all markets, all scheduled)", S.nomap_cells(), "primary", 1.0),
            ("Wide window (d-1, d, d+1)", S.FLAG_CELLS, "wide", 1.0)):
        var[name] = _evaluate(h, keys, sessions, calendar, cells, win, w, draws=cr_draws)
    for name in ("C1 int $100k", "C1 int $500k", "TL-v1 v1 ens frac"):
        hb = BK.host(books, name)
        var[f"Other book: {name}"] = _evaluate(hb, hb[["market", "entry_date"]], sessions, calendar,
                                               S.FLAG_CELLS, "primary", draws=cr_draws)
    R["variants"] = var
    # emit tables
    x = P["hits"].merge(h[["entry_date"]], left_on="idx", right_index=True)
    x["year"] = x["entry_date"].dt.year
    R["counts"] = x.groupby(["market", "event", "part", "year"]).size().rename("n").reset_index()
    hh = P["hits"].assign(tag=P["hits"]["event"] + "/" + P["hits"]["part"])
    ev = hh.groupby("idx")["tag"].agg(lambda t: "+".join(sorted(set(t))))
    R["flagged_trades"] = fl.assign(hit=ev.reindex(fl.index).to_numpy())
    R["host_stats"] = dict(
        flagged_mean=float(nets[mask, 1].mean()) if mask.any() else float("nan"),
        unflagged_mean=float(nets[~mask, 1].mean()),
        flagged_win=int((nets[mask, 1] > 0).sum()), flagged_loss=int((nets[mask, 1] <= 0).sum()),
        unflagged_win=int((nets[~mask, 1] > 0).sum()), unflagged_loss=int((nets[~mask, 1] <= 0).sum()),
        delta_lmh=P["delta"])
    return R


def render(R: dict) -> str:
    P, L = R["primary"], []
    p = L.append
    p("MFLAG-v1 TRAINING RUN -- REGISTERED_macro_flag_v1.md sec 3-4 (W15-0023 step 4)")
    p("Host: Donchian 20/10 C1, fractional @ $22,129, TRAINING 2010-06..2021-12. Negatives in brackets.")
    p("The holdout is not read. The seen window (2025-09-23 ->) is not in these books: not scored.")
    p(f"G5: books reproduce -- {R['host_n']} trades, net {money(R['host_net_mid'], 2)} at mid.")
    p("")
    p(f"VERDICT: {R['verdict']}")
    p("")
    p("HEADLINE (skip flagged trades; delta = net after skipping - net of host; friction saved is included):")
    p(f"  flagged trades: {P['n']}  (registered prediction: 70-110)")
    p("  delta low / mid / high: " + " / ".join(money(v) for v in P["delta"]))
    if P["n"]:
        c = R["cr"]
        p("  C-R (1,000 random removals, same count per market), mid: p5 %s  p50 %s  p95 %s  p99 %s" % tuple(
            money(c[k]) for k in ("p5", "p50", "p95", "p99")))
        p(f"  flag sits at the {P['pct_mid']:.0f}th percentile of C-R (registered prediction: 40th-80th)")
    p("")
    p("SEC 4 CRITERIA (all must hold; failing 2 or 6 closes the study):")
    for k, (name, ok, val) in R["crit"].items():
        p(f"  {k}. {'PASS' if ok else 'FAIL'}  {name}: {val}")
    p("")
    hs = R["host_stats"]
    p(f"Flagged: {hs['flagged_win']} wins / {hs['flagged_loss']} losses, mean net {money(hs['flagged_mean'], 2)}")
    p(f"Unflagged: {hs['unflagged_win']} wins / {hs['unflagged_loss']} losses, mean net {money(hs['unflagged_mean'], 2)}")
    p(f"Placebo (24 unsupported cells): {R['placebo']['n']} trades, delta {money(R['placebo']['delta'][1])} at mid; "
      f"{R['overlap_flag_placebo']} of them are also flagged (not de-duplicated, as registered).")
    p(f"Halves split at {R['med_date'].date() if R['med_date'] is not None else 'n/a'}: "
      f"{money(R['halves'][0])} / {money(R['halves'][1])}")
    p("Permutation seed tag 24 (the registration gave a seed for C-R only; disclosed).")
    p("")
    p("DELTA BY MARKET (mid):  " + ", ".join(f"{m} {money(v)}" for m, v in R["contrib_m"].items()))
    p("DELTA BY YEAR (mid):   " + ", ".join(f"{y} {money(v)}" for y, v in R["contrib_y"].items()))
    p("")
    p("REPORTED VARIANTS (never ranked, cannot spend the holdout): n / delta low, mid, high / percentile of C-R at mid")
    for name, v in R["variants"].items():
        p(f"  {name:<40}{v['n']:>4}   " + " / ".join(money(d) for d in v["delta"]) + f"   {v['pct_mid']:.0f}th")
    p("  Other books are reported only; they never change those studies' verdicts. CRUDELE-3S, BREIT-CAP and")
    p("  CHARTMARK-v1 training books do not exist yet.")
    p("")
    ft = R["flagged_trades"]
    if len(ft):
        s = ft.sort_values("net_mid")
        p("TEN LARGEST FLAGGED LOSERS (the ones skipping saves), mid:")
        for _, r in s.head(10).iterrows():
            p(f"  {r['entry_date'].date()}  {r['market']:<4}{r['hit']:<22}{money(r['net_mid'], 2)}")
        p("TEN LARGEST FLAGGED WINNERS (the ones skipping gives up), mid:")
        for _, r in s.tail(10).iloc[::-1].iterrows():
            p(f"  {r['entry_date'].date()}  {r['market']:<4}{r['hit']:<22}{money(r['net_mid'], 2)}")
    return "\n".join(L) + "\n"
