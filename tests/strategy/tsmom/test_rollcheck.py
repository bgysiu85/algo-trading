#!/usr/bin/env python3
"""AT-41's comparison and its registered stop rule, on hand-built calendars."""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.tsmom import rollcheck as RC
from tests.strategy.tsmom.fixtures import monthly_contracts, sessions

D = pd.Timestamp


def _c0_following(con, sess, shift_by=None):
    """c.0 exactly as a nearest-expiry series would be: each contract until the
    session after its expiration date. `shift_by` = {symbol: sessions late}."""
    shift_by = shift_by or {}
    con = con.sort_values("expiration")
    out = pd.Series(index=sess, dtype=object)
    k = 0
    syms, exps = list(con["symbol"]), list(con["expiration"])
    leave = {}
    for s, e in zip(syms, exps):
        j = sess.searchsorted(e, side="right") + shift_by.get(s, 0)
        leave[s] = j
    for i in range(len(sess)):
        while k < len(syms) and i >= leave[syms[k]]:
            k += 1
        out.iloc[i] = syms[k]
    return out


def _setup(**kw):
    sess = sessions("2015-01-01", "2020-12-31")
    con = monthly_contracts("CL", "2014-12", "2021-06")
    return con, sess, _c0_following(con, sess, **kw)


def test_an_exact_calendar_agrees_everywhere():
    con, sess, c0 = _setup()
    tab = RC.compare(c0, con)
    v = RC.verdict(tab)
    assert v["rolls_compared"] == 72        # Jan 2015 .. Dec 2020 expiries: 6 x 12
    assert v["disagree_gt1"] == 0 and v["any_disagreement"] == 0
    assert v["result"] == "PASS"


def test_one_session_late_is_listed_but_does_not_count():
    con, sess, c0 = _setup(shift_by={"CLF7_2017": 1})
    tab = RC.compare(c0, con)
    v = RC.verdict(tab)
    assert v["disagree_gt1"] == 0 and v["any_disagreement"] == 1
    assert int(tab.set_index("symbol").at["CLF7_2017", "diff_sessions"]) == 1


def test_two_percent_passes_and_just_over_stops():
    con, sess, _ = _setup()
    n = 72
    # 1 of 72 = 1.39% -> PASS; 2 of 72 = 2.78% -> STOP. "More than 2%" stops.
    one = RC.verdict(RC.compare(_c0_following(con, sess, shift_by={"CLF7_2017": 3}), con))
    assert one["disagree_gt1"] == 1 and one["result"] == "PASS"
    two = RC.verdict(RC.compare(_c0_following(
        con, sess, shift_by={"CLF7_2017": 3, "CLF8_2018": -2}), con))
    assert two["disagree_gt1"] == 2 and two["pct"] == pytest.approx(200 / n)
    assert two["result"] == "STOP"


def test_exactly_two_percent_does_not_stop():
    tab = pd.DataFrame({"diff_sessions": [5.0] + [0.0] * 49})
    assert RC.verdict(tab)["pct"] == pytest.approx(2.0)
    assert RC.verdict(tab)["result"] == "PASS"


def test_a_contract_never_seen_as_c0_is_a_disagreement():
    con, sess, c0 = _setup()
    skip = "CLG6_2016"
    nxt = "CLH6_2016"
    c0 = c0.where(c0 != skip, nxt)
    tab = RC.compare(c0, con).set_index("symbol")
    assert pd.isna(tab.at[skip, "diff_sessions"])
    assert RC.verdict(tab.reset_index())["disagree_gt1"] == 1


def test_a_late_listed_root_is_only_checked_inside_its_history():
    con = monthly_contracts("RTY", "2010-01", "2021-06")
    sess = sessions("2017-07-10", "2020-12-31")
    tab = RC.compare(_c0_following(con[con["expiration"] >= D("2017-07-01")], sess), con)
    assert tab["expiration"].min() >= D("2017-07-10").date()
    assert RC.verdict(tab)["disagree_gt1"] == 0


def test_the_report_lists_every_disagreement_and_the_overall_result():
    con, sess, _ = _setup()
    tab = RC.compare(_c0_following(con, sess, shift_by={"CLF7_2017": 3}), con)
    note = {"files": ["CL.dbn.zst"], "sunday_rows_dropped": 5, "unmapped_rows": 0,
            "unmapped_pct": 0.0, "point_value_mismatch": []}
    text = RC.format_report({"CL": (tab, RC.verdict(tab))}, {"CL": note})
    assert "CLF7_2017" in text and "diff +3  > 1" in text
    assert "OVERALL: PASS" in text
