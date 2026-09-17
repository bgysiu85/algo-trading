"""The live-path fakes quote 10.00 / 10.02 whatever frame the trader was
handed (`FakeTicker` in test_dryrun_roundtrip), and most frames close
somewhere else. Since 2026-09-17 a BUY into an ask more than
`DRIFT_GUARD_PCT` from the signal close is refused (REGISTERED_drift_guard),
which would turn every such test into a drift refusal. The guard is switched
off here for every module but its own, which scales its frame to the quote
and tests the guard on purpose. A test that wants the guard on sets the
constant back itself."""
from __future__ import annotations

import math

import pytest

from brokers.ibkr import trader as M


@pytest.fixture(autouse=True)
def _drift_guard_off_unless_under_test(request, monkeypatch):
    if request.node.fspath.basename == "test_drift_guard.py":
        return
    monkeypatch.setattr(M, "DRIFT_GUARD_PCT", math.inf)
