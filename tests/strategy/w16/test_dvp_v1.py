#!/usr/bin/env python3
"""DVP-v1 (REGISTERED_w16_drift_vwap_v1.md): refuses to read 2024+ without
--confirm-spend; with it, spends the ledger as DVP-v1-NQ, reads only locked
dates, uses the literal-points rule, and emits the registered criteria."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_drift_vwap import trend_session  # noqa: E402

import strategy.w16.dvp_holdout as DH
import strategy.w16.dvp_runner as DR
import strategy.w16.dvp_v1 as V1
import strategy.w16.preflight as PF


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(DH, "LEDGER_PATH", tmp_path / "holdout_w16_dvp.json")


def _archive(monkeypatch):
    dates = ["2023-06-01", "2023-06-02", "2024-02-01", "2024-02-02", "2025-03-03", "2026-08-10"]
    dfs = [trend_session(d, direction=("long" if i % 2 == 0 else "short"), slope=1.0,
                         dip_windows=["10:35", "12:35"], dip_size=6.0) for i, d in enumerate(dates)]
    df = pd.concat(dfs).sort_index()
    monkeypatch.setattr(V1, "load_root_bars", lambda archive, market: df)
    monkeypatch.setattr(PF, "load_root_bars", lambda archive, market: df)
    monkeypatch.setattr(DR, "load_root_bars", lambda archive, market: df)
    return dates


def test_without_confirm_spend_nothing_is_read(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("must not load bars")
    monkeypatch.setattr(V1, "load_root_bars", _boom)
    assert V1.main([]) == 0
    assert DH.read_ledger() is None


def test_run_spends_as_v1_and_reads_only_locked_dates(monkeypatch):
    _archive(monkeypatch)
    seen = []
    real = V1.D.generate_dvp_trades
    def _spy(frames, market, dates, **kw):
        seen.append((list(dates), kw.get("p_ref")))
        return real(frames, market, dates, **kw)
    monkeypatch.setattr(V1.D, "generate_dvp_trades", _spy)
    r = V1.run(None, n_control_draws=5, progress=False)
    assert DH.read_ledger()["candidate"] == "DVP-v1-NQ"
    literal = [d for d, p in seen if p is None]
    assert literal and all(all(x >= "2024-01-02" for x in ds) for ds in literal)
    for k in ("1_net_positive", "2_both_halves_positive", "3_net_positive_at_l3",
              "4_month_bootstrap_ge_95pct", "5_beats_c_d3_p95", "6_min_trades"):
        assert k in r["criteria"]
    assert r["first_date"] >= "2024-01-02"
    json.dumps(r, default=str)
    assert "OUT-OF-SAMPLE" in V1.txt_report(r)


def test_second_run_is_refused(monkeypatch):
    _archive(monkeypatch)
    V1.run(None, n_control_draws=0, progress=False)
    with pytest.raises(SystemExit):
        V1.run(None, n_control_draws=0, progress=False)


def test_c_d1_after_never_enters_before_the_real_fill(monkeypatch):
    dates = _archive(monkeypatch)
    frames = PF.session_frames(V1.load_root_bars(None, "NQ"))
    trades = V1.D.generate_dvp_trades(frames, "NQ", [d for d in dates if d >= "2024"], p_ref=None,
                                      loss_rule="total")
    assert trades
    cache = DR._session_arrays_cache(frames, {t["date"] for t in trades})
    by_date = {}
    for t in trades:
        by_date.setdefault(t["date"], []).append(t)
    for i in range(20):
        draw = V1.c_d1_after_draw(trades, cache, i)
        assert len(draw) <= len(trades)
        assert draw
        for ct in draw:
            assert ct["fill_minute"] >= ct["real_fill_minute"]
            assert (ct["fill_minute"] - 570) % 5 == 0
