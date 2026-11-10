"""common.forward_spend -- the shared US$5/month cap on Databento pulls for the two forward tests (W15-0069 sub 2)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common import forward_spend as FS


def _at(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


def test_a_pull_that_fits_under_the_cap_is_allowed_and_recorded(tmp_path):
    p = tmp_path / "s.json"
    FS.check("W16-0014", 1.25, now=_at(2026, 11, 7), path=p)
    FS.record("W16-0014", 1.25, files=2, now=_at(2026, 11, 7), path=p)
    st = FS.status(now=_at(2026, 11, 8), path=p)
    assert st["spent_usd"] == 1.25 and st["headroom_usd"] == 3.75 and st["month"] == "2026-11"


def test_the_cap_is_shared_by_both_tests(tmp_path):
    p = tmp_path / "s.json"
    FS.record("W16-0014", 3.00, files=1, now=_at(2026, 11, 3), path=p)
    with pytest.raises(FS.SpendRefused, match="STOP AND ASK BEN"):
        FS.check("W15-0037", 2.50, now=_at(2026, 11, 4), path=p)
    FS.check("W15-0037", 2.00, now=_at(2026, 11, 4), path=p)            # exactly $5.00 is allowed


def test_a_refusal_is_logged_and_nothing_is_recorded(tmp_path):
    p = tmp_path / "s.json"
    FS.record("W15-0037", 4.90, files=1, now=_at(2026, 11, 3), path=p)
    with pytest.raises(FS.SpendRefused):
        FS.check("W16-0014", 0.20, now=_at(2026, 11, 4), path=p)
    rec = FS.read(p)
    assert len(rec["entries"]) == 1
    assert rec["refusals"][-1]["test"] == "W16-0014" and "past the $5.00/month cap" in rec["refusals"][-1]["message"]
    assert FS.last_refusal(p)["test"] == "W16-0014"


def test_a_new_month_starts_from_zero(tmp_path):
    p = tmp_path / "s.json"
    FS.record("W16-0014", 4.99, files=1, now=_at(2026, 11, 30), path=p)
    FS.check("W16-0014", 4.00, now=_at(2026, 12, 1), path=p)
    assert FS.status(now=_at(2026, 12, 1), path=p)["spent_usd"] == 0


def test_a_free_pull_is_never_refused_even_when_the_month_is_full(tmp_path):
    p = tmp_path / "s.json"
    FS.record("W16-0014", 5.00, files=1, now=_at(2026, 11, 3), path=p)
    FS.check("W16-0014", 0.0, now=_at(2026, 11, 4), path=p)


@pytest.mark.parametrize("text,expected", [
    ("401 auth_authentication_failed", True),
    ("403 forbidden: no licence for GLBX.MDP3", True),
    ("Your subscription has ended", True),
    ("422 data_schema_not_fully_available", False),
    ("2026-11-06T13:04:07Z size 1403 bytes", False),
    ("symbology_invalid_request", False),
])
def test_access_refusals_are_told_apart_from_ordinary_errors(text, expected):
    assert FS.is_access_refusal(text) is expected


def test_raise_if_access_logs_and_scrubs_the_key(tmp_path):
    p = tmp_path / "s.json"
    with pytest.raises(FS.SpendRefused, match="STOP AND ASK BEN"):
        FS.raise_if_access("W16-0014", "pricing of 2026-11-06 ohlcv-1d", "403 forbidden db-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123", path=p)
    msg = FS.read(p)["refusals"][-1]["message"]
    assert "db-ABCDEF" not in msg and "redacted" in msg
    FS.raise_if_access("W16-0014", "pricing", "422 data_schema_not_fully_available", path=p)   # ordinary error: no raise


def test_the_default_path_follows_the_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("FORWARD_SPEND_PATH", str(tmp_path / "x.json"))
    FS.record("W16-0014", 0.5, files=1)
    assert (tmp_path / "x.json").exists()
