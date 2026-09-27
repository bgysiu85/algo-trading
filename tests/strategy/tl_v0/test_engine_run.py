"""engine.py, report.py and run.py end to end on synthetic markets (no archive)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.tl_v0 import bars as B
from strategy.tl_v0 import engine as E
from strategy.tl_v0 import report as Rp
from strategy.tl_v0 import run as RUN
from strategy.tl_v0.spec import EQUITY, MARKETS
from tests.strategy.tl_v0.synth import ROOT, contracts_and_rows


def _loader(name):
    seed = {"CL": 3, "GC": 11, "6E": 5}.get(name, 1)
    rows, con, _ = contracts_and_rows(n=1400, start="2015-01-05", seed=seed, carry=1.5)
    scale = 1.0 if name != "6E" else 0.01
    for k in ("open", "high", "low", "close"):
        rows[k] = rows[k] * scale
    mb = B.build_bars(rows, con, ROOT, name)
    c0 = mb.frame.set_index("date")["contract"]
    return mb, c0


@pytest.fixture(scope="module")
def cl_run():
    mb, _ = _loader("CL")
    return mb, E.run_market(mb, MARKETS["CL"])


def test_every_registered_sleeve_and_sizing_is_walked(cl_run):
    _, r = cl_run
    c = r.counts
    for spec, shares in (("v0", {"sleeve", "alone"}), ("v0-rev", {"sleeve", "alone"}),
                         ("C2", {"sleeve"}), ("C1", {"single"})):
        sub = c[c["spec"] == spec]
        assert set(sub["share"]) == shares
        assert set(zip(sub["sizing"], sub["equity"])) == set(E.SIZINGS)
    assert len(r.trades) > 0


def test_fractional_ensemble_is_the_mean_of_the_three_pivot_sizes_alone(cl_run):
    """Section 2.1: each ensemble sleeve is sized at one third of the risk.
    With fractional sizing a sleeve is exactly 1/3 of the same R alone."""
    _, r = cl_run
    t = r.trades[(r.trades["sizing"] == "frac") & (r.trades["spec"] == "v0-rev")]
    sl = t[t["share"] == "sleeve"]["net_mid"].sum()
    al = t[t["share"] == "alone"]["net_mid"].sum()
    assert sl == pytest.approx(al / 3, rel=1e-9)


def test_integer_books_never_hold_a_fraction(cl_run):
    _, r = cl_run
    q = r.trades[r.trades["sizing"] == "int"]["qty"]
    assert (q == np.floor(q)).all() and (q >= 1).all()


def test_bigger_accounts_skip_less(cl_run):
    _, r = cl_run
    c = r.counts[(r.counts["spec"] == "v0") & (r.counts["sizing"] == "int")]
    s = c.groupby("equity")["skipped_size"].sum().sort_index()
    assert s.is_monotonic_decreasing


def test_c3_hold_and_rebalance(cl_run):
    mb, _ = cl_run
    tr, cn = E.tsmom_hold_trades(mb.frame, 20, mult=100.0, risk_usd=221.29, integer=False)
    assert len(tr) > 3 and cn["entries"] > 0
    for t in tr[:-1]:
        assert t.exit_j - t.entry_j == 20 and t.reason == "rebalance"   # held exactly H
    for a, b in zip(tr[:-1], tr[1:]):
        assert b.entry_j >= a.exit_j                     # one position at a time
    assert tr[-1].reason in ("rebalance", "data_end")


def test_donchian_uses_the_prior_20_bars_only(cl_run):
    mb, _ = cl_run
    x = E.donchian_input(mb.frame)
    h, lo, c = (mb.frame[k].to_numpy() for k in ("high", "low", "close"))
    n = len(c)
    ups = [j for j in range(20, n) if c[j] > h[j - 20:j].max()]
    dns = [j for j in range(20, n) if c[j] < lo[j - 20:j].min()]
    assert len(ups) > 10 and len(dns) > 10
    assert np.nonzero(x.up)[0].tolist() == ups
    assert np.nonzero(x.dn)[0].tolist() == dns
    j = ups[5]
    assert x.init_long[j] == lo[j - 9:j + 1].min()      # the 10-bar exit channel, incl. j


def test_the_runner_writes_a_full_report(tmp_path):
    rep = RUN.run(None, ["CL", "GC", "6E"], tmp_path, "test", loader=_loader)
    text = rep.read_text(encoding="utf-8")
    assert "SCOPED RUN" in text                                # 3 of 12 markets
    for s in ("1. SECTION 4 VERDICT -- v0-rev", "1. SECTION 4 VERDICT -- v0 ",
              "2. EVERY BOOK", "3. EVERY CALENDAR YEAR", "4. BY MARKET", "5. COUNTS",
              "6. INTEGER SIZING", "7. SECTION 5.1", "8. DAVEY", "9. SAMPLE TRADES",
              "10. COVERAGE", "C3|v0-rev"):
        assert s in text, s
    trades = pd.read_csv(tmp_path / "tl_v0_backtest_trades_test.csv")
    assert set(trades["spec"]) >= {"v0", "v0-rev", "C1", "C2", "C3|v0", "C3|v0-rev"}
    assert pd.to_datetime(trades["exit_date"]).max() < pd.Timestamp("2022-01-01")
    books = pd.read_csv(tmp_path / "tl_v0_backtest_books_test.csv")
    assert len(books) == len(Rp.BOOKS) * 4


def test_book_totals_agree_between_trades_and_daily(tmp_path):
    runs = []
    for name in ("CL", "GC"):
        mb, _ = _loader(name)
        runs.append(E.run_market(mb, MARKETS[name]))
    cal = pd.DatetimeIndex(sorted(set(runs[0].dates) | set(runs[1].dates)))
    for spec, cut in Rp.BOOKS[:9]:
        b = Rp.build_book(runs, spec, cut, "frac", EQUITY, cal)
        for lv in ("low", "mid", "high"):
            assert b.series(lv).sum() == pytest.approx(b.net(lv), abs=1e-6)


def test_the_runner_refuses_the_holdout_and_limit():
    with pytest.raises(RUN.RunRefused):
        RUN.main(["--holdout"])
    with pytest.raises(RUN.RunRefused):
        RUN.main(["--limit", "3"])


def test_money_brackets_negatives():
    assert Rp.money(-1234.4).strip() == "($1,234)"
    assert Rp.money(1234.4).strip() == "$1,234"


def test_davey_mc_is_seeded_and_ordered():
    t = pd.DataFrame({"exit_date": pd.date_range("2015-01-01", periods=6),
                      "entry_date": pd.date_range("2014-12-01", periods=6),
                      "net_mid": [-100.0, -100.0, -100.0, 500.0, -2500.0, 100.0]})
    b = Rp.Book("v0-rev", "ens", "frac", EQUITY, t, {}, pd.DatetimeIndex([]))
    d1, d2 = Rp.davey(b, paths=500), Rp.davey(b, paths=500)
    assert d1 == d2
    assert d1["three_loss_events"] == 1 and d1["three_loss_first"] == "2015-01-03"
    assert d1["actual_dd"] == pytest.approx(2500.0)
    assert d1["pause_first"] == "2015-01-05" and d1["pause_episodes"] == 1


def test_duplicate_market_names_run_once(monkeypatch):
    seen = {}
    monkeypatch.setattr(RUN, "run", lambda archive, markets, out, stamp, **k: seen.setdefault("m", markets) or out)
    RUN.main(["--archive", "x", "--markets", "CL", "CL", "GC"])
    assert seen["m"] == ["CL", "GC"]


def test_load_rows_cuts_the_holdout_before_anything_else(monkeypatch):
    """A 2022 row that would make the loader refuse (one contract, two
    closes on one date) must never be looked at."""
    from strategy.tsmom import archive as A
    rows, con, _ = contracts_and_rows(n=2900, start="2011-01-03", seed=2)
    ids = {s: i + 100 for i, s in enumerate(con["symbol"])}
    df = rows.assign(instrument_id=rows["contract"].map(ids),
                     symbol="CL.c.0", ts_event=pd.to_datetime(rows["date"]).dt.tz_localize("UTC"))
    bad = df[df["date"] >= "2022-03-01"].head(1).assign(close=-999.0)
    df = pd.concat([df, bad]).set_index("ts_event")
    defs = con.assign(instrument_id=con["symbol"].map(ids))
    monkeypatch.setattr(A, "_dbn_df", lambda p: df.copy())
    monkeypatch.setattr(A, "load_definitions", lambda archive, root: (defs, []))
    monkeypatch.setattr(A, "point_value_check", lambda root, c: [])
    monkeypatch.setattr(B.Path, "exists", lambda self: "c2-c4" not in str(self))
    folded, contracts, c0, note = B.load_rows(B.Path("arch"), "CL")
    assert folded["date"].max() < pd.Timestamp("2022-01-01")
    assert note["locked_rows_dropped_on_load"] > 0
