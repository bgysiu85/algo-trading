"""OTF-G: the sec 2.1 state machine (every row of the table, hand-worked) and the G4 look-ahead guards (a, b, c)."""
import numpy as np
import pandas as pd
import pytest

from strategy.otf_gate import gate as G
from strategy.otf_gate import otf
from strategy.otf_gate.spec import BAL, DOWN, LONG, SHORT, UNDEF, UP

# (H, L, C) -> state after the bar; comments name the table row exercised
HAND = [
    (10.0, 8.0, 9.0, BAL),      # 0 initial BAL, ref = bar 0
    (11.0, 9.0, 10.5, UP),      # 1 BAL: C > H[ref]=10 -> UP
    (12.0, 10.0, 11.5, UP),     # 2 UP: OTF-up -> stay
    (13.0, 10.5, 11.0, BAL),    # 3 UP: neither up (C not > 12) nor down -> BAL, ref = bar 3 (13, 10.5)
    (12.0, 11.0, 11.5, BAL),    # 4 BAL: inside the ref range -> stay
    (12.5, 11.2, 12.2, BAL),    # 5 BAL: bar is OTF-up on its own but C <= H[ref]=13 -> stays (Imre rule 4)
    (14.0, 12.5, 13.5, UP),     # 6 BAL: C > 13 -> UP
    (13.0, 11.0, 11.5, DOWN),   # 7 UP: OTF-down -> DOWN
    (12.0, 10.0, 10.5, DOWN),   # 8 DOWN: OTF-down -> stay
    (12.4, 10.2, 12.1, UP),     # 9 DOWN: OTF-up -> UP directly
    (12.2, 10.4, 11.0, BAL),    # 10 UP -> BAL, ref = bar 10 (12.2, 10.4)
    (11.9, 10.0, 10.3, DOWN),   # 11 BAL: C < L[ref]=10.4 -> DOWN
    (11.0, 10.1, 10.6, BAL),    # 12 DOWN -> BAL, ref = bar 12 (11.0, 10.1)
    (10.9, 10.2, 10.5, BAL),    # 13 BAL stays
    (11.5, 10.3, 11.0, BAL),    # 14 BAL: C == H[ref] does not step (strict)
    (11.6, 10.4, 11.1, UP),     # 15 BAL: C > 11.0 -> UP
    (11.6, 10.5, 11.6, BAL),    # 16 UP: H == prev H does not step -> BAL
]


def _hlc():
    a = np.array(HAND)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3].astype(int)


def test_every_row_of_the_state_table_hand_worked():
    h, l, c, want = _hlc()
    st, rh, rl = otf.run_states(h, l, c)
    assert st.tolist() == want.tolist()
    assert (rh[3], rl[3]) == (13.0, 10.5) and (rh[4], rl[4]) == (13.0, 10.5) and (rh[5], rl[5]) == (13.0, 10.5)
    assert (rh[12], rl[12]) == (11.0, 10.1) and (rh[14], rl[14]) == (11.0, 10.1)   # G4 c: ref fixed when BAL starts


def test_initial_state_is_bal_with_first_bar_as_reference():
    st, rh, rl = otf.run_states([5.0], [4.0], [4.5])
    assert st.tolist() == [BAL] and (rh[0], rl[0]) == (5.0, 4.0)
    assert otf.run_states([], [], [])[0].size == 0


def test_bal_reference_is_not_moved_by_a_bar_that_looks_directional():
    """G4 c: if the ref moved to the previous bar, bar 5 (own OTF-up) would be UP; it must stay BAL until 6."""
    h, l, c, want = _hlc()
    st, *_ = otf.run_states(h[:6], l[:6], c[:6])
    assert st[5] == BAL
    moved = otf.run_states(h[:6], l[:6], c[:6])  # mutation: pretend the ref were bar t-1 (12.0, 11.0): C 12.2 > 12.0
    assert 12.2 > 12.0 and moved[0][5] == BAL


def test_dalton_classic_uses_only_the_low_or_high_test():
    # bar1: L > prev L but the close does not clear the prior high -> Imre BAL(stays), Dalton UP
    h, l, c = [10, 11, 11.5], [8, 9, 9.5], [9, 9.6, 10.0]
    assert otf.run_states(h, l, c, "imre")[0].tolist() == [BAL, BAL, BAL]
    st = otf.run_states(h, l, c, "dalton")[0].tolist()
    assert st[1] == BAL          # from BAL only the reference bar ends it: C 9.6 not > 10
    # from an UP state Dalton keeps it UP on L > prevL alone
    s, _, _ = otf.step(UP, np.nan, np.nan, 12, 10, 12.5, 10.5, 11.0, "dalton")
    assert s == UP
    s2, _, _ = otf.step(UP, np.nan, np.nan, 12, 10, 12.5, 10.5, 11.0, "imre")
    assert s2 == BAL
    with pytest.raises(ValueError):
        otf.step(UP, 0, 0, 1, 1, 1, 1, 1, "nope")


# ------------------------------------------------------------------ aggregation and 'completed before tau'
def _daily(n_weeks=8, seed=1, start="2020-01-06"):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=5 * n_weeks)
    c = 100 + np.cumsum(rng.normal(0, 1, len(dates)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0.1, 1, len(dates))
    l = np.minimum(o, c) - rng.uniform(0.1, 1, len(dates))
    return pd.DataFrame({"date": dates, "open": o, "high": h, "low": l, "close": c})


def test_aggregate_matches_pandas_resample():
    d = _daily()
    w = otf.aggregate(d, otf.iso_week_key(d["date"]))
    r = d.set_index("date").resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    assert len(w) == len(r)
    np.testing.assert_allclose(w[["open", "high", "low", "close"]].to_numpy(), r.to_numpy())
    m = otf.aggregate(d, otf.month_key(d["date"]))
    r2 = d.set_index("date").resample("ME").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    np.testing.assert_allclose(m[["open", "high", "low", "close"]].to_numpy(), r2.to_numpy())


def test_aggregate_rejects_a_key_that_comes_back():
    d = _daily(2)
    with pytest.raises(ValueError):
        otf.aggregate(d, np.array([1, 1, 2, 1, 1, 3, 3, 3, 3, 3]))


def test_stack_states_use_only_bars_completed_before_the_entry_session():
    """G4 a/b: change everything from the entry session on -> the state is identical; change the last completed
    bar -> it can change. The week/month the entry belongs to is never used by the primary."""
    d = _daily(12)
    s = d["date"].iloc[33]                                     # a Thursday in week 7 (0-based 6)
    base = otf.Stack(d).states_at([s]).iloc[0]
    d2 = d.copy()
    later = d2["date"] >= s
    d2.loc[later, ["open", "high", "low", "close"]] *= 3.7     # wreck the entry session and everything after it
    same = otf.Stack(d2).states_at([s]).iloc[0]
    assert (base[["d", "w", "m"]] == same[["d", "w", "m"]]).all()
    # wreck only the in-progress week's days BEFORE the entry session (Mon..Wed): daily may change, weekly must not
    wk = otf.iso_week_key(d["date"])
    inprog = (wk == otf.iso_week_key([s])[0]) & (d["date"] < s)
    d3 = d.copy()
    d3.loc[inprog, ["high"]] += 50.0
    w_same = otf.Stack(d3).states_at([s]).iloc[0]
    assert w_same["w"] == base["w"] and w_same["m"] == base["m"]


def test_a_one_bar_shift_of_the_completion_rule_breaks_the_test_above():
    """The mutation the guard exists for: if 'completed' were '<= entry session' the state would move."""
    d = _daily(12)
    s = d["date"].iloc[33]
    st = otf.Stack(d)
    i = st.D.completed_index(s)
    assert st.D.last[i] < np.datetime64(s, "ns")
    assert st.D.last[i + 1] >= np.datetime64(s, "ns")           # the next bar is the entry session itself
    j = st.W.completed_index(s)
    assert st.W.keys[j] != otf.iso_week_key([s])[0]              # never the week in progress
    assert st.W.keys[j + 1] == otf.iso_week_key([s])[0]


def test_first_session_of_a_week_and_month_use_the_previous_completed_bar():
    d = _daily(12)
    st = otf.Stack(d)
    monday = d["date"].iloc[15]                                  # first session of a week
    j = st.W.completed_index(monday)
    assert st.W.last[j] == np.datetime64(d["date"].iloc[14], "ns")
    firsts = d.groupby(d["date"].dt.to_period("M"))["date"].first()
    s = firsts.iloc[1]
    k = st.M.completed_index(s)
    assert st.M.keys[k] == otf.month_key([firsts.iloc[0]])[0]


def test_undefined_before_the_first_completed_bar_and_counted_as_removed():
    d = _daily(6)
    st = otf.Stack(d)
    s0 = d["date"].iloc[0]
    assert st.states_at([s0]).iloc[0][["d", "w", "m"]].tolist() == [UNDEF] * 3
    x = st.states_at([s0]).assign(direction=LONG)
    assert not G.keep_mask(x, x["direction"])[0]
    assert G.removal_reason(x, x["direction"])[0] == "undefined"


def test_live_variant_reads_only_sessions_before_the_entry_in_the_current_week():
    d = _daily(12)
    s = d["date"].iloc[33]
    base = otf.Stack(d).states_at([s], live=True).iloc[0]
    d2 = d.copy()
    d2.loc[d2["date"] >= s, ["open", "high", "low", "close"]] *= 2.9
    assert otf.Stack(d2).states_at([s], live=True).iloc[0].equals(base)


def test_live_step_equals_a_state_machine_run_on_the_partial_bar():
    d = _daily(12)
    s = d["date"].iloc[33]
    live = otf.Stack(d).states_at([s], live=True).iloc[0]
    part = d[(d["date"] < s)]
    w = otf.aggregate(part, otf.iso_week_key(part["date"]))          # last bar of `w` is the partial week
    st, *_ = otf.run_states(w["high"], w["low"], w["close"])
    assert live["w"] == st[-1]
    mo = otf.aggregate(part, otf.month_key(part["date"]))
    assert live["m"] == otf.run_states(mo["high"], mo["low"], mo["close"])[0][-1]


# ------------------------------------------------------------------ the gate
def _st(d, w, m, nd=1, nw=1, nm=1):
    return pd.DataFrame({"d": d, "w": w, "m": m, "nd": nd, "nw": nw, "nm": nm})


def test_strict_gate_and_reasons():
    st = _st([UP, UP, UP, DOWN, UP, UP, UNDEF, DOWN], [UP, UP, UP, DOWN, DOWN, BAL, UP, DOWN],
             [UP, UP, UP, DOWN, UP, UP, UP, DOWN])
    dirn = np.array([LONG, SHORT, LONG, SHORT, LONG, LONG, LONG, LONG])
    keep = G.keep_mask(st, dirn)
    assert keep.tolist() == [True, False, True, True, False, False, False, False]
    why = G.removal_reason(st, dirn)
    assert why.tolist() == ["", "against", "", "", "disagree", "any_bal", "undefined", "against"]


def test_variants_soft_dayweek_opposite_naive():
    st = _st([UP, BAL, DOWN, UP], [UP, UP, UP, BAL], [BAL, UP, UP, UP], nd=[1, 1, -1, 1], nw=[1, 1, 1, 1], nm=[1, 1, 1, 1])
    dirn = np.array([LONG] * 4)
    assert G.keep_mask(st, dirn, "soft").tolist() == [True, True, False, True]      # BAL kept, only 'against' removed
    assert G.keep_mask(st, dirn, "day_week").tolist() == [True, False, False, False]
    assert G.keep_mask(st, dirn, "opposite").tolist() == [False] * 4
    assert G.keep_mask(st, dirn, "naive").tolist() == [True, True, False, True]
    with pytest.raises(ValueError):
        G.keep_mask(st, dirn, "best")


def test_gate_direction_convention():
    st = _st([DOWN], [DOWN], [DOWN])
    assert G.keep_mask(st, np.array([SHORT]))[0] and not G.keep_mask(st, np.array([LONG]))[0]


def test_equal_low_or_high_does_not_step():
    # UP after bar 1; bar 2 makes a higher high and closes above the prior high but its LOW only equals the prior low
    st = otf.run_states([10, 11, 12], [8, 9, 9], [9, 10.5, 11.5])[0].tolist()
    assert st == [BAL, UP, BAL]
    # mirror: DOWN after bar 1; bar 2 makes a lower low and closes below the prior low but its HIGH equals the prior high
    st = otf.run_states([10, 7.5, 7.5], [8, 6, 5], [9, 6.5, 5.5])[0].tolist()
    assert st == [BAL, DOWN, BAL]


def test_a_partial_last_bar_in_the_data_is_never_used_as_completed():
    """G4 b: if the daily data STOP in the middle of the entry session's week (as the H-B rebuild does at the
    training end), the week bar's last date is before the entry yet it is still in progress."""
    d = _daily(12)
    s = d["date"].iloc[33]                                           # a Thursday: Mon-Wed are before it
    cut = d[d["date"] < s]                                           # data end Wednesday
    st = otf.Stack(cut)
    j = st.W.completed_index(s)
    assert st.W.last[j] < np.datetime64(s, "ns")                     # the partial week's last date is before s ...
    assert st.W.keys[j] != otf.iso_week_key([s])[0]                  # ... but it is not the one used
    assert st.W.keys[j + 1] == otf.iso_week_key([s])[0]              # (it is the next bar, the one in progress)
    m_cut = d[d["date"] < d["date"].iloc[42]]
    stm = otf.Stack(m_cut)
    k = stm.M.completed_index(d["date"].iloc[42])
    assert stm.M.keys[k] != otf.month_key([d["date"].iloc[42]])[0]


def test_strict_needs_the_monthly_leg_too():
    st = _st([UP, UP, UP], [UP, UP, UP], [BAL, DOWN, UP])
    dirn = np.array([LONG, LONG, LONG])
    assert G.keep_mask(st, dirn).tolist() == [False, False, True]
    assert G.removal_reason(st, dirn).tolist() == ["any_bal", "disagree", ""]
    assert G.keep_mask(st, dirn, "day_week").tolist() == [True, True, True]
