"""exec_id: the fill log's stable per-trade id.

W02-0006. The row's position in the day's CSV (`f-{i:05d}` in the portal's
mirror) resets every day and shifts on re-parse, so it cannot be a primary
key -- see claude/reporting_tab_design_20260917.md §2. IB's own execution id
is unique and never reused, so it can be. This pins the join/dedupe/sort
behaviour of `exec_ids()` directly, without going through a live order.
"""
import types

from brokers.ibkr import trader as M


def fill(exec_id):
    return types.SimpleNamespace(
        execution=types.SimpleNamespace(execId=exec_id))


def test_single_fill_returns_its_exec_id():
    assert M.exec_ids([fill("0001.abc.01.01")]) == "0001.abc.01.01"


def test_partial_fill_joins_every_execution_sorted():
    # Order does not matter -- the join is sorted so the same set of
    # executions always produces the same string.
    assert (M.exec_ids([fill("0001.abc.01.02"), fill("0001.abc.01.01")])
            == "0001.abc.01.01,0001.abc.01.02")


def test_no_fills_is_empty_string():
    assert M.exec_ids([]) == ""


def test_a_fill_with_no_exec_id_is_skipped_not_crashed():
    # Test fakes and a couple of synthetic rows (e.g. _adopt_unknown_entry)
    # build Fill-like objects with no execId. That must not raise, and must
    # not contribute a literal "None" to the string.
    assert M.exec_ids([fill(None)]) == ""
    assert M.exec_ids([fill(None), fill("0001.abc.01.01")]) == "0001.abc.01.01"


def test_duplicate_exec_ids_are_deduped():
    assert M.exec_ids([fill("X"), fill("X")]) == "X"


def test_exec_id_is_a_real_field_on_every_fill_log_row():
    assert "exec_id" in M.FIELDS
