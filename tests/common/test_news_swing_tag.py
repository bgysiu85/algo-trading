"""tests/common/test_news_swing_tag.py

W07-0011 subitem 2 -- the NEWS/NO-NEWS point-in-time tag on SWING-v0 picks,
`docs/research/REGISTERED_swing_v0.md` §11.2-§11.3. No real picks CSV exists
yet (W07-0010 has not run), so every fixture here is synthetic, in the
documented `PICK_FIELDS` shape.
"""
from __future__ import annotations

import csv
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from common import news_swing_tag as T

ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


# --- §11.2 filing form scope -- wider and different from news_events -------

def test_scored_filing_forms():
    for form in ("8-K", "10-Q", "10-K", "424B1", "424B3", "424B4", "424B5"):
        assert T.is_scored_filing_form(form), form


def test_unscored_filing_forms():
    for form in ("S-1", "S-3", "EFFECT", "DEF 14A"):
        assert not T.is_scored_filing_form(form), form


def test_filing_form_case_and_whitespace_insensitive():
    assert T.is_scored_filing_form(" 8-k ")
    assert T.is_scored_filing_form("424b4")


# --- §11.2 headline scope -- the >5-symbol exclusion ------------------------

def test_market_wrap_exclusion_boundary():
    assert T.is_scored_headline(5) is True     # "more than 5" -- 5 itself scores
    assert T.is_scored_headline(6) is False
    assert T.is_scored_headline(1) is True


# --- events -------------------------------------------------------------------

def test_filing_events_only_scored_forms():
    rows = [{"form": "8-K", "accepted": "2026-09-01T20:00:00.000Z"},
           {"form": "S-1", "accepted": "2026-09-01T20:00:00.000Z"},   # not scored here
           {"form": "424B3", "accepted": "2026-09-02T20:00:00.000Z"}]
    ev = T.filing_events(rows)
    assert {e.detail for e in ev} == {"8-K", "424B3"}


def test_filing_events_skips_missing_timestamp():
    rows = [{"form": "8-K", "accepted": ""}]
    assert T.filing_events(rows) == []


def test_headline_events_excludes_market_wraps():
    rows = [{"headline": "a", "created_at": "2026-09-01T13:00:00Z", "symbol_count": "2"},
           {"headline": "b", "created_at": "2026-09-01T13:00:00Z", "symbol_count": "12"}]
    ev = T.headline_events(rows)
    assert len(ev) == 1
    assert ev[0].detail == "2 symbol(s)"


def test_headline_events_missing_symbol_count_defaults_to_1():
    rows = [{"headline": "a", "created_at": "2026-09-01T13:00:00Z"}]
    ev = T.headline_events(rows)
    assert len(ev) == 1


# --- the tag itself, point-in-time -------------------------------------------

def test_tag_pick_news_when_event_inside_window():
    events = [T.Event(ts=_et(2026, 5, 3, 12, 0), kind="FILING", detail="8-K")]
    tag = T.tag_pick(_et(2026, 5, 1), _et(2026, 5, 5, 11, 30), events)
    assert tag == T.NEWS


def test_tag_pick_no_news_when_no_event():
    tag = T.tag_pick(_et(2026, 5, 1), _et(2026, 5, 5, 11, 30), [])
    assert tag == T.NO_NEWS


def test_tag_pick_entry_itself_excluded():
    # "every timestamp must be earlier than the entry time" -- an event AT
    # the entry timestamp does not count.
    events = [T.Event(ts=_et(2026, 5, 5, 11, 30), kind="FILING", detail="8-K")]
    tag = T.tag_pick(_et(2026, 5, 1), _et(2026, 5, 5, 11, 30), events)
    assert tag == T.NO_NEWS


def test_tag_pick_drop_start_itself_included():
    events = [T.Event(ts=_et(2026, 5, 1, 0, 0), kind="FILING", detail="8-K")]
    tag = T.tag_pick(_et(2026, 5, 1), _et(2026, 5, 5, 11, 30), events)
    assert tag == T.NEWS


def test_tag_pick_requires_tz_aware():
    with pytest.raises(ValueError):
        T.tag_pick(datetime(2026, 5, 1), _et(2026, 5, 5, 11, 30), [])


# --- MUTATION TEST (§11.2's own requirement): shifting a timestamp by one
# day must be able to flip the tag, or this test fails. -----------------------

def test_mutation_shifting_filing_date_by_one_day_flips_tag():
    drop_start = _et(2026, 5, 1)
    entry = _et(2026, 5, 5, 11, 30)
    # event lands the day AFTER entry -- NO NEWS
    ev_after = [T.Event(ts=_et(2026, 5, 6, 9, 0), kind="FILING", detail="8-K")]
    assert T.tag_pick(drop_start, entry, ev_after) == T.NO_NEWS
    # shift that same event one day earlier -- now inside the window -- NEWS
    ev_shifted = [T.Event(ts=_et(2026, 5, 5, 9, 0), kind="FILING", detail="8-K")]
    assert T.tag_pick(drop_start, entry, ev_shifted) == T.NEWS


def test_mutation_shifting_headline_date_by_one_day_flips_tag():
    drop_start = _et(2026, 5, 1)
    entry = _et(2026, 5, 5, 11, 30)
    ev_before_window = [T.Event(ts=_et(2026, 4, 30, 9, 0), kind="HEADLINE", detail="1 symbol(s)")]
    assert T.tag_pick(drop_start, entry, ev_before_window) == T.NO_NEWS
    ev_shifted = [T.Event(ts=_et(2026, 5, 1, 9, 0), kind="HEADLINE", detail="1 symbol(s)")]
    assert T.tag_pick(drop_start, entry, ev_shifted) == T.NEWS


def test_first_trigger_is_earliest_in_window():
    events = [T.Event(ts=_et(2026, 5, 3, 9, 0), kind="FILING", detail="10-Q"),
             T.Event(ts=_et(2026, 5, 2, 9, 0), kind="HEADLINE", detail="1 symbol(s)")]
    trig = T.first_trigger(_et(2026, 5, 1), _et(2026, 5, 5, 11, 30), events)
    assert trig.detail == "1 symbol(s)"


def test_first_trigger_none_when_no_news():
    assert T.first_trigger(_et(2026, 5, 1), _et(2026, 5, 5, 11, 30), []) is None


# --- the picks contract and the join -----------------------------------------

def _write_picks_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(T.PICK_FIELDS))
        w.writeheader()
        w.writerows(rows)


def _pick(symbol="AAA", entry_date="2026-05-05", entry_et="11:30",
         drop_start_date="2026-05-01", k=5, bucket="midday",
         gross=100.0, cost=10.0, net=90.0, net_2x_stress=80.0, mkt_rel_net=50.0):
    return {"symbol": symbol, "entry_date": entry_date, "entry_et": entry_et,
           "drop_start_date": drop_start_date, "k": k, "bucket": bucket,
           "gross": gross, "cost": cost, "net": net, "net_2x_stress": net_2x_stress,
           "mkt_rel_net": mkt_rel_net}


def test_load_picks_csv_round_trip_and_casts_types(tmp_path):
    p = tmp_path / "picks.csv"
    _write_picks_csv(p, [_pick()])
    got = T.load_picks_csv(str(p))
    assert len(got) == 1
    r = got[0]
    assert r["k"] == 5 and isinstance(r["k"], int)
    assert r["net"] == 90.0 and isinstance(r["net"], float)
    assert r["entry_ts"] == _et(2026, 5, 5, 11, 30)
    assert r["drop_start"] == _et(2026, 5, 1, 0, 0)


def test_load_picks_csv_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit, match="W07-0010"):
        T.load_picks_csv(str(tmp_path / "nope.csv"))


def test_population_from_picks_earliest_drop_start():
    picks = [_pick(symbol="AAA", drop_start_date="2026-05-10"),
            _pick(symbol="AAA", drop_start_date="2026-05-01"),
            _pick(symbol="BBB", drop_start_date="2026-06-01")]
    assert T.population_from_picks(picks) == {"AAA": "2026-05-01", "BBB": "2026-06-01"}


def test_tag_picks_end_to_end(tmp_path):
    p = tmp_path / "picks.csv"
    _write_picks_csv(p, [_pick(symbol="AAA"), _pick(symbol="BBB")])
    picks = T.load_picks_csv(str(p))
    filings = {"AAA": [{"form": "8-K", "accepted": "2026-05-03T20:00:00.000Z"}]}
    headlines: dict = {}
    tagged = T.tag_picks(picks, filings, headlines)
    by_symbol = {r["symbol"]: r for r in tagged}
    assert by_symbol["AAA"]["news_tag"] == T.NEWS
    assert by_symbol["AAA"]["news_trigger"].startswith("FILING:8-K@")
    assert by_symbol["BBB"]["news_tag"] == T.NO_NEWS
    assert by_symbol["BBB"]["news_trigger"] == ""


def test_tag_picks_symbol_absent_from_both_caches_is_no_news(tmp_path):
    p = tmp_path / "picks.csv"
    _write_picks_csv(p, [_pick(symbol="ZZZ")])
    picks = T.load_picks_csv(str(p))
    tagged = T.tag_picks(picks, {}, {})
    assert tagged[0]["news_tag"] == T.NO_NEWS
