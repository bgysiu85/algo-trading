#!/usr/bin/env python3
"""Pack the trader's live path into one tar for the NAS (W10-0013 sub 5).

    python deploy/nas_trader/build_release.py                 -> Claude outputs/w10_0013_sub5_nas.tar
    python deploy/nas_trader/build_release.py --out X.tar
    python deploy/nas_trader/build_release.py --list          print the files and stop

The tar unpacks (in /volume1/docker) to trader/app/ (the code) and, beside it, the project files: compose.yaml,
.env.example, NAS-TRADER-SETUP.md, probe_gateway.py, make_trader_env.sh. It never contains .env.

What goes in app/: main.py and every repo module it can reach by import (found with `ast`, lazy imports inside functions
included - the same method as the W10-0013 sub 2 audit), the __init__.py of each package on the way, run_trader.py, an
empty var/ (the mount point for the NAS folder), requirements.txt (the pinned packages) and RELEASE.json.

What stays out: tests, backtests, studies, caches, secrets (credentials.json), anything not reachable from main.py.

RELEASE.json is how the NAS copy says WHICH code it is, since there is no .git in the container: commit, `git describe`,
and `dirty` = a shipped file differs from HEAD (or is untracked). common/provenance.py reads it and writes it into the
session lock and the log, so a fill log can still be traced to a commit.

Files are written 0644 / folders 0755 on purpose: the container runs as user 1000, and a tar with owner-only modes once
left an app unable to read its own code (W17-0030).
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENTRY = "main"
LAUNCHER = REPO / "deploy" / "nas_trader" / "run_trader.py"
REQUIREMENTS = REPO / "deploy" / "nas_trader" / "requirements.nas.txt"
TOP = "trader"                                # the folder inside the tar; unpacked in /volume1/docker it becomes
APP = f"{TOP}/app"                            # /volume1/docker/trader/app (the code) beside compose.yaml and .env
# Files for the project folder itself (everything the project needs except the secrets in .env):
PROJECT_FILES = ("compose.yaml", ".env.example", "NAS-TRADER-SETUP.md", "probe_gateway.py", "make_trader_env.sh")
DEFAULT_OUT = REPO / "Claude outputs" / "w10_0013_sub5_nas.tar"


def module_file(name: str, repo: Path = REPO) -> Path | None:
    """The repo file for a dotted module name, or None when it is not ours (stdlib / third party)."""
    parts = name.split(".")
    p = repo.joinpath(*parts)
    if (p / "__init__.py").is_file():
        return p / "__init__.py"
    if p.with_suffix(".py").is_file():
        return p.with_suffix(".py")
    return None


def _imports(path: Path, modname: str, is_pkg: bool) -> set[str]:
    """Dotted names imported anywhere in the file, at any depth. Relative imports are made absolute."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    pkg = modname if is_pkg else modname.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg.split(".") if pkg else []
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            if mod:
                found.add(mod)
                found.update(f"{mod}.{a.name}" for a in node.names)     # `from pkg import submodule`
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in {"import_module", "__import__"} and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                found.add(node.args[0].value)
    return found


def closure(repo: Path = REPO, entry: str = ENTRY) -> dict[str, Path]:
    """{dotted module name: file} for the entry module and everything local it imports, plus parent packages."""
    seen: dict[str, Path] = {}
    todo = [entry]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        f = module_file(name, repo)
        if f is None:
            continue
        seen[name] = f
        parts = name.split(".")
        for i in range(1, len(parts)):                 # parent packages (their __init__ runs on import)
            todo.append(".".join(parts[:i]))
        todo.extend(_imports(f, name, f.name == "__init__.py"))
    return seen


def _git(*args: str, repo: Path = REPO, strip: bool = True) -> str:
    try:
        r = subprocess.run(("git", *args), cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=30, check=False)
        if r.returncode != 0:
            return ""
        return r.stdout.strip() if strip else r.stdout.rstrip("\n")   # porcelain lines start with a meaningful space
    except Exception:                                  # noqa: BLE001 - no git is a reportable state, not an error
        return ""


def manifest(files: list[str], repo: Path = REPO) -> dict:
    status = _git("status", "--porcelain", "--", *files, repo=repo, strip=False)
    return {
        "commit": _git("rev-parse", "--short", "HEAD", repo=repo),
        "described": _git("describe", "--tags", "--always", "--dirty", repo=repo),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD", repo=repo),
        "dirty": bool(status),
        "dirty_files": [ln[3:] for ln in status.splitlines()][:20],
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_count": len(files),
    }


def plan(repo: Path = REPO) -> dict[str, Path]:
    """{path inside app/: source file}, without RELEASE.json (generated) and the empty var/ (a folder)."""
    out = {f.relative_to(repo).as_posix(): f for f in closure(repo).values()}
    out["run_trader.py"] = repo / "deploy" / "nas_trader" / "run_trader.py"
    out["requirements.txt"] = repo / "deploy" / "nas_trader" / "requirements.nas.txt"
    return dict(sorted(out.items()))


def _entry(tar: tarfile.TarFile, name: str, data: bytes | None, mode: int, is_dir: bool = False) -> None:
    ti = tarfile.TarInfo(name.rstrip("/"))
    ti.mtime = int(datetime.now(timezone.utc).timestamp())
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = "root"
    ti.mode = mode
    if is_dir:
        ti.type = tarfile.DIRTYPE
        tar.addfile(ti)
    else:
        ti.size = len(data or b"")
        tar.addfile(ti, io.BytesIO(data or b""))


def build(out: Path, repo: Path = REPO) -> dict:
    files = plan(repo)
    sources = [src.relative_to(repo).as_posix() for src in files.values()]       # repo paths, not tar paths
    extras = {n: repo / "deploy" / "nas_trader" / n for n in PROJECT_FILES}
    meta = manifest(sources + [e.relative_to(repo).as_posix() for e in extras.values()], repo)
    meta["file_count"] = len(files)
    with tarfile.open(out, "w") as tar:
        dirs: set[str] = set()
        for rel in files:
            for i in range(1, len(rel.split("/"))):
                dirs.add("/".join(rel.split("/")[:i]))
        dirs.add("var")
        _entry(tar, TOP, None, 0o755, is_dir=True)
        _entry(tar, APP, None, 0o755, is_dir=True)
        for d in sorted(dirs):
            _entry(tar, f"{APP}/{d}", None, 0o755, is_dir=True)
        for rel, src in files.items():
            _entry(tar, f"{APP}/{rel}", src.read_bytes(), 0o755 if rel == "run_trader.py" else 0o644)
        _entry(tar, f"{APP}/RELEASE.json", (json.dumps(meta, indent=2) + "\n").encode("utf-8"), 0o644)
        for name, src in extras.items():
            _entry(tar, f"{TOP}/{name}", src.read_bytes(), 0o755 if name.endswith(".sh") else 0o644)
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--list", action="store_true", help="print the files that would be packed and stop")
    a = ap.parse_args(argv)
    files = plan()
    if a.list:
        print("\n".join(files))
        print(f"\n{len(files)} files")
        return 0
    meta = build(a.out)
    print(f"wrote {a.out}  ({meta['file_count']} app files + {len(PROJECT_FILES)} project files)")
    print(f"  commit {meta['commit'] or '(none)'}  described {meta['described'] or '-'}  "
          f"dirty={meta['dirty']} {meta['dirty_files'] if meta['dirty'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
