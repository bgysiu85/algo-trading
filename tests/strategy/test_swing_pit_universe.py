"""Tests for strategy/swing/pit_universe.py (G8, AT-45). Offline: every fetch is faked."""
from __future__ import annotations

import csv
import datetime as dt
import urllib.parse
from pathlib import Path

import pytest

from strategy.swing import pit_universe as P

D = dt.date

PAYLOAD = {
    "General": {"Code": "GSPC"},
    "Components": {
        "0": {"Code": "AAA", "Name": "Alpha"},
        "1": {"Code": "NEW", "Name": "Only in current list"},
    },
    "HistoricalTickerComponents": {
        "0": {"Code": "AAA", "Name": "Alpha", "StartDate": "2010-01-04",
              "EndDate": None, "IsActiveNow": 1, "IsDelisted": 0},
        "1": {"Code": "ZZZ.US", "Name": "Gone Co", "StartDate": "2012-03-01",
              "EndDate": "2019-06-30", "IsActiveNow": 0, "IsDelisted": 1},
        "2": {"Code": "BRK.B", "Name": "Berkshire", "StartDate": "2010-02-16",
              "EndDate": None, "IsActiveNow": 1, "IsDelisted": 0},
    },
}


def fake_fetch(prices: dict[str, list[dict]] | None = None, index_ids=("GSPC.INDX",)):
    prices = prices if prices is not None else {
        "eod/AAA.US": [{"date": "2015-01-02", "close": 1},
                       {"date": "2026-09-18", "close": 2}],
        "eod/BRK-B.US": [{"date": "2015-01-02", "close": 1},
                         {"date": "2026-09-18", "close": 2}],
        "eod/NEW.US": [{"date": "2025-01-02", "close": 1},
                       {"date": "2026-09-18", "close": 2}],
    }
    calls = []

    def fetch(path, params):
        calls.append((path, dict(params)))
        if path == "mp/unicornbay/spglobal/list":
            return [{"ID": i} for i in index_ids]
        if path.startswith("mp/unicornbay/spglobal/comp/"):
            return PAYLOAD
        if path.startswith("exchange-symbol-list"):
            return [{"Code": "ZZZ"}]
        if path in prices:
            return prices[path]
        raise P.NotFound(path)

    fetch.calls = calls
    return fetch


# -------------------------------------------------------------------- the key

def test_key_comes_only_from_the_environment():
    assert P.api_key({"EODHD_API_KEY": " abc123 "}) == "abc123"


def test_missing_key_refuses_with_the_op_read_command():
    with pytest.raises(P.Refused) as e:
        P.api_key({})
    assert 'op read "op://Trading/EODHD/api-token"' in str(e.value)


def test_an_unresolved_op_reference_is_refused():
    with pytest.raises(P.Refused):
        P.api_key({"EODHD_API_KEY": "op://Trading/EODHD/api-token"})


def test_scrub_removes_raw_and_url_encoded_key():
    key = "k3y+/="
    text = f"GET ?api_token={urllib.parse.quote(key, safe='')} and {key}"
    out = P.scrub(text, key)
    assert key not in out and urllib.parse.quote(key, safe="") not in out


def test_there_is_no_key_flag():
    with pytest.raises(SystemExit):
        P.main(["prices", "--key", "abc"])


# -------------------------------------------------------------- parsing

def test_records_accepts_lists_and_numbered_dicts():
    assert P.records([{"a": 1}, 3]) == [{"a": 1}]
    assert P.records({"0": {"a": 1}, "1": {"b": 2}}) == [{"a": 1}, {"b": 2}]
    assert P.records(None) == []


def test_eod_symbol_hyphenates_class_shares_and_adds_exchange():
    assert P.eod_symbol("BRK.B") == "BRK-B.US"
    assert P.eod_symbol("aapl") == "AAPL.US"
    assert P.eod_symbol("AAPL.US") == "AAPL.US"


def test_parse_keeps_delisted_spells_and_normalises_codes():
    spells = P.parse_constituents("sp500", PAYLOAD)
    by = {s.code: s for s in spells}
    assert by["ZZZ"].is_delisted and by["ZZZ"].end == D(2019, 6, 30)
    assert by["AAA"].end is None and by["AAA"].is_active_now


def test_current_member_missing_from_history_is_added_open_ended():
    spells = P.parse_constituents("sp500", PAYLOAD)
    new = [s for s in spells if s.code == "NEW"]
    assert len(new) == 1 and new[0].start is None and new[0].end is None


def test_parse_refuses_a_payload_without_history():
    with pytest.raises(P.Refused):
        P.parse_constituents("sp500", {"Components": {}})


def test_spell_coverage_is_inclusive_at_both_ends():
    s = P.Spell("sp500", "X", "", D(2016, 1, 4), D(2018, 1, 2), False, True)
    assert s.covers(D(2016, 1, 4)) and s.covers(D(2018, 1, 2))
    assert not s.covers(D(2016, 1, 3)) and not s.covers(D(2018, 1, 3))


def test_members_on_is_point_in_time():
    spells = P.parse_constituents("sp500", PAYLOAD)
    assert "ZZZ" in P.members_on(spells, "sp500", D(2016, 6, 1))
    assert "ZZZ" not in P.members_on(spells, "sp500", D(2020, 1, 2))


def test_membership_round_trips_through_csv(tmp_path):
    spells = P.parse_constituents("sp500", PAYLOAD)
    P.write_membership(tmp_path / "m.csv", spells)
    back = P.read_membership(tmp_path / "m.csv")
    assert sorted(back, key=lambda s: s.code) == sorted(spells, key=lambda s: s.code)


# ------------------------------------------------------------ stages

def test_constituents_saves_raw_json_before_parsing(tmp_path):
    fetch = fake_fetch()
    P.stage_constituents(fetch, tmp_path, {"sp500": "GSPC.INDX"})
    assert (tmp_path / "raw" / "comp_sp500.json").exists()
    assert (tmp_path / "raw" / "index_list.json").exists()
    assert (tmp_path / "membership.csv").exists()


def test_constituents_refuses_an_unknown_index_id(tmp_path):
    fetch = fake_fetch(index_ids=("GSPC.INDX",))
    with pytest.raises(P.Refused) as e:
        P.stage_constituents(fetch, tmp_path, {"sp400": "NOPE.INDX"})
    assert "--index sp400=" in str(e.value)


def test_prices_counts_missing_names_instead_of_dropping_them(tmp_path):
    fetch = fake_fetch()
    P.stage_constituents(fetch, tmp_path, {"sp500": "GSPC.INDX"})
    st = P.stage_prices(fetch, tmp_path, "2015-01-01", log=lambda m: None)
    assert st["missing"] == 1 and st["fetched"] == 3
    with (tmp_path / "prices_missing.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["code"] for r in rows] == ["ZZZ"]


def test_prices_resume_skips_what_is_already_on_disk(tmp_path):
    fetch = fake_fetch()
    P.stage_constituents(fetch, tmp_path, {"sp500": "GSPC.INDX"})
    P.stage_prices(fetch, tmp_path, "2015-01-01", log=lambda m: None)
    n = len(fetch.calls)
    st = P.stage_prices(fetch, tmp_path, "2015-01-01", log=lambda m: None)
    assert len(fetch.calls) == n and st["skipped"] == 4


def test_prices_requests_from_the_start_date(tmp_path):
    fetch = fake_fetch()
    P.stage_constituents(fetch, tmp_path, {"sp500": "GSPC.INDX"})
    P.stage_prices(fetch, tmp_path, "2015-01-01", log=lambda m: None)
    eod = [p for path, p in fetch.calls if path.startswith("eod/")]
    assert eod and all(p["from"] == "2015-01-01" for p in eod)


def test_classify_spell_full_partial_none_outside():
    w = (D(2016, 5, 10), D(2026, 9, 18))
    s = P.Spell("sp500", "X", "", D(2012, 1, 1), D(2019, 6, 30), False, True)
    assert P.classify_spell(s, (D(2015, 1, 2), D(2019, 6, 28), 100), w) == "full"
    assert P.classify_spell(s, (D(2018, 1, 2), D(2019, 6, 28), 100), w) == "partial"
    assert P.classify_spell(s, None, w) == "none"
    old = P.Spell("sp500", "Y", "", D(2001, 1, 1), D(2010, 1, 1), False, True)
    assert P.classify_spell(old, None, w) == "outside"


def test_report_names_the_survivorship_hole(tmp_path):
    fetch = fake_fetch()
    P.stage_constituents(fetch, tmp_path, {"sp500": "GSPC.INDX"})
    P.stage_prices(fetch, tmp_path, "2015-01-01", log=lambda m: None)
    lines = P.stage_report(tmp_path, (D(2016, 5, 10), D(2026, 9, 18)), None)
    hole = [l for l in lines if "survivorship hole" in l]
    assert hole and ": 1  <-" in hole[0]
    assert (tmp_path / "coverage_gaps.csv").exists()


def test_report_cross_checks_against_the_free_list(tmp_path):
    fetch = fake_fetch()
    P.stage_constituents(fetch, tmp_path, {"sp500": "GSPC.INDX"})
    fja = tmp_path / "fja.csv"
    fja.write_text('date,tickers\n2016-01-04,"AAA,BRK.B,ZZZ,OLD"\n'
                   '2020-01-02,"AAA,BRK.B"\n', encoding="utf-8")
    lines = P.stage_report(tmp_path, (D(2016, 5, 10), D(2026, 9, 18)), fja)
    text = "\n".join(lines)
    assert "vs the free fja05680 list" in text and "OLD(" in text


def test_sample_dates_are_inside_the_window():
    ds = P.sample_dates(D(2016, 5, 10), D(2017, 12, 31))
    assert ds == [D(2016, 7, 15), D(2017, 1, 15), D(2017, 7, 15)]


def test_report_stage_needs_no_key_and_writes_only_under_out_dir(tmp_path, monkeypatch):
    out = tmp_path / "pit"
    fetch = fake_fetch()
    P.stage_constituents(fetch, out, {"sp500": "GSPC.INDX"})
    monkeypatch.delenv("EODHD_API_KEY", raising=False)
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    assert P.main(["report", "--out-dir", str(out), "--no-compare",
                   "--window-end", "2026-09-18"]) == 0
    assert (out / "report.txt").exists()
    assert list(work.iterdir()) == []


def test_network_stages_refuse_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("EODHD_API_KEY", raising=False)
    with pytest.raises(P.Refused):
        P.main(["prices", "--out-dir", str(tmp_path)])


def test_self_test_passes():
    assert "passed" in P.self_test()[0]


def test_source_writes_files_as_utf8():
    src = Path(P.__file__).read_text(encoding="utf-8")
    for call in ("write_text(", ".open(\"w\""):
        for line in src.splitlines():
            if call in line and "encoding" not in line:
                pytest.fail(f"no encoding on: {line.strip()}")
