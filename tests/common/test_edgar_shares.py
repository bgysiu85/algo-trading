#!/usr/bin/env python3
r"""SEC EDGAR shares outstanding, and the two ways it can lie.

The first is the leak: joining on `end` instead of `filed` hands a July session
a figure that was not public until August. That is the same defect the whole
point-in-time universe exists to prevent, arriving through a new door.

The second is the silent gap: a CURRENT ticker map cannot resolve a symbol that
has since been delisted, and a symbol that resolves to nothing looks, in every
join downstream, exactly like a symbol that failed a filter.

Nothing here touches the network. `Fetcher` takes its opener, its clock and its
sleep, so the pacing and the retry behaviour are measured rather than asserted
in a comment.
"""
from __future__ import annotations

import csv
import json
import urllib.error
from datetime import date
from pathlib import Path

import pytest

from common import edgar_shares as E


# --- doubles ----------------------------------------------------------------

class FakeNet:
    """A URL -> payload map, counting calls and able to fail on demand."""

    def __init__(self, pages=None, fail=None):
        self.pages = pages or {}
        self.fail = fail or {}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url in self.fail:
            e = self.fail[url]
            if isinstance(e, int):
                raise urllib.error.HTTPError(url, e, "no", None, None)
            raise e
        if url not in self.pages:
            raise urllib.error.HTTPError(url, 404, "not found", None, None)
        return json.dumps(self.pages[url]).encode()


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def fetcher(tmp_path, net, clock=None, **kw):
    c = clock or Clock()
    return E.Fetcher("x@example.com", cache=tmp_path / "cache", opener=net,
                     sleep=c.sleep, clock=c.now, **kw)


def concept(rows, taxonomy="dei", tag="EntityCommonStockSharesOutstanding"):
    return {"cik": 1, "taxonomy": taxonomy, "tag": tag,
            "units": {"shares": rows}}


def fact(end, filed, val, form="10-Q"):
    return {"end": end, "filed": filed, "val": val, "form": form,
            "accn": f"a-{filed}"}


# --- the contact SEC requires -----------------------------------------------

def test_a_missing_contact_stops_the_run(monkeypatch):
    """Not defaulted, and not guessed from anything in the repo."""
    monkeypatch.delenv("SEC_CONTACT", raising=False)
    with pytest.raises(SystemExit, match="SEC_CONTACT"):
        E.contact()


def test_a_contact_that_is_not_an_address_is_refused(monkeypatch):
    monkeypatch.setenv("SEC_CONTACT", "Ben")
    with pytest.raises(SystemExit):
        E.contact()


def test_the_contact_reaches_the_user_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("SEC_CONTACT", "a@b.com")
    assert "a@b.com" in E.user_agent(E.contact())


# --- THE ONE THAT MATTERS: point-in-time ------------------------------------

def test_a_fact_filed_after_the_session_is_invisible():
    """THE LEAK THIS MODULE EXISTS TO PREVENT.

    end=2026-06-30 filed=2026-08-14 was not knowable on 2026-07-01. Joining on
    `end` would hand a July backtest a number that did not exist for six weeks.
    """
    facts = E.concept_facts(concept([fact("2026-06-30", "2026-08-14", 50e6)]))
    assert E.shares_known_at(facts, "2026-07-01") is None
    assert E.shares_known_at(facts, "2026-08-14")["val"] == 50e6


def test_the_latest_filing_wins_even_when_its_period_is_older():
    """`end` is not consulted when choosing. An amendment restating an EARLIER
    period is a later `filed`, and from its filing date it is what was public."""
    facts = E.concept_facts(concept([
        fact("2026-06-30", "2026-08-14", 50e6),
        fact("2026-03-31", "2026-09-02", 41e6, form="10-Q/A")]))
    got = E.shares_known_at(facts, "2026-09-03")
    assert got["val"] == 41e6 and got["form"] == "10-Q/A"


def test_before_any_filing_the_answer_is_none_not_the_oldest_fact():
    """A recent IPO genuinely had no public share count. Substituting the first
    one ever filed is the leak wearing a different hat."""
    facts = E.concept_facts(concept([fact("2026-06-30", "2026-08-14", 50e6)]))
    assert E.shares_known_at(facts, "2024-01-02") is None


def test_a_fact_with_no_filing_date_is_dropped_not_dated_to_its_period():
    facts = E.concept_facts(concept([
        {"end": "2026-06-30", "filed": None, "val": 1.0},
        fact("2026-06-30", "2026-08-14", 50e6)]))
    assert len(facts) == 1 and facts[0]["filed"] == "2026-08-14"


def test_every_unit_key_is_read_not_only_shares():
    """A filer using a different unit label would otherwise contribute zero
    facts and be indistinguishable from a filer with none."""
    body = {"cik": 1, "taxonomy": "dei", "tag": "T",
            "units": {"pure": [fact("2026-06-30", "2026-07-01", 3.0)]}}
    assert len(E.concept_facts(body)) == 1


# --- the ticker map ---------------------------------------------------------

def test_the_map_is_read_from_secs_row_keyed_object(tmp_path):
    net = FakeNet({E.SEC_TICKERS: {"0": {"cik_str": 320193, "ticker": "AAPL",
                                         "title": "Apple Inc."}}})
    got = E.ticker_map(fetcher(tmp_path, net))
    assert got["AAPL"] == (320193, "Apple Inc.")


def test_a_class_share_matches_across_spellings(tmp_path):
    r"""The tape writes BRK.B or BRK/B; SEC writes BRK-B. Matched raw, EVERY
    class share is a miss -- and a systematic miss on one kind of symbol reads
    in a coverage figure exactly like a scatter of odd names."""
    net = FakeNet({E.SEC_TICKERS: {"0": {"cik_str": 1, "ticker": "BRK-B"}}})
    tmap = E.ticker_map(fetcher(tmp_path, net))
    cov = E.coverage({"BRK.B": ["2026-01-02"], "BRK/B": ["2026-01-05"]}, tmap)
    assert cov["symbols_hit"] == 2 and not cov["miss"]


def test_a_map_that_parses_to_nothing_is_refused(tmp_path):
    """The shape changing is a thing that happens, and an empty map would
    otherwise be reported as 0% coverage -- a finding rather than a fault."""
    net = FakeNet({E.SEC_TICKERS: {"0": {"nope": 1}}})
    with pytest.raises(SystemExit, match="shape changed"):
        E.ticker_map(fetcher(tmp_path, net))


# --- coverage ---------------------------------------------------------------

def test_coverage_counts_symbols_and_symbol_days_separately():
    """43% of this universe appears on one session. One hit rate would hide
    whether the misses are one-day names or frequent flyers."""
    days = {"AAA": ["d1", "d2", "d3"], "BBB": ["d1"]}
    cov = E.coverage(days, {"AAA": (1, "A")})
    assert (cov["symbols_hit"], cov["symbols"]) == (1, 2)
    assert (cov["days_hit"], cov["days"]) == (3, 4)


def test_every_miss_is_printed():
    """A truncated miss list is how a systematic gap reads as a scatter."""
    days = {f"M{i:03d}": ["d1"] for i in range(60)}
    text = "\n".join(E.coverage_section(E.coverage(days, {})))
    for i in range(60):
        assert f"M{i:03d}" in text


def test_the_report_says_this_is_not_float():
    """The sentence is load-bearing: shares outstanding in a column called
    float is a wrong number with a right name."""
    text = E.coverage_report(E.coverage({"A": ["d1"]}, {"A": (1, "A")}), "p")
    assert "SHARES OUTSTANDING IS NOT FLOAT" in text
    assert "upper bound" in text


def test_the_report_says_the_map_is_current_day():
    text = E.coverage_report(E.coverage({"A": ["d1"]}, {}), "p")
    assert "CURRENT-DAY" in text and "REUSED" in text


# --- fetching ---------------------------------------------------------------

def test_a_cached_response_is_not_refetched(tmp_path):
    net = FakeNet({"u": {"a": 1}})
    f = fetcher(tmp_path, net)
    assert f.get("u", "k")[1] == "fetched"
    assert f.get("u", "k")[1] == "cached"
    assert len(net.calls) == 1


def test_a_404_is_recorded_so_it_is_asked_once(tmp_path):
    """Absence has to be a stored fact. Without it, every re-run of a
    2,123-symbol pull spends thousands of requests rediscovering the same
    nothing -- and 'not asked yet' and 'asked, nothing there' stay confused."""
    net = FakeNet({})
    f = fetcher(tmp_path, net)
    assert f.get("u", "k") == (None, "absent")
    assert f.get("u", "k") == (None, "absent")
    assert len(net.calls) == 1


def test_refresh_ignores_the_cache(tmp_path):
    net = FakeNet({"u": {"a": 1}})
    fetcher(tmp_path, net).get("u", "k")
    fetcher(tmp_path, net, refresh=True).get("u", "k")
    assert len(net.calls) == 2


def test_requests_are_paced_below_secs_ceiling(tmp_path):
    """SEC publishes 10/s and enforces it with a block. A block mid-pull leaves
    a half-populated cache that the next run cannot tell from a company with no
    filings."""
    clock = Clock()
    net = FakeNet({f"u{i}": {} for i in range(5)})
    f = fetcher(tmp_path, net, clock=clock)
    for i in range(5):
        f.get(f"u{i}", f"k{i}")
    assert clock.slept, "no pacing happened at all"
    assert all(s <= E.MIN_INTERVAL + 1e-9 for s in clock.slept)
    assert E.MIN_INTERVAL >= 0.1, "0.1s is exactly SEC's ceiling, not under it"


def test_a_rate_limit_is_retried_then_reported_not_raised(tmp_path):
    clock = Clock()
    net = FakeNet({}, fail={"u": 429})
    f = fetcher(tmp_path, net, clock=clock)
    body, why = f.get("u", "k")
    assert body is None and "429" in why
    assert len(net.calls) == E.MAX_TRIES
    assert clock.slept, "it retried without backing off"


def test_a_failure_is_not_cached_as_absence(tmp_path):
    """A 503 cached as 'this company has no filings' would be permanent, and
    the re-run that would have fixed it would never ask again."""
    net = FakeNet({}, fail={"u": 503})
    f = fetcher(tmp_path, net)
    f.get("u", "k")
    assert not f.path_for("k").exists()
    # And it is retried rather than given up on at the first refusal: SEC
    # returns 503 under load, and one transient 503 recorded as "this company
    # has no filings" is permanent.
    assert len(net.calls) == E.MAX_TRIES


# --- the fallback tag -------------------------------------------------------

def test_the_balance_sheet_tag_answers_when_the_cover_page_is_absent(tmp_path):
    cik = 7
    us = E.SEC_CONCEPT.format(cik=cik, taxonomy="us-gaap",
                              tag="CommonStockSharesOutstanding")
    net = FakeNet({us: concept([fact("2026-06-30", "2026-08-14", 12e6)],
                               "us-gaap", "CommonStockSharesOutstanding")})
    rows, src = E.pull_symbol(fetcher(tmp_path, net), "AAA", cik)
    assert src == "us-gaap:CommonStockSharesOutstanding"
    assert rows[0]["val"] == 12e6


def test_which_tag_answered_is_carried_per_row(tmp_path):
    """The cover-page tag is dated near the filing and the balance-sheet tag to
    the period end. Averaged as one population they are two things under one
    label -- so the column travels with the row."""
    facts = E.concept_facts(concept([fact("2026-06-30", "2026-08-14", 1.0)],
                                    "us-gaap", "CommonStockSharesOutstanding"))
    assert facts[0]["tag"] == "CommonStockSharesOutstanding"
    assert facts[0]["taxonomy"] == "us-gaap"


# --- the join ---------------------------------------------------------------

def universe_cov():
    days = {"AAA": ["2026-08-10", "2026-08-20"], "ZZZ": ["2026-08-10"]}
    cov = E.coverage(days, {"AAA": (1, "A Inc")})
    return days, cov


def test_a_symbol_day_with_nothing_knowable_is_a_row_not_a_gap():
    """Omitting it makes the output's own row count the denominator, and a
    denominator that shrinks to fit turns 50% into 100%."""
    days, cov = universe_cov()
    facts = {"AAA": E.concept_facts(
        concept([fact("2026-06-30", "2026-08-14", 50e6)]))}
    rows = E.asof_rows(days, facts, cov)
    assert len(rows) == 3
    by = {(r["symbol"], r["date"]): r for r in rows}
    assert by[("AAA", "2026-08-10")]["status"] == "before_first_filing"
    assert by[("AAA", "2026-08-20")]["shares"] == 50e6
    assert by[("ZZZ", "2026-08-10")]["status"] == "no_cik"


def test_a_stale_figure_is_kept_and_counted_apart():
    days = {"AAA": ["2026-08-20"]}
    cov = E.coverage(days, {"AAA": (1, "A")})
    old = (date.fromisoformat("2026-08-20")
           - __import__("datetime").timedelta(days=E.STALE_DAYS + 5)).isoformat()
    facts = {"AAA": E.concept_facts(concept([fact(old, old, 9e6)]))}
    r = E.asof_rows(days, facts, cov)[0]
    assert r["status"] == "stale" and r["shares"] == 9e6


def test_the_lag_is_the_session_minus_the_filing():
    days = {"AAA": ["2026-08-20"]}
    cov = E.coverage(days, {"AAA": (1, "A")})
    facts = {"AAA": E.concept_facts(concept([fact("2026-06-30", "2026-08-14",
                                                  50e6)]))}
    assert E.asof_rows(days, facts, cov)[0]["lag_days"] == 6


def test_the_asof_section_reports_every_status():
    days, cov = universe_cov()
    facts = {"AAA": E.concept_facts(
        concept([fact("2026-06-30", "2026-08-14", 50e6)]))}
    text = "\n".join(E.asof_section(E.asof_rows(days, facts, cov)))
    for s in ("known", "before_first_filing", "no_cik"):
        assert s in text
    assert "SHARES OUTSTANDING IS NOT FLOAT" in text


# --- the pull's accounting --------------------------------------------------

def test_the_pull_report_flags_symbols_that_left_unaccounted(tmp_path):
    """A pull that loses symbols between 'attempted' and its three outcomes is
    a partial table reporting success."""
    cov = E.coverage({"A": ["d"], "B": ["d"]}, {"A": (1, ""), "B": (2, "")})
    f = fetcher(tmp_path, FakeNet({}))
    text = E.pull_report(cov, {"A": []}, {"A": "absent"}, f)
    assert "DO NOT ADD UP" in text


def test_the_pull_report_lists_what_failed(tmp_path):
    cov = E.coverage({"A": ["d"]}, {"A": (1, "")})
    f = fetcher(tmp_path, FakeNet({}))
    text = E.pull_report(cov, {"A": []}, {"A": "HTTP 503"}, f)
    assert "HTTP 503" in text and "FAILED" in text
    assert "Re-run to retry" in text


# --- round trip -------------------------------------------------------------

def test_the_facts_csv_round_trips(tmp_path):
    rows = [dict(r, symbol="AAA", cik=1) for r in E.concept_facts(
        concept([fact("2026-06-30", "2026-08-14", 50e6)]))]
    p = tmp_path / "f.csv"
    E.write_csv(p, E.FACT_COLS, rows)
    back = E.load_facts_csv(p)
    assert back["AAA"][0]["val"] == 50e6
    assert back["AAA"][0]["filed"] == "2026-08-14"


def test_asof_without_a_pull_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="run `--pull` first"):
        E.load_facts_csv(tmp_path / "nope.csv")


def test_a_missing_universe_is_refused_with_what_to_run(tmp_path):
    with pytest.raises(SystemExit, match="screen_sim"):
        E.load_universe(tmp_path / "nope.json")


def test_the_universe_is_the_same_file_pit_h0_scores():
    """A coverage figure and a trade count that do not share a denominator are
    two numbers that look comparable and are not."""
    from common import pit_h0
    src = Path(pit_h0.__file__).read_text(encoding="utf-8")
    assert E.PAIRS in src, (
        "pit_h0 no longer defaults to the universe this module reads")


def test_the_universe_dedupes_a_repeated_symbol_day(tmp_path):
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps([{"symbol": "AAA", "date": "d1"},
                             {"symbol": "AAA", "date": "d1"},
                             {"symbol": "aaa", "date": "d2"}]), encoding="utf-8")
    assert E.load_universe(p) == {"AAA": ["d1", "d2"]}


# --- END TO END, because a suite that never runs the pipeline proves nothing -

def _pairs_file(tmp_path):
    p = tmp_path / "var" / "state" / "pairs.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([
        {"symbol": "AAA", "date": "2026-08-10"},
        {"symbol": "AAA", "date": "2026-08-20"},
        {"symbol": "ZZZ", "date": "2026-08-10"}]), encoding="utf-8")
    return p


def _wire(monkeypatch, net):
    monkeypatch.setattr(E.Fetcher, "_urlopen", lambda self, url: net(url))
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    monkeypatch.setenv("SEC_CONTACT", "a@b.com")


def _net():
    cik = 11
    return FakeNet({
        E.SEC_TICKERS: {"0": {"cik_str": cik, "ticker": "AAA", "title": "A"}},
        E.SEC_CONCEPT.format(cik=cik, taxonomy="dei",
                             tag="EntityCommonStockSharesOutstanding"):
            concept([fact("2026-06-30", "2026-08-14", 50e6)]),
    })


def test_end_to_end_coverage_pull_and_asof(tmp_path, monkeypatch, capsys):
    """THE TEST THE LAST TWO MODULES DID NOT HAVE.

    Nineteen green tests once covered `entry_split` without one of them running
    `run_day`, and the pipeline raised KeyError the first time it was asked to.
    This drives main() through all three steps.
    """
    _wire(monkeypatch, _net())
    pairs = _pairs_file(tmp_path)
    args = ["--pairs", str(pairs), "--cache", str(tmp_path / "cache"),
            "--facts", str(tmp_path / "facts.csv"),
            "--asof-out", str(tmp_path / "asof.csv")]

    assert E.main(args + ["--coverage", "--out", str(tmp_path / "cov.txt")]) == 0
    cov = (tmp_path / "cov.txt").read_text(encoding="utf-8")
    assert "ZZZ" in cov and "1 of 2" in cov.replace(",", "")

    assert E.main(args + ["--pull", "--out", str(tmp_path / "pull.txt")]) == 0
    facts = (tmp_path / "facts.csv").read_text(encoding="utf-8")
    assert "AAA" in facts and "2026-08-14" in facts

    assert E.main(args + ["--asof", "--out", str(tmp_path / "asof.txt")]) == 0
    rows = list(csv.DictReader((tmp_path / "asof.csv").open(encoding="utf-8")))
    assert len(rows) == 3, "a symbol-day was dropped rather than written empty"
    got = {(r["symbol"], r["date"]): r["status"] for r in rows}
    assert got[("AAA", "2026-08-10")] == "before_first_filing"
    assert got[("AAA", "2026-08-20")] == "known"
    assert got[("ZZZ", "2026-08-10")] == "no_cik"


def test_a_second_run_costs_no_requests(tmp_path, monkeypatch):
    """The cache is what makes a 2,123-symbol pull resumable, and resumability
    is the difference between a network error costing a minute and a morning."""
    net = _net()
    _wire(monkeypatch, net)
    pairs = _pairs_file(tmp_path)
    args = ["--pairs", str(pairs), "--cache", str(tmp_path / "cache"),
            "--facts", str(tmp_path / "f.csv"), "--pull",
            "--out", str(tmp_path / "o.txt")]
    E.main(args)
    first = len(net.calls)
    E.main(args)
    assert len(net.calls) == first, "the second run went back to the network"


def test_the_coverage_report_costs_the_pull_before_it_runs():
    """A tool that spends something states the number first. Here it is time
    and SEC's patience rather than money, and forty minutes is a different
    decision from four."""
    days = {f"S{i:04d}": ["d1"] for i in range(500)}
    cov = E.coverage(days, {f"S{i:04d}": (i, "") for i in range(500)})
    text = E.coverage_report(cov, "p")
    assert "WHAT THE PULL WOULD COST" in text
    assert "500" in text and "min" in text
