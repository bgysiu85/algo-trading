"""W15-0049: the TL-v2 backtest layer (C3, the 27-cell grid, the sec 3/4 report, the runner).
Synthetic markets only -- no archive is read. Each test breaks when the rule it names breaks."""
from __future__ import annotations

import re
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from strategy.tl_v0 import bars as B
from strategy.tl_v0.report import Book, Criterion
from strategy.tl_v0.spec import EQUITY, LEVELS, MARKETS, PIVOT_SIZES
from strategy.tl_v1.signals import MarketCtx
from strategy.tl_v2 import controls as K
from strategy.tl_v2 import engine as E
from strategy.tl_v2 import report as Rp
from strategy.tl_v2 import run as RUN
from strategy.tl_v2.signals import retest_signals
from tests.strategy.tl_v0.synth import ROOT, contracts_and_rows

SEEDS = {"CL": 3, "GC": 11, "6E": 5}
PKG = Path(__file__).resolve().parents[3] / "strategy" / "tl_v2"


def _loader(name):
    rows, con, _ = contracts_and_rows(n=1400, start="2015-01-05", seed=SEEDS.get(name, 1), carry=1.5)
    mb = B.build_bars(rows, con, ROOT, name)
    return mb, mb.frame.set_index("date")["contract"]


@pytest.fixture(scope="module")
def world():
    ctxs, runs = {}, []
    for name in ("CL", "GC"):
        mb, _ = _loader(name)
        r, ctx = E.run_market(mb, MARKETS[name])
        runs.append(r)
        ctxs[name] = ctx
    cal = pd.DatetimeIndex(sorted(set().union(*[set(r.dates) for r in runs])))
    return ctxs, runs, cal


# ---- C3 ---------------------------------------------------------------------------------------------

def test_the_draw_seed_is_the_registered_one():
    a = K.draw_rng(7, "CL", 5).integers(0, 10**9, 5)
    b = np.random.default_rng([zlib.crc32(b"7"), zlib.crc32(b"CL"), 5]).integers(0, 10**9, 5)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, K.draw_rng(8, "CL", 5).integers(0, 10**9, 5))
    assert not np.array_equal(a, K.draw_rng(7, "GC", 5).integers(0, 10**9, 5))


def test_a_pick_is_k_distinct_indices_of_the_pool_and_never_more_than_the_pool():
    p = K.c3_pick(3, "CL", 5, 50, 12)
    assert len(p) == 12 and len(set(p.tolist())) == 12 and p.min() >= 0 and p.max() < 50
    assert len(K.c3_pick(3, "CL", 5, 4, 12)) == 4            # k > pool: the whole pool, not an error
    assert len(K.c3_pick(3, "CL", 5, 0, 12)) == 0 and len(K.c3_pick(3, "CL", 5, 9, 0)) == 0


def test_one_markets_pick_does_not_depend_on_which_other_markets_ran():
    assert np.array_equal(K.c3_pick(9, "CL", 3, 40, 10), K.c3_pick(9, "CL", 3, 40, 10))
    a = K.c3_pick(9, "CL", 3, 40, 10)
    assert not np.array_equal(a, K.c3_pick(9, "CL", 5, 40, 10))          # R is in the seed too


def test_the_pool_is_every_weekly_ok_break_a_plus_not_required(world):
    ctxs, _, _ = world
    setup = K.c3_setup(ctxs)
    assert set(setup) == {(m, R) for m in ctxs for R in PIVOT_SIZES}
    grew = False
    for (name, R), s in setup.items():
        pool = len(s["pool_up"]) + len(s["pool_dn"])
        own = retest_signals(ctxs[name], R)
        assert s["n_sel"] == int(own.scan.ent_up.sum() + own.scan.ent_dn.sum())
        grew |= pool > s["n_sel"]
        assert s["own_in_pool"] <= s["own_total"] == s["n_sel"]
        # every pooled entry sits behind a raw break that agreed with the weekly filter at the break bar
        ev = retest_signals(ctxs[name], R, a1=False, a2=False, a3=False).scan.events
        ent = ev[ev["outcome"] == "entry"]
        assert len(ent) == pool
        htf = s["base"].htf
        for _, e in ent.iterrows():
            assert htf[int(e["t"])] == e["direction"]
    assert grew, "the synthetic pool must be larger than TL-v2's own entries for C3 to be a thinning"


def test_a_draw_feeds_the_simulator_exactly_k_pooled_signals_and_is_reproducible(world, monkeypatch):
    ctxs, _, _ = world
    setup = K.c3_setup(ctxs)
    seen = []

    def spy(ctx, x, risk=K.ENS_RISK):
        seen.append(x)
        return 0.0, 0

    monkeypatch.setattr(K, "sim_net_mid", spy)
    K.c3_draw(ctxs, setup, 4)
    assert len(seen) == sum(1 for s in setup.values() if s["n_sel"] > 0 and len(s["pool_up"]) + len(s["pool_dn"]) > 0)
    it = iter(seen)
    for (name, R), s in setup.items():
        size = len(s["pool_up"]) + len(s["pool_dn"])
        if s["n_sel"] == 0 or size == 0:
            continue
        x = next(it)
        assert int(x.qual_up.sum() + x.qual_dn.sum()) == min(s["n_sel"], size)
        assert set(np.nonzero(x.qual_up)[0]) <= set(s["pool_up"].tolist())
        assert set(np.nonzero(x.qual_dn)[0]) <= set(s["pool_dn"].tolist())
        assert (x.qual_up <= x.up).all() and (x.qual_dn <= x.dn).all()      # signals are also raw-marked
    monkeypatch.undo()
    assert K.c3_draw(ctxs, setup, 4) == K.c3_draw(ctxs, setup, 4)


def test_c3_reports_the_registered_percentiles_in_order(world):
    ctxs, _, _ = world
    c3 = K.run_c3(ctxs, draws=12)
    assert c3["draws"] == 12 and len(c3["totals"]) == 12
    assert c3["p5"] <= c3["p50"] <= c3["p95"] <= c3["p99"]
    assert c3["p99"] == pytest.approx(float(np.percentile(c3["totals"], 99)))
    assert c3["selected_entries"] <= c3["pool_entries"]
    assert 0 <= c3["own_in_pool"] <= c3["own_total"] == c3["selected_entries"]
    again = K.run_c3(ctxs, draws=12)
    assert np.array_equal(c3["totals"], again["totals"])


# ---- the 27-cell grid -------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def grid(world):
    return K.run_grid(world[0])


def test_the_grid_is_the_27_registered_cells(grid):
    assert len(grid) == 27
    assert set(grid["touch_buf"]) == {0.15, 0.25, 0.35}
    assert set(grid["window"]) == {125, 250, 400}
    assert set(grid["N"]) == {5, 10, 20}
    assert not grid.duplicated(["touch_buf", "window", "N"]).any()
    assert grid["net_mid"].nunique() > 1, "the axes must move the result"


def test_the_centre_cell_is_the_verdict_book_exactly(world, grid):
    """The strongest integration check: the grid's own simulate/book path and the engine's book path
    must agree to the cent, trade for trade, on the registered cell."""
    _, runs, cal = world
    b = Rp.make_books(runs, cal)[("v2", "ens", "frac", EQUITY)]
    c = grid[(grid["window"] == 250) & (grid["touch_buf"] == 0.25) & (grid["N"] == 10)].iloc[0]
    assert c["net_mid"] == pytest.approx(b.net("mid"), abs=1e-6)
    assert int(c["trades"]) == len(b.trades)


# ---- costs are IBKR everywhere ----------------------------------------------------------------------

def test_the_trade_rows_are_priced_at_ibkr_not_the_flat_friction(world):
    _, runs, _ = world
    t = pd.concat([r.trades for r in runs], ignore_index=True)
    t = t[(t["spec"] == "v2") & (t["sizing"] == "int")]
    assert len(t)
    assert (t["slip"] == 0).all()
    per_side = (t["gross"] - t["net_mid"]) / (t["qty"] * 2)             # >= 2 sides per trade
    flat = 1.25
    assert not np.allclose(per_side.groupby(t["market"]).median().to_numpy(), flat)


# ---- criteria ---------------------------------------------------------------------------------------

def fake_book(spec, n, total_mid, *, markets=("CL", "GC", "6E", "ES", "NG", "SI"), seed=1, drift_years=True):
    cal = pd.bdate_range("2010-06-01", "2021-12-31")
    rng = np.random.default_rng(seed)
    daily = {}
    for lv, add in zip(LEVELS, (0.5, 0.0, -0.5)):
        per_day = (total_mid + add * n) / len(cal) / len(markets)
        arr = rng.normal(per_day, 3.0, (len(cal), len(markets)))
        daily[lv] = pd.DataFrame(arr, index=cal, columns=list(markets))
    ent = pd.Series(cal[np.linspace(0, len(cal) - 2, n).astype(int)])
    trades = pd.DataFrame({"market": [markets[i % len(markets)] for i in range(n)],
                           "entry_date": ent.to_numpy(), "hold": 5,
                           "gross": total_mid / n + 3.0,
                           "net_low": total_mid / n + 0.5, "net_mid": total_mid / n, "net_high": total_mid / n - 0.5})
    return Book(spec, "ens" if spec != "C1" else "single", "frac", EQUITY, trades, daily, cal)


def fake_grid(npos):
    g = pd.DataFrame({"touch_buf": [0.25] * 27, "window": [250] * 27, "N": [10] * 27,
                      "net_mid": [100.0] * npos + [-100.0] * (27 - npos), "trades": 200})
    return g


C3 = dict(p5=-500.0, p50=100.0, p95=900.0, p99=1100.0, mean=100.0, draws=1000)


def test_under_150_trades_every_criterion_is_not_read_and_the_verdict_is_not_read():
    b, c1 = fake_book("v2", 120, 1500.0), fake_book("C1", 200, 100.0, seed=2)
    crit = Rp.criteria(b, c1, C3, fake_grid(27))
    assert [c.passed for c in crit] == [None] * 10
    assert all("for information only" in c.value for c in crit[:9])
    v = Rp.verdict_lines(crit, 120, b.net("mid"))
    assert v[0].startswith("NOT READ") and "rescue the count" in v[0]
    assert "FAIL" not in v[0].upper().replace("NEITHER PASSED NOR FAILED", "")


def test_criterion_6_is_the_p99_not_the_p95():
    b, c1 = fake_book("v2", 200, 1000.0), fake_book("C1", 200, 100.0, seed=2)
    crit = Rp.criteria(b, c1, C3, fake_grid(27))                        # 900 (p95) < 1000 < 1100 (p99)
    assert 900 < b.net("mid") < 1100
    assert crit[5].passed is False and "p99" in crit[5].value and "p99" in crit[5].text
    c3_lo = dict(C3, p95=800.0, p99=950.0)
    assert Rp.criteria(b, c1, c3_lo, fake_grid(27))[5].passed is True


def test_criterion_9_needs_18_of_27_cells():
    b, c1 = fake_book("v2", 200, 1000.0), fake_book("C1", 200, 100.0, seed=2)
    assert Rp.criteria(b, c1, C3, fake_grid(17))[8].passed is False
    assert Rp.criteria(b, c1, C3, fake_grid(18))[8].passed is True


def test_criterion_5_and_6_failing_closes_the_study_whatever_else_passes():
    b, c1 = fake_book("v2", 200, 1000.0), fake_book("C1", 200, 100.0, seed=2)
    crit = Rp.criteria(b, c1, C3, fake_grid(27))
    v = Rp.verdict_lines(crit, 200, b.net("mid"))
    assert v[0].startswith("DOES NOT PASS") and "study closes" in v[0]


def test_a_pass_below_tl_v1s_immediate_entry_says_so_in_the_first_line():
    """sec 4: 'If TL-v2 passes yet is below TL-v1's, the write-up says so in the first line.'"""
    ok = [Criterion(i, "x", "y", True) for i in range(1, 11)]
    low = Rp.verdict_lines(ok, 400, Rp.C2_REF["ibkr_mid"] - 1.0)
    assert len(low) == 1 and "BELOW TL-v1" in low[0] and low[0].startswith("PASSES all ten")
    high = Rp.verdict_lines(ok, 400, Rp.C2_REF["ibkr_mid"] + 1.0)
    assert "BELOW" not in high[0] and high[0].startswith("PASSES all ten")


def test_the_c2_reference_matches_the_requote_file_when_it_is_present():
    f = Path(__file__).resolve().parents[3] / "Claude outputs" / "w15_0033_requote_ibkr_20260930.txt"
    if not f.exists():
        pytest.skip("requote file not present")
    line = next(l for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("v1 ENSEMBLE(R3+R5+R8 sleeves) frac"))
    nums = re.findall(r"\(?\$[\d,]+\)?|\d+", line.split("frac", 1)[1])
    assert int(nums[0]) == Rp.C2_REF["trades"]
    assert "$606" in line and "$775" in line


# ---- the report -------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rendered(world, grid):
    ctxs, runs, cal = world
    c3 = K.run_c3(ctxs, draws=10)
    text, summary = Rp.render(runs, ctxs, cal, c3=c3, grid=grid, scoped=True, notes=["test"],
                              preflight_total=999)
    return text, summary


def test_the_report_has_every_registered_section_and_ibkr_wording(rendered):
    text, summary = rendered
    for s in ("1. SECTION 4 VERDICT", "2. EVERY BOOK", "3. CONTROLS", "4. COUNTS", "5. THE 27-CELL",
              "6. EVERY CALENDAR YEAR", "7. A3 THRESHOLDS", "8. SAMPLE TRADES", "9. SEEN WINDOW",
              "10. CAVEATS", "SCOPED / NON-REGISTERED RUN"):
        assert s in text, s
    assert "IBKR" in text and "p99" in text and "seen -- not evidence" in text
    assert "$1.25" not in text and "$2.50" not in text and "+ 1 tick on every stop fill" not in text
    assert "no best-cell" in text.lower() or "no best-cell table" in text
    assert len(summary) > 0


def test_the_report_counts_per_market_and_year_carry_the_registered_columns(rendered):
    text, _ = rendered
    for col in ("qualified", "entries", "failed", "no_retest", "skipped_size", "med_bars_to_retest",
                "med_bars_held"):
        assert col in text, col


def test_the_seen_window_block_finds_nothing_in_the_training_bars(world):
    _, _, cal = world
    from strategy.tl_v2 import holdout as TH
    assert TH.seen_dates([d.strftime("%Y-%m-%d") for d in cal])[0] == []


# ---- the runner -------------------------------------------------------------------------------------

def _pf_csv(tmp_path, entries_per_market, markets=None, name="w15_0030_tl_v2_preflight_20260930.csv"):
    markets = list(markets if markets is not None else MARKETS)
    rows = [dict(market=m, R=5, N=10, year=2015, entries=entries_per_market) for m in markets]
    p = tmp_path / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def test_the_runner_refuses_holdout_and_limit(tmp_path):
    with pytest.raises(RUN.RunRefused) as e:
        RUN.main(["--holdout", "--out-dir", str(tmp_path)])
    assert "holdout is not spent" in str(e.value)
    with pytest.raises(RUN.RunRefused) as e:
        RUN.main(["--limit", "5", "--out-dir", str(tmp_path)])
    assert "--limit is refused" in str(e.value)


def test_the_runner_refuses_to_start_without_the_preflight(tmp_path):
    with pytest.raises(RUN.RunRefused) as e:
        RUN.run(None, ["CL"], tmp_path, "t", draws=2, loader=_loader, log=lambda *_: None)
    assert "no TL-v2 pre-flight found" in str(e.value)
    assert not list(tmp_path.glob("w15_0031_*"))


def test_the_runner_refuses_on_the_stop_rule(tmp_path):
    pf = _pf_csv(tmp_path, 12)                                          # 12 x 12 = 144 < 150
    with pytest.raises(RUN.RunRefused) as e:
        RUN.run(None, ["CL"], tmp_path, "t", draws=2, loader=_loader, preflight_csv=pf, log=lambda *_: None)
    assert "STOP RULE HIT" in str(e.value) and "144" in str(e.value)
    assert not list(tmp_path.glob("w15_0031_*"))


def test_the_stop_rule_reads_the_primary_n_10_only(tmp_path):
    rows = [dict(market=m, R=5, N=10, year=2015, entries=1) for m in MARKETS]        # 12 primary entries
    rows += [dict(market=m, R=5, N=20, year=2015, entries=500) for m in MARKETS]     # N = 20 must not rescue it
    p = tmp_path / "w15_0030_tl_v2_preflight_20260930.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    with pytest.raises(RUN.RunRefused):
        RUN.check_stop_rule(p)


def test_the_runner_refuses_a_scoped_preflight(tmp_path):
    pf = _pf_csv(tmp_path, 100, markets=["CL", "GC"])
    with pytest.raises(RUN.RunRefused) as e:
        RUN.check_stop_rule(pf)
    assert "scoped" in str(e.value)


def test_the_runner_picks_the_newest_preflight_in_the_out_dir(tmp_path):
    _pf_csv(tmp_path, 1, name="w15_0030_tl_v2_preflight_20260929.csv")
    good = _pf_csv(tmp_path, 20, name="w15_0030_tl_v2_preflight_20260930.csv")
    assert RUN.latest_preflight_csv(tmp_path) == good
    assert RUN.check_stop_rule(good) == 240


@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    d = tmp_path_factory.mktemp("bt")
    _pf_csv(d, 20)
    rep = RUN.run(None, ["CL", "GC"], d, "20260930", draws=6, loader=_loader, log=lambda *_: None)
    return rep, d


def test_a_full_run_writes_every_registered_file_and_is_labelled_scoped(full_run):
    rep, d = full_run
    for kind in ("", "_trades", "_books", "_counts", "_events", "_c3", "_grid"):
        ext = ".txt" if kind == "" else ".csv"
        assert (d / f"w15_0031_tl_v2_backtest{kind}_20260930{ext}").exists(), kind
    text = rep.read_text(encoding="utf-8")
    assert "SCOPED / NON-REGISTERED RUN" in text and "Pre-flight stop rule (W15-0048) read before this run: 240" in text
    grid = pd.read_csv(d / "w15_0031_tl_v2_backtest_grid_20260930.csv")
    assert len(grid) == 27
    assert len(pd.read_csv(d / "w15_0031_tl_v2_backtest_c3_20260930.csv")) == 6


def test_no_trade_or_bar_of_the_run_touches_the_holdout_window(full_run):
    _, d = full_run
    t = pd.read_csv(d / "w15_0031_tl_v2_backtest_trades_20260930.csv")
    assert pd.to_datetime(t["exit_date"]).max() < pd.Timestamp("2022-01-01")


def test_the_new_modules_never_touch_the_holdout_spend_path():
    for f in ("controls.py", "report.py", "run.py"):
        src = (PKG / f).read_text(encoding="utf-8")
        assert "spend=True" not in src and ".load_for(" not in src and "candidate=" not in src, f
    run_src = (PKG / "run.py").read_text(encoding="utf-8")
    assert "B.load_market" in run_src                                    # bars come through the holdout cut
