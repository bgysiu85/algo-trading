#!/usr/bin/env python3
"""Which minute the trader acts on, and whether the trim costs it one.

Ben, 2026-09-09: TradingView signalled BNC at 06:21 ET and filled at $5.10;
the live trader filled at 06:23 at $5.22. One of those minutes is bookkeeping
-- a strategy that acts on a CLOSED bar cannot act on the 06:21 bar before
06:22, and TV marks the trade at the bar that produced it. The second minute
is the question, and `_fetch_bars` dropping the last bar of every response is
the suspect.

Nothing here talks to IB. What is tested is the classification -- the part
that decides which of two opposite conclusions the report reaches.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from brokers.ibkr import trader as T
from common import bar_freshness as B

ET = ZoneInfo("America/New_York")


def frame(last="2026-09-09 06:22", n=5):
    """A response whose LAST bar is labelled `last`. Bars are labelled at the
    interval START, which is the whole reason a 06:22 label can be either the
    minute in progress or a minute that ended a minute ago."""
    end = pd.Timestamp(last, tz=ET)
    idx = pd.DatetimeIndex(
        [end - timedelta(minutes=i) for i in reversed(range(n))],
        tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": 5.1, "high": 5.2, "low": 5.0, "close": 5.15,
                         "volume": 900.0}, index=idx)


def at(hhmmss="06:22:30"):
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return datetime(2026, 9, 9, h, m, s, tzinfo=ET)


# --- the classification ------------------------------------------------------

def test_a_bar_labelled_this_minute_is_the_one_still_forming():
    """06:22:30, last bar 06:22 -> that minute has not ended, so IB is
    including the forming bar and the trim is doing its job."""
    assert B.classify(at("06:22:30"), pd.Timestamp("2026-09-09 06:22", tz=ET)) \
        == "forming"


def test_a_bar_labelled_the_previous_minute_has_already_closed():
    """THE DEFECT THIS PROBE LOOKS FOR. At 06:22:30 the newest bar IB offers
    is 06:21, which closed at 06:22:00. Dropping it hands the strategy 06:20
    and every signal is a minute late."""
    assert B.classify(at("06:22:30"), pd.Timestamp("2026-09-09 06:21", tz=ET)) \
        == "closed"


def test_older_than_that_is_the_feed_itself_being_behind():
    """No trim setting fixes a feed that is two minutes back, so this must not
    be folded into 'closed' -- it sends the reader to a different problem."""
    assert B.classify(at("06:22:30"), pd.Timestamp("2026-09-09 06:20", tz=ET)) \
        == "stale"


@pytest.mark.parametrize("lag_s,expected", [
    (0, "forming"), (59, "forming"),
    (60, "closed"), (119, "closed"),
    (120, "stale"), (600, "stale"),
])
def test_the_boundaries_are_where_the_minute_actually_turns(lag_s, expected):
    """A minute is 60 seconds, not 'about a minute'. 59s and 60s must land on
    opposite sides or the two verdicts blur into each other."""
    now = at("06:30:00")
    assert B.classify(now, pd.Timestamp(now - timedelta(seconds=lag_s))) \
        == expected


# --- the ambiguous samples ---------------------------------------------------

def test_a_sample_taken_just_after_the_minute_rolls_is_not_counted():
    """At 06:23:02 a feed that is two seconds behind answers 06:22, which is
    62 seconds old and therefore reads as 'closed'. That is the WRONG verdict
    from a RIGHT feed, and it is the very verdict this probe is hunting, so
    counting it would confirm the hypothesis by accident."""
    assert B.at_minute_edge(at("06:23:02")) is True
    assert B.at_minute_edge(at("06:23:30")) is False


def test_the_edge_window_is_short_enough_to_leave_most_samples_usable():
    """A guard that discarded half the samples would be its own defect: the
    verdict is a majority over what survives."""
    assert 0 < B.EDGE_S <= 10


def test_an_edge_sample_is_recorded_rather_than_dropped():
    """Excluded from the counts, still visible in the report -- a sample that
    vanishes cannot be argued with."""
    r = B.sample(at("06:22:01"), frame(last="2026-09-09 06:21"))
    assert r["edge"] is True and r["kind"] == "closed"


# --- what the trader would act on --------------------------------------------

def test_acted_is_the_traders_own_trim_not_a_copy_of_it():
    """If this reimplemented `iloc[:-1]`, the probe would keep reporting the
    old answer after the trim changed -- and the trim changing is the whole
    point of running it."""
    df = frame(last="2026-09-09 06:22")
    r = B.sample(at("06:22:30"), df)
    expected = T.drop_forming_bar(df).index[-1].tz_convert(ET)
    assert r["acted"] == expected
    assert r["raw_last"] == pd.Timestamp("2026-09-09 06:22", tz=ET)


def test_the_trader_still_uses_the_trim_this_measures():
    """A shared function proves nothing if _fetch_bars stopped calling it.
    Asserted by running the real fetch over a stubbed IB and reading back what
    survives."""
    import asyncio

    class Stub:
        async def reqHistoricalDataAsync(self, contract, **kw):
            df = frame(last="2026-09-09 06:22", n=5).reset_index()
            return df.rename(columns={"index": "date"}).to_dict("records")

    tr = T.MCLPaperTrader.__new__(T.MCLPaperTrader)
    tr.ib = Stub()
    st = T.SymbolState(symbol="BNC")
    st.contract = object()
    out = asyncio.run(T.MCLPaperTrader._fetch_bars(tr, st))
    assert out.index[-1].tz_convert(ET) == pd.Timestamp(
        "2026-09-09 06:21", tz=ET), "the newest bar of the response is dropped"


def test_a_single_bar_response_is_not_trimmed_to_nothing():
    """An empty frame reaching a strategy is a crash, not a missed signal."""
    r = B.sample(at("06:22:30"), frame(last="2026-09-09 06:22", n=1))
    assert r["acted"] == r["raw_last"]


def test_an_empty_response_is_an_observation_not_a_sample():
    """IB signals pacing with an empty list rather than an error, so this must
    not be classified as anything about freshness."""
    assert B.sample(at(), None)["empty"] is True
    assert B.sample(at(), frame().iloc[0:0])["empty"] is True


# --- the verdict -------------------------------------------------------------

def rows(kinds, second=30):
    """Samples of the given kinds, at a chosen second of the minute."""
    lag = {"forming": 20, "closed": 80, "stale": 200}
    out = []
    for i, k in enumerate(kinds):
        now = at("06:30:00") + timedelta(minutes=i, seconds=second)
        out.append(B.sample(now, frame(
            last=str((now - timedelta(seconds=lag[k])).replace(
                second=0, tzinfo=None))[:16])))
    return out


def report(kinds, **kw):
    return "\n".join(B.render({"BNC": rows(kinds, **kw)}, 180, 15))


def test_a_majority_of_closed_says_the_trim_is_costing_a_minute():
    text = report(["closed"] * 8 + ["forming"])
    assert "discarding a bar that had" in text
    assert "one minute later than the rule it implements" in text


def test_a_majority_of_forming_says_the_trim_is_right():
    """And sends the reader somewhere else, rather than leaving them to
    conclude 'no bug found, therefore no problem' when Ben's two minutes are
    still unexplained."""
    text = report(["forming"] * 8 + ["closed"])
    assert "trim is correct" in text
    assert "somewhere else" in text


def test_a_split_result_concludes_nothing():
    """Five and five must not tip the report into a recommendation. This
    project has changed a rule on a 1.9% difference before."""
    text = report(["forming"] * 5 + ["closed"] * 5)
    assert "no clear majority" in text
    assert "discarding a bar" not in text


def test_the_verdict_ignores_the_samples_it_said_it_would_ignore():
    """Eight 'closed' readings, all taken in the first seconds of a minute
    where 'closed' is exactly what a correct feed looks like. The report must
    reach no verdict, and must say how many it set aside."""
    text = report(["closed"] * 8, second=1)
    assert "no clear majority" in text
    assert "excluded 8 sample(s)" in text
    assert "discarding a bar" not in text


def test_the_report_separates_the_expected_minute_from_the_disputed_one():
    """Without this the reader concludes the strategy is a minute late when
    one minute is simply what acting on a closed bar costs."""
    text = report(["forming"] * 4)
    assert "acts on a CLOSED bar" in text
    assert "SECOND" in text


def test_the_report_says_what_it_cannot_see():
    """The fill round trip is measured elsewhere (about 0.5s). A reader who
    thought this covered it would stop looking too early."""
    text = report(["forming"] * 3)
    assert "seconds_to_fill" in text


def test_the_report_names_the_request_it_made():
    """Two durations are in play since 2026-09-09 and the answer could differ
    between them; a report that does not say which it asked for cannot be
    compared with a later one."""
    assert T.HISTORY_DURATION in report(["forming"] * 3)


# --- safety ------------------------------------------------------------------

def test_it_refuses_a_live_port():
    """Read off the trader's own tables, not a copy of the numbers."""
    assert set(B.LIVE_PORTS) == set(T.LIVE_PORTS)
    for port in T.LIVE_PORTS:
        with pytest.raises(SystemExit) as e:
            B.main(["--symbols", "BNC", "--port", str(port)])
        assert "REFUSING TO RUN" in str(e.value)


def test_it_refuses_a_port_that_is_merely_unknown():
    with pytest.raises(SystemExit) as e:
        B.main(["--symbols", "BNC", "--port", "9999"])
    assert "not a known paper port" in str(e.value)


def test_it_does_not_share_a_client_id_with_anything_else_that_runs():
    """This is meant to run DURING a session. Two clients cannot share an id,
    and the loser is whichever connects second -- which would be the trader
    reconnecting after a drop."""
    from common import history_probe as H

    mine = B.build_parser().parse_args([]).client_id
    taken = {T.build_parser().parse_args([]).client_id,
             H.build_parser().parse_args([]).client_id}
    assert mine not in taken, (
        f"client id {mine} is already used by the trader or the history probe")


def test_the_default_request_budget_is_small():
    """IB paces at ~60 historical requests per 10 minutes ACROSS ALL
    CONTRACTS and signals the limit by returning empty lists rather than
    errors. A probe that quietly ate the budget would blind the trader it is
    running alongside, and the trader would not say so."""
    a = B.build_parser().parse_args([])
    per_symbol = a.seconds / a.interval
    assert a.limit * per_symbol <= 15, (
        "default run must stay well inside a quarter of IB's 10-minute budget")


# --- the tape-is-live guard, added 2026-09-10 after a run at 23:30 ET -------
#
# Ben ran the probe seven hours before the session. It failed on a refused
# socket, which was legible. Had IB Gateway been up it would have produced a
# full report whose verdict read "no clear majority -- re-run with more
# samples", and the next run would have been longer and equally empty.

@pytest.mark.parametrize("when,live", [
    ("2026-09-10 03:59:00", False),   # one minute before the tape opens
    ("2026-09-10 04:00:00", True),    # pre-market open, MCL's own start
    ("2026-09-10 06:21:00", True),    # the BNC signal this probe exists for
    ("2026-09-10 19:59:00", True),    # last minute of extended hours
    ("2026-09-10 20:00:00", False),   # the close is exclusive
    ("2026-09-10 23:30:00", False),   # the hour Ben actually ran it
    ("2026-09-12 06:21:00", False),   # Saturday, mid-session hour
    ("2026-09-13 06:21:00", False),   # Sunday, mid-session hour
])
def test_the_tape_window_admits_only_hours_that_print_bars(when, live):
    now = datetime.strptime(when, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
    assert B.tape_is_live(now) is live


def test_the_boundaries_are_open_closed_not_something_else():
    """A half-open interval either end would still pass the parametrised cases
    above if both boundaries moved together, so pin the asymmetry directly."""
    assert B.tape_is_live(datetime(2026, 9, 10, 4, 0, 0, tzinfo=ET))
    assert not B.tape_is_live(datetime(2026, 9, 10, 20, 0, 0, tzinfo=ET))


def test_a_stale_majority_is_reported_as_uninformative_not_inconclusive():
    """THE POINT OF THE WHOLE GUARD. A holiday clears tape_is_live() -- it is a
    weekday inside the window -- so render() is the only thing standing between
    a dead tape and a verdict that blames the sample size."""
    now = datetime(2026, 9, 10, 6, 21, 30, tzinfo=ET)
    rows = [{"now": now, "raw_last": now - timedelta(hours=9),
             "acted": now - timedelta(hours=9), "kind": "stale",
             "edge": False, "raw_lag_s": 32400.0, "acted_lag_s": 32400.0}
            for _ in range(10)]
    text = "\n".join(B.render({"BNC": rows}, 180, 15))
    assert "THE TAPE WAS NOT PRINTING" in text
    assert "This is not an inconclusive" in text
    assert "no clear majority" not in text, (
        "a dead tape must not read as an inconclusive measurement")


def test_a_forming_majority_still_reaches_its_real_verdict():
    """The guard must not swallow the answer it was added to protect. Same
    render(), a feed that DOES include the minute in progress."""
    now = datetime(2026, 9, 10, 6, 21, 30, tzinfo=ET)
    rows = [{"now": now, "raw_last": now - timedelta(seconds=30),
             "acted": now - timedelta(seconds=90), "kind": "forming",
             "edge": False, "raw_lag_s": 30.0, "acted_lag_s": 90.0}
            for _ in range(10)]
    text = "\n".join(B.render({"BNC": rows}, 180, 15))
    assert "trim is correct and the second minute is somewhere else" in text
    assert "THE TAPE WAS NOT PRINTING" not in text


def test_the_override_exists_and_is_off_by_default():
    a = B.build_parser().parse_args([])
    assert a.anyway is False
    assert B.build_parser().parse_args(["--anyway"]).anyway is True
