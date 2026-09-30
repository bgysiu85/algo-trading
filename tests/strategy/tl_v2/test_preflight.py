"""G2 of REGISTERED_tl_v2.md sec 5: the pre-flight counts and reads no exit price, no P&L."""
from __future__ import annotations

import pandas as pd
import pytest

import strategy.tl_v0.sim as SIM
from strategy.tl_v0 import bars as B
from strategy.tl_v0.spec import MARKETS
from strategy.tl_v2 import preflight as PF
from tests.strategy.tl_v0.synth import ROOT, contracts_and_rows


def _loader(name):
    seed = {"CL": 3, "GC": 11, "6E": 5}.get(name, 1)
    rows, con, _ = contracts_and_rows(n=1400, start="2015-01-05", seed=seed, carry=1.5)
    mb = B.build_bars(rows, con, ROOT, name)
    return mb, mb.frame.set_index("date")["contract"]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("pf")
    calls = []
    real = SIM.simulate

    def boom(*a, **k):
        calls.append(1)
        raise AssertionError("the pre-flight called the simulator")
    SIM.simulate = boom
    try:
        rep = PF.run(None, ["CL", "GC"], d, "20260930", loader=_loader, log=lambda *_: None)
    finally:
        SIM.simulate = real
    return rep, d, calls


def test_it_never_calls_the_simulator(out):
    assert out[2] == []


def test_the_csv_columns_are_exactly_the_registered_count_columns_and_no_pnl_word_appears(out):
    _, d, _ = out
    df = pd.read_csv(d / "w15_0030_tl_v2_preflight_20260930.csv", encoding="utf-8")
    assert tuple(df.columns) == PF.COLUMNS
    PF.assert_count_only(df.columns)
    text = (d / "w15_0030_tl_v2_preflight_20260930.txt").read_text(encoding="utf-8").lower()
    for w in ("gross", "net pnl", "profit", "sharpe", "profit factor"):
        assert w not in text


@pytest.mark.parametrize("bad", ["exit_px", "net_mid", "pnl", "gross", "return_pct", "hold_days", "slip"])
def test_a_pnl_or_exit_column_is_refused(bad):
    with pytest.raises(PF.PreflightRefused):
        PF.assert_count_only(list(PF.COLUMNS) + [bad])


def test_an_unregistered_column_is_refused_too():
    with pytest.raises(PF.PreflightRefused):
        PF.assert_count_only(list(PF.COLUMNS) + ["mystery"])


@pytest.mark.parametrize("argv", [["--holdout"], ["--limit", "5"], ["--pnl"], ["--exits"], ["--simulate"]])
def test_holdout_limit_and_pnl_flags_are_refused(argv):
    with pytest.raises(PF.PreflightRefused):
        PF.main(argv)


def test_the_counts_add_up(out):
    _, d, _ = out
    df = pd.read_csv(d / "w15_0030_tl_v2_preflight_20260930.csv", encoding="utf-8")
    assert len(df)
    resolved = df["entries"] + df["failed"] + df["no_retest"] + df["open_at_end"]
    assert (resolved == df["qualified"]).all(), "every qualified break has exactly one outcome"
    assert (df["entries_sr"] <= df["entries"]).all()
    assert (df["sizeable_full"] >= df["sizeable_sleeve"]).all()
    assert (df["no_stop"] + df["void"] + df["sizeable_sleeve"] <= df["entries"]).all()
    assert set(df["N"]) == {10, 20} and set(df["R"]) <= {3, 5, 8}


def test_the_report_states_the_stop_rule_and_reads_it(out):
    rep, _, _ = out
    t = rep.read_text(encoding="utf-8")
    assert "STOP RULE" in t or "stop rule" in t.lower()
    assert "SCOPED RUN" in t                           # only two markets: not the registered pre-flight
    assert "TOTAL TL-v2 retest entries" in t


def test_the_stop_rule_fires_below_150_and_clears_at_or_above_it():
    def frame(n_entries):
        return pd.DataFrame([dict(market="CL", R=5, N=10, year=2015, qualified=n_entries, ignored_pending=0,
                                  failed=0, no_retest=0, open_at_end=0, entries=n_entries, entries_sr=0,
                                  no_stop=0, void=0, sizeable_sleeve=0, sizeable_full=0,
                                  median_bars_to_retest=2.0)], columns=list(PF.COLUMNS))
    mk = list(MARKETS)
    low = PF.build_report(frame(149), [], mk, scoped=False)
    high = PF.build_report(frame(150), [], mk, scoped=False)
    assert "STOP RULE HIT: 149 < 150" in low
    assert "Clears the stop rule (150 >= 150)" in high and "STOP RULE HIT" not in high
    assert "Not read (scoped run)" in PF.build_report(frame(10), [], ["CL"], scoped=True)


def test_the_a3_threshold_cross_check_flags_a_difference():
    t = PF.build_report(pd.DataFrame([dict(market="CL", R=5, N=10, year=2015, qualified=1, ignored_pending=0,
                                           failed=0, no_retest=0, open_at_end=0, entries=1, entries_sr=0,
                                           no_stop=0, void=0, sizeable_sleeve=0, sizeable_full=0,
                                           median_bars_to_retest=1.0)], columns=list(PF.COLUMNS)),
                        [("CL", 0.109, 0.109), ("ES", 0.120, 0.104)], ["CL"], scoped=True)
    assert t.count("DIFFERS") == 1 and "ES: computed 0.120" in t
