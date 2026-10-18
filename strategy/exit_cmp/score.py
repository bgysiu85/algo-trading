#!/usr/bin/env python3
"""EXIT-CMP sec 10: the eight criteria, paired against B-STOP, FLAT, training, 1 MCL. W15-0053 sub 2."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.chartmark import book as BK
from strategy.exit_cmp import spec as S
from strategy.htf import book as HBK


def paired(df_rule: pd.DataFrame, df_base: pd.DataFrame) -> pd.DataFrame:
    """One row per entry: D = net(rule) - net(B-STOP). Both frames are in the same (entry) order."""
    if len(df_rule) != len(df_base) or not (df_rule["entry_j"].to_numpy() == df_base["entry_j"].to_numpy()).all():
        raise ValueError("the rule and the baseline are not on the same entry set")
    return pd.DataFrame(dict(entry_t=df_rule["entry_t"].to_numpy(), year=df_rule["year"].to_numpy(),
                             net=df_rule["net"].to_numpy() - df_base["net"].to_numpy()))


def year_d(d: pd.DataFrame) -> dict[int, float]:
    return HBK.year_table(d)


def halves(d: pd.DataFrame) -> tuple[float, float]:
    cut = pd.Timestamp(S.HALF_SPLIT)
    return float(d.loc[d["entry_t"] < cut, "net"].sum()), float(d.loc[d["entry_t"] >= cut, "net"].sum())


def criteria(rule_id: str, *, d_mid: pd.DataFrame, d_high: pd.DataFrame, rule_net_mid: float, c_p99: float,
             grid_positive: int | None, trigger_n: int) -> dict:
    """Returns {rows: [...], verdict}. A row is (n, name, value, ok)."""
    tot = float(d_mid["net"].sum())
    yd = year_d(d_mid)
    h1, h2 = halves(d_mid)
    d1, d2 = BK.drop_top(yd, 1), BK.drop_top(yd, 2)
    boot = HBK.bootstrap_by_year(yd, n=S.BOOTSTRAP_N, seed=S.boot_seed(rule_id))
    top_y, share = HBK.top_year_share(yd)
    hi = float(d_high["net"].sum())
    rows = [
        (1, "D > 0 at mid", tot, tot > 0),
        (2, "D > 0 at high friction", hi, hi > 0),
        (3, "D > 0 in both halves (2010-06..2015-12 | 2016-01..2021-12)", (h1, h2), h1 > 0 and h2 > 0),
        (4, "D > 0 after dropping the top-1 and top-2 years", (d1, d2), d1 > 0 and d2 > 0),
        (5, "bootstrap by entry year: D > 0 in >= 95%", boot, bool(boot >= 0.95)),
        (6, "net beats the p99 of C-RANDX", (rule_net_mid, c_p99), bool(rule_net_mid > c_p99)),
        (7, "no single year supplies more than 50% of D", (top_y, share), bool(tot > 0 and share <= 0.5)),
        (8, f"at least {S.GRID_MIN_POSITIVE} of 9 neighbour cells have D > 0", grid_positive,
         None if grid_positive is None else grid_positive >= S.GRID_MIN_POSITIVE),
    ]
    if trigger_n < S.NOT_READ_BELOW:
        verdict = f"NOT READ (trigger fires on {trigger_n} of the entries; fewer than {S.NOT_READ_BELOW})"
    elif any(r[3] is None for r in rows):
        verdict = "INCOMPLETE"
    else:
        verdict = "PASS" if all(r[3] for r in rows) else "FAIL"
    return dict(rows=rows, verdict=verdict, trigger_n=trigger_n)


def trigger_count(rule_id: str, exits: list) -> int:
    names = S.TRIGGER.get(rule_id, ())
    return sum(any(n in x.fired for n in names) for x in exits)
