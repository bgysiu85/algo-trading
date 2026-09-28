#!/usr/bin/env python3
"""W16 DVP-v1: Conti's LITERAL drift-VWAP pullback (80/40 long, 80/50 short
points, 5-min trigger, his guardrails) on NQ, 2024-01-02 -> latest bar -- a
single out-of-sample check of his published claim. Spends the DVP holdout
window as candidate "DVP-v1-NQ". docs/research/REGISTERED_w16_drift_vwap_v1.md.
Board W16-0012 (decision W16-0010).

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.dvp_v1 --confirm-spend --out "D:\\Trading\\Claude outputs\\w16_0012_dvp_v1.json"

Without --confirm-spend it only prints what it would do and reads no bar
from 2024 on. The rule path is unchanged from DVP-v0's replication block
(strategy.w16.drift_vwap.generate_dvp_trades with p_ref=None).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.w16 import controls as CTRL
from strategy.w16 import drift_vwap as D
from strategy.w16 import dvp_holdout as H
from strategy.w16 import dvp_runner as DR
from strategy.w16 import runner as R
from strategy.w16.preflight import load_root_bars, session_frames

CANDIDATE = "DVP-v1-NQ"
MARKET = "NQ"
LEVEL = "L2"
LEVELS = ("L0", "L1", "L2", "L3")
MIN_TRADES = 300
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_PASS_PCT = 0.95
N_CONTROL_DRAWS = 1000
CONTI_WINDOW_END = "2026-08-02"          # "as of yesterday" in the video (sec 4, reported)
CONTI_CLAIMS = {"win_rate": 0.64, "avg_win_nq": 866.0, "avg_loss_nq": -1300.0, "trades_per_day": 2.8}
ACCOUNT_USD = R.ACCOUNT_USD


def price_nq(trades: list[dict], level: str) -> list[dict]:
    return [DR._price_trade_full_contract(t, level) for t in trades if not t.get("voided")]


def price_mnq(trades: list[dict], level: str) -> list[dict]:
    return R.price_all(trades, level)


def _stats(priced: list[dict], n_sessions: int | None = None) -> dict:
    s = R.summarize(priced)
    s["win_rate"] = (s["wins"] / s["n_trades"]) if s["n_trades"] else None
    if n_sessions:
        s["trades_per_session"] = s["n_trades"] / n_sessions
    return s


def c_d1_after_draw(real_trades: list[dict], cache: dict, draw_idx: int) -> list[dict]:
    """W16-0011's fixed random-timing control: same session, same side, same
    point distances; entry at a uniformly random 1-minute bar open that is
    5-min aligned, within the fill window, AT OR AFTER the real fill minute."""
    rng = CTRL.draw_rng(draw_idx)
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        entry = cache.get(rt["date"])
        if entry is None:
            continue
        minute_of_day, opens, highs, lows, candidates, flat_minute = entry
        fill_ts = pd.Timestamp(rt["fill_time"])
        real_min = fill_ts.hour * 60 + fill_ts.minute
        cands = candidates[(minute_of_day[candidates] >= real_min)
                           & ((minute_of_day[candidates] - 570) % 5 == 0)]
        if len(cands) == 0:
            continue
        fill_idx = int(cands[int(rng.integers(0, len(cands)))])
        fill_price = float(opens[fill_idx])
        direction = rt["direction"]
        stop_dist, target_dist = rt["stop_dist"], rt["target_dist"]
        if direction == "long":
            stop, target = fill_price - stop_dist, fill_price + target_dist
        else:
            stop, target = fill_price + stop_dist, fill_price - target_dist
        exit_price, exit_reason, _idx, _tie = D.fast_walk_stop_target_time_exit(
            minute_of_day, opens, highs, lows, fill_idx, direction, stop, target, flat_minute)
        out.append({"date": rt["date"], "market": rt["market"], "direction": direction,
                    "voided": False, "fill_price": fill_price, "exit_price": exit_price,
                    "fill_minute": int(minute_of_day[fill_idx]), "real_fill_minute": real_min,
                    "exit_reason": exit_reason, "entry_fill_kind": "market_or_stop",
                    "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop"})
    return out


def _pcts(vals: list[float]) -> dict:
    return {"n_draws": len(vals),
            "p5": float(np.percentile(vals, 5)) if vals else None,
            "p50": float(np.percentile(vals, 50)) if vals else None,
            "p95": float(np.percentile(vals, 95)) if vals else None}


def score(trades: list[dict], *, c_d3_nets_mnq: list[float] | None) -> dict:
    l2 = price_nq(trades, "L2")
    l3 = price_nq(trades, "L3")
    s2 = R.summarize(l2)
    halves = R.both_halves(l2)
    boot = R.bootstrap_by_month(l2, n_draws=BOOTSTRAP_DRAWS, seed=0)
    net_mnq = R.summarize(price_mnq(trades, "L2"))["net"]
    crit5 = None
    if c_d3_nets_mnq:
        crit5 = net_mnq > float(np.percentile(c_d3_nets_mnq, 95))
    criteria = {
        "1_net_positive": s2["net"] > 0,
        "2_both_halves_positive": halves["early"]["net"] > 0 and halves["late"]["net"] > 0,
        "3_net_positive_at_l3": R.summarize(l3)["net"] > 0,
        "4_month_bootstrap_ge_95pct": (boot["pct_net_positive"] is not None
                                       and boot["pct_net_positive"] >= BOOTSTRAP_PASS_PCT),
        "5_beats_c_d3_p95": crit5,
        "6_min_trades": s2["n_trades"] >= MIN_TRADES,
    }
    computed = [v for v in criteria.values() if v is not None]
    criteria["passes_all_computed"] = bool(computed) and all(computed)
    return {"criteria": criteria, "both_halves_nq_l2": halves,
            "bootstrap": {"pct_net_positive": boot["pct_net_positive"], "n_draws": BOOTSTRAP_DRAWS,
                          "pass_threshold": BOOTSTRAP_PASS_PCT},
            "net_mnq_l2": net_mnq}


def run(archive, *, n_control_draws: int = N_CONTROL_DRAWS, progress: bool = True) -> dict:
    df_1m = load_root_bars(archive, MARKET)
    frames = session_frames(df_1m)
    all_dates = DR.trading_dates(frames)
    dates, n_train_side, label = H.split_dates(all_dates, spend=True, candidate=CANDIDATE)
    dates = sorted(dates)

    trades = D.generate_dvp_trades(frames, MARKET, dates, p_ref=None, loss_rule="total",
                                   scale=1.0, trigger_minutes=5)
    live = [t for t in trades if not t.get("voided")]
    n_sessions = len(dates)

    by_level_nq = {lvl: _stats(price_nq(trades, lvl), n_sessions) for lvl in LEVELS}
    by_level_mnq = {lvl: _stats(price_mnq(trades, lvl), n_sessions) for lvl in ("L1", "L2", "L3")}
    l2_nq = price_nq(trades, "L2")

    c_d3 = c_d1a = None
    c_d3_nets = None
    if n_control_draws:
        c_d3_nets = DR.compute_c_d3(trades, frames, p_ref=None, n_draws=n_control_draws,
                                    progress=progress)
        c_d3 = _pcts(c_d3_nets)
        cache = DR._session_arrays_cache(frames, {t["date"] for t in live})
        nets = []
        for i in range(n_control_draws):
            nets.append(R.summarize(R.price_all(c_d1_after_draw(trades, cache, i), LEVEL))["net"])
            if progress and (i + 1) % 100 == 0:
                print(f"    C-D1-after: {i + 1}/{n_control_draws} draws")
        c_d1a = _pcts(nets)

    result = {
        "candidate": CANDIDATE, "market": MARKET, "date_side": label,
        "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
        "n_sessions": n_sessions, "n_trades": len(live),
        "n_voided": sum(1 for t in trades if t.get("voided")),
    }
    result.update(score(trades, c_d3_nets_mnq=c_d3_nets))
    result["by_level_per_nq"] = by_level_nq
    result["by_level_per_mnq"] = by_level_mnq
    result["conti_claims"] = CONTI_CLAIMS
    s = by_level_nq["L2"]
    result["break_even_win_rate_l2"] = DR.break_even_win_rate(s["avg_win"], s["avg_loss"])
    result["by_year_nq_l2"] = {y: _stats(rows) for y, rows in _group_year(l2_nq).items()}
    result["conti_window_nq_l2"] = _stats([t for t in l2_nq if t["date"] <= CONTI_WINDOW_END])
    result["after_video_nq_l2"] = _stats([t for t in l2_nq if t["date"] > CONTI_WINDOW_END])
    result["exit_reasons"] = dict(Counter(t["exit_reason"] for t in l2_nq))
    result["same_bar_ties"] = sum(1 for t in live if t.get("same_bar_tie"))
    result["long_short_nq_l2"] = {
        side: _stats([t for t in l2_nq if t["direction"] == side]) for side in ("long", "short")}
    result["control_c_d3_per_mnq"] = c_d3
    result["control_c_d1_after_per_mnq"] = c_d1a
    result["account_view_mnq"] = R.account_view(price_mnq(trades, "L2"), "DVP", MARKET,
                                                account_usd=ACCOUNT_USD)
    result["sample_trades_nq_l2"] = R.sample_trades(l2_nq)
    scaled = D.generate_dvp_trades(frames, MARKET, dates, p_ref=D.P_REF_NQ, loss_rule="total")
    result["reported_dvp_v0_scaled_rule_mnq_l2"] = _stats(price_mnq(scaled, "L2"))
    return result


def _group_year(priced: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for t in priced:
        out.setdefault(t["date"][:4], []).append(t)
    return dict(sorted(out.items()))


def _d(x) -> str:
    if x is None:
        return "n/a"
    return f"(${abs(x):,.2f})" if x < 0 else f"${x:,.2f}"


def txt_report(r: dict) -> str:
    L = [f"=== W16 DVP-v1 -- Conti literal rule, OUT-OF-SAMPLE {r['first_date']} -> {r['last_date']} ===",
         f"ledger: {r['date_side']} (candidate {r['candidate']})",
         f"sessions: {r['n_sessions']}  trades: {r['n_trades']}  voided: {r['n_voided']}", ""]
    for lvl, s in r["by_level_per_nq"].items():
        wr = f"{s['win_rate']:.1%}" if s["win_rate"] is not None else "n/a"
        L.append(f"[per 1 NQ, {lvl}] n={s['n_trades']} win={wr} gross={_d(s['gross'])} "
                 f"cost={_d(s['cost'])} net={_d(s['net'])} avg_win={_d(s['avg_win'])} "
                 f"avg_loss={_d(s['avg_loss'])} max_dd={_d(s['max_drawdown'])}")
    s = r["by_level_per_mnq"]["L2"]
    L.append(f"[per 1 MNQ, L2] net={_d(s['net'])} max_dd={_d(s['max_drawdown'])}")
    L.append(f"break-even win rate (NQ, L2): {r['break_even_win_rate_l2']}")
    L.append(f"Conti claims: {r['conti_claims']}")
    L.append("")
    L.append("--- criteria ---")
    for k, v in r["criteria"].items():
        L.append(f"  {k}: {v}")
    L.append(f"bootstrap: {r['bootstrap']}")
    L.append(f"halves (NQ, L2): early {_d(r['both_halves_nq_l2']['early']['net'])} / "
             f"late {_d(r['both_halves_nq_l2']['late']['net'])} (split {r['both_halves_nq_l2']['split_date']})")
    L.append(f"C-D3 random side (per MNQ): {r['control_c_d3_per_mnq']}")
    L.append(f"C-D1-after random time at/after signal (per MNQ): {r['control_c_d1_after_per_mnq']}")
    L.append("")
    for y, s in r["by_year_nq_l2"].items():
        L.append(f"  {y}: n={s['n_trades']} win={s['win_rate']:.1%} net={_d(s['net'])}")
    L.append(f"Conti window (to {CONTI_WINDOW_END}): {_d(r['conti_window_nq_l2']['net'])} on {r['conti_window_nq_l2']['n_trades']}")
    L.append(f"after his video: {_d(r['after_video_nq_l2']['net'])} on {r['after_video_nq_l2']['n_trades']}")
    L.append(f"exit reasons: {r['exit_reasons']}")
    L.append(f"DVP-v0 scaled rule, same window (MNQ, L2): {_d(r['reported_dvp_v0_scaled_rule_mnq_l2']['net'])}")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="W16 DVP-v1 out-of-sample run (spends the DVP holdout).")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--confirm-spend", action="store_true",
                    help="Required. Records the DVP holdout as spent by DVP-v1-NQ, then reads 2024+.")
    ap.add_argument("--n-control-draws", type=int, default=N_CONTROL_DRAWS)
    a = ap.parse_args(argv)

    rec = H.read_ledger()
    if not a.confirm_spend:
        print("DVP-v1 would spend the DVP holdout (from "
              f"{H.LOCK_FROM}) as {CANDIDATE!r} and read NQ from that date on.")
        print(f"ledger now: {'SPENT by ' + rec['candidate'] if rec else 'UNSPENT'}")
        print("Nothing read. Re-run with --confirm-spend to do it (once).")
        return 0

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()
    result = run(archive, n_control_draws=a.n_control_draws)
    txt = txt_report(result)
    print(txt)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        a.out.with_suffix(".txt").write_text(txt, encoding="utf-8")
        print(f"full report: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
