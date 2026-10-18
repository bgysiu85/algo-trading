#!/usr/bin/env python3
"""EXIT-CMP G2: parity. B-V1 in HOLD (CHARTMARK-v1 exits unchanged, no time cap) must reproduce the 2,670 recorded v1 trades --
entry / exit timestamps and net per row to the cent -- and the total net of ($13,422) at mid, 1 MCL. W15-0053 sub 2.

    python -m strategy.exit_cmp.parity [--trades-csv PATH]

This is the ONLY module that opens the v1 trades CSV's outcome columns, and only after the code is frozen (the ledger's code hash
must still match). It prints match counts, never a candidate rule's result. A failure stops the study: back to the Research & spec
chat, no outcome is read."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from strategy.chartmark.data import indicators, load_training_frame
from strategy.exit_cmp import book as BKX
from strategy.exit_cmp import entries as EN
from strategy.exit_cmp import ledger as LG
from strategy.exit_cmp import spec as S
from strategy.exit_cmp.walk import Study
from strategy.chartmark_clone.ledger import load_frame_cache
from strategy.futbt import runner_common as RC

REGISTERED_NET = -13422.0


def compare(df: pd.DataFrame, csv: pd.DataFrame) -> dict:
    """Row-by-row comparison of the reproduced trades with the recorded ones."""
    out = dict(n_mine=len(df), n_csv=len(csv))
    if len(df) != len(csv):
        out.update(rows_ok=False, bad=[("count", len(df), len(csv))])
        return out
    bad = []
    for i, (r, c) in enumerate(zip(df.itertuples(), csv.itertuples())):
        if str(r.entry_t) != str(c.entry_t) or str(r.exit_t) != str(c.exit_t) or abs(r.net - c.net) >= 0.005:
            bad.append((i, str(r.entry_t), str(r.exit_t), round(r.net, 4), str(c.entry_t), str(c.exit_t), round(c.net, 4)))
    out.update(rows_ok=not bad, bad=bad[:5], n_bad=len(bad), net_mine=float(df["net"].sum()), net_csv=float(csv["net"].sum()))
    out["total_ok"] = abs(out["net_mine"] - out["net_csv"]) < 0.01 and abs(round(out["net_mine"]) - REGISTERED_NET) < 1
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("EXIT-CMP G2 parity (B-V1 reproduces the v1 trades)")
    ap.add_argument("--trades-csv")
    ap.add_argument("--frame-cache", help="load the training frame from this .npz instead of the archive")
    a = ap.parse_args(argv)
    out = Path(a.out)
    csv_path = Path(a.trades_csv) if a.trades_csv else out / S.TRADES_CSV_NAME
    fr = load_frame_cache(Path(a.frame_cache)) if a.frame_cache else load_training_frame(RC.archive_path(a.archive))
    LG.verify(out, fr)                                   # registration, frozen code and frame must be the pre-flight's
    ind = indicators(fr)
    entries = EN.entry_set(fr, ind)
    EN.check_registered(fr, entries)
    st = Study(fr, ind, entries)
    df = BKX.trade_frame(fr, entries, st.run(S.REFERENCE, "HOLD", cap=None), st.roll_cum, "MCL", "mid")
    csv = pd.read_csv(csv_path)
    r = compare(df, csv)
    ok = r["rows_ok"] and r.get("total_ok", False)
    print(f"G2 parity: reproduced {r['n_mine']} trades, recorded {r['n_csv']}; rows differing: {r.get('n_bad', 'n/a')}; "
          f"total net reproduced ${r.get('net_mine', float('nan')):,.2f} vs recorded ${r.get('net_csv', float('nan')):,.2f} "
          f"(registered (${abs(REGISTERED_NET):,.0f})).")
    for b in r["bad"]:
        print("  first differences:", b)
    if not ok:
        print("G2 FAILS -- stop. Back to the Research & spec chat; no outcome is read.")
        return 1
    LG.mark_parity(out)
    print("G2 PASSES. Ledger updated. NEXT: python -m strategy.exit_cmp.run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
