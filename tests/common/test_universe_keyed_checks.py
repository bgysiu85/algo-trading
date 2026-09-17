#!/usr/bin/env python3
"""Re-basing the B-series and Part A on another universe file.

The population check compares against the count published for THE FILE that
was run, never against another file's number; luck_vs_edge refuses inputs
from two different runs; the market regime reads its own daily archive."""
from __future__ import annotations

import json

import pytest

from common import entry_shares as E
from common import first_entry_skip as S
from common import gate_study as G
from common import luck_vs_edge as A
from common import range_rank as R
from tests.common.test_first_entry_skip import EARLY, LATE
from tests.common.test_range_rank import symday_pairs

BASIC = "var/state/screen_pairs_pit.json"
V2 = "var/state/screen_pairs_pit_itch_v2.json"


# --- the published count is a property of the universe file --------------------------

def test_published_count_is_keyed_on_the_file_basename_in_either_slash_style():
    assert E.published_mcl_trades(BASIC) == 3_955
    assert E.published_mcl_trades("var\\state\\screen_pairs_pit_itch_v2.json") == 3_908
    assert E.published_mcl_trades("var/state/screen_pairs_pit_itch_p50.json") == 3_960
    assert E.published_mcl_trades("var/state/screen_pairs_pit_ext.json") is None
    assert E.published_mcl_trades(None) is None
    # the BASIC number is still the one the older modules read
    assert E.PUBLISHED_TRADES["mcl"] == E.PUBLISHED_MCL_BY_UNIVERSE["screen_pairs_pit.json"]


def test_population_lines_match_against_the_run_file_and_say_none_for_an_unlisted_one():
    ok = "\n".join(S.population_lines(3_908, V2))
    assert "3,908" in ok and "matches" in ok and "DOES NOT MATCH" not in ok
    bad = "\n".join(S.population_lines(3_955, V2))          # BASIC's count on the v2 file
    assert "*** DOES NOT MATCH ***" in bad and "A DIFFERENT BOOK" in bad
    ext = "\n".join(S.population_lines(59, "var/state/screen_pairs_pit_ext.json"))
    assert "none for this universe file" in ext
    assert "DOES NOT MATCH" not in ext and "matches" not in ext


def test_h_b1_render_names_the_universe_and_the_bars_and_checks_that_file():
    b, g = symday_pairs(12, [-10.0, -10.0], [5.0, 5.0])
    books = {"MCL": b, "MCL-skip1": g, "MC5": b, "MC5-skip1": g}
    text = "\n".join(S.render(books, 24, 0, [EARLY, LATE], 1.0, 1, [],
                              universe=V2, dataset="XNAS.ITCH"))
    assert "universe    var/state/screen_pairs_pit_itch_v2.json   bars XNAS.ITCH" in text
    assert "published count     3,908" in text
    default = "\n".join(S.render(books, 24, 0, [EARLY, LATE], 1.0, 1, []))
    assert f"universe    {S.PAIRS}   bars XNAS.BASIC" in default
    assert "published count     3,955" in default


def test_gate_render_names_the_universe_and_checks_that_file_not_basic():
    b, g = symday_pairs(12, [-10.0, -10.0], [5.0, 5.0])
    books = {"MCL": b, "MCL-top3": g, "MCL-top1": g, "MC5": b, "MC5-top3": g, "MC5-top1": g}
    refused = {k: [] for k in ("MCL-top3", "MCL-top1", "MC5-top3", "MC5-top1")}
    binding = {k: (10, 20, {1: 10, 5: 10}) for k in refused}
    args = ("T", "docs/x.md", books, R.PAIRED, R.REPORTED, 24, 0, [EARLY, LATE], 1.0, 1, refused, binding)
    ext = "\n".join(G.render(*args, universe="var/state/screen_pairs_pit_ext.json", dataset="XNAS.BASIC"))
    assert "none for this universe file" in ext and "DOES NOT MATCH" not in ext
    v2 = "\n".join(G.render(*args, universe=V2, dataset="XNAS.ITCH"))
    assert "bars XNAS.ITCH" in v2 and "published count     3,908" in v2 and "DOES NOT MATCH" in v2
    default = "\n".join(G.render(*args))
    assert "published count     3,955" in default


# --- luck_vs_edge takes one run's inputs and its own daily archive ---------------------

def meta(**kw):
    m = {"sessions": [EARLY, LATE], "symbol_days": 24, "cut": EARLY, "pairs": V2,
         "dataset": "XNAS.ITCH", "qty": 100, "timestamps": "ET"}
    m.update(kw)
    return m


def test_input_refusal_accepts_one_runs_inputs_in_either_slash_style():
    assert A.input_refusal(meta(), V2, "XNAS.ITCH", {EARLY: "warm"}) is None
    assert A.input_refusal(meta(pairs="var\\state\\screen_pairs_pit_itch_v2.json"),
                           V2, "XNAS.ITCH", {}) is None


def test_input_refusal_names_the_tape_the_trades_were_written_on():
    r = A.input_refusal(meta(dataset="XNAS.BASIC"), V2, "XNAS.ITCH", {})
    assert r and "'XNAS.BASIC'" in r and "--dataset is 'XNAS.ITCH'" in r


def test_input_refusal_names_a_universe_mismatch():
    r = A.input_refusal(meta(pairs=BASIC), V2, "XNAS.ITCH", {})
    assert r and "screen_pairs_pit.json" in r and "screen_pairs_pit_itch_v2.json" in r


def test_input_refusal_catches_another_universes_readings_by_their_stray_sessions():
    r = A.input_refusal(meta(), V2, "XNAS.ITCH", {EARLY: "warm", "2026-09-01": "cold"})
    assert r and "1 session(s)" in r and "2026-09-01" in r and "--readings" in r
    # readings on a SUBSET of the sessions (MIN_HISTORY leaves early ones unread) are fine
    assert A.input_refusal(meta(), V2, "XNAS.ITCH", {LATE: "cold"}) is None


def test_main_refuses_before_touching_the_archive(tmp_path, monkeypatch):
    csv = tmp_path / "t.csv"
    csv.write_text("book,symbol,date,ordinal,entry_et,exit_et,net\n", encoding="utf-8")
    (tmp_path / "t_meta.json").write_text(json.dumps(meta(dataset="XNAS.BASIC")), encoding="utf-8")
    monkeypatch.setattr(A, "regime_labels", lambda *a: pytest.fail("archive read after a refusal"))
    with pytest.raises(SystemExit, match="REFUSING TO RUN.*XNAS.BASIC"):
        A.main(["--trades", str(csv), "--readings", str(tmp_path / "none.csv"),
                "--pairs", V2, "--dataset", "XNAS.ITCH", "--archive", str(tmp_path)])


def test_daily_dataset_is_its_own_flag_and_stays_basic_under_itch_bars():
    a = A.build_parser().parse_args(["--dataset", "XNAS.ITCH"])
    assert a.dataset == "XNAS.ITCH" and a.daily_dataset == "XNAS.BASIC"


def test_main_reads_the_regime_from_daily_dataset_not_dataset(tmp_path, monkeypatch):
    csv = tmp_path / "t.csv"
    csv.write_text("book,symbol,date,ordinal,entry_et,exit_et,net\n", encoding="utf-8")
    (tmp_path / "t_meta.json").write_text(json.dumps(meta()), encoding="utf-8")
    seen = {}

    def fake_regime(archive, dataset):
        seen["daily"] = dataset
        raise SystemExit("stop here")
    monkeypatch.setattr(A, "regime_labels", fake_regime)
    with pytest.raises(SystemExit, match="stop here"):
        A.main(["--trades", str(csv), "--readings", str(tmp_path / "none.csv"),
                "--pairs", V2, "--dataset", "XNAS.ITCH", "--archive", str(tmp_path)])
    assert seen["daily"] == "XNAS.BASIC"
