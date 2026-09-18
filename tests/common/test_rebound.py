#!/usr/bin/env python3
"""H-R1: the rebound census, and the four ways it could quietly lie.

REGISTERED_rebound.md. A census has no verdict to get wrong, which removes the
usual failure mode and leaves subtler ones:

  - "came back" must mean came back FROM THE DIP. A high that happened before
    the position ever went under is not a recovery from it, and counting it
    would turn every trade that rose then fell into a rebound;
  - the §2.3 cut is selected by the strategies' OWN exit label. A rename in
    either strategy empties the census's headline block, and an empty block
    that prints "no trades" is indistinguishable from a real finding;
  - the boundary check must be scored. A window that runs past where the engine
    stopped trading corrupts every post-exit number in §2.2 and shows up
    nowhere else;
  - and the report must stay a census: percent excursions are the subject
    matter, strategy P&L and verdict vocabulary are barred (§1).

The high side is pinned against `mfe_exit.excursion` on the same trade, so the
two modules cannot disagree about where a trade went.
"""
from __future__ import annotations

import math
import re

import pandas as pd
import pytest

from common import mfe_exit as M
from common import rebound as R


# --- fixtures ----------------------------------------------------------------

ET = R.ET


def bars(rows, start="2026-09-11 05:00", freq="1min"):
    """rows: (open, high, low, close) per bar, indexed in ET."""
    idx = pd.date_range(pd.Timestamp(start, tz=ET), periods=len(rows), freq=freq)
    return pd.DataFrame(rows, index=idx,
                        columns=["open", "high", "low", "close"])


class T:
    """A Trade, in the shape `excursion` reads it.

    Deliberately NOT a dict. `entry_px`/`exit_px` are what gate_study.trade_row
    puts in ITS dict and `entry_price`/`exit_price` are the object's own
    attributes; a fixture built from dicts is what let that confusion reach a
    six-hour run in chase_gate. See test_trade_attributes_exist_on_the_object.
    """

    def __init__(self, b, entry_i, exit_i, entry_px, exit_px, reason="trailing_stop",
                 net=-9.0, symbol="AAA", date="2026-09-11"):
        self.entry_time = b.index[entry_i]
        self.exit_time = b.index[exit_i]
        self.entry_price = entry_px
        self.exit_price = exit_px
        self.qty = 100
        self.reason = reason
        self.bars_held = exit_i - entry_i
        self.gross = net
        self.commission = 0.0
        self.net = net
        self.symbol = symbol
        self.date = date


# --- §2.1 inside the trade ----------------------------------------------------

def test_a_high_before_the_dip_is_not_a_recovery_from_it():
    """The mistake that would inflate the headline. This trade goes UP first,
    then under entry, and never returns -- exactly the path Ben described
    watching. Read carelessly (max high over the whole trade) it reports a
    rebound."""
    b = bars([(10, 10, 10, 10),      # entry bar
              (10, 12, 10, 12),      # up first
              (12, 12, 9, 9),        # then under entry
              (9, 9.5, 8, 8)])       # and never back
    r = R.excursion(b, T(b, 0, 3, entry_px=10.0, exit_px=8.0))
    assert r["went_under"] is True
    assert r["back_to_entry"] is False, "a pre-dip high was counted as a rebound"
    assert r["back_to_profit"] is False
    assert math.isnan(r["bars_to_recover"])
    assert r["mae_pct"] == pytest.approx(-20.0)   # low 8 against entry 10


def test_back_to_entry_is_not_back_to_a_profit():
    """The distinction §2.1 exists for: touching entry again is not making
    money, and the gap between them is one round trip of friction."""
    f = R.FRICTION_PER_SHARE
    b = bars([(10, 10, 10, 10),
              (10, 10, 9, 9),                       # under
              (9, 10 + f / 2, 9, 10)])              # back over entry, not over friction
    r = R.excursion(b, T(b, 0, 2, 10.0, 10.0))
    assert r["went_under"] is True
    assert r["back_to_entry"] is True
    assert r["back_to_profit"] is False, "a touch of entry was scored as a profit"
    assert r["bars_to_recover"] == 1


def test_a_trade_that_never_goes_under_reports_no_recovery_rather_than_a_failed_one():
    b = bars([(10, 10, 10, 10), (10, 12, 10.5, 12), (12, 13, 11, 13)])
    r = R.excursion(b, T(b, 0, 2, 10.0, 13.0, net=+40.0))
    assert r["went_under"] is False
    assert r["back_to_entry"] is False and r["back_to_profit"] is False
    assert r["won"] is True
    # It still has an MAE -- the worst it did was 10.5, above entry.
    assert r["mae_pct"] == pytest.approx(5.0)


def test_the_entry_bar_is_excluded_on_both_sides():
    """The convention mfe_exit set: the fill happens at the entry bar's close,
    so that bar's own low already happened and is not adverse excursion the
    position lived through."""
    b = bars([(10, 10, 1.0, 10),       # a huge low ON the entry bar
              (10, 11, 10, 11)])
    r = R.excursion(b, T(b, 0, 1, 10.0, 11.0, net=+80.0))
    assert r["went_under"] is False, "the entry bar's own low was counted"
    assert r["mae_pct"] == pytest.approx(0.0)


# --- §2.2 after the exit ------------------------------------------------------

def test_the_low_after_the_exit_is_measured_and_it_is_the_half_that_matters():
    """mfe_exit measures only the high. A stop that fired before a further fall
    SAVED money, and nothing in this project could say so before this."""
    b = bars([(10, 10, 10, 10),
              (10, 10, 9.5, 9.5),          # stopped out
              (9.5, 9.6, 8.0, 8.1),        # and it kept going
              (8.1, 8.2, 7.0, 7.2)])
    r = R.excursion(b, T(b, 0, 1, 10.0, 9.5))
    assert r["post_bars"] == 2
    assert r["post_lo_pct"] == pytest.approx(-30.0)         # low 7.0 vs entry 10
    assert r["post_lo_vs_exit"] == pytest.approx(-26.3157894, abs=1e-5)
    assert r["post_hi_pct"] == pytest.approx(-4.0)          # high 9.6 vs entry 10
    assert r["recovered_entry"] is False
    assert math.isnan(r["bars_to_entry"])


def test_a_recovery_after_the_exit_is_counted_with_how_long_it_took():
    b = bars([(10, 10, 10, 10),
              (10, 10, 9.5, 9.5),          # stopped out at -5%
              (9.5, 9.8, 9.4, 9.7),
              (9.7, 10.5, 9.6, 10.4)])     # back over entry, two bars later
    r = R.excursion(b, T(b, 0, 1, 10.0, 9.5))
    assert r["recovered_entry"] is True
    assert r["recovered_profit"] is True
    assert r["bars_to_entry"] == 2
    assert r["post_hi_vs_exit"] == pytest.approx(10.5 / 9.5 * 100 - 100)


def test_a_window_close_exit_has_nothing_after_it_and_says_zero_not_nan():
    b = bars([(10, 10, 10, 10), (10, 11, 9, 9.5)])
    r = R.excursion(b, T(b, 0, 1, 10.0, 9.5, reason="window_close"))
    assert r["post_bars"] == 0
    assert r["recovered_entry"] is False
    assert math.isnan(r["post_hi_pct"]) and math.isnan(r["post_lo_pct"])


def test_a_trade_with_no_path_at_all_is_excluded_rather_than_scored_as_flat():
    """Entered and exited on the session's last bar. A row of zeros here would
    read as 'it never moved', which is the one thing it does not say."""
    b = bars([(10, 10, 10, 10), (10, 11, 9, 10)])
    assert R.excursion(b, T(b, 1, 1, 10.0, 10.0)) is None


# --- the agreement with mfe_exit ----------------------------------------------

def test_the_high_side_agrees_with_mfe_exit_on_the_same_trade():
    """One implementation of 'where did this trade go'. mfe_exit's `after_px`
    is the highest price after the exit bar; this module's `post_hi_pct` is the
    same quantity as a percentage of entry. If they ever disagree, two studies
    are describing two different tapes."""
    b = bars([(10, 10, 10, 10),
              (10, 10.2, 9.1, 9.3),
              (9.3, 11.4, 9.2, 11.0),
              (11.0, 11.1, 10.2, 10.4)])
    t = T(b, 0, 1, 10.0, 9.3)
    mine = R.excursion(b, t)
    theirs = M.excursion(b, t)
    assert theirs["after_px"] == pytest.approx(11.4)
    assert mine["post_hi_pct"] == pytest.approx(
        (theirs["after_px"] / theirs["entry_px"] - 1.0) * 100.0)
    assert mine["post_hi_vs_exit"] == pytest.approx(
        (theirs["after_px"] / theirs["exit_px"] - 1.0) * 100.0)


def test_trade_attributes_exist_on_the_object_not_only_in_a_dict():
    """`entry_px`/`exit_px` are gate_study.trade_row's DICT keys; the Trade
    object carries `entry_price`/`exit_price`. Reaching for the wrong pair is
    what crashed chase_gate's smoke run after the fixtures, built from dicts,
    all passed."""
    from common.harness import Trade
    names = {f.name for f in Trade.__dataclass_fields__.values()}
    for attr in ("entry_price", "exit_price", "entry_time", "exit_time",
                 "reason", "bars_held", "net", "symbol", "date"):
        assert attr in names, f"excursion reads t.{attr}, which Trade lacks"
    assert "entry_px" not in names and "exit_px" not in names


# --- the §2.3 cut, and the rename that would empty it -------------------------

def test_both_strategies_still_label_the_trailing_stop_the_way_the_cut_selects():
    """THE TEST THAT MATTERS MOST. §2.3 is the census's entire reason for
    existing, and it is selected by an exit label the strategies own. A rename
    in either module would empty the block silently -- it would print 'no
    trades' and read like a finding."""
    from pathlib import Path
    root = Path(R.__file__).resolve().parents[1]
    for mod in ("strategy/mcl/mcl.py", "strategy/mc5/mc5.py"):
        src = (root / mod).read_text(encoding="utf-8")
        assert f'"{R.TRAIL_REASON}"' in src, \
            f"{mod} no longer emits {R.TRAIL_REASON!r}; §2.3 would be empty"
        assert f'"{R.CLOSE_REASON}"' in src, \
            f"{mod} no longer emits {R.CLOSE_REASON!r}; the boundary check dies"


def test_an_empty_section_two_three_shouts_instead_of_printing_no_trades():
    rows = [_row(reason="target", bars_held=4), _row(reason="target", bars_held=1)]
    text = "\n".join(_render(rows))
    assert "EMPTY" in text
    assert "measuring nothing" in text
    assert "contradicts H-P1" in text


def test_the_cut_takes_one_bar_trailing_stops_and_nothing_else():
    # `structure_stop` is the one that matters: MCL emits it, it is a DIFFERENT
    # exit, and any substring match on "stop" would sweep it into the cut and
    # quietly change what §2.3 is about.
    rows = [_row(reason="trailing_stop", bars_held=1, symbol="IN"),
            _row(reason="trailing_stop", bars_held=3, symbol="held-longer"),
            _row(reason="structure_stop", bars_held=1, symbol="other-stop"),
            _row(reason="window_close", bars_held=1, symbol="not-a-stop"),
            _row(reason="profit_floor", bars_held=1, symbol="not-a-stop-either")]
    text = "\n".join(_render(rows))
    # the block exists (so exactly one row reached it) and the three others did
    # not: each book's line prints its own count.
    assert "EMPTY" not in text
    block = text.split("THE ONE-BAR TRAILING-STOP EXITS")[1]
    assert "1 trades with tape left in the session" in block


# --- the grain: a 5-minute engine read on a 1-minute tape ---------------------

def test_a_five_minute_trade_does_not_count_its_own_exit_bar_as_after_the_exit():
    """THE DEFECT THE FIRST RUN SHIPPED, and the boundary check is what found
    it. MC5 acts on 5-minute bars, the tape is 1-minute, and a bar is stamped
    with its START -- so a trade stamped 09:25 fills at 09:29. Measured against
    the stamp, 09:26..09:29 read as 'after the exit' when they happened BEFORE
    the fill."""
    b = bars([(10, 10, 10, 10)] * 10)          # 05:00 .. 05:09
    # entry bar stamped 05:00 (fills 05:04), exit bar stamped 05:05 (fills 05:09)
    t = T(b, 0, 5, 10.0, 9.5)
    wrong = R.excursion(b, t, bar_minutes=1)
    right = R.excursion(b, t, bar_minutes=5)
    assert wrong["post_bars"] == 4, "05:06..05:09 counted as after the exit"
    assert right["post_bars"] == 0, "the exit bar's own minutes are not after it"


def test_the_one_minute_engine_is_bit_identical_to_no_offset_at_all():
    b = bars([(10, 10, 10, 10), (10, 11, 9, 9.5), (9.5, 9.6, 9.0, 9.1)])
    t = T(b, 0, 1, 10.0, 9.5)
    a, c = R.excursion(b, t), R.excursion(b, t, bar_minutes=1)
    assert a.keys() == c.keys()
    for k in a:                       # NaN != NaN, so compare it as a shape
        if isinstance(a[k], float) and math.isnan(a[k]):
            assert isinstance(c[k], float) and math.isnan(c[k]), k
        else:
            assert a[k] == c[k], k


def test_the_grain_is_scored_against_the_data_not_merely_asserted():
    """If the assumed grain is wrong the boundaries move by the wrong amount and
    every number shifts a few minutes with nothing looking amiss. A book assumed
    to trade N-minute bars must have EVERY entry land on an N-minute boundary."""
    ok = [_row(book="MC5", **{"entry_et": "05:05"}),
          _row(book="MC5", **{"entry_et": "05:10"})]
    text = "\n".join(_render(ok))
    assert "all 2 entries on a 5-minute boundary" in text
    assert "THE GRAIN IS WRONG" not in text

    bad = ok + [_row(book="MC5", symbol="ODD", **{"entry_et": "05:07"})]
    text = "\n".join(_render(bad))
    assert "THE GRAIN IS WRONG" in text
    assert "ODD" in text


def test_a_one_minute_book_is_not_required_to_sit_on_five_minute_boundaries():
    text = "\n".join(_render([_row(book="MCL", **{"entry_et": "05:07"})]))
    assert "MCL   assumed 1-minute bars   all 1 entries" in text
    assert "THE GRAIN IS WRONG" not in text


def test_run_day_actually_passes_the_grain_through():
    """THE WIRING GAP a unit test cannot see. `excursion` can take the grain
    correctly and `run_day` can still call it with the default, which is the
    shipped defect exactly -- and `run_day` needs the Databento archive, so no
    test here can drive it. Read the call instead."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(R.run_day))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "excursion"]
    assert calls, "run_day no longer calls excursion"
    for c in calls:
        assert len(c.args) >= 3 or any(k.arg == "bar_minutes" for k in c.keywords), \
            "run_day calls excursion without the engine's bar grain"


def test_the_engines_still_trade_the_bars_this_module_assumes():
    """The constant is a claim about two other modules. mc5 resamples to five
    minutes and mcl does not; if that ever changes, the offset is wrong and the
    numbers move quietly."""
    from strategy.mc5 import mc5 as M5
    from strategy.mcl import mcl as ML
    assert hasattr(M5, "to_5m"), "mc5 no longer resamples; BAR_MINUTES is stale"
    assert not hasattr(ML, "to_5m"), "mcl now resamples; BAR_MINUTES is stale"
    assert R.BAR_MINUTES == {"MCL": 1, "MC5": 5}


# --- the boundary check, scored -----------------------------------------------

def test_a_window_close_exit_with_bars_after_it_is_reported_as_a_window_bug():
    rows = [_row(reason="window_close", post_bars=0),
            _row(reason="window_close", post_bars=3, symbol="LATE")]
    text = "\n".join(_render(rows))
    assert "WINDOW MISMATCH" in text
    assert "LATE" in text
    assert "over too wide a window" in text


def test_a_clean_window_says_so_rather_than_saying_nothing():
    rows = [_row(reason="window_close", post_bars=0),
            _row(reason="trailing_stop", bars_held=1, post_bars=5)]
    text = "\n".join(_render(rows))
    assert "Clean: the window" in text
    assert "WINDOW MISMATCH" not in text


def test_no_window_close_trades_at_all_is_itself_reported():
    """Both books close out at the window every session. If none appears, the
    check did not run and §2.2 is unverified -- silence would read as a pass."""
    text = "\n".join(_render([_row(reason="trailing_stop", bars_held=1)]))
    assert "The check did not run" in text
    assert "unverified" in text


# --- §1: it stays a census ----------------------------------------------------

def test_the_report_prints_no_strategy_pnl_and_no_verdict():
    """The claim §1 rests on. Percent excursions are the subject matter here --
    unlike the pre-flight, which barred money outright -- so the bar is on
    strategy P&L, book comparison and verdict vocabulary. The ONE dollar figure
    allowed is the friction offset that defines 'back to a profit' (§2.1), and
    it must be on a line that says so."""
    rows = [_row(reason="trailing_stop", bars_held=1, book=b, won=w)
            for b in ("MCL", "MC5") for w in (True, False)]
    text = "\n".join(_render(rows))

    money = re.compile(r"\$\s*-?[\d,]+\.?\d*|\([\d,]+\.\d\d\)")
    hits = [ln for ln in text.splitlines() if money.search(ln)]
    assert all("friction" in ln for ln in hits), \
        f"the census printed money that is not the friction offset: {hits[:3]}"

    for banned in ("per trade", "per s-day", "CLEARS", "REFUSED",
                   "NOTHING", "drop-top", "p95", "bootstrap"):
        assert banned not in text, f"the census printed {banned!r}"

    # "per symbol-day" is the denominator a gate study scores money on, and
    # Amendment A prints a COUNT on the same denominator. The phrase is allowed
    # only in that one reading, so a P&L cannot arrive later wearing it.
    for ln in text.splitlines():
        if "per symbol-day" in ln:
            assert "entries per symbol-day" in ln, \
                f"a non-count reading appeared per symbol-day: {ln!r}"


def test_the_report_names_what_it_cannot_do_before_anyone_reads_the_numbers():
    text = "\n".join(_render([_row(reason="trailing_stop", bars_held=1)]))
    assert "NOT A PRICE ON A WIDER STOP" in text
    assert "changes the PATH" in text
    assert "consumes bars" in text            # the signal-ordinal reason
    assert "holdout.json has not been touched" in text
    assert "NOT A RULE" in text


def test_entries_per_symbol_day_separates_reaching_more_days_from_re_entering():
    """AMENDMENT A. Two books with the SAME trade count and opposite shapes:
    one entry on each of four days, against four entries on one day. A mean
    alone cannot tell them apart once the universe is large, which is why the
    touched-day count is printed beside it."""
    wide = [_row(book="MCL", symbol=s, date="2026-09-11")
            for s in ("A", "B", "C", "D")]
    deep = [_row(book="MC5", symbol="A", date="2026-09-11") for _ in range(4)]
    text = "\n".join(_render(wide + deep))
    assert "MCL   4 entries on 4 symbol-days" in text
    assert "MC5   4 entries on 1 symbol-days" in text
    assert "mean 1.00" in text and "mean 4.00" in text


def test_the_population_check_reconciles_on_the_raw_count_not_the_censused_one():
    """A trade with no path is dropped from the census but the published book
    still counted it. Reconciling on the filtered number would print DOES NOT
    MATCH every single run, and a check that always fails is a check nobody
    reads."""
    rows = [_row(book="MCL") for _ in range(3)]
    text = "\n".join(_render(rows, raw={"MCL": 5, "MC5": 0}))
    assert "5 trades   3 with a path to describe   2 excluded" in text


# --- helpers ------------------------------------------------------------------

def _row(book="MCL", symbol="AAA", date="2026-09-11", reason="trailing_stop",
         bars_held=1, post_bars=4, won=False, **kw):
    r = {"book": book, "symbol": symbol, "date": date, "entry_et": "05:00",
         "exit_et": "05:05", "reason": reason, "bars_held": bars_held,
         "entry_px": 10.0, "exit_px": 9.5, "exit_pct": -5.0, "won": won,
         "mae_pct": -6.0, "went_under": True, "back_to_entry": True,
         "back_to_profit": False, "bars_to_recover": 2.0,
         "post_hi_pct": -1.0, "post_lo_pct": -9.0, "post_hi_vs_exit": 4.2,
         "post_lo_vs_exit": -4.2, "recovered_entry": False,
         "recovered_profit": False, "bars_to_entry": float("nan"),
         "post_bars": post_bars}
    r.update(kw)
    return r


def _render(rows, raw=None):
    return R.render(rows, ["2026-09-11"], 1, 0.5, 1, "p.json", "XNAS.ITCH",
                    0, [], raw)
