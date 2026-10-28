r"""Which tickers still need a run, and how far each got.

    .\.venv\Scripts\python.exe -m desk.status                 # table for today
    .\.venv\Scripts\python.exe -m desk.status --pending --limit 3   # next 3 tickers, space separated
    .\.venv\Scripts\python.exe -m desk.status --show-date          # the US date a run would use
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from desk import config as cfgmod
from desk import pipeline


def stage(rd: Path) -> str:
    """How far this ticker-day got, judged only by which files exist."""
    if (rd / pipeline.DECISION_JSON).exists():
        return "decided"
    done = [n for n, f in pipeline.SEQUENCE if (rd / f).exists()]
    if done:
        return f"in progress (last: {done[-1]})"
    if all((rd / f).exists() for _, f in pipeline.ANALYSTS):
        return "analysts done"
    if (rd / "snapshot.json").exists():
        return "prepared"
    return "not started"


def pending(cfg: dict, date: str, base: Path | None = None) -> list[str]:
    return [t for t in cfg["tickers"]
            if not (cfgmod.run_dir(cfg, date, t, base) / pipeline.DECISION_JSON).exists()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--pending", action="store_true", help="print only pending tickers, space separated")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--show-date", action="store_true", help="print the US market date a run would use, then exit")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = cfgmod.load_config(a.config)
    date = cfgmod.norm_date(a.date) if a.date else cfgmod.default_run_date()
    if a.show_date:
        print(date)
        return 0
    if a.pending:
        p = pending(cfg, date)
        print(" ".join(p[: a.limit] if a.limit else p))
        return 0
    print(f"Desk status for {date} (US date)")
    for t in cfg["tickers"]:
        print(f"  {t:<6} {stage(cfgmod.run_dir(cfg, date, t))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
