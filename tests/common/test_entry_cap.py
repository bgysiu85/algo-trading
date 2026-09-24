"""common.entry_cap -- the cap is a pure ordinal cut, and its controls behave."""
from __future__ import annotations

import csv

import pytest

from common import entry_cap as ec


def _row(sym, day, k, net, t="07:00"):
    return {"symbol": sym, "date": day, "ordinal": k, "entry_et": t, "entry_px": 2.0,
            "exit_et": t, "exit_px": 2.0, "reason": "x", "bars_held": 1, "net": float(net)}


def _book():
    # A: 5 entries, B: 2 entries, C: 4 entries
    return ([_row("A", "2025-01-02", k, n) for k, n in enumerate([10, -5, -5, -20, -30], 1)]
            + [_row("B", "2025-01-02", k, n) for k, n in enumerate([3, -3], 1)]
            + [_row("C", "2025-06-02", k, n) for k, n in enumerate([1, 1, 1, -40], 1)])


def test_cap_is_the_ordinal_cut_and_a_subset():
    base = _book()
    kept, removed = ec.cap(base, 3)
    assert len(kept) + len(removed) == len(base)
    assert all(r["ordinal"] <= 3 for r in kept) and all(r["ordinal"] > 3 for r in removed)
    assert [r["net"] for r in removed] == [-20.0, -30.0, -40.0]
    ids = {id(r) for r in base}
    assert all(id(r) in ids for r in kept)          # no cascade: nothing new


def test_cap_large_enough_is_identity():
    base = _book()
    kept, removed = ec.cap(base, 99)
    assert kept == base and removed == []


def test_mutation_cap_is_not_off_by_one():
    base = _book()
    assert len(ec.cap(base, 3)[1]) == 3            # A#4, A#5, C#4
    assert len(ec.cap(base, 4)[1]) == 1            # A#5 only
    assert len(ec.cap(base, 2)[1]) == 5


def test_check_ordinals_flags_a_gap():
    base = _book()
    assert ec.check_ordinals(base) == []
    base[1]["ordinal"] = 7
    assert ec.check_ordinals(base) == ["A 2025-01-02"]


def test_positional_control_is_zero_when_every_trade_is_equal():
    base = [_row("A", "d", k, 5.0) for k in range(1, 7)] + [_row("B", "d", 1, 5.0)]
    p = ec.positional(base, 3, f=0.0, draws=200)
    assert p["valid"] and p["k"] == 3 and p["touched"] == 1
    assert p["p05"] == pytest.approx(0.0) and p["p95"] == pytest.approx(0.0)


def test_positional_control_only_draws_from_touched_symbol_days():
    # B is untouched and hugely negative; if the control drew from it, p05 would crater
    base = ([_row("A", "d", k, 0.0) for k in range(1, 5)]
            + [_row("B", "d", k, -1000.0) for k in range(1, 3)])
    p = ec.positional(base, 3, f=0.0, draws=500)
    assert p["k"] == 1
    assert p["p05"] == pytest.approx(p["p95"])     # every draw removes a 0.0 trade from A


def test_positional_invalid_when_nothing_removed():
    assert ec.positional(_book(), 99, f=0.0)["valid"] is False


def test_ordinal_table_buckets_five_plus():
    t = {lab: n for lab, n, *_ in ec.ordinal_table(_book(), f=0.0)}
    assert t == {"#1": 3, "#2": 3, "#3": 2, "#4": 2, "#5+": 1}


def test_load_books_reads_only_named_books(tmp_path):
    p = tmp_path / "t.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["book", "symbol", "date", "ordinal", "entry_et", "entry_px", "exit_et",
                    "exit_px", "reason", "bars_held", "net"])
        w.writerow(["MCL", "A", "2025-01-02", 1, "07:00", 2, "07:05", 2.1, "trailing_stop", 5, "-1.5"])
        w.writerow(["MCL-c033", "A", "2025-01-02", 1, "07:00", 2, "07:05", 2.1, "trailing_stop", 5, "-1.5"])
        w.writerow(["MC5", "B", "2025-01-02", 2, "08:00", 2, "08:05", 2.1, "window_close", 5, "3"])
    b = ec.load_books(p)
    assert len(b["MCL"]) == 1 and len(b["MC5"]) == 1
    assert b["MC5"][0]["ordinal"] == 2 and b["MCL"][0]["net"] == -1.5


def test_late_split_and_time_of_day():
    rows = [_row("A", "d", 1, 1, "07:00"), _row("A", "d", 2, -3, "08:00"), _row("A", "d", 3, -5, "09:00")]
    (nb, pb), (na, pa) = ec.late_split(rows, f=0.0)
    assert (nb, na) == (1, 2) and pb == 1.0 and pa == -4.0
    t = ec.time_of_day(rows)
    assert t["median"] == "08:00" and round(t["late_share"]) == 67
