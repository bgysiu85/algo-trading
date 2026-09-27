#!/usr/bin/env python3
"""Price, then pull, ES/NQ 1-minute bars for the W16 session-baselines study.
THIS MODULE CAN SPEND.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.fetch            # estimate, then STOP
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.fetch --confirm  # estimate, then spend

Registered by `docs/research/REGISTERED_w16_session_baselines.md` sec 6.1
(gate G1, board W16-0003 subitem 2).

WHAT IT BUYS
------------
Four files: for each of ES and NQ, `ohlcv-1m` (what the three baselines trade
on) and `ohlcv-1d` (bought only so `strategy.w16.readback` has an
independently-sourced daily close to check the 1-minute rebuild against --
the same purpose CL's owned `ohlcv-1d` serves for HTF-Ben's G1). Symbols are
the volume-led continuous front month, `ES.v.0` / `NQ.v.0` -- picked over
`c.0` (calendar rank) because index futures roll to the next quarter about
eight days before expiry, and a calendar-ranked front would trade the thin
expiring contract through roll week (sec 2 of the registration). Dataset
`GLBX.MDP3`, 2010-06-06 -> the pull date.

Written to `<archive>/GLBX.MDP3/w16_session/<schema>/<ROOT>.dbn.zst` -- its
own subtree, so the TSMOM and HTF-Ben (W15) files under the same archive root
are never touched (sec 6.1: "Stored ... in a folder of its own").

WHY IT REUSES common.tsmom_fetch AND common.tsmom_data_price
--------------------------------------------------------------
Same reason `strategy.htf.fetch` gives: the key is resolved through
`common.secrets_util` (an op:// reference once reached the vendor as a key
and came back as a 401), pricing retries only transient gateway errors, and
exception text is scrubbed of anything key-shaped. Re-implementing them here
would be a second copy to keep in step.

SPENDING GUARDS
---------------
  * estimate first, always, for every file not already on disk, and printed
    as one total before anything downloads;
  * nothing downloads without --confirm;
  * --max-cost (default $50.00, the registration's own ceiling, sec 6.1:
    "If the price is above $50, stop and go back to Ben") ABORTS -- a
    request at or under that is what four continuous-symbol files of
    fifteen-plus years should cost; well above it means the scope moved,
    not that ES/NQ minute bars got expensive;
  * a file already on disk is never re-requested: billing is on retrieval,
    so a re-run only prices and buys what is still missing, and prints
    "nothing to do" when nothing is.

It does not read the bars. The G1 read-back (`strategy.w16.readback`,
REGISTERED sec 0 gate G1 / sec 6.1) does that.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from common.tsmom_data_price import DATASET, require_databento
from common.tsmom_fetch import _key, _price, _retry, _scrub, default_archive

ROOTS = ("ES", "NQ")
SCHEMAS = ("ohlcv-1m", "ohlcv-1d")
STYPE_IN = "continuous"
START = "2010-06-06"          # REGISTERED_w16_session_baselines sec 2 / sec 6.1
MAX_COST = 50.00              # the registration's own ceiling, sec 6.1
ARCHIVE_SUBDIR = "w16_session"
BOARD = "W16-0003"
REGISTRATION = "docs/research/REGISTERED_w16_session_baselines.md"


def bar_path(root_dir: Path, root: str, schema: str) -> Path:
    return Path(root_dir) / DATASET / ARCHIVE_SUBDIR / schema / f"{root}.dbn.zst"


def manifest_path(root_dir: Path) -> Path:
    return Path(root_dir) / DATASET / ARCHIVE_SUBDIR / "manifest_w16_sb.json"


def request(root: str, schema: str, start: str, end: str) -> dict:
    """The one request shape, in one place, so a test can pin its scope."""
    return dict(dataset=DATASET, schema=schema, symbols=f"{root}.v.0",
                stype_in=STYPE_IN, start=start, end=end)


def dataset_end(client) -> str:
    try:
        rng = client.metadata.get_dataset_range(dataset=DATASET)
    except Exception as e:                               # noqa: BLE001
        raise SystemExit(f"dataset range lookup failed: {_scrub(e)}")
    return str(rng.get("end") or rng.get("end_date"))[:10]


def plan(client, root_dir: Path, start: str, end: str):
    """Every (root, schema) file that would actually run, and what it costs.

    Priced and listed independently per file (4 calls, at most) rather than
    combined into one request, so a file already on disk is skipped without
    pricing it, and the printed total describes only the bytes that will
    actually move -- the same "billing is on retrieval" rule `tsmom_fetch`
    and `strategy.htf.fetch` follow.
    """
    jobs, have = [], 0
    usd, nbytes = 0.0, 0
    for root in ROOTS:
        for schema in SCHEMAS:
            out = bar_path(root_dir, root, schema)
            if out.exists():
                have += 1
                continue
            kw = request(root, schema, start, end)
            try:
                u, n = _retry(lambda kw=kw: _price(client, kw))
            except Exception as e:                       # noqa: BLE001
                raise SystemExit(
                    f"pricing failed on {root} {schema} {start}..{end} "
                    f"-- nothing downloaded: {_scrub(e)}")
            jobs.append((root, schema, out, kw))
            usd += u
            nbytes += n
    return jobs, usd, nbytes, have


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser(
        description="Price, then pull, ES/NQ ohlcv-1m + ohlcv-1d for W16. CAN SPEND.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--end", help="override (default: the dataset's end)")
    ap.add_argument("--max-cost", type=float, default=MAX_COST)
    ap.add_argument("--confirm", action="store_true",
                    help="actually download. Without it, this only estimates.")
    a = ap.parse_args(argv)

    root_dir = a.archive or default_archive()
    print(f"dataset   {DATASET}\nschemas   {' '.join(SCHEMAS)}\n"
          f"roots     {' '.join(ROOTS)} (v.0, {STYPE_IN})\n"
          f"target    {Path(root_dir) / DATASET / ARCHIVE_SUBDIR}/")

    if client is None:
        databento = require_databento()
        client = databento.Historical(_key())

    missing = any(not bar_path(root_dir, r, s).exists() for r in ROOTS for s in SCHEMAS)
    end = a.end or (dataset_end(client) if missing else START)
    print(f"range     {START} .. {end}\n")

    jobs, usd, nbytes, have = plan(client, root_dir, START, end)
    print(f"{len(jobs)} job(s) to price/pull, {have} already on disk and skipped")
    print(f"estimate  ${usd:.2f}   {nbytes:,} bytes ({nbytes / 2**20:.1f} MiB)\n")

    if not jobs:
        print("Nothing to do. Nothing charged.")
        return 0

    if usd > a.max_cost:
        print(f"ABORT: ${usd:.2f} exceeds --max-cost ${a.max_cost:.2f}.")
        print("REGISTERED_w16_session_baselines.md sec 6.1: above $50, stop and")
        print("go back to Ben rather than spend. An estimate this large usually")
        print("means the scope moved (a wrong symbol or a wider date range),")
        print("not that ES/NQ minute bars got expensive. Nothing downloaded.")
        return 2

    if not a.confirm:
        print("ESTIMATE ONLY. Nothing downloaded, nothing charged.")
        print("Post this total on W16-0003 and re-run with --confirm to spend it.")
        return 0

    print(f"SPENDING ${usd:.2f}. Downloading {len(jobs)} job(s).\n")
    done, failed = [], []
    for root, schema, out, kw in jobs:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        try:
            data = _retry(lambda kw=kw: client.timeseries.get_range(**kw))
            data.to_file(tmp)
        except Exception as e:                           # noqa: BLE001
            failed.append((root, schema, _scrub(e)[:80]))
            if tmp.exists():
                tmp.unlink()
            continue
        # Only a finished download takes the real name, so an interrupted pull
        # can never be mistaken for a complete one by the "already on disk"
        # check (strategy.htf.fetch's own guard, same reasoning here).
        tmp.replace(out)
        done.append((root, schema, out))
        print(f"  {root:<3} {schema:<10} -> {out}")

    if failed:
        print(f"\n{len(failed)} job(s) FAILED, nothing kept for them:")
        for r, sc, msg in failed:
            print(f"  {r:<3} {sc:<10}  {msg}")

    rec = {
        "pulled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset": DATASET, "schemas": list(SCHEMAS), "roots": list(ROOTS),
        "stype_in": STYPE_IN, "start": START, "end": end,
        "estimated_usd": round(usd, 4), "estimated_bytes": nbytes,
        "files_pulled": [str(p) for _, _, p in done],
        "files_failed": [f"{r} {sc}" for r, sc, _ in failed],
        "registration": REGISTRATION, "board": BOARD,
    }
    mp = manifest_path(root_dir)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(f"\n{len(done)}/{len(jobs)} succeeded.\nmanifest  {mp}")

    if failed:
        print("INCOMPLETE. Re-run: finished files are on disk and free to skip.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
