#!/usr/bin/env python3
"""Offline check that a dry run produces complete round trips, not just entries.

Stubs out IB entirely: feeds synthetic bars through step_symbol and asserts the
CSV contains a BUY followed by a SELL carrying trade_pnl.

Temp paths come from tempfile.gettempdir(), NOT a hardcoded "/tmp". On Windows
Path("/tmp/x") resolves to a "tmp" folder at the root of the current DRIVE --
which does not exist -- so this failed with FileNotFoundError on Windows while
passing on POSIX.
gettempdir() gives %TEMP% on Windows and /tmp elsewhere.
"""
import asyncio, csv, sys, tempfile, types
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from brokers.ibkr import trader as M


class FakeTicker:
    def __init__(self): self.bid = 10.00; self.ask = 10.02


class FakeEvent:
    """Stand-in for ib_async's Event: supports `+=` and does nothing."""
    def __iadd__(self, fn): return self


class FakeIB:
    def __init__(self): self.errorEvent = FakeEvent()
    def positions(self): return []


RISE_END = 100      # bars 0..99 drift up, 100.. fall away


def make_bars(n, seed, spike_bar):
    """Upward random walk, then a decline. A clean linear ramp is useless here:
    it pins RSI and MFI at 100 so `value > value[3]` is never true. A noisy
    drift is both more realistic and actually able to satisfy the rules."""
    import random
    rng = random.Random(seed)
    idx = pd.date_range("2026-09-02 08:00", periods=n, freq="1min", tz="UTC")

    px, close = 3.0, []
    for _ in range(RISE_END):
        px *= 1.0 + rng.uniform(-0.004, 0.011)       # upward drift with pullbacks
        close.append(px)
    for _ in range(n - RISE_END):
        px *= 1.0 + rng.uniform(-0.012, 0.003)       # decline
        close.append(px)

    vol = [rng.randint(4000, 7000) for _ in range(n)]
    vol[spike_bar] = vol[spike_bar - 1] * 6          # clears the 3x rule easily

    return pd.DataFrame({
        "open": close, "high": [c * 1.003 for c in close],
        "low": [c * 0.997 for c in close], "close": close, "volume": vol,
    }, index=idx)


def find_firing_series(n=140):
    """Search seeds/spike bars for a series that produces a real entry."""
    for seed in range(400):
        for spike in range(70, 96):
            df = make_bars(n, seed, spike)
            s = M.evaluate(df.iloc[: spike + 1])
            if s and s.long_entry:
                return df, seed, spike
    return None, None, None


async def run_case(tag, bars_seq):
    out = Path(tempfile.gettempdir()) / f"test_{tag}.csv"
    if out.exists():
        out.unlink()
    log = M.FillLog(out)
    tr = M.MCLPaperTrader(FakeIB(), Path(tempfile.gettempdir()) / "wl.txt",
                          log, dry_run=True)
    tr.equity = 22290.96

    st = M.SymbolState(symbol="TEST")
    st.contract = object()
    st.ticker = FakeTicker()
    tr.states["TEST"] = st

    now = datetime(2026, 9, 2, 8, 0, tzinfo=M.ET)
    for i, df in enumerate(bars_seq):
        tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
        await tr.step_symbol(st, now + timedelta(minutes=i))

    log.close()
    rows = list(csv.DictReader(out.open()))
    return rows, tr


async def main():
    n = 140
    full, seed, spike = find_firing_series(n)
    if full is None:
        print("FAIL  could not construct a series that triggers an entry")
        return 1
    print(f"using seed={seed}, volume spike at bar {spike}")
    # replay the series one bar at a time, as the live loop would see it
    seq = [full.iloc[: k + 1] for k in range(M.MIN_BARS_REQUIRED, n)]

    rows, tr = await run_case("roundtrip", seq)

    print(f"rows written: {len(rows)}")
    for r in rows:
        print(f"  {r['action']:4s} {r['reason']:15s} status={r['status']:8s} "
              f"fill={r['fill_price']:>8s} qty={r['filled_qty']:>4s} "
              f"pnl={r['trade_pnl'] or '-':>8s}")

    buys = [r for r in rows if r["action"] == "BUY"]
    sells = [r for r in rows if r["action"] == "SELL"]

    ok = True

    if not buys:
        print("FAIL  no entry signal fired -- cannot test the exit path")
        return 1

    if not sells:
        print("FAIL  entry logged but NO EXIT -- dry run is entry-only")
        ok = False
    else:
        print("PASS  dry run produced a completed round trip")

    if sells and not sells[0]["trade_pnl"]:
        print("FAIL  sell row carries no trade_pnl")
        ok = False
    elif sells:
        e, x = float(sells[0]["entry_price"]), float(sells[0]["exit_price"])
        q, pnl = int(sells[0]["filled_qty"]), float(sells[0]["trade_pnl"])
        expect = (x - e) * q - M.COMMISSION_RT
        if abs(pnl - expect) < 0.01:
            print(f"PASS  trade_pnl arithmetic correct "
                  f"({e:.4f} -> {x:.4f} x{q} = {pnl:+.2f})")
        else:
            print(f"FAIL  trade_pnl {pnl} != expected {expect}")
            ok = False

    if len(buys) > 1 and len(sells) < len(buys):
        print(f"FAIL  {len(buys)} entries but only {len(sells)} exits -- "
              f"re-entry while already positioned")
        ok = False
    else:
        print(f"PASS  entries ({len(buys)}) matched by exits ({len(sells)})")

    if tr.session_trades == len(sells) and tr.session_trades > 0:
        print(f"PASS  session counter agrees ({tr.session_trades} trades, "
              f"{tr.session_pnl:+.2f})")
    else:
        print(f"FAIL  session counter {tr.session_trades} vs {len(sells)} sells")
        ok = False

    print("\n" + ("ALL CHECKS PASSED" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
