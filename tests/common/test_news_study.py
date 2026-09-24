#!/usr/bin/env python3
r"""tests/common/test_news_study.py

Synthetic populations only -- no tape, no live pull. H-N1's accounting form
reads straight from a trades CSV shaped like chase_gate_trades.csv; these
tests build small versions of that shape and check the arithmetic, not any
real result.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common import news_events as N
from common import news_study as S

ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def _trades_csv(tmp_path, rows: list[dict]) -> Path:
    cols = ["book", "symbol", "date", "ordinal", "entry_et", "entry_px", "exit_et",
           "exit_px", "reason", "bars_held", "net"]
    p = tmp_path / "trades.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            base = {"ordinal": 1, "entry_px": 1.0, "exit_px": 1.0,
                   "reason": "trailing_stop", "bars_held": 3}
            base.update(r)
            w.writerow(base)
    return p


def _row(book, symbol, date, entry_et, exit_et, net):
    return {"book": book, "symbol": symbol, "date": date, "entry_et": entry_et,
           "exit_et": exit_et, "net": net}


# --- population loading -------------------------------------------------------------

def test_load_population_filters_books_and_builds_timestamps(tmp_path):
    p = _trades_csv(tmp_path, [
        _row("MCL", "AAA", "2026-01-05", "09:35", "09:41", 12.5),
        _row("MC5", "BBB", "2026-01-05", "10:00", "10:04", -3.0),
        _row("MCL-c033", "CCC", "2026-01-05", "09:00", "09:05", 5.0),  # not scored
    ])
    pop = S.load_population(str(p))
    assert set(pop) == {"MCL", "MC5"}
    assert len(pop["MCL"]) == 1 and len(pop["MC5"]) == 1
    row = pop["MCL"][0]
    assert row["entry_ts"] == _et(2026, 1, 5, 9, 35)
    assert row["exit_ts"] == _et(2026, 1, 5, 9, 41)
    assert row["net"] == 12.5
    assert isinstance(row["ordinal"], int)


def test_load_population_missing_file_exits(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        S.load_population(str(tmp_path / "nope.csv"))


def test_symbol_days_and_median_cut(tmp_path):
    p = _trades_csv(tmp_path, [
        _row("MCL", "AAA", "2026-01-01", "09:35", "09:41", 1.0),
        _row("MCL", "AAA", "2026-01-01", "09:50", "09:55", 1.0),   # same symbol-day
        _row("MCL", "BBB", "2026-01-03", "09:35", "09:41", 1.0),
        _row("MCL", "CCC", "2026-01-05", "09:35", "09:41", 1.0),
    ])
    pop = S.load_population(str(p))
    assert S.symbol_days(pop["MCL"]) == 3
    assert S.median_cut(pop["MCL"]) == "2026-01-03"


# --- events + gating ----------------------------------------------------------------

def test_build_events_merges_both_sources():
    filings = {"AAA": [{"form": "424B5", "items": "", "accepted": "2026-01-01T20:00:00Z"}]}
    headlines = {"AAA": [{"headline": "AAA Announces Reverse Stock Split",
                         "created_at": "2026-01-02T13:00:00Z"}],
                "BBB": [{"headline": "PQR Receives FDA Clearance", "created_at": "2026-01-02T13:00:00Z"}]}
    events = S.build_events(filings, headlines)
    assert {e.kind for e in events["AAA"]} == {"TRIGGER_A", "TRIGGER_B"}
    assert events["BBB"] == []   # no trigger, classify_headline returns None


def test_gate_book_splits_kept_removed_by_entry_time_trigger():
    base = [{"symbol": "AAA", "entry_ts": _et(2026, 1, 5, 9, 35)},
           {"symbol": "BBB", "entry_ts": _et(2026, 1, 5, 9, 35)}]
    events = {"AAA": [N.Event(ts=_et(2026, 1, 5, 9, 0), kind="TRIGGER_A",
                              source="EDGAR", symbol="AAA", detail="424B5")]}
    kept, removed = S.gate_book(base, events, N.EDGAR_PLUS_HEADLINES)
    assert [r["symbol"] for r in removed] == ["AAA"]
    assert [r["symbol"] for r in kept] == ["BBB"]


def test_gate_book_no_coverage_never_vetoes():
    base = [{"symbol": "ZZZ", "entry_ts": _et(2026, 1, 5, 9, 35)}]
    kept, removed = S.gate_book(base, {}, N.EDGAR_PLUS_HEADLINES)
    assert len(kept) == 1 and len(removed) == 0


def test_gate_book_sources_filter():
    base = [{"symbol": "AAA", "entry_ts": _et(2026, 1, 5, 12, 0)}]
    events = {"AAA": [N.Event(ts=_et(2026, 1, 5, 11, 0), kind="TRIGGER_A",
                              source="ALPACA", symbol="AAA", detail="OFFERING_PRICED")]}
    kept, removed = S.gate_book(base, events, N.EDGAR_ONLY)
    assert len(removed) == 0    # ALPACA event invisible under EDGAR-only
    kept2, removed2 = S.gate_book(base, events, N.EDGAR_PLUS_HEADLINES)
    assert len(removed2) == 1


# --- abstention_hn1: parameters and determinism --------------------------------------

def test_abstention_hn1_deterministic_with_seed():
    base = [{"net": float(i)} for i in range(50)]
    a1 = S.abstention_hn1(base, k=10, symdays=20)
    a2 = S.abstention_hn1(base, k=10, symdays=20)
    assert a1["valid"] and a1["per_trade_q"] == a2["per_trade_q"]
    assert a1["draws"] == S.HN1_DRAWS
    assert a1["q"] == S.HN1_Q


def test_abstention_hn1_invalid_when_k_is_zero_or_all():
    base = [{"net": 1.0}, {"net": 2.0}]
    assert S.abstention_hn1(base, k=0, symdays=2)["valid"] is False
    assert S.abstention_hn1(base, k=2, symdays=2)["valid"] is False


# --- verdict_hn1: the three tags -----------------------------------------------------

def _synthetic_book(n=40, bad_symbols=()):
    """n symbol-days, one trade each, net alternating so the book nets
    negative overall (matching the project's own losing-book prior) with a
    subset of `bad_symbols` carrying a materially worse net."""
    rows = []
    for i in range(n):
        sym = f"S{i:03d}"
        date = f"2026-01-{(i % 28) + 1:02d}"
        net = -6.0 if sym in bad_symbols else -1.0
        rows.append({"symbol": sym, "date": date, "entry_et": "09:35",
                    "net": net})
    return rows


def test_verdict_hn1_nothing_or_refused_when_a_half_is_empty():
    # Both trades fall on the same side of the cut -- one half is empty for
    # both base and gated, which the function must catch before reading any
    # other number.
    base = [{"symbol": "A", "date": "2026-01-01", "net": 10.0 + S.MEASURED_FRICTION},
           {"symbol": "B", "date": "2026-01-02", "net": -100.0 + S.MEASURED_FRICTION}]
    gated = [base[1]]
    tag, why, n = S.verdict_hn1(base, gated, "2026-01-02", symdays=2)
    assert tag in ("REFUSED", "NOTHING")
    assert n["removed"] == 1


def test_verdict_hn1_nothing_when_gated_equals_base():
    base = _synthetic_book(40)
    tag, why, n = S.verdict_hn1(base, list(base), S.median_cut(base), symdays=40)
    assert tag == "NOTHING"
    assert n["removed"] == 0


def test_verdict_hn1_reports_removed_count():
    base = _synthetic_book(40)
    gated = base[5:]   # remove 5 trades
    tag, why, n = S.verdict_hn1(base, gated, "2026-01-14", symdays=40)
    assert n["removed"] == 5


# --- marginal trade + top-20 check ----------------------------------------------------

def test_marginal_trade_all_three_frictions():
    base = [{"net": 10.0}, {"net": -5.0}, {"net": 3.0}]
    gated = [{"net": 10.0}, {"net": 3.0}]   # the -5.0 trade removed
    marg = S.marginal_trade(base, gated)
    assert set(marg) == {"$1.00", "$4.26", "$8.92"}
    # removing the -5.0 trade: marginal = (tot(gated)-tot(base))/(n(gated)-n(base))
    # = (-(-5.0 - f)) / (-1) = -(5.0 + f) ... check sign consistent with formula
    for lab, f in S.FRICTIONS:
        expected = ((sum(r["net"] - f for r in gated) - sum(r["net"] - f for r in base))
                   / (len(gated) - len(base)))
        assert abs(marg[lab] - expected) < 1e-9


def test_top20_check_counts_absent_top_trades():
    base = [{"symbol": f"S{i}", "date": "2026-01-01", "entry_et": "09:35",
            "net": float(20 - i)} for i in range(25)]
    gated = base[3:]   # removes the 3 best trades (highest net)
    gone, ok = S.top20_check(base, gated)
    assert gone == 3
    assert ok is True   # 3 < 10 (half of 20)


# --- H-N2: mid-hold trigger counting -------------------------------------------------

def test_mid_hold_trades_false_at_entry_true_at_exit():
    base = [{"symbol": "AAA", "entry_ts": _et(2026, 1, 5, 9, 35),
            "exit_ts": _et(2026, 1, 5, 9, 41), "date": "2026-01-05",
            "entry_et": "09:35", "exit_et": "09:41"}]
    events = {"AAA": [N.Event(ts=_et(2026, 1, 5, 9, 38), kind="TRIGGER_A",
                              source="EDGAR", symbol="AAA", detail="424B5")]}
    mid = S.mid_hold_trades(base, events, N.EDGAR_PLUS_HEADLINES)
    assert len(mid) == 1


def test_mid_hold_trades_excludes_already_vetoed_at_entry():
    base = [{"symbol": "AAA", "entry_ts": _et(2026, 1, 5, 9, 35),
            "exit_ts": _et(2026, 1, 5, 9, 41), "date": "2026-01-05",
            "entry_et": "09:35", "exit_et": "09:41"}]
    events = {"AAA": [N.Event(ts=_et(2026, 1, 5, 9, 0), kind="TRIGGER_A",
                              source="EDGAR", symbol="AAA", detail="424B5")]}
    mid = S.mid_hold_trades(base, events, N.EDGAR_PLUS_HEADLINES)
    assert len(mid) == 0    # already vetoed at entry -- not a NEW mid-hold trigger


def test_mid_hold_trades_excludes_event_after_exit():
    base = [{"symbol": "AAA", "entry_ts": _et(2026, 1, 5, 9, 35),
            "exit_ts": _et(2026, 1, 5, 9, 41), "date": "2026-01-05",
            "entry_et": "09:35", "exit_et": "09:41"}]
    events = {"AAA": [N.Event(ts=_et(2026, 1, 5, 9, 50), kind="TRIGGER_A",
                              source="EDGAR", symbol="AAA", detail="424B5")]}
    mid = S.mid_hold_trades(base, events, N.EDGAR_PLUS_HEADLINES)
    assert len(mid) == 0


# --- csv + render smoke tests ---------------------------------------------------------

def test_write_labeled_csv_round_trips(tmp_path):
    pop = {"MCL": [{"symbol": "AAA", "date": "2026-01-05", "entry_et": "09:35",
                   "net": 1.0, "entry_ts": _et(2026, 1, 5, 9, 35)}],
          "MC5": []}
    events = {}
    out = tmp_path / "labeled.csv"
    S.write_labeled_csv(str(out), pop, events)
    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2   # MCL x 2 source cells (MC5 empty contributes 0)
    assert all(r["vetoed"] == "False" for r in rows)


def test_render_runs_without_exception_on_tiny_population():
    # a minimal population, built directly rather than via a CSV
    pop = {
        "MCL": [{"symbol": "AAA", "date": "2026-01-05", "entry_et": "09:35",
                "exit_et": "09:41", "net": 1.0,
                "entry_ts": _et(2026, 1, 5, 9, 35), "exit_ts": _et(2026, 1, 5, 9, 41)}],
        "MC5": [{"symbol": "BBB", "date": "2026-01-06", "entry_et": "10:00",
                "exit_et": "10:05", "net": -2.0,
                "entry_ts": _et(2026, 1, 6, 10, 0), "exit_ts": _et(2026, 1, 6, 10, 5)}],
    }
    events: dict = {}
    cuts = {"MCL": "2026-01-05", "MC5": "2026-01-06"}
    symdays = {"MCL": 1, "MC5": 1}
    lines = S.render(pop, events, cuts, symdays)
    assert any("H-N1" in l for l in lines)
    assert any("H-N2" in l for l in lines)
