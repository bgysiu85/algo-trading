#!/usr/bin/env python3
"""The feed probe: read-only, and its arithmetic.

REGISTERED_feed_freshness.md §5. This module exists to replace two inferences
with measurements -- the 04:00 roll (inferred today from four blocked stamps)
and the ~15-minute delay (inferred from when IBKR refused names). A probe whose
own arithmetic is wrong would replace an inference with a worse one.

The tests that matter most are the ones asserting what it must NOT do: never
write the watchlist, never take the writer lock, never let the session cookie
reach a file.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from common import tv_probe
from common.tv_screener import COLUMNS, VOLUME_COLUMN


def rec(t, poll, vol, arm="plain"):
    return {"poll_et": f"2026-09-19 {poll}", "arm": arm, "ticker": t,
            VOLUME_COLUMN: str(vol), "premarket_change": "31.0",
            "premarket_close": "4.10"}


# --- 5.2, the roll -----------------------------------------------------------

def test_a_name_whose_volume_never_moves_reads_as_never():
    """The carry-over's signature. A row that never moves inside the window is
    a row describing yesterday."""
    s = tv_probe.summarise([rec("BIAF", "04:00:05", 480_000),
                            rec("BIAF", "04:00:15", 480_000),
                            rec("BIAF", "04:00:25", 480_000)])
    h = {x["ticker"]: x for x in s["holds"]}["BIAF"]
    assert h["first_moved"] is None and h["held_s"] is None


def test_the_hold_is_measured_from_first_sight_to_first_movement():
    s = tv_probe.summarise([rec("VEEA", "04:00:05", 120_000),
                            rec("VEEA", "04:00:15", 120_000),
                            rec("VEEA", "04:00:45", 143_500),
                            rec("VEEA", "04:01:05", 150_000)])
    h = {x["ticker"]: x for x in s["holds"]}["VEEA"]
    assert h["first_seen"].endswith("04:00:05")
    assert h["first_moved"].endswith("04:00:45")
    assert h["held_s"] == 40.0


def test_a_volume_that_FALLS_counts_as_movement():
    """Yesterday's cumulative volume is usually larger than today's first
    prints, so the common case is a decrease. The same trap the gate has."""
    s = tv_probe.summarise([rec("BIAF", "04:00:05", 4_800_000),
                            rec("BIAF", "04:00:15", 118_000)])
    assert {x["ticker"]: x for x in s["holds"]}["BIAF"]["held_s"] == 10.0


def test_the_roll_table_reads_the_UNAUTHENTICATED_arm_only():
    """Mixing the arms would average two different feeds into one clock."""
    s = tv_probe.summarise([rec("VEEA", "04:00:05", 120_000, arm="plain"),
                            rec("VEEA", "04:00:15", 120_000, arm="plain"),
                            rec("VEEA", "04:00:05", 130_000, arm="auth"),
                            rec("VEEA", "04:00:15", 141_000, arm="auth")])
    assert [x["ticker"] for x in s["holds"]] == ["VEEA"]
    assert {x["ticker"]: x for x in s["holds"]}["VEEA"]["first_moved"] is None


# --- 5.3, the delay ----------------------------------------------------------

def test_the_delay_is_plain_minus_auth_so_a_leading_auth_arm_is_POSITIVE():
    """Sign convention, stated once and pinned: positive means the
    authenticated arm saw the name FIRST, which is the registered prediction."""
    s = tv_probe.summarise([rec("ACVA", "04:01:05", 880_000, arm="auth"),
                            rec("ACVA", "04:16:05", 900_000, arm="plain")])
    assert s["deltas"] == [{"ticker": "ACVA", "minutes": 15.0}]
    assert s["median_minutes"] == 15.0


def test_a_name_only_one_arm_ever_saw_is_reported_but_not_averaged():
    """A name the delayed arm never returned has no delta -- counting it as
    zero would drag the median toward 'no delay' using the very names that
    demonstrate one."""
    s = tv_probe.summarise([rec("ACVA", "04:01:05", 880_000, arm="auth"),
                            rec("VEEA", "04:00:05", 120_000, arm="auth"),
                            rec("VEEA", "04:00:05", 120_000, arm="plain")])
    assert s["auth_only"] == ["ACVA"]
    assert [d["ticker"] for d in s["deltas"]] == ["VEEA"]


def test_no_authenticated_arm_gives_no_median_rather_than_zero():
    """Zero is a reading -- 'the endpoint is not the delay'. Absent is not."""
    s = tv_probe.summarise([rec("VEEA", "04:00:05", 120_000)])
    assert s["median_minutes"] is None
    assert s["deltas"] == []


def test_the_report_says_the_arm_did_not_run_rather_than_printing_a_number():
    body = "\n".join(tv_probe.render(
        tv_probe.summarise([rec("VEEA", "04:00:05", 120_000)]),
        columns=None, polls=3, authed=False))
    assert tv_probe.COOKIE_ENV in body
    assert "not run" in body


# --- 5.1, the column probe ---------------------------------------------------

def test_candidate_columns_are_APPENDED_not_substituted():
    """A probe that screens differently is measuring a different screen. The
    row set must be the shipped one, so the filter and the leading columns are
    untouched and candidates go on the end."""
    p = tv_probe.columns_payload(("update_mode", "premarket_volume"))
    assert p["columns"][:len(COLUMNS)] == list(COLUMNS)
    assert p["columns"].count("premarket_volume") == 1, "a real column duplicated"
    assert p["columns"][-1] == "update_mode"
    assert p["filter"] == tv_probe.tv_payload()["filter"]


def test_an_unknown_column_reads_as_absent_rather_than_raising():
    """TradingView does not error on a column it does not know; it returns
    null, or a short row. Both must read as 'absent' -- that is the answer."""
    extra = ("update_mode", "nonsense_column")
    names = list(COLUMNS) + list(extra)
    body = {"data": [{"s": "NASDAQ:VEEA",
                      "d": [None] * len(COLUMNS) + ["delayed_streaming_900"]}]}
    got = tv_probe.read_columns(body, extra)
    assert got["update_mode"] == "delayed_streaming_900"
    assert got["nonsense_column"] is None
    assert len(names) == len(COLUMNS) + 2


def test_a_present_column_is_reported_as_making_the_gate_exact():
    body = "\n".join(tv_probe.render(
        tv_probe.summarise([rec("VEEA", "04:00:05", 120_000)]),
        columns={"update_mode": "delayed_streaming_900", "update_time": None},
        polls=1, authed=False))
    assert "update_mode" in body and "exact test" in body


# --- what it must NOT do -----------------------------------------------------

def test_the_probe_never_writes_the_watchlist_and_never_takes_the_lock():
    """It is safe to run beside a live feed. Two writers take turns and the
    trader sees the watchlist flip between two answers every few seconds.
    """
    import ast

    src = inspect.getsource(tv_probe)
    assert "session_lock" not in src, "the probe touches the writer lock"
    # By name, not by substring: the report TEXT says 'never writes
    # watchlist.txt', and a substring test on the source flags its own
    # disclaimer. What matters is that nothing here can call the writer or
    # name its path.
    tree = ast.parse(src)
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    called |= {n.func.attr for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "write_watchlist" not in called
    imported = {alias.name for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) for alias in n.names}
    assert "WATCHLIST" not in imported and "write_watchlist" not in imported
    # Every output path it owns lives under var/reports/.
    for const in (tv_probe.OUT_CSV, tv_probe.OUT_TXT):
        assert Path("var/reports") in Path(const).parents, const


def test_the_cookie_is_read_from_the_environment_and_never_a_flag():
    """The rule DATABENTO_API_KEY carries: a flag puts the secret in shell
    history. `--replay` and `--minutes` are flags; the credential is not.
    """
    flags = [a.option_strings for a in tv_probe.build_parser()._actions]
    flat = [s for opts in flags for s in opts]
    assert not any("session" in s or "cookie" in s or "token" in s for s in flat), flat
    src = inspect.getsource(tv_probe.main)
    assert f'os.environ.get(COOKIE_ENV)' in src


def test_the_cookie_value_never_reaches_the_csv_or_the_report():
    """A secret that leaks into a report is a secret in D:\\Trading\\Claude
    outputs, which is where files are delivered from."""
    row_src = inspect.getsource(tv_probe.append_rows)
    assert "cookie" not in row_src.lower()
    rendered = "\n".join(tv_probe.render(
        tv_probe.summarise([rec("VEEA", "04:00:05", 120_000, arm="auth"),
                            rec("VEEA", "04:00:05", 120_000)]),
        columns=None, polls=1, authed=True))
    assert "sessionid" not in rendered.lower()


def test_the_cookie_is_sent_as_a_cookie_header_when_given(monkeypatch):
    seen = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"data": []}'

    def fake_urlopen(req, timeout=None):
        seen["headers"] = dict(req.header_items())
        return FakeResp()

    monkeypatch.setattr(tv_probe.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(tv_probe.json, "load", lambda fh: {"data": []})
    tv_probe._scan({"filter": []}, cookie="abc123")
    cookie = [v for k, v in seen["headers"].items() if k.lower() == "cookie"]
    assert cookie == ["sessionid=abc123"]

    seen.clear()
    tv_probe._scan({"filter": []}, cookie=None)
    assert not [k for k in seen["headers"] if k.lower() == "cookie"]


def test_replay_re_reads_a_csv_without_touching_the_network(monkeypatch, tmp_path):
    """A morning's data is expensive in wall clock and free to re-read. A
    replay that quietly re-polled would be a different measurement."""
    csv_path = tmp_path / "tv_probe.csv"
    csv_path.write_text(
        "poll_et,arm,ticker,premarket_volume,premarket_change,premarket_close\n"
        "2026-09-19 04:00:05,plain,BIAF,480000,31.0,4.10\n"
        "2026-09-19 04:00:15,plain,BIAF,480000,31.0,4.10\n",
        encoding="utf-8")

    def boom(*a, **k):
        raise AssertionError("replay hit the network")

    monkeypatch.setattr(tv_probe, "_scan", boom)
    out = tmp_path / "tv_probe.txt"
    assert tv_probe.main(["--replay", str(csv_path), "--out", str(out)]) == 0
    assert "never" in out.read_text(encoding="utf-8")
