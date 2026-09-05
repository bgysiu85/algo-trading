#!/usr/bin/env python3
"""Grid the MIRROR mechanic: sell into strength, buy back on the dip.

    python -m common.scale_up_grid --out var/reports/scale_up_grid.csv

WHY THIS IS NOT THE MECHANIC ALREADY REJECTED
---------------------------------------------
claude/mcl_scale_out_decision.md tested Ben's description literally: sell on a
PULLBACK, buy back on the RECOVERY. That sells low and buys high, and it lost
at every setting at the shipped trail -- which, once measured, was not a
surprise but an identity.

This is the same two orders with the signs swapped: sell a portion when price
is `scale_up_pct` ABOVE the last transaction, buy it back when price then dips
`rebuy_dip_pct` from the peak it reached. It sells high and buys low, and it is
much closer to how scaling into strength is normally described.

It is not free money, and it is worth being precise about what it costs:

  * The sold shares are absent if price keeps running. That is the entire
    price of admission, and it is paid exactly on the trades that matter most
    -- this universe's P/L is carried by a handful of big movers.
  * Both legs REST (a limit sell above the market, a limit buy below it), so
    unlike the rejected mechanic there is no marketable-limit chase to pay.
    The cost moves from spread to QUEUE POSITION: a resting limit at a level
    that price only touches need not fill at all, and pre-market books are
    thin. A bar model cannot see this and this grid does not model it.

So read a positive result here as "worth a paper session to see if the fills
are real", never as a shipped edge.

Same construction as common/scale_grid.py: a duplicated position loop over
plain lists for speed, verified trade-for-trade AND share-for-share against
strategy/mcl/mcl.py before the grid is allowed to run.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import multiprocessing as mp
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import load_sessions, LIVE
from common.commissions import order_cost
from common.scale_grid import prepare, SLIP_PER_SHARE
from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")

# Ben's four knobs, mirrored. The trail is swept alongside because the
# rejected mechanic's result flipped sign with it, and that has to be checked
# rather than assumed to repeat.
TRAILS = [3.0, 5.0, 8.0, 10.0, 15.0]
UPS = [1.0, 2.0, 3.0, 5.0, 8.0, 12.0]          # sell this far above the last fill
PORTIONS = [25.0, 50.0, 75.0]                  # how much of the position to sell
DIPS = [1.0, 2.0, 3.0, 5.0, 8.0]               # buy back this far below the peak

QUICK = ([5.0], [2.0, 5.0], [50.0], [2.0, 5.0])


def _simulate(sess, trail_pct, up_pct, portion, dip_pct,
              max_cycles=None, rebuy=None, max_position_shares=None,
              cycle_log=None, rebuy_ref="peak"):
    """One session. (net, shares_traded, max_qty, cycles) per trade.

    `cycle_log`, when a list is passed, collects (sell_px, buy_px, qty) for
    every completed sell-then-buy-back. Purely observational -- it changes no
    behaviour, so verify() still covers this function -- and it exists because
    the question "is each individual round trip profitable?" turns out to be
    the one that explains the whole result.
    """
    _sym, entry, _o, high, low, close, keep = sess
    trades = []
    pos = None
    last_k = len(keep) - 1
    _last_sell = [0.0]

    for k, i in enumerate(keep):
        if pos is None:
            if entry[i]:
                px = close[i] + S.SLIPPAGE_TICKS * S.TICK
                if S.ENFORCE_PRICE_BAND and not (S.PRICE_MIN <= px <= S.PRICE_MAX):
                    continue
                q = S.size_for(px)
                if q >= 1:
                    # [qty, avg_px, realised, shares_traded, peak, scaled_up,
                    #  cycles, commission, up_ref, up_peak, sold_qty, max_qty]
                    pos = [q, px, 0.0, q, max(px, high[i]), False, 0,
                           order_cost(q, px, False, S.COMMISSION_PLAN),
                           px, 0.0, 0, q]
            continue

        trail = pos[4] * (1.0 - trail_pct / 100.0)
        exit_px = None
        if low[i] <= trail:
            exit_px = trail - S.SLIPPAGE_TICKS * S.TICK
        elif k == last_k:
            exit_px = close[i] - S.SLIPPAGE_TICKS * S.TICK

        if exit_px is not None:
            gross = pos[2] + (exit_px - pos[1]) * pos[0]
            comm = pos[7] + order_cost(pos[0], exit_px, True, S.COMMISSION_PLAN)
            trades.append((gross - comm, pos[3] + pos[0], pos[11], pos[6]))
            pos = None
        else:
            if not pos[5]:
                sell_level = pos[8] * (1.0 + up_pct / 100.0)
                if high[i] >= sell_level:
                    sell_q = int(pos[0] * portion / 100.0)
                    if 1 <= sell_q < pos[0]:
                        px_out = sell_level - S.SLIPPAGE_TICKS * S.TICK
                        pos[2] += (px_out - pos[1]) * sell_q
                        pos[7] += order_cost(sell_q, px_out, True,
                                             S.COMMISSION_PLAN)
                        pos[0] -= sell_q
                        pos[3] += sell_q
                        pos[5] = True
                        pos[10] = sell_q
                        pos[9] = pos[4] if pos[4] > high[i] else high[i]
                        pos.append(px_out) if False else None
                        _last_sell[0] = px_out
            else:
                ref = _last_sell[0] if rebuy_ref == "sell" else pos[9]
                buy_level = ref * (1.0 - dip_pct / 100.0)
                if low[i] <= buy_level:
                    capped = max_cycles is not None and pos[6] >= max_cycles
                    add = pos[10] if rebuy is None else rebuy
                    if max_position_shares is not None:
                        add = min(add, max_position_shares - pos[0])
                    if not capped and add >= 1:
                        px_in = buy_level + S.SLIPPAGE_TICKS * S.TICK
                        pos[1] = (pos[1] * pos[0] + px_in * add) / (pos[0] + add)
                        pos[7] += order_cost(add, px_in, False, S.COMMISSION_PLAN)
                        pos[0] += add
                        pos[3] += add
                        pos[6] += 1
                        if pos[0] > pos[11]:
                            pos[11] = pos[0]
                        pos[8] = px_in
                        if cycle_log is not None:
                            cycle_log.append((_last_sell[0], px_in, add))
                    pos[5] = False
                elif high[i] > pos[9]:
                    pos[9] = high[i]
            if pos[4] < high[i]:
                pos[4] = high[i]
    return trades


def evaluate(prepared, trail_pct, up_pct, portion, dip_pct,
             max_cycles=None, rebuy=None, max_position_shares=None,
             rebuy_ref="peak"):
    per_sym, n, net, real, mq, cyc = {}, 0, 0.0, 0.0, 0, 0
    for sess in prepared:
        sym = sess[0]
        for tnet, shares, m, c in _simulate(sess, trail_pct, up_pct, portion,
                                            dip_pct, max_cycles, rebuy,
                                            max_position_shares, None,
                                            rebuy_ref):
            n += 1
            net += tnet
            real += tnet - shares * SLIP_PER_SHARE
            per_sym[sym] = per_sym.get(sym, 0.0) + (tnet - shares * SLIP_PER_SHARE)
            mq = max(mq, m)
            cyc += c
    if not n:
        return None
    top = sorted(per_sym.values(), reverse=True)
    return dict(trail=trail_pct, up=up_pct, portion=portion, dip=dip_pct,
                trades=n, net=net, real=real, real_per=real / n,
                drop5=real - sum(top[:5]), syms=len(per_sym),
                max_qty=mq, cycles=cyc)


_PREPARED = None


def _init(prepared):
    global _PREPARED
    _PREPARED = prepared


def _work(combo):
    return evaluate(_PREPARED, *combo)


def verify(sessions, prepared, n_check=40):
    """The fast path must match the shipped engine, trade for trade."""
    cases = [(5.0, 2.0, 50.0, 2.0, None, "peak"),
             (10.0, 5.0, 75.0, 3.0, None, "peak"),
             (3.0, 1.0, 25.0, 1.0, None, "peak"),
             (5.0, 2.0, 50.0, 2.0, 1, "peak"),
             (5.0, 8.0, 50.0, 5.0, 3, "peak"),
             (5.0, 2.0, 50.0, 1.0, None, "sell"),
             (5.0, 5.0, 75.0, 3.0, 2, "sell")]
    for trail, up, portion, dip, cap, ref in cases:
        for (symbol, date_str, df), prep in list(zip(sessions, prepared))[:n_check]:
            real = S.backtest_session(
                df, datetime.strptime(date_str, "%Y-%m-%d").date(), ET, **LIVE,
                trail_pct=trail, scale_up_pct=up, scale_up_portion=portion,
                rebuy_dip_pct=dip, max_cycles=cap, rebuy_ref=ref)
            fast = _simulate(prep, trail, up, portion, dip, cap,
                             rebuy_ref=ref)
            tag = (f"trail={trail} up={up} portion={portion} dip={dip} "
                   f"cap={cap} ref={ref}")
            if len(real) != len(fast):
                return (f"trade COUNT differs on {symbol} {date_str} at {tag}: "
                        f"engine {len(real)}, fast {len(fast)}")
            for a, b in zip(real, fast):
                if abs(a.net - b[0]) > 0.005:
                    return (f"NET differs on {symbol} {date_str} at {tag}: "
                            f"engine {a.net:.4f}, fast {b[0]:.4f}")
                if a.shares_traded != b[1]:
                    return (f"SHARES differ on {symbol} {date_str} at {tag}: "
                            f"engine {a.shares_traded}, fast {b[1]}")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Sell-into-strength grid")
    ap.add_argument("--out", default="var/reports/scale_up_grid.csv")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--jobs", type=int, default=mp.cpu_count())
    a = ap.parse_args()

    sessions = load_sessions(Path("bar_cache"))
    dates = sorted({d for _, d, _ in sessions})
    split = dates[len(dates) // 2]
    prepared = prepare(sessions)
    print(f"{len(prepared)} sessions prepared, holdout split {split}")

    print("verifying the fast path against the shipped engine ...",
          end=" ", flush=True)
    err = verify(sessions, prepared)
    if err:
        print("FAILED")
        sys.exit(f"fast simulator disagrees with strategy/mcl/mcl.py: {err}")
    print("exact match")

    grid = QUICK if a.quick else (TRAILS, UPS, PORTIONS, DIPS)
    combos = list(itertools.product(*grid))
    print(f"{len(combos):,} combinations on {a.jobs} core(s)")

    early = prepare([s for s in sessions if s[1] < split])
    late = prepare([s for s in sessions if s[1] >= split])

    results = {}
    for name, prep in (("all", prepared), ("early", early), ("late", late)):
        t0 = time.time()
        with mp.Pool(a.jobs, initializer=_init, initargs=(prep,)) as pool:
            rows = [r for r in pool.map(_work, combos, chunksize=8) if r]
        results[name] = {(r["trail"], r["up"], r["portion"], r["dip"]): r
                         for r in rows}
        print(f"  {name:<6} {len(rows):,} cells in {time.time()-t0:.0f}s")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["trail_pct", "up_pct", "portion_pct", "dip_pct", "trades",
                    "real_net", "real_per_trade", "drop5", "symbols",
                    "cycles", "early_real", "late_real"])
        for key, r in results["all"].items():
            w.writerow([r["trail"], r["up"], r["portion"], r["dip"], r["trades"],
                        round(r["real"], 2), round(r["real_per"], 4),
                        round(r["drop5"], 2), r["syms"], r["cycles"],
                        round(results["early"].get(key, {}).get("real", float("nan")), 2),
                        round(results["late"].get(key, {}).get("real", float("nan")), 2)])
    print(f"\nwrote {len(results['all']):,} rows to {out}")

    # --- the only comparison that means anything: same trail, no scaling ----
    print("\nAGAINST THE SAME TRAIL WITH NO SCALING (size held constant)")
    print(f"  {'trail':>5} {'baseline':>10} {'best cell':>10} {'delta':>9}  "
          f"{'up/portion/dip':<18} {'drop5':>9} {'cycles':>7}")
    for t in sorted({r["trail"] for r in results["all"].values()}):
        # A sell level 1e9% above the last fill can never be reached, so this
        # is the identical engine with the mechanic switched off -- a cleaner
        # baseline than a separate code path that might drift.
        base = evaluate(prepared, t, 1e9, 50.0, 2.0)
        cells = [r for r in results["all"].values() if r["trail"] == t]
        best = max(cells, key=lambda r: r["real"])
        print(f"  {t:>5.0f} ${base['real']:>9,.0f} ${best['real']:>9,.0f} "
              f"${best['real']-base['real']:>+8,.0f}  "
              f"{best['up']:g}/{best['portion']:g}/{best['dip']:g}"
              f"{'':<10} ${best['drop5']:>8,.0f} {best['cycles']:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
