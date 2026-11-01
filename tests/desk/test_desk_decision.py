"""Tests for the decision gate, the CSV log, status and the ranking summary."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone

import pytest

from desk import config as cfgmod
from desk import decision, pipeline, status, summary

RULES = {"shares_per_symbol": 1, "max_hold_days": 180, "max_open_positions": 15}
SNAP = {"price": {"close": 100.0}, "indicators": {"atr14": 3.0}}


def good(**over):
    d = {"ticker": "MPC", "run_date": "2026-10-28", "rating": "Overweight", "conviction": 7,
         "entry": 100.0, "stop": 92.0, "target": 124.0, "horizon_days": 120, "size_shares": 1,
         "thesis": "Refining margins hold.", "key_risks": ["crack spreads", "outages"]}
    d.update(over)
    return d


def check(d, snap=SNAP):
    return decision.validate(d, "MPC", "2026-10-28", snap, RULES)


def report_with(d, extra=""):
    return f"# Final\nSome text\n```json\n{json.dumps(d)}\n```\n{extra}"


# ------------------------------------------------------------- extraction

def test_extract_takes_the_last_json_block_only():
    text = '```json\n{"a": 1}\n```\nmore\n```json\n{"a": 2}\n```\n'
    assert decision.extract_json(text) == {"a": 2}


@pytest.mark.parametrize("text, msg", [
    ("no block here", "no ```json block"),
    ("```json\n{not json}\n```", "not valid JSON"),
    ("```json\n[1,2]\n```", "must be an object"),
])
def test_extract_failures_are_explained(text, msg):
    with pytest.raises(ValueError, match=msg):
        decision.extract_json(text)


# ------------------------------------------------------------- validation

def test_good_buy_passes_with_rr_computed():
    errors, warns, clean = check(good())
    assert errors == [] and warns == []
    assert clean["actionable"] is True
    assert clean["risk_per_share"] == 8.0 and clean["reward_risk"] == 3.0


@pytest.mark.parametrize("over, fragment", [
    ({"ticker": "AMZN"}, "ticker is"),
    ({"run_date": "2026-10-27"}, "run_date is"),
    ({"rating": "Strong Buy"}, "rating must be"),
    ({"conviction": 11}, "conviction"),
    ({"conviction": "7"}, "conviction"),
    ({"conviction": True}, "conviction"),
    ({"size_shares": 5}, "1 share per symbol"),
    ({"horizon_days": 400}, "horizon_days"),
    ({"horizon_days": 0}, "horizon_days"),
    ({"stop": 105.0}, "stop must be below entry"),
    ({"target": 99.0}, "target must be above entry"),
    ({"stop": None}, "stop must be a positive"),
    ({"entry": -1}, "entry must be a positive"),
    ({"thesis": "  "}, "thesis"),
    ({"key_risks": []}, "key_risks"),
    ({"key_risks": [""]}, "key_risks"),
])
def test_each_bad_field_is_rejected(over, fragment):
    errors, _, _ = check(good(**over))
    assert any(fragment in e for e in errors), errors


def test_rating_is_case_insensitive_and_normalised():
    _, _, clean = check(good(rating="overweight"))
    assert clean["rating"] == "Overweight"


def test_warnings_do_not_block():
    _, w, _ = check(good(target=105.0))                       # reward:risk 0.625
    assert any("reward:risk" in x for x in w)
    _, w, _ = check(good(entry=115.0, stop=107.0, target=140.0))   # entry 15% above last close
    assert any("from the last close" in x for x in w)
    _, w, _ = check(good(stop=99.0, target=110.0))             # stop 0.33 ATR away
    assert any("noise" in x for x in w)
    _, w, _ = check(good(stop=60.0, target=200.0))             # stop 13 ATR away
    assert any("very wide" in x for x in w)


@pytest.mark.parametrize("rating", ["Hold", "Underweight", "Sell"])
def test_non_buy_needs_no_prices_and_never_becomes_a_position(rating):
    errors, _, clean = check(good(rating=rating, entry=None, stop=None, target=None, size_shares=0))
    assert errors == [] and clean["actionable"] is False and clean["entry"] is None


@pytest.mark.parametrize("hz", [None, 0, 1, 90, 400, "n/a"])
@pytest.mark.parametrize("rating", ["Hold", "Underweight", "Sell"])
def test_non_buy_never_fails_on_horizon_and_logs_it_empty(rating, hz):
    d = good(rating=rating, entry=None, stop=None, target=None, size_shares=0, horizon_days=hz)
    errors, warns, clean = check(d)
    assert errors == [] and clean["horizon_days"] is None and clean["actionable"] is False


def test_non_buy_with_prices_warns_and_drops_them():
    errors, w, clean = check(good(rating="Hold"))
    assert errors == [] and clean["entry"] is None and any("ignored" in x for x in w)


def test_validation_works_without_a_snapshot():
    errors, _, clean = check(good(), snap=None)
    assert errors == [] and clean["last_close"] is None


# ----------------------------------------------- a Hold's conditional plan (W18-0007)

def plan(**over):
    p = {"revisit_on": "2026-11-04", "trigger": {"type": "close_above", "level": 101.5},
         "entry_zone": [102.0, 105.0], "stop": 95.0, "target": 125.0, "size_note": "half size"}
    p.update(over)
    return p


def hold(**over):
    return good(rating="Hold", entry=None, stop=None, target=None, size_shares=0, horizon_days=None,
                watch_plan=plan(), **over)


def test_hold_with_a_plan_is_watched_but_never_actionable():
    errors, warns, c = check(hold())
    assert errors == [] and warns == []
    assert c["actionable"] is False and c["watch"] is True
    assert c["entry"] is None and c["stop"] is None and c["target"] is None and c["horizon_days"] is None
    assert (c["plan_revisit_on"], c["plan_trigger"]) == ("2026-11-04", "close_above 101.5")
    assert (c["plan_zone_low"], c["plan_zone_high"], c["plan_stop"], c["plan_target"]) == (102.0, 105.0, 95.0, 125.0)
    assert c["plan_size_note"] == "half size"


@pytest.mark.parametrize("p", [None, "absent"])
def test_hold_without_a_plan_is_not_watched(p):
    d = hold()
    d.pop("watch_plan") if p == "absent" else d.update(watch_plan=None)
    errors, _, c = check(d)
    assert errors == [] and c["watch"] is False and "plan_trigger" not in c


@pytest.mark.parametrize("over, fragment", [
    ({"revisit_on": "2026-10-28"}, "revisit_on must be after"),                 # same day as run_date
    ({"revisit_on": "2027-03-01"}, "within 90 days"),
    ({"revisit_on": "soon"}, "revisit_on must be a date"),
    ({"revisit_on": None}, "revisit_on must be a date"),
    ({"trigger": "close_above 101"}, "trigger must be"),
    ({"trigger": {"type": "intraday_above", "level": 101}}, "trigger must be"),
    ({"trigger": {"type": "close_above", "level": -1}}, "trigger must be"),
    ({"trigger": {"type": "close_above", "level": True}}, "trigger must be"),
    ({"entry_zone": [105.0, 102.0]}, "entry_zone must be"),
    ({"entry_zone": [102.0]}, "entry_zone must be"),
    ({"entry_zone": "102-105"}, "entry_zone must be"),
    ({"stop": 103.0}, "stop must be below the entry zone"),
    ({"stop": None}, "watch_plan.stop must be"),
    ({"target": 104.0}, "target must be above the entry zone"),
    ({"target": 0}, "watch_plan.target must be"),
    ({"size_note": 5}, "size_note must be a string"),
])
def test_each_bad_plan_field_is_rejected(over, fragment):
    d = hold()
    d["watch_plan"] = plan(**over)
    errors, _, _ = check(d)
    assert any(fragment in e for e in errors), errors


def test_plan_that_is_not_an_object_is_rejected():
    d = hold()
    d["watch_plan"] = "buy if it closes above 101"
    errors, _, _ = check(d)
    assert any("watch_plan must be an object" in e for e in errors)


def test_plan_warns_on_poor_reward_risk_but_still_passes():
    d = hold()
    d["watch_plan"] = plan(target=108.0)                       # (108-105)/(105-95) = 0.3
    errors, warns, c = check(d)
    assert errors == [] and c["watch"] is True and any("watch_plan reward:risk" in w for w in warns)


@pytest.mark.parametrize("rating", ["Underweight", "Sell", "Buy", "Overweight"])
def test_plan_on_any_rating_but_hold_is_ignored_with_a_warning(rating):
    d = good(rating=rating, watch_plan=plan())
    if rating not in decision.ACTIONABLE:
        d.update(entry=None, stop=None, target=None, size_shares=0, horizon_days=None)
    errors, warns, c = check(d)
    assert errors == [] and c["watch"] is False and any("watch_plan given" in w for w in warns)


def test_plan_survives_the_csv_and_old_rows_gain_empty_columns(tmp_path):
    p = tmp_path / "decisions.csv"
    old = ["run_date", "ticker", "rating", "actionable", "conviction", "warnings", "decided_at_utc"]
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=old)
        w.writeheader()
        w.writerow({"run_date": "2026-10-27", "ticker": "AMZN", "rating": "Underweight", "actionable": "False",
                    "conviction": "4", "warnings": "", "decided_at_utc": "2026-10-27T01:00:00Z"})
    _, _, c = check(hold())
    decision.log_decision(p, c)
    rows = list(csv.DictReader(p.open("r", encoding="utf-8", newline="")))
    assert list(rows[0].keys()) == decision.CSV_COLUMNS
    amzn, mpc = rows
    assert amzn["ticker"] == "AMZN" and amzn["watch"] == "" and amzn["plan_trigger"] == ""
    assert mpc["watch"] == "True" and mpc["actionable"] == "False" and mpc["entry"] == ""
    assert (mpc["plan_trigger"], mpc["plan_zone_low"], mpc["plan_zone_high"]) == ("close_above 101.5", "102.0", "105.0")


def test_process_logs_a_watch_end_to_end_and_cli_says_so(tmp_path, capsys):
    cfg, rd = setup_run(tmp_path, hold())
    cfgp = tmp_path / "c.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    assert decision.main(["--ticker", "MPC", "--date", "2026-10-28", "--config", str(cfgp)]) == 0
    assert "(no position; watching: close_above 101.5, revisit 2026-11-04)" in capsys.readouterr().out
    saved = json.loads((rd / pipeline.DECISION_JSON).read_text(encoding="utf-8"))
    assert saved["watch"] is True and saved["plan_stop"] == 95.0


# ---------------------------------------------------------------- the log

def test_log_inserts_replaces_and_sorts(tmp_path):
    p = tmp_path / "decisions.csv"
    t0 = datetime(2026, 10, 28, 1, 2, 3, tzinfo=timezone.utc)
    _, _, a = check(good())
    decision.log_decision(p, a, t0)
    _, _, b = decision.validate(good(ticker="AMZN"), "AMZN", "2026-10-28", SNAP, RULES)
    decision.log_decision(p, b, t0)
    _, _, a2 = check(good(conviction=9))
    decision.log_decision(p, a2, t0)                          # re-run replaces, does not duplicate
    rows = list(csv.DictReader(p.open("r", encoding="utf-8", newline="")))
    assert [r["ticker"] for r in rows] == ["AMZN", "MPC"] and len(rows) == 2
    assert rows[1]["conviction"] == "9" and rows[1]["decided_at_utc"] == "2026-10-28T01:02:03Z"
    assert list(rows[0].keys()) == decision.CSV_COLUMNS


def test_log_joins_several_warnings_into_one_cell(tmp_path):
    p = tmp_path / "d.csv"
    _, w, c = check(good(target=100.5, stop=99.0))
    assert len(w) >= 2
    decision.log_decision(p, c)
    row = list(csv.DictReader(p.open("r", encoding="utf-8", newline="")))[0]
    assert " | " in row["warnings"]


# ------------------------------------------------------ end to end (files)

def make_cfg(tmp_path):
    cfg = cfgmod.load_config()
    cfg["runs_dir"] = str(tmp_path / "runs")
    return cfg


def setup_run(tmp_path, d, ticker="MPC", with_snapshot=True):
    cfg = make_cfg(tmp_path)
    rd = cfgmod.run_dir(cfg, "2026-10-28", ticker)
    rd.mkdir(parents=True)
    (rd / pipeline.FINAL_REPORT).write_text(report_with(d), encoding="utf-8")
    if with_snapshot:
        (rd / "snapshot.json").write_text(json.dumps(SNAP), encoding="utf-8")
    return cfg, rd


def test_process_writes_decision_json_and_csv_when_valid(tmp_path):
    cfg, rd = setup_run(tmp_path, good())
    csvp = cfgmod.runs_dir(cfg) / pipeline.DECISIONS_CSV
    errors, _, clean = decision.process(rd, "MPC", "2026-10-28", cfg["paper_rules"], csvp)
    assert errors == [] and (rd / pipeline.DECISION_JSON).exists() and csvp.exists()
    assert json.loads((rd / pipeline.DECISION_JSON).read_text(encoding="utf-8"))["reward_risk"] == 3.0


def test_process_writes_nothing_when_invalid(tmp_path):
    cfg, rd = setup_run(tmp_path, good(stop=120.0))
    csvp = cfgmod.runs_dir(cfg) / pipeline.DECISIONS_CSV
    errors, _, clean = decision.process(rd, "MPC", "2026-10-28", cfg["paper_rules"], csvp)
    assert errors and clean is None
    assert not (rd / pipeline.DECISION_JSON).exists() and not csvp.exists()


def test_process_reports_missing_report_and_missing_block(tmp_path):
    cfg = make_cfg(tmp_path)
    rd = cfgmod.run_dir(cfg, "2026-10-28", "MPC")
    rd.mkdir(parents=True)
    csvp = tmp_path / "x.csv"
    errors, _, _ = decision.process(rd, "MPC", "2026-10-28", cfg["paper_rules"], csvp)
    assert "does not exist" in errors[0]
    (rd / pipeline.FINAL_REPORT).write_text("prose only", encoding="utf-8")
    errors, _, _ = decision.process(rd, "MPC", "2026-10-28", cfg["paper_rules"], csvp)
    assert "no ```json block" in errors[0]


def test_cli_exit_codes(tmp_path, capsys):
    cfg, rd = setup_run(tmp_path, good())
    cfgp = tmp_path / "c.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    assert decision.main(["--ticker", "mpc", "--date", "2026-10-28", "--config", str(cfgp)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("OK MPC Overweight") and "reward:risk 3.0" in out
    (rd / pipeline.FINAL_REPORT).write_text(report_with(good(rating="Nope")), encoding="utf-8")
    assert decision.main(["--ticker", "MPC", "--date", "2026-10-28", "--config", str(cfgp)]) == 2
    assert "INVALID MPC" in capsys.readouterr().out


# ----------------------------------------------------------------- status

def test_stage_follows_the_files(tmp_path):
    rd = tmp_path / "MPC"
    rd.mkdir()
    assert status.stage(rd) == "not started"
    (rd / "snapshot.json").write_text("{}", encoding="utf-8")
    assert status.stage(rd) == "prepared"
    for _, f in pipeline.ANALYSTS:
        (rd / f).write_text("x", encoding="utf-8")
    assert status.stage(rd) == "analysts done"
    (rd / "bull.md").write_text("x", encoding="utf-8")
    (rd / "bear.md").write_text("x", encoding="utf-8")
    assert status.stage(rd) == "in progress (last: desk-bear)"
    (rd / pipeline.DECISION_JSON).write_text("{}", encoding="utf-8")
    assert status.stage(rd) == "decided"


def test_pending_skips_decided_tickers_and_keeps_config_order(tmp_path):
    cfg = make_cfg(tmp_path)
    done = cfgmod.run_dir(cfg, "2026-10-28", "AMZN")
    done.mkdir(parents=True)
    (done / pipeline.DECISION_JSON).write_text("{}", encoding="utf-8")
    p = status.pending(cfg, "2026-10-28")
    assert "AMZN" not in p and p[0] == "MPC" and len(p) == 19
    assert status.pending(cfg, "2026-10-29")[:2] == ["MPC", "AMZN"]       # a new day starts clean


def test_status_cli_pending_limit(tmp_path, capsys):
    cfg = make_cfg(tmp_path)
    cfgp = tmp_path / "c.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    assert status.main(["--pending", "--limit", "3", "--date", "2026-10-28", "--config", str(cfgp)]) == 0
    assert capsys.readouterr().out.strip() == "MPC AMZN INTC"


# ---------------------------------------------------------------- summary

def row(t, conv, rr, act=True, rating="Buy"):
    return {"ticker": t, "conviction": str(conv), "reward_risk": str(rr), "actionable": str(act),
            "rating": rating, "entry": "1", "stop": "0.9", "target": "1.3", "horizon_days": "90", "warnings": ""}


def test_rank_orders_by_conviction_then_reward_risk_then_ticker_and_caps():
    rows = [row("AAA", 7, 2.0), row("BBB", 9, 1.6), row("CCC", 7, 3.0), row("DDD", 7, 2.0),
            row("EEE", 3, 5.0, act=False, rating="Hold")]
    r = summary.rank(rows, max_open=3)
    assert [x["ticker"] for x in r] == ["BBB", "CCC", "AAA", "DDD"]
    assert [x["take"] for x in r] == [True, True, True, False]


def test_render_lists_missing_and_marks_wait():
    rows = [row("AAA", 9, 2.0), row("BBB", 8, 2.0), row("CCC", 2, 0, act=False, rating="Sell")]
    text = summary.render("2026-10-28", rows, ["ZZZ"], max_open=1)
    assert "NOT DECIDED YET: ZZZ" in text
    assert "| 1 | AAA | Buy | 9 |" in text and "TAKE" in text
    assert "WAIT (over the position cap)" in text and "## No position" in text and "CCC" in text


def watch_row(t, date, revisit, rating="Hold"):
    r = row(t, 4, 0, act=False, rating=rating)
    r.update(run_date=date, watch="True", plan_trigger="close_above 100", plan_zone_low="101", plan_zone_high="104",
             plan_stop="95", plan_target="120", plan_revisit_on=revisit, plan_size_note="half size")
    return r


def test_render_lists_watches_apart_from_no_position():
    rows = [watch_row("AAA", "2026-10-28", "2026-11-04"), row("CCC", 2, 0, act=False, rating="Sell")]
    text = summary.render("2026-10-28", rows, [], max_open=1)
    assert "1 watching, 1 no position" in text
    watching, nopos = text.split("## Watching")[1].split("## No position")
    assert "AAA" in watching and "close_above 100" in watching and "101-104" in watching and "CCC" not in watching
    assert "CCC" in nopos and "AAA" not in nopos


def test_open_watches_use_the_latest_row_per_ticker_and_flag_due_ones():
    rows = [watch_row("AAA", "2026-10-20", "2026-10-27"),         # superseded by a later Buy below
            row("AAA", 8, 2.0) | {"run_date": "2026-10-28"},
            watch_row("BBB", "2026-10-25", "2026-10-29"),          # revisit date passed -> due
            watch_row("CCC", "2026-10-26", "2026-11-10"),          # not yet
            watch_row("DDD", "2026-10-30", "2026-11-06")]          # decided after "today": not known yet
    got = summary.open_watches(rows, "2026-10-30")
    assert [(r["ticker"], r["due"]) for r in got] == [("BBB", True), ("DDD", False), ("CCC", False)]
    text = summary.render("2026-10-30", [], [], 15, got)
    assert "## Open watches" in text and "DUE" in text


def test_old_rows_without_watch_columns_still_summarise():
    assert summary.open_watches([row("AAA", 5, 1) | {"run_date": "2026-10-28"}], "2026-10-30") == []
    assert "watching" in summary.render("2026-10-28", [row("AAA", 5, 1)], [], 15)


def test_summary_cli_end_to_end(tmp_path, capsys):
    cfg = make_cfg(tmp_path)
    cfgp = tmp_path / "c.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    csvp = cfgmod.runs_dir(cfg) / pipeline.DECISIONS_CSV
    _, _, c = check(good())
    decision.log_decision(csvp, c)
    assert summary.main(["--date", "2026-10-28", "--config", str(cfgp)]) == 0
    assert (cfgmod.day_dir(cfg, "2026-10-28") / "SUMMARY.md").exists()
    assert "MPC" in capsys.readouterr().out
