#!/usr/bin/env python3
"""TSMOM runner. AT-41 (roll cross-check) and coverage; the P/L run is AT-43.

    python -m strategy.tsmom.run rollcheck [--archive E:\\Databento\\GLBX.MDP3]
    python -m strategy.tsmom.run coverage  [--archive ...]
    python -m strategy.tsmom.run report    [--archive ...] [--dump DIR]

`rollcheck` exits 2 when the registered stop rule fires, so nothing chained
after it can run on a calendar that failed. It reads the whole calendar
(including the locked years' EXPIRY DATES, which are exchange facts, not
returns) because the check is about the data, not the strategy; it computes
no price change of any kind.

`coverage` is REGISTERED_tsmom section 3 item 12 on the TRAINING side only
(every date through split_months): bars, first/last session, held-contract
sessions carried forward, rolls, and the date each root has 261 returns.

`report` is AT-43 / W06-0005: REGISTERED_tsmom section 3 and the section 4
verdict, on the TRAINING side only (strategy/tsmom/report.py; amendment E).
`--dump DIR` also writes the verdict book's daily P/L and sides as CSV so the
headline can be re-derived without this code.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common.report_io import emit
from strategy.tsmom import archive as A
from strategy.tsmom import rollcheck as RC
from strategy.tsmom.engine import coverage

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "var" / "reports"


def cmd_rollcheck(archive: Path, out: Path) -> int:
    loaded = A.load_all(archive)
    results, notes = {}, {}
    for r, (_inp, c0, note) in loaded.items():
        tab = RC.compare(c0, loaded[r][0].contracts)
        results[r] = (tab, RC.verdict(tab))
        notes[r] = note
    text = RC.format_report(results, notes)
    emit(text, out, header=f"archive {archive}; dataset {A.DATASET}")
    return 2 if any(v["result"] == "STOP" for _, v in results.values()) else 0


def cmd_coverage(archive: Path, out: Path) -> int:
    loaded = A.load_all(archive)
    cov = coverage({r: v[0] for r, v in loaded.items()})
    emit("TSMOM coverage, TRAINING side (before 2022-01-01)\n" + cov.to_string(), out,
         header=f"archive {archive}; dataset {A.DATASET}")
    return 0


def cmd_report(archive: Path, out: Path, dump: Path | None = None) -> int:
    from strategy.tsmom import report as RP
    manifest = A.read_manifest(archive)
    loaded = A.load_all(archive)
    rep = RP.build({r: v[0] for r, v in loaded.items()},
                   load_notes={r: v[2] for r, v in loaded.items()}, manifest=manifest)
    emit(rep.text, out, header=f"archive {archive}; dataset {A.DATASET}")
    if dump:
        dump.mkdir(parents=True, exist_ok=True)
        b = rep.books["spec"]
        b.pnl_frac.to_csv(dump / "spec_pnl_frac.csv")
        (b.sides[("frac", "roll")] + b.sides[("frac", "rebalance")]).to_csv(dump / "spec_sides_frac.csv")
        b.pos_frac.to_csv(dump / "spec_pos_frac.csv")
        rep.books["bh"].pnl_frac.to_csv(dump / "bh_pnl_frac.csv")
        bb = rep.books["bh"]
        (bb.sides[("frac", "roll")] + bb.sides[("frac", "rebalance")]).to_csv(dump / "bh_sides_frac.csv")
        for e, ib in rep.books["int"].items():
            ib.pnl_int.to_csv(dump / f"int_{int(e)}_pnl.csv")
            (ib.sides[("int", "roll")] + ib.sides[("int", "rebalance")]).to_csv(dump / f"int_{int(e)}_sides.csv")
            ib.pos_int.to_csv(dump / f"int_{int(e)}_pos.csv")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["rollcheck", "coverage", "report"])
    ap.add_argument("--archive", type=Path, default=A.DEFAULT_ARCHIVE)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dump", type=Path, default=None,
                    help="report only: write the verdict book's daily frames as CSV here")
    a = ap.parse_args(argv)
    out = a.out or REPORTS / f"tsmom_{a.command}.txt"
    if a.command == "report":
        return cmd_report(a.archive, a.out or REPORTS / "tsmom_report_training.txt", a.dump)
    return {"rollcheck": cmd_rollcheck, "coverage": cmd_coverage}[a.command](a.archive, out)


if __name__ == "__main__":
    raise SystemExit(main())
