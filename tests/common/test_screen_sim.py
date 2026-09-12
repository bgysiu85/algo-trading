#!/usr/bin/env python3
"""The screener simulation — the two things that decide whether it is honest.

This finishes `PROGRAM_INDEX` §7 item 1, the item that gates every other result
in the project. Two properties carry the whole thing:

  1. **`first_seen` is an entry floor.** A name that first clears the screen at
     07:20 could not have been traded at 04:00. A universe file without that
     column re-introduces exactly the look-ahead this removes.
  2. **The fast path must reproduce `screen_at` exactly.** It accumulates
     volume in one pass as an optimisation of the one computation the result
     rests on, and an optimisation that disagrees with what it optimises is not
     an optimisation.

`test_the_fast_path_reproduces_screen_at_exactly` and
`test_a_late_qualifier_is_not_dated_to_the_open` are the headline tests.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import screen_sim as SS
from common.screen_at import ScreenConfig, screen_at

ET = ZoneInfo("America/New_York")
CFG = ScreenConfig()
D = date(2026, 3, 2)


def bars(spec, day=D):
    """spec = {symbol: [(minute_offset_from_0400, close, volume), ...]}"""
    rows, idx = [], []
    base = pd.Timestamp(datetime.combine(day, CFG.session_open, tzinfo=ET))
    for sym, pts in spec.items():
        for off, close, vol in pts:
            idx.append((base + timedelta(minutes=off)).tz_convert("UTC"))
            rows.append({"symbol": sym, "open": close, "high": close,
                         "low": close, "close": close, "volume": float(vol)})
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx, name="ts_event"))
    return df.sort_index(kind="mergesort")


def at(minutes, day=D):
    base = pd.Timestamp(datetime.combine(day, CFG.session_open, tzinfo=ET))
    return (base + timedelta(minutes=minutes)).tz_convert("UTC")


def prior(**kw):
    return pd.Series(kw, dtype=float)


# --- THE HEADLINE: the fast path is an optimisation, not a rewrite ----------

def qualifying_day():
    """Several names, some qualifying and some failing each clause, with
    volume arriving over time so the accumulation actually accumulates."""
    spec = {
        "AAA": [(i, 4.00 + 0.02 * i, 12_000) for i in range(40)],   # climbs
        "BBB": [(i, 3.00, 30_000) for i in range(40)],              # flat, fails change
        "CCC": [(i, 9.00 + 0.05 * i, 900) for i in range(40)],      # thin volume
        "DDD": [(i, 30.0 + 0.5 * i, 50_000) for i in range(40)],    # out of band
        "EEE": [(i, 2.50 + 0.03 * i, 20_000) for i in range(10, 40)],  # arrives late
    }
    pc = prior(AAA=3.00, BBB=3.00, CCC=8.00, DDD=20.0, EEE=2.00)
    return bars(spec), pc


def test_the_fast_path_reproduces_screen_at_exactly():
    """THE ONE THAT LICENSES THE OPTIMISATION. `screen_accumulated` groups once
    and selects; `screen_at` re-groups the raw window every tick. They must
    return the same symbols in the same order at every tick, or the 550-session
    run is measuring something other than the screen."""
    b, pc = qualifying_day()
    acc = SS.accumulate(b, CFG)
    compared = 0
    for m in range(1, 41):
        t = at(m)
        fast = SS.screen_accumulated(acc, pc, t, CFG)
        ref = screen_at(b, pc, t, CFG)
        assert list(fast["symbol"]) == list(ref["symbol"]), f"tick {m}"
        assert list(fast.get("rank", [])) == list(ref.get("rank", [])), f"tick {m}"
        if len(ref):
            compared += 1
    assert compared >= 10, "the fixture never qualified anything; vacuous"


def test_sample_agreement_reports_a_real_disagreement(monkeypatch):
    """The agreement check has to be able to FAIL, or it is decoration."""
    b, pc = qualifying_day()
    monkeypatch.setattr(SS, "reference_at",
                        lambda *a, **k: pd.DataFrame({"symbol": ["ZZZ"],
                                                      "rank": [1]}))
    checked, bad, first = SS.sample_agreement(b, pc, D, CFG, every=5)
    assert checked > 0 and bad > 0 and first is not None


def test_sample_agreement_is_clean_on_the_real_pair():
    b, pc = qualifying_day()
    checked, bad, _ = SS.sample_agreement(b, pc, D, CFG, every=5)
    assert checked > 0 and bad == 0


def test_the_report_voids_itself_if_the_fast_path_disagrees():
    out = "\n".join(SS.render([{"date": "2026-03-02", "universe": []}], 1, CFG,
                              60, (10, 3, ("t", ["A"], ["B"])), 1.0, []))
    assert "DOES NOT REPRODUCE THE REFERENCE" in out
    assert "void" in out


# --- THE SECOND HEADLINE: first_seen is an entry floor ----------------------

def test_a_late_qualifier_is_not_dated_to_the_open():
    """A name whose volume only clears the threshold at 07:20 could not have
    been on the watchlist at 04:00. If `first_seen` said otherwise, the
    backtest would arm it from the open BECAUSE it eventually qualified — the
    exact look-ahead this module exists to remove."""
    # Qualifies on change and price from the first bar, but the volume only
    # accumulates past the threshold after 20 minutes.
    need = CFG.volume_min_on_tape
    spec = {"LATE": [(i, 4.00, need / 20.0) for i in range(40)]}
    uni = SS.session_universe(bars(spec), prior(LATE=3.00), D, CFG)
    assert len(uni) == 1
    first = uni.iloc[0]["first_seen"]
    assert first > at(1), "dated to the open despite qualifying later"
    assert first.tz_convert(ET).hour == 4
    assert first.tz_convert(ET).minute >= 20


def test_a_symbol_that_never_qualifies_is_absent():
    spec = {"NOPE": [(i, 3.00, 50_000) for i in range(40)]}
    assert SS.session_universe(bars(spec), prior(NOPE=3.00), D, CFG).empty


def test_the_universe_carries_the_columns_the_backtest_needs():
    b, pc = qualifying_day()
    uni = SS.session_universe(b, pc, D, CFG)
    assert set(uni.columns) == {"symbol", "first_seen", "first_rank",
                                "best_rank", "ticks_on"}
    assert len(uni) >= 1


def test_best_rank_can_beat_first_rank():
    """A name can enter the list at rank 30 and climb. Recording only the first
    rank would lose that, and rank is how `tv_feed` tiers HOT/WARM/COLD."""
    spec = {
        "SLOW": [(i, 4.00 + 0.01 * i, 20_000) for i in range(40)],
        "FAST": [(i, 4.00 + 0.005 * i, 20_000) for i in range(40)],
    }
    uni = SS.session_universe(bars(spec), prior(SLOW=3.00, FAST=3.00), D, CFG)
    assert (uni["best_rank"] <= uni["first_rank"]).all()


# --- the bar-close convention, which flatters the result if got wrong -------

def test_a_bar_is_invisible_until_it_has_CLOSED():
    """`ts_event` is the interval START. The bar stamped 04:29 covers
    04:29:00-04:29:59 and is not knowable until 04:30:00. Reading it at 04:29
    is 59 seconds of the future on every symbol at every tick — the
    entry-latency defect with the sign reversed, and it FLATTERS the result,
    which is why it would not have been noticed."""
    need = CFG.volume_min_on_tape
    spec = {"AAA": [(0, 4.00, need)]}
    acc = SS.accumulate(bars(spec), CFG)
    pc = prior(AAA=3.00)
    assert SS.screen_accumulated(acc, pc, at(0), CFG).empty, "read at its start"
    assert len(SS.screen_accumulated(acc, pc, at(1), CFG)) == 1


def test_the_first_tick_is_one_bar_after_the_open():
    """At 04:00 nothing has closed, so a screen there is empty by construction
    and would only add a row of zeros to every session."""
    ts = SS.ticks(D, CFG, 60)
    assert ts[0] == at(1)


def test_a_coarser_cadence_never_finds_a_name_EARLIER():
    """The stated direction of the bias. A coarse cadence notices a name no
    earlier than the first tick after it qualifies, so it makes entries later
    and the result more conservative — never less."""
    b, pc = qualifying_day()
    fine = SS.session_universe(b, pc, D, CFG, cadence_s=60)
    coarse = SS.session_universe(b, pc, D, CFG, cadence_s=300)
    merged = fine.merge(coarse, on="symbol", suffixes=("_f", "_c"))
    assert len(merged) >= 1
    assert (merged["first_seen_c"] >= merged["first_seen_f"]).all()


def test_screening_faster_than_the_bars_cannot_change_the_answer():
    """Why one minute is the information limit and not a runtime compromise:
    the columns only move when a bar closes."""
    b, pc = qualifying_day()
    every_minute = SS.session_universe(b, pc, D, CFG, cadence_s=60)
    every_30s = SS.session_universe(b, pc, D, CFG, cadence_s=30)
    assert list(every_minute["symbol"]) == list(every_30s["symbol"])
    assert list(every_minute["first_seen"]) == list(every_30s["first_seen"])


# --- prior closes ------------------------------------------------------------

def test_a_symbols_first_day_has_no_prior_close_and_is_dropped():
    """An unknown denominator is not a 0% move."""
    daily = pd.DataFrame({"symbol": ["A", "A", "B"],
                          "date": ["2026-03-01", "2026-03-02", "2026-03-02"],
                          "close": [3.0, 4.0, 5.0]})
    pc = SS.prior_closes(daily)
    assert list(pc["date"]) == ["2026-03-02"]
    assert list(pc["symbol"]) == ["A"]


def test_prior_close_is_the_PREVIOUS_session_not_todays():
    daily = pd.DataFrame({"symbol": ["A", "A"],
                          "date": ["2026-03-01", "2026-03-02"],
                          "close": [3.0, 9.0]})
    pc = SS.prior_closes(daily)
    assert float(pc.iloc[0]["prior_close"]) == 3.0


def test_the_prior_close_shift_agrees_with_regimes():
    """Two modules now shift a daily close by one session. They must not drift:
    `premarket_change` and the regime gate's `gain` are both measured against
    the same quantity, and a disagreement would be invisible in both reports."""
    from common import regime as RG
    daily = pd.DataFrame({"symbol": ["A", "A", "A"],
                          "date": ["2026-03-01", "2026-03-02", "2026-03-03"],
                          "open": [3.0, 4.0, 5.0], "high": [3.0, 4.0, 5.0],
                          "low": [3.0, 4.0, 5.0], "close": [3.0, 4.0, 5.0],
                          "volume": [1e6, 1e6, 1e6]})
    mine = SS.prior_closes(daily).set_index("date")["prior_close"]
    theirs = RG.prepare(daily).set_index("date")["prior_close"]
    for d in mine.index:
        assert float(mine[d]) == pytest.approx(float(theirs[d]))


# --- the archive walk --------------------------------------------------------

def test_window_slices_do_not_pick_up_the_full_day_dailies(tmp_path):
    """Both live in ohlcv-1m. `2025-07-25.dbn.zst` is a whole day and
    `2025-07-25_0400_0930.dbn.zst` is the pre-market slice; screening the
    former would read the regular session as pre-market."""
    d = tmp_path / "XNAS.BASIC" / "ohlcv-1m"
    d.mkdir(parents=True)
    for n in ("2025-07-25.dbn.zst", "2025-07-25_0400_0930.dbn.zst",
              "2025-07-28_0400_0930.dbn.zst", "2025-07.dbn.zst"):
        (d / n).touch()
    got = [p.name for p in SS.window_slices(tmp_path, "XNAS.BASIC")]
    assert got == ["2025-07-25_0400_0930.dbn.zst",
                   "2025-07-28_0400_0930.dbn.zst"]


def test_the_date_is_read_off_the_slice_name():
    assert SS.date_of(SS.Path("x/2026-09-04_0400_0930.dbn.zst")) == "2026-09-04"


def test_missing_slices_name_the_command_that_makes_them(tmp_path):
    with pytest.raises(SystemExit) as e:
        SS.main(["--archive", str(tmp_path), "--dataset", "XNAS.BASIC"])
    assert "_0400_0930" in str(e.value) and "--window 04:00-09:30" in str(e.value)


# --- the report --------------------------------------------------------------

def test_the_report_leads_with_the_entry_floor():
    b, pc = qualifying_day()
    uni = SS.session_universe(b, pc, D, CFG)
    rows = [{"date": "2026-03-02",
             "universe": [{"symbol": r.symbol,
                           "first_seen": r.first_seen.isoformat(),
                           "first_rank": int(r.first_rank),
                           "best_rank": int(r.best_rank),
                           "ticks_on": int(r.ticks_on)}
                          for r in uni.itertuples()]}]
    out = "\n".join(SS.render(rows, 1, CFG, 60, (5, 0, None), 1.0, []))
    assert "WHEN A NAME FIRST CLEARS THE SCREEN" in out
    assert "entry floor" in out
    assert "could not" in out and "04:00" in out


def test_the_report_says_it_is_a_universe_and_not_a_result():
    out = "\n".join(SS.render([], 0, CFG, 60, (5, 0, None), 1.0, []))
    assert "It is a UNIVERSE" in out
    assert "+$4.72" in out and "-$9.81" in out


def test_the_report_states_the_scaled_volume_threshold():
    """The only clause that depends on an ESTIMATE rather than a printed price,
    so it is the only one whose error can move the universe."""
    out = "\n".join(SS.render([], 0, CFG, 60, (5, 0, None), 1.0, []))
    assert f"{CFG.volume_min_on_tape:,}" in out
    assert "capture" in out


def test_the_clauses_are_imported_and_not_restated():
    """A restated constant is a copy that goes stale silently. If Ben changes
    the screen, a re-run must change with it."""
    import inspect
    src = inspect.getsource(SS.screen_accumulated)
    assert "cfg.change_min" in src and "cfg.price_range" in src
    assert "cfg.volume_min_on_tape" in src
    for literal in ("20.0", "100_000", "100000"):
        assert literal not in src, f"{literal} is restated, not imported"


def test_a_microsecond_index_is_not_read_as_nanoseconds():
    """THE BUG THE AGREEMENT CHECK CAUGHT, pinned directly.

    The Databento archive indexes in datetime64[**us**]. `DatetimeIndex.asi8`
    returns the index's own unit; `pd.Timestamp.value` is always nanoseconds.
    Comparing one against the other is a silent factor of 1000 — every bar of
    the session became visible at 04:01, so the simulation read the whole
    morning at the open and emitted a plausible universe built entirely from
    look-ahead. No exception, no empty output, just a wrong answer.

    Built here on a us-resolution index specifically, because a ns fixture
    cannot fail this way and would have passed the whole suite.
    """
    need = CFG.volume_min_on_tape
    spec = {"LATE": [(i, 4.00, need) for i in (0, 100)]}
    b = bars(spec)
    b.index = b.index.as_unit("us")
    assert b.index.dtype == "datetime64[us, UTC]", "fixture is not microseconds"

    pc = prior(LATE=3.00)
    # The two bars are 100 minutes apart. Under the unit bug BOTH were visible
    # at tick 1, so cumulative volume was 2x the threshold from the open. The
    # assertion is on the VOLUME at tick 1, which is what the bug corrupted.
    first_tick = list(SS.sweep(b, pc, D, CFG, 60))[0][1]
    assert len(first_tick) == 1
    assert float(first_tick.iloc[0]["premarket_volume"]) == pytest.approx(need), \
        "a bar 100 minutes in the future was counted at 04:01"
    uni = SS.session_universe(b, pc, D, CFG)
    assert uni.iloc[0]["first_seen"] == at(1)


def test_the_unit_helper_agrees_with_pandas_on_a_known_instant():
    """One assertion against an independently-computed value, so the helper
    cannot be wrong in the same direction as its caller."""
    idx = pd.DatetimeIndex([pd.Timestamp("2026-03-02 09:00:00", tz="UTC")])
    for unit in ("us", "ns"):
        got = SS._utc_ns(idx.as_unit(unit))[0]
        assert got == pd.Timestamp("2026-03-02 09:00:00", tz="UTC").value


def test_skipped_sessions_are_NAMED_not_counted_as_names():
    """Counted SESSIONS and labelled "names dropped" until 2026-09-12. Four
    whole sessions missing from the universe read as four tickers, and the
    check that needed them reported "outside the archive window" instead."""
    out = "\n".join(SS.render([{"date": "2026-03-02", "universe": []}], 1, CFG,
                              60, (5, 0, None), 1.0,
                              ["2026-09-08", "2026-09-09", "2026-09-10",
                               "2026-09-11"]))
    assert "SESSIONS SKIPPED" in out
    assert "names dropped" not in out
    for d in ("2026-09-08", "2026-09-11"):
        assert d in out
    assert "daily archive is short, not the minute one" in out
    assert "ohlcv-1d" in out


def test_no_skipped_sessions_prints_no_remedy_block():
    out = "\n".join(SS.render([{"date": "2026-03-02", "universe": []}], 1, CFG,
                              60, (5, 0, None), 1.0, []))
    assert "SESSIONS SKIPPED, no prior close  0" in out
    assert "daily archive is short" not in out


def test_a_long_skip_list_is_truncated_with_a_count():
    out = "\n".join(SS.render([{"date": "2026-03-02", "universe": []}], 1, CFG,
                              60, (5, 0, None), 1.0,
                              [f"2026-01-{d:02d}" for d in range(1, 21)]))
    assert "and 8 more" in out
