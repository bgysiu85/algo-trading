#!/usr/bin/env python3
"""The separation pre-flight: its inputs, its split, and what it refuses to print.

The pre-flight's whole claim is that it is descriptive -- no rule, no
threshold, no P&L. These pin that claim, because a report that quietly grew a
P&L column would let a threshold be chosen for its P&L, which is the search
H-S6 §2 exists to prevent one level up.
"""
from __future__ import annotations

import csv
import json

import numpy as np
import pandas as pd
import pytest

from common import running_up as RU
from common import running_up_preflight as P

ET = RU.ET


def entry(book="MC5", symbol="X", date="2026-09-11", et="05:00", bars=1, **feats):
    row = {"book": book, "symbol": symbol, "date": date, "entry_et": et,
           "bars_held": bars}
    row.update({k: float("nan") for k in RU.FEATURES})
    row.update(feats)
    return row


# --- the split --------------------------------------------------------------

def test_one_bar_is_bars_held_at_most_one():
    rows = [entry(bars=1), entry(bars=2), entry(bars=0), entry(bars=238)]
    one, rest = P.split(rows, "MC5")
    assert len(one) == 2 and len(rest) == 2


def test_the_split_is_per_book():
    rows = [entry(book="MC5", bars=1), entry(book="MCL", bars=1),
            entry(book="MCL", bars=9)]
    assert len(P.split(rows, "MCL")[0]) == 1
    assert len(P.split(rows, "MC5")[0]) == 1
    assert P.split(rows, "MC5")[1] == []


# --- the inputs -------------------------------------------------------------

def write_trades(tmp_path, rows=None, meta_extra=None):
    p = tmp_path / "t.csv"
    rows = rows or [
        {"book": "MCL", "symbol": "A", "date": "2026-09-11", "ordinal": 1,
         "entry_et": "05:00", "entry_px": 2.0, "exit_et": "05:06", "exit_px": 2.1,
         "reason": "trailing_stop", "bars_held": 6, "net": 10.0},
        {"book": "MC5", "symbol": "B", "date": "2026-09-11", "ordinal": 1,
         "entry_et": "06:00", "entry_px": 3.0, "exit_et": "06:05", "exit_px": 2.8,
         "reason": "trailing_stop", "bars_held": 1, "net": -20.0},
        {"book": "MC5-pf5", "symbol": "B", "date": "2026-09-11", "ordinal": 1,
         "entry_et": "06:00", "entry_px": 6.0, "exit_et": "06:05", "exit_px": 5.8,
         "reason": "trailing_stop", "bars_held": 1, "net": -20.0}]
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    meta = {"pairs": "var/state/screen_pairs_pit_itch_v2.json", "dataset": "XNAS.ITCH",
            "sessions": ["2026-09-11"], "symbol_days": 2}
    meta.update(meta_extra or {})
    (tmp_path / "t_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return p


def test_only_the_plain_books_are_read(tmp_path):
    """The floored books are a different universe of entries; mixing them in
    would double-count the same signal at two price bands."""
    by_day = P.load_entries(write_trades(tmp_path))
    books = {e["book"] for v in by_day.values() for e in v}
    assert books == {"MCL", "MC5"}


def test_entries_are_grouped_by_date(tmp_path):
    by_day = P.load_entries(write_trades(tmp_path))
    assert list(by_day) == ["2026-09-11"] and len(by_day["2026-09-11"]) == 2


def test_a_csv_from_another_tape_is_refused(tmp_path):
    """Features computed from ITCH slices against BASIC-tape entries would be
    read off bars those entries never saw."""
    p = write_trades(tmp_path, meta_extra={"dataset": "XNAS.BASIC"})
    why = P.input_refusal(P.load_meta(p), "var/state/screen_pairs_pit_itch_v2.json",
                          "XNAS.ITCH")
    assert why and "tape the entries did" in why


def test_a_csv_from_another_universe_is_refused(tmp_path):
    p = write_trades(tmp_path, meta_extra={"pairs": "var/state/screen_pairs_pit.json"})
    why = P.input_refusal(P.load_meta(p), "var/state/screen_pairs_pit_itch_v2.json",
                          "XNAS.ITCH")
    assert why and "same file" in why


def test_the_matching_pair_is_accepted(tmp_path):
    p = write_trades(tmp_path)
    assert P.input_refusal(P.load_meta(p), "var/state/screen_pairs_pit_itch_v2.json",
                           "XNAS.ITCH") is None


# --- what the report says ---------------------------------------------------

def separable_rows(n=200):
    """One-bar trades with LOW rvol, survivors with HIGH -- the hypothesis, if
    it were true. Used to check the report says so in the right direction."""
    rng = np.random.default_rng(7)
    rows = []
    for i in range(n):
        rows.append(entry(bars=1, rvol_5m=float(rng.normal(1.0, 0.2)),
                          rand=float(rng.random())))
        rows.append(entry(bars=5, rvol_5m=float(rng.normal(3.0, 0.2)),
                          rand=float(rng.random())))
    return rows


def test_the_direction_is_spelled_out_rather_than_left_to_the_reader():
    one, rest = P.split(separable_rows(), "MC5")
    lines, scored = P.feature_block(one, rest)
    row = next(ln for ln in lines if ln.strip().startswith("rvol_5m"))
    # the fixture puts LOW rvol on the one-bar trades, so rvol_5m must read
    # "higher -> FEWER". Asserting the phrase appears ANYWHERE in the block is
    # not a test: eleven features print a direction and one of them says
    # FEWER whichever way round the branch is written.
    assert "higher -> FEWER one-bar (as hypothesised)" in row, row
    assert "MORE one-bar" not in row
    top = sorted(scored, reverse=True)[0]
    assert top[1] == "rvol_5m"


def test_the_null_control_reads_a_half_and_is_labelled():
    one, rest = P.split(separable_rows(600), "MC5")
    lines, scored = P.feature_block(one, rest)
    aucs = {name: au for _, name, au in scored}
    assert aucs["rand"] == pytest.approx(0.5, abs=0.06)
    assert "rand" in "\n".join(lines) and "<- control" in "\n".join(lines)


def test_the_controls_are_never_offered_as_the_best_feature():
    """`rand` and the clock are printed, but a gate must never be proposed on
    them -- on a book where the clock separated, the bind tables would read as
    a recommendation."""
    rng = np.random.default_rng(3)
    rows = []
    for i in range(300):
        rows.append(entry(bars=1, minutes_since_0400=float(rng.normal(60, 5)),
                          rand=float(rng.normal(0.9, 0.02))))
        rows.append(entry(bars=7, minutes_since_0400=float(rng.normal(300, 5)),
                          rand=float(rng.normal(0.1, 0.02))))
    text = "\n".join(P.render(rows, ["2026-09-11"], 1.0, 1, "p.json",
                              "XNAS.ITCH", "t.csv", 0))
    # Exercise the REPORT, not a re-implementation of its filter here: the
    # bind tables are what would read as a recommendation, so no control may
    # head one even when the control separates better than anything else.
    for ctl in ("rand", "minutes_since_0400"):
        assert f"  {ctl}: a `" not in text, f"a bind table was offered on {ctl}"
    assert "minutes_since_0400" in text, "the confound must still be PRINTED"


def test_a_useless_feature_keeps_the_same_share_of_both_groups():
    rng = np.random.default_rng(11)
    rows = ([entry(bars=1, rvol_5m=float(rng.normal())) for _ in range(400)]
            + [entry(bars=6, rvol_5m=float(rng.normal())) for _ in range(400)])
    one, rest = P.split(rows, "MC5")
    lines = P.bind_block(one, rest, "rvol_5m")
    # the difference column, parsed back out of the printed table
    diffs = [float(ln.split()[-1].rstrip("%")) for ln in lines
             if ln.startswith("    ") and "%" in ln and "cut" not in ln]
    assert max(abs(d) for d in diffs) < 12.0


def test_the_report_contains_no_pnl_column_at_all():
    """The claim the whole pre-flight rests on. A P&L column here would let a
    threshold be chosen for its P&L before any registration exists."""
    rows = separable_rows()
    text = "\n".join(P.render(rows, ["2026-09-11"], 1.0, 4,
                              "var/state/screen_pairs_pit_itch_v2.json",
                              "XNAS.ITCH", "t.csv", 0))
    import re
    # Money, in either of the two forms this project prints it: a dollar
    # figure, or the accounting bracket. The prose says "no P&L"; this checks
    # that no NUMBER in the report is one.
    money = re.compile(r"\$\s*-?[\d,]+\.?\d*|\([\d,]+\.\d\d\)")
    hits = [ln for ln in text.splitlines() if money.search(ln)]
    assert not hits, f"the pre-flight printed money: {hits[:3]}"
    # and no SCORE: the readings and verdicts a gate study prints. Naming the
    # abstention control in a forward-looking sentence is fine and is how the
    # report says what comes next; printing one is not.
    for banned in ("per trade", "per symbol-day", "drop-top",
                   "PASSES", "REFUSED", "NOTHING", "P(total"):
        assert banned not in text, f"the pre-flight printed {banned!r}"


def test_the_report_names_what_it_is_not():
    text = "\n".join(P.render(separable_rows(), ["2026-09-11"], 1.0, 4,
                              "p.json", "XNAS.ITCH", "t.csv", 3))
    assert "NOT A RESULT" in text
    assert "holdout.json has not been touched" in text
    assert "3 session(s) produced no rows" in text
    # the two honest limits on the comparison with Warrior's own scanner
    assert "no threshold from their screen transfers" in text.lower()
    assert "sub-second signal" in text


def test_a_book_with_one_group_empty_says_so_rather_than_dividing_by_zero():
    rows = [entry(book="MCL", bars=4) for _ in range(5)]
    text = "\n".join(P.render(rows, ["2026-09-11"], 1.0, 1, "p.json",
                              "XNAS.ITCH", "t.csv", 0))
    assert "not enough of one group to read" in text


# --- the features reach the rows -------------------------------------------

def test_run_day_stamps_the_entry_in_et_and_keeps_the_label(monkeypatch):
    """The entry_et in the CSV is bare HH:MM. Read as UTC it would move every
    session four or five hours -- the same defect that moved every
    time-of-day conclusion once already."""
    idx = pd.DatetimeIndex([pd.Timestamp(f"2026-09-11 05:{i:02d}", tz=ET)
                            for i in range(10)])
    df = pd.DataFrame({"open": 2.0, "high": 2.1, "low": 1.9,
                       "close": [2.0 + 0.01 * i for i in range(10)],
                       "volume": 100, "symbol": "B"}, index=idx)
    import common.pit_strategy as PS
    import common.dbn_io as DB
    monkeypatch.setattr(DB, "read_dbn", lambda p: df)
    monkeypatch.setattr(PS, "build_frame", lambda parts, day: df)
    entries = [{"book": "MC5", "symbol": "B", "date": "2026-09-11",
                "entry_et": "05:09", "bars_held": 1}]
    day, out, err = P.run_day((["2026-09-11.dbn"], "2026-09-11", entries))
    assert err == "" and len(out) == 1
    assert out[0]["bars_held"] == 1 and out[0]["book"] == "MC5"
    assert out[0]["minutes_since_0400"] == 69.0          # 05:09 ET
    assert out[0]["ret_1m"] == pytest.approx(2.09 / 2.08 - 1, rel=1e-6)


def test_run_day_with_no_entries_does_not_read_the_tape(monkeypatch):
    import common.dbn_io as DB
    called = []
    monkeypatch.setattr(DB, "read_dbn", lambda p: called.append(p))
    day, out, err = P.run_day((["x.dbn"], "2026-09-11", []))
    assert out == [] and err == "" and called == []
