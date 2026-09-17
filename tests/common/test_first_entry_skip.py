#!/usr/bin/env python3
"""The H-B1 report reads the registration and nothing else."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from common import first_entry_skip as S
from common import time_of_day as T

F = S.MEASURED_FRICTION
CUT = "2026-02-01"
EARLY, LATE = "2026-01-10", "2026-03-10"


def rows(date, nets, symbol="X", start="05:00", ordinal_from=1):
    """Trades on one symbol-day, entry times one minute apart from `start`,
    nets given NET OF the measured friction."""
    h, m = map(int, start.split(":"))
    out = []
    for k, n in enumerate(nets):
        mm = h * 60 + m + k
        out.append({"symbol": symbol, "date": date, "ordinal": ordinal_from + k,
                    "net": n + F, "entry_et": f"{mm // 60:02d}:{mm % 60:02d}",
                    "entry_px": 5.0, "exit_et": "09:00", "exit_px": 5.0,
                    "reason": "trailing_stop", "bars_held": 3})
    return out


def symday_pairs(n_syms: int, per_sym_base, per_sym_skip):
    """n symbols, each traded on EARLY and LATE, with the given nets."""
    base, skip = [], []
    for i in range(n_syms):
        for d in (EARLY, LATE):
            base += rows(d, per_sym_base, symbol=f"S{i}")
            skip += rows(d, per_sym_skip, symbol=f"S{i}", start="05:30")
    return base, skip


# --- arithmetic --------------------------------------------------------------

def test_halves_cut_on_one_date():
    a, b = S.halves(rows(EARLY, [1]) + rows(LATE, [1, 1]), CUT)
    assert len(a) == 1 and len(b) == 2


def test_delta_per_symbol_day_covers_the_union_of_days():
    base = rows(EARLY, [10], symbol="A") + rows(EARLY, [-5], symbol="B")
    skip = rows(EARLY, [2], symbol="A") + rows(EARLY, [7], symbol="C")
    d = S.deltas_by_symbol_day(base, skip, F)
    assert d == {("A", EARLY): pytest.approx(-8), ("B", EARLY): pytest.approx(5),
                 ("C", EARLY): pytest.approx(7)}


def test_drop_top_delta_drops_the_days_that_helped_most():
    d = {("A", EARLY): 100.0, ("B", EARLY): 50.0, ("C", EARLY): 20.0, ("D", EARLY): -1.0}
    assert S.drop_top_delta(d) == pytest.approx(-1.0)


def test_per_symbol_deltas_are_lists_not_sums():
    d = {("A", EARLY): 1.0, ("A", LATE): 2.0, ("B", EARLY): -1.0}
    assert S.delta_by_symbol(d) == {"A": [1.0, 2.0], "B": [-1.0]} or \
        S.delta_by_symbol(d) == {"A": [2.0, 1.0], "B": [-1.0]}


def test_accounting_removes_exactly_the_first_trade_of_each_symbol_day():
    base = rows(EARLY, [-10, 5, 5], symbol="A") + rows(EARLY, [3], symbol="B")
    kept, removed = S.accounting(base)
    assert [r["net"] - F for r in removed] == [-10, 3]
    assert [r["net"] - F for r in kept] == [5, 5]


def test_top_absent_is_keyed_on_symbol_day_and_entry_time():
    base = rows(EARLY, [50, 1], symbol="A")             # 05:00 (50), 05:01 (1)
    skip = rows(EARLY, [1], symbol="A", start="05:01")   # the 05:01 trade survives
    gone, gone_rows = S.top_absent(base, skip, F, n=1)
    assert gone == 1 and gone_rows[0]["entry_et"] == "05:00"
    assert S.top_absent(base, skip, F, n=2)[0] == 1


def test_new_entries_counts_skip_entries_the_baseline_lacks():
    base = rows(EARLY, [1, 1], symbol="A")               # 05:00, 05:01
    skip = rows(EARLY, [1], symbol="A", start="05:01") + rows(EARLY, [1], symbol="A", start="05:07")
    assert S.new_entries(base, skip) == 1


# --- the verdict, registered §3 -----------------------------------------------

def test_passes_needs_all_four():
    base, skip = symday_pairs(12, [-10, -10], [5, 5])
    tag, why, n = S.verdict(base, skip, CUT, symdays=24)
    assert tag == "PASSES", why
    assert n["d_per_trade"] > 0 and n["d_per_symday"] > 0 and n["boot_p"] >= S.BOOT_MIN_P


def test_a_sign_disagreement_between_denominators_is_a_refusal():
    """Skip trades less and better per trade, but its total is worse: per
    trade improves, per symbol-day does not. Neither a pass nor a fail."""
    base, skip = symday_pairs(12, [-1] * 10, [-0.9] * 12)   # -1.0/t, -10/day vs -0.9/t, -10.8/day
    tag, why, _ = S.verdict(base, skip, CUT, symdays=24)
    assert tag == "REFUSED" and "disagree" in why
    # Both worse is a plain NOTHING on item 1, not a refusal.
    base, skip = symday_pairs(12, [-1] * 10, [-3] * 4)
    tag, why, _ = S.verdict(base, skip, CUT, symdays=24)
    assert tag == "NOTHING" and "1 (" in why


def test_nothing_names_the_failed_reading():
    # Improves everywhere except concentrated in three symbol-days -> item 3 delta fails.
    base, skip = symday_pairs(12, [-1, -1], [-1, -1])
    skip = [dict(r) for r in skip]
    for k, r in enumerate(skip[:3]):
        r["net"] += 500.0                                   # three huge symbol-days carry it
    tag, why, n = S.verdict(base, skip, CUT, symdays=24)
    assert tag == "NOTHING" and "3 (" in why
    assert n["drop_delta"] <= 0


def test_a_half_that_gets_worse_fails_item_two_alone():
    """Better in total, better per trade, spread across every symbol, and
    worse in the late half: items 1, 3 and 4 hold and item 2 does not."""
    base, skip = [], []
    for i in range(12):
        base += rows(EARLY, [-10, -10], symbol=f"S{i}") + rows(LATE, [-10, -10], symbol=f"S{i}")
        skip += rows(EARLY, [5, 5], symbol=f"S{i}") + rows(LATE, [-11, -11], symbol=f"S{i}")
    tag, why, n = S.verdict(base, skip, CUT, symdays=24)
    assert tag == "NOTHING" and why == "fails 2 (both halves, both denominators)"
    assert n["late"][0] < 0 and n["boot_p"] >= S.BOOT_MIN_P


def test_drop_top_on_the_delta_can_fail_while_the_level_passes():
    """Three symbol-days carry the whole improvement. The level survives its
    own drop-top-3 (the rest of the skip book is only slightly worse than the
    baseline's), the delta does not -- and the reading is on both."""
    base, skip = symday_pairs(12, [-1, -1], [-1.05, -1.05])
    skip = [dict(r) for r in skip]
    boosted = {("S0", EARLY), ("S0", LATE), ("S1", EARLY)}
    for r in skip:
        if (r["symbol"], r["date"]) in boosted:
            r["net"] += 26.05                                 # +25 net of friction
    tag, why, n = S.verdict(base, skip, CUT, symdays=24)
    assert n["drop_level"][0] > n["drop_level"][1]
    assert n["drop_delta"] < 0
    assert tag == "NOTHING" and "3 (" in why


def test_an_empty_half_is_nothing():
    base = rows(LATE, [1] * 5)
    assert S.verdict(base, rows(LATE, [2] * 5), CUT, symdays=1)[0] == "NOTHING"


def test_bootstrap_reads_totals_at_the_registered_bar():
    """A rule whose whole gain sits in one symbol among many cannot clear 0.95
    on a symbol-cluster bootstrap, whatever the total says."""
    base, skip = symday_pairs(30, [-1, -1], [-1, -1])
    skip = [dict(r) for r in skip]
    skip[0]["net"] += 2000.0
    tag, why, n = S.verdict(base, skip, CUT, symdays=60)
    assert n["boot_p"] < S.BOOT_MIN_P and "4 (" in why


# --- the report ---------------------------------------------------------------

def books_for_render():
    b, s = symday_pairs(12, [-10, -10], [5, 5])
    return {"MCL": b, "MCL-skip1": s, "MC5": b, "MC5-skip1": s}


def test_render_carries_the_registration_the_verdicts_and_the_accounting_form():
    books = books_for_render()
    text = "\n".join(S.render(books, 24, 0, [EARLY, LATE], 1.0, 1))
    assert S.REGISTERED in text
    assert "THE VERDICT: MCL-skip1 against MCL" in text
    assert "THE VERDICT: MC5-skip1 against MC5" in text
    assert "NOT READ" in text and "losses avoided" in text
    assert "*** DOES NOT MATCH ***" in text          # 48 trades is not 3,955
    assert "cascade:" in text


def test_render_flags_a_cascade_of_zero_as_a_defect():
    b, _ = symday_pairs(3, [-10, -10], [5, 5])
    books = {"MCL": b, "MCL-skip1": list(b), "MC5": b, "MC5-skip1": list(b)}
    text = "\n".join(S.render(books, 6, 0, [EARLY, LATE], 1.0, 1))
    assert "SIGNAL-ORDINAL FORM DID NOT RUN" in text


def test_csv_and_meta_round_trip_and_time_of_day_reads_them(tmp_path):
    books = books_for_render()
    csv_path = tmp_path / "t.csv"
    S.write_csv(str(csv_path), books)
    a = SimpleNamespace(pairs="p.json", dataset="XNAS.BASIC")
    S.write_meta(str(csv_path), [EARLY, LATE], 24, CUT, a)
    meta = T.read_meta(csv_path)
    got = T.read_csv(csv_path)
    assert meta["cut"] == CUT and meta["timestamps"] == "ET"
    assert set(got) == {"MCL", "MCL-skip1", "MC5", "MC5-skip1"}
    assert got["MCL"][0]["entry_et"] == "05:00" and got["MCL"][0]["net"] == pytest.approx(-10 + F)


def test_time_of_day_refuses_a_csv_whose_timestamps_are_not_et(tmp_path):
    csv_path = tmp_path / "t.csv"
    csv_path.write_text("book,symbol,date,net,entry_et\n", encoding="utf-8")
    csv_path.with_name("t_meta.json").write_text(json.dumps({"timestamps": "UTC"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        T.read_meta(csv_path)


# --- time of day ---------------------------------------------------------------

def test_blocks_cover_the_session_half_open():
    b = T.blocks()
    assert b[0] == ("04:00", "04:30") and b[-1] == ("09:00", "09:30") and len(b) == 11
    r = {"entry_et": "07:59"}
    assert T.in_block(r, ("07:30", "08:00")) and not T.in_block(r, ("08:00", "08:30"))


def test_session_denominator_counts_sessions_not_trades():
    rs = rows(EARLY, [10, -3]) + rows(LATE, [-2])
    s = T.sessions(rs, F)
    assert s["n"] == 2 and s["positive"] == 0.5 and s["median"] == pytest.approx(2.5)


def test_named_reading_needs_all_four_checks():
    good = rows(EARLY, [10] * 5, start="07:45") + rows(LATE, [10] * 5, start="07:45")
    assert T.named_reading(good, CUT)[0] is True
    # one big trade carries it: drop-top-3 fails
    thin = rows(EARLY, [100, -1, -1, -1], start="07:45") + rows(LATE, [1], start="07:45")
    ok, lines = T.named_reading(thin, CUT)
    assert ok is False and any("FAILS" in ln and "drop-top" in ln for ln in lines)


def test_named_reading_fails_on_the_session_median_alone():
    """Two sessions carry the cell: positive at every friction, in both
    halves and after drop-top-3 (the winners are ten trades each), and the
    typical session still loses. Sessions, not trades, is the check that
    decided the stale run."""
    rs = []
    for k in range(1, 8):
        for month in ("01", "03"):
            d = f"2026-{month}-{k:02d}"
            rs += rows(d, [10] * 10 if k == 1 else [-1], start="07:45")
    ok, lines = T.named_reading(rs, CUT)
    assert ok is False
    assert [ln for ln in lines if "FAILS" in ln] == ["    FAILS  session median above zero at $4.26"]


def test_time_of_day_render_names_the_cell_and_closes_or_registers():
    meta = {"cut": CUT, "sessions": [EARLY, LATE], "symbol_days": 4, "timestamps": "ET"}
    mcl = rows(EARLY, [-5] * 4, start="07:45") + rows(LATE, [-5] * 4, start="07:45")
    text = "\n".join(T.render({"MCL": mcl, "MC5": []}, meta))
    assert "07:45-08:00" in text and "QUESTION CLOSES" in text
    mcl = rows(EARLY, [5] * 4, start="07:45") + rows(LATE, [5] * 4, start="07:45")
    text = "\n".join(T.render({"MCL": mcl, "MC5": []}, meta))
    assert "REGISTRABLE" in text and "Not a result" in text


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


def test_run_day_returns_four_books_and_the_skip_book_drops_the_first_entry(monkeypatch):
    """On a random tape the first MCL trade of the skipped book must be a
    later entry than the baseline's first, and every book comes from one
    pass over one symbol-day."""
    import pandas as pd
    hit = None
    for seed in range(60):
        df, D = _frame(seed=seed)
        monkeypatch.setattr("common.dbn_io.read_dbn", lambda p, df=df: df)
        fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert("UTC").isoformat()
        day, res, err = S.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                                   [{"symbol": "AAA", "date": D.isoformat(), "first_seen": fs}]))
        assert err == "" and res["errors"] == 0 and res["symdays"] == 1
        assert set(res["books"]) == {n for n, _, _ in S.BOOKS}
        if len(res["books"]["MCL"]) >= 2:
            hit = res
            break
    assert hit, "no seed produced two MCL trades"
    base, skip = hit["books"]["MCL"], hit["books"]["MCL-skip1"]
    assert base[0]["ordinal"] == 1 and [r["ordinal"] for r in base] == list(range(1, len(base) + 1))
    assert skip[0]["entry_et"] > base[0]["entry_et"]
    assert all(r["symbol"] == "AAA" and r["date"] == D.isoformat() for r in base + skip)


def test_main_writes_report_csv_and_meta_from_one_pass(monkeypatch, tmp_path):
    """The aggregation, the cut, the CSV and the meta file, without an
    archive: `run_day` is replaced by one that returns hand-built books."""
    from types import SimpleNamespace as NS
    books = books_for_render()

    def fake_run_day(args):
        paths, day, universe = args
        sub = {n: [r for r in rows if r["date"] == day] for n, rows in books.items()}
        return day, {"books": sub, "symdays": 12, "errors": 0, "error_days": []}, ""

    monkeypatch.setattr(S, "run_day", fake_run_day)
    monkeypatch.setattr("common.pit_h0.load_pit", lambda p: {EARLY: [{}], LATE: [{}]})
    monkeypatch.setattr("common.databento_fetch.default_archive", lambda: tmp_path)
    monkeypatch.setattr("common.screen_sim.window_slices",
                        lambda archive, ds: [tmp_path / f"{EARLY}_0400_0930.dbn.zst",
                                             tmp_path / f"{LATE}_0400_0930.dbn.zst"])
    out, csv_path = tmp_path / "r.txt", tmp_path / "t.csv"
    assert S.main(["--jobs", "1", "--out", str(out), "--csv", str(csv_path)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "H-B1: SKIP THE FIRST ENTRY" in text and f"halves cut at {LATE}" in text
    meta = json.loads(csv_path.with_name("t_meta.json").read_text(encoding="utf-8"))
    assert meta["sessions"] == [EARLY, LATE] and meta["symbol_days"] == 24 and meta["cut"] == LATE
    got = T.read_csv(csv_path)
    assert sum(len(v) for v in got.values()) == sum(len(v) for v in books.values())
    tod = tmp_path / "tod.txt"
    assert T.main(["--csv", str(csv_path), "--out", str(tod)]) == 0
    assert "THE NAMED CELL" in tod.read_text(encoding="utf-8")
