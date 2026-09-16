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
# THE ORDERING STATISTIC, AND THE CONTROL — the pieces most able to lie
# plausibly. The original criterion (top-5 rate, 15pp over control) was
# AMENDED before the first run because it cannot pass: a random name from our
# own universe is inside the top 5 93.7% of the time on a median 11-name list.
# ==========================================================================
def test_rank_auc_is_the_chance_of_outranking_another_name_on_the_list():
    """Stated as a probability in the report, so it has to be one. Rank 2 of
    [1,2,3,4,5] beats three of the other four."""
    assert CN.rank_auc(2, [1, 2, 3, 4, 5]) == pytest.approx(3 / 4)
    assert CN.rank_auc(1, [1, 2, 3, 4, 5]) == 1.0
    assert CN.rank_auc(5, [1, 2, 3, 4, 5]) == 0.0


def test_a_tie_counts_as_half():
    """550 of 551 real sessions have tied best_ranks, so this is the normal
    case and not an edge one. 2024-07-02 ranks six names 1,1,3,3,3,4."""
    assert CN.rank_auc(3, [1, 1, 3, 3, 3, 4]) == pytest.approx(
        (1 + 0.5 * 2) / 5)


def test_only_ONE_instance_of_the_name_is_removed_from_its_own_pool():
    """The name itself is in the pool once. Removing every entry that shares
    its rank would delete the ties it is supposed to be scored against, and
    on a tie-heavy field that is most of the comparison."""
    assert CN.rank_auc(1, [1, 1, 1, 9]) == pytest.approx((1 + 0.5 * 2) / 3)


def test_a_one_name_session_orders_nothing_and_says_so():
    """0.5, not 1.0. A name that is top of a list of one has not outranked
    anything, and scoring it a win would reward thin sessions."""
    assert CN.rank_auc(1, [1]) == 0.5


def test_the_control_sits_at_exactly_one_half_by_symmetry():
    """THE CHECK ON THE CHECK, and it is exact rather than approximate. A
    control that sampled the pooled universe instead of the session's own
    would still return a believable number; only agreement with 0.500 says
    which pool it drew from."""
    u = days(12, per=10)
    sd = [{"date": d, "symbol": next(iter(u[d]))} for d in u]
    c = CN.control(sd, u, "best_rank", draws=400, seed=1)
    assert abs(c["auc"] - 0.5) < 0.02


def test_the_control_draws_from_the_SAME_session_not_the_pool():
    """Two sessions, one tiny and one huge. Drawn from the pool, the tiny
    session's own ordering disappears into the big one's."""
    u = pit({"2026-01-01": [("A", 1, 1), ("B", 2, 2)],
             "2026-01-02": [(f"C{k}", k, k) for k in range(1, 41)]})
    sd = [{"date": "2026-01-01", "symbol": "A"}]
    c = CN.control(sd, u, "best_rank", draws=300, seed=7)
    assert c["top"] == 100.0, "only the two-name session may be drawn from"


def test_the_control_reads_the_FIELD_it_is_given():
    """best_rank and first_rank are different questions, and a control that
    silently answered the other one would be compared against his figure as
    though they were the same number."""
    u = pit({"2026-01-02": [(f"S{k}", k + 20, k) for k in range(1, 11)]})
    sd = [{"date": "2026-01-02", "symbol": f"S{k}"} for k in range(1, 11)]
    best = CN.control(sd, u, "best_rank", draws=200, seed=5)
    first = CN.control(sd, u, "first_rank", draws=200, seed=5)
    assert abs(best["top"] - 50.0) < 6, "ranks 1..10, half inside the top 5"
    assert first["top"] == 0.0, "first_ranks are 21..30, none can be inside"
    # the deterministic form, where the field cannot hide behind draw noise
    assert CN.control_top_rate(sd, u, "best_rank") == 50.0
    assert CN.control_top_rate(sd, u, "first_rank") == 0.0


def test_the_observed_side_reads_the_same_field_as_its_control():
    u = pit({"2026-01-02": [("A", 9, 1), ("B", 1, 9)]})
    cov = CN.coverage([{"date": "2026-01-02", "symbol": "A"}], u)
    assert CN.observed_auc(cov["present"], u, "best_rank") == [1.0]
    assert CN.observed_auc(cov["present"], u, "first_rank") == [0.0]


def test_the_closed_form_top_rate_is_COUNTED_not_assumed():
    """min(N, n)/n needs the ranks to enumerate 1..n within a session. They do
    not -- best_rank is the best a name ever reached. The assumed form gives
    0.536 against a true 0.937 on the real universe and would have raised a
    wrong-pool alarm on correct data."""
    u = pit({"2026-01-02": [("A", 1, 1), ("B", 1, 1), ("C", 1, 1),
                            ("D", 9, 9), ("E", 9, 9), ("F", 9, 9)]})
    sd = [{"date": "2026-01-02", "symbol": "A"}]
    assert CN.control_top_rate(sd, u, "best_rank") == 50.0
    assert CN.control_top_rate(sd, u, "best_rank") != 100.0 * min(
        CN.TOP_N, 6) / 6


def test_the_control_is_reproducible_from_its_seed():
    u = days(8, per=9)
    sd = [{"date": d, "symbol": next(iter(u[d]))} for d in u]
    a = CN.control(sd, u, "best_rank", draws=100, seed=42)
    b = CN.control(sd, u, "best_rank", draws=100, seed=42)
    assert a["aucs"] == b["aucs"]
    assert CN.control(sd, u, "best_rank", draws=100, seed=43)["aucs"] != a["aucs"]


def test_a_session_with_no_universe_is_skipped_by_both_sides():
    u = days(2, per=6)
    sd = [{"date": d, "symbol": next(iter(u[d]))} for d in u]
    sd.append({"date": "2099-01-01", "symbol": "GHOST"})
    assert CN.control(sd, u, "best_rank", draws=50, seed=3)["n"] == 2
    assert CN.control_top_rate(sd, u, "best_rank") > 0


def test_beat_rate_is_the_share_of_draws_reaching_the_observed_figure():
    assert CN.beat_rate(0.5, [0.1, 0.5, 0.9]) == pytest.approx(2 / 3)
    assert CN.beat_rate(0.99, [0.1, 0.5, 0.9]) == 0.0


# ==========================================================================
# THE ARMS — and the label that was wrong
# ==========================================================================
def test_the_five_arm_really_is_FIVE_names():
    """THE DEFECT THIS EXISTS FOR. `best_rank <= 5` is not five names: 550 of
    551 real sessions have tied best_ranks, so that filter takes 90.5% of every
    symbol-day in the universe -- a median of 10 a session and up to 28. An arm
    built that way is our WHOLE LIST wearing the label "top 5"."""
    u = pit({"2026-01-02": [(f"S{k}", 1, 1) for k in range(1, 21)]})
    arms = CN.arm_universes([{"date": "2026-01-02", "symbol": "S1"}], u)
    assert len(arms["OURS-5"]["2026-01-02"]) == CN.TOP_N
    assert len(arms["OURS-ALL"]["2026-01-02"]) == 20, \
        "the loose arm is the whole list, which is the point of printing it"


def test_a_session_smaller_than_the_cut_is_not_padded():
    u = pit({"2026-01-02": [("A", 1, 1), ("B", 2, 2)]})
    arms = CN.arm_universes([{"date": "2026-01-02", "symbol": "A"}], u)
    assert len(arms["OURS-5"]["2026-01-02"]) == 2


def test_the_strict_cut_ranks_on_first_rank_not_best_rank():
    """A watchlist is built from what you can see when you see it. best_rank
    is the best a name ever reached, which needs the rest of the day."""
    u = pit({"2026-01-02": [("EARLY", 1, 9), ("LATE", 9, 1)]})
    picked = [r["symbol"] for r in CN.strict_top(u["2026-01-02"])]
    assert picked[0] == "EARLY"


def test_the_strict_cut_breaks_ties_deterministically():
    """Otherwise the arm changes between runs and a difference in the P/L
    table cannot be attributed to anything."""
    u = pit({"2026-01-02": [(f"S{k}", 1, 1) for k in range(1, 21)]})
    a = [r["symbol"] for r in CN.strict_top(u["2026-01-02"])]
    b = [r["symbol"] for r in CN.strict_top(dict(reversed(
        list(u["2026-01-02"].items()))))]
    assert a == b == sorted(a)


def test_every_arm_comes_from_the_same_pair_records():
    """A name cannot be ranked from one tape and scored on another. There is
    one universe object here and every arm is a subset of it."""
    u = pit({"2026-01-02": [("AAA", 1, 1), ("BBB", 9, 9), ("CCC", 3, 3)]})
    arms = CN.arm_universes([{"date": "2026-01-02", "symbol": "BBB"}], u)
    assert [r["symbol"] for r in arms["HIS"]["2026-01-02"]] == ["BBB"]
    for name, per_day in arms.items():
        for r in per_day["2026-01-02"]:
            assert r is u["2026-01-02"][r["symbol"]], f"{name} copied a record"


def test_only_sessions_he_named_something_on_enter_any_arm():
    """Scoring ours over sessions with no mention would compare his 241 days
    against our 551 and call the difference selection."""
    u = days(4, per=8)
    one = sorted(u)[0]
    arms = CN.arm_universes([{"date": one, "symbol": next(iter(u[one]))}], u)
    for per_day in arms.values():
        assert set(per_day) == {one}


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
def ctrl_at(auc=0.5, top=90.0, n=50):
    """A control dict at a chosen mean rank-AUC. The draw spread is flat so
    the tests exercise the verdict logic and not the random stream."""
    return {"auc": auc, "aucs": [auc] * 100, "top": top, "n": n}


def report(cov, ctrl, aucs, auc_e=None, auc_l=None, ctrl_e=None, ctrl_l=None,
           causes=None, pnl=None, dropped=None):
    return "\n".join(CN.render(
        cov, ctrl, aucs,
        auc_e if auc_e is not None else aucs,
        auc_l if auc_l is not None else aucs,
        ctrl_e if ctrl_e is not None else ctrl_at(),
        ctrl_l if ctrl_l is not None else ctrl_at(),
        dropped or {"not a ticker": 1}, 4, 3, causes, pnl, 242, 1.0))


def aucs_at(mean, n=40):
    """`n` per-name rank-AUCs averaging exactly `mean`."""
    return [mean] * n


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
    txt = report(cov_at(20, 20), ctrl_at(), aucs_at(0.95))
    assert "he TRADED" in txt
    assert "settles nothing" in txt
    assert "PASSES the registered" in txt
    assert "does NOT say: that his names are better" in txt


def test_a_null_says_item_1c_is_CLOSED():
    """The whole point of the design: only a null closes anything, so the null
    has to actually say so rather than leaving the reader to infer it."""
    txt = report(cov_at(20, 4), ctrl_at(), aucs_at(0.51))
    assert "DOES NOT pass the registered" in txt
    assert "CLOSED" in txt
    assert "name selection is not where the gap is" in txt


def test_the_bar_is_a_real_threshold():
    """Just under and just over must read differently, or AUC_MIN could be any
    number and nothing would notice."""
    under = report(cov_at(100, 50), ctrl_at(), aucs_at(CN.AUC_MIN - 0.001))
    over = report(cov_at(100, 50), ctrl_at(), aucs_at(CN.AUC_MIN + 0.001))
    assert "DOES NOT pass" in under
    assert "PASSES the registered" in over


def test_a_draw_that_disagrees_with_its_closed_form_is_SHOUTED():
    """The control is the piece that can be wrong and still look right. If the
    two ever part company the report must not print a tidy gap underneath."""
    txt = report(cov_at(20, 10), ctrl_at(auc=0.62), aucs_at(0.7))
    assert "sampling the wrong pool" in txt


def test_an_agreeing_draw_is_marked_OK_rather_than_left_silent():
    txt = report(cov_at(20, 10), ctrl_at(auc=0.505), aucs_at(0.7))
    assert "sampling the wrong pool" not in txt
    assert "draw vs form" in txt


def test_both_denominators_are_printed_and_only_one_is_compared():
    txt = report(cov_at(20, 10, n_absent=30), ctrl_at(), aucs_at(0.7))
    assert "over ALL" in txt
    assert "a random name from OUR OWN list" in txt
    assert "discriminate at any threshold" in txt


def test_every_rank_is_printed_not_only_the_top_five():
    """Nothing ranked, every bucket printed. A table that stops at 5 hides
    whether the rest cluster at 6 or at 40."""
    u = pit({"2026-01-02": [("A", 1, 1), ("B", 12, 12)]})
    cov = CN.coverage([{"date": "2026-01-02", "symbol": "A"},
                       {"date": "2026-01-02", "symbol": "B"}], u)
    txt = report(cov, ctrl_at(n=2), aucs_at(0.7))
    body = txt.split("2. THE RANK WE GAVE THEM")[1]
    for r in range(1, 13):
        assert re.search(rf"^\s+{r}\s", body, re.M), f"rank {r} missing"


def test_the_declined_names_are_reported_with_their_cause():
    from collections import Counter
    txt = report(cov_at(10, 5, n_absent=7), ctrl_at(), aucs_at(0.7),
                 causes=Counter({"VOLUME": 5, "NOT ON THIS TAPE": 2}))
    assert "WHY WE DECLINED THE REST" in txt
    assert "VOLUME" in txt and "NOT ON THIS TAPE" in txt
    assert "turning down a name he traded" in txt


def test_halves_pointing_opposite_ways_refuse_the_verdict():
    # both halves sit below the bar, so only DIRECTION separates them -- the
    # case a bar-only check would wave through as agreement.
    txt = report(cov_at(20, 10), ctrl_at(), aucs_at(0.50),
                 auc_e=aucs_at(0.45), auc_l=aucs_at(0.55))
    assert "THE HALVES DISAGREE in direction" in txt


def test_halves_that_straddle_the_criterion_refuse_too():
    """One half passing and one failing is not a pooled pass, whatever the
    pooled number says."""
    txt = report(cov_at(20, 10), ctrl_at(), aucs_at(0.60),
                 auc_e=aucs_at(0.55), auc_l=aucs_at(0.70))
    assert "THE HALVES DISAGREE about the bar" in txt


def test_an_empty_half_is_UNCONFIRMED_and_never_agreement():
    txt = report(cov_at(20, 10), ctrl_at(), aucs_at(0.7),
                 auc_e=[], auc_l=aucs_at(0.7),
                 ctrl_e={"auc": 0.5, "aucs": [], "top": 0.0, "n": 0})
    assert "UNCONFIRMED" in txt
    assert "the halves agree." not in txt


def test_the_report_refuses_when_our_universe_carried_nothing():
    cov = CN.coverage([{"date": "2026-01-02", "symbol": "ZZZ"}], {})
    txt = report(cov, {"auc": 0.5, "aucs": [], "top": 0.0, "n": 0}, [])
    assert "REFUSED: our universe carried none of his names." in txt


def test_the_report_corrects_the_handovers_word_for_our_ranking():
    """The handover calls it a volatility ranking. It is premarket_change. A
    reader who believes the first will draw a different conclusion from the
    same number."""
    txt = report(cov_at(20, 10), ctrl_at(), aucs_at(0.7))
    assert "premarket_change descending" in txt
    assert "NOT volatility" in txt


def test_the_excluded_census_entries_are_declared_in_the_report():
    txt = report(cov_at(20, 10), ctrl_at(), aucs_at(0.7),
                 dropped={"not a ticker": 1, "unparseable": 3})
    assert "1 census entries excluded: not a ticker" in txt
    assert "3 census entries excluded: unparseable" in txt


def test_the_pnl_table_carries_its_contamination_warning_inline():
    """A reader who skips to the money table must still meet the caveat."""
    pnl = {"HIS": [{"date": "2026-01-02", "symbol": "A", "net": 12.0}],
           "OURS-5": [{"date": "2026-01-02", "symbol": "B", "net": -3.0}],
           "OURS-ALL": [{"date": "2026-01-02", "symbol": "C", "net": -9.0}]}
    txt = report(cov_at(20, 10), ctrl_at(), aucs_at(0.7), pnl=pnl)
    assert "read section 1 before this table" in txt
    assert "picked after the" in txt
    assert "Section 3 is the registered reading" in txt


def test_the_pnl_table_prints_all_three_frictions():
    pnl = {"HIS": [{"date": "2026-01-02", "symbol": "A", "net": 12.0}],
           "OURS-5": [{"date": "2026-01-02", "symbol": "B", "net": -3.0}],
           "OURS-ALL": [{"date": "2026-01-02", "symbol": "C", "net": -9.0}]}
    txt = report(cov_at(20, 10), ctrl_at(), aucs_at(0.7), pnl=pnl)
    for label in ("$1.00", "$4.26", "$8.92"):
        assert f"friction {label}" in txt


def test_a_thin_arm_prints_n_a_and_never_a_zero_drop():
    """With DROP or fewer symbols the drop removes everything and prints
    exactly 0.00, which is indistinguishable from a result whose top names
    cancelled out."""
    pnl = {"HIS": [{"date": "2026-01-02", "symbol": "A", "net": 12.0}],
           "OURS-5": [{"date": "2026-01-02", "symbol": "B", "net": -3.0}],
           "OURS-ALL": [{"date": "2026-01-02", "symbol": "C", "net": -9.0}]}
    txt = report(cov_at(20, 10), ctrl_at(), aucs_at(0.7), pnl=pnl)
    assert "n/a" in txt


def test_the_report_never_claims_this_settles_his_edge():
    txt = report(cov_at(20, 10), ctrl_at(), aucs_at(0.7))
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
