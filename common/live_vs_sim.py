#!/usr/bin/env python3
r"""H-L1 (W02-0002) -- is MC5 really better than MCL? The live book against
the backtest on the same sessions.

    python -m common.live_vs_sim --jobs 2
    python -m common.live_vs_sim --pairs var/state/screen_pairs_pit_itch_ext.json \
        --pairs var/state/screen_pairs_pit_itch_ext3.json --jobs 2

Registered in docs/research/REGISTERED_mcl_vs_mc5_live.md (9e4dddf), committed
before this file existed. Research only: the trader never imports it.

WHAT IT DOES
------------
1. Runs the sim books on the live sessions (2026-09-08 -> 09-22, the shared-cap
   window): MCL/MC5 at first_seen +0 and +15, and MC5 with the apex exit ON
   (+15) on the apex-ON sessions. The FEED-MATCHED book per session is +15 up
   to 2026-09-18 (anonymous TradingView, delayed_streaming_900) and +0 from
   2026-09-21 (signed in).
2. Pairs the live fill logs into round trips (churn_count's file-order rule,
   with prices kept) and joins them to the feed-matched sim trades.
3. Decomposes live total - sim total into matched execution + live-only -
   sim-only, an identity, and classifies every unmatched trade.
4. Replays the live cap (3 positions, shared across the two strategies) on the
   sim trades, here and on the ITCH v2 population, and bootstraps MCL - MC5 by
   session for the three verdict words fixed in the registration.

NOTHING PASSES HERE. The output is one word per denominator per book, and a
decomposition.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from common import gate_study as G
from common.entry_shares import QTY
from common.feed_delay import delayed_floor, hold_minutes, money
from common.first_entry_skip import FRICTIONS, trade_row

ET = ZoneInfo("America/New_York")
REGISTERED = "docs/research/REGISTERED_mcl_vs_mc5_live.md"
PAIRS = ("var/state/screen_pairs_pit_itch_ext.json",)
POPULATION_CSV = "var/reports/feed_delay_trades.csv"
POPULATION_PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
FIRST, LAST = "2026-09-08", "2026-09-22"      # the shared-cap window
BOTH_FROM = "2026-09-10"                      # first session both strategies ran
APEX_LAST = "2026-09-17"                      # paper_fill.apex: ON <= this
SIGNED_IN_FROM = "2026-09-21"                 # feed real time from this session
DELAY = 15
STRATEGIES = ("mcl", "mc5")
BAR_MIN = {"mcl": 1, "mc5": 5}
TOL_BARS = 2                                  # the join, registered
CAP = 3
MEASURED = 4.26
SEED = 20260923
NBOOT = 10_000
COMMISSION_PLAN = "ibkr_tiered"


def feed_offset(day: str) -> int:
    return DELAY if day < SIGNED_IN_FROM else 0


def apex_on(day: str) -> bool:
    return day <= APEX_LAST


def minute(hhmm: str) -> float:
    h, m = hhmm.split(":")[:2]
    return int(h) * 60 + int(m)


# --- the sim books ---------------------------------------------------------------

SIM_BOOKS = ("MCL +0", "MCL +15", "MC5 +0", "MC5 +15", "MC5A +15")


def run_universe(frame, day: str, universe: list[dict], engines: dict) -> dict:
    """Every sim book on every symbol-day of one session; all-or-none per
    symbol-day. `engines[key] = (module, extra)` with keys mcl, mc5, mc5a."""
    import pandas as pd  # noqa: F401
    from common.pit_h0 import first_seen_time

    d = _date.fromisoformat(day)
    res = {"books": {b: [] for b in SIM_BOOKS}, "symdays": 0, "errors": 0,
           "error_days": [], "symbols": []}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        seen = first_seen_time(rec)
        try:
            got = {}
            for book in SIM_BOOKS:
                key, off = book.split(" +")
                off = int(off)
                if key == "MC5A" and not apex_on(day):
                    continue
                mod, extra = engines[key.lower()]
                got[book] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=delayed_floor(seen, off, d), **extra)
        except Exception as e:                                   # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{rec['symbol']} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        res["symbols"].append(rec["symbol"])
        for book, trades in got.items():
            for k, t in enumerate(trades, 1):
                row = trade_row(t, rec["symbol"], day, k)
                row["hold_min"] = hold_minutes(row)
                res["books"][book].append(row)
    return res


def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
    engines = {"mcl": engine("mcl"), "mc5": engine("mc5"), "mc5a": engine("mc5", True)}
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


def merge_pairs(paths: list[str], out: Path) -> tuple[Path, dict]:
    """One universe file from several: for each date, the rows of the FIRST
    file that has that date. Returns the path and {date: source file}."""
    seen: dict[str, str] = {}
    rows: list[dict] = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        dates = sorted({r["date"] for r in data})
        for d in dates:
            if d in seen or not (FIRST <= d <= LAST):
                continue
            seen[d] = p
            rows += [r for r in data if r["date"] == d]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=0), encoding="utf-8")
    return out, seen


def c1_check(books: dict, path: str = "var/reports/feed_delay_live_trades.csv") -> str:
    """C1: the +0/+15 books reproduce feed_delay's Arm B to the trade on its sessions."""
    if not Path(path).exists():
        return "not run (no feed_delay_live_trades.csv)"
    ref = defaultdict(set)
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["book"] in ("MCL +0", "MCL +15", "MC5 +0", "MC5 +15"):
                ref[r["book"]].add((r["symbol"], r["date"], r["entry_et"], r["exit_et"], f"{float(r['net']):.2f}"))
    days = {k[1] for v in ref.values() for k in v}
    bad = 0
    for b, keys in ref.items():
        ours = {(r["symbol"], r["date"], r["entry_et"], r["exit_et"], f"{r['net']:.2f}")
                for r in books[b] if r["date"] in days}
        bad += len(ours ^ keys)
    n = sum(len(v) for v in ref.values())
    return (f"OK ({n} rows, {len(days)} sessions)" if not bad
            else f"*** FAILS: {bad} rows differ of {n} ***")


def c2_check(paths: list[str]) -> str:
    """C2: a later universe file reproduces the first one's rows on overlapping dates."""
    if len(paths) < 2:
        return "not applicable (one universe file)"
    def rows(p):
        out = defaultdict(set)
        for r in json.loads(Path(p).read_text(encoding="utf-8")):
            if FIRST <= r["date"] <= LAST:
                out[r["date"]].add((r["symbol"], r.get("first_seen")))
        return out
    a, b = rows(paths[0]), rows(paths[1])
    common = sorted(set(a) & set(b))
    diff = {d: (len(a[d] - b[d]), len(b[d] - a[d])) for d in common if a[d] != b[d]}
    return (f"OK ({len(common)} overlapping sessions identical)" if not diff else
            "*** DIFFERS: " + ", ".join(f"{d} -{x}/+{y}" for d, (x, y) in diff.items())
            + f" -- {Path(paths[0]).name} used on those dates ***")


def feed_matched(books: dict, strat: str) -> list[dict]:
    """The per-session feed-matched book for one strategy (apex OFF)."""
    s = strat.upper()
    return [r for r in books[f"{s} +{DELAY}"] if feed_offset(r["date"]) == DELAY] + \
           [r for r in books[f"{s} +0"] if feed_offset(r["date"]) == 0]


# --- the live book ---------------------------------------------------------------

def read_log(path: Path):
    """Every row of one fill log (all statuses), strategy label derived only
    when the column is absent -- churn_count.load's rule, without its filter."""
    import pandas as pd
    from common import textio as T
    d = pd.read_csv(io.StringIO(T.read_text(path)[0]))
    if "trade_pnl" not in d.columns or "ts_et" not in d.columns:
        return None
    d["ts_et"] = pd.to_datetime(d["ts_et"])
    if "strategy" not in d.columns:
        d["strategy"] = path.name.split("_", 1)[0].upper()
    d["file"] = path.name
    return d


def live_log(fills_dir: Path):
    import pandas as pd
    frames = [f for p in sorted(Path(fills_dir).glob("*_fills_*.csv"))
              if (f := read_log(p)) is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def live_round_trips(log) -> list[dict]:
    """churn_count.round_trips' pairing -- FILE ORDER per (strategy, symbol),
    each SELL carrying a P/L closes the last BUY -- keeping the prices."""
    f = log[log["status"] == "FILLED"]
    out = []
    for (st, sym), g in f.groupby(["strategy", "symbol"], sort=False):
        open_row = None
        for r in g.itertuples():
            if r.action == "BUY":
                open_row = r
            elif r.action == "SELL" and open_row is not None and r.trade_pnl == r.trade_pnl:
                day = r.ts_et.strftime("%Y-%m-%d")
                ep = float(r.entry_price) if r.entry_price == r.entry_price else float(open_row.fill_price)
                xp = float(r.exit_price) if r.exit_price == r.exit_price else float(r.fill_price)
                out.append({"strategy": str(st).lower(), "symbol": sym, "date": day,
                            "open_ts": open_row.ts_et, "close_ts": r.ts_et,
                            "entry_min": open_row.ts_et.hour * 60 + open_row.ts_et.minute
                                         + open_row.ts_et.second / 60,
                            "exit_min": r.ts_et.hour * 60 + r.ts_et.minute + r.ts_et.second / 60,
                            "entry_px": ep, "exit_px": xp,
                            "qty": float(r.filled_qty) if r.filled_qty == r.filled_qty else QTY,
                            "pnl": float(r.trade_pnl), "reason": r.reason,
                            "apex": (str(st).lower() == "mc5" and apex_on(day))})
                open_row = None
    out.sort(key=lambda x: (x["date"], x["open_ts"], x["strategy"], x["symbol"]))
    return out


def commission(price: float) -> float:
    from common.commissions import round_trip
    return round_trip(QTY, price, COMMISSION_PLAN)


# --- the join and the decomposition -----------------------------------------

def join(live: list[dict], sim: list[dict], strat: str, tol_bars: int = TOL_BARS):
    """One-to-one, nearest first, same strategy/symbol/session, |dt| <= tol.
    Returns (pairs [(live_i, sim_j, dt)], live-only idx, sim-only idx)."""
    tol = tol_bars * BAR_MIN[strat]
    cands = []
    for i, lv in enumerate(live):
        for j, sm in enumerate(sim):
            if lv["symbol"] != sm["symbol"] or lv["date"] != sm["date"]:
                continue
            dt = lv["entry_min"] - minute(sm["entry_et"])
            if abs(dt) <= tol:
                cands.append((abs(dt), lv["entry_min"], i, j, dt))
    cands.sort()
    used_l, used_s, pairs = set(), set(), []
    for _, _, i, j, dt in cands:
        if i in used_l or j in used_s:
            continue
        used_l.add(i)
        used_s.add(j)
        pairs.append((i, j, dt))
    return (sorted(pairs), [i for i in range(len(live)) if i not in used_l],
            [j for j in range(len(sim)) if j not in used_s])


def classify_sim_only(sm: dict, strat: str, log, live: list[dict]) -> str:
    tol = TOL_BARS * BAR_MIN[strat]
    t = minute(sm["entry_et"])
    rows = log[(log["strategy"].str.lower() == strat) & (log["symbol"] == sm["symbol"])
               & (log["action"] == "BUY")]
    rows = rows[rows["ts_et"].dt.strftime("%Y-%m-%d") == sm["date"]]
    mins = rows["ts_et"].dt.hour * 60 + rows["ts_et"].dt.minute + rows["ts_et"].dt.second / 60
    near = rows[(mins - t).abs() <= tol]
    if (near["status"] == "SKIPPED_CONCURRENCY_CAP").any():
        return "cap"
    if (near["status"] != "FILLED").any():
        return "other skip"
    for lv in live:
        if (lv["strategy"] == strat and lv["symbol"] == sm["symbol"] and lv["date"] == sm["date"]
                and lv["entry_min"] <= t < lv["exit_min"]):
            return "live busy"
    return "never signalled"


def classify_live_only(lv: dict, universe_by_day: dict) -> str:
    return ("sim no entry near" if lv["symbol"] in universe_by_day.get(lv["date"], set())
            else "not in sim universe")


def decompose(live: list[dict], sim: list[dict], strat: str, log, universe_by_day,
              tol_bars: int = TOL_BARS) -> dict:
    pairs, lonly, sonly = join(live, sim, strat, tol_bars)
    live_tot = sum(x["pnl"] for x in live)
    sim_tot = sum(x["net"] for x in sim)
    m_live = sum(live[i]["pnl"] for i, _, _ in pairs)
    m_sim = sum(sim[j]["net"] for _, j, _ in pairs)
    entry = sum(-(live[i]["entry_px"] - sim[j]["entry_px"]) * live[i]["qty"] for i, j, _ in pairs)
    exitd = sum((live[i]["exit_px"] - sim[j]["exit_px"]) * live[i]["qty"] for i, j, _ in pairs)
    lo = sum(live[i]["pnl"] for i in lonly)
    so = sum(sim[j]["net"] for j in sonly)
    resid = (live_tot - sim_tot) - ((m_live - m_sim) + lo - so)
    s_cls = defaultdict(lambda: [0, 0.0])
    for j in sonly:
        c = classify_sim_only(sim[j], strat, log, live)
        s_cls[c][0] += 1
        s_cls[c][1] += sim[j]["net"]
    l_cls = defaultdict(lambda: [0, 0.0])
    for i in lonly:
        c = classify_live_only(live[i], universe_by_day)
        l_cls[c][0] += 1
        l_cls[c][1] += live[i]["pnl"]
    return {"n_live": len(live), "n_sim": len(sim), "live_tot": live_tot, "sim_tot": sim_tot,
            "n_match": len(pairs), "m_live": m_live, "m_sim": m_sim,
            "m_entry": entry, "m_exit": exitd, "m_other": (m_live - m_sim) - entry - exitd,
            "n_lonly": len(lonly), "lonly": lo, "n_sonly": len(sonly), "sonly": so,
            "resid": resid, "sim_only_by": dict(s_cls), "live_only_by": dict(l_cls),
            "pairs": pairs, "lonly_idx": lonly, "sonly_idx": sonly}


# --- the cap replay --------------------------------------------------------------

def replay_cap(trades: list[dict], cap: float, scope: str = "shared",
               first: str = "mcl") -> list[dict]:
    """Admit trades in minute order under a position cap. Each row needs
    strategy, date, symbol, entry_et, exit_et. Occupancy is [entry, exit);
    exits at minute t release before entries at t; same-minute entries are
    ordered `first` strategy first, then symbol. Returns the admitted rows in
    their original order. cap=inf returns the input unchanged (control C4)."""
    if math.isinf(cap):
        return list(trades)
    rank = {first: 0}
    by_day = defaultdict(list)
    for k, r in enumerate(trades):
        by_day[r["date"]].append(k)
    keep = set()
    for day, idx in by_day.items():
        idx.sort(key=lambda k: (minute(trades[k]["entry_et"]),
                                rank.get(trades[k]["strategy"], 1), trades[k]["symbol"], k))
        open_: list[tuple[float, str]] = []           # (exit minute, strategy)
        for k in idx:
            r = trades[k]
            t = minute(r["entry_et"])
            open_ = [(x, s) for x, s in open_ if x > t]
            n = len(open_) if scope == "shared" else sum(1 for _, s in open_ if s == r["strategy"])
            if n < cap:
                keep.add(k)
                open_.append((minute(r["exit_et"]), r["strategy"]))
    return [trades[k] for k in sorted(keep)]


def tag(rows: list[dict], strat: str) -> list[dict]:
    return [dict(r, strategy=strat) for r in rows]


# --- the verdicts ------------------------------------------------------------------

def session_table(rows_by_strat: dict, sessions: list[str], f: float, symdays: dict | None):
    """{strategy: (net per session array, n per session array)} + symdays array."""
    out = {}
    for s, rows in rows_by_strat.items():
        net = defaultdict(float)
        n = defaultdict(int)
        for r in rows:
            net[r["date"]] += r["val"] - f
            n[r["date"]] += 1
        out[s] = (np.array([net[d] for d in sessions]), np.array([n[d] for d in sessions]))
    sd = np.array([symdays.get(d, 0) for d in sessions]) if symdays else None
    return out, sd


def point(tab, sd, a="mcl", b="mc5") -> dict:
    (na, ca), (nb, cb) = tab[a], tab[b]
    res = {"per_trade": (na.sum() / ca.sum() if ca.sum() else float("nan"))
                        - (nb.sum() / cb.sum() if cb.sum() else float("nan")),
           "per_session": (na.sum() - nb.sum()) / len(na) if len(na) else float("nan")}
    if sd is not None and sd.sum():
        res["per_symday"] = (na.sum() - nb.sum()) / sd.sum()
    return res


def bootstrap(tab, sd, a="mcl", b="mc5", n=NBOOT, seed=SEED) -> dict:
    rng = np.random.default_rng(seed)
    (na, ca), (nb, cb) = tab[a], tab[b]
    k = len(na)
    if k == 0:
        return {}
    draws = rng.integers(0, k, size=(n, k))
    A, CA, B, CB = na[draws].sum(1), ca[draws].sum(1), nb[draws].sum(1), cb[draws].sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        pt = A / CA - B / CB
    out = {"per_trade": pt[np.isfinite(pt)], "per_session": (A - B) / k}
    if sd is not None and sd.sum():
        S = sd[draws].sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            ps = (A - B) / S
        out["per_symday"] = ps[np.isfinite(ps)]
    return {key: (float(np.percentile(v, 5)), float(np.percentile(v, 95))) if len(v) else
            (float("nan"), float("nan")) for key, v in out.items()}


def word(lo: float, hi: float) -> str:
    if lo != lo or hi != hi:
        return "n/a"
    if lo > 0:
        return "MCL better"
    if hi < 0:
        return "MC5 better"
    return "can't tell"


def verdicts(rows_by_strat, sessions, f, symdays=None) -> dict:
    tab, sd = session_table(rows_by_strat, sessions, f, symdays)
    p = point(tab, sd)
    ci = bootstrap(tab, sd)
    per = {}
    for s, (net, cnt) in tab.items():
        per[s] = {"n": int(cnt.sum()), "net": float(net.sum()),
                  "per_trade": float(net.sum() / cnt.sum()) if cnt.sum() else float("nan"),
                  "per_session": float(net.sum() / len(sessions)) if sessions else float("nan"),
                  "per_symday": (float(net.sum() / sd.sum()) if sd is not None and sd.sum()
                                 else float("nan"))}
    return {"sessions": len(sessions), "per": per,
            "diff": {k: {"point": float(v), "ci": ci.get(k), "word": word(*ci[k]) if k in ci else "n/a"}
                     for k, v in p.items()}}


# --- the report --------------------------------------------------------------------

def vrow(label: str, v: dict) -> list[str]:
    L = [f"  {label}   ({v['sessions']} sessions)"]
    for s in STRATEGIES:
        p = v["per"][s]
        sym = f"   /symday {money(p['per_symday']):>8}" if p["per_symday"] == p["per_symday"] else ""
        L.append(f"    {s.upper():<4} n {p['n']:>6,}   net {money(p['net']):>11}   "
                 f"/trade {money(p['per_trade']):>8}   /session {money(p['per_session']):>9}{sym}")
    for k, d in v["diff"].items():
        lo, hi = d["ci"] if d["ci"] else (float("nan"), float("nan"))
        L.append(f"    MCL - MC5 {k:<12} {money(d['point']):>9}   90% [{money(lo)}, {money(hi)}]"
                 f"   -> {d['word'].upper()}")
    return L + [""]


def as_val(rows, key):
    return [dict(r, val=r[key]) for r in rows]


def decomp_block(title: str, d: dict) -> list[str]:
    gap = d["live_tot"] - d["sim_tot"]
    L = [f"  {title}",
         f"    live {d['n_live']:>4} trades {money(d['live_tot']):>10}   sim {d['n_sim']:>4} trades "
         f"{money(d['sim_tot']):>10} (gross)   live - sim {money(gap):>10}",
         f"    matched {d['n_match']:>4}   live {money(d['m_live'])}  sim {money(d['m_sim'])}   "
         f"execution {money(d['m_live'] - d['m_sim'])}"
         + (f" = {money((d['m_live'] - d['m_sim']) / d['n_match'])}/trade" if d["n_match"] else ""),
         f"               entry price {money(d['m_entry'])}   exit price {money(d['m_exit'])}"
         f"   other {money(d['m_other'])}",
         f"    live-only {d['n_lonly']:>4}  {money(d['lonly']):>10}   "
         + "  ".join(f"{k}: {v[0]} {money(v[1])}" for k, v in sorted(d["live_only_by"].items())),
         f"    sim-only  {d['n_sonly']:>4}  {money(-d['sonly']):>10} (removed)   "
         + "  ".join(f"{k}: {v[0]} {money(v[1])}" for k, v in sorted(d["sim_only_by"].items())),
         f"    identity residual {d['resid']:.6f}" + ("" if abs(d["resid"]) < 0.005 else "   *** C3 FAILS ***"),
         ""]
    return L


def cap_census(label, base_by, capped_by) -> list[str]:
    L = [f"  {label}"]
    for s in STRATEGIES:
        b, c = base_by[s], capped_by[s]
        nb, nc = len(b), len(c)
        tb, tc = sum(r["net"] for r in b), sum(r["net"] for r in c)
        rem = nb - nc
        marg = (tb - tc) / rem - MEASURED if rem else float("nan")
        L.append(f"    {s.upper():<4} {nb:>6,} -> {nc:>6,}  refused {rem:>5,} ({(rem / nb if nb else 0):.1%})"
                 f"   per trade {money(tb / nb - MEASURED if nb else float('nan'))} -> "
                 f"{money(tc / nc - MEASURED if nc else float('nan'))}   refused trade worth {money(marg)}")
    return L + [""]


# --- main ----------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", action="append", default=None,
                   help="universe file(s); for each date the first file that has it is used")
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.ITCH")
    p.add_argument("--fills", default="var/fills")
    p.add_argument("--population", default=POPULATION_CSV)
    p.add_argument("--population-pairs", default=POPULATION_PAIRS)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/live_vs_sim.txt")
    p.add_argument("--csv", default="var/reports/live_vs_sim_trades.csv")
    p.add_argument("--json", default="var/reports/live_vs_sim.json")
    return p


def load_population(path: str, pairs: str):
    rows = {"mcl": [], "mc5": []}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["book"] in ("MCL +0", "MC5 +0"):
                s = r["book"].split()[0].lower()
                rows[s].append({"symbol": r["symbol"], "date": r["date"], "entry_et": r["entry_et"],
                                "exit_et": r["exit_et"], "net": float(r["net"]), "strategy": s})
    sd = defaultdict(int)
    for r in json.loads(Path(pairs).read_text(encoding="utf-8")):
        if r.get("first_seen"):
            sd[r["date"]] += 1
    return rows, dict(sd)


def main(argv=None) -> int:
    import time
    from common.databento_fetch import default_archive
    from common.report_io import emit

    a = build_parser().parse_args(argv)
    t0 = time.time()
    pairs_list = a.pairs or list(PAIRS)
    merged, src = merge_pairs(pairs_list, Path("var/state/live_vs_sim_pairs.json"))
    archive = Path(a.archive) if a.archive else default_archive()
    tasks, by_date = G.build_tasks(str(merged), archive, a.dataset, None)
    got, _ = G.run_sessions(run_day, tasks, G.jobs_from(a.jobs), "live_vs_sim")
    days = sorted(d for d in got if got[d])
    books = {b: [] for b in SIM_BOOKS}
    symdays, errs, universe_by_day = {}, [], {}
    for d in days:
        for b in SIM_BOOKS:
            books[b] += got[d]["books"][b]
        symdays[d] = got[d]["symdays"]
        errs += got[d]["error_days"]
        universe_by_day[d] = set(got[d]["symbols"])
    missing = sorted(set(by_date) - set(days))

    log = live_log(Path(a.fills))
    live_all = live_round_trips(log)
    live = [x for x in live_all if x["date"] in set(days)]
    # C3: paired round trips equal FILLED SELLs, per strategy per session
    sells = log[(log["status"] == "FILLED") & (log["action"] == "SELL")]
    sells = sells.assign(date=sells["ts_et"].dt.strftime("%Y-%m-%d"),
                         s=sells["strategy"].str.lower())
    c3 = []
    for (d, s), g in sells.groupby(["date", "s"]):
        if d in days:
            k = sum(1 for x in live if x["date"] == d and x["strategy"] == s)
            if k != len(g):
                c3.append(f"{d} {s}: paired {k} vs FILLED SELL {len(g)}")

    fm = {s: tag(feed_matched(books, s), s) for s in STRATEGIES}
    alt = {s: tag([r for r in books[f"{s.upper()} +0"] if feed_offset(r["date"]) == DELAY]
                  + [r for r in books[f"{s.upper()} +{DELAY}"] if feed_offset(r["date"]) == 0], s)
           for s in STRATEGIES}
    both = [d for d in days if d >= BOTH_FROM]
    apex_days = [d for d in both if apex_on(d)]
    off_days = [d for d in both if not apex_on(d)]

    def live_by(strat, sess, apex=None):
        return [dict(x, net=x["pnl"]) for x in live if x["strategy"] == strat and x["date"] in sess
                and (apex is None or x["apex"] == apex)]

    def sim_by(rows, sess):
        return [r for r in rows if r["date"] in sess]

    L = ["H-L1 (W02-0002) -- IS MC5 REALLY BETTER THAN MCL? LIVE AGAINST THE BACKTEST, SAME SESSIONS", "",
         f"  registered   {REGISTERED}",
         f"  sessions     {len(days)}  {days[0] if days else '-'} -> {days[-1] if days else '-'}"
         f"   (both strategies from {BOTH_FROM}: {len(both)}; apex-ON {len(apex_days)}, apex-OFF {len(off_days)})",
         f"  universe     " + ", ".join(f"{d}<-{Path(p).name}" for d, p in sorted(src.items()) if d in days),
         f"  no tape      {', '.join(missing) if missing else 'none'}",
         f"  symbol-days  {sum(symdays.values())}   errors {len(errs)}",
         f"  feed-matched +{DELAY} for sessions < {SIGNED_IN_FROM}, +0 from it",
         f"  C1 books vs feed_delay Arm B: {c1_check(books)}",
         f"  C2 universe overlap: {c2_check(pairs_list)}",
         f"  live         {len(live)} round trips on these sessions; C3 "
         + ("OK" if not c3 else "FAILS: " + "; ".join(c3)), ""]

    # ---- C4 on the live sessions
    allfm = fm["mcl"] + fm["mc5"]
    c4a = replay_cap(allfm, math.inf) == allfm
    one = replay_cap(allfm, 1)
    c4b = True
    for d in days:
        iv = sorted((minute(r["entry_et"]), minute(r["exit_et"])) for r in one if r["date"] == d)
        c4b &= all(iv[k + 1][0] >= iv[k][1] for k in range(len(iv) - 1))
    # ---- C6
    a_on = [r for r in books["MC5A +15"] if r["date"] in apex_days]
    a_off = [r for r in books[f"MC5 +{DELAY}"] if r["date"] in apex_days]
    key = lambda r: (r["symbol"], r["date"], r["entry_et"], r["exit_et"], round(r["net"], 4))
    c6 = len(set(map(key, a_on)) ^ set(map(key, a_off)))
    L += [f"  C4 cap=inf identity {'OK' if c4a else 'FAILS'};  cap=1 no overlap {'OK' if c4b else 'FAILS'}",
          f"  C6 apex-ON book differs from apex-OFF on {c6} trade rows" + ("" if c6 else "  *** MEASURED NOTHING ***"),
          ""]

    J = {"days": days, "symdays": symdays, "missing": missing, "verdicts": {}, "decomp": {}, "cap": {}}

    # ---- 1. live
    L += ["1. THE LIVE BOOK  (as logged; price-only P/L)", ""]
    for label, sess, apx in (("all rows, both running", both, None),
                             ("MC5 apex-OFF sessions only", off_days, None),
                             ("MC5 apex-ON sessions only", apex_days, None)):
        rows = {"mcl": as_val(live_by("mcl", sess), "net"), "mc5": as_val(live_by("mc5", sess, apx), "net")}
        v = verdicts(rows, sess, 0.0)
        J["verdicts"][f"live | {label}"] = v
        L += vrow(label, v)
    rows = {s: [dict(x, val=x["pnl"] - commission(x["entry_px"])) for x in live_by(s, both)] for s in STRATEGIES}
    v = verdicts(rows, both, 0.0)
    J["verdicts"]["live | all rows, with IBKR tiered commission"] = v
    L += vrow("all rows, with IBKR tiered commission", v)
    mcl_solo = [x for x in live if x["strategy"] == "mcl" and x["date"] < BOTH_FROM]
    L += [f"  MCL alone before {BOTH_FROM}: {len(mcl_solo)} trades {money(sum(x['pnl'] for x in mcl_solo))}"
          " (not in the comparison)", ""]

    # ---- 2/3. sim, same sessions
    L += ["2. SIM, FEED-MATCHED, SAME SESSIONS  (read at $4.26; per-trade difference is friction-invariant)", ""]
    for label, sess in (("uncapped, both running", both), ("uncapped, apex-OFF sessions", off_days),
                        ("uncapped, apex-ON sessions", apex_days)):
        v = verdicts({s: as_val(sim_by(fm[s], sess), "net") for s in STRATEGIES}, sess, MEASURED, symdays)
        J["verdicts"][f"sim | {label}"] = v
        L += vrow(label, v)
    v = verdicts({"mcl": as_val(sim_by(fm["mcl"], apex_days), "net"),
                  "mc5": as_val([r for r in books["MC5A +15"] if r["date"] in apex_days], "net")},
                 apex_days, MEASURED, symdays)
    J["verdicts"]["sim | apex-ON sessions, MC5 apex-ON book"] = v
    L += vrow("apex-ON sessions, MC5 on the apex-ON book", v)
    v = verdicts({s: as_val(sim_by(alt[s], both), "net") for s in STRATEGIES}, both, MEASURED, symdays)
    J["verdicts"]["sim | sensitivity: the other feed offset"] = v
    L += vrow("sensitivity: the OTHER feed offset per session", v)

    L += ["3. SIM, FEED-MATCHED, SHARED CAP OF 3 REPLAYED", ""]
    capped_live = {}
    for first in STRATEGIES:
        adm = replay_cap(sim_by(fm["mcl"], both) + sim_by(fm["mc5"], both), CAP, "shared", first)
        by = {s: [r for r in adm if r["strategy"] == s] for s in STRATEGIES}
        capped_live[first] = by
        v = verdicts({s: as_val(by[s], "net") for s in STRATEGIES}, both, MEASURED, symdays)
        J["verdicts"][f"sim capped | {first.upper()} first"] = v
        L += vrow(f"shared cap, {first.upper()} first on a same-minute tie", v)
    base = {s: sim_by(fm[s], both) for s in STRATEGIES}
    L += ["  cap census on the live sessions (sim):"]
    for first in STRATEGIES:
        L += cap_census(f"{first.upper()} first", base, capped_live[first])
    lr = log[(log["action"] == "BUY") & (log["status"] == "SKIPPED_CONCURRENCY_CAP")]
    lr = lr[lr["ts_et"].dt.strftime("%Y-%m-%d").isin(both)]
    lb = log[(log["action"] == "BUY")]
    lb = lb[lb["ts_et"].dt.strftime("%Y-%m-%d").isin(both)]
    L += ["  live, same sessions: BUY rows refused by the cap / all BUY rows"]
    for s in STRATEGIES:
        k = int((lr["strategy"].str.lower() == s).sum())
        t = int((lb["strategy"].str.lower() == s).sum())
        L.append(f"    {s.upper():<4} {k:>4} / {t:<4} ({(k / t if t else 0):.1%})")
        J["cap"][f"live refused {s}"] = [k, t]
    L.append("")

    # ---- 4. population
    pop, pop_sd = load_population(a.population, a.population_pairs)
    psess = sorted(pop_sd)
    c5 = (len(pop["mcl"]), round(sum(r["net"] - MEASURED for r in pop["mcl"]) / max(1, len(pop["mcl"])), 2),
          len(pop["mc5"]), round(sum(r["net"] - MEASURED for r in pop["mc5"]) / max(1, len(pop["mc5"])), 2))
    L += ["4. THE POPULATION  (ITCH v2 +0, feed_delay_trades.csv)", "",
          f"  C5  MCL {c5[0]:,} at {money(c5[1])}   MC5 {c5[2]:,} at {money(c5[3])}   "
          + ("OK" if c5 == (3908, -8.97, 6462, -8.57) else "*** DOES NOT MATCH 3,908/(8.97), 6,462/(8.57) ***"),
          f"  symbol-days from {Path(a.population_pairs).name}: {sum(pop_sd.values()):,} over {len(psess)} sessions", ""]
    v = verdicts({s: as_val(pop[s], "net") for s in STRATEGIES}, psess, MEASURED, pop_sd)
    J["verdicts"]["population | uncapped (published)"] = v
    L += vrow("uncapped (published)", v)
    for scope in ("shared", "strategy"):
        for first in STRATEGIES:
            adm = replay_cap(pop["mcl"] + pop["mc5"], CAP, scope, first)
            by = {s: [r for r in adm if r["strategy"] == s] for s in STRATEGIES}
            v = verdicts({s: as_val(by[s], "net") for s in STRATEGIES}, psess, MEASURED, pop_sd)
            J["verdicts"][f"population | cap {scope}, {first.upper()} first"] = v
            L += vrow(f"cap 3 {scope}, {first.upper()} first", v)
            L += cap_census(f"census, cap 3 {scope}, {first.upper()} first", pop, by)
            J["cap"][f"population {scope} {first}"] = {
                s: {"n0": len(pop[s]), "n1": len(by[s]),
                    "net0": sum(r["net"] for r in pop[s]), "net1": sum(r["net"] for r in by[s])}
                for s in STRATEGIES}

    # ---- 5. decomposition
    L += ["5. LIVE - SIM, DECOMPOSED  (feed-matched, uncapped; gross; join within 2 bars)", ""]
    out_rows = []
    for s in STRATEGIES:
        groups = [("all sessions", days, None)] if s == "mcl" else \
                 [("apex-ON sessions, vs apex-ON book", apex_days, "A"),
                  ("apex-ON sessions, vs published book", apex_days, None),
                  ("apex-OFF sessions", off_days, None)]
        for label, sess, which in groups:
            lv = [x for x in live if x["strategy"] == s and x["date"] in sess]
            sm = ([r for r in books["MC5A +15"] if r["date"] in sess] if which == "A"
                  else sim_by(fm[s], sess))
            d = decompose(lv, sm, s, log, universe_by_day)
            d1 = decompose(lv, sm, s, log, universe_by_day, tol_bars=1)
            J["decomp"][f"{s} | {label}"] = {k: v for k, v in d.items()
                                             if k not in ("pairs", "lonly_idx", "sonly_idx")}
            L += decomp_block(f"{s.upper()} {label}   ({len(sess)} sessions)", d)
            L.append(f"    sensitivity, join within 1 bar: matched {d1['n_match']}, execution "
                     f"{money(d1['m_live'] - d1['m_sim'])}")
            L.append("")
            if which is None:
                for i, j, dt in d["pairs"]:
                    out_rows.append({"kind": "matched", "strategy": s, "group": label,
                                     "symbol": lv[i]["symbol"], "date": lv[i]["date"],
                                     "live_entry": lv[i]["open_ts"].strftime("%H:%M:%S"),
                                     "sim_entry": sm[j]["entry_et"], "live_pnl": round(lv[i]["pnl"], 2),
                                     "sim_net": round(sm[j]["net"], 2), "dt_min": round(dt, 2),
                                     "live_entry_px": lv[i]["entry_px"], "sim_entry_px": sm[j]["entry_px"],
                                     "live_exit_px": lv[i]["exit_px"], "sim_exit_px": sm[j]["exit_px"],
                                     "sim_reason": sm[j]["reason"], "live_reason": lv[i]["reason"]})
                for i in d["lonly_idx"]:
                    out_rows.append({"kind": "live-only", "strategy": s, "group": label,
                                     "symbol": lv[i]["symbol"], "date": lv[i]["date"],
                                     "live_entry": lv[i]["open_ts"].strftime("%H:%M:%S"),
                                     "live_pnl": round(lv[i]["pnl"], 2), "live_reason": lv[i]["reason"],
                                     "class": classify_live_only(lv[i], universe_by_day)})
                for j in d["sonly_idx"]:
                    out_rows.append({"kind": "sim-only", "strategy": s, "group": label,
                                     "symbol": sm[j]["symbol"], "date": sm[j]["date"],
                                     "sim_entry": sm[j]["entry_et"], "sim_net": round(sm[j]["net"], 2),
                                     "sim_reason": sm[j]["reason"],
                                     "class": classify_sim_only(sm[j], s, log, lv)})

    L += ["WHAT THIS IS NOT", "",
          "  NOT A GATE and not a live change. The words are the registration's three.",
          "  The cap replay only removes sim trades; a refused trade does not release",
          "  later entries the engine suppressed while it was held.", ""]
    if errs:
        L += ["symbol-days dropped:"] + [f"  {e}" for e in errs[:20]]
    L.append(f"  elapsed {time.time() - t0:.0f}s")
    emit("\n".join(L), a.out, header=f"common.live_vs_sim sessions={len(days)} registered={REGISTERED}")
    cols = ["kind", "strategy", "group", "symbol", "date", "live_entry", "sim_entry", "live_pnl", "sim_net",
            "dt_min", "live_entry_px", "sim_entry_px", "live_exit_px", "sim_exit_px", "live_reason",
            "sim_reason", "class"]
    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    with open(a.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)
    G.write_csv(str(Path(a.csv).with_name("live_vs_sim_books.csv")), books)
    Path(a.json).write_text(json.dumps(J, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
