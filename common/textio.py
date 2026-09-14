#!/usr/bin/env python3
r"""Read a text file this repo wrote, whichever generation wrote it.

THE DEFECT THIS EXISTS FOR
--------------------------
`FillLog` opened the fill log with no `encoding=`, so it used the locale
default -- cp1252 on Ben's machine. The moment any non-ASCII byte reached
`reject_reason` (IB's own error text can carry one; a CONFIG row with an em
dash was the first that did), the FILE became undecodable to every UTF-8
reader from that byte onward. Not the row. The file.

That was fixed at the writer. **Fixing the writer does not fix the corpus.**
Every fill log already on disk is cp1252, and after the fix every new one is
UTF-8, so `var/fills/` now holds two generations under one naming convention.
The readers were split three ways and no single encoding reads both:

  * locale default -- `friction.load`, `db_load.load_paper_fills`,
    `trader._held_row`: correct on the old files, mojibake on the new ones,
    and on a non-Windows machine an outright `UnicodeDecodeError`;
  * strict UTF-8 -- `churn_count.load` (pandas defaults to UTF-8 regardless of
    locale), `tv_reconcile.load_fills`: correct on the new files, raises on
    every old one;
  * `utf-8-sig` -- `ui_bridge._fills_today`: same, plus BOM tolerance.

So the fix cannot be "pick the right encoding". It has to be a decoder that
reads both, and that is what this is.

WHY UTF-8 FIRST IS NOT A GUESS
------------------------------
The two orders are not symmetric. cp1252 decodes almost any byte sequence, so
TRYING IT FIRST WOULD ALWAYS SUCCEED and would silently turn every UTF-8 file
into mojibake -- exactly the failure mode that makes this class so quiet.
UTF-8 is a validating encoding: a cp1252 file with a high byte in it is almost
always INVALID UTF-8, so the attempt fails and the fallback is reached.

The residue: a cp1252 file whose high bytes happen to form a valid UTF-8
sequence -- literally the two characters `Ã©`, say -- decodes as UTF-8 into the
character it was already mojibake for. That is a file that was corrupt before
it got here, and it is stated rather than claimed away.

The encoding used is RETURNED, never just applied, so a caller that needs to
tell a reader which generation it read can say so instead of inferring it.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

# utf-8-sig, not utf-8: it strips a BOM when one is there and is identical to
# utf-8 when it is not. Excel writes the BOM and Ben opens these in Excel.
PREFERRED = "utf-8-sig"

# The Windows-1252 fallback. Named, not spelled inline, because "cp1252" in a
# call reads like a choice and this is a legacy-file accommodation.
LEGACY = "cp1252"


def decode(raw: bytes) -> tuple[str, str]:
    """(text, which encoding read it). UTF-8 first -- see the module note."""
    try:
        return raw.decode(PREFERRED), PREFERRED
    except UnicodeDecodeError:
        return raw.decode(LEGACY, errors="replace"), LEGACY


def read_text(path: str | Path) -> tuple[str, str]:
    return decode(Path(path).read_bytes())


def read_csv(path: str | Path) -> tuple[list[dict], str]:
    """Rows and the encoding they were read with.

    `newline=""` is what `csv` requires, and `io.StringIO` gives it for free:
    the bytes are decoded once, here, rather than by a file object whose
    encoding the caller forgot to name -- which is the whole defect.
    """
    text, enc = read_text(path)
    return list(csv.DictReader(io.StringIO(text, newline=""))), enc


def read_header(path: str | Path) -> tuple[list[str], str]:
    """The first line's fields, for a caller checking a column layout."""
    text, enc = read_text(path)
    first = text.splitlines()[0] if text else ""
    return (next(csv.reader([first])) if first else []), enc
