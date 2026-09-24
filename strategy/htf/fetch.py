#!/usr/bin/env python3
"""Price, then pull, CL 1-hour bars for HTF-Ben v0. THIS MODULE CAN SPEND.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.fetch            # estimate, then STOP
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.fetch --confirm  # estimate, then spend

Registered by `docs/research/REGISTERED_htf_ben_v0.md` sec 2.1 (board W15-0002).

WHAT IT BUYS
------------
One request: GLBX.MDP3 `ohlcv-1h`, symbols `CL.c.0,CL.c.1` (continuous, calendar
rank), 2010-06-06 -> the dataset's end. c.0 is the held contract (the TSMOM roll
cross-check, AT-41, already found c.0's roll dates agree with the registered rule
for CL); c.1 is bought beside it so the roll gap can be read on the roll session.

Written to  <archive>/GLBX.MDP3/ohlcv-1h/CL.dbn.zst,  beside the owned `ohlcv-1d`
tree and never inside it, so nothing the TSMOM / TL-v0 readers open is touched.

WHY IT REUSES common.tsmom_fetch
--------------------------------
That module already carries the guards this project learned the hard way: the key
is resolved through `common.secrets_util` (an op:// reference once reached the
vendor as a key and came back as a 401), pricing retries only transient gateway
errors, and exception text is scrubbed of anything key-shaped. Re-implementing
them here would be a second copy to keep in step.

SPENDING GUARDS
---------------
  * estimate first, always, and print it;
  * nothing downloads without --confirm;
  * --max-cost (default $5.00) ABORTS: a large estimate means a mis-scoped request
    (e.g. ALL_SYMBOLS, or the parent symbol), not expensive data;
  * a file already on disk is never re-requested: billing is on retrieval, so a
    re-run is free and prints "nothing to do".

It does not read the bars. The G1 read-back (REGISTERED sec 5.1) does that.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from common.tsmom_data_price import DATASET, require_databento
from common.tsmom_fetch import _key, _price, _retry, _scrub, default_archive

SCHEMA = "ohlcv-1h"
ROOT = "CL"
SYMBOLS = f"{ROOT}.c.0,{ROOT}.c.1"
STYPE_IN = "continuous"
START = "2010-06-06"          # REGISTERED_htf_ben_v0 sec 6: training starts here
MAX_COST = 5.00


def bar_path(root_dir: Path) -> Path:
    return Path(root_dir) / DATASET / SCHEMA / f"{ROOT}.dbn.zst"


def manifest_path(root_dir: Path) -> Path:
    return Path(root_dir) / DATASET / "manifest_htf.json"


def request(start: str, end: str) -> dict:
    """The one request, in one place, so the test can pin its scope."""
    return dict(dataset=DATASET, schema=SCHEMA, symbols=SYMBOLS,
                stype_in=STYPE_IN, start=start, end=end)


def dataset_end(client) -> str:
    try:
        rng = client.metadata.get_dataset_range(dataset=DATASET)
    except Exception as e:                               # noqa: BLE001
        raise SystemExit(f"dataset range lookup failed: {_scrub(e)}")
    return str(rng.get("end") or rng.get("end_date"))[:10]


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser(description="Pull CL ohlcv-1h for HTF-Ben. CAN SPEND.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--end", help="override (default: the dataset's end)")
    ap.add_argument("--max-cost", type=float, default=MAX_COST)
    ap.add_argument("--confirm", action="store_true",
                    help="actually download. Without it, this only estimates.")
    a = ap.parse_args(argv)

    root_dir = a.archive or default_archive()
    out = bar_path(root_dir)
    print(f"dataset   {DATASET}\nschema    {SCHEMA}\nsymbols   {SYMBOLS} ({STYPE_IN})\n"
          f"target    {out}")

    if out.exists():
        print("\nAlready on disk. Nothing to do, nothing charged.")
        return 0

    if client is None:
        databento = require_databento()
        client = databento.Historical(_key())

    end = a.end or dataset_end(client)
    kw = request(START, end)
    print(f"range     {START} .. {end}\n")
    try:
        usd, nbytes = _retry(lambda: _price(client, kw))
    except Exception as e:                               # noqa: BLE001
        raise SystemExit(f"pricing failed -- nothing downloaded: {_scrub(e)}")
    print(f"estimate  ${usd:.2f}   {nbytes:,} bytes ({nbytes / 2**20:.1f} MiB)")

    if usd > a.max_cost:
        print(f"\nABORT: ${usd:.2f} exceeds --max-cost ${a.max_cost:.2f}.")
        print("Two continuous symbols of hourly bars should cost well under that.")
        print("An estimate above it means the scope moved. Nothing downloaded.")
        return 2

    if not a.confirm:
        print("\nESTIMATE ONLY. Nothing downloaded, nothing charged.")
        print("Re-run with --confirm to spend this.")
        return 0

    print(f"\nSPENDING ${usd:.2f}. Downloading.")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    try:
        data = _retry(lambda: client.timeseries.get_range(**kw))
        data.to_file(tmp)
    except Exception as e:                               # noqa: BLE001
        raise SystemExit(f"download failed -- nothing kept: {_scrub(e)}")
    # Only a finished download takes the real name, so an interrupted pull can
    # never be mistaken for a complete one by the "already on disk" check.
    tmp.replace(out)

    rec = {"pulled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "dataset": DATASET, "schema": SCHEMA, "symbols": SYMBOLS,
           "stype_in": STYPE_IN, "start": START, "end": end,
           "estimated_usd": round(usd, 4), "estimated_bytes": nbytes,
           "file": str(out), "file_bytes": out.stat().st_size,
           "registration": "docs/research/REGISTERED_htf_ben_v0.md", "board": "W15-0002"}
    mp = manifest_path(root_dir)
    mp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(f"done      {out}  ({rec['file_bytes']:,} bytes)\nmanifest  {mp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
