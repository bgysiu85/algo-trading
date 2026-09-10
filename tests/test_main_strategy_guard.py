import sys

import pytest

import main as M


def _paper(monkeypatch, argv, answer=None, tty=True):
    import contextlib, io
    seen = {}
    monkeypatch.setattr(M.session_lock, "active", lambda: None)
    monkeypatch.setattr(M.session_lock, "held",
                        lambda *a: contextlib.nullcontext())
    import brokers.ibkr.trader as T
    monkeypatch.setattr(T, "main", lambda a: seen.update(argv=a) or 0)
    if answer is not None:
        monkeypatch.setattr("builtins.input", lambda _p="": answer)

    class _Stdin(io.StringIO):
        def isatty(self): return tty
    monkeypatch.setattr(sys, "stdin", _Stdin())
    return M.run(argv), seen


def test_space_separated_strategies_are_refused(capsys):
    """The shape everyone types. It failed loudly tonight only because the
    trader's parser happened to have no positional to absorb the stray name."""
    rc = M.run(["--mode", "paper", "--strategy", "mcl", "mc5",
                "--max-positions", "3"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--strategy mcl,mc5" in err
    assert "Refusing rather than running only mcl" in err


def test_the_comma_form_reaches_the_trader_with_both_names(monkeypatch):
    """The guard must not block the correct spelling -- and the correct
    spelling must actually deliver BOTH names. Asserting only 'not refused'
    would pass on a build that silently dropped mc5, which is the failure the
    guard exists to prevent."""
    rc, seen = _paper(monkeypatch, ["--mode", "paper", "--strategy", "mcl,mc5",
                                    "--max-positions", "3"], answer="PAPER")
    assert rc == 0
    assert seen["argv"] == ["--max-positions", "3", "--strategy", "mcl", "mc5"]


def test_a_backtest_only_name_passed_bare_is_also_caught():
    rc = M.run(["--mode", "backtest", "--strategy", "mcl", "vw9_5m"])
    assert rc == 2


def test_an_ordinary_passthrough_flag_is_untouched(monkeypatch):
    """--port 4002 and its value must not look like a stray strategy."""
    rc, seen = _paper(monkeypatch, ["--mode", "paper", "--strategy", "mcl",
                                    "--port", "4002", "--no-archive"],
                      answer="PAPER")
    assert rc == 0
    assert seen["argv"] == ["--port", "4002", "--no-archive",
                            "--strategy", "mcl"]


def test_a_non_strategy_positional_still_passes_through(monkeypatch):
    """The guard names STRATEGIES only. A mode with real positionals must keep
    working, or the guard has broken something to fix something."""
    rc, seen = _paper(monkeypatch,
                      ["--mode", "paper", "--strategy", "mcl", "somefile.txt"],
                      answer="PAPER")
    assert rc == 0
    assert "somefile.txt" in seen["argv"]


# --- the confirmation, moved out of run_paper.ps1 on 2026-09-10 -------------
#
# It lived only in the PowerShell wrapper. Ben ran `python main.py` for the
# first time and found it gone -- nothing had removed it, the wrapper was
# simply no longer in the path. A safety prompt present in one of four entry
# points fails by being absent exactly when someone takes a new route.

def test_paper_requires_the_word(monkeypatch):
    rc, seen = _paper(monkeypatch, ["--mode", "paper", "--strategy", "mcl"],
                      answer="PAPER")
    assert rc == 0 and "argv" in seen


@pytest.mark.parametrize("answer", ["", "paper", "yes", "y", "PAPERS", "no"])
def test_anything_else_cancels(monkeypatch, answer):
    """Case-sensitive and exact. 'paper' lower-case must NOT pass -- the point
    of a typed word is that it cannot be produced by a reflex."""
    rc, seen = _paper(monkeypatch, ["--mode", "paper", "--strategy", "mcl"],
                      answer=answer)
    assert rc == 2 and "argv" not in seen


def test_dry_mode_is_not_prompted(monkeypatch):
    """--mode dry places no orders. Prompting there trains the reflex this
    guard depends on not existing."""
    rc, seen = _paper(monkeypatch, ["--mode", "dry", "--strategy", "mcl"])
    assert rc == 0 and "--dry-run" in seen["argv"]


def test_no_tty_without_yes_is_refused_not_assumed(monkeypatch):
    """A scheduled run has no stdin. Reading EOF as consent is how an
    unattended process starts placing orders nobody asked for; reading it as
    refusal at least fails safe and says why."""
    rc, seen = _paper(monkeypatch, ["--mode", "paper", "--strategy", "mcl"],
                      tty=False)
    assert rc == 2 and "argv" not in seen


def test_yes_runs_non_interactively_and_is_not_forwarded(monkeypatch):
    """--yes is main.py's flag. Forwarding it would reach the trader's parser,
    which does not define it, and the session would die on an unrecognized
    argument AFTER the confirmation was skipped."""
    rc, seen = _paper(monkeypatch,
                      ["--mode", "paper", "--strategy", "mcl", "--yes"],
                      tty=False)
    assert rc == 0
    assert "--yes" not in seen["argv"]


def test_the_banner_reports_the_real_cap_and_strategies(monkeypatch, capsys):
    _paper(monkeypatch, ["--mode", "paper", "--strategy", "mcl,mc5",
                         "--max-positions", "3", "--port", "7497"],
           answer="PAPER")
    out = capsys.readouterr().out
    assert "mcl, mc5" in out
    assert "3 across ALL strategies" in out
    assert "7497" in out


def test_an_absent_flag_says_so_rather_than_guessing(monkeypatch, capsys):
    """A banner that invents 'cap 2' when no cap was passed asserts a number
    nobody chose -- and the trader's default is the thing that would move."""
    _paper(monkeypatch, ["--mode", "paper", "--strategy", "mcl"],
           answer="PAPER")
    out = capsys.readouterr().out
    assert "trader default" in out
    assert "4002 (default)" in out
