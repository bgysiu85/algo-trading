#!/usr/bin/env python3
"""W03-0005 Part A: per-leg costs and the leg-by-leg re-pricing.

docs/research/REGISTERED_exec_cost.md. The failures that would break this
silently, each pinned below:

  * a sign flipped on one leg (every cost priced backwards, still plausible);
  * the trailing exit priced ON TOP of the engine's gap-through fill instead of
    from the level (the gap counted twice -- the whole reason for the gap-off run);
  * a gap-off run that is not the same trade list (the levels then belong to
    other trades);
  * a null re-pricing that does not reproduce the engine;
  * decision words that choose themselves.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from common import exec_cost_legs as X
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


# --- the live legs ------------------------------------------------------------

def fill(action="BUY", reason="", kind="signal_close", ref=5.00, px=5.02, strat="mcl",
         status="FILLED", qty=100, bid=5.00, ask=5.02, logged=None):
    if logged is None:
        cost = (px - ref) if action == "BUY" else (ref - px)
        logged = -cost                   # trader.py logs the NEGATED cost
    return {"ts_et": "2026-09-10 05:00:00", "strategy": strat, "symbol": "ABC",
            "action": action, "reason": reason, "ref_close": ref, "ref_kind": kind,
            "bid": bid, "ask": ask, "fill_price": px, "filled_qty": qty, "qty": qty,
            "status": status, "slippage_vs_ref": logged}


def test_signs_are_adverse_positive_on_every_leg():
    buy = X.leg_row(fill("BUY", ref=5.00, px=5.02), "2026-09-10")
    assert buy["leg"] == "ENTRY" and buy["cost_ps"] == pytest.approx(0.02)
    assert buy["cost_bps"] == pytest.approx(40.0)
    trail = X.leg_row(fill("SELL", "trailing_stop", "trail_level", ref=6.00, px=5.94), "2026-09-10")
    assert trail["leg"] == "TRAIL" and trail["cost_ps"] == pytest.approx(0.06)
    assert trail["cost_bps"] == pytest.approx(100.0)
    wc = X.leg_row(fill("SELL", "window_close", "quote", ref=4.00, px=4.02), "2026-09-10")
    assert wc["leg"] == "WCLOSE" and wc["cost_ps"] == pytest.approx(-0.02)   # favourable


def test_rows_without_a_decision_price_or_a_fill_are_not_legs():
    s = "2026-09-10"
    assert X.leg_row(fill(status="NO_FILL_CANCELLED"), s) is None
    assert X.leg_row(fill(status="SKIPPED_DRIFT"), s) is None
    for kind in ("late_fill", "ib_position", "ib_execution", ""):
        assert X.leg_row(fill("SELL", "trailing_stop", kind), s) is None
    assert X.leg_row(fill(strat="h0"), s) is None
    assert X.leg_row(fill(px=0), s) is None
    # A pre-2026-09-09 trailing sell measured against the ENTRY price has no
    # ref_kind and must never reach the TRAIL leg.
    assert X.leg_row(fill("SELL", "trailing_stop", ""), s) is None


def test_blank_strategy_is_mcl_and_other_exits_are_kept_apart():
    r = X.leg_row(fill(strat=""), "2026-09-10")
    assert r["strategy"] == "mcl"
    o = X.leg_row(fill("SELL", "gradient_reversal", "bar_close", ref=5, px=4.99), "2026-09-10")
    assert o["leg"] == "OTHER"


def test_entry_split_adds_up_to_the_entry_cost():
    r = X.leg_row(fill("BUY", ref=5.00, px=5.06, bid=5.02, ask=5.06), "2026-09-10")
    assert r["spread_bps"] + r["drift_bps"] == pytest.approx(r["cost_bps"])
    assert r["drift_bps"] == pytest.approx((5.04 - 5.00) / 5.00 * 1e4)


def test_c3_catches_a_flipped_sign():
    rows = [X.leg_row(fill(), "2026-09-10") for _ in range(10)]
    assert X.check_c3(rows)["ok"]
    rows = [X.leg_row(fill(logged=+0.02), "2026-09-10") for _ in range(10)]
    got = X.check_c3(rows)
    assert not got["ok"] and len(got["bad"]) == 10


def test_session_of_reads_rolled_aside_logs_and_load_honours_the_window(tmp_path):
    from pathlib import Path
    assert X.session_of(Path("mcl_fills_20260910_pre061502.csv")) == "2026-09-10"
    assert X.session_of(Path("other.csv")) is None
    cols = list(fill().keys())
    for day in ("20260908", "20260910", "20260926"):
        p = tmp_path / f"mcl_fills_{day}.csv"
        p.write_text(",".join(cols) + "\n" + ",".join(str(v) for v in fill().values()) + "\n",
                     encoding="utf-8")
    rows = X.load_legs(tmp_path)
    assert {r["session"] for r in rows} == {"2026-09-10"}


def test_the_minimum_sample_is_applied_as_registered():
    means = {"ENTRY": (2.0, 100), "TRAIL": (60.0, 100), "WCLOSE": (90.0, 7)}
    e, notes = X.resolve_e(means)
    assert e["WCLOSE"] == 60.0 and "NOT SEPARATELY MEASURABLE" in notes[0]
    e, _ = X.resolve_e({**means, "WCLOSE": (90.0, 15)})
    assert e["WCLOSE"] == 90.0
    with pytest.raises(SystemExit):
        X.resolve_e({**means, "TRAIL": (60.0, 14)})
    # Per-strategy sensitivity falls back to POOLED, not to TRAIL.
    e, _ = X.resolve_e({**means, "ENTRY": (9.0, 3)}, pooled={"ENTRY": 1.0, "TRAIL": 2.0, "WCLOSE": 3.0})
    assert e["ENTRY"] == 1.0 and e["WCLOSE"] == 3.0


def test_bootstrap_is_seeded_and_resamples_sessions():
    rows = []
    for k, s in enumerate(("2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15")):
        rows += [{"session": s, "leg": "ENTRY", "cost_bps": float(k)}] * 3
        rows += [{"session": s, "leg": "TRAIL", "cost_bps": 50.0 + 10 * k}] * 5
    a = X.bootstrap_e(rows, 200, 7)
    b = X.bootstrap_e(rows, 200, 7)
    assert np.array_equal(a["TRAIL"], b["TRAIL"])
    assert a["TRAIL"].min() >= 50 and a["TRAIL"].max() <= 80 and a["TRAIL"].std() > 0
    # No WCLOSE at all: every draw prices it at that draw's TRAIL.
    assert np.array_equal(a["WCLOSE"], a["TRAIL"]) and np.isnan(a["WCLOSE_raw"]).all()


def test_halves_flags_a_trail_that_more_than_doubles():
    rows = ([{"session": "2026-09-10", "leg": "TRAIL", "cost_bps": 30.0}]
            + [{"session": "2026-09-22", "leg": "TRAIL", "cost_bps": 90.0}])
    assert X.halves(rows)[3] == "UNSTABLE"
    rows[1]["cost_bps"] = 50.0
    assert X.halves(rows)[3] == "stable"


# --- the books ------------------------------------------------------------------

def brow(reason="trailing_stop", entry=5.01, exit_=4.90, nogap=4.95, qty=100, comm=1.0,
         sym="ABC", day="2026-09-10", k=1):
    gross = round((exit_ - entry) * qty, 2)
    return {"symbol": sym, "date": day, "ordinal": k, "entry_et": "05:00", "exit_et": "05:10",
            "entry_px": entry, "exit_px": exit_, "exit_px_nogap": nogap, "reason": reason,
            "reason_nogap": reason, "entry_et_nogap": "05:00", "exit_et_nogap": "05:10",
            "qty": qty, "gross": gross, "commission": comm, "net": round(gross - comm, 2)}


def test_r0_reproduces_the_engine_exactly():
    bk = X.Book([brow(), brow("window_close", exit_=5.20, nogap=5.20),
                 brow("gradient_reversal", exit_=5.10, nogap=5.10)])
    n0, _ = bk.repriced(0, 0, 0, "R0")
    assert np.allclose(n0, bk.net, atol=1e-9)


def test_the_trailing_exit_is_priced_from_the_level_not_on_top_of_the_gap():
    """THE DOUBLE COUNT. The engine sold a gapped stop at open - tick = 4.90;
    the level was 4.96 (gap-off fill 4.95 + tick). The live figure is
    fill-vs-level, so R1 must sell at 4.96 x (1 - E), NOT at 4.90 x (1 - E)."""
    bk = X.Book([brow(exit_=4.90, nogap=4.95)])
    assert bk.level[0] == pytest.approx(4.96)
    _, nx = bk.prices(0.0, 100.0, 0.0, "R1")
    assert nx[0] == pytest.approx(4.96 * 0.99)
    # R2 takes the WORSE of engine and R1 on each trailing exit.
    _, nx2 = bk.prices(0.0, 100.0, 0.0, "R2")
    assert nx2[0] == pytest.approx(min(4.90, 4.96 * 0.99))
    _, nx2 = bk.prices(0.0, 10.0, 0.0, "R2")
    assert nx2[0] == pytest.approx(4.90)


def test_entry_and_window_close_are_priced_from_their_own_references():
    bk = X.Book([brow("window_close", entry=5.01, exit_=6.00, nogap=6.00)])
    ne, nx = bk.prices(20.0, 999.0, 50.0, "R1")          # TRAIL must not touch a wc trade
    assert ne[0] == pytest.approx(5.00 * 1.002)
    assert nx[0] == pytest.approx(6.01 * 0.995)
    net, gross = bk.repriced(20.0, 999.0, 50.0, "R1")
    assert gross[0] == pytest.approx((6.01 * 0.995 - 5.00 * 1.002) * 100)
    assert net[0] == pytest.approx(gross[0] - 1.0)       # commission unchanged


def test_other_exits_keep_their_engine_price():
    bk = X.Book([brow("gradient_reversal", exit_=5.10, nogap=5.10)])
    _, nx = bk.prices(0.0, 500.0, 500.0, "R1")
    assert nx[0] == pytest.approx(5.10)


def test_flat_equivalent_is_the_flat_charge_that_gives_the_same_total():
    bk = X.Book([brow(), brow(k=2)])
    new = bk.net - 7.5
    assert bk.fe(new) == pytest.approx(7.5)


def test_leg_costs_add_up_to_the_net_difference():
    bk = X.Book([brow(), brow("window_close", exit_=5.2, nogap=5.2, k=2)])
    e = (15.0, 80.0, 120.0)
    r1, _ = bk.repriced(*e, "R1")
    diff = bk.engine_leg_costs()
    new = bk.leg_costs(*e, "R1")
    # Everything the re-pricing changes is a leg cost, so the totals agree.
    assert (bk.net.sum() - r1.sum()) == pytest.approx(sum(new.values()) - sum(diff.values()))


def test_c2_refuses_a_different_trade_list_and_a_better_published_fill():
    ok = X.check_c2([brow(), brow("window_close", exit_=5.2, nogap=5.2)])
    assert ok["ok"] and ok["trail"] == 1 and ok["no_gap"] == 0
    moved = brow()
    moved["exit_et_nogap"] = "05:11"
    assert not X.check_c2([moved])["ok"]
    better = brow(exit_=4.97, nogap=4.95)                # published better than gap-off: impossible
    assert not X.check_c2([better])["ok"]
    wc_moved = brow("window_close", exit_=5.2, nogap=5.1)  # only a TRAIL fill may differ
    assert not X.check_c2([wc_moved])["ok"]
    unp = brow()
    unp["unpaired"] = True
    assert not X.check_c2([unp])["ok"]


def test_run_universe_runs_both_fill_models_and_pairs_them():
    seen = []

    def T(entry, exit_, reason="trailing_stop"):
        return SimpleNamespace(entry_time="2026-09-10 09:00:00+00:00",
                               exit_time="2026-09-10 09:10:00+00:00", entry_price=entry,
                               exit_price=exit_, reason=reason, bars_held=10, net=-5.0,
                               gross=-4.0, commission=1.0, qty=100)

    class Fake:
        @staticmethod
        def backtest_session(df, d, tz, **kw):
            seen.append(kw["gap_fills"])
            return [T(5.01, 4.90 if kw["gap_fills"] else 4.95)]

    idx = pd.DatetimeIndex([datetime(2026, 9, 10, 5, 0, tzinfo=ET)])
    frame = pd.DataFrame({"symbol": ["ABC"], "close": [5.0]}, index=idx)
    uni = [{"symbol": "ABC", "first_seen": "2026-09-10T08:30:00+00:00"}]
    res = X.run_universe(frame, "2026-09-10", uni, {"mcl": (Fake, {}), "mc5": (Fake, {"x": 1})})
    assert seen == [True, False, True, False]
    r = res["books"]["mcl"][0]
    assert r["exit_px"] == 4.90 and r["exit_px_nogap"] == 4.95
    assert X.check_c2(res["books"]["mcl"])["ok"]


def test_real_mcl_engine_the_gap_off_fill_is_level_minus_a_tick():
    """Against the REAL engine: the one assumption the whole re-pricing rests
    on. Entry 5.01 (close 5.00 + tick), peak 6.00, trail 5.70; the exit bar
    OPENS at 5.50, below the level."""
    day = date(2026, 9, 11)
    bars = [(5.00, 5.00, 5.00, 5.00), (5.50, 6.00, 5.50, 5.90),
            (5.90, 5.95, 5.80, 5.85), (5.50, 5.55, 5.40, 5.45)]
    t0 = datetime.combine(day, dtime(7, 0), tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(bars))])
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 10_000
    take = pd.Series(False, index=idx)
    take.iloc[0] = True

    def run(gap):
        return MCL.backtest_session(df, day, ET, entry_bars=take, entry_shares=100,
                                    use_apex=False, gap_fills=gap)

    on, off = run(True), run(False)
    assert len(on) == len(off) == 1
    level = MCL.stop_level(6.00, MCL.TRAIL_PCT)
    assert off[0].exit_price == pytest.approx(round(level - 0.01, 4))
    assert on[0].exit_price == pytest.approx(5.50 - 0.01)
    assert (on[0].entry_time, on[0].exit_time) == (off[0].entry_time, off[0].exit_time)
    bk = X.Book([dict(brow(entry=on[0].entry_price, exit_=on[0].exit_price,
                           nogap=off[0].exit_price, comm=on[0].commission),
                      gross=on[0].gross)])
    assert bk.level[0] == pytest.approx(level, abs=1e-4)
    assert bk.signal_close[0] == pytest.approx(5.00)


# --- the words ------------------------------------------------------------------

def test_fe_words_are_the_registered_ones():
    assert X.fe_word(7.0, 10.0) == "$8.92 STANDS"
    assert X.fe_word(9.0, 12.0) == "$8.92 UNDERSTATES"
    assert X.fe_word(3.0, 4.0).startswith("$8.92 OVERSTATES  (and clears $4.26)")
    assert X.fe_word(5.0, 8.0).startswith("$8.92 OVERSTATES  (but not below")
    assert X.fe_word(float("nan"), 1.0) == "n/a"


def test_wc_words_are_the_registered_ones():
    assert X.wc_word(80, 120, 60, True) == "window_close is the dearer exit"
    assert X.wc_word(10, 40, 60, True) == "window_close is the cheaper exit"
    assert X.wc_word(40, 80, 60, True) == "no measurable difference"
    assert X.wc_word(80, 120, 60, False) == "not measurable"


def test_the_registered_constants_have_not_moved():
    assert (X.FIRST, X.LAST, X.SEED, X.NBOOT, X.MIN_N) == ("2026-09-09", "2026-09-25", 20260927, 2000, 15)
    assert X.PUBLISHED == {"mcl": (3_908, -35_063.12), "mc5": (6_462, -55_364.07)}


# --- the report renders end to end ------------------------------------------------

def test_render_produces_every_section_and_the_words(tmp_path):
    rng = np.random.default_rng(1)
    legs = []
    for k, s in enumerate(["2026-09-%02d" % d for d in (9, 10, 11, 14, 15, 16, 17, 18)]):
        for strat in ("mcl", "mc5"):
            for _ in range(4):
                legs.append(X.leg_row(fill(ref=5.0, px=5.0 + rng.normal(0, 0.01), strat=strat), s))
                legs.append(X.leg_row(fill("SELL", "trailing_stop", "trail_level", ref=6.0,
                                           px=6.0 - abs(rng.normal(0.04, 0.02)), strat=strat), s))
            legs.append(X.leg_row(fill("SELL", "window_close", "quote", ref=7.0,
                                       px=7.0 - abs(rng.normal(0.05, 0.02)), strat=strat), s))
    e_by = {"pooled": X.means_by_leg(legs), **{s: X.means_by_leg(legs, s) for s in X.STRATEGIES}}
    e, notes = X.resolve_e(e_by["pooled"])
    boot = X.bootstrap_e(legs, 100, X.SEED)
    rows = [brow(k=i, entry=5.01 + i * 0.01) for i in range(30)] + \
           [brow("window_close", exit_=5.6, nogap=5.6, k=40 + i) for i in range(6)]
    books = {s: X.Book(rows) for s in X.STRATEGIES}
    c1 = {"ok": True, "skipped": True, **{s: {"n": 36, "net": -1.0, "ok": True} for s in X.STRATEGIES}}
    c2 = X.check_c2(rows)
    c3 = X.check_c3(legs)
    meta = {"first": X.FIRST, "last": X.LAST, "sessions": 8, "c4": {"mcl": True, "mc5": True},
            "not_registered": True}
    text, words = X.render(legs, c3, books, c1, c2, e, notes, e_by, boot, meta)
    for part in ("IN PLAIN TERMS", "1. THE LIVE LEGS", "2. THE BOOKS RE-PRICED", "3. CONTROLS",
                 "4. DECISION WORDS", "NOT THE REGISTERED SAMPLE", "window_close trades"):
        assert part in text, part
    assert set(words) == {"mcl", "mc5", "window_close"}
    assert "STOPPED" not in text


def test_main_wires_the_controls_and_writes_its_files(tmp_path, monkeypatch):
    """main() end to end with the session runner faked: C1 must refuse a book
    that is not the published one, and the report and both CSVs must land
    where they were told to (never in var/)."""
    fills = tmp_path / "fills"
    fills.mkdir()
    cols = list(fill().keys())
    lines = [",".join(cols)]
    for k in range(20):
        lines.append(",".join(str(v) for v in fill(px=5.0 + 0.001 * k).values()))
        lines.append(",".join(str(v) for v in fill("SELL", "trailing_stop", "trail_level",
                                                    ref=6.0, px=5.95).values()))
    for day in ("20260910", "20260911"):
        (fills / f"mcl_fills_{day}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows = [brow(k=i) for i in range(5)]
    monkeypatch.setattr(X.G, "build_tasks", lambda *a, **k: ([], {}))
    monkeypatch.setattr(X.G, "run_sessions", lambda *a, **k: (
        {"2026-09-10": {"books": {"mcl": list(rows), "mc5": list(rows)}, "symdays": 1,
                        "errors": 0, "error_days": [], "unpaired": []}}, 0.1))
    out, cf, ct = tmp_path / "r.txt", tmp_path / "f.csv", tmp_path / "t.csv"
    rc = X.main(["--fills", str(fills), "--archive", str(tmp_path), "--nboot", "50",
                 "--out", str(out), "--csv-fills", str(cf), "--csv-trades", str(ct)])
    assert rc == 2                                   # C1: 5 trades is not the published book
    text = out.read_text(encoding="utf-8")
    assert "STOPPED" in text and "MISMATCH" in text
    assert cf.exists() and ct.exists()
    assert "net_r1" in ct.read_text(encoding="utf-8").splitlines()[0]
