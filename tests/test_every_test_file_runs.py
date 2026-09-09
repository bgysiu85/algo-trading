#!/usr/bin/env python3
"""Every test file must actually define a test.

WHY THIS EXISTS, 2026-09-09
---------------------------
Seven files in this suite were print-style scripts: they defined main(),
reported each check with PASS/FAIL, and declared no test_* function. pytest
collected ZERO tests from every one of them and ran none of the checks, while
the suite reported 915 passing.

The seven were not peripheral. They were the ENTIRE automated coverage of
brokers/ibkr/trader.py -- the price band, the live paths, IB pacing, the
trailing stop firing off a quote, the dry-run round trip, the concurrency cap
-- plus the MCL and MC5 engine checks.

Two of the seven were FAILING and said nothing:

  * tests/strategy/mcl/test_backtest_engine.py had compared
    evaluate_last_bar().exit_signal against the UNGATED exit_sig column, and
    had been failing since the 2026-09-08 apex fix made that comparison wrong;
  * tests/brokers/ibkr/test_pacing_and_trail.py stopped even importing when a
    parameter was renamed the same week.

So the pattern does not merely fail to catch a regression. It hides one that
has already happened, behind a green suite.

A convention -- "write test_ functions" -- is not a mechanism. This is the
mechanism.
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def defines_a_test(path: Path) -> bool:
    """A module-level `def test_*`, or a `class Test*` with a test method.

    Parsed rather than imported: importing to find out would run module-level
    code in exactly the files this is suspicious of.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                return True
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for sub in node.body:
                if (isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and sub.name.startswith("test")):
                    return True
    return False


def test_no_test_file_is_silently_uncollected():
    empty = sorted(str(p.relative_to(TESTS))
                   for p in TESTS.rglob("test_*.py")
                   if not defines_a_test(p))
    assert not empty, (
        "these files match test_*.py but define no test, so pytest collects "
        "nothing from them and any check inside runs never: "
        + ", ".join(empty)
        + ". Add a test_* function -- a thin wrapper asserting main() == 0 is "
          "enough to make the checks run and the suite fail when they do not.")


def test_the_guard_can_tell_the_difference(tmp_path):
    """A checker that passes everything proves nothing."""
    good = tmp_path / "test_good.py"
    good.write_text("def test_x():\n    assert True\n")
    bad = tmp_path / "test_bad.py"
    bad.write_text("def main():\n    return 0\n\n"
                   'if __name__ == "__main__":\n    main()\n')
    klass = tmp_path / "test_klass.py"
    klass.write_text("class TestThing:\n    def test_y(self):\n        pass\n")
    helper = tmp_path / "test_helper_only.py"
    helper.write_text("def build():\n    return 1\n")

    assert defines_a_test(good)
    assert defines_a_test(klass)
    assert not defines_a_test(bad)
    assert not defines_a_test(helper)


def test_the_guard_is_actually_looking_at_this_suite():
    """If the glob were wrong it would find nothing and pass forever."""
    found = list(TESTS.rglob("test_*.py"))
    assert len(found) > 30, f"only {len(found)} test files seen — wrong root?"
