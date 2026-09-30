#!/usr/bin/env python3
"""W15-0025 G6 diagnostic -- WHY did the H-B data check stop? Read-only, training side only, no P&L.

    python -m strategy.otf_gate.diag_g6 --out "D:\\Trading\\Claude outputs\\w15_0025_g6_diag_YYYYMMDD.txt"

For ES and NQ it lists (1) every XNYS trading day the rebuilt CME sessions are missing, with the number of 1-minute
bars found on that calendar day and on the CME label of that day (so a true data gap can be told from a labelling
problem), and (2) every roll switch whose two 1-minute bars are more than 5 minutes apart, with the 1-minute bars
either side (times and instrument ids only). It changes nothing and writes no ledger; the registered rule
(sec 2.3, G6) is untouched -- this only reports what is behind the STOP.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.otf_gate import bars_hb as BB
from strategy.otf_gate import spec as S

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "Claude outputs"


def missing_days(raw: pd.DataFrame) -> list[dict]:
    """Missing XNYS days (all years) with the bar counts found around them."""
    daily, _ = BB.rebuild_daily(raw, strict=False)
    chk = BB.session_check(daily)
    train = BB.cut_training(raw.sort_index())
    lab, _ins = BB.trading_labels(train.index)
    lab_days = pd.DatetimeIndex(lab).strftime("%Y-%m-%d")
    et_days = train.index.tz_convert(BB.ET).strftime("%Y-%m-%d")
    from strategy.w16.sessions import session_date_range
    y0, y1 = int(daily["date"].dt.year.min()), int(daily["date"].dt.year.max())
    have = set(daily["date"].dt.strftime("%Y-%m-%d"))
    first, last = daily["date"].min().strftime("%Y-%m-%d"), daily["date"].max().strftime("%Y-%m-%d")
    out = []
    for d in (d for d in session_date_range(y0, y1) if first <= d <= last):
        if d in have:
            continue
        out.append({"date": d, "dow": pd.Timestamp(d).day_name()[:3],
                    "bars_on_ET_calendar_day": int((et_days == d).sum()),
                    "bars_with_this_CME_label": int((lab_days == d).sum())})
    return out, chk


def wide_switches(raw: pd.DataFrame, around: int = 3) -> list[str]:
    df = BB.cut_training(raw.sort_index())
    sw = BB.find_switches(df)
    bad = sw[~sw["ok"]]
    idcol = BB._id_col(df)
    lines = []
    for _, r in bad.iterrows():
        k = int(r["k"])
        lines.append(f"  switch {r['time_old']} -> {r['time_new']}  ({r['minutes']:.0f} min apart, ids {r['id_old']} -> {r['id_new']})")
        seg = df.iloc[max(0, k - around):k + around]
        for t, row in seg.iterrows():
            lines.append(f"      {t}  id {row[idcol]}  volume {row['volume'] if 'volume' in seg.columns else 'n/a'}")
    return lines


def report(frames: dict) -> str:
    L = ["W15-0025 G6 DIAGNOSTIC -- training side, read-only, no P&L. The registered G6 rule is not changed by this file."]
    for root, raw in frames.items():
        miss, chk = missing_days(raw)
        L.append("")
        L.append(f"{root}: XNYS trading days missing from the rebuilt CME sessions: {len(miss)}"
                 f"   (per year with a shortfall: " + ", ".join(
                     f"{y}: {r['missing']}/{r['xnys_days']}" for y, r in chk["years"].items() if r["missing"]) + ")")
        for m in miss:
            L.append(f"  {m['date']} {m['dow']}  1-min bars on that ET calendar day {m['bars_on_ET_calendar_day']:>5}"
                     f"   bars carrying that CME label {m['bars_with_this_CME_label']:>5}")
        ws = wide_switches(raw)
        L.append(f"{root}: roll switches more than {S.HB_MAX_SWITCH_MINUTES} minutes apart: "
                 f"{sum(1 for x in ws if x.startswith('  switch'))}")
        L.extend(ws)
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    from strategy.otf_gate import run as RUN
    archive = Path(a.archive) if a.archive else RUN.default_archive_hb()
    frames = {r: BB.load_root(archive, r) for r in S.HB_ROOTS}
    text = report(frames)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
