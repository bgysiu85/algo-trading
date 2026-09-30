"""Host books for OTF-G (REGISTERED_otf_gate.md sec 2.4, G2, G5).

H-A: the C1 frac rows of Claude outputs\\tl_v1_backtest_trades_20260929.csv. The count-only pre-flight can not
load a P&L column: read_books(with_pnl=False) passes an explicit usecols without them (a test spies on it).

H-B: B1 (the W16 opening-range breakout). `b1_entry` is an ENTRY-ONLY mirror of strategy.w16.signals.orb_session:
same opening range, same trigger, same fill bar, same void rules -- and it never computes a stop walk, a target
or an exit, so the pre-flight can not see an outcome. A test proves it agrees with orb_session on random sessions.
`rerun_b1` (the P&L side, used only by --run) calls the frozen engine itself.
"""
from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd

from strategy.otf_gate import spec as S

KEY_COLS = ("market", "spec", "share", "sizing", "equity", "direction", "entry_date", "entry_j")
PNL_COLS = ("gross", "qty", "sides", "net_low", "net_mid", "net_high")


# ---------------------------------------------------------------- H-A
def read_books(path, *, with_pnl: bool) -> pd.DataFrame:
    cols = list(KEY_COLS) + (list(PNL_COLS) if with_pnl else [])
    return pd.read_csv(path, usecols=cols, encoding="utf-8", parse_dates=["entry_date"])


def host_a(df: pd.DataFrame) -> pd.DataFrame:
    spec, share, sizing, eq = S.HA_HOST
    m = (df["spec"] == spec) & (df["share"] == share) & (df["sizing"] == sizing) & (df["equity"] == eq)
    return df.loc[m].reset_index(drop=True)


def check_convention(host: pd.DataFrame, sessions: dict) -> int:
    """G4: sessions[market][entry_j] == entry_date for every trade (the daily state is then bar entry_j - 1)."""
    n = 0
    for mk, g in host.groupby("market"):
        s = pd.DatetimeIndex(sessions[mk])
        j = g["entry_j"].to_numpy(dtype=int)
        if (j < 1).any() or (j >= len(s)).any() or (s[j] != pd.DatetimeIndex(g["entry_date"])).any():
            raise SystemExit(f"G4 FAILED: {mk} entry_j does not index the entry_date in the daily session list.")
        n += len(g)
    return n


def check_count(host: pd.DataFrame, expected: int = S.HA_TRADES) -> int:
    """Pre-flight-safe part of G5: the host has 1,175 trades (a count, not a P&L)."""
    if len(host) != expected:
        raise SystemExit(f"G5 FAILED: C1 frac has {len(host)} trades; the registration says {expected}. "
                         "STOP, before any state is joined.")
    return len(host)


def check_reproduce(host: pd.DataFrame) -> tuple[int, float]:
    """G5 (run side): 1,175 trades and ($847) at the OLD mid, before any IBKR cost is applied."""
    n, net = len(host), float(host["net_mid"].sum())
    if n != S.HA_TRADES or round(net) != S.HA_NET_MID_ROUNDED:
        raise SystemExit(f"G5 FAILED: C1 frac gives {n} trades and net {net:,.2f} at the old mid; the registration "
                         f"says {S.HA_TRADES} and ({abs(S.HA_NET_MID_ROUNDED)}). STOP.")
    return n, net


def recost(host: pd.DataFrame, fee: dict, tick_value: dict, ticks: int) -> np.ndarray:
    """sec 2.4: net = gross - (fee + k * tick value) * qty * sides, per trade, from the books' own columns.
    `fee` and `tick_value` map market -> dollars per contract per side (fee table: W15-0033, still open)."""
    f = host["market"].map(fee).to_numpy(dtype=float)
    tv = host["market"].map(tick_value).to_numpy(dtype=float)
    if np.isnan(f).any() or np.isnan(tv).any():
        raise SystemExit("G5 OPEN: no IBKR fee / tick value for some market (W15-0033 has not written them in).")
    return host["gross"].to_numpy(dtype=float) - (f + ticks * tv) * host["qty"].to_numpy(dtype=float) * \
        host["sides"].to_numpy(dtype=float)


# ---------------------------------------------------------------- H-B
def _naive_et(df):
    from strategy.w16.readback import local_naive_et
    return local_naive_et(df.index)


def b1_entry(df_session: pd.DataFrame, date_str: str, *, market: str, range_minutes: int = 30) -> dict:
    """Entry-only mirror of strategy.w16.signals.orb_session. Returns
    {"skipped": bool, "entry": dict | None, "voided": str | None}; entry = date, market, direction (+1/-1), fill_time.
    No stop, target, exit or P&L is computed here."""
    from strategy.w16.sessions import add_minutes, has_valid_open, orb_time_exit
    if not has_valid_open(df_session):
        return {"skipped": True, "entry": None, "voided": None}
    bars = df_session.sort_index()
    t = _naive_et(bars).time
    range_end = add_minutes(dtime(9, 30), range_minutes)
    rb = bars[(t >= dtime(9, 30)) & (t < range_end)]
    hi, lo = float(rb["high"].max()), float(rb["low"].min())
    ex = orb_time_exit(date_str)
    end_min = ex.hour * 60 + ex.minute - 2
    entry_end = dtime(end_min // 60, end_min % 60)
    eb = bars[(t >= range_end) & (t <= entry_end)]
    pos, direction = None, 0
    for i in range(len(eb)):
        c = float(eb["close"].iloc[i])
        if c > hi:
            pos, direction = i, S.LONG
            break
        if c < lo:
            pos, direction = i, S.SHORT
            break
    if pos is None:
        return {"skipped": False, "entry": None, "voided": None}
    fill_idx = bars.index.get_loc(eb.index[pos]) + 1
    if fill_idx >= len(bars):
        return {"skipped": False, "entry": None, "voided": "no bar after trigger to fill on"}
    fill = float(bars["open"].iloc[fill_idx])
    stop = lo if direction == S.LONG else hi
    if (direction == S.LONG and fill <= stop) or (direction == S.SHORT and fill >= stop):
        return {"skipped": False, "entry": None, "voided": "fill already beyond stop (gap through range)"}
    return {"skipped": False, "voided": None,
            "entry": {"date": date_str, "market": market, "direction": direction,
                      "fill_time": bars.index[fill_idx]}}


ENTRY_KEYS = ("date", "market", "direction", "fill_time")


def run_b1_entries(frames: dict, market: str, train_days) -> tuple[pd.DataFrame, dict]:
    """B1 entries over the given (training) session dates. Counts: sessions, skipped, no_trigger, voided, entries."""
    cnt = {"sessions": 0, "skipped": 0, "no_trigger": 0, "voided": 0, "entries": 0}
    rows = []
    for d in sorted(train_days):
        if d not in frames:
            continue
        cnt["sessions"] += 1
        r = b1_entry(frames[d], d, market=market)
        if r["skipped"]:
            cnt["skipped"] += 1
        elif r["voided"]:
            cnt["voided"] += 1
        elif r["entry"] is None:
            cnt["no_trigger"] += 1
        else:
            cnt["entries"] += 1
            rows.append({k: r["entry"][k] for k in ENTRY_KEYS})
    out = pd.DataFrame(rows, columns=list(ENTRY_KEYS))
    if len(out):
        out["date"] = pd.to_datetime(out["date"])
    return out, cnt


def rerun_b1(frames: dict, market: str, train_days) -> pd.DataFrame:
    """P&L side (--run only, never the pre-flight): the frozen engine's full trade records for the given days,
    one row per entered (non-void) trade, with entry/exit prices and the exit reason."""
    from strategy.w16 import signals as SIG
    rows = []
    for d in sorted(train_days):
        if d not in frames:
            continue
        r = SIG.orb_session(frames[d], d, market=market)
        tr = r["trade"]
        if r["skipped"] or tr is None or tr.get("voided"):
            continue
        rows.append(tr)
    return pd.DataFrame(rows)
