"""tests/common/test_news_swing_pull.py

W07-0011 -- the swing-picks puller. Reuses `news_pull.pull_edgar` and
`news_pull.alpaca_symbol_history` unchanged (asserted here, not just
claimed); nothing touches the network -- same opener-injection convention
as `test_news_pull.py`.
"""
from __future__ import annotations

import csv
import json
import urllib.error
from pathlib import Path

import pytest

from common import edgar_shares as E
from common import news_pull as P
from common import news_swing_pull as SP
from common import news_swing_tag as T


def _write_picks_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(T.PICK_FIELDS))
        w.writeheader()
        w.writerows(rows)


def _pick(symbol="AAA", drop_start_date="2026-05-01"):
    return {"symbol": symbol, "entry_date": "2026-05-05", "entry_et": "11:30",
           "drop_start_date": drop_start_date, "k": 5, "bucket": "midday",
           "gross": 100.0, "cost": 10.0, "net": 90.0, "net_2x_stress": 80.0,
           "mkt_rel_net": 50.0}


# --- population, from picks not the full universe ---------------------------

def test_swing_population_missing_picks_exits(tmp_path):
    with pytest.raises(SystemExit, match="W07-0010"):
        SP.swing_population(str(tmp_path / "nope.csv"))


def test_swing_population_from_picks(tmp_path):
    p = tmp_path / "picks.csv"
    _write_picks_csv(p, [_pick("AAA", "2026-05-10"), _pick("AAA", "2026-05-01"),
                        _pick("BBB", "2026-06-01")])
    pop = SP.swing_population(str(p))
    assert pop == {"AAA": "2026-05-01", "BBB": "2026-06-01"}


def test_swing_population_empty_picks_file_exits(tmp_path):
    p = tmp_path / "picks.csv"
    _write_picks_csv(p, [])
    with pytest.raises(SystemExit, match="no pick rows"):
        SP.swing_population(str(p))


# --- EDGAR: this module's own wrapper calls news_pull.pull_edgar exactly ----

class FakeNet:
    def __init__(self, pages=None):
        self.pages = pages or {}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise urllib.error.HTTPError(url, 404, "not found", None, None)
        return json.dumps(self.pages[url]).encode()


def test_pull_edgar_for_swing_reuses_news_pull_pull_edgar(tmp_path, monkeypatch):
    called_with = {}
    real = P.pull_edgar

    def spy(pop, f, tmap, limit=None):
        called_with["pop"] = pop
        called_with["limit"] = limit
        return real(pop, f, tmap, limit=limit)

    monkeypatch.setattr(SP.P, "pull_edgar", spy)
    tmap = {"AAA": (1, "Alpha Inc")}
    net = FakeNet({P.SEC_SUBMISSIONS.format(cik=1): {
        "filings": {"recent": {"form": ["8-K"], "items": ["1.01"],
                               "acceptanceDateTime": ["2026-05-03T20:00:00.000Z"],
                               "filingDate": ["2026-04-01"]}}}})
    f = E.Fetcher("x@example.com", cache=tmp_path / "cache", opener=net)
    pop = {"AAA": "2026-05-01"}
    rows, status = SP.pull_edgar_for_swing(pop, f, tmap)
    assert called_with["pop"] is pop
    assert rows[0]["form"] == "8-K"
    assert status["AAA"] == "ok"


# --- Alpaca: symbol_count kept, unlike news_pull.pull_alpaca ----------------

def _alpaca_opener(pages_by_symbol):
    def opener(req, timeout):
        # symbols=<SYM> is in the query string
        import urllib.parse as up
        q = dict(up.parse_qsl(up.urlsplit(req.full_url).query))
        sym = q["symbols"]

        class Ctx:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return json.dumps(pages_by_symbol[sym]).encode()
        return Ctx()
    return opener


def test_pull_alpaca_with_symbol_count_keeps_symbols_length():
    pages = {"AAA": {"news": [
        {"headline": "AAA and 6 others move", "created_at": "2026-05-02T13:00:00Z",
        "symbols": ["AAA", "B", "C", "D", "E", "F", "G"]},
        {"headline": "AAA alone", "created_at": "2026-05-03T13:00:00Z",
        "symbols": ["AAA"]}], "next_page_token": None}}
    opener = _alpaca_opener(pages)
    rows, status = SP.pull_alpaca_with_symbol_count(
        {"AAA": "2026-05-01"}, "k", "s", opener=opener, sleep=lambda s: None)
    assert status == {"AAA": "ok"}
    counts = {r["headline"]: r["symbol_count"] for r in rows}
    assert counts["AAA and 6 others move"] == 7
    assert counts["AAA alone"] == 1


def test_pull_alpaca_with_symbol_count_missing_symbols_field_defaults_to_one():
    pages = {"AAA": {"news": [{"headline": "x", "created_at": "2026-05-02T13:00:00Z"}],
                     "next_page_token": None}}
    opener = _alpaca_opener(pages)
    rows, _status = SP.pull_alpaca_with_symbol_count(
        {"AAA": "2026-05-01"}, "k", "s", opener=opener, sleep=lambda s: None)
    assert rows[0]["symbol_count"] == 1


def test_pull_alpaca_reuses_alpaca_symbol_history(monkeypatch):
    calls = []
    real = P.alpaca_symbol_history

    def spy(symbol, start, key, secret, **kw):
        calls.append((symbol, start))
        return real(symbol, start, key, secret, **kw)

    monkeypatch.setattr(SP.P, "alpaca_symbol_history", spy)
    pages = {"AAA": {"news": [], "next_page_token": None}}
    opener = _alpaca_opener(pages)
    SP.pull_alpaca_with_symbol_count({"AAA": "2026-05-01"}, "k", "s",
                                     opener=opener, sleep=lambda s: None)
    assert calls == [("AAA", "2026-03-27")]   # 35-day buffer, same as news_pull


# --- csv round trip -----------------------------------------------------------

def test_load_swing_headlines_csv_round_trip(tmp_path):
    p = tmp_path / "headlines.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(SP.SWING_HEADLINE_COLS))
        w.writeheader()
        w.writerow({"symbol": "AAA", "headline": "h", "created_at": "2026-05-02T13:00:00Z",
                   "symbol_count": "3"})
    got = SP.load_swing_headlines_csv(str(p))
    assert got == {"AAA": [{"headline": "h", "created_at": "2026-05-02T13:00:00Z",
                            "symbol_count": "3"}]}


def test_load_swing_headlines_csv_missing_file_returns_empty(tmp_path):
    assert SP.load_swing_headlines_csv(str(tmp_path / "nope.csv")) == {}
