#!/usr/bin/env python3
"""W03-0013: the shared per-leg friction module.

Pins: pricing signs match exec_cost_legs' own convention (positive = worse);
`current()` refuses to invent a number when the state file is missing;
`refresh()` reproduces exec_cost_legs' own measurement byte-for-byte on a
synthetic fills dir, respects the registered MIN_N floor, and keeps every
prior state in `history` rather than overwriting it.
"""
from __future__ import annotations

import json

import pytest

from common import exec_cost as E
from common import exec_cost_legs as X


def fill(action="BUY", reason="", kind="signal_close", ref=5.00, px=5.02, strat="mcl",
         status="FILLED", qty=100, bid=5.00, ask=5.02, logged=None):
    if logged is None:
        cost = (px - ref) if action == "BUY" else (ref - px)
        logged = -cost
    return {"ts_et": "2026-09-10 05:00:00", "strategy": strat, "symbol": "ABC",
            "action": action, "reason": reason, "ref_close": ref, "ref_kind": kind,
            "bid": bid, "ask": ask, "fill_price": px, "filled_qty": qty, "qty": qty,
            "status": status, "slippage_vs_ref": logged}


def write_session(tmp_path, day: str, rows: list[dict]):
    cols = list(fill().keys())
    lines = [",".join(cols)]
    lines += [",".join(str(r.get(c, "")) for c in cols) for r in rows]
    (tmp_path / f"mcl_fills_{day}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


STATE = {
    "version": 1, "measured_at": "2026-09-28T00:00:00+00:00",
    "sessions": {"first": "2026-09-09", "last": "2026-09-25", "n_sessions": 13},
    "min_n": 15,
    "legs": {
        "ENTRY": {"mean_bps": -5.384265164294234, "n": 303, "ci95_bps": [-50.3, 52.5]},
        "TRAIL": {"mean_bps": 140.68328222096525, "n": 237, "ci95_bps": [113.7, 171.9]},
        "WCLOSE": {"mean_bps": 95.93243418851226, "n": 27, "ci95_bps": [47.2, 153.5]},
    },
    "notes": [], "source": "test fixture", "history": [],
}


# --- pricing ---------------------------------------------------------------------

def test_leg_cost_dollars_matches_the_bps_definition_and_sign():
    d = E.leg_cost_dollars("ENTRY", ref_price=10.0, qty=100, state=STATE)
    assert d == pytest.approx(10.0 * 100 * -5.384265164294234 / 10_000.0)
    trail = E.leg_cost_dollars("TRAIL", ref_price=10.0, qty=100, state=STATE)
    assert trail > 0                                          # TRAIL is adverse


def test_leg_cost_dollars_rejects_an_unknown_leg():
    with pytest.raises(ValueError):
        E.leg_cost_dollars("EXIT", 10.0, 100, state=STATE)


def test_round_trip_adds_entry_and_the_named_exit_leg():
    got = E.round_trip_cost_dollars(entry_ref=10.0, exit_ref=9.5, qty=100,
                                     exit_leg="WCLOSE", state=STATE)
    want = (E.leg_cost_dollars("ENTRY", 10.0, 100, STATE)
            + E.leg_cost_dollars("WCLOSE", 9.5, 100, STATE))
    assert got == pytest.approx(want)


def test_flat_equivalent_is_entry_plus_the_named_exit_pooled_mean():
    assert E.flat_equivalent_bps("TRAIL", STATE) == pytest.approx(
        STATE["legs"]["ENTRY"]["mean_bps"] + STATE["legs"]["TRAIL"]["mean_bps"])


def test_describe_brackets_negatives_like_the_project_convention():
    s = E.describe(STATE)
    assert "ENTRY (5.4)" in s and "TRAIL 140.7" in s and "WCLOSE 95.9" in s
    assert "2026-09-09 -> 2026-09-25, 13 sessions" in s


def test_current_refuses_to_invent_a_number_when_unmeasured(tmp_path):
    missing = tmp_path / "exec_cost_r1.json"
    with pytest.raises(FileNotFoundError):
        E.current(missing)


# --- refresh -----------------------------------------------------------------------

def _thirty_sessions(tmp_path, first="2026-09-01", n=16):
    """Enough sessions/fills to clear MIN_N (15) on every leg."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(first)
    days = [(d0 + timedelta(days=k)).isoformat() for k in range(n)]
    for day in days:
        rows = [fill("BUY", ref=5.00, px=5.02),
                fill("SELL", "trailing_stop", "trail_level", ref=6.00, px=5.94),
                fill("SELL", "window_close", "quote", ref=4.00, px=4.02)]
        write_session(tmp_path, day.replace("-", ""), rows)
    return days


def test_refresh_reproduces_exec_cost_legs_measurement_exactly(tmp_path):
    days = _thirty_sessions(tmp_path)
    out = tmp_path / "state.json"
    state = E.refresh(fills_dir=tmp_path, first=days[0], last=days[-1],
                       state_path=out, write=True)

    rows = X.load_legs(tmp_path, first=days[0], last=days[-1])
    means = X.means_by_leg(rows)
    e, _ = X.resolve_e(means)
    for leg in E.LEGS:
        assert state["legs"][leg]["mean_bps"] == pytest.approx(e[leg])
        assert state["legs"][leg]["n"] == means[leg][1]
    assert state["sessions"] == {"first": days[0], "last": days[-1], "n_sessions": len(days)}
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == state


def test_refresh_defaults_last_to_the_most_recent_session_on_disk(tmp_path):
    days = _thirty_sessions(tmp_path)
    state = E.refresh(fills_dir=tmp_path, first=days[0], write=False)
    assert state["sessions"]["last"] == days[-1]


def test_refresh_stops_below_the_registered_minimum_sample(tmp_path):
    write_session(tmp_path, "20260901",
                   [fill("BUY", ref=5.00, px=5.02),
                    fill("SELL", "trailing_stop", "trail_level", ref=6.00, px=5.94)])
    with pytest.raises(SystemExit):
        E.refresh(fills_dir=tmp_path, first="2026-09-01", last="2026-09-01", write=False)


def test_refresh_keeps_every_prior_state_in_history_not_overwriting_it(tmp_path):
    days = _thirty_sessions(tmp_path)
    out = tmp_path / "state.json"
    first = E.refresh(fills_dir=tmp_path, first=days[0], last=days[-1], state_path=out)
    assert first["history"] == []

    more_days = _thirty_sessions(tmp_path, first=days[-1], n=2)   # extend by one session
    second = E.refresh(fills_dir=tmp_path, first=days[0], last=more_days[-1], state_path=out)
    assert len(second["history"]) == 1
    assert second["history"][0]["sessions"] == first["sessions"]
    assert second["sessions"]["last"] == more_days[-1]

    third = E.refresh(fills_dir=tmp_path, first=days[0], last=more_days[-1], state_path=out)
    assert len(third["history"]) == 2


def test_cli_show_reads_back_the_file_it_wrote(tmp_path, capsys):
    import subprocess
    import sys
    days = _thirty_sessions(tmp_path)
    out = tmp_path / "state.json"
    E.refresh(fills_dir=tmp_path, first=days[0], last=days[-1], state_path=out)
    state = json.loads(out.read_text(encoding="utf-8"))
    assert E.describe(state) == E.describe(json.loads(out.read_text(encoding="utf-8")))
