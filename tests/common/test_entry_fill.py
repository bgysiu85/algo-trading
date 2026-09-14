#!/usr/bin/env python3
r"""Changing the fill, and the three ways that measurement flatters itself.

LOOK-AHEAD THROUGH THE FILL PRICE. The signal is not known until the bar closes,
so no price inside that bar was available. A variant filling at the signal bar's
own low prints a better number for reading the future, and renders identically
to an honest one.

A DENOMINATOR THAT SHRINKS TO FIT. A pullback limit skips every entry that ran
away without pulling back -- plausibly the best ones. Per trade, abstaining from
winners looks like skill. The book's total is what says otherwise, and the
pre-registered rule refuses any variant whose total is no better.

A SECOND EXIT MODEL. The whole point of driving the variants through
`entry_bars` is that the exit stays the engine's. A study that re-implemented
the trail beside the question is how the live path and the backtest drifted
apart for three days.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from common import entry_fill as F


def rows(n, gross, date="2026-01-02"):
    return [{"date": date, "gross": gross} for _ in range(n)]


def book(per_half_gross, n=100):
    out = []
    for half, g in zip(("2026-01-02", "2026-06-02"), per_half_gross):
        out += rows(n, g, half)
    return out


def results(**kw):
    out = {F.BASELINE: {"trades": kw.pop("baseline"), "missed": 0}}
    for k, v in kw.items():
        out[k.replace("_", " ")] = {"trades": v, "missed": 0}
    return out


# --- the variant list is fixed, not searched --------------------------------

def test_the_baseline_is_first_and_named():
    v = F.variants()
    assert v[0][0] == F.BASELINE and v[0][1]["kind"] == "baseline"


def test_every_variant_is_a_fixed_combination_not_a_sweep():
    names = [n for n, _ in F.variants()]
    assert len(names) == 1 + len(F.DEFER_BARS) + len(F.PULLBACK_PCT) * len(
        F.PULLBACK_WINDOW)
    assert len(set(names)) == len(names)


def test_the_rule_is_written_down_before_the_run():
    for word in ("PRE-REGISTERED", "CLEARS", "IMPROVES", "NOTHING"):
        assert word in F.__doc__


# --- no look-ahead ----------------------------------------------------------

def test_a_limit_cannot_fill_on_the_signal_bar_itself():
    """THE ONE THAT WOULD READ THE FUTURE. The signal is known only once the
    bar has closed, so that bar's own low was never available to buy at."""
    df = pd.DataFrame({"low": [1.0, 9.0, 9.0, 9.0]})
    assert F.limit_fill(df, 0, 1.0, 3) is None


def test_a_limit_fills_on_the_first_later_bar_that_reaches_it():
    df = pd.DataFrame({"low": [9.0, 9.0, 5.0, 4.0]})
    assert F.limit_fill(df, 0, 5.0, 3) == 2


def test_a_limit_that_is_never_reached_does_not_fill():
    df = pd.DataFrame({"low": [9.0, 9.0, 9.0, 9.0]})
    assert F.limit_fill(df, 0, 1.0, 3) is None


def test_the_window_is_bounded_and_does_not_run_past_it():
    df = pd.DataFrame({"low": [9.0, 9.0, 9.0, 1.0]})
    assert F.limit_fill(df, 0, 1.0, 2) is None
    assert F.limit_fill(df, 0, 1.0, 3) == 3


def test_the_report_states_that_nothing_fills_inside_the_signal_bar():
    out = "\n".join(F.render(results(baseline=book((1.0, 1.0))), 10, 1.0, 1))
    assert "NOTHING FILLS INSIDE THE SIGNAL BAR" in out


# --- the engine hook --------------------------------------------------------

def test_the_engine_fills_at_the_override_when_one_is_given():
    """A limit fills at the limit. The hook exists so the exit model stays the
    engine's rather than being rewritten beside the question."""
    from strategy.mcl import mcl as MCL
    import inspect
    assert "entry_px_by_bar" in inspect.signature(MCL.backtest_session).parameters
    src = Path("strategy/mcl/mcl.py").read_text(encoding="utf-8")
    assert "CANNOT BE USED TO FILL INSIDE THE SIGNAL BAR" in src


def test_no_slippage_tick_is_added_to_an_overridden_price():
    """A limit fills at the limit or better; charging market slippage to it
    would price an order that did not pay it."""
    src = Path("strategy/mcl/mcl.py").read_text(encoding="utf-8")
    blk = src.split("over = None if px_at is None")[1][:400]
    assert "float(over)" in blk and "SLIPPAGE_TICKS * TICK\n" in blk
    assert "float(over) + SLIPPAGE_TICKS" not in src


def test_the_default_path_is_untouched_when_no_override_is_passed():
    """`None` must leave the shipped behaviour bit-identical, which is the
    property that lets this hook live in the live strategy module at all."""
    src = Path("strategy/mcl/mcl.py").read_text(encoding="utf-8")
    assert "None leaves the fill untouched, so the default path is" in src


def test_this_module_does_not_reimplement_the_exit():
    src = Path("common/entry_fill.py").read_text(encoding="utf-8")
    for word in ("peak", "trail_level", "TRAIL_PCT"):
        assert f"def {word}" not in src
    assert "backtest_session" in src


# --- the refusal that was fixed in advance ----------------------------------

def test_abstention_is_refused_before_anything_else_is_asked():
    """THE FAILURE MODE THAT WOULD OTHERWISE WIN THIS TABLE OUTRIGHT.

    The baseline loses money, so trading less always earns more in total, and
    skipping losers always raises the per-trade figure. A variant taking two
    trades out of two hundred is not an improvement to this strategy; it is a
    different one.
    """
    base = book((-5.0, -5.0), n=100)          # 200 trades at -9.26 each
    good_but_tiny = book((20.0, 20.0), n=1)   # 2 trades, +15.74 each
    tag, why = F.verdict(good_but_tiny, base)
    assert tag == "NOTHING"
    assert "under the 50% floor" in why


def test_a_variant_that_earns_less_in_total_is_not_an_improvement():
    """Where the baseline EARNS money, a smaller total is not an improvement
    however good the per-trade figure. Guarded on a positive baseline because
    on a losing book this test is satisfied by abstaining, which the fill floor
    already refuses."""
    base = book((10.0, 10.0), n=100)           # 200 trades, +5.74 = +1,148
    fewer_better = book((14.0, 14.0), n=51)    # 102 trades, +9.74 = +993
    tag, why = F.verdict(fewer_better, base)
    assert tag == "NOTHING"
    assert "total net is no better" in why


def test_the_fill_floor_is_fixed_in_advance_and_documented():
    assert F.MIN_FILL == 0.50
    assert "Abstention is not an edge" in F.__doc__


def test_a_variant_positive_in_both_halves_and_larger_in_total_clears():
    base = book((-5.0, -5.0), n=100)
    better = book((20.0, 20.0), n=100)
    assert F.verdict(better, base)[0] == "CLEARS"


def test_a_variant_positive_in_only_one_half_does_not_clear():
    base = book((-5.0, -5.0), n=100)
    mixed = book((20.0, -20.0), n=100)
    assert F.verdict(mixed, base)[0] == "NOTHING"


def test_a_variant_better_by_more_than_friction_in_both_halves_improves():
    base = book((-20.0, -20.0), n=100)
    less_bad = book((-8.0, -8.0), n=100)
    tag, _ = F.verdict(less_bad, base)
    assert tag == "IMPROVES"


def test_a_variant_better_by_less_than_friction_is_nothing():
    base = book((-20.0, -20.0), n=100)
    marginal = book((-17.0, -17.0), n=100)
    assert F.verdict(marginal, base)[0] == "NOTHING"


# --- the table has to show what abstaining costs ----------------------------

def test_the_table_prints_the_total_beside_the_per_trade_figure():
    """They move in opposite directions, and the per-trade column is the one
    that flatters a rule which simply trades less."""
    res = results(baseline=book((-5.0, -5.0), n=100),
                  tiny=book((20.0, 20.0), n=1))
    out = "\n".join(F.table(res, F.BASELINE))
    assert "total $" in out
    assert "they can move in opposite directions" in out


def test_the_fill_rate_is_against_the_baselines_book():
    res = results(baseline=book((-5.0, -5.0), n=100),
                  half=book((-5.0, -5.0), n=50))
    out = "\n".join(F.table(res, F.BASELINE))
    assert "50%" in out


def test_the_skipped_entries_are_valued_not_merely_counted():
    """A limit that never fills skips a trade. If the skipped ones are the
    winners, the variant improves its average by abstaining from the part that
    pays -- and only this section can show it."""
    res = results(baseline=book((20.0, 20.0), n=100),
                  skips_the_winners=book((20.0, 20.0), n=10))
    out = "\n".join(F.missed_section(res, F.BASELINE))
    assert "abstained from money" in out
    # 180 skipped trades, each worth +15.74 at baseline
    assert "15.74" in out


def test_every_variant_is_printed_even_the_useless_ones():
    res = results(baseline=book((-5.0, -5.0)), a=book((-9.0, -9.0)),
                  b=book((-1.0, -1.0)))
    out = "\n".join(F.table(res, F.BASELINE))
    for name in res:
        assert name in out


def test_nothing_is_recommended():
    res = results(baseline=book((-5.0, -5.0)), a=book((-1.0, -1.0)))
    out = "\n".join(F.render(res, 10, 1.0, 1))
    assert "NONE RECOMMENDED" in out


# --- caveats that must survive ----------------------------------------------

def test_the_friction_caveat_for_limits_is_printed():
    out = "\n".join(F.render(results(baseline=book((-5.0, -5.0))), 10, 1.0, 1))
    assert "NOT A FRICTION MODEL FOR LIMITS" in out
    assert "measured on market" in out


def test_the_queue_caveat_names_the_thin_bars():
    """A limit at the low of a bar is assumed filled if the bar traded there.
    39.7% of these entries are on bars under $100,000, where it might not."""
    out = "\n".join(F.render(results(baseline=book((-5.0, -5.0))), 10, 1.0, 1))
    assert "NOT A QUEUE MODEL" in out
    assert "39.7%" in out


def test_a_book_that_does_not_match_the_published_count_stops_the_reader():
    out = "\n".join(F.render(results(baseline=book((-5.0, -5.0), n=1)), 1, 1.0, 1))
    assert "DOES NOT MATCH" in out


def test_the_n_equals_one_defer_row_is_named_as_the_status_quo():
    """The live order already leaves sixty seconds after the bar closes, so
    that row is a measurement of what is happening, not a proposal."""
    assert 1 in F.DEFER_BARS
    assert "not a proposal" in F.__doc__


# --- the pipeline -----------------------------------------------------------

def _frame(sym="AAA", n=330, period=40, amp=0.30, drift=0.004,
           base_v=40_000.0, spike=130_000.0):
    import math
    from datetime import date, datetime, time as dtime, timedelta
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    D = date(2026, 3, 2)
    idx = []
    for d in (D - timedelta(days=1), D):
        b = pd.Timestamp(datetime.combine(d, dtime(4, 0), tzinfo=ET))
        idx += [(b + timedelta(minutes=i)).tz_convert("UTC") for i in range(n)]
    close = [4.0 + drift * i + amp * math.sin(2 * math.pi * i / period)
             for i in range(len(idx))]
    vol = [spike if i % 3 == 0 else base_v for i in range(len(idx))]
    return pd.DataFrame({"symbol": sym, "open": close,
                         "high": [c + 0.02 for c in close],
                         "low": [c - 0.02 for c in close],
                         "close": close, "volume": vol},
                        index=pd.DatetimeIndex(idx)), D


def _run(monkeypatch, **kw):
    df, D = _frame(**kw)
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: df)
    fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert(
        "UTC").isoformat()
    return F.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                      [{"symbol": "AAA", "date": D.isoformat(),
                        "first_seen": fs}], F.variants()))


def test_run_day_produces_a_book_for_every_variant(monkeypatch):
    """THE TEST A RENDERER-ONLY SUITE CANNOT HAVE."""
    day, res, err = _run(monkeypatch)
    assert err == ""
    assert set(res) == {n for n, _ in F.variants()}
    assert res[F.BASELINE]["trades"], "the fixture produced no baseline trades"


def test_deferring_the_fill_changes_the_prices_not_the_engine(monkeypatch):
    """The variant must be a different book, not the same numbers relabelled --
    and it must come from the engine, so the exit model is shared."""
    _day, res, _err = _run(monkeypatch)
    base = [r["gross"] for r in res[F.BASELINE]["trades"]]
    name = "defer 1 bar(s), pay the close"
    other = [r["gross"] for r in res[name]["trades"]]
    assert other, "the deferred variant produced no trades at all"
    assert base != other, "deferring the fill changed nothing; the hook is inert"


def test_a_pullback_variant_takes_fewer_trades_than_the_baseline(monkeypatch):
    """It must actually skip something, or the fill-rate column is decoration."""
    _day, res, _err = _run(monkeypatch)
    base = len(res[F.BASELINE]["trades"])
    lim = len(res["limit -3% good for 5 bars"]["trades"])
    assert lim < base


def test_a_pullback_variant_does_fill_on_a_frame_that_pulls_back(monkeypatch):
    """The other half of the test above: `fewer` must not be able to pass by
    being ZERO on every frame, or the variant is untested rather than strict."""
    _day, res, _err = _run(monkeypatch, amp=0.6, period=24, drift=0.002)
    assert res["limit -1% good for 15 bars"]["trades"]


def test_the_report_renders_from_real_rows_end_to_end(monkeypatch):
    _day, res, _err = _run(monkeypatch)
    out = "\n".join(F.render(res, 1, 1.0, 1))
    assert "EVERY VARIANT" in out and "THE VERDICT, PER VARIANT" in out


def test_a_limit_variant_actually_filled_at_its_limit(monkeypatch):
    """THE GAP THE MUTATION PASS FOUND.

    If `entry_px_by_bar` is never handed to the engine, the limit variants fill
    at the chosen bar's CLOSE instead of at the limit -- a different and
    flattering measurement that renders identically to the honest one. The
    limit price travels with each trade so this can be asserted rather than
    assumed.
    """
    # A DEEPER WOBBLE THAN THE DEFAULT FIXTURE. The gentle one never pulls back
    # far enough for any limit to fill, so every limit row came back empty and
    # this test passed on an empty loop -- which is the shape of failure it was
    # written to catch, arriving in the test itself.
    _day, res, _err = _run(monkeypatch, amp=0.6, period=24, drift=0.002)
    checked = 0
    for name, r in res.items():
        if not name.startswith("limit "):
            continue
        for t in r["trades"]:
            assert "limit_px" in t, f"{name}: a fill carries no limit price"
            # Half a tick at the 4dp `Trade.entry_price` rounds to, not a
            # fudge: the engine stores round(entry_px, 4), so an exact limit of
            # 5.076752... is recorded as 5.0768 and is above itself by 5e-5.
            assert t["entry_px"] <= t["limit_px"] + 5e-5, (
                f"{name}: filled at {t['entry_px']:.4f}, above its own limit "
                f"{t['limit_px']:.4f} -- the override never reached the engine")
            checked += 1
    assert checked, "no limit variant produced a fill; the test proves nothing"
