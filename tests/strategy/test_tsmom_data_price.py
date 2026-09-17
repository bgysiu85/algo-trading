#!/usr/bin/env python3
"""`common.tsmom_data_price` cannot spend money, and the guard that says so can fail.

The module's safety property is STRUCTURAL rather than behavioural: it does not
guard a download path, it has none. That is only worth claiming if something
checks it, and a check on a property that holds by construction is exactly the
kind of check this project has caught itself writing before -- `PROGRAM_INDEX`
section 4, "a control whose output is indistinguishable from the failure it
detects is not a control". So the scan below is run against the real module AND
against a synthetic module that does spend, and it must pass the first and fail
the second.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MODULE = ROOT / "common" / "tsmom_data_price.py"

# Every databento call that transfers billable data. `get_cost` and
# `get_billable_size` are metadata lookups and are free; they are not here.
SPENDING_CALLS = {
    ("timeseries", "get_range"),
    ("timeseries", "get_range_async"),
    ("batch", "submit_job"),
}


def _spending_calls(source: str) -> list[str]:
    """Attribute calls in `source` that would transfer billable data.

    Matches on the last two attribute names, so `client.timeseries.get_range`
    and `self.client.timeseries.get_range` both land. A call assembled through
    getattr would not -- which is a limitation, not a hole, because the point
    is to catch a plausible edit rather than a determined one.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or not isinstance(fn.value, ast.Attribute):
            continue
        if (fn.value.attr, fn.attr) in SPENDING_CALLS:
            found.append(f"{fn.value.attr}.{fn.attr} at line {node.lineno}")
    return found


def test_the_module_has_no_download_path():
    source = MODULE.read_text(encoding="utf-8")
    assert _spending_calls(source) == [], (
        "common/tsmom_data_price.py has acquired a call that transfers billable "
        "data. Its whole claim is that it cannot spend. Move the pull into its "
        "own module, under its own registration."
    )


def test_the_guard_can_fail():
    """The scan must reject a module that DOES spend, or it is not a scan."""
    spends = textwrap.dedent("""
        def pull(client):
            return client.timeseries.get_range(dataset="GLBX.MDP3", schema="ohlcv-1d")
    """)
    assert _spending_calls(spends), (
        "the scan passed a module that calls timeseries.get_range -- it is "
        "matching nothing and would pass the real module for the same reason"
    )


def test_the_guard_does_not_fire_on_the_free_metadata_lookups():
    free = textwrap.dedent("""
        def price(client):
            a = client.metadata.get_cost(dataset="GLBX.MDP3")
            b = client.metadata.get_billable_size(dataset="GLBX.MDP3")
            c = client.metadata.get_dataset_range(dataset="GLBX.MDP3")
            return a, b, c
    """)
    assert _spending_calls(free) == []


def _option_strings(source: str) -> list[str]:
    """Every `--flag` the module declares to argparse.

    The first draft of this test scanned the raw source for the substring
    "--key" and failed on the DOCSTRING, which explains why there is no --key
    flag. A prose scan is both a false-positive generator and too narrow --
    it would have passed `--api-key` and `--secret`. Read the declarations.
    """
    flags = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            flags += [a.value for a in node.args
                      if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return flags


def test_the_key_is_never_a_command_line_flag():
    import common.tsmom_data_price as m

    source = MODULE.read_text(encoding="utf-8")
    flags = _option_strings(source)
    assert flags, "no argparse flags found -- the scan is matching nothing"
    leaky = [f for f in flags if "key" in f.lower() or "secret" in f.lower()
             or "token" in f.lower()]
    assert leaky == [], (
        f"{leaky} would put the Databento key in PowerShell history "
        "(PROGRAM_INDEX section 1: API keys never appear in chat, and they "
        "should not appear in shell history either)"
    )
    assert "DATABENTO_API_KEY" in source
    assert m._scrub("boom db-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 boom") == (
        "boom <DATABENTO_API_KEY> boom")


def test_scrub_removes_the_live_key_even_when_it_does_not_match_the_pattern(monkeypatch):
    import common.tsmom_data_price as m

    monkeypatch.setenv("DATABENTO_API_KEY", "not-a-db-prefixed-key")
    assert "not-a-db-prefixed-key" not in m._scrub("failed for not-a-db-prefixed-key")


def test_the_root_set_is_the_one_the_spec_registered():
    import common.tsmom_data_price as m

    assert set(m.ROOTS) == {"ES", "RTY", "GC", "SI", "HG", "CL", "NG",
                            "6E", "6A", "6B", "6J", "ZN"}
    # Rule 5 of spec section 2.1: one instrument per bucket. NQ and YM are the
    # same bucket as ES and must not creep back in as "more data".
    assert "NQ" not in m.ROOTS and "YM" not in m.ROOTS
    # Yield-quoted contracts are excluded outright -- long ZN is SHORT 10Y, and
    # a set that carries both trades the opposite of its own signal in one of
    # them while printing an ordinary-looking curve (spec section 2.3).
    assert not ({"2YY", "5YY", "10Y", "30Y"} & set(m.ROOTS))
    # TN is arm (b) and is opt-in, so arm (a) cannot pay for data it will not use.
    assert "TN" not in m.ROOTS and "TN" in m.TN_ROOT


def test_crude_is_CL_and_never_MCL():
    """MCL is a STRATEGY in this repo and the micro crude future elsewhere.

    `handover_tsmom_20260917.md` section 2.1 calls the collision out by name.
    A TSMOM module that carries an "MCL" root would read as the strategy to
    every other chat writing to this repo.
    """
    import common.tsmom_data_price as m

    assert "CL" in m.ROOTS
    assert "MCL" not in m.ROOTS


def test_unknown_roots_are_refused_rather_than_silently_dropped(capsys):
    import common.tsmom_data_price as m

    with pytest.raises(SystemExit) as e:
        m.main(["--roots", "ES", "WHEAT"])
    assert "WHEAT" in str(e.value)


def test_it_refuses_to_run_without_a_key(monkeypatch):
    import common.tsmom_data_price as m

    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        m._key()
    assert "DATABENTO_API_KEY" in str(e.value)
