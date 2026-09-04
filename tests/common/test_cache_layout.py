#!/usr/bin/env python3
"""Cache windows: that writers and readers agree, and cannot be confused.

The two pulls in this repo are not interchangeable and neither is a superset
of the other -- backtest.py fetches two days ending 09:30 (prior-day warm-up,
stops at the open), data_ib.py fetches one day ending 20:00 (no prior day,
runs to the post-market close). Keyed on symbol and date alone, a frame
fetched for one would be served to the other as a truncated session that
looks like good data.

The failure this guards is silent in both directions: a reader pointed at the
wrong window finds an empty directory and reports "no cached bars" for data
that is present, and a reader pointed at a populated wrong window gets the
wrong bars. Neither raises.
"""
from pathlib import Path

from common import backtest as B
from common import data_ib as D
from common.cache_io import cache_path, window_dir, window_key


def test_window_key_shape():
    assert window_key("2 D", "0930") == "2d_to_0930"
    assert window_key("1 D", "2000") == "1d_to_2000"


def test_the_two_windows_never_collide():
    root = Path("bar_cache")
    assert window_dir(root, "2 D", "0930") != window_dir(root, "1 D", "2000")


def test_both_consumers_fetch_the_same_shared_window():
    """One pull serves both, which is the point -- it halves the IB budget.

    Validated against the live API on 2026-09-04 (common/probe_window.py):
    all four probed pairs matched bar-for-bar in both windows.
    """
    from common.cache_io import SHARED_DURATION, SHARED_END_HHMM
    assert B.HIST_DURATION == SHARED_DURATION == "3 D"
    assert D.HIST_DURATION == SHARED_DURATION
    assert window_key(SHARED_DURATION, SHARED_END_HHMM) == "3d_to_2000"


def test_each_consumer_still_slices_to_the_window_it_needs():
    """Fetching a superset is only safe because nothing consumes it whole."""
    assert B.HIST_SESSIONS == 2 and (B.HIST_END_HOUR, B.HIST_END_MINUTE) == (9, 30)
    assert D.HIST_SESSIONS == 1
    assert (D.SESSION_END_HOUR, D.SESSION_END_MINUTE) == (20, 0)


def test_backtest_runner_writes_into_its_window(tmp_path):
    class _IB:
        pass
    r = B.Runner(_IB(), tmp_path / "reports", tmp_path / "cache",
                 tmp_path / "state", "mcl")
    assert r.cache_dir.name == "3d_to_2000"
    assert r._cache_path("ABOS", "2026-09-02").name == "ABOS_2026-09-02.csv.gz"


def test_readers_point_at_the_window_their_writer_populates():
    """Every reader and writer now agrees on one directory.

    A mismatch here is silent in both directions: an empty directory reports
    "no cached bars" for data that is present, a populated wrong one returns
    the wrong bars.
    """
    from common.cache_io import SHARED_DURATION, SHARED_END_HHMM
    shared = window_dir(Path("bar_cache"), SHARED_DURATION, SHARED_END_HHMM)
    assert window_dir(Path("bar_cache"), B.HIST_DURATION, SHARED_END_HHMM) == shared
    assert window_dir(Path("bar_cache"), D.HIST_DURATION, D.HIST_END_HHMM) == shared


def test_under_seeded_frame_is_refused_rather_than_used():
    """The one way a superset can still go wrong: not reaching back far enough.

    That would hand a strategy less warm-up than it asked for and move its
    EMA-seeded indicators silently, so it is counted and refused.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from common.cache_io import check_sessions, slice_sessions
    et = ZoneInfo("America/New_York")
    df = _sessions_frame(["2026-03-13", "2026-03-16"])

    end = datetime(2026, 3, 16, 9, 30, tzinfo=et)
    assert check_sessions(df, end, 2) == 2
    only_one = slice_sessions(df, datetime(2026, 3, 16, 20, 0, tzinfo=et), 1)
    assert check_sessions(only_one, end, 2) == 1 < B.HIST_SESSIONS


def test_cache_files_are_gzipped():
    """Section 5 standardised on gzip; the EMA side used to write plain CSV."""
    assert cache_path(Path("x"), "ABOS", "2026-09-02").suffixes[-2:] == [".csv", ".gz"]


# --- shared superset window ------------------------------------------------

def _sessions_frame(days):
    """Extended-hours bars for the given dates only -- non-trading days simply
    have no bars, which is how the real cache looks."""
    import numpy as np
    import pandas as pd
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    idx = None
    for d in days:
        day = pd.date_range(f"{d} 04:00", f"{d} 19:59", freq="1min", tz=et)
        idx = day if idx is None else idx.append(day)
    return pd.DataFrame({"close": np.arange(len(idx), dtype=float)},
                        index=idx.tz_convert("UTC"))


def test_ib_duration_counts_trading_sessions_not_calendar_days():
    """Pinned against a live probe on 2026-09-04.

    A "2 D" request ending 09:30 returned 1290 bars = 960 (a full 04:00-20:00
    session) + 330 (04:00 to 09:30 exclusive). The earlier calendar-based
    slice dropped a whole 960-bar session when starting from a Monday, and
    added 630 bars when starting from a Friday. Weekends are where it broke.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from common.cache_io import slice_sessions
    et = ZoneInfo("America/New_York")
    # Wed Thu Fri Mon -- the weekend is absent, as it is in real data
    df = _sessions_frame(["2026-03-11", "2026-03-12", "2026-03-13", "2026-03-16"])

    mon0930 = datetime(2026, 3, 16, 9, 30, tzinfo=et)
    assert len(slice_sessions(df, mon0930, 2)) == 960 + 330
    fri0930 = datetime(2026, 3, 13, 9, 30, tzinfo=et)
    assert len(slice_sessions(df, fri0930, 2)) == 960 + 330
    assert len(slice_sessions(df, datetime(2026, 3, 16, 20, 0, tzinfo=et), 1)) == 960


def test_two_sessions_from_a_monday_reach_back_over_the_weekend():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from common.cache_io import slice_sessions
    et = ZoneInfo("America/New_York")
    df = _sessions_frame(["2026-03-12", "2026-03-13", "2026-03-16"])
    got = slice_sessions(df, datetime(2026, 3, 16, 9, 30, tzinfo=et), 2)
    dates = sorted({str(d) for d in got.index.tz_convert(et).date})
    assert dates == ["2026-03-13", "2026-03-16"], dates


def test_the_endpoint_bar_is_excluded():
    """The probe reported exactly one 'extra' bar per pair: the endpoint."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from common.cache_io import slice_sessions
    et = ZoneInfo("America/New_York")
    df = _sessions_frame(["2026-03-16"])
    got = slice_sessions(df, datetime(2026, 3, 16, 9, 30, tzinfo=et), 1)
    times = {t.strftime("%H:%M") for t in got.index.tz_convert(et).time}
    assert "09:29" in times and "09:30" not in times


def test_slicing_a_superset_reproduces_each_window_exactly():
    """The property the shared cache depends on."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from common.cache_io import slice_sessions
    et = ZoneInfo("America/New_York")
    df = _sessions_frame(["2026-03-11", "2026-03-12", "2026-03-13", "2026-03-16"])
    superset = slice_sessions(df, datetime(2026, 3, 16, 20, 0, tzinfo=et), 3)
    for end, n in [(datetime(2026, 3, 16, 9, 30, tzinfo=et), 2),
                   (datetime(2026, 3, 16, 20, 0, tzinfo=et), 1)]:
        assert slice_sessions(df, end, n).equals(slice_sessions(superset, end, n))


def test_longer_warmup_moves_the_indicators():
    """The reason slicing is mandatory rather than tidy.

    If this ever stops being true the strategies have lost their EMA memory,
    which would be a far bigger problem than the cache layout.
    """
    import numpy as np
    import pandas as pd
    from strategy.mcl import mcl as S

    rng = np.random.default_rng(3)
    n = 2000
    px = 4.0 * np.cumprod(1 + rng.uniform(-0.006, 0.007, n))
    idx = pd.date_range("2026-08-30 04:00", periods=n, freq="1min", tz="UTC")
    full = pd.DataFrame({"open": px, "high": px * 1.003, "low": px * 0.997,
                         "close": px,
                         "volume": rng.integers(2000, 9000, n).astype(float)},
                        index=idx)
    short = full.iloc[-800:]
    a = S.signals(short)["rsi"].astype(float)
    b = S.signals(full)["rsi"].astype(float).loc[short.index]
    assert float((a - b).abs().max()) > 1.0, \
        "a longer warm-up must change RSI, or slicing would be unnecessary"
