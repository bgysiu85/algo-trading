#!/usr/bin/env python3
"""Accounting-style numbers for reports, and colour for the terminal only.

    from common.report_fmt import acct
    f"${acct(net, 11, 0)}"      ->  "$    (28,131)"

TWO SEPARATE JOBS, AND THEY HAVE VERY DIFFERENT RISK
-----------------------------------------------------
**Brackets are done AT THE FORMATTING SITE**, never by rewriting finished report
text. That is not fastidiousness -- the rewrite was tried first, over Ben's 40-odd
existing reports, and it corrupted values:

    win rate 26.1% vs 26.2%  (-0.1pp)   ->   ((0).1pp)
        < -0.005    68$   686$          ->   <(0.005)    68$   686$

The first is a number silently changed from -0.1 to 0. The second lost the space
that separated an operator from its operand. Both come from the same cause: a
regex cannot know which of a report's minus signs are money, which are ranges,
bullets, percentages-point deltas or fragments of a date. Alignment fails too --
`(28,131)` is a character wider than `-28,131`, and stealing a space back works
mid-line and breaks a row's leading indent.

Formatting at the site has neither problem. `acct` is handed a float and a field
width and returns exactly that width, so the column cannot move and a value
cannot be misread as something it is not.

**Colour is applied to the PRINTED COPY ONLY**, centrally in `report_io.emit`.
Colour is safe to do by pattern where brackets are not: a mismatch paints the
wrong characters red, it never changes a digit. It must never reach the file --
`\\x1b[31m` in a .txt is unreadable a week later and defeats the entire reason
these reports are written to disk (`report_io`'s own docstring).
"""
from __future__ import annotations

import os
import re
import sys

RED = "\x1b[31m"
RESET = "\x1b[0m"

# Bracketed money, which is what `acct` emits, plus a still-signed negative for
# the reports that have not adopted brackets yet. Anchored on a space or "$" and
# refusing a trailing word character so "2026-09-11", "drop-top-5", "04:00-09:30"
# and "$1.00-$8.92" are left alone. A miss here only mispaints; see the module
# docstring for why that asymmetry is the whole design.
#
# The trailing lookahead bans a digit, dot or comma as well as a word character,
# and that clause is load-bearing. Without it `win -9.0pp` matched `-9.0`, failed
# on the `p`, BACKTRACKED to `-9`, and painted half a number red -- which on
# screen reads as a value of -9. Refusing to match at all is the right answer for
# a token this pattern cannot parse.
_PAINT = re.compile(r"\((?:\d[\d,]*(?:\.\d+)?)\)"
                    r"|(?<=[\s$])-\d[\d,]*(?:\.\d+)?(?![\w%.,\d])")


def acct(value: float, width: int, dp: int = 2, comma: bool = True) -> str:
    """`value` right-aligned in exactly `width` characters, negatives bracketed.

    The width is honoured even when the brackets do not fit, in which case the
    field overflows rather than truncating -- a clipped number is a wrong number
    and there is no width worth that.

    A value that ROUNDS to zero is never bracketed. -0.004 at dp=2 prints
    "0.00", not "(0.00)": the brackets are a claim about sign, and a figure
    displaying as zero cannot support one.
    """
    fmt = f",.{dp}f" if comma else f".{dp}f"
    body = format(abs(value), fmt)
    if value < 0 and float(body.replace(",", "")) != 0.0:
        body = f"({body})"
    return body.rjust(width)


def supports_colour(stream=None) -> bool:
    """Whether to paint. A pipe, a redirect or NO_COLOR means no.

    `NO_COLOR` is honoured as the informal standard says: set at all, to
    anything including the empty string, disables colour.
    """
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        if not stream.isatty():
            return False
    except Exception:                                       # noqa: BLE001
        return False
    return _enable_windows_vt()


def _enable_windows_vt() -> bool:
    """Turn on virtual-terminal processing so Windows renders the escapes.

    Windows Terminal does this itself; a bare PowerShell 5.1 console does not,
    and without it the escapes print as literal garbage -- which is worse than
    no colour at all. Returning False on any failure means the caller simply
    does not paint.
    """
    if os.name != "nt":
        return True
    try:
        import ctypes
        k = ctypes.windll.kernel32                          # type: ignore[attr-defined]
        handle = k.GetStdHandle(-11)                        # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        return bool(k.SetConsoleMode(
            handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:                                       # noqa: BLE001
        return False


def paint(text: str) -> str:
    """Wrap negative figures in red. For stdout; never for a file."""
    return _PAINT.sub(lambda m: f"{RED}{m.group(0)}{RESET}", text)
