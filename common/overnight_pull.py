#!/usr/bin/env python3
"""One command that pulls everything worth having, unattended.

    $env:DATABENTO_API_KEY = "..."
    python -m common.overnight_pull                 # estimate everything, spend nothing
    python -m common.overnight_pull --confirm       # run it and go to bed

WHY THESE JOBS AND NOT "EVERYTHING"
------------------------------------
"All the data available" is not a target. `mbo` for the US equity universe over
eight years is hundreds of terabytes, Standard grants one MONTH of L2/L3
anyway, and none of it answers a question this project is asking.

What is worth having is everything at **L0** -- ohlcv, definitions, statistics.
Standard gives 8+ years of it, it is genuinely free (measured: 443.8 MB of
daily bars cost $0.0000), and it is the tier every strategy here actually
reads. So the job list is L0 across the datasets that matter, and nothing else.

The largest job by far is full-universe MINUTE bars. That one deserves its own
justification: it SUBSUMES every per-pair fetch this project would otherwise
keep making. The screened candidate list has already changed three times today,
and each change would mean another scoped download. Pull the whole universe
once and no future screen, strategy or date range needs a fetch again.

BUILT TO BE LEFT ALONE
----------------------
Nobody is watching at 2am, so:

  * every job is ESTIMATED before anything downloads, with a grand total, and
    nothing runs without --confirm
  * free disk is checked against the estimate first -- a full disk mid-run is
    the one failure that wastes the whole night
  * a failing job does NOT stop the run; the rest continue and the failure is
    reported at the end
  * every chunk already skips if present, so a re-run resumes for free
  * downloads land on .partial and rename only on success, so an interrupted
    job cannot leave a truncated file that the next run mistakes for complete
  * a report is written to var/reports/ so the morning does not depend on
    scrollback

Each job runs through common.databento_universe, so it inherits the range
clamp, the degraded-day manifest, the symbology archiving and the --max-cost
abort rather than reimplementing any of them.
"""
from __future__ import annotations

import argparse
import io
import re
import shutil
import sys
import time
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from common.databento_fetch import default_archive
from common.report_io import emit


@dataclass
class Job:
    """A full-universe pull, run through common.databento_universe."""
    dataset: str
    schema: str
    start: str
    why: str

    @property
    def label(self) -> str:
        return f"{self.dataset} {self.schema}"


@dataclass
class PairJob:
    """A pull scoped to a pair list, run through common.databento_fetch.

    L1 schemas cannot be taken universe-wide -- tbbo for one year of all US
    equities is roughly 4.5 TB. Scoped to the symbol-days a strategy would
    actually have traded it is a few GB, and it is the only way to have quote
    data at all once the rolling window has moved past these dates.
    """
    dataset: str
    schema: str
    pairs: str
    after: str | None
    why: str

    @property
    def label(self) -> str:
        return f"{self.dataset} {self.schema} (pairs)"


# Ordered cheapest-and-most-useful first, so an overnight run that dies early
# has still delivered the things the plan actually needs next.
JOBS = [
    Job("EQUS.SUMMARY", "ohlcv-1d", "2024-07-01",
        "consolidated daily volume across ALL exchanges -- the honest RVOL "
        "denominator. EQUS.MINI is a partial tape and its volume is not."),
    Job("EQUS.SUMMARY", "statistics", "2024-07-01",
        "consolidated volume normalised on every trade; the same figure "
        "intraday rather than end-of-day."),
    Job("XNAS.BASIC", "ohlcv-1d", "2024-07-01",
        "Nasdaq venues PLUS the FINRA TRFs, so it includes off-exchange "
        "prints. Cross-checks how much volume EQUS.MINI is missing."),
    Job("XNAS.ITCH", "ohlcv-1d", "2018-05-01",
        "eight years of daily bars. Nasdaq-listed only, but it is the deep "
        "history the regime test needs -- build the screen on 2023-2025 and "
        "check it survives a period it was never fitted to."),
    Job("EQUS.MINI", "definition", "2023-03-28",
        "instrument reference data. Carries shares outstanding, which is the "
        "only candidate anywhere for the point-in-time float filter MCL's "
        "universe rule needs and no tier otherwise provides."),
    Job("EQUS.MINI", "ohlcv-1m", "2023-03-28",
        "THE BIG ONE. Minute bars for the whole universe, 3.4 years. Subsumes "
        "every per-pair fetch: no future screen or strategy needs a download "
        "again. Expect tens of GB -- see the disk check."),
]

# L1, and therefore bounded by the ROLLING one-year window. These dates stop
# being free as the window moves, so they are the jobs with real regret risk:
# ohlcv can be re-derived from a cheaper source one day, a historical quote
# cannot be reconstructed from anything.
PAIR_JOBS = [
    PairJob("EQUS.MINI", "tbbo", "var/state/screen_pairs.json", "2025-09-06",
            "quotes for the screened candidates inside the free L1 window. "
            "Extends the crossing-cost measurement from Ben's own 587 "
            "symbol-days to the universe a strategy would actually trade -- "
            "the difference between 'what his fills cost' and 'what the "
            "strategy would pay'."),
]

# Deep minute history. Nasdaq-LISTED only, and large. Behind a flag because it
# is the one job whose size is not obviously worth its narrowness.
DEEP_JOBS = [
    Job("XNAS.ITCH", "ohlcv-1m", "2018-05-01",
        "eight years of MINUTE bars, Nasdaq-listed only. The regime test can "
        "run on daily bars for screening and only needs these to backtest the "
        "survivors -- so this is insurance, not a requirement. Expect it to "
        "dwarf every other job."),
]

def matches(job, patterns) -> bool:
    """Does `job` match any of `patterns`?

    A pattern is `DATASET` or `DATASET:SCHEMA`, case-insensitive. The second
    form exists because a dataset can carry several jobs of wildly different
    size -- EQUS.SUMMARY holds both a 362 MB daily-bar job and a statistics job
    estimated at 2.4 TB -- and selecting by dataset alone cannot separate them.
    """
    for p in patterns:
        p = p.upper()
        ds, sep, sc = p.partition(":")
        if job.dataset.upper() != ds:
            continue
        if not sep or job.schema.upper() == sc:
            return True
    return False


def select(all_jobs, only, skip) -> list:
    """Apply --only then --skip, refusing a pattern that matched nothing.

    A pattern is how someone excludes the one job that would otherwise run for
    days. A typo in it must not read as "nothing to exclude" -- that failure is
    silent, and its cost is the entire night.
    """
    jobs = list(all_jobs)
    for flag, pats in (("--only", only), ("--skip", skip)):
        if not pats:
            continue
        for p in pats:
            if not any(matches(j, [p]) for j in all_jobs):
                sys.exit(f"{flag} {p!r} matched no job. Use DATASET or "
                         "DATASET:SCHEMA, e.g. EQUS.SUMMARY:statistics. "
                         "Available: "
                         + ", ".join(f"{j.dataset}:{j.schema}" for j in all_jobs))
        jobs = ([j for j in jobs if matches(j, pats)] if flag == "--only"
                else [j for j in jobs if not matches(j, pats)])
    return jobs


SIZE_RE = re.compile(r"ESTIMATED SIZE\s*:\s*([\d,\.]+)\s*MB")
COST_RE = re.compile(r"ESTIMATED COST\s*:\s*\$([\d,\.]+)")
TODO_RE = re.compile(r"to download\s*:\s*(\d+)")


class _Tee(io.StringIO):
    """Capture a job's output AND let it through to the terminal as it happens.

    The first version captured into a plain StringIO and printed the lot when
    the job returned. That is fine for a fast job and wrong for this one: the
    planning pass makes two metadata calls per chunk, and XNAS.ITCH alone is
    ~100 monthly chunks back to 2018, so a job can sit silent for minutes.
    On a run designed to be left alone overnight, silence is indistinguishable
    from a hang -- and the whole point is that someone can glance at it and see
    it is alive.
    """

    def __init__(self, target):
        super().__init__()
        # The stream as it was BEFORE redirect_stdout replaced it -- not
        # sys.__stdout__. Using the process's original handle would punch
        # through any outer redirection: a shell `>`, a log wrapper, or
        # pytest's capture, none of which would then see this output.
        self._target = target

    def write(self, text: str) -> int:
        self._target.write(text)
        try:
            self._target.flush()
        except Exception:  # noqa: BLE001 -- flushing is best effort
            pass
        return super().write(text)


def _run(job, archive: str, confirm: bool, max_cost: float) -> tuple[int, str]:
    """Run one job, streaming and capturing its output. Dispatches on type."""
    from common import databento_fetch as FE
    from common import databento_universe as U

    if isinstance(job, PairJob):
        runner = FE.main
        argv = ["--pairs", job.pairs, "--dataset", job.dataset,
                "--schemas", job.schema, "--archive", archive,
                "--max-cost", str(max_cost)]
        if job.after:
            argv += ["--after", job.after]
    else:
        runner = U.main
        argv = ["--dataset", job.dataset, "--schema", job.schema,
                "--start", job.start, "--archive", archive,
                "--max-cost", str(max_cost)]
    if confirm:
        argv.append("--confirm")

    buf = _Tee(sys.stdout)
    try:
        with redirect_stdout(buf):
            rc = runner(argv)
    except SystemExit as e:
        # sys.exit("some message") sets .code to a STRING, not an int -- which
        # is exactly what databento_universe does when --max-cost trips or a
        # dataset is empty. int() on that raises, so the guard firing correctly
        # would itself have taken the whole overnight run down.
        code = e.code
        if isinstance(code, int):
            rc = code
        else:
            if code:
                buf.write(f"\n{code}\n")
            rc = 1
    except Exception as e:             # noqa: BLE001 -- one job must not end the night
        buf.write(f"\nJOB FAILED: {type(e).__name__}: {e}\n")
        rc = 1
    return rc, buf.getvalue()


def _parse(out: str) -> tuple[float, float, int]:
    mb = float(SIZE_RE.search(out).group(1).replace(",", "")) if SIZE_RE.search(out) else 0.0
    usd = float(COST_RE.search(out).group(1).replace(",", "")) if COST_RE.search(out) else 0.0
    todo = int(TODO_RE.search(out).group(1)) if TODO_RE.search(out) else 0
    return mb, usd, todo


def _free_gb(path: Path) -> float:
    p = path
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free / 1e9


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull every L0 dataset worth having")
    ap.add_argument("--archive", default=str(default_archive()),
                    help="archive root (default: %(default)s)")
    ap.add_argument("--max-cost", type=float, default=5.00,
                    help="per job; L0 should be $0.00, so this is a tripwire")
    ap.add_argument("--only", nargs="+", metavar="DATASET[:SCHEMA]",
                    help="run only jobs matching these")
    ap.add_argument("--skip", nargs="+", metavar="DATASET[:SCHEMA]",
                    help="drop jobs matching these, e.g. EQUS.SUMMARY:statistics")
    ap.add_argument("--deep", action="store_true",
                    help="add eight years of Nasdaq-listed MINUTE bars. Large, "
                         "narrow, and insurance rather than a requirement")
    ap.add_argument("--no-quotes", action="store_true",
                    help="skip the L1 quote jobs")
    ap.add_argument("--skip-disk-check", action="store_true")
    ap.add_argument("--confirm", action="store_true",
                    help="actually download; without it this only estimates")
    ap.add_argument("--out", default="var/reports/overnight_pull.txt")
    a = ap.parse_args(argv)

    all_jobs = list(JOBS)
    if not a.no_quotes:
        all_jobs += PAIR_JOBS
    if a.deep:
        all_jobs += DEEP_JOBS
    jobs = select(all_jobs, a.only, a.skip)
    if not jobs:
        sys.exit("every job was filtered out -- nothing to do")

    print("=" * 72)
    print("PLANNING -- nothing downloads in this pass")
    print("=" * 72)

    plan, total_mb, total_usd, total_chunks = [], 0.0, 0.0, 0
    for j in jobs:
        print(f"\n--- {j.label} ---")
        print(f"    {j.why}")
        rc, out = _run(j, a.archive, confirm=False, max_cost=a.max_cost)
        mb, usd, todo = _parse(out)
        total_mb += mb
        total_usd += usd
        total_chunks += todo
        plan.append((j, mb, usd, todo, rc))

    lines = ["OVERNIGHT PULL", ""]
    lines.append(f"{'dataset / schema':<28} {'chunks':>7} {'MB':>12} {'USD':>10}")
    lines.append("-" * 60)
    for j, mb, usd, todo, rc in plan:
        flag = "" if rc == 0 else "   <-- planning error"
        lines.append(f"{j.label:<28} {todo:>7} {mb:>12,.1f} {usd:>10.4f}{flag}")
    lines.append("-" * 60)
    lines.append(f"{'TOTAL':<28} {total_chunks:>7} {total_mb:>12,.1f} {total_usd:>10.4f}")

    free = _free_gb(Path(a.archive))
    need = total_mb / 1000.0
    lines.append("")
    lines.append(f"uncompressed estimate   {need:,.1f} GB  (billed on this)")
    lines.append(f"on disk, zstd, roughly  {need/5:,.1f} - {need/3:,.1f} GB")
    lines.append(f"free space              {free:,.1f} GB")
    print("\n" + "\n".join(lines))

    if total_usd > 0:
        print(f"\nNOTE: ${total_usd:.4f} is not zero. L0 should be free on "
              "Standard; check which job is charging before confirming.")

    # The one failure that wastes a whole night. Compressed is what lands, but
    # guard on a pessimistic third rather than the optimistic fifth.
    want = need / 3
    if not a.skip_disk_check and free < want * 1.3:
        emit("\n".join(lines) + "\n\nABORTED: insufficient free disk.", a.out,
             header="common.overnight_pull  PLAN ONLY -- aborted on disk")
        sys.exit(f"\nABORTED: needs roughly {want:,.1f} GB on disk and {free:,.1f} GB "
                 "is free. Free some space, or use --only to take the daily "
                 "jobs tonight and the minute bars another time. "
                 "--skip-disk-check overrides.")

    if not a.confirm:
        emit("\n".join(lines), a.out,
             header="common.overnight_pull  PLAN ONLY -- re-run with --confirm")
        print("\nDry run. Re-run with --confirm to download.")
        return 0

    print("\n" + "=" * 72)
    print("DOWNLOADING -- safe to walk away")
    print("=" * 72)

    results, t0 = [], time.time()
    for j, _mb, _usd, todo, _rc in plan:
        if not todo:
            results.append((j, 0, "already complete"))
            continue
        print(f"\n--- {j.label} ---", flush=True)
        t = time.time()
        rc, out = _run(j, a.archive, confirm=True, max_cost=a.max_cost)
        mins = (time.time() - t) / 60
        wrote = re.search(r"wrote (\d+) chunk", out)
        n = int(wrote.group(1)) if wrote else 0
        results.append((j, n, "ok" if rc == 0 else f"FAILED (rc={rc})"))
        print(f"    {n} chunk(s) in {mins:.1f} min", flush=True)

    lines += ["", "RESULTS", ""]
    for j, n, status in results:
        lines.append(f"  {j.label:<28} {n:>4} chunk(s)   {status}")
    bad = [r for r in results if r[2].startswith("FAILED")]
    lines.append("")
    lines.append(f"total elapsed {(time.time()-t0)/60:.0f} min")
    if bad:
        lines.append(f"{len(bad)} job(s) FAILED -- re-running this command "
                     "skips everything already on disk, so it resumes for free.")
    else:
        lines.append("all jobs completed.")

    emit("\n".join(lines), a.out, header="common.overnight_pull")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
