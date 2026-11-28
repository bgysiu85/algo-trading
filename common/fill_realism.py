#!/usr/bin/env python3
r"""W03-0016 -- fill realism: how much of the MCL/MC5 backtest rests on fills
a real order would not have got, and were the live signals that did not fill
the backtest's winners?

    python -m common.fill_realism --jobs 8
    python -m common.fill_realism --limit 20 --jobs 2        # smoke test

DESCRIPTIVE, NOT A RULE. Nothing here is registered, nothing passes or fails,
and nothing becomes a gate without its own registration (W03-0016 brief).

THE FLAW BEING CHECKED
----------------------
The engines fill at the CLOSE OF THE SIGNAL BAR (+1 tick). Live, the order
leaves ~60 seconds after that bar closes, so the price actually paid belongs to
the NEXT 1-minute bar (common/entry_fill.py measured this). Cameron's own
automated version made +$20,000 in a 30-day backtest and failed live because
the best trades jumped past his buy orders. Same question for our books.

THE POPULATION
--------------
Read straight from var/reports/chase_gate_trades.csv, books `MCL` (3,908) and
`MC5` (6,462) only -- no engine re-run, the same population every W03 study
has used. 100 shares.

DEFINITIONS (each is a reading of the brief, fixed here before the first run)
-----------------------------------------------------------------------------
TRIGGER       the backtest entry price (signal-bar close + 1 tick).
ENTRY BAR     the first 1-minute bar that STARTS at or after the signal bar's
              close: MCL signal bar is 1 minute, MC5's is 5 minutes. If the
              symbol printed no bar within MAX_WAIT_MIN of that, there was
              nothing to buy: bucket "no print".
GAP           entry-bar open / trigger - 1. Buckets: open <= trigger, 0-1%,
              1-3%, >3% above. ">10%" is reported inside ">3%".
MISSED        the entry bar's LOW is above trigger * (1 + 20bps): a marketable
              limit crossed by trader.py's LIMIT_CROSS_BPS = 20 never fills
              (or there was no print). A bar that dips into the limit is
              treated as fillable -- bar data cannot say more than that.
BEST 20       the 20 highest-net trades of the book at R1 pricing.
SPIKE-3MIN    the signal bar closes within [T+1m, T+4m] of the START of the
              symbol's first 1-minute bar of the session whose close is >= 10%
              above its own open or above the previous bar's close. DEPTH: the
              entry bar's volume >= 10 x 100 shares AND its low <= the limit.
              (Bar volume is an UPPER bound on what traded at or below the
              fill price; ticks would be needed to be exact.)
OVER-10%      backtest entry price > 1.10 x the close of the last 1-minute bar
              BEFORE the signal bar starts (the broker's 10% limit rejection).
LULD          signal bar closes 09:30-16:00; band set by the PRIOR close:
              10% above $3, 20% for $0.75-$3, 15c below $0.75. Reported by the
              distance from the trigger up to the upper band (<=1%, <=3%, and
              at-or-above). The real band reference is a 5-minute average;
              the prior close is the brief's own simplification.
COSTS         gross = (exit - entry) x 100; commission = gross - engine net;
              R1 = common.exec_cost leg-by-leg cost (ENTRY + TRAIL, or
              WCLOSE for a window_close exit). NET AT R1 = engine net - R1.
              A win is NET AT R1 > 0.

LIVE ARM
--------
Every live BUY signal logged NO_FILL_ABANDONED, NO_FILL_CANCELLED or
SKIPPED_DRIFT since 2026-09-10, joined to the SIM trades of
var/reports/live_vs_sim_trades.csv (same strategy, symbol, session; sim signal
bar at most one bar-length before the live minute). That file's sessions end
where `live_vs_sim` last ran: signals after it are counted and reported as
OUTSIDE COVERAGE, not guessed. Unfilled SELLs are counted apart -- a stop that
did not fill is a different problem from an entry that did not fill.

TWO FILL FOLDERS (since the NAS trader, W10-0013): var/fills, written on the
PC, and var/nas_mirror/fills, copied from the NAS. Both are read.
  * A file from a DRY session (or one mixing dry and paper rows, or unreadable)
    is left out and named, by the rule deploy/nas_trader/pull_nas_var.py uses to
    keep it out of var/fills.
  * The same file name in both folders is one day's log: a row identical in every
    column counts once. If the copies differ, every distinct row is kept and the
    name is printed, for a person to check.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from collections import Counter, defaultdict
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from deploy.nas_trader.pull_nas_var import dry_session_reason

ET = ZoneInfo("America/New_York")

TRADES_CSV = "var/reports/chase_gate_trades.csv"
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
DATASET = "XNAS.ITCH"
REGULAR_CLOSE = "var/state/regular_close.json"
FILLS_GLOBS = ("var/fills/*_fills_*.csv",                # written on the PC
               "var/nas_mirror/fills/*_fills_*.csv")     # copied from the NAS trader
LIVE_SIM = "var/reports/live_vs_sim_trades.csv"
LIVE_FIRST_DAY = "2026-09-10"

BOOKS = ("MCL", "MC5")
BAR_MIN = {"MCL": 1, "MC5": 5}
QTY = 100
TICK = 0.01
LIMIT_CROSS_BPS = 20            # brokers/ibkr/trader.py LIMIT_CROSS_BPS
MAX_WAIT_MIN = 5                # no bar this soon after the signal close = no print
SPIKE_MOVE = 0.10
SPIKE_WINDOW_MIN = 3
DEPTH_MULT = 10
BROKER_LIMIT = 0.10
FRICTION_FLAT = 4.26

GAP_BUCKETS = ("open <= trigger", "0-1% above", "1-3% above", ">3% above", "no print")
LIVE_TAGS = ("NO_FILL_ABANDONED", "NO_FILL_CANCELLED", "SKIPPED_DRIFT")


def money(x: float) -> str:
    if x != x:
        return "n/a"
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def pct(x: float, d: int = 1) -> str:
    return "n/a" if x != x else f"{100 * x:.{d}f}%"


# --- pure measurement ---------------------------------------------------------

def gap_bucket(gap: float | None) -> str:
    if gap is None:
        return "no print"
    if gap <= 0:
        return "open <= trigger"
    if gap <= 0.01:
        return "0-1% above"
    if gap <= 0.03:
        return "1-3% above"
    return ">3% above"


def luld_upper(prior_close: float) -> float:
    """Upper LULD band from the prior close (the brief's tiers)."""
    if prior_close > 3.0:
        return prior_close * 1.10
    if prior_close >= 0.75:
        return prior_close * 1.20
    return prior_close + 0.15


def first_spike_start(bars: pd.DataFrame) -> pd.Timestamp | None:
    """Start of the first 1-minute bar of the session that closed >= 10% above
    its own open or above the previous bar's close (previous bar of the SAME
    session; the first bar has no prior to compare with except its own open)."""
    if bars.empty:
        return None
    o = bars["open"].to_numpy(float)
    c = bars["close"].to_numpy(float)
    prev = np.concatenate(([np.nan], c[:-1]))
    with np.errstate(divide="ignore", invalid="ignore"):
        own = c / o - 1.0
        seq = c / prev - 1.0
    hit = (own >= SPIKE_MOVE) | (seq >= SPIKE_MOVE)
    if not hit.any():
        return None
    return bars.index[int(np.argmax(hit))]


def measure_trade(bars: pd.DataFrame, row: dict, prior_close: float | None) -> dict:
    """One trade against its symbol's 1-minute bars (ET-indexed, ascending,
    the session's own bars). `row` is a chase_gate_trades.csv row with numeric
    entry_px/exit_px/net and entry_et 'HH:MM'. Pure: no I/O."""
    book = row["book"]
    d = _date.fromisoformat(row["date"])
    hh, mm = row["entry_et"].split(":")
    sig_start = pd.Timestamp(datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=ET))
    sig_close = sig_start + pd.Timedelta(minutes=BAR_MIN[book])
    px = row["entry_px"]
    limit = px * (1.0 + LIMIT_CROSS_BPS / 10_000.0)

    out: dict = {"sig_close": sig_close}

    # entry bar
    later = bars[bars.index >= sig_close]
    nxt = None
    if not later.empty and later.index[0] <= sig_close + pd.Timedelta(minutes=MAX_WAIT_MIN):
        nxt = later.iloc[0]
    if nxt is None:
        out.update(gap=None, bucket="no print", missed=True, depth_ok=False)
    else:
        gap = float(nxt["open"]) / px - 1.0
        out.update(gap=gap, bucket=gap_bucket(gap),
                   missed=bool(float(nxt["low"]) > limit),
                   depth_ok=bool(float(nxt["volume"]) >= DEPTH_MULT * QTY
                                 and float(nxt["low"]) <= limit))

    # over-10% (backtest fill vs the bar before the signal bar)
    before = bars[bars.index < sig_start]
    if before.empty:
        out["over10"] = None
    else:
        out["over10"] = bool(px > (1.0 + BROKER_LIMIT) * float(before["close"].iloc[-1]))

    # first-3-minutes-of-spike
    t0 = first_spike_start(bars)
    if t0 is None:
        out["spike3"] = False
    else:
        lo = t0 + pd.Timedelta(minutes=1)
        out["spike3"] = bool(lo <= sig_close <= lo + pd.Timedelta(minutes=SPIKE_WINDOW_MIN))

    # LULD
    rth = sig_close.time() >= datetime(2000, 1, 1, 9, 30).time() and \
        sig_close.time() <= datetime(2000, 1, 1, 16, 0).time()
    if not rth or not prior_close or prior_close <= 0:
        out["luld_dist"] = None
    else:
        up = luld_upper(prior_close)
        out["luld_dist"] = (up - px) / px
    return out


def cost_fields(row: dict, r1_fn) -> dict:
    gross = (row["exit_px"] - row["entry_px"]) * QTY
    commission = gross - row["net"]
    leg = "WCLOSE" if row.get("reason") == "window_close" else "TRAIL"
    r1 = r1_fn(row["entry_px"], row["exit_px"], QTY, leg)
    return {"gross": gross, "commission": commission, "r1": r1,
            "net_r1": row["net"] - r1, "net_flat": row["net"] - FRICTION_FLAT}


# --- aggregation & rendering ---------------------------------------------------

def agg(rows: list[dict]) -> dict:
    n = len(rows)
    nr = [r["net_r1"] for r in rows]
    return {"n": n,
            "wins": sum(1 for x in nr if x > 0),
            "losses": sum(1 for x in nr if x <= 0),
            "gross": sum(r["gross"] for r in rows),
            "commission": sum(r["commission"] for r in rows),
            "r1": sum(r["r1"] for r in rows),
            "net_r1": sum(nr),
            "net": sum(r["net"] for r in rows)}


def table(title: str, groups: list[tuple[str, list[dict]]], total: list[dict]) -> list[str]:
    L = [title,
         f"  {'':<18}{'trades':>8}{'wins':>7}{'losses':>8}{'gross':>13}"
         f"{'commission':>13}{'R1 cost':>12}{'net at R1':>14}"]
    for name, rs in groups + [("ALL", total)]:
        a = agg(rs)
        L.append(f"  {name:<18}{a['n']:>8,}{a['wins']:>7,}{a['losses']:>8,}"
                 f"{money(a['gross']):>13}{money(a['commission']):>13}"
                 f"{money(a['r1']):>12}{money(a['net_r1']):>14}")
    return L


def share_line(label: str, sub: list[dict], whole: list[dict]) -> str:
    a, w = agg(sub), agg(whole)
    pos_sub = sum(r["net_r1"] for r in sub if r["net_r1"] > 0)
    pos_all = sum(r["net_r1"] for r in whole if r["net_r1"] > 0)
    return (f"  {label:<46}{a['n']:>7,} of {w['n']:,} trades ({pct(a['n'] / w['n'] if w['n'] else float('nan'))})"
            f"   net at R1 {money(a['net_r1'])} of {money(w['net_r1'])}"
            f"   winners' profit {money(pos_sub)} of {money(pos_all)}"
            f" ({pct(pos_sub / pos_all if pos_all else float('nan'))})")


def book_block(book: str, rows: list[dict]) -> list[str]:
    L = ["", "=" * 100, f"{book}  --  {len(rows):,} backtest trades, 100 shares, "
         f"{len({(r['symbol'], r['date']) for r in rows}):,} symbol-days", "=" * 100, ""]
    L += table("1. GAP FROM TRIGGER TO THE ENTRY BAR'S OPEN  (trigger = backtest entry price)",
               [(b, [r for r in rows if r["bucket"] == b]) for b in GAP_BUCKETS], rows)
    gapped = [r for r in rows if r["gap"] is not None]
    over10g = [r for r in gapped if r["gap"] > 0.10]
    L += ["", f"   of '>3% above', gapped more than 10%: {len(over10g):,} trades, "
          f"net at R1 {money(sum(r['net_r1'] for r in over10g))}"]

    best = sorted(rows, key=lambda r: -r["net_r1"])[:20]
    far = [r for r in best if r["bucket"] in ("1-3% above", ">3% above")]
    nop = [r for r in best if r["bucket"] == "no print"]
    L += ["", f"2. THE BOOK'S 20 BEST TRADES (net at R1): {len(far)} of 20 sit in the >1% buckets"
          f" (1-3% or >3%); {len(nop)} of 20 had no print at all",
          f"  {'symbol':<8}{'date':<12}{'entry':>7}{'exit':>7}{'entry px':>10}{'exit px':>9}"
          f"{'gap':>9}{'bucket':>18}{'net at R1':>12}"]
    for r in best:
        g = "n/a" if r["gap"] is None else pct(r["gap"], 2)
        L.append(f"  {r['symbol']:<8}{r['date']:<12}{r['entry_et']:>7}{r['exit_et']:>7}"
                 f"{r['entry_px']:>10.3f}{r['exit_px']:>9.3f}{g:>9}{r['bucket']:>18}"
                 f"{money(r['net_r1']):>12}")

    L += ["", "3. WHAT A REAL ORDER WOULD NOT HAVE GOT  (profit shares are of the book's winners)",
          share_line("missed: entry bar never traded down to a 20bp-cross limit",
                     [r for r in rows if r["missed"]], rows),
          share_line("first 3 minutes of a symbol's first +10% 1-min move",
                     [r for r in rows if r["spike3"]], rows),
          share_line("   ... of those, entry bar volume >= 10x our size at the limit",
                     [r for r in rows if r["spike3"] and r["depth_ok"]], rows),
          share_line("   ... of those, NOT enough depth in the entry bar",
                     [r for r in rows if r["spike3"] and not r["depth_ok"]], rows),
          share_line("fill price > 10% above the previous bar's close",
                     [r for r in rows if r["over10"]], rows)]

    luld = [r for r in rows if r["luld_dist"] is not None]
    L += ["", f"4. POST-09:30 ENTRIES NEAR AN LULD UPPER BAND  ({len(luld):,} of {len(rows):,} trades "
          "have a 09:30-16:00 signal and a prior close)"]
    for lbl, f in (("within 1% of the upper band (or above it)", lambda r: r["luld_dist"] <= 0.01),
                   ("within 3% of the upper band (or above it)", lambda r: r["luld_dist"] <= 0.03),
                   ("at or above the upper band", lambda r: r["luld_dist"] <= 0)):
        L.append(share_line(lbl, [r for r in luld if f(r)], rows))
    return L


# --- live arm -------------------------------------------------------------------

def _hm(s: str) -> int:
    h, m = s.split(":")[:2]
    return int(h) * 60 + int(m)


def _row_key(r: dict) -> tuple:
    return tuple(sorted((str(k), str(v)) for k, v in r.items()))


def read_fill_rows(fills_globs) -> tuple[list[dict], dict]:
    """The rows of every fill log matched by `fills_globs` (one glob or several),
    and what was done: {"matched": {glob: files}, "days": file names used,
    "left_out": ["path (why)"], "merged": names whose copies differ}. See the
    module docstring for the dry-session and two-copies rules."""
    if isinstance(fills_globs, str):
        fills_globs = [fills_globs]
    info: dict = {"matched": {}, "days": 0, "left_out": [], "merged": []}
    by_name: dict[str, list[str]] = defaultdict(list)
    for pattern in fills_globs:
        paths = sorted(glob.glob(pattern))
        info["matched"][pattern] = len(paths)
        for path in paths:
            by_name[Path(path).name].append(path)

    rows: list[dict] = []
    for name in sorted(by_name):
        copies = []
        for path in by_name[name]:
            why = dry_session_reason(Path(path))
            if why:
                info["left_out"].append(f"{Path(path)} ({why})")
                continue
            with open(path, newline="", encoding="utf-8") as fh:
                copies.append(list(csv.DictReader(fh)))
        if not copies:
            continue
        info["days"] += 1
        kept = list(copies[0])
        have = Counter(_row_key(r) for r in kept)
        for other in copies[1:]:
            if Counter(_row_key(r) for r in other) != Counter(_row_key(r) for r in copies[0]):
                info["merged"].append(name)
            seen: Counter = Counter()
            for r in other:
                key = _row_key(r)
                seen[key] += 1
                if seen[key] > have[key]:            # a row this day's log does not have yet
                    kept.append(r)
                    have[key] += 1
        rows.extend(kept)
    return rows, info


def read_live_signals(fills_globs, first_day: str,
                      info: dict | None = None) -> tuple[list[dict], Counter]:
    """(unfilled BUY signals, counts of every tagged row by (action, tag)).
    Pass a dict as `info` to receive read_fill_rows' account of the files."""
    rows, account = read_fill_rows(fills_globs)
    if info is not None:
        info.update(account)
    sig: list[dict] = []
    counts: Counter = Counter()
    for r in rows:
        ts = r.get("ts_et") or ""
        if ts[:10] < first_day:
            continue
        tag = next((v for v in r.values() if v in LIVE_TAGS), None)
        if tag is None:
            continue
        act = r.get("action", "")
        counts[(act, tag)] += 1
        if act == "BUY":
            sig.append({"ts": ts, "date": ts[:10], "minute": _hm(ts[11:16]),
                        "strategy": (r.get("strategy") or "").upper(),
                        "symbol": r.get("symbol", ""), "tag": tag,
                        "ref_close": r.get("ref_close", ""),
                        "reject": r.get("reject_reason", "")})
    sig.sort(key=lambda s: s["ts"])
    return sig, counts


def source_lines(info: dict) -> list[str]:
    """Which fill logs the live arm read, so a missing folder or a skipped day is visible."""
    L = ["  Fill logs: " + "; ".join(f"{n:,} file(s) match {p}" for p, n in info["matched"].items())
         + f".  Day files used: {info['days']:,}."]
    L += [f"  *** NO FILES match {p} -- that folder is not in the figures below ***"
          for p, n in info["matched"].items() if n == 0]
    if info["left_out"]:
        L.append(f"  Left out ({len(info['left_out']):,}, dry session or unreadable):")
        L += [f"    {x}" for x in info["left_out"]]
    if info["merged"]:
        L.append("  *** CHECK: the two folders' copies differ; every distinct row was kept: "
                 + ", ".join(info["merged"]) + " ***")
    return L


def read_sim(path: str) -> tuple[list[dict], str]:
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] not in ("matched", "sim-only"):
                continue
            rows.append({"strategy": r["strategy"].upper(), "symbol": r["symbol"],
                         "date": r["date"], "sim_entry": r["sim_entry"],
                         "minute": _hm(r["sim_entry"]), "kind": r["kind"],
                         "entry_px": float(r["sim_entry_px"] or 0),
                         "exit_px": float(r["sim_exit_px"] or 0),
                         "sim_net": float(r["sim_net"] or 0),
                         "reason": r.get("sim_reason", "")})
    seen, out = set(), []
    for r in rows:                                  # one row per sim trade, any group
        k = (r["strategy"], r["symbol"], r["date"], r["sim_entry"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out, max((r["date"] for r in out), default="")


def join_live(signals: list[dict], sim: list[dict], last_sim_day: str) -> dict:
    idx: dict = defaultdict(list)
    for s in sim:
        idx[(s["strategy"], s["symbol"], s["date"])].append(s)
    booked, unbooked, outside = [], [], []
    for g in signals:
        if last_sim_day and g["date"] > last_sim_day:
            outside.append(g)
            continue
        span = BAR_MIN.get(g["strategy"], 1) + 1
        hit = [s for s in idx.get((g["strategy"], g["symbol"], g["date"]), [])
               if 0 <= g["minute"] - s["minute"] <= span]
        if hit:
            booked.append((g, min(hit, key=lambda s: g["minute"] - s["minute"])))
        else:
            unbooked.append(g)
    return {"booked": booked, "unbooked": unbooked, "outside": outside}


def live_block(signals, counts, joined, last_sim_day, first_day) -> list[str]:
    L = ["", "=" * 100, f"LIVE ARM  --  unfilled / skipped live signals since {first_day}", "=" * 100, ""]
    by_tag = Counter(s["tag"] for s in signals)
    L.append("  BUY signals by tag: " + ", ".join(f"{t} {by_tag.get(t, 0):,}" for t in LIVE_TAGS)
             + f"   (total {len(signals):,})")
    sells = {t: counts.get(("SELL", t), 0) for t in LIVE_TAGS}
    L.append("  SELL (exit) orders by tag, counted apart: "
             + ", ".join(f"{t} {n:,}" for t, n in sells.items()))
    L.append(f"  Sim trades available through {last_sim_day or 'n/a'}; "
             f"{len(joined['outside']):,} BUY signals are after that and OUTSIDE COVERAGE.")
    b = joined["booked"]
    nets = [s["sim_net"] for _, s in b]
    L += ["", f"  The backtest BOOKED a trade for {len(b):,} of "
          f"{len(signals) - len(joined['outside']):,} covered BUY signals "
          f"({len(joined['unbooked']):,} had no sim trade at that symbol and minute).",
          f"  Those {len(b):,} sim trades: net {money(sum(nets))}, "
          f"winners {sum(1 for x in nets if x > 0):,} ({money(sum(x for x in nets if x > 0))}), "
          f"losers {sum(1 for x in nets if x <= 0):,} ({money(sum(x for x in nets if x <= 0))})"]
    for tag in LIVE_TAGS:
        sub = [s["sim_net"] for g, s in b if g["tag"] == tag]
        L.append(f"    {tag:<20}{len(sub):>5,} booked   net {money(sum(sub)):>12}   "
                 f"winners {sum(1 for x in sub if x > 0):,}")
    L += ["", f"  {'live ts':<20}{'strat':<6}{'symbol':<8}{'tag':<20}{'sim bar':>8}"
          f"{'sim in':>9}{'sim out':>9}{'sim net':>11}"]
    for g, s in sorted(b, key=lambda gs: -gs[1]["sim_net"]):
        L.append(f"  {g['ts']:<20}{g['strategy']:<6}{g['symbol']:<8}{g['tag']:<20}"
                 f"{s['sim_entry']:>8}{s['entry_px']:>9.3f}{s['exit_px']:>9.3f}{money(s['sim_net']):>11}")
    return L


# --- the engine-free session pass --------------------------------------------------

def run_day(task: tuple) -> tuple:
    """(paths, day, rows, prior_closes, r1_state) -> (day, measured rows, err)."""
    from common.dbn_io import read_dbn
    from common import exec_cost as X

    paths, day, rows, prior, r1_state = task
    try:
        f = read_dbn(Path(paths[-1]))
    except Exception as e:                                   # noqa: BLE001
        return day, None, f"unreadable ({type(e).__name__}: {e})"
    if f.empty or Path(paths[-1]).name[:10] != day:
        return day, None, ""
    f.index = f.index.tz_convert(ET)
    wanted = {r["symbol"] for r in rows}
    f = f[f["symbol"].isin(wanted)].sort_index(kind="mergesort")
    f = f[f.index.date == _date.fromisoformat(day)]
    r1_fn = lambda e, x, q, leg: X.round_trip_cost_dollars(e, x, q, exit_leg=leg, state=r1_state)  # noqa: E731

    out = []
    for r in rows:
        bars = f[f["symbol"] == r["symbol"]]
        m = measure_trade(bars, r, prior.get(r["symbol"]))
        out.append({**r, **m, **cost_fields(r, r1_fn)})
    return day, out, ""


def load_book_rows(path: str) -> dict[str, list[dict]]:
    p = Path(path)
    if not p.exists():
        sys.exit(f"{p} does not exist -- it is written by `python -m common.chase_gate`.")
    out: dict[str, list[dict]] = {b: [] for b in BOOKS}
    with p.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["book"] in out:
                out[r["book"]].append(dict(r, entry_px=float(r["entry_px"]),
                                           exit_px=float(r["exit_px"]), net=float(r["net"])))
    return out


def write_csv(path: str, measured: dict[str, list[dict]]) -> None:
    cols = ["book", "symbol", "date", "entry_et", "exit_et", "entry_px", "exit_px", "reason",
            "net", "gross", "commission", "r1", "net_r1", "gap", "bucket", "missed",
            "depth_ok", "over10", "spike3", "luld_dist"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for b in BOOKS:
            for r in measured[b]:
                w.writerow(r)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades-csv", default=TRADES_CSV)
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--regular-close", default=REGULAR_CLOSE)
    p.add_argument("--fills", nargs="+", default=list(FILLS_GLOBS),
                   help="one or more fill-log globs (default: var/fills and var/nas_mirror/fills)")
    p.add_argument("--live-sim", default=LIVE_SIM)
    p.add_argument("--live-first-day", default=LIVE_FIRST_DAY)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--live-only", action="store_true",
                   help="skip the tape pass; run only the live arm (needs no archive)")
    p.add_argument("--out", default="var/reports/w03_0016_fill_realism.txt")
    p.add_argument("--csv", default="var/reports/w03_0016_fill_realism_trades.csv")
    return p


def main(argv=None) -> int:
    from common.report_io import emit
    a = build_parser().parse_args(argv)
    L = ["W03-0016 -- FILL REALISM: MCL / MC5 backtest vs what real orders would have got",
         "Negatives in brackets. Descriptive only; nothing here is a rule.", ""]
    header = f"common.fill_realism trades={a.trades_csv} qty={QTY} cross={LIMIT_CROSS_BPS}bp"

    measured: dict[str, list[dict]] = {b: [] for b in BOOKS}
    if not a.live_only:
        from common import exec_cost as X
        from common import gate_study as G
        from common.databento_fetch import default_archive
        from common.dux_veto import load_prev_closes, prev_close_lookup

        books = load_book_rows(a.trades_csv)
        print("books:", {b: len(r) for b, r in books.items()}, flush=True)
        by_day: dict[str, list[dict]] = defaultdict(list)
        for b in BOOKS:
            for r in books[b]:
                by_day[r["date"]].append(r)

        archive = Path(a.archive) if a.archive else default_archive()
        tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
        session_days = [t[1] for t in tasks]
        prior_map: dict = {}
        if Path(a.regular_close).exists():
            prior_map = prev_close_lookup(load_prev_closes(a.regular_close), session_days)
        else:
            print(f"! {a.regular_close} missing: LULD block will be empty", flush=True)
        r1_state = X.current()
        tasks = [(p, d, by_day[d], {s: c for (s, dd), c in prior_map.items() if dd == d}, r1_state)
                 for p, d, _u in tasks if d in by_day]
        got, elapsed = G.run_sessions(run_day, tasks, G.jobs_from(a.jobs), "fill_realism")
        for day in sorted(got):
            for r in got[day]:
                measured[r["book"]].append(r)
        have = sum(len(v) for v in measured.values())
        want = sum(len(v) for v in books.values())
        L.append(f"Sessions run {len(got):,}; trades measured {have:,} of {want:,}"
                 + ("" if have == want else
                    f"  *** {want - have:,} trades are on sessions with no archive slice / "
                    "unreadable slice and are NOT in any table below ***"))
        L.append(f"R1 pricing: {X.describe(r1_state)}")
        for b in BOOKS:
            if measured[b]:
                L += book_block(b, measured[b])
        if a.csv:
            write_csv(a.csv, measured)

    sources: dict = {}
    sig, counts = read_live_signals(a.fills, a.live_first_day, info=sources)
    if Path(a.live_sim).exists():
        sim, last = read_sim(a.live_sim)
    else:
        sim, last = [], ""
        L.append(f"! {a.live_sim} missing: live arm cannot join to the sim")
    L += live_block(sig, counts, join_live(sig, sim, last), last, a.live_first_day)
    L += [""] + source_lines(sources)
    emit("\n".join(L), a.out, header=header)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
