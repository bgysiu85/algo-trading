#!/usr/bin/env python3
"""HTF-Ben v1 controls C1-C3, REGISTERED_htf_ben_v1.md sec 3. W15-0011.

Section 3, verbatim: "Controls (same bars, fills, sizing, costs, and v1's
exits S1/S2/X1/X2): C1 MACD cross alone (no E2, F1, F2, no curl route); C2
Donchian 20/10 as v0; C3 random entries, 1,000 seeded draws matched to v1's
trade count and long/short mix, p5/p50/p95."

C1  MACD cross alone, v1's own exits (S1/S2/X1/X2). Built as a fixed,
    documented set of kwargs into the EXISTING v1 engine
    (v1_preflight.detect_v1 / v1_runner.run_v1), not new entry-detection
    code: E1a's own cross-and-confirm logic never reads E2 in the first
    place -- E2 only gates E1b/curl (REGISTERED sec 2, E1b: "gated by T and
    E2 at t") -- so curl_enabled=False already removes the one route that
    touches E2, and f1_enabled=False/f2_enabled=False remove F1/F2. E3 (the
    daily filter) is v0's own unchanged rule and is not one of the three
    ablation-disabled checks (v1_preflight.detect_v1's own docstring lists
    only curl/F1/F2 as flag-gated) -- sec 3 does not say to remove it
    either, so C1 keeps it, exactly like every other v1 variant.

C2  Donchian 20/10, "as v0": controls.py's own detect_c2/simulate_c2,
    reused UNCHANGED. Its own channel exit (no stop, no trail) is the
    control's whole point -- REGISTERED_htf_ben_v0.md's own registration of
    it, carried over verbatim, sec 3 note included -- so this module does
    not touch it, just re-exports run_c2 under this module's own name for
    one consistent call surface alongside C1/C3 in the v1 report.

C3  Random entries, 1,000 seeded draws, matched to v1's OWN trade count and
    long/short mix (not v0's, unlike a casual re-read of "as v0" might
    suggest -- sec 3 is explicit: "matched to v1's trade count and
    long/short mix"). Reuses controls.py's own flat_pool/_draw_entries
    machinery (generic over any Trade list and any entry_adj -- neither
    reads anything v0-specific), but walks the draws through
    v1_runner.simulate_v1 (v1's own S1/S2/X1/X2) in place of
    runner.simulate, on the SAME entry_adj v1 itself ran on, so "flat"
    means flat relative to v1's actual trades, not v0's.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.htf import controls as CT
from strategy.htf import preflight as P
from strategy.htf import runner as R
from strategy.htf import signals as SIG
from strategy.htf import v1_exits as V1E
from strategy.htf import v1_preflight as V1P
from strategy.htf import v1_runner as V1R

C3_DRAWS = CT.C3_DRAWS

# C2 is v0's own control, unchanged (module docstring) -- re-exported so
# report wiring calls one v1_controls.run_c1/run_c2/run_c3 surface rather
# than reaching into controls.py directly for this one piece.
run_c2 = CT.run_c2


def run_c1(df_1h: pd.DataFrame, *, scenario: str, q_h: float, q_e: float,
          trail_trigger: float = V1E.TRAIL_TRIGGER,
          cross_window: int = V1P.CROSS_CONFIRM_WINDOW) -> tuple[list["R.Trade"], dict]:
    """C1: MACD cross alone (no E2/F1/F2/curl route), v1's own exits.
    q_h/q_e are still required parameters (v1_runner.run_v1's own
    signature) but never read: f1_enabled=False short-circuits
    detect_v1's F1 check before q_h/q_e are ever compared against
    anything -- see v1_preflight.detect_v1's `if f1_enabled and ...`
    guard. Passing the real registered values anyway (rather than NaN)
    costs nothing and avoids a caller having to know they are moot."""
    return V1R.run_v1(df_1h, scenario=scenario, q_h=q_h, q_e=q_e,
                      trail_trigger=trail_trigger, cross_window=cross_window,
                      curl_enabled=False, f1_enabled=False, f2_enabled=False)


def run_c3(df_1h: pd.DataFrame, *, scenario: str, v1_trades: list, symbol: str = "MCL",
          level: str = "mid", n_draws: int = C3_DRAWS, seed_prefix: str = "") -> dict:
    """1,000 seeded draws (seed = crc32(seed_prefix + str(draw_index))),
    matched to v1_trades' own count and long/short mix, walked through v1's
    own exits (v1_runner.simulate_v1). Returns net-$ percentiles plus the
    raw per-draw array, same shape as controls.run_c3."""
    grids, _ = P.prepare_grids(df_1h)
    hourly = grids["1H"]
    entry_adj = grids[P.SCENARIO_GRID[scenario]]
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    session_flatten = scenario in P.INTRADAY_SCENARIOS

    swing_low = SIG.swing_lows(entry_adj["low_adj"]).ffill()
    swing_high = SIG.swing_highs(entry_adj["high_adj"]).ffill()
    low_adj = entry_adj["low_adj"].to_numpy()
    high_adj = entry_adj["high_adj"].to_numpy()

    pool = CT.flat_pool(entry_adj, v1_trades)
    directions = [t.direction for t in v1_trades]

    nets = np.full(n_draws, np.nan)
    for d in range(n_draws):
        seed = zlib.crc32(f"{seed_prefix}{d}".encode()) & 0xFFFFFFFF
        rng = np.random.default_rng(seed)
        entries = CT._draw_entries(entry_adj, pool, directions, rng=rng, swing_low=swing_low,
                                   swing_high=swing_high, low_adj=low_adj, high_adj=high_adj)
        trades, _ = V1R.simulate_v1(entries, hourly, entry_adj, bar_hours=bar_hours,
                                    session_flatten=session_flatten)
        nets[d] = sum(t.net_pnl(symbol, level) for t in trades)

    return {
        "n_draws": n_draws, "pool_size": int(len(pool)), "n_trades_per_draw": len(directions),
        "p5": float(np.nanpercentile(nets, 5)), "p50": float(np.nanpercentile(nets, 50)),
        "p95": float(np.nanpercentile(nets, 95)), "nets": nets,
    }
