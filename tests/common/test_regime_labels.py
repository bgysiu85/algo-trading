#!/usr/bin/env python3
"""The first external check in this project, and the ways it could lie.

`common/regime_labels.py` asks whether our unsupervised hot/mixed/cold reading
agrees with 277 sessions a human labelled in his own recaps. That is the only
question here with an answer from outside the project, which makes it the one
worth getting wrong quietly.

The failures these guard against are the ones that would produce a CONFIDENT
number rather than an error:

  * a composite that is a copy of the classifier's, so the "agreement" is the
    instrument agreeing with itself;
  * a mapping from publish date to session that is never checked against the
    data, only against the calendar that produced it;
  * a halves verdict that reads a half the same page refused to print;
  * a lag comparison that voids the headline on a 0.001 margin;
  * thin days silently dropped, which removes the coldest days from a cold
    sample and then reports that cold days are rare.
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import pytest

from common import regime as RG
from common import regime_labels as RL

REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# A DayFeatures stand-in. The real one comes off a 205 MB archive that is not
# on this machine, and the module under test only ever reads `.usable`,
# `.n_movers`, `.lead` and `.round_trip`.
# --------------------------------------------------------------------------
@dataclass
class Fake:
    n_movers: int
    lead: float
    round_trip: float

    @property
    def usable(self) -> bool:
        return self.n_movers >= RG.MIN_NAMES


def feats(spec: dict[str, tuple]) -> dict[str, Fake]:
    return {d: Fake(*v) for d, v in spec.items()}


def ladder(n: int, start: str = "2026-01-01") -> dict[str, Fake]:
    """`n` sessions, monotonically hotter. The composite is then an exact
    ordering and every assertion about direction has a known right answer."""
    d0 = dt.date.fromisoformat(start)
    return {(d0 + dt.timedelta(days=i)).isoformat():
            Fake(10 + i, 0.5 + i * 0.1, 0.9 - i * 0.01) for i in range(n)}


# ==========================================================================
# THE COMPOSITE IS THE CLASSIFIER'S, NOT A COPY OF IT
# ==========================================================================
def test_the_scale_comes_from_regime_itself():
    """THE LOAD-BEARING ONE.

    If this module built its own composite, it would agree with itself
    forever: hot days would sit high on a scale written to make them sit high,
    and the report would read exactly the same whether or not `classify` --
    the thing actually being validated -- measures anything.
    """
    f = ladder(30)
    assert RL.composite(f) == pytest.approx(RG.composite(f))


def test_the_classifier_and_the_scale_cannot_drift_apart():
    """A rewritten `regime.composite` has to move BOTH. Nothing here may still
    read the old scale while the labels come off a new one."""
    f = ladder(30)
    comp, lab = RG.composite(f), RG.classify(f)
    hot = [comp[d] for d, v in lab.items() if v == "hot"]
    cold = [comp[d] for d, v in lab.items() if v == "cold" and d in comp]
    assert min(hot) > max(cold), \
        "classify's own buckets must be terciles OF THIS composite"


def test_classify_is_unchanged_by_the_extraction():
    """The refactor that made the scale shareable must not have moved a single
    label, or every earlier figure in this project quietly changed meaning."""
    f = ladder(30)
    lab = RG.classify(f)
    assert sorted(set(lab.values())) == ["cold", "hot", "mixed"]
    assert sum(1 for v in lab.values() if v == "hot") == 10
    assert sum(1 for v in lab.values() if v == "cold") == 10


def test_a_market_where_nothing_moves_reads_COLD_and_not_MIXED():
    """The lower tercile is INCLUSIVE, and on a flat tape that is the whole
    answer. Four identical sessions all sit on the same composite, which is
    simultaneously the lower and the upper tercile; an exclusive cut calls
    every one of them "mixed" and the report then describes a market with
    nothing moving in it as ordinary.

    Not a contrived input. Ties are the normal case here -- `n_movers` is an
    integer and quiet stretches produce long runs of the same value.
    """
    flat = feats({f"2026-01-0{i}": (10, 1.0, 0.5) for i in range(1, 5)})
    assert set(RG.classify(flat).values()) == {"cold"}


def test_a_day_too_thin_to_rate_sits_at_the_bottom_and_is_not_dropped():
    """`classify` calls those days cold. If the scale dropped them instead,
    the coldest days would leave a cold sample and the comparison would report
    that his cold days look unremarkable."""
    f = ladder(20)
    f["2026-02-01"] = Fake(1, 0.0, 1.0)          # under MIN_NAMES
    comp = RL.composite(f)
    assert "2026-02-01" in comp, "a thin day must not vanish"
    assert comp["2026-02-01"] == 0.0
    assert RG.classify(f)["2026-02-01"] == "cold", \
        "and the two must agree about it"


def test_too_few_rated_sessions_yields_no_scale_rather_than_a_fake_one():
    assert RG.composite(feats({"2026-01-01": (10, 1.0, 0.5),
                               "2026-01-02": (20, 2.0, 0.4)})) == {}


# ==========================================================================
# THE MAPPING
# ==========================================================================
def test_a_recap_maps_to_its_own_session():
    s = {"2026-03-02", "2026-03-03"}
    assert RL.map_to_session("2026-03-03", s) == "2026-03-03"


def test_a_weekend_recap_maps_BACK_to_the_friday():
    """41 of the 277 publish on a Saturday or Sunday. A fixed shift would be
    right for those and wrong for the 233 that land on their own session."""
    s = {"2026-03-06", "2026-03-09"}              # Friday, Monday
    assert RL.map_to_session("2026-03-08", s) == "2026-03-06"   # Sunday


def test_the_search_never_runs_FORWARD_into_a_later_session():
    """Mapping a recap onto a session it could not have described would be
    look-ahead dressed as a join."""
    s = {"2026-03-10"}
    assert RL.map_to_session("2026-03-06", s) is None


def test_a_recap_from_outside_the_archive_maps_to_nothing():
    """Silently attaching it to the nearest thing available would put a 2023
    label on a 2024 session."""
    assert RL.map_to_session("2020-01-02", {"2026-03-03"}) is None


def test_the_offset_shifts_the_whole_search_window():
    """The -1 run has to be a different mapping, or the check against the data
    compares offset 0 with itself and always passes."""
    s = {"2026-03-02", "2026-03-03"}
    assert RL.map_to_session("2026-03-03", s, offset=0) == "2026-03-03"
    assert RL.map_to_session("2026-03-03", s, offset=-1) == "2026-03-02"


# ==========================================================================
# THE LABELS THEMSELVES
# ==========================================================================
def test_only_rows_a_human_actually_labelled_are_loaded(tmp_path):
    """124 census rows carry "?" -- he did not say. A default would invent 124
    opinions and then measure our agreement with them."""
    p = tmp_path / "c.csv"
    p.write_text("videoId,market,publish_date\n"
                 "a,hot,2026-01-02\n"
                 "b,?,2026-01-03\n"
                 "c,cold,\n"
                 "d,cold,2026-01-06\n", encoding="utf-8")
    assert RL.load_labels(p) == [("2026-01-02", "hot"),
                                 ("2026-01-06", "cold")]


def test_the_real_census_still_carries_the_277():
    """The module's every figure rests on this file. If it is regenerated to a
    different shape, this fails here rather than in a report."""
    rows = list(csv.DictReader(
        (REPO / RL.CENSUS).open(encoding="utf-8-sig")))
    assert len(RL.load_labels(REPO / RL.CENSUS)) == 277
    assert len(rows) == 401


# ==========================================================================
# THE SEPARATION
# ==========================================================================
def test_hot_days_that_really_are_hotter_separate():
    f = ladder(30)
    comp = RL.composite(f)
    d = sorted(comp)
    pairs = ([(x, "cold") for x in d[:10]] + [(x, "hot") for x in d[-10:]])
    s = RL.separation(pairs, comp)
    assert s["gap"] > 0 and s["auc"] == 1.0


def test_labels_assigned_at_random_to_the_same_days_do_NOT_separate():
    """The null. If this ever returned a gap, the instrument is reading its
    own construction rather than the labels."""
    f = ladder(30)
    comp = RL.composite(f)
    d = sorted(comp)
    pairs = [(x, "hot" if i % 2 else "cold") for i, x in enumerate(d)]
    s = RL.separation(pairs, comp)
    assert abs(s["auc"] - 0.5) < 0.1


def test_AUC_is_the_chance_a_hot_day_outranks_a_cold_one():
    """Stated as a probability in the report, so it has to be one. Three hot
    against one cold, with one hot below it: 2 wins of 3."""
    comp = {"h1": 0.9, "h2": 0.8, "h3": 0.1, "c1": 0.5}
    s = RL.separation([("h1", "hot"), ("h2", "hot"), ("h3", "hot"),
                       ("c1", "cold")], comp)
    assert s["auc"] == pytest.approx(2 / 3)


def test_a_tie_counts_as_half_and_an_all_tied_comparison_reads_as_no_signal():
    comp = {"a": 0.5, "b": 0.5}
    assert RL.separation([("a", "hot"), ("b", "cold")], comp)["auc"] == 0.5


def test_a_reversed_reading_is_reported_as_negative_and_not_as_strength():
    """|AUC - 0.5| would make a classifier that is exactly BACKWARDS look as
    good as one that is right."""
    comp = {"h": 0.1, "c": 0.9}
    s = RL.separation([("h", "hot"), ("c", "cold")], comp)
    assert s["auc"] == 0.0 and s["gap"] < 0


def test_a_side_with_no_days_refuses_rather_than_returning_zero():
    comp = {"a": 0.5}
    s = RL.separation([("a", "hot")], comp)
    assert s["gap"] is None and s["auc"] is None and s["n_cold"] == 0


def test_days_that_did_not_map_are_not_counted_as_present():
    """A pair whose session is absent from the composite must not inflate n."""
    comp = {"a": 0.9}
    s = RL.separation([("a", "hot"), ("ghost", "hot"), ("a", "cold")], comp)
    assert s["n_hot"] == 1


def test_mixed_is_carried_but_is_not_part_of_the_verdict():
    comp = {"h": 0.9, "m": 0.5, "c": 0.1}
    s = RL.separation([("h", "hot"), ("m", "mixed"), ("c", "cold")], comp)
    assert s["n_mixed"] == 1 and s["mixed"] == 0.5
    assert s["auc"] == 1.0, "mixed must not move the hot-vs-cold AUC"


# ==========================================================================
# THE HALVES
# ==========================================================================
def test_the_split_is_the_projects_split_and_not_a_second_one():
    """`regime_study.halves_split` is the rule used everywhere else. A private
    copy here would drift and still look current."""
    from common.regime_study import halves_split

    pairs = [(f"2026-01-{i:02d}", "hot") for i in range(1, 11)]
    e, l = RL.halves(pairs)
    cut = halves_split([d for d, _ in pairs])
    assert all(d < cut for d, _ in e) and all(d >= cut for d, _ in l)
    assert len(e) + len(l) == len(pairs), "no row may be lost in the split"


def test_every_row_lands_in_exactly_one_half():
    pairs = [("2026-01-01", "hot"), ("2026-01-01", "cold"),
             ("2026-01-05", "hot")]
    e, l = RL.halves(pairs)
    assert sorted(e + l) == sorted(pairs)


def test_a_thin_half_is_not_usable():
    thin = {"gap": 0.2, "auc": 0.7, "n_hot": RL.MIN_PER_SIDE - 1,
            "n_cold": 100, "n_mixed": 0, "hot": 0.7, "cold": 0.5, "mixed": None}
    assert not RL.usable_half(thin)


def test_a_refused_half_is_not_usable_however_thick_it_looks():
    assert not RL.usable_half({"gap": None, "auc": None, "n_hot": 99,
                               "n_cold": 99, "n_mixed": 0, "hot": None,
                               "cold": None, "mixed": None})


def test_a_thick_half_is_usable_at_exactly_the_threshold():
    """The boundary, spelled out, so >= never becomes > unnoticed."""
    assert RL.usable_half({"gap": 0.2, "auc": 0.7, "n_hot": RL.MIN_PER_SIDE,
                           "n_cold": RL.MIN_PER_SIDE, "n_mixed": 0,
                           "hot": 0.7, "cold": 0.5, "mixed": None})


# ==========================================================================
# THE REPORT: it has to say the discouraging thing when the numbers are
# discouraging. Every one of these is a text assertion because the text is
# the only part anyone reads.
# ==========================================================================
def thick(gap, auc, n=40):
    return {"gap": gap, "auc": auc, "n_hot": n, "n_cold": n, "n_mixed": 5,
            "hot": 0.5 + gap / 2, "cold": 0.5 - gap / 2, "mixed": 0.5}


def report(sep, sep_lag=None, early=None, late=None, ours=None, mapped=None):
    sep_lag = sep_lag if sep_lag is not None else thick(0.05, 0.55)
    return "\n".join(RL.render(
        mapped if mapped is not None else [("2026-01-02", "hot")],
        3, 124, ours if ours is not None else {"2026-01-02": "hot"},
        sep, sep_lag,
        early if early is not None else thick(0.2, 0.7),
        late if late is not None else thick(0.2, 0.7),
        {"2026-01-02"}, 1.0))


def test_the_report_says_so_when_the_lag_separates_materially_better():
    txt = report(thick(0.1, 0.60), sep_lag=thick(0.3, 0.80))
    assert "THE LAG SEPARATES BETTER" in txt
    assert "no conclusion above stands" in txt


def test_a_hair_thin_lead_for_the_lag_does_NOT_void_the_headline():
    """Without a margin, a coin flip prints a catastrophic verdict and the
    run is thrown away over nothing."""
    txt = report(thick(0.1, 0.600), sep_lag=thick(0.1, 0.601))
    assert "THE LAG SEPARATES BETTER" not in txt
    assert "cannot be told apart" in txt


def test_the_margin_is_a_real_threshold_and_not_decoration():
    """Just inside and just outside must read differently, or LAG_MARGIN could
    be any number at all and nothing would notice."""
    base = 0.60
    inside = report(thick(0.1, base),
                    sep_lag=thick(0.1, base + RL.LAG_MARGIN - 0.001))
    outside = report(thick(0.1, base),
                     sep_lag=thick(0.1, base + RL.LAG_MARGIN + 0.001))
    assert "THE LAG SEPARATES BETTER" not in inside
    assert "THE LAG SEPARATES BETTER" in outside


def test_the_report_names_persistence_as_the_floor_under_the_lag_check():
    """Regimes persist, so offset -1 separates somewhat whatever the mapping
    is. A reader told only 'offset 0 won' would take the check for more than
    it is."""
    txt = report(thick(0.1, 0.60))
    assert "autocorrelation" in txt


def test_halves_that_point_opposite_ways_refuse_the_verdict():
    txt = report(thick(0.1, 0.6), early=thick(0.3, 0.8), late=thick(-0.3, 0.2))
    assert "THE HALVES DISAGREE" in txt
    assert "No verdict" in txt


def test_halves_that_agree_say_so():
    txt = report(thick(0.1, 0.6), early=thick(0.3, 0.8), late=thick(0.2, 0.7))
    assert "the halves AGREE in direction." in txt
    assert "DISAGREE" not in txt


def test_a_refused_half_can_never_be_read_as_agreement():
    """THE DEFECT THIS SHAPE KEEPS PRODUCING: the page prints REFUSED for a
    half and then declares the halves in agreement on the strength of it."""
    txt = report(thick(0.1, 0.6),
                 early={"gap": None, "auc": None, "n_hot": 2, "n_cold": 1,
                        "n_mixed": 0, "hot": None, "cold": None,
                        "mixed": None},
                 late=thick(0.2, 0.7))
    assert "REFUSED" in txt
    assert "AGREE in direction" not in txt
    assert "UNCONFIRMED" in txt


def test_a_thin_half_is_refused_in_the_text_not_just_in_the_predicate():
    txt = report(thick(0.1, 0.6), early=thick(0.2, 0.7, n=3),
                 late=thick(0.2, 0.7))
    assert "REFUSED" in txt and f"under {RL.MIN_PER_SIDE} a side" in txt


def test_a_THIN_half_cannot_be_read_as_agreement_either():
    """The same defect as above, in its harder form. A thin half still HAS a
    gap, so a verdict guarded on "is there a number" rather than on "may this
    number be read" sails straight past it -- and prints REFUSED and AGREE on
    the same page, one from each rule."""
    txt = report(thick(0.1, 0.6), early=thick(0.2, 0.7, n=3),
                 late=thick(0.2, 0.7))
    assert "AGREE in direction" not in txt
    assert "UNCONFIRMED" in txt


def test_a_null_result_is_printed_rather_than_buried():
    """AUC 0.50 is a real outcome and the report has to carry the number that
    says so, not only the number that would have been good news."""
    txt = report(thick(0.0, 0.500))
    assert "AUC  0.500" in txt
    assert "SUPERVISED TARGET" in txt, \
        "and it has to say what a null result turns the labels into"


def test_the_report_refuses_when_a_side_never_mapped():
    txt = report({"gap": None, "auc": None, "n_hot": 0, "n_cold": 5,
                  "n_mixed": 0, "hot": None, "cold": None, "mixed": None})
    assert "REFUSED: one side has no mapped days." in txt


def test_the_report_never_claims_this_licenses_trading():
    """A same-day label cannot be acted on at 04:00. Only `regime.lagged` is a
    gate and its ceiling is the label's autocorrelation."""
    txt = report(thick(0.4, 0.9))
    assert "NONE OF THESE licenses trading on it" in txt
    assert "lagged" in txt


def test_the_report_says_his_P_L_is_not_used():
    """The census could not fix SOURCE bias on a channel that sells a course.
    The label is a claim about the tape; the earnings are not checkable."""
    txt = report(thick(0.4, 0.9))
    assert "self-reported" in txt


def test_the_unlabelled_rows_are_declared_rather_than_hidden():
    assert "124 census rows carry no label" in report(thick(0.1, 0.6))


def test_the_recaps_that_could_not_be_mapped_are_declared():
    """A join that silently loses rows shrinks the sample without saying so."""
    assert "(3 could not be)" in report(thick(0.1, 0.6))


def test_the_three_way_table_prints_every_cell_including_the_empty_ones():
    """Nothing ranked, every bucket printed. A table that omits its zeros
    reads as though those combinations never came up."""
    mapped = [("d1", "hot"), ("d2", "cold")]
    ours = {"d1": "hot", "d2": "hot"}
    txt = report(thick(0.1, 0.6), ours=ours, mapped=mapped)
    body = txt.split("THE THREE-WAY TABLE")[1]
    for lab in RL.LABELS:
        assert f"  {lab:<14}" in body
    assert "raw agreement 1/2" in body


def test_the_raw_agreement_carries_its_own_caveat():
    """Printed because a reader wants it, immediately undercut because the
    marginals make it misleading. Printing it bare would hand over the one
    number on the page that is wrong."""
    txt = report(thick(0.1, 0.6))
    assert "depressed by the marginals" in txt


# ==========================================================================
# CONFUSION
# ==========================================================================
def test_confusion_counts_pairs_and_drops_sessions_we_never_rated():
    cm = RL.confusion([("d1", "hot"), ("d2", "cold"), ("d3", "hot")],
                      {"d1": "hot", "d2": "hot"})
    assert cm == {("hot", "hot"): 1, ("cold", "hot"): 1}


def test_confusion_keeps_his_label_first_and_ours_second():
    """Transposed, the table would read as our classifier's marginals being
    his. The two are 61% cold and a third hot respectively, so a transpose is
    not cosmetic."""
    cm = RL.confusion([("d1", "hot")], {"d1": "cold"})
    assert cm == {("hot", "cold"): 1}


# ==========================================================================
# THE ENTRY POINT
# ==========================================================================
def test_a_missing_census_stops_with_an_instruction(tmp_path):
    with pytest.raises(SystemExit) as e:
        RL.main(["--census", str(tmp_path / "nope.csv"),
                 "--archive", str(tmp_path)])
    assert "check the merge" in str(e.value)


def test_the_default_census_path_is_the_dated_one():
    """The undated census has no publish_date column and every row would drop,
    reporting a clean 0-of-0 agreement."""
    assert RL.build_parser().parse_args([]).census.endswith("_dated.csv")


def test_the_default_output_is_a_var_report_path():
    assert RL.build_parser().parse_args([]).out.startswith("var/reports/")
