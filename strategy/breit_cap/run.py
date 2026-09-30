#!/usr/bin/env python3
"""BREIT-CAP G1 + G2 pre-flight runner (counts only, training side). REGISTERED_breit_cap.md sec 5.

    python -m strategy.breit_cap.run --preflight [--volume-amendment-committed]

G1 first: if any market's held-contract volume coverage is < 99% the runner stops with exit code 3
unless --volume-amendment-committed is given (the PRE-RUN amendment scoring G-volume 'no' for that market
must be committed before the pre-flight is read). No P&L, holdout, seen-window or --limit mode exists.
"""
from __future__ import annotations

import sys
import warnings
from datetime import date

from strategy.breit_cap import preflight as PF
from strategy.futbt import loading as LD
from strategy.futbt import runner_common as RC


def main(argv=None) -> int:
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    argv = list(sys.argv[1:] if argv is None else argv)
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("BREIT-CAP G1/G2 pre-flight (counts only)")
    ap.add_argument("--preflight", action="store_true", required=True)
    ap.add_argument("--volume-amendment-committed", action="store_true")
    ap.add_argument("--no-cl4h", action="store_true", help="skip the CL 4H secondary")
    a = ap.parse_args(argv)
    names, scoped = RC.pick_markets(a.markets)
    arch = RC.archive_path(a.archive)
    frames, notes = LD.load_daily(arch, names)
    cl4h_note = None
    vol = PF.check_volume(frames)
    if vol["failing"] and not a.volume_amendment_committed:
        print("G1 VOLUME COVERAGE FAILS for: " + ", ".join(vol["failing"]))
        for m, c in vol["coverage"].items():
            print(f"  {m:>5}: {100 * c:6.2f}%")
        print("STOP (exit 3): commit the PRE-RUN volume amendment, then re-run with --volume-amendment-committed.")
        return 3
    if not a.no_cl4h and "CL" in names:
        try:
            frames["CL4H"] = LD.load_cl4h(arch)
        except FileNotFoundError as e:
            cl4h_note = (f"CL 4H NOT EVALUATED: 1-hour file not found ({e}). Connect the E: drive "
                         "(or fix the path) and re-run; the daily primary below is unaffected.")
            print(cl4h_note)
    reports = PF.run_all(frames, no_volume=vol["failing"])
    summary = PF.summarize(reports)
    clean = {"volume": vol, "summary": summary,
             "markets": {m: {k: v for k, v in r.items() if k != "entries"} | {"n_entries": len(r["entries"])}
                         for m, r in reports.items()}}
    text = PF.render(reports, summary, vol, scoped=scoped, notes=[f"{m}: {n}" for m, n in notes.items() if n] + ([cl4h_note] if cl4h_note else []))
    stem = f"w15_0022_breit_preflight_{date.today():%Y%m%d}" + ("_scoped" if scoped else "")
    t, j = RC.write_outputs(RC.Path(a.out), stem, text, clean)
    print(text)
    print(f"wrote {t}\nwrote {j}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
