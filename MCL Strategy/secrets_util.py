#!/usr/bin/env python3
"""
One credential resolver for every broker and data vendor in this project.

WHY THIS EXISTS
---------------
tz_check.py resolved its own credentials inline, which was fine for a probe you
run by hand. It is not fine for a long-running trader, for one reason:

    a lazy re-resolve blocks the process on a GUI unlock prompt.

If credentials are fetched on demand -- on reconnect, on a 401 retry, per
request -- then at 05:30 ET, with a position open and the trailing stop living
only inside the running script, the process can stop dead waiting for a
fingerprint that nobody is at the desk to provide.

So: everything resolves ONCE, at startup, through preload(). After that the
values sit in memory and 1Password is never touched again. get() on an
unpreloaded name is a programming error and says so.

SOURCES, in order of precedence
-------------------------------
  1. environment variable holding the literal secret
  2. environment variable holding an `op://vault/item/field` reference
  3. credentials.json beside this file, same two forms

SERVICE ACCOUNTS
----------------
With OP_SERVICE_ACCOUNT_TOKEN set, `op read` is non-interactive -- no unlock
prompt, which is what makes an unattended launch possible.

The trap: a service account CANNOT read the Private, Personal, Employee or
default Shared vaults. An `op://Private/...` reference fails under a service
account no matter how the token is scoped. check() detects that specific
combination and says so, because the raw CLI error is not obvious.

NEVER log a resolved value. mask() exists for when you want to prove in a log
that the right secret was loaded without putting it in the log.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

OP_TIMEOUT_S = 25          # generous: a biometric prompt needs human reaction time
CRED_FILE = Path(__file__).with_name("credentials.json")

# Vaults a 1Password service account is structurally unable to read.
SERVICE_ACCOUNT_BLIND_VAULTS = {"private", "personal", "employee", "shared"}

_cache: dict[str, str] = {}
_sources: dict[str, str] = {}


def using_service_account() -> bool:
    return bool(os.environ.get("OP_SERVICE_ACCOUNT_TOKEN", "").strip())


def mask(value: str) -> str:
    """Safe to log. Enough to tell two keys apart, not enough to use one."""
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]} ({len(value)} chars)"


def _read_file() -> dict:
    if not CRED_FILE.exists():
        return {}
    try:
        return json.loads(CRED_FILE.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"{CRED_FILE.name} is not valid JSON: {e}")


def _op_read(ref: str, label: str) -> str:
    """Resolve one op:// reference through the 1Password CLI."""
    vault = ref.split("/")[2].lower() if ref.count("/") >= 3 else ""
    if using_service_account() and vault in SERVICE_ACCOUNT_BLIND_VAULTS:
        sys.exit(
            f"{label}: reference points at the '{vault}' vault, which a 1Password\n"
            f"  service account cannot read -- this is a hard limit, not a\n"
            f"  permissions setting you can grant.\n"
            f"  Move the item into a purpose-made vault (e.g. 'Trading') and\n"
            f"  update the reference to op://Trading/<item>/<field>."
        )
    try:
        out = subprocess.run(["op", "read", ref], capture_output=True,
                             text=True, timeout=OP_TIMEOUT_S)
    except FileNotFoundError:
        sys.exit("1Password CLI ('op') not found on PATH. "
                 "Install it, or set the literal value instead of an op:// reference.")
    except subprocess.TimeoutExpired:
        hint = ("the service account token may be invalid"
                if using_service_account()
                else "1Password is probably locked and waiting for you")
        sys.exit(f"`op read` timed out resolving {label} -- {hint}.")
    if out.returncode != 0:
        sys.exit(f"`op read` failed for {label}:\n  {out.stderr.strip()}")
    return out.stdout.strip()


def _resolve_one(env_var: str, label: str) -> tuple[str, str]:
    raw = os.environ.get(env_var, "").strip()
    source = "environment"
    if not raw:
        raw = str(_read_file().get(env_var, "")).strip()
        source = CRED_FILE.name
    if not raw:
        return "", "missing"
    if raw.startswith("op://"):
        return _op_read(raw, label), f"{source} -> 1Password"
    return raw, source


def preload(names: dict[str, str]) -> None:
    """Resolve every credential now, at startup, before any event loop starts.

    names maps ENV_VAR_NAME -> human label used in errors.
    Call this once. Anything unresolvable exits here, loudly, while you are
    still watching the terminal -- which is the entire point.
    """
    missing = []
    for env_var, label in names.items():
        value, source = _resolve_one(env_var, label)
        if not value:
            missing.append((env_var, label))
            continue
        _cache[env_var] = value
        _sources[env_var] = source
    if missing:
        lines = "\n".join(f"    {v}   ({l})" for v, l in missing)
        sys.exit(
            "missing credentials:\n" + lines + "\n\n"
            "  Set each as an environment variable, either as the literal secret\n"
            "  or as an op:// reference, for example:\n\n"
            f'     setx {missing[0][0]} "op://Trading/<item>/<field>"\n\n'
            f"  or put the same keys in {CRED_FILE.name} beside this script.\n"
            "  Open a NEW terminal after setx -- it does not affect the current one."
        )


def get(env_var: str) -> str:
    if env_var not in _cache:
        raise RuntimeError(
            f"{env_var} was never preloaded. Add it to the preload() call at "
            f"startup. Resolving credentials lazily can block a live session "
            f"on an unlock prompt."
        )
    return _cache[env_var]


def report() -> str:
    """A line per credential, safe to print or log."""
    mode = ("service account (non-interactive)" if using_service_account()
            else "interactive 1Password / literal values")
    out = [f"credential mode: {mode}"]
    for k in sorted(_cache):
        out.append(f"  {k:24} {_sources[k]:28} {mask(_cache[k])}")
    return "\n".join(out)
