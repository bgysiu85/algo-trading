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
    (tmp / f"watchlist_{stem}.txt").write_text(body, encoding="utf-8")
    if blocked is not None:
        (tmp / f"watchlist_blocked_{stem}.txt").write_text(blocked, encoding="utf-8")


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
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        V.load_sim(p)
    assert "screen_sim" in str(e.value)


# --- the header's date, the tiers, and the 04:00 carry-over (2026-09-17) ----

def sim_rows(day, names, first_seen="08:05"):
    return {day: {n: {"symbol": n, "date": day,
                      "first_seen": f"{day}T{first_seen}:00+00:00",
                      "first_rank": i + 1, "best_rank": i + 1}
                  for i, n in enumerate(names)}}


def test_the_session_is_the_headers_date_not_the_filename(tmp_path):
    """Under AEDT `archive_watchlist` names the file a day late."""
    write(tmp_path, "20260912", AUTO + "TNON\n")        # header says 09-11
    rows, skipped = V.collect(tmp_path, sim_rows("2026-09-11", ["TNON"]))
    assert rows and rows[0]["date"] == "2026-09-11" and rows[0]["file_date"] == "2026-09-12"
    assert rows[0]["found"] == ["TNON"]


def test_tiers_are_read_from_the_counts_and_the_order(tmp_path):
    hdr = "# tv_feed 2026-09-16 09:29:56 ET  hot=2 warm=1 cold=2\n"
    wl = V.read_watchlist(_w(tmp_path, "20260916",
                             hdr + "# ZTG   <-- BLOCKED 2026-09-16 07:22:56: Error 201\n"
                             "MEDS\nBIG\nVEEA\nMYSZ\n"))
    assert wl["date"] == "2026-09-16"
    assert wl["tiers"] == {"ZTG": "hot", "MEDS": "hot", "BIG": "warm",
                           "VEEA": "cold", "MYSZ": "cold"}
    assert wl["blocked"] == {"ZTG": "2026-09-16 07:22:56"}


def test_counts_that_do_not_match_the_file_set_nothing_aside(tmp_path):
    hdr = "# tv_feed 2026-09-16 09:29:56 ET  hot=1 warm=0 cold=9\n"
    _w(tmp_path, "20260915", "# tv_feed 2026-09-15 09:29:50 ET  hot=1 warm=0 cold=0\nVEEA\n")
    _w(tmp_path, "20260916", hdr + "MEDS\nVEEA\n")
    sim = {**sim_rows("2026-09-15", ["VEEA"]), **sim_rows("2026-09-16", ["MEDS"])}
    rows, _ = V.collect(tmp_path, sim)
    r = rows[1]
    assert not r["tiers_known"] and r["carry"] == [] and r["missed_clean"] == ["VEEA"]


def test_a_cold_name_from_the_previous_list_is_a_carry_over_and_is_sim_blind(tmp_path):
    _w(tmp_path, "20260915", "# tv_feed 2026-09-15 09:29:50 ET  hot=2 warm=0 cold=0\nVEEA\nNAMI\n")
    _w(tmp_path, "20260916",
       "# tv_feed 2026-09-16 09:29:56 ET  hot=2 warm=0 cold=3\n"
       "MEDS\nRETO\nNAMI\nVEEA\nMYSZ\n",
       blocked="PSNYW  # 2026-09-16 04:00:06 - no Stock security definition\n")
    sim = {**sim_rows("2026-09-15", ["VEEA", "NAMI"]),
           **sim_rows("2026-09-16", ["MEDS", "RETO", "NAMI"])}
    rows, _ = V.collect(tmp_path, sim)
    r = rows[1]
    # NAMI is cold and on yesterday's list -> set aside even though the sim
    # found it; MYSZ is cold but NOT on yesterday's list -> a real miss;
    # PSNYW was blocked at the first poll but is not on yesterday's list here.
    assert r["carry"] == ["NAMI", "VEEA"] and r["carry_found"] == ["NAMI"]
    assert r["missed"] == ["MYSZ", "PSNYW", "VEEA"]
    assert r["live_clean"] == ["MEDS", "MYSZ", "PSNYW", "RETO"]
    assert r["missed_clean"] == ["MYSZ", "PSNYW"]
    assert r["prev_date"] == "2026-09-15"


def test_a_first_poll_block_of_yesterdays_name_is_counted_as_04_00_evidence(tmp_path):
    _w(tmp_path, "20260915", "# tv_feed 2026-09-15 09:29:50 ET  hot=1 warm=0 cold=0\nPSNYW\n")
    _w(tmp_path, "20260916",
       "# tv_feed 2026-09-16 09:29:56 ET  hot=1 warm=0 cold=1\nMEDS\n# PSNYW   <-- BLOCKED 2026-09-16 04:00:06: no def\n")
    sim = {**sim_rows("2026-09-15", ["PSNYW"]), **sim_rows("2026-09-16", ["MEDS"])}
    rows, _ = V.collect(tmp_path, sim)
    assert rows[1]["stale_0400"] == ["PSNYW"] and rows[1]["carry"] == ["PSNYW"]


def test_a_hand_synced_list_is_not_the_previous_list(tmp_path):
    _w(tmp_path, "20260910", "# tv_feed 2026-09-10 09:29:50 ET  hot=1 warm=0 cold=0\nAAA\n")
    _w(tmp_path, "20260911", HAND + "BBB\n")
    _w(tmp_path, "20260914", "# tv_feed 2026-09-14 09:29:50 ET  hot=1 warm=0 cold=2\nCCC\nAAA\nBBB\n")
    sim = {**sim_rows("2026-09-10", ["AAA"]), **sim_rows("2026-09-14", ["CCC"])}
    rows, _ = V.collect(tmp_path, sim)
    assert rows[-1]["prev_date"] == "2026-09-10"
    assert rows[-1]["carry"] == ["AAA"] and rows[-1]["missed_clean"] == ["BBB"]


def test_the_verdict_is_read_on_the_clean_basis_and_both_are_printed(tmp_path):
    live = [f"S{i}" for i in range(20)]
    carry = [f"C{i}" for i in range(10)]
    row = {"date": "2026-09-16", "prev_date": "2026-09-15", "file_date": "2026-09-16",
           "live": live + carry, "sim": live, "found": live, "missed": carry,
           "sim_only": [], "sim_only_rank": {}, "tiers_known": True,
           "carry": carry, "carry_found": [], "stale_0400": carry[:2],
           "live_clean": live, "found_clean": live, "missed_clean": [], "timing": []}
    rows = [dict(row, date=f"2026-09-{d}") for d in (10, 11, 14, 15, 16)]
    out = "\n".join(V.render(rows, [], 5, "XNAS.ITCH"))
    assert "100 of 150 live names surfaced" in out            # every name
    assert "100 of 100 live names were surfaced" in out       # the clean basis
    assert verdict_of(out) == "THE SIMULATION REPRODUCES"
    assert "THE 04:00 CARRY-OVER, SET ASIDE" in out and "[XNAS.ITCH]" in out


def test_timing_pairs_a_block_stamp_with_the_sims_first_seen(tmp_path):
    _w(tmp_path, "20260914",
       "# tv_feed 2026-09-14 09:29:58 ET  hot=1 warm=0 cold=0\nRAYA\n",
       blocked="RAYA  # 2026-09-14 08:58:50 - Error 201\n")
    rows, _ = V.collect(tmp_path, sim_rows("2026-09-14", ["RAYA"], "12:43"))
    t = rows[0]["timing"]
    assert t == [{"symbol": "RAYA", "blocked_et": "08:58:50",
                  "sim_first_seen_et": "08:43:00", "live_minus_sim_min": 15.8}]
    out = "\n".join(V.render(rows, [], 1))
    assert "median live-sim +15.8 min" in out


def test_sim_only_names_carry_their_best_rank(tmp_path):
    _w(tmp_path, "20260914", "# tv_feed 2026-09-14 09:29:58 ET  hot=1 warm=0 cold=0\nA\n")
    rows, _ = V.collect(tmp_path, sim_rows("2026-09-14", ["A", "B"]))
    assert rows[0]["sim_only"] == ["B"] and rows[0]["sim_only_rank"] == {"B": 2}


def _w(tmp, stem, body, blocked=None):
    write(tmp, stem, body, blocked)
    return tmp / f"watchlist_{stem}.txt"


# --- the diagnosis, on a synthetic tape --------------------------------------

def _tape(day, sym, closes, volumes, start="04:00"):
    import pandas as pd
    from zoneinfo import ZoneInfo
    t0 = pd.Timestamp(f"{day} {start}", tz=ZoneInfo("America/New_York")).tz_convert("UTC")
    idx = [t0 + pd.Timedelta(minutes=i) for i in range(len(closes))]
    return pd.DataFrame({"symbol": sym, "close": closes, "volume": volumes},
                        index=pd.DatetimeIndex(idx, name="ts_event"))


def test_diagnose_names_the_failing_clause():
    from datetime import date
    from common.screen_at import ScreenConfig
    cfg = ScreenConfig(change_min=20.0, price_range=(2.0, 20.0), volume_min=100_000,
                       capture=0.1, max_symbols=40)
    d = date(2026, 9, 16)
    # change never there: +5% at best
    r = V.diagnose_symbol(_tape("2026-09-16", "X", [10.2, 10.5, 10.4], [5000] * 3), 10.0, d, cfg)
    assert r["verdict"].startswith("change never reached 20%") and "+5.0%" in r["verdict"]
    # change and price fine, volume short of the 10,000-share tape threshold
    r = V.diagnose_symbol(_tape("2026-09-16", "X", [12.0, 12.5, 13.0], [2000] * 3), 10.0, d, cfg)
    assert r["verdict"].startswith("volume 6,000 < 10,000")
    # price outside the band whenever the change qualified
    r = V.diagnose_symbol(_tape("2026-09-16", "X", [30.0, 31.0], [50000] * 2), 20.0, d, cfg)
    assert r["verdict"].startswith("price outside")
    # passed all three -> points at the simulation
    r = V.diagnose_symbol(_tape("2026-09-16", "X", [12.0, 12.5, 13.0], [4000] * 3), 10.0, d, cfg)
    assert r["verdict"].startswith("PASSED all three at 04:03")
    # not on the tape / no prior close
    assert V.diagnose_symbol(None, 10.0, d, cfg)["verdict"] == "not on the tape"
    assert V.diagnose_symbol(_tape("2026-09-16", "X", [1.0], [1]), None, d, cfg)["verdict"] == "no prior close"


def test_clauses_at_reads_the_name_at_the_live_moment():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from common.screen_at import ScreenConfig
    cfg = ScreenConfig(change_min=20.0, price_range=(2.0, 20.0), volume_min=100_000,
                       capture=0.1, max_symbols=40)
    when = datetime(2026, 9, 16, 4, 2, 30, tzinfo=ZoneInfo("America/New_York"))
    # by 04:02:30 two bars have closed: cum 4,000 < 10,000 and change +25%
    r = V.clauses_at(_tape("2026-09-16", "X", [12.0, 12.5, 13.0], [2000] * 3), 10.0, when, cfg)
    assert r["verdict"] == "volume 4,000 < 10,000" and r["at_et"] == "04:02:30"
    r = V.clauses_at(_tape("2026-09-16", "X", [10.5, 10.6], [9000] * 2), 10.0, when, cfg)
    assert r["verdict"].startswith("change +6.0% < 20%")
    assert V.clauses_at(None, 10.0, when, cfg)["verdict"] == "not on the tape"


def test_read_fills_takes_the_first_buy_per_name_and_day(tmp_path):
    (tmp_path / "mcl_fills_20260914.csv").write_text(
        "ts_et,strategy,symbol,action,reason\n"
        "2026-09-14 03:40:37,,,CONFIG,session_open\n"
        "2026-09-14 08:16:00,MCL,DRCT,BUY,entry_signal\n"
        "2026-09-14 07:02:05,MC5,DRCT,BUY,entry_signal\n"
        "2026-09-14 07:30:00,MCL,DRCT,SELL,trailing_stop\n", encoding="utf-8")
    assert V.read_fills(tmp_path) == {"2026-09-14": {"DRCT": "2026-09-14 07:02:05"}}
    assert V.read_fills(tmp_path / "nope") == {}


def test_a_first_signal_before_first_seen_is_a_negative_delta(tmp_path):
    _w(tmp_path, "20260911", "# tv_feed 2026-09-11 09:29:53 ET  hot=1 warm=0 cold=0\nXRTX\n")
    fills = {"2026-09-11": {"XRTX": "2026-09-11 04:31:02"}}
    rows, _ = V.collect(tmp_path, sim_rows("2026-09-11", ["XRTX"], "09:13"), fills)
    assert rows[0]["signals"][0]["live_minus_sim_min"] == -42.0
    out = "\n".join(V.render(rows, [], 1))
    assert "smallest -42.0" in out


def test_diagnose_fills_the_rows_from_the_archive(monkeypatch, tmp_path):
    """The orchestration, with the archive readers stubbed: one clean miss
    and one live-first name, both read off the same slice."""
    import pandas as pd
    from pathlib import Path
    from common import dbn_io, screen_sim
    from common.screen_at import ScreenConfig

    day = "2026-09-11"
    slice_path = Path("E/XNAS.ITCH/ohlcv-1m") / f"{day}_0400_0930.dbn.zst"
    tape = pd.concat([_tape(day, "TPET", [10.5, 10.6, 10.7], [1000] * 3),
                      _tape(day, "XRTX", [12.0, 12.5, 13.0], [2000] * 3)])
    monkeypatch.setattr(screen_sim, "window_slices", lambda root, ds: [slice_path])
    monkeypatch.setattr(dbn_io, "read_dbn", lambda p: tape)
    monkeypatch.setattr(dbn_io, "daily_frame", lambda root, ds: pd.DataFrame(
        {"symbol": ["TPET", "XRTX"], "date": ["2026-09-10"] * 2, "close": [10.0, 10.0]}))
    monkeypatch.setattr(screen_sim, "load_repaired", lambda *a, **k: None)
    monkeypatch.setattr(screen_sim, "prior_closes", lambda daily, rep: pd.DataFrame(
        {"symbol": ["TPET", "XRTX"], "date": [day] * 2, "prior_close": [10.0, 10.0]}))

    _w(tmp_path, "20260911", "# tv_feed 2026-09-11 09:29:53 ET  hot=2 warm=0 cold=0\nTPET\nXRTX\n")
    rows, _ = V.collect(tmp_path, sim_rows(day, ["XRTX"], "09:13"),
                        {day: {"XRTX": f"{day} 04:02:30"}})
    cfg = ScreenConfig(change_min=20.0, price_range=(2.0, 20.0), volume_min=100_000,
                       capture=0.1, max_symbols=40)
    V.diagnose(rows, Path("E"), "XNAS.ITCH", "XNAS.BASIC", cfg, None, "2026-03-30")
    assert rows[0]["diagnosis"]["TPET"]["verdict"].startswith("change never reached 20%")
    assert rows[0]["late"]["XRTX"]["verdict"] == "volume 4,000 < 10,000"
    out = "\n".join(V.render(rows, [], 1))
    assert "THE MISSES, READ OFF THE TAPE" in out and "THE NAMES THE LIVE FEED HAD FIRST" in out
