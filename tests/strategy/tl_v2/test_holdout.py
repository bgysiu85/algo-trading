"""G3 of REGISTERED_tl_v2.md sec 5-6: the TL-v2 holdout cut and ledger are in code and mutation-tested."""
from __future__ import annotations

import json

import pytest

from strategy.futbt.holdout import OTHER_LINES, OWN_LEDGERS, Holdout, HoldoutRefused
from strategy.tl_v2 import holdout as TH

DATES = ["2021-12-30", "2021-12-31", "2022-01-03", "2025-09-22", "2025-09-23"]
EARLIER_LEDGERS = (
    "holdout.json", "holdout_pairs_2026H2.json", "holdout_spy.json", "holdout_h60.json", "holdout_swing.json",
    "tsmom_holdout_spent.json", "tl_v0_holdout_spent.json", "tl_bounce_holdout_spent.json",
    "tl_v1_holdout_spent.json", "holdout_htf_ben.json", "holdout_htf_ben_v1.json", "holdout_htf_ben_v2.json",
    "holdout_w16_sb.json", "holdout_w16_dvp.json", "holdout_w16_bb.json", "holdout_crudele_3s.json",
    "holdout_breit_cap.json", "holdout_breit_cap_cl4h.json", "holdout_macro_flag.json",
    "holdout_chartmark_v1.json", "holdout_chartmark_short_v1.json", "holdout_chartmark_v2.json")


def _h(tmp_path):
    h = Holdout("TL-v2", "holdout_tl_v2.json", "TL-v2", "REGISTERED_tl_v2.md")
    h.ledger_path = tmp_path / "holdout_tl_v2.json"
    return h


def test_the_ledger_and_candidate_are_the_registered_ones():
    assert TH.H.ledger_name == "holdout_tl_v2.json" and TH.H.candidate == "TL-v2"
    assert TH.LEDGER_PATH.name == "holdout_tl_v2.json" and "holdout_tl_v2.json" in OWN_LEDGERS


def test_training_side_excludes_2022_01_03_onward_and_the_seen_window():
    keep, aside, label = TH.split_dates(DATES)
    assert keep == ["2021-12-30", "2021-12-31"] and aside == 3 and "training" in label
    assert TH.is_locked("2022-01-03") and not TH.is_locked("2021-12-31")


@pytest.mark.parametrize("kw", [{"limit": 10}, {"limit": 0}, {"markets": ["CL"]}, {"tail": 5}])
def test_limit_and_every_narrowing_flag_are_refused_on_both_sides(kw, tmp_path):
    with pytest.raises(HoldoutRefused):
        TH.split_dates(DATES, **kw)
    h = _h(tmp_path)
    with pytest.raises(HoldoutRefused):
        h.split_dates(DATES, spend=True, candidate="TL-v2", verdict="PASS", **kw)
    assert not h.ledger_path.exists()


@pytest.mark.parametrize("name", EARLIER_LEDGERS)
def test_every_earlier_ledger_is_refused_by_name(name):
    with pytest.raises(HoldoutRefused) as e:
        TH.load_for(name)
    assert "not the TL-v2 holdout" in str(e.value)
    TH.load_for("holdout_tl_v2.json")        # its own name passes


def test_the_earlier_ledgers_are_all_known_to_the_shared_refusal_lists():
    known = set(OTHER_LINES) | set(OWN_LEDGERS)
    assert set(EARLIER_LEDGERS) <= known


def test_only_the_tl_v2_primary_may_spend_and_only_with_a_pass(tmp_path):
    h = _h(tmp_path)
    for bad in ("TL-v2 + S/R", "TL-v2-SR", "TL-v2-N20", "TL-v1", "TL-v0-rev", "C1", "C3", "tl_v2", None):
        with pytest.raises(HoldoutRefused):
            h.split_dates(DATES, spend=True, candidate=bad, verdict="PASS")
    for v in ("FAIL", None, "pass", "9 of 10"):
        with pytest.raises(HoldoutRefused):
            h.split_dates(DATES, spend=True, candidate="TL-v2", verdict=v)
    assert not h.ledger_path.exists(), "a refused spend must not write the ledger"


def test_spending_hands_over_only_the_holdout_window_and_writes_the_ledger_in_the_same_call(tmp_path):
    h = _h(tmp_path)
    keep, _, label = h.split_dates(DATES, spend=True, candidate="TL-v2", verdict="PASS")
    assert keep == ["2022-01-03", "2025-09-22"] and "LOCKED" in label
    rec = json.loads(h.ledger_path.read_text(encoding="utf-8"))
    assert rec["candidate"] == "TL-v2" and rec["verdict"] == "PASS" and rec["holdout_to"] == "2025-09-22"


def test_a_second_spend_is_refused_even_by_the_same_candidate(tmp_path):
    h = _h(tmp_path)
    h.split_dates(DATES, spend=True, candidate="TL-v2", verdict="PASS")
    before = h.ledger_path.read_text(encoding="utf-8")
    with pytest.raises(HoldoutRefused) as e:
        h.split_dates(DATES, spend=True, candidate="TL-v2", verdict="PASS")
    assert "already spent" in str(e.value)
    assert h.ledger_path.read_text(encoding="utf-8") == before


def test_the_seen_window_is_reported_only(tmp_path):
    keep, label = TH.seen_dates(DATES)
    assert keep == ["2025-09-23"] and "not evidence" in label


def test_no_ledger_for_this_line_is_committed_before_it_is_spent():
    assert not TH.LEDGER_PATH.exists(), "holdout_tl_v2.json exists: the holdout has been spent"


def test_the_backtest_and_preflight_route_dates_through_the_tl_v0_cut():
    """The training loader used by the pre-flight and the engine cuts 2022-01-01 onward before any bar
    is built (strategy.tl_v0.bars.training_sessions -> split_dates), so neither module has a path to
    the holdout; neither imports this module's spend."""
    import inspect
    from strategy.tl_v0 import bars
    from strategy.tl_v2 import engine, preflight
    assert "split_dates" in inspect.getsource(bars.training_sessions)
    for mod in (engine, preflight):
        src = inspect.getsource(mod)
        assert "spend=True" not in src and "verdict" not in src.replace("verdict/", "")
