#!/usr/bin/env python3
"""The shared position cap, as a per-session parameter.

Ben, 2026-09-10, adding MC5 alongside MCL: raise the cap to 3. MC5 takes ~3.5x
MCL's entries, and one cap of 2 shared between them would crowd MCL out.

The cap moved from a module constant to an instance value. The constant stays
as the DEFAULT, because every dry run, every test and every previous session's
semantics rest on it -- an edited constant would move all of them silently and
a later reader of an old fill log would have no way to tell which cap produced
it.
"""
from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

import pytest

from brokers.ibkr import trader as T
from tests.brokers.ibkr.test_live_paths import FakeIB


def build(**kw):
    """A trader on the project's FakeIB. Constructing one must not touch IB,
    1Password or the filesystem beyond a temp path."""
    tmp = Path(tempfile.gettempdir())
    return T.MCLPaperTrader(FakeIB([]), tmp / "wl.txt",
                            T.FillLog(tmp / "maxpos_test.csv"),
                            dry_run=True, **kw)


def test_the_default_is_still_the_documented_constant():
    """Not passing the argument must change nothing. If this drifts, every
    figure and every dry run taken at the old cap is describing a different
    trader from the one running."""
    assert T.MAX_CONCURRENT_POSITIONS == 2
    assert build().max_positions == 2
    assert build(max_positions=None).max_positions == 2


@pytest.mark.parametrize("n", [1, 3, 4, 10])
def test_an_explicit_cap_is_used(n):
    assert build(max_positions=n).max_positions == n


def test_zero_means_no_entries_not_the_default():
    """`max_positions or MAX_CONCURRENT_POSITIONS` would turn 0 into 2 -- so a
    run intended to take NO entries while still recording signals would quietly
    take two positions. Same trap as trail_cents and max_hold_bars."""
    assert build(max_positions=0).max_positions == 0
    src = inspect.getsource(T.MCLPaperTrader.__init__)
    assert "max_positions is None" in src, (
        "the cap must be tested against None, never for truthiness")


def test_the_entry_gate_reads_the_instance_not_the_constant():
    """The gate is the only thing that enforces the cap. If it still read the
    module constant, --max-positions would be accepted, logged, and ignored --
    which is worse than not having the flag, because the log would assert a cap
    that was not in force.
    """
    src = inspect.getsource(T.MCLPaperTrader)
    gate = [ln for ln in src.splitlines() if "open_now >=" in ln]
    assert gate, "the concurrency gate moved; this test needs updating"
    for ln in gate:
        assert "self.max_positions" in ln, ln
        assert "MAX_CONCURRENT_POSITIONS" not in ln, ln


def test_the_declined_row_records_the_cap_actually_in_force():
    """A SKIPPED_CONCURRENCY_CAP row is read back weeks later. If it recorded
    the constant it would say 'cap 2' on a session that ran at 3."""
    src = inspect.getsource(T.MCLPaperTrader)
    i = src.index("SKIPPED_CONCURRENCY_CAP")
    near = src[max(0, i - 600):i + 300]
    assert "self.max_positions" in near
    assert "MAX_CONCURRENT_POSITIONS" not in near


def test_the_flag_exists_and_defaults_to_none():
    a = T.build_parser().parse_args([])
    assert a.max_positions is None
    assert T.build_parser().parse_args(["--max-positions", "3"]).max_positions == 3


def test_the_startup_log_reads_the_trader_not_the_argument():
    """main() logged the constant before the trader existed. A log line that
    can disagree with the running value is worse than none, because it is what
    gets quoted in a session review."""
    src = inspect.getsource(T.main) if hasattr(T, "main") else ""
    if "one book, cap" not in src:            # main may be async/wrapped
        import re
        whole = inspect.getsource(T)
        m = re.search(r"one book, cap[^\n]*\n[^\n]*", whole)
        src = m.group(0) if m else ""
    assert "trader.max_positions" in src, (
        "the startup log must report the cap in force, not the constant")
