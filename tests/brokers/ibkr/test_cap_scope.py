"""--cap-scope: what the position cap counts (W02-0014, 2026-09-23).

Ben: "allow each strategy a max position of 3, rather than a total pool of 3
... it seems like MC5 is dragging down MCL." With `cap_scope="strategy"` each
strategy gets its own pool of `max_positions`; the default, "account", is the
shared pool every earlier session ran under and must not move.

What is pinned here:
  1. the default is still the shared pool, on the trader and on the parser
  2. an unknown scope is refused, not quietly defaulted
  3. per-strategy: MCL still enters while MC5 holds its full cap -- and the
     SAME setup under the shared pool declines it (the control)
  4. per-strategy: a strategy is still capped by its OWN positions, and the
     declined row says which pool refused it
  5. the CONFIG row records the scope in force
"""
from __future__ import annotations

import asyncio
import csv
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from brokers.ibkr import trader as T
from common import strategy_adapter as SA
from tests.brokers.ibkr.test_concurrency_cap import build as build_conc, feed_one
from tests.brokers.ibkr.test_dryrun_roundtrip import FakeTicker, find_firing_series
from tests.brokers.ibkr.test_live_paths import FakeIB, FakeTrade


def _seq():
    n = 140
    full, _seed, _spike = find_firing_series(n)
    return [full.iloc[: k + 1] for k in range(T.MIN_BARS_REQUIRED, n)]


def _rows(log, out):
    log.close()
    return list(csv.DictReader(out.open(encoding="utf-8")))


def _hold_mc5(tr, symbols):
    """Put MC5 states on the book that are already holding a position."""
    for s in symbols:
        st = T.SymbolState(symbol=s, strategy=SA.mc5_adapter())
        st.contract = object()
        st.ticker = FakeTicker()
        st.position = T.Position(symbol=s, qty=100, entry_price=10.0,
                                 entry_time=datetime(2026, 9, 2, 7, 0, tzinfo=T.ET),
                                 peak=10.0)
        tr.states[(st.strategy.name, s)] = st


def _build(tag, symbols, cap, scope):
    tr, sts, ib, log, out = build_conc(tag, symbols,
                                       [FakeTrade(100, 10.00, "Filled")] * 40,
                                       cap=cap)
    tr.cap_scope = scope
    return tr, sts, ib, log, out


# --- 1 / 2 -------------------------------------------------------------------

def _plain(**kw):
    tmp = Path(tempfile.gettempdir())
    return T.MCLPaperTrader(FakeIB([]), tmp / "wl.txt",
                            T.FillLog(tmp / "capscope_plain.csv"),
                            dry_run=True, **kw)


def test_the_default_is_still_the_shared_pool():
    assert T.DEFAULT_CAP_SCOPE == "account"
    assert _plain().cap_scope == "account"
    assert _plain(cap_scope=None).cap_scope == "account"
    assert _plain(cap_scope="strategy").cap_scope == "strategy"
    assert T.build_parser().parse_args([]).cap_scope is None
    assert T.build_parser().parse_args(
        ["--cap-scope", "strategy"]).cap_scope == "strategy"


def test_an_unknown_scope_is_refused():
    with pytest.raises(ValueError):
        _plain(cap_scope="per-strategy")
    with pytest.raises(SystemExit):
        T.build_parser().parse_args(["--cap-scope", "bogus"])


# --- 3 -----------------------------------------------------------------------

@pytest.mark.parametrize("scope,expect_entry", [("strategy", True),
                                                ("account", False)])
def test_mc5_holding_its_cap_does_not_block_mcl_per_strategy(scope, expect_entry):
    tr, sts, ib, log, out = _build(f"mc5full_{scope}", ["AAA"], cap=3, scope=scope)
    _hold_mc5(tr, ["M1", "M2", "M3"])
    asyncio.run(feed_one(tr, sts["AAA"], _seq()))
    rows = _rows(log, out)
    declined = [r for r in rows if r["symbol"] == "AAA"
                and r["status"] == "SKIPPED_CONCURRENCY_CAP"]
    if expect_entry:
        assert sts["AAA"].position is not None, "MCL was crowded out by MC5"
        assert not declined
    else:
        assert sts["AAA"].position is None, "shared pool no longer shared"
        assert declined and declined[0]["reject_reason"] == "3 open, cap 3"


# --- 4 -----------------------------------------------------------------------

def test_a_strategy_is_still_capped_by_its_own_positions():
    tr, sts, ib, log, out = _build("own", ["AAA", "BBB", "CCC"], cap=2,
                                   scope="strategy")
    _hold_mc5(tr, ["M1", "M2", "M3", "M4"])        # MC5 over MCL's cap: irrelevant
    seq = _seq()
    for s in ("AAA", "BBB", "CCC"):
        asyncio.run(feed_one(tr, sts[s], seq))
    held = sorted(s for s, st in sts.items() if st.position is not None)
    assert held == ["AAA", "BBB"]
    rows = _rows(log, out)
    d = [r for r in rows if r["symbol"] == "CCC"
         and r["status"] == "SKIPPED_CONCURRENCY_CAP"]
    assert d, "third MCL entry not declined"
    name = SA.mcl_adapter().name
    assert d[0]["reject_reason"] == f"2 open for {name}, cap 2 per strategy"


# --- 5 -----------------------------------------------------------------------

def test_the_config_row_records_the_scope(monkeypatch):
    monkeypatch.delenv("UI_RELAY_URL", raising=False)
    from tests.brokers.ibkr.test_config_row_and_band import Book
    b = Book()
    b.record_config()
    assert "cap_scope=account" in b.log.rows[0]["reject_reason"]
    b = Book()
    b.cap_scope = "strategy"
    b.record_config()
    assert "cap_scope=strategy" in b.log.rows[0]["reject_reason"]
