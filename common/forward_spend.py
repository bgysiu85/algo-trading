#!/usr/bin/env python3
"""One shared monthly Databento spend cap for the two forward tests (W16-0014 DVP-F1 and W15-0037 CHARTMARK-v2).

WHY THIS EXISTS (W15-0069 sub 2, Ben's decision on W15-0070, 2026-11-03)
-----------------------------------------------------------------------
The Databento subscription has ended, so the weekly forward-test pulls are pay-as-you-go. Ben's rule: US$5 per calendar
month for BOTH tests combined; if a pull is refused or would take the month past the cap, STOP AND ASK BEN -- never
quietly buy it and never quietly skip it.

WHAT IT DOES
------------
* `check(test, usd)`   refuses (raises SpendRefused) when this month's recorded spend + `usd` would pass the cap, and logs the refusal.
* `record(test, usd)`  adds a pull to this month's total (call it after a download, with what was actually bought).
* `raise_if_access(e)` turns a Databento access refusal (401/403/licence/subscription/payment text) into a SpendRefused
                       instead of an ordinary abort, so it also stops-and-asks. Anything else is left for the caller.
* The scorers' main() turns SpendRefused into exit code 4; the Task Scheduler wrappers write "STOP AND ASK BEN" plus the
  refusal text into the weekly log.

The ledger is a plain JSON file, `Claude outputs/forward_spend.json` (git-ignored, one file for both tests; override with the
FORWARD_SPEND_PATH environment variable, which the tests do). Month = UTC calendar month of the pull. The cap is a rule, not
a tuning knob: it changes only by Ben's decision and a POST-RUN note in both registrations.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAP_USD = 5.00
REFUSAL_PREFIX = "STOP AND ASK BEN"
EXIT_CODE = 4          # what a scorer's main() returns after a SpendRefused

_ACCESS_WORDS = ("unauthorized", "unauthorised", "forbidden", "not authorized", "not authorised",
                 "license", "licence", "subscription", "payment", "insufficient", "credit", "plan does not")


class SpendRefused(Exception):
    """A pull was refused (cap or access). The message always starts with 'STOP AND ASK BEN'."""


def default_path() -> Path:
    env = os.environ.get("FORWARD_SPEND_PATH")
    return Path(env) if env else ROOT / "Claude outputs" / "forward_spend.json"


def _now(now=None) -> datetime:
    n = now or datetime.now(timezone.utc)
    return n if n.tzinfo else n.replace(tzinfo=timezone.utc)


def month_key(now=None) -> str:
    return _now(now).strftime("%Y-%m")


def _stamp(now=None) -> str:
    return _now(now).strftime("%Y-%m-%dT%H:%M:%SZ")


def read(path: Path | None = None) -> dict:
    p = Path(path) if path else default_path()
    if not p.exists():
        return {"cap_usd": CAP_USD, "entries": [], "refusals": []}
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec.setdefault("cap_usd", CAP_USD)
    rec.setdefault("entries", [])
    rec.setdefault("refusals", [])
    return rec


def _write(rec: dict, path: Path | None) -> None:
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def month_total(rec: dict, month: str) -> float:
    return round(sum(float(e["usd"]) for e in rec["entries"] if e.get("month") == month), 6)


def status(*, now=None, path: Path | None = None, cap: float = CAP_USD) -> dict:
    rec = read(path)
    m = month_key(now)
    spent = month_total(rec, m)
    return {"month": m, "spent_usd": spent, "cap_usd": cap, "headroom_usd": round(cap - spent, 6)}


def log_refusal(test: str, message: str, *, now=None, path: Path | None = None) -> None:
    rec = read(path)
    rec["refusals"].append({"at": _stamp(now), "test": test, "message": message[:500]})
    _write(rec, path)


def last_refusal(path: Path | None = None) -> dict | None:
    r = read(path)["refusals"]
    return r[-1] if r else None


def check(test: str, usd: float, *, now=None, path: Path | None = None, cap: float = CAP_USD) -> dict:
    """Return the month's status if `usd` fits under the cap; otherwise log the refusal and raise SpendRefused."""
    st = status(now=now, path=path, cap=cap)
    if usd > 0 and st["spent_usd"] + usd > cap + 1e-9:
        msg = (f"{REFUSAL_PREFIX}: {test} pull of ${usd:.2f} would take {st['month']} to "
               f"${st['spent_usd'] + usd:.2f}, past the ${cap:.2f}/month cap for both forward tests "
               f"(already ${st['spent_usd']:.2f}). Nothing was bought.")
        log_refusal(test, msg, now=now, path=path)
        raise SpendRefused(msg)
    return st


def record(test: str, usd: float, *, files: int = 0, note: str = "", now=None, path: Path | None = None) -> None:
    if usd <= 0 and not files:
        return
    rec = read(path)
    rec["entries"].append({"at": _stamp(now), "month": month_key(now), "test": test, "usd": round(float(usd), 6),
                           "files": int(files), "note": note})
    _write(rec, path)


_ACCESS_CODE = re.compile(r"\b40[13]\b")


def is_access_refusal(text) -> bool:
    t = str(text).lower()
    return bool(_ACCESS_CODE.search(t)) or any(w in t for w in _ACCESS_WORDS)


def access_refusal(test: str, context: str, err, *, now=None, path: Path | None = None) -> SpendRefused:
    """Build (and log) the SpendRefused for a Databento access refusal."""
    from common.tsmom_fetch import _scrub
    msg = f"{REFUSAL_PREFIX}: Databento refused {test} {context}: {_scrub(err)[:300]}"
    log_refusal(test, msg, now=now, path=path)
    return SpendRefused(msg)


def raise_if_access(test: str, context: str, err, *, now=None, path: Path | None = None) -> None:
    if is_access_refusal(err):
        raise access_refusal(test, context, err, now=now, path=path)
