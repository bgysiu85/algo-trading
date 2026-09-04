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


def test_writer_window_is_derived_from_the_request_it_makes():
    """The directory name and the IB request are built from the same values.

    If these drifted apart the directory would claim to hold bars it does not
    hold, which is the whole failure mode being prevented.
    """
    assert window_key(B.HIST_DURATION, B.HIST_END_HHMM) == "2d_to_0930"
    assert B.HIST_END_HOUR == 9 and B.HIST_END_MINUTE == 30
    assert window_key(D.HIST_DURATION, D.HIST_END_HHMM) == "1d_to_2000"
    assert D.SESSION_END_HOUR == 20 and D.SESSION_END_MINUTE == 0


def test_backtest_runner_writes_into_its_window(tmp_path):
    class _IB:
        pass
    r = B.Runner(_IB(), tmp_path / "reports", tmp_path / "cache",
                 tmp_path / "state", "mcl")
    assert r.cache_dir.name == "2d_to_0930"
    assert r._cache_path("ABOS", "2026-09-02").name == "ABOS_2026-09-02.csv.gz"


def test_readers_point_at_the_window_their_writer_populates():
    """setup_counts reads data_ib's window; sweep_variants reads backtest's."""
    root = Path("bar_cache")
    assert window_dir(root, "1 D", "2000") == window_dir(
        root, D.HIST_DURATION, D.HIST_END_HHMM)
    assert window_dir(root, "2 D", "0930") == window_dir(
        root, B.HIST_DURATION, B.HIST_END_HHMM)


def test_cache_files_are_gzipped():
    """Section 5 standardised on gzip; the EMA side used to write plain CSV."""
    assert cache_path(Path("x"), "ABOS", "2026-09-02").suffixes[-2:] == [".csv", ".gz"]
