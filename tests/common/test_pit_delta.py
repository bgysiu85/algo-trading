#!/usr/bin/env python3
"""Does the intraday floor move a delta, or only a level?

The module exists to test one inference in HANDOVER_20260911.md §4 -- that a
$6.84-$11.99 gap between two LEVELS tells you something about DELTAS measured on
the same trades. These tests defend the two things that would make its answer
worthless: a variant that differs from its base by nothing, and four runs that
drop different sessions.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import pit_delta as PD
from strategy.mcl import mcl as MCL
from tests.common.test_pit_strategy import frame, rec

ET = ZoneInfo("America/New_York")
D = date(2026, 3, 2)
LIVE = dict(use_apex=False, require_macd_pos=True)


# --- a variant must actually differ from its base ----------------------------

def test_a_variant_that_does_nothing_is_refused_rather_than_run():
    """Base against base reports a delta of exactly 0.00, which renders as
    NOT MATERIAL -- the same words a real null produces. Cameron's breakeven
    stop is not a single kwarg, so it is absent rather than stubbed."""
    with pytest.raises(SystemExit) as e:
        PD.variant_kwargs("breakeven")
    assert "unknown variant" in str(e.value)


@pytest.mark.parametrize("v", ["ladder", "ladder_linear", "cameron_partial"])
def test_every_known_variant_differs_from_its_base(v):
    base, var, what = PD.variant_kwargs(v)
    assert base != var, f"{v} runs base against base"
    assert what and "PLACEHOLDER" not in what


# --- the four runs share a session set --------------------------------------

def test_all_four_runs_come_from_the_same_sessions():
    """If a session the engine cannot run were dropped from three arms and not
    the fourth, the deltas would be computed over different session sets --
    the exact failure this module detects, inside the detector."""
    df = frame()
    got = PD.run_day(df, D.isoformat(), [rec(h=6, m=0)], mod=MCL, extra=LIVE,
                     base={}, var={"ladder": None})
    dates = {k: {t["date"] for t in v} for k, v in got.items()}
    assert all(d == dates["base_free"] for d in dates.values())


def test_a_symbol_with_no_bars_contributes_to_no_arm():
    got = PD.run_day(frame(), D.isoformat(), [rec(sym="ZZZ")], mod=MCL,
                     extra=LIVE, base={}, var={"ladder": None})
    assert all(v == [] for v in got.values())


def test_a_stage2_record_with_no_first_seen_is_skipped():
    """This module only compares floored against unfloored, so a name with no
    first_seen has no floored arm and must not silently join the unfloored one."""
    got = PD.run_day(frame(), D.isoformat(),
                     [{"symbol": "AAA", "date": D.isoformat(),
                       "first_seen": None}],
                     mod=MCL, extra=LIVE, base={}, var={"ladder": None})
    assert all(v == [] for v in got.values())


def test_the_floored_arms_enter_no_earlier_than_first_seen():
    got = PD.run_day(frame(), D.isoformat(), [rec(h=8, m=0)], mod=MCL,
                     extra=LIVE, base={}, var={"ladder": None})
    for k in ("base_held", "var_held"):
        for t in got[k]:
            assert pd.Timestamp(t["entry_time"]).tz_convert(ET).time() \
                >= dtime(8, 0)
    assert got["base_free"], "the unfloored arm should still have trades"


# --- the verdict ------------------------------------------------------------

def rows(per, n, start=0):
    return [{"date": f"2026-{1 + i % 9:02d}-01", "symbol": f"S{i + start}",
             "net": per + 4.26} for i in range(n)]


def out(base_free, var_free, base_held, var_held, n=400):
    arms = {"base_free": rows(base_free, n), "var_free": rows(var_free, n),
            "base_held": rows(base_held, n), "var_held": rows(var_held, n)}
    return "\n".join(PD.render("mcl", "ladder", "the ladder against none",
                               arms, "2026-05-01", 546, 4997, 1.0))


def test_a_delta_the_floor_barely_moves_reads_as_not_material():
    o = out(-10.0, -10.2, -14.0, -14.25)
    assert "NOT MATERIAL" in o
    assert "does not hold here" in o


def test_a_delta_the_floor_moves_past_the_threshold_says_re_run():
    o = out(-10.0, -10.2, -14.0, -16.0)
    assert "MATERIAL." in o
    assert "re-run floored" in o
    assert "better as easily as worse" in o


def test_a_delta_that_changes_sign_is_called_out_above_the_threshold():
    o = out(-10.0, -9.0, -14.0, -15.0)
    assert "CHANGES SIGN" in o


def test_the_threshold_is_stated_in_the_report_before_the_numbers():
    o = out(-10.0, -10.2, -14.0, -14.25)
    i, j = o.index("PRE-REGISTERED"), o.index("UNFLOORED")
    assert i < j, "the threshold must be stated before the arms"
    assert f"{PD.MATERIAL:.2f}" in o


def test_a_thin_arm_refuses_a_verdict():
    # A non-zero delta, or the never-fired guard fires first and correctly.
    arms = {"base_free": rows(-10.0, 5), "var_free": rows(-10.6, 5),
            "base_held": rows(-14.0, 5), "var_held": rows(-14.9, 5)}
    o = "\n".join(PD.render("mcl", "ladder", "x", arms, "2026-05-01", 10, 50,
                            1.0))
    assert "NO VERDICT" in o
    assert str(PD.MIN_TRADES) in o


def test_unequal_trade_counts_are_surfaced_not_hidden_in_one_number():
    """A mechanic that changes how many trades happen moves the per-trade delta
    without any money moving."""
    arms = {"base_free": rows(-10.0, 400), "var_free": rows(-10.0, 300),
            "base_held": rows(-14.0, 400), "var_held": rows(-14.0, 300)}
    o = "\n".join(PD.render("mcl", "ladder", "x", arms, "2026-05-01", 546,
                            4997, 1.0))
    assert "DO NOT HOLD THE SAME TRADE COUNT" in o
    assert "delta net" in o


def test_one_mechanic_is_not_claimed_to_settle_the_others():
    o = out(-10.0, -10.2, -14.0, -14.25)
    assert "cannot prove the other three" in o
    assert "A null here is weaker evidence than a positive" in o


def test_the_report_refuses_comparison_with_the_published_ladder_result():
    o = out(-10.0, -10.2, -14.0, -14.25)
    assert "Not the published ladder result" in o
    assert "has NOT been spent" in o


def test_every_delta_is_reported_at_all_three_friction_levels():
    o = out(-10.0, -10.2, -14.0, -14.25)
    for label, _ in PD.FRICTIONS:
        assert o.count(label) >= 2, label


def test_a_mechanic_that_never_fired_is_not_reported_as_a_null():
    """Exactly-zero deltas with matching counts mean base and variant ran the
    same trades -- the mechanic's trigger was never reached. That produces the
    same words as a real null. Caught on a synthetic archive where the ladder's
    rungs sat above every price in the data."""
    o = out(-10.0, -10.0, -14.0, -14.0)
    assert "THE MECHANIC NEVER FIRED" in o
    assert "NOT MATERIAL" not in o
    assert "trigger against this universe's price range" in o


def test_a_real_null_is_still_reported_as_not_material():
    """The guard must not swallow a genuine small-but-nonzero delta."""
    o = out(-10.0, -10.05, -14.0, -14.02)
    assert "NOT MATERIAL" in o
    assert "NEVER FIRED" not in o
