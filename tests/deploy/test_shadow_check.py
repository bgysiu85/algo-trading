import importlib.util
import json
import sys
import time
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader" / "shadow_check.py"
_spec = importlib.util.spec_from_file_location("shadow_check", PATH)
sc = importlib.util.module_from_spec(_spec)
sys.modules["shadow_check"] = sc
_spec.loader.exec_module(sc)

HEADER = "ts_et,strategy,symbol,action,reason,status,reject_reason\n"
OPEN_DRY = "2026-11-02 01:00:10,,,CONFIG,session_open,APPLIED,trail_pct=MCL:5.0 dry_run=True bridge=off\n"
OPEN_LIVE = "2026-11-02 01:00:10,,,CONFIG,session_open,APPLIED,trail_pct=MCL:5.0 dry_run=False bridge=on\n"
BUY = "2026-11-02 04:06:00,MC5,CLRO,BUY,entry_signal,DRY_RUN,\n"
ERR = "2026-11-02 04:07:00,MC5,CLRO,BUY,entry_signal,ERROR,\n"
SKIP = ("2026-11-02 04:11:00,MC5,CLRO,BUY,entry_signal,SKIPPED_BAR_BEFORE_EXIT,"
        "bar 04:05 opened before this strategy's exit at 04:09:17\n")
REJ = "2026-11-02 04:12:00,MC5,CLRO,BUY,entry_signal,REJECTED,price outside the 10% band\n"
REASON_ONLY = "2026-11-02 04:13:00,MC5,CLRO,BUY,entry_signal,SUBMITTED,no buying power\n"


def fills_block(days: dict[str, str]) -> str:
    return "".join(f"##FILE mcl_fills_{d}.csv\n{HEADER}{rows}" for d, rows in days.items())


def lock_json(age_s: float = 5, mode: str = "dry") -> str:
    return json.dumps({"mode": mode, "strategy": "mcl,mc5", "version": "v", "started_at": "t",
                       "heartbeat_epoch": time.time() - age_s})


def remote_output(lock: str, fills: str, watch_lines: int = 0) -> str:
    return (f"@@LOCK\n{lock}\n@@LOAD\n0.10 0.10 0.10 1/100 1\nMemTotal: 3000000 kB\nMemAvailable: 1900000 kB\n"
            f"@@WATCH\n{watch_lines}\nwatchlist_20261102.txt\n@@FILLS\n{fills}")


def run(monkeypatch, tmp_path, capsys, out: str) -> tuple[int, str, list[dict]]:
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(sc, "ssh", lambda: out)
    monkeypatch.setattr(sc, "LOG", log)
    code = sc.main()
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    return code, capsys.readouterr().out, lines


def test_empty_lock_means_no_session_running():
    assert sc.parse_lock("") == (None, None)
    assert sc.parse_lock("\n  \n") == (None, None)


def test_a_valid_lock_is_returned():
    lock, problem = sc.parse_lock(lock_json())
    assert problem is None and lock["mode"] == "dry"


def test_an_unreadable_lock_is_a_problem_not_a_crash():
    for text in ("not json", "[]", '{"mode": "dry"}'):
        lock, problem = sc.parse_lock(text)
        assert lock is None and "not readable" in problem


def test_after_the_session_no_lock_still_counts_the_session(monkeypatch, tmp_path, capsys):
    # The 02:00 run: trader stopped, lock removed, watchlist archived and cleared.
    out = remote_output("", fills_block({"20261102": OPEN_DRY + BUY}))
    code, text, lines = run(monkeypatch, tmp_path, capsys, out)
    assert code == 0
    assert "lock: none" in text
    assert "1 of 3" in text and "VERDICT: NOT YET" in text
    assert "PROBLEM" not in text
    assert lines[0]["mode"] is None and lines[0]["heartbeat_age_s"] is None
    assert lines[0]["fills"]["20261102"]["session_open"] == 1


def test_three_weekday_sessions_without_a_lock_pass(monkeypatch, tmp_path, capsys):
    days = {d: OPEN_DRY + BUY for d in ("20261102", "20261103", "20261104")}
    _, text, _ = run(monkeypatch, tmp_path, capsys, remote_output("", fills_block(days)))
    assert "3 of 3" in text and "VERDICT: PASS" in text


def test_weekend_and_pre_release_days_do_not_count(monkeypatch, tmp_path, capsys):
    days = {"20261031": OPEN_DRY, "20261101": OPEN_DRY, "20261102": OPEN_DRY}  # Sat, Sun, Mon
    _, text, _ = run(monkeypatch, tmp_path, capsys, remote_output("", fills_block(days)))
    assert "1 of 3" in text


def test_a_session_that_was_not_dry_is_a_problem_even_without_a_lock(monkeypatch, tmp_path, capsys):
    out = remote_output("", fills_block({"20261102": OPEN_LIVE}))
    _, text, _ = run(monkeypatch, tmp_path, capsys, out)
    assert "without dry_run=True" in text and "VERDICT: PROBLEMS" in text


def test_a_by_design_skip_is_not_a_reject(monkeypatch, tmp_path, capsys):
    # 2 Nov 2026 session: four SKIPPED_BAR_BEFORE_EXIT rows made the first version report PROBLEMS.
    out = remote_output("", fills_block({"20261102": OPEN_DRY + BUY + SKIP}))
    _, text, lines = run(monkeypatch, tmp_path, capsys, out)
    assert "PROBLEM" not in text and "VERDICT: NOT YET" in text
    assert lines[0]["fills"]["20261102"]["skipped"] == 1 and lines[0]["fills"]["20261102"]["rejects"] == 0


def test_real_rejects_are_still_problems(monkeypatch, tmp_path, capsys):
    for bad in (REJ, REASON_ONLY):
        out = remote_output("", fills_block({"20261102": OPEN_DRY + bad}))
        _, text, _ = run(monkeypatch, tmp_path, capsys, out)
        assert "1 reject" in text and "VERDICT: PROBLEMS" in text


def test_error_rows_are_a_problem(monkeypatch, tmp_path, capsys):
    out = remote_output("", fills_block({"20261102": OPEN_DRY + ERR}))
    _, text, _ = run(monkeypatch, tmp_path, capsys, out)
    assert "1 error" in text and "VERDICT: PROBLEMS" in text


def test_in_session_checks_still_apply_when_a_lock_exists(monkeypatch, tmp_path, capsys):
    fills = fills_block({"20261102": OPEN_DRY})
    _, text, _ = run(monkeypatch, tmp_path, capsys, remote_output(lock_json(age_s=500), fills))
    assert "heartbeat" in text and "VERDICT: PROBLEMS" in text
    _, text, _ = run(monkeypatch, tmp_path, capsys, remote_output(lock_json(), fills, watch_lines=0))
    assert "empty watchlist" in text
    _, text, _ = run(monkeypatch, tmp_path, capsys, remote_output(lock_json(mode="paper"), fills, watch_lines=2))
    assert "not dry" in text
    _, text, _ = run(monkeypatch, tmp_path, capsys, remote_output(lock_json(), fills, watch_lines=2))
    assert "PROBLEM" not in text and "lock: dry" in text


def test_the_script_only_reads_on_the_nas():
    src = PATH.read_text(encoding="utf-8")
    for bad in ("sudo", "docker ", "sed -i", "tee ", " rm ", "chmod ", " >> ", "mv "):
        assert bad not in src.split('"""', 2)[2].split("REMOTE", 1)[1].split("def ssh", 1)[0], bad
