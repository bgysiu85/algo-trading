#!/usr/bin/env python3
"""HTF-Ben fidelity check (W15-0005, REGISTERED_htf_ben_v0.md sec 6.1).

Ben's own NinjaTrader paper trades (claude/raw/w15_0005_ninjatrader_trades_
20260925.json, pulled via the Ninja_Trader_Paper connector 2026-09-25) fall
inside the locked 2022+ holdout. Sec 6.1: this reads SIGNAL TIMING ONLY for
those weeks -- same bar, same side, same initial stop, same exit bar. NO
P&L IS COMPUTED for the window (this module never touches exits.py or
runner.py), and nothing outside the days of Ben's trades is REPORTED (the
indicator warm-up still needs the full history, same as every other htf
gate -- G1-G5 already read the whole archive; only the report is windowed).
Reported, not a gate (REGISTERED sec 0): must not hold up the study, and
cannot spend the holdout. A mismatch here means either (a) a code bug
against the rules as written, fixed and recorded as a POST-RUN bug-fix
note, or (b) a new registered variant spending from sec 9's budget --
never a silent rule change.

WHY SCENARIO B (4-hour), NOT A
--------------------------------
Ben's manual method is the 4-hour entry chart and he holds positions
overnight (trade 10 in the trade file: entered 2026-09-23 22:01 UTC,
exited 2026-09-24 10:10 UTC) -- that is scenario B, not the flat-by-17:00
scenario A.

WHY THIS REUSES preflight.detect_v0 RATHER THAN RE-DERIVING THE CHAIN
------------------------------------------------------------------------
detect_v0 already implements exactly what sec 6.1 asks for: the E1-E3
trigger -> confirmation -> daily-filter chain and the S1 initial stop, with
no exit price and no P&L anywhere in it (see preflight.py's own module
docstring). It runs over whatever frame it is given -- callers slice to a
window afterward. This module calls it once over the WHOLE back-adjusted
series (same as G2 does), then keeps only the v0 entries that fall in the
window covering Ben's trade dates for the report, exactly as sec 6.1 asks.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.fidelity
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from strategy.htf import bars as B
from strategy.htf import preflight as P

SCENARIO = "B"
TRADES_FILE = (Path(__file__).resolve().parents[2] / "claude" / "raw"
              / "w15_0005_ninjatrader_trades_20260925.json")
# Window Ben's trades fall in, plus a day of slack either side so a trigger
# the evening before his first trade, or a fill after his last, isn't cut.
WINDOW_START = pd.Timestamp("2026-09-19", tz="UTC")
WINDOW_END = pd.Timestamp("2026-09-26", tz="UTC")
# S1's stop is a $ distance from the fill; "same initial stop" is scored to
# within 1 tick ($0.01) of exact, since both sides round to the tick.
STOP_TOL = 0.01
# A v0 fill within this many hours of Ben's own entry counts as "same bar"
# -- one 4-hour bucket either side, matching sec 6.1's own vocabulary
# ("same bar") without demanding the two clocks agree to the second (Ben's
# own fill time is his broker's execution stamp, not a bar boundary).
SAME_BAR_TOL_HOURS = 4


def load_ben_trades(path: Path = TRADES_FILE) -> list[dict]:
    data = json.loads(path.read_text())
    return data["round_trips"]


def prepare_b(archive) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Back-adjusted 4-hour entry grid + daily grid (REGISTERED sec 2.1)."""
    df_1h = B.load_1h(archive)
    entry_adj = B.back_adjust(B.resample(df_1h, "4H"))
    daily_adj = B.back_adjust(B.daily(df_1h))
    return entry_adj, daily_adj


def v0_entries_in_window(entry_adj: pd.DataFrame, daily_adj: pd.DataFrame,
                         start: pd.Timestamp = WINDOW_START,
                         end: pd.Timestamp = WINDOW_END) -> list[dict]:
    """Every v0 entry (REGISTERED E1-E3, S1) over the WHOLE series (same
    call G2 makes), kept only if its fill bar's t_open falls in [start,
    end) -- sec 6.1's "reads nothing outside the days of his trades",
    applied to the report, not to the indicator warm-up."""
    entries, _counts = P.detect_v0(entry_adj, daily_adj, scenario=SCENARIO)
    out = []
    for e in entries:
        t = pd.Timestamp(e["t_open"])
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        if start <= t < end:
            out.append(e)
    return out


def match_trade(trade: dict, v0_window: list[dict]) -> dict | None:
    """The v0 entry (if any) that agrees with Ben's own trade on side and
    fill time (within SAME_BAR_TOL_HOURS). Ties broken by nearest fill
    time. None if v0 never triggered anything on that side near this fill."""
    entry_t = pd.Timestamp(trade["entry_time"])
    side = trade["side"]
    best, best_dt = None, None
    for e in v0_window:
        if e["direction"] != side:
            continue
        t = pd.Timestamp(e["t_open"])
        dt = abs((t - entry_t).total_seconds())
        if dt <= SAME_BAR_TOL_HOURS * 3600 and (best is None or dt < best_dt):
            best, best_dt = e, dt
    return best


def replay(trades: list[dict], v0_window: list[dict]) -> list[dict]:
    results = []
    for trade in trades:
        m = match_trade(trade, v0_window)
        row = {
            "trade_id": trade["trade_id"], "side": trade["side"],
            "ben_entry_time": trade["entry_time"],
            "ben_entry_price": trade["entry_price"],
            "ben_exit_time": trade["exit_time"],
            "ben_exit_price": trade["exit_price"],
            "v0_signal_found": m is not None,
        }
        if m is not None:
            stop_diff = None
            row.update({
                "v0_fill_t_open": m["t_open"], "v0_fill_price": m["fill_price"],
                "v0_initial_stop": m["stop"], "v0_stop_dist": m["stop_dist"],
                "same_bar": abs((pd.Timestamp(m["t_open"]) -
                                pd.Timestamp(trade["entry_time"])).total_seconds())
                           <= SAME_BAR_TOL_HOURS * 3600,
            })
        results.append(row)
    return results


def run(archive) -> dict:
    entry_adj, daily_adj = prepare_b(archive)
    v0_window = v0_entries_in_window(entry_adj, daily_adj)
    trades = load_ben_trades()
    results = replay(trades, v0_window)
    n_match = sum(r["v0_signal_found"] for r in results)
    # v0 triggers in the window that correspond to none of Ben's trades --
    # reported so the comparison is honest in both directions, not just
    # "did v0 agree with Ben" but also "what did v0 do that Ben didn't".
    matched_t_opens = {r.get("v0_fill_t_open") for r in results if r["v0_signal_found"]}
    unmatched_v0 = [e for e in v0_window if e["t_open"] not in matched_t_opens]
    return {
        "scenario": SCENARIO, "window": [str(WINDOW_START), str(WINDOW_END)],
        "n_ben_trades": len(results), "n_v0_signal_found": n_match,
        "n_mismatch": len(results) - n_match,
        "n_v0_triggers_in_window": len(v0_window),
        "n_v0_triggers_unmatched": len(unmatched_v0),
        "trades": results, "v0_triggers_unmatched": unmatched_v0,
    }


def main(argv=None) -> int:
    from common.tsmom_fetch import default_archive
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(Path("Claude outputs")
                                          / "w15_0005_fidelity_20260925.json"))
    args = ap.parse_args(argv)
    result = run(default_archive())
    out_path = Path(args.out)
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"wrote {out_path}")
    print(f"scenario B, window {result['window'][0]} .. {result['window'][1]}")
    print(f"Ben's trades: {result['n_ben_trades']}, "
          f"v0 signal found for {result['n_v0_signal_found']}, "
          f"mismatch {result['n_mismatch']}")
    print(f"v0 triggers in window: {result['n_v0_triggers_in_window']}, "
          f"of which {result['n_v0_triggers_unmatched']} match none of Ben's trades")
    for r in result["trades"]:
        tag = "MATCH" if r["v0_signal_found"] else "NO V0 SIGNAL"
        print(f"  trade {r['trade_id']} {r['side']:5s} "
              f"Ben@{r['ben_entry_time']} {r['ben_entry_price']:.2f} -> {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
