"""Daily bars from IBKR (read-only API connection, paper ports only).

Needs IB Gateway (4002) or TWS (7497) paper running and logged in, with API
access enabled. Uses its own client id (config: 91) so it cannot collide with
the trader (17), the viewer (77), the scanner (55) or the params dump (88).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

LOG = logging.getLogger("desk.fetch_bars")

PAPER_PORTS = {4002: "IB Gateway paper", 7497: "TWS paper"}
LIVE_PORTS = {4001: "IB Gateway LIVE", 7496: "TWS LIVE"}
PRIMARIES = ["NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"]


class BarFetchError(RuntimeError):
    pass


def bars_to_df(bars) -> pd.DataFrame:
    """ib_async BarData objects (or anything with the same attributes) -> frame."""
    rows = [{"date": b.date, "open": b.open, "high": b.high, "low": b.low,
             "close": b.close, "volume": b.volume} for b in bars]
    if not rows:
        raise BarFetchError("IBKR returned no bars")
    return pd.DataFrame(rows)


def load_csv(path: str | Path) -> pd.DataFrame:
    """Offline route: a CSV with date,open,high,low,close,volume. Used for
    tests and for running the desk when the Gateway is not up."""
    return pd.read_csv(path, encoding="utf-8")


def _qualify(ib, symbol: str, make_stock):
    """SMART first; if IBKR cannot pick one listing, try each primary exchange.
    Returns a qualified contract or raises BarFetchError."""
    tried = []
    for primary in [None] + PRIMARIES:
        c = make_stock(symbol, "SMART", "USD", primaryExchange=primary) if primary else \
            make_stock(symbol, "SMART", "USD")
        try:
            got = ib.qualifyContracts(c)
        except Exception as e:                     # noqa: BLE001 - broker errors vary
            tried.append(f"{primary or 'SMART'}: {e}")
            continue
        if got and getattr(got[0], "conId", 0):
            return got[0]
        tried.append(f"{primary or 'SMART'}: not qualified")
    raise BarFetchError(f"could not qualify {symbol} ({'; '.join(tried)})")


def fetch_daily_bars(symbol: str, host: str = "127.0.0.1", port: int = 4002,
                     client_id: int = 91, duration: str = "2 Y", timeout: float = 15.0,
                     _ib=None, _stock=None) -> pd.DataFrame:
    """One historical-data request. `_ib` / `_stock` are for tests."""
    if port in LIVE_PORTS:
        raise BarFetchError(f"port {port} is {LIVE_PORTS[port]}; the desk uses paper ports only")
    if port not in PAPER_PORTS:
        raise BarFetchError(f"port {port} is not a known paper port {sorted(PAPER_PORTS)}")

    if _ib is None:
        try:
            from ib_async import IB, Stock
        except ImportError as e:
            raise BarFetchError("ib_async is not installed in this Python") from e
        ib, make_stock = IB(), Stock
    else:
        ib, make_stock = _ib, _stock

    try:
        try:
            ib.connect(host, port, clientId=client_id, timeout=timeout, readonly=True)
        except Exception as e:                      # noqa: BLE001
            raise BarFetchError(
                f"cannot connect to {host}:{port} ({PAPER_PORTS[port]}): {e}. "
                "Is the Gateway/TWS running, logged in to PAPER, with API enabled?") from e
        contract = _qualify(ib, symbol, make_stock)
        bars = ib.reqHistoricalData(contract, endDateTime="", durationStr=duration,
                                    barSizeSetting="1 day", whatToShow="TRADES",
                                    useRTH=True, formatDate=1)
        return bars_to_df(bars)
    finally:
        try:
            ib.disconnect()
        except Exception:                           # noqa: BLE001
            pass
