"""G2 -- VA80 v1 count-only pre-flight (REGISTERED_va80.md sec 5). No outcome, no far-edge rate, no P&L.

Runs engine.evaluate(want_exit=False): it reads bars only up to each entry bar (the profile comes from the prior
session; brackets only after they closed; the entry price is the entry bar's open) and never calls walk_exit.
Prints counts per year (sessions, skipped, opens above / below / inside, triggers, already rotated, trades by side),
the value-area width distribution, and trigger counts for the 27 neighbour cells. Stop rule: fewer than 200 ES
triggers on the training side -> STOP, back to Ben before any outcome is read.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from strategy.va80 import grid as GR
from strategy.va80 import spec as S
from strategy.va80.engine import Params, evaluate


def days_for(first: str, last: str) -> list[str]:
    """Consecutive XNYS trading days from `first` through `last`."""
    from strategy.w16.sessions import session_date_range
    ds = session_date_range(int(first[:4]), int(last[:4]))
    return [d for d in ds if first <= d <= last]


def frame_of(records) -> pd.DataFrame:
    return pd.DataFrame([{k: v for k, v in r.items() if k != "trade"} for r in records])


def yearly(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("year")
    ok = df["status"] == "ok"
    t = df["trigger"] & ok
    out = pd.DataFrame({
        "sessions": g.size(),
        "skip_data": df[df["status"] == "skip_data"].groupby("year").size(),
        "skip_roll": df[df["status"] == "skip_roll"].groupby("year").size(),
        "open_above": df[ok & (df["open"] == S.ABOVE)].groupby("year").size(),
        "open_below": df[ok & (df["open"] == S.BELOW)].groupby("year").size(),
        "open_inside": df[ok & (df["open"] == S.INSIDE)].groupby("year").size(),
        "triggers": df[t].groupby("year").size(),
        "rotated": df[t & df["rotated"]].groupby("year").size(),
        "trades_long": df[t & ~df["rotated"] & (df["side"] == S.LONG)].groupby("year").size(),
        "trades_short": df[t & ~df["rotated"] & (df["side"] == S.SHORT)].groupby("year").size(),
    }).fillna(0).astype(int)
    out.loc["total"] = out.sum()
    return out


def run(store, days: list[str], market: str) -> dict:
    recs = evaluate(store, days, Params(), want_exit=False)
    df = frame_of(recs)
    y = yearly(df)
    ok = df["status"] == "ok"
    w = df.loc[ok, "va_width"].dropna()
    wy = df[ok].groupby("year")["va_width"].quantile([0.1, 0.5, 0.9]).unstack()
    grid = {}
    for c in GR.CELLS:
        grid[c] = GR.counts(evaluate(store, days, GR.params(c), want_exit=False))
    tot = y.loc["total"]
    return {"market": market, "yearly": y, "va_width": {"p10": float(w.quantile(.1)) if len(w) else np.nan,
            "p50": float(w.median()) if len(w) else np.nan, "p90": float(w.quantile(.9)) if len(w) else np.nan,
            "by_year": wy}, "grid": grid, "triggers": int(tot["triggers"]),
            "trades": int(tot["trades_long"] + tot["trades_short"]), "rotated": int(tot["rotated"]), "sessions": int(tot["sessions"]),
            "stop": int(tot["triggers"]) < S.MIN_TRIGGERS, "trades_below_floor": int(tot["trades_long"] + tot["trades_short"]) < S.MIN_TRADES}


def sha256_frames(frames: dict) -> str:
    """Identity of the session frames used (dates + OHLCV bytes), for the --run match."""
    h = hashlib.sha256()
    for d in sorted(frames):
        f = frames[d]
        h.update(d.encode())
        for c in ("open", "high", "low", "close", "volume"):
            if c in f.columns:
                h.update(np.ascontiguousarray(f[c].to_numpy(dtype=float)).tobytes())
    return h.hexdigest()


def render(reps: dict, *, scoped: bool = False) -> str:
    L = ["VA80 v1 G2 PRE-FLIGHT -- REGISTERED_va80.md sec 5 (W15-0025 sub 3/4)",
         "TRAINING SIDE ONLY, COUNTS ONLY: no bar after each entry bar is read; no outcome, far-edge rate or P&L."]
    if scoped:
        L.append("SCOPED RUN: NOT THE REGISTERED PRE-FLIGHT.")
    es = reps["ES"]
    L.append("")
    L.append(f"STOP RULE: ES triggers {es['triggers']} (< {S.MIN_TRIGGERS}?) -> "
             + ("BELOW -- STOP. Report to Ben; the counts are the finding. No outcome is read." if es["stop"]
                else "at or above 200: the training run may proceed (Ben to say go)."))
    L.append(f"ES trades (triggers not already rotated): {es['trades']} vs criterion 7 floor {S.MIN_TRADES} -> "
             + ("BELOW: would be NOT READ" if es["trades_below_floor"] else "at or above the floor"))
    for m, r in reps.items():
        L.append("")
        L.append(f"{m}{' (scored)' if m == 'ES' else ' (reported)'} -- counts per year "
                 "(sessions = XNYS days in range; skipped = data or roll; rotated = far edge already traded):")
        L.append("  " + r["yearly"].to_string().replace("\n", "\n  "))
        v = r["va_width"]
        L.append(f"  value-area width (points), evaluated sessions: p10 {v['p10']:.2f}  median {v['p50']:.2f}  p90 {v['p90']:.2f}")
        if len(v["by_year"]):
            L.append("  by year (p10 / p50 / p90): " + "   ".join(
                f"{y}: {row[0.1]:.1f}/{row[0.5]:.1f}/{row[0.9]:.1f}" for y, row in v["by_year"].iterrows()))
        L.append("  TRIGGERS (trades) per neighbour cell (accept brackets, bracket minutes, VA share); reported, never ranked:")
        for c, cn in r["grid"].items():
            L.append(f"    {c[0]} x {c[1]:>2} min x {int(c[2] * 100)}%: {cn['triggers']:>4} ({cn['trades']:>4})"
                     + ("   <- primary" if c == S.CENTRE else ""))
    return "\n".join(L) + "\n"


def clean(reps: dict, inputs: dict) -> dict:
    es = reps["ES"]
    return {"triggers": es["triggers"], "trades": es["trades"], "rotated": es["rotated"], "stop": bool(es["stop"]),
            "trades_below_floor": bool(es["trades_below_floor"]),
            "yearly": {m: r["yearly"].reset_index().to_dict(orient="records") for m, r in reps.items()},
            "grid": {m: {f"{c[0]}|{c[1]}|{c[2]}": cn for c, cn in r["grid"].items()} for m, r in reps.items()},
            "inputs_sha256": inputs}
