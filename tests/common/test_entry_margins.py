#!/usr/bin/env python3
r"""By how much each entry clause passed, and the ways that can be misread.

Three shapes of error this file exists for.

A THRESHOLD MEASURED AGAINST THE WRONG NUMBER. Every margin here is computed
against the constant the strategy actually applies. If `VOL_MULTIPLE` moves in
`mcl.py` and this module keeps its own 3.0, the report is a measurement of a
rule nobody is running, and it looks identical to a correct one.

A PERCENTILE READ AS AN ABSOLUTE. Ranking six margins in six units against each
other is the only way to ask which clause was binding, and a rank cannot say
the population is marginal: if every entry cleared by a hair, the tightest
would still rank 0 and the loosest 100. The raw section has to come first and
the limit has to be printed.

A THRESHOLD SEARCH WEARING A LADDER'S CLOTHES. Printing eight dollar floors and
reading off the best one is choosing a threshold after seeing its outcome. The
ladder prints every level, in both halves, and recommends none.

The last section drives `run_day` against a real frame, because a suite that
only feeds the renderer proves nothing about the pipeline.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from common import entry_margins as M


def row(gross=0.0, date="2026-01-02", price=5.0, **kw):
    r = {"symbol": "AAA", "date": date, "gross": gross, "located": True,
         "entry_price": price,
         "vol_multiple": 5.0, "floor_margin": 1.0, "macd_margin": 0.05,
         "macd_level": 0.10, "rsi_slope": 4.0, "mfi_slope": 3.0,
         "dollar_vol_bar": 200_000.0, "dollar_vol_session": 5_000_000.0}
    r.update(kw)
    return r


def book(n=200, col="vol_multiple", lo=3.0, step=0.05, gross=lambda i: -10.0):
    out = []
    for half in ("2026-01-02", "2026-06-02"):
        for i in range(n):
            out.append(row(gross=gross(i), date=half, **{col: lo + i * step}))
    M.derive(out)
    return out


# --- the thresholds are the strategy's, not this module's -------------------

def test_every_threshold_matches_the_strategy_constant():
    """THE GUARD THAT MATTERS MOST HERE. A margin measured against a stale
    threshold is a measurement of a rule nobody is running, and it renders
    exactly like a correct one."""
    from strategy.mcl import mcl as MCL
    assert M.CLAUSES["vol_multiple"][2] == MCL.VOL_MULTIPLE
    assert M.CLAUSES["floor_margin"][2] == MCL.FLOOR_FRACTION
    for col in ("macd_margin", "macd_level", "rsi_slope", "mfi_slope"):
        assert M.CLAUSES[col][2] == 0.0, f"{col} is a sign test, not a level"


def test_the_three_bar_reference_is_the_strategys_lookback():
    """`rsi - rsi[3]` is only the right expression while TREND_LOOKBACK is 3."""
    from strategy.mcl import mcl as MCL
    assert MCL.TREND_LOOKBACK == 3
    assert "[3]" in M.CLAUSES["rsi_slope"][0]
    assert "[3]" in M.CLAUSES["mfi_slope"][0]


def test_the_clause_list_covers_every_condition_the_rule_ands_together():
    """MCL's entry is c_macd & c_mfi & c_rsi & c_vol & c_floor. c_macd is two
    tests, so six columns. A clause added to the strategy and not here is a
    margin nobody measures."""
    src = Path("strategy/mcl/mcl.py").read_text(encoding="utf-8")
    line = [l for l in src.splitlines() if 'out["entry"] = ' in l]
    assert line, "the entry expression moved; this test cannot see it"
    joined = " ".join(src.split('out["entry"] = ')[1].split(")")[0].split())
    for cond in ("c_macd", "c_mfi", "c_rsi", "c_vol", "c_floor"):
        assert cond in joined
    assert len(M.CLAUSES) == 6


def test_features_at_is_imported_rather_than_reimplemented():
    """A second copy with its own idea of trail_avg produces figures that look
    comparable with entry_features' and are not."""
    tree = ast.parse(Path("common/entry_margins.py").read_text(encoding="utf-8"))
    names = {n.name for node in ast.walk(tree)
             if isinstance(node, ast.ImportFrom)
             for n in node.names}
    assert "features_at" in names and "frame_ctx" in names
    src = Path("common/entry_margins.py").read_text(encoding="utf-8")
    assert "def features_at" not in src


# --- pre-registration -------------------------------------------------------

def test_the_rule_is_written_down_before_the_run():
    for word in ("PRE-REGISTERED", "CLEARS", "SEPARATES", "NOTHING"):
        assert word in M.__doc__


def test_the_report_restates_the_rule():
    out = "\n".join(M.render(book(), "mcl", 10, 1.0, 1))
    assert "PRE-REGISTERED" in out and "dropping its best" in out


# --- absolute before relative ----------------------------------------------

def test_the_raw_figures_come_before_the_percentiles():
    """Only the raw section can answer whether the entries were thin at all."""
    out = "\n".join(M.render(book(), "mcl", 10, 1.0, 1))
    assert out.index("PAST ITS OWN THRESHOLD") < out.index("BINDING ONE")


def test_the_percentile_limit_is_printed_not_assumed():
    out = "\n".join(M.render(book(), "mcl", 10, 1.0, 1))
    assert "cannot say the population is marginal" in out


def test_the_absolute_section_says_no_clause_reads_liquidity():
    out = "\n".join(M.absolute_section([row()]))
    assert "no entry clause reads this" in out


def test_every_dollar_level_is_printed():
    out = "\n".join(M.absolute_section([row()]))
    for lvl in M.DOLLAR_FLOORS:
        assert f"{lvl:,.0f}" in out


def test_a_hair_is_defined_per_column_and_printed():
    out = "\n".join(M.absolute_section([row()]))
    for col in M.CLAUSES:
        assert f"a hair, {col}" in out


def test_the_hair_test_counts_the_marginal_entries():
    rows = [row(vol_multiple=3.01) for _ in range(3)] + [row() for _ in range(7)]
    M.derive(rows)
    out = "\n".join(M.absolute_section(rows))
    line = [l for l in out.splitlines() if l.strip().startswith("vol_multiple")][0]
    assert "30.0%" in line


def test_macd_is_expressed_in_basis_points_of_price():
    """0.01 of MACD is a different thing on a $2 stock and a $25 one, and the
    screen admits both."""
    rows = M.derive([row(price=5.0, macd_margin=0.005)])
    assert rows[0]["macd_bps"] == pytest.approx(10.0)


def test_a_missing_price_does_not_become_a_zero_margin():
    rows = M.derive([row(price=0.0, macd_margin=0.005)])
    assert rows[0]["macd_bps"] is None


# --- ranks and the binding clause -------------------------------------------

def test_ties_are_not_split_by_list_order():
    """A run of identical values sorted is not reordered, so bucketing one is
    the entry order of the pairs file wearing a feature's name."""
    rows = [row(vol_multiple=3.0) for _ in range(10)]
    M.pct_ranks(rows, "vol_multiple")
    assert len({r["vol_multiple_pct"] for r in rows}) == 1


def test_the_binding_clause_is_the_tightest_one():
    """vol_multiple ASCENDS and every other column DESCENDS, so row 0 is the
    tightest on vol_multiple and the loosest on all five others. Without that
    the fixture ties five columns at rank 0 and the answer falls out of
    alphabetical order rather than out of the data."""
    rows = []
    for i in range(20):
        rows.append(row(vol_multiple=3.0 + i * 0.01,
                        floor_margin=100.0 - i, macd_margin=100.0 - i,
                        macd_level=100.0 - i, rsi_slope=100.0 - i,
                        mfi_slope=100.0 - i))
    M.add_slack(rows)
    assert rows[0]["binding"] == "vol_multiple"
    assert rows[0]["min_slack"] == 0.0
    # and the loosest row on vol_multiple is binding on something else
    assert rows[-1]["binding"] != "vol_multiple"


def test_a_constant_column_is_excluded_from_the_binding_comparison():
    """It ranks 0 on every row, so it would be named binding on every entry --
    a column that measures nothing, presented as the thing that nearly stopped
    every trade."""
    rows = [row(vol_multiple=3.0 + i * 0.01, floor_margin=1.0) for i in range(20)]
    _r, flat = M.add_slack(rows)
    assert "floor_margin" in flat
    assert all(r["binding"] != "floor_margin" for r in rows)
    out = "\n".join(M.binding_section(rows, flat))
    assert "EXCLUDED, one value across the book" in out


def test_a_row_with_no_usable_margin_gets_none_not_zero():
    rows = [{"symbol": "A", "date": "d", "gross": 0.0, "located": True}]
    M.add_slack(rows)
    assert rows[0]["min_slack"] is None and rows[0]["binding"] == "none"


def test_the_binding_census_names_a_clause_that_never_binds():
    out = "\n".join(M.binding_section(
        [dict(row(), binding="vol_multiple") for _ in range(10)]))
    assert "vol_multiple" in out
    assert "being carried by the others" in out


def test_the_slack_columns_survive_the_copy_into_the_scored_rows():
    """`with_net` copies each row; a derived column written before it and not
    carried across would leave min_slack absent and its section silently
    unbucketable."""
    out = "\n".join(M.render(book(), "mcl", 10, 1.0, 1))
    assert "min_slack" in out
    assert "min_slack   n=0" not in out


# --- nothing is dropped -----------------------------------------------------

def test_an_unlocated_entry_bar_is_counted_not_dropped():
    rows = [row() for _ in range(9)]
    rows.append({"symbol": "A", "date": "d", "gross": 1.0, "located": False})
    out = "\n".join(M.population(rows, "mcl", 5))
    assert "trades              10" in out
    assert "1 NOT located" in out


def test_a_book_that_does_not_match_the_published_count_stops_the_reader():
    out = "\n".join(M.population([row()], "mcl", 1))
    assert "DOES NOT MATCH" in out
    assert "Do not read the" in out and "sections below" in out


# --- the ladder is not a search ---------------------------------------------

def test_the_ladder_prints_every_level_in_both_halves():
    out = "\n".join(M.ladder_section(M.with_net(book(), M.MEASURED_FRICTION)))
    for lvl in M.DOLLAR_FLOORS:
        assert f"{lvl:,.0f}" in out
    assert "1st" in out and "2nd" in out


def test_the_ladder_recommends_nothing_and_says_why():
    out = "\n".join(M.ladder_section(M.with_net(book(), M.MEASURED_FRICTION)))
    assert "nothing recommended" in out
    assert "is not a rule" in out


def test_the_ladder_carries_a_no_floor_baseline():
    """Without it every row looks like an improvement or a loss against
    nothing, and the reader supplies the comparison from memory."""
    out = "\n".join(M.ladder_section(M.with_net(book(), M.MEASURED_FRICTION)))
    assert "baseline, no floor" in out


# --- verdicts ---------------------------------------------------------------

def test_a_profitable_bucket_in_both_halves_clears():
    rows = M.with_net(book(gross=lambda i: 30.0 if i < 50 else -30.0),
                      M.MEASURED_FRICTION)
    _, v = M.one_column(rows, "vol_multiple")
    assert v == "CLEARS"


def test_a_monotone_unprofitable_gradient_separates():
    rows = M.with_net(book(gross=lambda i: -5.0 - i * 0.3), M.MEASURED_FRICTION)
    _, v = M.one_column(rows, "vol_multiple")
    assert v == "SEPARATES"


def test_a_flat_margin_is_nothing():
    rows = M.with_net(book(), M.MEASURED_FRICTION)
    _, v = M.one_column(rows, "vol_multiple")
    assert v == "NOTHING"


def test_a_column_with_no_spread_says_why_rather_than_bucketing():
    rows = M.with_net([row(vol_multiple=3.0) for _ in range(200)],
                      M.MEASURED_FRICTION)
    out, v = M.one_column(rows, "vol_multiple")
    assert v == "NOTHING" and "not bucketable" in "\n".join(out)


def test_the_nothing_verdict_answers_the_question_it_was_built_for():
    out = "\n".join(M.render(book(), "mcl", 10, 1.0, 1))
    assert "the entries ARE thin" in out
    assert "not what is losing the money" in out


def test_multiplicity_admits_the_overlap_with_entry_features():
    out = "\n".join(M.render(book(), "mcl", 10, 1.0, 1))
    assert "not independent evidence" in out


def test_mc5_is_refused_rather_than_measured_on_mcls_features():
    with pytest.raises(SystemExit):
        M.build_parser().parse_args(["--strategy", "mc5"])


# --- the pipeline -----------------------------------------------------------

def _frame(sym="AAA", n=330, period=40, amp=0.30, drift=0.004,
           base_v=40_000.0, spike=130_000.0):
    """Two 04:00-09:30 sessions shaped to MCL's real entry conditions."""
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


def test_run_day_produces_a_margin_for_every_clause(monkeypatch):
    import pandas as pd
    df, D = _frame()
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: df)
    fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert(
        "UTC").isoformat()
    day, out, err = M.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                               [{"symbol": "AAA", "date": D.isoformat(),
                                 "first_seen": fs}], "mcl"))
    assert err == "" and day == D.isoformat()
    assert out, "the fixture produced no trades; the test proves nothing"
    for r in out:
        assert r["located"] is True
        for col in M.CLAUSES:
            assert r.get(col) is not None, f"{col} missing from a real entry"
        assert r["dollar_vol_bar"] and r["dollar_vol_session"]


def test_every_real_entry_actually_passed_the_clauses_it_is_measured_on(
        monkeypatch):
    """THE SANITY CHECK ON THE WHOLE INSTRUMENT. If a measured margin is
    negative, the bar the features were read from is not the bar the trade
    entered on -- an off-by-one that would render as a perfectly plausible
    table of margins."""
    import pandas as pd
    df, D = _frame()
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: df)
    fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert(
        "UTC").isoformat()
    _d, out, _e = M.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                             [{"symbol": "AAA", "date": D.isoformat(),
                               "first_seen": fs}], "mcl"))
    assert out
    for r in out:
        assert r["vol_multiple"] >= M.CLAUSES["vol_multiple"][2]
        assert r["floor_margin"] >= M.CLAUSES["floor_margin"][2]
        assert r["macd_margin"] > 0 and r["macd_level"] > 0
        assert r["rsi_slope"] > 0 and r["mfi_slope"] > 0


def test_the_report_renders_from_real_rows_end_to_end(monkeypatch):
    import pandas as pd
    df, D = _frame()
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: df)
    fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert(
        "UTC").isoformat()
    _d, out, _e = M.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                             [{"symbol": "AAA", "date": D.isoformat(),
                               "first_seen": fs}], "mcl"))
    M.derive(out)
    text = "\n".join(M.render(out, "mcl", 1, 1.0, 1))
    assert "PAST ITS OWN THRESHOLD" in text and "THE VERDICT" in text


# --- the gaps the mutation pass found ---------------------------------------

class _Trade:
    def __init__(self, entry_time, entry_price=5.0, exit_price=5.5):
        self.entry_time, self.entry_price, self.exit_price = (
            entry_time, entry_price, exit_price)


def test_a_trade_whose_entry_bar_is_absent_is_kept_and_flagged():
    """THE BRANCH THAT WOULD SHORTEN THE TABLE IN SILENCE. A `continue` here
    drops the trade, the book gets smaller, and nothing says so."""
    import pandas as pd
    from common.entry_features import frame_ctx
    from strategy.mcl import mcl as MCL
    df, D = _frame()
    sig = MCL.signals(df)
    ctx = frame_ctx(sig)
    missing = sig.index[0] - pd.Timedelta(minutes=7)
    r = M.margin_row(sig, ctx, _Trade(missing), "AAA", D.isoformat())
    assert r["located"] is False
    assert r["gross"] == pytest.approx((5.5 - 5.0) * M.QTY)
    assert "vol_multiple" not in r, "an unlocated row must not carry margins"


def test_a_located_trade_carries_every_clause():
    from common.entry_features import frame_ctx
    from strategy.mcl import mcl as MCL
    df, D = _frame()
    sig = MCL.signals(df)
    r = M.margin_row(sig, frame_ctx(sig), _Trade(sig.index[200]), "AAA",
                     D.isoformat())
    assert r["located"] is True
    for col in M.CLAUSES:
        assert col in r


def test_a_hair_test_that_cannot_be_evaluated_reads_n_a_not_zero():
    """NONE IS NOT ZERO. Swallowing a KeyError made a derived column that was
    never computed report 0.0% marginal entries -- which reads exactly like a
    book with no marginal entries in it."""
    rows = [row() for _ in range(5)]        # NOT passed through derive()
    assert M.hair_count(rows, "macd_margin") is None
    out = "\n".join(M.absolute_section(rows))
    assert "n/a" in out
    assert "COULD NOT BE EVALUATED" in out
    assert "not as zero" in out


def test_a_hair_test_that_can_be_evaluated_reports_a_percentage():
    rows = M.derive([row() for _ in range(5)])
    assert M.hair_count(rows, "macd_margin") == 0
    assert "n/a" not in "\n".join(M.absolute_section(rows))


def test_the_raw_section_is_emitted_before_the_binding_census():
    """Not just computed first -- PRINTED first. The percentile sections cannot
    answer whether the entries were thin, and a reader who meets them first
    will answer it from them anyway."""
    src = Path("common/entry_margins.py").read_text(encoding="utf-8")
    body = src.split("def render(")[1]
    assert body.index("absolute_section(located)") < body.index("binding_section(")
