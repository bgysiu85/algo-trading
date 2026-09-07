#!/usr/bin/env python3
"""The control that decides whether a screened backtest means anything.

Stage 2 selects on the session's own daily bar. A backtest over its survivors
has read the answer first, and the result is large, clean and not a strategy
result. This measures how much of it that explains -- so a bug here does not
produce an error, it produces a clearance.
"""
from __future__ import annotations

import csv
import json

import pytest

from common import leak_control as L
from common import screen as S
from tests.common.test_day_compare import trade, write_trades, write_state


def pairs_file(tmp_path, name, keys):
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps([{"symbol": s, "date": d} for s, d in keys]))
    return p


# --- the measurement --------------------------------------------------------

def test_only_evaluable_days_count(tmp_path):
    """A day with no bars is not evidence either way. Counted as 'no entry' it
    would make any strategy look clean in exact proportion to how much data was
    missing -- and missing data is precisely what a thin, rejected day has."""
    write_trades(tmp_path, "mcl", [trade(symbol="AAA", date="2026-03-16")])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "OK"},
                                  "BBB|2026-03-16": {"status": "OK"},
                                  "CCC|2026-03-16": {"status": "NO_DATA"}})
    m = L.measure(tmp_path, tmp_path, "mcl",
                  {("AAA", "2026-03-16"), ("BBB", "2026-03-16"),
                   ("CCC", "2026-03-16")})
    assert m["days"] == 2                 # not 3
    assert m["trades"] == 1
    assert m["entries_per_day"] == pytest.approx(0.5)


def test_a_declined_day_is_a_day_with_no_entry_not_a_missing_day(tmp_path):
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "OK"}})
    m = L.measure(tmp_path, tmp_path, "mcl", {("AAA", "2026-03-16")})
    assert m["days"] == 1 and m["trades"] == 0
    assert m["entries_per_day"] == 0.0


# --- the verdict ------------------------------------------------------------

def base(days=100, trades=50, net=-100.0):
    return {"days": days, "trades": trades, "net": net,
            "days_with_a_trade": trades,
            "entries_per_day": trades / days,
            "share_of_days_traded": trades / days,
            "net_per_day": net / days}


def test_a_quiet_reject_sample_reads_as_a_small_leak():
    out = "\n".join(L.verdict(base(trades=50), base(trades=5)))
    assert "SMALL LEAK" in out


def test_a_busy_reject_sample_reads_as_a_load_bearing_leak():
    """The uncomfortable answer has to be as easy to reach as the comfortable
    one, and it has to name what it means: stage 2 was doing the selecting."""
    out = "\n".join(L.verdict(base(trades=50), base(trades=45)))
    assert "LEAK IS LOAD-BEARING" in out
    assert "turned out" in out


def test_losing_money_on_rejected_days_is_called_out():
    out = "\n".join(L.verdict(base(trades=50), base(trades=45, net=-900.0)))
    assert "LOST money" in out


def test_a_strategy_that_never_enters_cannot_be_cleared_by_this():
    """Zero entries on survivors AND zero on rejects is not a pass. It is a
    strategy that did nothing, and dividing by it would report a ratio."""
    out = "\n".join(L.verdict(base(trades=0), base(trades=0)))
    assert "nothing for stage 2 to have leaked into" in out
    assert "SMALL LEAK" not in out


def test_the_threshold_is_a_named_judgement_not_a_buried_constant():
    assert 0 < L.SMALL_LEAK_RATIO < 1


# --- the two populations must be disjoint -----------------------------------

def test_a_day_in_both_lists_is_refused(tmp_path, monkeypatch):
    """An overlap puts the same symbol-day on both sides of the comparison and
    flattens exactly the difference being measured."""
    s = pairs_file(tmp_path, "surv", [("AAA", "2026-03-16")])
    r = pairs_file(tmp_path, "rej", [("AAA", "2026-03-16")])
    with pytest.raises(SystemExit) as e:
        L.main(["--survivors", str(s), "--rejects", str(r),
                "--reports", str(tmp_path), "--states", str(tmp_path),
                "--strategy", "mcl", "--out", str(tmp_path / "o.txt")])
    assert "BOTH" in str(e.value)


# --- the sample the control runs on -----------------------------------------

def feats(rows):
    import pandas as pd
    return pd.DataFrame(rows, columns=["symbol", "date", "prior_close",
                                       "prior_avg_dollar_vol", "rvol",
                                       "range_pct"])


def test_rejects_pass_stage_1_and_fail_stage_2():
    """The control sample must be days a live scanner WOULD have offered.
    A stage-1 failure is not evidence about stage 2 -- it was never a
    candidate, so the strategy skipping it says nothing."""
    cfg = S.Config()
    df = feats([
        ("PASS", "2026-03-16", 5.0, 1e7, 99.0, 99.0),   # survivor
        ("REJ", "2026-03-16", 5.0, 1e7, 0.5, 0.5),      # stage 1 ok, stage 2 no
        ("S1NO", "2026-03-16", 999.0, 1.0, 0.5, 0.5),   # fails stage 1 too
    ])
    got = set(S.rejects(df, cfg)["symbol"])
    assert got == {"REJ"}


def test_the_reject_sample_follows_the_survivors_date_distribution():
    """Rejects are far more numerous on quiet sessions. A uniform draw would be
    mostly quiet days, on which any strategy takes few trades for reasons that
    have nothing to do with stage 2 -- and the control would 'prove' the filter
    harmless by comparing active days against dull ones."""
    cfg = S.Config()
    rows = []
    for i in range(50):                      # a busy day: many survivors
        rows.append((f"A{i}", "2026-03-16", 5.0, 1e7, 0.1, 0.1))
    for i in range(50):                      # a quiet day: as many rejects
        rows.append((f"B{i}", "2026-03-17", 5.0, 1e7, 0.1, 0.1))
    rej = feats(rows)
    sel = feats([(f"S{i}", "2026-03-16", 5.0, 1e7, 99.0, 99.0)
                 for i in range(9)]
                + [("S9", "2026-03-17", 5.0, 1e7, 99.0, 99.0)])
    got = S.sample_rejects(rej, sel, 20, seed=1)
    n = got.groupby("date").size().to_dict()
    # survivors are 9:1 across the two dates, so the draw must be too
    assert n["2026-03-16"] > n["2026-03-17"] * 4


def test_the_draw_is_reproducible():
    cfg = S.Config()
    rej = feats([(f"A{i}", "2026-03-16", 5.0, 1e7, 0.1, 0.1) for i in range(40)])
    sel = feats([("S0", "2026-03-16", 5.0, 1e7, 99.0, 99.0)])
    a = S.sample_rejects(rej, sel, 10, seed=7)
    b = S.sample_rejects(rej, sel, 10, seed=7)
    c = S.sample_rejects(rej, sel, 10, seed=8)
    assert list(a["symbol"]) == list(b["symbol"])
    assert list(a["symbol"]) != list(c["symbol"])


def test_sampling_never_asks_for_more_than_a_session_has():
    cfg = S.Config()
    rej = feats([("A0", "2026-03-16", 5.0, 1e7, 0.1, 0.1)])
    sel = feats([(f"S{i}", "2026-03-16", 5.0, 1e7, 99.0, 99.0) for i in range(5)])
    got = S.sample_rejects(rej, sel, 100, seed=0)
    assert len(got) == 1


def test_an_empty_reject_population_returns_an_empty_frame():
    rej = feats([])
    sel = feats([("S0", "2026-03-16", 5.0, 1e7, 99.0, 99.0)])
    assert S.sample_rejects(rej, sel, 10, seed=0).empty


# --- the default that produced a plausible wrong answer ---------------------

def test_the_screen_defaults_to_consolidated_volume():
    """Every threshold in the screen is a volume threshold. EQUS.MINI carries a
    median 4.7% of the consolidated tape and the shortfall varies four-fold
    between symbols, so an RVOL computed on it is wrong by a per-name factor.

    The default used to be EQUS.MINI. A run with the flag omitted returned
    12,128 candidates instead of ~22,900, wrote them to a file named
    screen_pairs_consolidated.json, and reported nothing unusual."""
    assert S.DATASET_DEFAULT == "EQUS.SUMMARY"


def test_the_report_names_the_dataset_it_used():
    """The one thing that would have caught it: the header says which tape the
    numbers came from."""
    import inspect
    src = inspect.getsource(S.main)
    assert "dataset={a.dataset}" in src


# --- the quality cut, added 2026-09-07 --------------------------------------

def _m(days, trades, net):
    return {"days": days, "trades": trades, "net": net,
            "days_with_a_trade": min(days, trades),
            "entries_per_day": trades / days if days else 0.0,
            "share_of_days_traded": 0.0,
            "net_per_day": net / days if days else 0.0,
            "net_per_trade": (net / trades) if trades else None}


def test_the_rate_test_can_pass_while_the_quality_test_fails():
    """MC5 on 2026-09-07: rejected-day entry rate was 7% of the survivors' --
    a clear pass -- while the rejected days lost $7.21 a trade against +$1.11
    on the ones stage 2 kept. The rate test does not detect that, and this is
    the whole reason the quality cut exists."""
    surv = _m(21_407, 7_403, 8_209.18)
    rej = _m(3_886, 92, -663.9)
    out = "\n".join(L.verdict(surv, rej))
    assert "SMALL LEAK" in out                      # the rate test passes
    assert "WARNING" in out                          # and the quality test does not
    assert "THREW AWAY" in out


def test_a_clean_result_says_which_pass_is_the_stronger_one():
    surv = _m(1000, 500, 500.0)
    rej = _m(1000, 100, 200.0)          # better per trade on the rejects
    out = "\n".join(L.quality_verdict(surv, rej))
    assert "stronger of the two passes" in out
    assert "WARNING" not in out


def test_too_few_rejected_trades_is_reported_as_a_signal_not_a_finding():
    surv = _m(1000, 500, 500.0)
    rej = _m(1000, 5, -50.0)
    out = "\n".join(L.quality_verdict(surv, rej))
    assert "Too few" in out and "WARNING" not in out


def test_a_population_with_no_trades_yields_no_quality_verdict():
    assert L.quality_verdict(_m(10, 0, 0.0), _m(10, 0, 0.0)) == []


def test_the_threshold_is_a_named_constant_not_a_literal():
    """SMALL_LEAK_RATIO is named so it can be argued with rather than buried in
    an if. The same has to hold for the new one."""
    import inspect
    assert L.QUALITY_MIN_TRADES == 30
    src = inspect.getsource(L.quality_verdict)
    assert "QUALITY_MIN_TRADES" in src and "< 30" not in src


def test_measure_reports_per_trade_as_none_when_there_are_no_trades():
    """0.00 per trade and 'never traded' are different findings."""
    assert _m(10, 0, 0.0)["net_per_trade"] is None
