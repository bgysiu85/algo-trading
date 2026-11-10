"""common.forward_price_check -- the price-only Databento check (W15-0069 sub 1). It must never call get_range."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common import forward_price_check as PC
from common import forward_spend as FS


class _Meta:
    def __init__(self, end="2026-11-09T14:00:00Z", cost=0.02, fail=None):
        self.end, self.cost, self.fail, self.costs = end, cost, fail, []

    def get_dataset_range(self, dataset):
        if self.fail == "range":
            raise RuntimeError("403 forbidden: subscription ended")
        return {"start": "2010-06-06T00:00:00Z", "end": self.end}

    def get_cost(self, **kw):
        self.costs.append(kw)
        if self.fail and self.fail == kw["schema"]:
            raise RuntimeError("401 auth_authentication_failed")
        return self.cost

    def get_billable_size(self, **kw):
        return 12345


class _Client:
    def __init__(self, **k):
        self.metadata = _Meta(**k)

    @property
    def timeseries(self):
        raise AssertionError("price-only check must never touch timeseries / get_range")


def test_latest_complete_weekday_skips_weekends_and_unfinished_days():
    f = lambda s: PC.latest_complete_weekday(datetime.fromisoformat(s).replace(tzinfo=timezone.utc))   # noqa: E731
    assert f("2026-11-09T14:00:00") == "2026-11-06"          # Monday afternoon: Sunday/Saturday skipped -> Friday
    assert f("2026-11-06T13:00:00") == "2026-11-05"          # Friday 13:00Z: Friday not complete -> Thursday
    assert f("2026-11-07T00:00:00") == "2026-11-06"          # exactly midnight: Friday is complete


def test_all_three_pulls_are_priced_and_nothing_is_bought(tmp_path, capsys):
    c = _Client()
    rc = PC.run(c, out=tmp_path / "r.txt")
    assert rc == 0
    assert [k["schema"] for k in c.metadata.costs] == ["ohlcv-1h", "ohlcv-1m", "ohlcv-1d"]
    assert {k["symbols"][0] for k in c.metadata.costs} == {"CL.c.0", "NQ.v.0"}
    assert "can still price" in (tmp_path / "r.txt").read_text()


def test_an_access_refusal_returns_4_and_is_logged(tmp_path):
    rc = PC.run(_Client(fail="ohlcv-1m"), out=tmp_path / "r.txt")
    assert rc == FS.EXIT_CODE
    assert "STOP AND ASK BEN" in FS.last_refusal()["message"]


def test_a_refused_dataset_range_returns_4(tmp_path):
    assert PC.run(_Client(fail="range"), out=tmp_path / "r.txt") == FS.EXIT_CODE
