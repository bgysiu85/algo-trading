#!/usr/bin/env python3
"""
Show every op:// reference the current 1Password credentials can actually read.

    python op_list.py                 # all vaults it can see
    python op_list.py --vault Trading # just one

Run this instead of guessing item and field names. It prints ready-to-paste
references, so the setx line below is a copy rather than a spelling exercise --
a wrong field name is the single most common way to end up authenticating with
the wrong key pair, and with TradeZero that is the difference between paper and
live.

Values are NEVER read or printed. This lists names only.

If a service account token is set, this shows what that token can reach, which
is deliberately narrower than what you see in the 1Password app: service
accounts cannot read Private, Personal, Employee or default Shared vaults at
all. A vault missing from this list is the answer to "why does op read fail
when it works interactively".
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

TIMEOUT_S = 30
BLIND = {"private", "personal", "employee", "shared"}


def op(args: list[str]) -> object:
    try:
        out = subprocess.run(["op", *args, "--format=json"],
                             capture_output=True, text=True, timeout=TIMEOUT_S)
    except FileNotFoundError:
        sys.exit("1Password CLI ('op') not found on PATH.")
    except subprocess.TimeoutExpired:
        sys.exit("`op` timed out. If interactive, 1Password is waiting for an "
                 "unlock. If using a service account, the token may be invalid.")
    if out.returncode != 0:
        sys.exit(f"`op {' '.join(args)}` failed:\n  {out.stderr.strip()}")
    return json.loads(out.stdout or "[]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault")
    a = ap.parse_args()

    sa = bool(os.environ.get("OP_SERVICE_ACCOUNT_TOKEN", "").strip())
    print(f"mode: {'service account' if sa else 'interactive'}\n")

    vaults = op(["vault", "list"])
    names = [v["name"] for v in vaults]
    print(f"vaults visible ({len(names)}): {', '.join(names) or '(none)'}")
    if sa:
        hidden = [n for n in ("Private", "Personal", "Employee", "Shared")
                  if n not in names]
        if hidden:
            print(f"  not readable by a service account: {', '.join(hidden)}")
    print()

    targets = [a.vault] if a.vault else names
    for vault in targets:
        if a.vault and vault.lower() in BLIND and sa:
            print(f"'{vault}' cannot be read by a service account at all.")
            continue
        try:
            items = op(["item", "list", "--vault", vault])
        except SystemExit:
            print(f"--- {vault} --- unreadable\n")
            continue
        print(f"--- {vault} ({len(items)} items) ---")
        for it in items:
            title = it.get("title", "?")
            try:
                full = op(["item", "get", it["id"], "--vault", vault])
            except SystemExit:
                print(f"  {title}   (fields unreadable)")
                continue
            fields = [f for f in full.get("fields", [])
                      if f.get("label") and f.get("type") not in ("OTP",)]
            print(f"  {title}")
            for f in fields:
                label = f["label"]
                has = "set" if ("value" in f or f.get("type") == "CONCEALED") else "empty"
                print(f'      op://{vault}/{title}/{label}          [{has}]')
        print()

    print("Paste the two you need, then open a NEW terminal:")
    print('  setx DATABENTO_API_KEY  "op://Trading/<item>/<field>"')
    print('  setx TZ_API_KEY_ID      "op://Trading/<item>/<field>"')
    print('  setx TZ_API_SECRET_KEY  "op://Trading/<item>/<field>"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
