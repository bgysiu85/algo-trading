#!/usr/bin/env python3
"""Every reader of the fill log ignores a CONFIG row.

The strategy side checked all seven read sites by hand and found each one
already excluded it -- `status != "FILLED"`, or `action == "SELL"`, or
`status in ("FILLED", "PARTIAL_FILL")`. That is a fact about today's code and
not a guarantee about tomorrow's, and the request that came back with the
agreed row shape was explicit: the row shape is the claim, a test that runs the
real readers over a book with and without the rows is the evidence.

So this file drives the actual `load` functions, not a re-statement of their
gates. A re-statement would pass while the reader it describes changed.

Agreed shape: claude/portal_config_row_reply_20260914.md.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pytest

from brokers.ibkr import trader as T
from common import ui_bridge

NOW = datetime(2026, 9, 14, 7, 20, 0)

TRADES = [
    dict(ts_et="2026-09-14 07:20:00", strategy="MCL", symbol="AAA",
         action="BUY", reason="entry_signal", status="FILLED",
         ref_close=4.0, ref_kind="signal_close", fill_price=4.02,
         filled_qty=100, qty=100, slippage_vs_ref=-0.02,
         macd=0.1, macd_sig=0.05, rsi=61.0, vol=90000.0),
    dict(ts_et="2026-09-14 07:41:00", strategy="MCL", symbol="AAA",
         action="SELL", reason="trailing_stop", status="FILLED",
         ref_close=3.9, ref_kind="trail_level", fill_price=3.88,
         filled_qty=100, qty=100, slippage_vs_ref=-0.02,
         entry_price=4.02, exit_price=3.88, trade_pnl=-14.0,
         trade_pct=-3.48, hold_minutes=21.0),
    dict(ts_et="2026-09-14 08:02:00", strategy="MC5", symbol="BBB",
         action="BUY", reason="entry_signal", status="FILLED",
         ref_close=9.0, ref_kind="signal_close", fill_price=9.01,
         filled_qty=50, qty=50, slippage_vs_ref=-0.01),
    dict(ts_et="2026-09-14 08:55:00", strategy="MC5", symbol="BBB",
         action="SELL", reason="session_end", status="FILLED",
         ref_close=9.4, ref_kind="bar_close", fill_price=9.39,
         filled_qty=50, qty=50, slippage_vs_ref=-0.01,
         entry_price=9.01, exit_price=9.39, trade_pnl=19.0,
         trade_pct=4.22, hold_minutes=53.0),
]


def _book(directory: Path, with_config: bool) -> Path:
    """The same four trades, with and without CONFIG rows interleaved.

    Interleaved rather than appended: a reader that happens to stop at the
    first non-trade row would pass an appended version and fail a real session.
    """
    path = directory / "mcl_fills_20260914.csv"
    log = T.FillLog(path)
    if with_config:
        for name, trail in (("MCL", 5.0), ("MC5", 5.0)):
            log.write(ts_et="2026-09-14 07:19:00", strategy=name,
                      symbol=ui_bridge.SETTING_TRAIL,
                      action=ui_bridge.CONFIG_ACTION,
                      status=ui_bridge.CONFIG_APPLIED, reason="session_open",
                      reject_reason=f"trail_pct={trail} paused=False "
                                    f"max_positions=3 enabled=True",
                      trail_pct=trail)
    for i, trade in enumerate(TRADES):
        log.write(**trade)
        if with_config and i == 1:
            log.write(ts_et="2026-09-14 07:45:00", strategy="MCL",
                      symbol=ui_bridge.SETTING_TRAIL,
                      action=ui_bridge.CONFIG_ACTION,
                      status=ui_bridge.CONFIG_APPLIED, reason="set_setting",
                      reject_reason="5.0 -> 9.0", trail_pct=9.0)
            log.write(ts_et="2026-09-14 07:45:00", strategy="MCL",
                      symbol=ui_bridge.SETTING_PAUSED,
                      action=ui_bridge.CONFIG_ACTION,
                      status=ui_bridge.CONFIG_REJECTED, reason="stop",
                      reject_reason="already stopped")
    log.close()
    return path


@pytest.fixture
def books(tmp_path):
    clean = tmp_path / "clean"
    noisy = tmp_path / "noisy"
    clean.mkdir()
    noisy.mkdir()
    return _book(clean, False), _book(noisy, True)


def test_the_fixture_really_does_differ(books):
    """Guard the guard: if the CONFIG rows were not written, every comparison
    below would pass by comparing a book with itself."""
    clean, noisy = books
    rows = {p: list(csv.DictReader(p.open(newline="", encoding="utf-8"))) for p in (clean, noisy)}
    assert len(rows[noisy]) == len(rows[clean]) + 4
    assert any(r["action"] == "CONFIG" for r in rows[noisy])
    assert not any(r["action"] == "CONFIG" for r in rows[clean])


def test_churn_count_sees_the_same_trades(books):
    from common import churn_count

    clean, noisy = books
    a, _ = churn_count.load(clean)
    b, _ = churn_count.load(noisy)

    assert len(a) == len(b) == 4
    assert list(a.symbol) == list(b.symbol)
    assert list(a.action) == list(b.action)


def test_tv_reconcile_sees_the_same_fills(books):
    from common import tv_reconcile

    clean, noisy = books
    a = tv_reconcile.load_fills(clean)
    b = tv_reconcile.load_fills(noisy)

    assert len(a) == len(b) == 4
    assert [r["symbol"] for r in a] == [r["symbol"] for r in b]


def test_friction_measures_the_same_book(books):
    from common import friction

    clean, noisy = books
    a = friction.load(None, clean.parent)
    b = friction.load(None, noisy.parent)

    assert _shape(a) == _shape(b)


def _shape(loaded):
    """friction.load returns (by_session, excluded) or similar; compare the
    part that matters -- how many rows survived, per session."""
    by_session = loaded[0] if isinstance(loaded, tuple) else loaded
    return {k: len(v) for k, v in by_session.items()}


def test_the_portal_itself_sees_the_same_fills(books):
    """ui_bridge reads this file to build the dashboard. A CONFIG row appearing
    as a trade would put a fake fill in front of Ben."""
    clean, noisy = books

    class Log:
        def __init__(self, path):
            self.path = path

    class Trader:
        def __init__(self, path):
            self.log = Log(path)

    a = ui_bridge.UIBridge._fills_today(Trader(clean))
    b = ui_bridge.UIBridge._fills_today(Trader(noisy))

    assert len(a) == len(b) == 4
    assert [f["symbol"] for f in a] == [f["symbol"] for f in b]


def test_the_trade_arithmetic_is_untouched(books):
    """The number that would actually mislead: total P/L."""
    from common import churn_count

    clean, noisy = books
    a, _ = churn_count.load(clean)
    b, _ = churn_count.load(noisy)

    assert a.trade_pnl.sum() == b.trade_pnl.sum() == 5.0
