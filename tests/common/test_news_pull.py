#!/usr/bin/env python3
r"""tests/common/test_news_pull.py

Nothing here touches the network -- Fetcher takes its opener (the same
convention test_edgar_shares.py uses) and alpaca_symbol_history takes its
opener and sleep, so pagination and pacing are measured, not assumed.
"""
from __future__ import annotations

import csv
import json
import urllib.error
from pathlib import Path

import pytest

from common import edgar_shares as E
from common import news_pull as P


# --- doubles, same shape as test_edgar_shares.py's FakeNet ------------------

class FakeNet:
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


def fetcher(tmp_path, net, **kw):
    return E.Fetcher("x@example.com", cache=tmp_path / "cache", opener=net, **kw)


def _write_trades_csv(path: Path, rows: list[dict]) -> None:
    cols = ["book", "symbol", "date", "ordinal", "entry_et", "entry_px",
           "exit_et", "exit_px", "reason", "bars_held", "net"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({**{c: "" for c in cols}, **r})


# --- population, read from the study's own scored trades --------------------

def test_population_symbols_filters_to_mcl_mc5_and_earliest_date(tmp_path):
    p = tmp_path / "trades.csv"
    _write_trades_csv(p, [
        {"book": "MCL", "symbol": "AAA", "date": "2026-01-05"},
        {"book": "MCL", "symbol": "AAA", "date": "2026-01-02"},   # earlier
        {"book": "MC5", "symbol": "BBB", "date": "2026-02-01"},
        {"book": "MCL-c033", "symbol": "CCC", "date": "2026-03-01"},  # not scored
    ])
    pop = P.population_symbols(str(p))
    assert pop == {"AAA": "2026-01-02", "BBB": "2026-02-01"}


def test_population_symbols_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit, match="does not exist"):
        P.population_symbols(str(tmp_path / "nope.csv"))


def test_population_symbols_wrong_books_exits(tmp_path):
    p = tmp_path / "trades.csv"
    _write_trades_csv(p, [{"book": "MCL-c033", "symbol": "AAA", "date": "2026-01-01"}])
    with pytest.raises(SystemExit, match="no rows"):
        P.population_symbols(str(p))


# --- EDGAR filing extraction -------------------------------------------------

def _submissions(forms, items=None, accepted=None, filed=None):
    n = len(forms)
    return {"filings": {"recent": {
        "form": forms,
        "items": items or [""] * n,
        "acceptanceDateTime": accepted or ["2026-09-01T20:00:00.000Z"] * n,
        "filingDate": filed or ["2026-09-01"] * n}}}


def test_interesting_filing_rows_unfiltered():
    sub = _submissions(["424B3", "10-Q", "8-K"], items=["", "", "5.03"])
    rows = P.interesting_filing_rows(sub)
    assert [r["form"] for r in rows] == ["424B3", "10-Q", "8-K"]
    assert rows[2]["items"] == "5.03"


def test_interesting_filing_rows_empty_submission():
    assert P.interesting_filing_rows({}) == []
    assert P.interesting_filing_rows(None) == []


def test_oldest_recent_filing_date():
    sub = _submissions(["424B3", "8-K"], filed=["2026-08-01", "2026-06-15"])
    assert P.oldest_recent_filing_date(sub) == "2026-06-15"
    assert P.oldest_recent_filing_date({}) == ""


# --- EDGAR pull, via edgar_shares.Fetcher with a fake opener ----------------

def test_pull_edgar_writes_rows_and_flags_truncation(tmp_path):
    tmap = {"AAA": (1, "Alpha Inc"), "BBB": (2, "Beta Inc")}
    sub_a = _submissions(["424B3"], filed=["2025-01-10"])   # recent reaches back fine
    sub_b = _submissions(["8-K"], items=["5.03"], filed=["2026-02-01"])  # truncated
    net = FakeNet({
        P.SEC_SUBMISSIONS.format(cik=1): sub_a,
        P.SEC_SUBMISSIONS.format(cik=2): sub_b,
    })
    f = fetcher(tmp_path, net)
    pop = {"AAA": "2026-01-05", "BBB": "2026-01-05"}   # BBB's earliest predates its filings
    rows, status = P.pull_edgar(pop, f, tmap)
    assert len(rows) == 2
    assert status["AAA"] == "ok"
    assert "TRUNCATED" not in status["AAA"]
    assert status["BBB"].startswith("ok, but")


def test_pull_edgar_no_cik_is_reported_not_silently_dropped(tmp_path):
    net = FakeNet({})
    f = fetcher(tmp_path, net)
    rows, status = P.pull_edgar({"ZZZ": "2026-01-01"}, f, {})
    assert rows == []
    assert status == {"ZZZ": "no_cik"}


def test_pull_edgar_respects_limit(tmp_path):
    tmap = {"AAA": (1, "A"), "BBB": (2, "B")}
    net = FakeNet({
        P.SEC_SUBMISSIONS.format(cik=1): _submissions(["424B3"]),
        P.SEC_SUBMISSIONS.format(cik=2): _submissions(["424B3"]),
    })
    f = fetcher(tmp_path, net)
    pop = {"AAA": "2026-01-01", "BBB": "2026-01-01"}
    rows, status = P.pull_edgar(pop, f, tmap, limit=1)
    assert len(status) == 1


# --- Alpaca, HTTP-error path (same shape as the probe's own test) ----------

def test_alpaca_get_http_error():
    import io

    def opener(req, timeout):
        assert req.get_header("Apca-api-key-id") == "k"
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {},
                                     io.BytesIO(b'{"message":"forbidden"}'))
    st, body = P.alpaca_get({"symbols": "AAA", "page_token": None}, "k", "s", opener=opener)
    assert st == 403 and "forbidden" in body["message"]


def test_alpaca_get_200():
    class Ctx:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return json.dumps({"news": [{"headline": "x"}]}).encode()

    def opener(req, timeout):
        return Ctx()

    st, body = P.alpaca_get({"symbols": "AAA"}, "k", "s", opener=opener)
    assert st == 200
    assert body["news"][0]["headline"] == "x"


# --- Alpaca per-symbol pagination --------------------------------------------

def test_alpaca_symbol_history_pages_until_no_token():
    calls = []
    pages = [
        {"news": [{"headline": "h1", "created_at": "2026-01-01T00:00:00Z"}],
         "next_page_token": "tok2"},
        {"news": [{"headline": "h2", "created_at": "2026-01-02T00:00:00Z"}],
         "next_page_token": None},
    ]

    def opener(req, timeout):
        idx = len(calls)
        calls.append(req.full_url)

        class Ctx:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return json.dumps(pages[idx]).encode()
        return Ctx()

    slept = []
    st, rows = P.alpaca_symbol_history("AAA", "2026-01-01", "k", "s",
                                       opener=opener, sleep=slept.append)
    assert st == 200
    assert [r["headline"] for r in rows] == ["h1", "h2"]
    assert len(calls) == 2
    assert len(slept) == 1   # paced once, between the two pages, not after the last


def test_alpaca_symbol_history_stops_on_http_error():
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "rate", {}, None)
    st, rows = P.alpaca_symbol_history("AAA", "2026-01-01", "k", "s", opener=opener)
    assert st == 429
    assert rows == []


# --- pull_alpaca orchestration -----------------------------------------------

def test_pull_alpaca_reports_status_per_symbol():
    def opener(req, timeout):
        import io
        class Ctx:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return json.dumps({"news": [{"headline": "h", "created_at": "2026-01-01T00:00:00Z"}],
                                   "next_page_token": None}).encode()
        return Ctx()
    pop = {"AAA": "2026-01-05"}
    rows, status = P.pull_alpaca(pop, "k", "s", opener=opener, sleep=lambda s: None)
    assert status == {"AAA": "ok"}
    assert rows == [{"symbol": "AAA", "headline": "h", "created_at": "2026-01-01T00:00:00Z"}]


def test_buffered_start():
    assert P._buffered_start("2026-02-05") == "2026-01-01"   # 35 days back


# --- csv round trip, the shape common.news_events consumes ------------------

def test_filings_csv_round_trip(tmp_path):
    rows = [{"symbol": "AAA", "form": "8-K", "items": "1.01,5.03",
            "accepted": "2026-09-01T20:00:00.000Z", "filed": "2026-09-01"}]
    out = tmp_path / "filings.csv"
    P.write_csv(str(out), P.FILING_COLS, rows)
    got = P.load_filings_csv(str(out))
    assert got == {"AAA": [{"form": "8-K", "items": "1.01,5.03",
                            "accepted": "2026-09-01T20:00:00.000Z"}]}


def test_headlines_csv_round_trip(tmp_path):
    rows = [{"symbol": "AAA", "headline": "X Announces Reverse Split",
            "created_at": "2026-09-01T13:00:00Z"}]
    out = tmp_path / "headlines.csv"
    P.write_csv(str(out), P.HEADLINE_COLS, rows)
    got = P.load_headlines_csv(str(out))
    assert got == {"AAA": [{"headline": "X Announces Reverse Split",
                            "created_at": "2026-09-01T13:00:00Z"}]}


def test_load_csv_missing_file_returns_empty(tmp_path):
    assert P.load_filings_csv(str(tmp_path / "nope.csv")) == {}
    assert P.load_headlines_csv(str(tmp_path / "nope.csv")) == {}


# --- cost sections print without raising, and name the population size -----

def test_edgar_cost_section_mentions_matched_count():
    pop = {"AAA": "2026-01-01", "BBB": "2026-01-01"}
    tmap = {"AAA": (1, "A")}
    L = P.edgar_cost_section(pop, tmap)
    text = "\n".join(L)
    assert "1" in text and "requests" in text


def test_alpaca_cost_section_mentions_population():
    pop = {"AAA": "2026-01-01"}
    text = "\n".join(P.alpaca_cost_section(pop))
    assert "1" in text
