#!/usr/bin/env python3
"""The TradingView login, the column that says whether it worked, and arrivals.

From the analysis chat's handover (`claude/handover_live_screen_feed_20260918.md`).
`tv_feed` posts to the scanner endpoint with no cookie, so Ben's premium
entitlement has never reached it. Whether the rows are therefore DELAYED is
answered by TradingView's own `update_mode` column and is still unmeasured; this
module gains the ability to send the cookie and to read the column, and changes
nothing at all when the environment is empty.

THE TEST THAT MATTERS MOST is the half-set pair. TradingView signs the session:
`sessionid` without `sessionid_sign` is accepted and served ANONYMOUSLY. A feed
that sent one of them would look logged in, read delayed data, and raise nothing
-- and a probe built the same way would report "the login makes no difference"
and close the question for the wrong reason.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from common import tv_feed
from common.tv_feed import Arrivals, cookie_header, mode_verdict, session_cookie

ET = ZoneInfo("America/New_York")


# --- the cookie pair ---------------------------------------------------------

def test_both_cookies_make_a_header():
    assert cookie_header("abc", "sig") == "sessionid=abc; sessionid_sign=sig"


@pytest.mark.parametrize("sid,sign", [("abc", None), (None, "sig"),
                                      ("abc", ""), ("", "sig"), (None, None)])
def test_a_half_set_pair_is_NO_cookie_and_never_a_partial_header(sid, sign):
    """An anonymous request wearing a login is the worst of both: it looks
    authenticated in the code and is served delayed by the server."""
    assert cookie_header(sid, sign) is None


def test_the_half_set_case_is_reported_loudly_rather_than_silently(monkeypatch, caplog):
    monkeypatch.setenv(tv_feed.COOKIE_ENV, "abc")
    monkeypatch.delenv(tv_feed.SIGN_ENV, raising=False)
    with caplog.at_level("ERROR"):
        assert session_cookie() is None
    assert any("ANONYMOUSLY" in r.message or "ANONYMOUSLY" in str(r.msg)
               for r in caplog.records), caplog.text


def test_both_unset_is_silent_and_returns_none(monkeypatch, caplog):
    """No cookie is the shipped state today, not a fault."""
    monkeypatch.delenv(tv_feed.COOKIE_ENV, raising=False)
    monkeypatch.delenv(tv_feed.SIGN_ENV, raising=False)
    with caplog.at_level("ERROR"):
        assert session_cookie() is None
    assert not caplog.records


def test_the_cookie_is_never_a_command_line_flag():
    """A flag puts the secret in shell history -- the rule DATABENTO_API_KEY
    carries."""
    flat = [s for a in tv_feed.build_parser()._actions for s in a.option_strings]
    assert not any(k in s for s in flat for k in ("session", "cookie-value", "token")), flat
    assert "--no-cookie" in flat, "there must be a way to force anonymous"


def test_no_cookie_means_the_request_is_byte_identical_to_todays(monkeypatch):
    """Nothing changes until the environment says so. The steady-state poll
    must carry exactly the headers it carried before this existed."""
    seen = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(tv_feed.urllib.request, "urlopen",
                        lambda req, timeout=None: (seen.update(
                            headers=dict(req.header_items())), FakeResp())[1])
    monkeypatch.setattr(tv_feed.json, "load", lambda fh: {"data": []})
    tv_feed._scan({"filter": []})
    assert not [k for k in seen["headers"] if k.lower() == "cookie"]
    assert {k.lower() for k in seen["headers"]} == {"content-type", "user-agent"}


# --- update_mode -------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    ("streaming", "STREAMING"),
    ("delayed_streaming_900", "DELAYED"),
    ("delayed", "DELAYED"),
    ("end_of_day", "UNRECOGNISED"),
    (None, "UNKNOWN"),
])
def test_the_verdict_reads_the_column(raw, want):
    assert mode_verdict(raw) == want


def test_delayed_wins_over_streaming_in_a_compound_value():
    """`delayed_streaming_900` contains BOTH words. Checking for 'streaming'
    first would read a fifteen-minute delay as real time -- and TradingView
    spells the delay in seconds into that very string."""
    assert mode_verdict("delayed_streaming_900") == "DELAYED"


def _fake_scan(monkeypatch, value):
    def scan(payload, cookie=None):
        cols = payload["columns"]
        assert cols[-1] == tv_feed.MODE_COLUMN, "the column was not requested"
        return {"data": [{"s": "NASDAQ:VEEA",
                          "d": [None] * (len(cols) - 1) + [value]}]}
    monkeypatch.setattr(tv_feed, "_scan", scan)


def test_a_cookie_that_is_sent_and_still_delayed_is_an_ERROR(monkeypatch, caplog):
    """The expiry case, and the reason the check exists at all. A stale cookie
    does not fail -- the endpoint serves the anonymous feed and a delayed
    watchlist looks exactly like a real-time one."""
    _fake_scan(monkeypatch, "delayed_streaming_900")
    with caplog.at_level("ERROR"):
        verdict, raw = tv_feed.check_update_mode("sessionid=a; sessionid_sign=b")
    assert verdict == "DELAYED"
    assert any(r.levelname == "ERROR" for r in caplog.records)
    assert "expired" in caplog.text.lower()


def test_delayed_with_no_cookie_is_a_warning_not_an_error(monkeypatch, caplog):
    """That is today's shipped state. Logging it at ERROR would train the
    reader to ignore the line that matters."""
    _fake_scan(monkeypatch, "delayed_streaming_900")
    with caplog.at_level("WARNING"):
        verdict, _ = tv_feed.check_update_mode(None)
    assert verdict == "DELAYED"
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_streaming_says_so(monkeypatch, caplog):
    _fake_scan(monkeypatch, "streaming")
    with caplog.at_level("INFO"):
        verdict, _ = tv_feed.check_update_mode(None)
    assert verdict == "STREAMING"
    assert "REAL TIME" in caplog.text


def test_the_check_never_stops_the_feed_starting(monkeypatch, caplog):
    """A feed that refuses to start because a diagnostic failed is worse than
    one that starts without it."""
    def boom(payload, cookie=None):
        raise TimeoutError("no answer")

    monkeypatch.setattr(tv_feed, "_scan", boom)
    with caplog.at_level("WARNING"):
        assert tv_feed.check_update_mode(None) == ("UNKNOWN", None)


def test_the_check_does_not_change_the_polls_own_columns(monkeypatch):
    """It asks in its OWN request, so the 1,980 polls of a session stay
    byte-identical to what they were before this existed."""
    from common.tv_screener import COLUMNS
    _fake_scan(monkeypatch, "streaming")
    tv_feed.check_update_mode(None)
    assert list(tv_feed.tv_payload()["columns"]) == list(COLUMNS)


def test_the_cookie_value_is_never_logged(monkeypatch, caplog):
    _fake_scan(monkeypatch, "delayed_streaming_900")
    with caplog.at_level("DEBUG"):
        tv_feed.check_update_mode("sessionid=SECRETVALUE; sessionid_sign=SIGVALUE")
    assert "SECRETVALUE" not in caplog.text and "SIGVALUE" not in caplog.text


# --- arrivals ----------------------------------------------------------------

def test_a_name_is_stamped_once_at_its_FIRST_appearance(tmp_path):
    """The measurement the archive cannot make retrospectively: a single 09:29
    snapshot has no per-name arrival times, which is why the only timing
    evidence on record is eight blocked names."""
    a = Arrivals(root=tmp_path)
    day = datetime(2026, 9, 19, 4, 0, 5, tzinfo=ET)
    a.begin_session(day.date())
    assert a.record(["VEEA"], {"VEEA": "hot"}, day) == ["VEEA"]
    later = datetime(2026, 9, 19, 4, 5, 0, tzinfo=ET)
    assert a.record(["VEEA", "BIAF"], {"VEEA": "hot", "BIAF": "cold"}, later) == ["BIAF"]

    lines = (tmp_path / "watchlist_arrivals_20260919.csv").read_text(
        encoding="utf-8").splitlines()
    assert lines[0] == "ticker,first_et,tier"
    assert lines[1] == "VEEA,2026-09-19 04:00:05,hot"
    assert lines[2] == "BIAF,2026-09-19 04:05:00,cold"


def test_a_new_session_starts_a_new_file_and_forgets(tmp_path):
    a = Arrivals(root=tmp_path)
    d1 = datetime(2026, 9, 19, 4, 0, 5, tzinfo=ET)
    a.begin_session(d1.date())
    a.record(["VEEA"], {}, d1)
    d2 = datetime(2026, 9, 20, 4, 0, 5, tzinfo=ET)
    a.begin_session(d2.date())
    assert a.record(["VEEA"], {}, d2) == ["VEEA"], "yesterday's stamp suppressed today's"
    assert (tmp_path / "watchlist_arrivals_20260920.csv").exists()


def test_it_appends_so_a_crash_keeps_what_it_had(tmp_path):
    a = Arrivals(root=tmp_path)
    day = datetime(2026, 9, 19, 4, 0, 5, tzinfo=ET)
    a.begin_session(day.date())
    a.record(["VEEA"], {}, day)
    b = Arrivals(root=tmp_path)          # a restart mid-session
    b.begin_session(day.date())
    b.record(["BIAF"], {}, day)
    text = (tmp_path / "watchlist_arrivals_20260919.csv").read_text(encoding="utf-8")
    assert "VEEA" in text and "BIAF" in text
    assert text.count("ticker,first_et,tier") == 1, "the header was written twice"


def test_a_disk_failure_costs_a_ROW_and_never_a_POLL(tmp_path, monkeypatch):
    """Telemetry inside the loop that keeps the watchlist current. A hiccup
    here must not raise into the poll."""
    a = Arrivals(root=tmp_path / "nope")
    day = datetime(2026, 9, 19, 4, 0, 5, tzinfo=ET)
    a.begin_session(day.date())
    monkeypatch.setattr(tv_feed.Path, "mkdir",
                        lambda *args, **kw: (_ for _ in ()).throw(OSError("full")))
    assert a.record(["VEEA"], {}, day) == ["VEEA"]


def test_the_loop_records_arrivals_only_for_what_it_WROTE(monkeypatch, tmp_path):
    """A held name is not in the file, so it has not arrived. Stamping it would
    date it earlier than the trader could ever have acted on it -- and this
    series exists precisely to measure that lag."""
    polls = [[{"ticker": "BIAF", "symbol": "NASDAQ:BIAF", "premarket_close": 5.0,
               "premarket_volume": 480_000},
              {"ticker": "VEEA", "symbol": "NASDAQ:VEEA", "premarket_close": 5.0,
               "premarket_volume": 120_000}]]
    monkeypatch.setattr(tv_feed, "fetch", lambda limit=None, cookie=None:
                        [dict(r) for r in polls[0]])
    out = tmp_path / "watchlist.txt"
    args = tv_feed.build_parser().parse_args(
        ["--once", "--all-hours", "--out", str(out), "--no-telegram",
         "--heartbeat", "0"])
    arr = Arrivals(root=tmp_path / "archive")
    tv_feed._loop(args, tv_feed.Ranking(), tv_feed.Freshness(), arr, None,
                  tv_feed.notify.Notifier(), set(), 0.0, 0.0)
    files = list((tmp_path / "archive").glob("watchlist_arrivals_*.csv"))
    body = files[0].read_text(encoding="utf-8") if files else ""
    assert "BIAF" not in body and "VEEA" not in body, body


# --- main() wires them in ----------------------------------------------------
#
# THE GAP A _loop TEST LEAVES, and mutation testing found it: every assertion
# above drives `_loop` directly, so `main` could fail to build the cookie or
# skip the startup check entirely and nothing would notice.

def _main_once(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(tv_feed, "fetch", lambda limit=None, cookie=None: [])
    calls = {}
    monkeypatch.setattr(tv_feed, "check_update_mode",
                        lambda ck: (calls.update(checked=True, cookie=ck),
                                    ("STREAMING", "streaming"))[1])
    monkeypatch.setattr(tv_feed, "Arrivals",
                        lambda root=None: Arrivals(root=tmp_path / "archive"))
    state = tmp_path / "feed_state.json"
    assert tv_feed.main(argv + ["--once", "--dry-run", "--all-hours",
                                "--no-telegram", "--heartbeat", "0",
                                "--feed-state", str(state)]) == 0
    calls["state"] = state
    return calls


def test_main_publishes_the_contract_1_8_feed_block(monkeypatch, tmp_path):
    """main() is where the state file gets wired, and a _loop test would not
    see it -- the same gap that let main skip the startup check entirely."""
    from common import feed_state as FS
    monkeypatch.setenv(tv_feed.COOKIE_ENV, "abc")
    monkeypatch.setenv(tv_feed.SIGN_ENV, "sig")
    got = FS.read(_main_once(monkeypatch, tmp_path, [])["state"])
    assert got is not None, "main() published nothing for the portal to read"
    assert got["mode"] == "streaming" and got["delay_seconds"] == 0
    assert got["cookie_state"] == "signed" and got["authenticated"] is True


def test_main_records_no_cookie_as_disabled_rather_than_absent(
        monkeypatch, tmp_path):
    """Told 'no cookie is set', Ben sets both variables and nothing changes --
    the flag is still on the command line."""
    from common import feed_state as FS
    monkeypatch.setenv(tv_feed.COOKIE_ENV, "abc")
    monkeypatch.setenv(tv_feed.SIGN_ENV, "sig")
    got = FS.read(_main_once(monkeypatch, tmp_path, ["--no-cookie"])["state"])
    assert got["cookie_state"] == "disabled" and got["authenticated"] is False


def test_main_checks_update_mode_before_it_starts_polling(monkeypatch, tmp_path):
    monkeypatch.delenv(tv_feed.COOKIE_ENV, raising=False)
    monkeypatch.delenv(tv_feed.SIGN_ENV, raising=False)
    calls = _main_once(monkeypatch, tmp_path, [])
    assert calls.get("checked"), "the feed started without reading update_mode"
    assert calls["cookie"] is None


def test_main_sends_the_cookie_when_BOTH_variables_are_set(monkeypatch, tmp_path):
    monkeypatch.setenv(tv_feed.COOKIE_ENV, "abc")
    monkeypatch.setenv(tv_feed.SIGN_ENV, "sig")
    calls = _main_once(monkeypatch, tmp_path, [])
    assert calls["cookie"] == "sessionid=abc; sessionid_sign=sig"


def test_no_cookie_forces_anonymous_even_with_the_variables_set(monkeypatch, tmp_path):
    """The escape hatch the probe needs: run the feed anonymously on a machine
    where the cookie is configured, to compare the two."""
    monkeypatch.setenv(tv_feed.COOKIE_ENV, "abc")
    monkeypatch.setenv(tv_feed.SIGN_ENV, "sig")
    calls = _main_once(monkeypatch, tmp_path, ["--no-cookie"])
    assert calls["cookie"] is None
