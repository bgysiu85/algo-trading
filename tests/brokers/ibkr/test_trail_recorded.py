#!/usr/bin/env python3
"""The trail a trade ran at has to be IN the fill log.

The portal can change TRAIL_PCT mid-session. Before it could, the trail was a
module constant and the log did not need to say so -- every row in a session
ran the same width, and the width was in the repo. The moment a browser button
could change it, that stopped being true, and rows taken at 5% became
indistinguishable from rows taken at 9% in the one ledger every study reads.

That is this project's recurring defect shape: a number that used to be fixed
becomes variable, and the record does not follow.
"""
from __future__ import annotations

import csv

import pytest

from brokers.ibkr import trader as T


def test_the_column_exists():
    assert "trail_pct" in T.FIELDS


def test_it_is_not_confused_with_the_volume_average():
    """trail_avg is a 60-bar volume average. The names are one character apart
    and mean nothing alike; a reader who conflates them draws a conclusion
    about stops from a conclusion about volume."""
    assert "trail_avg" in T.FIELDS and "trail_pct" in T.FIELDS
    assert T.FIELDS.index("trail_avg") != T.FIELDS.index("trail_pct")


def test_a_column_missing_from_FIELDS_is_dropped_in_silence(tmp_path):
    """Why the column matters rather than just the keyword argument: the writer
    is DictWriter(extrasaction="ignore"). Passing trail_pct without listing it
    in FIELDS writes nothing and raises nothing."""
    log = T.FillLog(tmp_path / "f.csv")
    log.write(symbol="AAA", action="BUY", trail_pct=7.5, not_a_column=1)
    log.close()

    row = next(csv.DictReader((tmp_path / "f.csv").open(newline="", encoding="utf-8")))
    assert row["trail_pct"] == "7.5"
    assert "not_a_column" not in row


def test_a_log_from_before_the_column_is_rolled_aside_not_appended_to(tmp_path):
    """Appending would put today's values under yesterday's header, silently
    misaligned -- and this CSV is the entire point of the exercise."""
    path = tmp_path / "f.csv"
    path.write_text("ts_et,symbol,action\n2026-09-14,AAA,BUY\n", encoding="utf-8")

    log = T.FillLog(path)
    log.close()

    assert list(csv.DictReader(path.open(newline="", encoding="utf-8")).fieldnames) == T.FIELDS
    rolled = [p for p in tmp_path.iterdir() if "_pre" in p.name]
    assert len(rolled) == 1, "the old log must be kept, not overwritten"
    assert "2026-09-14,AAA,BUY" in rolled[0].read_text(encoding="utf-8")


# -- which value gets written -----------------------------------------------

class _Adapter:
    def __init__(self, trail_pct):
        self.trail_pct = trail_pct


class _Position:
    def __init__(self, trail_pct):
        self.trail_pct = trail_pct


class _State:
    def __init__(self, strategy=None, position=None):
        self.symbol = "AAA"
        self.strategy = strategy
        self.position = position


def test_an_entry_records_the_width_it_is_about_to_be_opened_with():
    """No position yet, so the strategy's current value is the truth -- it is
    what stamps the Position moments later."""
    st = _State(strategy=_Adapter(5.0))
    assert T.MCLPaperTrader._trail_for(st) == 5.0


def test_an_exit_records_the_positions_own_width_not_the_strategys():
    """THE CASE THE PORTAL CREATED. Someone moves the trail to 9% while a
    position opened at 5% is still running. That position exits on its 5%
    trail -- the strategy's 9% had nothing to do with it. Recording 9% on the
    exit row would attribute the stop to a width that never applied."""
    st = _State(strategy=_Adapter(9.0), position=_Position(5.0))
    assert T.MCLPaperTrader._trail_for(st) == 5.0


def test_an_unknowable_width_is_left_empty_rather_than_defaulted():
    """A wrong number here is worse than a blank one, because a reader would
    believe it."""
    assert T.MCLPaperTrader._trail_for(_State()) is None


def test_the_entry_reads_the_same_attribute_that_stamps_the_position():
    """The column is only worth having if it agrees with what actually governs
    the trade. Both must read st.strategy.trail_pct, or the log describes a
    trade that did not happen."""
    import inspect

    src = inspect.getsource(T.MCLPaperTrader.step_symbol)
    assert "trail_pct=st.strategy.trail_pct" in src, (
        "the Position stamp moved -- _trail_for must follow it")


# ---------------------------------------------------------------------------
# Encoding. Found 2026-09-14: a CONFIG row carried an em dash, FillLog opened
# the file with the LOCALE encoding (cp1252 on Windows), and the byte it wrote
# was undecodable to every reader that opens this file as UTF-8 -- which is
# churn_count, tv_reconcile and the portal. One character, and the whole
# session's log is unreadable to three of the four readers.
#
# Latent long before the CONFIG row: reject_reason has always been able to hold
# whatever IB sent back.

def test_the_log_is_written_utf8_whatever_the_locale(tmp_path):
    path = tmp_path / "f.csv"
    log = T.FillLog(path)
    log.write(symbol="AAA", action="BUY", reject_reason="em dash — here")
    log.close()

    # The assertion that matters is that a UTF-8 reader can read it back. On a
    # cp1252 default this raises UnicodeDecodeError before reaching the row.
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    assert rows[0]["reject_reason"] == "em dash — here"


def test_a_non_ascii_row_does_not_poison_the_whole_file(tmp_path):
    """The failure mode was not a bad field — it was a bad FILE. Every row
    after the offending byte becomes unreachable too."""
    path = tmp_path / "f.csv"
    log = T.FillLog(path)
    log.write(symbol="AAA", action="BUY", reject_reason="—")
    log.write(symbol="BBB", action="SELL", status="FILLED")
    log.close()

    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    assert [r["symbol"] for r in rows] == ["AAA", "BBB"]


def test_reading_the_old_header_survives_a_non_ascii_file(tmp_path):
    """The header check reads the existing file. It must not raise before it
    can decide to roll the file aside — that would make a damaged log
    unopenable rather than replaceable."""
    path = tmp_path / "f.csv"
    path.write_bytes(b"ts_et,symbol,action\n2026-09-14,AAA,\x97\n")

    log = T.FillLog(path)            # must not raise
    log.close()

    assert list(csv.DictReader(path.open(newline="", encoding="utf-8")).fieldnames) \
        == T.FIELDS


def test_the_log_names_its_encoding_explicitly(monkeypatch, tmp_path):
    """The round-trip test above passes on Linux whether or not FillLog names
    an encoding, because the locale default there IS utf-8 — it fails only on
    the platform the bug lives on. That is the same trap as writing a Windows
    junction test with symlink_to.

    The locale default cannot be forced from inside the process: CPython
    resolves it in C, and patching locale.getpreferredencoding or
    locale.getencoding does not reach it. So this asserts the thing that
    DETERMINES the behaviour — that the parameter is passed at all — which
    fails on every platform if it goes missing.
    """
    import pathlib

    seen = []
    real_open = pathlib.Path.open

    def recording_open(self, *args, **kwargs):
        seen.append((args, kwargs))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", recording_open)
    T.FillLog(tmp_path / "f.csv").close()

    appends = [kw for args, kw in seen if "a" in (args[0] if args else kw.get("mode", ""))]
    assert appends, "FillLog did not open the log for append"
    assert all(kw.get("encoding", "").lower().replace("-", "") == "utf8"
               for kw in appends), (
        f"the fill log was opened without encoding='utf-8': {appends}. On "
        "Windows that is cp1252, and one non-ASCII byte makes the whole file "
        "unreadable to every UTF-8 reader.")
