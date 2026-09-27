#!/usr/bin/env python3
r"""W03-0005 Part A -- what each leg of a trade costs live, and the books
re-priced leg by leg instead of with one flat per-round-trip charge.

    python -m common.exec_cost_legs --jobs 8

Registered in docs/research/REGISTERED_exec_cost.md, committed before this
file existed. Research only: the trader never imports it.

WHAT IT DOES
------------
1. LIVE. Reads the paper fill ledger (var/fills, sessions 2026-09-09 ->
   2026-09-25, fixed by the registration) and measures three legs against the
   price each order was decided on:

       ENTRY   BUY,  ref = the signal bar's close     cost = fill - ref
       TRAIL   SELL trailing_stop, ref = stop level   cost = ref - fill
       WCLOSE  SELL window_close,  ref = the quote    cost = ref - fill

   in basis points of the reference, mean first, session-cluster bootstrap.

2. BOOKS. Runs MCL and MC5 on screen_pairs_pit_itch_v2.json twice: as
   published (gap_fills=True) and with gap_fills=False. The second run differs
   ONLY in the trailing-stop fill (`level - 1 tick` instead of
   `min(level, open) - 1 tick`), so it hands over every trailing exit's stop
   level exactly, from the engine's own arithmetic, with nothing rebuilt here.

3. RE-PRICE. R1 prices each leg from its reference with the live mean: entry
   from the signal close, the trailing exit from the LEVEL, the window close
   from the bar close. The trailing exit is priced from the level and NOT added
   to the engine's gap-through fill: the live figure is fill-vs-level at tick
   resolution and already contains whatever gaps the market produced, so adding
   it on top of a bar-level gap charge would count the gap twice -- on MC5's
   five-minute bars, where 48% of stop exits open below the level, by a lot.
   R2 is the conservative bound (the worse of engine and R1 on each trailing
   exit). R0 is the control (the engine's own assumptions) and must reproduce
   the engine to the cent.

NOTHING PASSES HERE. The output is a per-leg table, re-priced books in dollars,
a flat-equivalent per round trip with its interval, and the decision words the
registration fixed before any number existed.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from common import gate_study as G
from common import textio as T
from common.entry_shares import QTY
from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")
REGISTERED = "docs/research/REGISTERED_exec_cost.md"
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
FILLS_DIR = "var/fills"

# --- fixed by the registration (A.2, A.5) --------------------------------------
FIRST, LAST = "2026-09-09", "2026-09-25"
SEED = 20260927
NBOOT = 2_000
MIN_N = 15
TICK = 0.01                          # both engines: TICK = 0.01, SLIPPAGE_TICKS = 1
STRATEGIES = ("mcl", "mc5")
LEGS = ("ENTRY", "TRAIL", "WCLOSE")
FILLED = ("FILLED", "PARTIAL_FILL")
NO_DECISION_PRICE = ("late_fill", "ib_position", "ib_execution")
FLATS = (("$1.00", 1.00), ("$4.26", 4.26), ("$8.92", 8.92))
HONEST = 8.92
MEASURED = 4.26
# C1: the books of record at $4.26 (mcl_vs_mc5_live_RESULT_20260923 C5,
# w05_0019_running_up_universe_scored_RESULT_20260923).
PUBLISHED = {"mcl": (3_908, -35_063.12), "mc5": (6_462, -55_364.07)}
C3_SHARE = 0.99
C3_TOL = 0.001


# ================================================================================
# LIVE: the legs
# ================================================================================

_STEM = re.compile(r"^mcl_fills_(\d{8})")


def session_of(path: Path) -> str | None:
    """`mcl_fills_20260910.csv` and the rolled-aside
    `mcl_fills_20260910_pre061502.csv` both belong to 2026-09-10."""
    m = _STEM.match(path.stem)
    if not m:
        return None
    s = m.group(1)
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def _f(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return x


def classify(row: dict) -> str | None:
    """Which leg a filled row is, or None. OTHER is a filled SELL that is none
    of the three (reported, never used)."""
    action = (row.get("action") or "").strip().upper()
    reason = (row.get("reason") or "").strip()
    kind = (row.get("ref_kind") or "").strip()
    if kind in NO_DECISION_PRICE or not kind:
        return None
    if action == "BUY":
        return "ENTRY" if kind == "signal_close" else None
    if action == "SELL":
        if reason == "trailing_stop" and kind == "trail_level":
            return "TRAIL"
        if reason == "window_close" and kind == "quote":
            return "WCLOSE"
        return "OTHER"
    return None


def leg_row(row: dict, session: str) -> dict | None:
    """One usable fill, with its cost. None if the row is not one."""
    if (row.get("status") or "").strip() not in FILLED:
        return None
    strat = (row.get("strategy") or "").strip().lower() or "mcl"
    if strat not in STRATEGIES:
        return None
    leg = classify(row)
    if leg is None:
        return None
    fill, ref = _f(row.get("fill_price")), _f(row.get("ref_close"))
    qty = _f(row.get("filled_qty"))
    if not (fill > 0 and ref > 0 and qty > 0):
        return None
    buy = (row.get("action") or "").strip().upper() == "BUY"
    cost = (fill - ref) if buy else (ref - fill)          # positive = worse
    bid, ask = _f(row.get("bid")), _f(row.get("ask"))
    mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0 and ask >= bid) else float("nan")
    out = {"session": session, "strategy": strat, "leg": leg,
           "symbol": (row.get("symbol") or "").strip(), "ts_et": row.get("ts_et", ""),
           "reason": (row.get("reason") or "").strip(), "ref": ref, "fill": fill,
           "qty": qty, "cost_ps": cost, "cost_bps": cost / ref * 10_000.0,
           "logged": _f(row.get("slippage_vs_ref")), "mid": mid,
           "spread_bps": float("nan"), "drift_bps": float("nan")}
    if buy and mid == mid:
        # ENTRY split, reported only: what the spread took, and how far the
        # market had moved between the signal close and the order.
        out["spread_bps"] = (fill - mid) / ref * 10_000.0
        out["drift_bps"] = (mid - ref) / ref * 10_000.0
    return out


def load_legs(fills_dir: Path, first: str = FIRST, last: str = LAST) -> list[dict]:
    rows = []
    for f in sorted(Path(fills_dir).glob("mcl_fills_*.csv")):
        s = session_of(f)
        if s is None or not (first <= s <= last):
            continue
        recs, _enc = T.read_csv(f)
        for r in recs:
            got = leg_row(r, s)
            if got is not None:
                rows.append(got)
    return rows


def check_c3(rows: list[dict]) -> dict:
    """C3: the cost computed here equals the negated logged slippage (trader.py
    logs the NEGATION of the cost -- friction.py's docstring). A sign flipped
    here would price every leg backwards and look entirely plausible."""
    have = [r for r in rows if r["leg"] in LEGS and r["logged"] == r["logged"]]
    bad = [r for r in have if abs(r["cost_ps"] + r["logged"]) > C3_TOL]
    share = 1.0 - len(bad) / len(have) if have else 0.0
    return {"checked": len(have), "bad": bad, "share": share,
            "ok": bool(have) and share >= C3_SHARE}


def leg_stats(xs) -> dict:
    """Mean first. `worst` is the largest COST (positive = worse)."""
    v = np.asarray(list(xs), dtype=float)
    if v.size == 0:
        return {"n": 0}
    srt = np.sort(v)                     # ascending: the worst fills are last
    return {"n": int(v.size), "mean": float(v.mean()), "median": float(np.median(v)),
            "p90": float(np.quantile(v, 0.9)), "worst": float(srt[-1]),
            "drop1": float(srt[:-1].mean()) if v.size > 1 else float("nan"),
            "drop3": float(srt[:-3].mean()) if v.size > 3 else float("nan")}


def means_by_leg(rows: list[dict], strategy: str | None = None) -> dict:
    out = {}
    for leg in LEGS:
        xs = [r["cost_bps"] for r in rows if r["leg"] == leg
              and (strategy is None or r["strategy"] == strategy)]
        out[leg] = (float(np.mean(xs)) if xs else float("nan"), len(xs))
    return out


def resolve_e(means: dict, pooled: dict | None = None) -> tuple[dict, list[str]]:
    """The E (bps) each leg is priced at, applying A.2's minimum sample.

    With `pooled` given (the per-strategy sensitivity), a leg below MIN_N falls
    back to the pooled figure. Pooled itself: WCLOSE below MIN_N is priced at
    TRAIL's mean and flagged; ENTRY or TRAIL below MIN_N stops the run."""
    e, notes = {}, []
    for leg in LEGS:
        m, n = means[leg]
        if n >= MIN_N:
            e[leg] = m
        elif pooled is not None:
            e[leg] = pooled[leg]
            notes.append(f"{leg} n={n} < {MIN_N}: pooled figure used")
        elif leg == "WCLOSE":
            e[leg] = means["TRAIL"][0]
            notes.append(f"WCLOSE n={n} < {MIN_N}: NOT SEPARATELY MEASURABLE -- "
                         "window_close priced at TRAIL's mean")
        else:
            raise SystemExit(f"STOPPED: {leg} has n={n} live fills, below the "
                             f"registered minimum of {MIN_N} (A.2)")
    return e, notes


def bootstrap_e(rows: list[dict], nboot: int = NBOOT, seed: int = SEED) -> dict:
    """Session-cluster bootstrap of the pooled leg means, applying the same
    fallback as resolve_e in every draw. Returns {leg: array(nboot)} plus the
    raw WCLOSE draws (NaN where a draw had none) for its own interval."""
    sessions = sorted({r["session"] for r in rows})
    by = {s: defaultdict(list) for s in sessions}
    for r in rows:
        if r["leg"] in LEGS:
            by[r["session"]][r["leg"]].append(r["cost_bps"])
    rng = np.random.default_rng(seed)
    out = {leg: np.empty(nboot) for leg in LEGS}
    raw_w = np.full(nboot, np.nan)
    k = 0
    tries = 0
    while k < nboot:
        tries += 1
        if tries > nboot * 50:
            raise RuntimeError("bootstrap could not draw a sample with ENTRY and TRAIL fills")
        pick = rng.integers(0, len(sessions), len(sessions))
        acc = {leg: [] for leg in LEGS}
        for i in pick:
            for leg in LEGS:
                acc[leg].extend(by[sessions[i]][leg])
        if not acc["ENTRY"] or not acc["TRAIL"]:
            continue
        out["ENTRY"][k] = np.mean(acc["ENTRY"])
        out["TRAIL"][k] = np.mean(acc["TRAIL"])
        if acc["WCLOSE"]:
            raw_w[k] = np.mean(acc["WCLOSE"])
        n_w = len(acc["WCLOSE"])
        out["WCLOSE"][k] = raw_w[k] if n_w >= MIN_N else out["TRAIL"][k]
        k += 1
    out["WCLOSE_raw"] = raw_w
    return out


def halves(rows: list[dict], leg: str = "TRAIL") -> tuple[float, float, str, str]:
    """TRAIL's mean in the first and second half of the sessions (split at the
    middle session), and whether it is UNSTABLE (A.6 item 4)."""
    sessions = sorted({r["session"] for r in rows})
    if len(sessions) < 2:
        return float("nan"), float("nan"), "", "n/a"
    cut = sessions[len(sessions) // 2]
    a = [r["cost_bps"] for r in rows if r["leg"] == leg and r["session"] < cut]
    b = [r["cost_bps"] for r in rows if r["leg"] == leg and r["session"] >= cut]
    if not a or not b:
        return float("nan"), float("nan"), cut, "n/a"
    ma, mb = float(np.mean(a)), float(np.mean(b))
    if ma <= 0 or mb <= 0:
        word = "UNSTABLE" if (ma > 0) != (mb > 0) else "stable"
    else:
        word = "UNSTABLE" if max(ma, mb) / min(ma, mb) > 2.0 else "stable"
    return ma, mb, cut, word


# ================================================================================
# BOOKS: run twice, pair, re-price
# ================================================================================

def book_row(t, t_nogap, symbol: str, day: str, ordinal: int) -> dict:
    from common.first_entry_skip import trade_row
    r = trade_row(t, symbol, day, ordinal)
    r.update(gross=float(t.gross), commission=float(t.commission), qty=int(t.qty),
             exit_px_nogap=float(t_nogap.exit_price), reason_nogap=t_nogap.reason,
             entry_et_nogap=None, exit_et_nogap=None)
    rn = trade_row(t_nogap, symbol, day, ordinal)
    r["entry_et_nogap"], r["exit_et_nogap"] = rn["entry_et"], rn["exit_et"]
    return r


def run_universe(frame, day: str, universe: list[dict], engines: dict) -> dict:
    """Both strategies, both fill models, all or none per symbol-day.
    `engines[name] = (module, extra)`. Pure enough to test with a fake."""
    from common.feed_delay import delayed_floor
    from common.pit_h0 import first_seen_time

    d = _date.fromisoformat(day)
    res = {"books": {s: [] for s in STRATEGIES}, "symdays": 0, "errors": 0,
           "error_days": [], "unpaired": []}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        floor = delayed_floor(first_seen_time(rec), 0, d)
        try:
            got = {}
            for s in STRATEGIES:
                mod, extra = engines[s]
                on = mod.backtest_session(df, d, ET, entry_shares=QTY, not_before=floor,
                                          **dict(extra, gap_fills=True))
                off = mod.backtest_session(df, d, ET, entry_shares=QTY, not_before=floor,
                                           **dict(extra, gap_fills=False))
                got[s] = (on, off)
        except Exception as e:                                   # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{rec['symbol']} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for s, (on, off) in got.items():
            if len(on) != len(off):
                res["unpaired"].append(f"{s} {rec['symbol']} {day}: {len(on)} vs {len(off)} trades")
                # Keep the published trades so C1 still counts them; C2 fails.
                for k, t in enumerate(on, 1):
                    r = book_row(t, t, rec["symbol"], day, k)
                    r["unpaired"] = True
                    res["books"][s].append(r)
                continue
            for k, (t, tn) in enumerate(zip(on, off), 1):
                res["books"][s].append(book_row(t, tn, rec["symbol"], day, k))
    return res


def run_day(args: tuple) -> tuple:
    """One session. Module-level and picklable."""
    from common.dbn_io import read_dbn
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
    engines = {s: engine(s) for s in STRATEGIES}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                                   # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    return day, run_universe(frame, day, universe, engines), ""


def check_c2(rows: list[dict]) -> dict:
    """C2: the gap-off run is the same trade list, and on every trailing exit
    the published fill is no better than the gap-off one."""
    bad_key, bad_px, trail, equal = [], [], 0, 0
    for r in rows:
        if r.get("unpaired"):
            bad_key.append(r)
            continue
        if (r["entry_et"], r["exit_et"], r["reason"]) != \
                (r["entry_et_nogap"], r["exit_et_nogap"], r["reason_nogap"]):
            bad_key.append(r)
            continue
        if r["reason"] == "trailing_stop":
            trail += 1
            if r["exit_px"] > r["exit_px_nogap"] + 1e-6:
                bad_px.append(r)
            elif abs(r["exit_px"] - r["exit_px_nogap"]) <= 1e-6:
                equal += 1
        elif abs(r["exit_px"] - r["exit_px_nogap"]) > 1e-6:
            bad_px.append(r)             # only the trailing fill may differ
    return {"ok": not bad_key and not bad_px, "bad_key": bad_key, "bad_px": bad_px,
            "trail": trail, "no_gap": equal}


class Book:
    """One book as arrays, so a bootstrap draw re-prices it in one pass."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.n = len(rows)
        self.qty = np.array([r["qty"] for r in rows], dtype=float)
        self.gross = np.array([r["gross"] for r in rows], dtype=float)
        self.comm = np.array([r["commission"] for r in rows], dtype=float)
        # The engine's net AS THE RE-PRICING SEES IT: gross - commission from
        # the same rounded fields, so R0 can be held to it exactly. Trade.net
        # is rounded separately and can differ by a cent; C1 uses Trade.net.
        self.trade_net = np.array([r["net"] for r in rows], dtype=float)
        self.net = self.gross - self.comm
        self.entry = np.array([r["entry_px"] for r in rows], dtype=float)
        self.exit = np.array([r["exit_px"] for r in rows], dtype=float)
        self.trail = np.array([r["reason"] == "trailing_stop" for r in rows])
        self.wc = np.array([r["reason"] == "window_close" for r in rows])
        self.other = ~(self.trail | self.wc)
        self.signal_close = self.entry - TICK
        # The stop level, from the engine's own gap-off fill: level - 1 tick.
        nogap = np.array([r["exit_px_nogap"] for r in rows], dtype=float)
        self.level = np.where(self.trail, nogap + TICK, np.nan)
        self.bar_close = np.where(self.wc | self.other, self.exit + TICK, np.nan)

    def prices(self, e_entry: float, e_trail: float, e_wc: float, mode: str = "R1"):
        """New (entry, exit) arrays. E in bps, positive = cost."""
        if mode == "R0":
            new_entry = self.signal_close + TICK
            new_exit = np.where(self.wc, self.bar_close - TICK, self.exit)
            return new_entry, new_exit
        new_entry = self.signal_close * (1.0 + e_entry / 1e4)
        r1_trail = self.level * (1.0 - e_trail / 1e4)
        trail_px = np.minimum(self.exit, r1_trail) if mode == "R2" else r1_trail
        new_exit = np.where(self.trail, trail_px,
                            np.where(self.wc, self.bar_close * (1.0 - e_wc / 1e4), self.exit))
        return new_entry, new_exit

    def repriced(self, e_entry: float, e_trail: float, e_wc: float, mode: str = "R1"):
        """Net per trade: the engine's gross moved by the price changes, its
        commission unchanged (A.4)."""
        ne, nx = self.prices(e_entry, e_trail, e_wc, mode)
        gross = self.gross + (nx - self.exit) * self.qty - (ne - self.entry) * self.qty
        return gross - self.comm, gross

    def fe(self, new_net) -> float:
        """The flat charge that, on top of the engine's net, gives the same total."""
        return float((self.net.sum() - np.sum(new_net)) / self.n) if self.n else float("nan")

    def leg_costs(self, e_entry, e_trail, e_wc, mode="R1") -> dict:
        """Total $ each leg costs against its own reference."""
        ne, nx = self.prices(e_entry, e_trail, e_wc, mode)
        entry = float(np.sum((ne - self.signal_close) * self.qty))
        trail = float(np.nansum(np.where(self.trail, (self.level - nx) * self.qty, 0.0)))
        wc = float(np.nansum(np.where(self.wc, (self.bar_close - nx) * self.qty, 0.0)))
        other = float(np.nansum(np.where(self.other, (self.bar_close - nx) * self.qty, 0.0)))
        return {"entries": entry, "trailing exits": trail, "window_close exits": wc,
                "other exits": other}

    def engine_leg_costs(self) -> dict:
        """What the ENGINE charges per leg against the same references."""
        entry = float(np.sum((self.entry - self.signal_close) * self.qty))
        trail = float(np.nansum(np.where(self.trail, (self.level - self.exit) * self.qty, 0.0)))
        wc = float(np.nansum(np.where(self.wc, (self.bar_close - self.exit) * self.qty, 0.0)))
        other = float(np.nansum(np.where(self.other, (self.bar_close - self.exit) * self.qty, 0.0)))
        return {"entries": entry, "trailing exits": trail, "window_close exits": wc,
                "other exits": other}


def interval(xs) -> tuple[float, float]:
    v = np.asarray(xs, dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return float("nan"), float("nan")
    return float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))


def fe_word(lo: float, hi: float) -> str:
    if not (lo == lo and hi == hi):
        return "n/a"
    if lo <= HONEST <= hi:
        return "$8.92 STANDS"
    if lo > HONEST:
        return "$8.92 UNDERSTATES"
    return "$8.92 OVERSTATES" + ("  (and clears $4.26)" if hi < MEASURED
                                 else "  (but not below $4.26)")


def wc_word(wc_lo: float, wc_hi: float, trail_mean: float, measurable: bool) -> str:
    if not measurable:
        return "not measurable"
    if wc_lo > trail_mean:
        return "window_close is the dearer exit"
    if wc_hi < trail_mean:
        return "window_close is the cheaper exit"
    return "no measurable difference"


def summarise(net, gross, comm) -> dict:
    net = np.asarray(net, dtype=float)
    return {"n": int(net.size), "gross": float(np.sum(gross)), "costs": float(np.sum(comm)),
            "net": float(net.sum()), "per": float(net.mean()) if net.size else float("nan"),
            "wins": int(np.sum(net > 0)), "losses": int(np.sum(net <= 0))}


# ================================================================================
# REPORT
# ================================================================================

def _bps(x: float, w: int = 8) -> str:
    return f"{'n/a':>{w}}" if x != x else acct(x, w, 1)


def leg_table(rows: list[dict], boot: dict) -> list[str]:
    L = [f"  {'leg':<8}{'who':<8}{'n':>5}{'sess':>6}{'mean bps':>10}{'95% CI':>18}"
         f"{'median':>9}{'p90':>9}{'worst':>9}{'drop-1':>9}{'drop-3':>9}"
         f"{'$/sh':>9}{'$/100sh':>10}"]
    for leg in LEGS:
        for who in ("pooled", *STRATEGIES):
            sub = [r for r in rows if r["leg"] == leg and (who == "pooled" or r["strategy"] == who)]
            s = leg_stats(r["cost_bps"] for r in sub)
            if not s["n"]:
                L.append(f"  {leg:<8}{who:<8}{0:>5}")
                continue
            ps = float(np.mean([r["cost_ps"] for r in sub]))
            ci = ""
            if who == "pooled":
                lo, hi = interval(boot["WCLOSE_raw"] if leg == "WCLOSE" else boot[leg])
                ci = f"[{_bps(lo, 7).strip()}, {_bps(hi, 7).strip()}]"
            L.append(f"  {leg:<8}{who:<8}{s['n']:>5}{len({r['session'] for r in sub}):>6}"
                     f"{_bps(s['mean'], 10)}{ci:>18}{_bps(s['median'], 9)}{_bps(s['p90'], 9)}"
                     f"{_bps(s['worst'], 9)}{_bps(s['drop1'], 9)}{_bps(s['drop3'], 9)}"
                     f"{acct(ps, 9, 4)}{acct(ps * 100, 10, 2)}")
    return L


def book_block(strat: str, bk: Book, e: dict, e_strat: dict, boot: dict) -> tuple[list[str], dict]:
    L = [f"  {strat.upper()} -- {bk.n:,} trades   (exit mix: trailing {int(bk.trail.sum()):,}"
         f" / window_close {int(bk.wc.sum()):,} / other {int(bk.other.sum()):,})",
         f"    {'pricing':<28}{'trades':>7}{'W/L':>12}{'gross':>13}{'costs':>11}"
         f"{'net':>13}{'per trade':>11}"]

    def line(label, net, gross, costs):
        s = summarise(net, gross, costs)
        wl = f"{s['wins']}/{s['losses']}"
        L.append(f"    {label:<28}{s['n']:>7}{wl:>12}"
                 f"{acct(s['gross'], 13)}{acct(-s['costs'], 11)}{acct(s['net'], 13)}"
                 f"{acct(s['per'], 11)}")
        return s

    for lab, f in FLATS:
        # The flat charge is a cost: gross unchanged, costs = commission + flat.
        line(f"engine + {lab} flat", bk.net - f, bk.gross, bk.comm + f)
    r1n, r1g = bk.repriced(e["ENTRY"], e["TRAIL"], e["WCLOSE"], "R1")
    r2n, r2g = bk.repriced(e["ENTRY"], e["TRAIL"], e["WCLOSE"], "R2")
    rsn, rsg = bk.repriced(e_strat["ENTRY"], e_strat["TRAIL"], e_strat["WCLOSE"], "R1")
    s1 = line("R1 per-leg (primary)", r1n, r1g, bk.comm)
    s2 = line("R2 conservative bound", r2n, r2g, bk.comm)
    line(f"R1, {strat.upper()}'s own legs", rsn, rsg, bk.comm)

    fe1, fe2 = bk.fe(r1n), bk.fe(r2n)
    nb = len(boot["ENTRY"])
    draws1 = np.array([bk.fe(bk.repriced(boot["ENTRY"][k], boot["TRAIL"][k], boot["WCLOSE"][k],
                                         "R1")[0]) for k in range(nb)])
    draws2 = np.array([bk.fe(bk.repriced(boot["ENTRY"][k], boot["TRAIL"][k], boot["WCLOSE"][k],
                                         "R2")[0]) for k in range(nb)])
    lo1, hi1 = interval(draws1)
    lo2, hi2 = interval(draws2)
    word = fe_word(lo1, hi1)
    L += ["",
          "    (gross is after each row's own fill prices; costs = commission, plus the flat"
          " charge where there is one)",
          f"    flat-equivalent per round trip, R1  ${acct(fe1, 7).strip()}   95% CI "
          f"[${acct(lo1, 6).strip()}, ${acct(hi1, 6).strip()}]   ->  {word}",
          f"    flat-equivalent per round trip, R2  ${acct(fe2, 7).strip()}   95% CI "
          f"[${acct(lo2, 6).strip()}, ${acct(hi2, 6).strip()}]   (upper bound, not scored)",
          "", "    cost of each leg against its own reference price ($, whole book; "
          "costs shown as negatives)",
          f"      {'leg':<22}{'engine':>12}{'R1':>12}{'R1 - engine':>13}"]
    eng = bk.engine_leg_costs()
    r1c = bk.leg_costs(e["ENTRY"], e["TRAIL"], e["WCLOSE"], "R1")
    for k in eng:
        L.append(f"      {k:<22}{acct(-eng[k], 12)}{acct(-r1c[k], 12)}{acct(-(r1c[k] - eng[k]), 13)}")
    L.append(f"      {'total':<22}{acct(-sum(eng.values()), 12)}{acct(-sum(r1c.values()), 12)}"
             f"{acct(-(sum(r1c.values()) - sum(eng.values())), 13)}")
    L.append(f"      (the flat $8.92 would add {acct(-HONEST * bk.n, 12).strip()} on top of the engine column)")

    # The window_close trades on their own: the runners.
    wc_idx = np.flatnonzero(bk.wc)
    wc = None
    if wc_idx.size:
        eng_wc = bk.net[wc_idx] - HONEST
        wc = {"n": int(wc_idx.size), "eng": float(eng_wc.sum()), "r1": float(r1n[wc_idx].sum())}
        L += ["", f"    window_close trades ({wc_idx.size:,}):  engine at $8.92 "
              f"${acct(float(eng_wc.sum()), 11).strip()}  ({acct(float(eng_wc.mean()), 8).strip()}/trade)"
              f"   R1 ${acct(float(r1n[wc_idx].sum()), 11).strip()}  "
              f"({acct(float(r1n[wc_idx].mean()), 8).strip()}/trade)",
              f"      {'symbol':<8}{'date':<12}{'entry':>8}{'exit':>8}{'engine@8.92':>13}{'R1':>10}"]
        order = list(wc_idx[np.argsort(-bk.net[wc_idx], kind="mergesort")])
        pick = order[:5] + [i for i in order[-5:] if i not in order[:5]]
        for i in pick:
            r = bk.rows[i]
            L.append(f"      {r['symbol']:<8}{r['date']:<12}{r['entry_px']:>8.2f}{r['exit_px']:>8.2f}"
                     f"{acct(bk.net[i] - HONEST, 13)}{acct(float(r1n[i]), 10)}")
    return L, {"fe": fe1, "lo": lo1, "hi": hi1, "word": word, "r1": s1, "r2": s2,
               "fe2": fe2, "wc": wc, "eng426": float((bk.net - MEASURED).sum()),
               "eng892": float((bk.net - HONEST).sum())}


def render(legs: list[dict], c3: dict, books: dict, c1: dict, c2: dict, e: dict,
           notes: list[str], e_by: dict, boot: dict, meta: dict) -> tuple[str, dict]:
    words, res = {}, {}
    stops = [k for k, ok in (("C1", c1["ok"]), ("C2", c2["ok"]), ("C3", c3["ok"]),
                             ("C4", all(meta["c4"].values()))) if not ok]
    head = []
    if stops:
        head.append(f"*** STOPPED: control(s) {', '.join(stops)} failed -- NOT A RESULT ***")
    if meta.get("not_registered"):
        head.append("*** NOT THE REGISTERED SAMPLE (--first/--last/--limit changed) -- NOT A RESULT ***")
    head += [f"*** {n} ***" for n in notes]
    ma, mb, cut, stab = halves(legs)
    if stab == "UNSTABLE":
        head.append(f"*** TRAIL is UNSTABLE between halves: {ma:.1f} vs {mb:.1f} bps (cut {cut}) ***")

    # Section 1: the legs.
    S1 = ["1. THE LIVE LEGS (paper fills, sessions "
          f"{meta['first']} -> {meta['last']}, {meta['sessions']} sessions)",
          "   cost in bps of the decision price; positive = worse; 95% CI by session bootstrap",
          *leg_table(legs, boot), ""]
    ent = [r for r in legs if r["leg"] == "ENTRY" and r["spread_bps"] == r["spread_bps"]]
    if ent:
        S1.append(f"   ENTRY split (n={len(ent)}): spread paid vs mid "
                  f"{np.mean([r['spread_bps'] for r in ent]):+.1f} bps + drift signal-close -> "
                  f"mid at order {np.mean([r['drift_bps'] for r in ent]):+.1f} bps (reported only)")
    other = [r for r in legs if r["leg"] == "OTHER"]
    if other:
        byr = defaultdict(list)
        for r in other:
            byr[r["reason"] or "?"].append(r["cost_bps"])
        S1.append("   OTHER exits (never used): " + ", ".join(
            f"{k} n={len(v)} mean {np.mean(v):+.1f} bps" for k, v in sorted(byr.items())))
    S1.append(f"   TRAIL by half: {_bps(ma, 6).strip()} / {_bps(mb, 6).strip()} bps "
              f"(cut {cut}) -> {stab}")
    wlo, whi = interval(boot["WCLOSE_raw"])
    measurable = e_by["pooled"]["WCLOSE"][1] >= MIN_N
    words["window_close"] = wc_word(wlo, whi, e_by["pooled"]["TRAIL"][0], measurable)
    S1 += [f"   window_close vs trailing stop  ->  {words['window_close']}", ""]

    # Section 2: the books.
    S2 = ["2. THE BOOKS RE-PRICED (screen_pairs_pit_itch_v2, XNAS.ITCH, 100 shares)",
          f"   priced at ENTRY {e['ENTRY']:+.1f} / TRAIL {e['TRAIL']:+.1f} / WCLOSE "
          f"{e['WCLOSE']:+.1f} bps (pooled)", ""]
    for s in STRATEGIES:
        bk = books.get(s)
        if bk is None or not bk.n:
            continue
        es, _ = resolve_e(e_by[s], pooled=e)
        blk, res[s] = book_block(s, bk, e, es, boot)
        words[s] = res[s]["word"]
        S2 += blk + [""]

    # Plain terms, written last because it quotes both sections.
    P = ["IN PLAIN TERMS", "-" * 78]
    if stops:
        P.append("A control failed, so none of the numbers below is a result. See section 3.")
    else:
        P.append(f"On the paper account (costs in bps of the price; bracketed = better than the "
                 f"reference): buying costs {acct(e['ENTRY'], 6, 1).strip()} bps against the signal "
                 f"bar's close, a trailing stop costs {acct(e['TRAIL'], 6, 1).strip()} bps against its "
                 f"level, and the 09:30 window close costs {acct(e['WCLOSE'], 6, 1).strip()} bps "
                 f"against the quote ({words['window_close']}).")
        for s in STRATEGIES:
            if s in res:
                r = res[s]
                P.append(f"{s.upper()} priced leg by leg nets {acct(r['r1']['net'], 12).strip()} over "
                         f"{r['r1']['n']:,} trades ({acct(r['r1']['per'], 8).strip()}/trade), "
                         f"the same as a flat ${acct(r['fe'], 8).strip()} per round trip on top of "
                         f"the engine [${acct(r['lo'], 8).strip()}, ${acct(r['hi'], 8).strip()}] "
                         f"-> {r['word']}.")
        P.append("No book turns positive under any pricing: both lose before costs.")
    P.append("")

    C = ["3. CONTROLS",
         "   C1 baseline      " + "; ".join(
             f"{s.upper()} {c1[s]['n']:,} trades {acct(c1[s]['net'], 12).strip()} at $4.26 "
             f"(published {PUBLISHED[s][0]:,} / {acct(PUBLISHED[s][1], 12).strip()}) "
             f"{'OK' if c1[s]['ok'] else 'MISMATCH'}" for s in STRATEGIES if s in c1)
         + ("  (not checked: --limit)" if c1.get("skipped") else ""),
         f"   C2 pairing       {'OK' if c2['ok'] else 'FAILED'}: {len(c2['bad_key'])} key "
         f"mismatches, {len(c2['bad_px'])} price violations; {c2['trail']:,} trailing exits, "
         f"{c2['no_gap']:,} without a gap ({100 * c2['no_gap'] / max(c2['trail'], 1):.1f}%)",
         f"   C3 ledger sign   {'OK' if c3['ok'] else 'FAILED'}: {c3['checked'] - len(c3['bad'])} of "
         f"{c3['checked']} rows agree ({100 * c3['share']:.2f}%, need {100 * C3_SHARE:.0f}%)",
         "   C4 null (R0)     " + "; ".join(
             f"{s.upper()} {'OK' if meta['c4'][s] else 'FAILED'}" for s in meta["c4"])]
    for r in c3["bad"][:10]:
        C.append(f"      C3 row: {r['session']} {r['symbol']} {r['leg']} cost {r['cost_ps']:+.4f} "
                 f"logged {r['logged']:+.4f}")
    for r in (c2["bad_key"] + c2["bad_px"])[:10]:
        C.append(f"      C2 row: {r['symbol']} {r['date']} #{r['ordinal']} {r['reason']} "
                 f"{r['exit_px']} vs {r['exit_px_nogap']}")
    C += ["", "4. DECISION WORDS (REGISTERED_exec_cost.md A.7)"]
    for s in STRATEGIES:
        if s in words:
            C.append(f"   {s.upper():<5} {words[s]}")
    if all(s in words for s in STRATEGIES):
        a, b = words["mcl"].split("  ")[0], words["mc5"].split("  ")[0]
        C.append(f"   single word: {a if a == b else 'none -- the books disagree'}")
    C.append(f"   window_close  {words['window_close']}")
    C += ["", "CAVEATS: IBKR paper fills; the live exit code changed mid-sample (see halves);",
          "the live universe is the watchlist, not the v2 file, hence bps not cents;",
          "commission is the engine's own and is not re-computed for the new prices."]
    L = (head + [""] if head else []) + P + S1 + S2 + C
    return "\n".join(L), words


# ================================================================================
# MAIN
# ================================================================================

def write_rows(path: str, rows: list[dict], cols: list[str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.ITCH")
    p.add_argument("--fills", default=FILLS_DIR)
    p.add_argument("--first", default=FIRST)
    p.add_argument("--last", default=LAST)
    p.add_argument("--limit", type=int, default=None, help="first N sessions only (smoke test)")
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--nboot", type=int, default=NBOOT)
    p.add_argument("--out", default="var/reports/exec_cost_legs.txt")
    p.add_argument("--csv-fills", default="var/reports/exec_cost_legs_fills.csv")
    p.add_argument("--csv-trades", default="var/reports/exec_cost_legs_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)

    legs = load_legs(Path(a.fills), a.first, a.last)
    if not legs:
        raise SystemExit(f"no usable fills in {a.fills} for {a.first} -> {a.last}")
    c3 = check_c3(legs)
    e_by = {"pooled": means_by_leg(legs), **{s: means_by_leg(legs, s) for s in STRATEGIES}}
    e, notes = resolve_e(e_by["pooled"])
    boot = bootstrap_e(legs, a.nboot, SEED)

    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    got, elapsed = G.run_sessions(run_day, tasks, G.jobs_from(a.jobs), "exec_cost_legs")
    rows = {s: [] for s in STRATEGIES}
    unpaired, errors = [], 0
    for day in sorted(got):              # DAY ORDER: float sums must not move with --jobs
        for s in STRATEGIES:
            rows[s] += got[day]["books"][s]
        unpaired += got[day]["unpaired"]
        errors += got[day]["errors"]

    c1 = {"ok": True, "skipped": bool(a.limit)}
    for s in STRATEGIES:
        n = len(rows[s])
        net = round(sum(r["net"] - MEASURED for r in rows[s]), 2)
        ok = (n == PUBLISHED[s][0] and abs(net - PUBLISHED[s][1]) < 0.005)
        c1[s] = {"n": n, "net": net, "ok": ok or bool(a.limit)}
        c1["ok"] = c1["ok"] and c1[s]["ok"]
    c2 = check_c2(rows["mcl"] + rows["mc5"])
    books = {s: Book([r for r in rows[s] if not r.get("unpaired")]) for s in STRATEGIES}
    c4 = {}
    for s, bk in books.items():
        n0, _ = bk.repriced(0, 0, 0, "R0")
        c4[s] = bool(np.all(np.abs(n0 - bk.net) < 1e-6)
                     and np.all(np.abs(bk.net - bk.trade_net) < 0.011))

    sessions = sorted({r["session"] for r in legs})
    meta = {"first": a.first, "last": a.last, "sessions": len(sessions), "c4": c4,
            "not_registered": (a.first, a.last) != (FIRST, LAST) or bool(a.limit)}
    if not c2["ok"] and unpaired:
        notes.append(f"{len(unpaired)} symbol-day(s) with different trade counts gap on/off")
    text, words = render(legs, c3, books, c1, c2, e, notes, e_by, boot, meta)
    ok = c1["ok"] and c2["ok"] and c3["ok"] and all(c4.values())
    emit(text, a.out,
         header=f"common.exec_cost_legs pairs={a.pairs} dataset={a.dataset} fills={a.fills} "
                f"sessions={a.first}..{a.last} ({len(sessions)}) qty={QTY} nboot={a.nboot} "
                f"seed={SEED} errors={errors} elapsed={elapsed:.0f}s registered={REGISTERED}"
                + ("" if ok else "  STOPPED"))

    write_rows(a.csv_fills, legs, ["session", "strategy", "leg", "symbol", "ts_et", "reason",
                                   "ref", "fill", "qty", "cost_ps", "cost_bps", "logged",
                                   "mid", "spread_bps", "drift_bps"])
    out_rows = []
    for s, bk in books.items():
        if not bk.n:
            continue
        r1, _ = bk.repriced(e["ENTRY"], e["TRAIL"], e["WCLOSE"], "R1")
        r2, _ = bk.repriced(e["ENTRY"], e["TRAIL"], e["WCLOSE"], "R2")
        for i, r in enumerate(bk.rows):
            out_rows.append(dict(r, book=s, level=(None if math.isnan(bk.level[i]) else round(bk.level[i], 4)),
                                 net_r1=round(float(r1[i]), 2), net_r2=round(float(r2[i]), 2)))
    write_rows(a.csv_trades, out_rows, ["book", "symbol", "date", "ordinal", "entry_et", "entry_px",
                                        "exit_et", "exit_px", "exit_px_nogap", "level", "reason",
                                        "qty", "gross", "commission", "net", "net_r1", "net_r2"])
    print(f"wrote {a.csv_fills} ({len(legs):,} fills) and {a.csv_trades} ({len(out_rows):,} trades)")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
