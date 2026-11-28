"""VA80 v1 training-side study (REGISTERED_va80.md sec 3, 4; W15-0041, the build behind W15-0025 sub 5).

Reads the session frames of the TRAINING side only (the runner cuts them through the ledger before anything is built),
prices every VA80 trade with the IBKR costs of Amendment 2, scores it against the seeded random-time control (C-RT),
counts the 27 neighbour cells, checks the seven criteria and reports the variants. It computes; it decides nothing:
the verdict string is the registered rule applied to the numbers, and a pass only tells Ben the holdout MAY be spent.

Nothing here spends the holdout, narrows the sample or ranks a variant (sec 7).
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pandas as pd

from strategy.va80 import controls as K
from strategy.va80 import costs as C
from strategy.va80 import engine as E
from strategy.va80 import grid as GR
from strategy.va80 import preflight as PF
from strategy.va80 import spec as S
from strategy.va80 import variants as V
from strategy.va80.engine import Params

LEVELS = ("low", "mid", "high")
CLAIM_EDGE_PCT = 70.0                 # sec 3: claim reproduced if the far-edge rate is >= 70%
SAMPLE_N = 15
COLS = ["date", "year", "side", "gross", "cost", "net", "reason", "entry_minute", "entry_px", "exit_px", "val", "vah",
        "target", "stop"]


def money(x: float, d: int = 0) -> str:
    """Negatives in brackets, never a minus sign."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"(${abs(x):,.{d}f})" if x < 0 and round(abs(x), d) > 0 else f"${abs(x):,.{d}f}"


# ------------------------------------------------------------------ priced books
def price_book(trades: list[dict], vehicle: str, level: str) -> pd.DataFrame:
    """One row per trade, in date order: gross, cost and net in dollars for 1 `vehicle` at `level`."""
    rows = []
    for t in trades:
        p = C.price_trade(t, vehicle, level)
        rows.append({"date": t["date"], "year": int(t["date"][:4]), "side": int(t["side"]), "gross": p["gross"],
                     "cost": p["cost"], "net": p["net"], "reason": t["exit_reason"], "entry_minute": t["entry_minute"],
                     "entry_px": t["entry_px"], "exit_px": t["exit_px"], "val": t["val"], "vah": t["vah"],
                     "target": t["target"], "stop": t["stop"]})
    df = pd.DataFrame(rows, columns=COLS)
    return df.sort_values("date", kind="mergesort").reset_index(drop=True)


def max_drawdown(nets) -> float:
    """Worst peak-to-trough of the closed-trade equity curve, in the order given; the start (0) is the first peak."""
    nets = np.asarray(nets, dtype=float)
    if not len(nets):
        return 0.0
    eq = np.cumsum(nets)
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    return float((peak - eq).max())


def book_stats(df: pd.DataFrame) -> dict:
    n = len(df)
    nets = df["net"].to_numpy(dtype=float)
    win, loss = nets[nets > 0], nets[nets < 0]
    ex = Counter(df["reason"]) if n else Counter()
    return {"trades": n, "gross": float(df["gross"].sum()), "costs": float(df["cost"].sum()), "net": float(nets.sum()),
            "wins": int(len(win)), "losses": int(len(loss)), "win_pct": float(100.0 * len(win) / n) if n else 0.0,
            "mean_win": float(win.mean()) if len(win) else 0.0, "mean_loss": float(loss.mean()) if len(loss) else 0.0,
            "exits": {S.TARGET: int(ex.get(S.TARGET, 0)), S.STOP: int(ex.get(S.STOP, 0)), S.TIME: int(ex.get(S.TIME, 0))},
            "max_dd": max_drawdown(nets)}


def by_year(df: pd.DataFrame) -> dict:
    g = df.groupby("year")
    return {"net": {int(y): float(v) for y, v in g["net"].sum().items()},
            "trades": {int(y): int(v) for y, v in g.size().items()},
            "gross": {int(y): float(v) for y, v in g["gross"].sum().items()}}


def by_side(df: pd.DataFrame) -> dict:
    out = {}
    for name, sd in (("long", S.LONG), ("short", S.SHORT)):
        d = df[df["side"] == sd]
        out[name] = {"trades": int(len(d)), "net": float(d["net"].sum()), "wins": int((d["net"] > 0).sum()),
                     "gross": float(d["gross"].sum())}
    return out


def _q(x) -> dict:
    x = np.asarray(x, dtype=float)
    if not len(x):
        return {"p10": float("nan"), "p50": float("nan"), "p90": float("nan")}
    return {f"p{q}": float(np.percentile(x, q)) for q in (10, 50, 90)}


def distances(trades: list[dict]) -> dict:
    """Target and stop distances in points from the entry (median, p10, p90). A trade with no stop (no-stop variant)
    has no stop distance."""
    tgt = [abs(t["target"] - t["entry_px"]) for t in trades]
    stp = [abs(t["entry_px"] - t["stop"]) for t in trades if t.get("stop") is not None]
    return {"target": _q(tgt), "stop": _q(stp)}


def halves(df: pd.DataFrame) -> dict:
    """Split at the median entry date: early = date <= median, late = after. An empty half fails (criterion 3)."""
    if not len(df):
        return {"median_date": None, "early": 0.0, "late": 0.0, "early_n": 0, "late_n": 0, "both_positive": False}
    med = sorted(df["date"])[len(df) // 2]
    e, l = df[df["date"] <= med], df[df["date"] > med]
    en, ln = float(e["net"].sum()), float(l["net"].sum())
    return {"median_date": med, "early": en, "late": ln, "early_n": int(len(e)), "late_n": int(len(l)),
            "both_positive": bool(len(e) and len(l) and en > 0 and ln > 0)}


def sample_trades(df: pd.DataFrame, n: int = SAMPLE_N) -> pd.DataFrame:
    """n trades spread evenly through the date-ordered book (all of them if there are fewer)."""
    if len(df) <= n:
        return df.copy()
    idx = np.unique(np.linspace(0, len(df) - 1, n).round().astype(int))
    return df.iloc[idx].copy()


# ------------------------------------------------------------------ controls netted with the same costs
def draw_net(draws: dict, vehicle: str, level: str) -> np.ndarray:
    """Net dollars per control draw: gross points x point value, less the fee on both sides and the level's ticks on every
    market entry and every non-target exit (a target limit fill pays none)."""
    k, fee, tv = C.LEVEL_TICKS[level], C.FEE_PER_SIDE[vehicle], C.TICK_VALUE[vehicle]
    n, other = np.asarray(draws["n"], dtype=float), np.asarray(draws["n_other"], dtype=float)
    cost = n * 2.0 * fee + k * tv * (n + other)
    return np.asarray(draws["gross_pts"], dtype=float) * C.POINT_VALUE[vehicle] - cost


# ------------------------------------------------------------------ the 80% check (sec 3)
def outcome_of(s: E.Sess, st: dict) -> str:
    """'edge' | 'stop' | 'neither' for a triggered setup. A setup that had ALREADY rotated traded at the far edge before the
    entry (that is what 'rotated' means), so it counts as reached. Otherwise: does price TRADE AT (touch) the far edge
    before the stop level, from the entry bar on; stop wins a same-bar tie (controls.edge_outcome)."""
    if st["rotated"]:
        return "edge"
    return K.edge_outcome(s, st["j"], st["side"], st["target"], st["stop"])


def claim_shares(counter) -> dict:
    n = int(sum(counter.get(k, 0) for k in ("edge", "stop", "neither")))
    pct = lambda k: float(100.0 * counter.get(k, 0) / n) if n else 0.0
    return {"n": n, "edge": int(counter.get("edge", 0)), "stop": int(counter.get("stop", 0)),
            "neither": int(counter.get("neither", 0)), "edge_pct": pct("edge"), "stop_pct": pct("stop"),
            "neither_pct": pct("neither"), "reproduced": bool(n and pct("edge") >= CLAIM_EDGE_PCT)}


def claim_check(store, records: list[dict]) -> dict:
    """Of ALL triggered setups (rotated included): far edge reached / stop level first / neither. Also the same split for
    the trades alone (not yet rotated)."""
    allc, tradesc, rotated = Counter(), Counter(), 0
    for r in records:
        if r["status"] != "ok" or not r["trigger"]:
            continue
        if r["rotated"]:
            allc["edge"] += 1
            rotated += 1
            continue
        t = r["trade"]
        s = store.sess(r["date"])
        j = int(np.searchsorted(s.minute, t["entry_minute"], side="left"))
        o = outcome_of(s, {"rotated": False, "j": j, "side": t["side"], "target": t["target"], "stop": t["stop"]})
        allc[o] += 1
        tradesc[o] += 1
    return {"all": claim_shares(allc), "trades": claim_shares(tradesc), "rotated": rotated}


# ------------------------------------------------------------------ the seven criteria (sec 4)
def criteria(*, net_mid, net_high, crt_p95, halves, year_nets, cells_positive, n_trades) -> dict:
    """The registered bar, applied to numbers. Fewer than 200 trades is NOT READ, not a failure. Failing criterion 2
    closes the study whatever else passes."""
    top = (max(year_nets.values()) / net_mid) if (net_mid > 0 and year_nets) else float("nan")
    c = {
        1: ("Net > $0 at mid", bool(net_mid > 0), money(net_mid)),
        2: ("Net > the C-RT p95", bool(net_mid > crt_p95), f"{money(net_mid)} vs p95 {money(crt_p95)}"),
        3: ("Both halves net > $0", bool(halves["both_positive"]), f"{money(halves['early'])} / {money(halves['late'])}"),
        4: ("Net > $0 at high friction", bool(net_high > 0), money(net_high)),
        5: ("No single year supplies more than 50% of net", bool(net_mid > 0 and year_nets and top <= 0.5),
            f"largest year {top:.0%} of net" if net_mid > 0 and year_nets else "net not positive"),
        6: (f"At least {S.GRID_MIN_POSITIVE} of 27 neighbour cells net > $0 at mid", bool(cells_positive >= S.GRID_MIN_POSITIVE),
            f"{cells_positive} of 27"),
        7: (f"At least {S.MIN_TRADES} trades", bool(n_trades >= S.MIN_TRADES), str(n_trades)),
    }
    failed = [k for k, v in c.items() if not v[1]]
    if n_trades < S.MIN_TRADES:
        verdict = "NOT READ"
    elif failed:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return {"crit": c, "verdict": verdict, "failed": failed, "closed": bool(verdict != "NOT READ" and 2 in failed)}


# ------------------------------------------------------------------ one market
def _book(trades, vehicle) -> dict:
    return {lv: book_stats(price_book(trades, vehicle, lv)) for lv in LEVELS}


def _variant(trades, vehicle) -> dict:
    b = _book(trades, vehicle)
    return {"trades": b["mid"]["trades"], "net": {lv: b[lv]["net"] for lv in LEVELS}, "gross": b["mid"]["gross"],
            "win_pct": b["mid"]["win_pct"], "exits": b["mid"]["exits"], "max_dd": b["mid"]["max_dd"]}


def _counts(records) -> dict:
    y = PF.yearly(PF.frame_of(records))
    t = y.loc["total"]
    return {"yearly": y, "sessions": int(t["sessions"]), "triggers": int(t["triggers"]), "rotated": int(t["rotated"]),
            "trades": int(t["trades_long"] + t["trades_short"])}


def _inside_sessions(store, days) -> list[dict]:
    return [{"date": d, "val": val, "vah": vah} for d, status, pack in V.iter_setups(store, days)
            if status == "ok" for (_, _, val, vah, st) in [pack] if st["open"] == S.INSIDE]


def _market(root, store, days, draws, log, scored) -> dict:
    head, full = C.HEADLINE[root], C.FULL[root]
    log(f"{root}: evaluating sessions ...")
    records = E.evaluate(store, days, Params(), want_exit=True)
    trades = [V.with_legs(dict(r["trade"])) for r in records if r["trade"]]
    counts = _counts(records)
    skipped = {"skip_data": [r["date"] for r in records if r["status"] == "skip_data"],
               "skip_roll": [r["date"] for r in records if r["status"] == "skip_roll"]}
    book = _book(trades, head)
    mid = price_book(trades, head, "mid")
    out = {"market": root, "vehicle": head, "full_vehicle": full, "scored": scored, "counts": counts,
           "trades": len(trades), "book": book, "full": _book(trades, full), "by_year": by_year(mid),
           "by_side": by_side(mid), "distances": distances(trades), "halves": halves(mid),
           "sample": sample_trades(mid), "claim": claim_check(store, records),
           "skipped_dates": skipped["skip_data"], "skipped_roll_dates": skipped["skip_roll"]}
    if not scored:
        return out
    log(f"{root}: C-RT ({draws} draws) ...")
    if trades:
        crt = K.run_crt(store, trades, draws)
    else:
        crt = K._empty(draws)
    crt_mid = draw_net(crt, head, "mid")
    tot = {k: float(crt[k].sum()) for k in ("n_edge", "n_stop", "n_neither")}
    out["crt"] = {"net_mid": crt_mid, "summary": K.summary(crt_mid),
                  "va80_pct": K.percentile_of(book["mid"]["net"], crt_mid), "unused_mean": float(crt["unused"].mean()),
                  "claim": claim_shares({"edge": tot["n_edge"], "stop": tot["n_stop"], "neither": tot["n_neither"]})}
    log(f"{root}: C-ND ({draws} draws) ...")
    ins = _inside_sessions(store, days)
    cnd = K.run_cnd(store, ins, draws) if ins else K._empty(draws)
    cnd_mid = draw_net(cnd, head, "mid")
    out["cnd"] = {"net_mid": cnd_mid, "summary": K.summary(cnd_mid), "sessions": len(ins),
                  "va80_pct": K.percentile_of(book["mid"]["net"], cnd_mid)}
    log(f"{root}: 27-cell grid ...")
    cells = {}
    for cell in GR.CELLS:
        ts = V.primary_trades(store, days, GR.params(cell))
        cells[cell] = {"trades": len(ts), "net_mid": float(price_book(ts, head, "mid")["net"].sum())}
    out["grid"] = {"cells": cells, "positive": sum(1 for c in cells.values() if c["net_mid"] > 0)}
    log(f"{root}: variants ...")
    out["variants"] = {
        "reclaim": _variant(V.reclaim_trades(store, days), head),
        "one_bracket": _variant(V.primary_trades(store, days, Params(accept=1)), head),
        "no_stop": _variant(V.nostop_trades(store, days), head),
        "poc_half": _variant(V.poc_half_trades(store, days), head)}
    yn = out["by_year"]["net"]
    out["crit"] = criteria(net_mid=book["mid"]["net"], net_high=book["high"]["net"], crt_p95=out["crt"]["summary"]["p95"],
                           halves=out["halves"], year_nets=yn, cells_positive=out["grid"]["positive"], n_trades=len(trades))
    out["verdict"] = out["crit"]["verdict"]
    return out


def analyse(roots: dict, *, draws: int = S.CR_DRAWS, log=print) -> dict:
    """roots = {'ES': (store, training days), 'NQ': (store, days)}. ES is scored; NQ is reported (1 MNQ, 1 NQ)."""
    return {r: _market(r, store, days, draws, log, scored=(r == "ES")) for r, (store, days) in roots.items()}
