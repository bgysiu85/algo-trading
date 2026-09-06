#!/usr/bin/env python3
"""Print a report AND save it, in UTF-8, from Python.

WHY NOT JUST REDIRECT IN POWERSHELL
------------------------------------
Because PROGRAM_INDEX section 5 already records what happens: `Tee-Object`
writes UTF-16, `>` in PS 5.1 does much the same, and `$ErrorActionPreference =
"Stop"` plus `2>&1` turns Python's stderr into a terminating error. A saved
report that is UTF-16 with a BOM is then read back as mojibake or not at all,
and the failure appears at the far end -- when something tries to parse it --
rather than where it was caused.

Writing the file from Python sidesteps every one of those. The encoding is
chosen here, once, and the shell is not involved.

WHY IT MATTERS BEYOND TIDINESS
-------------------------------
These runs happen on Ben's machine and are read in a Claude session that can
see D:\\Trading. A report that exists only in terminal scrollback has to be
copied by hand, which is slow, truncates, and loses the exact figures. A report
on disk is just read. Every tool here that produces a summary should therefore
take --out and use it by default, so the record is a side effect of running
rather than a thing someone remembers to do.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def emit(text: str, out: str | Path | None = None, *, header: str = "") -> None:
    """Print to stdout and, when `out` is given, write the same text as UTF-8.

    The file gets a timestamp line the terminal does not, because a saved
    report read weeks later needs to say when it was produced -- half the
    figures in this project have been quietly superseded by a later run.
    """
    print(text)
    if not out:
        return
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    body = (f"# generated {stamp}\n"
            + (f"# {header}\n" if header else "")
            + "\n" + text + "\n")
    p.write_text(body, encoding="utf-8")
    print(f"\nreport written to {p}")
