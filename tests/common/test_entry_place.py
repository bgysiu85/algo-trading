#!/usr/bin/env python3
"""Can the placement instrument be trusted to DISCONFIRM?

This module's whole value is the RULED OUT list -- the features on which Ben's
samples are indistinguishable from ordinary bars. Every failure mode here
produces a list that is wrong in the flattering direction:

  * a NaN left in a reference column deflates every percentile on it
  * a sample silently dropped shrinks the set without saying so
  * a 5-minute sample matched by equality on the stamp vanishes
  * a reference built from a different tape than the samples

so those are what these tests are about.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from common import entry_place as P

ET = ZoneInfo("America/New_York")


def bars(n=700, day="2026-09-14", seed=0, symbol="AAAA", start_prior=True):
    """1-minute bars over a warm-up session and the target session."""
    rng = np.random.default_rng(seed)
    idx = []
    d = datetime.strptime(day, "%Y-%m-%d").date()
    days = [d - timedelta(days=1), d] if start_prior else [d]
    per = n // len(days)
    for dd in days:
        t0 = pd.Timestamp(datetime.combine(dd, dtime(4, 0), tzinfo=ET))
        idx += [t0 + timedelta(minutes=i) for i in range(per)]
    m = len(idx)
    c = 7.0 + np.cumsum(rng.normal(0.002, 0.02, m))
    hi = c + np.abs(rng.normal(0.02, 0.01, m))
    lo = c - np.abs(rng.normal(0.02, 0.01, m))
    return pd.DataFrame(
        {"open": c, "high": hi, "low": lo, "close": c,
         "volume": rng.integers(100, 9000, m).astype(float),
         "symbol": symbol},
        index=pd.DatetimeIndex(idx).tz_convert("UTC"))


# --- the loader ----------------------------------------------------------------

def test_a_label_it_does_not_recognise_is_counted_not_dropped():
    """One of the 21 rows has a blank label. A loader that skipped unknown
    spellings would change the population without saying so, and the spelling
    in that sheet is not consistent -- 'Pass', 'pass', 'took and lost'."""
    assert P.normalise_label("Pass") == "pass"
    assert P.normalise_label("took and lost") == "took-and-lost"
    assert P.normalise_label(None) == P.UNLABELLED
    assert P.normalise_label("scalped it") == P.UNLABELLED


def test_excel_fraction_of_a_day_reads_as_a_time():
    """A cell typed as text in one row and formatted as a time in the next
    comes back as 0.2923611 for 07:01. str()[:5] turns that into '0.292' and
    the sample disappears."""
    assert P._as_hhmm(dtime(7, 1)) == "07:01"
    assert P._as_hhmm("7:01") == "07:01"
    assert P._as_hhmm((7 * 60 + 1) / (24 * 60)) == "07:01"


def test_csv_and_xlsx_load_the_same_rows(tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text("symbol,date,time_et,label (x),note\n"
                   "crbp,2026-09-14,07:19,Pass,8.png\n", encoding="utf-8")
    got = P.load_samples(csv)
    assert got == [{"symbol": "CRBP", "date": "2026-09-14", "hhmm": "07:19",
                    "label": "pass", "outcome": None, "outcome_note": "",
                    "note": "8.png"}]


def test_a_missing_column_says_which_one(tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text("symbol,date,label (x),note\nA,2026-01-01,took,\n",
                   encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        P.load_samples(csv)
    assert "time" in str(e.value)


# --- the percentile ------------------------------------------------------------

def test_a_nan_in_the_reference_deflates_every_percentile():
    """NaN sorts last, so searchsorted finds the right insertion point and
    then divides it by a length that counts the NaNs.

    I wrote this test first believing the failure was a 100th-percentile
    reading on everything. It is the opposite, and the opposite is worse: a
    sample above every real value reads 75%, not 100%, and on a column that
    is mostly NaN -- `ema200_dist` on 5-minute bars -- every sample would land
    in the bottom few percent, look ordinary, and join the RULED OUT list.
    That list is the one thing in this report meant to be acted on.

    So the trap is pinned as it actually behaves, then the guard is shown to
    hold."""
    dirty = np.array([1.0, 2.0, 3.0, np.nan])
    assert np.searchsorted(dirty, 3.5, side="left") / len(dirty) == 0.75
    assert np.searchsorted(np.array([1.0, 2.0, 3.0]), 3.5) / 3 == 1.0

    got = {"d": {1: np.array([[1.0], [2.0], [np.nan], [3.0]],
                             dtype=np.float32)}}
    ref = P.collate(got, ["f"])
    assert len(ref[1]["f"]) == 3
    assert P.percentile_of(ref[1]["f"], 0.5) == pytest.approx(0.0)
    assert P.percentile_of(ref[1]["f"], 2.5) == pytest.approx(200 / 3)


def test_percentile_is_none_when_the_sample_has_no_value():
    ref = np.array([1.0, 2.0, 3.0])
    assert P.percentile_of(ref, None) is None
    assert P.percentile_of(ref, float("nan")) is None
    assert P.percentile_of(np.empty(0), 1.0) is None


def test_middle_treats_absent_as_absent_not_as_ordinary():
    """None must not count towards 'in the middle half'. Counting absent
    values as ordinary is how a feature that could not be computed on any
    sample ends up on the RULED OUT list."""
    assert P.middle(50.0)
    assert not P.middle(5.0)
    assert not P.middle(None)


# --- the 5-minute match --------------------------------------------------------

def test_a_five_minute_sample_matches_the_bar_that_CONTAINS_it():
    """Bars are left-labelled. The 5-minute bar containing 07:22 is stamped
    07:20. An equality test on the stamp would drop every sample not landing
    on a multiple of five -- which is most of them, and they would vanish
    without a line in the report.

    The first version of this test recomputed the match instead of calling
    it, so swapping the module's `<=` for `==` left it green: a guard one
    step short of the thing it protects, written into the test for the guard
    against exactly that. It calls `bar_index_at` now.
    """
    from strategy.mc5 import mc5 as MC5
    from strategy.mcl import mcl as MCL

    sig = MCL.signals(MC5.to_5m(bars(n=700)))
    local = sig.index.tz_convert(ET)
    j = P.bar_index_at(sig, "2026-09-14", "07:22")
    assert j is not None
    assert (local[j].hour, local[j].minute) == (7, 20)
    # a time that IS on the boundary still lands on its own bar, not the
    # one before it
    k = P.bar_index_at(sig, "2026-09-14", "07:20")
    assert k == j


def test_bar_index_at_returns_none_rather_than_a_neighbouring_day():
    from strategy.mcl import mcl as MCL
    sig = MCL.signals(bars(n=700))
    assert P.bar_index_at(sig, "2026-09-14", "03:59") is None
    assert P.bar_index_at(sig, "2099-01-01", "07:22") is None


def test_a_feature_that_puts_the_samples_somewhere_extreme_is_NOT_ruled_out():
    """The RULED OUT list is the only actionable output of this report. A
    feature wrongly on it is a quantity Ben would stop looking at on the
    strength of a run that never measured it properly."""
    names = ["flat", "extreme"]
    ref = _fake_ref(names)
    placed = _fake_placed(names, n=8)
    for _, f in placed:
        for tf in P.TIMEFRAMES:
            f[tf]["flat"] = 0.0                 # dead centre of a N(0,1)
            f[tf]["extreme"] = 9.9              # above every reference value
    text = "\n".join(P.render(placed, [], ref, names, ["2026-09-14"], 10, 1,
                              1.0, "p.json"))
    for block in text.split("=== ")[1:]:
        ruled = [l for l in block.splitlines() if "RULED OUT" in l][0]
        unusual = [l for l in block.splitlines() if "unusual " in l][0]
        assert "flat" in ruled and "extreme" not in ruled
        assert "extreme" in unusual


# --- the frame -----------------------------------------------------------------

def test_the_reference_scores_the_target_day_only():
    """The warm-up session is in the frame so the indicators are warm. Scoring
    its bars too would put a second copy of every prior session into the
    reference and weight the early days double."""
    from strategy.mcl import mcl as MCL
    df = bars(n=700)
    sig = MCL.signals(df)
    idx = P.bars_of_day(sig, "2026-09-14")
    assert len(idx) == 350
    local = sig.index.tz_convert(ET)
    assert all(local[i].date().isoformat() == "2026-09-14" for i in idx)


def test_score_frame_returns_one_row_per_scored_bar_and_the_right_width():
    from common.entry_features import FEATURES
    df = bars(n=700)
    a = P.score_frame(df, "2026-09-14", 1, 1)
    assert a.shape == (350, len(FEATURES))
    assert a.dtype == np.float32


def test_bar_stride_thins_the_reference_and_nothing_else():
    a1 = P.score_frame(bars(n=700), "2026-09-14", 1, 1)
    a5 = P.score_frame(bars(n=700), "2026-09-14", 1, 5)
    assert len(a5) == len(range(0, len(a1), 5))
    np.testing.assert_allclose(a5[0], a1[0], equal_nan=True)
    np.testing.assert_allclose(a5[1], a1[5], equal_nan=True)


def test_the_five_minute_view_has_no_ema200_and_says_so_by_being_nan():
    """200 five-minute bars is about four pre-market sessions and the archive
    window holds one. The column must be ABSENT, not a shorter EMA wearing the
    name of a 200-period one."""
    from common.entry_features import FEATURES
    names = list(FEATURES)
    j = names.index("ema200_dist")
    a = P.score_frame(bars(n=700), "2026-09-14", 5, 1)
    assert len(a)
    assert np.isnan(a[:, j]).all()
    # and the 1-minute view, which has 700 bars, does have it
    b = P.score_frame(bars(n=700), "2026-09-14", 1, 1)
    assert not np.isnan(b[:, j]).all()


# --- the report ----------------------------------------------------------------

def _fake_placed(names, n=6):
    rng = np.random.default_rng(3)
    out = []
    for k in range(n):
        f = {tf: {nm: float(rng.normal(0, 1)) for nm in names}
             for tf in P.TIMEFRAMES}
        for tf in P.TIMEFRAMES:
            f[tf]["_bar"] = "07:20"
        out.append(({"symbol": f"S{k}", "date": "2026-09-14",
                     "hhmm": "07:22", "label": "took", "note": ""}, f))
    return out


def _fake_ref(names, n=4000, seed=1):
    rng = np.random.default_rng(seed)
    return {tf: {nm: np.sort(rng.normal(0, 1, n)) for nm in names}
            for tf in P.TIMEFRAMES}


def test_the_report_leads_with_what_it_cannot_show():
    names = ["a", "b", "c"]
    text = "\n".join(P.render(_fake_placed(names), [], _fake_ref(names),
                              names, ["2026-09-14"], 10, 1, 1.0, "p.json"))
    lead = text.index("READ THE NEGATIVE DIRECTION FIRST")
    assert lead < text.index("=== 1-MINUTE ===")
    assert "is NOT evidence" in text
    assert "RULED OUT" in text


def test_a_sample_that_could_not_be_measured_appears_in_the_report():
    """Nine of the twenty-one were unmeasurable until 2026-09-14 was pulled,
    and both original `pass` rows were among them. A set that looks complete
    while its most informative rows are missing is the failure this guards."""
    names = ["a"]
    bad = ({"symbol": "ZZZZ", "date": "2099-01-01", "hhmm": "07:00",
            "label": "pass", "note": ""}, "2099-01-01 is not in the archive")
    text = "\n".join(P.render(_fake_placed(names), [bad], _fake_ref(names),
                              names, ["2026-09-14"], 10, 1, 1.0, "p.json"))
    assert "NOT MEASURED" in text
    assert "ZZZZ" in text
    assert "is not in the archive" in text
    # the header counts it too: 6 measured + 1 not, out of 7
    assert "7 sample(s): 6 measured, 1 not" in text


def test_every_feature_is_printed_including_the_flat_ones():
    """Reporting only the features that put the samples somewhere unusual is
    the selection this whole family of modules exists to resist."""
    names = ["a", "b", "c", "d"]
    text = "\n".join(P.render(_fake_placed(names), [], _fake_ref(names),
                              names, ["2026-09-14"], 10, 1, 1.0, "p.json"))
    for nm in names:
        # once per sample per timeframe, plus once in each summary
        assert text.count(nm) >= len(P.TIMEFRAMES) * (6 + 1)


def test_a_feature_absent_on_every_sample_is_not_called_ruled_out():
    """Absent is not ordinary. A column that could not be computed anywhere
    must not join the list of things this run has settled."""
    names = ["a"]
    placed = _fake_placed(names, n=4)
    for _, f in placed:
        for tf in P.TIMEFRAMES:
            f[tf]["a"] = float("nan")
    text = "\n".join(P.render(placed, [], _fake_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))
    assert "absent on every sample" in text
    assert "RULED OUT   0 of 1" in text


def test_the_report_refuses_to_recommend_a_threshold():
    names = ["a"]
    text = "\n".join(P.render(_fake_placed(names), [], _fake_ref(names),
                              names, ["2026-09-14"], 10, 1, 1.0, "p.json"))
    assert "MUST NOT" in text
    assert "0.108%" in text
    assert "holdout.json" in text


def test_the_reference_and_the_samples_come_from_the_same_archive():
    """Not a style point. A reference from bar_cache/ (IB's tape) and samples
    from the archive (XNAS.BASIC) would give percentiles that look comparable
    and are not -- the defect already found in five places in this repo."""
    import inspect
    src = inspect.getsource(P)
    assert "bar_cache" not in src.replace("`bar_cache/`", "")
    assert "load_cached_bars" not in src


# --- end to end, against a fake archive ----------------------------------------
#
# Ben's last two pull commands both printed success-shaped output and fetched
# nothing. A module whose report renders fine on an empty reference has the
# same defect one layer up, so main() is driven here rather than trusted.

def _fake_archive(monkeypatch, tmp_path, days, symbols):
    """Patch the two archive entry points so no .dbn.zst is needed."""
    from common import entry_place as M

    paths = {d: tmp_path / f"{d}_0400_0930.dbn.zst" for d in days}
    for p in paths.values():
        p.write_bytes(b"")

    frames = {}
    for k, d in enumerate(days):
        parts = [bars(n=350, day=d, seed=k * 10 + j, symbol=s,
                      start_prior=False)
                 for j, s in enumerate(symbols)]
        frames[str(paths[d])] = pd.concat(parts).sort_index()

    monkeypatch.setattr("common.dbn_io.read_dbn",
                        lambda p, **kw: frames[str(p)])
    monkeypatch.setattr("common.screen_sim.window_slices",
                        lambda a, ds: sorted(paths.values()))
    monkeypatch.setattr(M, "default_archive_for_test", None, raising=False)
    return paths


def test_main_runs_end_to_end_and_the_reference_is_not_empty(
        monkeypatch, tmp_path):
    import json
    days = ["2026-09-10", "2026-09-11", "2026-09-14"]
    syms = ["AAAA", "BBBB"]
    _fake_archive(monkeypatch, tmp_path, days, syms)

    pairs = tmp_path / "pit.json"
    pairs.write_text(json.dumps(
        [{"symbol": s, "date": d, "first_seen": f"{d}T08:00:00+00:00"}
         for d in days for s in syms]), encoding="utf-8")
    samples = tmp_path / "s.csv"
    samples.write_text(
        "symbol,date,time_et,label (x),note\n"
        "AAAA,2026-09-14,07:22,took,a\n"
        "BBBB,2026-09-14,08:15,Pass,b\n"
        "ZZZZ,2026-09-14,08:15,took,c\n"          # not in the tape
        "AAAA,2099-01-01,08:15,took,d\n",          # not in the archive
        encoding="utf-8")
    out = tmp_path / "r.txt"

    rc = P.main(["--samples", str(samples), "--pairs", str(pairs),
                 "--archive", str(tmp_path), "--out", str(out), "--jobs", "1"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")

    # the reference actually has bars in it -- the whole point
    assert " 1m: " in text and " 5m: " in text
    assert " 1m: 0 bars" not in text
    # both unmeasurable rows are named, not dropped
    assert "4 sample(s): 2 measured, 2 not" in text
    assert "ZZZZ" in text and "2099-01-01" in text
    # and the measured ones are placed on both timeframes
    assert "=== 1-MINUTE ===" in text and "=== 5-MINUTE ===" in text
    assert "RULED OUT" in text


def _uniform_ref(names, n=1000):
    """A reference where percentile == value/10, so a test can place a sample
    exactly where it means to."""
    v = np.arange(n, dtype=np.float64)
    return {tf: {nm: v.copy() for nm in names} for tf in P.TIMEFRAMES}


def _place(names, pcts):
    """One sample per entry in `pcts`, each at that percentile on every
    feature named in it."""
    out = []
    for k, per in enumerate(pcts):
        f = {tf: {nm: v * 10.0 for nm, v in per.items()} for tf in P.TIMEFRAMES}
        for tf in P.TIMEFRAMES:
            f[tf]["_bar"] = "07:20"
        out.append(({"symbol": f"S{k}", "date": "2026-09-14", "hhmm": "07:22",
                     "label": "took", "note": ""}, f))
    return out


def test_a_SPLIT_set_is_not_ruled_out_even_though_its_median_is_ordinary():
    """The two original `pass` rows sit at opposite ends of MFI -- 8.10 on a
    dead tape, 100.00 on a vertical move. A set shaped like that has a median
    near the middle and nothing in the middle, and a median-only test would
    file it as settled. It is the most interesting shape in the data.
    """
    names = ["split"]
    placed = _place(names, [{"split": p} for p in (2, 3, 4, 96, 97, 98)])
    text = "\n".join(P.render(placed, [], _uniform_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))
    for block in text.split("=== ")[1:]:
        ruled = [ln for ln in block.splitlines() if "RULED OUT" in ln][0]
        assert "split" not in ruled, ruled
        assert "0/6 in the middle half" in block


def test_a_set_clustered_low_is_not_ruled_out_on_the_middle_count_alone():
    """Half the samples ordinary and half of them at the bottom clears the
    count test (4 of 8) while the median sits at 15%. Counting alone would
    call that feature settled."""
    names = ["low"]
    placed = _place(names, [{"low": p} for p in (3, 4, 5, 6, 26, 27, 28, 29)])
    text = "\n".join(P.render(placed, [], _uniform_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))
    for block in text.split("=== ")[1:]:
        ruled = [ln for ln in block.splitlines() if "RULED OUT" in ln][0]
        assert "low" not in ruled, ruled
        assert "4/8 in the middle half" in block


# --- reading the spreadsheet without openpyxl ---------------------------------
#
# The first live run of this module died on `pip install openpyxl`. openpyxl is
# still preferred when it imports; the stdlib reader exists so that a missing
# package cannot be the reason a report does not get produced. Two readers for
# one value is the shape this project keeps finding defects in, so the
# agreement is asserted rather than assumed.

def _no_openpyxl(monkeypatch):
    """Make `import openpyxl` fail, so the fallback path runs."""
    import builtins
    real = builtins.__import__

    def blocked(name, *a, **k):
        if name == "openpyxl":
            raise ImportError("blocked for this test")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", blocked)


def _write_sheet(path, rows, sheet_title="Sheet1"):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    for r in rows:
        ws.append(list(r))
    wb.save(path)
    return path


SHEET = [
    ("symbol", "date", "time_et", "label (took/passed/took-and-lost)", "note"),
    ("slbt", date(2026, 6, 16), dtime(4, 1), "took", "1.png"),
    ("CRBP", date(2026, 9, 14), dtime(7, 19), "Pass", "8.png"),
    ("RGNT", date(2026, 6, 17), dtime(4, 18), None, "17.png"),
    ("ICCM", date(2026, 6, 17), dtime(8, 27), "took and lost",
     "18.png, bought near peak and held too long"),
]


def test_the_two_xlsx_readers_agree(tmp_path, monkeypatch):
    """The oracle test. A hand-rolled parser of somebody else's format is
    worth exactly as much as the library it is checked against."""
    p = _write_sheet(tmp_path / "s.xlsx", SHEET)
    want = P.load_samples(p)
    _no_openpyxl(monkeypatch)
    got = P.load_samples(p)
    assert got == want
    assert [r["symbol"] for r in got] == ["SLBT", "CRBP", "RGNT", "ICCM"]
    assert [r["hhmm"] for r in got] == ["04:01", "07:19", "04:18", "08:27"]
    assert [r["date"] for r in got] == ["2026-06-16", "2026-09-14",
                                        "2026-06-17", "2026-06-17"]
    assert [r["label"] for r in got] == ["took", "pass", P.UNLABELLED,
                                         "took-and-lost"]


def test_the_stdlib_reader_uses_the_cell_reference_not_the_cell_order(
        tmp_path, monkeypatch):
    """A run of empty cells is simply ABSENT from the sheet XML. Counting <c>
    elements instead of reading their `r` attribute shifts every column after
    the first blank -- so a row with no note would read its label as its note
    and its time as its label, and the sample would not be dropped, it would
    be WRONG."""
    rows = [SHEET[0],
            ("AAAA", date(2026, 9, 14), dtime(7, 22), None, None),
            ("BBBB", date(2026, 9, 14), dtime(8, 15), "took", "x.png")]
    p = _write_sheet(tmp_path / "gaps.xlsx", rows)
    want = P.load_samples(p)
    _no_openpyxl(monkeypatch)
    got = P.load_samples(p)
    assert got == want
    assert got[0]["label"] == P.UNLABELLED and got[0]["note"] == ""
    assert got[0]["hhmm"] == "07:22"
    assert got[1]["label"] == "took"


def test_the_stdlib_reader_follows_workbook_order_not_the_filename(
        tmp_path, monkeypatch):
    """sheet1.xml is not always the first TAB. Picking the worksheet by
    filename works until someone reorders the tabs, and then the report is
    built from a different sheet without saying so."""
    openpyxl = pytest.importorskip("openpyxl")
    p = _write_sheet(tmp_path / "two.xlsx", SHEET, sheet_title="samples")
    wb = openpyxl.load_workbook(p)
    other = wb.create_sheet("scratch")
    other.append(["symbol", "date", "time_et", "label (x)", "note"])
    other.append(["ZZZZ", date(2026, 1, 2), dtime(5, 0), "took", "no"])
    wb.move_sheet("scratch", offset=-len(wb.sheetnames) + 1)   # make it first
    wb.save(p)

    want = P.load_samples(p)
    _no_openpyxl(monkeypatch)
    got = P.load_samples(p)
    assert got == want
    assert got[0]["symbol"] == "ZZZZ", "both readers must take the FIRST tab"


def test_a_date_serial_that_cannot_be_a_date_is_an_error_not_1902():
    """Excel serials are day counts. A small number in the date column is a
    number in the wrong column; converting it would place a sample three days
    into 1900 and lose it as 'not in the archive'."""
    assert P._as_date(46279.0) == "2026-09-14"
    assert P._as_date(datetime(2026, 9, 14, 7, 3)) == "2026-09-14"
    with pytest.raises(SystemExit):
        P._as_date(3.0)


def test_a_whole_number_in_the_time_column_is_an_error_not_midnight():
    """00:00 is a real pre-market minute, so a date serial landing in the time
    column must not quietly render as one."""
    assert P._as_hhmm(0.28958333333333336) == "06:57"
    with pytest.raises(SystemExit):
        P._as_hhmm(46279.0)
    with pytest.raises(SystemExit):
        P._as_hhmm(0.0)


def test_a_file_that_is_not_a_zip_says_so(tmp_path, monkeypatch):
    p = tmp_path / "old.xlsx"
    p.write_bytes(b"\xd0\xcf\x11\xe0not a zip")      # an actual .xls header
    _no_openpyxl(monkeypatch)
    with pytest.raises(SystemExit) as e:
        P.load_samples(p)
    assert ".xlsx" in str(e.value) or "zip" in str(e.value)


# --- the format assumptions, against a hand-built workbook --------------------
#
# openpyxl always writes sheetN.xml in tab order and never writes rich text
# unless asked, so a workbook it generates cannot exercise either of those
# branches -- a mutation pass showed both surviving. These build the zip
# directly, which is also the clearest statement of what the reader assumes.

def _minimal_xlsx(path, sheets, shared_xml):
    """`sheets` is [(tab name, worksheet filename, rows_xml)], in TAB order."""
    import zipfile
    NSMAIN = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    NSREL = ('xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
             '2006/relationships"')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/content-types"/>')
        sx = "".join(f'<sheet name="{n}" sheetId="{i+1}" r:id="rId{i+1}"/>'
                     for i, (n, _, _) in enumerate(sheets))
        z.writestr("xl/workbook.xml",
                   f'<?xml version="1.0"?><workbook {NSMAIN} {NSREL}>'
                   f'<sheets>{sx}</sheets></workbook>')
        rx = "".join(
            f'<Relationship Id="rId{i+1}" Target="worksheets/{fn}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            f'relationships/worksheet"/>'
            for i, (_, fn, _) in enumerate(sheets))
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships">'
                   + rx + "</Relationships>")
        z.writestr("xl/sharedStrings.xml",
                   f'<?xml version="1.0"?><sst {NSMAIN}>{shared_xml}</sst>')
        for _, fn, rows_xml in sheets:
            z.writestr(f"xl/worksheets/{fn}",
                       f'<?xml version="1.0"?><worksheet {NSMAIN}>'
                       f'<sheetData>{rows_xml}</sheetData></worksheet>')
    return path


def _srow(n, cells):
    """cells: [(ref, xml)] -- xml already formed, e.g. 't="s"><v>0</v>'."""
    return f'<row r="{n}">' + "".join(
        f'<c r="{ref}" {body}</c>' for ref, body in cells) + "</row>"


def test_the_first_TAB_is_read_even_when_it_is_not_sheet1_xml(tmp_path):
    """sheet1.xml is not always the first tab. Resolving through
    workbook.xml -> the rels file is the only thing that keeps the report
    built from the sheet the user is looking at."""
    strings = ("<si><t>symbol</t></si><si><t>date</t></si>"
               "<si><t>time_et</t></si><si><t>label (x)</t></si>"
               "<si><t>note</t></si><si><t>WANTED</t></si>"
               "<si><t>took</t></si><si><t>DECOY</t></si>")
    head = _srow(1, [("A1", 't="s"><v>0</v>'), ("B1", 't="s"><v>1</v>'),
                     ("C1", 't="s"><v>2</v>'), ("D1", 't="s"><v>3</v>'),
                     ("E1", 't="s"><v>4</v>')])
    def body(sym_idx):
        return _srow(2, [("A2", f't="s"><v>{sym_idx}</v>'),
                         ("B2", '><v>46279</v>'),
                         ("C2", '><v>0.28958333333333336</v>'),
                         ("D2", 't="s"><v>6</v>')])
    # TAB order puts the WANTED sheet first, but its file is sheet2.xml
    p = _minimal_xlsx(tmp_path / "order.xlsx",
                      [("first", "sheet2.xml", head + body(5)),
                       ("second", "sheet1.xml", head + body(7))],
                      strings)
    got = P._rows_from_xlsx_stdlib(p)
    assert got[1][0] == "WANTED", f"read the wrong worksheet: {got[1][0]!r}"


def test_a_rich_text_shared_string_is_read_whole(tmp_path):
    """A cell with bold part-way through splits into several <t> runs. Taking
    only the first silently truncates it -- and the label column is exactly
    where someone would bold a word."""
    strings = ("<si><t>symbol</t></si><si><t>date</t></si>"
               "<si><t>time_et</t></si><si><t>label (x)</t></si>"
               "<si><t>note</t></si><si><t>CRBP</t></si>"
               "<si><r><t>took </t></r><r><t>and </t></r><r><t>lost</t></r></si>")
    rows = (_srow(1, [("A1", 't="s"><v>0</v>'), ("B1", 't="s"><v>1</v>'),
                      ("C1", 't="s"><v>2</v>'), ("D1", 't="s"><v>3</v>'),
                      ("E1", 't="s"><v>4</v>')])
            + _srow(2, [("A2", 't="s"><v>5</v>'), ("B2", '><v>46279</v>'),
                        ("C2", '><v>0.28958333333333336</v>'),
                        ("D2", 't="s"><v>6</v>')]))
    p = _minimal_xlsx(tmp_path / "rich.xlsx",
                      [("s", "sheet1.xml", rows)], strings)
    # the stdlib reader directly: this hand-built zip has no Content_Types
    # part, so openpyxl -- correctly -- refuses it.
    got = P._rows_from_xlsx_stdlib(p)
    assert got[1][3] == "took and lost", f"truncated to {got[1][3]!r}"
    assert P.normalise_label(got[1][3]) == "took-and-lost"


def test_trailing_blank_rows_do_not_change_the_sample_count(tmp_path,
                                                            monkeypatch):
    """Both readers must return the SAME rows, blanks included. The stdlib
    reader used to trim trailing empties and openpyxl does not, so the two
    disagreed on row count for the same file -- caught by a mutation pass, and
    the trim was the wrong half."""
    openpyxl = pytest.importorskip("openpyxl")
    p = _write_sheet(tmp_path / "blanks.xlsx", SHEET)
    wb = openpyxl.load_workbook(p)
    ws = wb.active
    ws.append([None, None, None, None, None])
    ws.append([None, None, None, None, None])
    wb.save(p)

    want = P.load_samples(p)
    _no_openpyxl(monkeypatch)
    got = P.load_samples(p)
    assert got == want
    assert len(got) == len(SHEET) - 1


# --- the reference population, and why the first run needed one ---------------
#
# The first live run placed the samples against EVERY bar of the pre-market
# window and called 22 of 27 features unusual, with medians clustered at the
# 80th-94th percentile. That is not a finding about Ben's eye: that population
# is mostly dead minutes, and he screenshots bars where something is happening.
# The control's output was indistinguishable from the thing it was meant to
# detect -- this project's signature defect, inside the instrument built to
# look for it.

def test_the_reference_mask_uses_MCLs_own_columns():
    """No threshold is invented here. `signal` is c_vol and `entry` is the
    five conditions, both read off the strategy, so the denominator cannot
    drift from what the strategy actually does."""
    from strategy.mcl import mcl as MCL
    sig = MCL.signals(bars(n=700))
    for which, col in (("signal", "c_vol"), ("entry", "entry")):
        got = P.reference_mask(sig, which)
        np.testing.assert_array_equal(got, sig[col].to_numpy(dtype=bool))
    assert P.reference_mask(sig, "all").all()


def test_an_unknown_reference_name_raises_rather_than_defaulting_to_all():
    """Every percentile in the report is measured against this population.
    Silently falling back to `all` would produce a full, plausible report
    answering a different question than the one asked."""
    from strategy.mcl import mcl as MCL
    sig = MCL.signals(bars(n=700))
    with pytest.raises(KeyError):
        P.reference_mask(sig, "active")


def test_each_reference_is_a_subset_of_the_one_above_it():
    df = bars(n=700, seed=5)
    n_all = len(P.score_frame(df, "2026-09-14", 1, 1, "all"))
    n_sig = len(P.score_frame(df, "2026-09-14", 1, 1, "signal"))
    n_ent = len(P.score_frame(df, "2026-09-14", 1, 1, "entry"))
    assert n_all > n_sig >= n_ent
    assert n_sig > 0, "the fixture must produce some c_vol bars to test this"


def test_the_report_names_the_population_it_measured_against():
    """A percentile without its denominator is not a number anyone can use,
    and two runs of this module can differ by nothing else."""
    names = ["a"]
    for which in P.REFERENCES:
        text = "\n".join(P.render(_fake_placed(names), [], _fake_ref(names),
                                  names, ["2026-09-14"], 10, 1, 1.0,
                                  "p.json", which))
        assert f"reference population: {which}" in text


# --- coverage ------------------------------------------------------------------

def test_a_feature_measured_on_a_handful_is_neither_ruled_out_nor_unusual():
    """The first run printed `vol_over_trail  median 93.1%  0/2 in the middle
    half` on the 5-minute view and listed it under `unusual` beside features
    measured on all 21 -- a median of two presented as comparable with a
    median of twenty-one."""
    names = ["thin", "full"]
    placed = _fake_placed(names, n=10)
    for k, (_, f) in enumerate(placed):
        for tf in P.TIMEFRAMES:
            f[tf]["full"] = 0.0
            f[tf]["thin"] = 9.9 if k < 2 else float("nan")   # only 2 of 10
    text = "\n".join(P.render(placed, [], _fake_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))
    assert "TOO THIN TO PLACE" in text
    for block in text.split("=== ")[1:]:
        ruled = [ln for ln in block.splitlines() if "RULED OUT" in ln][0]
        unusual = [ln for ln in block.splitlines() if "unusual " in ln][0]
        thin = [ln for ln in block.splitlines() if "too thin" in ln][0]
        assert "thin" not in ruled and "thin" not in unusual.replace("too thin", "")
        assert "thin (2/10)" in thin
        assert "full" in ruled


def test_full_coverage_is_still_classified():
    names = ["full"]
    placed = _fake_placed(names, n=10)
    for _, f in placed:
        for tf in P.TIMEFRAMES:
            f[tf]["full"] = 0.0
    text = "\n".join(P.render(placed, [], _fake_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))
    assert "TOO THIN TO PLACE" not in text
    assert "too thin" not in text


# --- the outcome column, added 2026-09-16 --------------------------------------
#
# The first runs reported a `took` vs `took-and-lost` comparison as the only
# non-tautological cut available, with the caveat that `took` did not assert a
# win -- it meant "I would take this", outcome unstated. Ben then added the
# column. The caveat is now answerable from the sheet instead of assumed, which
# is the whole point.

def test_the_outcome_column_is_optional(tmp_path):
    """Every earlier sample file, and every csv fixture in this suite, has no
    such column. Requiring it would turn all of them into errors."""
    csv = tmp_path / "old.csv"
    csv.write_text("symbol,date,time_et,label (x),note\n"
                   "AAAA,2026-09-14,07:19,took,a\n", encoding="utf-8")
    got = P.load_samples(csv)
    assert got[0]["outcome"] is None and got[0]["outcome_note"] == ""


def test_the_outcome_column_is_read_when_present(tmp_path):
    csv = tmp_path / "new.csv"
    csv.write_text("symbol,date,time_et,label (x),wonl/loss,note\n"
                   "AAAA,2026-09-14,07:19,took,won,a\n"
                   "BBBB,2026-09-14,07:20,took and lost,lost,b\n"
                   "CCCC,2026-09-14,07:21,Pass,,c\n", encoding="utf-8")
    got = P.load_samples(csv)
    assert [r["outcome"] for r in got] == ["won", "lost", None]
    assert [r["note"] for r in got] == ["a", "b", "c"], \
        "the note column must still be found past the new one"


def test_a_qualified_win_keeps_its_sentence():
    """One win is annotated "won (but it was honestly a fluke)". Reducing that
    to "won" and discarding the text deletes the only thing in the row that
    says not to trust it."""
    assert P.normalise_outcome("won (but it was honestly a fluke)") == "won"
    assert P.normalise_outcome("Lost") == "lost"
    assert P.normalise_outcome("") is None
    assert P.normalise_outcome(None) is None
    assert P.normalise_outcome("scratched") is None


def test_the_outcome_column_is_not_confused_with_label_or_note(tmp_path):
    """"won" is a prefix match, and so is "note". A header order that put the
    outcome after the note, or a label column starting with one of the outcome
    words, must not capture the wrong index."""
    csv = tmp_path / "order.csv"
    csv.write_text("symbol,date,time_et,label (x),note,outcome\n"
                   "AAAA,2026-09-14,07:19,took,the note,won\n",
                   encoding="utf-8")
    got = P.load_samples(csv)
    assert got[0]["note"] == "the note"
    assert got[0]["outcome"] == "won"


def _with_outcomes(names, spec):
    """spec: [(label, outcome)] -- one placed sample each."""
    out = []
    for k, (lab, oc) in enumerate(spec):
        f = {tf: {nm: 0.0 for nm in names} for tf in P.TIMEFRAMES}
        for tf in P.TIMEFRAMES:
            f[tf]["_bar"] = "07:20"
        out.append(({"symbol": f"S{k}", "date": "2026-09-14", "hhmm": "07:22",
                     "label": lab, "outcome": oc, "outcome_note": oc or "",
                     "note": ""}, f))
    return out


def test_the_cross_tab_appears_once_an_outcome_exists():
    names = ["a"]
    placed = _with_outcomes(names, [("took", "won"), ("took-and-lost", None)])
    text = "\n".join(P.render(placed, [], _fake_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))
    assert "LABEL AGAINST OUTCOME" in text
    assert "took            won        1" in text


def test_a_took_marked_lost_is_flagged_LOUDLY():
    """The report cuts its groups on LABEL. A `took` marked lost would sit in
    the winners' group and quietly move the one comparison in this report that
    is not a tautology."""
    names = ["a"]
    placed = _with_outcomes(names, [("took", "won"), ("took", "lost"),
                                    ("pass", "won")])
    text = "\n".join(P.render(placed, [], _fake_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))
    assert "LABEL AND OUTCOME DISAGREE" in text
    assert "took marked lost" in text
    assert "pass marked won" in text
    assert "the winners' group contains a loser" in text


def test_no_cross_tab_when_the_sheet_has_no_outcomes():
    """A section of dashes tells the reader nothing and trains them to skip."""
    names = ["a"]
    placed = _with_outcomes(names, [("took", None), ("pass", None)])
    text = "\n".join(P.render(placed, [], _fake_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))
    assert "LABEL AGAINST OUTCOME" not in text


def test_a_qualified_outcome_is_surfaced_in_the_report():
    names = ["a"]
    placed = _with_outcomes(names, [("took", "won")])
    placed[0][0]["outcome_note"] = "won (but it was honestly a fluke)"
    text = "\n".join(P.render(placed, [], _fake_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))
    assert "outcomes the sheet qualifies in words" in text
    assert "fluke" in text
    assert "does not endorse" in text


def test_the_loader_carries_the_qualifying_sentence_through(tmp_path):
    """Not just `normalise_outcome`. A mutation that emptied `outcome_note` in
    the loader survived, because the report test set the field by hand -- a
    check one step short of the thing it protects, again."""
    csv = tmp_path / "q.csv"
    csv.write_text(
        "symbol,date,time_et,label (x),wonl/loss,note\n"
        'PLYX,2026-02-17,06:34,took,"won (but it was honestly a fluke)",12.png\n',
        encoding="utf-8")
    got = P.load_samples(csv)
    assert got[0]["outcome"] == "won"
    assert "fluke" in got[0]["outcome_note"]

    text = "\n".join(P.render(
        [(got[0], {tf: {"a": 0.0, "_bar": "06:34"} for tf in P.TIMEFRAMES})],
        [], _fake_ref(["a"]), ["a"], ["2026-02-17"], 10, 1, 1.0, "p.json"))
    assert "fluke" in text, "the sheet's own caveat must reach the report"


# --- the caveat must be counted, not asserted ---------------------------------
#
# This paragraph used to say "there is no comparison group worth the name".
# True of the first 21 samples; false twice since -- once when the passes
# doubled, again when the outcome column arrived. A hard-coded description of
# the data is a second source of truth about the data.

def _labelled(names, spec):
    """spec: {label: count}."""
    out = []
    k = 0
    for lab, n in spec.items():
        for _ in range(n):
            f = {tf: {nm: 0.0 for nm in names} for tf in P.TIMEFRAMES}
            for tf in P.TIMEFRAMES:
                f[tf]["_bar"] = "07:20"
            out.append(({"symbol": f"S{k}", "date": "2026-09-14",
                         "hhmm": "07:22", "label": lab,
                         "outcome": "won" if lab == "took" else None,
                         "outcome_note": "", "note": ""}, f))
            k += 1
    return out


def _render(placed, names=("a",)):
    names = list(names)
    return "\n".join(P.render(placed, [], _fake_ref(names), names,
                              ["2026-09-14"], 10, 1, 1.0, "p.json"))


def test_the_caveat_counts_the_set_it_was_given():
    text = _render(_labelled(["a"], {"took": 11, "took-and-lost": 6,
                                     "pass": 6}))
    assert "TAKE against PASS is available: 11 vs 6" in text
    assert "WON against LOST is available: 11 vs 6" in text
    assert "no comparison group worth the name" not in text


def test_a_thin_side_removes_only_its_own_comparison():
    """Three passes and six losses: the outcome cut stands, the selection cut
    does not. Printing both would overstate; printing neither would understate
    the one that is there."""
    text = _render(_labelled(["a"], {"took": 11, "took-and-lost": 6,
                                     "pass": 3}))
    assert "TAKE against PASS" not in text
    assert "WON against LOST is available: 11 vs 6" in text


def test_with_neither_side_it_says_so_rather_than_implying_a_cut():
    text = _render(_labelled(["a"], {"took": 11, "took-and-lost": 2,
                                     "pass": 2}))
    assert "Neither comparison has enough rows" in text
    assert "is available" not in text


def test_the_two_comparisons_are_never_presented_as_one():
    """The mistake this module is one step from at all times: reading a
    feature that separates his takes from his passes as evidence the selection
    makes money."""
    text = _render(_labelled(["a"], {"took": 11, "took-and-lost": 6,
                                     "pass": 6}))
    assert "describes what he SELECTS" in text
    assert "says nothing about whether the selection makes money" in text
    assert "only one about OUTCOME" in text
