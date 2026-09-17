#!/usr/bin/env python3
"""Pull the TSMOM futures archive from Databento. THIS MODULE CAN SPEND.

    set DATABENTO_API_KEY=...       (or an op:// reference; see common.secrets_util)

    python -m common.tsmom_fetch                      # estimate, then STOP
    python -m common.tsmom_fetch --confirm            # estimate, then spend

Registered by `docs/research/REGISTERED_tsmom_fetch.md`. Scope and roll sourcing
are amendment A of `docs/research/REGISTERED_tsmom.md` section 0.1.

WHY THIS IS A SEPARATE MODULE FROM common.tsmom_data_price
-----------------------------------------------------------
`tsmom_data_price` claims it cannot spend, and it backs that claim structurally:
there is no `timeseries.get_range` call in the file and a test scans the AST to
keep it that way. That claim is worth keeping true, so the pull lives here
instead of being added to it behind a flag.

The division is deliberate. Anyone reading `tsmom_data_price` can satisfy
themselves in one grep that it is safe to run. Anyone reading THIS file should
assume it is not.

WHAT IT BUYS, AND WHY IT IS $3.65 AND NOT $71.62
--------------------------------------------------
Measured 2026-09-17, `claude/raw/tsmom_price_20260917.txt`:

    ohlcv-1d       6,254,416 bytes   $1.11     continuous c.0 + c.1
    definition 1,605,203,600 bytes   $2.54     parent, 190 monthly samples
    TOTAL      1,611,458,016 (1.501 GiB)  $3.65

The first scoping asked for every contract month of every root on every session
and came to 29.030 GiB / $71.62, of which $50.52 was `definition` republished
daily for expiry dates that never move. Amendment A has the full reasoning.

BILLING IS ON RETRIEVAL, SO THIS SKIPS WHAT IS ALREADY ON DISK
----------------------------------------------------------------
A file in the archive is free to read forever. Re-running this is free by
construction: every job checks for its output first, and the estimate printed
covers ONLY the jobs that would actually run. An estimate that quotes the whole
pull while intending to download a tenth of it is a number that teaches the
reader to ignore numbers.

SPENDING GUARDS
---------------
  * estimate first, always, and print the total;
  * nothing downloads without --confirm;
  * --max-cost (default $5.00, above the measured $3.65 with room for the
    monthly samples to drift) ABORTS rather than proceeding, because a large
    estimate means a mis-scoped request rather than expensive data -- the same
    range once priced at $1,500 with ALL_SYMBOLS and under a cent scoped right;
  * and the key is resolved through `common.secrets_util`, never read from the
    environment directly. `tsmom_data_price` shipped with its own environment
    reader on 2026-09-17, sent Ben's op:// reference to the vendor as though it
    were a key, and got back a 401 that reads like a revoked subscription.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from common.tsmom_data_price import (DATASET, DEFINITION_SAMPLES, ROOTS,
                                     TN_ROOT, require_databento)

# The archive lives OUTSIDE the repo, beside the XNAS trees, for the reason
# PROGRAM_INDEX section 3 gives: this is expensive, reusable, general-purpose
# market data rather than a project artefact. Resolution order matches
# common.databento_fetch so there is one answer to "where is the archive".
ARCHIVE_CONFIG = Path(".databento_archive")
ARCHIVE_FALLBACK = Path("databento")

BAR_SCHEMA = "ohlcv-1d"
DEF_SCHEMA = "definition"


def default_archive() -> Path:
    import os
    env = os.environ.get("DATABENTO_ARCHIVE")
    if env:
        return Path(env)
    if ARCHIVE_CONFIG.exists():
        line = ARCHIVE_CONFIG.read_text(encoding="utf-8").strip()
        if line:
            return Path(line)
    return ARCHIVE_FALLBACK


def _scrub(text: str) -> str:
    """Never let a key reach a log, however it got into an exception."""
    return re.sub(r"(db-)?[A-Za-z0-9]{20,}", "<redacted>", str(text))


def _key() -> str:
    """Through secrets_util. See the module docstring for what happened when a
    sibling module read the environment variable directly."""
    from common import secrets_util as S

    k = S.resolve("DATABENTO_API_KEY", "Databento API key")
    if not k:
        raise SystemExit(
            "DATABENTO_API_KEY is not set. In PowerShell, either\n"
            '  $env:DATABENTO_API_KEY = "db-..."              (this shell only)\n'
            '  setx DATABENTO_API_KEY "op://Trading/<item>/<field>"'
            "   (persistent, resolved via 1Password)")
    if not k.startswith("db-"):
        print(f"WARNING: DATABENTO_API_KEY resolved to {len(k)} characters not "
              "beginning 'db-'. If the next call returns 401, that is why.",
              file=sys.stderr)
    return k


def bar_path(root_dir: Path, root: str) -> Path:
    return root_dir / DATASET / BAR_SCHEMA / f"{root}.dbn.zst"


def def_path(root_dir: Path, root: str, day: str) -> Path:
    return root_dir / DATASET / DEF_SCHEMA / root / f"{day}.dbn.zst"


def definition_days(start: str, end: str, samples: int = DEFINITION_SAMPLES) -> list[str]:
    """The monthly grid the roll calendar is sampled on.

    One session per calendar month, taken as the 15th (or the nearest earlier
    day the vendor has), which avoids month-end and month-start holidays
    clustering. A contract is listed months to years before it expires and stays
    listed, so any day in the month carries the same expiration dates.

    Deterministic and derived from the range, NOT a count chosen to hit a cost.
    `samples` caps it so the estimate and the pull cannot disagree about how
    many requests there are.
    """
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    days, y, m = [], s.year, s.month
    while (y, m) <= (e.year, e.month) and len(days) < samples:
        d = date(y, m, 15)
        if s <= d <= e:
            days.append(d.isoformat())
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return days


def plan(client, roots: dict, root_dir: Path, start: str, end: str):
    """Every job that would actually run, priced. Jobs already on disk are
    skipped and are NOT in the total."""
    jobs, have = [], 0

    for root in roots:
        out = bar_path(root_dir, root)
        kw = dict(dataset=DATASET, schema=BAR_SCHEMA,
                  symbols=f"{root}.c.0,{root}.c.1", stype_in="continuous",
                  start=start, end=end)
        if out.exists():
            have += 1
            continue
        jobs.append((root, BAR_SCHEMA, out, kw))

    for root in roots:
        for day in definition_days(start, end):
            out = def_path(root_dir, root, day)
            nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
            kw = dict(dataset=DATASET, schema=DEF_SCHEMA, symbols=f"{root}.FUT",
                      stype_in="parent", start=day, end=nxt)
            if out.exists():
                have += 1
                continue
            jobs.append((root, DEF_SCHEMA, out, kw))

    usd, nbytes = 0.0, 0
    for _, _, _, kw in jobs:
        try:
            usd += float(client.metadata.get_cost(**kw))
            nbytes += int(client.metadata.get_billable_size(**kw))
        except Exception as e:                       # noqa: BLE001
            raise SystemExit(f"pricing failed, nothing downloaded: {_scrub(e)}")
    return jobs, usd, nbytes, have


def write_manifest(root_dir: Path, rec: dict) -> Path:
    """What was bought, when, and under which registration.

    PROGRAM_INDEX section 1: every report names its data source and refuses the
    wrong one. A report cannot do that unless the archive says what it is, and
    an assertion in a docstring is not the archive saying anything -- the ORB
    pre-flight printed an EQUS.MINI caveat over XNAS.BASIC numbers and two tests
    pinned the bug.
    """
    p = root_dir / DATASET / "manifest_tsmom.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    prior = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"pulls": []}
    prior["pulls"].append(rec)
    prior["dataset"] = DATASET
    prior["schemas"] = {BAR_SCHEMA: "continuous c.0 + c.1",
                        DEF_SCHEMA: f"parent, {DEFINITION_SAMPLES} monthly samples"}
    prior["registration"] = "docs/research/REGISTERED_tsmom_fetch.md"
    prior["scope_amendment"] = "REGISTERED_tsmom.md section 0.1 amendment A"
    p.write_text(json.dumps(prior, indent=2) + "\n", encoding="utf-8")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull the TSMOM archive. CAN SPEND.")
    ap.add_argument("--roots", nargs="+", metavar="ROOT")
    ap.add_argument("--with-tn", action="store_true",
                    help="include TN (rates arm (b) of tsmom spec section 2.3)")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--start", help="override (default: the dataset's start)")
    ap.add_argument("--end", help="override (default: the dataset's end)")
    ap.add_argument("--max-cost", type=float, default=5.00)
    ap.add_argument("--confirm", action="store_true",
                    help="actually download. Without it, this only estimates.")
    a = ap.parse_args(argv)

    roots = dict(ROOTS)
    if a.with_tn:
        roots.update(TN_ROOT)
    if a.roots:
        unknown = [r for r in a.roots if r not in roots]
        if unknown:
            raise SystemExit(f"not in the registered set: {' '.join(unknown)}")
        roots = {r: roots[r] for r in a.roots}

    databento = require_databento()
    client = databento.Historical(_key())
    root_dir = a.archive or default_archive()

    try:
        rng = client.metadata.get_dataset_range(dataset=DATASET)
    except Exception as e:                           # noqa: BLE001
        raise SystemExit(f"dataset range lookup failed: {_scrub(e)}")
    ds_start = str(rng.get("start") or rng.get("start_date"))[:10]
    ds_end = str(rng.get("end") or rng.get("end_date"))[:10]
    start, end = a.start or ds_start, a.end or ds_end

    print(f"dataset   {DATASET}\narchive   {root_dir}/\n"
          f"range     {start} .. {end}   (vendor: {ds_start} .. {ds_end})\n"
          f"roots     {len(roots)}\n")

    jobs, usd, nbytes, have = plan(client, roots, root_dir, start, end)
    print(f"{len(jobs)} job(s) to run, {have} already on disk and skipped "
          f"(retrieval is what bills; a file on disk is free forever)")
    print(f"estimate  ${usd:.2f}   {nbytes:,} bytes ({nbytes / 2**30:.3f} GiB)\n")

    if not jobs:
        print("Nothing to do. The archive is complete for this range.")
        return 0

    if usd > a.max_cost:
        print(f"ABORT: ${usd:.2f} exceeds --max-cost ${a.max_cost:.2f}.")
        print("The measured figure on 2026-09-17 was $3.65 for the whole set.")
        print("An estimate well above that means the scope moved, not that the")
        print("data got expensive. Re-run common.tsmom_data_price --diagnose")
        print("before raising the ceiling.")
        return 2

    if not a.confirm:
        print("ESTIMATE ONLY. Nothing downloaded, nothing charged.")
        print("Re-run with --confirm to spend this.")
        return 0

    print(f"SPENDING ${usd:.2f}. Downloading {len(jobs)} job(s).\n")
    done = 0
    for root, schema, out, kw in jobs:
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = client.timeseries.get_range(**kw)
            data.to_file(out)
        except Exception as e:                       # noqa: BLE001
            print(f"  {root:<5} {schema:<10} FAILED: {_scrub(e)[:70]}")
            continue
        done += 1
        if done % 25 == 0 or schema == BAR_SCHEMA:
            print(f"  {root:<5} {schema:<10} -> {out.name}   ({done}/{len(jobs)})")

    rec = {
        "pulled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start": start, "end": end, "roots": sorted(roots),
        "jobs_run": done, "jobs_planned": len(jobs),
        "estimated_usd": round(usd, 4), "estimated_bytes": nbytes,
    }
    print(f"\n{done}/{len(jobs)} succeeded.")
    print(f"manifest: {write_manifest(root_dir, rec)}")
    if done < len(jobs):
        print("INCOMPLETE. Re-run: finished jobs are on disk and free to skip.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
