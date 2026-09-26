#!/usr/bin/env python3
"""G2 -- HTF-Ben v1 pre-flight (training side only, NO EXIT PRICES, NO P&L).
W15-0011, REGISTERED_htf_ben_v1.md sec 0.3, sec 5.2.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.v1_preflight

WHAT THIS ANSWERS, AND WHAT IT DOES NOT: same discipline as v0's own
preflight.py (that module's docstring) -- there is no exit-price column or
P&L arithmetic anywhere in this file. It answers two things: (1) q_h, q_e
-- the 25th-percentile F1 thresholds sec 5.2 says must be written into
REGISTERED_htf_ben_v1.md as a PRE-RUN amendment BEFORE any run is scored,
computed here from training-side 4-hour bars only; (2) whether there are at
least 150 v1 entries on scenario B on the training side (sec 5.2's stop
rule) -- fewer, and the study stops as underpowered, reported as the
finding, back to Ben before any P&L.

E5 (one position at a time) IS NOT APPLIED HERE, same reason and same
caveat as v0's detect_v0/detect_c1: it needs to know when the prior trade
exited, which needs exit simulation, which this gate is forbidden from
doing. "entries" here is therefore an upper bound on what the full runner
will take.

VARIANTS RUN AT THIS GATE: v1 (full rules), v1-curl (E1a cross route only,
sec 2.4), v1-F1 (F1 disabled), v1-F2 (F2 disabled). v1-X (S1/S2 exits only,
no X1/X2) is NOT a separate variant here: X1/X2 are exit rules and G2 never
reads an exit price, so v1-X's entry counts are identical to v1's -- reported
as v1's own numbers relabelled, exactly as v0's own preflight.py relabels
v0-1H.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.htf import preflight as P
from strategy.htf import signals as SIG
from strategy.htf import tl_variant as TLV
from strategy.htf import v1_lines as V1L
from strategy.htf import v1_signals as V1S

TRAIN_START = P.TRAIN_START
TRAIN_END = P.TRAIN_END
MIN_ENTRIES = P.MIN_ENTRIES  # 150 -- sec 5.2's single-scenario stop rule

F1_PERCENTILE = 25          # sec 2.1 F1: 25th primary (20th/33rd in the grid)
CROSS_CONFIRM_WINDOW = 3    # E1a primary window (2 in the grid) -- Q4 "2-3 is fine"
T_OFFSETS = V1L.T_OFFSETS   # (2, 3)
SCENARIOS = ("B", "A-2H")   # sec 2.3: only B and A-2H are run for v1


def training_mask_4h(four_h_adj: pd.DataFrame) -> np.ndarray:
    d = pd.Series(four_h_adj["session"]).to_numpy()
    return (d >= TRAIN_START) & (d <= TRAIN_END)


def compute_percentiles(four_h_adj: pd.DataFrame, *, window: int = V1S.F1_WINDOW_4H,
                        pctl: float = F1_PERCENTILE):
    """(q_h, q_e, ratio_h, ratio_e, atr) -- sec 5.2: q_h/q_e are the
    `pctl`th percentile of F1's own rolling ratios, over TRAINING-SIDE
    4-hour bars only ('computed in G2 from indicators only'). ratio_h/
    ratio_e/atr are returned too so every variant run reuses the same
    arrays rather than recomputing the 4-hour geometry per call."""
    hist_4h, spread_4h = V1S.four_h_indicators(four_h_adj)
    _, _, atr = V1L.build_4h_lines(four_h_adj)
    ratio_h, ratio_e = V1S.f1_ratio_series(hist_4h, spread_4h, atr, window=window)
    train = training_mask_4h(four_h_adj)
    train_h = ratio_h[train]
    train_h = train_h[~np.isnan(train_h)]
    train_e = ratio_e[train]
    train_e = train_e[~np.isnan(train_e)]
    q_h = float(np.percentile(train_h, pctl)) if len(train_h) else float("nan")
    q_e = float(np.percentile(train_e, pctl)) if len(train_e) else float("nan")
    return q_h, q_e, ratio_h, ratio_e, atr


def detect_v1(entry_adj: pd.DataFrame, daily_adj: pd.DataFrame, four_h_adj: pd.DataFrame,
             *, scenario: str, q_h: float, q_e: float,
             warmup_bars: int = SIG.WARMUP_ENTRY_BARS,
             cross_window: int = CROSS_CONFIRM_WINDOW, t_offsets=T_OFFSETS,
             f1_window: int = V1S.F1_WINDOW_4H, f2_lookback: int = V1L.F2_LOOKBACK_4H,
             swing_LR: int = 2, curl_enabled: bool = True, f1_enabled: bool = True,
             f2_enabled: bool = True, line_low=None, line_high=None, atr=None,
             ratio_h=None, ratio_e=None) -> tuple[list[dict], dict]:
    """v1's entries and G2 counts: E1a (cross) / E1b (curl, gated by T and
    E2 at t) -> F1 -> F2 -> E3 (daily filter) -> end-of-session -> S1 stop.
    E5 not applied (module docstring). `curl_enabled`/`f1_enabled`/
    `f2_enabled` select the sec 2.4 ablation variants (v1-curl, v1-F1,
    v1-F2) without duplicating this whole walk three times.

    ORDER OF CHECKS -- AN ASSUMPTION FLAGGED, same spirit as v1_lines.py's
    and v1_signals.py's own notes: sec 2.1's table does not fix the order
    F1/F2/E3 are applied in once a confirmation bar c is found. This checks
    F1, then F2, then E3, top-to-bottom as the table lists them. A trigger
    failing more than one lands in whichever is checked first; the tests
    only assert the partition (every trigger accounted for exactly once),
    not which bucket a multiply-failing trigger lands in.

    Precomputed 4-hour geometry (`line_low`/`line_high`/`atr`/`ratio_h`/
    `ratio_e`) can be passed in so callers running several scenarios/
    variants off the same four_h_adj build it once (compute_percentiles
    already returns ratio_h/ratio_e/atr for exactly this reuse)."""
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    n = len(entry_adj)

    macd_line, signal_line, hist, ema9, ema21, spread = V1S.entry_chart_indicators(entry_adj)
    up = SIG.macd_cross_up(macd_line, signal_line)
    down = SIG.macd_cross_down(macd_line, signal_line)
    curl_long, curl_short = V1S.curl_trigger_series(hist)
    confirms_long, confirms_short = V1S.e2_confirms(ema9, spread)
    daily_dir = SIG.daily_filter_as_of(entry_adj, daily_adj, bar_hours)
    ready = SIG.entry_ready_mask(entry_adj, warmup_bars)
    swing_low = SIG.swing_lows(entry_adj["low_adj"], L=swing_LR, R=swing_LR).ffill()
    swing_high = SIG.swing_highs(entry_adj["high_adj"], L=swing_LR, R=swing_LR).ffill()
    last_bar = SIG.session_last_bar_mask(entry_adj, bar_hours)
    low_adj = entry_adj["low_adj"].to_numpy()
    high_adj = entry_adj["high_adj"].to_numpy()
    open_adj = entry_adj["open_adj"].to_numpy()

    if line_low is None or line_high is None or atr is None:
        line_low, line_high, atr = V1L.build_4h_lines(four_h_adj)
    if ratio_h is None or ratio_e is None:
        hist_4h, spread_4h = V1S.four_h_indicators(four_h_adj)
        ratio_h, ratio_e = V1S.f1_ratio_series(hist_4h, spread_4h, atr, window=f1_window)
    # .values, not .to_numpy(): a tz-aware Series' .to_numpy() returns
    # object dtype in this pandas version, which map_to_last_closed_4h's
    # own timedelta64 arithmetic can't use (W15-0007's tl_variant.py hit
    # the same bug -- see that module's docstring).
    four_h_t_open = four_h_adj["t_open"].values
    entry_t_open = entry_adj["t_open"].values
    t4_idx = TLV.map_to_last_closed_4h(entry_t_open, four_h_t_open)

    counts = {"triggers_cross": 0, "triggers_curl": 0, "curl_failing_t": 0,
             "lapsed": 0, "blocked_f1": 0, "blocked_f2": 0,
             "blocked_e3": 0, "blocked_end_of_session": 0,
             "voided": 0, "entries": 0}
    entries: list[dict] = []

    for i in range(n):
        if not ready[i]:
            continue

        is_up, is_down = bool(up.iloc[i]), bool(down.iloc[i])
        is_curl_long = curl_enabled and bool(curl_long.iloc[i])
        is_curl_short = curl_enabled and bool(curl_short.iloc[i])

        if is_up or is_down:
            direction = "long" if is_up else "short"
            counts["triggers_cross"] += 1
            confirms = confirms_long if direction == "long" else confirms_short
            c = None
            for off in range(1, cross_window + 1):
                j = i + off
                if j >= n:
                    break
                hist_ok = (hist.iloc[j] > 0) if direction == "long" else (hist.iloc[j] < 0)
                if bool(confirms.iloc[j]) and hist_ok:
                    c = j
                    break
            if c is None:
                counts["lapsed"] += 1
                continue
        elif is_curl_long or is_curl_short:
            direction = "long" if is_curl_long else "short"
            counts["triggers_curl"] += 1
            t4_trigger = int(t4_idx[i])
            if not V1L.t_condition(direction, t4_trigger, four_h_adj, line_low, line_high,
                                   atr, offsets=t_offsets):
                counts["curl_failing_t"] += 1
                continue
            e2_ok = bool((confirms_long if direction == "long" else confirms_short).iloc[i])
            if not e2_ok:
                counts["lapsed"] += 1
                continue
            c = i
        else:
            continue

        t4 = int(t4_idx[c])
        if f1_enabled and V1S.f1_blocked_at(t4, ratio_h, ratio_e, q_h, q_e):
            counts["blocked_f1"] += 1
            continue
        if f2_enabled and V1L.f2_direction_block(direction, t4, four_h_adj, line_low,
                                                  line_high, atr, lookback=f2_lookback):
            counts["blocked_f2"] += 1
            continue
        if daily_dir.iloc[c] != direction:
            counts["blocked_e3"] += 1
            continue
        fill_idx = c + 1
        if fill_idx >= n:
            counts["lapsed"] += 1
            continue
        if scenario in P.INTRADAY_SCENARIOS and bool(last_bar[fill_idx]):
            counts["blocked_end_of_session"] += 1
            continue
        fill_price = float(open_adj[fill_idx])
        stop = P._initial_stop(direction, fill_idx, fill_price, swing_low, swing_high,
                               low_adj, high_adj)
        if stop is None:
            counts["voided"] += 1
            continue
        counts["entries"] += 1
        rec = P._entry_record(entry_adj, fill_idx, direction, fill_price, stop, scenario,
                              bar_hours)
        rec["route"] = "cross" if (is_up or is_down) else "curl"
        entries.append(rec)

    return entries, counts


def stop_rule(v1_b_entries_training: int, min_required: int = MIN_ENTRIES) -> dict:
    """sec 5.2, verbatim: 'fewer than 150 v1 entries on B -> stop as
    underpowered, reported as the finding, and back to Ben before any
    P&L.' A single-scenario rule (unlike v0's AND-of-B-and-A2H in
    preflight.combine_underpowered) -- kept separate so the two studies'
    different stop conditions are not silently conflated."""
    underpowered = v1_b_entries_training < min_required
    return {"v1_B_entries_training": v1_b_entries_training,
           "min_required": min_required, "underpowered": underpowered}


def run(archive_1h) -> dict:
    """Load once; compute q_h/q_e from training-side 4-hour bars; run v1
    and the sec 2.4 ablations (v1-curl, v1-F1, v1-F2) on B and A-2H."""
    df_1h = B.load_1h(archive_1h)
    grids, daily_adj = P.prepare_grids(df_1h)
    four_h_adj = grids["4H"]

    q_h, q_e, ratio_h, ratio_e, atr = compute_percentiles(four_h_adj)
    line_low, line_high, _ = V1L.build_4h_lines(four_h_adj)

    variant_kwargs = {
        "v1": {},
        "v1-curl": {"curl_enabled": False},
        "v1-F1": {"f1_enabled": False},
        "v1-F2": {"f2_enabled": False},
    }
    report: dict = {"q_h": q_h, "q_e": q_e, "percentile": F1_PERCENTILE, "variants": {}}
    for variant, kwargs in variant_kwargs.items():
        report["variants"][variant] = {}
        for scenario in SCENARIOS:
            entry_adj = grids[P.SCENARIO_GRID[scenario]]
            entries, counts = detect_v1(
                entry_adj, daily_adj, four_h_adj, scenario=scenario, q_h=q_h, q_e=q_e,
                line_low=line_low, line_high=line_high, atr=atr,
                ratio_h=ratio_h, ratio_e=ratio_e, **kwargs)
            report["variants"][variant][scenario] = {
                "counts_full_history": counts,
                **P.summarize(entries, counts, scenario=scenario),
            }
    report["variants"]["v1-X"] = {
        "note": "identical to v1 at the entry-counting level (X1/X2 are exit "
                "rules; G2 reads no exit price). See variants.v1 for the numbers.",
    }
    v1_b_entries = report["variants"]["v1"]["B"]["totals"]["entries_training"]
    report["stop_rule"] = stop_rule(v1_b_entries)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G2: HTF-Ben v1 pre-flight (no P&L).")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    report = run(archive)
    print("G2 -- HTF-Ben v1 pre-flight (training side, no P&L, no exit prices)\n")
    print(f"q_h={report['q_h']:.4f}  q_e={report['q_e']:.4f}  "
          f"(F1 {report['percentile']}th percentile, training-side 4H bars)\n")
    for variant in ("v1", "v1-curl", "v1-F1", "v1-F2"):
        for scenario in SCENARIOS:
            t = report["variants"][variant][scenario]["totals"]
            print(f"{variant:8s} {scenario:5s}  cross={t['triggers_cross']:5d}  "
                  f"curl={t['triggers_curl']:5d}  curl_fail_T={t['curl_failing_t']:5d}  "
                  f"lapsed={t['lapsed']:5d}  f1_blk={t['blocked_f1']:5d}  "
                  f"f2_blk={t['blocked_f2']:5d}  e3_blk={t['blocked_e3']:5d}  "
                  f"eos_blk={t['blocked_end_of_session']:5d}  voided={t['voided']:4d}  "
                  f"entries(training)={t['entries_training']:5d}")
    sr = report["stop_rule"]
    print(f"\nstop rule (sec 5.2): v1 B entries(training)={sr['v1_B_entries_training']} "
          f"(need >= {sr['min_required']}) -> "
          f"{'UNDERPOWERED' if sr['underpowered'] else 'OK'}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nfull report: {a.out}")

    return 1 if sr["underpowered"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
