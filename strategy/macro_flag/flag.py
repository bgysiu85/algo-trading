"""The MFLAG-v1 flag (REGISTERED_macro_flag_v1.md sec 2.2). Pure functions, no P&L.

A host trade in market m is flagged if its entry_date (the session whose open fills the entry, as the
host books record it) is in the window of a flag event on session date d:
    W1  entry_date == d                          (the position is open through the release)
    W2  entry_date == next session after d       (the signal bar was d; next-open entry)
    W0  session before d                         (only in the reported 'wide' variant)
Inputs are ONLY (market, entry_date), the calendar and the session list. A test proves the flag does
not move when any P&L column is changed, and that a one-session shift of the calendar changes it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.macro_flag import spec as S

PARTS = {"primary": ("W1", "W2"), "w1": ("W1",), "w2": ("W2",), "wide": ("W0", "W1", "W2")}
HIT_COLS = ["idx", "market", "event", "part"]


class ConventionError(SystemExit):
    pass


def load_calendar(path) -> dict[str, pd.DatetimeIndex]:
    df = pd.read_csv(path, encoding="utf-8", parse_dates=["date"])
    return {e: pd.DatetimeIndex(sorted(set(df.loc[df["event"] == e, "date"]))) for e in S.ALL_EVENTS}


def window_dates(sessions: pd.DatetimeIndex, days: pd.DatetimeIndex, window: str = "primary") -> dict:
    s = sessions.values
    d = days.values
    out = {}
    if "W1" in PARTS[window]:
        out["W1"] = days
    if "W2" in PARTS[window]:
        i = np.searchsorted(s, d, side="right")            # first session strictly after d
        out["W2"] = pd.DatetimeIndex(s[i[i < len(s)]])
    if "W0" in PARTS[window]:
        i = np.searchsorted(s, d, side="left")             # first session >= d; the one before is W0
        out["W0"] = pd.DatetimeIndex(s[i[i > 0] - 1])
    return out


def hits(keys: pd.DataFrame, sessions_by_market: dict, calendar: dict, cells: dict,
         window: str = "primary") -> pd.DataFrame:
    """One row per (trade, event, part) hit. `keys` must be ONLY market and entry_date."""
    if list(keys.columns) != ["market", "entry_date"]:
        raise ValueError("flag.hits takes exactly [market, entry_date]; it may not see anything else")
    parts = []
    for m, evs in cells.items():
        sub = keys.loc[keys["market"] == m, "entry_date"]
        if sub.empty or m not in sessions_by_market:
            continue
        for ev in evs:
            for part, dts in window_dates(sessions_by_market[m], calendar[ev], window).items():
                sel = sub.index[sub.isin(dts)]
                if len(sel):
                    parts.append(pd.DataFrame({"idx": sel, "market": m, "event": ev, "part": part}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=HIT_COLS)


def mask_from(index, h: pd.DataFrame) -> np.ndarray:
    return np.asarray(pd.Index(index).isin(h["idx"].unique()))


def check_convention(trades: pd.DataFrame, sessions_by_market: dict) -> int:
    """G4: entry_date must be the session whose open fills, i.e. sessions[entry_j]. Returns the number of
    trades checked; raises ConventionError on the first market with any mismatch."""
    n = 0
    for m, g in trades.groupby("market"):
        s = sessions_by_market[m]
        j = g["entry_j"].to_numpy(dtype=int)
        bad = (j < 0) | (j >= len(s))
        ok = ~bad
        ok[ok] = s[j[ok]] == g["entry_date"].to_numpy()[ok]
        if not ok.all():
            raise ConventionError(f"CONVENTION BROKEN in {m}: {int((~ok).sum())} of {len(g)} trades have "
                                  "entry_date != sessions[entry_j]; the W1/W2 window would be wrong. STOP.")
        n += len(g)
    return n


def assert_training(trades: pd.DataFrame) -> None:
    last = trades["entry_date"].max()
    if last >= pd.Timestamp(S.LOCK_FROM):
        raise SystemExit(f"REFUSED: books contain entry_date {last.date()} >= {S.LOCK_FROM}; "
                         "the holdout is not read by this runner (sec 6).")
