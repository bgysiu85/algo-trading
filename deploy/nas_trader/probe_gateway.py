#!/usr/bin/env python3
"""Connection probe for the NAS paper IB Gateway (W10-0013 sub 4).

Run it INSIDE the Gateway container's network, so it sees the Gateway exactly as the trader (sub 5) will:

    sudo docker run --rm --security-opt seccomp=unconfined --network container:trader-ib-gateway \
        -v /volume1/docker/trader/probe_gateway.py:/probe.py:ro --entrypoint python \
        trade-journal-recorder:latest /probe.py --check-orders

(The recorder image already holds ib_async 2.1.0, the same pin as the trader. Nothing here needs pandas.)

What it answers, one line each (PASS / FAIL / WARN / INFO):
  1. ports   Which of 4002 (the Gateway's own API) and 4004 (gnzsnz's socat relay) accept a connection.
             Inside the Gateway's namespace both should be open; from any other container only 4004 is.
             The trader accepts only 4002 / 7497, so 4004 is the "risk A" the step-2 audit raised.
  2. api     A read-only API session on 4002 completes the handshake (the Gateway is logged in and the API is on).
  3. paper   Every account the login sees is a paper account (ids start with "D"). A live id is a FAIL.
  4. clock   The Gateway's clock against this machine's, in seconds.
  5. bars    (--bars SPY) one small daily-bar request: market data / permissions work for this login.
  6. orders  (--check-orders) "risk B": is the Gateway's Read-Only API switch OFF? It sends ONE what-if order
             (a margin preview: IBKR answers it and never works the order, nothing is placed) and looks for
             error 321, the Read-Only API rejection. No answer in time is INCONCLUSIVE, not a pass.

It refuses live ports (4001, 4003, 7496, 7498). It never places or cancels an order.
Client ids used: 93 (read-only session) and 94 (what-if session). Taken elsewhere: 17 trader, 55 scanner,
62 trade-alerts, 63 backfill, 77 viewer, 88 params, 91 desk.
"""
from __future__ import annotations

import argparse
import asyncio
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

PAPER_PORTS = {4002: "IB Gateway paper API", 4004: "gnzsnz paper relay (socat)", 7497: "TWS paper API"}
LIVE_PORTS = {4001: "IB Gateway LIVE", 4003: "gnzsnz LIVE relay", 7496: "TWS LIVE", 7498: "TWS LIVE relay"}
READ_ONLY_REJECTION = 321          # "Error validating request ... Read-Only API"
CLIENT_READONLY = 93
CLIENT_WHATIF = 94


@dataclass
class Result:
    status: str                    # PASS | FAIL | WARN | INFO
    name: str
    detail: str

    def line(self) -> str:
        return f"{self.status:<4}  {self.name:<7} {self.detail}"


def tcp_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def default_ib_factory():
    try:
        from ib_async import IB
    except ImportError as e:                                    # pragma: no cover - environment
        raise SystemExit("ib_async is not installed in this Python (use the recorder image)") from e
    return IB()


def check_ports(host: str, ports: list[int], api_port: int, tcp=tcp_open) -> list[Result]:
    out = []
    for p in ports:
        up = tcp(host, p)
        label = PAPER_PORTS.get(p, "port")
        if p == api_port and not up:
            out.append(Result("FAIL", "ports", f"{host}:{p} ({label}) is CLOSED - Gateway not running, still logging in, or wrong network"))
        else:
            out.append(Result("INFO", "ports", f"{host}:{p} ({label}) is {'open' if up else 'closed'}"))
    return out


def explain_connect_error(e: Exception, host: str, port: int) -> str:
    kind = type(e).__name__
    if isinstance(e, ConnectionRefusedError):
        why = "nothing is listening: the Gateway is not up"
    elif isinstance(e, (TimeoutError, asyncio.TimeoutError)):
        why = ("the port accepted but the API never answered: the Gateway is still logging in, is waiting for a "
               "login prompt (see the VNC screen), or the API is switched off")
    else:
        why = "see the Gateway log: docker logs --tail 80 trader-ib-gateway"
    return f"cannot open an API session on {host}:{port} ({kind}: {e}) - {why}"


def check_api(ib, host: str, port: int, timeout: float) -> list[Result]:
    """Connect read-only; the caller keeps `ib` for the later checks. Raises nothing."""
    try:
        ib.connect(host, port, clientId=CLIENT_READONLY, timeout=timeout, readonly=True)
    except Exception as e:                                      # noqa: BLE001 - broker/socket errors vary
        return [Result("FAIL", "api", explain_connect_error(e, host, port))]
    try:
        version = ib.client.serverVersion()
    except Exception:                                           # noqa: BLE001
        version = "?"
    out = [Result("PASS", "api", f"read-only session open on {host}:{port}, client id {CLIENT_READONLY}, server version {version}")]
    accounts = list(ib.managedAccounts())
    if not accounts:
        out.append(Result("FAIL", "paper", "the login reports no accounts"))
    else:
        live = [a for a in accounts if not a.upper().startswith("D")]
        if live:
            out.append(Result("FAIL", "paper", f"account(s) {', '.join(live)} do not look like paper accounts (paper ids start with D) - STOP"))
        else:
            out.append(Result("PASS", "paper", f"paper account(s): {', '.join(accounts)}"))
    return out


def check_clock(ib, now=None) -> Result:
    try:
        server = ib.reqCurrentTime()
    except Exception as e:                                      # noqa: BLE001
        return Result("WARN", "clock", f"could not read the Gateway's clock ({type(e).__name__}: {e})")
    if server.tzinfo is None:
        server = server.replace(tzinfo=timezone.utc)
    here = now or datetime.now(timezone.utc)
    diff = (here - server).total_seconds()
    status = "PASS" if abs(diff) <= 5 else "WARN"
    return Result(status, "clock", f"this machine minus the Gateway = {diff:+.1f} s ({'ok' if status == 'PASS' else 'more than 5 s: check NTP on the NAS'})")


def check_bars(ib, symbol: str, timeout: float) -> Result:
    try:
        from ib_async import Stock
        contract = Stock(symbol, "SMART", "USD")
        if not ib.qualifyContracts(contract):
            return Result("FAIL", "bars", f"{symbol} did not qualify")
        bars = ib.reqHistoricalData(contract, endDateTime="", durationStr="5 D", barSizeSetting="1 day",
                                    whatToShow="TRADES", useRTH=True, formatDate=1, timeout=timeout)
    except Exception as e:                                      # noqa: BLE001
        return Result("FAIL", "bars", f"{symbol} daily bars failed ({type(e).__name__}: {e})")
    if not bars:
        return Result("FAIL", "bars", f"{symbol}: IBKR returned no daily bars (market-data permission or pacing?)")
    last = bars[-1]
    return Result("PASS", "bars", f"{symbol}: {len(bars)} daily bars, last {last.date} close {last.close}")


def check_orders(ib_factory, host: str, port: int, symbol: str, timeout: float) -> Result:
    """Risk B. Own session (not read-only, client id 94) and ONE what-if order; never transmits a working order."""
    ib = ib_factory()
    errors: list[tuple[int, str]] = []

    def on_error(reqId, errorCode, errorString, contract=None, *rest):
        errors.append((int(errorCode), str(errorString)))

    try:
        ib.connect(host, port, clientId=CLIENT_WHATIF, timeout=timeout, readonly=False)
    except Exception as e:                                      # noqa: BLE001
        return Result("FAIL", "orders", explain_connect_error(e, host, port))
    ib.errorEvent += on_error
    pending = None
    try:
        from ib_async import LimitOrder, Stock
        contract = Stock(symbol, "SMART", "USD")
        if not ib.qualifyContracts(contract):
            return Result("WARN", "orders", f"INCONCLUSIVE: {symbol} did not qualify, so no what-if was sent")
        order = LimitOrder("BUY", 1, 1.00)             # a what-if preview: IBKR answers it, never works it
        pending = ib.whatIfOrderAsync(contract, order)
        try:
            state = ib.run(asyncio.wait_for(pending, timeout))
        except asyncio.TimeoutError:
            state = None
        codes = {c for c, _ in errors}
        if READ_ONLY_REJECTION in codes:
            msg = next(m for c, m in errors if c == READ_ONLY_REJECTION)
            return Result("FAIL", "orders", f"Read-Only API is ON (error 321: {msg}) - every order would be rejected; "
                                            "set READ_ONLY_API=no in .env and recreate the Gateway container")
        if state is not None:
            return Result("PASS", "orders", f"what-if accepted ({symbol} BUY 1 LMT 1.00, status {getattr(state, 'status', '?')}): "
                                            "Read-Only API is OFF, orders can reach IBKR. Nothing was placed")
        extra = f" Errors seen: {errors}" if errors else ""
        return Result("WARN", "orders", f"INCONCLUSIVE: no what-if answer within {timeout:.0f} s and no error 321.{extra} "
                                        "Check the setting directly: grep -i ReadOnlyApi in the Gateway's ibc config (see NAS-TRADER-SETUP.md)")
    except Exception as e:                                      # noqa: BLE001
        return Result("WARN", "orders", f"INCONCLUSIVE: what-if raised {type(e).__name__}: {e}")
    finally:
        try:
            if pending is not None and hasattr(pending, "done") and not pending.done():
                pending.cancel()
        except Exception:                                       # noqa: BLE001
            pass
        try:
            ib.errorEvent -= on_error
        except Exception:                                       # noqa: BLE001
            pass
        try:
            ib.disconnect()
        except Exception:                                       # noqa: BLE001
            pass


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Probe the NAS paper IB Gateway (W10-0013 sub 4). Paper ports only.")
    ap.add_argument("--host", default="127.0.0.1", help="default 127.0.0.1 = inside the Gateway container's network")
    ap.add_argument("--port", type=int, default=4002, help="API port to open a session on (default 4002, what the trader requires)")
    ap.add_argument("--ports", default="4002,4004", help="ports to test with a plain TCP connect (comma list)")
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--bars", metavar="SYMBOL", help="also request 5 daily bars for SYMBOL, e.g. SPY")
    ap.add_argument("--check-orders", action="store_true", help="risk B: send one what-if order and look for the Read-Only API error 321")
    ap.add_argument("--order-symbol", default="SPY")
    return ap.parse_args(argv)


def main(argv=None, ib_factory=default_ib_factory, tcp=tcp_open, out=print) -> int:
    a = parse_args(argv)
    if a.port in LIVE_PORTS:
        out(f"REFUSED: port {a.port} is {LIVE_PORTS[a.port]}. This probe is for paper ports only.")
        return 2
    if a.port not in PAPER_PORTS:
        out(f"REFUSED: port {a.port} is not a known paper port {sorted(PAPER_PORTS)}.")
        return 2
    ports = [int(p) for p in a.ports.split(",") if p.strip()]
    if any(p in LIVE_PORTS for p in ports):
        out(f"REFUSED: --ports contains a live port {sorted(set(ports) & set(LIVE_PORTS))}.")
        return 2

    results = check_ports(a.host, ports, a.port, tcp=tcp)
    if not any(r.status == "FAIL" for r in results):
        ib = ib_factory()
        api = check_api(ib, a.host, a.port, a.timeout)
        results += api
        if api[0].status == "PASS":
            try:
                results.append(check_clock(ib))
                if a.bars:
                    results.append(check_bars(ib, a.bars, a.timeout))
            finally:
                try:
                    ib.disconnect()
                except Exception:                               # noqa: BLE001
                    pass
            if a.check_orders:
                results.append(check_orders(ib_factory, a.host, a.port, a.order_symbol, a.timeout))
    for r in results:
        out(r.line())
    fails = [r for r in results if r.status == "FAIL"]
    warns = [r for r in results if r.status == "WARN"]
    verdict = "FAIL" if fails else ("PASS with warnings" if warns else "PASS")
    out(f"VERDICT {verdict} ({len(fails)} fail, {len(warns)} warn) at {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
