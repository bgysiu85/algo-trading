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
    assert "med MFE to close" in o
    assert "500.00" in o
    assert "not cut short" in o and "no exit" in o


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
