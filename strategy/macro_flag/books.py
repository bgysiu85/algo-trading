"""Reads the host books CSV. The count-only pre-flight can not load a P&L column (sec 5, G2)."""
from __future__ import annotations

import pandas as pd

from strategy.macro_flag import spec as S

KEY_COLS = ("market", "spec", "share", "sizing", "equity", "entry_date", "entry_j")
PNL_COLS = ("net_low", "net_mid", "net_high")

HOSTS = {   # name -> (spec, share, sizing, equity)
    "C1 frac $22,129": ("C1", "single", "frac", 22129.0),
    "C1 int $100k": ("C1", "single", "int", 100000.0),
    "C1 int $500k": ("C1", "single", "int", 500000.0),
    "TL-v1 v1 ens frac": ("v1", "sleeve", "frac", 22129.0),
}
PRIMARY_HOST = "C1 frac $22,129"


def read_books(path, *, with_pnl: bool) -> pd.DataFrame:
    cols = list(KEY_COLS) + (list(PNL_COLS) if with_pnl else [])
    df = pd.read_csv(path, usecols=cols, encoding="utf-8", parse_dates=["entry_date"])
    return df


def host(df: pd.DataFrame, name: str) -> pd.DataFrame:
    spec, share, sizing, eq = HOSTS[name]
    m = (df["spec"] == spec) & (df["share"] == share) & (df["sizing"] == sizing) & (df["equity"] == eq)
    return df.loc[m].reset_index(drop=True)


def check_books_reproduce(h: pd.DataFrame) -> tuple[int, float]:
    """G5: C1 frac at mid = ($847) on 1,175 trades, before any flag is applied."""
    n, net = len(h), float(h["net_mid"].sum())
    if n != S.HOST_TRADES or round(net) != S.HOST_NET_MID_ROUNDED:
        raise SystemExit(f"G5 FAILED: C1 frac books give {n} trades and net {net:,.2f} at mid; the registration "
                         f"says {S.HOST_TRADES} and ({abs(S.HOST_NET_MID_ROUNDED)}). STOP, before any flag.")
    return n, net
