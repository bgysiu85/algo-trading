#!/usr/bin/env python3
"""W05-0019: the symbol-day mask, and the ways it could lie.

REGISTERED_running_up_universe_scored.md. This is a MASK, not a re-simulated
gate: it only removes whole symbol-days from an already-published book, so
the parts worth pinning are the ones a mistake would make plausible --

  - a zero-pre-bar day (NaN peak_ret5m) must never be admitted, at any cut,
    including a cut below zero;
  - the mask drops WHOLE symbol-days, never a single row within one that
    survives while a sibling row on the same day is dropped;
  - `gated` is always an exact subset of `base` -- nothing is added,
    nothing is reordered, nothing is mutated;
  - the "could bind" ceiling counts trades, not symbol-days, and does not
    move with the cut;
  - `symdays_of` / `days_of` de-duplicate by (symbol, date), not by row.
"""
from __future__ import annotations

from common import running_up_universe_gate as UG


def row(sym, date, ordinal=1, net="0.00", entry_et="07:00"):
    return {"book": "MCL", "symbol": sym, "date": date, "ordinal": str(ordinal),
            "entry_et": entry_et, "entry_px": "1.00", "exit_et": "07:05",
            "exit_px": "1.00", "reason": "trailing_stop", "bars_held": "3", "net": net}


def feat(sym, date, pre_bars, peak):
    return (sym, date), {"pre_bars": pre_bars,
                          "peak_ret5m": float("nan") if peak is None else peak}


# --- keep_set -----------------------------------------------------------

def test_zero_pre_bar_day_is_never_kept_even_below_zero():
    features = dict([feat("A", "2026-01-01", 0, None)])
    keep = UG.keep_set(features, cut=-999.0)
    assert keep == set(), "a bought-on-sight day must not clear ANY cut"


def test_boundary_is_inclusive():
    features = dict([feat("A", "2026-01-01", 10, 0.148)])
    assert ("A", "2026-01-01") in UG.keep_set(features, cut=0.148)
    assert ("A", "2026-01-01") not in UG.keep_set(features, cut=0.1481)


def test_missing_pre_bars_field_never_admitted_by_a_stray_nan_compare():
    # peak_ret5m present (bad data) but pre_bars still 0 -- the explicit
    # pre_bars > 0 check must be what excludes it, not reliance on NaN alone.
    features = dict([feat("A", "2026-01-01", 0, 5.0)])
    assert UG.keep_set(features, cut=0.01) == set()


# --- gate_book: whole symbol-days, never a single row -------------------

def test_a_symbol_day_is_all_or_nothing():
    rows = [row("A", "2026-01-01", 1), row("A", "2026-01-01", 2),
            row("B", "2026-01-01", 1)]
    keep = {("A", "2026-01-01")}
    gated, refused = UG.gate_book(rows, keep)
    assert {r["symbol"] for r in gated} == {"A"}
    assert len(gated) == 2, "both of A's trades must survive together"
    assert {r["symbol"] for r in refused} == {"B"}


def test_gated_is_an_exact_subset_never_reorders_or_mutates():
    rows = [row("A", "2026-01-01", 1, net="12.34"), row("B", "2026-01-01", 1, net="-5.00")]
    keep = {("A", "2026-01-01"), ("B", "2026-01-01")}
    gated, refused = UG.gate_book(rows, keep)
    assert gated == rows, "keeping every symbol-day must reproduce base bit-for-bit"
    assert refused == []


def test_refused_is_the_exact_complement():
    rows = [row("A", "2026-01-01"), row("B", "2026-01-02"), row("C", "2026-01-03")]
    keep = {("B", "2026-01-02")}
    gated, refused = UG.gate_book(rows, keep)
    assert [r["symbol"] for r in gated] == ["B"]
    assert [r["symbol"] for r in refused] == ["A", "C"]
    assert len(gated) + len(refused) == len(rows)


# --- could_bind: the ceiling, independent of cut -------------------------

def test_could_bind_counts_trades_not_symbol_days():
    rows = [row("A", "2026-01-01", 1), row("A", "2026-01-01", 2),  # same day, 2 trades
            row("B", "2026-01-02", 1)]
    features = dict([feat("A", "2026-01-01", 10, 0.2), feat("B", "2026-01-02", 0, None)])
    could, total, detail = UG.could_bind(rows, features)
    assert total == 3
    assert could == 2, "both of A's trades sit on a coverable day"
    assert detail[">0 pre-entry bars"] == 2
    assert detail["0 pre-entry bars"] == 1


def test_could_bind_missing_symbol_day_treated_as_uncoverable():
    rows = [row("Z", "2026-01-09")]
    could, total, detail = UG.could_bind(rows, features={})
    assert could == 0 and total == 1
    assert detail["0 pre-entry bars"] == 1


# --- symdays_of / days_of -------------------------------------------------

def test_symdays_of_dedupes_by_symbol_and_date():
    rows = [row("A", "2026-01-01", 1), row("A", "2026-01-01", 2), row("B", "2026-01-01", 1)]
    assert UG.symdays_of(rows) == 2


def test_days_of_is_sorted_and_deduped():
    rows = [row("A", "2026-01-03"), row("B", "2026-01-01"), row("C", "2026-01-01")]
    assert UG.days_of(rows) == ["2026-01-01", "2026-01-03"]


# --- the nine cuts are fixed, not re-derived ------------------------------

def test_cuts_are_the_preflights_own_nine_printed_deciles():
    assert UG.CUTS == (0.045, 0.067, 0.089, 0.117, 0.148, 0.188, 0.243, 0.336, 0.542)
    assert len(UG.CUTS) == 9
