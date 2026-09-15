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

from datetime import datetime, time as dtime, timedelta
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
                    "label": "pass", "note": "8.png"}]


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
