#!/usr/bin/env python3
"""Start the CHARTMARK-CLONE labelling tool. Stop and resume whenever you like: every decision is saved as you make it.

    python -m strategy.chartmark_clone.label

Opens a matplotlib window. T take / S skip, a reason key, Enter. Close the window (or Ctrl+C here) to stop."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from strategy.chartmark_clone import ledger as LG
from strategy.chartmark_clone import qorder as QO
from strategy.chartmark_clone import spec as S
from strategy.chartmark_clone.build import CACHE, OUT
from strategy.chartmark_clone.chartdata import build_chart_data
from strategy.chartmark_clone.labels import LabelStore, new_sitting_id
from strategy.chartmark_clone.session import App


def load_app(out_dir: Path, cache: Path, sitting_id: str | None = None) -> App:
    out_dir = Path(out_dir)
    fr = LG.load_frame_cache(cache)
    LG.check_inputs(out_dir, fr)                                   # G7: queue / manifest / frame == ledger
    LG.check_labels_open(out_dir)                                  # G7: refuse once the clone is frozen (sub 4)
    man = pd.read_csv(out_dir / S.MANIFEST_FILE, dtype={"candidate_id": str, "decision_t": str})
    q = pd.read_csv(out_dir / S.QUEUE_FILE, dtype={"candidate_id": str, "key": str})
    if set(q["candidate_id"]) != set(man["candidate_id"]) or len(q) != len(man):
        raise LG.LedgerError("queue and manifest do not hold the same candidates -- refusing to start.")
    items = QO.schedule(q)
    store = LabelStore(out_dir / S.LABELS_FILE, items, sitting_id or new_sitting_id())
    return App(out_dir, build_chart_data(fr), man.set_index("candidate_id"), store)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CHARTMARK-CLONE labelling tool")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--cache", default=str(CACHE))
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    app = load_app(Path(a.out), Path(a.cache))
    p = app.store.progress()
    print(f"Labelling tool: already labelled {p['unique']} candidates ({p['takes']} takes). Sitting {app.store.sitting_id}.")
    print("A window opens. T take / S skip, a reason key, Enter. Close the window to stop; nothing is lost.")
    from strategy.chartmark_clone import gui
    try:
        gui.run(app)
    except KeyboardInterrupt:
        pass
    q = app.store.progress()
    print(f"Stopped. Labelled {q['unique']} candidates ({q['takes']} takes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
