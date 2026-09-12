#!/usr/bin/env python3
"""Does the simulated screen match the live one?

The measurement is easy to get wrong in two specific ways, and both were nearly
made by hand before this module existed:

1. **Scoring against a hand-synced watchlist.** Those were built under
   `RVOL(1D) >= 5x, float < 20m` -- clauses the shipped FILTERS do not have --
   so disagreement measures the gap between two screens and reads as a
   simulation defect. A first pass scored 6 of 13 on exactly those files.
2. **Treating the two directions as symmetric.** A live name the simulation
   missed is a definite miss; a simulated name absent from a CAPPED live list
   may just have ranked twelfth.
"""
from __future__ import annotations

import json

import pytest

from common import screen_validate as V

AUTO = "# tv_feed 2026-09-11 09:29:53 ET  hot=6 warm=0 cold=2\n"
HAND = ("# MCL watchlist -- one ticker per line.\n"
        "# Screen: $2-20 price, RVOL(1D) >= 5x, float < 20m, top-2 gainer.\n")


def write(tmp, stem, body, blocked=None):
    (tmp / f"watchlist_{stem}.txt").write_text(body)
    if blocked is not None:
        (tmp / f"watchlist_blocked_{stem}.txt").write_text(blocked)


# --- provenance -------------------------------------------------------------

def test_a_hand_synced_list_is_excluded_and_the_reason_is_printed(tmp_path):
    write(tmp_path, "20260903", HAND + "TLYS\nGYGY\n")
    rows, skipped = V.collect(tmp_path, {"2026-09-03": {"AEHL", "DAIC"}})
    assert rows == []
    assert skipped and "different screen" in skipped[0]["why"]


def test_an_automated_list_is_compared(tmp_path):
    write(tmp_path, "20260911", AUTO + "TNON\nACVA\n")
    rows, _ = V.collect(tmp_path, {"2026-09-11": {"TNON"}})
    assert len(rows) == 1
    assert rows[0]["found"] == ["TNON"] and rows[0]["missed"] == ["ACVA"]


def test_a_date_outside_the_archive_is_excluded_not_scored_as_a_miss(tmp_path):
    write(tmp_path, "20260911", AUTO + "TNON\n")
    rows, skipped = V.collect(tmp_path, {"2026-09-03": {"X"}})
    assert rows == []
    assert "archive window" in skipped[0]["why"]


# --- blocked names were still screened --------------------------------------

def test_a_name_ibkr_refused_still_counts_as_screened(tmp_path):
    """The screen surfaced it; the broker declined. Different failure,
    different fix, and this module measures the screen."""
    write(tmp_path, "20260911", AUTO + "TNON\n", blocked="PCLA  # Error 201\n")
    rows, _ = V.collect(tmp_path, {"2026-09-11": {"TNON", "PCLA"}})
    assert set(rows[0]["live"]) == {"TNON", "PCLA"}
    assert rows[0]["found"] == ["PCLA", "TNON"]


def test_an_inline_blocked_comment_is_read_as_a_name(tmp_path):
    write(tmp_path, "20260911",
          AUTO + "TNON\n# MIMI   <-- BLOCKED 2026-09-11 04:01: Error 201\n")
    rows, _ = V.collect(tmp_path, {"2026-09-11": {"TNON", "MIMI"}})
    assert set(rows[0]["live"]) == {"TNON", "MIMI"}


def test_an_ordinary_comment_is_not_read_as_a_name(tmp_path):
    write(tmp_path, "20260911", AUTO + "# just a note about the session\nTNON\n")
    rows, _ = V.collect(tmp_path, {"2026-09-11": {"TNON"}})
    assert rows[0]["live"] == ["TNON"]


def test_tickers_are_case_normalised(tmp_path):
    """The hand-synced files mixed `ppbt` and `SGLD`; a case-sensitive compare
    would score every lowercase name as a miss."""
    write(tmp_path, "20260911", AUTO + "tnon\nAcva\n")
    rows, _ = V.collect(tmp_path, {"2026-09-11": {"TNON", "ACVA"}})
    assert rows[0]["missed"] == []


# --- the interval and the verdict -------------------------------------------

def test_the_verdict_reads_the_LOWER_bound_not_the_point_estimate():
    """A small sample landing at 81% is not evidence of 80%."""
    rows = [{"date": "2026-09-11", "live": [f"S{i}" for i in range(10)],
             "sim": [f"S{i}" for i in range(10)],
             "found": [f"S{i}" for i in range(9)], "missed": ["S9"],
             "sim_only": []}]
    out = "\n".join(V.render(rows, [], 5))
    assert "90%" in out                       # the point estimate is 90%
    assert "THE SIMULATION REPRODUCES" not in out, \
        "a 9/10 sample cleared the 80% band on its point estimate"
    assert "PARTIAL" in out


def test_a_large_clean_sample_can_clear_the_top_band():
    n = 200
    rows = [{"date": "2026-09-11", "live": [f"S{i}" for i in range(n)],
             "sim": [f"S{i}" for i in range(n)],
             "found": [f"S{i}" for i in range(190)],
             "missed": [f"S{i}" for i in range(190, n)], "sim_only": []}]
    out = "\n".join(V.render(rows, [], 5))
    assert "THE SIMULATION REPRODUCES" in out


def test_a_poor_agreement_says_the_pit_figures_describe_another_universe():
    rows = [{"date": "2026-09-11", "live": [f"S{i}" for i in range(20)],
             "sim": ["S0"], "found": ["S0"],
             "missed": [f"S{i}" for i in range(1, 20)], "sim_only": []}]
    out = "\n".join(V.render(rows, [], 5))
    assert "A DIFFERENT UNIVERSE" in out
    assert "including that MCL beats its control" in out


def test_a_wide_interval_is_called_out():
    rows = [{"date": "2026-09-11", "live": ["A", "B", "C", "D"],
             "sim": ["A", "B", "C"], "found": ["A", "B", "C"],
             "missed": ["D"], "sim_only": []}]
    out = "\n".join(V.render(rows, [], 5))
    assert "small sample" in out


def test_wilson_is_bounded_and_centred():
    lo, hi = V.wilson(9, 10)
    assert 0.0 <= lo < 0.9 < hi <= 1.0
    assert V.wilson(0, 0) == (0.0, 0.0)


# --- the asymmetry ----------------------------------------------------------

def verdict_of(text):
    for band in ("THE SIMULATION REPRODUCES", "PARTIAL", "A DIFFERENT UNIVERSE"):
        if band in text:
            return band
    return None


def test_sim_only_names_do_not_move_the_verdict():
    """The live list is CAPPED, so a simulated name ranked twelfth is not an
    error. Counting it as one would make a good simulation look bad. Same
    found/live either way, so the verdict must be identical."""
    live = [f"S{i}" for i in range(200)]
    base = {"date": "2026-09-11", "live": live, "sim": live,
            "found": live[:190], "missed": live[190:], "sim_only": []}
    noisy = dict(base, sim=live + [f"X{i}" for i in range(300)],
                 sim_only=[f"X{i}" for i in range(300)])
    clean_out = "\n".join(V.render([base], [], 5))
    noisy_out = "\n".join(V.render([noisy], [], 5))
    assert verdict_of(clean_out) == verdict_of(noisy_out) == \
        "THE SIMULATION REPRODUCES"
    assert "300 simulated name(s) were not on the live list" in noisy_out
    assert "NOT a symmetric count" in noisy_out


def test_a_single_name_session_cannot_clear_a_band_on_its_own():
    """1 of 1 is 100% with a Wilson lower bound near 20%. Reading the point
    estimate would let one lucky session certify the whole simulation."""
    rows = [{"date": "2026-09-11", "live": ["A"], "sim": ["A"],
             "found": ["A"], "missed": [], "sim_only": []}]
    assert verdict_of("\n".join(V.render(rows, [], 5))) == \
        "A DIFFERENT UNIVERSE"


def test_no_comparable_session_refuses_a_verdict(tmp_path):
    out = "\n".join(V.render([], [{"date": "2026-09-03", "n": 7,
                                   "why": "hand-synced"}], 546))
    assert "NO VERDICT" in out
    assert "extend the Databento archive" in out


def test_an_empty_universe_file_names_the_command(tmp_path):
    p = tmp_path / "pairs.json"
    p.write_text("[]")
    with pytest.raises(SystemExit) as e:
        V.load_sim(p)
    assert "screen_sim" in str(e.value)
