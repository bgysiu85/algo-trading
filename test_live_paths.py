#!/usr/bin/env python3
"""Offline checks for the LIVE order paths — the ones dry run never exercises.

Covers: outright rejection, partial fill, and a failed exit that must retry
instead of silently leaving the position held.
"""
import asyncio, csv, sys, types
from datetime import datetime, timedelta
from pathlib import Path

import mcl_paper_trader as M
from test_dryrun_roundtrip import FakeTicker, find_firing_series


class FakeFill:
    def __init__(self, shares): self.execution = types.SimpleNamespace(shares=shares)


class FakeLogEntry:
    def __init__(self, msg): self.message = msg


class FakeTrade:
    def __init__(self, filled, avg, status, msgs=()):
        self.fills = [FakeFill(filled)] if filled else []
        self.orderStatus = types.SimpleNamespace(status=status, avgFillPrice=avg)
        self.log = [FakeLogEntry(m) for m in msgs]
    def isDone(self): return True


class FakeIB:
    """Returns a scripted sequence of trade outcomes, one per placeOrder call."""
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.placed, self.cancelled = [], []
        from test_dryrun_roundtrip import FakeEvent
        self.errorEvent = FakeEvent()
    def placeOrder(self, contract, order):
        self.placed.append(order)
        return self.outcomes.pop(0) if self.outcomes else \
            FakeTrade(0, 0.0, "Submitted")
    def cancelOrder(self, order): self.cancelled.append(order)
    def positions(self): return []


def build(tag, outcomes):
    out = Path(f"/tmp/live_{tag}.csv")
    if out.exists():
        out.unlink()
    log = M.FillLog(out)
    ib = FakeIB(outcomes)
    tr = M.MCLPaperTrader(ib, Path("/tmp/wl.txt"), log, dry_run=False)
    tr.equity = 22290.96
    st = M.SymbolState(symbol="TEST")
    st.contract = object()
    st.ticker = FakeTicker()
    tr.states["TEST"] = st
    return tr, st, ib, log, out


async def feed(tr, st, seq, start_min=0):
    now = datetime(2026, 9, 2, 8, 0, tzinfo=M.ET)
    for i, df in enumerate(seq):
        tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
        await tr.step_symbol(st, now + timedelta(minutes=start_min + i))


async def main():
    n = 140
    full, seed, spike = find_firing_series(n)
    seq = [full.iloc[: k + 1] for k in range(M.MIN_BARS_REQUIRED, n)]
    ok = True

    # ---- 1. rejection is not recorded as a no-fill ------------------------
    tr, st, ib, log, out = build("reject", [
        FakeTrade(0, 0.0, "Inactive",
                  ["Order rejected - reason: read-only API connection"]),
    ] * 20)
    await feed(tr, st, seq)
    log.close()
    rows = list(csv.DictReader(out.open()))
    rejected = [r for r in rows if r["status"] == "REJECTED"]
    nofill = [r for r in rows if r["status"] == "NO_FILL_CANCELLED"]
    if rejected and not nofill:
        print(f"PASS  rejection logged as REJECTED, not NO_FILL "
              f"(reason: {rejected[0]['reject_reason'][:40]}...)")
    else:
        print(f"FAIL  rejection handling: {len(rejected)} REJECTED, "
              f"{len(nofill)} NO_FILL")
        ok = False
    if st.position is None:
        print("PASS  no position opened on a rejected buy")
    else:
        print("FAIL  position opened despite rejection")
        ok = False

    # ---- 2. partial fill: remainder cancelled, position = filled qty ------
    tr, st, ib, log, out = build("partial", [
        FakeTrade(40, 10.04, "Submitted"),          # BUY 100 -> 40 filled
        FakeTrade(40, 9.98, "Filled"),              # SELL 40 -> all of it
    ])
    await feed(tr, st, seq)
    log.close()
    rows = list(csv.DictReader(out.open()))
    part = [r for r in rows if r["status"] == "PARTIAL_FILL"]
    if part and int(part[0]["filled_qty"]) == 40:
        print("PASS  partial fill recorded as PARTIAL_FILL with qty 40")
    else:
        print(f"FAIL  partial fill not recorded correctly: {part}")
        ok = False
    if ib.cancelled:
        print("PASS  unfilled remainder was cancelled")
    else:
        print("FAIL  remainder left working on the book")
        ok = False
    sells = [r for r in rows if r["action"] == "SELL"]
    if sells and int(sells[0]["qty"]) == 40:
        print("PASS  exit sized to the 40 shares actually held, not 100")
    else:
        print(f"FAIL  exit sized wrong: {[r['qty'] for r in sells]}")
        ok = False

    # ---- 3. exit that doesn't fill must retry -----------------------------
    tr, st, ib, log, out = build("stickyexit", [
        FakeTrade(100, 10.04, "Filled"),            # BUY fills
        FakeTrade(0, 0.0, "Submitted"),             # first SELL: no fill
        FakeTrade(0, 0.0, "Submitted"),             # second SELL: no fill
        FakeTrade(100, 9.90, "Filled"),             # third SELL: fills
    ])
    await feed(tr, st, seq)
    log.close()
    rows = list(csv.DictReader(out.open()))
    sells = [r for r in rows if r["action"] == "SELL"]
    if len(sells) >= 3:
        print(f"PASS  exit retried after no-fill ({len(sells)} sell attempts)")
    else:
        print(f"FAIL  exit not retried — only {len(sells)} sell attempt(s); "
              f"position would have been silently held")
        ok = False
    if st.position is None:
        print("PASS  flat once the retry filled")
    else:
        print("FAIL  still holding after a successful exit fill")
        ok = False

    print("\n" + ("ALL LIVE-PATH CHECKS PASSED" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
