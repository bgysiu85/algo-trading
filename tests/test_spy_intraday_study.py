#!/usr/bin/env python3
"""H0, the five gates and the point-in-time sigma1 gate, on data with a KNOWN answer.

A verdict function is only worth its output if it can say both words. These
tests build books whose answer is known by construction -- an injected edge
large enough to clear the bar, and a pure coin flip that must not -- and
require PASSES on the first and NOTHING on the second.

The test that matters most is `test_trailing_gate_has_no_look_ahead`. The
trailing percentile is the one place in this study where a future value could
leak into a past decision, and look-ahead is this project's most expensive
recurring defect: a full-sample percentile would have been an entirely
plausible-looking implementation that produced a better answer for the wrong
reason. It is checked by MUTATION -- rewrite the future and require every past
gate decision to be bit-identical -- rather than by reading the code.
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pandas as pd
import pytest

if "ib_async" not in sys.modules:                             # pragma: no cover
    try:
        import ib_async                                       # noqa: F401
    except ImportError:
        _stub = types.ModuleType("ib_async")

        def _attr(name):
            if name == "util":
                return types.SimpleNamespace(df=lambda x: None)
            return type("_Stub", (), {"__init__": lambda self, *a, **k: None})

        _stub.__getattr__ = _attr
        sys.modules["ib_async"] = _stub

from common import spy_intraday_study as ST                    # noqa: E402


def _sessions(n: int, edge: float, seed: int = 1) -> pd.DataFrame:
    """r1 and r13 with a controllable amount of sign agreement between them.

    `edge` is the probability that r13's sign matches r1's beyond a coin
    flip: 0.0 is a pure control, 0.5 is a hit rate of about 75%.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-02", periods=n).strftime("%Y-%m-%d")
    r1 = rng.normal(0, 0.004, n)
    mag = np.abs(rng.normal(0, 0.0025, n))
    agree = rng.random(n) < (0.5 + edge / 2.0)
    r13 = np.where(agree, np.sign(r1), -np.sign(r1)) * mag
    return pd.DataFrame({"r1": r1, "r13": r13}, index=pd.Index(idx, name="sess"))


# --------------------------------------------------------------------------
# H0 -- it runs first and it can stop the study
# --------------------------------------------------------------------------

def test_h0_on_a_coin_flip_lands_on_minus_friction():
    b = ST.book(_sessions(1500, edge=0.0))
    res = ST.h0(b, "realistic", draws=2000)
    flat, why = ST.h0_is_flat(res)
    assert flat, why
    assert res["mean"] == pytest.approx(res["expected"], abs=3e-6)


def test_h0_flatness_check_can_fail():
    """A control that cannot report a problem is not a control."""
    res = ST.h0(ST.book(_sessions(500, edge=0.0)), "realistic", draws=500)
    res["mean"] = res["expected"] + 0.001          # 10 bps out
    flat, why = ST.h0_is_flat(res)
    assert not flat and "harness is wrong" in why


def test_h0_expected_value_tracks_the_friction_level():
    b = ST.book(_sessions(800, edge=0.0))
    lo = ST.h0(b, "optimistic", draws=800)
    hi = ST.h0(b, "pessimistic", draws=800)
    assert lo["expected"] > hi["expected"]
    assert lo["mean"] > hi["mean"]


# --------------------------------------------------------------------------
# the gates, both words
# --------------------------------------------------------------------------

def test_a_real_edge_passes_all_five():
    tag, failed, n = ST.verdict(ST.book(_sessions(2000, edge=0.45, seed=5)))
    assert tag == "PASSES", failed
    assert n["per_trade"] > 0 and n["annual_pct"] > 0


def test_a_coin_flip_fails():
    tag, failed, _ = ST.verdict(ST.book(_sessions(2000, edge=0.0, seed=9)))
    assert tag == "NOTHING" and failed


def test_an_edge_that_only_survives_optimistic_friction_is_nothing():
    """Spec section 13. The primary read is REALISTIC, and it is not negotiable."""
    b = ST.book(_sessions(2500, edge=0.05, seed=11))
    opt = ST.net(b, "optimistic").mean()
    real = ST.net(b, "realistic").mean()
    assert opt > real                                  # cheaper friction, better
    tag, _, _ = ST.verdict(b, "realistic")
    assert tag == "NOTHING"


def test_an_empty_half_is_not_a_pass():
    b = ST.book(_sessions(40, edge=0.9, seed=3))
    tag, failed, _ = ST.verdict(b.iloc[:0])
    assert tag == "NOTHING"


def test_drop_top_removes_sessions_and_can_flip_a_thin_result():
    b = ST.book(_sessions(600, edge=0.0, seed=13))
    full = ST.net(b, "realistic").sum()
    assert ST.drop_top(b, "realistic", 5) < full


# --------------------------------------------------------------------------
# the point-in-time gate -- checked by mutation
# --------------------------------------------------------------------------

def test_trailing_gate_has_no_look_ahead():
    """Rewrite the future; every earlier decision must be bit-identical."""
    rng = np.random.default_rng(4)
    idx = pd.bdate_range("2015-01-02", periods=900).strftime("%Y-%m-%d")
    sig = pd.Series(rng.lognormal(mean=-6, sigma=0.5, size=900), index=idx)
    base = ST.trailing_gate(sig)

    tampered = sig.copy()
    tampered.iloc[600:] = tampered.iloc[600:] * 50.0       # a wildly different future
    after = ST.trailing_gate(tampered)

    assert base.iloc[:600].equals(after.iloc[:600]), (
        "a change after session 600 moved a decision before it -- look-ahead")


def test_trailing_gate_does_not_trade_the_first_window():
    rng = np.random.default_rng(6)
    idx = pd.bdate_range("2015-01-02", periods=400).strftime("%Y-%m-%d")
    sig = pd.Series(rng.lognormal(size=400), index=idx)
    g = ST.trailing_gate(sig)
    assert not g.iloc[:ST.TRAIL_WINDOW].any(), (
        "sessions with no trailing history must not be gated in")
    assert g.iloc[ST.TRAIL_WINDOW:].any()


def test_trailing_gate_is_not_a_full_sample_percentile():
    """The defect this is guarding against, written out so it can be seen."""
    rng = np.random.default_rng(8)
    idx = pd.bdate_range("2015-01-02", periods=800).strftime("%Y-%m-%d")
    sig = pd.Series(rng.lognormal(size=800), index=idx)
    pit = ST.trailing_gate(sig)
    full = sig >= sig.quantile(ST.SIGMA_Q)                # the look-ahead version
    assert not pit.equals(full)


def test_gated_book_is_a_subset_of_the_ungated_one():
    s = _sessions(700, edge=0.2, seed=15)
    sig = pd.Series(np.random.default_rng(2).lognormal(size=len(s)),
                    index=s.index)
    b_all = ST.book(s)
    b_gated = ST.book(s, ST.trailing_gate(sig))
    assert set(b_gated.index) <= set(b_all.index)
    assert len(b_gated) < len(b_all)
    # and the two cells therefore have different denominators, which the
    # report is required to state
    assert len(b_gated) != len(b_all)


# --------------------------------------------------------------------------
# the rule as written
# --------------------------------------------------------------------------

def test_a_zero_r1_goes_short():
    """'r1 > 0 -> LONG, r1 <= 0 -> SHORT'. The tie is specified; honour it."""
    s = pd.DataFrame({"r1": [0.0, 1e-12, -1e-12], "r13": [0.001] * 3},
                     index=["2020-01-02", "2020-01-03", "2020-01-06"])
    assert list(ST.book(s)["sign"]) == [-1.0, 1.0, -1.0]


def test_gross_is_sign_times_r13():
    s = pd.DataFrame({"r1": [0.01, -0.01], "r13": [0.002, 0.002]},
                     index=["2020-01-02", "2020-01-03"])
    b = ST.book(s)
    assert b.loc["2020-01-02", "gross"] == pytest.approx(0.002)
    assert b.loc["2020-01-03", "gross"] == pytest.approx(-0.002)


def test_friction_is_charged_once_per_round_trip():
    s = pd.DataFrame({"r1": [0.01], "r13": [0.0]}, index=["2020-01-02"])
    b = ST.book(s)
    for lvl, f in ST.FRICTION_BPS.items():
        assert ST.net(b, lvl).iloc[0] == pytest.approx(-f / 10_000.0)


def test_month_bootstrap_blocks_by_calendar_month():
    b = ST.book(_sessions(600, edge=0.3, seed=21))
    bt = ST.month_bootstrap(b, "realistic", draws=500)
    assert bt["valid"]
    assert bt["n_months"] == len({x[:7] for x in b.index})
    assert bt["lo"] < bt["hi"]


# --------------------------------------------------------------------------
# the run gate -- relaxed to the scored window, and it must still fire
# --------------------------------------------------------------------------

def _res(bad=(), gaps=(), dst=(), conflicts=0):
    return {"bad_first_bar": list(bad), "n_bad_first_bar": len(bad),
            "gaps": [(a, b, 9, ["x"]) for a, b in gaps], "n_gaps": len(gaps),
            "dst_bad": list(dst), "dup_conflicts": conflicts}


def _sess(days):
    return pd.DataFrame(index=pd.Index(days, name="sess"))


def test_run_gate_ignores_defects_before_the_scored_window():
    """A 2004 defect cannot reach a 2015+ book, and must not block the run."""
    s = _sess(["2014-12-31", "2015-01-02", "2015-01-05"])
    ok, why = ST.assertions_clean(
        _res(bad=["2008-03-31", "2004-02-10"],
             gaps=[("2004-01-28", "2004-02-02")]), s)
    assert ok, why


def test_run_gate_still_fires_on_a_defect_inside_the_window():
    s = _sess(["2014-12-31", "2015-01-02", "2020-06-01"])
    ok, why = ST.assertions_clean(_res(bad=["2020-06-01"]), s)
    assert not ok and "scored window" in why[0]
    ok, why = ST.assertions_clean(_res(gaps=[("2020-05-20", "2020-06-01")]), s)
    assert not ok and "unexplained session gaps" in why[0]


def test_run_gate_checks_the_session_the_first_scored_r1_reads():
    """r1 of the first scored session reads the session BEFORE the window."""
    s = _sess(["2014-12-31", "2015-01-02"])
    ok, why = ST.assertions_clean(_res(bad=["2014-12-31"]), s)
    assert not ok, "a defect on the boundary session must block the run"


def test_run_gate_never_ignores_a_price_disagreement():
    """Two cache rows disagreeing on a price is not a windowed question."""
    s = _sess(["2014-12-31", "2015-01-02"])
    ok, why = ST.assertions_clean(_res(conflicts=3), s)
    assert not ok and "disagree on price" in why[0]


# --------------------------------------------------------------------------
# pit_strategy --use-apex: the flag must REACH the engine
# --------------------------------------------------------------------------

def test_use_apex_flag_reaches_the_engine_kwargs():
    """An inert flag would make both arms of the registered comparison
    identical and print a 0.00 delta as a finding.
    REGISTERED_apex_counterfactual.md section 5."""
    from common import pit_strategy as PS
    _, off = PS.engine("mc5", use_apex=False)
    _, on = PS.engine("mc5", use_apex=True)
    _, default = PS.engine("mc5")
    assert off == {"use_apex": False}
    assert on == {"use_apex": True}
    assert default == {}, "omitting the flag must not change the published run"
    _, mcl_default = PS.engine("mcl")
    _, mcl_on = PS.engine("mcl", use_apex=True)
    assert mcl_on["use_apex"] is True
    assert mcl_default.get("use_apex") is False   # MCL's LIVE, untouched
