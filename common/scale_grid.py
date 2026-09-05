#!/usr/bin/env python3
"""
Exhaustive grid search over the four scale-out exit parameters.

    python -m common.scale_grid --out var/reports/scale_grid.csv
    python -m common.scale_grid --quick        # coarse grid, for a smoke test

Ben's requested grid, 4,900 combinations:

    trail_pct          2 .. 15   step 1     (14)
    partial_trail_pct  0.5 .. 5  step 0.5   (10)
    scale_out_pct      20 .. 80  step 10     (7)
    rebuy_qty          50 .. 150 step 25     (5)

WHY THIS FILE EXISTS RATHER THAN A LOOP OVER backtest_session()
---------------------------------------------------------------
backtest_session() costs ~29 ms per session, of which ~20 ms is pandas row
access (`rows.iloc[i]` per bar) rather than anything numeric. 4,900 configs x
373 sessions at that rate is ~15 hours on the two cores available.

_simulate() below is the same state machine over plain Python lists, which is
~40x faster and brings the grid under 15 minutes. It is a DUPLICATE of the
logic in strategy/mcl/mcl.py, which is a real risk -- a duplicated engine that
silently drifts from the one being shipped is worse than a slow one. So
verify() checks it trade-for-trade against the real engine across a sample of
sessions and several parameter sets, and main() refuses to run the grid unless
that check passes.

Two exact-semantics details that are easy to get wrong when porting:

  * prev_high is updated ONLY on bars where a position was already open. The
    real engine `continue`s out of the no-position branch before reaching the
    update, so a bar with no position does not refresh it. Replicated, not
    "fixed", because the point is to match. It matters only for the legacy
    rebuy_trigger="prev_bar_high"; the default "peak" trigger uses the frozen
    rebuy level instead.
  * The trail and the partial level are both derived from the peak AS OF THE
    PREVIOUS BAR -- peak is updated at the bottom of the loop.

READ THE OUTPUT AS A SURFACE, NOT A MAXIMUM
-------------------------------------------
4,900 cells on one dataset is a large multiple-comparisons problem: the best
cell is the best of 4,900 draws and is guaranteed to flatter itself. So the
grid is reported three ways -- the in-sample best, whether the optimum sits on
a boundary (a boundary optimum usually means the model is being arbitraged
rather than fitted), and the honest test: pick the winner on the EARLY half of
the dates and score that same cell on the LATE half.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import multiprocessing as mp
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import load_sessions, LIVE
from common.commissions import order_cost
from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")

# Measured live 2026-09-03 (common/friction.py): buys favourable, sells not.
# Charged per SHARE TRANSACTED so extra cycles are actually paid for.
SLIP_PER_SHARE = (0.0590 - 0.0164) / 2

TRAILS = [float(x) for x in range(2, 16)]
PARTIALS = [x / 2 for x in range(1, 11)]
PORTIONS = [float(x) for x in range(20, 90, 10)]
REBUYS = [50, 75, 100, 125, 150]

QUICK = ([2.0, 5.0, 10.0], [1.0, 2.5], [50.0], [100])


def prepare(sessions):
    """Precompute per session what does not depend on the parameters."""
    out = []
    for symbol, date_str, df in sessions:
        sig = S.signals(df)
        local = sig.index.tz_convert(ET)
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        keep = [i for i, (dt, t) in enumerate(zip(local.date, local.time))
                if dt == d and S.SESSION_START <= t < S.SESSION_END]
        # Sessions with no in-session bars are kept, not skipped. They produce
        # no trades either way, but dropping them would break the positional
        # alignment verify() relies on when zipping prepared against sessions
        # -- which is exactly the bug the first run of this file hit.
        out.append((symbol,
                    sig["entry"].tolist(), sig["open"].tolist(),
                    sig["high"].tolist(), sig["low"].tolist(),
                    sig["close"].tolist(), keep))
    return out


# Re-entering on a reclaim of the peak is a STOP-BUY, which IBKR does not
# accept pre-market. Live it is a marketable limit sent after the
# break is seen, so the fill lands above the trigger. trader.py crosses by
# LIMIT_CROSS_BPS = 20, and tick rounding on a $2-5 stock roughly doubles that
# in practice -- the measured effective cross on this universe is 37-43 bps.
# Charging 0 models a fill nobody can get, and the first run of this grid did
# exactly that.
REBUY_SLIP_BPS = 40.0


def _simulate(sess, trail_pct, partial_pct, portion, rebuy,
              rebuy_slip_bps=REBUY_SLIP_BPS, max_cycles=None,
              rebuy_trigger="peak", max_position_shares=None):
    """One session. Returns (net, shares_traded, max_qty_held, cycles) per trade.

    `rebuy` may be None, meaning "restore exactly what was sold", which holds
    position size constant across cycles. That is the size-NEUTRAL form of the
    mechanic and the only one that measures the idea rather than measuring
    leverage; an integer lets the position grow and `max_position_shares` caps
    how far.
    """
    _sym, entry, _o, high, low, close, keep = sess
    trades = []
    pos = None
    prev_high = None
    last_k = len(keep) - 1

    for k, i in enumerate(keep):
        if pos is None:
            if entry[i]:
                px = close[i] + S.SLIPPAGE_TICKS * S.TICK
                if S.ENFORCE_PRICE_BAND and not (S.PRICE_MIN <= px <= S.PRICE_MAX):
                    continue
                q = S.size_for(px)
                if q >= 1:
                    pos = [q, px, 0.0, q, max(px, high[i]), False, 0,
                           order_cost(q, px, False, S.COMMISSION_PLAN), q,
                           None, 0, q, False]
            continue
        # pos = [qty, avg_px, realised, shares_traded, peak, scaled_out,
        #        cycles, commission, init_qty, rebuy_level, sold_qty, max_qty,
        #        capped_out]
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
            partial = pos[4] * (1.0 - partial_pct / 100.0)
            if pos[12]:
                pass                     # mechanic retired by max_cycles
            elif not pos[5] and low[i] <= partial:
                sell_q = int(pos[0] * portion / 100.0)
                if 1 <= sell_q < pos[0]:
                    px_out = partial - S.SLIPPAGE_TICKS * S.TICK
                    pos[2] += (px_out - pos[1]) * sell_q
                    pos[7] += order_cost(sell_q, px_out, True, S.COMMISSION_PLAN)
                    pos[0] -= sell_q
                    pos[3] += sell_q
                    pos[5] = True
                    pos[9] = pos[4]          # freeze the pullback's peak
                    pos[10] = sell_q
            elif pos[5] and (
                    (trigger := (pos[9] if rebuy_trigger == "peak"
                                 else prev_high)) is not None) \
                    and high[i] >= trigger:
                capped = max_cycles is not None and pos[6] >= max_cycles
                if capped:
                    pos[12] = True
                add = pos[10] if rebuy is None else rebuy
                if max_position_shares is not None:
                    add = min(add, max_position_shares - pos[0])
                if not capped and add >= 1:
                    px_in = (trigger * (1.0 + rebuy_slip_bps / 10_000.0)
                             + S.SLIPPAGE_TICKS * S.TICK)
                    pos[1] = (pos[1] * pos[0] + px_in * add) / (pos[0] + add)
                    pos[7] += order_cost(add, px_in, False, S.COMMISSION_PLAN)
                    pos[0] += add
                    pos[3] += add
                    pos[6] += 1
                    if pos[0] > pos[11]:
                        pos[11] = pos[0]
                pos[5] = False
            if pos[4] < high[i]:
                pos[4] = high[i]
        prev_high = high[i]
    return trades


def evaluate(prepared, trail_pct, partial_pct, portion, rebuy,
             rebuy_slip_bps=REBUY_SLIP_BPS, max_cycles=None,
             rebuy_trigger="peak", max_position_shares=None):
    per_sym = {}
    n = 0
    net = 0.0
    real = 0.0
    max_q = 0
    tot_cycles = 0
    for sess in prepared:
        sym = sess[0]
        for tnet, shares, mq, cyc in _simulate(
                sess, trail_pct, partial_pct, portion, rebuy, rebuy_slip_bps,
                max_cycles, rebuy_trigger, max_position_shares):
            n += 1
            net += tnet
            real += tnet - shares * SLIP_PER_SHARE
            per_sym[sym] = per_sym.get(sym, 0.0) + tnet
            max_q = max(max_q, mq)
            tot_cycles += cyc
    if not n:
        return None
    top = sorted(per_sym.values(), reverse=True)
    return dict(trail=trail_pct, partial=partial_pct, portion=portion, rebuy=rebuy,
                trades=n, net=net, per=net / n, real=real, real_per=real / n,
                drop5=net - sum(top[:5]), syms=len(per_sym),
                max_qty=max_q, cycles=tot_cycles)


_PREPARED = None


def _init(prepared):
    global _PREPARED
    _PREPARED = prepared


def _work(combo):
    return evaluate(_PREPARED, *combo)


def verify(sessions, prepared, n_check=40):
    """The fast path must agree with the shipped engine, trade for trade.

    Both triggers and a capped-cycle case are checked, because the cap and the
    frozen rebuy level are exactly the kind of state that drifts between two
    copies of a state machine.
    """
    cases = [(5.0, 2.5, 50.0, 100, "peak", None, None),
             (10.0, 1.0, 75.0, 150, "peak", None, None),
             (3.0, 0.5, 20.0, 50, "peak", None, None),
             (5.0, 2.5, 50.0, 100, "peak", 1, None),
             (5.0, 2.5, 50.0, 100, "peak", 3, None),
             (5.0, 2.5, 50.0, None, "peak", None, None),   # size-neutral
             (5.0, 0.5, 20.0, 150, "peak", None, 200),     # capped growth
             (5.0, 2.5, 50.0, 100, "prev_bar_high", None, None)]
    for trail, partial, portion, rebuy, trigger, cap, maxpos in cases:
        for (symbol, date_str, df), prep in list(zip(sessions, prepared))[:n_check]:
            real = S.backtest_session(
                df, datetime.strptime(date_str, "%Y-%m-%d").date(), ET, **LIVE,
                trail_pct=trail, scale_out_pct=portion,
                partial_trail_pct=partial, rebuy_qty=rebuy,
                rebuy_slip_bps=REBUY_SLIP_BPS, max_cycles=cap,
                rebuy_trigger=trigger, max_position_shares=maxpos)
            fast = _simulate(prep, trail, partial, portion, rebuy,
                             REBUY_SLIP_BPS, cap, trigger, maxpos)
            tag = (f"trail={trail} partial={partial} portion={portion} "
                   f"rebuy={rebuy} trigger={trigger} cap={cap} maxpos={maxpos}")
            if len(real) != len(fast):
                return (f"trade COUNT differs on {symbol} {date_str} at "
                        f"{tag}: engine {len(real)}, fast {len(fast)}")
            for a, b in zip(real, fast):
                if abs(a.net - b[0]) > 0.005:
                    return (f"NET differs on {symbol} {date_str} at {tag}: "
                            f"engine {a.net:.4f}, fast {b[0]:.4f}")
                if a.shares_traded != b[1]:
                    return (f"SHARES differ on {symbol} {date_str} at {tag}: "
                            f"engine {a.shares_traded}, fast {b[1]}")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Scale-out parameter grid")
    ap.add_argument("--out", default="var/reports/scale_grid.csv")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--jobs", type=int, default=mp.cpu_count())
    a = ap.parse_args()

    sessions = load_sessions(Path("bar_cache"))
    dates = sorted({d for _, d, _ in sessions})
    split = dates[len(dates) // 2]
    prepared = prepare(sessions)
    print(f"{len(prepared)} sessions prepared, holdout split {split}")

    print("verifying the fast path against the shipped engine ...", end=" ", flush=True)
    err = verify(sessions, prepared)
    if err:
        print("FAILED")
        sys.exit(f"fast simulator disagrees with strategy/mcl/mcl.py: {err}")
    print("exact match")

    grid = QUICK if a.quick else (TRAILS, PARTIALS, PORTIONS, REBUYS)
    combos = list(itertools.product(*grid))
    print(f"{len(combos):,} combinations on {a.jobs} core(s)")

    early = prepare([s for s in sessions if s[1] < split])
    late = prepare([s for s in sessions if s[1] >= split])

    results = {}
    for name, prep in (("all", prepared), ("early", early), ("late", late)):
        t0 = time.time()
        with mp.Pool(a.jobs, initializer=_init, initargs=(prep,)) as pool:
            rows = [r for r in pool.map(_work, combos, chunksize=16) if r]
        results[name] = {(r["trail"], r["partial"], r["portion"], r["rebuy"]): r
                         for r in rows}
        print(f"  {name:<6} {len(rows):,} cells in {time.time()-t0:.0f}s")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["trail_pct", "partial_pct", "portion_pct", "rebuy_qty",
                    "trades", "net", "per_trade", "real_net", "real_per_trade",
                    "drop5", "symbols", "early_real", "late_real"])
        for key, r in results["all"].items():
            w.writerow([r["trail"], r["partial"], r["portion"], r["rebuy"],
                        r["trades"], round(r["net"], 2), round(r["per"], 4),
                        round(r["real"], 2), round(r["real_per"], 4),
                        round(r["drop5"], 2), r["syms"],
                        round(results["early"].get(key, {}).get("real", float("nan")), 2),
                        round(results["late"].get(key, {}).get("real", float("nan")), 2)])
    print(f"\nwrote {len(results['all']):,} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
