#!/usr/bin/env python3
"""The live path must refuse entries outside the $2-20 band.

Found 2026-09-05 while reproducing Ben's TradingView screener. The band was
enforced in TWO of the three places that matter and missing from the third:

    strategy/mcl/mcl.py      backtest_session() -- enforced (ENFORCE_PRICE_BAND)
    brokers/ibkr/scanner.py  the scan -- enforced (abovePrice / belowPrice)
    brokers/ibkr/trader.py   the LIVE entry -- NOT enforced

So anything that reached the watchlist by another route, or drifted out of band
between the scan and the signal, was traded live at a price the backtest
refuses to model. GELS was bought at $0.935 that way. The cost is not that one
trade; it is that every live-vs-backtest comparison silently became a
comparison of two different universes.

METHOD. The same firing bar series the other broker suites use, with every
price multiplied by a constant. MCL's entry conditions are all ratios -- MACD
crossings, RSI/MFI direction, volume against its own average -- so scaling
leaves the signal identical and moves ONLY the price. That isolates the band
from everything else, which a hand-built frame at a chosen price could not do.

Script suite, matching its siblings, so run_tests.ps1 picks it up.
"""
import asyncio
import csv
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from brokers.ibkr import trader as M
from strategy.mcl import mcl as S

from tests.brokers.ibkr.test_dryrun_roundtrip import (FakeTicker,
                                                      find_firing_series)
from tests.brokers.ibkr.test_live_paths import FakeIB, FakeTrade


def scaled(df, factor):
    out = df.copy()
    for col in ("open", "high", "low", "close"):
        out[col] = out[col] * factor
    return out


async def drive(tag, target_price):
    """Run one symbol through the firing series, rescaled so the entry lands
    at roughly `target_price`. Returns (state, fill-log rows)."""
    n = 140
    full, _seed, _spike = find_firing_series(n)
    # Anchor the scaling on the bar that ACTUALLY fires the entry, not the last
    # bar of the series. Anchoring on the last bar was wrong by enough to
    # invert two of the cases below: the series keeps moving after the signal,
    # so the entry price and the final close are different numbers.
    sig = S.signals(full)
    fires = [i for i, e in enumerate(sig["entry"]) if e]
    if not fires:
        raise AssertionError("the firing series no longer fires an entry")
    entry_close = float(full["close"].iloc[fires[0]])
    full = scaled(full, target_price / entry_close)

    out = Path(tempfile.gettempdir()) / f"band_{tag}.csv"
    if out.exists():
        out.unlink()
    log = M.FillLog(out)
    tr = M.MCLPaperTrader(FakeIB([FakeTrade(100, target_price, "Filled")] * 40),
                          Path(tempfile.gettempdir()) / "wl.txt", log,
                          dry_run=False)
    tr.equity = 22290.96
    st = M.SymbolState(symbol="TEST")
    st.contract = object()
    st.ticker = FakeTicker()
    tr.states["TEST"] = st

    now = datetime(2026, 9, 2, 8, 0, tzinfo=M.ET)
    for i, k in enumerate(range(M.MIN_BARS_REQUIRED, n)):
        df = full.iloc[: k + 1]
        tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
        await tr.step_symbol(st, now + timedelta(minutes=i))
        if st.position is not None:
            break
    log.close()
    return st, list(csv.DictReader(out.open()))


def main():
    ok = True

    # --- inside the band: the entry still happens -------------------------
    # Guards against the fix being too aggressive. A band check that also
    # blocked legitimate entries would look like a pass on the tests below.
    for px in (2.50, 5.00, 19.00):
        st, _rows = asyncio.run(drive(f"in{px}", px))
        good = st.position is not None
        print(("PASS" if good else "FAIL"),
              f"in-band ${px:>6.2f} -> "
              f"{'entered' if good else 'NO ENTRY -- the check is too tight'}")
        ok &= good

    # --- outside the band: refused, AND the refusal is recorded -----------
    # The log row matters as much as the refusal. A silent skip is
    # indistinguishable from "no signal fired" when the session is reviewed,
    # which is exactly how this gap survived unnoticed.
    for px, why in ((0.935, "the GELS price"), (1.90, "just below"),
                    (21.00, "just above"), (60.00, "far above")):
        st, rows = asyncio.run(drive(f"out{px}", px))
        refused = st.position is None
        skipped = [r for r in rows if r.get("status") == "SKIPPED_PRICE_BAND"]
        bought = [r for r in rows
                  if r.get("action") == "BUY"
                  and r.get("status") in ("FILLED", "PARTIAL_FILL")]
        good = refused and skipped and not bought
        print(("PASS" if good else "FAIL"),
              f"out-of-band ${px:>6.2f} ({why}) -> "
              f"{'refused' if refused else 'ENTERED'}, "
              f"{len(skipped)} SKIPPED_PRICE_BAND row(s), "
              f"{len(bought)} order(s) placed")
        ok &= bool(good)

    # --- live reads the STRATEGY's band, it does not keep its own ----------
    # If someone changes the backtest band, live follows. The whole defect was
    # two copies of one rule drifting apart, so a duplicated constant here
    # would reintroduce it in a new place.
    src = Path("brokers/ibkr/trader.py").read_text()
    good = "S.PRICE_MIN <= sig.close <= S.PRICE_MAX" in src
    print(("PASS" if good else "FAIL"),
          "trader.py tests against S.PRICE_MIN/S.PRICE_MAX, not its own copy")
    ok &= good
    good = S.ENFORCE_PRICE_BAND and (S.PRICE_MIN, S.PRICE_MAX) == (2.0, 20.0)
    print(("PASS" if good else "FAIL"),
          f"strategy band is {S.PRICE_MIN}-{S.PRICE_MAX}, "
          f"enforce={S.ENFORCE_PRICE_BAND}")
    ok &= good

    print("\n" + ("ALL PRICE-BAND CHECKS PASSED" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
