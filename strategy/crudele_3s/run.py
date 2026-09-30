#!/usr/bin/env python3
"""CRUDELE-3S G2 pre-flight runner (counts only, training side). REGISTERED_crudele_3s.md sec 5.2.

    python -m strategy.crudele_3s.run --preflight

No P&L, holdout, seen-window or --limit mode exists here; those flags are refused.
"""
from __future__ import annotations

import sys
import warnings
from datetime import date

from strategy.crudele_3s import preflight as PF
from strategy.futbt import loading as LD
from strategy.futbt import runner_common as RC


def main(argv=None) -> int:
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    argv = list(sys.argv[1:] if argv is None else argv)
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("CRUDELE-3S G2 pre-flight (counts only)")
    ap.add_argument("--preflight", action="store_true", required=True)
    a = ap.parse_args(argv)
    names, scoped = RC.pick_markets(a.markets)
    arch = RC.archive_path(a.archive)
    frames, notes = LD.load_daily(arch, names)
    rep = PF.run_all(frames)
    clean = PF._clean(rep)
    text = PF.render(clean, scoped=scoped, notes=[f"{m}: {n}" for m, n in notes.items() if n])
    stem = f"w15_0022_crudele_preflight_{date.today():%Y%m%d}" + ("_scoped" if scoped else "")
    t, j = RC.write_outputs(RC.Path(a.out), stem, text, clean)
    print(text)
    print(f"wrote {t}\nwrote {j}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
