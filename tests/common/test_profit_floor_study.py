#!/usr/bin/env python3
"""H-C2's study reads docs/research/REGISTERED_profit_floor.md §2-§3 as written."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import profit_floor_study as P
from tests.common.test_first_entry_skip import EARLY, LATE

ET = ZoneInfo("America/New_York")
F = P.MEASURED_FRICTION
CUT = "2026-02-01"


def tr(date, net_after_f, symbol="X", start="05:00", k=0, reason="trailing_stop",
       entry_px=5.01, exit_px=4.80, mfe=0.0, armed=False):
    mm = int(start[:2]) * 60 + int(start[3:]) + k
    return {"symbol": symbol, "date": date, "ordinal": k + 1, "net": net_after_f + F,
            "entry_et": f"{mm // 60:02d}:{mm % 60:02d}", "entry_px": entry_px,
            "exit_et": "09:00", "exit_px": exit_px, "reason": reason, "bars_held": 3,
            "mfe_pct": mfe, "armed": armed}


def books(n_syms, base_nets, floor_nets, floor_reason="profit_floor", start_floor="05:00"):
    """Each symbol traded on EARLY and LATE. The FIRST floored trade of each
    symbol-day carries `floor_reason`."""
    base, flo = [], []
    for i in range(n_syms):
        for d in (EARLY, LATE):
            base += [tr(d, v, f"S{i}", k=k) for k, v in enumerate(base_nets)]
            flo += [tr(d, v, f"S{i}", start=start_floor, k=k,
                       reason=floor_reason if k == 0 else "trailing_stop")
                    for k, v in enumerate(floor_nets)]
    return base, flo


def symdays(n_syms):
    return 2 * n_syms


# --- §3 ---------------------------------------------------------------------------

def test_a_clean_improvement_passes():
    base, flo = books(40, [-10, -10], [2, -10])
    tag, why, n = P.verdict(base, flo, CUT, symdays(40), True)
    assert tag == "PASSES", why
    assert n["floor_share"] == pytest.approx(50.0)


def test_no_verdict_without_the_published_baseline():
    base, flo = books(40, [-10, -10], [2, -10])
    tag, why, _ = P.verdict(base, flo, CUT, symdays(40), False)
    assert tag == "NO VERDICT" and "§2" in why


def test_a_rule_that_is_better_per_trade_and_worse_in_total_is_refused():
    base, flo = books(40, [-10], [-6, -6])
    tag, why, _ = P.verdict(base, flo, CUT, symdays(40), True)
    assert tag == "REFUSED" and "$4.26" in why


def test_the_high_friction_level_is_read_too():
    # One base trade at (10.00); two floored at (4.00) each, at $4.26. Both
    # denominators improve there; at $8.92 the extra round trip turns the
    # per-symbol-day delta negative while per trade stays positive.
    base, flo = books(40, [-10], [-4, -4])
    tag, why, n = P.verdict(base, flo, CUT, symdays(40), True)
    assert n["d426"][0] > 0 and n["d426"][1] > 0
    assert n["d892"][0] > 0 and n["d892"][1] < 0
    assert tag == "REFUSED" and "$8.92" in why


def test_a_floor_that_does_not_fire_cannot_pass():
    base, flo = books(40, [-10, -10], [2, -10], floor_reason="trailing_stop")
    tag, why, n = P.verdict(base, flo, CUT, symdays(40), True)
    assert n["floor_share"] == 0.0
    assert tag == "NOTHING" and "5 (floor exits" in why


def test_an_improvement_carried_by_three_names_fails_drop_top_three():
    base, flo = books(40, [-10], [-10])
    for r in flo:
        if r["symbol"] in ("S0", "S1", "S2"):
            r["net"] += 500
    for r in flo[: len(flo) // 5]:
        r["reason"] = "profit_floor"
    tag, why, n = P.verdict(base, flo, CUT, symdays(40), True)
    assert n["drop_delta"] <= 0
    assert "3 (drop-top-3 symbols" in why


def test_drop_top_three_removes_names_not_symbol_days():
    d = {("A", EARLY): 10.0, ("A", LATE): 10.0, ("B", EARLY): 5.0, ("C", EARLY): 4.0,
         ("D", EARLY): 1.0}
    assert P.drop_top_symbols_delta(d) == pytest.approx(1.0)      # A (20), B, C gone


def test_an_empty_half_is_not_a_pass():
    base = [tr(LATE, -10, f"S{i}") for i in range(40)]
    flo = [tr(LATE, 5, f"S{i}", reason="profit_floor") for i in range(40)]
    tag, why, _ = P.verdict(base, flo, CUT, 40, True)
    assert tag == "NOTHING" and "half is empty" in why


def test_one_improving_half_is_not_enough():
    base, flo = books(40, [-10], [-10])
    for r in flo:
        r["reason"] = "profit_floor"
        r["net"] += 5 if r["date"] == LATE else -1
    tag, why, _ = P.verdict(base, flo, CUT, symdays(40), True)
    assert tag == "NOTHING" and "2 (both halves" in why


# --- §2 ---------------------------------------------------------------------------

def test_baseline_check_needs_count_and_per_trade():
    rows = [tr(EARLY, -8.49, f"S{i}") for i in range(10)]
    assert P.baseline_check("MC5", rows, (10, -8.49))[0]
    assert not P.baseline_check("MC5", rows, (11, -8.49))[0]
    assert not P.baseline_check("MC5", rows, (10, -8.40))[0]
    ok, why = P.baseline_check("MC5", rows, None)
    assert not ok and "--expect" in why


def test_published_figures_are_the_itch_p50_reports():
    assert P.PUBLISHED[P.PAIRS] == {"mcl": (3960, -8.81), "mc5": (6630, -8.49)}


def test_parse_expect():
    assert P.parse_expect("mcl=3960:-8.81, mc5=6630:-8.49") == {
        "mcl": (3960, -8.81), "mc5": (6630, -8.49)}
    assert P.parse_expect(None) == {}


def test_the_wrong_tape_is_refused():
    with pytest.raises(SystemExit) as e:
        P.main(["--dataset", "XNAS.BASIC"])
    assert "REFUSED" in str(e.value)


def test_the_registered_rule_is_fifteen_and_ten():
    assert P.PF == (15, 10) and all(pf in (None, P.PF) for _, _, pf in P.BOOKS)


# --- the mechanism lines -------------------------------------------------------

def test_excursion_excludes_the_entry_bar_and_splits_on_the_exit_bar():
    t0 = datetime(2026, 3, 2, 7, 0, tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(4)])
    bars = pd.DataFrame({"high": [9.0, 5.20, 5.10, 6.00]}, index=idx)
    upto, before = P.excursion(bars, str(idx[0]), str(idx[3]), 5.01)
    assert upto == pytest.approx(6.00)          # exit bar included
    assert before == pytest.approx(5.20)        # entry bar's 9.00 never counts
    upto, before = P.excursion(bars, str(idx[0]), str(idx[1]), 5.01)
    assert before == pytest.approx(5.01)        # nothing strictly between -> the entry price


def test_mechanism_counts_fills_positives_and_runners():
    base = [tr(EARLY, 30, "A", mfe=12.0), tr(EARLY, -10, "B", mfe=1.0),
            tr(EARLY, 20, "C", mfe=15.0)]
    flo = [tr(EARLY, 5.74 - F, "A", reason="profit_floor", exit_px=5.10, armed=True),   # at floor
           tr(EARLY, -10, "B"),
           tr(EARLY, -6 - F, "C", reason="profit_floor", exit_px=4.95, armed=True)]     # gapped below entry
    L = "\n".join(P.mechanism_block("MCL", "MCL-floor", base, flo))
    assert "floor exits   2 " in L
    assert "at the floor (less one tick) 1   gapped below it 1   of which below the entry price 1" in L
    assert "runners cut: 2 of MCL's 2 trades" in L
    # forgone, both at $4.26: (30 - (5.74 - F)) + (20 - (-6 - F)) = 58.78
    assert P.money((30 - (5.74 - F)) + (20 - (-6 - F))) in L


def test_render_prints_both_verdicts_and_the_provenance(tmp_path):
    base, flo = books(40, [-10, -10], [2, -10])
    bk = {"MCL": base, "MCL-floor": flo, "MC5": base, "MC5-floor": flo}
    pairs = tmp_path / "p.json"
    pairs.write_text("[]", encoding="utf-8")
    a = argparse.Namespace(dataset="XNAS.ITCH", pairs=str(pairs))
    exp = {"mcl": (len(base), P.per_trade(base, F)), "mc5": (len(base), P.per_trade(base, F))}
    L = "\n".join(P.render(bk, symdays(40), 0, [EARLY, LATE], 1.0, 1, a, [], exp))
    assert L.count("PASSES:") == 2
    assert "sha256" in L and "THE MECHANISM: MC5-floor" in L
