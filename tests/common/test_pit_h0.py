#!/usr/bin/env python3
"""H0 on the point-in-time universe.

The measurement `screener_simulation_scope.md` §5 asks for. One property
decides whether it is honest:

**No trade may start before its own symbol's `first_seen`.** A name the screen
surfaces at 06:10 cannot be bought at 04:30, and a runner that ignored the
field would reproduce exactly the look-ahead `screen_sim` was built to remove —
while producing a number that looks like an answer.

`test_no_trade_starts_before_its_symbols_first_seen` is the headline test.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import pit_h0 as P
from strategy.premkt import hypotheses as H

ET = ZoneInfo("America/New_York")
D = date(2026, 3, 2)


def session(sym="AAA", start=4, n=330, px=4.0, step=0.01):
    base = pd.Timestamp(datetime.combine(D, dtime(start, 0), tzinfo=ET))
    idx = pd.DatetimeIndex(
        [(base + timedelta(minutes=i)).tz_convert("UTC") for i in range(n)])
    close = [px + step * i for i in range(n)]
    return pd.DataFrame({"symbol": sym, "open": close, "high": close,
                         "low": close, "close": close,
                         "volume": [10_000.0] * n}, index=idx)


def at_et(h, m):
    return pd.Timestamp(datetime.combine(D, dtime(h, m), tzinfo=ET)
                        ).tz_convert("UTC").isoformat()


def rec(sym="AAA", h=4, m=30, rank=1):
    return {"symbol": sym, "date": D.isoformat(), "first_seen": at_et(h, m),
            "first_rank": rank, "best_rank": rank, "ticks_on": 10}


# --- THE HEADLINE ------------------------------------------------------------

def test_no_trade_starts_before_its_symbols_first_seen():
    """A name surfaced at 07:00 cannot be bought at 04:30. Ignoring the field
    would reproduce the look-ahead `screen_sim` exists to remove, and would do
    it while producing a number that looks like an answer."""
    bars = session()
    for h, m in ((4, 30), (6, 10), (7, 0), (9, 0)):
        trades = P.run_day(bars, D.isoformat(), [rec(h=h, m=m)],
                           as_screened=True, trail=8.0)
        assert trades, f"no trade at {h}:{m}"
        entry = pd.Timestamp(trades[0]["entry_time"]).tz_convert(ET)
        assert entry.time() >= dtime(h, m), f"entered before first_seen {h}:{m}"


def test_the_floor_can_only_move_an_entry_LATER():
    """`max(ENTRY_FROM, first_seen)`. A first_seen of 04:05 must not pull the
    entry in front of the registered 04:30 — that would be a different and
    better-filled hypothesis wearing H0's name."""
    bars = session()
    trades = P.run_day(bars, D.isoformat(), [rec(h=4, m=5)],
                       as_screened=True, trail=8.0)
    entry = pd.Timestamp(trades[0]["entry_time"]).tz_convert(ET)
    assert entry.time() >= H.ENTRY_FROM


def test_signal_h0_with_no_floor_is_bit_identical_to_the_registered_rule():
    """`not_before` was added to a REGISTERED module. The default path must be
    the rule exactly as it was scored, or the +$4.72 it is being compared
    against was produced by different code."""
    bars = session()
    a = H.signal_h0(bars, D, ET)
    b = H.signal_h0(bars, D, ET, not_before=None)
    assert list(a["entry"]) == list(b["entry"])
    assert a["entry"].sum() == 1
    fired = pd.Timestamp(a.index[list(a["entry"]).index(True)]).tz_convert(ET)
    assert fired.time() == H.ENTRY_FROM


# --- the two variants are different questions -------------------------------

def test_knowable_at_0430_SKIPS_a_late_name_rather_than_entering_late():
    """The variant holds the ENTRY TIME fixed and varies only the universe —
    that is what makes it comparable to the +$4.72. Entering a late name late
    would change both at once and compare nothing."""
    bars = session()
    assert P.run_day(bars, D.isoformat(), [rec(h=7, m=0)],
                     as_screened=False, trail=8.0) == []
    assert P.run_day(bars, D.isoformat(), [rec(h=4, m=15)],
                     as_screened=False, trail=8.0), "an early name was skipped"


def test_as_screened_keeps_the_late_name():
    bars = session()
    assert P.run_day(bars, D.isoformat(), [rec(h=7, m=0)],
                     as_screened=True, trail=8.0)


def test_a_symbol_with_no_bars_is_skipped_not_crashed():
    bars = session(sym="AAA")
    assert P.run_day(bars, D.isoformat(), [rec(sym="ZZZ")],
                     as_screened=True, trail=8.0) == []


# --- scoring -----------------------------------------------------------------

def trades(spec):
    """spec = [(date, symbol, net)]"""
    return [{"date": d, "symbol": s, "net": n} for d, s, n in spec]


def test_friction_is_charged_per_trade_and_moves_the_total():
    t = trades([("2026-03-02", "A", 10.0)] * 10)
    assert P.score(t, "2026-03-02", 1.00)["net"] == pytest.approx(90.0)
    assert P.score(t, "2026-03-02", 8.92)["net"] == pytest.approx(10.8)


def test_drop_top_5_removes_SYMBOLS_not_trades():
    """Concentration is what killed everything else here, and it concentrates
    in names rather than in individual trades — one symbol traded twenty times
    is one bet."""
    t = trades([("2026-03-02", "BIG", 100.0)] * 5
               + [("2026-03-02", f"S{i}", 1.0) for i in range(20)])
    s = P.score(t, "2026-03-02", 0.0)
    assert s["net"] == pytest.approx(520.0)
    assert s["dropped"] < 100.0, "removing 5 trades, not 5 symbols"


def test_both_halves_are_counted_separately():
    t = trades([("2026-01-01", "A", 10.0), ("2026-06-01", "B", -10.0)])
    s = P.score(t, "2026-03-01", 0.0)
    assert s["ne"] == 1 and s["nl"] == 1
    assert s["early"] > 0 > s["late"]


# --- the verdict reads the brackets correctly -------------------------------

def result(per_trade, n=400):
    return {"knowable": trades([(f"2026-{1 + i % 9:02d}-01", f"S{i}",
                                 per_trade + 4.26) for i in range(n)]),
            "as_screened": trades([(f"2026-{1 + i % 9:02d}-01", f"S{i}",
                                    per_trade + 4.26) for i in range(n)])}


def test_landing_with_the_survivors_says_the_screen_did_the_work():
    out = "\n".join(P.render(result(4.9), 100, 500, "2026-05-01", 8.0, 1.0))
    assert "THE SCREEN WAS DOING THE WORK" in out


def test_landing_with_the_rejects_says_the_figure_was_the_leak():
    out = "\n".join(P.render(result(-9.9), 100, 500, "2026-05-01", 8.0, 1.0))
    assert "THE +$4.72 WAS THE LEAK" in out
    assert "overstated" in out


def test_landing_between_says_so_rather_than_picking_a_side():
    out = "\n".join(P.render(result(-2.0), 100, 500, "2026-05-01", 8.0, 1.0))
    assert "BETWEEN THE BRACKETS" in out
    assert "Neither published figure should be quoted alone" in out


def test_an_empty_knowable_bucket_refuses_a_verdict_and_says_why():
    """If nothing is on the watchlist by 04:30, that IS the finding — every
    backtest here assumed a universe the live screen does not surface that
    early — and it must not read as a strategy result."""
    res = {"knowable": [], "as_screened": trades([("2026-03-02", "A", 5.0)])}
    out = "\n".join(P.render(res, 10, 50, "2026-03-02", 8.0, 1.0))
    assert "NO VERDICT" in out
    assert "does not" in out and "surface this universe" in out


def test_every_figure_is_reported_at_all_three_friction_levels():
    """friction_reconciliation_20260911.md §5 item 3. One extra column, and it
    removes the argument from every future doc."""
    out = "\n".join(P.render(result(1.0), 100, 500, "2026-05-01", 8.0, 1.0))
    for label, _ in P.FRICTIONS:
        assert label in out
    assert "SIGN STABILITY" in out


def test_the_report_says_the_holdout_has_not_been_spent():
    out = "\n".join(P.render(result(1.0), 100, 500, "2026-05-01", 8.0, 1.0))
    assert "has NOT been spent" in out


def test_as_screened_is_marked_not_comparable_to_the_brackets():
    """Its entry time moved, so reading it against +$4.72 compares two changes
    at once."""
    out = "\n".join(P.render(result(1.0), 100, 500, "2026-05-01", 8.0, 1.0))
    i = out.index("AS SCREENED")
    assert "NOT comparable" in out[i:i + 400]


# --- loading -----------------------------------------------------------------

def test_an_empty_pairs_file_names_the_command_that_fills_it(tmp_path):
    p = tmp_path / "pit.json"
    p.write_text("[]")
    with pytest.raises(SystemExit) as e:
        P.load_pit(p)
    assert "screen_sim" in str(e.value)


def test_first_seen_is_read_back_as_an_ET_time():
    assert P.first_seen_time(rec(h=6, m=10)) == dtime(6, 10)


# --- provenance, and the pool ------------------------------------------------

def test_the_report_says_which_prior_close_the_universe_was_built_on():
    """`pit_strategy` pins H0's symbol-day COUNT as its staleness guard and
    nothing else. Two universes of the same size built against different prior
    closes would slip past that guard, so the number this module produces has
    to carry the mix that distinguishes them."""
    out = "\n".join(P.render(result(1.0), 100, 500, "2026-05-01", 8.0, 1.0,
                             mix={"repaired": 38, "daily": 462}))
    assert "THE UNIVERSE THIS WAS SCORED ON" in out
    assert "repaired" in out and "38" in out
    assert "daily" in out and "462" in out


def test_a_pairs_file_without_provenance_says_so_instead_of_guessing():
    out = "\n".join(P.render(result(1.0), 100, 500, "2026-05-01", 8.0, 1.0,
                             mix={"unknown": 500}))
    assert "UNKNOWN rows" in out
    assert "screen_sim" in out


def test_source_mix_counts_missing_provenance_as_unknown():
    assert P.source_mix([rec(), rec(sym="BBB")]) == {"unknown": 2}
    assert P.source_mix([dict(rec(), prior_source="repaired"),
                         dict(rec(sym="BBB"), prior_source="daily"),
                         dict(rec(sym="CCC"), prior_source="daily")]) == {
        "repaired": 1, "daily": 2}


def test_h0_day_is_the_same_implementation_the_sequential_path_uses(tmp_path,
                                                                    monkeypatch):
    """The worker must not be a second copy of the runner. It is given a path
    and reads its own slice, so the test hands it a fake reader and checks the
    trades match `run_day` exactly."""
    bars = session()
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: bars)
    day, kn, asc, nu, err = P.h0_day(("ignored.dbn", D.isoformat(),
                                      [rec(h=6, m=10)], 8.0))
    assert err == "" and day == D.isoformat() and nu == 1
    assert asc == P.run_day(bars, D.isoformat(), [rec(h=6, m=10)],
                            as_screened=True, trail=8.0)
    assert kn == P.run_day(bars, D.isoformat(), [rec(h=6, m=10)],
                           as_screened=False, trail=8.0)


def test_an_unreadable_slice_is_named_not_silently_counted(monkeypatch):
    """A day that cannot be read must contribute nothing to the universe count.
    Counting its symbol-days while scoring none of them would deflate every
    per-symbol-day figure by exactly the unreadable share."""
    def boom(p):
        raise ValueError("truncated")
    monkeypatch.setattr("common.dbn_io.read_dbn", boom)
    day, kn, asc, nu, err = P.h0_day(("bad.dbn", D.isoformat(), [rec()], 8.0))
    assert nu == 0 and kn == [] and asc == []
    assert "ValueError" in err and "truncated" in err


def test_an_empty_slice_scores_nothing_and_reports_no_error(monkeypatch):
    monkeypatch.setattr("common.dbn_io.read_dbn",
                        lambda p: pd.DataFrame(columns=["symbol", "close"]))
    _day, kn, asc, nu, err = P.h0_day(("empty.dbn", D.isoformat(),
                                       [rec()], 8.0))
    assert (kn, asc, nu, err) == ([], [], 0, "")


def test_the_merge_is_day_ordered_not_completion_ordered():
    """A pool returns days in whatever order the workers finish. This module
    SUMS floats, so a net that depends on that order would make the control
    constant move when --jobs changes."""
    by_date = {"2026-03-02": [rec()], "2026-03-03": [rec(sym="BBB")],
               "2026-03-04": [rec(sym="CCC")]}
    got = {"2026-03-04": ([], [{"date": "2026-03-04", "net": 0.1}], 1),
           "2026-03-02": ([], [{"date": "2026-03-02", "net": 0.2}], 1),
           "2026-03-03": ([], [{"date": "2026-03-03", "net": 0.3}], 1)}
    res, universe, n = P.merge(got, by_date)
    assert [t["date"] for t in res["as_screened"]] == [
        "2026-03-02", "2026-03-03", "2026-03-04"]
    assert n == 3 and len(universe) == 3
    # and the reversed-completion pool gives the identical list
    assert P.merge(dict(reversed(list(got.items()))), by_date)[0] == res


def test_a_day_that_scored_nothing_is_out_of_the_provenance_mix_too():
    """`n_universe` and the mix must describe the same rows -- otherwise the
    percentages are computed over a wider universe than the constants were."""
    by_date = {"2026-03-02": [dict(rec(), prior_source="repaired")],
               "2026-03-03": [dict(rec(sym="BBB"), prior_source="daily")]}
    got = {"2026-03-02": ([], [], 1), "2026-03-03": ([], [], 0)}
    _res, universe, n = P.merge(got, by_date)
    assert n == 1
    assert P.source_mix(universe) == {"repaired": 1}


# --- the constants other modules quote ---------------------------------------

def test_the_report_emits_the_constants_pit_strategy_wants():
    """Every earlier refresh of these was a hand-transcription out of the
    table. A hand-transcribed control constant is the same defect shape as the
    rest -- a number that looks like it came from the measurement."""
    out = "\n".join(P.render(result(1.0), 100, 500, "2026-05-01", 8.0, 1.0,
                             mix={"repaired": 500}, n_knowable=120))
    for k in ("H0_PIT_NET", "H0_PIT_TRADES", "H0_PIT_OFFERED",
              "H0_KNOWABLE_NET", "H0_KNOWABLE_TRADES", "H0_KNOWABLE_OFFERED",
              "H0_REFERENCE_SOURCE"):
        assert f"  {k} = " in out, k
    assert "H0_PIT_OFFERED = 500" in out
    assert "H0_KNOWABLE_OFFERED = 120" in out
    assert "repaired=500" in out


def test_the_emitted_constants_are_the_dollar_4_26_column():
    """$4.26 is the figure pit_strategy compares against. Emitting any other
    friction here would put a number in the file that the table does not
    contain."""
    res = result(1.0)
    out = "\n".join(P.render(res, 100, 500, "2026-05-01", 8.0, 1.0,
                             mix={"repaired": 500}, n_knowable=120))
    s = P.score(res["as_screened"], "2026-05-01", 4.26)
    assert f"H0_PIT_NET = {s['net']:_.1f}" in out
    assert f"H0_PIT_TRADES = {s['n']:_}" in out


def test_knowable_offered_counts_only_names_on_the_list_by_0430():
    """The KNOWABLE denominator is not the universe size -- run_day skips a
    name whose first_seen is later, so counting all of them would deflate the
    per-symbol-day figure by the late share."""
    uni = [rec(h=4, m=0), rec(sym="B", h=4, m=30), rec(sym="C", h=4, m=31),
           rec(sym="D", h=7, m=0)]
    assert P.knowable_offered(uni) == 2
    scored = [t for r in uni
              for t in P.run_day(session(), D.isoformat(), [r],
                                 as_screened=False, trail=8.0)]
    assert len({t["symbol"] for t in scored}) <= P.knowable_offered(uni)


def test_a_run_that_did_not_compute_knowable_offered_says_so(monkeypatch):
    out = "\n".join(P.render(result(1.0), 100, 500, "2026-05-01", 8.0, 1.0,
                             mix={"repaired": 500}))
    assert "H0_KNOWABLE_OFFERED = ?" in out and "not computed" in out
