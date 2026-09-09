#!/usr/bin/env python3
"""The size probe exists to catch an estimate nobody can sanity-check."""
from __future__ import annotations

import pytest

from common import databento_probe as P


class FakeMeta:
    def __init__(self, mb, usd=0.0):
        self.mb, self.usd, self.calls = mb, usd, []

    def get_billable_size(self, **kw):
        self.calls.append(kw)
        return int(self.mb * 1e6)

    def get_cost(self, **kw):
        return self.usd


class FakeClient:
    def __init__(self, meta):
        self.metadata = meta


def test_one_day_is_priced_over_exactly_one_day():
    """An off-by-one on `end` doubles every figure the check is based on."""
    m = FakeMeta(1234.5)
    mb, usd = P.size_one_day(FakeClient(m), "EQUS.SUMMARY", "statistics",
                             "2026-08-04")
    kw = m.calls[0]
    assert kw["start"] == "2026-08-04" and kw["end"] == "2026-08-05"
    assert kw["symbols"] == "ALL_SYMBOLS"
    assert mb == pytest.approx(1234.5)
    assert usd == 0.0


def test_a_bare_dataset_is_rejected_rather_than_guessed():
    with pytest.raises(SystemExit, match="DATASET:SCHEMA"):
        P.parse_size_args(["EQUS.SUMMARY"])


def test_pairs_are_split_and_the_dataset_upcased():
    assert P.parse_size_args(["equs.summary:statistics"]) == [
        ("EQUS.SUMMARY", "statistics")]


def test_one_dataset_failing_does_not_stop_the_others(capsys):
    """The probe is run precisely when something looks wrong, so a schema the
    account cannot query must report and continue rather than end the run."""
    class Flaky(FakeMeta):
        def get_billable_size(self, **kw):
            if kw["schema"] == "statistics":
                raise RuntimeError("no entitlement")
            return int(10 * 1e6)

    P.probe_sizes(FakeClient(Flaky(0)), "2026-08-04",
                  [("EQUS.SUMMARY", "statistics"), ("EQUS.SUMMARY", "ohlcv-1d")])
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "ohlcv-1d" in out


def test_the_probe_writes_its_result_to_a_file(tmp_path):
    """The figure this decision turns on must not live only in scrollback.
    The first version printed and nothing else, so the one number worth having
    had to be copied back by hand -- which is what report_io exists to stop."""
    out = tmp_path / "size_probe.txt"
    P.probe_sizes(FakeClient(FakeMeta(4400.0)), "2026-08-04",
                  [("EQUS.SUMMARY", "statistics")], out)
    text = out.read_text(encoding="utf-8")
    assert "4,400.0" in text
    assert "92,400" in text          # the x21 month column
    assert "# generated" in text


def test_a_failure_still_reaches_the_file(tmp_path):
    """A probe that failed is itself the finding -- an empty or absent report
    is indistinguishable from one nobody ran."""
    class Dead(FakeMeta):
        def get_billable_size(self, **kw):
            raise RuntimeError("401 auth_authentication_failed")

    out = tmp_path / "size_probe.txt"
    P.probe_sizes(FakeClient(Dead(0)), "2026-08-04",
                  [("EQUS.SUMMARY", "statistics")], out)
    assert "FAILED" in out.read_text(encoding="utf-8")


# --- pricing an intraday window ---------------------------------------------
# Added 2026-09-09 for the screener simulation, which needs only the pre-market
# slice. Pricing a whole day overstates that by better than an order of
# magnitude, which is enough to talk someone out of an affordable pull.

from datetime import datetime, timezone          # noqa: E402
from zoneinfo import ZoneInfo                    # noqa: E402

ET_ = ZoneInfo("America/New_York")


def test_no_window_still_prices_a_whole_calendar_day():
    """The existing behaviour, unchanged, or every earlier size probe in the
    reports directory silently stops being comparable."""
    assert P.day_bounds("2026-08-04") == ("2026-08-04", "2026-08-05")


def test_a_window_is_read_in_ET_and_sent_as_UTC():
    """Databento takes UTC. Every session boundary in this project is stated in
    ET, and converting by hand is how a DST week ends up an hour out."""
    start, end = P.day_bounds("2026-08-04", "04:00-04:30")
    assert start == "2026-08-04T08:00:00", "04:00 ET in August is 08:00 UTC"
    assert end == "2026-08-04T08:30:00"


def test_the_conversion_follows_daylight_saving_rather_than_a_fixed_offset():
    """August is EDT (UTC-4), January is EST (UTC-5). A hard-coded offset would
    price the wrong half-hour for five months of every year -- and would return
    a plausible number rather than an error."""
    summer, _ = P.day_bounds("2026-08-04", "04:00-04:30")
    winter, _ = P.day_bounds("2026-01-14", "04:00-04:30")
    assert summer.endswith("T08:00:00")
    assert winter.endswith("T09:00:00")


def test_a_window_covering_the_screen_is_a_small_fraction_of_the_day():
    """Sanity on the arithmetic itself: 30 minutes is 30 minutes."""
    s, e = P.day_bounds("2026-08-04", "04:00-04:30")
    span = (datetime.fromisoformat(e).replace(tzinfo=timezone.utc)
            - datetime.fromisoformat(s).replace(tzinfo=timezone.utc))
    assert span.total_seconds() == 1800


def test_a_malformed_window_is_refused_rather_than_guessed():
    """A window silently read as a whole day would price the pull at 20x and
    the error would appear as a budget decision, not as a bug."""
    import pytest
    with pytest.raises(SystemExit):
        P.day_bounds("2026-08-04", "0400")


def test_the_window_reaches_the_billing_call(tmp_path):
    """A window that is parsed correctly and then not forwarded prices the
    whole day anyway -- and reports the window in its own header while doing
    it, which is worse than not offering the option at all."""
    m = FakeMeta(1.0)
    P.probe_sizes(FakeClient(m), "2026-08-04", [("XNAS.BASIC", "ohlcv-1m")],
                  out=str(tmp_path / "r.txt"), window="04:00-04:30")
    kw = m.calls[0]
    assert kw["start"] == "2026-08-04T08:00:00"
    assert kw["end"] == "2026-08-04T08:30:00"


def test_the_report_says_which_window_it_priced(tmp_path):
    """The figure decides a spend. A report that does not name its window
    cannot be compared with the next one."""
    p = tmp_path / "r.txt"
    P.probe_sizes(FakeClient(FakeMeta(1.0)), "2026-08-04",
                  [("XNAS.BASIC", "ohlcv-1m")], out=str(p),
                  window="04:00-04:30")
    text = p.read_text()
    assert "04:00-04:30" in text and "ET" in text
