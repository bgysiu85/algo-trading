#!/usr/bin/env python3
"""H-B3's gate and the shared gate-study arithmetic read the registration."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from common import gate_study as G
from common import range_rank as R
from tests.common.test_first_entry_skip import EARLY, LATE, rows, symday_pairs

ET = ZoneInfo("America/New_York")
DAY = date(2026, 3, 2)
F = G.MEASURED_FRICTION
CUT = "2026-02-01"


def bars(minutes, hlc, symbol="A"):
    """Session-day bars at the given minutes-after-04:00, (high, low, close)."""
    t0 = datetime.combine(DAY, dtime(4, 0), tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=m) for m in minutes]).tz_convert("UTC")
    h, lo, c = zip(*hlc)
    return pd.DataFrame({"symbol": symbol, "open": c, "high": h, "low": lo, "close": c,
                         "volume": 1000}, index=idx)


# --- the running range ----------------------------------------------------------

def test_running_range_is_strictly_before_the_minute_and_forward_filled():
    df = bars([10, 11, 20], [(10.5, 9.5, 10.0), (10.2, 9.8, 10.0), (11.0, 9.0, 10.0)])
    v = R.running_range_pct(df)
    assert np.isnan(v[:11]).all()                      # nothing printed before minute 10 CLOSED
    assert v[11] == pytest.approx(10.0)                # bar at 10 only: 1.0/10 = 10%
    assert v[12] == pytest.approx(7.0)                 # bars 10, 11: mean(10%, 4%)
    assert v[20] == pytest.approx(7.0)                 # bar 20 not yet counted at minute 20
    assert v[21] == pytest.approx(34.0 / 3)            # mean(10, 4, 20)
    assert v[329] == pytest.approx(34.0 / 3)


def test_running_range_ignores_bars_outside_the_session_and_empty_frames():
    df = bars([-60, 5, 400], [(11.0, 9.0, 10.0), (10.1, 9.9, 10.0), (12.0, 8.0, 10.0)])
    v = R.running_range_pct(df)
    assert np.isnan(v[5]) and v[6] == pytest.approx(2.0) and v[329] == pytest.approx(2.0)
    assert np.isnan(R.running_range_pct(df.iloc[:0])).all()


# --- the rank -------------------------------------------------------------------

def vals(**per_sym):
    """{sym: constant range_pct from minute 1}."""
    out = {}
    for s, x in per_sym.items():
        a = np.full(R.SESSION_MINUTES, float(x))
        a[0] = np.nan
        out[s] = a
    return out


def test_rank_is_among_visible_names_only():
    v = vals(A=5.0, B=8.0, C=9.0)
    gates, vis = R.gates_for_session(v, {"A": 0, "B": 0, "C": 100}, n=1)
    # before C appears, B is top-1; after, C is.
    assert gates["B"][50] and not gates["A"][50] and not gates["C"][50]
    assert gates["C"][150] and not gates["B"][150]
    assert vis["A"][50] == 2 and vis["A"][150] == 3


def test_a_name_not_yet_seen_is_not_gated_in_even_if_it_would_rank():
    v = vals(A=5.0, C=9.0)
    gates, _ = R.gates_for_session(v, {"A": 0, "C": 100}, n=3)
    assert not gates["C"][50] and gates["C"][100]


def test_ties_are_inside_the_cut_and_fewer_names_than_n_admits_all():
    v = vals(A=5.0, B=5.0, C=5.0, D=1.0)
    gates, _ = R.gates_for_session(v, {s: 0 for s in "ABCD"}, n=1)
    assert gates["A"][10] and gates["B"][10] and gates["C"][10] and not gates["D"][10]
    gates, _ = R.gates_for_session(vals(A=1.0, B=2.0), {"A": 0, "B": 0}, n=3)
    assert gates["A"][10] and gates["B"][10]


def test_no_value_means_no_gate():
    v = vals(A=5.0)
    v["A"][:] = np.nan
    gates, vis = R.gates_for_session(v, {"A": 0}, n=3)
    assert not gates["A"].any() and vis["A"][10] == 0


def test_gate_series_stamps_each_bar_with_its_own_minute():
    g = np.zeros(R.SESSION_MINUTES, dtype=bool)
    g[7] = g[10] = True
    df = bars([5, 7, 10, 400], [(1, 1, 1)] * 4)
    s = R.gate_series(g, df.index)
    assert s.tolist() == [False, True, True, False]
    labels = pd.DatetimeIndex([datetime.combine(DAY, dtime(4, 5), tzinfo=ET),
                               datetime.combine(DAY, dtime(4, 10), tzinfo=ET)])
    assert R.gate_series(g, labels).tolist() == [False, True]


# --- the abstention control and the verdict --------------------------------------

def test_abstention_on_a_losing_book_is_positive_per_symbol_day_and_flat_per_trade():
    base = rows(EARLY, [-10.0] * 50) + rows(EARLY, [-10.0 + 0.5 * k for k in range(-20, 20)])
    a = G.abstention(base, k=30, symdays=10, draws=300)
    assert a["valid"]
    assert a["per_symday"]["p05"] > 0                  # abstaining always helps a losing total
    assert abs(a["per_trade"]["p50"]) < 1.0            # and does nothing per trade, on average
    assert a["per_trade"]["p95"] > a["per_trade"]["p50"]


def test_abstention_is_not_computable_with_nothing_or_everything_removed():
    base = rows(EARLY, [-1.0] * 5)
    assert not G.abstention(base, 0, 1)["valid"]
    assert not G.abstention(base, 5, 1)["valid"]


def test_verdict_item_one_carries_the_margin():
    """+0.03 a trade satisfied H-B1's item 1; here it must not."""
    base, gated = symday_pairs(12, [-10.0, -10.0], [-9.97, -9.97])
    tag, why, n = G.verdict(base, gated, CUT, symdays=24)
    assert tag == "NOTHING" and "1 (" in why


def test_verdict_passes_only_when_the_gate_beats_random_removal():
    # A gate that keeps the good trades: baseline has 2 good and 8 bad per day.
    base, gated = [], []
    for i in range(12):
        for d in (EARLY, LATE):
            base += rows(d, [10.0, 10.0] + [-10.0] * 8, symbol=f"S{i}")
            gated += rows(d, [10.0, 10.0], symbol=f"S{i}")
    tag, why, n = G.verdict(base, gated, CUT, symdays=24)
    assert tag == "PASSES", why
    assert n["d_per_trade"] > n["abst"]["per_trade"]["p95"]
    # The same trade count removed with no selection: fails 1 (margin) and 5.
    base, gated = symday_pairs(12, [-float(k) for k in range(1, 11)], [-5.3, -5.3])
    tag, why, n = G.verdict(base, gated, CUT, symdays=24)
    assert tag == "NOTHING" and "1 (" in why and "5 (" in why


def test_verdict_refuses_on_a_denominator_disagreement():
    base, gated = symday_pairs(12, [-1.0] * 10, [-0.9] * 12)
    assert G.verdict(base, gated, CUT, symdays=24)[0] == "REFUSED"


# --- report blocks ----------------------------------------------------------------

def test_binding_block_flags_a_gate_that_could_never_bind():
    text = "\n".join(G.binding_block("MCL-top3", 0, 100, {1: 60, 2: 40}))
    assert "THE GATE DID NOT RUN" in text
    text = "\n".join(G.binding_block("MCL-top3", 30, 100, {1: 60, 4: 40}))
    assert "30.0%" in text and "DID NOT RUN" not in text


def test_refused_block_splits_losses_avoided_from_winners_lost():
    refused = rows(EARLY, [-10.0, -5.0, 20.0])
    text = "\n".join(G.refused_block("MCL", "MCL-top3", refused))
    assert "(15.00)" in text and "20.00" in text and "refused                3" in text


def test_render_reads_the_registered_pair_and_prints_the_reported_one(tmp_path):
    b, g = symday_pairs(12, [-10.0, -10.0], [5.0, 5.0])
    books = {"MCL": b, "MCL-top3": g, "MCL-top1": g, "MC5": b, "MC5-top3": g, "MC5-top1": g}
    refused = {k: [] for k in ("MCL-top3", "MCL-top1", "MC5-top3", "MC5-top1")}
    binding = {k: (10, 20, {1: 10, 5: 10}) for k in refused}
    text = "\n".join(G.render("T", "docs/x.md", books, R.PAIRED, R.REPORTED, 24, 0, [EARLY, LATE],
                              1.0, 1, refused, binding))
    assert "THE VERDICT: MCL-top3 against MCL" in text
    assert "REPORTED, NOT REGISTERED: MCL-top1 against MCL" in text
    assert "*** DOES NOT MATCH ***" in text
    csv_path = tmp_path / "t.csv"
    G.write_csv(str(csv_path), books)
    G.write_meta(str(csv_path), [EARLY, LATE], 24, CUT, {"N": 3})
    from common.time_of_day import read_csv, read_meta
    assert set(read_csv(csv_path)) == set(books) and read_meta(csv_path)["N"] == 3


# --- run_day against the real engines ----------------------------------------------

def _two_symbol_frame(seed=7, n=330):
    rng = np.random.default_rng(seed)
    idx = []
    for d in (DAY - timedelta(days=1), DAY):
        b = pd.Timestamp(datetime.combine(d, dtime(4, 0), tzinfo=ET))
        idx += [(b + timedelta(minutes=i)).tz_convert("UTC") for i in range(n)]
    frames = []
    for sym, vol in (("AAA", 0.012), ("BBB", 0.004)):
        c = 5 * np.exp(np.cumsum(rng.normal(0.0004, vol, len(idx))))
        o = np.r_[c[0], c[:-1]]
        h = np.maximum(o, c) * (1 + abs(rng.normal(0, vol / 3, len(c))))
        lo = np.minimum(o, c) * (1 - abs(rng.normal(0, vol / 3, len(c))))
        v = rng.lognormal(8, 1.2, len(c)).astype(int)
        frames.append(pd.DataFrame({"symbol": sym, "open": o, "high": h, "low": lo,
                                    "close": c, "volume": v}, index=pd.DatetimeIndex(idx)))
    return pd.concat(frames)


def test_run_day_gates_the_quiet_name_out_at_top1(monkeypatch):
    hit = None
    for seed in range(40):
        df = _two_symbol_frame(seed=seed)
        monkeypatch.setattr("common.dbn_io.read_dbn", lambda p, df=df: df)
        fs = pd.Timestamp(f"{DAY.isoformat()}T04:00:00-05:00").tz_convert("UTC").isoformat()
        uni = [{"symbol": s, "date": DAY.isoformat(), "first_seen": fs} for s in ("AAA", "BBB")]
        day, res, err = R.run_day(([f"{DAY.isoformat()}.dbn"], DAY.isoformat(), uni))
        assert err == "" and res["errors"] == 0 and res["symdays"] == 2
        assert set(res["books"]) == {n for n, _, _ in R.BOOKS}
        if any(r["symbol"] == "BBB" for r in res["books"]["MCL"]):
            hit = res
            break
    assert hit, "no seed gave the quiet name an MCL trade"
    # With two names visible, top-3 cannot bind; top-1 must bind on every entry.
    assert hit["binding"]["MCL-top3"][0] == 0
    assert hit["binding"]["MCL-top3"][1] == len(hit["books"]["MCL"])
    assert hit["binding"]["MCL-top1"][0] == hit["binding"]["MCL-top1"][1]
    assert hit["books"]["MCL-top3"] == hit["books"]["MCL"]
    # The volatile name out-ranges the quiet one: BBB's entries are refused at top-1.
    assert all(r["symbol"] == "BBB" for r in hit["refused"]["MCL-top1"])
    assert all(r["symbol"] != "BBB" for r in hit["books"]["MCL-top1"])


def test_run_day_with_one_name_visible_cannot_bind_even_at_top1(monkeypatch):
    """One name is rank 1 by definition. 'Could bind' means MORE names than
    the cut were visible, so with a single name top-1 could never refuse."""
    df = _two_symbol_frame(seed=3)
    df = df[df["symbol"] == "AAA"]
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p, df=df: df)
    fs = pd.Timestamp(f"{DAY.isoformat()}T04:00:00-05:00").tz_convert("UTC").isoformat()
    uni = [{"symbol": "AAA", "date": DAY.isoformat(), "first_seen": fs}]
    for seed in range(40):
        df = _two_symbol_frame(seed=seed)
        df = df[df["symbol"] == "AAA"]
        monkeypatch.setattr("common.dbn_io.read_dbn", lambda p, df=df: df)
        day, res, err = R.run_day(([f"{DAY.isoformat()}.dbn"], DAY.isoformat(), uni))
        if res["books"]["MCL"]:
            break
    assert res["books"]["MCL"]
    assert res["binding"]["MCL-top1"][0] == 0
    assert res["binding"]["MCL-top1"][1] == len(res["books"]["MCL"])
    assert res["refused"]["MCL-top1"] == [] and res["books"]["MCL-top1"] == res["books"]["MCL"]
