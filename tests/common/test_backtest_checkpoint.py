#!/usr/bin/env python3
"""Checkpointing, and what a run says when it did not finish.

THE INCIDENT, 2026-09-07
------------------------
The screened MCL run died at pair 511 of 27,877 with

    PermissionError: [WinError 5] Access is denied:
      'backtest_state_mcl.tmp' -> 'backtest_state_mcl.json'

and then printed a complete-looking result: 61 trades, NET +190.54, a
concentration table, best and worst symbols. Every symbol in it began with A,
because pairs are processed in list order. Nothing in the output said the run
had covered 1.8% of the universe.

Three defects, one incident:

1. The state file was rewritten after EVERY pair. It grows with the run, so
   that is O(n^2) bytes and 27,877 chances for the rename to lose a race.
2. os.replace on Windows fails transiently when a virus scanner or indexer
   holds a handle for an instant. Nothing retried.
3. report() runs from a `finally`, so it prints whether the run finished or
   died -- and it had no idea which had happened.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common import backtest as B


class FakeRunner:
    """Just the checkpoint and reporting machinery, without IB or a strategy."""

    def __init__(self, tmp_path, requested=None, done=0, trades=()):
        self.state_path = Path(tmp_path) / "backtest_state_mcl.json"
        self.state = {"done": {f"S{i}|2026-03-16": {"status": "OK", "bars": 1,
                                                    "session_bars": 1,
                                                    "trades": 0, "net": 0.0}
                               for i in range(done)},
                      "trades": list(trades)}
        self._since_save = 0
        self.requested = requested
        self.strategy = "mcl"
        self.out_dir = Path(tmp_path)
        self.cache_hits = done
        self.cache_misses = 0

    _save_state = B.Runner._save_state
    incomplete = B.Runner.incomplete
    report = B.Runner.report


# --- the checkpoint interval ------------------------------------------------

def test_the_state_is_not_written_on_every_pair(tmp_path):
    """The write is O(file size), and the file grows with the run. Per-pair is
    O(n^2) bytes -- invisible over 587 pairs, tens of gigabytes over 27,877."""
    r = FakeRunner(tmp_path)
    for _ in range(B.CHECKPOINT_EVERY - 1):
        r._save_state()
    assert not r.state_path.exists()


def test_it_is_written_once_the_interval_is_reached(tmp_path):
    r = FakeRunner(tmp_path)
    for _ in range(B.CHECKPOINT_EVERY):
        r._save_state()
    assert r.state_path.exists()


def test_force_writes_immediately(tmp_path):
    """The final save, the interrupt save and the --retry-failed save must not
    wait for an interval that may never be reached."""
    r = FakeRunner(tmp_path, done=3)
    r._save_state(force=True)
    assert len(json.loads(r.state_path.read_text())["done"]) == 3


def test_the_counter_resets_so_saves_stay_periodic(tmp_path):
    r = FakeRunner(tmp_path)
    for _ in range(B.CHECKPOINT_EVERY):
        r._save_state()
    first = r.state_path.stat().st_mtime_ns
    r.state["done"]["X|2026-03-16"] = {"status": "OK", "bars": 1,
                                       "session_bars": 1, "trades": 0}
    r._save_state()
    assert r.state_path.stat().st_mtime_ns == first


# --- the Windows rename race ------------------------------------------------

def test_a_transient_permission_error_is_retried(tmp_path, monkeypatch):
    """WinError 5 here is a virus scanner holding the file for an instant, not
    a permissions problem. It killed a run at pair 511."""
    r = FakeRunner(tmp_path, done=1)
    calls = {"n": 0}
    real = Path.replace

    def flaky(self, target):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", flaky)
    monkeypatch.setattr(B, "CHECKPOINT_BACKOFF_S", 0)
    r._save_state(force=True)
    assert calls["n"] == 3
    assert r.state_path.exists()


def test_a_persistent_lock_is_explained_not_raised_as_winerror(tmp_path,
                                                               monkeypatch):
    """`PermissionError: [WinError 5]` names neither the cause nor the fix."""
    r = FakeRunner(tmp_path, done=1)

    def always(self, target):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(Path, "replace", always)
    monkeypatch.setattr(B, "CHECKPOINT_BACKOFF_S", 0)
    with pytest.raises(RuntimeError) as e:
        r._save_state(force=True)
    msg = str(e.value)
    assert "antivirus" in msg and "rerun to resume" in msg


# --- what a partial run is allowed to claim ---------------------------------

def test_a_finished_run_reports_nothing_unusual(tmp_path, capsys):
    r = FakeRunner(tmp_path, requested=10, done=10)
    r.report(probe_only=True)
    assert "PARTIAL RUN" not in capsys.readouterr().out


def test_a_partial_run_says_so_before_any_figure(tmp_path, capsys):
    r = FakeRunner(tmp_path, requested=27_877, done=511)
    r.report(probe_only=True)
    out = capsys.readouterr().out
    assert "PARTIAL RUN" in out
    assert "DO NOT QUOTE" in out
    # Before the numbers, not after them.
    assert out.index("PARTIAL RUN") < out.index("pairs attempted")
    assert "511" in out and "27,877" in out


def test_a_partial_run_says_it_is_a_prefix_not_a_sample(tmp_path, capsys):
    """This is the part that makes the figures meaningless rather than noisy:
    every symbol in the 511 began with A."""
    r = FakeRunner(tmp_path, requested=27_877, done=511)
    r.report(probe_only=True)
    assert "PREFIX" in capsys.readouterr().out


def test_a_partial_run_does_not_get_the_real_csv_name(tmp_path, capsys):
    """day_compare, compound_sim and db_load all read
    backtest_trades_<strategy>.csv. Writing a prefix of the universe there
    replaces a good result with a bad one under a name that says nothing."""
    tr = [{"symbol": "ACON", "net": 12.0, "date": "2026-03-16"}]
    r = FakeRunner(tmp_path, requested=27_877, done=511, trades=tr)
    r.report(probe_only=False)
    assert (tmp_path / "backtest_trades_mcl.partial.csv").exists()
    assert not (tmp_path / "backtest_trades_mcl.csv").exists()
    assert ".partial" in capsys.readouterr().out


def test_a_finished_run_does_get_the_real_csv_name(tmp_path):
    tr = [{"symbol": "ACON", "net": 12.0, "date": "2026-03-16"}]
    r = FakeRunner(tmp_path, requested=1, done=1, trades=tr)
    r.report(probe_only=False)
    assert (tmp_path / "backtest_trades_mcl.csv").exists()
    assert not (tmp_path / "backtest_trades_mcl.partial.csv").exists()


def test_a_run_that_was_never_started_makes_no_claim(tmp_path, capsys):
    """requested is None until run() sets it -- e.g. --probe on an empty list.
    That is not evidence of a partial run."""
    r = FakeRunner(tmp_path, requested=None, done=4)
    assert r.incomplete() == 0
    r.report(probe_only=True)
    assert "PARTIAL RUN" not in capsys.readouterr().out


def test_resuming_past_the_requested_count_is_not_negative(tmp_path):
    """A state file carried over from a bigger run has more done than this run
    asked for. That is fine, and must not report as negative."""
    r = FakeRunner(tmp_path, requested=10, done=25)
    assert r.incomplete() == 0


# --- requested has to reach report(), not just exist ------------------------

def test_run_records_how_many_pairs_it_was_asked_for(tmp_path, monkeypatch):
    """report() can only say a run was partial if run() told it the target.
    The FakeRunner above sets `requested` by hand; this checks the real path
    does too, since a field nothing populates would report every run as
    complete -- which is exactly the failure being fixed."""
    import asyncio
    import json

    (tmp_path / "p.json").write_text(json.dumps(
        [{"symbol": s, "date": "2026-03-16"} for s in ("AAA", "BBB", "CCC")]))
    r = B.Runner(None, tmp_path / "out", cache_dir=tmp_path / "nocache",
                 state_dir=tmp_path / "state", strategy="mcl", offline=True)
    assert r.requested is None
    asyncio.run(r.run(B.load_pairs(tmp_path / "p.json"), False, None))
    assert r.requested == 3
    assert r.incomplete() == 0

    # A run that died two pairs in reports two missing, not zero.
    r.state["done"] = {"AAA|2026-03-16": r.state["done"]["AAA|2026-03-16"]}
    assert r.incomplete() == 2


def test_the_final_save_is_forced_so_the_tail_is_not_lost(tmp_path):
    """With periodic checkpointing the last pairs live only in memory. A run
    of fewer than CHECKPOINT_EVERY pairs would otherwise save nothing at all
    and redo everything on resume."""
    import asyncio
    import json

    n = max(3, B.CHECKPOINT_EVERY - 10)
    syms = [f"A{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(n)]
    (tmp_path / "p.json").write_text(json.dumps(
        [{"symbol": s, "date": "2026-03-16"} for s in syms]))
    r = B.Runner(None, tmp_path / "out", cache_dir=tmp_path / "nocache",
                 state_dir=tmp_path / "state", strategy="mcl", offline=True)
    asyncio.run(r.run(B.load_pairs(tmp_path / "p.json"), False, None))
    assert not r.state_path.exists()      # interval never reached
    r._save_state(force=True)             # what main_async's finally does
    assert len(json.loads(r.state_path.read_text())["done"]) == len(set(syms))
