"""W18-0003: the scheduled run's ticker selection, the NAS pull / outbox, and the phone message."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from desk import notify, pipeline, pull_nas, schedule

DEC_COLS = ["run_date", "ticker", "rating", "actionable", "conviction", "entry", "stop", "target", "horizon_days",
            "size_shares", "risk_per_share", "reward_risk", "last_close", "atr14", "warnings", "decided_at_utc",
            "watch", "plan_revisit_on", "plan_trigger", "plan_zone_low", "plan_zone_high", "plan_stop",
            "plan_target", "plan_size_note"]
ORD_COLS = ["logged_at_utc", "run_date", "ticker", "rating", "conviction", "outcome", "reason", "entry", "stop",
            "target", "shares", "risk_usd", "hold_until", "order_ref", "parent_order_id", "take_profit_order_id",
            "stop_order_id", "broker_status"]
TICKERS = ["AAA", "BBB", "CCC", "DDD", "EEE"]
MON, TUE = "2026-11-09", "2026-11-10"        # 2026-11-09 is a Monday


def cfg_for(tmp: Path, **extra) -> dict:
    c = {"tickers": TICKERS, "runs_dir": str(tmp), "paper_rules": {"max_open_positions": 15}}
    c.update(extra)
    return c


def write_csv(path: Path, cols, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def dec(ticker, run_date, rating="Hold", actionable=False, **kw):
    return dict(run_date=run_date, ticker=ticker, rating=rating, actionable=str(actionable), conviction="5",
                decided_at_utc=f"{run_date}T01:00:00Z", watch=str(kw.pop("watch", False)), **kw)


def order(ticker, run_date, hold_until, outcome="PLACED"):
    return dict(logged_at_utc=f"{run_date}T02:00:00Z", run_date=run_date, ticker=ticker, outcome=outcome,
                hold_until=hold_until)


def decided_marker(tmp: Path, date: str, ticker: str):
    d = tmp / date / ticker
    d.mkdir(parents=True)
    (d / pipeline.DECISION_JSON).write_text("{}", encoding="utf-8")


def test_monday_is_a_full_run_of_everything_not_yet_decided(tmp_path):
    cfg = cfg_for(tmp_path)
    decided_marker(tmp_path, MON, "BBB")
    p = schedule.plan(cfg, MON)
    assert p["mode"] == "full"
    assert p["tickers"] == ["AAA", "CCC", "DDD", "EEE"]
    assert p["already_decided"] == ["BBB"]


def test_full_run_weekday_comes_from_config(tmp_path):
    cfg = cfg_for(tmp_path, schedule={"full_run_weekday": 1})
    assert schedule.plan(cfg, TUE)["mode"] == "full"
    assert schedule.plan(cfg, MON)["mode"] != "full"


def test_other_days_run_only_active_names_and_say_why(tmp_path):
    cfg = cfg_for(tmp_path)
    write_csv(tmp_path / pipeline.DECISIONS_CSV, DEC_COLS, [
        dec("AAA", "2026-11-02", "Overweight", True),                                       # bought, order placed
        dec("BBB", "2026-11-02", "Overweight", True),                                       # buy, never ordered
        dec("CCC", "2026-11-02", "Hold", watch=True, plan_revisit_on=TUE, plan_trigger="close_above 10"),   # due
        dec("DDD", "2026-11-02", "Hold", watch=True, plan_revisit_on="2026-11-11", plan_trigger="x"),      # not due
        dec("EEE", "2026-11-02", "Underweight"),
    ])
    write_csv(tmp_path / pipeline.ORDERS_CSV, ORD_COLS, [order("AAA", "2026-11-02", "2027-01-01")])
    p = schedule.plan(cfg, TUE)
    assert p["mode"] == "active"
    assert p["tickers"] == ["AAA", "BBB", "CCC"]
    assert "hold until 2027-01-01" in p["reasons"]["AAA"]
    assert "no order logged" in p["reasons"]["BBB"]
    assert "watch plan due" in p["reasons"]["CCC"]


def test_expired_hold_rejected_orders_and_decided_names_are_not_active(tmp_path):
    cfg = cfg_for(tmp_path)
    write_csv(tmp_path / pipeline.DECISIONS_CSV, DEC_COLS, [dec("AAA", "2026-11-02", "Hold"), dec("BBB", "2026-11-02", "Hold"),
                                                            dec("CCC", "2026-11-02", "Hold")])
    write_csv(tmp_path / pipeline.ORDERS_CSV, ORD_COLS, [
        order("AAA", "2026-11-02", "2026-11-09"),                  # hold_until already passed
        order("BBB", "2026-11-02", "2027-01-01", outcome="REJECTED"),
        order("CCC", "2026-11-02", "2027-01-01"),
    ])
    decided_marker(tmp_path, TUE, "CCC")                            # already decided today
    p = schedule.plan(cfg, TUE)
    assert p["mode"] == "none" and p["tickers"] == []


def test_no_files_at_all_is_a_quiet_day_not_a_crash(tmp_path):
    assert schedule.plan(cfg_for(tmp_path), TUE)["mode"] == "none"


def test_a_name_with_a_working_order_is_not_listed_twice_for_a_due_watch(tmp_path):
    cfg = cfg_for(tmp_path)
    write_csv(tmp_path / pipeline.DECISIONS_CSV, DEC_COLS, [
        dec("AAA", "2026-11-02", "Hold", watch=True, plan_revisit_on=TUE, plan_trigger="t")])
    write_csv(tmp_path / pipeline.ORDERS_CSV, ORD_COLS, [order("AAA", "2026-11-01", "2027-01-01")])
    p = schedule.plan(cfg, TUE)
    assert p["tickers"] == ["AAA"] and "desk order" in p["reasons"]["AAA"]


# ---------------------------------------------------------------------- NAS pull / outbox
def test_scp_pull_command_uses_O_flag_key_and_the_day_folder(tmp_path):
    cfg = cfg_for(tmp_path)
    cmd = pull_nas.scp_pull_cmd(cfg, TUE, key="/k/key", dest=tmp_path)
    assert cmd[:3] == ["scp", "-O", "-r"]
    assert cmd[cmd.index("-i") + 1] == "/k/key"
    assert "BatchMode=yes" in cmd
    assert cmd[-2] == f"claude@192.168.1.109:/volume1/docker/desk/var/desk_runs/{TUE}"
    assert cmd[-1] == str(tmp_path)


def test_pull_failure_returns_2_and_names_the_nas_job(tmp_path, capsys):
    run = lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="No such file or directory")
    assert pull_nas.pull(cfg_for(tmp_path), TUE, key="k", dest=tmp_path, run=run) == 2
    out = capsys.readouterr().out
    assert "PULL FAILED" in out and "prepare" in out


def test_pull_never_passes_a_stripped_environment(tmp_path):
    seen = {}
    def run(cmd, **kw):
        seen.update(kw)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    pull_nas.pull(cfg_for(tmp_path), TUE, key="k", dest=tmp_path, run=run)
    assert "env" not in seen          # WinError 10106 if SYSTEMROOT is missing


def test_outbox_uploads_a_part_file_then_renames_it(tmp_path):
    calls = []
    def run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    assert pull_nas.push_outbox(cfg_for(tmp_path), "hello", "desk_2026-11-10.txt", key="k", run=run, tmp_dir=tmp_path) == 0
    assert calls[0][0] == "scp" and calls[0][-1].endswith("/outbox/desk_2026-11-10.txt.part")
    assert calls[1][0] == "ssh" and "mv '/volume1/docker/desk/var/outbox/desk_2026-11-10.txt.part'" in calls[1][-1]


@pytest.mark.parametrize("bad", ["../x.txt", "a/b.txt", "x.sh", "x.txt; rm -rf /.txt\\", "a b.txt", "a'b.txt", ".hidden.txt"])
def test_outbox_refuses_odd_names(tmp_path, bad):
    with pytest.raises(ValueError):
        pull_nas.push_outbox(cfg_for(tmp_path), "t", bad, key="k", run=lambda *a, **k: None, tmp_dir=tmp_path)


# ---------------------------------------------------------------------- phone message
def test_message_lists_buys_watches_missing_and_never_claims_orders_were_placed():
    rows = [dec("AAA", MON, "Overweight", True, entry="10", stop="9", target="12", reward_risk="2.0"),
            dec("BBB", MON, "Hold", watch=True, plan_trigger="close_above 5", plan_revisit_on="2026-11-20"),
            dec("CCC", MON, "Underweight")]
    rows[0]["conviction"] = "6"
    msg = notify.build_message(MON, rows, ["AAA", "BBB", "CCC", "DDD"], 15, mode="full")
    assert "Desk 2026-11-09 (full): 3 decided, 1 not finished" in msg
    assert "- AAA Overweight 6/10 entry 10 stop 9 target 12 R:R 2.0" in msg
    assert "not ordered yet" in msg and "not placed automatically" in msg
    assert "WATCH: BBB close_above 5 (revisit 2026-11-20)" in msg
    assert "No position: CCC" in msg
    assert "NOT FINISHED: DDD" in msg


def test_message_for_a_quiet_day_and_length_cap():
    assert "No buys today." in notify.build_message(TUE, [], [], 15)
    rows = [dec(f"T{i}", TUE, "Underweight", warnings="w" * 300) for i in range(30)]
    assert len(notify.build_message(TUE, rows, [], 15)) <= notify.MAX_LEN


def test_config_has_the_schedule_and_nas_blocks():
    cfg = json.loads((Path(__file__).resolve().parents[2] / "desk" / "config.json").read_text(encoding="utf-8"))
    assert cfg["schedule"]["full_run_weekday"] == 0
    assert cfg["nas"]["remote_outbox"].startswith("/volume1/docker/desk/")
