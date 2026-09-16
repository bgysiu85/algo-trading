#!/usr/bin/env python3
"""The four places the trader touches the portal, pinned.

WHY THIS FILE EXISTS. The portal is an optional passenger: every hook is
wrapped so that a dead relay cannot disturb trading, and `self.ui` is None when
no portal is configured. That is the right design, and it has one consequence
worth defending against -- if a refactor drops one of these hooks, NOTHING
fails. The trader trades perfectly, the suite stays green, and the only symptom
is a dashboard that quietly stops updating. On 2026-09-15 a variant of exactly
that (the bridge configured but never attached) went unnoticed for two hours.

So this is the agreed interface between the two sides of the project:

  portal owns    common/ui_bridge.py, tests/common/test_ui_bridge.py,
                 the contract schema and the UI repo
  strategy owns  everything else, including all four call sites below
  shared         this file. A hook changes by agreement, and changing it means
                 changing this test -- which is the point: the test makes the
                 change visible rather than silent.

These assertions read source rather than running a session, deliberately. A
behavioural test would need a live IB connection or a mock deep enough to be a
second implementation; what is being defended here is the EXISTENCE of the
call, and source is where existence lives.
"""
from __future__ import annotations

import inspect

from brokers.ibkr import trader as T


def _src(obj) -> str:
    return inspect.getsource(obj)


def test_hook_1_the_trader_starts_with_no_portal():
    """`self.ui = None` in __init__. Without it every other hook raises
    AttributeError on a session with no portal configured -- which is most of
    them, and all of the backtests."""
    src = _src(T.MCLPaperTrader.__init__)
    assert "self.ui = None" in src, (
        "the trader no longer starts with self.ui = None; a session without a "
        "portal will now raise AttributeError at the first hook")


def test_hook_2_the_loop_pushes_to_the_portal():
    """`await self.ui.tick(self, now_et)` in run(). This is the ONLY thing that
    puts data on the dashboard. Drop it and the page renders perfectly, shows
    the last state it ever received, and says nothing is wrong."""
    src = _src(T.MCLPaperTrader.run)
    assert "self.ui is not None" in src and "self.ui.tick(" in src, (
        "the trading loop no longer pushes to the portal. The dashboard will "
        "keep serving its last state and will not report a problem -- see the "
        "module docstring")


def test_hook_3_the_portal_is_attached_at_startup():
    """`trader.ui = ui_bridge.UIBridge.from_env(...)` in main_async. The bridge
    reads its own configuration from the environment; if this assignment goes,
    UI_RELAY_URL is set and nothing ever reads it."""
    src = _src(T.main_async)
    assert "UIBridge.from_env(" in src and "trader.ui" in src, (
        "nothing attaches the portal at startup; UI_RELAY_URL would be set and "
        "silently ignored")


def test_hook_4_a_configured_portal_that_will_not_start_is_loud():
    """The refusal notice. bridge_state() records the three states durably;
    this is the half that reaches Ben during the session. The failure it covers
    -- configured but unattached -- is indistinguishable from a quiet market
    unless something says so."""
    src = _src(T.main_async)
    assert "configured-but-unattached" in src, (
        "the loud refusal is gone. A portal that is configured and fails to "
        "attach will look exactly like a session with no portal")


def test_the_three_bridge_states_are_still_distinguishable():
    """Behavioural, because this one can be. `off` and
    `configured-but-unattached` are different facts and were once the same
    log line."""
    assert set(inspect.signature(T.MCLPaperTrader.bridge_state).parameters) == {"self"}
    src = _src(T.MCLPaperTrader.bridge_state)
    for state in ("attached", "configured-but-unattached", "off"):
        assert f'"{state}"' in src, f"bridge_state no longer reports {state!r}"


def test_the_bridge_is_optional_in_both_directions():
    """The portal must never be able to stop the trader. Every hook that calls
    into the bridge is guarded or wrapped."""
    loop = _src(T.MCLPaperTrader.run)
    tick = loop[loop.index("self.ui.tick("):]
    assert "except Exception" in loop[:loop.index("self.ui.tick(")] + tick[:400], (
        "the portal tick is no longer wrapped; a relay failure can now reach "
        "the trading loop")
