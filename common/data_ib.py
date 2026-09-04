#!/usr/bin/env python3
"""
Full-session 1-minute bars from IB, cached to disk, for the EMA Crossover
strategy family (E15, VW9).

Adapted from common/backtest.py's Runner class -- same
qualify/pace/checkpoint pattern -- but pulling a DIFFERENT window. V7's
puller ends at 09:30 ET because V7 only trades pre-market. E15 and VW9 both
trade the full 04:00-20:00 ET session (ema15_full_day_strategy_spec.md,
vw9_strategy_spec.md), so this one ends at 20:00 ET and requests the whole
extended-hours day.

    .\\.venv\\Scripts\\python.exe -m common.data_ib --probe
    .\\.venv\\Scripts\\python.exe -m common.data_ib

Read-only: requests history and places no orders. Paper port by default.

CACHING
-------
Every pair's bars are written once to bars_cache/<SYMBOL>_<DATE>.csv and never
refetched (a checkpoint entry in data_pull_state.json marks it done). This
matters more here than it did for mcl_backtest.py, because vw9_setup_counts.py
needs to run repeatedly while parameters are tuned (§8.3, then §8.4, then
calibration) -- re-pulling 407 pairs from IB every time a threshold changes
would be both slow (IB's ~60-requests-per-10-minutes cap) and pointless, since
the bars themselves never change.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from ib_async import IB, Stock, util
except ImportError:
    sys.exit("ib_async not installed.  pip install ib_async pandas")

from common.cache_io import cache_path, load_cached_bars, load_pairs

ET = ZoneInfo("America/New_York")
PAPER_PORTS = {4002: "IB Gateway paper", 7497: "TWS paper"}
LIVE_PORTS = {4001: "IB Gateway LIVE", 7496: "TWS LIVE"}

# Same pacing as mcl_backtest.py -- IB's cap is account-wide, so running this
# alongside the live trader or the V7 backtest will contend for the same
# budget. Don't.
REQUEST_INTERVAL_S = 12.5
RETRY_BACKOFF_S = 20.0
QUALIFY_INTERVAL_S = 2.0
QUALIFY_COOLDOWN_S = 60.0
QUALIFY_FAIL_STREAK = 5

PRIMARIES = ["NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"]

SESSION_END_HOUR, SESSION_END_MINUTE = 20, 0  # 20:00 ET -- the full VW9/E15 session

LOG = logging.getLogger("data_ib")


class BarSource:
    def __init__(self, ib: IB, cache_dir: Path):
        self.ib = ib
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.contracts: dict[str, object] = {}
        self.unqualified: set[str] = set()
        self.state_path = cache_dir / "data_pull_state.json"
        self.state = self._load_state()
        self._last_req = 0.0
        self._last_qual = 0.0
        self._qual_fails = 0

    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except json.JSONDecodeError:
                LOG.warning("state file unreadable -- starting fresh")
        return {"done": {}}

    def _save_state(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        tmp.replace(self.state_path)

    def _cache_path(self, symbol: str, date_str: str) -> Path:
        return cache_path(self.cache_dir, symbol, date_str)

    async def _pace(self) -> None:
        wait = REQUEST_INTERVAL_S - (time.monotonic() - self._last_req)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_req = time.monotonic()

    async def _pace_qualify(self) -> None:
        wait = QUALIFY_INTERVAL_S - (time.monotonic() - self._last_qual)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_qual = time.monotonic()

    async def _try_qualify(self, contract):
        await self._pace_qualify()
        try:
            got = await self.ib.qualifyContractsAsync(contract)
        except Exception:
            return None
        return got[0] if got else None

    async def qualify(self, symbol: str):
        """Identical logic to mcl_backtest.Runner.qualify -- see there for
        why the fail-streak cooldown exists (IB throttling looks exactly
        like a delisted symbol per-call; only a STREAK distinguishes them)."""
        if symbol in self.contracts:
            return self.contracts[symbol]
        if symbol in self.unqualified:
            return None

        got = await self._try_qualify(Stock(symbol, "SMART", "USD"))
        if got is None:
            for primary in PRIMARIES:
                got = await self._try_qualify(
                    Stock(symbol, "SMART", "USD", primaryExchange=primary))
                if got is not None:
                    break

        if got is not None:
            self.contracts[symbol] = got
            self._qual_fails = 0
            return got

        self._qual_fails += 1
        if self._qual_fails >= QUALIFY_FAIL_STREAK:
            LOG.warning("%d consecutive qualification failures -- likely IB "
                        "throttling. Cooling off %.0fs.",
                        self._qual_fails, QUALIFY_COOLDOWN_S)
            await asyncio.sleep(QUALIFY_COOLDOWN_S)
            self._qual_fails = 0
            got = await self._try_qualify(Stock(symbol, "SMART", "USD"))
            if got is not None:
                self.contracts[symbol] = got
                LOG.info("  %s qualified after cooldown -- it WAS throttling", symbol)
                return got

        self.unqualified.add(symbol)
        return None

    async def bars_for_session(self, contract, date_str: str):
        """Full 1-minute bars for the extended-hours day ending 20:00 ET on
        date_str. Unlike mcl_backtest's 09:30-ending, 2-day pull, this needs
        no prior-day warm-up: both E15 and VW9 explicitly do NOT seed
        indicators from the prior session (E15 §0: 'Default: no seeding.
        EMAs start from the first bar of the session'; VW9 has no equivalent
        section because its faster EMA9 + VWAP don't need one). So '1 D' is
        enough, and pulling less means less IB request budget spent per pair.

        Retries once on an empty response, exactly as mcl_backtest.py does --
        IB returns an empty list on throttling, not an error, so one empty
        result is not proof the data doesn't exist.
        """
        end = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=SESSION_END_HOUR, minute=SESSION_END_MINUTE, tzinfo=ET)
        last_err = "no data returned"
        for attempt in (1, 2):
            await self._pace()
            try:
                data = await self.ib.reqHistoricalDataAsync(
                    contract, endDateTime=end, durationStr="1 D",
                    barSizeSetting="1 min", whatToShow="TRADES",
                    useRTH=False, formatDate=2)
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {str(e)[:90]}"
                data = None
            if data:
                df = util.df(data)
                if df is not None and not df.empty:
                    df = df.rename(columns=str.lower)
                    df["date"] = pd.to_datetime(df["date"], utc=True)
                    return df.set_index("date").sort_index(), None
                last_err = "empty frame"
            if attempt == 1:
                LOG.debug("  %s %s empty, backing off then retrying",
                          contract.symbol, date_str)
                await asyncio.sleep(RETRY_BACKOFF_S)
        return None, last_err

    async def fetch_all(self, pairs: list[dict], probe_only: bool = False) -> None:
        total = len(pairs)
        for n, p in enumerate(pairs, 1):
            key = f"{p['symbol']}|{p['date']}"
            if key in self.state["done"]:
                continue

            contract = await self.qualify(p["symbol"])
            if contract is None:
                self.state["done"][key] = {"status": "NOT_QUALIFIED", "bars": 0}
                LOG.warning("[%d/%d] %-6s %s  could not qualify",
                            n, total, p["symbol"], p["date"])
                self._save_state()
                continue

            if probe_only:
                self.state["done"][key] = {"status": "PROBE_SKIPPED", "bars": 0}
                self._save_state()
                continue

            df, err = await self.bars_for_session(contract, p["date"])
            if df is None:
                self.state["done"][key] = {"status": "NO_DATA", "reason": err, "bars": 0}
                LOG.warning("[%d/%d] %-6s %s  no bars (%s)",
                            n, total, p["symbol"], p["date"], err)
                self._save_state()
                continue

            df.to_csv(self._cache_path(p["symbol"], p["date"]))
            self.state["done"][key] = {"status": "OK", "bars": len(df)}
            LOG.info("[%d/%d] %-6s %s  bars=%d", n, total, p["symbol"], p["date"], len(df))
            self._save_state()

    def load_cached(self, symbol: str, date_str: str) -> pd.DataFrame | None:
        """Read back a previously-fetched pair's 1-minute bars. Returns None
        if it was never fetched OK (check self.state['done'] for why)."""
        return load_cached_bars(self.cache_dir, symbol, date_str)


async def main_async(args) -> int:
    if args.port in LIVE_PORTS:
        print(f"REFUSING: port {args.port} is {LIVE_PORTS[args.port]}.")
        return 1

    pairs_path = Path(args.pairs)
    if not pairs_path.exists():
        print(f"{pairs_path} not found")
        return 1
    pairs = load_pairs(pairs_path)
    if args.limit:
        pairs = pairs[: args.limit]
    print(f"{len(pairs)} symbol/date pairs to process\n")

    ib = IB()
    try:
        await ib.connectAsync("127.0.0.1", args.port, clientId=args.client_id, timeout=15)
    except Exception as e:  # noqa: BLE001
        print(f"could not connect to 127.0.0.1:{args.port} -- {e}")
        print("Is IB Gateway running and logged in?")
        return 1
    LOG.info("connected, accounts %s", ib.managedAccounts())

    src = BarSource(ib, Path(args.out_dir))
    try:
        await src.fetch_all(pairs, probe_only=args.probe)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\ninterrupted -- progress saved, rerun to resume")
    finally:
        done = src.state["done"]
        ok = sum(1 for v in done.values() if v["status"] == "OK")
        print(f"\n  pairs attempted   {len(done)}")
        print(f"  bars cached OK    {ok}")
        print(f"  not qualified     {sum(1 for v in done.values() if v['status']=='NOT_QUALIFIED')}")
        print(f"  no data           {sum(1 for v in done.values() if v['status']=='NO_DATA')}")
        ib.disconnect()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Pull full-session 1-minute bars for E15/VW9")
    p.add_argument("--pairs", default="var/state/traded_pairs.json",
                   help="reuse the same 407 pairs as MCL, per both specs' §1")
    p.add_argument("--out-dir", default="bars_cache")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=34)
    p.add_argument("--probe", action="store_true",
                   help="qualify contracts only; fetch no bars")
    p.add_argument("--limit", type=int, help="process only the first N pairs")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
