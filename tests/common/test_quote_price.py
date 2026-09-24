#!/usr/bin/env python3
"""quote_price: the windows are the right minutes, and nothing is bought by accident."""
from __future__ import annotations

import csv
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from common import quote_price as Q

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def rows():
    return [
        # MC5 bar stamped 04:05 closes 04:10 -- the order goes out at the CLOSE
        {"book": "mc5", "symbol": "AEHL", "date": "2026-09-18", "entry_et": "04:05", "bar_min": "5"},
        {"book": "mcl", "symbol": "AEHL", "date": "2026-09-18", "entry_et": "06:30", "bar_min": "1"},
        {"book": "mcl", "symbol": "DAIC", "date": "2026-09-18", "entry_et": "07:00", "bar_min": "1"},
        {"book": "mcl", "symbol": "OLDX", "date": "2025-01-10", "entry_et": "05:00", "bar_min": "1"},
    ]


def write_csv(tmp_path, rs):
    p = tmp_path / "entries.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rs[0].keys()))
        w.writeheader()
        w.writerows(rs)
    return p


class Meta:
    def __init__(self, usd=0.0, nbytes=1000, fail=False):
        self.usd, self.nbytes, self.fail, self.calls = usd, nbytes, fail, []

    def get_cost(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("schema not supported db-ABCDEFGHIJKLMNOPQRSTUVWX")
        return self.usd

    def get_billable_size(self, **kw):
        return self.nbytes


class FlakyMeta:
    """Fails get_cost the first `fail_times` calls, then succeeds -- models
    the transient '504 The remote gateway timed out' W02-0013 subitem 8 hit
    live on 2026-09-24 (1-2 of 1,888 windows), which cleared on the very
    next attempt."""
    def __init__(self, fail_times, usd=0.0, nbytes=1000):
        self.fail_times, self.usd, self.nbytes, self.calls = fail_times, usd, nbytes, 0

    def get_cost(self, **kw):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("504 The remote gateway timed out.")
        return self.usd

    def get_billable_size(self, **kw):
        return self.nbytes


class TS:
    def __init__(self):
        self.calls = []

    def get_range(self, path, **kw):
        self.calls.append(kw)
        with open(path, "wb") as fh:
            fh.write(b"x")


class Client:
    def __init__(self, meta):
        self.metadata, self.timeseries = meta, TS()


def test_signal_close_is_bar_start_plus_bar_length():
    """The H-R1 grain defect: without bar_min every MC5 quote is a bar early."""
    c = Q.signal_close("2026-09-18", "04:05", 5)
    assert c == datetime(2026, 9, 18, 4, 10, tzinfo=ET)
    assert Q.signal_close("2026-09-18", "04:05", 1) == datetime(2026, 9, 18, 4, 6, tzinfo=ET)


def test_one_window_per_symbol_day_spanning_both_books():
    ws = Q.windows(rows(), before=10, after=5)
    aehl = [w for w in ws if w.symbol == "AEHL"][0]
    assert aehl.entries == 2 and aehl.books == {"mc5", "mcl"}
    # first close 04:10 - 10 min, last close 06:31 + 5 min, in UTC (EDT = UTC-4)
    assert aehl.start == datetime(2026, 9, 18, 8, 0, tzinfo=UTC)
    assert aehl.end == datetime(2026, 9, 18, 10, 36, tzinfo=UTC)
    assert len(ws) == 3


def test_sample_is_reproducible_and_bounded():
    ws = Q.windows(rows())
    a, b = Q.sample(ws, 2), Q.sample(list(reversed(ws)), 2)
    assert [w.key for w in a] == [w.key for w in b]
    assert len(Q.sample(ws, 99)) == len(ws)


def test_request_is_one_symbol_over_the_window_only():
    """ALL_SYMBOLS or a whole day is how a cent becomes $1,500."""
    w = Q.windows(rows())[1]
    kw = Q.request("XNAS.ITCH", "mbp-1", w)
    assert kw["symbols"] == [w.symbol]
    assert kw["start"] == w.start.isoformat() and kw["end"] == w.end.isoformat()


def test_default_run_prices_only_and_never_downloads(tmp_path):
    p = write_csv(tmp_path, rows())
    c = Client(Meta())
    rc = Q.main(["--entries", str(p), "--report", str(tmp_path / "r.txt")],
                client=c, today=date(2026, 9, 19))
    assert rc == 0
    assert c.timeseries.calls == []
    txt = (tmp_path / "r.txt").read_text(encoding="utf-8")
    for ds, sc in Q.CANDIDATES:
        assert ds in txt and sc in txt


def test_older_than_the_plan_is_excluded_by_default(tmp_path):
    p = write_csv(tmp_path, rows())
    m = Meta()
    Q.main(["--entries", str(p), "--full", "--dataset", "XNAS.ITCH",
            "--schema", "mbp-1", "--report", str(tmp_path / "r.txt")],
           client=Client(m), today=date(2026, 9, 19))
    assert all(kw["symbols"] != ["OLDX"] for kw in m.calls)
    assert len(m.calls) == 2


def test_confirm_refuses_above_max_cost(tmp_path):
    p = write_csv(tmp_path, rows())
    c = Client(Meta(usd=0.01))
    rc = Q.main(["--entries", str(p), "--dataset", "XNAS.ITCH", "--schema",
                 "mbp-1", "--confirm", "--archive", str(tmp_path / "a"),
                 "--report", str(tmp_path / "r.txt")],
                client=c, today=date(2026, 9, 19))
    assert rc == 2
    assert c.timeseries.calls == []
    assert "REFUSED" in (tmp_path / "r.txt").read_text(encoding="utf-8")


def test_confirm_refuses_when_any_window_failed_to_price(tmp_path):
    p = write_csv(tmp_path, rows())
    c = Client(Meta(fail=True))
    rc = Q.main(["--entries", str(p), "--dataset", "XNAS.ITCH", "--schema",
                 "mbp-1", "--confirm", "--archive", str(tmp_path / "a"),
                 "--report", str(tmp_path / "r.txt")],
                client=c, today=date(2026, 9, 19))
    assert rc == 2 and c.timeseries.calls == []


def test_price_retries_a_transient_failure_then_succeeds():
    """W02-0013 subitem 8, 2026-09-24: don't refuse a whole 1,888-window run
    over one gateway blip that clears on retry."""
    m = FlakyMeta(fail_times=2)
    c = Client(m)
    ws = Q.windows(rows())[:1]
    pr = Q.price(c, "XNAS.ITCH", "mbp-1", ws, sleep=lambda s: None)
    assert pr.failed == 0 and pr.n == 1
    assert m.calls == 3          # 2 failures + the try that succeeded


def test_price_still_fails_a_window_that_never_recovers():
    """Retrying must not turn a real, persistent failure into a silent pass."""
    m = FlakyMeta(fail_times=99)
    c = Client(m)
    ws = Q.windows(rows())[:1]
    pr = Q.price(c, "XNAS.ITCH", "mbp-1", ws, sleep=lambda s: None)
    assert pr.failed == 1 and pr.n == 0
    assert m.calls == 3          # gives up after RETRIES attempts, not forever


def test_price_retry_wait_is_between_attempts_only_not_after_the_last():
    waits = []
    m = FlakyMeta(fail_times=99)
    Q.price(Client(m), "XNAS.ITCH", "mbp-1", Q.windows(rows())[:1],
            sleep=waits.append)
    assert waits == [Q.RETRY_WAIT, Q.RETRY_WAIT]   # 3 attempts -> 2 gaps, no trailing wait


def test_confirm_pulls_free_windows_and_skips_what_is_on_disk(tmp_path):
    p = write_csv(tmp_path, rows())
    c = Client(Meta(usd=0.0))
    args = ["--entries", str(p), "--dataset", "XNAS.ITCH", "--schema", "mbp-1",
            "--confirm", "--archive", str(tmp_path / "a"),
            "--report", str(tmp_path / "r.txt")]
    assert Q.main(args, client=c, today=date(2026, 9, 19)) == 0
    assert len(c.timeseries.calls) == 2
    f = tmp_path / "a" / "XNAS.ITCH" / "mbp-1" / "windows" / "2026-09-18" / "AEHL.dbn.zst"
    assert f.exists()
    assert (tmp_path / "a" / "XNAS.ITCH" / "mbp-1" / "windows" / "manifest.json").exists()
    c2 = Client(Meta(usd=0.0))
    assert Q.main(args, client=c2, today=date(2026, 9, 19)) == 0
    assert c2.timeseries.calls == []


def test_the_key_never_reaches_the_report(tmp_path):
    from common.databento_fetch import _scrub
    p = write_csv(tmp_path, rows())
    Q.main(["--entries", str(p), "--report", str(tmp_path / "r.txt")],
           client=Client(Meta(fail=True)), today=date(2026, 9, 19))
    assert "ABCDEFGHIJKLMNOPQRSTUVWX" not in (tmp_path / "r.txt").read_text(encoding="utf-8")
    pr = Q.price(Client(Meta(fail=True)), "X", "y", Q.windows(rows()), scrub=_scrub)
    assert pr.first_error and "ABCDEFGHIJKLMNOPQRSTUVWX" not in pr.first_error


def test_full_and_confirm_need_one_named_tape():
    with pytest.raises(SystemExit):
        Q.parse(["--full"])
    with pytest.raises(SystemExit):
        Q.parse(["--confirm", "--dataset", "XNAS.ITCH"])


def test_mbp10_is_accepted_like_any_other_schema_no_special_casing(tmp_path):
    """W02-0013 step 7 needs XNAS.ITCH mbp-10 for the live H-L2 pull.
    quote_price is schema-agnostic already (CANDIDATES is only the sample
    menu; --full/--confirm take any --dataset/--schema pair) -- this locks
    that in rather than trusting it stays true by accident."""
    p = write_csv(tmp_path, rows())
    c = Client(Meta(usd=0.0))
    args = ["--entries", str(p), "--dataset", "XNAS.ITCH", "--schema", "mbp-10",
            "--confirm", "--archive", str(tmp_path / "a"),
            "--report", str(tmp_path / "r.txt")]
    assert Q.main(args, client=c, today=date(2026, 9, 19)) == 0
    assert len(c.timeseries.calls) == 2
    f = tmp_path / "a" / "XNAS.ITCH" / "mbp-10" / "windows" / "2026-09-18" / "AEHL.dbn.zst"
    assert f.exists()
