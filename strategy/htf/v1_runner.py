#!/usr/bin/env python3
"""HTF-Ben v1 runner: turns v1_preflight's independently-scored candidates
into a real, E5-enforced trade ledger with raw-series dollar P&L, using
v1_exits' own X1/X2-plus-S1/S2 walk. W15-0011, REGISTERED_htf_ben_v1.md
sec 2.2. Mirrors strategy/htf/runner.py's own run_v0/simulate exactly (same
E5 one-at-a-time enforcement, same roll/cost bookkeeping, same Trade shape
-- reused directly from runner.py, unchanged); the only difference is the
exit call itself and what it needs: v1_exits.simulate_exit_v1 requires each
candidate's own entry-chart row position (so it knows which bars are
'after the fill bar' for X1/X2) and the entry chart's X1/X2 signal arrays,
built once per scenario from v1_signals' hist/EMA9.
"""
from __future__ import annotations

import pandas as pd

from strategy.htf import bars as B
from strategy.htf import exits as EX
from strategy.htf import preflight as P
from strategy.htf import runner as R
from strategy.htf import v1_exits as V1E
from strategy.htf import v1_preflight as V1P
from strategy.htf import v1_signals as V1S

Trade = R.Trade  # identical shape; v1 only changes how a trade's exit is produced


def _entry_chart_index_lookup(entry_adj: pd.DataFrame) -> dict:
    """{t_open: row position in entry_adj}. Every v1 candidate's own t_open
    is an exact entry_adj row by construction (v1_preflight.detect_v1
    builds fill_idx as a position into entry_adj itself), so an exact match
    always exists; a caller passing a candidate from a DIFFERENT entry_adj
    is a bug, surfaced by the KeyError below, not silently mismapped."""
    return {pd.Timestamp(t): i for i, t in enumerate(entry_adj["t_open"])}


def simulate_v1(entries: list[dict], hourly: pd.DataFrame, entry_adj: pd.DataFrame, *,
                bar_hours: int, session_flatten: bool,
                trail_trigger: float = V1E.TRAIL_TRIGGER,
                x2_bars: int = 1) -> tuple[list[R.Trade], int]:
    """Same E5 walk as runner.simulate (blocked_until, in time order),
    calling v1_exits.simulate_exit_v1 in place of exits.simulate_exit.
    x2_bars: 1 (primary) or 2 (neighbour-grid variant, sec 3) -- passed
    straight through to v1_exits.x_signal_series."""
    macd_line, signal_line, hist, ema9, ema21, spread = V1S.entry_chart_indicators(entry_adj)
    x1_long, x1_short, x2_long, x2_short = V1E.x_signal_series(hist, ema9, x2_bars=x2_bars)
    entry_lookup = V1E.entry_bar_lookup(entry_adj)
    t_open_lookup = _entry_chart_index_lookup(entry_adj)

    trades: list[R.Trade] = []
    n_ignored = 0
    blocked_until: pd.Timestamp | None = None

    for e in entries:
        t_open = pd.Timestamp(e["t_open"])
        if blocked_until is not None and t_open <= blocked_until:
            n_ignored += 1
            continue
        fill_entry_idx = t_open_lookup[t_open]
        start_pos = EX.find_start_pos(hourly, t_open)
        fill_adj = float(hourly["open_adj"].iloc[start_pos])
        stop_dist = float(e["stop_dist"])
        direction = e["direction"]
        initial_stop_adj = (fill_adj - stop_dist) if direction == "long" else (fill_adj + stop_dist)

        outcome = V1E.simulate_exit_v1(
            hourly, entry_lookup, start_pos=start_pos, fill_entry_idx=fill_entry_idx,
            direction=direction, fill_price=fill_adj, initial_stop=initial_stop_adj,
            bar_hours=bar_hours, session_flatten=session_flatten,
            x1_long=x1_long, x1_short=x1_short, x2_long=x2_long, x2_short=x2_short,
            trail_trigger=trail_trigger)

        offset = hourly["adj_offset"].to_numpy()
        fill_raw = fill_adj - float(offset[start_pos])
        exit_raw = outcome.exit_price - float(offset[outcome.exit_pos])
        exit_t = hourly["t_open"].iloc[outcome.exit_pos]
        n_rolls = R._count_rolls(hourly, start_pos, outcome.exit_pos)

        trades.append(R.Trade(
            session=str(e["session"]), direction=direction, entry_t=t_open,
            fill_adj=fill_adj, fill_raw=fill_raw, stop_dist=stop_dist,
            initial_stop_adj=initial_stop_adj, start_pos=start_pos,
            exit_pos=outcome.exit_pos, exit_t=exit_t,
            exit_price_adj=outcome.exit_price, exit_price_raw=exit_raw,
            exit_reason=V1E.REASONS[outcome.reason], trail_started=outcome.trail_started,
            n_rolls=n_rolls,
        ))
        blocked_until = exit_t

    return trades, n_ignored


def run_v1(df_1h: pd.DataFrame, *, scenario: str, q_h: float, q_e: float,
          trail_trigger: float = V1E.TRAIL_TRIGGER,
          cross_window: int = V1P.CROSS_CONFIRM_WINDOW,
          curl_enabled: bool = True, f1_enabled: bool = True, f2_enabled: bool = True,
          ) -> tuple[list[R.Trade], dict]:
    """v1, or one of the sec 2.4 ablations (v1-curl/v1-F1/v1-F2 via the
    matching flag), one scenario, whole archive (caller slices to
    training/holdout by each trade's own session, as preflight.summarize
    already does for the entry-only counts). v1-X (S1/S2 only, no X1/X2) is
    NOT a flag here -- see run_v1_no_signal_exits, which reuses v0's own
    exits.simulate_exit unchanged rather than threading a fourth boolean
    through this function's exit call."""
    grids, daily_adj = P.prepare_grids(df_1h)
    hourly = grids["1H"]
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    entry_adj = grids[P.SCENARIO_GRID[scenario]]
    four_h_adj = grids["4H"]
    entries, counts = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario=scenario,
                                    q_h=q_h, q_e=q_e, cross_window=cross_window,
                                    curl_enabled=curl_enabled, f1_enabled=f1_enabled,
                                    f2_enabled=f2_enabled)
    session_flatten = scenario in P.INTRADAY_SCENARIOS
    trades, n_ignored = simulate_v1(entries, hourly, entry_adj, bar_hours=bar_hours,
                                    session_flatten=session_flatten, trail_trigger=trail_trigger)
    counts = dict(counts)
    counts["ignored_in_position"] = n_ignored
    counts["trades_taken"] = len(trades)
    return trades, counts


def run_v1_no_signal_exits(df_1h: pd.DataFrame, *, scenario: str, q_h: float, q_e: float,
                           trail_trigger: float = EX.TRAIL_TRIGGER) -> tuple[list[R.Trade], dict]:
    """v1-X, REGISTERED sec 2.4: v1's own entries, S1/S2 only (no X1/X2) --
    reuses exits.simulate_exit and runner.simulate (v0's own walk)
    unchanged, since with no signal layer this IS v0's exit walk."""
    grids, daily_adj = P.prepare_grids(df_1h)
    hourly = grids["1H"]
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    entry_adj = grids[P.SCENARIO_GRID[scenario]]
    four_h_adj = grids["4H"]
    entries, counts = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario=scenario,
                                    q_h=q_h, q_e=q_e)
    session_flatten = scenario in P.INTRADAY_SCENARIOS
    trades, n_ignored = R.simulate(entries, hourly, bar_hours=bar_hours,
                                   session_flatten=session_flatten, trail_trigger=trail_trigger)
    counts = dict(counts)
    counts["ignored_in_position"] = n_ignored
    counts["trades_taken"] = len(trades)
    return trades, counts
