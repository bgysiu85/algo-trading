#!/usr/bin/env python3
"""Contract 1.8: the feed's real-time state, and the one way it must never fail.

`claude/feed_state_CONTRACT_PROPOSAL_20260918.md`. The block itself is trivial;
what needs pinning is the failure direction. Every one of these is a way the
portal could end up showing "Real-time" while the watchlist is a quarter of an
hour old:

  - a missing, truncated, corrupt or half-written file;
  - a value TradingView starts sending that this code does not recognise;
  - a delay string whose number will not parse;
  - a file left over from YESTERDAY's session, which is the one that survives
    a reboot and looks completely normal.

And one that sends Ben to the wrong fix rather than lying outright: a half-set
cookie pair reported as "no cookie is set".
"""
from __future__ import annotations

import json

import pytest

from common import feed_state as FS


# --- the mapping --------------------------------------------------------------

def test_streaming_is_zero_delay_not_a_missing_one():
    b = FS.block("STREAMING", "streaming", "signed")
    assert b["mode"] == "streaming"
    assert b["delay_seconds"] == 0
    assert b["authenticated"] is True
    assert b["detail"] == "streaming"


def test_the_delay_is_parsed_here_once_and_in_python():
    """`delayed_streaming_900`. Parsing it a second time in JavaScript would be
    a second definition of 'delayed' in a second language, and the day the
    vendor writes it differently the page is the one on screen."""
    b = FS.block("DELAYED", "delayed_streaming_900", "absent")
    assert b["mode"] == "delayed"
    assert b["delay_seconds"] == 900
    assert b["detail"] == "delayed_streaming_900", "the raw value must survive"


def test_a_delay_with_no_number_in_it_is_null_and_never_zero():
    """Zero means real time. An unparsed delay is not real time, and returning
    0 would render a delayed feed as current -- the exact mistake the block
    exists to prevent."""
    b = FS.block("DELAYED", "delayed", "signed")
    assert b["mode"] == "delayed"
    assert b["delay_seconds"] is None


def test_an_unrecognised_value_is_unknown_and_not_streaming():
    """`mode_verdict` has FOUR answers and the contract has three. UNRECOGNISED
    maps to `unknown`: a value that is neither streaming nor delayed is not a
    fourth thing the portal can render, and it is certainly not real time."""
    b = FS.block("UNRECOGNISED", "some_new_mode_v2", "signed")
    assert b["mode"] == "unknown"
    assert b["delay_seconds"] is None
    assert b["detail"] == "some_new_mode_v2", "the tooltip needs the raw value"


def test_no_reading_at_all_is_unknown():
    b = FS.block("UNKNOWN", None, "absent")
    assert b["mode"] == "unknown"
    assert b["detail"] is None


# --- the cookie state, which decides what Ben is told to do -------------------

def test_a_half_set_pair_is_incomplete_rather_than_absent():
    """THE ONE WORTH HAVING. TradingView SIGNS the session, so `sessionid`
    alone is served anonymously. Reported as `absent` the banner would tell Ben
    no cookie is set while one is, and send him to the wrong fix."""
    assert FS.cookie_state("abc", None) == "incomplete"
    assert FS.cookie_state(None, "sig") == "incomplete"
    assert FS.cookie_state("abc", "sig") == "signed"
    assert FS.cookie_state(None, None) == "absent"


def test_no_cookie_on_purpose_is_disabled_not_absent():
    """--no-cookie is a fourth fix: restart without the flag. Told 'no cookie
    is set', Ben would set the variables and nothing would change."""
    assert FS.cookie_state("abc", "sig", disabled=True) == "disabled"
    assert FS.cookie_state(None, None, disabled=True) == "disabled"


def test_authenticated_means_a_signed_pair_actually_went_out():
    for state, expect in (("signed", True), ("absent", False),
                          ("incomplete", False), ("disabled", False)):
        assert FS.block("DELAYED", "delayed_streaming_900",
                        state)["authenticated"] is expect


def test_an_unknown_cookie_state_degrades_to_absent_rather_than_through():
    b = FS.block("STREAMING", "streaming", "probably-fine")
    assert b["cookie_state"] == "absent"


# --- the file, and every way reading it can go wrong --------------------------

def test_a_round_trip_survives_the_file(tmp_path):
    p = tmp_path / "feed_state.json"
    want = FS.block("DELAYED", "delayed_streaming_900", "signed")
    assert FS.publish(want, p) is True
    assert FS.read(p) == want


def test_a_missing_file_reads_as_nothing_rather_than_raising(tmp_path):
    assert FS.read(tmp_path / "never_written.json") is None


@pytest.mark.parametrize("body", [
    "",                                    # truncated to nothing
    "{",                                   # half-written
    "null",                                # valid JSON, not a block
    "[1, 2, 3]",                           # valid JSON, wrong shape
    '{"mode": "realtime"}',                # a mode this contract does not have
    '{"mode": "streaming"}',               # no checked_at: not a reading
    '{"source": "tradingview"}',           # no mode at all
])
def test_anything_wrong_with_the_file_reads_as_nothing(tmp_path, body):
    """NEVER `streaming`. A reader that defaults to the good value on error is
    the same defect as a cookie that silently degrades to anonymous: a control
    whose output is indistinguishable from the failure it detects."""
    p = tmp_path / "feed_state.json"
    p.write_text(body, encoding="utf-8")
    assert FS.read(p) is None


def test_the_write_is_atomic_so_a_reader_never_sees_half_a_file(tmp_path):
    """The temp file sits in the SAME directory, so os.replace is a rename
    within one filesystem. A reader sees the old file or the new one."""
    p = tmp_path / "feed_state.json"
    FS.publish(FS.block("STREAMING", "streaming", "signed"), p)
    FS.publish(FS.block("DELAYED", "delayed_streaming_900", "signed"), p)
    assert FS.read(p)["mode"] == "delayed"
    assert not list(tmp_path.glob("*.tmp")), "a temp file was left behind"


def test_a_publish_that_fails_halfway_leaves_the_PREVIOUS_reading_whole(
        tmp_path, monkeypatch):
    """What atomicity actually buys, stated as behaviour rather than as an
    implementation note. The new content goes to a temp file first, so a
    failure at the moment of swapping cannot leave the reader looking at half
    a block -- it leaves them looking at the last complete one. Writing in
    place would destroy a good reading to produce a broken one."""
    p = tmp_path / "feed_state.json"
    FS.publish(FS.block("STREAMING", "streaming", "signed"), p)

    def boom(src, dst):
        raise OSError("no space left on device")
    monkeypatch.setattr(FS.os, "replace", boom)

    assert FS.publish(FS.block("DELAYED", "delayed_streaming_900", "signed"),
                      p) is False
    assert FS.read(p)["mode"] == "streaming", "the previous reading was clobbered"
    assert not list(tmp_path.glob("*.tmp")), "a temp file was left behind"


def test_a_write_that_fails_says_so_instead_of_raising(tmp_path):
    """A feed that will not start because a diagnostic file could not be
    written is worse than one that starts without it."""
    blocked = tmp_path / "a-file"
    blocked.write_text("not a directory", encoding="utf-8")
    assert FS.publish(FS.block("STREAMING", "streaming", "signed"),
                      blocked / "nested" / "feed_state.json") is False


def test_the_initial_block_is_unknown_so_yesterdays_file_cannot_survive(tmp_path):
    """STALENESS IS THE WRITER'S JOB. var/ survives across days, so yesterday's
    file would render as a confident Real-time all through this morning.
    Publishing `unknown` before the first check means the file can never
    describe a session it does not belong to, and neither side has to invent an
    age rule."""
    p = tmp_path / "feed_state.json"
    FS.publish(FS.block("STREAMING", "streaming", "signed"), p)   # yesterday
    assert FS.read(p)["mode"] == "streaming"
    FS.publish(FS.initial("signed"), p)                            # this morning
    got = FS.read(p)
    assert got["mode"] == "unknown"
    assert got["delay_seconds"] is None
    assert got["checked_at"], "an unknown reading still has a time"


def test_the_block_carries_every_field_the_portal_renders():
    b = FS.block("DELAYED", "delayed_streaming_900", "signed")
    assert set(b) == {"source", "mode", "delay_seconds", "authenticated",
                      "cookie_state", "checked_at", "detail"}
    assert b["source"] == "tradingview"
    assert json.loads(json.dumps(b)) == b, "the block must be JSON-serialisable"


def test_the_source_survives_the_feed_changing():
    """If the watchlist ever comes from IB's scanner the tile still reads
    correctly, rather than the field having to be replaced."""
    b = FS.block("STREAMING", "streaming", "disabled", source="ibkr")
    assert b["source"] == "ibkr" and b["mode"] == "streaming"
