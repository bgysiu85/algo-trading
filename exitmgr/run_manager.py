#!/usr/bin/env python3
"""Entry point of the live exit manager (W15-0053 sub 4a). Paper account only; dry by default.

    python -m exitmgr.run_manager                 # settings from the environment (exitmgr/config.py lists them)

It connects to the Gateway with client id 31, checks the paper lock (rail 10: every reported account starts with D; in paper
mode XM_ACCOUNT=DU... must be the connected account), then runs the manager loop: one pass every XM_LOOP_S seconds, reconnecting
with back-off if the Gateway drops (daily / weekly restarts are expected). It writes ONLY to XM_OUT_DIR:
    events.jsonl   append-only event log (rail 14)      state.json   the manager's state (atomic)
    control/       PAUSE, FLATTEN, STOP_MANAGER flags (killswitch.py)
Ctrl-C or a STOP_MANAGER file stops it and leaves the resting stops at IBKR. Exit codes: 0 stopped cleanly, 1 refused
(configuration, port, account), 2 could not connect.
"""
from __future__ import annotations

import argparse
import sys

from exitmgr import config as C
from exitmgr.eventlog import EventLog
from exitmgr.killswitch import KillSwitch
from exitmgr.manager import Manager
from exitmgr.timeutil import utcnow

BACKOFF = (5, 10, 20, 40, 60)


def connect(ib, cfg) -> None:
    C.check_port(cfg.port)
    ib.connect(cfg.host, cfg.port, clientId=cfg.client_id, timeout=15, readonly=(cfg.mode != "paper"))


def main(argv=None, env=None, ib_factory=None, clock=None, out=print, max_steps: int | None = None,
         atr_provider=None) -> int:
    ap = argparse.ArgumentParser(description="W15-0053 live exit manager (paper only; dry by default)")
    ap.add_argument("--max-steps", type=int, default=None, help="stop after N loop passes (tests / smoke runs)")
    a = ap.parse_args(argv)
    max_steps = a.max_steps if a.max_steps is not None else max_steps
    clock = clock or utcnow
    try:
        cfg = C.load(env)
    except C.Refused as e:
        out(f"REFUSED: {e}")
        return 1
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    log = EventLog(cfg.out_dir / "events.jsonl", clock=clock, echo=out)
    if ib_factory is None:                                     # pragma: no cover - environment
        from ib_async import IB
        ib_factory = IB
    ib = ib_factory()
    try:
        connect(ib, cfg)
    except C.Refused as e:
        log.write("refused", rail="10", msg=str(e))
        out(f"REFUSED: {e}")
        return 1
    except Exception as e:                                     # noqa: BLE001
        log.alert("CONNECT", f"could not connect to {cfg.host}:{cfg.port}: {type(e).__name__}: {e}")
        return 2
    try:
        account = C.check_accounts(cfg, ib.managedAccounts())
    except C.Refused as e:
        log.write("refused", rail="10", msg=str(e))
        out(f"REFUSED: {e}")
        ib.disconnect()
        return 1
    kill = KillSwitch(cfg.out_dir / "control", clock=clock)
    mgr = Manager(ib, cfg, account, log, kill, clock=clock, atr_provider=atr_provider)
    out(f"exit manager {cfg.mode.upper()} on {account} via {cfg.host}:{cfg.port} client {cfg.client_id}; log {log.path}")
    steps, retry = 0, 0
    try:
        mgr.start()
        while max_steps is None or steps < max_steps:
            steps += 1
            if not ib.isConnected():
                mgr.on_disconnect()
                if kill.stop_requested():
                    mgr.stop("STOP_MANAGER file (while disconnected)")
                    break
                wait = BACKOFF[min(retry, len(BACKOFF) - 1)]
                retry += 1
                ib.sleep(wait)
                try:
                    connect(ib, cfg)
                    C.check_accounts(cfg, ib.managedAccounts())
                except C.Refused as e:
                    log.write("refused", rail="10", msg=str(e))
                    out(f"REFUSED after reconnect: {e}")
                    mgr.stop("paper lock failed after reconnect")
                    return 1
                except Exception as e:                         # noqa: BLE001
                    log.write("reconnect_failed", error=f"{type(e).__name__}: {e}", attempt=retry)
                    continue
                retry = 0
                mgr.on_reconnect()
                continue
            if not mgr.step():
                break
            ib.sleep(cfg.loop_s)
    except KeyboardInterrupt:
        mgr.stop("Ctrl-C")
    finally:
        mgr.stop("loop ended")
        try:
            ib.disconnect()
        except Exception:                                      # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
