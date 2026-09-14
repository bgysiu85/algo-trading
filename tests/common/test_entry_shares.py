#!/usr/bin/env python3
r"""Shares outstanding against the trades, and the ways that join can flatter.

Three failure shapes are what this file is for.

THE MISSING ARE NOT MISSING AT RANDOM. 28.9% of the universe's symbol-days
have no knowable share count, and they skew toward the delisted microcaps this
strategy exists to trade. A bucket table built on the other 71.1% describes a
subset. The coverage control has to be computed and PRINTED before any bucket,
and the tests below pin both.

A SHRINKING DENOMINATOR. A trade whose symbol-day has no figure must still be
counted somewhere. Dropping it silently turns "57% of trades had a number" into
"100% of the trades we measured".

KNOWN AND STALE AVERAGED TOGETHER. A count filed 30 days before a session and
one filed 4,880 days before it are not one population. Merging them is how a
disagreement gets hidden instead of resolved.

The last section runs the real pipeline, because `entry_split` shipped with 19
green tests and raised KeyError on its first real session.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from common import entry_shares as S


def trade(symbol="AAA", date="2026-01-02", gross=0.0, status="known",
          shares=None, **kw):
    r = {"symbol": symbol, "date": date, "gross": gross, "status": status}
    if shares is not None:
        r["shares"] = float(shares)
    r.update(kw)
    return r


def spread(n, per_bucket_gross, date="2026-01-02", status="known"):
    """n trades per bucket, share counts 1e6 apart so the quantiles are clean."""
    out = []
    for b, g in enumerate(per_bucket_gross):
        for i in range(n):
            out.append(trade(gross=g, status=status, date=date,
                             shares=(b + 1) * 1e6 + i))
    return S.with_net(out, S.MEASURED_FRICTION)


# --- the pre-registration is in the module, not in a chat message -----------

def test_the_decision_rule_is_written_down_before_the_run():
    """A rule chosen after the table is a rule fitted to it."""
    doc = S.__doc__
    assert "PRE-REGISTERED" in doc
    for word in ("CLEARS", "SEPARATES", "NOTHING"):
        assert word in doc
    assert "both halves" in doc.lower()
    assert str(S.DROP) in doc or "five best" in doc


def test_the_report_restates_the_rule_it_was_judged_by():
    out = "\n".join(S.render([trade(shares=1e6)], {"known": 1}, "mcl", 1, 0.1, 1))
    assert "PRE-REGISTERED" in out
    assert "dropping its best" in out


# --- the coverage control ---------------------------------------------------

def test_the_coverage_control_is_printed_before_any_bucket():
    """Its whole job is to be read first. A control printed under the table it
    invalidates is a footnote."""
    rows = ([trade(gross=10.0, status="known", shares=1e6 + i) for i in range(60)]
            + [trade(gross=10.0, status="no_cik") for _ in range(40)])
    out = "\n".join(S.render(rows, {"known": 60, "no_cik": 40}, "mcl", 20, 1.0, 1))
    assert out.index("COVERAGE CONTROL") < out.index("IN QUARTILES")


def test_a_biased_subset_is_called_out_not_footnoted():
    """Covered trades winning and uncovered trades losing means every bucket
    below describes a population the rule would not be applied to."""
    rows = ([trade(gross=40.0, status="known", shares=1e6 + i) for i in range(60)]
            + [trade(gross=-40.0, status="no_cik") for _ in range(60)])
    out = "\n".join(S.bias_control(rows))
    assert "DIFFER BY MORE THAN ONE ROUND TRIP" in out
    assert "does not generalise" in out


def test_populations_within_friction_are_not_called_equal():
    """Failing to show a difference is not showing there is none, and the
    report has to say which one it did."""
    rows = ([trade(gross=10.0, status="known", shares=1e6 + i) for i in range(60)]
            + [trade(gross=10.0, status="no_cik") for _ in range(60)])
    out = "\n".join(S.bias_control(rows))
    assert "DIFFER BY MORE THAN" not in out
    assert "fails to show they differ" in out


def test_the_control_charges_friction_to_both_sides():
    rows = ([trade(gross=4.26, status="known", shares=1e6 + i) for i in range(30)]
            + [trade(gross=4.26, status="no_cik") for _ in range(30)])
    out = "\n".join(S.bias_control(rows))
    assert "0.00" in out          # 4.26 gross less 4.26 friction


# --- nothing is dropped -----------------------------------------------------

def test_every_trade_lands_in_a_status_even_with_no_table_row():
    """A symbol-day absent from the as-of table is a different thing from a
    filer with no facts, and both are different from a known figure."""
    got, by_status = S.attach([trade(symbol="ZZZ")],
                              {("AAA", "2026-01-02"): {"status": "known",
                                                       "shares": "1000",
                                                       "lag_days": "5"}})
    assert got[0]["status"] == "not_in_universe_table"
    assert by_status["not_in_universe_table"] == 1


def test_the_status_comes_from_the_table_not_from_whether_shares_parsed():
    got, _ = S.attach([trade()], {("AAA", "2026-01-02"):
                                  {"status": "before_first_filing",
                                   "shares": "", "lag_days": ""}})
    assert got[0]["status"] == "before_first_filing"
    assert "shares" not in got[0]


def test_the_accounting_totals_every_trade():
    rows = [trade(status="known", shares=1e6), trade(status="no_cik"),
            trade(status="stale", shares=2e6)]
    out = "\n".join(S.accounting(rows, {"known": 1, "no_cik": 1, "stale": 1},
                                 "mcl", 5))
    for s in ("known", "no_cik", "stale"):
        assert s in out
    assert "trades              3" in out


def test_a_book_that_does_not_match_the_published_count_stops_the_reader():
    """entry_excursion measured 3,521 trades against pit_strategy's 3,955 under
    a caveat claiming the same tape and warm-up. The check is cheap and the
    failure is silent without it."""
    out = "\n".join(S.accounting([trade(shares=1e6)], {"known": 1}, "mcl", 1))
    assert "DOES NOT MATCH" in out
    assert "Do not read the sections below" in out


def test_the_published_count_is_quoted_from_a_named_source():
    import inspect
    src = inspect.getsource(S)
    assert "pit_strategy_result_20260914" in src


# --- strata -----------------------------------------------------------------

def test_known_and_stale_are_reported_separately():
    rows = (spread(30, [10.0, 10.0, 10.0, 10.0])
            + spread(30, [-10.0, -10.0, -10.0, -10.0], status="stale"))
    out = "\n".join(S.render(rows, {"known": 120, "stale": 120}, "mcl", 20,
                             1.0, 1))
    assert "STRATUM: known" in out
    assert "STRATUM: stale" in out
    assert "STRATUM: known+stale" in out


def test_a_stratum_disagreement_refuses_a_verdict():
    """The same rule as a halves disagreement: one of the two is wrong and
    nothing here says which, so the combined figure is not a tie-break."""
    good = spread(40, [30.0, 30.0, 30.0, 30.0], date="2026-01-02")
    good += spread(40, [30.0, 30.0, 30.0, 30.0], date="2026-06-02")
    bad = spread(40, [-30.0] * 4, date="2026-01-02", status="stale")
    bad += spread(40, [-30.0] * 4, date="2026-06-02", status="stale")
    out = "\n".join(S.render(good + bad, {"known": 320, "stale": 320}, "mcl",
                             40, 1.0, 1))
    assert "REFUSED" in out
    assert "is not a tie-break" in out


# --- the bucket verdict -----------------------------------------------------

def two_halves(per_bucket, status="known"):
    return (spread(40, per_bucket, date="2026-01-02", status=status)
            + spread(40, per_bucket, date="2026-06-02", status=status))


def test_a_profitable_bucket_in_both_halves_clears():
    _, verdict = S.quantile_section(two_halves([30.0, -30.0, -30.0, -30.0]),
                                    "known")
    assert verdict == "CLEARS"


def test_a_bucket_profitable_only_on_its_top_five_does_not_clear():
    """THE WHOLE POINT OF DROP-TOP-N.

    Five trades in eighty carry the cheapest bucket. Both halves come out
    positive -- three of the five fall in one half and two in the other -- and
    the bucket is a fact about five trades, not about the bucket. Exactly five,
    because six would survive dropping five and the test would be asserting
    something weaker than it claims.
    """
    rows, big = [], {"2026-01-02": 3, "2026-06-02": 2}
    for half, n_big in big.items():
        for b, base in enumerate([3.0, -30.0, -30.0, -30.0]):
            for i in range(40):
                g = 2_000.0 if (b == 0 and i < n_big) else base
                rows.append(trade(gross=g, date=half,
                                  shares=(b + 1) * 1e6 + i))
    rows = S.with_net(rows, S.MEASURED_FRICTION)
    a, b_ = S.split(rows)
    from common.entry_features import buckets
    assert buckets(a, "shares", 4)[0]["mean"] > 0
    assert buckets(b_, "shares", 4)[0]["mean"] > 0, "the fixture is not the case"
    _, verdict = S.quantile_section(rows, "known")
    assert verdict != "CLEARS"


def test_a_monotone_unprofitable_gradient_separates_but_does_not_clear():
    _, verdict = S.quantile_section(
        two_halves([-5.0, -15.0, -25.0, -35.0]), "known")
    assert verdict == "SEPARATES"


def test_a_flat_feature_is_nothing():
    _, verdict = S.quantile_section(two_halves([-20.0] * 4), "known")
    assert verdict == "NOTHING"


def test_an_unbucketable_stratum_says_why_rather_than_bucketing_anyway():
    """A run of identical share counts bucketed anyway is list order wearing a
    feature's name -- the tape_density defect, which was large enough to have
    been read as a finding."""
    rows = S.with_net([trade(gross=1.0, shares=5e6) for _ in range(200)],
                      S.MEASURED_FRICTION)
    out, verdict = S.quantile_section(rows, "known")
    assert verdict == "NOTHING"
    assert "not bucketable" in "\n".join(out)


def test_every_bucket_is_printed_including_the_losing_ones():
    out, _ = S.quantile_section(two_halves([-5.0, -15.0, -25.0, -35.0]),
                                "known")
    text = "\n".join(out)
    assert text.count("n=") >= 16       # 4 buckets x all/1st/2nd/less-top5


def test_the_fixed_bands_print_the_empty_ones_too():
    """A band with no trades is a fact about the universe, not a gap."""
    rows = S.with_net([trade(gross=1.0, shares=1e6 + i) for i in range(50)],
                      S.MEASURED_FRICTION)
    out = "\n".join(S.fixed_section(rows))
    assert "no trades" in out
    assert "500M+" in out


def test_the_fixed_bands_are_reported_beside_the_quantiles_not_instead():
    rows = two_halves([-5.0, -15.0, -25.0, -35.0])
    out = "\n".join(S.render(rows, {"known": len(rows)}, "mcl", 40, 1.0, 1))
    assert "IN QUARTILES" in out and "SCANNER'S OWN THRESHOLDS" in out


# --- arithmetic -------------------------------------------------------------

def test_friction_is_charged_per_trade_not_per_book():
    rows = [trade(gross=10.0) for _ in range(10)]
    assert S.net_at(rows, 4.26) == pytest.approx(10 * (10.0 - 4.26))


def test_the_halves_cut_comes_from_the_data():
    rows = [trade(date=f"2026-01-{d:02d}") for d in range(1, 11)]
    a, b = S.split(rows)
    assert a and b and max(r["date"] for r in a) < min(r["date"] for r in b)


def test_drop_top_removes_the_largest_not_the_last():
    rows = [trade(gross=g) for g in (1.0, 99.0, 2.0)]
    assert sorted(r["gross"] for r in S.drop_top(rows, 1)) == [1.0, 2.0]


def test_the_caveats_survive_into_every_report():
    out = "\n".join(S.render([trade(shares=1e6)], {"known": 1}, "mcl", 1, 0.1, 1))
    for line in ("NOT FLOAT", "NOT A RULE", "NOT OUT OF SAMPLE",
                 "NOT A COMPLETE UNIVERSE"):
        assert line in out


def test_the_asof_table_must_exist_before_this_runs():
    with pytest.raises(SystemExit, match="edgar_shares --pull"):
        S.load_asof("var/edgar/does_not_exist.csv")


# --- the pipeline, not just the renderer ------------------------------------

def _frame(sym="AAA", n=330, period=40, amp=0.30, drift=0.004,
           base_v=40_000.0, spike=130_000.0):
    """Two 04:00-09:30 sessions shaped to MCL's real entry conditions. Copied
    from test_entry_split rather than imported, so this file does not depend on
    another test module's internals."""
    import math
    from datetime import date, datetime, time as dtime, timedelta
    from zoneinfo import ZoneInfo

    import pandas as pd
    ET = ZoneInfo("America/New_York")
    D = date(2026, 3, 2)
    idx = []
    for d in (D - timedelta(days=1), D):
        b = pd.Timestamp(datetime.combine(d, dtime(4, 0), tzinfo=ET))
        idx += [(b + timedelta(minutes=i)).tz_convert("UTC") for i in range(n)]
    close = [4.0 + drift * i + amp * math.sin(2 * math.pi * i / period)
             for i in range(len(idx))]
    vol = [spike if i % 3 == 0 else base_v for i in range(len(idx))]
    return pd.DataFrame({"symbol": sym, "open": close,
                         "high": [c + 0.02 for c in close],
                         "low": [c - 0.02 for c in close],
                         "close": close, "volume": vol},
                        index=pd.DatetimeIndex(idx)), D


def test_run_day_produces_trades_from_a_real_frame(monkeypatch):
    """THE TEST A SUITE THAT ONLY FEEDS THE RENDERER CANNOT HAVE."""
    import pandas as pd
    df, D = _frame()
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: df)
    fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert(
        "UTC").isoformat()
    day, out, err = S.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                               [{"symbol": "AAA", "date": D.isoformat(),
                                 "first_seen": fs}], "mcl"))
    assert err == "" and day == D.isoformat()
    assert out, "the fixture produced no trades; the test proves nothing"
    for r in out:
        assert set(r) == {"symbol", "date", "gross"}
        assert r["date"] == D.isoformat()


def test_the_pipeline_joins_to_the_asof_table_end_to_end(monkeypatch, tmp_path):
    """run_day -> attach -> render, with a real as-of CSV on disk. A join keyed
    on the wrong pair produces an empty table that renders perfectly well."""
    import pandas as pd
    from common import edgar_shares as E
    df, D = _frame()
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: df)
    fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert(
        "UTC").isoformat()
    _day, out, _err = S.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                                 [{"symbol": "AAA", "date": D.isoformat(),
                                   "first_seen": fs}], "mcl"))
    p = tmp_path / "universe_shares.csv"
    E.write_csv(p, E.ASOF_COLS, [{"symbol": "AAA", "date": D.isoformat(),
                                  "cik": 1, "shares": 7_500_000.0,
                                  "filed": "2026-02-01", "end": "2025-12-31",
                                  "form": "10-K", "taxonomy": "dei",
                                  "tag": "EntityCommonStockSharesOutstanding",
                                  "lag_days": 29, "status": "known"}])
    trades, by_status = S.attach(out, S.load_asof(p))
    assert by_status.get("known") == len(out), "the join missed every trade"
    assert all(t["shares"] == 7_500_000.0 for t in trades)
    text = "\n".join(S.render(trades, by_status, "mcl", 1, 1.0, 1))
    assert "COVERAGE CONTROL" in text and "THE VERDICT" in text


def test_the_join_key_is_the_symbol_and_the_session(monkeypatch, tmp_path):
    """Keyed on symbol alone, every session of a name would get whichever row
    happened to be last -- a point-in-time figure applied out of its time."""
    from common import edgar_shares as E
    p = tmp_path / "u.csv"
    E.write_csv(p, E.ASOF_COLS, [
        {"symbol": "AAA", "date": "2026-01-02", "shares": 1_000_000.0,
         "status": "known", "lag_days": 5},
        {"symbol": "AAA", "date": "2026-06-02", "shares": 9_000_000.0,
         "status": "known", "lag_days": 5}])
    asof = S.load_asof(p)
    got, _ = S.attach([trade(date="2026-01-02"), trade(date="2026-06-02")], asof)
    assert [t["shares"] for t in got] == [1_000_000.0, 9_000_000.0]
