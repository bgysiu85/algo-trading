#!/usr/bin/env python3
"""Resolving instrument_id -> ticker without databento's vectorised resolver.

The resolver dies on the full-universe monthly chunks with

    TypeError: Cannot compare structured arrays unless they have a common dtype

so there is a fallback. A fallback that disagrees with the path it replaces is
worse than no fallback -- it produces a whole run of wrong tickers and nothing
raises. It was verified against the working path on the 2025-04 daily chunk:
199,380 rows, zero mismatches, zero nulls on either side. These tests pin the
rules that verification depends on.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from common import dbn_io


def sidecar(entries) -> str:
    """entries: {ticker: [(d0, d1, instrument_id), ...]}"""
    return json.dumps({"result": {
        t: [{"d0": a, "d1": b, "s": str(s)} for a, b, s in ivs]
        for t, ivs in entries.items()}})


def test_the_interval_is_half_open():
    """d1 is EXCLUSIVE. Treating it as inclusive puts the last day of one
    mapping and the first of the next on the same id, and whichever is written
    second wins -- silently, for one session per rollover."""
    text = sidecar({"AAA": [("2025-04-01", "2025-05-01", 7)]})
    lut = dbn_io.symbol_lookup(text, ["2025-03-31", "2025-04-30", "2025-05-01"])
    assert (7, "2025-04-30") in lut
    assert (7, "2025-05-01") not in lut
    assert (7, "2025-03-31") not in lut


def test_a_reused_instrument_id_resolves_by_date():
    """An instrument_id is unique only within its interval. Keying the map on
    the id alone would give every row of a reused id the wrong ticker -- and a
    wrong ticker propagates, where a missing one stops."""
    text = sidecar({"OLD": [("2025-04-01", "2025-04-15", 7)],
                    "NEW": [("2025-04-15", "2025-05-01", 7)]})
    lut = dbn_io.symbol_lookup(text, ["2025-04-10", "2025-04-20"])
    assert lut[(7, "2025-04-10")] == "OLD"
    assert lut[(7, "2025-04-20")] == "NEW"


def test_one_ticker_can_hold_several_ids():
    text = sidecar({"AAA": [("2025-04-01", "2025-04-15", 7),
                            ("2025-04-15", "2025-05-01", 9)]})
    lut = dbn_io.symbol_lookup(text, ["2025-04-10", "2025-04-20"])
    assert lut[(7, "2025-04-10")] == "AAA" and lut[(9, "2025-04-20")] == "AAA"


def test_malformed_entries_are_skipped_not_fatal():
    text = json.dumps({"result": {"AAA": [{"d0": "2025-04-01",
                                           "d1": "2025-05-01", "s": "7"}],
                                  "BAD": [{"d0": "2025-04-01"}],
                                  "WORSE": "not-a-list"}})
    lut = dbn_io.symbol_lookup(text, ["2025-04-10"])
    assert lut == {(7, "2025-04-10"): "AAA"}


def test_only_the_dates_present_are_expanded():
    """A month of the full universe is ~11,500 tickers. Expanding the whole
    history rather than the dates in hand turns a lookup into a memory
    problem."""
    text = sidecar({"AAA": [("2020-01-01", "2030-01-01", 7)]})
    assert len(dbn_io.symbol_lookup(text, ["2025-04-10"])) == 1


# --- the frame-level join ---------------------------------------------------

def frame(rows):
    """rows: (utc_timestamp, instrument_id)."""
    idx = pd.DatetimeIndex([pd.Timestamp(t, tz="UTC") for t, _ in rows])
    return pd.DataFrame({"instrument_id": [i for _, i in rows]}, index=idx)


def test_the_join_uses_each_rows_own_date():
    text = sidecar({"OLD": [("2025-04-01", "2025-04-15", 7)],
                    "NEW": [("2025-04-15", "2025-05-01", 7)]})
    df = frame([("2025-04-10 14:30", 7), ("2025-04-20 14:30", 7)])
    out = dbn_io.map_symbols_manually(df, text)
    assert list(out["symbol"]) == ["OLD", "NEW"]


def test_an_unmapped_id_becomes_none_rather_than_raising():
    """None is visible downstream -- read_dbn already refuses a frame that is
    entirely None. A raise here would lose the rows that DID map."""
    text = sidecar({"AAA": [("2025-04-01", "2025-05-01", 7)]})
    out = dbn_io.map_symbols_manually(frame([("2025-04-10 14:30", 999)]), text)
    assert out["symbol"].isna().all()


def test_the_input_frame_is_not_mutated():
    text = sidecar({"AAA": [("2025-04-01", "2025-05-01", 7)]})
    df = frame([("2025-04-10 14:30", 7)])
    dbn_io.map_symbols_manually(df, text)
    assert "symbol" not in df.columns


def test_a_naive_index_is_handled_as_utc():
    text = sidecar({"AAA": [("2025-04-01", "2025-05-01", 7)]})
    df = pd.DataFrame({"instrument_id": [7]},
                      index=pd.DatetimeIndex([pd.Timestamp("2025-04-10 14:30")]))
    assert list(dbn_io.map_symbols_manually(df, text)["symbol"]) == ["AAA"]


# --- the fallback is narrow -------------------------------------------------

def test_an_unrelated_typeerror_is_not_swallowed(tmp_path, monkeypatch):
    """The fallback triggers only on the resolver's structured-array failure.
    Catching every TypeError would turn a real bug into a silent second code
    path, which is how a wrong answer gets a fresh chance to look right."""
    import databento as db

    class Store:
        symbology = {"mappings": {"x": 1}}

        def to_df(self, **kw):
            raise TypeError("something else entirely")

    monkeypatch.setattr(db.DBNStore, "from_file",
                        staticmethod(lambda p: Store()), raising=True)
    f = tmp_path / "2025-04.dbn.zst"
    f.write_bytes(b"")
    with pytest.raises(TypeError, match="something else entirely"):
        dbn_io.read_dbn(f, require_symbols=False)
