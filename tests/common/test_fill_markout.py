#!/usr/bin/env python3
"""W03-0005 Part B: the markout decomposition of Ben's real fills.

docs/research/REGISTERED_exec_cost.md B.4. What would break it silently:

  * the identity not adding up (a component double-counted or dropped);
  * a stale quote used as if it were current (> 60 s at the fill);
  * a quote leaking between symbols;
  * a short's entry treated as an exit (the drift then signed backwards);
  * a position with an unpriced fill left in (its gross then half-explained).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from common import fill_markout as FM
from common import flex

UTC = "UTC"


def ex(sym, qty, px, t, day="2026-08-03", comm=-1.0, fifo=0.0, tid=None, timed=True):
    return flex.Execution(symbol=sym, trade_date=day, dt_raw=datetime.fromisoformat(t),
                          qty=float(qty), price=float(px), commission=comm, fifo_pnl=fifo,
                          side="BUY" if qty > 0 else "SELL", trade_id=tid or f"{sym}{t}{qty}",
                          time_known=timed, et_minute=5 * 60)


def Q(sym, t, bid, ask):
    return {"ts": pd.Timestamp(t, tz=UTC), "symbol": sym, "bid": bid, "ask": ask,
            "bid_sz": 100, "ask_sz": 100}


# --- positions ----------------------------------------------------------------

def test_positions_match_flex_round_trips_and_roles_cover_shorts():
    execs = [ex("AAA", 100, 5.0, "2026-08-03 09:00:00"),
             ex("AAA", 100, 5.1, "2026-08-03 09:00:10"),       # add: entry
             ex("AAA", -150, 5.2, "2026-08-03 09:01:00"),      # scale out: exit
             ex("AAA", -50, 5.3, "2026-08-03 09:02:00"),       # flat
             ex("BBB", -200, 3.0, "2026-08-03 09:00:00"),      # SHORT entry
             ex("BBB", 200, 2.9, "2026-08-03 09:03:00"),       # cover: exit
             ex("CCC", 100, 7.0, "2026-08-03 09:00:00")]       # never flat
    role, pos = FM.assign_positions(execs)
    assert len(pos) == len(flex.round_trips(execs)) == 3
    ent = [role[e.trade_id][1] for e in execs]
    assert ent == [True, True, False, False, True, False, True]
    assert pos[2]["open_at_end"] and not pos[0]["open_at_end"]
    assert pos[0]["peak"] == 200 and pos[1]["peak"] == 200


# --- quotes -------------------------------------------------------------------

def frame(execs):
    role, pos = FM.assign_positions(execs)
    return FM.fills_frame(execs, "UTC", role), pos


def test_the_quote_is_the_last_one_before_the_fill_and_never_stale_or_foreign():
    execs = [ex("AAA", 100, 5.02, "2026-08-03 09:00:30"),
             ex("AAA", -100, 5.10, "2026-08-03 09:05:00"),
             ex("BBB", 100, 3.00, "2026-08-03 09:00:30")]
    f, _ = frame(execs)
    q = pd.DataFrame([Q("AAA", "2026-08-03 09:00:10", 5.00, 5.02),
                      Q("AAA", "2026-08-03 09:00:40", 5.04, 5.06),   # after the fill: not used for m0
                      Q("AAA", "2026-08-03 09:01:40", 5.08, 5.10),
                      Q("ZZZ", "2026-08-03 09:00:29", 1.00, 1.02)])  # another symbol
    p = FM.price_fills(f, q).set_index("trade_id")
    a = p.loc[execs[0].trade_id]
    assert a["m0"] == pytest.approx(5.01)
    assert a["m60"] == pytest.approx(5.05)            # last at or before 09:01:30 is 09:00:40
    assert a["m5"] == pytest.approx(5.01) and bool(a["same5"])
    assert a["m300"] == pytest.approx(5.09)
    # The exit at 09:05:00: last AAA quote is 09:01:40, 200 s old -> unpriced.
    assert np.isnan(p.loc[execs[1].trade_id]["m0"])
    # BBB has no quote of its own; ZZZ's must not leak in.
    assert np.isnan(p.loc[execs[2].trade_id]["m0"])


# --- the identity -------------------------------------------------------------

def test_the_identity_adds_up_and_the_parts_have_the_right_signs():
    """Buy 100 at 5.02 into 5.00/5.02 (paid 1c vs mid); a minute later the mid
    is 4.97 (went AGAINST him by 4c); sell at 5.08 into 5.08/5.10 (paid 1c);
    a minute later the mid is 5.00 (he got out before an 9c drop)."""
    execs = [ex("AAA", 100, 5.02, "2026-08-03 09:00:30", comm=-1.0),
             ex("AAA", -100, 5.08, "2026-08-03 09:10:30", comm=-1.2)]
    f, pos = frame(execs)
    q = pd.DataFrame([Q("AAA", "2026-08-03 09:00:20", 5.00, 5.02),
                      Q("AAA", "2026-08-03 09:01:20", 4.96, 4.98),
                      Q("AAA", "2026-08-03 09:10:20", 5.08, 5.10),
                      Q("AAA", "2026-08-03 09:11:20", 4.99, 5.01)])
    g = FM.components(FM.price_fills(f, q), pos, 60)
    r = g.iloc[0]
    assert r["G"] == pytest.approx(6.0)
    assert r["S_in"] == pytest.approx(1.0) and r["S_out"] == pytest.approx(1.0)
    assert r["D_in"] == pytest.approx(-4.0)            # against him after buying
    assert r["D_out"] == pytest.approx(9.0)            # he sold before a 9c drop
    assert r["C"] == pytest.approx(2.2)
    assert r["M"] - r["S"] == pytest.approx(r["G"])
    assert r["D_in"] + r["D_out"] + r["R"] - r["S"] - r["C"] == pytest.approx(r["net"])
    assert r["net"] == pytest.approx(3.8)


def test_a_short_s_first_minute_is_signed_for_the_short():
    """Short 100 at 3.00; a minute later the mid FELL 5c: good for a short."""
    execs = [ex("BBB", -100, 3.00, "2026-08-03 09:00:30"),
             ex("BBB", 100, 2.90, "2026-08-03 09:05:30")]
    f, pos = frame(execs)
    q = pd.DataFrame([Q("BBB", "2026-08-03 09:00:20", 3.00, 3.02),
                      Q("BBB", "2026-08-03 09:01:20", 2.95, 2.97),
                      Q("BBB", "2026-08-03 09:05:20", 2.88, 2.90)])
    g = FM.components(FM.price_fills(f, q), pos, 60)
    assert g.iloc[0]["D_in"] == pytest.approx(5.0)
    assert g.iloc[0]["G"] == pytest.approx(10.0)


def test_a_position_with_one_unpriced_fill_is_left_out_whole():
    execs = [ex("AAA", 100, 5.02, "2026-08-03 09:00:30"),
             ex("AAA", -100, 5.10, "2026-08-03 09:30:00"),     # no quote within 60 s
             ex("CCC", 100, 7.0, "2026-08-03 09:00:30"),
             ex("CCC", -100, 7.1, "2026-08-03 09:00:50")]
    f, pos = frame(execs)
    q = pd.DataFrame([Q("AAA", "2026-08-03 09:00:20", 5.00, 5.02),
                      Q("CCC", "2026-08-03 09:00:20", 6.99, 7.01)])
    g = FM.components(FM.price_fills(f, q), pos, 60)
    assert list(g["symbol"]) == ["CCC"]


def test_an_open_position_is_left_out():
    execs = [ex("AAA", 100, 5.02, "2026-08-03 09:00:30")]
    f, pos = frame(execs)
    q = pd.DataFrame([Q("AAA", "2026-08-03 09:00:20", 5.00, 5.02)])
    assert FM.components(FM.price_fills(f, q), pos, 60).empty


# --- the words ------------------------------------------------------------------

def test_first_minute_words_are_the_registered_ones():
    assert FM.din_word(-3.0, -1.0) == "PICKED OFF"
    assert FM.din_word(1.0, 3.0) == "MOMENTUM ON HIS SIDE"
    assert FM.din_word(-1.0, 1.0) == "NO RELIABLE FIRST-MINUTE MOVE"


def test_drags_rank_costs_and_only_negative_moves():
    tot = {"C": 100.0, "S": 300.0, "D_in": -500.0, "D_out": 50.0, "R": -20.0}
    got = FM.drags(tot)
    assert [k for k, _ in got][:3] == ["D_in", "S", "C"]
    assert dict(got)["D_out"] == 0.0


def test_boot_din_is_seeded_and_its_point_is_the_ratio_of_sums():
    g = pd.DataFrame({"symbol": ["A", "A", "B"], "date": ["d1", "d1", "d2"],
                      "D_in": [-2.0, -4.0, 1.0], "q_in": [100.0, 100.0, 200.0]})
    p1 = FM.boot_din(g, 200, 1)
    assert p1 == FM.boot_din(g, 200, 1)
    assert p1[0] == pytest.approx(-5.0 / 400 * 100)


def test_the_registered_constants_have_not_moved():
    assert (FM.PRIMARY, FM.HORIZONS, FM.TOLERANCE_S, FM.SEED, FM.NBOOT) == (60, (5, 60, 300), 60, 20260927, 2000)
    assert (FM.DATASET, FM.SCHEMA) == ("XNAS.BASIC", "tcbbo")


# --- end to end -------------------------------------------------------------------

def test_main_end_to_end_on_a_synthetic_flex_file(tmp_path, monkeypatch):
    cols = ["Symbol", "TradeDate", "DateTime", "Quantity", "TradePrice", "IBCommission",
            "FifoPnlRealized", "Buy/Sell", "AssetClass", "LevelOfDetail", "TradeID"]
    # Report timezone UTC; 13:00:30 UTC on 2026-08-03 is 09:00:30 ET.
    rows = [["AAA", "2026-08-03", "2026-08-03 13:00:30", "100", "5.02", "-1", "0", "BUY", "STK", "EXECUTION", "1"],
            ["AAA", "2026-08-03", "2026-08-03 13:10:30", "-100", "5.08", "-1.2", "3.8", "SELL", "STK", "EXECUTION", "2"],
            ["AAA", "2026-08-03", "2026-08-03 13:10:30", "-100", "5.08", "-1.2", "3.8", "SELL", "STK", "ORDER", "3"]]
    d = tmp_path / "flex"
    d.mkdir()
    (d / "report.csv").write_text("\n".join(",".join(r) for r in [cols] + rows) + "\n", encoding="utf-8")

    q = pd.DataFrame([Q("AAA", "2026-08-03 13:00:20", 5.00, 5.02),
                      Q("AAA", "2026-08-03 13:01:20", 4.96, 4.98),
                      Q("AAA", "2026-08-03 13:10:20", 5.08, 5.10),
                      Q("AAA", "2026-08-03 13:11:20", 4.99, 5.01)])
    import common.friction_quotes as FQ
    monkeypatch.setattr(FQ, "quotes_for_date", lambda *a, **k: q.copy())
    out = tmp_path / "r.txt"
    rc = FM.main(["--flex-dir", str(d), "--archive", str(tmp_path), "--tz", "UTC", "--nboot", "50",
                  "--out", str(out), "--csv-fills", str(tmp_path / "f.csv"),
                  "--csv-positions", str(tmp_path / "p.csv")])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "C1: 2 executions / 1 positions" in text          # not the registered history
    assert "C2 identity" in text and "OK" in text
    assert "WHERE THE MONEY WENT" in text and "DECISION WORDS" in text
    assert (tmp_path / "p.csv").exists()
