"""W10-0013 sub 12: the watcher's rules and the compose service that runs it. No network, no NAS."""
from __future__ import annotations

import importlib.util
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("nas_watch", ROOT / "deploy" / "nas_trader" / "watch.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

NY = ZoneInfo("America/New_York")
MON_0600 = datetime(2026, 11, 2, 6, 0, tzinfo=NY)       # a Monday inside the window
MON_1100 = datetime(2026, 11, 2, 11, 0, tzinfo=NY)
SAT_0600 = datetime(2026, 11, 7, 6, 0, tzinfo=NY)


def cfg(**env):
    return watch.Cfg(env)


def lock(now, age=10.0):
    return {"mode": "dry", "strategy": "mcl,mc5", "heartbeat_epoch": now.timestamp() - age}


def test_fresh_heartbeat_in_window_is_fine():
    assert watch.trader_problem(MON_0600, lock(MON_0600), cfg(), MON_0600.timestamp()) is None


def test_missing_lock_in_window_is_a_problem():
    assert "no trader session" in watch.trader_problem(MON_0600, None, cfg(), MON_0600.timestamp())


def test_stale_heartbeat_in_window_is_a_problem():
    msg = watch.trader_problem(MON_0600, lock(MON_0600, age=300), cfg(), MON_0600.timestamp())
    assert "heartbeat stopped" in msg


def test_heartbeat_at_the_limit_is_still_alive():
    assert watch.trader_problem(MON_0600, lock(MON_0600, age=119), cfg(), MON_0600.timestamp()) is None


def test_nothing_checked_outside_window_weekend_or_skip_date():
    assert watch.trader_problem(MON_1100, None, cfg(), MON_1100.timestamp()) is None
    assert watch.trader_problem(SAT_0600, None, cfg(), SAT_0600.timestamp()) is None
    c = cfg(WATCH_SKIP_DATES="2026-11-02")
    assert watch.trader_problem(MON_0600, None, c, MON_0600.timestamp()) is None


def test_window_edges_in_new_york_time_whatever_the_clock_zone():
    utc = ZoneInfo("UTC")
    just_before = datetime(2026, 11, 2, 4, 9, tzinfo=NY).astimezone(utc)
    just_after = datetime(2026, 11, 2, 4, 10, tzinfo=NY).astimezone(utc)
    assert watch.trader_problem(just_before, None, cfg(), 0) is None
    assert watch.trader_problem(just_after, None, cfg(), 0) is not None


def test_read_lock_missing_and_broken(tmp_path):
    assert watch.read_lock(tmp_path) is None
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "session.lock").write_text("{broken", encoding="utf-8")
    assert watch.read_lock(tmp_path) is None
    (tmp_path / "state" / "session.lock").write_text('{"mode": "dry"}', encoding="utf-8")
    assert watch.read_lock(tmp_path) == {"mode": "dry"}


def make(clock, portal_ok=True, lock_value=None, **env):
    sent, pings = [], []
    state = {"ok": portal_ok, "lock": lock_value}
    w = watch.Watcher(cfg(HC_PING_URL="https://hc-ping.com/x", **env), sent.append, clock=clock,
                      lock_reader=lambda: state["lock"], portal=lambda: (state["ok"], "HTTP 530"),
                      pinger=lambda u: pings.append(u) or True)
    return w, sent, pings, state


def test_ping_every_step_even_with_problems():
    w, sent, pings, state = make(lambda: MON_0600.timestamp(), lock_value=None)
    w.step(); w.step()
    assert pings == ["https://hc-ping.com/x"] * 2


def test_no_ping_when_url_unset():
    sent, pings = [], []
    w = watch.Watcher(cfg(), sent.append, clock=lambda: MON_1100.timestamp(), lock_reader=lambda: None,
                      portal=lambda: (True, "HTTP 303"), pinger=lambda u: pings.append(u) or True)
    w.step()
    assert pings == [] and "NO dead-man ping" in sent[0]


def test_portal_needs_three_misses_then_recovers():
    t = {"now": MON_1100.timestamp()}
    w, sent, _, state = make(lambda: t["now"], portal_ok=False)
    w.step(); w.step()
    assert not any("portal" in m and "not answering" in m for m in sent)
    w.step()
    assert any("not answering" in m for m in sent)
    n = len(sent)
    w.step()
    assert len(sent) == n                              # no repeat inside the hour
    state["ok"] = True
    t["now"] += 600
    w.step()
    assert "OK again: portal" in sent[-1]


def test_problem_repeats_after_the_repeat_time():
    t = {"now": MON_0600.timestamp()}
    w, sent, _, _ = make(lambda: t["now"], lock_value=None)
    w.step()
    first = len(sent)
    t["now"] += 3601
    w.step()
    assert len(sent) == first + 1 and "Still a problem" in sent[-1]


def test_a_failing_send_does_not_stop_the_step():
    def boom(_):
        raise OSError("down")
    w = watch.Watcher(cfg(), boom, clock=lambda: MON_1100.timestamp(), lock_reader=lambda: None,
                      portal=lambda: (True, "ok"), pinger=lambda u: True)
    w.step()


# ---------------------------------------------------------------------------- the compose service
COMPOSE = (ROOT / "deploy" / "nas_trader" / "compose.yaml").read_text(encoding="utf-8")


def block(name: str) -> str:
    m = re.search(rf"^  {name}:\n(.*?)(?=^  \w[\w-]*:\n|^\w+:)", COMPOSE, re.S | re.M)
    assert m, name
    return m.group(1)


def test_watch_service_is_isolated_and_read_only():
    b = block("watch")
    assert 'profiles: ["watch"]' in b
    assert "ports:" not in b and "network_mode" not in b and "networks:" not in b
    assert re.search(r":/var-data:ro\b", b) and re.search(r":/watch:ro\b", b)
    assert "read_only: true" in b and "restart: always" in b


def test_watch_script_is_stdlib_only_and_has_no_order_code():
    src = (ROOT / "deploy" / "nas_trader" / "watch.py").read_text(encoding="utf-8")
    imports = set(re.findall(r"^(?:from|import) (\w+)", src, re.M))
    assert imports <= {"argparse", "json", "logging", "os", "sys", "time", "urllib", "datetime", "pathlib", "zoneinfo",
                       "__future__"}
    assert "ib_async" not in src and "placeOrder" not in src


def test_env_example_has_the_watcher_lines_empty():
    env = (ROOT / "deploy" / "nas_trader" / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^HC_PING_URL=$", env, re.M)
