#!/usr/bin/env python3
"""The MCL-PB report reads the registration and nothing else."""
from __future__ import annotations

from collections import Counter

import pytest

from common import pullback_break as S

F = S.MEASURED_FRICTION


def rows(date, nets, pre07=True):
    return [{"date": date, "net": n + F, "pre07": pre07, "symbol": "X",
             "entry_px": 5.0, "entry_et": "05:00", "reason": "trailing_stop",
             "bars_held": 3} for n in nets]


CUT = "2026-02-01"


def test_halves_cut_both_books_on_ONE_date():
    a, b = S.halves(rows("2026-01-10", [1]) + rows("2026-03-10", [1, 1]), CUT)
    assert len(a) == 1 and len(b) == 2


def test_clears_needs_both_halves_and_drop_top_five():
    pb = rows("2026-01-10", [10] * 6) + rows("2026-03-10", [10] * 6)
    assert S.verdict(pb, [], CUT)[0] == "CLEARS"
    # positive only because of five big trades
    pb = rows("2026-01-10", [100] * 3 + [-5] * 20) + rows("2026-03-10", [100] * 2 + [-5] * 20)
    assert S.verdict(pb, rows("2026-01-10", [-50]) + rows("2026-03-10", [-50]), CUT)[0] != "CLEARS"


def test_trading_less_on_a_losing_book_is_not_enough_per_trade_alone():
    """Better average, worse total in a half -> NOTHING."""
    mcl = rows("2026-01-10", [-1] * 10) + rows("2026-03-10", [-1] * 10)
    pb = rows("2026-01-10", [-0.5] * 30) + rows("2026-03-10", [-0.5] * 5)
    tag, why = S.verdict(pb, mcl, CUT)
    assert tag == "NOTHING" and "total" in why


def test_improves_needs_average_and_total_in_both_halves():
    mcl = rows("2026-01-10", [-10] * 10) + rows("2026-03-10", [-10] * 10)
    pb = rows("2026-01-10", [-2] * 5) + rows("2026-03-10", [-2] * 5)
    assert S.verdict(pb, mcl, CUT)[0] == "IMPROVES"


def test_an_empty_half_is_nothing_not_a_pass():
    assert S.verdict(rows("2026-03-10", [50] * 10), [], CUT)[0] == "NOTHING"


def test_pre07_reads_only_the_pre07_rows():
    mcl = rows("2026-01-10", [-10]) + rows("2026-03-10", [-10]) \
        + rows("2026-01-10", [50], pre07=False) + rows("2026-03-10", [50], pre07=False)
    pb = rows("2026-01-10", [-1]) + rows("2026-03-10", [-1]) \
        + rows("2026-01-10", [-50], pre07=False) + rows("2026-03-10", [-50], pre07=False)
    assert S.pre07_holds(pb, mcl, CUT)[0] is True
    assert S.pre07_holds(mcl, pb, CUT)[0] is False


def test_drop_top_removes_the_best_not_the_first():
    r = rows("2026-01-10", [1, 100, 2, 90, 3, 80, 70, 60])
    assert S.drop_top(r, F) == pytest.approx(1 + 2 + 3)


def test_money_brackets_negatives():
    assert S.money(-3.5) == "(3.50)" and S.money(2) == "2.00"


def test_render_prints_verdict_population_cells_and_level_outcomes():
    mcl = rows("2026-01-10", [-5] * 4) + rows("2026-03-10", [-5] * 4)
    pb = rows("2026-01-10", [1] * 7) + rows("2026-03-10", [1] * 7)
    pbs = {n: pb for n, _ in S.CELLS}
    txt = "\n".join(S.render(mcl, pbs, Counter(triggered=14, refused_macd=3, expired=2),
                             [3, 5, 8], 40, 0, ["2026-01-10", "2026-03-10"], 1.0, 1))
    for must in ("POPULATION CHECK", "DOES NOT MATCH", "refused_macd", "THE VERDICT",
                 "PRE-07", "before 07:00", "PB2-10c", "PB2-25c", "CLEARS",
                 "read on PB2", "median 5"):
        assert must in txt


def test_csv_carries_every_book(tmp_path):
    p = tmp_path / "t.csv"
    pbs = {"PB2": rows("2026-01-10", [2, 3]), "PB2-10c": rows("2026-01-10", [1])}
    S.write_csv(str(p), rows("2026-01-10", [1]), pbs)
    lines = p.read_text().splitlines()
    assert len(lines) == 5
    assert sum(l.startswith("PB2,") for l in lines) == 2
    assert sum(l.startswith("PB2-10c,") for l in lines) == 1


# --- run_day against the real engines -----------------------------------------

def _frame(n=330, seed=7):
    import numpy as np
    import pandas as pd
    from datetime import date, datetime, time as dtime, timedelta
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    D = date(2026, 3, 2)
    idx = []
    for d in (D - timedelta(days=1), D):
        b = pd.Timestamp(datetime.combine(d, dtime(4, 0), tzinfo=ET))
        idx += [(b + timedelta(minutes=i)).tz_convert("UTC") for i in range(n)]
    rng = np.random.default_rng(seed)
    c = 5 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(idx))))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + abs(rng.normal(0, .004, len(c))))
    lo = np.minimum(o, c) * (1 - abs(rng.normal(0, .004, len(c))))
    v = rng.lognormal(8, 1.2, len(c)).astype(int)
    return pd.DataFrame({"symbol": "AAA", "open": o, "high": h, "low": lo,
                         "close": c, "volume": v}, index=pd.DatetimeIndex(idx)), D


def test_run_day_returns_every_book_from_one_pass(monkeypatch):
    import pandas as pd
    hit = None
    for seed in range(40):
        df, D = _frame(seed=seed)
        monkeypatch.setattr("common.dbn_io.read_dbn", lambda p, df=df: df)
        fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert("UTC").isoformat()
        day, res, err = S.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                                   [{"symbol": "AAA", "date": D.isoformat(),
                                     "first_seen": fs}]))
        assert err == "" and res["errors"] == 0 and res["symdays"] == 1
        assert set(res["pb"]) == {n for n, _ in S.CELLS}
        if res["mcl"] and res["pb"]["PB2"]:
            hit = res
            break
    assert hit, "no seed produced trades in both books"
    assert hit["setups"]["triggered"] + hit["setups"]["band_refused"] >= len(hit["pb"]["PB2"])
    assert hit["levels_per_symday"] == [sum(hit["setups"].values())]
    for r in hit["pb"]["PB2"]:
        # the chart coordinates a person needs to find the trade
        assert r["top_et"] <= r["armed_et"] < r["entry_et"] <= r["exit_et"]
        assert r["reds"] >= 2
        assert r["entry_px"] >= r["level"] + 0.02 - 1e-4
    assert not any("level" in r for r in hit["mcl"])
    # the target cells are the same entries, exited differently or the same
    e0 = [r["entry_et"] for r in hit["pb"]["PB2"]]
    assert hit["pb"]["PB2-10c"][0]["entry_et"] == e0[0]
