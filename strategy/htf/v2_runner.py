#!/usr/bin/env python3
"""HTF-Ben v2 runner: v1's entries (unchanged) walked through v0's own
S1/S2 stop/trail exits (unchanged), with v1's X1/X2 signal exits removed
entirely. W15-0021, REGISTERED_htf_ben_v2.md sec 2.1-2.2.

WHY THIS IS A NEW FILE RATHER THAN A NEW FLAG ON v1_runner.py
--------------------------------------------------------------
v1_runner.run_v1_no_signal_exits already IS this recombination -- it is the
exact call that produced the $3,956.12/286-trade v1-X ablation number
REGISTERED_htf_ben_v2.md sec 0.2 is built from (v1's own entries via
V1P.detect_v1, walked through runner.simulate/exits.simulate_exit, v0's
unmodified S1/S2/S4). run_v2 below is that same call, kept here under v2's
own name rather than reused directly from v1_runner, for two reasons: (1)
sec 2.4's "None" (no variants) still needs sec 3.6's fresh C1 control,
which requires curl_enabled/f1_enabled/f2_enabled passthrough that
run_v1_no_signal_exits does not expose (it always calls detect_v1 at its
defaults); (2) v2 is registered as its OWN hypothesis (sec 0.4: "a rule
change discovered from a result is a new, separately pre-registered
hypothesis, not an amendment to v1") -- v2's own report/controls/holdout
should call v2's own named engine, not reach into v1_runner's private
implementation detail, so a future edit to v1's ablation table cannot
silently change what v2 scores against.

v1_runner.py itself is NOT edited: run_v1_no_signal_exits keeps meaning
exactly what it always has (v1's sec 2.4 reported ablation, inside v1's own
report). run_v2 below is a second, independent caller of the same
underlying primitives (v1_preflight.detect_v1, runner.simulate), not a
wrapper around v1_runner's function -- so a future change to
run_v1_no_signal_exits's own signature cannot silently change v2's engine
underneath it. At its defaults (no ablation flags, registered swing_LR/
trail_trigger), run_v2 is functionally identical to run_v1_no_signal_exits
-- proven by equivalence in tests/strategy/htf/test_v2_runner.py, not just
asserted here.
"""
from __future__ import annotations

import pandas as pd

from strategy.htf import bars as B
from strategy.htf import exits as EX
from strategy.htf import preflight as P
from strategy.htf import runner as R
from strategy.htf import v1_preflight as V1P

# q_h/q_e are inherited from v1 Amendment C (REGISTERED_htf_ben_v2.md sec
# 2.1), not recomputed here -- callers pass them in explicitly (same
# convention as v1_runner.run_v1) so there is exactly one place
# (v2_preflight.py) that reads the registered constants.


def run_v2(df_1h: pd.DataFrame, *, scenario: str, q_h: float, q_e: float,
          trail_trigger: float = EX.TRAIL_TRIGGER,
          cross_window: int = V1P.CROSS_CONFIRM_WINDOW,
          swing_LR: int = 2,
          curl_enabled: bool = True, f1_enabled: bool = True, f2_enabled: bool = True,
          ) -> tuple[list[R.Trade], dict]:
    """v2: v1's entries (V1P.detect_v1, unchanged rules) walked through
    v0's own exits.simulate_exit/runner.simulate (S1/S2/S4 only -- no X1/
    X2, module docstring). At its defaults this is functionally identical
    to v1_runner.run_v1_no_signal_exits (same detect_v1 call, same
    runner.simulate call). The curl_enabled/f1_enabled/f2_enabled/
    swing_LR kwargs exist only so v2_controls.run_c1 (sec 3.6: MACD cross
    alone, v2's own exits) and v2_grid.py (sec 5.3: swing L/R neighbour
    dimension) can reach the same engine without duplicating this
    function."""
    grids, daily_adj = P.prepare_grids(df_1h)
    hourly = grids["1H"]
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    entry_adj = grids[P.SCENARIO_GRID[scenario]]
    four_h_adj = grids["4H"]
    entries, counts = V1P.detect_v1(
        entry_adj, daily_adj, four_h_adj, scenario=scenario, q_h=q_h, q_e=q_e,
        cross_window=cross_window, swing_LR=swing_LR,
        curl_enabled=curl_enabled, f1_enabled=f1_enabled, f2_enabled=f2_enabled)
    session_flatten = scenario in P.INTRADAY_SCENARIOS
    trades, n_ignored = R.simulate(entries, hourly, bar_hours=bar_hours,
                                   session_flatten=session_flatten, trail_trigger=trail_trigger)
    counts = dict(counts)
    counts["ignored_in_position"] = n_ignored
    counts["trades_taken"] = len(trades)
    return trades, counts
