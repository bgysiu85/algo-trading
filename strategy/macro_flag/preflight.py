"""G2 -- MFLAG-v1 count-only pre-flight (REGISTERED_macro_flag_v1.md sec 5). No P&L is loaded.

Reads market, spec, share, sizing, equity, entry_date, entry_j from the host books (never a net/gross
column: books.read_books(with_pnl=False)), joins them to the event calendar, and prints flagged counts
per market x event x window part x year. Stop rule: fewer than 60 flagged C1 trades -> STOP, back to Ben
before any P&L is read. G4 convention (sessions[entry_j] == entry_date) is checked here on real sessions.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from strategy.macro_flag import books as BK
from strategy.macro_flag import flag as F
from strategy.macro_flag import spec as S


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _counts(host: pd.DataFrame, h: pd.DataFrame) -> pd.DataFrame:
    if not len(h):
        return pd.DataFrame(columns=["market", "event", "part", "year", "n"])
    x = h.merge(host[["entry_date"]], left_on="idx", right_index=True)
    x["year"] = x["entry_date"].dt.year
    return x.groupby(["market", "event", "part", "year"]).size().rename("n").reset_index()


def run(books: pd.DataFrame, sessions: dict, calendar: dict) -> dict:
    host = BK.host(books, BK.PRIMARY_HOST)
    F.assert_training(host)
    checked = F.check_convention(host, sessions)
    keys = host[["market", "entry_date"]]
    prim = F.hits(keys, sessions, calendar, S.FLAG_CELLS)
    mask = F.mask_from(host.index, prim)
    out = dict(host_trades=len(host), convention_checked=checked, flagged=int(mask.sum()),
               flagged_share=float(mask.mean()), by_market={m: int(mask[(host["market"] == m).to_numpy()].sum())
                                                            for m in S.MARKETS},
               host_by_market=host["market"].value_counts().to_dict(),
               counts=_counts(host, prim), variants={})
    out["stop"] = out["flagged"] < S.MIN_FLAGGED
    variants = {"W1 only": (S.FLAG_CELLS, "w1"), "W2 only": (S.FLAG_CELLS, "w2"),
                "NFP cells alone": (S.per_event_cells("NFP"), "primary"),
                "FOMC cells alone": (S.per_event_cells("FOMC"), "primary"),
                "No map": (S.nomap_cells(), "primary"), "Wide window": (S.FLAG_CELLS, "wide"),
                "Placebo (24 unsupported cells)": (S.placebo_cells(), "primary")}
    for name, (cells, win) in variants.items():
        v = F.hits(keys, sessions, calendar, cells, win)
        out["variants"][name] = int(F.mask_from(host.index, v).sum())
    return out


def render(rep: dict, *, scoped: bool = False) -> str:
    L, p = [], None
    L.append("MFLAG-v1 G2 PRE-FLIGHT -- REGISTERED_macro_flag_v1.md sec 5 (W15-0023 step 4)")
    L.append("TRAINING SIDE ONLY (2010-06 .. 2021-12), COUNTS ONLY: no net / gross column is loaded.")
    if scoped:
        L.append("SCOPED RUN: NOT THE REGISTERED PRE-FLIGHT.")
    L.append("")
    L.append(f"Host C1 frac @ $22,129: {rep['host_trades']} trades. G4 convention "
             f"(sessions[entry_j] == entry_date) checked on {rep['convention_checked']} trades: OK.")
    L.append(f"FLAGGED (primary, sec 2.2, unique trades): {rep['flagged']}  "
             f"({100 * rep['flagged_share']:.1f}% of host trades)   stop rule: fewer than {S.MIN_FLAGGED} -> STOP")
    L.append("  -> " + ("BELOW THE FLOOR -- STOP. Report to Ben; the counts are the finding. No P&L run."
                        if rep["stop"] else "at or above 60: the training run may proceed (Ben to say go)."))
    L.append("")
    L.append("FLAGGED BY MARKET (host trades in brackets):")
    for m in S.MARKETS:
        L.append(f"  {m:<4}{rep['by_market'][m]:>5}   ({rep['host_by_market'].get(m, 0)})")
    L.append("")
    L.append("COUNT-ONLY VARIANTS (unique trades flagged; reported, never ranked):")
    for k, v in rep["variants"].items():
        L.append(f"  {k:<34}{v:>5}")
    L.append("")
    L.append("FLAGGED BY MARKET x EVENT x PART x YEAR (a trade hit by two rows is counted in each row):")
    c = rep["counts"]
    if len(c):
        pv = c.pivot_table(index=["market", "event", "part"], columns="year", values="n", fill_value=0,
                           aggfunc="sum")
        pv["total"] = pv.sum(axis=1)
        L.append(pv.to_string())
    else:
        L.append("  (none)")
    return "\n".join(L) + "\n"


def clean(rep: dict, books_path, calendar_path) -> dict:
    d = {k: v for k, v in rep.items() if k not in ("counts",)}
    d["counts"] = rep["counts"].to_dict(orient="records")
    d["books_sha256"] = sha256(books_path)
    d["calendar_sha256"] = sha256(calendar_path)
    return d
