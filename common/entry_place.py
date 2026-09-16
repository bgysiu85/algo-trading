#!/usr/bin/env python3
"""Where do Ben's labelled samples sit in the tape they came from?

    python -m common.entry_place --samples "Samples - Momentum Trading.xlsx"

THE QUESTION, AND WHY IT IS THIS ONE
------------------------------------
Ben supplied 21 screenshots of bars he would have taken, taken and lost, or
passed on. The tempting move is to fit a rule to them. That move is wrong here
and it is worth being precise about why:

  * The base rate for the kind of move these samples are drawn from is 0.108%
    -- about 1 bar in 926 (`run_signal`). A couple of dozen positives against
    that base rate cannot distinguish a real edge from the shape of a couple
    of dozen arbitrary bars.
  * Twenty-seven features against that many points, with no halves to
    disagree, is a search with nothing to catch it.
  * The labels are written AFTER the outcomes are known.

TWO COMPARISONS, AND THEY ANSWER DIFFERENT QUESTIONS
-----------------------------------------------------
The set grew: three `pass` rows became six, and on 2026-09-16 Ben added a
won/loss column, so `took` now asserts a win instead of meaning "I would take
this". That makes two cuts possible, and conflating them is the mistake this
module is one step away from at all times:

  TAKE against PASS   describes what he SELECTS. A feature that separates
                      these says nothing about whether the selection makes
                      money -- `range_pct` separates them cleanly and does
                      NOT separate his winners from his losers.

  WON against LOST    is the only cut that does not restate his own criterion
                      back at him, and the only one about outcome.

The report counts both from the set rather than describing them in prose. A
hard-coded sentence about the data is a second source of truth about the data,
and the first version of this file carried one that went stale twice.

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
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit.json"
TIMEFRAMES = (1, 5)

# WHICH BARS THE SAMPLES ARE COMPARED AGAINST, and it decides what the word
# "unusual" in this report means.
#
# The first run used `all` and reported 22 of 27 features as unusual on the
# 1-minute view, with medians clustered at the 80th-94th percentile. That is
# not a finding about Ben's eye. `all` is every bar of the pre-market window,
# and that population is mostly DEAD MINUTES -- the archive frames are
# gap-filled and LGHL 2026-05-21 has 1,999 of its 2,770 bars at zero volume.
# He screenshots bars where something is happening. Of course they sit at the
# 93rd percentile of volume against a tape that is mostly not trading.
#
# That is this project's signature defect appearing inside the instrument
# built to look for it: a control whose output is indistinguishable from the
# thing it is meant to detect. The fix is not a different threshold, it is a
# different denominator.
#
# Every alternative below is defined by the STRATEGY'S OWN columns, never by a
# cut-off chosen here -- a hand-picked activity threshold would be a fitted
# parameter smuggled into the control.
REFERENCES = {
    "all": "every bar of the 04:00-09:30 window. Mostly dead minutes, so "
           "almost any bar a human would screenshot scores as unusual; useful "
           "only for the RULED OUT direction.",
    "signal": "bars where MCL's volume clause holds (c_vol: volume >= 3x "
              "prev_vol, prev_vol > 0). The bars something was happening on, "
              "by the strategy's own definition.",
    "entry": "bars MCL would have ENTERED on -- all five conditions. The "
             "sharpest question available: of the bars the strategy picks, "
             "do Ben's look different?",
}

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

# An OPTIONAL outcome column, added by Ben on 2026-09-16 after the first runs
# showed that `took` did not assert a win -- it meant "I would take this", with
# the result unstated, which left the only non-tautological comparison in the
# report (his winners against his losers) resting on an assumption.
#
# Matched on a PREFIX because the header in the sheet is actually "wonl/loss",
# and pinning that string would break the loader the moment he fixes the typo.
# Absent entirely on older sheets and on the csv fixtures, so it must stay
# optional: a required column would turn every earlier sample file into an
# error.
OUTCOME_HEADERS = ("won", "win", "outcome", "result")


def normalise_outcome(raw) -> str | None:
    """"won", "lost", or None. The raw text is kept separately -- one of his
    wins is annotated "won (but it was honestly a fluke)", and a loader that
    reduced that to "won" and threw the sentence away would delete the one
    piece of information that says not to trust that row."""
    if raw is None:
        return None
    t = str(raw).strip().lower()
    if not t:
        return None
    if t.startswith(("won", "win")):
        return "won"
    if "lost" in t or "loss" in t:
        return "lost"
    return None


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
    # No exclusion of the label/note columns here. A mutation pass showed that
    # guard was unreachable -- a header cannot begin with both "note" and one
    # of OUTCOME_HEADERS, and a label column named for an outcome word would
    # already have failed `col("label")`. An unreachable guard is noise that
    # reads like protection.
    i_out = None
    for k, h in enumerate(head):
        if h.startswith(OUTCOME_HEADERS):
            i_out = k
            break
    out = []
    for r in rows[1:]:
        if not r or r[i_sym] in (None, ""):
            continue
        raw = r[i_out] if (i_out is not None and i_out < len(r)) else None
        out.append({
            "symbol": str(r[i_sym]).upper().strip(),
            "date": _as_date(r[i_date]),
            "hhmm": _as_hhmm(r[i_time]),
            "label": normalise_label(r[i_lab]),
            "outcome": normalise_outcome(raw),
            "outcome_note": "" if raw is None else str(raw).strip(),
            "note": "" if r[i_note] is None else str(r[i_note]),
        })
    return out


def _rows_from_xlsx(path: Path) -> list[list]:
    """One sheet of an .xlsx, through openpyxl when it is installed.

    TWO READERS, AND A TEST THAT THEY AGREE
    ---------------------------------------
    openpyxl is the right tool and is preferred whenever it imports. But the
    first live run of this module died on `pip install openpyxl`, and a report
    that cannot be produced because the venv is missing a package is a report
    that does not exist. So `_rows_from_xlsx_stdlib` reads the same sheet from
    zipfile and ElementTree -- an .xlsx is a zip of XML -- and takes over when
    the import fails.

    Two code paths for one value is the shape this project keeps finding
    defects in, so it is not left to hope:
    `test_the_two_xlsx_readers_agree` builds a workbook with openpyxl and
    asserts `load_samples` returns identical rows through both. A hand-rolled
    parser of somebody else's format is worth exactly as much as its oracle.
    """
    try:
        import openpyxl
    except ImportError:
        return _rows_from_xlsx_stdlib(path)
    wb = openpyxl.load_workbook(path, data_only=True)
    return [list(r) for r in wb[wb.sheetnames[0]].iter_rows(values_only=True)]


def _rows_from_xlsx_stdlib(path: Path) -> list[list]:
    """The same sheet without openpyxl. See `_rows_from_xlsx`.

    Values come back RAW -- a string, or a float. Dates and times in a
    spreadsheet are serial numbers whose date-ness lives in a style record, and
    this reader deliberately does not consult the styles: `_as_date` and
    `_as_hhmm` interpret the number instead, so there is one place that decides
    what a cell means rather than two that can disagree.
    """
    import re as _re
    import xml.etree.ElementTree as ET
    import zipfile

    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"

    def col_index(ref: str) -> int:
        """'AB12' -> 27. The `r` attribute is the ONLY reliable column: a run
        of empty cells is simply absent from the XML, so counting <c> elements
        shifts every column after the first blank."""
        n = 0
        for ch in ref:
            if not ch.isalpha():
                break
            n = n * 26 + (ord(ch.upper()) - 64)
        return n - 1

    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        sys.exit(f"{path} is not a readable .xlsx (not a zip). If it is an old "
                 f".xls, save it as .xlsx or .csv.")
    with z:
        names = set(z.namelist())
        # The first sheet in WORKBOOK order, resolved through the rels file.
        # Zip order is not sheet order and sheet1.xml is not always the first
        # tab -- picking by filename works until someone reorders the tabs.
        target = "xl/worksheets/sheet1.xml"
        try:
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            first = wb.find(f"{NS}sheets/{NS}sheet")
            rid = first.get(f"{REL}id")
            rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            for rel in rels:
                if rel.get("Id") == rid:
                    t = rel.get("Target").lstrip("/")
                    target = t if t.startswith("xl/") else "xl/" + t
                    break
        except (KeyError, AttributeError, ET.ParseError):
            pass
        if target not in names:
            sys.exit(f"{path}: cannot find the first worksheet ({target}).")

        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                # Concatenate every <t>: rich text splits one string across
                # several runs, and taking only the first loses the rest.
                shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))

        rows: list[list] = []
        for row in ET.fromstring(z.read(target)).iter(f"{NS}row"):
            cells: dict[int, object] = {}
            for c in row.findall(f"{NS}c"):
                k = col_index(c.get("r") or "A")
                typ = c.get("t")
                if typ == "inlineStr":
                    v = "".join(t.text or "" for t in c.iter(f"{NS}t"))
                else:
                    vt = c.find(f"{NS}v")
                    if vt is None or vt.text is None:
                        continue
                    raw = vt.text
                    if typ == "s":
                        v = shared[int(raw)] if int(raw) < len(shared) else ""
                    elif typ == "b":
                        v = raw == "1"
                    elif typ in (None, "n"):
                        try:
                            v = float(raw)
                        except ValueError:
                            v = raw
                    else:                       # "str" (formula), "e" (error)
                        v = raw
                if v != "":
                    cells[k] = v
            width = (max(cells) + 1) if cells else 0
            rows.append([cells.get(i) for i in range(width)])

    # NO trailing-blank-row trim, deliberately. openpyxl returns those rows,
    # `load_samples` already skips any row without a symbol, and trimming here
    # made the two readers return different row counts for the same file --
    # which is the one thing the agreement test exists to prevent. A mutation
    # pass found it: nothing could tell the trim from its absence except the
    # oracle, and against the oracle the trim was the wrong answer.
    if not rows:
        return []
    width = max(len(r) for r in rows)
    return [r + [None] * (width - len(r)) for r in rows]


# Excel's day zero. 1899-12-30, not 1899-12-31, because Excel believes 1900
# was a leap year; the off-by-one and the phantom 29 February cancel for every
# date after 1900-03-01, which is every date this project will ever see.
EXCEL_EPOCH = _date(1899, 12, 30)


def _as_date(v) -> str:
    """YYYY-MM-DD from a datetime, a date, an Excel serial, or a string."""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, _date):
        return v.isoformat()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        # A serial date is a day count. Anything under 1000 is not a date --
        # it is a number in the wrong column, and guessing 1902 from it would
        # put a sample three days into the archive and lose it quietly.
        if float(v) < 1000:
            sys.exit(f"cannot read {v!r} as a date")
        return (EXCEL_EPOCH + timedelta(days=int(float(v)))).isoformat()
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
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        frac = float(v) % 1.0
        # A whole number here is a date serial in the time column, or a bare
        # integer. Both would render as 00:00, which is a real pre-market
        # minute -- so it has to be an error, not a default.
        if frac == 0.0:
            sys.exit(f"cannot read {v!r} as a time of day")
        mins = int(round(frac * 24 * 60))
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


def reference_mask(sig, which: str) -> np.ndarray:
    """Boolean over `sig` selecting the bars the reference is built from.

    The columns are MCL's own (`c_vol`, `entry`), so nothing here invents a
    threshold. An unknown name is a crash, not a silent fall back to `all`:
    a reference that is not the one asked for is the one error this module
    cannot afford, because every percentile in the report is measured
    against it.
    """
    n = len(sig)
    if which == "all":
        return np.ones(n, dtype=bool)
    col = {"signal": "c_vol", "entry": "entry"}[which]
    return sig[col].to_numpy(dtype=bool, na_value=False)


def score_frame(df, day: str, tf: int, stride: int,
                which: str = "all") -> np.ndarray:
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
    keep = reference_mask(sig, which)
    idx = idx[keep[idx]]
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

    paths, day, universe, stride, tfs, which = args
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
                a = score_frame(df, day, tf, stride, which)
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
    p.add_argument("--reference", default="all", choices=sorted(REFERENCES),
                   help="which bars the samples are placed against. "
                        + "  ".join(f"`{k}`: {v}" for k, v in REFERENCES.items()))
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
                      by_date[day], max(1, a.bar_stride), TIMEFRAMES,
                      a.reference))

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
                  a.bar_stride, time.time() - t0, a.pairs, a.reference)
    out = a.out or f"var/reports/entry_place_{a.reference}.txt"
    emit("\n".join(text), out,
         header=f"common.entry_place  samples={Path(a.samples).name}  "
                f"reference={a.reference}")
    return 0


# A feature has to be measurable on most of the samples before it is called
# either ruled out or unusual. The first run printed
#
#     vol_over_trail   median 93.1%   0/2 in the middle half
#
# on the 5-minute view and listed it under `unusual` beside features measured
# on all 21 -- a median of two, presented as comparable with a median of
# twenty-one. `vol_over_trail` and `floor_margin` need MCL's 60-bar shifted
# mean, and a sample whose symbol did not trade the previous pre-market
# session has no warm-up and so has no value. That is honest as an `n/a` per
# sample and dishonest as a summary line.
MIN_COVERAGE = 0.6


def render(placed, failed, ref, names, have, syms, stride, elapsed,
           pairs_path, which="all") -> list[str]:
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
         f"  reference population: {which} -- {REFERENCES[which]}",
         "  ".join(f"    {tf}m: {n_ref[tf]:,} bars" for tf in sorted(ref)),
         f"  elapsed {elapsed:.1f}s", ""]

    counts: dict[str, int] = {}
    for s, _ in placed:
        counts[s["label"]] = counts.get(s["label"], 0) + 1
    for s, _ in failed:
        counts[s["label"]] = counts.get(s["label"], 0) + 1
    L += ["THE SET", ""] + \
         [f"  {k:<16}{v:>4}" for k, v in sorted(counts.items())] + [""]

    # LABEL against OUTCOME, printed whenever the outcome column exists.
    #
    # Today every `took` is marked `won`, so the two fields agree and the
    # cross-tab is redundant. It is here for the day they stop agreeing: the
    # report groups by LABEL, so a `took` later marked lost would sit in the
    # winners' group and quietly move the one comparison in this report that
    # is not a tautology. A divergence has to be visible, not inferred.
    pairs = [(s["label"], s.get("outcome")) for s, _ in placed] + \
            [(s["label"], s.get("outcome")) for s, _ in failed]
    if any(o for _, o in pairs):
        seen: dict[tuple, int] = {}
        for k in pairs:
            seen[k] = seen.get(k, 0) + 1
        L += ["LABEL AGAINST OUTCOME", ""]
        for (lab, out), n in sorted(seen.items(), key=lambda x: str(x[0])):
            L.append(f"  {lab:<16}{str(out or '-'):<8}{n:>4}")
        bad = [(lab, out, n) for (lab, out), n in seen.items()
               if (lab == "took" and out == "lost")
               or (lab == "took-and-lost" and out == "won")
               or (lab == "pass" and out)]
        L.append("")
        if bad:
            L += ["  *** LABEL AND OUTCOME DISAGREE ***", "",
                  "  The groups below are cut on LABEL. These rows say "
                  "something else:", ""]
            L += [f"    {lab} marked {out}: {n}" for lab, out, n in bad]
            L += ["", "  Fix the sheet, or the winners' group contains a "
                  "loser.", ""]
        # An annotated outcome is the row saying "do not trust me".
        notes = [(s["symbol"], s["hhmm"], s["outcome_note"])
                 for s, _ in placed
                 if s.get("outcome_note")
                 and s["outcome_note"].strip().lower() not in ("won", "lost",
                                                               "win", "loss")]
        if notes:
            L += ["  outcomes the sheet qualifies in words:", ""]
            L += [f"    {sym} {hh}  {txt}" for sym, hh, txt in notes]
            L += ["", "  A win the trader does not endorse is not a win to "
                  "fit against.", ""]

    if failed:
        L += ["NOT MEASURED  (reported, not dropped)", ""]
        for s, why in failed:
            L.append(f"  {s['symbol']:<6} {s['date']} {s['hhmm']}  {why}")
        L.append("")

    # WHAT THIS SET CAN AND CANNOT CARRY, COUNTED FROM THE SET.
    #
    # This paragraph used to assert "there is no comparison group worth the
    # name". That was true of the first 21 samples -- three passes and no
    # outcome column -- and became false twice: once when the passes doubled,
    # and again when Ben added won/lost. A hard-coded description of the data
    # is a SECOND SOURCE OF TRUTH about the data, and it drifts. This project
    # has now found that shape in a loader, a guard, a metric and a report.
    #
    # So the counts come from `placed`, and the caveat is phrased from them.
    n_took = sum(1 for s, _ in placed if s["label"] == "took")
    n_lost = sum(1 for s, _ in placed if s["label"] == "took-and-lost")
    n_pass = sum(1 for s, _ in placed if s["label"] == "pass")
    cmp_lines = []
    if n_took >= 5 and n_pass >= 5:
        cmp_lines.append(f"  TAKE against PASS is available: {n_took} vs "
                         f"{n_pass}. It describes what he SELECTS, and a "
                         "feature that")
        cmp_lines.append("  separates them says nothing about whether the "
                         "selection makes money.")
    if n_took >= 5 and n_lost >= 5:
        cmp_lines.append(f"  WON against LOST is available: {n_took} vs "
                         f"{n_lost}. It is the only cut here that does not")
        cmp_lines.append("  restate his own criterion back at him, and the "
                         "only one about OUTCOME.")
    if not cmp_lines:
        cmp_lines = ["  Neither comparison has enough rows on both sides to "
                     "be worth cutting."]

    L += ["READ THE NEGATIVE DIRECTION FIRST", "",
          "  A sample landing somewhere unusual is NOT evidence. These bars",
          "  were chosen because their outcome was known, "
          f"{len(names)} features were",
          "  tried on each, and roughly half of any bar's features land in an",
          "  outer quartile by construction. There are no halves here to",
          "  disagree, and the labels were written after the outcomes were",
          "  known.",
          "",
          "  A feature on which the samples are spread like ordinary bars is",
          "  worth something real: it is RULED OUT as the thing that",
          "  describes what Ben sees. That list is the output of this run.",
          "",
          "  THE TWO COMPARISONS, AND THEY ANSWER DIFFERENT QUESTIONS", ""
          ] + cmp_lines + [""]

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
        ruled_out, unusual, absent, thin = [], [], [], []
        n_meas = sum(1 for s, f in placed if tf in f)
        floor = max(2, int(np.ceil(n_meas * MIN_COVERAGE)))
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
            tag = "" if len(have_p) >= floor else "   TOO THIN TO PLACE"
            L.append(f"    {n:<20} median {med:>5.1f}%   "
                     f"{mid}/{len(have_p)} in the middle half   "
                     f"[{min(have_p):.0f}% .. {max(have_p):.0f}%]{tag}")
            if len(have_p) < floor:
                thin.append(f"{n} ({len(have_p)}/{n_meas})")
                continue
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
        if thin:
            L.append(f"    too thin   {len(thin):>2}          "
                     f"measured on fewer than {floor} of {n_meas} samples: "
                     + ", ".join(thin))
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
