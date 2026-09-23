"""H-L1 (W02-0002): the pieces of common/live_vs_sim that decide a number."""
import math

import pandas as pd
import pytest

from common import live_vs_sim as L


def t(strategy, entry, exit_, symbol="AAA", date="2026-09-18", net=0.0):
    return {"strategy": strategy, "symbol": symbol, "date": date,
            "entry_et": entry, "exit_et": exit_, "net": net, "entry_px": 1.0, "exit_px": 1.0}


# --- regime boundaries --------------------------------------------------------

def test_feed_offset_boundary():
    assert L.feed_offset("2026-09-18") == 15
    assert L.feed_offset("2026-09-21") == 0


def test_apex_boundary_matches_paper_fill_apex():
    assert L.apex_on("2026-09-17") and not L.apex_on("2026-09-18")


# --- the cap replay -------------------------------------------------------------

def test_cap_inf_is_identity():
    rows = [t("mcl", "04:00", "04:10"), t("mc5", "04:01", "04:20"), t("mcl", "04:02", "04:03")]
    assert L.replay_cap(rows, math.inf) == rows


def test_cap_refuses_fourth_concurrent():
    rows = [t("mcl", "04:00", "05:00", "A"), t("mc5", "04:01", "05:00", "B"),
            t("mcl", "04:02", "05:00", "C"), t("mc5", "04:03", "05:00", "D")]
    adm = L.replay_cap(rows, 3)
    assert [r["symbol"] for r in adm] == ["A", "B", "C"]


def test_exit_at_t_releases_before_entry_at_t():
    rows = [t("mcl", "04:00", "04:05", "A"), t("mc5", "04:05", "04:10", "B")]
    assert len(L.replay_cap(rows, 1)) == 2


def test_same_minute_tie_order_is_the_bracket():
    rows = [t("mcl", "04:00", "04:30", "A"), t("mc5", "04:00", "04:30", "B")]
    assert [r["strategy"] for r in L.replay_cap(rows, 1, first="mcl")] == ["mcl"]
    assert [r["strategy"] for r in L.replay_cap(rows, 1, first="mc5")] == ["mc5"]


def test_per_strategy_scope_counts_own_positions_only():
    rows = [t("mc5", "04:00", "05:00", "A"), t("mc5", "04:01", "05:00", "B"),
            t("mc5", "04:02", "05:00", "C"), t("mcl", "04:03", "05:00", "D"),
            t("mc5", "04:04", "05:00", "E")]
    shared = {r["symbol"] for r in L.replay_cap(rows, 3, "shared")}
    per = {r["symbol"] for r in L.replay_cap(rows, 3, "strategy")}
    assert shared == {"A", "B", "C"}
    assert per == {"A", "B", "C", "D"}


def test_cap_is_per_session():
    rows = [t("mcl", "04:00", "05:00", "A", "2026-09-18"), t("mcl", "04:00", "05:00", "A", "2026-09-21")]
    assert len(L.replay_cap(rows, 1)) == 2


# --- the join -------------------------------------------------------------------

def lv(entry_min, symbol="AAA", pnl=0.0, date="2026-09-18"):
    return {"strategy": "mcl", "symbol": symbol, "date": date, "entry_min": entry_min,
            "exit_min": entry_min + 5, "entry_px": 1.0, "exit_px": 1.0, "qty": 100, "pnl": pnl}


def test_join_tolerance_is_two_bars():
    sim = [t("mcl", "04:10", "04:20")]
    assert len(L.join([lv(252.0)], sim, "mcl")[0]) == 1      # 04:12 = +2 min
    assert len(L.join([lv(252.5)], sim, "mcl")[0]) == 0      # +2.5 min
    assert len(L.join([lv(260.0)], [t("mc5", "04:10", "04:20")], "mc5")[0]) == 1   # +10 on MC5


def test_join_is_one_to_one_nearest_first():
    sim = [t("mcl", "04:10", "04:20"), t("mcl", "04:11", "04:20")]
    pairs, lonly, sonly = L.join([lv(251.1)], sim, "mcl")
    assert [(i, j) for i, j, _ in pairs] == [(0, 1)] and sonly == [0] and lonly == []


def test_join_never_crosses_symbol_or_session():
    sim = [t("mcl", "04:10", "04:20", "BBB"), t("mcl", "04:10", "04:20", "AAA", "2026-09-21")]
    pairs, lonly, sonly = L.join([lv(250.0)], sim, "mcl")
    assert pairs == [] and lonly == [0] and sonly == [0, 1]


# --- the decomposition is an identity -------------------------------------------

def test_decompose_identity_holds():
    live = [lv(250.0, pnl=12.0), lv(300.0, pnl=-7.5)]
    live[0]["entry_px"], live[0]["exit_px"] = 1.02, 1.14
    sim = [dict(t("mcl", "04:10", "04:20", net=15.0), entry_px=1.0, exit_px=1.15),
           t("mcl", "06:00", "06:10", net=-3.0)]
    log = pd.DataFrame({"strategy": ["MCL"], "symbol": ["AAA"], "action": ["BUY"],
                        "status": ["SKIPPED_CONCURRENCY_CAP"],
                        "ts_et": [pd.Timestamp("2026-09-18 06:01:00")]})
    d = L.decompose(live, sim, "mcl", log, {"2026-09-18": {"AAA"}})
    assert d["n_match"] == 1 and d["n_lonly"] == 1 and d["n_sonly"] == 1
    assert abs(d["resid"]) < 1e-9
    assert d["m_entry"] == pytest.approx(-2.0) and d["m_exit"] == pytest.approx(-1.0)
    assert d["sim_only_by"]["cap"][0] == 1
    assert d["live_only_by"]["sim no entry near"][0] == 1


# --- the words --------------------------------------------------------------------

def test_words():
    assert L.word(0.1, 2) == "MCL better"
    assert L.word(-2, -0.1) == "MC5 better"
    assert L.word(-1, 1) == "can't tell"


def test_bootstrap_is_seeded_and_brackets_the_point():
    rows = {"mcl": [{"date": f"d{k}", "val": v} for k, v in enumerate([-5, 3, -8, 1, -2, 4])],
            "mc5": [{"date": f"d{k}", "val": v} for k, v in enumerate([-9, -1, -6, -4, 2, -7])]}
    sess = [f"d{k}" for k in range(6)]
    a = L.verdicts(rows, sess, 0.0)
    b = L.verdicts(rows, sess, 0.0)
    assert a["diff"] == b["diff"]          # per_symday is NaN here; NaN != NaN
    lo, hi = a["diff"]["per_trade"]["ci"]
    assert lo <= a["diff"]["per_trade"]["point"] <= hi


def test_a_clear_difference_gets_a_direction():
    sess = [f"d{k}" for k in range(30)]
    rows = {"mcl": [{"date": d, "val": 5.0 + (k % 3)} for k, d in enumerate(sess)],
            "mc5": [{"date": d, "val": -5.0 - (k % 3)} for k, d in enumerate(sess)]}
    assert L.verdicts(rows, sess, 4.26)["diff"]["per_trade"]["word"] == "MCL better"


# --- the live pairing agrees with churn_count's --------------------------------

def test_live_pairing_matches_churn_count_on_the_real_logs():
    from pathlib import Path
    from common.churn_count import round_trips
    d = Path("var/fills")
    if not d.is_dir():
        pytest.skip("no fill logs here")
    log = L.live_log(d)
    ours = L.live_round_trips(log)
    theirs = round_trips(log[log["status"] == "FILLED"])
    assert len(ours) == len(theirs)
    assert sum(x["pnl"] for x in ours) == pytest.approx(float(theirs["pnl"].sum()))
