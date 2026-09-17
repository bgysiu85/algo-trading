#!/usr/bin/env python3
"""Chunking the universe pull.

Chunks decide two things that are expensive to get wrong: what is re-fetched
after a failure, and whether two chunks can cover the same bars twice.
"""
from __future__ import annotations

from pathlib import Path

from common import databento_universe as U

# --- per-weekday windowed chunks --------------------------------------------
# Added 2026-09-09 for the screener simulation, which needs 04:00-09:30 ET and
# nothing else. Month chunks cannot express a time of day: a request from 04:00
# on the 1st to 09:30 on the 31st spans the whole 24-hour tape in between.

def test_a_windowed_chunk_covers_one_day_not_a_month():
    got = U.day_chunks("2026-08-03", "2026-08-08", "04:00-09:30")
    assert len(got) == 5, "Mon-Fri"
    _, lo, hi = got[0]
    assert lo == "2026-08-03T08:00:00" and hi == "2026-08-03T13:30:00"


def test_weekends_are_not_requested():
    """Every chunk costs a metadata round trip, and a Saturday buys nothing."""
    labels = [l for l, _, _ in U.day_chunks("2026-08-08", "2026-08-11",
                                            "04:00-09:30")]
    assert labels == ["2026-08-10_0400_0930"], "Sat and Sun dropped"


def test_the_label_carries_the_window():
    """THE CORRUPTION THIS PREVENTS. Chunks are skipped when the file already
    exists, so without the window in the name a later pull covering different
    hours would silently reuse the old bars -- and produce a plausible screen
    rather than an error."""
    a = U.day_chunks("2026-08-03", "2026-08-04", "04:00-09:30")[0][0]
    b = U.day_chunks("2026-08-03", "2026-08-04", "04:00-04:30")[0][0]
    assert a != b
    assert a.startswith("2026-08-03") and b.startswith("2026-08-03")


def test_windowed_chunks_never_overlap():
    """dbn_io.daily_frame warns on duplicate symbol-date rows precisely because
    an overlapping scheme would double volume and corrupt every relative-volume
    figure downstream."""
    got = U.day_chunks("2026-08-03", "2026-08-15", "04:00-09:30")
    for (_, _, hi), (_, lo2, _) in zip(got, got[1:]):
        assert hi <= lo2


def test_the_window_follows_daylight_saving():
    """A fixed offset would pull the wrong hours for five months of the year
    and return plausible bars rather than an error."""
    summer = U.day_chunks("2026-08-03", "2026-08-04", "04:00-09:30")[0][1]
    winter = U.day_chunks("2026-01-05", "2026-01-06", "04:00-09:30")[0][1]
    assert summer.endswith("T08:00:00") and winter.endswith("T09:00:00")


def test_no_window_still_chunks_by_month():
    """The daily archive was pulled this way and must stay reproducible."""
    got = U.month_chunks("2026-07-01", "2026-09-01")
    assert [l for l, _, _ in got] == ["2026-07", "2026-08"]


# --- a partial chunk is not a present chunk ---------------------------------

def test_a_chunk_ending_well_before_the_window_is_flagged_short(tmp_path,
                                                                monkeypatch):
    """The September daily chunk was pulled on the 5th, held four sessions, and
    was skipped by every run afterwards. screen_sim then dropped four sessions
    for having no prior close while their minute slices sat on disk."""
    import common.databento_universe as U
    f = tmp_path / "2026-09.dbn.zst"
    f.write_bytes(b"x")
    monkeypatch.setattr(U, "chunk_last_bar", lambda p: "2026-09-04")
    assert U.chunk_ends_before(f, "2026-10-01")


def test_a_complete_chunk_is_not_re_bought(tmp_path, monkeypatch):
    import common.databento_universe as U
    f = tmp_path / "2026-08.dbn.zst"
    f.write_bytes(b"x")
    monkeypatch.setattr(U, "chunk_last_bar", lambda p: "2026-08-31")
    assert not U.chunk_ends_before(f, "2026-09-01")


def test_a_holiday_at_the_end_does_not_trigger_a_re_buy(tmp_path, monkeypatch):
    """Two days of slack, because the true last session before an end date
    depends on market holidays this cannot know."""
    import common.databento_universe as U
    f = tmp_path / "2026-12.dbn.zst"
    f.write_bytes(b"x")
    monkeypatch.setattr(U, "chunk_last_bar", lambda p: "2026-12-30")
    assert not U.chunk_ends_before(f, "2027-01-01")


def test_an_unreadable_chunk_is_never_re_bought(tmp_path, monkeypatch):
    """This decides whether to spend money. A parsing error must not become a
    purchase."""
    import common.databento_universe as U
    f = tmp_path / "2026-09.dbn.zst"
    f.write_bytes(b"not a dbn file")
    monkeypatch.setattr(U, "chunk_last_bar", lambda p: None)
    assert not U.chunk_ends_before(f, "2030-01-01")


def test_chunk_last_bar_swallows_a_bad_file_rather_than_raising(tmp_path):
    import common.databento_universe as U
    f = tmp_path / "junk.dbn.zst"
    f.write_bytes(b"not a dbn file")
    assert U.chunk_last_bar(f) is None


# --- the newest available day was unreachable -------------------------------

class _RangeClient:
    """A client whose dataset ends on a known day."""

    def __init__(self, end="2026-09-14", start="2024-07-01"):
        self._r = {"start": start, "end": end}
        outer = self

        class metadata:
            @staticmethod
            def get_dataset_range(ds):
                return outer._r
        self.metadata = metadata


def test_the_datasets_last_available_day_can_actually_be_pulled():
    """THE DEFECT: the clamp treated `avail_end` as an achievable end while
    both chunkers take `end` EXCLUSIVE, so asking for the newest session gave
    start == end, zero chunks, and a report reading "to download 0 / $0.0000"
    -- indistinguishable from "everything is already on disk". The most recent
    day was unreachable and nothing said so."""
    from common.databento_universe import clamp_to_dataset, day_chunks
    s, e, notes = clamp_to_dataset(_RangeClient(), "XNAS.BASIC",
                                   "2026-09-14", "2026-09-15")
    chunks = day_chunks(s, e, "04:00-09:30")
    assert [c[0] for c in chunks] == ["2026-09-14_0400_0930"], (
        "the dataset's last day still cannot be pulled")
    assert any("exclusive" in n for n in notes), (
        "the clamp must say which convention its end is in")


def test_the_clamp_overruns_rather_than_falls_short():
    """Asymmetric by design: a day past the end costs one free metadata call
    and falls out as `empty (holiday/no data)`. A day short is a silent hole."""
    from common.databento_universe import clamp_to_dataset
    _s, e, _n = clamp_to_dataset(_RangeClient(end="2026-09-14"), "X",
                                 "2026-09-01", "2026-12-31")
    assert e == "2026-09-15", "clamped end must be exclusive of the last day"


def test_a_start_before_the_dataset_is_still_clamped_forward():
    from common.databento_universe import clamp_to_dataset
    s, _e, notes = clamp_to_dataset(_RangeClient(start="2024-07-01"), "X",
                                    "2020-01-01", "2026-09-14")
    assert s == "2024-07-01" and any("before" in n for n in notes)


def test_a_same_day_range_really_does_cover_nothing():
    assert U.day_chunks("2026-09-14", "2026-09-14", "04:00-09:30") == []
    assert U.month_chunks("2026-09-01", "2026-09-01") == []


def test_a_window_covering_no_days_is_refused_not_reported_as_done(monkeypatch,
                                                                   tmp_path):
    """A REQUEST THAT COVERS NOTHING IS NOT A SUCCESSFUL NO-OP.

    `--end` is EXCLUSIVE, so --start D --end D covers zero days. That printed
    the same "to download 0 / ESTIMATED COST $0.0000" as a pull with nothing
    left to fetch, and exited 0. The two look identical and mean opposite
    things.

    Driven through main() rather than asserted against the source: the first
    version of this test looked for the string "NOTHING TO DO" in the file,
    which a mutation replacing the guard with `if False:` left untouched.
    """
    import pytest

    class Fake:
        class metadata:
            @staticmethod
            def get_dataset_range(ds):
                return {"start": "2024-07-01", "end": "2026-09-14"}

    class FakeDB:
        @staticmethod
        def Historical(key):
            return Fake()

    monkeypatch.setattr(U, "require_databento", lambda: FakeDB)
    monkeypatch.setattr(U, "_key", lambda: "x", raising=False)
    with pytest.raises(SystemExit) as ex:
        U.main(["--dataset", "XNAS.BASIC", "--schema", "ohlcv-1m",
                "--window", "04:00-09:30", "--start", "2026-09-14",
                "--end", "2026-09-14", "--archive", str(tmp_path),
                "--confirm"])
    msg = str(ex.value)
    assert "NOTHING TO DO" in msg
    assert "EXCLUSIVE" in msg, "the message must say which end is exclusive"


def test_a_chunk_whose_estimate_failed_is_not_a_silent_success(monkeypatch,
                                                               tmp_path):
    """THE SAME DEFECT ONE LEVEL DOWN. A chunk whose estimate raised was
    counted in none of the four outcome buckets, printed once mid-loop, and
    the run exited 0 reporting "$0.0000" -- so a window reaching past what the
    dataset holds looked exactly like a pull with nothing left to fetch.
    """
    import pytest

    class Fake:
        class metadata:
            @staticmethod
            def get_dataset_range(ds):
                return {"start": "2024-07-01", "end": "2026-09-14"}

            @staticmethod
            def get_cost(**kw):
                raise RuntimeError(
                    "422 data_end_after_available_end: has data available up "
                    "to '2026-09-14 12:30:00+00:00'")

            @staticmethod
            def get_billable_size(**kw):
                raise RuntimeError("422 data_end_after_available_end")

    monkeypatch.setattr(U, "require_databento", lambda: type(
        "DB", (), {"Historical": staticmethod(lambda k: Fake())}))
    monkeypatch.setattr(U, "_key", lambda: "x", raising=False)
    rc = U.main(["--dataset", "XNAS.BASIC", "--schema", "ohlcv-1m",
                 "--window", "04:00-09:30", "--start", "2026-09-14",
                 "--end", "2026-09-15", "--archive", str(tmp_path),
                 "--confirm"])
    assert rc != 0, ("every chunk failed to price and the run still exited 0 "
                     "-- indistinguishable from having nothing to fetch")


def test_the_estimate_failure_count_is_in_the_summary(capsys, monkeypatch,
                                                      tmp_path):
    """Printed once mid-loop is not reported: the summary is what a person
    reads, and it listed four outcomes that this one belongs to none of."""
    import pytest

    class Fake:
        class metadata:
            @staticmethod
            def get_dataset_range(ds):
                return {"start": "2024-07-01", "end": "2026-09-14"}

            @staticmethod
            def get_cost(**kw):
                raise RuntimeError("422 data_end_after_available_end")

            @staticmethod
            def get_billable_size(**kw):
                raise RuntimeError("422 data_end_after_available_end")

    monkeypatch.setattr(U, "require_databento", lambda: type(
        "DB", (), {"Historical": staticmethod(lambda k: Fake())}))
    monkeypatch.setattr(U, "_key", lambda: "x", raising=False)
    U.main(["--dataset", "XNAS.BASIC", "--schema", "ohlcv-1m",
            "--window", "04:00-09:30", "--start", "2026-09-14",
            "--end", "2026-09-15", "--archive", str(tmp_path), "--confirm"])
    out = capsys.readouterr().out
    assert "ESTIMATE FAILED          : 1" in out
    # and the live-session case is explained rather than left as a 422
    assert "TIMESTAMP, not a date" in out
    assert "different label" in out, (
        "a narrower --window is fetched under a label window_slices() does "
        "not glob, and that trap has to be named")


def test_the_degraded_day_list_was_not_renamed_out_from_under_itself():
    """`bad` already meant per-chunk degraded days inside the download loop.
    A second `bad` for failed estimates would have shadowed it and corrupted
    the manifest's `degraded_days` silently."""
    src = Path("common/databento_universe.py").read_text(encoding="utf-8")
    assert '"degraded_days": bad,' in src
    assert "unpriced.append" in src


# --- a failed chunk does not take the pull down -------------------------------

def test_fetch_chunk_retries_and_then_gives_up_without_raising(tmp_path, capsys):
    from common import databento_universe as U

    class Flaky:
        def __init__(self, fail_times):
            self.calls, self.fail_times = 0, fail_times

        class timeseries:  # noqa: N801
            pass

    f = Flaky(2)

    def get_range(**kw):
        f.calls += 1
        if f.calls <= f.fail_times:
            raise RuntimeError("Error streaming response: Response ended prematurely")
        open(kw["path"], "wb").write(b"ok")
    f.timeseries.get_range = staticmethod(get_range)
    tmp = tmp_path / "x.partial"
    assert U.fetch_chunk(f, "XNAS.ITCH", "status", "2026-03-01", "2026-04-01", tmp, "2026-03")
    assert f.calls == 3 and tmp.read_bytes() == b"ok"

    g = Flaky(99)
    g.timeseries.get_range = staticmethod(get_range.__wrapped__ if hasattr(get_range, "__wrapped__") else
                                          (lambda **kw: (_ for _ in ()).throw(RuntimeError("down"))))
    assert not U.fetch_chunk(g, "XNAS.ITCH", "status", "2026-03-01", "2026-04-01", tmp_path / "y.partial", "2026-03")
    assert "FAILED after 3 attempts" in capsys.readouterr().out


def test_discard_partial_survives_a_locked_file(tmp_path, monkeypatch, capsys):
    from common import databento_universe as U
    p = tmp_path / "z.partial"
    p.write_bytes(b"x")
    calls = {"n": 0}
    real_unlink = type(p).unlink

    def locked(self, missing_ok=False):
        calls["n"] += 1
        raise PermissionError("in use")
    monkeypatch.setattr(type(p), "unlink", locked)
    monkeypatch.setattr("time.sleep", lambda s: None)
    U.discard_partial(p, "2026-03")          # must not raise
    assert calls["n"] == 5
    assert "could not remove z.partial" in capsys.readouterr().out
    monkeypatch.setattr(type(p), "unlink", real_unlink)
