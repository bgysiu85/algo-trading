#!/usr/bin/env python3
"""WICK-REV analysis of one market / timeframe: everything sec 5 asks for, and the sec 6 reading.
W15-0063, REGISTERED_wick_reversal.md. Pure functions of a `Series`; no files, no archive.

Nothing is ranked and no combination is picked: the caller walks the six combinations in the fixed order.
"""
from __future__ import annotations

import numpy as np

from strategy.wick_rev import spec as S
from strategy.wick_rev import signals as G
from strategy.wick_rev import stats as ST
from strategy.wick_rev import trades as TR

SIDE_NAME = {1: "up->down (UWR)", -1: "down->up (LWR)"}


def _p(num, den):
    return float(num) / den if den else float("nan")


def _group(name, sel, months, rev3, cont3, amb3, kind20, bar20, base_sel, base_months, base_rev3):
    """Stats for the signals picked by boolean `sel` (aligned to the base context bars)."""
    n = int(sel.sum())
    r = int(rev3[sel].sum()); c = int(cont3[sel].sum()); a = int(amb3[sel].sum())
    out = {"name": name, "n": n, "rev3": r, "cont3": c, "amb3": a, "none3": n - r - c - a,
           "p_rev": _p(r, n), "p_rev_decided": _p(r, r + c),
           "base_n": int(base_sel.sum()), "base_p": _p(base_rev3[base_sel].sum(), base_sel.sum())}
    out["edge"] = ST.edge_ci(months[sel], rev3[sel], base_months[base_sel], base_rev3[base_sel],
                             universe_months=np.unique(base_months))
    k20, b20 = kind20[sel], bar20[sel]
    rev20 = k20 == G.REV
    out["cum"] = {m: _p((rev20 & (b20 + 1 <= m)).sum(), n) for m in S.CUM_BARS}
    out["median_tau"] = float(np.median(b20[rev20] + 1)) if rev20.any() else float("nan")
    out["cont_first_20"] = _p((k20 == G.CONT).sum(), n)
    out["amb20"] = int((k20 == G.AMBIG).sum())
    return out


def _money(s, f, idx, side, halves_cut):
    tr = TR.simulate(s, f, idx, side)
    n = len(tr["gross"])
    net_mid = tr["net"]["mid"]
    years = tr["signal_date"].astype("datetime64[Y]").astype(int) + 1970 if n else np.zeros(0, int)
    out = {"trades": n, "skipped": tr["skipped"], "wins": int((net_mid > 0).sum()), "losses": int((net_mid <= 0).sum()),
           "gross": float(tr["gross"].sum()), "cost": {lv: float(tr["cost"][lv] * n) for lv in S.LEVELS},
           "net": {lv: float(tr["net"][lv].sum()) for lv in S.LEVELS},
           "avg_net_mid": float(net_mid.mean()) if n else float("nan"),
           "by_year": {int(y): float(net_mid[years == y].sum()) for y in np.unique(years)} if n else {},
           "by_reason": {r: int((tr["reason"] == r).sum()) for r in sorted(set(tr["reason"].tolist()))},
           "samples": []}
    if n:
        first = np.arange(n)[:: max(1, n // 20)][:20]
        out["samples"] = [(str(tr["signal_date"][i]), float(tr["entry"][i]), float(tr["exit"][i]),
                           str(tr["reason"][i]), float(tr["net"]["mid"][i])) for i in first]
        if halves_cut is not None:
            early = tr["signal_date"] < halves_cut
            out["net_mid_halves"] = (float(net_mid[early].sum()), float(net_mid[~early].sum()))
    return out


def analyse_side(s: G.Series, f: G.Features, side: int, *, ks=S.KS, with_money=True) -> dict:
    base_idx = G.signal_indices(f, side)
    ratio = G.ratio_for(f, side)[base_idx]
    bucket = G.bucket_of(G.ratio_for(f, side))[base_idx]
    months = ST.month_codes(s.session[base_idx])
    years = s.session[base_idx].astype("datetime64[Y]").astype(int) + 1970
    prim = ratio >= S.UWR_CUT
    size = f.size_cat[base_idx]
    colour = f.colour[base_idx]
    classic = (f.star if side == 1 else f.hammer)[base_idx]
    out = {"side": side, "n_base_bars": int(len(base_idx)), "by_k": {}}
    if len(base_idx) == 0:
        return out
    halves_cut = None
    if prim.sum() > 0:
        halves_cut = np.median(s.session[base_idx][prim].astype("datetime64[D]").astype("int64"))
        halves_cut = np.datetime64(int(halves_cut), "D")
    for k in ks:
        res = G.race(s, f, base_idx, side, k)
        k3 = G.outcome_within(res, S.WINDOW)
        rev3, cont3, amb3 = k3 == G.REV, k3 == G.CONT, k3 == G.AMBIG
        allsel = np.ones(len(base_idx), bool)
        args = (months, rev3, cont3, amb3, res["kind"], res["bar"])
        blk = {"all": _group("all bars in context (base rate)", allsel, *args, allsel, months, rev3),
               "primary": _group("primary group (ratio >= 0.6)", prim, *args, allsel, months, rev3),
               "classic": _group("classic shape", classic, *args, allsel, months, rev3),
               "buckets": [], "size": [], "colour": []}
        for b in range(10):
            sel = bucket == b
            blk["buckets"].append(_group(f"{b/10:.1f}-{(b+1)/10:.1f}", sel, *args, allsel, months, rev3))
        for sc, nm in ((0, "small"), (1, "normal"), (2, "large")):
            blk["size"].append(_group(f"primary & {nm} bar", prim & (size == sc), *args, size == sc, months, rev3))
        for cc, nm in ((1, "green"), (-1, "red"), (0, "doji")):
            blk["colour"].append(_group(f"primary & {nm}", prim & (colour == cc), *args, colour == cc, months, rev3))
        # Spearman (descriptive only): ratio vs bars-to-reversal among reversals, and vs reversed-by-bar-3
        rev20 = res["kind"] == G.REV
        blk["rho_tau_all"] = ST.spearman_ci(ratio[rev20], (res["bar"] + 1)[rev20], months[rev20])
        blk["rho_tau_primary"] = ST.spearman_ci(ratio[rev20 & prim], (res["bar"] + 1)[rev20 & prim], months[rev20 & prim])
        blk["rho_flag_all"] = ST.spearman_ci(ratio, rev3.astype(float), months)
        blk["rho_flag_primary"] = ST.spearman_ci(ratio[prim], rev3[prim].astype(float), months[prim])
        # reading inputs (headline k only)
        if abs(k - S.K_HEADLINE) < 1e-9 and prim.any():
            half = s.session[base_idx] < halves_cut
            def edge_half(h):
                ps, bs = prim & h, h
                return _p(rev3[ps].sum(), ps.sum()) - _p(rev3[bs].sum(), bs.sum()), int(ps.sum())
            e1, n1 = edge_half(half)
            e2, n2 = edge_half(~half)
            ex = {}
            for y in np.unique(years):
                ys = years == y
                ps = prim & ys
                ex[int(y)] = float(rev3[ps].sum() - ps.sum() * _p(rev3[ys].sum(), ys.sum())) if ps.any() else 0.0
            tot = sum(ex.values())
            blk["halves"] = {"cut": str(halves_cut), "edge": (e1, e2), "n": (n1, n2)}
            blk["year_excess"] = ex
            blk["max_year_share"] = (max(ex.values()) / tot) if tot > 0 else float("nan")
        out["by_k"][k] = blk
    if with_money:
        mi = {}
        cut = halves_cut
        mi["primary"] = _money(s, f, base_idx[prim], side, cut)
        mi["buckets"] = [_money(s, f, base_idx[bucket == b], side, cut) for b in range(10)]
        mi["classic"] = _money(s, f, base_idx[classic], side, cut)
        out["money"] = mi
    return out


def read_edge(side_res: dict, *, reported_only: bool) -> dict:
    """Sec 6: does this combination-direction SHOW AN EDGE / is it TRADEABLE AS SHAPED?"""
    if reported_only:
        return {"verdict": "REPORTED ONLY", "reasons": ["MCL 30m is on the short IBKR window (Amendment A)"]}
    blk = side_res.get("by_k", {}).get(S.K_HEADLINE)
    if not blk:
        return {"verdict": "NOT READ", "reasons": ["no signals"]}
    g = blk["primary"]
    if g["n"] < S.MIN_SIGNALS:
        return {"verdict": "NOT READ", "reasons": [f"{g['n']} signals < {S.MIN_SIGNALS}"]}
    e = g["edge"]
    c1 = bool(e["edge"] > 0 and e["lo995"] > 0)
    h = blk["halves"]["edge"]
    c2 = bool(h[0] > 0 and h[1] > 0)
    share = blk["max_year_share"]
    c3 = bool(share == share and share <= S.MAX_YEAR_SHARE)       # NaN (no excess) fails
    shows = c1 and c2 and c3
    m = side_res["money"]["primary"]
    c5 = bool(m["net"]["mid"] > 0 and m["net"]["high"] > 0)
    hm = m.get("net_mid_halves")
    c6 = bool(hm is not None and hm[0] > 0 and hm[1] > 0)
    tradeable = shows and c5 and c6
    return {"verdict": ("SHOWS AN EDGE + TRADEABLE AS SHAPED" if tradeable else
                        "SHOWS AN EDGE (not tradeable as shaped)" if shows else "NO EDGE"),
            "shows_edge": shows, "tradeable": tradeable,
            "checks": {"1 edge>0 & 99.5% CI excludes 0": c1, "2 both halves >0": c2,
                       "3 no year > 25% of excess": c3, "5 net mid & high > 0": c5, "6 both halves net mid > 0": c6}}


def analyse(s: G.Series, *, reported_only: bool = False) -> dict:
    f = G.features(s)
    out = {"market": s.market, "tf": s.tf, "reported_only": reported_only, "counts": G.counts_only(s),
           "sides": {}}
    for side in (1, -1):
        r = analyse_side(s, f, side)
        r["reading"] = read_edge(r, reported_only=reported_only)
        out["sides"][side] = r
    return out


def seen_summary(s: G.Series) -> dict:
    """Seen window: counts and P(rev) only (k = 1, 3 bars). Labelled 'seen -- not evidence'."""
    f = G.features(s)
    out = {}
    for side in (1, -1):
        idx = G.signal_indices(f, side)
        if len(idx) == 0:
            out[side] = {"n_base": 0}
            continue
        res = G.race(s, f, idx, side, S.K_HEADLINE)
        rev3 = G.outcome_within(res, S.WINDOW) == G.REV
        prim = G.ratio_for(f, side)[idx] >= S.UWR_CUT
        out[side] = {"n_base": int(len(idx)), "p_base": _p(rev3.sum(), len(idx)),
                     "n_primary": int(prim.sum()), "p_primary": _p(rev3[prim].sum(), prim.sum())}
    return out
