#!/usr/bin/env python3
"""The paper trader's own fill logs, into the database.

Ben, 2026-09-10: "i would like the paper trade csv files to go into the
database as well."

Until now every paper session lived only as var/fills/mcl_fills_YYYYMMDD.csv,
one loose file per day. The whole justification for putting MC5 on paper is
LIVE FILLS -- entry slippage measured at 7-15c/share against a $4.26/round-trip
allowance, on n=2 -- and that measurement is a comparison ACROSS sessions,
which two loose CSVs cannot answer.

Everything here runs against a real SQLite database rather than a mock, so the
round trip is measured. A mocked conn would have accepted the double-count in
test_loading_twice_is_a_no_op without noticing.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select

from common import db as D
from common import db_load as L

HEADER = ",".join(L.__dict__.get("_FIELDS", [])) or None


def fills_csv(tmp_path, rows, name="mcl_fills_20260910.csv"):
    """A fill log with the trader's real header, so a column added there and
    not here fails visibly instead of loading as nulls."""
    from brokers.ibkr.trader import FIELDS
    p = tmp_path / name
    lines = [",".join(FIELDS)]
    for r in rows:
        lines.append(",".join(str(r.get(f, "")) for f in FIELDS))
    p.write_text("\n".join(lines) + "\n")
    return p


def row(ts, symbol="WYHG", strategy="MCL", action="BUY",
        status="FILLED", **kw):
    base = {"ts_et": ts, "strategy": strategy, "symbol": symbol,
            "action": action, "status": status, "reason": "entry_signal",
            "ref_close": 5.21, "ref_kind": "signal_close",
            "fill_price": 5.22, "filled_qty": 100, "qty": 100,
            "slippage_vs_ref": -0.01, "seconds_to_fill": 1.3}
    base.update(kw)
    return base


@pytest.fixture
def conn():
    eng = create_engine("sqlite://")
    D.META.create_all(eng)
    with eng.begin() as c:
        yield c


def count(conn):
    return conn.execute(select(func.count()).select_from(D.paper_fill)).scalar()


# --- the table exists and has a way in --------------------------------------

def test_the_table_has_a_loader_flag():
    """db_load's own rule: three tables once shipped that nothing could fill,
    and an empty table looks identical either way."""
    assert L.FILLED_BY["paper_fill"] == "--paper-fills"
    assert "--paper-fills" in {a.option_strings[0]
                               for a in L.parser()._actions
                               if a.option_strings}


def test_every_trader_field_has_a_column():
    """If the trader adds a column and this table does not, the value is
    dropped and the load still reports success."""
    from brokers.ibkr.trader import FIELDS
    cols = set(D.paper_fill.c.keys())
    missing = [f for f in FIELDS if f not in cols]
    assert not missing, f"paper_fill has no column for {missing}"


# --- THE ONE THAT MATTERS ---------------------------------------------------

def test_loading_twice_is_a_no_op(tmp_path, conn):
    p = fills_csv(tmp_path, [row("2026-09-10 06:21:00"),
                             row("2026-09-10 06:23:00", action="SELL")])
    n1, days = L.load_paper_fills(conn, [p])
    assert (n1, days) == (2, ["2026-09-10"])
    L.load_paper_fills(conn, [p])
    assert count(conn) == 2, "a second load duplicated the session"


def test_a_mid_session_load_then_a_final_one_does_not_double_count(tmp_path, conn):
    """THE REASON THIS TABLE IS KEYED BY SESSION AND NOT BY run_id.

    A fill log GROWS while the session is live. Keyed on path+mtime the way
    every other loader is, 06:00 and 09:35 would be two different run_ids, the
    delete would clear neither, and every fill from the first half of the
    session would be counted twice -- valid table, working queries, wrong P/L.
    """
    p = fills_csv(tmp_path, [row("2026-09-10 06:21:00")])
    L.load_paper_fills(conn, [p])

    # The session continues and the file grows.
    p = fills_csv(tmp_path, [row("2026-09-10 06:21:00"),
                             row("2026-09-10 07:26:00", symbol="LABT"),
                             row("2026-09-10 09:29:00", action="SELL")])
    n, _ = L.load_paper_fills(conn, [p])
    assert n == 3
    assert count(conn) == 3, "the mid-session rows were counted twice"


def test_a_second_session_does_not_disturb_the_first(tmp_path, conn):
    """Replacing by session must replace ONE session. A loader that cleared the
    table would pass every test above and lose the history that is the entire
    point of putting these in a database."""
    a = fills_csv(tmp_path, [row("2026-09-09 06:21:00")], "f_09.csv")
    b = fills_csv(tmp_path, [row("2026-09-10 06:21:00")], "f_10.csv")
    L.load_paper_fills(conn, [a])
    L.load_paper_fills(conn, [b])
    assert count(conn) == 2
    got = conn.execute(select(D.paper_fill.c.session_date)).scalars().all()
    assert sorted(str(d) for d in got) == ["2026-09-09", "2026-09-10"]


# --- keying -----------------------------------------------------------------

def test_two_strategies_in_the_same_minute_are_two_rows(tmp_path, conn):
    """MCL and MC5 share one log and one account, and can act on the same
    symbol in the same minute. Without strategy in the key one would silently
    overwrite the other -- and 'which strategy took it' is the question the
    shared-book design exists to answer."""
    p = fills_csv(tmp_path, [row("2026-09-10 06:21:00", strategy="MCL"),
                             row("2026-09-10 06:21:00", strategy="MC5")])
    n, _ = L.load_paper_fills(conn, [p])
    assert n == 2 and count(conn) == 2


def test_a_buy_and_a_sell_in_one_minute_are_two_rows(tmp_path, conn):
    p = fills_csv(tmp_path, [row("2026-09-10 06:21:00", action="BUY"),
                             row("2026-09-10 06:21:00", action="SELL")])
    assert L.load_paper_fills(conn, [p])[0] == 2


def test_a_fill_and_a_skip_in_one_minute_are_two_rows(tmp_path, conn):
    """SKIPPED_CONCURRENCY_CAP rows are decisions, not trades, and they are
    what tonight's cap change has to be judged on."""
    p = fills_csv(tmp_path, [
        row("2026-09-10 06:21:00", status="FILLED"),
        row("2026-09-10 06:21:00", status="SKIPPED_CONCURRENCY_CAP")])
    assert L.load_paper_fills(conn, [p])[0] == 2


def test_the_session_comes_from_the_rows_not_the_filename(tmp_path, conn):
    """The filename is a convention nothing enforces; ts_et is when the row
    actually happened. A log appended across a restart lands each row in its
    own session instead of all of them under whichever date the name claimed."""
    p = fills_csv(tmp_path, [row("2026-09-09 06:21:00"),
                             row("2026-09-10 06:21:00")],
                  name="mcl_fills_20260101.csv")
    n, days = L.load_paper_fills(conn, [p])
    assert days == ["2026-09-09", "2026-09-10"]


# --- inputs that are wrong rather than absent -------------------------------

def test_overlapping_files_do_not_abort_the_load(tmp_path, conn):
    """FillLog rolls a log aside as <name>_preHHMMSS.csv when its header
    changes, so a glob picks up both and they overlap. A duplicate primary key
    is an IntegrityError that aborts AFTER the delete has run -- which would
    leave the session EMPTY rather than unchanged."""
    r = row("2026-09-10 06:21:00")
    a = fills_csv(tmp_path, [r], "mcl_fills_20260910.csv")
    b = fills_csv(tmp_path, [r], "mcl_fills_20260910_pre093000.csv")
    n, _ = L.load_paper_fills(conn, [a, b])
    assert n == 1 and count(conn) == 1


def test_a_row_with_no_timestamp_is_dropped_not_stored(tmp_path, conn):
    """It cannot be keyed and cannot be de-duplicated."""
    p = fills_csv(tmp_path, [row(""), row("2026-09-10 06:21:00")])
    n, _ = L.load_paper_fills(conn, [p])
    assert n == 1


def test_a_missing_file_is_skipped_quietly(tmp_path, conn):
    n, days = L.load_paper_fills(conn, [tmp_path / "nope.csv"])
    assert (n, days) == (0, [])


def test_ts_et_is_stored_as_the_et_wall_clock(tmp_path, conn):
    """NOT normalised to UTC. _ts() would convert a tz-aware value and store it
    under a column called ts_et on a different clock from every row beside it,
    and two clocks in one column is not something a query can detect."""
    p = fills_csv(tmp_path, [row("2026-09-10 06:21:00")])
    L.load_paper_fills(conn, [p])
    got = conn.execute(select(D.paper_fill.c.ts_et)).scalar()
    assert str(got) == "2026-09-10 06:21:00"


def test_a_tz_aware_timestamp_is_refused_rather_than_converted():
    assert L._et_naive("2026-09-10 06:21:00-04:00") is None
    assert L._et_naive("2026-09-10 06:21:00") == datetime(2026, 9, 10, 6, 21)


def test_the_indicator_state_survives_the_round_trip(tmp_path, conn):
    """'Why did it take that one' is unanswerable afterwards without it."""
    p = fills_csv(tmp_path, [row("2026-09-10 06:21:00", macd=0.031,
                                 rsi=61.2, vol=812000, prev_vol=201000)])
    L.load_paper_fills(conn, [p])
    r = conn.execute(select(D.paper_fill.c.macd, D.paper_fill.c.rsi,
                            D.paper_fill.c.vol)).one()
    assert r.macd == pytest.approx(0.031)
    assert r.rsi == pytest.approx(61.2)
    assert r.vol == pytest.approx(812000)
