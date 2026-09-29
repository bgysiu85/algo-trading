#!/usr/bin/env python3
"""W03-0014/W03-0015: entry_gates.py's quote source (BASIC/cbbo-1s originally)
must be swappable via --quote-dataset/--quote-schema for a re-run on a
different consolidated tape (e.g. DBEQ.BASIC/mbp-1), WITHOUT changing
BARS_DATASET -- the MCL/MC5 engine's own bar tape, which must stay identical
to the published W03-0002 book or the re-run stops being a comparison of
quote sources and becomes a comparison of different books.

These are unit tests against the module's own functions and source, with no
Databento archive on disk -- they do not (and must not) require real data."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pandas as pd
import pytest

from common import entry_gates as E


# --- quote_window_path / load_quote_window: dataset/schema are parameters,
#     not frozen constants, and default to the originally-registered tape ---

def test_quote_window_path_defaults_to_the_registered_tape():
    p = E.quote_window_path(Path("E:/Databento"), "2026-09-10", "MCL")
    assert p == Path("E:/Databento/XNAS.BASIC/cbbo-1s/windows/2026-09-10/MCL.dbn.zst")


def test_quote_window_path_honours_an_explicit_dataset_and_schema():
    p = E.quote_window_path(Path("E:/Databento"), "2026-09-10", "MCL",
                             dataset="DBEQ.BASIC", schema="mbp-1")
    assert p == Path("E:/Databento/DBEQ.BASIC/mbp-1/windows/2026-09-10/MCL.dbn.zst")


def test_load_quote_window_missing_file_is_empty_regardless_of_dataset(tmp_path):
    # No file written under either tree -- both must return the same
    # legitimate "no quote" empty frame, not raise.
    out_default = E.load_quote_window(tmp_path, "2026-09-10", "MCL")
    out_dbeq = E.load_quote_window(tmp_path, "2026-09-10", "MCL",
                                    dataset="DBEQ.BASIC", schema="mbp-1")
    for out in (out_default, out_dbeq):
        assert list(out.columns) == ["ts", "bid", "ask"]
        assert out.empty


# --- CLI: --quote-dataset/--quote-schema exist, default to the registered
#     tape, and are independently overridable -----------------------------

def test_cli_quote_source_flags_default_to_the_registered_tape():
    args = E.build_parser().parse_args([])
    assert (args.quote_dataset, args.quote_schema) == (E.QUOTE_DATASET, E.QUOTE_SCHEMA)
    assert (E.QUOTE_DATASET, E.QUOTE_SCHEMA) == ("XNAS.BASIC", "cbbo-1s")


def test_cli_quote_source_flags_are_overridable_independently_of_bars():
    args = E.build_parser().parse_args(
        ["--quote-dataset", "DBEQ.BASIC", "--quote-schema", "mbp-1"])
    assert args.quote_dataset == "DBEQ.BASIC"
    assert args.quote_schema == "mbp-1"
    # BARS_DATASET is a module constant, not a CLI flag -- there is no way
    # to override it from the command line at all.
    assert not hasattr(args, "bars_dataset")
    assert not hasattr(args, "dataset")
    assert E.BARS_DATASET == "XNAS.BASIC"


# --- static checks on main()/run_day: BARS_DATASET feeds build_tasks no
#     matter what --quote-dataset is; quote_dataset/quote_schema are
#     threaded through the task tuple (not read off a mutated global,
#     which would silently not reach a spawned worker process on Windows)

def test_main_builds_tasks_from_bars_dataset_not_a_cli_flag():
    src = inspect.getsource(E.main)
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
              and getattr(n.func, "attr", None) == "build_tasks"]
    assert calls, "main() no longer calls G.build_tasks"
    call = calls[0]
    # third positional arg is the dataset build_tasks reads bars from
    dataset_arg = call.args[2]
    assert isinstance(dataset_arg, ast.Name) and dataset_arg.id == "BARS_DATASET", (
        "build_tasks() must be called with the BARS_DATASET constant, "
        "never args.quote_dataset or the old DATASET name -- a re-run on a "
        "different quote tape must not also swap which bars the engine sees"
    )


def test_run_day_forwards_quote_dataset_and_schema_to_load_quote_window():
    src = inspect.getsource(E.run_day)
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
              and getattr(n.func, "id", None) == "load_quote_window"]
    assert calls, "run_day no longer calls load_quote_window"
    call = calls[0]
    arg_names = [a.id for a in call.args if isinstance(a, ast.Name)]
    assert "quote_dataset" in arg_names and "quote_schema" in arg_names, (
        f"load_quote_window call in run_day doesn't pass through the "
        f"per-task quote source (got args: {arg_names})"
    )


def test_task_tuples_carry_quote_dataset_and_schema_not_a_module_global():
    """On Windows, ProcessPoolExecutor uses spawn: each worker re-imports
    this module fresh, so a global mutated in main() after tasks are built
    would silently revert to the module-level default in every worker. The
    only safe way to hand a worker a non-default quote source is through
    the task tuple itself."""
    src = inspect.getsource(E.main)
    assert "args.quote_dataset, args.quote_schema" in src.replace("\n", " ").replace("  ", " ") or \
        ("quote_dataset" in src and "quote_schema" in src and "for pp, d, u in tasks" in src)
