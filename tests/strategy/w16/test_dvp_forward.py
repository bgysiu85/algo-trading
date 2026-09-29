"""strategy.w16.dvp_forward -- the weekly W16-0014 forward scorer (Board
W16-0014 subitem 2). A fake client stands in for databento (modelled on
tests/strategy/w16/test_fetch_trades.py), and the ledger path is redirected
into tmp_path so no test ever touches the real w16_dvp_forward_ledger.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_drift_vwap import trend_session  # noqa: E402

import strategy.w16.dvp_forward as F
import strategy.w16.runner as R


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "LEDGER_PATH", tmp_path / "w16_dvp_forward_ledger.json")


class _Data:
    def __init__(self, log):
        self.log = log

    def to_file(self, path):
        self.log.append(("to_file", str(path)))
        with open(path, "wb") as fh:
            fh.write(b"DBN-fake")


class _Meta:
    def __init__(self, cost, log, dataset_end="2026-10-10T00:00:00Z"):
        self.cost, self.log, self.dataset_end = cost, log, dataset_end

    def get_dataset_range(self, dataset):
        self.log.append(("range", dataset))
        return {"start": "2010-06-06T00:00:00Z", "end": self.dataset_end}

    def get_cost(self, **kw):
        self.log.append(("cost", kw))
        return self.cost

    def get_billable_size(self, **kw):
        return 100_000


class _TS:
    def __init__(self, log):
        self.log = log

    def get_range(self, **kw):
        self.log.append(("get_range", kw))
        return _Data(self.log)


class FakeClient:
    def __init__(self, cost=0.05, dataset_end="2026-10-10T00:00:00Z"):
        self.log = []
        self.metadata = _Meta(cost, self.log, dataset_end)
        self.timeseries = _TS(self.log)

    def calls(self, name):
        return [c for c in self.log if c[0] == name]


def _pass_gate(monkeypatch):
    """Bypass the real G1 read-back (already covered by test_readback.py)
    so scoring tests exercise the frozen-rule call and the ledger, not the
    daily-close comparison a second time."""
    monkeypatch.setattr(F, "read_back", lambda archive, days: {
        "passed": True, "pass_threshold_pct": 0.99,
        "daily_agreement": {"n_within_tol": len(days), "n_compared": len(days), "pct_within_tol": 1.0},
    })


def _synthetic_bars(monkeypatch, dates):
    dfs = [trend_session(d, direction=("long" if i % 2 == 0 else "short"), slope=1.0,
                         dip_windows=["10:35", "12:35"], dip_size=6.0)
          for i, d in enumerate(dates)]
    df = pd.concat(dfs).sort_index()
    monkeypatch.setattr(F, "_load_1m_from_days", lambda archive, days: df)
    return df


# --- candidate_dates ---------------------------------------------------

def test_candidate_dates_starts_at_forward_start_and_excludes_today():
    days = F.candidate_dates(F._default_ledger(), as_of="2026-10-01")
    assert days[0] == F.FORWARD_START
    assert "2026-10-01" not in days               # "today" is never scored
    assert days[-1] == "2026-09-30"


def test_candidate_dates_excludes_already_scored():
    ledger = F._default_ledger()
    ledger["scored_dates"] = ["2026-09-29", "2026-09-30"]
    days = F.candidate_dates(ledger, as_of="2026-10-02")
    assert "2026-09-29" not in days and "2026-09-30" not in days
    assert "2026-10-01" in days


def test_candidate_dates_never_exceeds_forward_end():
    # FORWARD_END (2027-03-26, per REGISTERED_w16_dvp_forward.md sec 1) is
    # itself Good Friday, an XNYS holiday -- so the last day this ever
    # returns is 2027-03-25, the last real trading day at or before it.
    # See the FORWARD_END comment in strategy/w16/dvp_forward.py.
    days = F.candidate_dates(F._default_ledger(), as_of="2027-06-01")
    assert days[-1] == "2027-03-25"
    assert all(d <= F.FORWARD_END for d in days)
    assert F.FORWARD_END not in days


def test_candidate_dates_excludes_weekends():
    days = F.candidate_dates(F._default_ledger(), as_of="2026-10-06")
    assert "2026-10-03" not in days           # Saturday
    assert "2026-10-04" not in days           # Sunday


# --- pricing / pull guards (mirrors test_fetch_trades.py) --------------

def test_estimate_only_never_downloads(tmp_path):
    c = FakeClient()
    rc = F.main(["--archive", str(tmp_path), "--as-of", "2026-10-01", "--out", str(tmp_path / "r")], client=c)
    assert rc == 0
    assert c.calls("cost")
    assert not c.calls("get_range")
    assert not F.LEDGER_PATH.exists()


def test_confirm_pulls_both_schemas_for_every_due_day(tmp_path, monkeypatch):
    _pass_gate(monkeypatch)
    _synthetic_bars(monkeypatch, ["2026-09-29"])
    c = FakeClient()
    rc = F.main(["--archive", str(tmp_path), "--as-of", "2026-09-30", "--confirm",
                "--out", str(tmp_path / "r")], client=c)
    assert rc == 0
    # 2026-09-29 is the only day due before 2026-09-30
    assert len(c.calls("get_range")) == 2   # ohlcv-1m + ohlcv-1d
    for schema in F.SCHEMAS:
        assert F.day_path(tmp_path, schema, "2026-09-29").exists()


def test_request_scope_is_pinned(tmp_path):
    c = FakeClient()
    F.main(["--archive", str(tmp_path), "--as-of", "2026-09-30", "--out", str(tmp_path / "r")], client=c)
    kws = [k for _, k in c.calls("cost")]
    assert len(kws) == 2
    for k in kws:
        assert k["dataset"] == "GLBX.MDP3"
        assert k["symbols"] == ["NQ.v.0"]
        assert k["stype_in"] == "continuous"
    assert {k["schema"] for k in kws} == {"ohlcv-1m", "ohlcv-1d"}


def test_files_land_under_their_own_subtree(tmp_path, monkeypatch):
    _pass_gate(monkeypatch)
    _synthetic_bars(monkeypatch, ["2026-09-29"])
    c = FakeClient()
    F.main(["--archive", str(tmp_path), "--as-of", "2026-09-30", "--confirm",
           "--out", str(tmp_path / "r")], client=c)
    p = F.day_path(tmp_path, "ohlcv-1m", "2026-09-29")
    assert p.parent.name == "ohlcv-1m"
    assert p.parent.parent.name == "w16_dvp_forward"
    assert p.parent.parent.parent.name == "GLBX.MDP3"


def test_days_already_on_disk_are_never_repriced(tmp_path, monkeypatch):
    _pass_gate(monkeypatch)
    _synthetic_bars(monkeypatch, ["2026-09-29"])
    for schema in F.SCHEMAS:
        p = F.day_path(tmp_path, schema, "2026-09-29")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"already")
    c = FakeClient()
    F.main(["--archive", str(tmp_path), "--as-of", "2026-09-30", "--confirm",
           "--out", str(tmp_path / "r")], client=c)
    assert not c.calls("cost") and not c.calls("get_range")


def test_over_max_cost_aborts(tmp_path):
    c = FakeClient(cost=30.0)     # 2 files x $30 = $60 > default $50 ceiling
    with pytest.raises(SystemExit):
        F.main(["--archive", str(tmp_path), "--as-of", "2026-09-30", "--confirm",
               "--out", str(tmp_path / "r")], client=c)
    assert not c.calls("get_range")


# --- scoring + ledger ----------------------------------------------------

def test_score_new_days_calls_the_frozen_rule_with_registered_kwargs(tmp_path, monkeypatch):
    _pass_gate(monkeypatch)
    dates = ["2026-09-29", "2026-09-30"]
    _synthetic_bars(monkeypatch, dates)
    seen = []
    real = F.D.generate_dvp_trades
    def _spy(frames, market, days, **kw):
        seen.append((market, list(days), kw))
        return real(frames, market, days, **kw)
    monkeypatch.setattr(F.D, "generate_dvp_trades", _spy)
    trades, gate = F.score_new_days(tmp_path, dates)
    assert gate["passed"]
    assert seen and seen[0][0] == "NQ" and sorted(seen[0][1]) == dates
    assert seen[0][2] == {"p_ref": None, "loss_rule": "total", "trigger_minutes": 5}
    assert trades


def test_score_new_days_raises_and_leaves_ledger_untouched_on_failed_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "read_back", lambda archive, days: {
        "passed": False, "pass_threshold_pct": 0.99,
        "daily_agreement": {"n_within_tol": 1, "n_compared": 5, "pct_within_tol": 0.2},
    })
    with pytest.raises(SystemExit):
        F.score_new_days(tmp_path, ["2026-09-29"])
    assert not F.LEDGER_PATH.exists()


def test_run_appends_trades_and_scored_dates_to_the_ledger(tmp_path, monkeypatch):
    _pass_gate(monkeypatch)
    dates = ["2026-09-29", "2026-09-30"]
    _synthetic_bars(monkeypatch, dates)
    c = FakeClient()
    r = F.run(tmp_path, as_of="2026-10-01", client=c, confirm=True)
    assert r["scored_dates"] == dates
    assert r["n_trades_new"] > 0
    ledger = F.read_ledger()
    assert ledger["scored_dates"] == dates
    assert len(ledger["trades"]) == r["n_trades_new"]
    assert ledger["runs"] and ledger["runs"][0]["dates_scored"] == dates


def test_second_run_only_scores_the_new_gap(tmp_path, monkeypatch):
    _pass_gate(monkeypatch)
    _synthetic_bars(monkeypatch, ["2026-09-29"])
    c = FakeClient()
    F.run(tmp_path, as_of="2026-09-30", client=c, confirm=True)

    _synthetic_bars(monkeypatch, ["2026-09-30"])
    r2 = F.run(tmp_path, as_of="2026-10-01", client=c, confirm=True)
    assert r2["scored_dates"] == ["2026-09-30"]
    ledger = F.read_ledger()
    assert ledger["scored_dates"] == ["2026-09-29", "2026-09-30"]


def test_run_with_nothing_due_reports_no_new_sessions(tmp_path):
    c = FakeClient()
    r = F.run(tmp_path, as_of=F.FORWARD_START, client=c, confirm=True)
    assert r["no_new_sessions"]
    assert not c.calls("cost")


# --- cumulative_summary / check_early_stop --------------------------------

def _flat_trade(date, net_each_cost_only=True, entry=100.0, exit_=100.0, direction="long"):
    return {"date": date, "market": "NQ", "direction": direction, "voided": False,
           "fill_price": entry, "exit_price": exit_,
           "entry_fill_kind": "market_or_stop", "exit_fill_kind": "market_or_stop"}


def test_cumulative_summary_win_rate_and_break_even():
    ledger = F._default_ledger()
    ledger["trades"] = [
        _flat_trade("2026-09-29", entry=100.0, exit_=110.0),   # win
        _flat_trade("2026-09-30", entry=100.0, exit_=90.0),    # loss
    ]
    s = F.cumulative_summary(ledger)
    assert s["n_trades"] == 2 and s["wins"] == 1 and s["losses"] == 1
    assert s["win_rate"] == 0.5
    assert s["break_even_win_rate"] is not None


def test_stop_a_fires_after_150_trades_at_net_le_zero():
    ledger = F._default_ledger()
    ledger["trades"] = [_flat_trade(f"2026-{(i % 12) + 1:02d}-01", entry=100.0, exit_=100.0)
                        for i in range(150)]
    s = F.cumulative_summary(ledger)
    assert s["n_trades"] == 150 and s["net"] <= 0
    stop = F.check_early_stop(s)
    assert stop == {"stop": "A", "detail": stop["detail"]}
    assert "150" in stop["detail"]


def test_stop_a_does_not_fire_under_150_trades_even_if_net_negative():
    ledger = F._default_ledger()
    ledger["trades"] = [_flat_trade(f"2026-09-{i + 1:02d}", entry=100.0, exit_=100.0)
                        for i in range(10)]
    s = F.cumulative_summary(ledger)
    assert s["net"] < 0
    assert F.check_early_stop(s) is None


def test_stop_b_fires_when_drawdown_worse_than_3300():
    ledger = F._default_ledger()
    trades = [_flat_trade("2026-09-29", entry=0.0, exit_=100.0, direction="long")]  # peak
    for i in range(17):
        trades.append(_flat_trade(f"2026-10-{i + 1:02d}", entry=100.0, exit_=0.0, direction="long"))
    ledger["trades"] = trades
    s = F.cumulative_summary(ledger)
    assert s["max_drawdown"] < -3300.0
    stop = F.check_early_stop(s)
    assert stop["stop"] == "B"


def test_stop_b_does_not_fire_at_exactly_the_registered_reference_point():
    ledger = F._default_ledger()
    trades = [_flat_trade("2026-09-29", entry=0.0, exit_=100.0, direction="long")]
    for i in range(16):  # 16 * 202.88 = 3246.08, short of 3300
        trades.append(_flat_trade(f"2026-10-{i + 1:02d}", entry=100.0, exit_=0.0, direction="long"))
    ledger["trades"] = trades
    s = F.cumulative_summary(ledger)
    assert s["max_drawdown"] > -3300.0
    assert F.check_early_stop(s) is None


# --- the stop is a latch ---------------------------------------------------

def test_a_fired_stop_is_latched_and_blocks_further_pulls(tmp_path, monkeypatch):
    _pass_gate(monkeypatch)
    _synthetic_bars(monkeypatch, ["2026-09-29"])

    def _flat_score(archive, days):
        return ([_flat_trade(d, entry=100.0, exit_=100.0) for _ in range(150) for d in [days[0]]],
               {"passed": True})
    monkeypatch.setattr(F, "score_new_days", _flat_score)

    c = FakeClient()
    r1 = F.run(tmp_path, as_of="2026-09-30", client=c, confirm=True)
    assert r1["stop"] is not None and r1["stop"]["stop"] == "A"

    r2 = F.run(tmp_path, as_of="2026-10-15", client=c, confirm=True)
    assert r2["already_stopped"] is True
    assert not c.calls("cost")[len(c.calls("cost")):]  # no new pricing calls happened for r2
    calls_before_r2 = len(c.log)
    r3 = F.run(tmp_path, as_of="2026-11-01", client=c, confirm=True)
    assert r3["already_stopped"] is True
    assert len(c.log) == calls_before_r2, "a stopped test must never touch the client again"


# --- reporting --------------------------------------------------------

def test_txt_report_and_json_report_are_written(tmp_path, monkeypatch):
    _pass_gate(monkeypatch)
    _synthetic_bars(monkeypatch, ["2026-09-29"])
    c = FakeClient()
    out = tmp_path / "report" / "w16_0014_forward_test.json"
    rc = F.main(["--archive", str(tmp_path), "--as-of", "2026-09-30", "--confirm",
                "--out", str(out)], client=c)
    assert rc == 0
    assert out.exists()
    txt = out.with_suffix(".txt").read_text(encoding="utf-8")
    assert "DVP-F1" in txt and F.FROZEN_COMMIT in txt
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["scored_dates"] == ["2026-09-29"]
