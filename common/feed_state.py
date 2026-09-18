#!/usr/bin/env python3
"""The feed's real-time state, written by `tv_feed` and read by `ui_bridge`.

Answers `claude/feed_state_CONTRACT_PROPOSAL_20260918.md`. Contract 1.8.

WHY THIS FILE EXISTS AT ALL. `tv_feed` runs its own 5.5-hour loop and holds the
watchlist-writer lock; the state document the portal reads is published by the
TRADER, a different process. So the process that knows whether the feed is real
time is not the process that can say so. This module is the one definition of
that block, imported by both sides, so the writer and the reader cannot drift
apart in two languages the way a page parsing `delayed_streaming_900` in
JavaScript would.

THE PROPERTY THAT MATTERS, AND IT IS THE WHOLE POINT:

    A FAILURE TO LEARN THE MODE MUST PRODUCE `unknown`, NEVER `streaming`.

A missing file, a malformed one, a truncated write, a value this module does
not recognise -- every one of them reads back as `unknown`. A reader that
defaults to the good value on error is the same defect as a cookie that
silently degrades to anonymous: a control whose output is indistinguishable
from the failure it exists to detect. That trap is why `update_mode` is
checked at all, and this is the same trap one layer up.

STALENESS IS THE WRITER'S JOB, NOT THE READER'S. `var/` survives across days,
so yesterday's file sitting on disk would render as a confident "Real-time"
all through this morning. Neither side should have to invent an age rule for
that -- the portal is right to refuse to. Instead `tv_feed` calls `initial()`
and publishes an `unknown` block the moment the process starts, BEFORE its
first check, so the file can never survive into a session it does not describe.
Between process start and the first answer the state is honestly unknown, which
is what it is.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path("var/feed_state.json")
SOURCE = "tradingview"

# `unknown` is a REAL value, not a missing one: the check could not run, the
# request failed, or the agent predates the field. It is not "fine".
MODES = ("streaming", "delayed", "unknown")

# Four, not a boolean, because each one has a DIFFERENT fix and a delayed feed
# cannot distinguish them:
#   signed      both cookies were set and sent  -> it expired; refresh it
#   absent      neither is set                  -> set them
#   incomplete  exactly one is set              -> set the other one
#   disabled    --no-cookie was passed          -> restart without the flag
# `incomplete` is the one worth having. TradingView SIGNS the session, so
# `sessionid` alone is served anonymously; without this the portal would tell
# Ben no cookie is set while one is, and send him to the wrong fix.
COOKIE_STATES = ("signed", "absent", "incomplete", "disabled")

_DIGITS = re.compile(r"(\d+)")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def delay_seconds(raw) -> int | None:
    """900 out of `delayed_streaming_900`, parsed HERE and once.

    None when the value carries no number -- never 0. Zero means real time, and
    a delay we failed to parse is not real time; returning 0 would render a
    delayed feed as current, which is the one mistake this whole block exists
    to prevent.
    """
    if raw is None:
        return None
    m = _DIGITS.search(str(raw))
    return int(m.group(1)) if m else None


def cookie_state(sid: str | None, sign: str | None, disabled: bool = False) -> str:
    if disabled:
        return "disabled"
    if sid and sign:
        return "signed"
    if sid or sign:
        return "incomplete"
    return "absent"


def cookie_state_from_env(sid_env: str, sign_env: str, disabled: bool = False) -> str:
    return cookie_state(os.environ.get(sid_env), os.environ.get(sign_env),
                        disabled)


def block(verdict: str, raw, cookie: str, checked_at: str | None = None,
          source: str = SOURCE) -> dict:
    """The contract block, from `tv_feed.mode_verdict`'s four-word answer.

    UNRECOGNISED maps to `unknown`, deliberately and stated so both sides
    agree: a value that is neither streaming nor delayed is not a fourth thing
    the portal can render, and it is certainly not real time. The vendor's raw
    string goes into `detail` verbatim, so nothing is lost and a tooltip can
    show exactly what was said.
    """
    v = (verdict or "").upper()
    if v == "STREAMING":
        mode, delay = "streaming", 0
    elif v == "DELAYED":
        mode, delay = "delayed", delay_seconds(raw)
    else:
        mode, delay = "unknown", None
    if cookie not in COOKIE_STATES:
        cookie = "absent"
    return {
        "source": source,
        "mode": mode,
        "delay_seconds": delay,
        "authenticated": cookie == "signed",
        "cookie_state": cookie,
        "checked_at": checked_at or utc_now(),
        "detail": None if raw is None else str(raw),
    }


def initial(cookie: str, source: str = SOURCE) -> dict:
    """What the file says between process start and the first answer."""
    return block("UNKNOWN", None, cookie, source=source)


def publish(state: dict, path: Path | str = STATE_PATH) -> bool:
    """Write atomically. Never raises: a feed that will not start because a
    diagnostic file could not be written is worse than one that starts without
    it, and the reader treats a missing file as `unknown` anyway.

    The temp file sits in the SAME directory so `os.replace` is a rename within
    one filesystem and therefore atomic -- a reader sees the old file or the
    new one, never a half-written one.
    """
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, p)
        return True
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def read(path: Path | str = STATE_PATH) -> dict | None:
    """The block, or None if anything at all is wrong with it.

    None is what the publisher omits the block for, which the portal renders as
    `unknown`. Validated rather than trusted: a file with `mode: "streaming"`
    and nothing else is not a reading, and a mode this module does not know is
    not one either.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        got = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(got, dict):
        return None
    if got.get("mode") not in MODES:
        return None
    if not got.get("checked_at"):
        return None
    return got
