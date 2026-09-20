#!/usr/bin/env python3
"""Which contract is held, and the continuous series built from it.

Hand-built calendars only (handover_tsmom_engine_20260920 section 4). The two
failures these exist for: holding the wrong contract around a roll (amendment
C), and a continuous series that looks right while booking the wrong contract
(PROGRAM_INDEX section 3, the project's signature failure).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.tsmom.registry import ALL_ROOTS, CORE, Root
from strategy.tsmom.roll import held_contract, held_series, roll_schedule
from tests.strategy.tsmom.fixtures import monthly_contracts, sessions

D = pd.Timestamp


def _held(contracts, sess, root):
    return held_contract(roll_schedule(contracts, sess, root), sess)


# --- the front-month rule ----------------------------------------------------

def test_front_rule_rolls_five_sessions_before_expiry():
    sess = sessions("2020-01-01", "2020-06-30")
    con = monthly_contracts("CL", "2020-01", "2020-08")        # expire the 20th
    held = _held(con, sess, CORE["CL"])
    # Feb contract expires Thu 2020-02-20. Five sessions before: Thu 2020-02-13.
    assert held[D("2020-02-12")] == "CLG0_2020"
    assert held[D("2020-02-13")] == "CLH0_2020", "rolled AT the close of R"
    assert held[D("2020-02-20")] == "CLH0_2020"


def test_front_rule_counts_sessions_not_calendar_days():
    """A holiday inside the window pushes the roll one session earlier."""
    sess = sessions("2020-01-01", "2020-06-30", holidays=["2020-02-17"])
    con = monthly_contracts("CL", "2020-01", "2020-08")
    held = _held(con, sess, CORE["CL"])
    # sessions before 02-20: 19, 18, 14(Fri), 13, 12 -> R = Wed 2020-02-12
    assert held[D("2020-02-11")] == "CLG0_2020"
    assert held[D("2020-02-12")] == "CLH0_2020"


def test_front_rule_expiry_on_a_non_session_uses_the_last_session_before():
    sess = sessions("2020-01-01", "2020-06-30")
    con = monthly_contracts("CL", "2020-01", "2020-08", expiry_day=22)   # Sat 2020-02-22
    held = _held(con, sess, CORE["CL"])
    # event = Fri 02-21; R = five sessions earlier = Fri 02-14
    assert held[D("2020-02-13")] == "CLG0_2020"
    assert held[D("2020-02-14")] == "CLH0_2020"


# --- amendment C: the active-cycle rule --------------------------------------

def test_hg_late_august_rolls_straight_to_december():
    """Amendment C's own example: HG in late August holds December, which is
    c.4 that day (Aug, Sep, Oct, Nov, Dec listed). Oct and Nov are never held."""
    sess = sessions("2020-06-01", "2020-12-31")
    # HG's last trade is the third-last business day of the month (27 Aug 2020)
    con = monthly_contracts("HG", "2020-06", "2021-03", expiry_day=27)
    held = _held(con, sess, CORE["HG"])
    # first business day of Sep 2020 = Tue 09-01; five sessions before = Tue 08-25
    assert held[D("2020-08-24")] == "HGU0_2020"
    assert held[D("2020-08-25")] == "HGZ0_2020"
    listed_that_day = [s for s, e in zip(con["symbol"], con["expiration"])
                       if e >= D("2020-08-25")]
    assert listed_that_day.index("HGZ0_2020") == 4, "December is c.4 on the roll day"
    assert "HGV0_2020" not in set(held) and "HGX0_2020" not in set(held)
    assert "HGQ0_2020" not in set(held), "Aug is not in HG's cycle"


def test_cycle_rule_never_holds_into_the_delivery_month():
    for name in ("GC", "SI", "HG"):
        root = CORE[name]
        sess = sessions("2019-01-01", "2020-12-31")
        con = monthly_contracts(name, "2019-01", "2021-06")
        held = _held(con, sess, root)
        month_of = dict(zip(con["symbol"], zip(con["year"], con["month"])))
        for t, sym in held.items():
            y, m = month_of[sym]
            assert (t.year, t.month) < (y, m), f"{name} holds {sym} on {t.date()}"
            assert m in root.cycle


def test_gc_cycle_and_si_skips_january():
    sess = sessions("2019-01-01", "2020-12-31")
    gc = set(_held(monthly_contracts("GC", "2019-01", "2021-06"), sess, CORE["GC"]))
    assert all("FGHJKMNQUVXZ".index(s[2]) + 1 in (2, 4, 6, 8, 10, 12) for s in gc)
    si = set(_held(monthly_contracts("SI", "2019-01", "2021-06"), sess, CORE["SI"]))
    assert not any(s[2] == "F" for s in si), "SI January is listed but NOT held"
    assert any(s[2] == "Z" for s in si) and any(s[2] == "H" for s in si)


def test_zn_and_tn_quarterly_roll_before_the_delivery_month():
    sess = sessions("2020-01-01", "2020-12-31")
    con = monthly_contracts("ZN", "2020-01", "2021-06", months=(3, 6, 9, 12))
    for root in (ALL_ROOTS["ZN"], ALL_ROOTS["TN"]):
        held = _held(con, sess, root)
        # Jun 2020: first business day Mon 06-01; five sessions before = Mon 05-25
        assert held[D("2020-05-22")] == "ZNM0_2020"
        assert held[D("2020-05-25")] == "ZNU0_2020"


def test_the_front_rule_would_have_held_into_delivery_so_the_rules_differ():
    """If the cycle rule were silently the front rule, HG would hold a serial
    month and hold into delivery. Pin that the two rules give different books."""
    sess = sessions("2020-06-01", "2020-12-31")
    con = monthly_contracts("HG", "2020-06", "2021-03")
    front = Root("HG", 25000.0, "MHG", 0.1)
    assert (_held(con, sess, CORE["HG"]) != _held(con, sess, front)).any()


# --- the calendar is sessions, and weekends are refused ------------------------

def test_a_weekend_date_in_the_calendar_is_refused():
    sess = sessions("2020-01-01", "2020-03-31").append(pd.DatetimeIndex([D("2020-04-05")]))
    con = monthly_contracts("CL", "2020-01", "2020-08")
    with pytest.raises(ValueError, match="weekend"):
        roll_schedule(con, sess, CORE["CL"])


def test_no_contract_for_the_last_sessions_is_refused():
    sess = sessions("2020-01-01", "2020-06-30")
    con = monthly_contracts("CL", "2020-01", "2020-03")
    with pytest.raises(ValueError, match="no contract"):
        _held(con, sess, CORE["CL"])


# --- the continuous series against the held-contract book ----------------------

def _two_contracts(gap=10.0):
    """A expires 2020-03-20; B = A + gap on every day. Prices move."""
    sess = sessions("2020-02-03", "2020-04-30")
    con = pd.DataFrame({"symbol": ["A", "B"],
                        "expiration": [D("2020-03-20"), D("2020-06-19")],
                        "year": [2020, 2020], "month": [3, 6]})
    base = 50 + np.arange(len(sess)) * 0.3 + np.sin(np.arange(len(sess)))
    px = pd.DataFrame({"A": base, "B": base + gap}, index=sess)
    px.loc[px.index > D("2020-03-20"), "A"] = np.nan
    return con, sess, px


def test_continuous_and_held_book_differ_by_exactly_the_gap():
    con, sess, px = _two_contracts(gap=10.0)
    held = _held(con, sess, CORE["CL"])
    s = held_series(px, held)
    R = s.index[s["rolled"]]
    assert list(R) == [D("2020-03-13")], "one roll, five sessions before 03-20"
    r = R[0]

    # the held-contract P/L on the roll day is the OLD contract's move
    prev = s.index[s.index.get_loc(r) - 1]
    assert s.at[r, "dP"] == pytest.approx(px.at[r, "A"] - px.at[prev, "A"])
    assert s.at[r, "gap"] == pytest.approx(10.0)

    # the spliced raw price jumps by the gap; the held book does not
    splice = s["raw"].diff()
    diff = (splice - s["dP"]).iloc[1:]
    assert diff[r] == pytest.approx(10.0)
    assert (diff.drop(r).abs() < 1e-12).all()
    assert splice.iloc[1:].sum() - s["dP"].iloc[1:].sum() == pytest.approx(10.0)

    # the back-adjusted series moves by EXACTLY the held-contract P/L, every day
    assert np.allclose(s["cont"].diff().iloc[1:], s["dP"].iloc[1:], atol=1e-12)
    # ... it equals the raw price after the last roll, and raw + gap before it
    assert np.allclose(s.loc[s.index >= r, "cont"], s.loc[s.index >= r, "raw"])
    assert np.allclose(s.loc[s.index < r, "cont"], s.loc[s.index < r, "raw"] + 10.0)


def test_two_rolls_accumulate_gaps_backwards():
    sess = sessions("2020-01-01", "2020-09-30")
    con = monthly_contracts("ES", "2020-01", "2020-12", months=(3, 6, 9, 12))
    base = 100 + np.arange(len(sess)) * 0.1
    px = pd.DataFrame({c: base + 3.0 * i for i, c in enumerate(con["symbol"])}, index=sess)
    s = held_series(px, _held(con, sess, CORE["ES"]))
    assert int(s["rolled"].sum()) == 3
    assert s["cont"].iloc[0] - s["raw"].iloc[0] == pytest.approx(9.0)
    assert np.allclose(s["cont"].diff().iloc[1:], s["dP"].iloc[1:])


def test_return_is_the_held_contracts_own_return():
    con, sess, px = _two_contracts()
    s = held_series(px, _held(con, sess, CORE["CL"]))
    t = s.index[10]
    prev = s.index[9]
    h = s.at[prev, "held"]
    assert s.at[t, "ret"] == pytest.approx(px.at[t, h] / px.at[prev, h] - 1)


def test_a_missing_bar_is_carried_and_counted():
    con, sess, px = _two_contracts()
    t = sess[5]
    px.loc[t, "A"] = np.nan
    s = held_series(px, _held(con, sess, CORE["CL"]))
    assert bool(s.at[t, "stale"]) and int(s["stale"].sum()) == 1
    assert s.at[t, "dP"] == 0.0


def test_a_held_contract_with_no_price_yet_is_refused():
    con, sess, px = _two_contracts()
    px.loc[px.index <= D("2020-03-16"), "B"] = np.nan
    with pytest.raises(ValueError, match="no price yet"):
        held_series(px, _held(con, sess, CORE["CL"]))


def test_a_nonpositive_price_is_refused():
    con, sess, px = _two_contracts()
    px.loc[sess[3], "A"] = 0.0
    with pytest.raises(ValueError, match="<= 0"):
        held_series(px, _held(con, sess, CORE["CL"]))
