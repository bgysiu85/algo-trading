#!/usr/bin/env python3
"""CHARTMARK-CLONE builder: manifest + queue + repeats + frame cache + ledger. W15-0050 sub 2 (gates G1, G2, G7).
COUNTS AND ORDER ONLY -- no price, exit or P&L is computed or reported here.

    python -m strategy.chartmark_clone.build

Re-runs the CHARTMARK-v1 base long engine on the training frame (CL 1H, cut before 2022-01-01), reconstructs the
buy-stop level for each of the 2,670 fills, checks the fill timestamps against the v1 trades file (entry_t column only),
writes the outputs, and records the SHA-256 of the queue in the ledger BEFORE any label can exist. It refuses to run a
second time: the queue is fixed once written."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from strategy.chartmark import spec as V1
from strategy.chartmark_clone import ledger as LG
from strategy.chartmark_clone import manifest as MF
from strategy.chartmark_clone import qorder as QO
from strategy.chartmark_clone import spec as S

REPO = Path(__file__).resolve().parents[2]
OUT = Path(r"D:\Trading\Claude outputs")
CACHE = REPO / "var" / S.FRAME_CACHE_FILE
REPORT_FILE = f"clone_build_report_{S.ID}.txt"


def write_csv(df: pd.DataFrame, path: Path, float_format=None) -> None:
    df.to_csv(path, index=False, lineterminator="\n", encoding="utf-8", float_format=float_format)


def build(fr, ind, trades, out_dir: Path, cache_path: Path, trades_csv: Path, *, repo_root: Path = REPO,
          check_registered: bool = True, log=print) -> dict:
    out_dir = Path(out_dir)
    clash = [p for p in (out_dir / S.MANIFEST_FILE, out_dir / S.QUEUE_FILE, out_dir / S.LEDGER_FILE, Path(cache_path))
             if p.exists()]
    if clash:
        raise LG.LedgerError(f"already built ({[str(p) for p in clash]}): the queue is fixed once written; never rebuilt.")
    m, info = MF.build_manifest(fr, ind, trades, V1.BASE)
    if check_registered:
        MF.check_registered_counts(info)
    MF.check_against_trades_csv(m, MF.read_entry_times(trades_csv))
    q = QO.build_queue(m)
    items = QO.schedule(q)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(m, out_dir / S.MANIFEST_FILE, float_format="%.6f")
    write_csv(q, out_dir / S.QUEUE_FILE)
    LG.save_frame_cache(fr, cache_path)
    led = LG.write_ledger(out_dir, fr=fr, info=info, n_queue=len(q), n_seq=len(items), repo_root=repo_root)
    text = report(m, q, items, info, led)
    (out_dir / REPORT_FILE).write_text(text, encoding="utf-8")
    log(text)
    return dict(manifest=m, queue=q, items=items, info=info, ledger=led)


def report(m: pd.DataFrame, q: pd.DataFrame, items, info: dict, led: dict) -> str:
    qm = q.merge(m[["candidate_id", "year", "daily_trend"]], on="candidate_id")
    L = [f"{S.STUDY} -- build report (counts and order only; no price, exit or P&L)", "",
         f"fills in the pool: {info['n']} (registered {S.POOL_N})   per year: {info['per_year']}",
         f"daily trend F1: up {info['up']}  down {info['down']}  (of which warm-up counted as down: {info['f1_warmup']})",
         f"queue: {len(q)} candidates; presentations incl. repeats: {len(items)} "
         f"({sum(i.is_repeat for i in items)} repeats, first one after the 110th new candidate)", "",
         "Queue prefix check -- candidates per year in the first 500 / 1,000 of the queue:"]
    for k in (500, 1000):
        c = Counter(qm.head(k)["year"])
        L.append(f"  first {k}: " + "  ".join(f"{y}:{c.get(y, 0)}" for y in sorted(info["per_year"])))
    c = Counter(qm.head(500)["daily_trend"])
    L.append(f"  first 500 by daily trend: up {c.get(1, 0)}  down {c.get(-1, 0)}")
    L += ["", f"queue_sha256    {led['queue_sha256']}", f"manifest_sha256 {led['manifest_sha256']}",
          f"frame_sha256    {led['frame_content_sha256']}  ({led['n_frame_bars']} 1H bars)",
          f"git commit at build: {led['git_commit']}", "",
          "NEXT: commit the code + these files, then start the labelling tool (python -m strategy.chartmark_clone.label)."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    from strategy.futbt import runner_common as RC
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("CHARTMARK-CLONE builder (manifest, queue, ledger)")
    ap.add_argument("--trades-csv", help="the v1 trades file (only its entry_t column is read)")
    ap.add_argument("--cache", default=str(CACHE), help="frame cache path (default var/, gitignored)")
    a = ap.parse_args(argv)
    from strategy.chartmark.data import indicators, load_training_frame
    arch = RC.archive_path(a.archive)
    out = Path(a.out)
    csv_path = Path(a.trades_csv) if a.trades_csv else out / S.TRADES_CSV_NAME
    if not csv_path.exists():
        raise SystemExit(f"trades file not found: {csv_path}")
    fr = load_training_frame(arch)
    ind = indicators(fr)
    print(f"training frame: {fr.n} 1H bars {fr.ny[0]} .. {fr.ny[-1]}")
    trades = MF.simulate_pool(fr, ind, V1.BASE)
    build(fr, ind, trades, out, Path(a.cache), csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
