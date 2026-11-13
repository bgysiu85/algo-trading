#!/usr/bin/env python3
"""IBKR shortability probe for the NAS (W05-0022 part 2, hosted by W10-0022). READ-ONLY: it opens a read-only API session
on the paper Gateway's own network and asks for market data on a list of symbols. It cannot place, preview or cancel an
order (no order call exists in this file; the session is opened readonly=True), and it refuses live ports.

For each symbol it records what IBKR sends for generic tick 236 (shortable shares): the "shortable" level (tick 46:
>2.5 = easy to borrow, >1.5 = may be available, otherwise not) and the number of shortable shares (tick 89), plus the
last price. A borrow FEE RATE is not a documented API tick; NOT verified that IBKR sends one for this login. So the output
also lists every tick type that arrived for the symbol ("ticks") - if a fee-like value exists, it shows up there.

Run (inside the Gateway's network; NAS-TRADER-SETUP.md part 9 has the exact command):
    python /extras/borrow_probe.py --symbols-file /out/gappers.txt
Output: one JSON line per symbol appended to  <out-dir>/borrow_probe.jsonl . Client id 96 (see client_ids.py).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PAPER_PORTS = {4002, 7497}
LIVE_PORTS = {4001, 4003, 7496, 7498}
CLIENT_ID = 96
MAX_SYMBOLS = 50                   # IBKR's default is 100 market-data lines; stay well under it


class Refused(Exception):
    pass


def read_symbols(args_symbols: str | None, symbols_file: str | None) -> list[str]:
    raw: list[str] = []
    if args_symbols:
        raw += args_symbols.replace(",", " ").split()
    if symbols_file:
        raw += Path(symbols_file).read_text(encoding="utf-8").replace(",", " ").split()
    out: list[str] = []
    for s in raw:
        s = s.strip().upper()
        if s and s not in out:
            out.append(s)
    if not out:
        raise Refused("no symbols: pass --symbols AAA,BBB or --symbols-file FILE")
    if len(out) > MAX_SYMBOLS:
        raise Refused(f"{len(out)} symbols; the limit is {MAX_SYMBOLS} per run (market-data line limit). Split the list.")
    return out


def check_port(port: int) -> None:
    if port in LIVE_PORTS:
        raise Refused(f"port {port} is a LIVE port. Refused. Paper only: {sorted(PAPER_PORTS)}.")
    if port not in PAPER_PORTS:
        raise Refused(f"port {port} is not a paper port {sorted(PAPER_PORTS)}.")


def _num(x):
    """A float, or None for None / NaN (ib_async uses NaN for 'no tick yet')."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def shortable_label(level) -> str:
    v = _num(level)
    if v is None:
        return "unknown"
    if v > 2.5:
        return "easy"
    if v > 1.5:
        return "available"
    return "not shortable"


def _log_ticks(tick_log: dict, ticks) -> None:
    """Fold one batch of ticks into {tickType: {count, first, last}} so a rare tick is not lost when the next batch replaces it
    (ib_async's ticker.ticks holds only the latest batch). first / last are [price, size]."""
    for t in ticks or []:
        k = str(int(getattr(t, "tickType", -1)))
        pair = [_num(getattr(t, "price", None)), _num(getattr(t, "size", None))]
        e = tick_log.setdefault(k, {"count": 0, "first": pair, "last": pair})
        e["count"] += 1
        e["last"] = pair


def probe_symbol(ib, symbol: str, wait_s: float, sleep=time.sleep, capture_s: float = 0.0) -> dict:
    from ib_async import Stock
    row = {"symbol": symbol, "shortable": None, "shortable_label": "unknown", "shortable_shares": None,
           "last": None, "ticks": []}
    contract = Stock(symbol, "SMART", "USD")
    if not ib.qualifyContracts(contract):
        row["error"] = "did not qualify"
        return row
    ticker = ib.reqMktData(contract, genericTickList="236", snapshot=False, regulatorySnapshot=False)
    tick_log: dict = {}
    on_update = None
    if capture_s > 0 and hasattr(ticker, "updateEvent"):
        def on_update(tk, _log=tick_log):                          # called for every batch while subscribed
            _log_ticks(_log, getattr(tk, "ticks", None))
        ticker.updateEvent += on_update
    try:
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            ib.sleep(0.25)
            if _num(getattr(ticker, "shortableShares", None)) is not None and _num(getattr(ticker, "shortable", None)) is not None:
                break
        level = _num(getattr(ticker, "shortable", None))
        row["shortable"] = level
        row["shortable_label"] = shortable_label(level)
        row["shortable_shares"] = _num(getattr(ticker, "shortableShares", None))
        row["last"] = _num(getattr(ticker, "last", None))
        if capture_s > 0:                                         # keep listening: the rest of the wait is the capture
            end = time.monotonic() + capture_s
            while time.monotonic() < end:
                ib.sleep(0.25)
            _log_ticks(tick_log, getattr(ticker, "ticks", None))
            row["capture_s"] = capture_s
            row["tick_log"] = dict(sorted(tick_log.items(), key=lambda kv: int(kv[0])))
        row["ticks"] = sorted({int(getattr(t, "tickType", -1)) for t in (getattr(ticker, "ticks", None) or [])}
                              | {int(k) for k in tick_log})
    finally:
        if on_update is not None:
            try:
                ticker.updateEvent -= on_update
            except Exception:                                      # noqa: BLE001
                pass
        ib.cancelMktData(contract)
    return row


def run(symbols: list[str], host: str, port: int, out_dir: Path, wait_s: float, ib_factory=None, now=None,
        capture_s: float = 0.0) -> list[dict]:
    check_port(port)
    if ib_factory is None:                                         # pragma: no cover - environment
        from ib_async import IB
        ib_factory = IB
    ib = ib_factory()
    ib.connect(host, port, clientId=CLIENT_ID, timeout=15, readonly=True)
    try:
        accounts = list(ib.managedAccounts())
        if not accounts or any(not a.upper().startswith("D") for a in accounts):
            raise Refused(f"accounts {accounts} are not all paper accounts (ids start with D). Stopping.")
        stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = []
        for s in symbols:
            try:
                row = probe_symbol(ib, s, wait_s, capture_s=capture_s)
            except Exception as e:                                 # noqa: BLE001 - broker errors vary
                row = {"symbol": s, "error": f"{type(e).__name__}: {e}"}
            row["at"] = stamp
            rows.append(row)
    finally:
        try:
            ib.disconnect()
        except Exception:                                          # noqa: BLE001
            pass
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "borrow_probe.jsonl", "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return rows


def main(argv=None, ib_factory=None, out=print) -> int:
    ap = argparse.ArgumentParser(description="Read-only IBKR shortability probe (W05-0022). Paper ports only.")
    ap.add_argument("--symbols", help="comma or space separated")
    ap.add_argument("--symbols-file")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--out-dir", default=os.environ.get("BORROW_OUT_DIR", "/out"))
    ap.add_argument("--wait", type=float, default=6.0, help="seconds to wait for the shortable ticks per symbol")
    ap.add_argument("--capture", type=float, default=0.0,
                    help="seconds to keep listening per symbol after the shortable ticks arrive; every tick type seen is "
                         "counted in tick_log (to find out whether IBKR sends a borrow fee rate). 0 = off. Max 120.")
    a = ap.parse_args(argv)
    try:
        if not 0 <= a.capture <= 120:
            raise Refused(f"--capture {a.capture}: use 0-120 seconds per symbol")
        symbols = read_symbols(a.symbols, a.symbols_file)
        if a.capture and len(symbols) * (a.capture + a.wait) > 900:
            raise Refused(f"{len(symbols)} symbols x ({a.capture:g}+{a.wait:g}) s is over 15 minutes; use fewer symbols or a shorter --capture")
        rows = run(symbols, a.host, a.port, Path(a.out_dir), a.wait, ib_factory=ib_factory, capture_s=a.capture)
    except Refused as e:
        out(f"REFUSED: {e}")
        return 1
    for r in rows:
        out(f"{r['symbol']:<8} {r.get('shortable_label', r.get('error', '?')):<14} shares={r.get('shortable_shares')} last={r.get('last')}")
    out(f"DONE {len(rows)} symbols appended to {Path(a.out_dir) / 'borrow_probe.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
