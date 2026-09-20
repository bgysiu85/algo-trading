#!/usr/bin/env python3
"""AT-41: the roll calendar read two ways, and the registered stop rule.

REGISTERED_tsmom_fetch section 5, threshold fixed before the numbers:

    More than 2% of rolls disagreeing by more than one session, on any single
    root, stops the run. Below that, every disagreement is listed in the report
    and the registered `definition` date is used.

The two readings:
  (a) the `definition` schema's expiration for each contract;
  (b) the sessions on which Databento's `c.0` (nearest expiry) changes
      instrument in the bars.

Databento's c.0 is the nearest-expiring contract, so it should move to the next
contract on the first session AFTER the old one's expiration date. For every
contract expiring inside the root's own bar history, the check compares that
expected session with the session c.0 actually moved. A contract that expired
in range but was never c.0, or never left c.0, is a disagreement with no
session count (counted as > 1).

This checks the CALENDAR DATA. It does not check which contract is held, which
amendment C changed for five roots (REGISTERED_tsmom section 0.2, last para).
A late-listed root is only checked inside its own history: its bars start
where its listing starts, so a missing pre-listing year cannot appear here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STOP_PCT = 2.0          # registered, REGISTERED_tsmom_fetch section 5
TOLERANCE_SESSIONS = 1  # "by more than one session"


def compare(c0: pd.Series, contracts: pd.DataFrame) -> pd.DataFrame:
    """One row per contract expiring strictly inside the c.0 history.

    `c0`: index = sessions (weekdays), value = contract key held as c.0.
    `contracts`: symbol, expiration.
    Columns: symbol, expiration, expected (session), observed (session or NaT),
    diff_sessions (observed - expected, in sessions; NaN if unobserved).
    """
    c0 = c0.sort_index()
    sess = pd.DatetimeIndex(c0.index)
    first, last = sess[0], sess[-1]
    exp = contracts.drop_duplicates("symbol").set_index("symbol")["expiration"]
    exp = pd.to_datetime(exp).dt.normalize()
    inside = exp[(exp >= first) & (exp < last)].sort_values()

    change = c0.ne(c0.shift(1))
    change.iloc[0] = False
    left_on = {}                      # symbol -> first session it is no longer c.0
    for t in sess[change.values]:
        prev = c0.iloc[sess.get_loc(t) - 1]
        left_on.setdefault(prev, t)

    rows = []
    for sym, e in inside.items():
        k = sess.searchsorted(e, side="right")        # first session after expiry date
        expected = sess[k] if k < len(sess) else pd.NaT
        observed = left_on.get(sym, pd.NaT)
        if pd.notna(observed) and pd.notna(expected):
            d = int(sess.get_loc(observed)) - int(k)
        else:
            d = np.nan
        rows.append({"symbol": sym, "expiration": e.date(),
                     "expected": expected, "observed": observed, "diff_sessions": d})
    return pd.DataFrame(rows)


def verdict(table: pd.DataFrame) -> dict:
    n = len(table)
    off = table["diff_sessions"].isna() | (table["diff_sessions"].abs() > TOLERANCE_SESSIONS)
    bad = int(off.sum())
    pct = 100.0 * bad / n if n else 0.0
    return {"rolls_compared": n, "disagree_gt1": bad, "pct": pct,
            "any_disagreement": int((table["diff_sessions"].fillna(99) != 0).sum()),
            "result": "STOP" if pct > STOP_PCT else "PASS"}


def format_report(results: dict[str, tuple[pd.DataFrame, dict]], notes: dict) -> str:
    lines = ["TSMOM AT-41 -- roll calendar cross-check (REGISTERED_tsmom_fetch section 5)",
             f"stop rule: > {STOP_PCT:.0f}% of rolls disagreeing by > "
             f"{TOLERANCE_SESSIONS} session on any single root",
             "reading (a): definition expiration -> expected c.0 change on the next session",
             "reading (b): session on which c.0 changes instrument in the bars",
             "", f"{'root':<5} {'rolls':>6} {'>1 sess':>8} {'%':>7} {'any':>5}  result"]
    stop = False
    for root, (tab, v) in results.items():
        lines.append(f"{root:<5} {v['rolls_compared']:>6} {v['disagree_gt1']:>8} "
                     f"{v['pct']:>6.2f}% {v['any_disagreement']:>5}  {v['result']}")
        stop |= v["result"] == "STOP"
    lines += ["", "OVERALL: " + ("STOP -- the run does not proceed" if stop else
                               "PASS -- the registered definition dates are used"), ""]
    lines.append("Every disagreement (diff = observed - expected, in sessions):")
    any_listed = False
    for root, (tab, _) in results.items():
        d = tab[tab["diff_sessions"].fillna(99) != 0]
        for r in d.itertuples():
            any_listed = True
            obs = r.observed.date() if pd.notna(r.observed) else "never"
            exp_ = r.expected.date() if pd.notna(r.expected) else "-"
            diff = "n/a" if pd.isna(r.diff_sessions) else f"{int(r.diff_sessions):+d}"
            flag = "  > 1" if (pd.isna(r.diff_sessions) or abs(r.diff_sessions) > 1) else ""
            lines.append(f"  {root:<4} {r.symbol:<12} expires {r.expiration}  "
                         f"expected {exp_}  observed {obs}  diff {diff}{flag}")
    if not any_listed:
        lines.append("  none")
    lines += ["", "Load notes (Sunday UTC stubs dropped, unmapped ids, point values):"]
    for root, n in notes.items():
        lines.append(f"  {root:<4} files={','.join(n['files'])} sunday_dropped="
                     f"{n['sunday_rows_dropped']} unmapped={n['unmapped_rows']} "
                     f"({n['unmapped_pct']:.2f}%) pv_mismatch={n['point_value_mismatch'] or 'none'}")
        for rev in n.get("expiration_revisions", []):
            lines.append(f"       expiration revised: {rev}  (latest used)")
    return "\n".join(lines)
