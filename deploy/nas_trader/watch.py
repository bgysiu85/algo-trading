#!/usr/bin/env python3
"""Outside dead-man ping and trader / portal health checks (W10-0013 sub 12). Standard library only.

Runs as the container `trader-watch` (profile "watch") in the trader project, once a minute:

  ping    GET HC_PING_URL (healthchecks.io). Sent every cycle while this container lives. healthchecks.io messages Ben
          (its own Telegram integration) when the pings STOP, which is what catches the NAS, its network or Docker going
          down: nothing on the NAS can report its own death. No HC_PING_URL = no ping.
  portal  https://trader.thesiuz.com must answer. Any reply under 500 counts (a login redirect is fine, the relay is
          closed to strangers); a Cloudflare error (530 when the tunnel is down, 502 when the relay is), a timeout or
          no connection counts as down. Needs PORTAL_FAIL_AFTER misses in a row (3) before it speaks.
  trader  on weekdays between TRADER_WATCH_START and TRADER_WATCH_END New York (04:10-09:25) the session lock
          var/state/session.lock must exist with a heartbeat under 120 s old. Anything else means the trader is not
          running when it should be (or died). Outside the window nothing is checked. US market holidays are not known
          here: put the date in WATCH_SKIP_DATES (YYYY-MM-DD, comma separated) to silence a holiday.

Messages go to Telegram with the trader's own bot (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID); without them they are only
logged. A problem repeats every WATCH_REPEAT_S (3600) and an "OK again" follows. The container reads var/ read-only,
publishes nothing, is not in the Gateway's network, and can place no order. `--once` prints what it sees and sends nothing.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("trader.watch")
NY = ZoneInfo("America/New_York")
HEARTBEAT_STALE_S = 120          # same rule as common/session_lock.py and CLAUDE.md


def _hhmm(text: str) -> dtime:
    h, m = text.strip().split(":")
    return dtime(int(h), int(m))


class Cfg:
    def __init__(self, env=os.environ):
        g = lambda k, d="": (env.get(k) or "").strip() or d  # noqa: E731
        self.var = Path(g("TRADER_VAR_DIR_IN_CONTAINER", "/var-data"))
        self.ping_url = g("HC_PING_URL")
        self.portal_url = g("WATCH_PORTAL_URL", "https://trader.thesiuz.com/api/health")
        self.portal_fail_after = int(g("PORTAL_FAIL_AFTER", "3"))
        self.start = _hhmm(g("TRADER_WATCH_START", "04:10"))
        self.end = _hhmm(g("TRADER_WATCH_END", "09:25"))
        self.skip_dates = {d.strip() for d in g("WATCH_SKIP_DATES").split(",") if d.strip()}
        self.repeat_s = float(g("WATCH_REPEAT_S", "3600"))
        self.name = g("WATCH_NAME", "NAS trader")
        self.token = g("TELEGRAM_BOT_TOKEN")
        self.chat = g("TELEGRAM_CHAT_ID")


# ---------------------------------------------------------------------------- the checks
def trader_problem(now: datetime, lock: dict | None, cfg: Cfg, now_epoch: float) -> str | None:
    """A message when the trader should be running and is not; None otherwise (or outside the window)."""
    ny = now.astimezone(NY)
    if ny.weekday() >= 5 or ny.strftime("%Y-%m-%d") in cfg.skip_dates:
        return None
    if not (cfg.start <= ny.time() < cfg.end):
        return None
    if not lock:
        return (f"no trader session is running ({ny.strftime('%a %H:%M')} New York, expected from "
                f"{cfg.start.strftime('%H:%M')}). Is trader-trader started? (sudo docker ps -a | grep trader)")
    beat = lock.get("heartbeat_epoch")
    if not isinstance(beat, (int, float)):
        return "the session lock has no heartbeat (an old-format lock?)"
    age = now_epoch - beat
    if age > HEARTBEAT_STALE_S:
        return (f"the trader's heartbeat stopped {age / 60:.0f} min ago ({lock.get('mode', '?')} "
                f"{lock.get('strategy', '?')}): it crashed or hung. sudo docker logs --tail 40 trader-trader")
    return None


def read_lock(var: Path) -> dict | None:
    """The lock file, or None when there is none. A half-written file is retried once, then counted as none."""
    p = Path(var) / "state" / "session.lock"
    for _ in range(2):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            time.sleep(0.2)
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def portal_up(url: str, timeout: float = 10.0) -> tuple[bool, str]:
    """(reachable, detail). A reply under 500 is reachable; redirects are not followed."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "trader-watch"}), timeout=timeout) as r:
            return r.status < 500, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return e.code < 500, f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"no answer ({type(getattr(e, 'reason', e)).__name__})"


def ping(url: str, timeout: float = 10.0) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "trader-watch"}), timeout=timeout).read(64)
        return True
    except (urllib.error.URLError, OSError):
        return False


# ---------------------------------------------------------------------------- the loop
class Watcher:
    def __init__(self, cfg: Cfg, send, clock=time.time, lock_reader=None, portal=None, pinger=None):
        self.cfg, self.send, self.clock = cfg, send, clock
        self.lock_reader = lock_reader or (lambda: read_lock(cfg.var))
        self.portal = portal or (lambda: portal_up(cfg.portal_url))
        self.pinger = pinger or ping
        self.active: dict[str, dict] = {}
        self.misses = 0
        self.started = False

    def problems(self, now: float) -> dict[str, str]:
        out: dict[str, str] = {}
        ok, detail = self.portal()
        self.misses = 0 if ok else self.misses + 1
        if self.misses >= self.cfg.portal_fail_after:
            out["portal"] = (f"the portal {self.cfg.portal_url} is not answering ({detail}) for {self.misses} checks. "
                             f"Tunnel or relay? (sudo docker ps | grep -E 'edge-tunnel|trader-relay')")
        msg = trader_problem(datetime.fromtimestamp(now, tz=ZoneInfo("UTC")), self.lock_reader(), self.cfg, now)
        if msg:
            out["trader"] = msg
        return out

    def step(self) -> list[str]:
        now = self.clock()
        queued: list[str] = []
        if self.cfg.ping_url:
            if not self.pinger(self.cfg.ping_url):
                log.warning("dead-man ping failed (healthchecks.io unreachable?)")
        if not self.started:
            self.started = True
            queued.append(f"🟢 {self.cfg.name}: watcher running (portal, trader heartbeat"
                          f"{', dead-man ping' if self.cfg.ping_url else ', NO dead-man ping set'}).")
        problems = self.problems(now)
        for key, msg in problems.items():
            st = self.active.get(key)
            if st is None:
                self.active[key] = {"since": now, "last": now}
                queued.append(f"⚠️ {self.cfg.name}: {msg}")
            elif now - st["last"] >= self.cfg.repeat_s:
                st["last"] = now
                queued.append(f"⚠️ Still a problem - {self.cfg.name}: {msg}")
        for key in [k for k in self.active if k not in problems]:
            st = self.active.pop(key)
            queued.append(f"✅ {self.cfg.name} OK again: {key} (was down {(now - st['since']) / 60:.0f} min).")
        for m in queued:
            try:
                self.send(m)
            except Exception as e:  # noqa: BLE001 - a failed message must not stop the loop
                log.warning("send failed: %s", type(e).__name__)
        return queued


def telegram_sender(token: str, chat: str):
    def send(text: str) -> None:
        body = json.dumps({"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
        log.info("sent: %s", text.splitlines()[0][:100])
    return send


def log_sender(text: str) -> None:
    log.info("WOULD SEND (no Telegram settings): %s", text)


def main(argv=None, env=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--every", type=float, default=60.0)
    ap.add_argument("--once", action="store_true", help="print what is seen, send and ping nothing")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    cfg = Cfg(os.environ if env is None else env)
    if a.once:
        w = Watcher(cfg, log_sender, pinger=lambda u: True)
        w.cfg.portal_fail_after = 1
        probs = w.problems(time.time())
        print("lock:", read_lock(cfg.var))
        print("no problems" if not probs else "\n".join(f"{k}: {v}" for k, v in probs.items()))
        return 0
    send = telegram_sender(cfg.token, cfg.chat) if cfg.token and cfg.chat else log_sender
    w = Watcher(cfg, send)
    while True:
        try:
            w.step()
        except Exception:  # noqa: BLE001
            log.exception("check failed")
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
