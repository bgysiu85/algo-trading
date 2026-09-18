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
import time
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

    One session per calendar month, the 15th, stepped BACK to the Friday when
    the 15th is a Saturday or Sunday. A contract is listed months to years
    before it expires and stays listed, so any session in the month carries the
    same expiration dates -- which day it is does not matter, only that it IS a
    session.

    THE BUG THIS EXISTS FOR, 2026-09-18. The first version took the 15th
    unconditionally. **55 of the 190 samples land on a weekend**, the third one
    being 2010-08-15, a Sunday. A one-day window over a non-session day has
    nothing to resolve, and the vendor answered

        422 symbology_invalid_request -- None of the symbols could be resolved

    on the first live run, which reads like a wrong symbol or a wrong scope and
    is neither. Both this docstring and REGISTERED_tsmom_fetch section 1 already
    SAID the grid stepped off non-sessions. Neither the code nor a test did.
    That is the second time in two days a property was asserted in prose and not
    implemented (see common/tsmom_holdout._normalise) and it is
    PROGRAM_INDEX section 5: a report must read its own inputs, not assert them.

    Weekends are handled here because they are known in advance. HOLIDAYS are
    not -- the exchange calendar is not in hand -- so `plan` retries a
    still-unresolvable day forward and reports any month it cannot place.

    Deterministic and derived from the range, NOT a count chosen to hit a cost.
    """
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    days, y, m = [], s.year, s.month
    while (y, m) <= (e.year, e.month) and len(days) < samples:
        d = date(y, m, 15)
        while d.weekday() >= 5:              # Sat=5, Sun=6 -> step back to Friday
            d -= timedelta(days=1)
        if s <= d <= e:
            days.append(d.isoformat())
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return days


def _is_symbology_miss(e: Exception) -> bool:
    """A day with no session, as opposed to a request that is actually wrong.

    Narrow on purpose. Every other failure still aborts the run: a blanket
    retry would turn a mis-scoped request into a slow one instead of a loud one.
    """
    t = str(e)
    return "symbology_invalid_request" in t or "could not be resolved" in t.lower()


# Gateway hiccups, as opposed to anything about the request. A 504 on one of
# 2,292 calls used to abort the whole run; now it is slept on and retried.
TRANSIENT = ("504", "502", "503", "429", "timed out", "timeout",
             "connection reset", "connection aborted", "temporarily unavailable")

# Module-level so a test can replace it. A test that can reach the real
# time.sleep is a test that can hang the suite, which one mutation duly did.
_SLEEP = time.sleep


def _is_transient(e: Exception) -> bool:
    t = str(e).lower()
    return any(k in t for k in TRANSIENT)


def _price(client, kw: dict):
    return (float(client.metadata.get_cost(**kw)),
            int(client.metadata.get_billable_size(**kw)))


def _retry(fn, *, attempts: int = 4, sleep=None):
    """Run fn, retrying ONLY a transient gateway failure, with backoff.

    Narrow on purpose, for the same reason `_is_symbology_miss` is: a blanket
    retry turns a mis-scoped request into a slow failure instead of a loud one.
    """
    nap = sleep or _SLEEP
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:                       # noqa: BLE001
            if _is_transient(e) and i < attempts - 1:
                nap(2 ** i)
                continue
            raise


def plan(client, roots: dict, root_dir: Path, start: str, end: str):
    """Every job that would actually run, and what it would cost.

    WHY THE DEFINITION COST IS SAMPLED RATHER THAN SUMMED, 2026-09-18.
    The first version priced every job individually: 12 roots x 190 monthly
    samples = 2,280 metadata round trips, plus 12 for the bars, BEFORE a single
    byte is downloaded. At a few hundred milliseconds each that is ten minutes
    of pricing in which any one transient failure aborts everything. It did:

        pricing failed on NG definition 2023-01-13 -- nothing downloaded:
        504 The remote gateway timed out.

    That was call 1,304 of 2,292. Nothing was lost, and nothing could ever
    finish either.

    So definition is priced the way `common.tsmom_data_price --scope lean`
    priced it, and the way the registered $3.65 was produced: ONE representative
    session per root, multiplied by the number of sessions still to fetch. Same
    methodology as the registered figure, 24 calls instead of 2,292. The
    per-session cost is exact; the count is arithmetic. Bars are one call each
    regardless, so they are still summed.

    Jobs already on disk are skipped and are NOT in the total -- billing is on
    retrieval, so the printed estimate describes only work that will happen.
    """
    jobs, have = [], 0
    usd, nbytes = 0.0, 0

    for root in roots:
        out = bar_path(root_dir, root)
        if out.exists():
            have += 1
            continue
        kw = dict(dataset=DATASET, schema=BAR_SCHEMA,
                  symbols=f"{root}.c.0,{root}.c.1", stype_in="continuous",
                  start=start, end=end)
        try:
            u, n = _retry(lambda kw=kw: _price(client, kw))
        except Exception as e:                       # noqa: BLE001
            raise SystemExit(
                f"pricing failed on {root} {BAR_SCHEMA} {start}..{end} "
                f"({kw['symbols']}, stype_in={kw['stype_in']}) "
                f"-- nothing downloaded: {_scrub(e)}")
        jobs.append((root, BAR_SCHEMA, out, kw))
        usd += u
        nbytes += n

    days = definition_days(start, end)
    late: dict[str, str] = {}
    for root in roots:
        todo = []
        for day in days:
            out = def_path(root_dir, root, day)
            if out.exists():
                have += 1
                continue
            nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
            kw = dict(dataset=DATASET, schema=DEF_SCHEMA, symbols=f"{root}.FUT",
                      stype_in="parent", start=day, end=nxt)
            todo.append((root, DEF_SCHEMA, out, kw))
        if not todo:
            continue

        sample, first_i = _first_resolvable(client, todo, root)
        if sample is None:
            raise SystemExit(
                f"pricing failed on {root} {DEF_SCHEMA}: NO session in "
                f"{todo[0][3]['start']}..{todo[-1][3]['start']} could be "
                "resolved -- nothing downloaded. That is not a late listing, "
                "it is a wrong root.")
        if first_i:
            late[root] = todo[first_i][3]["start"]
            todo = todo[first_i:]
        u, n = sample
        usd += u * len(todo)
        nbytes += n * len(todo)
        jobs += todo

    if late:
        # COVERAGE, printed in the same pass as the cost. PROGRAM_INDEX section
        # 4 requires it beside the P/L; it is just as necessary beside a price,
        # because a root that starts seven years late is not the instrument the
        # registration described.
        print("\nLATE LISTINGS -- these roots have no GLBX history at the "
              "dataset's start:")
        for r, d in sorted(late.items()):
            missing = (date.fromisoformat(d) - date.fromisoformat(start)).days / 365.25
            print(f"  {r:<5} first resolvable session {d}   "
                  f"({missing:.1f} years after {start})")
        print("  The warm-up rule (261 returns) already keeps these out of the "
              "book until they have\n  history; what changes is that the book "
              "has FEWER MARKETS in its early years.\n  Recorded in the "
              "manifest and in REGISTERED_tsmom_fetch section 1.4.")

    return jobs, usd, nbytes, have, late


def _first_resolvable(client, todo, root):
    """(priced sample, index of the first session that resolves) for one root.

    WHY THIS EXISTS, 2026-09-18. The third live run stopped at

        pricing failed on RTY definition: none of the first four monthly
        samples could be resolved -- nothing downloaded

    RTY did not exist on CME Globex in 2010. Russell 2000 futures were listed on
    ICE; CME relisted them for trade date 2017-07-10 (CME SER-7960), so
    RTY.FUT has no GLBX history for about seven of the sixteen years.

    Selection rule 3 of `claude/tsmom_spec_20260917.md` section 2.1 ASSERTS that
    every root "has continuous GLBX.MDP3 daily history from the dataset's
    start". For RTY that is false and was never checked -- the third property in
    two days asserted in prose and not verified.

    So a root's first session is DISCOVERED rather than assumed: the first four
    samples, then a yearly stride, then a scan within the year that hit. All
    metadata lookups, all free. A root that resolves immediately costs one call.
    """
    for i, cand in enumerate(todo[:4]):
        try:
            return _retry(lambda kw=cand[3]: _price(client, kw)), i
        except Exception as e:                       # noqa: BLE001
            if not _is_symbology_miss(e):
                raise SystemExit(
                    f"pricing failed on {root} {DEF_SCHEMA} "
                    f"{cand[3]['start']} -- nothing downloaded: {_scrub(e)}")

    hit = None
    for i in range(0, len(todo), 12):                # yearly stride
        try:
            _retry(lambda kw=todo[i][3]: _price(client, kw))
            hit = i
            break
        except Exception as e:                       # noqa: BLE001
            if not _is_symbology_miss(e):
                raise SystemExit(
                    f"pricing failed on {root} {DEF_SCHEMA} "
                    f"{todo[i][3]['start']} -- nothing downloaded: {_scrub(e)}")
    if hit is None:
        return None, 0

    for i in range(max(0, hit - 11), hit + 1):       # narrow to the month
        try:
            return _retry(lambda kw=todo[i][3]: _price(client, kw)), i
        except Exception as e:                       # noqa: BLE001
            if not _is_symbology_miss(e):
                raise
    return None, 0


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

    jobs, usd, nbytes, have, late = plan(client, roots, root_dir, start, end)
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
    done, failed = 0, []
    unplaced: list[tuple[str, str]] = []
    for root, schema, out, kw in jobs:
        out.parent.mkdir(parents=True, exist_ok=True)
        placed, broke = False, False
        # Weekends were removed when the grid was built. HOLIDAYS are not
        # knowable here -- the exchange calendar is not in hand -- so a
        # definition day that will not resolve moves forward up to three days.
        for shift in (range(4) if schema == DEF_SCHEMA else range(1)):
            k, dest = dict(kw), out
            if shift:
                d = (date.fromisoformat(kw["start"]) + timedelta(days=shift)).isoformat()
                k["start"] = d
                k["end"] = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
                dest = def_path(root_dir, root, d)
                if dest.exists():
                    placed = True
                    break
            try:
                data = _retry(lambda k=k: client.timeseries.get_range(**k))
                data.to_file(dest)
            except Exception as e:                   # noqa: BLE001
                if schema == DEF_SCHEMA and _is_symbology_miss(e):
                    continue
                failed.append((root, schema, k.get("start"), _scrub(e)[:60]))
                broke = True
                break
            done += 1
            placed = True
            if done % 50 == 0 or schema == BAR_SCHEMA:
                print(f"  {root:<5} {schema:<10} -> {dest.name}   ({done}/{len(jobs)})")
            break
        if not placed and not broke and schema == DEF_SCHEMA:
            unplaced.append((root, kw["start"][:7]))

    if unplaced:
        # Reported, never silent. A month with no roll-calendar sample is a hole
        # in the thing the roll rule reads, and a run that quietly drops a few
        # is indistinguishable from one that drops a year.
        print(f"\n{len(unplaced)} month(s) had no resolvable session within 4 "
              f"days of the 15th:")
        for r, mon in unplaced[:12]:
            print(f"  {r} {mon}")
        if len(unplaced) > 12:
            print(f"  ... and {len(unplaced) - 12} more")
        share = len(unplaced) / max(1, len(roots) * len(definition_days(start, end)))
        if share > 0.02:
            print(f"WARNING: {share:.1%} of monthly samples unplaceable, above "
                  "the 2% the registration allows. The roll calendar has holes; "
                  "do not run the engine on this archive until it is explained.")
    if failed:
        print(f"\n{len(failed)} job(s) FAILED:")
        for r, sc, d, msg in failed[:10]:
            print(f"  {r:<5} {sc:<10} {d}  {msg}")

    rec = {
        "pulled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start": start, "end": end, "roots": sorted(roots),
        "jobs_run": done, "jobs_planned": len(jobs),
        "estimated_usd": round(usd, 4), "estimated_bytes": nbytes,
        # A root that starts years late is a coverage fact a report must be able
        # to READ, not one it has to be told.
        "late_listings": late,
    }
    print(f"\n{done}/{len(jobs)} succeeded.")
    print(f"manifest: {write_manifest(root_dir, rec)}")
    if done < len(jobs):
        print("INCOMPLETE. Re-run: finished jobs are on disk and free to skip.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
