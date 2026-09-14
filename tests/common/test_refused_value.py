#!/usr/bin/env python3
"""Does the refused-bar pricing measure what it claims, and refuse what it must?

Two hazards here, and they pull in opposite directions.

OVERSTATING. Every total assumes each refused bar could have been taken
independently, which the concurrency cap makes false -- live it refused 29% of
buy attempts. So a positive pooled total must never be presented as money left
on the table, and the module's verdict has to lead with the per-trade figure,
which is the only one the cap does not touch.

UNDERSTATING BY CONSTRUCTION. If the population quietly included bars the
indicators had already rejected, or if the exit were re-implemented here rather
than taken from the strategy, a negative result would be an artefact and the
line of enquiry would close on a mistake.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import refused_value as R
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def sig_frame(rows):
    """rows = [(c_macd, c_mfi, c_rsi, c_vol, c_floor, trail_avg)]"""
    idx = pd.DatetimeIndex([
        pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                      dtime(7, 0), tzinfo=ET))
        + timedelta(minutes=i) for i in range(len(rows))])
    cols = ["c_macd", "c_mfi", "c_rsi", "c_vol", "c_floor"]
    d = pd.DataFrame([r[:5] for r in rows], columns=cols, index=idx)
    for c in cols:
        d[c] = d[c].astype(bool)
    d["trail_avg"] = [r[5] for r in rows]
    return d


class T:
    """Only the field price() reads."""
    def __init__(self, net):
        self.net = net


# --- the population -----------------------------------------------------------

def test_floor_sole_needs_the_other_three_to_have_APPROVED():
    """A bar MACD rejected could never have entered whatever the volume did.
    Including it would drag the measured value toward zero for free."""
    d = sig_frame([(0, 1, 1, 1, 0, 45_000.0),      # MACD said no
                   (1, 1, 1, 1, 0, 45_000.0)])     # the real shape
    m = R.refused_mask(d, "floor_sole")
    assert list(m) == [False, True]


def test_a_warm_up_bar_is_never_in_the_population():
    d = sig_frame([(1, 1, 1, 1, 0, float("nan")),
                   (1, 1, 1, 1, 0, 45_000.0)])
    assert list(R.refused_mask(d, "floor_sole")) == [False, True]


def test_locked_is_a_SUBSET_of_floor_sole():
    d = sig_frame([(1, 1, 1, 1, 0, 45_000.0),
                   (1, 1, 1, 0, 1, 45_000.0),
                   (1, 1, 1, 1, 0, 45_000.0)])
    fs = R.refused_mask(d, "floor_sole")
    lk = R.refused_mask(d, "locked")
    assert list(fs) == [True, False, True]
    assert list(lk) == [True, False, False]
    assert not (lk & ~fs).any()


def test_a_bar_that_ENTERED_is_not_refused():
    d = sig_frame([(1, 1, 1, 1, 1, 45_000.0)])
    assert not R.refused_mask(d, "floor_sole").any()


def test_an_unknown_population_raises():
    with pytest.raises(ValueError, match="unknown population"):
        R.refused_mask(sig_frame([(1, 1, 1, 1, 0, 45_000.0)]), "everything")


# --- the exit is the STRATEGY'S ------------------------------------------------

def test_entry_bars_REPLACES_the_rule_rather_than_adding_to_it():
    """'Enter where the rule said no' and 'enter where the rule said yes OR
    where I say so' are different populations. A union would mix the control
    into its own treatment."""
    import inspect
    src = inspect.getsource(MCL.backtest_session)
    assert "entry_bars" in src
    assert "fires = row[\"entry\"] if take is None else take[i]" in src


def test_the_default_path_is_untouched_when_no_mask_is_given():
    """The addition must be bit-identical when unused, or every published MCL
    figure silently moves."""
    import numpy as np
    n = 200
    t0 = pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                       dtime(4, 0), tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)])
    rng = np.random.default_rng(3)
    c = 7.0 + np.cumsum(rng.normal(0, 0.02, n))
    v = rng.integers(4000, 9000, n).astype(float)
    v[120] = v[119] * 9
    df = pd.DataFrame({"open": c, "high": c * 1.003, "low": c * 0.997,
                       "close": c, "volume": v}, index=idx)
    day = pd.Timestamp("2026-09-11").date()
    a = MCL.backtest_session(df, day, ET)
    b = MCL.backtest_session(df, day, ET, entry_bars=None)
    assert [t.net for t in a] == [t.net for t in b]


def test_a_mask_of_all_False_produces_no_trades():
    import numpy as np
    n = 200
    t0 = pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                       dtime(4, 0), tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)])
    rng = np.random.default_rng(3)
    c = 7.0 + np.cumsum(rng.normal(0, 0.02, n))
    v = rng.integers(4000, 9000, n).astype(float)
    v[120] = v[119] * 9
    df = pd.DataFrame({"open": c, "high": c * 1.003, "low": c * 0.997,
                       "close": c, "volume": v}, index=idx)
    mask = pd.Series(False, index=df.index)
    assert MCL.backtest_session(df, pd.Timestamp("2026-09-11").date(), ET,
                                entry_bars=mask) == []


# --- friction and the drop ----------------------------------------------------

def test_friction_is_charged_per_round_trip():
    r = R.price([T(10.0), T(-4.0)], 4.26)
    assert r["per"] == pytest.approx((10.0 - 4.26 + -4.0 - 4.26) / 2)


def test_drop_top_5_is_n_a_not_zero_when_there_is_nothing_to_drop():
    """$0 would read as 'dropping the best five costs nothing' instead of
    'this was not computed'."""
    r = R.price([T(10.0), T(2.0)], 1.00)
    assert r["drop"] != r["drop"]          # NaN
    text = "\n".join(R.render(
        [{"symbol": "A", "date": "2026-09-11", "trades": [T(10.0)]}],
        [{"symbol": "A", "date": "2026-09-11", "trades": [T(1.0)]}],
        "floor_sole", "p.json", 1, 0, 0.1))
    assert "n/a" in text


def test_drop_top_5_removes_the_BEST_five():
    r = R.price([T(x) for x in [100, 90, 80, 70, 60, 1, 1]], 0.0)
    assert r["drop"] == pytest.approx(1.0)


# --- the verdict --------------------------------------------------------------

def rows(nets, date="2026-09-11"):
    return [{"symbol": "A", "date": date, "trades": [T(x) for x in nets]}]


def test_a_negative_per_trade_settles_it_WITHOUT_the_cap():
    text = "\n".join(R.render(rows([-20.0] * 8), rows([-5.0] * 8),
                              "floor_sole", "p.json", 1, 0, 0.1))
    assert "LOSE" in text
    assert "without the concurrency cap being consulted" in text
    assert "No variant needs writing" in text


def test_a_negative_result_worse_than_the_control_says_so():
    text = "\n".join(R.render(rows([-40.0] * 8), rows([-5.0] * 8),
                              "floor_sole", "p.json", 1, 0, 0.1))
    assert "declining bad ones" in text


def test_a_POSITIVE_per_trade_hands_the_decision_to_the_cap():
    """The only branch where the cap matters -- and it must not be presented
    as money left on the table."""
    text = "\n".join(R.render(
        rows([60.0] * 6, "2026-09-01") + rows([60.0] * 6, "2026-09-11"),
        rows([5.0] * 6), "floor_sole", "p.json", 2, 0, 0.1))
    assert "ONLY branch where the concurrency cap matters" in text
    assert "upper bound" in text


def test_halves_disagreeing_in_sign_REFUSES_a_verdict():
    text = "\n".join(R.render(
        rows([80.0] * 6, "2026-09-01") + rows([-70.0] * 6, "2026-09-11"),
        rows([5.0] * 6), "floor_sole", "p.json", 2, 0, 0.1))
    assert "NO VERDICT" in text or "LOSE" in text


def test_an_empty_population_is_named_not_scored():
    text = "\n".join(R.render([], rows([1.0]), "locked", "p.json", 0, 0, 0.1))
    assert "NO REFUSED BAR PRICED" in text
    assert "not about the interlock" in text


def test_the_report_states_the_cap_and_the_market_impact_caveats():
    text = "\n".join(R.render(rows([-20.0] * 8), rows([-5.0] * 8),
                              "floor_sole", "p.json", 1, 0, 0.1))
    assert "Not free of the cap" in text
    assert "Not a claim about the market" in text
    assert "Not out of sample" in text


# --- the main path, end to end ------------------------------------------------

def _fixture_with_a_refused_bar():
    """A frame carrying one real floor_sole bar: MACD, MFI and RSI approve,
    c_vol passes on a 40k bar after a 7k one, and c_floor fails because 7k is
    under half the ~50k trailing average.

    Built by SEARCH rather than by hand. Three attempts at constructing it
    directly produced zero refused bars -- a linear ramp saturates RSI at 100
    and pins MFI at 50, so `rising()` is False and the bar never qualifies.
    A fixture that produces nothing would have let this module ship with its
    main path never once executed, which is exactly how the last two bugs got
    out.
    """
    import numpy as np
    n = 220
    t0 = pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                       dtime(4, 0), tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)])
    rng = np.random.default_rng(0)
    c = 7.0 + np.cumsum(rng.normal(0.004, 0.03, n))
    v = np.abs(np.full(n, 50_000.0) + rng.normal(0, 2000, n))
    v[117], v[118] = 7_000.0, 40_000.0
    return pd.DataFrame({"open": c, "high": c * 1.004, "low": c * 0.996,
                         "close": c, "volume": v}, index=idx)


def test_a_refused_bar_is_actually_PRICED_end_to_end():
    df = _fixture_with_a_refused_bar()
    sig = MCL.signals(df)
    mask = R.refused_mask(sig, "floor_sole")
    assert mask.sum() == 1, "the fixture must contain exactly one refused bar"

    trades = MCL.backtest_session(df, pd.Timestamp("2026-09-11").date(), ET,
                                  entry_bars=mask)
    assert len(trades) == 1
    t = trades[0]
    assert t.entry_price > 0 and t.exit_price > 0
    assert t.bars_held > 0


def test_the_refused_trade_is_NOT_one_the_rule_would_have_taken():
    """If the mask happened to select a bar the rule already enters on, the
    module would be pricing the control against itself."""
    df = _fixture_with_a_refused_bar()
    sig = MCL.signals(df)
    assert not sig["entry"].iloc[118], "bar 118 must be one the rule REFUSED"
    mask = R.refused_mask(sig, "floor_sole")
    refused = MCL.backtest_session(df, pd.Timestamp("2026-09-11").date(), ET,
                                   entry_bars=mask)
    control = MCL.backtest_session(df, pd.Timestamp("2026-09-11").date(), ET)
    assert [t.entry_time for t in refused] != [t.entry_time for t in control]


def test_the_exit_used_is_the_STRATEGYS_trailing_stop():
    """The trade must terminate the way MCL terminates trades -- not at the
    next bar, and not at some exit written here."""
    df = _fixture_with_a_refused_bar()
    mask = R.refused_mask(MCL.signals(df), "floor_sole")
    t = MCL.backtest_session(df, pd.Timestamp("2026-09-11").date(), ET,
                             entry_bars=mask)[0]
    assert t.bars_held > 1, "a one-bar hold would mean the exit never ran"
    # The field is `reason`, not `exit_reason` -- read off the Trade dataclass
    # rather than assumed. Guessing it cost a test run.
    assert t.reason, "the trade must record HOW it exited"
    assert t.reason in {"trailing_stop", "session_end", "apex_reversal",
                        "target", "ladder", "window_close", "flat_at_close"}, \
        f"unexpected exit reason {t.reason!r}"


# --- the halves outrank the sign ----------------------------------------------

def test_a_SMALL_negative_with_disagreeing_halves_refuses_a_verdict():
    """The `locked` run pooled at (0.06) with halves of (3.39) and +2.70. The
    first version tested the sign first, so every pooled negative -- however
    small, however unstable -- short-circuited into 'settled' and skipped the
    standing evidence rule entirely."""
    text = "\n".join(R.render(
        rows([-30.0] * 6, "2026-09-01") + rows([30.0] * 6, "2026-09-11"),
        rows([5.0] * 6), "locked", "p.json", 2, 0, 0.1))
    assert "NO VERDICT" in text
    assert "REFUSAL, not a negative result" in text
    assert "does not clear" in text and "does not condemn" in text


def test_a_LARGE_negative_with_agreeing_halves_still_settles_it():
    """The refusal must not swallow a real result."""
    text = "\n".join(R.render(
        rows([-40.0] * 6, "2026-09-01") + rows([-35.0] * 6, "2026-09-11"),
        rows([5.0] * 6), "floor_sole", "p.json", 2, 0, 0.1))
    assert "LOSE" in text
    assert "NO VERDICT" not in text


def test_the_refusal_prints_BOTH_half_figures():
    """A refusal that did not show the two numbers would be unactionable."""
    text = "\n".join(R.render(
        rows([-30.0] * 6, "2026-09-01") + rows([30.0] * 6, "2026-09-11"),
        rows([5.0] * 6), "locked", "p.json", 2, 0, 0.1))
    assert "early" in text and "late" in text


# --- the single-case view -----------------------------------------------------

def test_only_parses_symbol_and_date():
    p = R.build_parser()
    assert p.parse_args(["--only", "TNON:2026-09-11"]).only == "TNON:2026-09-11"
    assert p.parse_args([]).only is None


def test_the_single_case_view_lists_the_trade_in_full():
    class Full:
        # UTC, as Trade stores it. 11:35 UTC IS 07:35 ET -- the real TNON bar.
        entry_time = "2026-09-11 11:35:00+00:00"
        exit_time = "2026-09-11 11:48:00+00:00"
        entry_price, exit_price, qty = 7.48, 8.20, 100
        reason, bars_held = "trailing_stop", 13
        gross, commission, net = 72.0, 1.40, 70.60
    text = "\n".join(R.render_one(
        [{"symbol": "TNON", "date": "2026-09-11", "trades": [Full()]}],
        [], "floor_sole", "TNON:2026-09-11", 0.1))
    assert "07:35" in text and "07:48" in text
    assert "trailing_stop" in text
    assert "13 bar(s)" in text
    for f in ("1.00", "4.26", "8.92"):
        assert f in text


def test_the_single_case_view_STATES_the_selection_bias():
    """The whole risk of answering this question: one case chosen because its
    outcome was known cannot be evidence about the rule."""
    class Full:
        # UTC, as Trade stores it. 11:35 UTC IS 07:35 ET -- the real TNON bar.
        entry_time = "2026-09-11 11:35:00+00:00"
        exit_time = "2026-09-11 11:48:00+00:00"
        entry_price, exit_price, qty = 7.48, 8.20, 100
        reason, bars_held = "trailing_stop", 13
        gross, commission, net = 72.0, 1.40, 70.60
    text = "\n".join(R.render_one(
        [{"symbol": "TNON", "date": "2026-09-11", "trades": [Full()]}],
        [], "floor_sole", "TNON:2026-09-11", 0.1))
    assert "chosen AFTER its outcome was known" in text
    assert "selection bias" in text
    assert "(3.41)" in text, "the population result must be restated here"
    assert "however large the" in text


def test_the_single_case_view_has_NO_verdict_section():
    """The aggregate view answers 'should the mechanic change'. This one
    answers 'what was that trade worth'. Sharing a verdict would let the
    second masquerade as the first."""
    class Full:
        # UTC, as Trade stores it. 11:35 UTC IS 07:35 ET -- the real TNON bar.
        entry_time = "2026-09-11 11:35:00+00:00"
        exit_time = "2026-09-11 11:48:00+00:00"
        entry_price, exit_price, qty = 7.48, 8.20, 100
        reason, bars_held = "trailing_stop", 13
        gross, commission, net = 72.0, 1.40, 70.60
    text = "\n".join(R.render_one(
        [{"symbol": "TNON", "date": "2026-09-11", "trades": [Full()]}],
        [], "floor_sole", "TNON:2026-09-11", 0.1))
    assert "VERDICT" not in text
    assert "No variant needs writing" not in text


def test_a_symbol_day_with_no_refused_bar_says_so():
    text = "\n".join(R.render_one([], [], "locked", "AAA:2026-09-11", 0.1))
    assert "NO REFUSED BAR ON THIS SYMBOL-DAY" in text
    assert "did not occur" in text or "shape did not occur" in text


# --- the archive source -------------------------------------------------------

def test_the_archive_source_declares_that_it_is_not_the_live_tape():
    """Volumes on XNAS.BASIC are ~55% of consolidated and the capture is not
    constant bar to bar. Prices are unaffected, which is why the trade can
    still be priced -- but which bars QUALIFIED carries that uncertainty and
    the report must say so."""
    class Full:
        # UTC, as Trade stores it. 11:35 UTC IS 07:35 ET -- the real TNON bar.
        entry_time = "2026-09-11 11:35:00+00:00"
        exit_time = "2026-09-11 11:48:00+00:00"
        entry_price, exit_price, qty = 7.48, 8.20, 100
        reason, bars_held = "trailing_stop", 13
        gross, commission, net = 72.0, 1.40, 70.60
    text = "\n".join(R.render_one(
        [{"symbol": "TNON", "date": "2026-09-11", "trades": [Full()]}],
        [], "floor_sole", "TNON:2026-09-11", 0.1, "archive"))
    assert "NOT THE BARS THE LIVE TRADER SAW" in text
    assert "55.2% capture" in text
    assert "PRICES are prices" in text
    assert "bars from: archive" in text


def test_the_cache_source_makes_no_such_caveat():
    class Full:
        # UTC, as Trade stores it. 11:35 UTC IS 07:35 ET -- the real TNON bar.
        entry_time = "2026-09-11 11:35:00+00:00"
        exit_time = "2026-09-11 11:48:00+00:00"
        entry_price, exit_price, qty = 7.48, 8.20, 100
        reason, bars_held = "trailing_stop", 13
        gross, commission, net = 72.0, 1.40, 70.60
    text = "\n".join(R.render_one(
        [{"symbol": "TNON", "date": "2026-09-11", "trades": [Full()]}],
        [], "floor_sole", "TNON:2026-09-11", 0.1, "cache"))
    assert "NOT THE BARS THE LIVE TRADER SAW" not in text
    assert "bars from: cache" in text


def test_the_source_choices_are_the_two_that_exist():
    p = R.build_parser()
    assert p.parse_args([]).source == "cache"
    assert p.parse_args(["--source", "archive"]).source == "archive"


# --- times are ET, not UTC ----------------------------------------------------

def test_times_render_in_EASTERN_not_utc():
    """Trade.entry_time is str(a UTC Timestamp). The first --only run printed
    the TNON entry as "11:35" -- the right trade under a label four hours
    wrong, and indistinguishable from a wrong trade unless the reader noticed
    the offset. Every other time in this project is ET."""
    assert R.et_hhmm("2026-09-11 11:35:00+00:00") == "07:35"
    assert R.et_hhmm("2026-09-11 11:48:00+00:00") == "07:48"


def test_a_naive_timestamp_is_treated_as_UTC_not_as_local():
    """Guessing local here would shift every figure by the machine's offset,
    and Ben's machine is UTC+10."""
    assert R.et_hhmm("2026-09-11 11:35:00") == "07:35"


def test_the_report_labels_the_times_as_ET():
    class Full:
        entry_time = "2026-09-11 11:35:00+00:00"
        exit_time = "2026-09-11 11:48:00+00:00"
        entry_price, exit_price, qty = 7.49, 8.37, 100
        reason, bars_held = "trailing_stop", 13
        gross, commission, net = 88.31, 1.38, 86.93
    text = "\n".join(R.render_one(
        [{"symbol": "TNON", "date": "2026-09-11", "trades": [Full()]}],
        [], "floor_sole", "TNON:2026-09-11", 0.1))
    assert "07:35 ET" in text and "07:48 ET" in text


# --- the best refusal is not the refusal ---------------------------------------

def test_the_comparison_names_the_BEST_single_refusal_and_warns_about_it():
    """TNON 09-11 has three floor_sole bars: +82.67, (39.84) and (10.82).
    Quoting the winner alone is the same selection the population test exists
    to defeat, applied to one day instead of one dataset."""
    def tr(h, m, net):
        class X:
            entry_time = f"2026-09-11 {h:02d}:{m:02d}:00+00:00"
            exit_time = f"2026-09-11 {h:02d}:{m + 5:02d}:00+00:00"
            entry_price, exit_price, qty = 7.0, 7.5, 100
            reason, bars_held = "trailing_stop", 5
            gross, commission = net + 1.4, 1.4
        X.net = net
        return X()
    ts = [tr(12, 4, -35.58), tr(11, 35, 86.93), tr(16, 31, -6.56)]
    ct = [tr(13, 3, 67.38)]
    text = "\n".join(R.render_one(
        [{"symbol": "TNON", "date": "2026-09-11", "trades": ts}],
        [{"symbol": "TNON", "date": "2026-09-11", "trades": ct}],
        "floor_sole", "TNON:2026-09-11", 0.1))
    assert "the BEST single refusal" in text
    assert "would have taken ALL of the refused bars" in text
    assert "made LESS than the rule made" in text


def test_no_best_line_when_there_is_only_one_refusal():
    class Full:
        entry_time = "2026-09-11 11:35:00+00:00"
        exit_time = "2026-09-11 11:48:00+00:00"
        entry_price, exit_price, qty = 7.49, 8.37, 100
        reason, bars_held = "trailing_stop", 13
        gross, commission, net = 88.31, 1.38, 86.93
    text = "\n".join(R.render_one(
        [{"symbol": "TNON", "date": "2026-09-11", "trades": [Full()]}],
        [], "floor_sole", "TNON:2026-09-11", 0.1))
    assert "the BEST single refusal" not in text
