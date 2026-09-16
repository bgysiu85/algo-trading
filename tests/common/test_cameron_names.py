#!/usr/bin/env python3
"""Item 1c, and the ways a contaminated comparison could read as a clean one.

The registration (`docs/research/REGISTERED_cameron_names.md`, commit
`f1fa64c`) fixes the arms and the reading BEFORE any number exists, because the
obvious version of this test is rigged: he names the symbol he traded, in a
recap published after the close, so his arm is picked with the whole session
known and ours is picked at a tick.

These assertions guard the parts that would turn a rigged comparison into a
confident one:

  * a control drawn from the wrong pool, which still produces a plausible
    number and nothing else would catch;
  * a rate whose denominator the control cannot match;
  * absent names dropped, which computes the rank distribution over exactly
    the names our screen likes and then reports that our screen likes them;
  * `best_rank` and `first_rank` pooled -- two numbers that look comparable
    and are not;
  * a halves verdict that reads a half the same page refused;
  * the registered one-directional reading quietly going missing from the
    report when the numbers come out favourable.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from common import cameron_names as CN

REPO = Path(__file__).resolve().parents[2]
REGISTRATION = REPO / "docs" / "research" / "REGISTERED_cameron_names.md"


def pit(spec: dict[str, list[tuple[str, int, int]]]) -> dict:
    """{date: [(symbol, first_rank, best_rank)]} -> the loaded-pairs shape."""
    return {d: {s: {"symbol": s, "date": d, "first_rank": fr, "best_rank": br,
                    "first_seen": f"{d}T08:00:00+00:00", "ticks_on": 10,
                    "prior_source": "repaired"}
                for s, fr, br in rows}
            for d, rows in spec.items()}


def days(n: int, per: int, start: int = 1) -> dict:
    """`n` sessions of `per` names each, ranks 1..per."""
    return pit({f"2026-01-{i:02d}": [(f"S{i}{k}", k, k)
                                     for k in range(1, per + 1)]
                for i in range(start, start + n)})


# ==========================================================================
# PARSING HIS CORPUS
# ==========================================================================
def test_a_multi_symbol_cell_becomes_several_mentions(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("publish_date,videoId,symbols\n"
                 "2026-01-02,v1,ABC;DEF\n"
                 "2026-01-03,v2,GHI\n", encoding="utf-8")
    m, _ = CN.mentions(p)
    assert [x["symbol"] for x in m] == ["ABC", "DEF", "GHI"]


def test_a_row_he_said_nothing_about_contributes_nothing(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("publish_date,videoId,symbols\n2026-01-02,v1,?\n"
                 "2026-01-03,v2,\n", encoding="utf-8")
    m, _ = CN.mentions(p)
    assert m == []


def test_what_cannot_be_parsed_is_COUNTED_not_silently_dropped(tmp_path):
    """A filter that quietly removes what it cannot read reports a coverage
    rate over the rows it happened to understand."""
    p = tmp_path / "c.csv"
    p.write_text("publish_date,videoId,symbols\n"
                 "2026-01-02,v1,SPACEX;ABC\n"
                 "2026-01-03,v2,TOOLONGXX\n"
                 ",v3,ZZZ\n", encoding="utf-8")
    m, dropped = CN.mentions(p)
    assert [x["symbol"] for x in m] == ["ABC"]
    assert dropped == {"not a ticker": 1, "unparseable": 1,
                       "no publish date": 1}


def test_the_real_census_still_yields_the_mentions_this_rests_on():
    m, _ = CN.mentions(REPO / CN.CENSUS)
    assert len(m) == 629, "SPACEX is the one excluded name of 630"
    assert len({x["symbol"] for x in m}) == 409


# ==========================================================================
# MAPPING AND DE-DUPLICATION
# ==========================================================================
def test_a_weekend_recap_maps_back_to_the_friday():
    s = {"2026-03-06", "2026-03-09"}
    assert CN.map_to_session("2026-03-08", s) == "2026-03-06"


def test_the_search_never_runs_forward_into_a_later_session():
    assert CN.map_to_session("2026-03-06", {"2026-03-10"}) is None


def test_two_recaps_naming_the_same_symbol_day_count_ONCE():
    """Counting it twice weights a name by how often he talked about it rather
    than by how often our screen had to find it."""
    ment = [{"publish_date": "2026-01-02", "symbol": "ABC", "videoId": "a"},
            {"publish_date": "2026-01-02", "symbol": "ABC", "videoId": "b"}]
    sd, unmapped, dupes = CN.to_symbol_days(ment, {"2026-01-02"})
    assert len(sd) == 1 and dupes == 1 and unmapped == 0


def test_the_same_symbol_on_two_sessions_is_two_pairs():
    ment = [{"publish_date": "2026-01-02", "symbol": "ABC", "videoId": "a"},
            {"publish_date": "2026-01-03", "symbol": "ABC", "videoId": "b"}]
    sd, _, dupes = CN.to_symbol_days(ment, {"2026-01-02", "2026-01-03"})
    assert len(sd) == 2 and dupes == 0


def test_the_three_counts_account_for_every_mention():
    """mapped + unmapped + duplicates == what went in. A join that loses rows
    shrinks the sample without saying so."""
    ment = [{"publish_date": "2026-01-02", "symbol": "ABC", "videoId": "a"},
            {"publish_date": "2026-01-02", "symbol": "ABC", "videoId": "b"},
            {"publish_date": "2020-01-02", "symbol": "XYZ", "videoId": "c"}]
    sd, unmapped, dupes = CN.to_symbol_days(ment, {"2026-01-02"})
    assert len(sd) + unmapped + dupes == len(ment)


# ==========================================================================
# COVERAGE
# ==========================================================================
def test_a_name_we_never_carried_is_ABSENT_and_still_counted():
    """THE ONE THAT MATTERS. Dropping the absent names computes the rank
    distribution over exactly the names our screen likes."""
    u = pit({"2026-01-02": [("AAA", 1, 1)]})
    cov = CN.coverage([{"date": "2026-01-02", "symbol": "AAA"},
                       {"date": "2026-01-02", "symbol": "ZZZ"}], u)
    assert cov["n_all"] == 2
    assert len(cov["present"]) == 1 and len(cov["absent"]) == 1


def test_best_rank_and_first_rank_are_counted_SEPARATELY():
    """A name that touched rank 3 at 09:25 was not on a five-name watchlist at
    05:00. Pooled, the report would claim it was."""
    u = pit({"2026-01-02": [("AAA", 9, 2)]})
    cov = CN.coverage([{"date": "2026-01-02", "symbol": "AAA"}], u)
    assert cov["best"] == {2: 1} and cov["first"] == {9: 1}
    assert cov["top_best"] == 1 and cov["top_first"] == 0


def test_the_top_cut_is_inclusive_at_exactly_TOP_N():
    u = pit({"2026-01-02": [("AAA", CN.TOP_N, CN.TOP_N),
                            ("BBB", CN.TOP_N + 1, CN.TOP_N + 1)]})
    cov = CN.coverage([{"date": "2026-01-02", "symbol": "AAA"},
                       {"date": "2026-01-02", "symbol": "BBB"}], u)
    assert cov["top_best"] == 1


def test_the_present_rate_is_the_denominator_the_control_can_match():
    """His rate over ALL mentions is deflated by names our screen never had;
    the control is drawn from our universe and is present by construction.
    Comparing those two is two numbers that look comparable and are not."""
    u = pit({"2026-01-02": [("AAA", 1, 1)]})
    cov = CN.coverage([{"date": "2026-01-02", "symbol": "AAA"},
                       {"date": "2026-01-02", "symbol": "ZZZ"}], u)
    assert CN.top_rate(cov) == 100.0          # 1 of 1 present
    assert cov["top_best"] / cov["n_all"] == 0.5


# ==========================================================================
# THE CONTROL — the piece most able to lie plausibly
# ==========================================================================
def test_the_draw_matches_its_own_closed_form():
    """THE CHECK ON THE CHECK. A control that sampled the pooled universe
    instead of the session's own would still return a believable percentage.
    Only agreement with min(N, n)/n says which pool it drew from."""
    u = days(12, per=10)
    sd = [{"date": d, "symbol": next(iter(u[d]))} for d in u]
    c = CN.control(sd, u, draws=400, seed=1)
    assert abs(c["mean"] - CN.expected_top_rate(sd, u)) < 3.0


def test_the_closed_form_is_min_N_over_n_and_not_N_over_n():
    """On a session with fewer than TOP_N names EVERY name is in the top N,
    and N/n would put the control above 100%."""
    u = days(1, per=2)
    sd = [{"date": "2026-01-01", "symbol": "S11"}]
    assert CN.expected_top_rate(sd, u) == 100.0


def test_the_control_draws_from_the_SAME_session_not_the_pool():
    """Two sessions, one tiny and one huge. Drawn from the pool, the control
    inherits the big session's ranks and the small session's easy top-5 rate
    disappears."""
    u = pit({"2026-01-01": [("A", 1, 1), ("B", 2, 2)],
             "2026-01-02": [(f"C{k}", k, k) for k in range(1, 41)]})
    sd = [{"date": "2026-01-01", "symbol": "A"}]
    c = CN.control(sd, u, draws=300, seed=7)
    assert c["mean"] == 100.0, "only the two-name session may be drawn from"


def test_the_control_is_reproducible_from_its_seed():
    u = days(8, per=9)
    sd = [{"date": d, "symbol": next(iter(u[d]))} for d in u]
    a = CN.control(sd, u, draws=100, seed=42)
    b = CN.control(sd, u, draws=100, seed=42)
    assert a["rates"] == b["rates"]
    assert CN.control(sd, u, draws=100, seed=43)["rates"] != a["rates"]


def test_a_session_with_no_universe_is_skipped_by_both_control_and_form():
    """Or the two disagree for a reason that has nothing to do with the pool,
    and the check above starts failing for the wrong cause."""
    u = days(2, per=6)
    sd = [{"date": d, "symbol": next(iter(u[d]))} for d in u]
    sd.append({"date": "2099-01-01", "symbol": "GHOST"})
    assert CN.control(sd, u, draws=50, seed=3)["n"] == 2


def test_beat_rate_is_the_share_of_draws_reaching_the_observed_rate():
    assert CN.beat_rate(50.0, [10.0, 50.0, 90.0]) == pytest.approx(2 / 3)
    assert CN.beat_rate(99.0, [10.0, 50.0, 90.0]) == 0.0


# ==========================================================================
# THE ARMS
# ==========================================================================
def test_both_arms_come_from_the_same_pair_records():
    """A name cannot be ranked from one tape and scored on another. There is
    one universe object here and both arms are subsets of it."""
    u = pit({"2026-01-02": [("AAA", 1, 1), ("BBB", 9, 9), ("CCC", 3, 3)]})
    his, ours = CN.arm_universes([{"date": "2026-01-02", "symbol": "BBB"}], u)
    assert [r["symbol"] for r in his["2026-01-02"]] == ["BBB"]
    assert sorted(r["symbol"] for r in ours["2026-01-02"]) == ["AAA", "CCC"]
    assert all(r is u["2026-01-02"][r["symbol"]] for r in his["2026-01-02"])


def test_the_OURS_arm_is_the_top_cut_and_not_the_whole_universe():
    u = pit({"2026-01-02": [(f"S{k}", k, k) for k in range(1, 15)]})
    _, ours = CN.arm_universes([{"date": "2026-01-02", "symbol": "S1"}], u)
    assert len(ours["2026-01-02"]) == CN.TOP_N


def test_only_sessions_he_named_something_on_enter_either_arm():
    """Scoring OURS over sessions with no mention would compare his 242 days
    against our 551 and call the difference selection."""
    u = days(4, per=8)
    one = sorted(u)[0]
    his, ours = CN.arm_universes(
        [{"date": one, "symbol": next(iter(u[one]))}], u)
    assert set(his) == set(ours) == {one}


# ==========================================================================
# THE HALVES
# ==========================================================================
def test_the_split_is_the_projects_split():
    from common.regime_study import halves_split
    sd = [{"date": f"2026-01-{i:02d}", "symbol": "A"} for i in range(1, 11)]
    e, l = CN.halves(sd)
    cut = halves_split([x["date"] for x in sd])
    assert all(x["date"] < cut for x in e) and all(x["date"] >= cut for x in l)
    assert len(e) + len(l) == len(sd)


# ==========================================================================
# THE REPORT — the text is the only part anyone reads
# ==========================================================================
def report(cov, ctrl, exp, early=None, late=None, ctrl_e=None, ctrl_l=None,
           causes=None, pnl=None, dropped=None):
    thick = {"mean": 40.0, "rates": [40.0] * 100, "n": 50}
    return "\n".join(CN.render(
        cov, ctrl, exp,
        early if early is not None else cov,
        late if late is not None else cov,
        ctrl_e if ctrl_e is not None else thick,
        ctrl_l if ctrl_l is not None else thick,
        dropped or {"not a ticker": 1}, 4, 3, causes, pnl, 242, 1.0))


def cov_at(n_present, n_top, n_absent=0):
    """A coverage dict with EXACTLY `n_top` of `n_present` names inside the top
    cut, spread over as many sessions as it takes.

    Spread, because a single session has only TOP_N ranks at or under TOP_N --
    an earlier version of this helper asked one session for twenty top-five
    names, got five, and every threshold test around it passed for the wrong
    reason. A fixture that cannot express the case under test is worse than no
    fixture: it is a green assertion about something else.
    """
    import datetime as _dt
    spec, sd = {}, []
    need_top, need_rest = n_top, n_present - n_top
    assert need_rest >= 0
    day = 0
    while need_top or need_rest:
        day += 1
        d = (_dt.date(2026, 1, 1) + _dt.timedelta(days=day)).isoformat()
        spec[d] = [(f"S{day}x{k}", k, k) for k in range(1, 2 * CN.TOP_N + 1)]
        t = min(CN.TOP_N, need_top)
        sd += [{"date": d, "symbol": f"S{day}x{k}"} for k in range(1, t + 1)]
        need_top -= t
        r = min(CN.TOP_N, need_rest)
        sd += [{"date": d, "symbol": f"S{day}x{k}"}
               for k in range(CN.TOP_N + 1, CN.TOP_N + 1 + r)]
        need_rest -= r
    if not spec:
        spec["2026-01-02"] = [("S1x1", 1, 1)]
    first = sorted(spec)[0]
    sd += [{"date": first, "symbol": f"Z{k}"} for k in range(n_absent)]
    return CN.coverage(sd, pit(spec))


def test_the_fixture_makes_the_rate_it_claims_to():
    """The helper above decides what every threshold test below is actually
    testing, so it is checked rather than trusted."""
    for present, top in ((20, 20), (20, 0), (100, 66), (7, 3)):
        c = cov_at(present, top)
        assert len(c["present"]) == present
        assert c["top_best"] == top
        assert CN.top_rate(c) == pytest.approx(100.0 * top / present)


def test_the_registered_one_directional_reading_is_always_on_the_page():
    """It has to survive a FAVOURABLE result, which is the only time anyone
    would want it gone."""
    cov = cov_at(20, 20)                      # 100% in the top 5
    txt = report(cov, {"mean": 20.0, "rates": [20.0] * 100, "n": 20}, 20.0)
    assert "he TRADED" in txt
    assert "settles nothing" in txt
    assert "PASSES the registered margin" in txt
    assert "does NOT say: that his names are better" in txt


def test_a_null_says_item_1c_is_CLOSED():
    """The whole point of the design: only a null closes anything, so the null
    has to actually say so rather than leaving the reader to infer it."""
    cov = cov_at(20, 4)
    txt = report(cov, {"mean": 20.0, "rates": [20.0] * 100, "n": 20}, 20.0)
    assert "DOES NOT pass the registered margin" in txt
    assert "CLOSED" in txt
    assert "name selection is not where the gap is" in txt


def test_the_margin_is_a_real_threshold():
    """Just inside and just outside must read differently, or MARGIN_PP could
    be any number and nothing would notice."""
    ctrl = {"mean": 50.0, "rates": [50.0] * 100, "n": 20}
    inside = report(cov_at(100, 64), ctrl, 50.0)    # 64% - 50% = 14pp
    outside = report(cov_at(100, 66), ctrl, 50.0)   # 66% - 50% = 16pp
    assert "DOES NOT pass" in inside
    assert "PASSES the registered margin" in outside


def test_a_draw_that_disagrees_with_its_closed_form_is_SHOUTED():
    """The control is the piece that can be wrong and still look right. If the
    two ever part company the report must not print a tidy gap underneath."""
    cov = cov_at(20, 10)
    txt = report(cov, {"mean": 20.0, "rates": [20.0] * 100, "n": 20}, 55.0)
    assert "sampling the wrong pool" in txt


def test_an_agreeing_draw_is_marked_OK_rather_than_left_silent():
    cov = cov_at(20, 10)
    txt = report(cov, {"mean": 20.0, "rates": [20.0] * 100, "n": 20}, 20.4)
    assert "sampling the wrong pool" not in txt
    assert "draw vs form" in txt


def test_both_denominators_are_printed_and_only_one_is_compared():
    cov = cov_at(20, 10, n_absent=30)
    txt = report(cov, {"mean": 20.0, "rates": [20.0] * 100, "n": 20}, 20.0)
    assert "over ALL" in txt
    assert "NOT comparable to the control" in txt
    assert "<- the criterion" in txt


def test_every_rank_is_printed_not_only_the_top_five():
    """Nothing ranked, every bucket printed. A table that stops at 5 hides
    whether the rest cluster at 6 or at 40."""
    u = pit({"2026-01-02": [("A", 1, 1), ("B", 12, 12)]})
    cov = CN.coverage([{"date": "2026-01-02", "symbol": "A"},
                       {"date": "2026-01-02", "symbol": "B"}], u)
    txt = report(cov, {"mean": 20.0, "rates": [20.0] * 100, "n": 2}, 20.0)
    body = txt.split("2. THE RANK WE GAVE THEM")[1]
    for r in range(1, 13):
        assert re.search(rf"^\s+{r}\s", body, re.M), f"rank {r} missing"


def test_the_declined_names_are_reported_with_their_cause():
    from collections import Counter
    cov = cov_at(10, 5, n_absent=7)
    txt = report(cov, {"mean": 20.0, "rates": [20.0] * 100, "n": 10}, 20.0,
                 causes=Counter({"VOLUME": 5, "NOT ON THIS TAPE": 2}))
    assert "WHY WE DECLINED THE REST" in txt
    assert "VOLUME" in txt and "NOT ON THIS TAPE" in txt
    assert "turning down a name he traded" in txt


def test_halves_pointing_opposite_ways_refuse_the_verdict():
    lo = {"mean": 80.0, "rates": [80.0] * 100, "n": 20}
    hi = {"mean": 10.0, "rates": [10.0] * 100, "n": 20}
    txt = report(cov_at(20, 10), {"mean": 40.0, "rates": [40.0] * 100,
                                  "n": 20}, 40.0,
                 early=cov_at(20, 2), late=cov_at(20, 18),
                 ctrl_e=lo, ctrl_l=hi)
    assert "THE HALVES DISAGREE" in txt


def test_halves_that_straddle_the_criterion_refuse_too():
    """One half passing and one failing is not a pooled pass, whatever the
    pooled number says."""
    c = {"mean": 40.0, "rates": [40.0] * 100, "n": 20}
    txt = report(cov_at(20, 10), c, 40.0,
                 early=cov_at(20, 4), late=cov_at(20, 16),
                 ctrl_e=c, ctrl_l=c)
    assert "THE HALVES DISAGREE about the criterion" in txt


def test_an_empty_half_is_UNCONFIRMED_and_never_agreement():
    c = {"mean": 40.0, "rates": [40.0] * 100, "n": 20}
    txt = report(cov_at(20, 10), c, 40.0,
                 early=CN.coverage([], {}), late=cov_at(20, 10),
                 ctrl_e={"mean": 0.0, "rates": [], "n": 0}, ctrl_l=c)
    assert "UNCONFIRMED" in txt
    assert "the halves agree." not in txt


def test_the_report_refuses_when_our_universe_carried_nothing():
    cov = CN.coverage([{"date": "2026-01-02", "symbol": "ZZZ"}], {})
    txt = report(cov, {"mean": 0.0, "rates": [], "n": 0}, 0.0)
    assert "REFUSED: our universe carried none of his names." in txt


def test_the_report_corrects_the_handovers_word_for_our_ranking():
    """The handover calls it a volatility ranking. It is premarket_change. A
    reader who believes the first will draw a different conclusion from the
    same number."""
    txt = report(cov_at(20, 10), {"mean": 20.0, "rates": [20.0] * 100,
                                  "n": 20}, 20.0)
    assert "premarket_change descending" in txt
    assert "NOT volatility" in txt


def test_the_excluded_census_entries_are_declared_in_the_report():
    txt = report(cov_at(20, 10), {"mean": 20.0, "rates": [20.0] * 100,
                                  "n": 20}, 20.0,
                 dropped={"not a ticker": 1, "unparseable": 3})
    assert "1 census entries excluded: not a ticker" in txt
    assert "3 census entries excluded: unparseable" in txt


def test_the_pnl_table_carries_its_contamination_warning_inline():
    """A reader who skips to the money table must still meet the caveat."""
    pnl = {"HIS": [{"date": "2026-01-02", "symbol": "A", "net": 12.0}],
           "OURS": [{"date": "2026-01-02", "symbol": "B", "net": -3.0}]}
    txt = report(cov_at(20, 10), {"mean": 20.0, "rates": [20.0] * 100,
                                  "n": 20}, 20.0, pnl=pnl)
    assert "read section 1 before this table" in txt
    assert "picked after the" in txt
    assert "Section 3 is the registered reading" in txt


def test_the_pnl_table_prints_all_three_frictions():
    pnl = {"HIS": [{"date": "2026-01-02", "symbol": "A", "net": 12.0}],
           "OURS": [{"date": "2026-01-02", "symbol": "B", "net": -3.0}]}
    txt = report(cov_at(20, 10), {"mean": 20.0, "rates": [20.0] * 100,
                                  "n": 20}, 20.0, pnl=pnl)
    for label in ("$1.00", "$4.26", "$8.92"):
        assert f"friction {label}" in txt


def test_a_thin_arm_prints_n_a_and_never_a_zero_drop():
    """With DROP or fewer symbols the drop removes everything and prints
    exactly 0.00, which is indistinguishable from a result whose top names
    cancelled out."""
    pnl = {"HIS": [{"date": "2026-01-02", "symbol": "A", "net": 12.0}],
           "OURS": [{"date": "2026-01-02", "symbol": "B", "net": -3.0}]}
    txt = report(cov_at(20, 10), {"mean": 20.0, "rates": [20.0] * 100,
                                  "n": 20}, 20.0, pnl=pnl)
    assert "n/a" in txt


def test_the_report_never_claims_this_settles_his_edge():
    txt = report(cov_at(20, 10), {"mean": 20.0, "rates": [20.0] * 100,
                                  "n": 20}, 20.0)
    assert "self-reported" in txt
    assert "holdout.json is untouched" in txt


# ==========================================================================
# THE REGISTRATION ITSELF
# ==========================================================================
def test_the_registration_exists_and_predates_the_module():
    """A registration written after the run is not a registration. Both are in
    git; this asserts the document is there at all, and its commit is what
    dates it."""
    assert REGISTRATION.exists()
    txt = REGISTRATION.read_text(encoding="utf-8")
    assert "Only a **NULL** closes anything" in txt


def test_the_module_and_the_registration_agree_on_the_threshold():
    """A threshold that drifts between the plan and the code is a threshold
    chosen after seeing the data."""
    txt = REGISTRATION.read_text(encoding="utf-8")
    assert f"**{CN.MARGIN_PP:.0f} percentage\npoints**" in txt \
        or f"{CN.MARGIN_PP:.0f} percentage" in txt
    assert f"`best_rank <= {CN.TOP_N}`" in txt


# ==========================================================================
# THE ENTRY POINT
# ==========================================================================
def test_a_missing_census_stops_with_an_instruction(tmp_path):
    with pytest.raises(SystemExit) as e:
        CN.main(["--census", str(tmp_path / "no.csv"),
                 "--pairs", str(tmp_path / "no.json")])
    assert "check the merge" in str(e.value)


def test_a_missing_universe_names_the_command_that_builds_it(tmp_path):
    c = tmp_path / "c.csv"
    c.write_text("publish_date,videoId,symbols\n2026-01-02,v,ABC\n",
                 encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        CN.main(["--census", str(c), "--pairs", str(tmp_path / "no.json")])
    assert "screen_sim" in str(e.value)


def test_a_census_that_maps_to_nothing_refuses_rather_than_reporting_zero(
        tmp_path):
    """0 of 0 would render as a clean, confident null."""
    c = tmp_path / "c.csv"
    c.write_text("publish_date,videoId,symbols\n2020-01-02,v,ABC\n",
                 encoding="utf-8")
    j = tmp_path / "p.json"
    j.write_text(json.dumps([{"symbol": "AAA", "date": "2026-01-02",
                              "first_seen": "2026-01-02T08:00:00+00:00",
                              "first_rank": 1, "best_rank": 1, "ticks_on": 3,
                              "prior_source": "repaired"}]), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        CN.main(["--census", str(c), "--pairs", str(j)])
    assert "nothing to measure" in str(e.value)


def test_the_defaults_point_at_the_dated_census_and_the_pit_universe():
    a = CN.build_parser().parse_args([])
    assert a.census.endswith("_dated.csv")
    assert a.pairs.endswith("screen_pairs_pit.json")
    assert a.out.startswith("var/reports/")
