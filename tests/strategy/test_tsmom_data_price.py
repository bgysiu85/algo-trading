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


def test_scrub_removes_the_resolved_key_even_when_it_does_not_match_the_pattern(monkeypatch):
    """A key that does not look like one is still a key.

    The regex only catches `db-`-prefixed values. A vendor is free to change
    that shape, and a 1Password field can hold anything, so the literal
    resolved value is removed too.
    """
    import common.tsmom_data_price as m

    monkeypatch.setattr("common.secrets_util.resolve", lambda *a, **k: "not-a-db-prefixed-key")
    m._RESOLVED = ""
    m._key()
    assert "not-a-db-prefixed-key" not in m._scrub("failed for not-a-db-prefixed-key")
    m._RESOLVED = ""


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

    monkeypatch.setattr("common.secrets_util.resolve", lambda *a, **k: "")
    with pytest.raises(SystemExit) as e:
        m._key()
    assert "DATABENTO_API_KEY" in str(e.value)


def _reads_env_directly(source: str, var: str) -> list[str]:
    """os.environ / os.getenv reads of `var` anywhere in `source`.

    `os.environ.get(var)`, `os.environ[var]` and `os.getenv(var)` all count.
    """
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Subscript):          # os.environ["X"]
            sl = node.slice
            if (isinstance(node.value, ast.Attribute) and node.value.attr == "environ"
                    and isinstance(sl, ast.Constant) and sl.value == var):
                hits.append(f"os.environ[{var!r}] at line {node.lineno}")
        if isinstance(node, ast.Call):               # .get(...) / os.getenv(...)
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else None
            envish = (name == "getenv") or (
                name == "get" and isinstance(fn, ast.Attribute)
                and isinstance(fn.value, ast.Attribute) and fn.value.attr == "environ")
            if envish and node.args and isinstance(node.args[0], ast.Constant) \
                    and node.args[0].value == var:
                hits.append(f"{name}({var!r}) at line {node.lineno}")
    return hits


def test_the_key_is_resolved_through_secrets_util():
    """One resolver, not two. This module shipped with the second one.

    The first draft read os.environ["DATABENTO_API_KEY"] directly. On Ben's
    machine that variable holds an op:// 1Password reference set with `setx`,
    so the reference went to the vendor and came back 401 -- the exact failure
    `common/databento_fetch.py::_key` had already found, fixed and documented,
    and the one `secrets_util.resolve`'s docstring names as the reason it
    exists. Writing a second reader four days later reproduced it verbatim.

    PROGRAM_INDEX section 1 settles this class by fiat for the holdout:
    `holdout.split_sessions` is THE one implementation and a test asserts every
    study calls it. Same treatment here.
    """
    source = MODULE.read_text(encoding="utf-8")
    direct = _reads_env_directly(source, "DATABENTO_API_KEY")
    assert direct == [], (
        f"{direct} reads the environment variable directly. On a machine where "
        "it holds an op:// reference that sends the REFERENCE to Databento and "
        "returns a 401 that reads like a revoked key. Use "
        "common.secrets_util.resolve -- the repo has one resolver."
    )
    assert "secrets_util" in source, (
        "the module resolves its key some third way -- there is one resolver")


def test_the_one_resolver_guard_can_fail():
    """The scan must reject a module that DOES read the variable directly."""
    import textwrap

    bad = textwrap.dedent("""
        import os
        def key():
            return os.environ.get("DATABENTO_API_KEY")
    """)
    worse = textwrap.dedent("""
        import os
        def key():
            return os.environ["DATABENTO_API_KEY"]
    """)
    getenv = textwrap.dedent("""
        import os
        def key():
            return os.getenv("DATABENTO_API_KEY")
    """)
    for src, label in ((bad, "environ.get"), (worse, "environ[]"), (getenv, "getenv")):
        assert _reads_env_directly(src, "DATABENTO_API_KEY"), (
            f"the scan missed {label} -- it would pass the real module for the "
            "same reason, which is no reason at all")
    # and it must not fire on an unrelated variable
    other = "import os\nx = os.environ.get('DATABENTO_ARCHIVE')\n"
    assert _reads_env_directly(other, "DATABENTO_API_KEY") == []


def test_scrub_removes_the_resolved_key_not_the_environment_variable(monkeypatch):
    """The two are different strings when the variable holds an op:// reference.

    Scrubbing the reference while printing the secret is the wrong way round,
    and it is what the first draft did.
    """
    import common.tsmom_data_price as m

    monkeypatch.setenv("DATABENTO_API_KEY", "op://Trading/databento/credential")
    monkeypatch.setattr("common.secrets_util.resolve", lambda *a, **k: "SECRETVALUE1234567890")
    m._RESOLVED = ""
    m._key()
    assert "SECRETVALUE1234567890" not in m._scrub("failed for SECRETVALUE1234567890")
    m._RESOLVED = ""


class _FakeMeta:
    """Records the kwargs every metadata lookup was called with."""

    def __init__(self):
        self.calls = []

    def get_cost(self, **kw):
        self.calls.append(kw)
        return 0.01

    def get_billable_size(self, **kw):
        return 1000


class _FakeClient:
    def __init__(self):
        self.metadata = _FakeMeta()


def test_lean_asks_for_the_front_and_next_contract_only():
    import common.tsmom_data_price as m

    c = _FakeClient()
    m.price_one(c, "CL", "ohlcv-1d", "2010-06-06", "2026-09-17", scope="lean")
    kw = c.metadata.calls[-1]
    assert kw["stype_in"] == "continuous"
    assert kw["symbols"] == "CL.c.0,CL.c.1", (
        "the roll holds the front contract and, for the five sessions before "
        "its expiry, the next one. c.2 and beyond are the deferred months out "
        "to 2035 that made the first estimate $21 of bars.")


def test_full_still_asks_for_every_contract_month():
    import common.tsmom_data_price as m

    c = _FakeClient()
    m.price_one(c, "CL", "ohlcv-1d", "2010-06-06", "2026-09-17", scope="full")
    kw = c.metadata.calls[-1]
    assert kw["stype_in"] == "parent" and kw["symbols"] == "CL.FUT"


def test_lean_definition_prices_one_session_and_says_by_how_much_it_scaled():
    """$50 of the first estimate was sixteen years of daily definition snapshots.

    The expiration dates they carry are static per contract, so the roll
    calendar is sampled rather than streamed. The estimate must price a single
    session and scale by the sample count -- not price the full range.
    """
    import common.tsmom_data_price as m

    c = _FakeClient()
    usd, nbytes = m.price_one(c, "CL", "definition", "2010-06-06", "2026-09-17",
                              scope="lean")
    kw = c.metadata.calls[-1]
    assert kw["start"] == "2026-09-16" and kw["end"] == "2026-09-17", (
        "a lean definition estimate prices ONE session; a Databento range is "
        "[start, end) so start == end is empty and returns 422")
    assert usd == 0.01 * m.DEFINITION_SAMPLES
    assert nbytes == 1000 * m.DEFINITION_SAMPLES


def test_a_one_day_range_is_never_empty():
    """start == end is an EMPTY range, not a one-day range.

    The first --diagnose probe passed start=end and got back
    422 data_time_range_start_on_or_after_end -- it asked for no days and the
    vendor said so, which read like a scoping failure and was a date-arithmetic
    bug.
    """
    import common.tsmom_data_price as m

    c = _FakeClient()
    m.price_one(c, "ES", "definition", "2010-06-06", "2026-09-17", scope="lean")
    kw = c.metadata.calls[-1]
    assert kw["start"] < kw["end"]


def test_lean_is_the_default():
    import common.tsmom_data_price as m

    flags = {}
    for node in ast.walk(ast.parse(MODULE.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument" and node.args
                and isinstance(node.args[0], ast.Constant)):
            for kw in node.keywords:
                if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                    flags[node.args[0].value] = kw.value.value
    assert flags.get("--scope") == "lean", (
        "full scope is $71.62 for data the strategy does not read; it stays "
        "available and does not stay the default")


def test_every_diagnostic_probe_asks_for_a_non_empty_range():
    """The 422 came from `diagnose`, and the first test for it covered `price_one`.

    Mutation-testing caught that: reverting the fix inside `diagnose` left the
    suite green. A check one step short of the thing it protects is
    PROGRAM_INDEX section 4's own entry -- "a clock inside the session is not a
    bar inside the session". This asserts the probes themselves.
    """
    import common.tsmom_data_price as m

    c = _FakeClient()
    m.diagnose(c, "ES", "2010-06-06", "2026-09-17")
    assert c.metadata.calls, "diagnose issued no lookups -- it is matching nothing"
    empty = [kw for kw in c.metadata.calls if kw["start"] >= kw["end"]]
    assert empty == [], (
        f"{len(empty)} probe(s) ask for an empty range and return "
        "422 data_time_range_start_on_or_after_end, which reads as a scoping "
        "failure and is date arithmetic")
    assert any(kw["schema"] == "definition" and kw["start"] == "2026-09-16"
               for kw in c.metadata.calls), "the ONE-day definition probe is gone"
