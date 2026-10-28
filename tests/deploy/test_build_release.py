"""Tests for deploy/nas_trader/build_release.py (W10-0013 sub 5): the tar of the trader's live path for the NAS.

The risk is a module missing from the tar - the trader would fail at import on the NAS, at the worst moment. So the
headline test unpacks the real tar into an empty folder and imports the trader there, with the repo off the path.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PATH = REPO / "deploy" / "nas_trader" / "build_release.py"
_spec = importlib.util.spec_from_file_location("build_release", PATH)
br = importlib.util.module_from_spec(_spec)
sys.modules["build_release"] = br
_spec.loader.exec_module(br)


# ------------------------------------------------------------------ the import finder, on a made-up repo
def make_repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "pkg" / "sub").mkdir(parents=True)
    (r / "other").mkdir()
    (r / "tests").mkdir()
    (r / "main.py").write_text("import os\nfrom pkg import a\n\ndef f():\n    from other import lazy\n", encoding="utf-8")
    (r / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (r / "pkg" / "a.py").write_text("from . import b\nfrom .sub import c\nimport pandas\n", encoding="utf-8")
    (r / "pkg" / "b.py").write_text("import importlib\nm = importlib.import_module('pkg.dyn')\n", encoding="utf-8")
    (r / "pkg" / "dyn.py").write_text("X = 1\n", encoding="utf-8")
    (r / "pkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (r / "pkg" / "sub" / "c.py").write_text("", encoding="utf-8")
    (r / "other" / "__init__.py").write_text("", encoding="utf-8")
    (r / "other" / "lazy.py").write_text("", encoding="utf-8")
    (r / "other" / "unused.py").write_text("", encoding="utf-8")
    (r / "tests" / "test_x.py").write_text("import main\n", encoding="utf-8")
    return r


def test_closure_follows_plain_relative_lazy_and_string_imports_and_nothing_else(tmp_path):
    r = make_repo(tmp_path)
    got = {k: v.relative_to(r).as_posix() for k, v in br.closure(r).items()}
    assert set(got.values()) == {"main.py", "pkg/__init__.py", "pkg/a.py", "pkg/b.py", "pkg/dyn.py",
                                 "pkg/sub/__init__.py", "pkg/sub/c.py", "other/__init__.py", "other/lazy.py"}


def test_stdlib_and_third_party_names_are_not_treated_as_ours(tmp_path):
    r = make_repo(tmp_path)
    assert br.module_file("os", r) is None and br.module_file("pandas", r) is None


# ------------------------------------------------------------------ the real repo
def test_the_real_plan_has_the_trader_and_leaves_out_tests_secrets_and_studies():
    files = set(br.plan())
    assert {"main.py", "run_trader.py", "requirements.txt", "brokers/ibkr/trader.py", "strategy/mcl/mcl.py",
            "strategy/mc5/mc5.py", "common/session_lock.py", "common/provenance.py", "common/ui_bridge.py",
            "common/tv_feed.py", "common/notify.py"} <= files
    for f in files:
        assert not f.startswith(("tests/", "desk/", "docs/", "var/", "deploy/", "tools/", "Claude outputs/")), f
        assert "credentials" not in f and not f.endswith((".json", ".env")) or f == "requirements.txt", f


def test_the_audit_found_29_modules_and_this_finds_at_least_those():
    """W10-0013 sub 2 counted 29 local modules reachable from main.py (strategy/*/__init__ are the extra ones here)."""
    assert len([f for f in br.plan() if f.endswith(".py")]) >= 30


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("rel")
    out = d / "app.tar"
    meta = br.build(out)
    dest = d / "x"
    dest.mkdir()
    with tarfile.open(out) as t:
        t.extractall(dest)
    return out, dest / "trader" / "app", meta


def test_tar_layout_modes_and_manifest(built):
    out, app, meta = built
    with tarfile.open(out) as t:
        names = t.getnames()
        assert all(n == "trader" or n.startswith("trader/") for n in names)
        for extra in br.PROJECT_FILES:
            assert f"trader/{extra}" in names, extra          # compose.yaml etc. travel in the same tar
        assert "trader/.env" not in names                      # the secrets file is never packed
        assert not [n for n in names if n.startswith("/") or ".." in n.split("/")]
        for m in t.getmembers():
            want = 0o755 if (m.isdir() or m.name.endswith(("/run_trader.py", ".sh"))) else 0o644
            assert m.mode == want, (m.name, oct(m.mode))     # the container user (1000) must be able to read it all
    assert (app / "var").is_dir() and list((app / "var").iterdir()) == []
    rel = json.loads((app / "RELEASE.json").read_text(encoding="utf-8"))
    assert {"commit", "described", "branch", "dirty", "built_at", "file_count"} <= set(rel)
    assert rel["file_count"] == len(br.plan()) == meta["file_count"]


def test_every_import_in_the_shipped_tree_resolves_inside_the_shipped_tree(built):
    _, app, _ = built
    shipped = {k: v.relative_to(app).as_posix() for k, v in br.closure(app).items()}
    assert set(shipped.values()) == {f for f in br.plan() if f.endswith(".py") and f != "run_trader.py"}


def test_the_unpacked_tree_imports_and_selfchecks_with_the_repo_off_the_path(built):
    pytest.importorskip("pandas")
    pytest.importorskip("ib_async")
    _, app, _ = built
    import os
    env = dict(os.environ)          # NOT a stripped-down environment: on Windows, dropping SYSTEMROOT breaks sockets
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p and str(REPO) not in p)     # repo off the path
    r = subprocess.run([sys.executable, str(app / "run_trader.py"), "--selfcheck"], cwd=str(app.parent), env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    assert r.returncode == 0, r.stdout
    assert "SELFCHECK PASS" in r.stdout and "release identity" in r.stdout
    assert str(REPO) not in r.stdout.replace(str(app), "")      # it ran the unpacked copy, not the repo


# ------------------------------------------------------------------ RELEASE.json says which code, and whether it was clean
def _git(repo, *a):
    subprocess.run(["git", *a], cwd=str(repo), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_manifest_names_the_exact_shipped_files_that_differ_from_head(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    (r / "a.py").write_text("x = 1\n", encoding="utf-8")
    (r / "b.py").write_text("y = 1\n", encoding="utf-8")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "one")
    clean = br.manifest(["a.py", "b.py"], r)
    assert clean["dirty"] is False and clean["dirty_files"] == [] and clean["commit"]
    (r / "a.py").write_text("x = 2\n", encoding="utf-8")
    (r / "new.py").write_text("", encoding="utf-8")                     # untracked, and shipped
    (r / "elsewhere.py").write_text("", encoding="utf-8")               # untracked, NOT shipped: must not count
    dirty = br.manifest(["a.py", "b.py", "new.py"], r)
    assert dirty["dirty"] is True and sorted(dirty["dirty_files"]) == ["a.py", "new.py"]


def test_manifest_without_git_is_reportable_not_an_error(tmp_path):
    m = br.manifest(["a.py"], tmp_path)
    assert m["commit"] == "" and m["dirty"] is False and m["file_count"] == 1
