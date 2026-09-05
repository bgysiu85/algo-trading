#!/usr/bin/env python3
"""Setup B on its own — the one test that can reopen VW9.

    python -m strategy.vw9.setup_b_study

WHY THIS IS NOT THE POST-HOC SLICE ALREADY REPORTED
---------------------------------------------------
claude/vw9_first_results.md §6 quotes Setup B at +$24.67/trade from a mixed
run, filtered to kind == "B" afterwards. That number understates B, and the
reason is mechanical rather than statistical:

  * Setup A is 81% of triggers;
  * A consumes MAX_ENTRIES_PER_SESSION, so once four A trades have fired, a
    later B trigger is refused;
  * and while an A position is open, the no-overlap rule blocks B entirely.

So the post-hoc slice is not "what Setup B would have done", it is "what B
managed in the gaps A left". `only_setup="B"` filters BEFORE the cap and
BEFORE the overlap block, which is the difference this module exists to
measure. The trade count is the giveaway: if B-only produces materially more
trades than the slice, the slice was the weaker thing.

WHAT WOULD ACTUALLY REOPEN VW9, and it is not P/L
-------------------------------------------------
VW9 was rejected for CONCENTRATION, not for losing: all twelve grid cells had
negative drop-top-3 and drop-top-5, and two names (WLDS, PLYX) were $11,290 of
a $9,005 result. The post-hoc B slice fails the same way -- AEHL alone
(+$2,232) exceeds its whole result, with 20 of 55 symbols profitable.

So the bar here is:

    drop-top-3 and drop-top-5 POSITIVE, and a decent share of symbols
    profitable -- with the P/L in RTH rather than pre-market.

That last clause is why B is interesting at all. §9 is explicit that
pre-market fills are the ones the model cannot support (Day Limit orders only,
no market order, no resting stop), and B is the only variant whose profit sits
in RTH, the one window where the fill assumptions are believable.

A B-only run that makes MORE money but still fails drop-3 does not reopen
anything. It closes VW9 for good, which is worth knowing.
"""
from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.cache_io import load_pairs
from strategy.vw9.backtest import backtest_session_tf
from strategy.vw9.preflight import load

ET = ZoneInfo("America/New_York")

# MCL's measured friction, applied per share transacted. VW9's own friction has
# never been measured -- flagged in vw9_first_results.md's caveats and still
# true, so treat every "real" column as borrowed.
SLIP_PER_SHARE = (0.0590 - 0.0164) / 2


def run(sessions, **kw):
    trades = []
    for symbol, date_str, df in sessions:
        try:
            got = backtest_session_tf(
                df, datetime.strptime(date_str, "%Y-%m-%d").date(), ET, 5,
                exit_mode="trail_atr", use_vwap_exit=False, **kw)
        except Exception:
            continue
        for t in got:
            t.symbol = symbol
            trades.append(t)
    return trades


def real(t) -> float:
    shares = t.shares_traded or (t.qty * 2)
    return t.net - shares * SLIP_PER_SHARE


def summarise(label, trades):
    if not trades:
        print(f"  {label:<26} no trades")
        return None
    by_sym = defaultdict(float)
    by_block = defaultdict(lambda: [0, 0.0])
    for t in trades:
        by_sym[t.symbol] += real(t)
        b = by_block[t.session_block]
        b[0] += 1
        b[1] += real(t)
    net = sum(by_sym.values())
    top = sorted(by_sym.values(), reverse=True)
    win = sum(1 for v in by_sym.values() if v > 0)
    print(f"  {label:<26} {len(trades):>4} tr  ${net:>9,.0f}  "
          f"${net/len(trades):>7.2f}/tr   "
          f"drop1 ${net - sum(top[:1]):>8,.0f}  "
          f"drop3 ${net - sum(top[:3]):>8,.0f}  "
          f"drop5 ${net - sum(top[:5]):>8,.0f}   "
          f"{win}/{len(by_sym)} syms")
    return dict(trades=trades, by_sym=by_sym, by_block=by_block, net=net,
                drop3=net - sum(top[:3]), drop5=net - sum(top[:5]),
                syms=len(by_sym), winners=win)


def main() -> int:
    ap = argparse.ArgumentParser(description="VW9 Setup B, standalone")
    ap.add_argument("--cache", type=Path, default=Path("bar_cache"))
    ap.add_argument("--pairs", default="var/state/traded_pairs.json")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    # VW9's OWN loader, not common.analysis.load_sessions.
    #
    # This is the documented trap and it caught the first run of this file.
    # load_sessions() slices MCL's window -- TWO sessions ending 09:30 -- while
    # VW9 needs ONE session ending 20:00. Using MCL's, every VW9 trade lands in
    # pre-market by construction: the frame simply has no RTH bars in it. The
    # first run reported 176 trades, 100% PRE and 0 RTH, against the published
    # 407, and the giveaway was that "all of Setup B is pre-market" flatly
    # contradicted the documented result. A wrong slice does not error; it
    # returns a smaller, plausible, meaningless answer.
    sessions, missing = load(load_pairs(Path(a.pairs)), a.cache, a.limit)
    print(f"{len(sessions)} sessions ({missing} without cached bars), "
          f"1 session ending 20:00 -- VW9's window")
    print("5m, trail_atr, VWAP exit off, band on")
    print(f"friction ${SLIP_PER_SHARE:.4f}/share transacted (MCL's, borrowed)\n")

    print("THE COMPARISON THAT MATTERS")
    print(f"  {'':<26} {'trades':>7} {'real net':>11} {'per tr':>10}  "
          f"{'drop1':>14} {'drop3':>14} {'drop5':>14}   profitable")
    mixed = run(sessions)
    m = summarise("mixed (as rejected)", mixed)
    summarise("  its Setup-B slice", [t for t in mixed if t.setup_kind == "B"])
    summarise("  its Setup-A slice", [t for t in mixed if t.setup_kind == "A"])
    b_only = run(sessions, only_setup="B")
    b = summarise("SETUP B ONLY", b_only)
    a_only = run(sessions, only_setup="A")
    summarise("Setup A only (control)", a_only)

    if b is None:
        return 1

    slice_n = len([t for t in mixed if t.setup_kind == "B"])
    print(f"\n  Setup B trades: {slice_n} in the mixed run -> {len(b_only)} "
          f"standalone. The difference is what Setup A was crowding out.")

    print("\nSESSION BLOCK — the reason Setup B is worth testing at all")
    print("  §9: pre-market takes Day Limit orders only, so PRE fills are the")
    print("  ones the model cannot support. RTH is the believable window.")
    print(f"  {'block':<8} {'trades':>7} {'real net':>11} {'per trade':>11}")
    for blk in ("PRE", "RTH", "POST"):
        n, v = b["by_block"].get(blk, [0, 0.0])
        if n:
            print(f"  {blk:<8} {n:>7} ${v:>10,.0f} ${v/n:>10.2f}")

    print("\nVERDICT AGAINST THE BAR THAT REJECTED VW9")
    checks = [
        ("drop-top-3 positive", b["drop3"] > 0, f"${b['drop3']:,.0f}"),
        ("drop-top-5 positive", b["drop5"] > 0, f"${b['drop5']:,.0f}"),
        ("majority of symbols profitable",
         b["winners"] * 2 > b["syms"], f"{b['winners']}/{b['syms']}"),
        ("RTH profitable on its own",
         b["by_block"].get("RTH", [0, 0.0])[1] > 0,
         f"${b['by_block'].get('RTH', [0, 0.0])[1]:,.0f}"),
    ]
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}]  {name:<32} {detail}")
    passed = sum(1 for _n, ok, _d in checks if ok)
    print(f"\n  {passed}/4 — ", end="")
    if passed == 4:
        print("Setup B survives the test that rejected VW9. Worth reopening.")
    elif passed >= 2:
        print("partial. Better than the mixed strategy, still not an edge.")
    else:
        print("Setup B fails the same way the mixed strategy did. VW9 is done.")

    print("\n  top contributors, to see what is carrying it:")
    for sym, v in sorted(b["by_sym"].items(), key=lambda kv: -kv[1])[:5]:
        print(f"    {sym:<8} ${v:>9,.0f}  ({100*v/b['net']:>5.1f}% of net)"
              if b["net"] else f"    {sym:<8} ${v:>9,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
