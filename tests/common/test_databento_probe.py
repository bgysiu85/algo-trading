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
