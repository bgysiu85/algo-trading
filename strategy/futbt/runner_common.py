"""Shared plumbing for the CRUDELE-3S / BREIT-CAP pre-flight runners (W15-0022 subitem 5)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from strategy.futbt import loading as LD
from strategy.tl_v0.spec import MARKETS

OUT_DIR = Path(r"D:\Trading\Claude outputs")
REFUSED_FLAGS = ("--pnl", "--backtest", "--holdout", "--limit", "--net", "--gross", "--spend", "--seen")


def refuse_pnl_flags(argv) -> None:
    """The pre-flight has no P&L, holdout or limit mode; any such flag is refused, not ignored."""
    bad = [a for a in argv if a.split("=")[0] in REFUSED_FLAGS]
    if bad:
        sys.stderr.write(f"REFUSED: {bad} -- the G2 pre-flight is counts-only on the training side. "
                         "P&L runs are a separate, later item that needs Ben's read of this pre-flight.\n")
        raise SystemExit(2)


def base_parser(desc: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("--markets", help="comma list, e.g. CL,GC (scoped run, NOT the registered pre-flight)")
    ap.add_argument("--archive", help="archive path (default: the program's futures archive)")
    ap.add_argument("--out", default=str(OUT_DIR), help="output folder")
    return ap


def pick_markets(arg):
    names = list(MARKETS)
    if arg:
        want = [m.strip().upper() for m in arg.split(",")]
        unknown = [m for m in want if m not in MARKETS]
        if unknown:
            raise SystemExit(f"unknown market(s): {unknown}; known: {names}")
        return want, True
    return names, False


def write_outputs(out_dir: Path, stem: str, text: str, payload: dict) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    t, j = out_dir / f"{stem}.txt", out_dir / f"{stem}.json"
    t.write_text(text, encoding="utf-8")
    j.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return t, j


def archive_path(arg):
    return Path(arg) if arg else LD.default_archive()
