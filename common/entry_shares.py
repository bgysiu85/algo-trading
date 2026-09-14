#!/usr/bin/env python3
r"""Does shares outstanding separate the winners from the losers?

    python -m common.entry_shares --jobs 8
    python -m common.entry_shares --strategy mcl --limit 40

PRE-REGISTERED, AND THIS BLOCK WAS WRITTEN BEFORE THE FIRST RUN
---------------------------------------------------------------
The claim being tested: **a lower share count at entry predicts a better net
per trade.** It is the low-float thesis the scanner is built on, and it has
never been measured on this universe because the number was not available.

The decision rule, fixed in advance:

    CLEARS      the bucket's net per trade is positive after $4.26 friction,
                in BOTH halves, and still positive after dropping the five
                best trades in that bucket.
    SEPARATES   the buckets run monotonically the same way in both halves and
                the ends differ by more than friction, without any bucket
                clearing.
    NOTHING     everything else.

Anything short of CLEARS changes no rule. `entry_features` has already run 88
buckets across 22 features and produced 0 of 22; the prior here is not neutral.

WHY THIS FEATURE AND NOT A TWENTY-THIRD PRICE FEATURE
-----------------------------------------------------
Every one of those 22 features is a function of the same minute tape the entry
is taken from, so they are 22 views of one object and their joint failure is
less surprising than 22 independent failures would be. Shares outstanding is
the first thing tried that comes from somewhere else entirely -- a filing, not
a print -- which is the only reason to expect it to behave differently.

THE CONTROL THAT COMES FIRST
----------------------------
28.9% of the universe's symbol-days have no knowable share count: no CIK
(19.8%), a filer that never tagged the concept (5.5%), or nothing filed yet as
at the session (3.7%). Those are not missing at random -- the unmatched are
disproportionately the delisted microcaps this strategy trades.

So before any bucket is read, this reports the net per trade on covered
symbol-days against uncovered ones. If they differ materially, every bucket
below is conditioned on a biased subset, and the report says so rather than
letting the reader assume otherwise.

KNOWN AND STALE ARE NOT ONE POPULATION
--------------------------------------
A figure filed 30 days before the session and one filed 4,880 days before it
are both "the latest public number", and only one of them is likely to still
be true. They are bucketed separately and together; **if the two disagree, no
verdict is issued** -- the standing rule for a halves disagreement, applied to
a stratum split for the same reason.

WHAT THIS IS NOT
----------------
Not float. EDGAR publishes shares OUTSTANDING, an upper bound, and on the
names this trades the two differ by an order of magnitude. Not a rule: no
filter is applied anywhere here, and the trades are exactly the ones the
strategy took.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

from common.entry_features import QUANTILES, buckets, monotone, why_not_bucketable
from common.report_io import emit

ET = ZoneInfo("America/New_York")
QTY = 100

# The three published frictions, as everywhere else in this project.
FRICTIONS = (("$1.00", 1.00), ("$4.26", 4.26), ("$8.92", 8.92))
MEASURED_FRICTION = 4.26

# Drop-top-N, the standing robustness check: a bucket whose whole result rests
# on five trades is not a property of the bucket.
DROP = 5

# A difference in net per trade between the covered and uncovered populations
# larger than this makes the covered subset unrepresentative, and says so.
BIAS_TOLERANCE = MEASURED_FRICTION

# The scanner's own thresholds, in shares. Reported ALONGSIDE the quantile
# buckets and never instead of them: round numbers are already a fitted choice,
# and quantile edges come from the data. They are here because a rule, if one
# ever came of this, would have to be stated at a number a screener can take.
FIXED_EDGES = (0, 5e6, 10e6, 20e6, 50e6, 100e6, 500e6, float("inf"))

ASOF = "var/edgar/universe_shares.csv"
PAIRS = "var/state/screen_pairs_pit.json"

# The published trade count for MCL over this universe, from
# claude/pit_strategy_result_20260914.md. The loop below must reproduce it: a
# module that measures a DIFFERENT 3,955 trades under the same caveat is the
# defect entry_excursion shipped with and had to be corrected for.
PUBLISHED_TRADES = {"mcl": 3_955}


# --- the tape ---------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    """One session's trades: symbol, date, net. Module-level and picklable.

    Deliberately lighter than `entry_split.run_day` -- no excursions, no
    features -- because the only thing joined here is a per-symbol-day figure.
    The POPULATION must still be identical, which is why the warm-up frames and
    `build_frame` come from `pit_strategy` rather than being rebuilt: MACD is an
    EMA with unbounded memory, so a single day's slice produces a different book
    and reports it under the same caveat.
    """
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe, strategy = args
    mod, extra = engine(strategy)
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, [], f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, [], ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)
    out: list[dict] = []
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        try:
            trades = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                          not_before=first_seen_time(rec),
                                          **extra)
        except Exception:                                   # noqa: BLE001
            continue
        for t in trades:
            gross = (t.exit_price - t.entry_price) * QTY
            out.append({"symbol": rec["symbol"], "date": day, "gross": gross})
    return day, out, ""


# --- the join ---------------------------------------------------------------

def load_asof(path: str | Path) -> dict[tuple[str, str], dict]:
    """(symbol, date) -> the point-in-time row `edgar_shares --asof` wrote."""
    from common import textio as T
    p = Path(path)
    if not p.exists():
        sys.exit(f"{p} does not exist -- run\n"
                 f"    python -m common.edgar_shares --pull\n"
                 f"    python -m common.edgar_shares --asof")
    rows, _enc = T.read_csv(p)
    out = {}
    for r in rows:
        out[(r["symbol"], r["date"])] = r
    return out


def attach(trades: list[dict], asof: dict) -> tuple[list[dict], dict[str, int]]:
    """Give every trade its status and, where there is one, its share count.

    A trade whose symbol-day is not in the as-of table at all is a DIFFERENT
    thing from one whose company has not filed, and both are different from a
    known figure. All three are kept and counted; none is dropped, because the
    population that gets dropped is the one nobody can check.
    """
    miss: dict[str, int] = defaultdict(int)
    for t in trades:
        row = asof.get((t["symbol"], t["date"]))
        if row is None:
            t["status"] = "not_in_universe_table"
        else:
            t["status"] = row["status"] or "unknown"
            if row["shares"]:
                t["shares"] = float(row["shares"])
            if row["lag_days"]:
                t["lag_days"] = int(float(row["lag_days"]))
        miss[t["status"]] += 1
    return trades, dict(miss)


def net_at(rows: list[dict], friction: float) -> float:
    return sum(r["gross"] - friction for r in rows)


def per_trade(rows: list[dict], friction: float) -> float:
    return net_at(rows, friction) / len(rows) if rows else 0.0


def split(rows: list[dict]) -> tuple[list, list]:
    """Chronological halves, cut at the median SESSION -- the same split
    `entry_features` uses, so a result here is comparable with the 0-of-22."""
    dates = sorted({r["date"] for r in rows})
    if len(dates) < 2:
        return rows, []
    cut = dates[len(dates) // 2]
    return ([r for r in rows if r["date"] < cut],
            [r for r in rows if r["date"] >= cut])


def with_net(rows: list[dict], friction: float) -> list[dict]:
    """The bucketing machinery averages a column called `net`."""
    return [dict(r, net=r["gross"] - friction) for r in rows]


def drop_top(rows: list[dict], n: int = DROP) -> list[dict]:
    """Without the n largest trades. `sorted` is stable, so ties come off in
    file order rather than by anything that varies between runs."""
    ordered = sorted(rows, key=lambda r: r["gross"], reverse=True)
    return ordered[n:]


# --- sections ---------------------------------------------------------------

def accounting(trades: list[dict], by_status: dict[str, int],
               strategy: str, n_days: int) -> list[str]:
    n = len(trades)
    L = ["POPULATION", "",
         f"  trades              {n:,}",
         f"  sessions            {n_days:,}"]
    pub = PUBLISHED_TRADES.get(strategy)
    if pub is not None:
        ok = "matches" if n == pub else "*** DOES NOT MATCH ***"
        L += [f"  published count     {pub:,}   {ok}"]
        if n != pub:
            L += ["",
                  "  A DIFFERENT BOOK UNDER THE SAME CAVEAT. This must measure",
                  "  the trades pit_strategy published or its figures are not",
                  "  comparable with anything. Do not read the sections below",
                  "  until this reconciles."]
    L += [""]
    for k in sorted(by_status, key=lambda k: -by_status[k]):
        L.append(f"    {k:<24} {by_status[k]:>7,}   {100.0*by_status[k]/n:5.1f}%")
    return L + [""]


COVERED = ("known", "stale")


def bias_control(trades: list[dict]) -> list[str]:
    """THE CONTROL THAT DECIDES WHETHER THE REST MEANS ANYTHING.

    The uncovered symbol-days are not missing at random: they are
    disproportionately delisted microcaps, which is the population this
    strategy exists to trade. If their trades behave differently from the
    covered ones, every bucket below describes a subset, not the strategy.
    """
    cov = [t for t in trades if t["status"] in COVERED]
    unc = [t for t in trades if t["status"] not in COVERED]
    L = ["THE COVERAGE CONTROL, READ BEFORE ANY BUCKET", "",
         "  Is the covered population the same animal as the uncovered one?",
         "",
         f"  {'':<12}{'n':>8}" + "".join(f"{lab:>12}" for lab, _ in FRICTIONS),
         f"  {'covered':<12}{len(cov):>8,}"
         + "".join(f"{per_trade(cov, f):>12,.2f}" for _, f in FRICTIONS),
         f"  {'uncovered':<12}{len(unc):>8,}"
         + "".join(f"{per_trade(unc, f):>12,.2f}" for _, f in FRICTIONS), ""]
    if not cov or not unc:
        return L + ["  One side is empty; no comparison is possible.", ""]
    gap = per_trade(cov, MEASURED_FRICTION) - per_trade(unc, MEASURED_FRICTION)
    L.append(f"  difference    {gap:+,.2f} per trade at ${MEASURED_FRICTION:.2f}")
    if abs(gap) > BIAS_TOLERANCE:
        L += ["",
              "  *** THE TWO POPULATIONS DIFFER BY MORE THAN ONE ROUND TRIP'S",
              "      FRICTION. Every bucket below describes the covered subset",
              "      and does not generalise to the universe. Any rule derived",
              "      from it would be applied to names it was never measured",
              "      on -- which is the shape of this project's worst defects,",
              "      not a caveat to note and move past. ***", ""]
    else:
        L += ["",
              "  Within one round trip's friction. That does not prove the two",
              "  populations are the same; it fails to show they differ, which",
              "  is the most this control can ever say.", ""]
    return L


def bucket_lines(bs: list[dict], label: str) -> list[str]:
    if not bs:
        return [f"    {label:<10} could not be bucketed"]
    cells = "  ".join(f"[{b['lo']/1e6:,.1f}M-{b['hi']/1e6:,.1f}M] "
                      f"{b['mean']:>8,.2f} (n={b['n']:,})" for b in bs)
    return [f"    {label:<10} {cells}"]


def quantile_section(rows: list[dict], stratum: str) -> tuple[list[str], str]:
    """Quartiles of shares outstanding, both halves, and drop-top-N."""
    L = [f"  STRATUM: {stratum}   n={len(rows):,}", ""]
    why = why_not_bucketable(rows, "shares", QUANTILES)
    if why:
        return L + [f"    not bucketable: {why}", ""], "NOTHING"

    whole = buckets(rows, "shares", QUANTILES)
    a, b = split(rows)
    ba = buckets(a, "shares", QUANTILES) if a else []
    bb = buckets(b, "shares", QUANTILES) if b else []
    L += bucket_lines(whole, "all")
    L += bucket_lines(ba, "1st half")
    L += bucket_lines(bb, "2nd half")

    # Drop-top-N, per bucket, on the whole stratum.
    robust = []
    for k in range(QUANTILES):
        vals = sorted(rows, key=lambda r: r["shares"])
        lo, hi = len(vals) * k // QUANTILES, len(vals) * (k + 1) // QUANTILES
        chunk = vals[lo:hi]
        kept = drop_top(chunk)
        robust.append({"lo": chunk[0]["shares"], "hi": chunk[-1]["shares"],
                       "n": len(kept),
                       "mean": (sum(r["net"] for r in kept) / len(kept))
                       if kept else 0.0,
                       "win": 0.0})
    L += bucket_lines(robust, f"less top{DROP}")
    L += [""]

    verdict = "NOTHING"
    why_v = "no bucket is positive after friction in both halves"
    if ba and bb:
        for k in range(min(len(whole), len(ba), len(bb), len(robust))):
            if (whole[k]["mean"] > 0 and ba[k]["mean"] > 0
                    and bb[k]["mean"] > 0 and robust[k]["mean"] > 0):
                verdict, why_v = "CLEARS", (
                    f"bucket {k+1} is positive in both halves and survives "
                    f"dropping its top {DROP}")
                break
        else:
            ma, mb = monotone(ba), monotone(bb)
            da = ba[-1]["mean"] - ba[0]["mean"]
            db = bb[-1]["mean"] - bb[0]["mean"]
            if (ma and ma == mb and (da > 0) == (db > 0)
                    and min(abs(da), abs(db)) > MEASURED_FRICTION):
                verdict, why_v = "SEPARATES", (
                    "monotone the same way in both halves, ends differ by "
                    "more than friction -- but nothing is profitable")
    L += [f"    verdict: {verdict} -- {why_v}", ""]
    return L, verdict


def fixed_section(rows: list[dict]) -> list[str]:
    """The same trades against the thresholds a screener could actually take.

    Reported alongside the quantiles, never instead: round numbers are a
    fitted choice made before the data was seen, which makes them honest as a
    RULE and useless as a MEASUREMENT. Every band is printed, including the
    empty ones -- a band with no trades is a fact about the universe.
    """
    L = ["  AT THE SCANNER'S OWN THRESHOLDS", ""]
    for lo, hi in zip(FIXED_EDGES, FIXED_EDGES[1:]):
        band = [r for r in rows if lo <= r["shares"] < hi]
        label = (f"{lo/1e6:,.0f}M-{hi/1e6:,.0f}M" if hi != float("inf")
                 else f"{lo/1e6:,.0f}M+")
        if not band:
            L.append(f"    {label:<14} {'-':>9}   no trades")
            continue
        wins = sum(1 for r in band if r["net"] > 0) / len(band) * 100.0
        L.append(f"    {label:<14} {sum(r['net'] for r in band)/len(band):>9,.2f}"
                 f"   n={len(band):>5,}   win {wins:4.1f}%")
    return L + [""]


def render(trades: list[dict], by_status: dict, strategy: str, n_days: int,
           elapsed: float, jobs: int) -> list[str]:
    L = ["DOES SHARES OUTSTANDING SEPARATE THE WINNERS FROM THE LOSERS?", "",
         f"  strategy {strategy.upper()}   outcome: net at "
         f"${MEASURED_FRICTION:.2f}/round trip   {QUANTILES} buckets",
         f"  elapsed {elapsed:.1f}s on {jobs} worker(s)",
         "",
         "  PRE-REGISTERED: a lower share count at entry predicts a better net",
         "  per trade. CLEARS requires a bucket positive after friction in both",
         f"  halves AND after dropping its best {DROP} trades. One family, one",
         f"  feature, {QUANTILES} buckets x 2 halves x 2 strata.", ""]
    L += accounting(trades, by_status, strategy, n_days)
    L += bias_control(trades)

    known = with_net([t for t in trades if t["status"] == "known"
                      and "shares" in t], MEASURED_FRICTION)
    stale = with_net([t for t in trades if t["status"] == "stale"
                      and "shares" in t], MEASURED_FRICTION)
    both = with_net([t for t in trades if t["status"] in COVERED
                     and "shares" in t], MEASURED_FRICTION)

    L += ["SHARES OUTSTANDING, IN QUARTILES", ""]
    v_known, v_stale, v_both = "NOTHING", "NOTHING", "NOTHING"
    for rows, name in ((known, "known"), (stale, "stale"), (both, "known+stale")):
        if not rows:
            L += [f"  STRATUM: {name}   n=0", "", "    no trades", ""]
            continue
        sec, verdict = quantile_section(rows, name)
        L += sec
        if name == "known":
            v_known = verdict
        elif name == "stale":
            v_stale = verdict
        else:
            v_both = verdict

    if both:
        L += fixed_section(both)

    L += ["THE VERDICT", ""]
    if known and stale and v_known != v_stale:
        L += [f"  REFUSED. `known` says {v_known} and `stale` says {v_stale}.",
              "",
              "  A stratum disagreement refuses a verdict for the same reason a",
              "  halves disagreement does: one of the two is wrong and nothing",
              "  here says which. The combined figure is not a tie-break -- it",
              "  is the two populations averaged, which is how a disagreement",
              "  gets hidden rather than resolved.", ""]
    else:
        L += [f"  {v_both} on the covered population "
              f"(known {v_known}, stale {v_stale}).", ""]
        if v_both == "NOTHING":
            L += ["  The 23rd feature behaves like the first 22. That is worth",
                  "  more than it looks: this one did NOT come from the same",
                  "  minute tape as the others, so its failure is not another",
                  "  view of the same object.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  NOT FLOAT. EDGAR publishes shares OUTSTANDING, an upper bound.",
          "  NOT A RULE. No filter was applied; the trades are exactly the ones",
          f"  {strategy.upper()} took.",
          "  NOT OUT OF SAMPLE. holdout.json has not been spent here.",
          "  NOT A COMPLETE UNIVERSE. See the coverage control above.", ""]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--strategy", default="mcl", choices=["mcl", "mc5"])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--asof", default=ASOF)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    asof = load_asof(a.asof)
    by_date = load_pit(Path(a.pairs))
    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]

    have = [d for d in days if d in slices]
    tasks = []
    for k, day in enumerate(have):
        # The warm-up frames come from the days ACTUALLY AVAILABLE, not from
        # the calendar: a gap in the archive would otherwise shorten the
        # warm-up silently and move the book by a trade or two.
        first = max(0, k - WARMUP_SESSIONS)
        tasks.append(([str(slices[d]) for d in have[first:k + 1]], day,
                      by_date[day], a.strategy))

    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"entry_shares: {len(tasks):,} session(s) on {jobs} worker(s)",
          flush=True)
    t0 = time.time()
    got: dict[str, list] = {}
    if jobs == 1:
        for day, rows, err in map(run_day, tasks):
            got[day] = rows
            if err:
                print(f"  ! {day}: {err}", flush=True)
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for k, (day, rows, err) in enumerate(
                    ex.map(run_day, tasks, chunksize=4), 1):
                got[day] = rows
                if err:
                    print(f"  ! {day}: {err}", flush=True)
                if k % 50 == 0:
                    print(f"  ... {k:,} of {len(tasks):,}", flush=True)

    # DAY ORDER, not completion order. This module sums floats and float
    # addition is not associative, so a net that moves when --jobs changes is
    # not a constant. Same reasoning as pit_h0.merge.
    trades: list[dict] = []
    for day in sorted(got):
        trades.extend(got[day])

    trades, by_status = attach(trades, asof)
    emit("\n".join(render(trades, by_status, a.strategy, len(have),
                          time.time() - t0, jobs)),
         a.out or f"var/reports/entry_shares_{a.strategy}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
