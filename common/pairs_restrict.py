#!/usr/bin/env python3
r"""Cut a point-in-time pairs file down to the sessions another run covered.

    python -m common.pairs_restrict --pairs var/state/screen_pairs_pit_itch_v2.json \
        --dates-from var/reports/mc5_full_day_trades_meta.json \
        --out var/state/screen_pairs_pit_itch_v2_fullday.json

WHY THIS EXISTS (REGISTERED_mc5_full_day.md amendment D)

`mc5_full_day` can only run a session that has all three full-day window slices
AND the pre-market one. Four dates in the published universe have the
pre-market pull and no regular-hours pull, so the study's arm A covered 6,378
of the universe's 6,411 symbol-days -- and then failed its own reconciliation
against a figure computed over all 6,411.

That is a POPULATION difference, not a different book, and the fix is to score
the published baseline over the SAME sessions rather than to relax the check.
This module writes that restricted universe; `pit_strategy` run on it produces
the figure arm A must reproduce.

IT ONLY EVER REMOVES. The output is a subset of the input, filtered on date,
with every row byte-identical to the row it came from -- a test asserts both,
because a "restriction" that rewrote a row would hand the reconciliation a
different universe wearing the right name.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def dates_from(path: Path) -> list[str]:
    """The `sessions` list of a study's *_meta.json."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    got = doc.get("sessions")
    if not got:
        sys.exit(f"{path} has no non-empty 'sessions' list")
    return list(got)


def restrict(rows: list[dict], dates) -> list[dict]:
    keep = set(dates)
    return [r for r in rows if r.get("date") in keep]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", required=True)
    p.add_argument("--dates-from", required=True, metavar="META_JSON")
    p.add_argument("--out", required=True)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if Path(a.out.replace("\\", "/")) == Path(a.pairs.replace("\\", "/")):
        sys.exit("--out must not be --pairs: the published universe file is not "
                 "overwritten by a restriction of itself")
    rows = json.loads(Path(a.pairs).read_text(encoding="utf-8"))
    dates = dates_from(Path(a.dates_from))
    out = restrict(rows, dates)
    if not out:
        sys.exit("the restriction kept nothing -- check that the two files "
                 "describe the same universe")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    dropped = sorted({r["date"] for r in rows} - set(dates))
    print(f"{len(out):,} of {len(rows):,} symbol-days kept, over "
          f"{len({r['date'] for r in out}):,} of {len({r['date'] for r in rows}):,} sessions")
    if dropped:
        print(f"  {len(dropped)} date(s) dropped: " + ", ".join(dropped[:12])
              + (" ..." if len(dropped) > 12 else ""))
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
