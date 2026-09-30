#!/usr/bin/env python3
"""W15-0033: re-quote FINISHED daily-futures books at IBKR costs. No re-run: costs are per trade.
new net(level k) = gross - qty * sides * (fee + k*tick_usd), k = 0/1/2 (low/mid/high); the old separate
'1 tick on stop fills' (slip) is dropped because the tick is charged on every fill (CRUDELE Amendment C).
Usage (from D:\\Trading):  .venv\\Scripts\\python.exe tools\\w15_0033_requote_ibkr.py
"""
import os, sys
import pandas as pd

OUT = os.environ.get("W15_OUT", r"D:\Trading\Claude outputs")
FEE = {"ES": .62, "RTY": .62, "CL": .77, "NG": 2.47, "6A": .51, "6B": .51, "6E": .51, "6J": 2.47,
       "GC": .97, "SI": .97, "HG": .97, "MTN": .57}
TICK = {"ES": 1.25, "RTY": .50, "CL": 1.00, "NG": 10.0, "6A": 1.0, "6B": .625, "6E": 1.25, "6J": 6.25,
        "GC": 1.0, "SI": 5.0, "HG": 1.25, "MTN": 100 / 64}
LV = {"low": 0, "mid": 1, "high": 2}

def money(x):
    return f"(${abs(x):,.0f})" if x < 0 else f"${x:,.0f}"

def requote(d, market_col=None, fixed_market=None):
    m = d[market_col] if market_col else pd.Series(fixed_market, index=d.index)
    fee = m.map(FEE); tick = m.map(TICK)
    sides = d["sides"] if "sides" in d else 2 + 2 * d["n_rolls"]
    for lv, k in LV.items():
        d[f"ib_{lv}"] = d["gross"] - d["qty"] * sides * (fee + k * tick)
    return d

def table(d, keys, title, out):
    out.append(f"\n{title}\n" + "-" * len(title))
    hdr = f"{'book':<34}{'n':>6}{'gross':>11} | {'old mid':>10}{'IBKR low':>10}{'IBKR mid':>10}{'IBKR high':>10}"
    out.append(hdr)
    for key, g in d.groupby(keys):
        name = " ".join(str(x) for x in (key if isinstance(key, tuple) else (key,)))
        old = g["net_mid"].sum()
        out.append(f"{name:<34}{len(g):>6}{money(g['gross'].sum()):>11} | {money(old):>10}"
                   f"{money(g['ib_low'].sum()):>10}{money(g['ib_mid'].sum()):>10}{money(g['ib_high'].sum()):>10}")

out = ["W15-0033 -- finished daily-futures books re-quoted at IBKR costs (dated 2026-09-30). No re-run.",
       "Levels: fee + 0/1/2 ticks per side. Fees: MES/M2K .62, MCL .77, NG/6J 2.47, M6x .51, MGC/SIL/MHG .97, MTN .57.",
       "Negatives in brackets. 'old mid' = the figure quoted in the RESULT doc ($1.25/side + 1 tick per stop fill)."]
for f, label in (("tl_v0_backtest_trades_20260928.csv", "TL-v0 / TL-v0-rev (W15-0014)"),
                 ("tl_v1_backtest_trades_20260929.csv", "TL-v1 (W15-0020)")):
    d = requote(pd.read_csv(os.path.join(OUT, f)), market_col="market")
    fr = d[d["sizing"] == "frac"]
    # ensemble = R3+R5+R8 sleeves summed
    sl = fr[fr["share"] == "sleeve"].copy(); sl["book"] = "ENSEMBLE(R3+R5+R8 sleeves) frac"
    table(sl, ["spec", "book"], f"{label}: verdict ensembles, fractional @ $22,129", out)
    table(fr[fr["share"] != "sleeve"], ["spec", "R", "share"], f"{label}: controls / singles, fractional", out)
    table(d[(d["sizing"] == "int") & (d["share"] == "sleeve")].assign(book="ENSEMBLE integer"),
          ["spec", "book"], f"{label}: integer-contract ensembles (reported beside)", out)
d = requote(pd.read_csv(os.path.join(OUT, "w15_0027_tl_v1_cl4h_trades_20260930.csv")), fixed_market="CL")
d["sides"] = 2 + 2 * d["n_rolls"]
table(d[d["part"].str.contains("sleeve|single")], ["spec", "part"], "TL-v1 CL 4-hour (W15-0027), priced as 1 MCL", out)
out.append("\nNot re-quoted here (no per-trade file in the repo, or already IBKR): CHARTMARK-v1/S (IBKR already), CRUDELE-3S/BREIT-CAP (un-run),"
           "\nMFLAG-v1 (delta of a closed FAIL; sign cannot change: skipping saves friction on both sides), W16 ES/NQ/MNQ books (need the IBKR ES/NQ table; see the amendment).")
path = os.path.join(OUT, "w15_0033_requote_ibkr_20260930.txt")
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
print("\n".join(out)); print("\nwritten:", path)
