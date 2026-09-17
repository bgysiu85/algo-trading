#!/usr/bin/env python3
"""The full-day screen: block windows, references, volume resets, and the
control that the PRE block IS screen_sim (REGISTERED_mc5_full_day.md §2)."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import screen_day as D
from common import screen_sim as S
from common.screen_at import ScreenConfig

ET = ZoneInfo("America/New_York")
DAY = date(2026, 3, 2)
CFG = ScreenConfig(capture=1.0)          # a whole-tape threshold: 100,000 shares


def bars(rows):
    """rows: (HH:MM ET, symbol, close, volume)."""
    idx, sym, close, vol = [], [], [], []
    for hhmm, s, c, v in rows:
        h, m = (int(x) for x in hhmm.split(":"))
        idx.append(pd.Timestamp(datetime.combine(DAY, dtime(h, m), tzinfo=ET)
                                ).tz_convert("UTC"))
        sym.append(s); close.append(c); vol.append(v)
    return pd.DataFrame({"symbol": sym, "open": close, "high": close, "low": close,
                         "close": close, "volume": vol},
                        index=pd.DatetimeIndex(idx)).sort_index()


def run(block, rows, ref, cfg=CFG, cadence=60):
    name, start, end, _kind, _suffix = next(b for b in D.BLOCKS if b[0] == block)
    return list(D.sweep_block(bars(rows), pd.Series(ref), DAY, cfg, cadence, start, end))


def seen(ticks):
    """{symbol: first tick ET HH:MM}."""
    out = {}
    for t, sel in ticks:
        for s in sel["symbol"]:
            out.setdefault(s, t.tz_convert(ET).strftime("%H:%M"))
    return out


# --- windows --------------------------------------------------------------------

def test_each_block_sees_only_its_own_bars():
    rows = [("04:05", "A", 3.0, 200_000), ("10:05", "A", 3.0, 200_000),
            ("17:05", "A", 3.0, 200_000)]
    ref = {"A": 2.0}                                  # +50%, clears on change
    assert seen(run("PRE", rows, ref)) == {"A": "04:06"}
    assert seen(run("RTH", rows, ref)) == {"A": "10:06"}
    assert seen(run("POST", rows, ref)) == {"A": "17:06"}


def test_volume_restarts_at_each_block():
    # 60k in the morning and 60k after the open clears 100k ONLY if the two
    # are added together. The live `volume` column restarts at 09:30, so RTH
    # must not see the morning's shares.
    rows = [("04:05", "A", 3.0, 60_000), ("10:05", "A", 3.0, 60_000)]
    ref = {"A": 2.0}
    assert seen(run("PRE", rows, ref)) == {}
    assert seen(run("RTH", rows, ref)) == {}
    rows2 = rows + [("10:20", "A", 3.0, 45_000)]
    assert seen(run("RTH", rows2, ref)) == {"A": "10:21"}


def test_a_bar_is_not_visible_until_it_closes():
    rows = [("10:05", "A", 3.0, 200_000)]
    ticks = run("RTH", rows, {"A": 2.0})
    at = {t.tz_convert(ET).strftime("%H:%M"): list(sel["symbol"]) for t, sel in ticks}
    assert at["10:05"] == [] and at["10:06"] == ["A"]


def test_the_last_tick_of_a_block_is_the_next_blocks_start():
    ts = [t.tz_convert(ET).strftime("%H:%M")
          for t in D.block_ticks(DAY, dtime(9, 30), dtime(16, 0), CFG, 60)]
    assert ts[0] == "09:31" and ts[-1] == "16:00"


# --- references -----------------------------------------------------------------

def test_post_measures_against_todays_close_not_yesterdays():
    rows = [("17:05", "A", 3.0, 200_000)]
    # Yesterday 2.00 -> +50%. Today's 16:00 close 2.90 -> +3.4%, which fails.
    assert seen(run("POST", rows, {"A": 2.0})) == {"A": "17:06"}
    assert seen(run("POST", rows, {"A": 2.90})) == {}


def test_exchange_test_symbols_never_reach_the_universe():
    """The tape carries venue test symbols. screen_at excludes them by the same
    single definition; a block sweep that forgot would put them in a universe
    the trader can never buy."""
    from common.screen import is_test_symbol
    bad = next(s for s in ("ZAZZT", "ZBZZT", "ZVZZT", "ZWZZT") if is_test_symbol(s))
    rows = [("10:05", bad, 3.0, 200_000), ("10:05", "A", 3.0, 200_000)]
    assert seen(run("RTH", rows, {bad: 2.0, "A": 2.0})) == {"A": "10:06"}


def test_a_name_with_no_reference_close_is_dropped_silently_and_completely():
    rows = [("10:05", "A", 3.0, 200_000), ("10:05", "B", 3.0, 200_000)]
    assert seen(run("RTH", rows, {"A": 2.0})) == {"A": "10:06"}


def test_the_session_universe_uses_the_right_reference_per_block():
    b = {"0400_0930": bars([("04:05", "A", 3.0, 200_000)]),
         "0930_1600": bars([("10:05", "B", 3.0, 200_000)]),
         "1600_2000": bars([("17:05", "C", 3.0, 200_000)])}
    prior = pd.Series({"A": 2.0, "B": 2.0, "C": 2.99})     # C fails on yesterday
    today = pd.Series({"A": 2.99, "B": 2.99, "C": 2.0})    # C clears on today
    uni = D.session_universe_day(b, prior, today, DAY, CFG)
    assert dict(zip(uni["symbol"], uni["block"])) == {"A": "PRE", "B": "RTH", "C": "POST"}


def test_first_seen_is_the_first_tick_of_the_day_and_a_name_is_never_dropped():
    b = {"0400_0930": bars([("04:05", "A", 3.0, 200_000)]),
         "0930_1600": bars([("10:05", "A", 3.0, 200_000)]),
         "1600_2000": pd.DataFrame()}
    uni = D.session_universe_day(b, pd.Series({"A": 2.0}), pd.Series(dtype=float), DAY, CFG)
    assert len(uni) == 1
    row = uni.iloc[0]
    assert row["block"] == "PRE"
    assert row["first_seen"].tz_convert(ET).strftime("%H:%M") == "04:06"
    assert row["ticks_on"] > 1                    # it held a place in both blocks


# --- the control ----------------------------------------------------------------

def test_the_pre_block_reproduces_screen_sim_tick_for_tick():
    rows = []
    for i, sym in enumerate(("AAA", "BBB", "CCC", "DDD")):
        for k in range(20):
            rows.append((f"{4 + k // 6:02d}:{(5 + 7 * k) % 60:02d}", sym,
                         2.5 + 0.1 * i + 0.01 * k, 12_000 + 900 * k))
    b = bars(rows)
    prior = pd.Series({"AAA": 2.0, "BBB": 2.1, "CCC": 2.2, "DDD": 9.0})
    checked, bad, first_bad = D.pre_matches_screen_sim(b, prior, DAY, CFG)
    assert checked > 300 and bad == 0, first_bad


def test_the_control_can_fail():
    """A control that cannot fail is not a control. Screening the PRE block
    against a DIFFERENT reference must be caught."""
    b = bars([("04:05", "A", 3.0, 200_000)])
    prior = pd.Series({"A": 2.0})
    mine = list(D.sweep_block(b, pd.Series({"A": 9.0}), DAY, CFG, 60,
                              dtime(4, 0), dtime(9, 30)))
    theirs = list(S.sweep(b, prior, DAY, CFG, 60))
    assert [len(s) for _t, s in mine] != [len(s) for _t, s in theirs]


# --- the archive walk -----------------------------------------------------------

def test_a_day_missing_a_window_is_not_a_full_day(tmp_path):
    d = tmp_path / "XNAS.ITCH" / "ohlcv-1m"
    d.mkdir(parents=True)
    for suffix in ("0400_0930", "0930_1600", "1600_2000"):
        (d / f"2026-03-02_{suffix}.dbn.zst").write_bytes(b"")
    (d / "2026-03-03_0400_0930.dbn.zst").write_bytes(b"")
    got = D.day_slices(tmp_path, "XNAS.ITCH")
    full, partial = D.complete(got)
    assert full == ["2026-03-02"] and partial == ["2026-03-03"]


def test_the_deciding_universe_file_cannot_be_overwritten():
    with pytest.raises(SystemExit) as e:
        D.main(["--out", D.DECIDING_OUT])
    assert "decided on" in str(e.value)


def test_the_blocks_cover_the_day_without_gaps_or_overlaps():
    edges = [(s, e) for _n, s, e, _k, _x in D.BLOCKS]
    assert edges[0][0] == dtime(4, 0) and edges[-1][1] == dtime(20, 0)
    assert all(a[1] == b[0] for a, b in zip(edges, edges[1:]))
