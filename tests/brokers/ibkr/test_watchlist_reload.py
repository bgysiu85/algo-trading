#!/usr/bin/env python3
"""One bad ticker must not stop the watchlist reloading.

2026-09-15, live. PSNYW is a warrant, so there is no Stock security definition
for it, and one symbol took the whole reload down:

    ERROR   Error 200 ... contract: Stock(symbol='PSNYW', ...)
    WARNING PSNYW could not read minTick ...
    WARNING PSNYW tradability probe failed ...
    WARNING watchlist reload failed: 'NoneType' object has no attribute 'secType'

THREE defects, and the third is the one that matters:

  1. `qualifyContractsAsync` returned a list with None in it. `st.contract =
     qualified[0]` accepted the None and carried it to reqMktData, which reads
     `contract.secType`.
  2. The subscribe loop had no per-symbol guard, so the raise abandoned every
     OTHER new name in the same pass -- and `wanted - self.symbols` is a set,
     so which ones were skipped depended on iteration order.
  3. `self._wl_mtime = mtime` was committed at the TOP of sync_watchlist,
     before the work. So once the pass failed, every later pass saw
     `mtime == self._wl_mtime` and returned immediately. **The watchlist did
     not reload again until tv_feed happened to rewrite the file.** A trader
     working from a stale list, saying nothing.

That third one is the project's recurring shape: state advanced before the
work it guards completed.
"""
from __future__ import annotations

import asyncio

import pytest

from brokers.ibkr import trader as M
from common import strategy_adapter as SA


class Reloader:
    """The parts of the trader sync_watchlist actually touches."""

    def __init__(self, tmp_path, names, fail_on=(), blow_up_on=()):
        self.watchlist = tmp_path / "watchlist.txt"
        self.watchlist.write_text("\n".join(names) + "\n", encoding="utf-8")
        self.states = {}
        self.feeds = {}
        self.strategies = [SA.mcl_adapter()]
        self._wl_mtime = None
        self.subscribed = []
        self._fail_on = set(fail_on)        # returns False, like a blocked name
        self._blow_up_on = set(blow_up_on)  # raises, like PSNYW did

    @property
    def symbols(self):
        return M.MCLPaperTrader.symbols.fget(self)

    async def _subscribe(self, sym):
        # the real one registers the states BEFORE qualifying, which is why a
        # raise still leaves the symbol in self.states
        st = M.SymbolState(symbol=sym, feed=None, strategy=self.strategies[0])
        self.states[(self.strategies[0].name, sym)] = st
        self.subscribed.append(sym)
        if sym in self._blow_up_on:
            raise AttributeError("'NoneType' object has no attribute 'secType'")
        if sym in self._fail_on:
            st.blocked = True
            return False
        return True

    async def sync(self, first=False):
        await M.MCLPaperTrader.sync_watchlist(self, first=first)


def test_one_raising_symbol_does_not_abandon_the_others(tmp_path):
    r = Reloader(tmp_path, ["AAAA", "PSNYW", "ZZZZ"], blow_up_on=["PSNYW"])
    asyncio.run(r.sync(first=True))
    assert set(r.subscribed) == {"AAAA", "PSNYW", "ZZZZ"}, \
        "every name in the pass must be attempted"
    assert r.symbols == {"AAAA", "PSNYW", "ZZZZ"}


def test_the_raising_symbol_is_blocked_so_it_cannot_spin(tmp_path):
    r = Reloader(tmp_path, ["AAAA", "PSNYW"], blow_up_on=["PSNYW"])
    asyncio.run(r.sync(first=True))
    bad = [v for k, v in r.states.items() if k[1] == "PSNYW"]
    assert bad and all(st.blocked for st in bad)


def test_the_mtime_is_not_spent_when_the_pass_raises_outright(tmp_path):
    """The per-symbol guard catches a symbol. If something OUTSIDE it throws,
    the mtime must still be unspent so the next pass retries -- otherwise the
    reload stops for the life of that file version."""
    r = Reloader(tmp_path, ["AAAA"])

    def boom(_):
        raise RuntimeError("parse blew up")

    import brokers.ibkr.trader as T
    real = T.parse_watchlist
    T.parse_watchlist = boom
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(r.sync(first=True))
    finally:
        T.parse_watchlist = real
    assert r._wl_mtime is None, \
        "a failed pass must leave the mtime unspent so it is retried"

    # and the retry, once the cause is gone, actually happens
    asyncio.run(r.sync(first=True))
    assert r.subscribed == ["AAAA"]


def test_a_successful_pass_does_spend_the_mtime(tmp_path):
    """The other half. Without this, the reload would re-subscribe every poll
    and walk straight into IB's pacing limit."""
    r = Reloader(tmp_path, ["AAAA", "BBBB"])
    asyncio.run(r.sync(first=True))
    assert r._wl_mtime is not None
    n = len(r.subscribed)
    asyncio.run(r.sync())
    assert len(r.subscribed) == n, "unchanged file must not re-subscribe"


def test_the_pass_is_ordered_so_a_failure_is_reproducible(tmp_path):
    """`wanted - self.symbols` is a set. Before the per-symbol guard, WHICH
    names got skipped after a raise depended on iteration order, so the same
    watchlist could fail differently on two runs."""
    names = [f"S{i:02d}" for i in range(12)]
    a = Reloader(tmp_path, names)
    asyncio.run(a.sync(first=True))
    b = Reloader(tmp_path, names)
    asyncio.run(b.sync(first=True))
    assert a.subscribed == b.subscribed == sorted(names)


def test_retiring_still_happens_after_a_symbol_raised(tmp_path):
    """The retire loop runs after the subscribe loop. A raise that escaped the
    subscribe loop used to skip it, so a name removed from the file kept
    taking new entries."""
    r = Reloader(tmp_path, ["AAAA", "PSNYW"], blow_up_on=["PSNYW"])
    asyncio.run(r.sync(first=True))
    r.watchlist.write_text("PSNYW\n", encoding="utf-8")
    import os
    os.utime(r.watchlist, (0, 0))
    asyncio.run(r.sync())
    gone = [v for k, v in r.states.items() if k[1] == "AAAA"]
    assert gone and all(st.retired for st in gone), \
        "AAAA left the file and must be retired"


# --- the qualification itself --------------------------------------------------

class Qualifier:
    """The parts of the trader _subscribe touches, with a scripted IB."""

    class IB:
        def __init__(self, answer):
            self.answer = answer
            self.md = []

        async def qualifyContractsAsync(self, c):
            return self.answer

        async def reqContractDetailsAsync(self, c):
            return []

        def reqMktData(self, contract, *a, **k):
            # the real ib_async reads contract.secType here, which is exactly
            # how a None travelled out of _subscribe as an AttributeError
            _ = contract.secType
            self.md.append(contract)
            return object()

    def __init__(self, tmp_path, answer):
        self.ib = self.IB(answer)
        self.states = {}
        self.feeds = {}
        self.strategies = [SA.mcl_adapter()]
        self.watchlist = tmp_path / "watchlist.txt"
        self.watchlist.write_text("AAAA\n", encoding="utf-8")
        self.blocked = []

    def feed_for(self, sym):
        return M.MCLPaperTrader.feed_for(self, sym)

    def block_symbol(self, st, why):
        st.blocked = True
        self.blocked.append((st.symbol, why))

    async def check_tradable(self, st):
        return None

    async def subscribe(self, sym):
        return await M.MCLPaperTrader._subscribe(self, sym)


class FakeContract:
    def __init__(self, secType="STK", symbol="AAAA"):
        self.secType = secType
        self.symbol = symbol
        self.minTick = 0.01


def test_a_None_in_the_qualified_list_never_reaches_the_data_line(tmp_path):
    """PSNYW, exactly. The list came back non-empty with a None in it, and
    `st.contract = qualified[0]` accepted it. reqMktData then read
    contract.secType and raised out of the whole reload."""
    q = Qualifier(tmp_path, [None])
    ok = asyncio.run(q.subscribe("PSNYW"))
    assert ok is False
    assert q.ib.md == [], "no market-data line for an unqualified contract"
    assert q.blocked and q.blocked[0][0] == "PSNYW"
    assert all(st.blocked for st in q.states.values())


def test_a_contract_that_is_not_a_stock_is_refused_by_TYPE(tmp_path):
    """Checking secType is a mechanism. Guessing from the ticker -- five
    letters ending in W -- is a heuristic that would be wrong on the first
    five-letter common stock it met."""
    q = Qualifier(tmp_path, [FakeContract(secType="WAR", symbol="PSNYW")])
    ok = asyncio.run(q.subscribe("PSNYW"))
    assert ok is False
    assert q.ib.md == []
    assert q.blocked and "WAR" in q.blocked[0][1]


def test_a_real_stock_still_subscribes(tmp_path):
    """The other half: the guards must not refuse the normal case."""
    q = Qualifier(tmp_path, [FakeContract(secType="STK", symbol="AAAA")])
    ok = asyncio.run(q.subscribe("AAAA"))
    assert ok is True
    assert len(q.ib.md) == 1
    assert not q.blocked


def test_a_contract_with_no_secType_at_all_is_refused_not_assumed(tmp_path):
    """The default direction. `getattr(got, "secType", "STK")` would make the
    guard permissive in precisely the case where nothing is known about the
    object -- a guard that passes when it cannot tell is not a guard."""
    class Bare:
        symbol = "PSNYW"
        minTick = 0.01
    q = Qualifier(tmp_path, [Bare()])
    assert asyncio.run(q.subscribe("PSNYW")) is False
    assert q.ib.md == []
    assert q.blocked and "unknown" in q.blocked[0][1]
