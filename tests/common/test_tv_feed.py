"""The screener feed: ranking, tiering, and the atomic watchlist write.

No network. The HTTP call is deliberately one small function (fetch) so that
everything with a decision in it -- what order symbols end up in, what gets
trimmed, what the trader actually reads -- is testable offline. The parts that
matter here are the ones that could silently cost money:

  * a symbol that drops out of the screen must NOT vanish from the file, since
    that is how a held position gets orphaned mid-session;
  * the file must never be readable in a half-written state, because the
    trader reads it on its own schedule;
  * the file must not grow without bound, because every symbol costs an IB
    qualification (paced, and IB signals throttling by returning EMPTY lists)
    and a streaming data line.
"""
from __future__ import annotations

import pytest

from common import tv_feed as F
from common.tv_screener import FILTERS


def row(ticker, px, chg=25.0):
    return {"ticker": ticker, "symbol": f"NASDAQ:{ticker}",
            "premarket_close": px, "premarket_change": chg}


# --- the wire payload is DERIVED, not restated ------------------------------

def test_payload_is_built_from_the_screener_definition():
    """If someone edits the screen in tv_screener.py, the live feed must
    follow. A hand-copied filter list here would be the classic two-copies
    bug -- the same shape as the price band that was enforced in the backtest
    and not in the live trader."""
    sent = F.tv_payload()["filter"]
    assert sent == [dict(f) for f in FILTERS]
    # The screen as of 2026-09-08: exactly two clauses, nothing else.
    assert {c["left"] for c in sent} == {"premarket_change", "premarket_close",
                                         "premarket_volume"}


def test_parse_maps_positional_columns_to_names():
    """TradingView returns values positionally against the columns asked for.
    Getting this wrong misreads every field without erroring."""
    body = {"data": [{"s": "NASDAQ:AOUT",
                      "d": [None] * len(F.COLUMNS)}]}
    got = F.parse(body)
    assert got[0]["ticker"] == "AOUT"
    assert got[0]["symbol"] == "NASDAQ:AOUT"
    assert set(F.COLUMNS) <= set(got[0])


# --- tiering ---------------------------------------------------------------

def test_in_band_matches_the_strategy_band():
    assert F.in_band(row("A", F.PRICE_MIN))
    assert F.in_band(row("B", F.PRICE_MAX))
    assert not F.in_band(row("C", F.PRICE_MIN - 0.01))
    assert not F.in_band(row("D", F.PRICE_MAX + 0.01))
    assert not F.in_band({"premarket_close": None})


def test_out_of_band_names_rank_below_tradeable_ones():
    """The screen has no upper price bound, so it surfaces names the trader
    will refuse at entry. They stay in the file but must never displace a
    symbol MCL can actually trade -- order decides who gets the position when
    only two may be open."""
    r = F.Ranking()
    out = r.update([row("EXPENSIVE", 60.0), row("GOOD", 5.0)])
    assert out.index("GOOD") < out.index("EXPENSIVE")


# --- the rule Ben asked for: deprioritise, never remove ---------------------

def test_a_symbol_that_drops_out_is_kept_but_demoted():
    r = F.Ranking()
    r.update([row("AAA", 5.0), row("BBB", 6.0)], now=100.0)
    out = r.update([row("BBB", 6.0)], now=110.0)
    assert "AAA" in out, "a symbol that left the screen was dropped"
    assert out.index("BBB") < out.index("AAA")


def test_a_symbol_that_returns_is_promoted_again():
    """Pre-market screens flicker -- a name can fail rel-vol for one poll and
    pass the next. Coming back must restore its priority, or a brief dropout
    would permanently bury a live runner."""
    r = F.Ranking()
    r.update([row("AAA", 5.0)], now=100.0)
    r.update([row("BBB", 5.0)], now=110.0)
    out = r.update([row("AAA", 5.0)], now=120.0)
    assert out[0] == "AAA"


def test_colder_symbols_order_by_how_recently_they_screened():
    r = F.Ranking()
    r.update([row("OLD", 5.0)], now=100.0)
    r.update([row("MID", 5.0)], now=200.0)
    r.update([row("NEW", 5.0)], now=300.0)
    out = r.update([], now=400.0)
    assert out == ["NEW", "MID", "OLD"]


def test_the_file_is_capped_and_trims_from_the_cold_end():
    r = F.Ranking(max_symbols=3)
    for i in range(6):
        r.update([row(f"S{i}", 5.0)], now=100.0 + i)
    out = r.update([row("HOTONE", 5.0)], now=200.0)
    assert len(out) == 3
    assert out[0] == "HOTONE"
    assert "S0" not in out, "the cap trimmed a recent symbol instead of an old one"


def test_a_held_name_still_present_after_many_polls_without_it():
    """The orphan case, stated directly: 200 polls in which the symbol never
    screens must not evict it while it is still inside the cap."""
    r = F.Ranking(max_symbols=10)
    r.update([row("HELD", 5.0)], now=0.0)
    for i in range(200):
        r.update([row("OTHER", 5.0)], now=float(i + 1))
    assert "HELD" in r.update([row("OTHER", 5.0)], now=999.0)


# --- the write -------------------------------------------------------------

def test_write_is_atomic_and_leaves_no_temp_file(tmp_path):
    p = tmp_path / "watchlist.txt"
    F.write_watchlist(p, ["AAA", "BBB"], header="test")
    assert not p.with_suffix(".txt.tmp").exists()
    lines = [ln for ln in p.read_text().splitlines() if not ln.startswith("#")]
    assert lines == ["AAA", "BBB"]


def test_write_reports_whether_the_symbols_actually_changed(tmp_path):
    """So a 10-second loop does not log an identical line 2,000 times a
    session. The header carries a timestamp and must NOT count as a change."""
    p = tmp_path / "watchlist.txt"
    assert F.write_watchlist(p, ["AAA"], header="first") is True
    assert F.write_watchlist(p, ["AAA"], header="second, later") is False
    assert F.write_watchlist(p, ["AAA", "BBB"], header="third") is True


def test_an_empty_screen_writes_an_empty_file_not_a_broken_one(tmp_path):
    p = tmp_path / "watchlist.txt"
    F.write_watchlist(p, [], header="nothing screening")
    body = [ln for ln in p.read_text().splitlines() if not ln.startswith("#")]
    assert body == []


# --- the session window ----------------------------------------------------

@pytest.mark.parametrize("hhmm,expected", [
    ((3, 59), False), ((4, 0), True), ((7, 30), True),
    ((9, 29), True), ((9, 30), False), ((16, 0), False),
])
def test_session_window_matches_MCL(hhmm, expected):
    from datetime import datetime
    now = datetime(2026, 9, 2, *hhmm, tzinfo=F.ET)
    assert F.in_session(now) is expected


def test_the_feed_writes_the_file_the_trader_reads():
    """THREE PROCESSES, ONE FILE, AND THEY MUST AGREE ON WHICH.

    tv_feed wrote watchlist.txt in the repo root; trader.py and scanner.py both
    read var/watchlist.txt. Neither side errors -- the feed reports the symbols
    it wrote, the trader reports an empty watchlist, and both are telling the
    truth about different files. A pre-market session would run watching
    nothing, which looks exactly like a quiet morning.

    The two argparse defaults are read out of the SOURCE rather than retyped
    here, because retyping them would move the drift into the test.
    """
    import inspect
    import re
    from pathlib import Path

    import brokers.ibkr.scanner as SC
    import brokers.ibkr.trader as TR
    from common import tv_feed as TV

    paths = {"tv_feed": Path(TV.WATCHLIST).resolve()}
    for name, mod in (("trader", TR), ("scanner", SC)):
        m = re.search(r'"--watchlist",\s*default="([^"]+)"', inspect.getsource(mod))
        assert m, f"{name}: no --watchlist default found to compare against"
        paths[name] = Path(m.group(1)).resolve()

    assert len(set(paths.values())) == 1, (
        "the watchlist writers and the reader disagree on the file:\n  "
        + "\n  ".join(f"{k:<8} {v}" for k, v in sorted(paths.items())))


# --- the screen as of 2026-09-08 -------------------------------------------------

def test_the_screen_is_exactly_the_two_clauses_ben_asked_for():
    """Ben, 2026-09-08, final: remove all existing filters; keep only
    pre-market price $2-25 and pre-market change >= 20% -- the gap versus the
    PREVIOUS REGULAR-SESSION CLOSE, by TradingView's own definition. Not the
    move since the 04:00 print (premarket_change_from_open), which was the
    screen for one bundle and was wrong. Relative volume and float are GONE,
    not lowered."""
    from common import tv_screener as S
    lefts = [f["left"] for f in S.FILTERS]
    assert lefts == ["premarket_change", "premarket_close", "premarket_volume"]
    chg = next(f for f in S.FILTERS if f["left"] == "premarket_change")
    px = next(f for f in S.FILTERS if f["left"] == "premarket_close")
    vol = next(f for f in S.FILTERS if f["left"] == "premarket_volume")
    assert chg["operation"] == "egreater" and chg["right"] == 20.0
    assert px["operation"] == "in_range" and px["right"] == [2.0, 25.0]
    assert vol["operation"] == "egreater" and vol["right"] == 100_000
    for gone in ("relative_volume_10d_calc", "float_shares_outstanding",
                 "premarket_change_from_open"):
        assert gone not in lefts, f"{gone} is not part of the screen any more"


def test_the_feed_ranks_on_the_column_it_filters_on():
    """The trader takes the top of the file. Sorting on the gap while
    filtering on the move since open would rank the list by a number the
    screen no longer uses."""
    from common import tv_screener as S
    assert F.tv_payload()["sort"]["sortBy"] == S.CHANGE_COLUMN
    assert S.payload()["sort_by"] == S.CHANGE_COLUMN
    assert S.CHANGE_COLUMN in S.COLUMNS, "the ranking column must be returned"


def test_the_screen_ceiling_is_above_the_strategy_band_on_purpose():
    """$25 screen, $20 trader. The gap is what makes $20-25 names WARM."""
    from common import tv_screener as S
    assert S.PREMARKET_PRICE_RANGE == (2.0, 25.0)
    assert S.PRICE_MAX == 20.0
    assert F.in_band(row("X", 20.0)) and not F.in_band(row("Y", 22.0))


def test_an_ignored_filter_is_logged_not_swallowed(monkeypatch, caplog):
    """The server accepts a clause it cannot apply and lists it under
    ignored_filters. The feed read the rows and never the key, so an
    unfiltered watchlist looked exactly like a filtered one."""
    import io
    import json as _json
    import logging

    body = {"data": [{"s": "NASDAQ:AAA", "d": [None] * len(F.COLUMNS)}],
            "ignored_filters": ["premarket_change"]}

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(F.urllib.request, "urlopen",
                        lambda req, timeout: _Resp(_json.dumps(body).encode()))
    with caplog.at_level(logging.WARNING, logger="tv_feed"):
        rows = F.fetch()
    assert len(rows) == 1
    assert any("IGNORED" in r.message and "premarket_change" in r.message
               for r in caplog.records), "the ignored filter was not surfaced"


def test_check_response_reads_both_response_shapes():
    from common.tv_screener import check_response
    mcp_shape = {"data": {"rows": [], "ignored_filters": ["a"]}}
    raw_shape = {"data": [{"s": "X", "d": []}], "ignored_filters": ["b"]}
    clean = {"data": [{"s": "X", "d": []}]}
    assert check_response(mcp_shape) == ["a"]
    assert check_response(raw_shape) == ["b"]
    assert check_response(clean) == []


# --- parity between the three Pine scripts and the Python band --------------

def test_every_pine_script_enforces_the_same_price_band():
    """PROGRAM_INDEX §1: whatever filter one strategy enforces, all must.

    MCL's Pine was the last of the three without the band, so a chart outside
    $2-20 showed entry signals the live trader would refuse -- the same
    live/backtest split that let the apex exit run for three days after it was
    turned off.
    """
    import re
    from pathlib import Path

    from strategy.mcl.mcl import PRICE_MAX, PRICE_MIN

    root = Path(__file__).resolve().parents[2] / "pine"
    for name in ("MCL.pine", "MC5.pine", "VW9.pine"):
        src = (root / name).read_text(encoding="utf-8")
        assert "usePriceBand" in src, f"{name} has no price-band input"
        lo = re.search(r'priceMin = input\.float\(([\d.]+)', src)
        hi = re.search(r'priceMax = input\.float\(([\d.]+)', src)
        assert lo and hi, f"{name}: could not read the band defaults"
        assert float(lo.group(1)) == PRICE_MIN, f"{name} min != mcl.py"
        assert float(hi.group(1)) == PRICE_MAX, f"{name} max != mcl.py"
        assert 'input.bool(true, "Enforce $2-20 price band"' in src, \
            f"{name}: the band must default ON, as every engine does"
        assert "bandBlocked" in src, (
            f"{name}: no PRICE BAND BLOCKED line. A symbol outside the band "
            "produces no trades, which reads as no signal unless it says so")


# --- why a name dropped off the watchlist (Ben, 2026-09-09) -----------------

def test_the_drop_lookup_asks_for_the_named_symbols_with_no_filters():
    """The screen is applied server-side, so a name that stops passing returns
    no row. The only way to learn why is to ask for it unfiltered."""
    p = F.tickers_payload(["NASDAQ:WYHG", "NYSE:BNC"])
    assert p["filter"] == [], "any clause here re-hides the row we are asking about"
    assert p["symbols"]["tickers"] == ["NASDAQ:WYHG", "NYSE:BNC"]
    assert p["columns"] == list(F.COLUMNS), (
        "the reason is computed from these columns; a short list means a "
        "clause cannot be evaluated and gets reported as 'n/a'")


def test_the_reason_is_derived_from_the_live_filter_list():
    """THE TRAP THIS TEST EXISTS FOR. The screen was five clauses last week and
    is three today. A hand-written explanation would keep describing last
    week's screen, confidently, in a message that looked right."""
    from common import tv_screener as TS
    row = {"premarket_change": 25.0, "premarket_close": 8.0,
           "premarket_volume": 62_000.0}
    assert [c["column"] for c in TS.failing_clauses(row)] == ["premarket_volume"]

    # Add a clause to the screen and the explanation follows it, with no edit
    # here and none in notify.py.
    extra = list(TS.FILTERS) + [{"left": "relative_volume_10d_calc",
                                 "operation": "egreater", "right": 5.0}]
    cols = [c["column"] for c in TS.failing_clauses(row, filters=extra)]
    assert cols == ["premarket_volume", "relative_volume_10d_calc"]


def test_a_missing_column_is_a_failure_not_a_pass():
    """A row TradingView returns without the column is not a row that passed
    on it. Treating absent as passing would drop the real reason silently."""
    from common import tv_screener as TS
    bad = TS.failing_clauses({"premarket_change": 25.0, "premarket_close": 8.0})
    assert [c["column"] for c in bad] == ["premarket_volume"]
    assert bad[0]["value"] is None


def test_an_operation_the_evaluator_does_not_know_blames_nothing():
    """Reporting an unevaluable clause as failed would blame a clause the row
    may well pass."""
    from common import tv_screener as TS
    weird = [{"left": "premarket_close", "operation": "matches_pattern",
              "right": "x"}]
    assert TS.failing_clauses({"premarket_close": 8.0}, filters=weird) == []


def test_the_lookup_never_raises_into_the_poll(monkeypatch):
    """This is a cosmetic feature inside the loop that keeps the watchlist
    current. A TradingView hiccup must cost a reason string, never a poll."""
    def boom(*a, **k):
        raise OSError("connection reset")
    monkeypatch.setattr(F.urllib.request, "urlopen", boom)
    assert F.explain_drops(["NASDAQ:WYHG"]) == {}


def test_a_symbol_the_unfiltered_query_also_loses_is_not_blamed_on_a_clause(
        monkeypatch):
    """Halted, delisted, or simply not carried by the scanner. Naming a clause
    it failed would be a lie -- we never saw a value to judge."""
    monkeypatch.setattr(F, "_scan", lambda payload: {"data": []})
    assert F.explain_drops(["NASDAQ:GONE"]) == {
        "GONE": "no longer returned by the scanner"}


def test_a_symbol_that_comes_back_is_explained_by_its_failing_clause(
        monkeypatch):
    vals = {"premarket_change": 25.0, "premarket_close": 8.0,
            "premarket_volume": 62_000.0}
    d = [vals.get(c) for c in F.COLUMNS]
    monkeypatch.setattr(F, "_scan",
                        lambda payload: {"data": [{"s": "NASDAQ:WYHG", "d": d}]})
    assert F.explain_drops(["NASDAQ:WYHG"]) == {"WYHG": "pm vol 62k < 100k"}


def test_nothing_dropped_means_no_extra_request(monkeypatch):
    """One extra call per poll that lost something, and none otherwise."""
    calls = []
    monkeypatch.setattr(F, "_scan", lambda payload: calls.append(payload) or {})
    assert F.explain_drops([]) == {}
    assert calls == []
