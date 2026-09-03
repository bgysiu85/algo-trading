#!/usr/bin/env python3
"""
MCL — read-only account viewer.

IB Gateway has no order/trade UI, and IBKR won't let you log the same username
into Client Portal while Gateway holds the session.  But the API *does* accept
several simultaneous clients on one Gateway, so this connects on its own
client id and prints what the account currently looks like.

    .\\.venv\\Scripts\\python.exe report_trades.py            # once
    .\\.venv\\Scripts\\python.exe report_trades.py --watch    # refresh every 30s

Places no orders.  Safe to run while mcl_paper_trader.py is trading.

NOTE ON EXECUTIONS
------------------
IB only shows a client the orders and executions *that client placed*, unless
it connects as the "Master API client".  To see the trader's fills here:

    IB Gateway -> Configure -> Settings -> API -> Settings
    Master API client ID:  77          (then restart Gateway)

Positions, cash and P&L are account-wide and always visible regardless.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

try:
    from ib_async import IB, ExecutionFilter
except ImportError:
    sys.exit("ib_async not installed.  Run:  pip install ib_async")

PAPER_PORTS = {7497: "TWS paper", 4002: "IB Gateway paper"}
LIVE_PORTS = {7496: "TWS LIVE", 4001: "IB Gateway LIVE"}

HOST = "127.0.0.1"
VIEWER_CLIENT_ID = 77          # distinct from the trader's id


def hr(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))


async def snapshot(ib: IB) -> None:
    print(f"\n{'=' * 70}")
    print(f"  MCL account view — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'=' * 70}")

    # ---- balances (account-wide, always available) ------------------------
    hr("account")
    want = ["NetLiquidation", "TotalCashValue", "BuyingPower",
            "AvailableFunds", "GrossPositionValue", "RealizedPnL",
            "UnrealizedPnL"]
    rows = {r.tag: r.value for r in await ib.accountSummaryAsync()
            if r.currency in ("USD", "")}
    for tag in want:
        if tag in rows:
            try:
                print(f"  {tag:22s} {float(rows[tag]):>14,.2f}")
            except ValueError:
                print(f"  {tag:22s} {rows[tag]:>14s}")

    # ---- positions --------------------------------------------------------
    hr("open positions")
    positions = await ib.reqPositionsAsync()
    if not positions:
        print("  (flat)")
    else:
        print(f"  {'SYMBOL':8s} {'QTY':>8s} {'AVG COST':>10s} {'BOOK':>12s}")
        for p in positions:
            book = p.position * p.avgCost
            print(f"  {p.contract.symbol:8s} {p.position:>8.0f} "
                  f"{p.avgCost:>10.4f} {book:>12,.2f}")

    # ---- open orders ------------------------------------------------------
    hr("open orders")
    orders = await ib.reqAllOpenOrdersAsync()
    if not orders:
        print("  (none)")
    else:
        for t in orders:
            o, c = t.order, t.contract
            lmt = f"@{o.lmtPrice}" if o.lmtPrice else ""
            print(f"  {c.symbol:8s} {o.action:5s} {o.totalQuantity:>7.0f} "
                  f"{o.orderType:6s} {lmt:>10s}  {t.orderStatus.status}"
                  f"  (client {o.clientId})")

    # ---- today's executions ----------------------------------------------
    hr("executions today")
    fills = await ib.reqExecutionsAsync(ExecutionFilter())
    if not fills:
        print("  (none visible to this client)")
        print("  If the trader has filled orders, set 'Master API client ID' to")
        print(f"  {VIEWER_CLIENT_ID} in Gateway API settings and restart Gateway.")
        print("  Either way, mcl_fills_YYYYMMDD.csv is the authoritative record.")
    else:
        print(f"  {'TIME':10s} {'SYMBOL':8s} {'SIDE':5s} {'QTY':>7s} "
              f"{'PRICE':>10s} {'COMM':>8s} {'RLZ P/L':>10s}")
        realized = 0.0
        for f in sorted(fills, key=lambda x: x.execution.time):
            e, r = f.execution, f.commissionReport
            comm = r.commission if r else 0.0
            pnl = r.realizedPNL if r and r.realizedPNL not in (None, 0.0) else 0.0
            if pnl and abs(pnl) < 1e11:      # IB sends a sentinel for "n/a"
                realized += pnl
            print(f"  {e.time:%H:%M:%S}  {e.contract.symbol:8s} {e.side:5s} "
                  f"{e.shares:>7.0f} {e.price:>10.4f} {comm:>8.2f} "
                  f"{pnl if pnl else 0.0:>10.2f}")
        print(f"\n  {len(fills)} fills, realized P/L {realized:>,.2f}")


async def main_async(port: int, watch: bool) -> int:
    if port in LIVE_PORTS:
        print(f"REFUSING: port {port} is {LIVE_PORTS[port]}. Paper only.")
        return 1
    if port not in PAPER_PORTS:
        print(f"REFUSING: port {port} is not a known paper port "
              f"({sorted(PAPER_PORTS)}).")
        return 1

    ib = IB()
    try:
        await ib.connectAsync(HOST, port, clientId=VIEWER_CLIENT_ID, timeout=10)
    except Exception as exc:
        print(f"Could not connect to {HOST}:{port} — {type(exc).__name__}: {exc}")
        print("Is IB Gateway running and logged in?")
        return 1

    accounts = ib.managedAccounts()
    if not accounts or not all(a.startswith("DU") for a in accounts):
        print(f"REFUSING: accounts {accounts} are not paper (expect 'DU' prefix).")
        ib.disconnect()
        return 1
    print(f"connected on port {port} ({PAPER_PORTS[port]}), account {accounts}")

    try:
        while True:
            await snapshot(ib)
            if not watch:
                break
            await asyncio.sleep(30)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        ib.disconnect()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only IBKR paper account view")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--watch", action="store_true",
                    help="refresh every 30 seconds until Ctrl-C")
    a = ap.parse_args()
    try:
        return asyncio.run(main_async(a.port, a.watch))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
