#!/usr/bin/env python3
"""Price the TSMOM futures pull. ESTIMATE ONLY -- this module cannot spend.

    set DATABENTO_API_KEY=...        (PowerShell: $env:DATABENTO_API_KEY="...")

    python -m common.tsmom_data_price                 # the registered set
    python -m common.tsmom_data_price --with-tn       # + TN, for rates arm (b)
    python -m common.tsmom_data_price --roots ES GC   # a scoped re-price

WHY THIS IS A SEPARATE MODULE FROM common.databento_fetch
----------------------------------------------------------
`databento_fetch` is shaped for equities: it takes a list of (symbol, date)
pairs, groups them BY DATE, and writes one archive file per day. That is the
right shape for 6,564 symbol-days scattered across a year of pre-market windows.

It is the wrong shape for futures. A TSMOM pull is a dozen ROOTS over sixteen
years of continuous daily bars -- twelve range requests, not four thousand
day requests -- and it is symbol-scoped through the `parent` symbology
(`ES.FUT` resolves to every ES contract month) rather than through an explicit
ticker list. Forcing it through the day-grouping path would issue ~4,000
requests to build twelve files and would make the estimate meaningless.

THIS MODULE HAS NO DOWNLOAD PATH. NOT A GUARDED ONE.
-----------------------------------------------------
`PROGRAM_INDEX` section 1: a tool that can spend money states the number before
it spends it. `databento_fetch` satisfies that with an estimate plus --confirm.
This module goes further and satisfies it structurally: it imports
`metadata.get_cost` and `metadata.get_billable_size` and nothing else. There is
no `timeseries.get_range` call anywhere in the file, so there is no flag, typo
or merge that makes it spend. When the number has been confirmed, the pull is
written as its own module under its own registration.

--max-cost (default $5) still aborts, because an estimate that comes back large
is itself a signal that the request is mis-scoped -- which is how the $1,500
ALL_SYMBOLS quote was caught -- and printing it calmly next to a total invites
someone to run the pull anyway.

THE KEY IS NEVER AN ARGUMENT AND IS NEVER PRINTED
--------------------------------------------------
Resolved through `common.secrets_util.resolve` -- the ONE resolver in this repo,
which follows an op:// 1Password reference if that is what the environment
variable holds. It usually is: the README tells you to `setx` a reference, and
`setx` is persistent. A module that reads the variable directly sends that
reference to the vendor and gets back a 401 that reads like a revoked key. This
module did exactly that in its first draft; see `_key`.

A --key flag would put the secret in PowerShell history, so there is none.
Client exceptions are scrubbed before they are shown, because a Telegram token
once leaked out of an exception handler in common/notify.py.

WHAT THE ANSWER IS EXPECTED TO BE, AND WHY IT IS STILL RUN
-----------------------------------------------------------
`ohlcv-1d`, `definition` and `statistics` are L0 schemas, and the $199/month
Standard plan includes 16+ years of L0. So this pull is expected to price at or
near $0.00, the way the XNAS.BASIC extension through 2026-09-17 did. "Expected"
is not a number, `get_cost()` is the only thing that knows Ben's plan, and the
key lives only on his machine -- so the estimate is run there and the figure is
what gets registered.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, timedelta

DATASET = "GLBX.MDP3"

# The instrument set of claude/tsmom_spec_20260917.md section 2.2 -- the FULL-SIZE
# roots. Signals are computed on these; the micros in the comments are the
# execution vehicle only, and most of them did not exist before 2019.
#
# NB: "MCL" in claude/diversifier_candidates_20260911.md section 5.1 means the
# micro crude oil future. In this project MCL is a strategy. Crude is CL here and
# in every TSMOM doc -- see handover section 2.1.
ROOTS: dict[str, str] = {
    "ES": "US large-cap equity      -> MES",
    "RTY": "US small-cap equity      -> M2K",
    "GC": "precious metal           -> MGC",
    "SI": "second precious metal    -> SIL",
    "HG": "base metal               -> MHG",
    "CL": "crude                    -> MCL",
    "NG": "natural gas              -> MNG",
    "6E": "EUR                      -> M6E",
    "6A": "AUD                      -> M6A",
    "6B": "GBP                      -> M6B",
    "6J": "JPY                      -> MJY",
    "ZN": "10-year rates            -> ZN full size (no price-quoted micro)",
}

# Rates arm (b) of spec section 2.3: signal from TN's own history, traded as MTN.
# Off by default -- arm (a) needs only ZN, which is already in ROOTS.
TN_ROOT = {"TN": "Ultra 10-year            -> MTN (arm (b) only)"}

SCHEMAS = ("ohlcv-1d", "definition")

# How many sessions the roll calendar is sampled on, under --scope lean.
# A contract is listed months to years before it expires and stays listed, so a
# monthly grid catches every contract with its expiration date long before the
# roll needs it. Sixteen years is about 190 monthly samples out of ~4,000
# sessions.
DEFINITION_SAMPLES = 190
SESSIONS_PER_YEAR = 252


_RESOLVED: str = ""      # the resolved key, kept only so _scrub can remove it


def _scrub(text: str) -> str:
    """Remove anything that looks like a key from text before it is printed.

    Scrubs the RESOLVED key, not the environment variable's contents. Those are
    different strings on Ben's machine -- the variable holds an op:// reference
    and the key comes out of 1Password -- and scrubbing the reference while
    printing the secret is the wrong way round.
    """
    out = str(text)
    if _RESOLVED:
        out = out.replace(_RESOLVED, "<DATABENTO_API_KEY>")
    return re.sub(r"\bdb-[A-Za-z0-9]{20,}\b", "<DATABENTO_API_KEY>", out)


def _key() -> str:
    """Resolve the Databento key through the ONE resolver this repo has.

    THE DEFECT THIS REPLACES, 2026-09-17. The first draft read
    os.environ["DATABENTO_API_KEY"] and handed whatever it found to the client.
    On Ben's machine that variable holds an op:// 1PASSWORD REFERENCE, set
    persistently with setx, and the vendor answered

        401 auth_authentication_failed

    which reads as an expired subscription or a revoked key and is neither.

    `common.databento_fetch._key` had already hit this, already fixed it, and
    already written the explanation into its own docstring -- and
    `secrets_util.resolve`'s docstring names databento_fetch's environment-only
    reader as the thing its existence is meant to prevent. This module grew the
    same reader anyway, four days later, and produced the same 401.

    That is the shape PROGRAM_INDEX section 1 fixes by fiat elsewhere:
    `holdout.split_sessions` is THE one implementation and a test asserts every
    study calls it, because two studies were written without it. Credential
    resolution now gets the same treatment --
    `tests/strategy/test_tsmom_data_price.py::test_the_key_is_resolved_through_
    secrets_util` refuses a second reader in this module.
    """
    global _RESOLVED
    from common import secrets_util as S

    key = S.resolve("DATABENTO_API_KEY", "Databento API key")
    if not key:
        raise SystemExit(
            "DATABENTO_API_KEY is not set. In PowerShell, either\n"
            '  $env:DATABENTO_API_KEY = "db-..."              (this shell only)\n'
            '  setx DATABENTO_API_KEY "op://Trading/<item>/<field>"'
            "   (persistent, resolved via 1Password)\n"
            "Never a command-line flag -- that puts it in shell history\n"
            "(PROGRAM_INDEX section 1)."
        )
    _RESOLVED = key
    if not key.startswith("db-"):
        # Warn, do not block: the shape of a vendor's key is theirs to change.
        # But a wrong-shaped key produces the same opaque 401 as an unresolved
        # op:// reference, so say the likely reason BEFORE the server does.
        # No part of the value is printed.
        print(f"WARNING: DATABENTO_API_KEY resolved to {len(key)} characters "
              "not beginning 'db-'. If the next call returns 401, that is why.",
              file=sys.stderr)
    return key


def require_databento():
    try:
        import databento  # noqa: F401
    except ImportError:
        raise SystemExit(
            "the databento package is not importable by THIS interpreter:\n"
            f"  {sys.executable}\n"
            "On Windows that is usually the system Python rather than the venv --\n"
            "a terminal can show (.venv) while `python` resolves elsewhere. Use:\n"
            "  D:\\Trading\\.venv\\Scripts\\python.exe -m common.tsmom_data_price"
        )
    import databento
    return databento


def available_range(client) -> tuple[str, str]:
    """The dataset's full history, asked for rather than assumed.

    GLBX.MDP3's start date is a fact about the vendor, not about this project,
    and hard-coding it would be a second source of truth that goes stale in
    silence (PROGRAM_INDEX section 4).
    """
    rng = client.metadata.get_dataset_range(dataset=DATASET)
    start = rng.get("start") or rng.get("start_date")
    end = rng.get("end") or rng.get("end_date")
    return str(start)[:10], str(end)[:10]


def price_one(client, root: str, schema: str, start: str, end: str,
              scope: str = "lean"):
    """Cost and billable size for one root and one schema, at the given scope.

    WHY `lean` IS THE DEFAULT, 2026-09-17. The first whole-set estimate under
    `parent` for both schemas came back 29.030 GiB / $71.62. Diagnosed:

      * ohlcv-1d is $21 of it, and `parent` is only ~3x `continuous` -- so it is
        resolving contract months, not spreads. It is buying the deferred
        months out to 2035 that a front-month strategy never holds.
      * definition is $50 of it, at 28.9 GiB, because it is republished for
        every listed instrument EVERY session. The expiration dates it carries
        are STATIC PER CONTRACT. Sixteen years of daily snapshots to read when
        ESH14 expired is the same fact bought four thousand times.

    `lean` asks for what the strategy reads:

      * bars from `continuous` c.0 and c.1 -- the front and next contract, which
        is what a 5-days-before-expiry roll ever holds. These resolve to real
        instruments, so P/L is still booked on the contract actually held
        (registration section 7) rather than on a synthetic series.
      * the roll calendar from `definition` on a monthly grid.

    Neither changes a number the strategy computes. Both are PRE-RUN amendment
    A of docs/research/REGISTERED_tsmom.md.
    """
    if scope == "full" or schema == "definition":
        kw = dict(dataset=DATASET, schema=schema, symbols=f"{root}.FUT",
                  stype_in="parent", start=start, end=end)
    else:
        kw = dict(dataset=DATASET, schema=schema,
                  symbols=f"{root}.c.0,{root}.c.1", stype_in="continuous",
                  start=start, end=end)

    if scope == "lean" and schema == "definition":
        # Price ONE session and scale, rather than the whole range: the pull
        # will issue DEFINITION_SAMPLES separate single-day requests. Stated as
        # an estimate with its assumption, not passed off as a quote.
        kw["start"] = (date.fromisoformat(end) - timedelta(days=1)).isoformat()
        usd = float(client.metadata.get_cost(**kw)) * DEFINITION_SAMPLES
        nbytes = int(client.metadata.get_billable_size(**kw)) * DEFINITION_SAMPLES
        return usd, nbytes

    usd = float(client.metadata.get_cost(**kw))
    nbytes = int(client.metadata.get_billable_size(**kw))
    return usd, nbytes


# Scopings the diagnostic prices against each other. All metadata lookups, all
# free. The point is to find WHICH axis is responsible for a large total before
# anyone decides whether the total is worth paying -- the same question the
# $1,500 ALL_SYMBOLS quote turned out to be asking.
DIAGNOSTIC_SCOPES = [
    ("ohlcv-1d  parent  all history",
     dict(schema="ohlcv-1d", symbols="{r}.FUT", stype_in="parent", span="full")),
    ("ohlcv-1d  continuous front, all history",
     dict(schema="ohlcv-1d", symbols="{r}.c.0", stype_in="continuous", span="full")),
    ("ohlcv-1d  continuous front+next, all history",
     dict(schema="ohlcv-1d", symbols="{r}.c.0,{r}.c.1", stype_in="continuous", span="full")),
    ("definition  parent  all history",
     dict(schema="definition", symbols="{r}.FUT", stype_in="parent", span="full")),
    ("definition  parent  ONE day",
     dict(schema="definition", symbols="{r}.FUT", stype_in="parent", span="day")),
]


def diagnose(client, root: str, ds_start: str, ds_end: str) -> int:
    """Price one root several ways, so the driver of a large total is visible.

    A total is not a decision. `parent` symbology resolves <ROOT>.FUT to every
    futures instrument sharing that parent -- which on CME includes the listed
    CALENDAR SPREADS, not just the outright contract months, and there are
    orders of magnitude more of those. And `definition` is republished for every
    listed instrument EVERY session, so it scales with (instruments x days)
    while the expiry dates it carries are static per contract and need to be
    read once.

    Either of those turns a megabyte question into a gigabyte one without
    changing a single number the strategy actually uses. This prints them side
    by side rather than inviting anyone to pay the first figure that appears.
    """
    print(f"DIAGNOSTIC -- one root ({root}), several scopings, all free metadata "
          f"lookups.\nNothing here downloads anything.\n")
    print(f"{'scoping':<42}{'billable':>16}{'USD':>10}")
    rows = []
    for label, spec in DIAGNOSTIC_SCOPES:
        if spec["span"] == "full":
            start, end = ds_start, ds_end
        else:
            # A Databento range is [start, end). start == end is EMPTY and
            # returns 422 data_time_range_start_on_or_after_end, which is what
            # the first version of this probe did -- it asked for no days and
            # the vendor said so. One session means [end-1d, end).
            start = (date.fromisoformat(ds_end) - timedelta(days=1)).isoformat()
            end = ds_end
        kw = dict(dataset=DATASET, schema=spec["schema"],
                  symbols=spec["symbols"].format(r=root),
                  stype_in=spec["stype_in"], start=start, end=end)
        try:
            usd = float(client.metadata.get_cost(**kw))
            nbytes = int(client.metadata.get_billable_size(**kw))
        except Exception as e:                       # noqa: BLE001
            print(f"{label:<42}{'FAILED':>16}{'':>10}   {_scrub(e)[:50]}")
            continue
        rows.append((label, nbytes, usd))
        print(f"{label:<42}{nbytes:>16,}{usd:>10.2f}")

    if len(rows) >= 4:
        print(f"\nRead it this way:")
        par = next((r for r in rows if r[0].startswith("ohlcv-1d  parent")), None)
        con = next((r for r in rows if "front+next" in r[0]), None)
        dfull = next((r for r in rows if r[0].startswith("definition  parent  all")), None)
        dday = next((r for r in rows if "ONE day" in r[0]), None)
        if par and con and con[1]:
            ratio = par[1] / con[1]
            print(f"  parent vs continuous on ohlcv-1d: {ratio:,.1f}x more bytes.")
            if ratio > 50:
                print( "    A ratio this large means `parent` is resolving the listed")
                print( "    CALENDAR SPREADS, not just contract months. Scope it down.")
            else:
                print( "    Single digits: `parent` is resolving contract months, which")
                print(f"    is what it should. {ratio:,.1f}x is roughly the deferred months")
                print( "    the strategy never holds -- worth dropping, but not the driver")
                print( "    of a large total. Look at the definition rows instead.")
        if dfull and dday and dday[1]:
            print(f"  definition full history vs one day: {dfull[1] / dday[1]:,.0f}x.")
            print( "    Expiry dates are static per contract. If this ratio is large,")
            print( "    the roll calendar is being bought once per session per")
            print( "    instrument for sixteen years to read a fact that never moves.")
        print(f"\nx{len(ROOTS)} roots for a whole-set figure, roughly.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Estimate the cost of the TSMOM futures pull. Cannot download.")
    ap.add_argument("--roots", nargs="+", metavar="ROOT",
                    help="price only these roots (default: the registered set)")
    ap.add_argument("--with-tn", action="store_true",
                    help="include TN (rates arm (b) of spec section 2.3)")
    ap.add_argument("--schemas", nargs="+", default=list(SCHEMAS))
    ap.add_argument("--start", help="override the start date (default: dataset start)")
    ap.add_argument("--end", help="override the end date (default: today)")
    ap.add_argument("--max-cost", type=float, default=5.0,
                    help="abort above this total, in USD (default 5.00)")
    ap.add_argument("--scope", choices=("lean", "full"), default="lean",
                    help="lean (default): front+next contract bars via continuous "
                         "symbology, and the roll calendar sampled monthly -- what "
                         "the strategy reads. full: every contract month, every "
                         "session, via parent symbology.")
    ap.add_argument("--diagnose", metavar="ROOT", nargs="?", const="ES",
                    help="price ONE root several ways to find what drives a "
                         "large total, then exit (default root: ES)")
    a = ap.parse_args(argv)

    roots = dict(ROOTS)
    if a.with_tn:
        roots.update(TN_ROOT)
    if a.roots:
        unknown = [r for r in a.roots if r not in roots]
        if unknown:
            raise SystemExit(f"not in the registered set: {' '.join(unknown)}\n"
                             f"known: {' '.join(roots)}")
        roots = {r: roots[r] for r in a.roots}

    databento = require_databento()
    client = databento.Historical(_key())

    try:
        ds_start, ds_end = available_range(client)
    except Exception as e:                       # noqa: BLE001
        raise SystemExit(f"dataset range lookup failed: {_scrub(e)}")
    start = a.start or ds_start
    end = a.end or min(ds_end, date.today().isoformat())

    if a.diagnose:
        return diagnose(client, a.diagnose, ds_start, ds_end)

    print(f"ESTIMATE ONLY -- this module has no download path.\n")
    print(f"dataset   {DATASET}")
    print(f"history   {ds_start} .. {ds_end}   (vendor's stated range)")
    print(f"pricing   {start} .. {end}")
    print(f"schemas   {' '.join(a.schemas)}")
    print(f"roots     {len(roots)}   symbology: parent (<ROOT>.FUT = all contract months)\n")

    print(f"scope     {a.scope}" + ("   (front+next contract bars; roll calendar "
          f"sampled on {DEFINITION_SAMPLES} sessions)" if a.scope == "lean"
          else "   (every contract month, every session)") + "\n")
    width = max(len(s) for s in a.schemas)
    print(f"{'root':<6}{'schema':<{width + 2}}{'billable':>14}{'USD':>10}   note")
    total_usd, total_bytes = 0.0, 0
    by_schema: dict[str, list] = {sc: [0.0, 0] for sc in a.schemas}
    by_root: dict[str, float] = {}
    failures = []
    for root, note in roots.items():
        for schema in a.schemas:
            try:
                usd, nbytes = price_one(client, root, schema, start, end, a.scope)
            except Exception as e:               # noqa: BLE001
                failures.append((root, schema, _scrub(e)))
                print(f"{root:<6}{schema:<{width + 2}}{'FAILED':>14}{'':>10}   {_scrub(e)[:60]}")
                continue
            total_usd += usd
            total_bytes += nbytes
            by_schema[schema][0] += usd
            by_schema[schema][1] += nbytes
            by_root[root] = by_root.get(root, 0.0) + usd
            shown = note if schema == a.schemas[0] else ""
            print(f"{root:<6}{schema:<{width + 2}}{nbytes:>14,}{usd:>10.2f}   {shown}")

    print()
    for schema, (usd, nbytes) in by_schema.items():
        # A per-schema subtotal is the line that would have shown, on the first
        # run, that definition was 70% of the bill. The first version printed
        # only per-root rows and one TOTAL, and the driver was invisible.
        print(f"{'  sub':<6}{schema:<{width + 2}}{nbytes:>14,}{usd:>10.2f}"
              f"   {nbytes / 2**30:.3f} GiB")
    print(f"{'TOTAL':<6}{'':<{width + 2}}{total_bytes:>14,}{total_usd:>10.2f}"
          f"   ({total_bytes / 2**30:.3f} GiB uncompressed)")
    if by_root:
        top = sorted(by_root.items(), key=lambda kv: -kv[1])[:5]
        print("\nbiggest roots: " + "  ".join(f"{r} ${u:.2f}" for r, u in top))
    if a.scope == "lean":
        print(f"\nThe definition figure is ONE session priced and multiplied by "
              f"{DEFINITION_SAMPLES}.\nThe pull issues that many single-day requests; "
              "the per-day cost is exact,\nthe sample count is the assumption.")

    if failures:
        print(f"\n{len(failures)} lookup(s) FAILED -- the total above is a LOWER BOUND,")
        print("not the cost of the pull. Do not confirm a spend against it.")

    if total_usd > a.max_cost:
        print(f"\nABORT: ${total_usd:.2f} exceeds --max-cost ${a.max_cost:.2f}.")
        print("A large estimate usually means the request is mis-scoped, not that")
        print("the data is expensive -- the same range once priced at $1,500 with")
        print("symbols=ALL_SYMBOLS and under a cent scoped properly. Check the")
        print("roots and the date range before raising the ceiling.")
        return 2

    print("\nNothing has been downloaded and nothing has been charged.")
    print("Send this total to the TSMOM chat. The pull is written as its own")
    print("module, under its own registration, only after Ben confirms it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
