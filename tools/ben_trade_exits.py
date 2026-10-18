#!/usr/bin/env python3
"""W15-0058-style side study: Ben's discretionary MCL trades vs mechanical exits from the SAME entries. EXPLORATORY, not registered.

  Set-Location D:\\Trading
  .\\.venv\\Scripts\\python.exe tools\\ben_trade_exits.py

Inputs : var\\flex\\TradeZella_Live.csv (IBKR Flex executions, times in Sydney), Claude outputs\\mcl_bars_20261017.csv (5-min MCL, UTC).
Outputs: Claude outputs\\ben_trade_exits_20261018.txt and .csv

DECLARED BEFORE THE RESULTS WERE LOOKED AT (so nothing below is tuned on Ben's trades):
  * Round trip = flat-to-flat per contract month. Entry = Ben's size-weighted average entry price at the time of his FIRST fill.
  * Rules are exitmgr.rules unchanged (the code the live manager imports) on 5-minute bars. A short is run mirrored (prices negated).
  * Initial stop S = 2.0 x ATR(14, 5m) at the entry bar. R-MOM's minimum-range number is the median 5-min ATR (0.30 is a 1H figure).
    Everything else is the registered Params (ratchet arm 0.20, half profit).
  * Rule sets: B-STOP (S only), R-BEN, R-MOM, X-JUMP, B-V1 (CHARTMARK-v1's EMA trail + reversal). Time caps 120 min and 480 min.
  * Bars are another contract month, so each trade's bars are shifted by one constant (the median of fill - bar mid on that day).
  * The entry bar's high/low are clamped to the entry and its close: nothing before the fill may arm a rule.
  * Costs: Ben's actual commissions on his own entries; rules pay $0.86 commission + 1 tick on the exit; his own exits are as filled.
  * Trades before 2026-10-05 have no bars and are left out.
"""
import os
import numpy as np
import pandas as pd

from exitmgr import rules as R
from strategy.chartmark.data import indicators, make_frame
from strategy.exit_cmp.walk import walk

OUT = os.environ.get("W15_OUT", r"D:\Trading\Claude outputs")
LIVE = os.environ.get("LIVE_CSV", r"D:\Trading\var\flex\TradeZella_Live.csv")
BARS = os.path.join(OUT, "mcl_bars_20261017.csv")
SYD = 11            # hours ahead of UTC (AEDT from 4 Oct 2026); picked by fit, see report
MULT, TICK_USD, COMM = 100.0, 1.0, 0.86
STOP_ATR = 2.0
CAPS = {"120m": 24, "480m": 96}
RULES = ("B-STOP", "R-BEN", "R-MOM", "X-JUMP", "B-V1")


def money(x):
    return f"(${abs(x):,.0f})" if x < 0 else f"${x:,.0f}"


def load_trips():
    d = pd.read_csv(LIVE, low_memory=False)
    d["t"] = pd.to_datetime(d["Date/Time"], format="%Y-%m-%d;%H:%M:%S") - pd.Timedelta(hours=SYD)   # -> UTC
    d = d.sort_values(["t", "TradeID"]).reset_index(drop=True)
    d["q"] = d.Quantity.astype(float)
    d["px"] = d.Price.astype(float)
    d["comm"] = d.Commission.astype(float)
    trips = []
    for sym, g in d.groupby("Symbol"):
        pos, cur = 0.0, None
        for r in g.itertuples():
            if cur is None:
                cur, pos = [], 0.0
            cur.append(r)
            pos += r.q
            if abs(pos) < 1e-9:
                trips.append((sym, cur))
                cur = None
    return d, trips


def main():
    bars = pd.read_csv(BARS)
    bars["t"] = pd.to_datetime(bars.date, utc=True)
    bars = bars.sort_values("t").reset_index(drop=True)
    d, trips = load_trips()
    tb = bars.t.dt.tz_localize(None)
    # constant shift per day: fill price - bar mid, from every fill that day
    mid = (bars.high + bars.low) / 2
    ix = np.searchsorted(tb.to_numpy(), d.t.dt.floor("5min").to_numpy())
    ok = ix < len(bars)
    ix = np.where(ok, ix, 0)
    match = ok & (tb.to_numpy()[ix] == d.t.dt.floor("5min").to_numpy())
    d["basis"] = np.where(match, d.px - mid.to_numpy()[ix], np.nan)
    d["day"] = d.t.dt.date
    day_basis = d.groupby(["Symbol", "day"]).basis.median()
    lines = ["Ben's MCL trades vs mechanical exits from the same entries -- EXPLORATORY, not a registered test",
             f"fills {len(d)}, round trips {len(trips)}; bars 5-min {tb.min()} .. {tb.max()} UTC; sydney offset used: {SYD} h", ""]
    rows = []
    for sym, fl in trips:
        side = np.sign(fl[0].q)
        opens = [x for x in fl if np.sign(x.q) == side]
        closes = [x for x in fl if np.sign(x.q) != side]
        qty = sum(abs(x.q) for x in opens)
        entry = sum(abs(x.q) * x.px for x in opens) / qty
        exitp = sum(abs(x.q) * x.px for x in closes) / qty
        t_in, t_out = fl[0].t, closes[-1].t
        comm_open = sum(abs(x.comm) for x in opens)
        comm_all = sum(abs(x.comm) for x in fl)
        ben_gross = side * (exitp - entry) * qty * MULT
        ben_net = ben_gross - comm_all
        if t_in < tb.min() + pd.Timedelta(hours=1):
            continue
        key = (sym, fl[0].t.date())
        basis = day_basis.get(key, np.nan)
        if not basis == basis:
            basis = d[(d.Symbol == sym)].basis.median()
        b0 = bars.copy()
        for c in ("open", "high", "low", "close"):
            b0[c] = b0[c] + basis
        e = int(np.searchsorted(tb.to_numpy(), pd.Timestamp(t_in).floor("5min").to_numpy()))
        if side < 0:     # mirror: a short is a long in negated prices
            o, h, l, c = -b0.open, -b0.low, -b0.high, -b0.close
            ent = -entry
        else:
            o, h, l, c = b0.open, b0.high, b0.low, b0.close
            ent = entry
        o, h, l, c = (np.asarray(x, float).copy() for x in (o, h, l, c))
        h[e] = max(ent, c[e])
        l[e] = min(ent, c[e])
        fr = make_frame(b0.t, o, h, l, c, bars.volume)
        ind = indicators(fr)
        for nm in ("atr", "e9", "e21", "hist"):
            setattr(fr, nm, getattr(ind, nm))
        a0 = float(ind.atr[e - 1])
        s0 = ent - STOP_ATR * a0
        end_j = int(np.searchsorted(tb.to_numpy(), pd.Timestamp(t_out).floor("5min").to_numpy()))
        path_h = h[e:end_j + 1].max() if end_j >= e else ent
        path_l = l[e:end_j + 1].min() if end_j >= e else ent
        mfe = (path_h - ent) * qty * MULT                       # best the trade ever showed during Ben's hold
        mae = (ent - path_l) * qty * MULT
        medatr = float(np.nanmedian(ind.atr[max(0, e - 2000):e]))
        p = R.Params(mom_min_range=medatr)
        row = dict(entry_utc=pd.Timestamp(t_in), exit_utc=pd.Timestamp(t_out), sym=sym, side="long" if side > 0 else "short",
                   qty=qty, entry=entry, ben_exit=exitp, hold_min=(t_out - t_in).total_seconds() / 60,
                   ben_net=ben_net, mfe_during_hold=mfe, mae_during_hold=mae, atr5=a0)
        for cap_name, cap in CAPS.items():
            for rid in RULES:
                comps = R.build(rid, fr, e, ent, a0, s0, 0.01, p, None)
                ex = walk(fr, e, ent, a0, s0, comps, scenario="HOLD", sess_end=np.zeros(fr.n, bool), cap=cap, n=fr.n)
                gross = (ex.exit_px - ent) * qty * MULT                  # already in the long (mirrored) frame
                net = gross - comm_open - qty * COMM - qty * TICK_USD
                row[f"{rid}|{cap_name}"] = net
                row[f"{rid}|{cap_name}|why"] = ex.reason
                row[f"{rid}|{cap_name}|min"] = (ex.exit_j - e) * 5
        rows.append(row)
    T = pd.DataFrame(rows)
    T.to_csv(os.path.join(OUT, "ben_trade_exits_20261018.csv"), index=False)
    n = len(T)
    lines += [f"trades with bars: {n}   Ben: net {money(T.ben_net.sum())}, wins {(T.ben_net>0).sum()}, losses {(T.ben_net<=0).sum()}, "
              f"median hold {T.hold_min.median():.0f} min, mean {T.hold_min.mean():.0f} min",
              f"hindsight ceiling: sum of best-price-during-hold {money(T.mfe_during_hold.sum())} "
              f"(not achievable; it is the high of each trade); worst excursion {money(T.mae_during_hold.sum())}", ""]
    hdr = f"{'rule':9s}{'cap':>6s}{'net':>11s}{'D vs Ben':>11s}{'beats Ben':>10s}{'wins':>6s}{'median min':>11s}"
    for cap_name in CAPS:
        lines += [f"== cap {cap_name}", hdr, f"{'Ben':9s}{'':>6s}{money(T.ben_net.sum()):>11s}{'':>11s}{'':>10s}{(T.ben_net>0).sum():>6d}{T.hold_min.median():>11.0f}"]
        for rid in RULES:
            net = T[f"{rid}|{cap_name}"]
            lines.append(f"{rid:9s}{cap_name:>6s}{money(net.sum()):>11s}{money(net.sum() - T.ben_net.sum()):>11s}"
                         f"{int((net > T.ben_net).sum()):>7d}/{n:<2d}{int((net > 0).sum()):>6d}{T[f'{rid}|{cap_name}|min'].median():>11.0f}")
        lines.append("")
    lines += ["== per trade, cap 120m: net by Ben and by each rule (negatives in brackets)",
              f"{'entry (UTC)':17s}{'side':6s}{'qty':>4s}{'hold':>6s}{'Ben':>9s}" + "".join(f"{r:>9s}" for r in RULES)]
    for r in T.itertuples():
        lines.append(f"{r.entry_utc:%m-%d %H:%M}     {r.side:6s}{int(r.qty):>4d}{r.hold_min:>6.0f}{money(r.ben_net):>9s}"
                     + "".join(f"{money(T.loc[r.Index, f'{rid}|120m']):>9s}" for rid in RULES))
    txt = "\n".join(lines)
    with open(os.path.join(OUT, "ben_trade_exits_20261018.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
