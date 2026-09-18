#!/usr/bin/env python3
"""H-E2: the entry sweep, and the things that would make it a different study.

Registered in docs/research/REGISTERED_entry_sweep.md. The sweep's whole claim
is "one constant at a time, everything else published". The failure that would
break that claim silently is a swept value LOSING to the engine's published
config -- F1's macd-off cell would then be a second copy of the base and the
table would show two identical rows that nobody reads as a bug.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common import entry_sweep as E
from common import running_up as RU

ET = RU.ET
CUT = "2026-09-11"


def t(net=10.0, date="2026-09-10", bars=5, ret5=0.02, symbol="X"):
    return {"symbol": symbol, "date": date, "ordinal": 1, "net": float(net),
            "entry_et": "05:00", "entry_px": 3.0, "exit_et": "05:05",
            "exit_px": 3.1, "reason": "trailing_stop", "bars_held": bars,
            "ret_5m": ret5}


def book(n, net, date="2026-09-10", **kw):
    return [t(net=net, date=date, symbol=f"S{i}", **kw) for i in range(n)]


def both_halves(n, net, **kw):
    """Half the trades either side of the median session, so the halves tests
    have something to read."""
    return book(n, net, "2026-09-10", **kw) + book(n, net, "2026-09-12", **kw)


# --- the sweep's structure --------------------------------------------------

def test_every_swept_value_is_the_one_the_registration_names():
    """§2 fixed these before any code existed. A value added later is a search."""
    assert [k.get("vol_multiple") for _, _, k in E.F2] == [1.5, 2.0, 2.5, None, 4.0]
    assert [k.get("entry_rsi_roc") for _, _, k in E.F3] == [1.0, 2.5, None, 7.5, 10.0]
    assert [k.get("require_macd_pos") for _, _, k in E.F1] == [None, False]


def test_each_family_sweeps_exactly_one_constant():
    """V9 dropped MACD > 0 and the surge together and collapsed 81%, and
    nobody could say which did it. That is what this pins."""
    for _title, fam, _base, _b in E.FAMILIES:
        keys = {k for _, _, kw in fam for k in kw}
        assert len(keys) <= 1, f"{keys} -- more than one constant moves in this family"


def test_the_base_book_is_run_once_not_once_per_family():
    """MCL is the base of F1 and F2. Two copies could drift on a float sum and
    the two families would then be scored against different baselines."""
    names = [n for n, _, _ in E.BOOKS]
    assert len(names) == len(set(names))
    assert names.count("MCL") == 1 and names.count("MC5") == 1
    assert len(E.BOOKS) == 11


def test_the_swept_value_beats_the_engines_published_config(monkeypatch):
    """THE BUG THIS EXISTS FOR. engine("mcl") returns LIVE, which already
    contains require_macd_pos=True. If the published config were merged over
    the swept value, F1's macd-off cell would silently be a second copy of the
    base -- two identical rows in the table and no error anywhere."""
    seen = []

    class FakeMod:
        @staticmethod
        def backtest_session(df, d, tz, **kw):
            seen.append(kw)
            return []

    import common.pit_strategy as PS
    import common.dbn_io as DB
    idx = pd.DatetimeIndex([pd.Timestamp(f"2026-09-11 05:0{i}", tz=ET) for i in range(6)])
    df = pd.DataFrame({"open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0,
                       "volume": 100, "symbol": "A"}, index=idx)
    monkeypatch.setattr(DB, "read_dbn", lambda p: df)
    monkeypatch.setattr(PS, "build_frame", lambda parts, day: df)
    monkeypatch.setattr(PS, "engine",
                        lambda name: (FakeMod, {"require_macd_pos": True}))
    universe = [{"symbol": "A", "first_seen": "2026-09-11T05:00:00-04:00"}]
    E.run_day((["2026-09-11.dbn"], "2026-09-11", universe))

    off = [kw for kw in seen if kw.get("require_macd_pos") is False]
    assert off, "the macd-off cell never reached the engine with False"
    # and the base still gets the published value
    assert any(kw.get("require_macd_pos") is True for kw in seen)


# --- the verdict ------------------------------------------------------------

def test_a_cell_that_beats_the_base_both_ways_in_both_halves_improves():
    base = both_halves(40, -10.0)
    cell = both_halves(50, -5.0)              # more trades AND better per trade
    tag, why, n = E.verdict(base, cell, CUT, 100)
    assert tag == "IMPROVES", (tag, why)
    assert n["d_pt"] > 0


def test_a_cell_that_is_better_per_trade_but_worse_in_total_is_nothing():
    """The realistic loose-threshold case: a lower bar ADDS trades that are
    individually less bad, and the book still loses more money overall. §4
    requires both readings precisely so that cannot be sold as an improvement."""
    base = both_halves(50, -10.0)
    cell = both_halves(150, -9.0)
    tag, why, n = E.verdict(base, cell, CUT, 100)
    assert n["d_pt"] > 0, "fixture no longer improves per trade"
    assert tag in ("NOTHING", "REFUSED"), (tag, why)


def test_improves_requires_the_total_in_BOTH_halves_not_just_overall():
    """The gap a one-sided reading leaves. This cell is better per trade in
    both halves and better overall, so the denominators agree and it reaches
    the IMPROVES branch -- but its LATE half loses more money than the base's.
    Without the total-in-both-halves clause it would read IMPROVES."""
    base = book(50, -10.0, "2026-09-10") + book(50, -10.0, "2026-09-12")
    cell = book(40, -8.0, "2026-09-10") + book(70, -9.0, "2026-09-12")
    tag, why, n = E.verdict(base, cell, CUT, 100)
    assert n["d_pt"] > 0 and n["d_sd"] > 0, (n["d_pt"], n["d_sd"])
    assert tag == "NOTHING" and "total" in why, (tag, why)


def test_a_positive_book_in_both_halves_clears():
    base = both_halves(40, -10.0)
    cell = both_halves(40, +10.0)          # net of the $4.26 friction, still up
    tag, why, _ = E.verdict(base, cell, CUT, 100)
    assert tag == "CLEARS", (tag, why)


def test_the_denominators_disagreeing_is_a_refusal():
    """Fewer, better trades: per trade up, per symbol-day down. Every other
    study here refuses that, and so does this one."""
    base = both_halves(50, -10.0)
    cell = both_halves(150, -9.0)          # better per trade, bigger total loss
    tag, why, n = E.verdict(base, cell, CUT, 100)
    assert n["d_pt"] > 0 and n["d_sd"] < 0
    assert tag == "REFUSED" and "denominators disagree" in why


def tightening_pair(seed=5):
    """A cell that keeps half the base and is only slightly better per trade --
    the shape a tightened threshold actually takes."""
    rng = np.random.default_rng(seed)
    keep, drop = [], []
    for i in range(200):
        for date, bucket, mu in (("2026-09-10", keep, -9.0), ("2026-09-12", keep, -9.0),
                                 ("2026-09-10", drop, -11.0), ("2026-09-12", drop, -11.0)):
            bucket.append(t(net=float(rng.normal(mu, 30)), date=date,
                            symbol=f"S{len(bucket)}"))
    return keep + drop, keep


def test_a_tightening_cell_is_scored_against_random_removal():
    """§3: most cells ADD trades, so abstention cannot flatter them. The ones
    that tighten are the exception and carry the control -- and a small gain
    that sits inside random removal's band is not a pass."""
    base, cell = tightening_pair()
    tag, why, n = E.verdict(base, cell, CUT, 500)
    assert n["abst"] is not None and n["abst"]["valid"]
    assert 0 < n["d_pt"] <= n["abst"]["per_trade"]["p95"], n["d_pt"]
    assert tag == "NOTHING" and "random removal" in why


def test_a_refused_tightening_cell_still_carries_its_control():
    """A refusal with no control attached leaves the reader unable to tell
    abstention from a real effect."""
    base = both_halves(60, -10.0)
    cell = both_halves(5, -30.0)          # fewer trades, worse -> denominators split
    _tag, _why, n = E.verdict(base, cell, CUT, 500)
    assert n["abst"] is not None


def test_a_cell_that_adds_trades_gets_no_abstention_control():
    base = both_halves(30, -10.0)
    cell = both_halves(60, -10.0)
    _tag, _why, n = E.verdict(base, cell, CUT, 100)
    assert n["abst"] is None


# --- the boundary check is scored, not decorative ---------------------------

def test_an_optimum_at_the_edge_reads_undecided():
    books = {n: both_halves(40, -10.0) for n, _, _ in E.BOOKS}
    books["MCL vol 1.5"] = both_halves(60, -2.0)          # best, and it is the edge
    out = "\n".join(E.family_block("F2", E.F2, "MCL", True, books, CUT, 100))
    assert "AT THE EDGE OF THE SWEPT RANGE" in out
    assert "UNDECIDED -- BOUNDARY" in out


def test_an_interior_optimum_keeps_its_verdict():
    books = {n: both_halves(40, -10.0) for n, _, _ in E.BOOKS}
    books["MCL vol 2.5"] = both_halves(60, -2.0)          # best, and interior
    out = "\n".join(E.family_block("F2", E.F2, "MCL", True, books, CUT, 100))
    assert "interior" in out and "UNDECIDED -- BOUNDARY" not in out


def test_the_two_value_family_claims_no_boundary_check():
    """§4: a two-value family is all boundary, so none is claimed."""
    books = {n: both_halves(40, -10.0) for n, _, _ in E.BOOKS}
    out = "\n".join(E.family_block("F1", E.F1, "MCL", False, books, CUT, 100))
    assert "no boundary check" in out and "EDGE" not in out


# --- the mechanism, read back as a measurement ------------------------------

def test_a_looser_cell_that_does_not_enter_earlier_is_said_so():
    """§5. The claim is observable, and a cell that fails it may not be called
    'entering earlier' whatever its P&L says."""
    books = {n: both_halves(40, -10.0, ret5=0.05) for n, _, _ in E.BOOKS}
    books["MCL vol 1.5"] = both_halves(40, -10.0, ret5=0.01)    # earlier
    books["MCL vol 2.0"] = both_halves(40, -10.0, ret5=0.09)    # later
    books["MCL vol 2.5"] = both_halves(40, -10.0, ret5=0.05)    # unchanged
    out = "\n".join(E.mechanism_block(books))
    assert "vol 1.5" in out and "enters EARLIER" in out
    assert "enters LATER" in out and "no change" in out


def test_median_ret5_ignores_nan_rather_than_poisoning_the_median():
    rows = [t(ret5=0.01), t(ret5=float("nan")), t(ret5=0.03)]
    assert E.median_ret5(rows) == pytest.approx(0.02)
    assert E.median_ret5([t(ret5=float("nan"))]) != E.median_ret5([t(ret5=float("nan"))])


def test_drop_top_removes_five_not_three():
    """§4 of this registration says five; first_entry_skip's DROP is three, and
    importing the wrong one would quietly change the bar."""
    rows = [t(net=100.0) for _ in range(5)] + [t(net=-1.0) for _ in range(3)]
    assert E.DROP_N == 5
    assert E.drop_top(rows, 0.0) == pytest.approx(-3.0)


# --- the report -------------------------------------------------------------

def test_the_report_names_the_registration_and_every_family():
    books = {n: both_halves(40, -10.0) for n, _, _ in E.BOOKS}
    text = "\n".join(E.render(books, 500, 0, ["2026-09-10", CUT, "2026-09-12"],
                              1.0, 4, [], E.PAIRS, "XNAS.ITCH"))
    assert E.REGISTERED in text
    for title, _f, _b, _bd in E.FAMILIES:
        assert title in text
    assert "NOT THE SUB-MINUTE QUESTION" in text
    assert "holdout.json has not been touched" in text
    assert "evaluate_last_bar still" in text          # the live-path separation
