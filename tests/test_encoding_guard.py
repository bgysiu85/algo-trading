#!/usr/bin/env python3
"""No text-mode file is opened anywhere in this repo without naming its encoding.

THE FAILURE, 2026-09-16. `common/report_io.emit` writes UTF-8. The ORB grid's
test fixture read the report back with a bare `read_text()`, which on Ben's
Windows machine means cp1252, so every `§` in the report came back as `Â§` and
`assert "are NOT READ (§5)" in text` failed there and passed here. Same commit,
same code, two answers -- decided by the locale of whoever ran it.

It was one instance of a class: 242 text-mode opens across tests/, common/,
strategy/ and brokers/ carried no encoding. Every one that reads a file some
other code wrote in UTF-8 is a Windows-only failure waiting for a `§`, an em
dash, or an accented ticker name -- and the production ones are worse than the
test ones, because a fill log written in cp1252 and read in UTF-8 is not a
failing test, it is a wrong number.

`PYTHONUTF8=1` would make the symptom disappear on the machines that set it,
which is a way of hiding the defect from the person most likely to hit it.
So: every text-mode `open`, `Path.open`, `read_text`, `write_text` and
`gzip.open` names `encoding=` explicitly, and this guard refuses a bare one
anywhere in the tree.

The guard is checked against itself below (`test_the_guard_can_fail`) so that
it cannot pass by matching nothing -- a control whose output is
indistinguishable from the failure it detects is not a control.
"""
from __future__ import annotations

import ast
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCANNED = ("tests", "common", "strategy", "brokers", "main.py")

# Module-qualified opens that are not file text I/O or take no encoding.
NOT_FILE_TEXT = {"codecs", "zipfile", "tarfile", "io", "os", "webbrowser",
                 "urllib", "socket", "subprocess"}


UNKNOWN = object()      # a mode expression the scan cannot read statically


def _mode(call: ast.Call, path_first: bool):
    """The mode argument, or None when absent, or UNKNOWN when it is an
    expression rather than a literal. `path_first` is True for the builtin
    `open(path, mode)` and `gzip.open(path, mode)`; False for `Path.open(mode)`.
    The first draft read args[0] for all three and so mistook every builtin
    open's PATH for its mode -- caught by the self-check below."""
    idx = 1 if path_first else 0
    for kw in call.keywords:
        if kw.arg == "mode":
            return kw.value.value if isinstance(kw.value, ast.Constant) else UNKNOWN
    if len(call.args) > idx:
        a = call.args[idx]
        return a.value if isinstance(a, ast.Constant) else UNKNOWN
    return None


def _textio_aliases(tree: ast.AST) -> set[str]:
    """Names under which `common.textio` is bound in this module.

    `textio.read_text(path)` is the repo's own two-generation decoder -- it
    reads the cp1252 fill logs written before FillLog named its encoding AND
    the UTF-8 ones written since -- and it takes no `encoding=`. The mass fix
    of 2026-09-16 put one on it anyway and broke `churn_count.load`, which is
    why this guard exempts the real thing by import rather than by the letter
    `T`, which is also what three test files call the trader."""
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == "common":
            for a in n.names:
                if a.name == "textio":
                    names.add(a.asname or "textio")
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name == "common.textio":
                    names.add(a.asname or "common.textio")
    return names


def bare_text_opens(source: str, filename: str = "<unknown>") -> list[tuple[int, str]]:
    """(line, call name) for every text-mode open with no `encoding=`.

    `filename` reaches `ast.parse` so that a SyntaxWarning raised while
    parsing -- Python 3.14 warns on `"\\."` in a non-raw string -- names the
    file it came from instead of `<unknown>`, which is what Ben saw."""
    hits = []
    # A SyntaxWarning at parse time -- Python 3.14 warns on `"\\."` in a
    # non-raw string -- is an error in a later Python. Refused here, now,
    # where the file is named, rather than found on the day the interpreter
    # moves. brokers/ibkr/scan_params.py carried one in its docstring.
    # 3.12+ raises SyntaxWarning for it; 3.11 raised DeprecationWarning for
    # the same thing. Both are the same defect and both are refused.
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        warnings.simplefilter("error", DeprecationWarning)
        tree = ast.parse(source, filename=filename)
    textio = _textio_aliases(tree)
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute):
            name, recv = f.attr, f.value
        elif isinstance(f, ast.Name):
            name, recv = f.id, None
        else:
            continue
        if name not in ("open", "read_text", "write_text"):
            continue
        if recv is None and name != "open":
            # A bare `read_text(...)` is a function of this module or an
            # import -- textio's own, in one file -- never Path's method.
            continue
        if isinstance(recv, ast.Name) and recv.id in NOT_FILE_TEXT:
            continue
        if isinstance(recv, ast.Name) and recv.id in textio:
            continue
        if any(kw.arg == "encoding" for kw in n.keywords):
            continue
        if name == "open":
            is_gzip = isinstance(recv, ast.Name) and recv.id in ("gzip", "_gz")
            mode = _mode(n, path_first=(recv is None or is_gzip))
            if mode is UNKNOWN:
                # A parametrised mode cannot be judged here. Narrow and
                # visible: one such call exists, in test_artefact_guard.
                continue
            # gzip.open defaults to "rb"; builtin open and Path.open to "r".
            if mode is None and is_gzip:
                continue
            if mode is not None and "b" in mode:
                continue
        hits.append((n.lineno, name))
    return hits


def _tree_files():
    for top in SCANNED:
        p = ROOT / top
        if p.is_file():
            yield p
        else:
            yield from sorted(p.rglob("*.py"))


def test_no_text_mode_open_in_the_tree_is_missing_its_encoding():
    offenders = []
    for p in _tree_files():
        for line, name in bare_text_opens(p.read_text(encoding="utf-8"),
                                          filename=str(p)):
            offenders.append(f"{p.relative_to(ROOT)}:{line}  {name}()")
    assert not offenders, (
        f"{len(offenders)} text-mode open(s) without encoding= -- each is a "
        "Windows-only failure waiting for a non-ASCII character:\n  "
        + "\n  ".join(offenders))


@pytest.mark.parametrize("src,want", [
    ('Path("x").read_text()', 1),
    ('Path("x").read_text(encoding="utf-8")', 0),
    ('p.write_text("a")', 1),
    ('p.write_text("a", encoding="utf-8")', 0),
    ('open("x")', 1),
    ('open("x", "w")', 1),
    ('open("x", "rb")', 0),
    ('open("x", mode="wb")', 0),
    ('open("x", encoding="utf-8")', 0),
    ('out.open("w", newline="")', 1),
    ('out.open("w", newline="", encoding="utf-8")', 0),
    ('gzip.open(p)', 0),                     # binary by default
    ('gzip.open(p, "rt")', 1),
    ('gzip.open(p, "wt", encoding="utf-8")', 0),
    ('gzip.open(p, "rb")', 0),
    ('os.open(p, 0)', 0),                    # not file text I/O
    ('codecs.open(p, "r", "utf-8")', 0),
    ('from common import textio as T\nT.read_text(p)', 0),   # the decoder itself
    ('read_text(p)', 0),                     # a bare function, not Path's
    ('from brokers.ibkr import trader as T\nT.read_text(p)', 1),  # same letter, not exempt
    ('open(HOLDOUT, mode)', 0),              # unreadable mode: skipped, on purpose
    ('open("x", mode)', 0),
    ('p.open(mode)', 0),
])
def test_the_guard_can_fail(src, want):
    """A guard that never fires is indistinguishable from its own absence.
    Each shape above is one the fixer had to handle on 2026-09-16."""
    assert len(bare_text_opens(src)) == want, src


def test_an_invalid_escape_is_refused_not_warned():
    """The compiler turns a parse-time warning under an "error" filter into a
    SyntaxError carrying the filename and line -- not into the warning class
    itself, which is what the first draft of this test waited for."""
    with pytest.raises(SyntaxError, match=r"planted\.py"):
        bare_text_opens('x = "a\\.b"', filename="planted.py")
    assert bare_text_opens('x = r"a\\.b"') == []


def test_the_guard_reads_the_tree_it_claims_to():
    """Not vacuous: the scan must actually reach the files that had the
    defect. If SCANNED were empty, or a rename moved tests/ out from under it,
    the first test would pass on nothing."""
    seen = {p.relative_to(ROOT).parts[0] for p in _tree_files()}
    assert {"tests", "common", "strategy", "brokers"} <= seen
    assert (ROOT / "tests" / "strategy" / "test_orb_grid.py") in set(_tree_files())
