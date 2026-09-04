#!/usr/bin/env python3
"""
MCL offline backtest over the symbol/date pairs actually traded.

    .\\.venv\\Scripts\\python.exe mcl_backtest.py --probe     # coverage only
    .\\.venv\\Scripts\\python.exe mcl_backtest.py             # full backtest

Reads traded_pairs.json (symbol + date), pulls 1-minute bars for each from IB,
and runs the V7 strategy offline. TradingView cannot do this: its 1-minute chart
history reaches only ~5 weeks, which excludes every one of these dates.

WHY THIS MATTERS
----------------
These names were picked in real time by a live trading process, not chosen with
hindsight because they ran. That is the fix for the selection bias in every
backtest so far.

PACING
------
IB allows roughly 60 historical-data requests per 10 minutes. This throttles to
one request per REQUEST_INTERVAL_S and CHECKPOINTS after every pair, so a run
can be interrupted and resumed without refetching. Expect ~75 minutes for 431
pairs. Ctrl-C is safe.

Read-only: requests history and places no orders. Paper port by default, though
market data is identical either way.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from ib_async import IB, Stock, util
except ImportError:
    sys.exit("ib_async not installed.  pip install ib_async pandas")

import importlib

from common import session_lock
from common.cache_io import (cache_path as _cache_path, check_sessions,
                             slice_sessions, window_dir,
                             SHARED_DURATION, SHARED_END_HHMM, SHARED_SESSIONS)

# Both expose backtest_session(df, session_date, tz) and accept the same
# 1-minute frame -- MC5 resamples internally, so the engine does not need to
# know the bar size a strategy trades on.
STRATEGY_MODULES = {
    "mcl": "strategy.mcl.mcl",
    "mc5": "strategy.mc5.mc5",
}

ET = ZoneInfo("America/New_York")
PAPER_PORTS = {4002: "IB Gateway paper", 7497: "TWS paper"}
LIVE_PORTS = {4001: "IB Gateway LIVE", 7496: "TWS LIVE"}

# IB allows ~60 historical requests per 10 minutes. Contract qualification also
# consumes requests, and an unknown symbol costs up to 5 (one per exchange
# tried), so leave headroom rather than sitting on the cap.
REQUEST_INTERVAL_S = 12.5     # ~48 historical requests / 10 min
RETRY_BACKOFF_S = 20.0        # extra pause before retrying an empty response

# Contract qualification is ALSO a paced IB request, and the 2026-09-03 run
# proved it the expensive way: qualify() ran unthrottled, so 302 symbols x up
# to 5 exchanges was up to ~1500 requests fired as fast as the loop could go.
# IB started refusing after roughly 47 symbols -- alphabetically ABOS..CAMP --
# and every symbol after that was recorded NOT_QUALIFIED. 337 of 407 pairs
# were lost to this, not to missing data.
#
# IB answers a refused qualification with an empty list, exactly as it does
# for a genuinely unknown symbol, so the two are indistinguishable per call.
# The only defences are to pace, and to treat a STREAK of failures as evidence.
QUALIFY_INTERVAL_S = 2.0      # ~30 qualification requests / minute
QUALIFY_COOLDOWN_S = 60.0     # pause after a suspicious run of failures
QUALIFY_FAIL_STREAK = 5       # consecutive failures that trigger the cooldown

PRIMARIES = ["NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"]

# Bars are cached to disk after the first fetch, and a cache hit costs no IB
# request and no pacing wait.
#
# The reason this matters: every strategy variant we want to compare needs the
# SAME bars -- apex on/off, MACD > 0 on/off, intrabar vs bar-close entry, MC5
# against MCL. Without a cache each of those is another ~85-minute paced pass
# that also cannot overlap a live session. With one, the first pass pays for
# the data and every comparison afterwards runs offline in seconds.
#
# csv.gz rather than parquet on purpose: pandas reads and writes it with no
# extra dependency, so nothing new has to be installed in the venv.
CACHE_ROOT = Path("bar_cache")

# The window this engine pulls, in ONE place: the same two values build the IB
# request and the cache directory name, so the cache cannot claim to hold bars
# it does not hold. "2 D" gives the session plus the prior day, which covers
# the 60-bar warm-up the volume average and MACD both need.
# What this engine NEEDS: two trading sessions ending 09:30 -- the session
# plus the prior day, covering the 60-bar warm-up the volume average and MACD
# both need.
HIST_SESSIONS = 2
HIST_END_HOUR, HIST_END_MINUTE = 9, 30

# What it FETCHES: the shared superset, so one pull serves this engine and
# data_ib.py's full-session window instead of two. Validated against the live
# API on 2026-09-04 -- see common/probe_window.py. Bars are sliced back to
# HIST_SESSIONS before any strategy sees them, because a longer frame changes
# EMA-seeded indicators on identical bars.
HIST_DURATION = SHARED_DURATION

LOG = logging.getLogger("bt")


def load_pairs(path: Path) -> list[dict]:
    pairs = json.loads(path.read_text())
    out = []
    for p in pairs:
        sym = str(p["symbol"]).upper().strip()
        # forex and anything with a dot is not a US equity
        if "." in sym or not sym.isalpha():
            continue
        out.append({"symbol": sym, "date": p["date"]})
    return out


class Runner:
    def __init__(self, ib: IB, out_dir: Path, cache_dir: Path | None = None,
                 state_dir: Path | None = None, strategy: str = "mcl"):
        self.ib = ib
        self.strategy = strategy
        # The strategy module supplies SESSION_START/SESSION_END and
        # backtest_session(); nothing else about it is known here.
        self.S = importlib.import_module(STRATEGY_MODULES[strategy])
        self.out_dir = out_dir
        # The resumable checkpoint and the trade report are different kinds
        # of thing and now live in different var/ subdirectories, so they no
        # longer share one --out-dir. Both are gitignored and therefore
        # absent on a fresh clone; create them rather than assume.
        self.state_dir = state_dir or out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.contracts: dict[str, object] = {}
        self.unqualified: set[str] = set()
        self.state_path = self.state_dir / f"backtest_state_{strategy}.json"
        self.state = self._load_state()
        self._last_req = 0.0
        self._last_qual = 0.0
        self._qual_fails = 0
        # The SHARED superset window, so data_ib.py reads the same files.
        self.cache_dir = window_dir(cache_dir or CACHE_ROOT,
                                    SHARED_DURATION, SHARED_END_HHMM)
        self.cache_hits = 0
        self.cache_misses = 0

    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except json.JSONDecodeError:
                LOG.warning("state file unreadable -- starting fresh")
        return {"done": {}, "trades": []}

    def _save_state(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        tmp.replace(self.state_path)

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
        """Resolve a symbol to a contract, paced, with throttle detection.

        Plain SMART is tried FIRST and resolves most US equities in a single
        request. The per-exchange fallbacks run only when that fails, so a
        typical symbol now costs 1 request instead of up to 5.
        """
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

        # A delisted symbol looks identical to a throttled one, so treat a
        # STREAK as evidence of throttling: cool off, then give this symbol
        # one more chance before condemning it.
        self._qual_fails += 1
        if self._qual_fails >= QUALIFY_FAIL_STREAK:
            LOG.warning("%d consecutive qualification failures -- likely IB "
                        "throttling, not missing symbols. Cooling off %.0fs.",
                        self._qual_fails, QUALIFY_COOLDOWN_S)
            await asyncio.sleep(QUALIFY_COOLDOWN_S)
            self._qual_fails = 0
            got = await self._try_qualify(Stock(symbol, "SMART", "USD"))
            if got is not None:
                self.contracts[symbol] = got
                LOG.info("  %s qualified after cooldown -- it WAS throttling",
                         symbol)
                return got

        self.unqualified.add(symbol)
        return None

    def _cache_path(self, symbol: str, date_str: str) -> Path:
        return _cache_path(self.cache_dir, symbol, date_str)

    def _cache_read(self, symbol: str, date_str: str):
        path = self._cache_path(symbol, date_str)
        if not path.exists():
            return None
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=[0])
        except Exception as e:  # noqa: BLE001
            LOG.warning("cache unreadable for %s %s (%s) -- refetching",
                        symbol, date_str, type(e).__name__)
            return None
        if df.empty:
            return None
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        return df.sort_index()

    def _cache_write(self, symbol: str, date_str: str, df) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(self._cache_path(symbol, date_str))
        except Exception as e:  # noqa: BLE001
            LOG.warning("could not cache %s %s: %s", symbol, date_str, e)

    def _slice(self, frame, want_end, symbol: str, date_str: str):
        """Cut the superset down to this engine's window, loudly.

        A superset that does not reach back far enough would quietly hand the
        strategy less warm-up than it asked for. Counting sessions turns that
        into a visible warning and a NO_DATA rather than a wrong backtest.
        """
        have = check_sessions(frame, want_end, HIST_SESSIONS)
        if have < HIST_SESSIONS:
            LOG.warning("%s %s cached frame holds %d session(s), need %d -- "
                        "treating as missing rather than under-seeding the "
                        "strategy", symbol, date_str, have, HIST_SESSIONS)
            return None
        return slice_sessions(frame, want_end, HIST_SESSIONS)

    async def bars_for(self, contract, date_str: str):
        """1-minute bars for the two sessions ending 09:30 ET on the target date.

        Fetches the shared superset window and slices it, so this engine and
        data_ib.py share one pull instead of making two.

        Retries once on an empty response. IB returns an empty list rather than
        an error when it throttles, so a single empty result is NOT evidence
        that the data does not exist -- and the probe showed the same symbol
        succeeding on one date and returning nothing on the adjacent one, which
        is the signature of pacing rather than missing history.
        """
        # The cache holds the SHARED superset; slice it to this engine's own
        # window before returning, or the strategy gets extra warm-up and its
        # indicators move on identical bars.
        want_end = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=HIST_END_HOUR, minute=HIST_END_MINUTE, tzinfo=ET)
        cached = self._cache_read(contract.symbol, date_str)
        if cached is not None:
            sliced = self._slice(cached, want_end, contract.symbol, date_str)
            if sliced is not None:
                self.cache_hits += 1
                return sliced, None

        end = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=int(SHARED_END_HHMM[:2]), minute=int(SHARED_END_HHMM[2:]), tzinfo=ET)
        last_err = "no data returned"
        for attempt in (1, 2):
            await self._pace()
            try:
                data = await self.ib.reqHistoricalDataAsync(
                    contract, endDateTime=end, durationStr=HIST_DURATION,
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
                    out = df.set_index("date").sort_index()
                    self._cache_write(contract.symbol, date_str, out)
                    self.cache_misses += 1
                    return self._slice(out, want_end, contract.symbol,
                                       date_str), None
                last_err = "empty frame"
            if attempt == 1:
                LOG.debug("  %s %s empty, backing off then retrying",
                          contract.symbol, date_str)
                await asyncio.sleep(RETRY_BACKOFF_S)
        return None, last_err

    async def run(self, pairs: list[dict], probe_only: bool) -> None:
        total = len(pairs)
        for n, p in enumerate(pairs, 1):
            key = f"{p['symbol']}|{p['date']}"
            if key in self.state["done"]:
                continue

            contract = await self.qualify(p["symbol"])
            if contract is None:
                self.state["done"][key] = {"status": "NOT_QUALIFIED", "bars": 0,
                                           "session_bars": 0, "trades": 0}
                LOG.warning("[%d/%d] %-6s %s  could not qualify",
                            n, total, p["symbol"], p["date"])
                self._save_state()
                continue

            df, err = await self.bars_for(contract, p["date"])
            if df is None:
                self.state["done"][key] = {"status": "NO_DATA", "reason": err,
                                           "bars": 0, "session_bars": 0, "trades": 0}
                LOG.warning("[%d/%d] %-6s %s  no bars (%s)",
                            n, total, p["symbol"], p["date"], err)
                self._save_state()
                continue

            local = df.index.tz_convert(ET)
            target = datetime.strptime(p["date"], "%Y-%m-%d").date()
            sess = int(((local.date == target)
                        & (local.time >= self.S.SESSION_START)
                        & (local.time < self.S.SESSION_END)).sum())

            rec = {"status": "OK", "bars": len(df), "session_bars": sess,
                   "trades": 0, "net": 0.0}

            if not probe_only and sess > 0:
                trades = self.S.backtest_session(df, target, ET)
                for t in trades:
                    d = asdict(t)
                    d["symbol"] = p["symbol"]
                    self.state["trades"].append(d)
                rec["trades"] = len(trades)
                rec["net"] = round(sum(t.net for t in trades), 2)

            self.state["done"][key] = rec
            LOG.info("[%d/%d] %-6s %s  bars=%-5d session=%-4d trades=%-2d net=%+.2f",
                     n, total, p["symbol"], p["date"], rec["bars"], sess,
                     rec["trades"], rec.get("net", 0.0))
            self._save_state()

    def report(self, probe_only: bool) -> None:
        done = self.state["done"]
        ok = [v for v in done.values() if v["status"] == "OK"]
        with_sess = [v for v in ok if v["session_bars"] > 0]
        print("\n" + "=" * 66)
        print(f"  pairs attempted        {len(done)}")
        nq = sum(1 for v in done.values() if v["status"] == "NOT_QUALIFIED")
        print(f"  contract not qualified {nq}")
        if done and nq / len(done) > 0.25:
            print(f"    ^^ {nq / len(done) * 100:.0f}% failed to qualify -- that is")
            print("       almost certainly IB throttling, not delisted symbols.")
            print("       Rerun with --retry-failed.")
        print(f"  no bars returned       {sum(1 for v in done.values() if v['status']=='NO_DATA')}")
        print(f"  bars OK                {len(ok)}")
        print(f"  bars from cache        {self.cache_hits}  (fetched {self.cache_misses})")
        print(f"  with pre-market bars   {len(with_sess)}")
        if probe_only:
            print("\n  (probe only -- no backtest run)")
            print("=" * 66)
            return

        tr = self.state["trades"]
        if not tr:
            print("\n  NO TRADES across every pair with data.")
            print("=" * 66)
            return
        net = sum(t["net"] for t in tr)
        wins = sum(1 for t in tr if t["net"] > 0)
        per_sym: dict[str, float] = {}
        for t in tr:
            per_sym[t["symbol"]] = per_sym.get(t["symbol"], 0.0) + t["net"]
        top = sorted(per_sym.items(), key=lambda kv: -kv[1])

        print(f"\n  TRADES {len(tr)}   NET {net:+,.2f}   WIN {wins/len(tr)*100:.1f}%"
              f"   {net/len(tr):+.2f}/trade")
        print(f"  symbols with trades    {len(per_sym)}  "
              f"({sum(1 for v in per_sym.values() if v>0)} profitable)")
        print("\n  concentration:")
        for n in (1, 3, 5):
            print(f"    drop top {n:<2} -> {net - sum(v for _, v in top[:n]):+,.2f}")
        print("\n  best / worst symbols:")
        for s, v in top[:5]:
            print(f"    {s:6} {v:+9.2f}")
        print("    ...")
        for s, v in top[-5:]:
            print(f"    {s:6} {v:+9.2f}")
        print("=" * 66)

        out = self.out_dir / f"backtest_trades_{self.strategy}.csv"
        pd.DataFrame(tr).to_csv(out, index=False)
        print(f"\n  trades written to {out}")


async def main_async(args) -> int:
    live = None if args.force else session_lock.active()
    if live:
        print("REFUSING: " + session_lock.describe(live))
        print("  IB's ~60-requests-per-10-minutes cap is account-wide, so this")
        print("  backtest would throttle that session -- and IB signals")
        print("  throttling with empty results, not errors, so both sides")
        print("  would fail silently. Wait for it to finish, or pass --force.")
        return 1

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
        await ib.connectAsync("127.0.0.1", args.port, clientId=args.client_id,
                              timeout=15)
    except Exception as e:  # noqa: BLE001
        print(f"could not connect to 127.0.0.1:{args.port} -- {e}")
        print("Is IB Gateway running and logged in?")
        return 1
    LOG.info("connected, accounts %s", ib.managedAccounts())

    runner = Runner(ib, Path(args.out_dir), Path(args.cache_dir),
                    Path(args.state_dir), args.strategy)
    if args.retry_failed:
        # NOT_QUALIFIED is included deliberately. On 2026-09-03 it was the
        # dominant failure (337 of 407) and it was caused by throttling, not
        # by delisted symbols -- so it is exactly what needs re-attempting.
        retry_statuses = ("NO_DATA", "NOT_QUALIFIED")
        stale = [k for k, v in runner.state["done"].items()
                 if v["status"] in retry_statuses]
        for k in stale:
            del runner.state["done"][k]
        print("cleared %d failed entries (%s) for retry\n"
              % (len(stale), " + ".join(retry_statuses)))
        runner._save_state()
    try:
        await runner.run(pairs, args.probe)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\ninterrupted -- progress saved, rerun to resume")
    finally:
        runner.report(args.probe)
        ib.disconnect()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MCL offline backtest over traded pairs")
    p.add_argument("--strategy", default="mcl", choices=sorted(STRATEGY_MODULES),
                   help="which strategy to backtest")
    p.add_argument("--force", action="store_true",
                   help="run even while a live session holds the lock. IB's "
                        "request cap is account-wide, so this WILL contend "
                        "with that session.")
    p.add_argument("--pairs", default="var/state/traded_pairs.json")
    p.add_argument("--out-dir", default="var/reports",
                   help="where backtest_trades_<strategy>.csv is written")
    p.add_argument("--state-dir", default="var/state",
                   help="where the resumable backtest_state_<strategy>.json checkpoint lives")
    p.add_argument("--cache-dir", default=str(CACHE_ROOT),
                   help="where fetched bars are stored. A cache hit costs "
                        "no IB request, so variant sweeps run offline.")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=33)
    p.add_argument("--probe", action="store_true",
                   help="check data availability only; run no backtest")
    p.add_argument("--limit", type=int,
                   help="process only the first N pairs (for a quick trial)")
    p.add_argument("--retry-failed", action="store_true",
                   help="re-attempt pairs previously recorded as NO_DATA "
                        "(they are usually throttling, not missing history)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
