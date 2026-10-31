"""deploy/nas_trader/make_relay_env.py: right names, LF line ends, no secret on screen, refuses values compose would mangle."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "make_relay_env", Path(__file__).resolve().parents[2] / "deploy" / "nas_trader" / "make_relay_env.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def ui_repo(tmp_path: Path, **over) -> Path:
    var = tmp_path / "var"
    var.mkdir()
    auth = {"OIDC_ISSUER": "https://id.thesiuz.com", "OIDC_CLIENT_ID": "cid", "OIDC_CLIENT_SECRET": "csecret",
            "SESSION_SECRET": "sess", "ALLOWED_SUBJECTS": "sub1", **over}
    (var / "auth.env").write_text("# c\n" + "\n".join(f"{k}={v}" for k, v in auth.items()) + "\n", encoding="utf-8")
    (var / "neon.env").write_text("DATABASE_URL=postgresql://u:p@h/db\n", encoding="utf-8")
    (var / "agent_token.txt").write_text("tok123\n", encoding="utf-8")
    return tmp_path


def test_writes_relay_names_with_lf_endings(tmp_path):
    buf = io.BytesIO()
    assert M.main(["--root", str(ui_repo(tmp_path))], stdout=buf) == 0
    text = buf.getvalue().decode()
    assert b"\r" not in buf.getvalue()
    lines = dict(l.split("=", 1) for l in text.splitlines())
    assert lines["RELAY_OIDC_CLIENT_SECRET"] == "csecret" and lines["UI_AGENT_TOKEN"] == "tok123"
    assert lines["RELAY_DATABASE_URL"] == "postgresql://u:p@h/db" and lines["RELAY_SESSION_SECRET"] == "sess"


def test_check_mode_shows_no_secret(tmp_path, capsys):
    assert M.main(["--root", str(ui_repo(tmp_path)), "--check"]) == 0
    out = capsys.readouterr().out
    assert "RELAY_OIDC_CLIENT_SECRET" in out and "sha256:" in out
    for secret in ("csecret", "tok123", "sess", "postgresql://"):
        assert secret not in out


def test_missing_required_value_and_unsafe_value_are_refused(tmp_path, capsys):
    assert M.main(["--root", str(ui_repo(tmp_path, OIDC_CLIENT_SECRET=""))], stdout=io.BytesIO()) == 1
    other = tmp_path / "x"
    other.mkdir()
    assert M.main(["--root", str(ui_repo(other, SESSION_SECRET="a$b"))], stdout=io.BytesIO()) == 1
    assert "PROBLEM" in capsys.readouterr().err
