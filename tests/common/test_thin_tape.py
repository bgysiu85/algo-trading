#!/usr/bin/env python3
"""H-T1: the thin-tape pre-flight, and the ways a volume reading goes wrong.

REGISTERED_thin_tape.md. The statistic is simple; what needs pinning is the
quantity it is computed on:

  - the signal bar is the ENGINE'S bar, not `bar_minutes` worth of tape. MC5
    acts on five-minute bars and the figures Ben objected to are five-minute
    figures; read off the 1-minute tape they come back five times too small
    with nothing looking wrong. That is H-R1's defect, one day old;
  - the stamp must LAND on the engine's resampled index, or the bar being read
    is not the bar the engine read and every number shifts by one bucket;
  - the decile shape decides whether a floor is expressible at all, so
    monotonicity has to be measured rather than eyeballed;
  - and the report stays a pre-flight: no money, no threshold, no verdict.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from common import thin_tape as T


ET = T.ET


def bars(vols, start="2026-09-11 05:00", px=10.0):
    idx = pd.date_range(pd.Timestamp(start, tz=ET), periods=len(vols), freq="1min")
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": [float(v) for v in vols]}, index=idx)


# --- the quantity -------------------------------------------------------------

def test_a_five_minute_engine_reads_its_whole_bar_not_one_minute_of_tape():
    """THE DEFECT THIS EXISTS TO AVOID. Ben's AEHL figures -- 2,003 and 634 --
    are five-minute figures. At the tape's grain they would read as whatever
    the last minute happened to carry."""
    b = bars([100, 200, 300, 400, 500,        # 05:00-05:04, the 05:00 bucket
              10, 20, 30, 40, 50])            # 05:05-05:09, the 05:05 bucket
    ts = pd.Timestamp("2026-09-11 05:05", tz=ET)
    one, _, _ = T.signal_volume(b, ts, 1)
    five, _, _ = T.signal_volume(b, ts, 5)
    assert one == 10, "the tape's last minute"
    assert five == 150, "the engine's bar: 10+20+30+40+50"


def test_a_one_minute_engine_is_the_tape_itself():
    b = bars([7, 11, 13])
    ts = pd.Timestamp("2026-09-11 05:02", tz=ET)
    assert T.signal_volume(b, ts, 1)[0] == 13


def test_the_five_bar_sum_is_five_ENGINE_bars_not_five_minutes():
    b = bars([1] * 50)
    ts = pd.Timestamp("2026-09-11 05:45", tz=ET)
    _, five_at_1, _ = T.signal_volume(b, ts, 1)
    _, five_at_5, _ = T.signal_volume(b, ts, 5)
    assert five_at_1 == 5, "five one-minute bars"
    assert five_at_5 == 25, "five five-minute bars, of five minutes each"


def test_a_stamp_off_the_engines_grid_is_reported_rather_than_rounded():
    """An off-by-one-bucket stamp convention would move every reading by a bar
    and produce numbers that look entirely ordinary. So it is returned."""
    b = bars([1] * 20)
    on = pd.Timestamp("2026-09-11 05:10", tz=ET)
    off = pd.Timestamp("2026-09-11 05:12", tz=ET)
    assert T.signal_volume(b, on, 5)[2] is True
    assert T.signal_volume(b, off, 5)[2] is False
    # and it still returns a number rather than raising -- the run reports the
    # count and the reader decides, as the grain check does in the census
    assert T.signal_volume(b, off, 5)[0] == T.signal_volume(b, off, 5)[0]


def test_a_naive_timestamp_is_refused_by_name():
    """Read as UTC a naive stamp moves every session boundary four or five
    hours and the volumes still come back looking ordinary."""
    with pytest.raises(ValueError, match="tz-aware"):
        T.signal_volume(bars([1, 2, 3]), pd.Timestamp("2026-09-11 05:02"), 1)


def test_an_entry_before_any_bar_is_nan_rather_than_zero():
    """Zero shares is a real and damning reading. 'no bars yet' is not that."""
    b = bars([5, 5, 5], start="2026-09-11 06:00")
    v, _, _ = T.signal_volume(b, pd.Timestamp("2026-09-11 05:00", tz=ET), 1)
    assert v != v, "an absent history was reported as an empty bar"


# --- the shape, which decides whether a floor is expressible -------------------

def _row(book="MCL", vol=1000.0, bars_held=4, reason="trailing_stop", **kw):
    r = {"book": book, "symbol": "AAA", "date": "2026-09-11", "entry_et": "05:00",
         "bar_min": 1, "on_grid": True, "bars_held": bars_held, "reason": reason,
         T.VOL_BAR: vol, T.VOL_5BAR: vol * 5,
         "rand": 0.5, "minutes_since_0400": 60.0}
    r.update(kw)
    return r


def monotone_rows(book="MCL", n=200):
    """One-bar share falling steadily as volume rises -- the shape a floor can
    express."""
    out = []
    for i in range(n):
        vol = float(i + 1) * 100.0
        dies = (i % 10) < max(0, 9 - (i * 10) // n)
        out.append(_row(book=book, vol=vol, bars_held=1 if dies else 4))
    return out


def test_a_monotone_bottom_half_is_reported_as_falling():
    rows = monotone_rows("MCL") + monotone_rows("MC5")
    _, falls = T.decile_block(rows)
    assert falls["MCL"], "no steps were measured"
    assert all(falls["MCL"]), "a falling shape was not read as falling"


def test_a_non_monotone_shape_is_reported_as_such_rather_than_smoothed():
    """The live table's shape: the middle behaves better than both ends. A
    floor cannot express that, which is the whole reason this is measured."""
    rows = []
    for i in range(200):
        vol = float(i + 1) * 100.0
        # alternating blocks: the one-bar share RISES from decile 1 to 2, which
        # is the bottom half behaving like the live table rather than like a
        # gradient a floor could cut.
        dies = (i // 20) % 2 == 1
        rows.append(_row(vol=vol, bars_held=1 if dies else 4))
    _, falls = T.decile_block(rows)
    assert not all(falls["MCL"]), "a U-shape was read as monotone"


def humped_rows(book="MCL", n=200):
    """Falls across the bottom five deciles and RISES across the top five --
    the live table's own shape, where the middle behaves better than either
    end. A floor operates on the bottom, so this is the case that says why the
    window is the bottom five and not all ten."""
    out = []
    for i in range(n):
        d = (i * 10) // n                     # 0..9, the decile
        share = [9, 7, 5, 3, 1, 1, 3, 5, 7, 9][d]
        out.append(_row(book=book, vol=float(i + 1) * 100.0,
                        bars_held=1 if (i % 10) < share else 4))
    return out


def test_the_window_is_the_BOTTOM_deciles_because_that_is_where_a_floor_acts():
    """A floor refuses low volume and cannot express anything about the top.
    Requiring all ten deciles to fall would refuse a shape a floor handles
    perfectly well."""
    _, falls = T.decile_block(humped_rows("MCL"))
    assert len(falls["MCL"]) == T.MONOTONE_DECILES - 1, falls["MCL"]
    assert all(falls["MCL"]), "the bottom half falls and was not read as falling"


def test_the_rule_block_prints_both_quantities_and_applies_neither_silently():
    rows = monotone_rows("MCL") + monotone_rows("MC5")
    _, aucs = T.auc_block(rows, "x", "y")
    _, falls = T.decile_block(rows)
    text = "\n".join(T.rule_block(aucs, falls))
    assert f"{T.AUC_BAR:.2f}" in text
    assert "falls throughout" in text or "not monotone" in text
    assert "Printed, not applied" in text


# --- the controls -------------------------------------------------------------

def test_the_null_control_is_carried_over_and_lands_on_a_half():
    """`rand` is the crc32-seeded null from running_up. A separation statistic
    whose null is not visible is a control whose output cannot be told from the
    failure it detects."""
    rng = np.random.default_rng(11)
    rows = [_row(vol=float(rng.integers(100, 100_000)),
                 bars_held=int(rng.integers(1, 6)),
                 rand=float(rng.random())) for _ in range(4000)]
    _, aucs = T.auc_block(rows, "x", "y")
    assert abs(aucs["MCL:rand"] - 0.5) < 0.05, aucs["MCL:rand"]
    assert "rand" in T.CONTROLS and "minutes_since_0400" in T.CONTROLS


def test_the_clock_confound_is_scored_beside_the_feature():
    """Time of day is a CLOSED question on these books. If it separates and the
    volume feature does not, the volume feature is a clock in disguise."""
    rows = monotone_rows("MCL")
    text = "\n".join(T.auc_block(rows, "x", "y")[0])
    assert "minutes_since_0400" in text and "<- control" in text


# --- it stays a pre-flight ----------------------------------------------------

def _render(rows):
    return T.render(rows, ["2026-09-11"], 1, 0.5, 1, "p.json", "XNAS.ITCH", 0, [])


def test_no_money_reaches_the_report():
    """The claim the pre-flight rests on. A P&L column here would let a
    threshold be chosen for its P&L, which is a search wearing a table's
    clothes."""
    text = "\n".join(_render(monotone_rows("MCL") + monotone_rows("MC5")))
    money = re.compile(r"\$\s*-?[\d,]+\.?\d*|\([\d,]+\.\d\d\)")
    hits = [ln for ln in text.splitlines() if money.search(ln)]
    assert not hits, f"the pre-flight printed money: {hits[:3]}"


def test_no_scoring_vocabulary_reaches_the_report():
    text = "\n".join(_render(monotone_rows("MCL") + monotone_rows("MC5")))
    # ONE stated carve-out: the §3.3(5) heading quotes Ben's own phrase for the
    # DAIC finding, "three times nothing is nothing". It is prose, not a
    # verdict, and removing it keeps the ban on the verdict itself exact.
    text = text.replace('"THREE TIMES NOTHING"', "")
    for banned in ("CLEARS", "REFUSED", "NOTHING", "per trade", "per symbol-day",
                   "drop-top", "p95", "bootstrap", "PASSES"):
        assert banned not in text, f"the pre-flight printed {banned!r}"


def test_the_report_names_what_it_is_not():
    text = "\n".join(_render(monotone_rows("MCL")))
    assert "NOT A GATE" in text
    assert "holdout.json has not been touched" in text
    assert "better half of a bad" in text                # H-P1's lesson, carried
    assert "The FEATURE is knowable at" in text          # and the honest limit


def test_the_stamp_check_is_scored_not_decorative():
    ok = [_row(on_grid=True)]
    assert "all on the engine's grid" in "\n".join(T.grid_block(ok))
    bad = ok + [_row(symbol="OFF", on_grid=False, bar_min=5)]
    text = "\n".join(T.grid_block(bad))
    assert "NOT ON THE ENGINE'S GRID" in text and "OFF" in text


def test_the_reported_never_scored_cut_is_labelled_and_separate():
    text = "\n".join(_render(monotone_rows("MCL") + monotone_rows("MC5")))
    assert "REPORTED, NEVER SCORED" in text
    assert "not read\n  into the decision" in text or "into the decision" in text


def test_the_trailing_stop_cut_drops_one_bar_exits_that_were_not_the_stop():
    """H-R1's population: one-bar exits that were the trailing stop FIRING. A
    one-bar exit for any other reason is neither a death of that kind nor a
    survivor, so it leaves the comparison rather than switching sides -- and
    read on the RENDERED report, because the filter lives in `render` and a
    test that restates it cannot see the filter go missing."""
    rows = ([_row(bars_held=1, reason="trailing_stop", vol=float(i)) for i in range(1, 31)]
            + [_row(bars_held=1, reason="window_close", vol=float(i)) for i in range(31, 61)]
            + [_row(bars_held=6, reason="window_close", vol=float(i)) for i in range(61, 101)])
    block = "\n".join(_render(rows)).split("REPORTED, NEVER SCORED")[1]
    m = re.search(r"vol_bar\s+([\d,]+)\s+([\d,]+)", block)
    assert m, block[:400]
    one, rest = (int(x.replace(",", "")) for x in m.groups())
    assert one == 30, f"the never-scored cut counted {one} one-bar trades, not 30"
    assert rest == 40, f"the never-scored cut counted {rest} survivors, not 40"


# --- the engine's own grain, derived not assumed ------------------------------

def test_the_grain_comes_from_the_engine():
    """Imported from `rebound` rather than restated, so there is one answer to
    'what bar does this engine act on' -- including the thin-name case where
    MC5 declines to resample and its bars ARE the tape's."""
    from strategy.mc5 import mc5 as M5
    from strategy.mcl import mcl as ML
    assert T.engine_bar_minutes is not None
    assert T.engine_bar_minutes(ML, None) == 1
    dense = bars([1] * 60)
    assert T.engine_bar_minutes(M5, dense) == M5.BAR_MINUTES
    assert T.engine_bar_minutes(M5, dense.iloc[::10]) == 1


def test_run_day_derives_the_grain_and_passes_it_to_the_volume():
    """The wiring gap no unit test can see: `signal_volume` can be right while
    `run_day` calls it with the tape's grain, and `run_day` needs the archive."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(T.run_day))
    derived = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
               and getattr(n.func, "id", None) == "engine_bar_minutes"]
    assert derived, "run_day no longer derives the grain from the engine"
    assert len(derived[0].args) >= 2, "engine_bar_minutes must see the frame"
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "signal_volume"]
    assert calls, "run_day no longer reads the signal volume"
    for c in calls:
        assert len(c.args) >= 3, "signal_volume called without a grain"
        assert not isinstance(c.args[2], ast.Constant), \
            "the grain passed is a literal, not the engine's own answer"
