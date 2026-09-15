#!/usr/bin/env python3
"""Where do Ben's labelled samples sit in the tape they came from?

    python -m common.entry_place --samples "Samples - Momentum Trading.xlsx"

THE QUESTION, AND WHY IT IS THIS ONE
------------------------------------
Ben supplied 21 screenshots of bars he would have taken, taken and lost, or
passed on. The tempting move is to fit a rule to them. That move is wrong here
and it is worth being precise about why:

  * The base rate for the kind of move these samples are drawn from is 0.108%
    -- about 1 bar in 926 (`run_signal`). Twenty-one positives against that
    base rate cannot distinguish a real edge from the shape of twenty-one
    arbitrary bars.
  * Eleven of the twenty-one are `took`, three are `pass`. There is no
    comparison group. A rule fitted here would be fitted to one side.
  * Twenty-seven features against twenty-one points, with no halves to
    disagree, is a search with nothing to catch it.

So this module does the one thing the sample size does support: it PLACES each
sample in the distribution of ordinary bars from the same tape, feature by
feature, and reports where it landed.

THE USEFUL DIRECTION IS THE NEGATIVE ONE
----------------------------------------
A feature that puts the samples somewhere unusual proves nothing -- they were
selected because their outcome was known, twenty-seven features were tried,
and roughly half of any bar's features land in an outer quartile by
construction.

A feature that puts the samples EXACTLY WHERE RANDOM BARS LAND is worth
something real: it rules that feature out as the thing that describes what Ben
sees on his screen. Twenty-seven of those and the honest conclusion is that
none of the quantities on his chart, or in this project's two earlier feature
tranches, is the missing condition -- and that is a finding that costs nothing
and can be acted on, unlike a fitted threshold.

The report is built so that the ruled-out list is the headline and the
"unusual" list carries its own warning.

THE SAME TAPE, THE SAME FRAME, THE SAME CODE
--------------------------------------------
The reference population and the samples are both built from the Databento
archive, both through `pit_strategy.build_frame` with the same warm-up, both
scored by `entry_features.features_at`. That is not tidiness. A reference
built from `bar_cache/` (which is IB's tape) and samples built from the
archive (which is XNAS.BASIC) would produce percentiles that look comparable
and are not -- the defect this project has now found in five separate places.

WHAT THE ARCHIVE WINDOW CANNOT GIVE, STATED UP FRONT
----------------------------------------------------
The archive holds 04:00-09:30 ET slices. One warm-up session in front of the
target day is 660 one-minute bars, so:

  * EMA(9), BB(20) and the 20-bar volume mean are exactly what his chart draws.
  * EMA(200) on the 1-minute view is computed over PRE-MARKET bars only. His
    chart's EMA 200 at 07:00 includes yesterday's regular session, which these
    slices do not contain. The column is therefore a 200-bar mean of the same
    tape, not the line on his screen, and the report says so where it is used.
  * EMA(200) on the 5-minute view needs 200 five-minute bars = about four
    pre-market sessions. It does not exist here at all, and is reported as
    absent rather than as NaN buried in a table.

Pulling full-day `ohlcv-1m` would fix both. That is the next lever, not this
module's job.

TIMEFRAME
---------
His screenshots are not one timeframe: CRBP is a 1-minute chart, ARMP a
5-minute one. An EMA(9) of 5-minute closes is forty-five minutes of tape; of
1-minute closes it is nine. They are different measurements wearing one name.
So every sample is placed on BOTH, against a reference built on BOTH, and the
two are never averaged together.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date as _date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit.json"
TIMEFRAMES = (1, 5)

# The label vocabulary in Ben's spreadsheet, as actually spelled there. Case
# and the "and" are both inconsistent across rows, and a row whose label does
# not match must be counted as UNLABELLED rather than dropped: a sample that
# disappears because of its spelling changes the population without saying so.
LABELS = {
    "took": "took",
    "took and lost": "took-and-lost",
    "took-and-lost": "took-and-lost",
    "pass": "pass",
    "passed": "pass",
}
UNLABELLED = "unlabelled"


def normalise_label(raw) -> str:
    if raw is None:
        return UNLABELLED
    return LABELS.get(str(raw).strip().lower(), UNLABELLED)


def load_samples(path: Path) -> list[dict]:
    """The sample list from .xlsx or .csv.

    Columns wanted: symbol, date, time_et, label, note. The header is matched
    on a PREFIX, because the spreadsheet's label column is actually called
    "label (took/passed/took-and-lost)" and pinning the full string would make
    the loader break the first time he retitles it.
    """
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        rows = _rows_from_xlsx(path)
    else:
        from common.textio import read_csv
        recs, _ = read_csv(path)
        rows = ([list(recs[0].keys())] + [list(r.values()) for r in recs]
                if recs else [])
    if not rows:
        sys.exit(f"{path} has no rows")
    head = [str(c or "").strip().lower() for c in rows[0]]

    def col(prefix: str) -> int:
        for k, h in enumerate(head):
            if h.startswith(prefix):
                return k
        sys.exit(f"{path}: no column starting {prefix!r} in {head}")

    i_sym, i_date, i_time = col("symbol"), col("date"), col("time")
    i_lab, i_note = col("label"), col("note")
    out = []
    for r in rows[1:]:
        if not r or r[i_sym] in (None, ""):
            continue
        out.append({
            "symbol": str(r[i_sym]).upper().strip(),
            "date": _as_date(r[i_date]),
            "hhmm": _as_hhmm(r[i_time]),
            "label": normalise_label(r[i_lab]),
            "note": "" if r[i_note] is None else str(r[i_note]),
        })
    return out


def _rows_from_xlsx(path: Path) -> list[list]:
    try:
        import openpyxl
    except ImportError:                                     # pragma: no cover
        sys.exit("reading .xlsx needs openpyxl: pip install openpyxl\n"
                 "(or save the sheet as .csv and pass that)")
    wb = openpyxl.load_workbook(path, data_only=True)
    return [list(r) for r in wb[wb.sheetnames[0]].iter_rows(values_only=True)]


def _as_date(v) -> str:
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, _date):
        return v.isoformat()
    return str(v)[:10]


def _as_hhmm(v) -> str:
    """HH:MM, from a spreadsheet time, a string, or Excel's fraction-of-a-day.

    The third form is the one that bites: a cell formatted as text in one row
    and as a time in the next comes back as 0.2923611111 for 07:01, which
    str() renders as "0.29..." and a naive [:5] slice turns into "0.292" --
    a time that parses to nothing and a sample that vanishes.
    """
    if hasattr(v, "hour") and hasattr(v, "minute"):
        return f"{v.hour:02d}:{v.minute:02d}"
    if isinstance(v, (int, float)):
        mins = int(round(float(v) * 24 * 60))
        return f"{mins // 60:02d}:{mins % 60:02d}"
    s = str(v).strip()
    if ":" not in s:
        sys.exit(f"cannot read {v!r} as a time")
    hh, mm = s.split(":")[:2]
    return f"{int(hh):02d}:{int(mm):02d}"


# --- the reference population -------------------------------------------------

def feature_names() -> list[str]:
    from common.entry_features import FEATURES
    return list(FEATURES)


def frame_for(parts, day: str):
    from common.pit_strategy import build_frame
    return build_frame(parts, day)


def bars_of_day(sig, day: str) -> np.ndarray:
    """Indices of `sig` that belong to the TARGET session.

    The warm-up session is in the frame so the indicators are warm; scoring
    its bars would put a second copy of every prior day into the reference and
    weight the early days double.
    """
    local = sig.index.tz_convert(ET)
    want = _date.fromisoformat(day)
    return np.flatnonzero(np.array([t.date() == want for t in local]))


def score_frame(df, day: str, tf: int, stride: int) -> np.ndarray:
    """(n_bars, n_features) float32 for one symbol-day at one timeframe."""
    from common.entry_features import frame_ctx, features_at
    from strategy.mcl import mcl as MCL

    if tf != 1:
        from strategy.mc5 import mc5 as MC5
        df = MC5.to_5m(df)
    if df is None or len(df) < 25:
        return np.empty((0, len(feature_names())), dtype=np.float32)
    sig = MCL.signals(df)
    idx = bars_of_day(sig, day)
    if stride > 1:
        idx = idx[::stride]
    if len(idx) == 0:
        return np.empty((0, len(feature_names())), dtype=np.float32)
    ctx = frame_ctx(sig)
    names = feature_names()
    out = np.empty((len(idx), len(names)), dtype=np.float32)
    for k, i in enumerate(idx):
        f = features_at(sig, int(i), ctx)
        out[k] = [f[n] for n in names]
    return out


def run_day(args):
    """One session's reference bars, per timeframe. Picklable.

    Returns (day, {tf: array}, n_symbols, err). Arrays rather than dicts
    because a session contributes a few thousand rows and the IPC cost of
    dicts over 550 sessions is most of the runtime.
    """
    from pathlib import Path as P

    from common.dbn_io import read_dbn

    paths, day, universe, stride, tfs = args
    parts = []
    for pth in paths:
        try:
            f = read_dbn(P(pth))
        except Exception as e:                              # noqa: BLE001
            return day, {}, 0, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((P(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, {}, 0, ""
    frame = frame_for(parts, day)
    per: dict[int, list] = {tf: [] for tf in tfs}
    n_sym = 0
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty:
            continue
        df = df.sort_index(kind="mergesort")
        n_sym += 1
        for tf in tfs:
            try:
                a = score_frame(df, day, tf, stride)
            except Exception:                               # noqa: BLE001
                continue
            if len(a):
                per[tf].append(a)
    out = {tf: (np.vstack(v) if v else
                np.empty((0, len(feature_names())), dtype=np.float32))
           for tf, v in per.items()}
    return day, out, n_sym, ""


# --- the samples ---------------------------------------------------------------

def sample_features(s: dict, archive: Path, dataset: str,
                    tfs=TIMEFRAMES) -> tuple[dict, str]:
    """({tf: features}, "") for one sample, or ({}, why not).

    A sample that cannot be measured is REPORTED, never dropped. Nine of the
    twenty-one are from 2026-09-14 and were unmeasurable until that day was
    pulled; a loader that skipped them silently would have made the set look
    complete while the two `pass` rows -- the highest-information rows in the
    file -- were missing.
    """
    from common.entry_features import frame_ctx, features_at
    from common.screen_sim import date_of, window_slices
    from common.dbn_io import read_dbn
    from strategy.mcl import mcl as MCL

    slices = {date_of(p): p for p in window_slices(archive, dataset)}
    days = sorted(slices)
    if s["date"] not in slices:
        return {}, (f"{s['date']} is not in the archive "
                    f"({days[0]} .. {days[-1]})")
    i = days.index(s["date"])
    parts = []
    for d in days[max(0, i - 1):i + 1]:
        f = read_dbn(slices[d])
        if not f.empty:
            parts.append((d, f))
    frame = frame_for(parts, s["date"])
    df = frame[frame["symbol"] == s["symbol"]]
    if df.empty:
        return {}, f"{s['symbol']} has no bars in the {s['date']} slice"
    df = df.sort_index(kind="mergesort")

    got: dict[int, dict] = {}
    for tf in tfs:
        d2 = df
        if tf != 1:
            from strategy.mc5 import mc5 as MC5
            d2 = MC5.to_5m(df)
        if d2 is None or len(d2) < 25:
            continue
        sig = MCL.signals(d2)
        j = bar_index_at(sig, s["date"], s["hhmm"])
        if j is None:
            continue
        local = sig.index.tz_convert(ET)
        f = features_at(sig, j, frame_ctx(sig))
        f["_bar"] = f"{local[j].hour:02d}:{local[j].minute:02d}"
        got[tf] = f
    if not got:
        return {}, f"{s['symbol']} {s['date']}: no bar at or before {s['hhmm']}"
    return got, ""


# --- placement -----------------------------------------------------------------

def bar_index_at(sig, day: str, hhmm: str) -> int | None:
    """The index of the bar CONTAINING `hhmm` ET on `day`, or None.

    Bars are LEFT-LABELLED: a bar stamped 07:35 covers 07:35:00-07:35:59
    (dbn_io, line 10). So the 5-minute bar containing 07:22 is the one stamped
    07:20, and the match is "the last bar of that day stamped at or before the
    sample time", not an equality test -- which would drop every 5-minute
    sample not landing on a multiple of five. Most of them do not, and they
    would have vanished without a line in the report.

    THIS LIVES HERE, not inline in `sample_features`, because the version that
    lived inline could only be tested by a copy of itself. A guard one step
    short of the thing it protects is the defect shape this project keeps
    finding, and I wrote it again here before catching it in a mutation pass.
    """
    local = sig.index.tz_convert(ET)
    want = _date.fromisoformat(day)
    mins = np.array([t.hour * 60 + t.minute if t.date() == want else -1
                     for t in local])
    want_min = int(hhmm[:2]) * 60 + int(hhmm[3:5])
    ok = np.flatnonzero((mins >= 0) & (mins <= want_min))
    return int(ok[-1]) if len(ok) else None


def percentile_of(sorted_vals: np.ndarray, v: float) -> float | None:
    """Percent of the reference strictly below `v`. None if unplaceable.

    `sorted_vals` must already have its NaNs removed. NaN sorts last, so
    searchsorted still finds the right INSERTION POINT -- and then divides it
    by a length that counts the NaNs. On [1, 2, 3, NaN] a sample of 3.5 reads
    75%, not 100%.

    That error runs in the reassuring direction, which is why it is worth a
    guard rather than a comment. `ema200_dist` is NaN on nearly every
    5-minute bar; left in, the denominator would be twenty times the number
    of real values and every sample would land in the bottom few percent of
    it -- ordinary-looking, and onto the RULED OUT list, which is the one
    list in this report that is meant to be acted on.
    """
    if v is None or v != v or len(sorted_vals) == 0:
        return None
    return float(np.searchsorted(sorted_vals, v, side="left")) \
        / len(sorted_vals) * 100.0


def middle(p: float | None, lo: float = 25.0, hi: float = 75.0) -> bool:
    """Is this percentile in the middle half? None is not middle and not
    outer -- it is absent, and counted separately."""
    return p is not None and lo <= p <= hi


def collate(got: dict, names: list[str]) -> dict:
    """{tf: {feature: sorted values, NaNs removed}} from the per-day arrays.

    DAY ORDER, not completion order. Nothing here sums floats, so the result
    would be identical either way -- but every other parallel module in this
    repo merges in day order for a reason that does apply to them, and one
    that merges differently invites the reader to assume the reason is gone.

    NaNs are dropped HERE rather than at the point of use, so no caller can
    forget: see `percentile_of` for what they do to the denominator, and why
    the resulting error points at the one list this report exists to produce.
    """
    out: dict[int, dict[str, np.ndarray]] = {}
    for tf in TIMEFRAMES:
        chunks = [got[d][tf] for d in sorted(got)
                  if tf in got[d] and len(got[d][tf])]
        big = (np.vstack(chunks) if chunks
               else np.empty((0, len(names)), dtype=np.float32))
        per: dict[str, np.ndarray] = {}
        for j, n in enumerate(names):
            v = big[:, j]
            v = np.sort(v[~np.isnan(v)])
            per[n] = v
        out[tf] = per
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--samples", required=True,
                   help="the .xlsx or .csv with symbol, date, time_et, label")
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=0,
                   help="first N sessions of the reference only. For a smoke "
                        "run; a truncated reference is NOT a smaller version "
                        "of the same distribution, it is the earliest part "
                        "of it.")
    p.add_argument("--bar-stride", type=int, default=1,
                   help="keep every Nth bar of each session in the reference. "
                        "1 is every bar. Raising it shrinks memory and the "
                        "report says what was used.")
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    samples = load_samples(Path(a.samples))
    if not samples:
        sys.exit(f"no samples in {a.samples}")
    archive = Path(a.archive) if a.archive else default_archive()
    by_date = load_pit(Path(a.pairs))
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    have = [d for d in days if d in slices]
    if not have:
        sys.exit(f"none of the {len(days)} universe day(s) are in "
                 f"{archive}/{a.dataset}")

    tasks = []
    for k, day in enumerate(have):
        first = max(0, k - WARMUP_SESSIONS)
        tasks.append(([str(slices[d]) for d in have[first:k + 1]], day,
                      by_date[day], max(1, a.bar_stride), TIMEFRAMES))

    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"entry_place: {len(tasks):,} session(s) on {jobs} worker(s)",
          flush=True)
    t0 = time.time()
    got: dict[str, dict] = {}
    syms = 0

    def consume(it):
        nonlocal syms
        for k, (day, per, n_sym, err) in enumerate(it, 1):
            got[day] = per
            syms += n_sym
            if err:
                print(f"  ! {day}: {err}", flush=True)
            if k % 25 == 0:
                print(f"  ... {k:,} of {len(tasks):,}", flush=True)

    if jobs == 1:
        consume(map(run_day, tasks))
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            consume(ex.map(run_day, tasks, chunksize=2))

    names = feature_names()
    ref = collate(got, names)

    placed, failed = [], []
    for s in samples:
        f, why = sample_features(s, archive, a.dataset)
        if not f:
            failed.append((s, why))
        else:
            placed.append((s, f))

    text = render(placed, failed, ref, names, have, syms,
                  a.bar_stride, time.time() - t0, a.pairs)
    emit("\n".join(text), a.out or "var/reports/entry_place.txt",
         header=f"common.entry_place  samples={Path(a.samples).name}")
    return 0


def render(placed, failed, ref, names, have, syms, stride, elapsed,
           pairs_path) -> list[str]:
    n_ref = {tf: (max(len(v) for v in ref[tf].values()) if ref[tf] else 0)
             for tf in ref}
    L = ["WHERE DO BEN'S LABELLED SAMPLES SIT IN THE TAPE THEY CAME FROM?", "",
         f"  {len(placed) + len(failed)} sample(s): {len(placed)} measured, "
         f"{len(failed)} not",
         f"  reference: {len(have):,} session(s) {have[0]} .. {have[-1]} "
         f"from {pairs_path}",
         f"             {syms:,} symbol-day(s), every "
         + ("bar" if stride == 1 else f"{stride}th bar")
         + " of the 04:00-09:30 window",
         "  ".join(f"    {tf}m: {n_ref[tf]:,} bars" for tf in sorted(ref)),
         f"  elapsed {elapsed:.1f}s", ""]

    counts: dict[str, int] = {}
    for s, _ in placed:
        counts[s["label"]] = counts.get(s["label"], 0) + 1
    for s, _ in failed:
        counts[s["label"]] = counts.get(s["label"], 0) + 1
    L += ["THE SET", ""] + \
         [f"  {k:<16}{v:>4}" for k, v in sorted(counts.items())] + [""]

    if failed:
        L += ["NOT MEASURED  (reported, not dropped)", ""]
        for s, why in failed:
            L.append(f"  {s['symbol']:<6} {s['date']} {s['hhmm']}  {why}")
        L.append("")

    L += ["READ THE NEGATIVE DIRECTION FIRST", "",
          "  A sample landing somewhere unusual is NOT evidence. These bars",
          "  were chosen because their outcome was known, "
          f"{len(names)} features were",
          "  tried on each, and roughly half of any bar's features land in an",
          "  outer quartile by construction. There are no halves here to",
          "  disagree and no comparison group worth the name.",
          "",
          "  A feature on which the samples are spread like ordinary bars is",
          "  worth something real: it is RULED OUT as the thing that",
          "  describes what Ben sees. That list is the output of this run.", ""]

    for tf in sorted(ref):
        L += [f"=== {tf}-MINUTE ===", ""]
        if tf == 5:
            L += ["  ema200_dist needs 200 five-minute bars -- about four "
                  "pre-market",
                  "  sessions. The archive window holds one warm-up session, "
                  "so the",
                  "  column is ABSENT here rather than approximate.", ""]
        L += ["  EVERY SAMPLE, EVERY FEATURE  (percentile of the reference)",
              ""]
        for s, f in placed:
            if tf not in f:
                L.append(f"  {s['symbol']:<6} {s['date']} {s['hhmm']}  "
                         f"[{s['label']}]  no {tf}m bar")
                continue
            L.append(f"  {s['symbol']:<6} {s['date']} {s['hhmm']} "
                     f"(bar {f[tf]['_bar']})  [{s['label']}]")
            for n in names:
                p = percentile_of(ref[tf][n], f[tf].get(n))
                v = f[tf].get(n)
                vs = "     n/a" if v is None or v != v else f"{v:>10,.2f}"
                ps = "  --  " if p is None else f"{p:>5.1f}%"
                L.append(f"      {n:<20}{vs}   {ps}")
            L.append("")

        L += [f"  WHERE THE {len(placed)} LAND, FEATURE BY FEATURE", "",
              "    middle = percentile 25-75, where an ordinary bar sits.",
              "    Expect about half the samples there if the feature says",
              "    nothing about them.", ""]
        ruled_out, unusual, absent = [], [], []
        for n in names:
            ps = [percentile_of(ref[tf][n], f[tf].get(n))
                  for s, f in placed if tf in f]
            have_p = [p for p in ps if p is not None]
            if not have_p:
                absent.append(n)
                L.append(f"    {n:<20} absent on every sample")
                continue
            mid = sum(1 for p in have_p if middle(p))
            med = float(np.median(have_p))
            L.append(f"    {n:<20} median {med:>5.1f}%   "
                     f"{mid}/{len(have_p)} in the middle half   "
                     f"[{min(have_p):.0f}% .. {max(have_p):.0f}%]")
            # "Ruled out" is the CONSERVATIVE call and it is deliberately hard
            # to earn: at least half the samples ordinary AND a median that is
            # not itself extreme. Anything else goes on the other list, which
            # carries the warning above.
            if mid >= len(have_p) / 2 and 20.0 <= med <= 80.0:
                ruled_out.append(n)
            else:
                unusual.append(n)
        L += ["",
              f"    RULED OUT  {len(ruled_out):>2} of {len(names)}   "
              + (", ".join(ruled_out) if ruled_out else "none"),
              f"    unusual    {len(unusual):>2}          "
              + (", ".join(unusual) if unusual else "none")]
        if absent:
            L.append(f"    absent     {len(absent):>2}          "
                     + ", ".join(absent))
        L.append("")

    L += ["WHAT HAPPENS NEXT, AND WHAT MUST NOT", "",
          "  MUST NOT: pick the feature with the most extreme median and add",
          "  it as a condition. That is the whole failure mode. The samples",
          "  are 21, the features are "
          f"{len(names)}, and the base rate for the move they",
          "  are drawn from is 0.108% -- one bar in 926.",
          "",
          "  CAN: take the RULED OUT list as settled. Those quantities do not",
          "  distinguish the bars Ben picks from the bars he does not, on",
          "  this tape, and no threshold on them would have.",
          "",
          "  CAN: if a feature survives on BOTH timeframes and the `pass`",
          "  rows sit opposite the `took` rows on it, register that as a",
          "  hypothesis in writing, with its direction and threshold fixed,",
          "  BEFORE any backtest is run against it. `var/state/holdout.json`",
          "  stays shut either way -- it was cut 2026-09-07 and is not spent",
          "  on a search.",
          "",
          "  The 3 `pass` rows cannot carry a comparison on their own. More",
          "  `pass` examples are the highest-information thing Ben can add:",
          "  every one of them is a bar that looked takeable and was not.", ""]
    return L


if __name__ == "__main__":
    raise SystemExit(main())
