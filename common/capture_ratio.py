#!/usr/bin/env python3
"""How much of the consolidated tape does EQUS.MINI actually see?

    python -m common.capture_ratio --pairs var/state/screen_pairs.json
    python -m common.capture_ratio --pairs ... --limit 40      # a quick pass

THE QUESTION
------------
`consolidated_volume_gap.md` measured five symbols on one day and found
EQUS.MINI carrying 4.8%-19.6% of the consolidated volume, with a four-fold
spread between symbols. Every absolute volume threshold in the screen is
computed on that partial figure, so the size of the error, and whether it is
stable, decides whether those thresholds mean anything.

Three questions, in order of what they change:

1. **How much of the spread is BETWEEN symbols versus WITHIN one over time?**
   This is the one that matters. If capture is a stable per-symbol property,
   RVOL -- a ratio of two partial numbers -- survives, because the factor
   cancels. If it wanders day to day within a symbol, RVOL is noise and the
   screen is selecting partly on tape coverage rather than on activity.
2. Was 2025-04-09 representative? It was the tariff-pause session, about as
   extreme a volume day as the period contains.
3. What is the median capture, so the dollar-volume floor can be restated in
   true terms rather than tape terms?

THE CONFOUND THIS TOOL EXISTS TO NOT FALL INTO
-----------------------------------------------
`CLEARED_VOLUME` is published 04:00-20:00 ET. If `EQUS.MINI ohlcv-1d` covers
only regular hours, then a naive ratio measures *session definition* and calls
it *tape coverage* -- and the number would look like a coverage finding while
being an artefact of comparing a 16-hour figure to a 6.5-hour one.

So this does two things rather than assume:

* computes the ratio at BOTH cutoffs, 16:00 and 20:00 ET, and reports both;
* runs a direct check first -- sum EQUS.MINI's own MINUTE bars over 04:00-20:00
  for a sample of symbol-days and compare against its DAILY bar. If they agree,
  the daily bar is full-session and the 20:00 cutoff is the honest comparison.

The check is on the same source as the thing being checked, so it settles the
session question without any assumption about the other dataset.

A capture ratio above 1.0 is impossible -- a partial tape cannot exceed the
consolidated one -- so any such row is a defect in the join, not a finding, and
is counted and reported separately rather than averaged in.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
import time
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.databento_fetch import default_archive
from common.dbn_io import read_dbn
from common.report_io import emit

ET = ZoneInfo("America/New_York")
CLEARED_VOLUME = 6          # databento_dbn.StatType.CLEARED_VOLUME
SESSION_START_MIN = 4 * 60  # 04:00 ET
RTH_CLOSE_MIN = 16 * 60     # 16:00 ET
SESSION_END_MIN = 20 * 60   # 20:00 ET


# --- reading ---------------------------------------------------------------

def load_pairs(path: Path) -> dict[str, list[str]]:
    """Screened pairs grouped by date, which is how the archive is chunked."""
    by_date: dict[str, list[str]] = defaultdict(list)
    for row in json.load(open(path)):
        by_date[row["date"]].append(row["symbol"])
    return {d: sorted(set(s)) for d, s in sorted(by_date.items())}


def et_minutes(series) -> pd.Series:
    """Minutes past ET midnight for a tz-aware timestamp series."""
    et = pd.to_datetime(series, utc=True).dt.tz_convert(ET)
    return et.dt.hour * 60 + et.dt.minute


def cleared_by_cutoff(stats: pd.DataFrame, cutoff_min: int) -> dict[str, int]:
    """Highest CLEARED_VOLUME per symbol at or before `cutoff_min` ET.

    Uses max rather than the last row. The series was verified monotonic
    non-decreasing on the probe day, but max is correct either way and a
    revision that arrived out of order would otherwise silently lower the
    total.

    Times must be `ts_event` -- when the venue stamped the statistic -- not
    `ts_recv`, when Databento received it. On the probe file those differ by up
    to 4.67 seconds, which is nothing at this scale except exactly at a cutoff,
    where it puts a boundary print on the wrong side.

    `dbn_io.read_dbn` already re-indexes on ts_event, which CONSUMES the
    column: a frame from it has the right times in the index and no ts_event
    column at all. A raw `store.to_df()` is the opposite -- indexed on ts_recv
    with ts_event as a column. Both arrive here, so both are handled, and the
    column is preferred when present because its meaning is unambiguous. This
    was correct by accident before it was correct on purpose: the first version
    documented the ts_event rule and then silently fell through to the index.
    """
    if stats.empty or "stat_type" not in stats.columns:
        return {}
    cv = stats[stats["stat_type"] == CLEARED_VOLUME]
    if cv.empty:
        return {}
    times = cv["ts_event"] if "ts_event" in cv.columns else cv.index.to_series()
    mins = et_minutes(times)
    keep = cv[(mins >= SESSION_START_MIN).to_numpy()
              & (mins < cutoff_min).to_numpy()]
    if keep.empty or "symbol" not in keep.columns:
        return {}
    return {s: int(v) for s, v in keep.groupby("symbol")["quantity"].max().items()}


def daily_volume(archive: Path, dataset: str, month: str) -> pd.DataFrame:
    """EQUS.MINI daily bars for one month, as symbol / date / volume.

    THE DATE LABEL IS UTC, DELIBERATELY, AND THIS IS NOT AN OVERSIGHT.
    ------------------------------------------------------------------
    Daily bars are stamped at UTC MIDNIGHT. Converting that to ET gives 20:00
    on the PREVIOUS day, so an ET date label moves every session back one --
    and the first version of this function did exactly that, against an
    explicit warning in dbn_io.daily_frame's docstring saying not to.

    The damage was not an exception. Every symbol-day joined the wrong
    session's volume, and the result was a full report of plausible numbers:
    a median capture of 1.2% against the probe's hand-checked 4.8%-19.6%, and
    a session check reporting the daily bar as 22.8% of the sum of its OWN
    minute bars -- a figure that is arithmetically impossible for one dataset
    and was the only reason the join got questioned at all.

    Intraday timestamps ARE converted to ET, because those are real event times
    within a session. Only the daily bar's synthetic midnight stamp is a label
    rather than a moment.
    """
    f = archive / dataset / "ohlcv-1d" / f"{month}.dbn.zst"
    if not f.exists():
        return pd.DataFrame()
    df = read_dbn(f)
    if df.empty:
        return df
    out = df[["symbol", "volume"]].copy()
    out["date"] = df.index.strftime("%Y-%m-%d")      # UTC. See above.
    return out


# --- the session-definition check ------------------------------------------

def session_check(archive: Path, dataset: str, samples) -> list[dict]:
    """Does the DAILY bar equal the sum of the MINUTE bars 04:00-20:00?

    Both sides are EQUS.MINI, so this settles what session its daily bar covers
    without assuming anything about EQUS.SUMMARY. If they agree, comparing the
    daily bar against consolidated-at-20:00 is like for like. If the daily bar
    is materially smaller, it is an RTH figure and the 16:00 cutoff is the
    honest comparison instead.
    """
    rows = []
    by_month: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for sym, day in samples:
        by_month[day[:7]].append((sym, day))

    for month, pairs in sorted(by_month.items()):
        mf = archive / dataset / "ohlcv-1m" / f"{month}.dbn.zst"
        if not mf.exists():
            continue
        minute = read_dbn(mf)
        if minute.empty:
            continue
        et = minute.index.tz_convert(ET)
        minute = minute.assign(
            _day=et.strftime("%Y-%m-%d"),
            _min=et.hour * 60 + et.minute)
        daily = daily_volume(archive, dataset, month)
        if daily.empty:
            continue
        dmap = {(r.symbol, r.date): int(r.volume)
                for r in daily.itertuples(index=False)}

        for sym, day in pairs:
            g = minute[(minute["symbol"] == sym) & (minute["_day"] == day)]
            if g.empty or (sym, day) not in dmap:
                continue
            full = int(g.loc[(g["_min"] >= SESSION_START_MIN)
                             & (g["_min"] < SESSION_END_MIN), "volume"].sum())
            rth = int(g.loc[(g["_min"] >= 9 * 60 + 30)
                            & (g["_min"] < RTH_CLOSE_MIN), "volume"].sum())
            rows.append({"symbol": sym, "date": day, "daily_bar": dmap[(sym, day)],
                         "minutes_full": full, "minutes_rth": rth})
    return rows


def session_verdict(rows) -> tuple[str, str]:
    """(verdict, prose). Which cutoff the daily bar should be compared against."""
    if not rows:
        return "unknown", ("No sample could be checked, so which session the "
                           "daily bar covers is UNVERIFIED. Read both cutoffs "
                           "below as bounds, not as one answer.")
    full = [r["daily_bar"] / r["minutes_full"] for r in rows if r["minutes_full"]]
    rth = [r["daily_bar"] / r["minutes_rth"] for r in rows if r["minutes_rth"]]
    mf = st.median(full) if full else float("nan")
    mr = st.median(rth) if rth else float("nan")
    if full and 0.98 <= mf <= 1.02:
        return "full", (f"The daily bar matches the FULL 04:00-20:00 minute sum "
                        f"(median ratio {mf:.4f}), so compare it against "
                        f"consolidated-at-20:00.")
    if rth and 0.98 <= mr <= 1.02:
        return "rth", (f"The daily bar matches the RTH 09:30-16:00 minute sum "
                       f"(median ratio {mr:.4f}), so compare it against "
                       f"consolidated-at-16:00. The 20:00 column below "
                       f"UNDERSTATES capture by counting hours the daily bar "
                       f"does not cover.")
    return "neither", (f"The daily bar matches NEITHER minute sum (full "
                       f"{mf:.4f}, RTH {mr:.4f}). Something about the daily "
                       f"bar's construction is not understood, and no capture "
                       f"figure below should be quoted until it is.")


# --- the decomposition -----------------------------------------------------

def decompose(rows, key="capture_2000") -> dict:
    """Split the variation in log-capture into between-symbol and within-symbol.

    THIS IS THE QUESTION. If capture is a stable per-symbol property, the
    factor cancels out of RVOL -- a ratio of two partial numbers -- and RVOL
    survives the finding. If it wanders within a symbol day to day, RVOL is
    partly noise and the screen is selecting on tape coverage as much as on
    activity.

    Logs, because these are ratios: a symbol at 5% and one at 20% differ by the
    same factor as 20% to 80%, and an arithmetic variance would call the second
    pair four times more spread out.
    """
    by_sym: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        v = r.get(key)
        if v and v > 0:
            by_sym[r["symbol"]].append(math.log(v))

    allv = [v for vs in by_sym.values() for v in vs]
    repeat = {s: vs for s, vs in by_sym.items() if len(vs) >= 2}
    out = {
        "symbols": len(by_sym),
        "symbols_with_repeats": len(repeat),
        "observations": len(allv),
        "total_var": st.pvariance(allv) if len(allv) > 1 else 0.0,
        "within_var": None, "between_var": None, "icc": None,
    }
    if len(repeat) >= 2:
        within = st.mean([st.pvariance(vs) for vs in repeat.values()])
        between = st.pvariance([st.mean(vs) for vs in repeat.values()])
        out["within_var"] = within
        out["between_var"] = between
        tot = within + between
        out["icc"] = (between / tot) if tot > 0 else None
    return out


def drift_vs_noise(rows, key="capture_2000", min_obs=5) -> dict:
    """Is the within-symbol variation slow DRIFT or day-to-day NOISE?

    The two have opposite consequences and the variance decomposition cannot
    tell them apart. RVOL divides today's volume by a 10-day trailing mean of
    the same symbol, so:

    * DRIFT -- capture moving slowly -- largely cancels. Today's capture and
      the trailing window's average capture are close, so the ratio is nearly
      clean.
    * NOISE -- capture independent day to day -- does not cancel at all. The
      numerator carries one full draw while the denominator averages ten, so
      the noise passes almost undamped into RVOL.

    Lag-1 autocorrelation of each symbol's log-capture series separates them.
    Near +1 is drift; near 0 is noise. Reported as the median across symbols
    with at least `min_obs` observations, because a mean is dominated by the
    few symbols with long series.

    Dates are sorted before differencing: the rows come from a per-month walk
    and are not guaranteed to arrive in date order, and an unsorted series
    would report the autocorrelation of an arbitrary permutation -- which is
    zero, i.e. it would claim "pure noise" no matter what the data did.
    """
    by_sym: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r in rows:
        v = r.get(key)
        if v and v > 0:
            by_sym[r["symbol"]].append((r["date"], math.log(v)))

    acs = []
    for vs in by_sym.values():
        if len(vs) < min_obs:
            continue
        xs = [v for _, v in sorted(vs)]          # by date. See docstring.
        m = st.mean(xs)
        num = sum((xs[i] - m) * (xs[i + 1] - m) for i in range(len(xs) - 1))
        den = sum((x - m) ** 2 for x in xs)
        if den > 0:
            acs.append(num / den)
    return {"symbols": len(acs), "min_obs": min_obs,
            "median_ac1": st.median(acs) if acs else None}


def quantiles(values, qs=(0.05, 0.25, 0.5, 0.75, 0.95)) -> dict:
    if not values:
        return {q: float("nan") for q in qs}
    s = sorted(values)
    return {q: s[min(len(s) - 1, int(q * len(s)))] for q in qs}


# --- the report ------------------------------------------------------------

def render(rows, checks, impossible, missing, elapsed_min) -> str:
    verdict, prose = session_verdict(checks)
    L = ["EQUS.MINI CAPTURE OF THE CONSOLIDATED TAPE", ""]
    L += [f"  symbol-days matched     {len(rows):,}",
          f"  unmatched (no data)     {missing:,}",
          f"  IMPOSSIBLE (capture>1)  {impossible:,}",
          f"  elapsed                 {elapsed_min:.1f} min", ""]

    L += ["THE SESSION CHECK  (does the daily bar cover the full session?)", ""]
    L += [f"  sampled symbol-days     {len(checks)}",
          f"  verdict                 {verdict.upper()}", ""]
    for line in prose.split(". "):
        if line.strip():
            L.append(f"  {line.strip().rstrip('.')}.")
    L.append("")

    if not rows:
        L += ["NO ROWS MATCHED -- nothing below can be computed.",
              "Check that the statistics archive and the EQUS.MINI daily bars",
              "cover the same dates as the pair list."]
        return "\n".join(L)

    L += ["CAPTURE DISTRIBUTION  (EQUS.MINI daily volume / consolidated)", "",
          f"  {'cutoff':<10} {'p05':>8} {'p25':>8} {'median':>8} {'p75':>8} "
          f"{'p95':>8}", "  " + "-" * 54]
    for key, label in (("capture_1600", "16:00 ET"), ("capture_2000", "20:00 ET")):
        vals = [r[key] for r in rows if r.get(key)]
        q = quantiles(vals)
        L.append(f"  {label:<10} " + " ".join(f"{100*q[x]:>7.1f}%"
                 for x in (0.05, 0.25, 0.5, 0.75, 0.95)))
    L.append("")
    primary = "capture_1600" if verdict == "rth" else "capture_2000"
    L.append(f"  Primary column, per the session check: {primary}")
    L.append("")

    d = decompose(rows, primary)
    L += ["BETWEEN SYMBOLS vs WITHIN A SYMBOL  (variance of log capture)", "",
          f"  distinct symbols            {d['symbols']:,}",
          f"  symbols seen on 2+ days     {d['symbols_with_repeats']:,}",
          f"  observations used           {d['observations']:,}"]
    if d["icc"] is None:
        L += ["", "  Not enough repeated symbols to separate the two. The "
              "screened", "  universe may simply not revisit names often enough."]
    else:
        ratio = (d["between_var"] / d["within_var"]) if d["within_var"] else None
        L += [f"  between-symbol variance     {d['between_var']:.4f}",
              f"  within-symbol variance      {d['within_var']:.4f}",
              f"  share between (ICC)         {d['icc']:.3f}"]
        if ratio:
            L.append(f"  between / within            {ratio:.2f}x")
        L.append("")
        # State the ratio, not just the band. At ICC 0.675 the old prose said
        # "roughly as much within as between" while between was actually 2.1x
        # within -- a banded sentence describing the middle of its band rather
        # than the number in front of it.
        if d["symbols_with_repeats"] < 30:
            L += [f"  CAUTION: only {d['symbols_with_repeats']} symbols appear "
                  "on two or more days, so the",
                  "  within-symbol figure rests on very little. Read the split "
                  "as indicative",
                  "  until the full run.", ""]
        if d["icc"] >= 0.7:
            L += ["  MOSTLY A PER-SYMBOL PROPERTY. Capture is roughly stable "
                  "for a given",
                  "  name, so it largely cancels out of RVOL -- a ratio of two "
                  "partial",
                  "  numbers with the same factor top and bottom. The ABSOLUTE "
                  "floors",
                  "  (min_avg_dollar_vol, max_pct_of_dollar_vol) are still "
                  "wrong and still",
                  "  need restating in true terms."]
        elif d["icc"] <= 0.4:
            L += ["  MOSTLY DAY-TO-DAY NOISE within a symbol. Capture does not "
                  "cancel out",
                  "  of RVOL, so RVOL is measuring tape coverage as well as "
                  "activity, and",
                  "  the screen is selecting partly on which prints EQUS.MINI "
                  "happened to",
                  "  see. This is the worse outcome and would mean rebuilding "
                  "the screen's",
                  "  volume inputs on consolidated data, not just rescaling "
                  "the floors."]
        else:
            share = 100 * (1 - d["icc"])
            L += [f"  MIXED. {share:.0f}% of the variation is day-to-day "
                  "within a name, so the",
                  "  per-symbol factor does NOT fully cancel out of RVOL. RVOL "
                  "is measuring",
                  "  tape coverage as well as activity, to that extent. Treat "
                  "any",
                  "  RVOL-dependent result as partly contaminated and check it "
                  "against",
                  "  consolidated volume before relying on it."]
    L.append("")

    dn = drift_vs_noise(rows, primary)
    L += ["DRIFT OR NOISE?  (lag-1 autocorrelation of a symbol's log capture)",
          "",
          f"  symbols with {dn['min_obs']}+ days     {dn['symbols']:,}"]
    if dn["median_ac1"] is None:
        L += ["", "  Too few symbols with a long enough series to tell."]
    else:
        ac = dn["median_ac1"]
        L += [f"  median lag-1 autocorr      {ac:+.3f}", ""]
        if ac >= 0.4:
            L += ["  DRIFT. Capture moves slowly, so today's value and the "
                  "10-day trailing",
                  "  average are close and most of the within-symbol variation "
                  "CANCELS out",
                  "  of RVOL. The contamination is smaller than the variance "
                  "split implies."]
        elif ac <= 0.15:
            L += ["  NOISE. Capture is near-independent day to day, so it does "
                  "NOT cancel:",
                  "  the numerator carries one full draw while the denominator "
                  "averages ten.",
                  "  The within-symbol variation passes almost undamped into "
                  "RVOL, and the",
                  "  variance split above is the honest measure of the damage."]
        else:
            L += ["  PARTLY BOTH. Some of the within-symbol variation cancels "
                  "in a 10-day",
                  "  window and some does not. Neither the optimistic nor the "
                  "pessimistic",
                  "  reading of the variance split is safe."]
    L.append("")

    by_date: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.get(primary):
            by_date[r["date"]].append(r[primary])
    med = {d_: st.median(v) for d_, v in by_date.items() if v}
    if med:
        allmed = sorted(med.values())
        L += ["WAS 2025-04-09 REPRESENTATIVE?  (per-date median capture)", "",
              f"  dates                   {len(med):,}",
              f"  median of date medians  {100*st.median(allmed):.1f}%",
              f"  lowest date             {100*allmed[0]:.1f}%",
              f"  highest date            {100*allmed[-1]:.1f}%"]
        if "2025-04-09" in med:
            probe = med["2025-04-09"]
            rank = sum(1 for v in allmed if v <= probe) / len(allmed)
            L += [f"  2025-04-09              {100*probe:.1f}%  "
                  f"({100*rank:.0f}th percentile of dates)"]
            if rank < 0.2 or rank > 0.8:
                L.append("  -> it sat in a tail. The five-symbol figures in "
                         "consolidated_volume_gap.md")
                L.append("     should not be read as typical.")
            else:
                L.append("  -> unremarkable. The probe day was not misleading "
                         "about the level.")
        else:
            L.append("  2025-04-09 is not in the screened pair list, so the "
                     "probe day cannot")
            L.append("  be placed against the distribution here.")
    return "\n".join(L)


# --- driver ----------------------------------------------------------------

def analyse(archive: Path, by_date, stats_dataset, mini_dataset, tick=25):
    rows, impossible, missing = [], 0, 0
    months = defaultdict(list)
    for day in by_date:
        months[day[:7]].append(day)

    t0 = time.time()
    done, total = 0, len(by_date)
    for month in sorted(months):
        daily = daily_volume(archive, mini_dataset, month)
        dmap = {} if daily.empty else {
            (r.symbol, r.date): int(r.volume)
            for r in daily.itertuples(index=False)}

        for day in sorted(months[month]):
            done += 1
            f = archive / stats_dataset / "statistics" / f"{day}.dbn.zst"
            if not f.exists():
                missing += len(by_date[day])
                continue
            try:
                stats = read_dbn(f, require_symbols=False)
            except Exception as e:  # noqa: BLE001
                print(f"  {day}: unreadable ({type(e).__name__}: {e})", flush=True)
                missing += len(by_date[day])
                continue
            at16 = cleared_by_cutoff(stats, RTH_CLOSE_MIN)
            at20 = cleared_by_cutoff(stats, SESSION_END_MIN)

            for sym in by_date[day]:
                mini = dmap.get((sym, day))
                c20, c16 = at20.get(sym), at16.get(sym)
                if mini is None or not c20:
                    missing += 1
                    continue
                row = {"symbol": sym, "date": day, "mini_daily": mini,
                       "consolidated_1600": c16 or 0, "consolidated_2000": c20,
                       "capture_1600": (mini / c16) if c16 else None,
                       "capture_2000": mini / c20}
                # A partial tape cannot exceed the consolidated one. Such a row
                # is a defect in the join, not a finding, and averaging it in
                # would drag every statistic towards a number that cannot exist.
                if row["capture_2000"] > 1.0:
                    impossible += 1
                    continue
                rows.append(row)

            if tick and (done % tick == 0 or done == total):
                el = (time.time() - t0) / 60
                print(f"  {done:>4}/{total} dates  {len(rows):,} rows  "
                      f"{el:.1f} min elapsed, "
                      f"~{el/done*(total-done):.1f} min left", flush=True)
    return rows, impossible, missing, (time.time() - t0) / 60


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EQUS.MINI capture of the tape")
    ap.add_argument("--pairs", default="var/state/screen_pairs.json")
    ap.add_argument("--archive", default=str(default_archive()))
    ap.add_argument("--stats-dataset", default="EQUS.SUMMARY")
    ap.add_argument("--mini-dataset", default="EQUS.MINI")
    ap.add_argument("--limit", type=int, default=0,
                    help="only the first N dates -- for a quick pass")
    ap.add_argument("--check-sample", type=int, default=40,
                    help="symbol-days for the session check")
    ap.add_argument("--report", default="var/reports/capture_ratio.txt")
    ap.add_argument("--csv", default="var/reports/capture_ratio.csv")
    ap.add_argument("--from-csv", action="store_true",
                    help="re-render from the existing CSV instead of re-reading "
                         "the archive. Seconds rather than minutes -- use it to "
                         "add an analysis without re-doing the measurement")
    a = ap.parse_args(argv)

    if a.from_csv:
        # The measurement took 11 minutes over 10 GB. Every later question
        # asked of the SAME rows should cost seconds, or it will not get asked.
        p = Path(a.csv)
        if not p.exists():
            sys.exit(f"{p} does not exist -- run without --from-csv first.")
        rows = pd.read_csv(p).to_dict("records")
        rows = [{k: (None if pd.isna(v) else v) for k, v in r.items()}
                for r in rows]
        print(f"{len(rows):,} rows from {p}")
        # The session check is a property of the archive, not of these rows, so
        # it cannot be recovered from the CSV. Saying "unknown" is right: the
        # alternative is a report that silently asserts a verdict it never made.
        emit(render(rows, [], 0, 0, 0.0), a.report,
             header=f"common.capture_ratio  re-rendered from {p}")
        return 0

    archive = Path(a.archive)
    by_date = load_pairs(Path(a.pairs))
    # The statistics archive starts where the dataset does; earlier dates in the
    # pair list simply have no file and would all count as "missing".
    have = {p.name[: -len(".dbn.zst")]
            for p in (archive / a.stats_dataset / "statistics").glob("*.dbn.zst")}
    by_date = {d: s for d, s in by_date.items() if d in have}
    if a.limit:
        by_date = dict(list(by_date.items())[: a.limit])
    if not by_date:
        sys.exit(f"no screened dates have a statistics file under "
                 f"{archive/a.stats_dataset}/statistics. Run the overnight "
                 "pull first.")

    print(f"{sum(len(v) for v in by_date.values()):,} symbol-days over "
          f"{len(by_date)} dates", flush=True)

    sample = [(s, d) for d in list(by_date)[:: max(1, len(by_date) // 8)]
              for s in by_date[d][:5]][: a.check_sample]
    print(f"session check on {len(sample)} symbol-days...", flush=True)
    checks = session_check(archive, a.mini_dataset, sample)

    rows, impossible, missing, mins = analyse(
        archive, by_date, a.stats_dataset, a.mini_dataset)

    if rows:
        out = Path(a.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"\nper-symbol-day rows written to {out}")

    emit(render(rows, checks, impossible, missing, mins), a.report,
         header=f"common.capture_ratio  {a.stats_dataset} vs {a.mini_dataset}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
