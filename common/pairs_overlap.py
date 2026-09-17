#!/usr/bin/env python3
"""Two point-in-time universe files, side by side.

    python -m common.pairs_overlap var/state/screen_pairs_pit.json var/state/screen_pairs_pit_itch_p50.json

Registered reading in docs/research/REGISTERED_screen_itch.md §2.2: how much
of the universe the screen picks is the tape rather than the market. Symbol-days
in both, in one only, and for the shared ones how far `first_seen` moved --
the floor every entry is held to, so a name noticed later on one tape is a
different trading opportunity, not the same one on cleaner bars.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.report_io import emit

ET = ZoneInfo("America/New_York")


def load(path: str | Path) -> pd.DataFrame:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["first_seen"] = pd.to_datetime(df["first_seen"], utc=True)
    return df.set_index(["symbol", "date"]).sort_index()


def overlap(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    ia, ib = set(a.index), set(b.index)
    both = sorted(ia & ib)
    out = {"a": len(ia), "b": len(ib), "both": len(both),
           "a_only": len(ia - ib), "b_only": len(ib - ia),
           "jaccard": len(both) / len(ia | ib) if ia | ib else 0.0,
           "sessions_a": a.index.get_level_values("date").nunique(),
           "sessions_b": b.index.get_level_values("date").nunique()}
    if both:
        fa = a.loc[both, "first_seen"]
        fb = b.loc[both, "first_seen"]
        d = (fb.values - fa.values) / np.timedelta64(1, "m")
        out["first_seen_shift_min"] = {"p10": float(np.quantile(d, .10)),
                                       "p50": float(np.quantile(d, .50)),
                                       "p90": float(np.quantile(d, .90)),
                                       "same": int((d == 0).sum()),
                                       "later_on_b": int((d > 0).sum()),
                                       "earlier_on_b": int((d < 0).sum())}
    for tag, df in (("a", a), ("b", b)):
        t = df["first_seen"].dt.tz_convert(ET)
        mins = t.dt.hour * 60 + t.dt.minute
        out[f"knowable_0430_{tag}"] = int((mins <= 4 * 60 + 30).sum())
        out[f"first_seen_p50_{tag}"] = f"{int(mins.median()) // 60:02d}:{int(mins.median()) % 60:02d}"
    return out


def render(o: dict, pa: str, pb: str) -> list[str]:
    L = ["TWO POINT-IN-TIME UNIVERSES", "",
         f"  A  {pa}   {o['a']:,} symbol-days over {o['sessions_a']} sessions",
         f"  B  {pb}   {o['b']:,} symbol-days over {o['sessions_b']} sessions", "",
         f"  in both        {o['both']:,}",
         f"  A only         {o['a_only']:,}",
         f"  B only         {o['b_only']:,}",
         f"  Jaccard        {o['jaccard']:.3f}   (shared / union)", "",
         f"  knowable by 04:30    A {o['knowable_0430_a']:,}   B {o['knowable_0430_b']:,}",
         f"  first_seen median    A {o['first_seen_p50_a']}   B {o['first_seen_p50_b']}", ""]
    s = o.get("first_seen_shift_min")
    if s:
        L += ["  first_seen on the shared symbol-days, B minus A, minutes:",
              f"    p10 {s['p10']:+.0f}   p50 {s['p50']:+.0f}   p90 {s['p90']:+.0f}",
              f"    same {s['same']:,}   later on B {s['later_on_b']:,}   earlier on B {s['earlier_on_b']:,}", ""]
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--out", default="var/reports/pairs_overlap.txt")
    a = p.parse_args(argv)
    o = overlap(load(a.a), load(a.b))
    emit("\n".join(render(o, a.a, a.b)), a.out,
         header=f"common.pairs_overlap  {a.a}  {a.b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
