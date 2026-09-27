#!/usr/bin/env python3
"""HTF-Ben v2 controls C1-C3, REGISTERED_htf_ben_v2.md sec 3.6. W15-0021.

Sec 3.6, verbatim: "C1 (v2): MACD cross alone ... paired with v2's own
exits (S1/S2 only)... C2 (v2): Donchian 20/10 ... exactly as v0 defined
it ... Re-run inside v2's own backtest pass rather than importing v1's
$5,163.50/594 trades... C3 (v2): 1,000 seeded random-entry draws ...
matched to v2's own realized trade count and long/short mix -- not v1's
293 -- same v0 S1/S2 exits." Every control here is walked through v0's own
exit machinery (exits.simulate_exit / runner.simulate) -- NEVER v1's
X1/X2-carrying simulate_v1 -- because v2 itself has no signal exit to
control for; this is the one place v2_controls.py's shape diverges from
v1_controls.py's (which wired C1/C3 through v1's own simulate_v1, sec 3
of REGISTERED_htf_ben_v1.md).

C1  MACD cross alone (curl_enabled=f1_enabled=f2_enabled=False), v2's own
    engine (v2_runner.run_v2) -- a fixed, documented set of kwargs into the
    EXISTING v2 engine, not new entry-detection code, same reasoning as
    v1_controls.run_c1's own docstring.

C2  Donchian 20/10, "exactly as v0 defined it": controls.py's own
    detect_c2/simulate_c2, reused UNCHANGED and re-exported under this
    module's name (identical re-export to v1_controls.run_c2 -- sec 3.6:
    "self-contained and unaffected by v2's entry/exit choice"). Re-running
    it here (rather than reaching for v1's own $5,163.50/594-trade number)
    is deliberate (sec 0.3, sec 3.6): the dollar figure is expected to come
    out identical to v1's C2 run since the strategy and data are the same
    either way, but v2's own gates stand on their own file, not on trust in
    a different registration's run.

C3  Random entries, 1,000 seeded draws, matched to v2's OWN trade count and
    long/short mix, walked through v0's own exits.simulate_exit/
    runner.simulate -- controls.py's own flat_pool/_draw_entries/run_c3 are
    already fully generic over any Trade list and any entry_adj (neither
    reads anything v0-specific -- controls.py's own module docstring), and
    v0's run_c3 already walks its draws through runner.simulate, which is
    exactly v2's own exit walk too. So v2's C3 needs no new draw/walk code
    at all -- only a v2-named wrapper so report wiring calls one
    v2_controls.run_c1/run_c2/run_c3 surface and the `v2_trades` kwarg name
    does not read as v0's own hypothesis trades.
"""
from __future__ import annotations

from strategy.htf import controls as CT
from strategy.htf import exits as EX
from strategy.htf import v1_preflight as V1P
from strategy.htf import v2_runner as V2R

C3_DRAWS = CT.C3_DRAWS

# C2 is v0's own control, unchanged (module docstring) -- re-exported so
# report wiring calls one v2_controls.run_c1/run_c2/run_c3 surface rather
# than reaching into controls.py directly for this one piece. Identical
# re-export to v1_controls.run_c2 -- same function, same object.
run_c2 = CT.run_c2


def run_c1(df_1h, *, scenario: str, q_h: float, q_e: float,
          trail_trigger: float = EX.TRAIL_TRIGGER,
          cross_window: int = V1P.CROSS_CONFIRM_WINDOW):
    """C1: MACD cross alone (no E2/F1/F2/curl route), v2's own exits
    (S1/S2 only, via v2_runner.run_v2). q_h/q_e are still required
    (v2_runner.run_v2's own signature) but never read once f1_enabled is
    False -- see v1_preflight.detect_v1's `if f1_enabled and ...` guard,
    same note as v1_controls.run_c1's own docstring."""
    return V2R.run_v2(df_1h, scenario=scenario, q_h=q_h, q_e=q_e,
                      trail_trigger=trail_trigger, cross_window=cross_window,
                      curl_enabled=False, f1_enabled=False, f2_enabled=False)


def run_c3(df_1h, *, scenario: str, v2_trades: list, symbol: str = "MCL",
          level: str = "mid", n_draws: int = C3_DRAWS, seed_prefix: str = ""):
    """1,000 seeded draws (seed = crc32(seed_prefix + str(draw_index))),
    matched to v2_trades' own count and long/short mix, walked through
    v0's own exits (controls.run_c3, unchanged -- see module docstring).
    Returns net-$ percentiles plus the raw per-draw array, same shape as
    controls.run_c3 / v1_controls.run_c3."""
    return CT.run_c3(df_1h, scenario=scenario, v0_trades=v2_trades, symbol=symbol,
                     level=level, n_draws=n_draws, seed_prefix=seed_prefix)
