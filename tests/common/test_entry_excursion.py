#!/usr/bin/env python3
"""How far price moves in our favour after entry.

The module exists to settle one disagreement, so the properties that carry it
are the ones that decide the verdict:

1. **The entry bar is excluded.** Within a bar, OHLCV cannot say whether the
   high came before or after the fill. Including it would credit the entry with
   a move that had already happened, in the direction that makes the entry look
   good -- which is the direction that ends the argument prematurely.
2. **Per-share and per-trade figures are never compared.** $4.26 is a round trip
   on 100 shares. Reading a $0.41/share excursion against it understates by a
   hundred times.
3. **The verdict is pre-registered and applied without looking.** Both branches
   are reachable, and the middle refuses.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import entry_excursion as E

ET = ZoneInfo("America/New_York")
D = date(2026, 3, 2)


def frame(closes, highs=None, lows=None):
    b = pd.Timestamp(datetime.combine(D, dtime(4, 0), tzinfo=ET))
    idx = pd.DatetimeIndex([(b + timedelta(minutes=i)).tz_convert("UTC")
                            for i in range(len(closes))])
    return pd.DataFrame(
        {"symbol": "AAA", "open": closes, "close": closes,
         "high": highs if highs is not None else closes,
         "low": lows if lows is not None else closes,
         "volume": [1000.0] * len(closes)}, index=idx)


def trade(df, i, j, entry, exit_px, net=0.0, qty=100):
    return SimpleNamespace(symbol="AAA", date=D.isoformat(),
                           entry_time=df.index[i].isoformat(),
                           exit_time=df.index[j].isoformat(),
                           entry_price=entry, exit_price=exit_px,
                           qty=qty, net=net, bars_held=j - i)


# --- 1. the entry bar ---------------------------------------------------------

def test_the_entry_bars_own_high_is_not_counted():
    """A spike ON the entry bar had already happened when the decision was
    made. Counting it credits the entry with a move it did not catch, in the
    direction that would end this argument early."""
    df = frame([10.0, 10.0, 10.0], highs=[99.0, 10.0, 10.0])
    m = E.measure(df, trade(df, 0, 2, 10.0, 10.0))
    assert m["mfe_in"] == pytest.approx(0.0)


def test_the_exit_bar_is_inside_the_trade():
    """Price traded at that bar while the position was still open, so its high
    was reachable. Excluding it would understate every trade by one bar."""
    df = frame([10.0, 10.0, 10.0], highs=[10.0, 10.0, 11.0])
    m = E.measure(df, trade(df, 0, 2, 10.0, 10.0))
    assert m["mfe_in"] == pytest.approx(100.0)   # $1/share x 100


def test_a_trade_that_exits_on_the_next_bar_measures_that_one_bar():
    df = frame([10.0, 10.0], highs=[10.0, 10.5])
    m = E.measure(df, trade(df, 0, 1, 10.0, 10.0))
    assert m["mfe_in"] == pytest.approx(50.0)


# --- 2. the two windows -------------------------------------------------------

def test_in_trade_and_to_session_end_are_different_numbers():
    """Conflating them is the trap: the session-end window includes everything
    that happened after we were already out."""
    df = frame([10.0] * 5, highs=[10.0, 10.5, 10.0, 10.0, 20.0])
    m = E.measure(df, trade(df, 0, 2, 10.0, 10.0))
    assert m["mfe_in"] == pytest.approx(50.0)
    assert m["mfe_end"] == pytest.approx(1000.0)
    assert m["mfe_end"] > m["mfe_in"]


def test_the_adverse_side_is_measured_too():
    """MFE alone rewards a longer hold for being longer. MAE is the offset."""
    df = frame([10.0] * 4, highs=[10.0, 10.2, 10.0, 10.0],
               lows=[10.0, 9.0, 10.0, 10.0])
    m = E.measure(df, trade(df, 0, 3, 10.0, 10.0))
    assert m["mae_in"] == pytest.approx(100.0)
    assert m["mfe_in"] == pytest.approx(20.0)


# --- 3. locating the bar ------------------------------------------------------

def test_a_stamp_absent_from_the_frame_is_refused_not_snapped():
    """searchsorted on a missing stamp returns a perfectly plausible index, so
    a frame mismatch would silently measure a different bar's excursion."""
    df = frame([10.0] * 3)
    # 30 seconds into the first bar: between two real stamps, so searchsorted
    # hands back index 1 -- a plausible answer for a bar that does not exist.
    gap = (df.index[0] + pd.Timedelta(seconds=30)).isoformat()
    assert df.index.searchsorted(pd.Timestamp(gap)) == 1
    assert E.locate(df.index, gap) is None
    t = trade(df, 0, 2, 10.0, 10.0)
    t.exit_time = gap
    assert E.measure(df, t) is None


def test_a_present_stamp_returns_its_own_position():
    df = frame([10.0] * 5)
    for i in range(5):
        assert E.locate(df.index, df.index[i].isoformat()) == i


# --- 4. units -----------------------------------------------------------------

def test_dollar_figures_are_on_the_traded_size_not_per_share():
    """$4.26 is a round trip on 100 shares. A per-share excursion read against
    it is out by a factor of a hundred, in whichever direction hurts."""
    df = frame([10.0] * 3, highs=[10.0, 11.0, 10.0])
    m = E.measure(df, trade(df, 0, 2, 10.0, 10.0, qty=100))
    assert m["mfe_in"] == pytest.approx(100.0)
    assert m["mfe_in_share"] == pytest.approx(1.0)
    assert m["mfe_in"] == pytest.approx(m["mfe_in_share"] * 100)


def test_the_report_states_the_per_share_friction_beside_the_per_trade_one():
    rows = [{"symbol": "A", "date": "2026-03-02", "net": 1.0, "bars_held": 3,
             "mfe_in": 50.0, "mae_in": 10.0, "mfe_end": 60.0,
             "mfe_in_share": 0.5, "mae_in_share": 0.1, "entry_price": 10.0,
             "qty": 100}]
    o = "\n".join(E.render(rows, "mcl", 10, 100, "2026-03-02", 1.0, 1))
    assert "0.0426" in o
    assert "never compared without being put on the same footing" in o


# --- 5. the pre-registered verdict -------------------------------------------

def rows_with(mfes, nets=None):
    nets = nets or [0.0] * len(mfes)
    return [{"symbol": f"S{i}", "date": "2026-03-02", "net": n,
             "bars_held": 3, "mfe_in": m, "mae_in": 0.0, "mfe_end": m,
             "mfe_in_share": m / 100, "mae_in_share": 0.0,
             "entry_price": 10.0, "qty": 100}
            for i, (m, n) in enumerate(zip(mfes, nets))]


def test_plenty_of_room_says_the_exit_is_worth_attacking():
    v, _why = E.verdict(rows_with([20.0] * 100), 4.26)
    assert v == "THE EXIT IS WORTH ATTACKING"


def test_most_trades_never_covering_friction_says_the_entry_is_the_problem():
    v, why = E.verdict(rows_with([1.0] * 80 + [50.0] * 20), 4.26)
    assert v == "THE ENTRY IS THE PROBLEM"
    assert "No exit rule reaches this" in "\n".join(why)


def test_a_median_below_friction_says_the_entry_is_the_problem_too():
    """Even with a minority of huge excursions, if the MEDIAN trade's best
    moment is under its own round trip, a perfect exit does not rescue it."""
    v, _ = E.verdict(rows_with([3.0] * 51 + [500.0] * 49), 4.26)
    assert v == "THE ENTRY IS THE PROBLEM"


def test_the_middle_refuses_rather_than_leaning():
    """Between the bounds the report must not pick the reading that suits
    whatever work comes next."""
    v, why = E.verdict(rows_with([6.0] * 100), 4.26)
    assert v == "NO VERDICT"
    assert "refuses rather than" in "\n".join(why)


def test_both_verdict_branches_are_reachable_from_the_same_code_path():
    """A verdict only one branch can reach is a constant wearing a decision's
    clothes."""
    got = {E.verdict(rows_with(m), 4.26)[0]
           for m in ([20.0] * 100, [1.0] * 100, [6.0] * 100)}
    assert got == {"THE EXIT IS WORTH ATTACKING", "THE ENTRY IS THE PROBLEM",
                   "NO VERDICT"}


def test_never_covered_counts_at_or_below_the_friction_not_strictly_below():
    """A trade whose peak exactly equals its round trip nets zero at best. It
    could not have been PROFITABLE, which is what the count claims."""
    assert E.never_covered(rows_with([4.26, 4.27]), 4.26) == 1


# --- 6. the ceiling is not a strategy ----------------------------------------

def test_the_perfect_exit_bound_is_labelled_as_a_bound():
    rows = rows_with([50.0] * 40, nets=[-10.0] * 40)
    o = "\n".join(E.render(rows, "mcl", 10, 100, "2026-03-02", 1.0, 1))
    assert "AN UPPER BOUND, NOT A RULE" in o
    assert "frees the slot" in o
    assert "nothing reaches this number" in o


def test_the_bound_is_reported_beside_the_actual_not_alone():
    """The bound alone is the number that invites being quoted."""
    pe = E.perfect_exit(rows_with([50.0] * 10, nets=[-10.0] * 10), 4.26)
    assert pe["actual_per"] == pytest.approx(-14.26)
    assert pe["ideal_per"] == pytest.approx(45.74)


def test_drop_top_5_is_n_a_rather_than_zero_on_too_few_symbols():
    """With DROP or fewer symbols the drop removes everything and prints 0.00,
    which is indistinguishable from a result whose top names cancelled."""
    rows = rows_with([50.0] * 3)
    o = "\n".join(E.render(rows, "mcl", 10, 100, "2026-03-02", 1.0, 1))
    assert "n/a" in o


# --- 7. the lower-bound caveat travels ---------------------------------------

def test_the_report_says_every_figure_is_a_lower_bound():
    o = "\n".join(E.render(rows_with([50.0] * 40), "mcl", 10, 100,
                           "2026-03-02", 1.0, 1))
    assert "LOWER BOUND" in o
    assert "entry bar is excluded" in o


def test_a_sign_disagreement_between_halves_refuses_the_figure():
    rows = (rows_with([-5.0] * 30) + rows_with([50.0] * 30))
    for r in rows[:30]:
        r["date"] = "2026-03-01"
    o = "\n".join(E.render(rows, "mcl", 10, 100, "2026-03-02", 1.0, 1))
    assert "THE HALVES DISAGREE IN SIGN" in o


def test_no_trades_renders_without_a_verdict():
    o = "\n".join(E.render([], "mcl", 10, 100, "", 1.0, 1))
    assert "NO TRADES" in o
    assert "THE EXIT IS WORTH ATTACKING" not in o
    assert "THE ENTRY IS THE PROBLEM" not in o


# --- 8. the frame must match pit_strategy's ----------------------------------

def test_the_report_says_how_many_trades_could_not_be_located():
    """The first version measured 3,521 trades against pit_strategy's 3,955 and
    said nothing. A silent drop is how a biased subsample gets reported as the
    whole book."""
    o = "\n".join(E.render(rows_with([50.0] * 90), "mcl", 10, 100,
                           "2026-03-02", 1.0, 1, made=100))
    assert "10 of 100 trades (10.0%) COULD NOT BE LOCATED" in o
    assert "Read nothing below until that is zero" in o


def test_a_clean_run_carries_no_drop_banner():
    o = "\n".join(E.render(rows_with([50.0] * 100), "mcl", 10, 100,
                           "2026-03-02", 1.0, 1, made=100))
    assert "COULD NOT BE LOCATED" not in o


def test_the_warm_up_is_stated_and_matches_pit_strategy():
    """MACD is an EMA with unbounded memory, so a frame without the prior slice
    is a different population, not the same one measured differently. The first
    version read one day's slice under a report saying 'same warm-up as
    pit_strategy'."""
    from common.pit_strategy import WARMUP_SESSIONS
    o = "\n".join(E.render(rows_with([50.0] * 40), "mcl", 10, 100,
                           "2026-03-02", 1.0, 1))
    assert f"{WARMUP_SESSIONS} session(s) of warm-up" in o
    assert "unbounded memory" in o
    assert E.WARMUP_SESSIONS == WARMUP_SESSIONS


def test_sessions_short_of_warm_up_are_counted_not_hidden():
    o = "\n".join(E.render(rows_with([50.0] * 40), "mcl", 10, 100,
                           "2026-03-02", 1.0, 1, warm_short=3))
    assert "3 session(s) ran with less warm-up than asked" in o


# --- 9. which extreme came first ---------------------------------------------

def test_extremes_agree_with_the_values_excursions_returns():
    """Two implementations of one window is how an off-by-one becomes a
    finding. The positions must point at the values the other function found."""
    import random
    from common.dip_entry import excursions
    rng = random.Random(11)
    for _ in range(60):
        n = rng.randint(3, 40)
        hi = [round(rng.uniform(5, 15), 2) for _ in range(n)]
        lo = [round(h - rng.uniform(0.1, 3.0), 2) for h in hi]
        df = frame([10.0] * n, highs=hi, lows=lo)
        i = rng.randint(0, n - 2)
        end = rng.randint(i + 2, n)
        entry = 10.0
        mfe, mae = excursions(df, i, entry, end=end)
        hi_i, lo_i = E.extremes(df, i, end)
        assert df["high"].iloc[hi_i] == pytest.approx(mfe * entry + entry)
        assert df["low"].iloc[lo_i] == pytest.approx(entry - mae * entry)


def test_a_window_with_no_bars_after_entry_returns_no_positions():
    df = frame([10.0, 10.0])
    assert E.extremes(df, 0, 1) == (-1, -1)


def test_adverse_first_is_true_when_the_low_precedes_the_high():
    df = frame([10.0] * 5, highs=[10.0, 10.0, 10.0, 10.0, 12.0],
               lows=[10.0, 9.0, 10.0, 10.0, 10.0])
    m = E.measure(df, trade(df, 0, 4, 10.0, 10.0))
    assert m["mae_i"] == 1 and m["mfe_i"] == 4
    assert m["adverse_first"] is True


def test_adverse_first_is_false_when_the_high_precedes_the_low():
    df = frame([10.0] * 5, highs=[10.0, 12.0, 10.0, 10.0, 10.0],
               lows=[10.0, 10.0, 10.0, 10.0, 9.0])
    m = E.measure(df, trade(df, 0, 4, 10.0, 10.0))
    assert m["adverse_first"] is False


def test_the_order_section_refuses_the_comparison_the_percentiles_invite():
    """'The median trade goes $16 against and $14 for' describes no trade that
    exists -- those are two different trades. The report has to say so where
    the two rows sit next to each other."""
    rows = rows_with([50.0] * 20)
    for k, r in enumerate(rows):
        r.update(mfe_i=5, mae_i=1 if k < 15 else 9,
                 adverse_first=k < 15)
    o = "\n".join(E.order_section(rows, 4.26))
    assert "Per trade, not per percentile" in o
    assert "cannot" in o and "be read against each other" in o
    assert "75.0% of trades were at their worst BEFORE they were at their best"\
        in o


def test_both_orderings_are_reported_with_their_own_medians():
    rows = rows_with([10.0] * 10 + [90.0] * 10)
    for k, r in enumerate(rows):
        r.update(mfe_i=5, mae_i=1 if k < 10 else 9, adverse_first=k < 10)
    o = "\n".join(E.order_section(rows, 4.26))
    assert "drawdown first" in o and "move first" in o
    assert "10.00" in o and "90.00" in o


def test_the_order_section_does_not_claim_to_settle_entry_versus_exit():
    rows = rows_with([50.0] * 10)
    for r in rows:
        r.update(mfe_i=5, mae_i=1, adverse_first=True)
    o = "\n".join(E.order_section(rows, 4.26))
    assert "this report does not settle which" in o


def test_the_split_reports_the_move_that_continued_after_the_exit():
    """Without it a small in-trade MFE is ambiguous between 'the move was
    small' and 'the trail cut us out of a move that continued'. Those are
    opposite findings -- an entry problem and an exit problem -- and they render
    as the same number."""
    rows = rows_with([10.0] * 10)
    for k, r in enumerate(rows):
        r.update(mfe_i=5, mae_i=1 if k < 5 else 9, adverse_first=k < 5,
                 mfe_end=10.0 if k < 5 else 500.0)
    o = "\n".join(E.order_section(rows, 4.26))
    assert "to close" in o
    assert "500.00" in o
    assert "no exit reaches what was never there" in o


# --- 10. the double must not be more permissive than the real thing ----------

@pytest.mark.parametrize("mod", ["mcl", "mc5"])
def test_measure_reads_a_REAL_trade_from_each_engine(mod):
    """`portal_bridge_handover_20260914.md` §9: a test double more permissive
    than the class it stands in for hides defects completely -- an ordinary
    object accepts any attribute you set on it, so the fakes agreed with each
    other and disagreed with production.

    Every other test here builds a SimpleNamespace. This one builds the engine's
    own Trade, so a renamed or removed field fails here instead of at runtime.
    """
    import importlib
    M = importlib.import_module(f"strategy.{mod}.{mod}")
    df = frame([10.0] * 4, highs=[10.0, 10.0, 11.0, 10.0],
               lows=[10.0, 9.5, 10.0, 10.0])
    t = M.Trade(symbol="AAA", date=D.isoformat(),
                entry_time=df.index[0].isoformat(),
                exit_time=df.index[3].isoformat(),
                entry_price=10.0, exit_price=10.0, qty=100,
                reason="trailing_stop", bars_held=3,
                gross=0.0, commission=0.0, net=0.0)
    m = E.measure(df, t)
    assert m is not None, f"{mod}.Trade no longer carries what measure() reads"
    assert m["mfe_in"] == pytest.approx(100.0)
    assert m["mae_in"] == pytest.approx(50.0)
    assert m["adverse_first"] is True


def test_the_fields_measure_reads_all_exist_on_the_real_trade():
    """Named explicitly, so a rename shows up as this test rather than as a
    silently smaller book."""
    import dataclasses
    from strategy.mcl import mcl as M
    have = {f.name for f in dataclasses.fields(M.Trade)}
    for field in ("symbol", "date", "entry_time", "exit_time", "entry_price",
                  "qty", "net", "bars_held"):
        assert field in have, f"measure() reads .{field} and Trade lost it"


# --- 11. the fixed horizon, against the window-length confound ---------------

def test_mfe_to_close_depends_on_when_the_trade_ended_and_the_fixed_one_does_not():
    """`to close` runs to the session's last bar, so a trade stopped out early
    is credited with more tape than one stopped out late -- and the group that
    exits soonest collects the largest figure for it. The fixed horizon gives
    every trade the same window from its own entry."""
    n = E.FIXED_HORIZON + 20
    highs = [10.0] * n
    highs[E.FIXED_HORIZON + 10] = 50.0     # a spike beyond the fixed horizon
    df = frame([10.0] * n, highs=highs)
    early = E.measure(df, trade(df, 0, 2, 10.0, 10.0))
    late = E.measure(df, trade(df, 0, n - 2, 10.0, 10.0))
    # both see the spike in `to close`, because both run to the last bar
    assert early["mfe_end"] == pytest.approx(4000.0)
    assert late["mfe_end"] == pytest.approx(4000.0)
    # neither sees it in the fixed window, which stops at the same bar for both
    assert early["mfe_fix"] == pytest.approx(0.0)
    assert late["mfe_fix"] == pytest.approx(0.0)


def test_the_fixed_horizon_sees_a_move_inside_its_own_window():
    n = E.FIXED_HORIZON + 20
    highs = [10.0] * n
    highs[5] = 12.0
    df = frame([10.0] * n, highs=highs)
    m = E.measure(df, trade(df, 0, 2, 10.0, 10.0))
    assert m["mfe_in"] == pytest.approx(0.0)      # the spike is after the exit
    assert m["mfe_fix"] == pytest.approx(200.0)   # and inside the fixed window


def test_bars_left_records_how_much_session_each_trade_was_handed():
    df = frame([10.0] * 20)
    assert E.measure(df, trade(df, 0, 2, 10.0, 10.0))["bars_left"] == 17
    assert E.measure(df, trade(df, 0, 18, 10.0, 10.0))["bars_left"] == 1


def test_the_table_tells_the_reader_to_use_the_fixed_column():
    rows = rows_with([10.0] * 10)
    for k, r in enumerate(rows):
        r.update(mfe_i=5, mae_i=1 if k < 5 else 9, adverse_first=k < 5,
                 mfe_end=500.0, mfe_fix=20.0, bars_left=200 if k < 5 else 3)
    o = "\n".join(E.order_section(rows, 4.26))
    assert f"READ THE +{E.FIXED_HORIZON}-BAR COLUMN, NOT `to close`" in o
    assert "the group that exits soonest is" in o
    assert "bars left" in o


def test_the_fixed_horizon_is_registered_not_tuned():
    """A horizon chosen after seeing the split is a parameter fitted to the
    answer. It is a module constant with its reasoning written beside it."""
    import inspect
    src = inspect.getsource(E)
    i = src.index("FIXED_HORIZON = ")
    assert "registered here rather" in src[:i]
    assert "p90" in src[:i]


# --- 12. can a stop separate the two groups at all ---------------------------

def grp(maes):
    return [{"symbol": f"S{i}", "date": "2026-03-02", "net": 0.0,
             "bars_held": 3, "mfe_in": 50.0, "mae_in": m, "mfe_end": 50.0,
             "mfe_fix": 50.0, "bars_left": 10, "mfe_in_share": 0.5,
             "mae_in_share": m / 100, "entry_price": 10.0, "qty": 100,
             "mfe_i": 5, "mae_i": 1, "adverse_first": True}
            for i, m in enumerate(maes)]


def test_the_scan_reports_both_groups_at_every_level():
    o = "\n".join(E.stop_scan(grp([5.0] * 10), grp([30.0] * 10)))
    assert "IF A HARD STOP HAD SAT AT EACH LEVEL" in o
    for lvl in ("$      5", "$     10", "$     20", "$     25"):
        assert lvl in o


def test_a_clean_separation_shows_a_ratio_far_above_one():
    """Winners all draw down $5, losers all $30. A stop at $10 catches every
    loser and no winner."""
    o = "\n".join(E.stop_scan(grp([5.0] * 100), grp([30.0] * 100)))
    line = [l for l in o.splitlines() if l.lstrip().startswith("$     10")][0]
    assert "0.0%" in line and "100.0%" in line


def test_no_separation_shows_a_ratio_near_one():
    """Both groups drawing down the same amount. A stop cannot tell them apart
    and no width is the right width -- which the report says in those words."""
    o = "\n".join(E.stop_scan(grp([12.0] * 100), grp([12.0] * 100)))
    line = [l for l in o.splitlines() if l.lstrip().startswith("$     10")][0]
    assert "1.00" in line
    assert "width is the right width" in " ".join(o.split())


def test_the_scan_says_it_is_a_bound_and_not_a_backtest():
    """A real stop ends the position, so nothing after it happens. Reading
    these rows as a P/L would be reading a counterfactual that was never run."""
    o = "\n".join(E.stop_scan(grp([5.0] * 10), grp([30.0] * 10)))
    # the phrase wraps across lines in the rendered report
    flat = " ".join(o.split())
    assert "NOT A BACKTEST" in flat
    assert "A real stop also ends the position" in flat


def test_an_empty_group_produces_no_scan_rather_than_a_divide_by_zero():
    assert E.stop_scan([], grp([30.0] * 10)) == []
    assert E.stop_scan(grp([5.0] * 10), []) == []


def test_the_report_prints_the_drawdown_distribution_not_just_the_median():
    """The two medians invite a stop between them. A median cannot support
    that: if the winners' tail reaches into the losers' body, a stop there kills
    winners faster than it saves losers, and the medians look identical either
    way."""
    rows = grp([5.0] * 50)
    for r in rows[25:]:
        r["adverse_first"] = False
        r["mae_i"], r["mfe_i"] = 9, 5
        r["mae_in"] = 30.0
    o = "\n".join(E.order_section(rows, 4.26))
    assert "THE DRAWDOWN EACH GROUP HAS TO SURVIVE" in o
    assert "p90" in o and "p95" in o
    assert "the overlap between the two rows is the whole" in o


# --- 13. the book estimate, with its assumptions charged ---------------------

def test_the_stop_book_charges_friction_and_measured_slippage():
    """A stop narrower than the slippage must not look free. Live trailing
    stops fill worse than reference by a measured amount per share, and a
    stopped trade pays it."""
    from common.scale_grid import SLIP_PER_SHARE
    # everyone is stopped: mae above the level on every row
    w = grp([99.0] * 10)
    l = grp([99.0] * 10)
    got = E.stop_book(w, l, 5.0)
    assert got == pytest.approx(-5.0 - 4.26 - SLIP_PER_SHARE * 100)


def test_a_stop_nobody_reaches_leaves_the_book_where_it_was():
    w = grp([1.0] * 10)
    for r in w:
        r["net"] = 20.0
    l = grp([1.0] * 10)
    for r in l:
        r["net"] = -10.0
    got = E.stop_book(w, l, 50.0)
    assert got == pytest.approx((20.0 - 4.26 + (-10.0 - 4.26)) / 2)


def test_the_estimate_is_labelled_and_its_assumptions_named():
    """It flatters the stop in two ways and has to say both: survivors are
    selected for small drawdowns, and a real stop ends the position."""
    o = " ".join("\n".join(E.stop_scan(grp([5.0] * 10),
                                       grp([30.0] * 10))).split())
    assert "IS AN ESTIMATE, NOT A BACKTEST" in o
    assert "survivors are selected for small drawdowns" in o
    assert "A real stop also ends the position" in o
    assert "It sizes the question; it does not answer it." in o


def test_the_scan_states_the_stop_in_the_unit_slippage_is_measured_in():
    """$5 on 100 shares is 5 cents a share, which is the same order as the
    measured fill difference. Printing only the dollar figure hides that."""
    o = "\n".join(E.stop_scan(grp([5.0] * 10), grp([30.0] * 10)))
    assert "per share" in o
    assert "0.0500" in o


def test_the_book_column_is_reported_against_the_current_book():
    """A level that improves nothing must read as zero change rather than as a
    number the reader has to subtract themselves."""
    w, l = grp([1.0] * 10), grp([1.0] * 10)
    o = "\n".join(E.stop_scan(w, l))
    assert "vs now" in o
