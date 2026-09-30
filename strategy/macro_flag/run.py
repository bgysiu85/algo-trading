#!/usr/bin/env python3
"""MFLAG-v1 runner, TRAINING SIDE ONLY. W15-0023 step 4.

    python -m strategy.macro_flag.run --preflight     # counts only, no P&L loaded
    python -m strategy.macro_flag.run --run           # P&L; refuses unless the pre-flight cleared 60 flagged

Host books: Claude outputs\\tl_v1_backtest_trades_20260929.csv (W15-0020). Sessions come from the TL-v0 loader
(training rows only, cut at 2022-01-01 before any bar is built). No --holdout, --limit, --spend or --seen exists:
those are refused. The holdout is spent by a later, separate step and only on an eight-of-eight pass.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from strategy.macro_flag import books as BK
from strategy.macro_flag import flag as F
from strategy.macro_flag import preflight as PF
from strategy.macro_flag import spec as S
from strategy.macro_flag import study as ST

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "Claude outputs"
BOOKS = OUT_DIR / "tl_v1_backtest_trades_20260929.csv"
CALENDAR = ROOT / "strategy" / "macro_events" / "macro_event_calendar.csv"
REFUSED = ("--holdout", "--limit", "--spend", "--seen", "--markets", "--window", "--cells")


def load_sessions(archive, names, loader=None):
    if loader is None:
        from strategy.tl_v0 import bars as B
        from strategy.tl_v0.spec import MARKETS
        from strategy.tsmom import archive as A
        A.read_manifest(archive)
        loader = lambda n: B.load_market(archive, MARKETS[n])
    return {n: pd.DatetimeIndex(loader(n)[0].frame["date"]) for n in names}


def default_archive() -> Path:
    from strategy.tl_v1.run import default_archive as da
    return da()


def latest_preflight(out_dir: Path) -> Path | None:
    hits = sorted(out_dir.glob("w15_0023_mflag_preflight_*.json"))
    return hits[-1] if hits else None


def require_preflight(out_dir: Path, books: Path, calendar: Path) -> dict:
    pj = latest_preflight(out_dir)
    if pj is None:
        raise SystemExit("REFUSED: no pre-flight on disk. Run --preflight first (sec 5, G2).")
    rec = json.loads(pj.read_text(encoding="utf-8"))
    if rec["books_sha256"] != PF.sha256(books) or rec["calendar_sha256"] != PF.sha256(calendar):
        raise SystemExit(f"REFUSED: {pj.name} was made on different books or a different calendar. Re-run --preflight.")
    if rec["stop"] or rec["flagged"] < S.MIN_FLAGGED:
        raise SystemExit(f"REFUSED: the pre-flight flagged {rec['flagged']} < {S.MIN_FLAGGED}. The counts are the "
                         "finding (sec 5 stop rule); back to Ben before any P&L.")
    return rec


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    bad = [a for a in argv if a.split("=")[0] in REFUSED]
    if bad:
        sys.stderr.write(f"REFUSED: {bad} -- the registered sample, window and cells are fixed (sec 6, 7).\n")
        return 2
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--preflight", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--books", type=Path, default=BOOKS)
    ap.add_argument("--calendar", type=Path, default=CALENDAR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    a = ap.parse_args(argv)
    cal = F.load_calendar(a.calendar)
    if a.preflight:
        books = BK.read_books(a.books, with_pnl=False)
        sessions = load_sessions(a.archive or default_archive(), list(S.MARKETS))
        rep = PF.run(books, sessions, cal)
        text = PF.render(rep)
        a.out_dir.mkdir(parents=True, exist_ok=True)
        stem = a.out_dir / f"w15_0023_mflag_preflight_{a.stamp}"
        stem.with_suffix(".txt").write_text(text, encoding="utf-8")
        stem.with_suffix(".json").write_text(json.dumps(PF.clean(rep, a.books, a.calendar), indent=1, default=str),
                                             encoding="utf-8")
        print(text)
        print(f"wrote {stem}.txt / .json")
        return 0
    require_preflight(a.out_dir, a.books, a.calendar)
    books = BK.read_books(a.books, with_pnl=True)
    sessions = load_sessions(a.archive or default_archive(), list(S.MARKETS))
    R = ST.analyse(books, sessions, cal)
    text = ST.render(R)
    stem = a.out_dir / f"w15_0023_mflag_v1_training_{a.stamp}"
    stem.with_suffix(".txt").write_text(text, encoding="utf-8")
    R["counts"].to_csv(f"{stem}_counts.csv", index=False, encoding="utf-8")
    R["flagged_trades"].to_csv(f"{stem}_flagged_trades.csv", index=False, encoding="utf-8")
    print(text)
    print(f"wrote {stem}.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
