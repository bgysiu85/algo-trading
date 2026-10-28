"""Tests for deploy/nas_trader/run_trader.py (W10-0013 sub 5): the Linux launcher that replaces run_paper.ps1.

The launcher is a safety surface (it decides dry vs paper and which port), so each rule is tested in both directions:
the unsafe value is refused AND the safe value passes. Nothing here touches IBKR.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader" / "run_trader.py"
_spec = importlib.util.spec_from_file_location("run_trader", PATH)
rt = importlib.util.module_from_spec(_spec)
sys.modules["run_trader"] = rt
_spec.loader.exec_module(rt)


def flag(args, name):
    return args[args.index(name) + 1]


# ------------------------------------------------------------------ defaults are the safe ones
def test_default_is_a_dry_run_on_the_paper_port_with_no_yes_flag():
    a = rt.build_args({})
    assert flag(a, "--mode") == "dry" and flag(a, "--port") == "4002" and flag(a, "--strategy") == "mcl"
    assert "--yes" not in a and "--no-feed" not in a and "--no-archive" not in a
    assert flag(a, "--watchlist") == "var/watchlist.txt"


def test_paper_mode_is_only_by_explicit_choice_and_then_passes_yes():
    a = rt.build_args({"TRADER_MODE": "paper"})
    assert flag(a, "--mode") == "paper" and "--yes" in a
    assert "--yes" not in rt.build_args({"TRADER_MODE": "dry"})


@pytest.mark.parametrize("mode", ["live", "PAPERLIVE", "both", "backtest", "scan", "report"])
def test_other_modes_are_refused(mode):
    with pytest.raises(rt.Refused):
        rt.build_args({"TRADER_MODE": mode})


def test_mode_is_case_and_space_tolerant():
    assert flag(rt.build_args({"TRADER_MODE": "  Paper "}), "--mode") == "paper"


# ------------------------------------------------------------------ ports
@pytest.mark.parametrize("port", ["4001", "4003", "7496", "7498"])
def test_live_ports_are_refused_in_every_mode(port):
    for mode in ("dry", "paper"):
        with pytest.raises(rt.Refused, match="LIVE"):
            rt.build_args({"TRADER_MODE": mode, "TRADER_PORT": port})


@pytest.mark.parametrize("port", ["4004", "5555", "0", "-1", "abc", "4002.5"])
def test_any_port_that_is_not_a_paper_port_is_refused(port):
    with pytest.raises(rt.Refused):
        rt.build_args({"TRADER_PORT": port})


@pytest.mark.parametrize("port", ["4002", "7497"])
def test_paper_ports_pass(port):
    assert flag(rt.build_args({"TRADER_PORT": port}), "--port") == port


# ------------------------------------------------------------------ strategy and the optional settings
def test_strategy_list_is_comma_separated_and_a_space_is_refused():
    assert flag(rt.build_args({"TRADER_STRATEGY": "mcl,mc5"}), "--strategy") == "mcl,mc5"
    for bad in ("mcl mc5", "mcl,", ",mc5", "mcl,,mc5"):
        with pytest.raises(rt.Refused):
            rt.build_args({"TRADER_STRATEGY": bad})


def test_optional_settings_pass_through_and_empty_means_leave_the_trader_default():
    a = rt.build_args({"TRADER_MAX_POSITIONS": "3", "TRADER_CAP_SCOPE": "strategy", "TRADER_TELEGRAM_BATCH_MIN": "5",
                       "TRADER_NO_ARCHIVE": "1", "TRADER_FEED": "off"})
    assert flag(a, "--max-positions") == "3" and flag(a, "--cap-scope") == "strategy"
    assert flag(a, "--telegram-batch-min") == "5" and "--no-archive" in a and "--no-feed" in a
    b = rt.build_args({"TRADER_MAX_POSITIONS": "", "TRADER_CAP_SCOPE": " ", "TRADER_TELEGRAM_BATCH_MIN": "0"})
    for name in ("--max-positions", "--cap-scope", "--telegram-batch-min"):
        assert name not in b


@pytest.mark.parametrize("env", [{"TRADER_MAX_POSITIONS": "0"}, {"TRADER_MAX_POSITIONS": "two"},
                                 {"TRADER_MAX_POSITIONS": "-1"}, {"TRADER_CAP_SCOPE": "all"},
                                 {"TRADER_TELEGRAM_BATCH_MIN": "soon"}, {"TRADER_FEED": "maybe"}])
def test_malformed_settings_are_refused_rather_than_guessed(env):
    with pytest.raises(rt.Refused):
        rt.build_args(env)


def test_the_windows_sleep_flag_can_never_be_produced():
    envs = [{}, {"TRADER_MODE": "paper"}, {"TRADER_MODE": "paper", "TRADER_STRATEGY": "mcl,mc5",
            "TRADER_MAX_POSITIONS": "3", "TRADER_CAP_SCOPE": "strategy", "TRADER_NO_ARCHIVE": "1",
            "TRADER_FEED": "off", "TRADER_TELEGRAM_BATCH_MIN": "2"}]
    for env in envs:
        assert not [a for a in rt.build_args(env) if "sleep" in a]


# ------------------------------------------------------------------ what main.run() hands to the trader
def test_trader_args_consume_the_launchers_own_flags_and_split_the_strategy_list():
    a = rt.build_args({"TRADER_MODE": "paper", "TRADER_STRATEGY": "mcl,mc5", "TRADER_FEED": "off",
                       "TRADER_MAX_POSITIONS": "3"})
    t = rt.trader_args(a)
    assert "--mode" not in t and "--yes" not in t and "--no-feed" not in t
    assert t[t.index("--strategy") + 1:t.index("--strategy") + 3] == ["mcl", "mc5"]
    assert flag(t, "--max-positions") == "3" and flag(t, "--port") == "4002"
    assert "--dry-run" not in t


def test_dry_mode_adds_dry_run_for_the_trader():
    assert "--dry-run" in rt.trader_args(rt.build_args({}))


# ------------------------------------------------------------------ var/ preparation
def test_prepare_var_creates_folders_and_an_empty_watchlist_and_warns_about_it(tmp_path):
    warns = rt.prepare_var(tmp_path)
    for sub in ("state", "fills", "archive"):
        assert (tmp_path / "var" / sub).is_dir()
    assert (tmp_path / "var" / "watchlist.txt").is_file()
    assert any("empty" in w for w in warns)
    assert not (tmp_path / "var" / "state" / ".write_test").exists()


def test_prepare_var_does_not_warn_when_the_watchlist_has_names_and_keeps_them(tmp_path):
    (tmp_path / "var").mkdir()
    wl = tmp_path / "var" / "watchlist.txt"
    wl.write_text("# header\nUPC  # rank 1\n", encoding="utf-8")
    assert rt.prepare_var(tmp_path) == []
    assert wl.read_text(encoding="utf-8") == "# header\nUPC  # rank 1\n"


def test_prepare_var_refuses_with_the_chown_hint_when_var_is_not_writable(tmp_path):
    (tmp_path / "var").write_text("i am a file, not a folder", encoding="utf-8")
    with pytest.raises(rt.Refused, match="chown"):
        rt.prepare_var(tmp_path)


# ------------------------------------------------------------------ main()
def run_main(argv, env, tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = []
    code = rt.main(argv, env=env, run_main=lambda a: calls.append(a) or 0)
    return code, calls


def test_main_runs_the_session_with_the_built_arguments(tmp_path, monkeypatch, capsys):
    code, calls = run_main([], {"TRADER_MODE": "paper"}, tmp_path, monkeypatch)
    out = capsys.readouterr().out
    assert code == 0 and len(calls) == 1 and flag(calls[0], "--mode") == "paper"
    assert "ORDERS WILL BE PLACED" in out and "DRY RUN" not in out


def test_main_dry_banner_says_no_orders(tmp_path, monkeypatch, capsys):
    run_main([], {}, tmp_path, monkeypatch)
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "NO orders" in out and "ORDERS WILL BE PLACED" not in out


def test_main_refuses_a_live_port_without_starting_anything(tmp_path, monkeypatch, capsys):
    code, calls = run_main([], {"TRADER_MODE": "paper", "TRADER_PORT": "4001"}, tmp_path, monkeypatch)
    assert code == 1 and calls == [] and "REFUSED" in capsys.readouterr().err


def test_main_refuses_when_var_cannot_be_written(tmp_path, monkeypatch, capsys):
    (tmp_path / "var").write_text("x", encoding="utf-8")
    code, calls = run_main([], {}, tmp_path, monkeypatch)
    assert code == 1 and calls == [] and "REFUSED" in capsys.readouterr().err


def test_print_command_shows_the_arguments_and_starts_nothing(tmp_path, monkeypatch, capsys):
    code, calls = run_main(["--print-command"], {"TRADER_STRATEGY": "mcl,mc5"}, tmp_path, monkeypatch)
    assert code == 0 and calls == [] and "main.py --mode dry --strategy mcl,mc5" in capsys.readouterr().out


def test_main_rejects_unknown_command_line_arguments(tmp_path, monkeypatch, capsys):
    for argv in (["--sleep-on-exit"], ["--port", "4001"], ["--live"]):
        code, calls = run_main(argv, {}, tmp_path, monkeypatch)
        assert code == 1 and calls == []
    assert "unknown argument" in capsys.readouterr().err


def test_main_passes_the_session_exit_code_through(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    assert rt.main([], env={}, run_main=lambda a: 3) == 3


# ------------------------------------------------------------------ --selfcheck must fail loudly, never crash
def test_selfcheck_reports_a_module_that_calls_sys_exit_on_import_as_a_failure_not_a_crash(tmp_path):
    """trader.py does sys.exit('ib_async not installed...') at import. SystemExit is not an Exception, so a naive
    `except Exception` would kill the selfcheck half way and print no verdict. Run in a subprocess: stub modules."""
    import shutil
    import subprocess
    root = tmp_path / "app"
    for pkg in ("brokers/ibkr", "common", "strategy/mcl", "strategy/mc5"):
        (root / pkg).mkdir(parents=True)
    for d in ("brokers", "brokers/ibkr", "common", "strategy", "strategy/mcl", "strategy/mc5"):
        (root / d / "__init__.py").write_text("", encoding="utf-8")
    for mod in ("main", "brokers/ibkr/scanner", "common/tv_feed", "common/ui_bridge", "common/notify",
                "common/session_lock", "common/provenance", "strategy/mcl/mcl", "strategy/mc5/mc5"):
        (root / f"{mod}.py").write_text("", encoding="utf-8")
    (root / "brokers/ibkr/trader.py").write_text("import sys\nsys.exit('ib_async not installed.')\n", encoding="utf-8")
    shutil.copy(PATH, root / "run_trader.py")
    r = subprocess.run([sys.executable, str(root / "run_trader.py"), "--selfcheck"], cwd=str(tmp_path),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    assert r.returncode == 2, r.stdout
    assert "FAIL  import brokers.ibkr.trader" in r.stdout and "SELFCHECK FAIL" in r.stdout


# ------------------------------------------------------------------ stale locks after an unclean stop
def write_lock(root, rel, **info):
    import json
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(info), encoding="utf-8")
    return p


def test_a_lock_left_by_an_earlier_run_of_this_container_is_removed_so_it_cannot_block_the_next_session(tmp_path):
    """The container's PIDs repeat every run, so session_lock's 'is that PID alive' answers yes for the new process
    itself. Reproduce the premise: the lock records the PID we are running as."""
    import os
    sess = write_lock(tmp_path, "var/state/session.lock", pid=os.getpid(), mode="paper", strategy="mcl",
                      started_at="2026-10-28T08:00:00", tree=str(tmp_path))
    wr = write_lock(tmp_path, "var/state/watchlist_writer.lock", pid=os.getpid(), mode="watchlist-writer",
                    strategy="tv_feed")
    notes = rt.clear_container_locks(tmp_path, {})
    assert not sess.exists() and not wr.exists()
    assert len(notes) == 2 and all("removed" in n for n in notes)


def test_a_lock_written_by_another_tree_is_left_alone(tmp_path):
    p = write_lock(tmp_path, "var/state/session.lock", pid=1234, mode="paper", strategy="mcl",
                   tree="D:\\Trading")
    notes = rt.clear_container_locks(tmp_path, {})
    assert p.exists() and "LEFT ALONE" in notes[0] and "D:\\Trading" in notes[0]


def test_unreadable_lock_is_removed_and_no_lock_is_a_no_op(tmp_path):
    assert rt.clear_container_locks(tmp_path, {}) == []
    p = tmp_path / "var" / "state" / "session.lock"
    p.parent.mkdir(parents=True)
    p.write_text("{broken", encoding="utf-8")
    assert "removed" in rt.clear_container_locks(tmp_path, {})[0] and not p.exists()


def test_clearing_can_be_switched_off(tmp_path):
    p = write_lock(tmp_path, "var/state/session.lock", pid=1, tree=str(tmp_path))
    assert rt.clear_container_locks(tmp_path, {"TRADER_CLEAR_STALE_LOCKS": "0"}) == [] and p.exists()


def test_main_clears_locks_before_the_banner_but_not_for_print_command(tmp_path, monkeypatch, capsys):
    p = write_lock(tmp_path, "var/state/session.lock", pid=7, tree=str(tmp_path), mode="dry", strategy="mcl")
    run_main(["--print-command"], {}, tmp_path, monkeypatch)
    assert p.exists()                                           # --print-command changes nothing
    code, calls = run_main([], {}, tmp_path, monkeypatch)
    assert code == 0 and calls and not p.exists()
    assert "removed var/state/session.lock" in capsys.readouterr().out
