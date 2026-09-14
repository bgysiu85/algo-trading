#!/usr/bin/env python3
"""Accounting numbers and terminal colour.

The design point this file defends: brackets are produced AT THE FORMATTING
SITE and colour is applied to finished text. Doing brackets by rewriting
finished text was tried against Ben's existing reports and corrupted values --
`-0.1pp` became `(0).1pp` and `< -0.005` became `<(0.005)`. Colour has no such
failure mode: a mismatch paints the wrong characters, it never changes a digit.
"""
from __future__ import annotations

import io

import pytest

from common import report_fmt as F
from common.report_io import emit


# --- acct --------------------------------------------------------------------

def test_negatives_are_bracketed_and_positives_are_not():
    assert F.acct(-10.49, 8) == " (10.49)"
    assert F.acct(10.49, 8) == "   10.49"


def test_the_field_width_is_exact_so_columns_cannot_move():
    """The reason this is not a text rewrite. `(28,131)` is a character wider
    than `-28,131`, and a rewrite has to steal a space from somewhere -- which
    works mid-line and breaks a row's leading indent."""
    for v in (-28131.0, 28131.0, -5.0, 0.0, -0.5):
        assert len(F.acct(v, 11, 0)) == 11, v


def test_an_oversized_value_overflows_rather_than_truncating():
    """A clipped number is a wrong number and no column is worth that."""
    out = F.acct(-123456789.0, 4, 0)
    assert out == "(123,456,789)"


def test_a_value_that_rounds_to_zero_is_not_bracketed():
    """Brackets are a claim about sign. A figure displaying as 0.00 cannot
    support one, and `(0.00)` reads as a negative zero."""
    assert F.acct(-0.004, 8).strip() == "0.00"
    assert F.acct(-0.006, 8).strip() == "(0.01)"


def test_commas_can_be_turned_off():
    assert F.acct(-1234.0, 9, 0, comma=False).strip() == "(1234)"


# --- paint -------------------------------------------------------------------

def test_bracketed_figures_are_painted():
    assert F.RED in F.paint("net $ (28,131)")
    assert F.paint("net $ (28,131)").endswith(F.RESET)


def test_a_plain_negative_is_painted_for_reports_not_yet_converted():
    assert F.RED in F.paint("  median $-2.17")


def test_positives_are_left_alone():
    assert F.paint("  net $ 28,131  win 27.3%") == "  net $ 28,131  win 27.3%"


@pytest.mark.parametrize("text", [
    "# generated 2026-09-11 22:34:57",      # a date, not a negative
    "  546 sessions, cadence 60s, 04:00-09:30 ET",
    "  STABLE across $1.00-$8.92",
    "  drop-top-5 removes symbols",
    "  see friction_reconciliation_20260911.md",
])
def test_things_that_merely_contain_a_hyphen_are_not_painted(text):
    assert F.paint(text) == text


def test_a_percentage_point_delta_is_left_alone():
    """The exact token the bracket-by-rewrite attempt corrupted: it turned
    `-0.1pp` into `(0).1pp`, silently changing the value."""
    assert F.paint("  win rate 26.1% vs 26.2%  (-0.1pp)").count(F.RED) == 0


# --- emit --------------------------------------------------------------------

def test_colour_never_reaches_the_file(tmp_path, capsys):
    """An ANSI escape in a .txt is unreadable weeks later and defeats the
    reason report_io writes files at all."""
    p = tmp_path / "r.txt"
    emit("net $ (28,131)", p, colour=True)
    body = p.read_text(encoding="utf-8")
    assert "\x1b[" not in body
    assert "(28,131)" in body
    assert "\x1b[" in capsys.readouterr().out


def test_colour_off_prints_clean_text(capsys):
    emit("net $ (28,131)", colour=False)
    assert "\x1b[" not in capsys.readouterr().out


def test_a_redirect_gets_no_colour_without_anyone_passing_a_flag(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert not F.supports_colour(io.StringIO())


def test_no_color_is_honoured_even_when_set_empty(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "")

    class Tty(io.StringIO):
        def isatty(self):
            return True

    assert not F.supports_colour(Tty())


def test_a_number_the_pattern_cannot_parse_is_not_painted_in_half():
    """`win -9.0pp` used to match `-9.0`, fail on the `p`, backtrack to `-9`
    and paint that -- half a number in red, which on screen reads as -9."""
    line = "  stop change only  -27,260   per trade -6.50   win -9.0pp"
    out = F.paint(line)
    assert "-9.0pp" in out.replace(F.RED, "").replace(F.RESET, "")
    assert f"{F.RED}-9{F.RESET}" not in out
    assert f"{F.RED}-27,260{F.RESET}" in out
    assert f"{F.RED}-6.50{F.RESET}" in out
