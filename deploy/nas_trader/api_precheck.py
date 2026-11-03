#!/usr/bin/env python3
"""Pre-session API check for the NAS paper IB Gateway (W10-0013 sub 16).

WHY. On Sun 1 Nov the Gateway's health check stayed green while IBKR refused every API session with error 10141
("Paper trading disclaimer must first be accepted for API connection"): the health check only tests that port 4002
accepts a TCP connection, and a dialog left open on the Gateway's screen does not close the port. This check does
what the trader does: it opens a real, read-only API session, asks for the accounts and the server time, and
tells Ben on Telegram when that fails.

RUN IT INSIDE THE GATEWAY CONTAINER'S NETWORK (nothing is published; the trader refuses any other route too):

    sudo docker run --rm --security-opt seccomp=unconfined --network container:trader-ib-gateway \
        -e TELEGRAM_BOT_TOKEN -e TELEGRAM_CHAT_ID \
        -v /volume1/docker/trader/api_precheck.py:/precheck.py:ro --entrypoint python \
        trade-journal-recorder:latest /precheck.py

(`api_precheck.sh` wraps this for the DSM Task Scheduler. The recorder image already holds ib_async 2.1.0.)

WHAT PASSES. A read-only session opens, the login reports at least one account, every account is a paper account
(ids start with "D"), the Gateway answers a server-time request, and no error 10141 arrived while connecting.

RETRIES. A Gateway that is mid-reconnect needs a minute or two, so a failed attempt is repeated (default 3 attempts,
20 s apart) before anyone is messaged. Telegram is told only about the FINAL result, and only on failure unless
--notify-ok is given.

IT NEVER PLACES, CANCELS OR PREVIEWS AN ORDER. It refuses live ports (4001, 4003, 7496, 7498). Client id 95 is used
(taken elsewhere: 17 trader, 55 scanner, 62 trade-alerts, 63 backfill, 77 viewer, 88 params, 91 desk, 93/94 probe).

Exit codes: 0 handshake OK, 1 handshake failed after all attempts, 2 refused (live or unknown port).
Standard library plus ib_async (imported only when it runs for real).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

PAPER_PORTS = {4002: "IB Gateway paper API", 7497: "TWS paper API"}
LIVE_PORTS = {4001: "IB Gateway LIVE", 4003: "gnzsnz LIVE relay", 7496: "TWS LIVE", 7498: "TWS LIVE relay"}
CLIENT_ID = 95
DISCLAIMER_CODE = 10141          # "Paper trading disclaimer must first be accepted for API connection"
CLIENT_ID_IN_USE = 326

FIX_HINT = ("Fix: sudo docker restart trader-ib-gateway (this cleared it on 1 Nov), then wait about 3 minutes. "
            "Or read the dialog on the Gateway's screen (VNC on the NAS at 127.0.0.1:5901, reach it by SSH tunnel).")


@dataclass
class Outcome:
    ok: bool
    reason: str
    code: int | None = None        # an IBKR error code worth naming, if one arrived


def default_ib_factory():
    try:
        from ib_async import IB
    except ImportError as e:                                    # pragma: no cover - environment
        raise SystemExit("ib_async is not installed in this Python (use the recorder image)") from e
    return IB()


# ---------------------------------------------------------------------------- the handshake
def explain(code: int | None, error: Exception | None, host: str, port: int) -> str:
    if code == DISCLAIMER_CODE:
        return ("IBKR refuses API sessions: the paper-trading disclaimer has not been accepted (error 10141), usually "
                "a dialog left open on the Gateway's screen after a reconnect. Port 4002 still answers, so Docker "
                "shows the Gateway healthy.")
    if code == CLIENT_ID_IN_USE:
        return f"client id {CLIENT_ID} is already in use (error 326): another check is running, try again."
    if isinstance(error, ConnectionRefusedError):
        return f"nothing is listening on {host}:{port}: the Gateway is not up (restarting, or stopped)."
    if isinstance(error, (TimeoutError, )) or type(error).__name__ == "TimeoutError":
        return (f"the port {port} accepted but the API never answered: the Gateway is still logging in, a dialog is "
                "waiting on its screen, or the API is switched off.")
    if error is not None:
        return f"cannot open an API session on {host}:{port} ({type(error).__name__}: {error})."
    return f"the API session on {host}:{port} did not complete the handshake."


def handshake(ib_factory, host: str, port: int, timeout: float) -> Outcome:
    """One attempt. Never raises. Any 10141 seen while connecting is a failure even if the connect call returned."""
    ib = ib_factory()
    seen: list[tuple[int, str]] = []

    def on_error(reqId, errorCode, errorString, *rest):          # noqa: N803 - ib_async's names
        seen.append((int(errorCode), str(errorString)))

    try:
        ib.errorEvent += on_error
    except Exception:                                           # noqa: BLE001 - a fake without events is fine
        pass
    try:
        try:
            ib.connect(host, port, clientId=CLIENT_ID, timeout=timeout, readonly=True)
        except Exception as e:                                  # noqa: BLE001 - broker/socket errors vary
            code = next((c for c, _ in seen if c in (DISCLAIMER_CODE, CLIENT_ID_IN_USE)), None)
            return Outcome(False, explain(code, e, host, port), code)
        if any(c == DISCLAIMER_CODE for c, _ in seen):
            return Outcome(False, explain(DISCLAIMER_CODE, None, host, port), DISCLAIMER_CODE)
        accounts = list(ib.managedAccounts())
        if not accounts:
            return Outcome(False, "the session opened but the login reports no accounts (the Gateway is not fully logged in).")
        live = [a for a in accounts if not str(a).upper().startswith("D")]
        if live:
            return Outcome(False, f"account(s) {', '.join(live)} do not look like paper accounts (paper ids start with D): STOP.")
        try:
            server_time = ib.reqCurrentTime()
        except Exception as e:                                  # noqa: BLE001
            return Outcome(False, f"the session opened but the Gateway did not answer a server-time request ({type(e).__name__}: {e}).")
        if not isinstance(server_time, datetime):
            return Outcome(False, "the session opened but the Gateway returned no server time.")
        code = next((c for c, _ in seen if c == DISCLAIMER_CODE), None)
        return Outcome(True, f"API session OK on {host}:{port}: paper account(s) {', '.join(accounts)}, server time {server_time:%Y-%m-%d %H:%M:%S}.", code)
    finally:
        try:
            ib.disconnect()
        except Exception:                                       # noqa: BLE001
            pass


def run_attempts(ib_factory, host: str, port: int, timeout: float, attempts: int, gap_s: float,
                 sleep=time.sleep, out=print) -> tuple[Outcome, int]:
    last = Outcome(False, "no attempt was made")
    for n in range(1, max(1, attempts) + 1):
        last = handshake(ib_factory, host, port, timeout)
        out(f"attempt {n}/{attempts}: {'PASS' if last.ok else 'FAIL'} - {last.reason}")
        if last.ok:
            return last, n
        if n < attempts:
            sleep(gap_s)
    return last, attempts


# ---------------------------------------------------------------------------- Telegram
def send_telegram(token: str, chat: str, text: str, urlopen=urllib.request.urlopen) -> bool:
    """Best effort. A failure to message must never change the check's own result."""
    if not token or not chat:
        return False
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": text}).encode(),
            headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=10) as r:
            return 200 <= getattr(r, "status", 200) < 300
    except Exception:                                           # noqa: BLE001
        return False


def message(label: str, outcome: Outcome, attempts: int, note: str) -> str:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    head = "NAS trader: Gateway API check" + (f" ({label})" if label else "")
    if outcome.ok:
        return f"{head} OK at {when}. {outcome.reason}" + (f" {note}" if note else "")
    return (f"{head} FAILED at {when} after {attempts} attempt(s). {outcome.reason} "
            + (f"{note} " if note else "") + FIX_HINT)


# ---------------------------------------------------------------------------- main
def parse_args(argv):
    ap = argparse.ArgumentParser(description="Pre-session API handshake check for the NAS paper IB Gateway (W10-0013 sub 16).")
    ap.add_argument("--host", default="127.0.0.1", help="default 127.0.0.1 = inside the Gateway container's network")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--timeout", type=float, default=15.0, help="seconds per connect attempt")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--gap", type=float, default=20.0, help="seconds between attempts")
    ap.add_argument("--label", default=os.environ.get("PRECHECK_LABEL", ""), help="short name for the message, e.g. 'before the window'")
    ap.add_argument("--note", default="", help="extra sentence appended to the message, e.g. 'after one Gateway restart'")
    ap.add_argument("--notify-ok", action="store_true", help="also message Telegram when the check passes")
    ap.add_argument("--no-notify", action="store_true", help="never message Telegram (the wrapper uses it for a first pass)")
    return ap.parse_args(argv)


def main(argv=None, ib_factory=default_ib_factory, sleep=time.sleep, out=print, notify=send_telegram, env=os.environ) -> int:
    a = parse_args(argv)
    if a.port in LIVE_PORTS:
        out(f"REFUSED: port {a.port} is {LIVE_PORTS[a.port]}. This check is for paper ports only.")
        return 2
    if a.port not in PAPER_PORTS:
        out(f"REFUSED: port {a.port} is not a known paper port {sorted(PAPER_PORTS)}.")
        return 2
    outcome, used = run_attempts(ib_factory, a.host, a.port, a.timeout, a.attempts, a.gap, sleep=sleep, out=out)
    verdict = "PASS" if outcome.ok else "FAIL"
    out(f"PRECHECK {verdict} at {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z" + (f" ({a.label})" if a.label else ""))
    if not a.no_notify and (not outcome.ok or a.notify_ok):
        sent = notify(env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", ""),
                      message(a.label, outcome, used, a.note))
        out("telegram: sent" if sent else "telegram: NOT sent (no token/chat id, or Telegram unreachable)")
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    sys.exit(main())
