#!/usr/bin/env python3
r"""H-D1 -- what the live feed's 900 seconds cost, and whether they are the
shape of the live book.

    python -m common.feed_delay --jobs 8                          # Arm A, ITCH v2
    python -m common.feed_delay --pairs var/state/screen_pairs_pit_itch_ext.json \
        --out var/reports/feed_delay_live.txt --csv var/reports/feed_delay_live_trades.csv

Registered in docs/research/REGISTERED_feed_delay_cost.md (da5a00d), committed
before this file existed.

WHAT IS MODELLED, EXACTLY
-------------------------
Until 2026-09-18 the live watchlist came from TradingView's scanner polled
without a login, which TradingView labels `delayed_streaming_900`. The live
trader therefore could not see a name until `first_seen + 900 s`; from then
on it read IB's real-time bars. That is a FLOOR on the first entry, not a
shift of every bar, and `not_before` (the point-in-time floor every PIT study
uses) is exactly that floor -- so the delayed book is the published book with
the floor moved by 15 minutes. Nothing in either engine changes.

FOUR FLOORS, NOT ONE. 0 is the published v2 baseline and must reproduce it to
the trade (a floor that silently did nothing is the recurring control failure
in PROGRAM_INDEX §4); 15 is the measured delay; 5 and 30 bracket it so the
reading is a curve.

NOTHING PASSES HERE. The output is a cost per trade and a classification of
the live-vs-simulated shape gap into one of three words fixed in the
registration before any number existed: "the shape", "part of it", "not it".
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from common import gate_study as G
from common import running_up as RU
from common.entry_shares import MEASURED_FRICTION, QTY, published_mcl_trades
from common.first_entry_skip import FRICTIONS, halves, net, per_trade, trade_row
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
REGISTERED = "docs/research/REGISTERED_feed_delay_cost.md"
OFFSETS = (0, 5, 15, 30)           # minutes after first_seen; 0 = published
DELAY = 15                         # the measured one: delayed_streaming_900
STRATEGIES = ("mcl", "mc5")
BAR_MINUTES = {"mcl": 1, "mc5": 5}
SHORT_HOLD_MIN = 2.0               # the live table's "0-2 min" bucket
CSV_COLS = G.CSV_COLS + ["ret_5m", "hold_min"]


def book_name(strategy: str, offset: int) -> str:
    return f"{strategy.upper()} +{offset}"


BOOKS: tuple = tuple((book_name(s, o), s, o) for s in STRATEGIES for o in OFFSETS)


# --- the floor ---------------------------------------------------------------

def delayed_floor(first_seen_et, offset_min: int, day: _date):
    """`first_seen` as an ET time-of-day plus the delay, still a time-of-day.

    `not_before` takes a time; adding minutes to a time needs a date to carry
    the arithmetic. A floor that lands after 09:30 admits nothing, which is
    the right answer for a name the delayed feed would have shown after the
    session ended -- it is NOT clamped back into the session.
    """
    return (datetime.combine(day, first_seen_et) + timedelta(minutes=offset_min)).time()


# --- the tape ----------------------------------------------------------------

def run_universe(frame, day: str, universe: list[dict], engines: dict) -> dict:
    """Every book on every symbol-day of one session. Pure enough to test with
    a fake engine: `engines[name] = (module, extra_kwargs)`."""
    import pandas as pd
    from common.pit_h0 import first_seen_time

    d = _date.fromisoformat(day)
    res = {"books": {n: [] for n, _, _ in BOOKS}, "symdays": 0,
           "errors": 0, "error_days": []}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        seen = first_seen_time(rec)
        # ALL OR NONE per symbol-day, as every point-in-time study here.
        try:
            got = {}
            for name, strat, off in BOOKS:
                mod, extra = engines[strat]
                floor = delayed_floor(seen, off, d)
                got[name] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=floor, **extra)
        except Exception as e:                               # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{rec['symbol']} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for name, trades in got.items():
            for k, t in enumerate(trades, 1):
                row = trade_row(t, rec["symbol"], day, k)
                row["ret_5m"] = RU.ret_at(df, pd.Timestamp(f"{day} {row['entry_et']}", tz=ET))
                row["hold_min"] = hold_minutes(row)
                res["books"][name].append(row)
    return res


def run_day(args: tuple) -> tuple:
    """One session, every book. Module-level and picklable."""
    from common.dbn_io import read_dbn
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
    engines = {name: engine(name) for name in STRATEGIES}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                               # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    return day, run_universe(frame, day, universe, engines), ""


# --- the shape ---------------------------------------------------------------

def hold_minutes(row: dict) -> float:
    """Minutes between the entry and exit stamps of one trade row (HH:MM)."""
    def m(s: str) -> int:
        h, mm = s.split(":")
        return int(h) * 60 + int(mm)
    return float(max(0, m(row["exit_et"]) - m(row["entry_et"])))


def shape(rows, f: float = MEASURED_FRICTION) -> dict:
    """The five numbers the live book is compared on, at friction `f`."""
    if not rows:
        return {"n": 0, "per_trade": float("nan"), "win": float("nan"), "R": float("nan"),
                "hold_med": float("nan"), "short": float("nan"), "one_bar": float("nan"),
                "ret5": float("nan")}
    nets = [r["net"] - f for r in rows]
    wins = [x for x in nets if x > 0]
    losses = [-x for x in nets if x <= 0]
    holds = [float(r["hold_min"]) for r in rows]
    ret5 = [r["ret_5m"] for r in rows
            if r.get("ret_5m") is not None and r["ret_5m"] == r["ret_5m"]]
    return {
        "n": len(rows),
        "per_trade": sum(nets) / len(nets),
        "win": len(wins) / len(nets),
        "R": (np.mean(wins) / np.mean(losses)) if wins and losses and np.mean(losses) > 0
             else float("nan"),
        "hold_med": float(np.median(holds)),
        "short": sum(1 for h in holds if h <= SHORT_HOLD_MIN) / len(holds),
        "one_bar": sum(1 for r in rows if int(r.get("bars_held", 99)) <= 1) / len(rows),
        "ret5": float(np.median(ret5)) if ret5 else float("nan"),
    }


def marginal(base, cell, f: float = MEASURED_FRICTION) -> float:
    """What each trade the delay REMOVED (or added) was worth."""
    dn = len(cell) - len(base)
    if dn == 0:
        return float("nan")
    return (net(cell, f) - net(base, f)) / dn


def per_symday(rows, symdays: int, f: float = MEASURED_FRICTION) -> float:
    return net(rows, f) / symdays if symdays else float("nan")


def classify(sim0: dict, sim15: dict, live: dict) -> tuple[str, dict]:
    """§2 reading 4, the three words fixed in the registration.

    The delay 'is the shape' if the +15 book closes at least half of BOTH the
    win-rate distance and the R distance from the 0 book to the live book;
    'part of it' if one; 'not it' if neither. Distances are measured from the
    0 book, so a +15 book that overshoots the live figure still counts as
    closing the gap (it moved past it, not away from it)."""
    out = {}
    closed = 0
    for k in ("win", "R"):
        d0 = live[k] - sim0[k]
        d15 = live[k] - sim15[k]
        if any(math.isnan(x) for x in (d0, d15)):
            out[k] = {"d0": d0, "d15": d15, "closed": float("nan"), "half": False}
            continue
        if d0 == 0:
            frac = 1.0
        else:
            frac = 1.0 - d15 / d0          # 1.0 = landed on live; >1 overshoot; <0 moved away
        half = frac >= 0.5
        closed += int(half)
        out[k] = {"d0": d0, "d15": d15, "closed": frac, "half": half}
    word = {2: "THE SHAPE", 1: "PART OF IT", 0: "NOT IT"}[closed]
    return word, out


def monotone(values: list[float]) -> str:
    v = [x for x in values if x == x]
    if len(v) < 3:
        return "n/a"
    if all(b >= a for a, b in zip(v, v[1:])):
        return "rising"
    if all(b <= a for a, b in zip(v, v[1:])):
        return "falling"
    return "mixed"


# --- the live book -----------------------------------------------------------

def live_round_trips(fills_dir: Path, sessions: list[str]):
    """Live round trips whose EXIT falls on one of the run's sessions, per
    strategy, via churn_count's pairing (file order, not a re-sort)."""
    import pandas as pd
    from common.churn_count import load, round_trips

    frames = []
    for p in sorted(Path(fills_dir).glob("*_fills_*.csv")):
        try:
            f, _derived = load(p)
        except Exception:                                    # noqa: BLE001
            continue
        if not f.empty:
            frames.append(f)
    if not frames:
        return {}
    rt = round_trips(pd.concat(frames, ignore_index=True))
    if rt.empty:
        return {}
    rt["date"] = pd.to_datetime(rt["close_ts"]).dt.strftime("%Y-%m-%d")
    rt = rt[rt["date"].isin(set(sessions))]
    out = {}
    for st, g in rt.groupby("strategy"):
        pnl = g["pnl"].astype(float).tolist()
        wins = [x for x in pnl if x > 0]
        losses = [-x for x in pnl if x <= 0]
        holds = g["hold"].astype(float).tolist()
        out[str(st).lower()] = {
            "n": len(pnl), "per_trade": float(np.mean(pnl)),
            "win": len(wins) / len(pnl),
            "R": (np.mean(wins) / np.mean(losses)) if wins and losses and np.mean(losses) > 0
                 else float("nan"),
            "hold_med": float(np.median(holds)),
            "short": sum(1 for h in holds if h <= SHORT_HOLD_MIN) / len(holds),
            "sessions": sorted(set(g["date"])),
        }
    return out


# --- the report --------------------------------------------------------------

def money(x: float) -> str:
    if x != x:
        return "n/a"
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def pct(x: float, d: int = 1) -> str:
    return "n/a" if x != x else f"{100 * x:.{d}f}%"


def num(x: float, d: int = 2) -> str:
    return "n/a" if x != x else f"{x:.{d}f}"


def strategy_block(strat: str, books: dict, symdays: int, cut: str) -> list[str]:
    base = books[book_name(strat, 0)]
    L = [f"{strat.upper()}  --  bar {BAR_MINUTES[strat]} min  --  {len(base):,} trades at +0",
         "",
         "  floor      n     $1.00     $4.26     $8.92   /symday   1st half  2nd half"
         "    win      R   hold  <=2min  1-bar   ret5m",
         ]
    shapes = {}
    for off in OFFSETS:
        rows = books[book_name(strat, off)]
        s = shape(rows)
        shapes[off] = s
        h1, h2 = halves(rows, cut)
        L.append(f"  +{off:<3d} {len(rows):>7,}  "
                 + "  ".join(f"{money(per_trade(rows, fv)):>8}" for _, fv in FRICTIONS)
                 + f"  {money(per_symday(rows, symdays)):>8}"
                 + f"  {money(per_trade(h1, MEASURED_FRICTION)):>9} {money(per_trade(h2, MEASURED_FRICTION)):>9}"
                 + f"  {pct(s['win']):>6} {num(s['R']):>6} {num(s['hold_med'], 0):>5}"
                 + f" {pct(s['short'], 0):>6} {pct(s['one_bar'], 0):>6} {pct(s['ret5'], 2):>7}")
    L += ["",
          "  against +0, at $4.26:",
          "  floor   trades    per trade    /symday   marginal trade   win    R"]
    for off in OFFSETS[1:]:
        rows = books[book_name(strat, off)]
        s = shapes[off]
        s0 = shapes[0]
        L.append(f"  +{off:<3d} {len(rows) - len(base):>+8,}  "
                 f"{money(s['per_trade'] - s0['per_trade']):>11}  "
                 f"{money(per_symday(rows, symdays) - per_symday(base, symdays)):>9}  "
                 f"{money(marginal(base, rows)):>15}  "
                 f"{100 * (s['win'] - s0['win']):>+5.1f}pt {s['R'] - s0['R']:>+5.2f}")
    L += ["",
          f"  monotone across +0/+5/+15/+30:  per trade {monotone([shapes[o]['per_trade'] for o in OFFSETS])}"
          f"  ·  win {monotone([shapes[o]['win'] for o in OFFSETS])}"
          f"  ·  ret5m {monotone([shapes[o]['ret5'] for o in OFFSETS])}"
          f"  ·  trades {monotone([float(len(books[book_name(strat, o)])) for o in OFFSETS])}",
          ""]
    return L


def live_block(books: dict, live: dict, sessions: list[str]) -> list[str]:
    L = ["THE LIVE BOOK, SAME SESSIONS  (§2 reading 4)", ""]
    if not live:
        return L + ["  no live round trips on these sessions -- Arm A, or fills not found", ""]
    lsess = sorted({d for v in live.values() for d in v.get("sessions", [])})
    L += [f"  live sessions with round trips inside this run: {len(lsess)} of {len(sessions)}"
          + (f"  ({lsess[0]} -> {lsess[-1]})" if lsess else ""), "",
          "  strategy  book        n   per trade    win      R   hold  <=2min"]
    for strat in STRATEGIES:
        lv = live.get(strat)
        if not lv:
            continue
        L.append(f"  {strat.upper():<8}  live   {lv['n']:>6,}  {money(lv['per_trade']):>9}  "
                 f"{pct(lv['win']):>6} {num(lv['R']):>6} {num(lv['hold_med'], 0):>5} {pct(lv['short'], 0):>6}")
        for off in (0, DELAY):
            s = shape(books[book_name(strat, off)])
            L.append(f"  {'':<8}  sim +{off:<2d} {s['n']:>6,}  {money(s['per_trade']):>9}  "
                     f"{pct(s['win']):>6} {num(s['R']):>6} {num(s['hold_med'], 0):>5} {pct(s['short'], 0):>6}")
        L.append("")
    lv = live.get("mcl")
    if lv:
        word, det = classify(shape(books[book_name("mcl", 0)]),
                             shape(books[book_name("mcl", DELAY)]), lv)
        L += ["  MCL, the classification (the three words are the registration's):", ""]
        for k, lab in (("win", "win rate"), ("R", "R")):
            d = det[k]
            L.append(f"    {lab:<9} gap at +0 {d['d0']:+.3f}   gap at +15 {d['d15']:+.3f}   "
                     f"closed {num(d['closed'])} of the way  {'(>= half)' if d['half'] else '(< half)'}")
        L += ["", f"    THE DELAY IS {word}", ""]
    if "mc5" in live:
        L += ["  MC5 live rows 2026-09-10 -> prod-20260918 are apex-ON rows (a different",
              "  strategy from the published one): printed, NOT classified.", ""]
    return L


def population_block(books: dict, pairs: str) -> tuple[list[str], bool]:
    n = len(books[book_name("mcl", 0)])
    pub = published_mcl_trades(pairs)
    if pub is None:
        return [f"  published count     none for this universe file -- Arm B, the live sessions"], True
    ok = n == pub
    L = [f"  published count     {pub:,}   MCL +0 {n:,}   " + ("matches" if ok else "*** DOES NOT MATCH ***")]
    if not ok:
        L += ["", "  THE +0 BOOK IS NOT THE PUBLISHED BOOK. The registration stops the run",
              "  here: a floor that does not reproduce the baseline at offset 0 cannot",
              "  be trusted at offset 15. Nothing below is read."]
    return L, ok


def render(books: dict, symdays: int, errors: int, days: list[str], elapsed: float,
           jobs: int, error_days: list[str], *, universe: str, dataset: str,
           live: dict) -> tuple[str, bool]:
    cut = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
    pop, ok = population_block(books, universe)
    L = ["H-D1 -- WHAT THE LIVE FEED'S 900 SECONDS COST, AND WHETHER THEY ARE THE SHAPE",
         "",
         f"  registered   {REGISTERED}",
         f"  universe     {universe}   tape {dataset}",
         f"  sessions     {len(days)}   {days[0] if days else '-'} -> {days[-1] if days else '-'}   cut {cut}",
         f"  symbol-days  {symdays:,}   errors {errors}   {elapsed:.0f}s on {jobs} worker(s)",
         f"  floors       first_seen + {' / '.join(str(o) for o in OFFSETS)} min;"
         f" +{DELAY} is delayed_streaming_900",
         *pop, ""]
    if not ok:
        return "\n".join(L), False
    L += ["THE FOUR FLOORS  (§2 readings 1-3, 5)", ""]
    for strat in STRATEGIES:
        L += strategy_block(strat, books, symdays, cut)
    L += live_block(books, live, days)
    L += ["WHAT THIS IS NOT", "",
          "  NOT A GATE. Nothing here passes or clears; the output is a cost and one",
          "  of three words fixed before the run. NOT A LIVE CHANGE: not_before is",
          "  used as it exists in both engines. The cookie path exists on main from",
          "  2026-09-18 and is promoted separately; this prices the sessions before it.", ""]
    if error_days:
        L += ["symbol-days dropped (all books):"] + [f"  {e}" for e in error_days[:20]]
        if len(error_days) > 20:
            L.append(f"  ... {len(error_days) - 20} more")
    return "\n".join(L), True


def write_csv(path: str, books: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for name, rows in books.items():
            for r in rows:
                w.writerow(dict(r, book=name))


# --- main --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.ITCH")
    p.add_argument("--fills", default="var/fills",
                   help="live fills directory for Arm B; '' to skip")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/feed_delay.txt")
    p.add_argument("--csv", default="var/reports/feed_delay_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "feed_delay")

    books = {n: [] for n, _, _ in BOOKS}
    symdays, errors, error_days = 0, 0, []
    days = sorted(got)                     # DAY ORDER: float sums must not move with --jobs
    for day in days:
        r = got[day]
        for name in books:
            books[name] += r["books"][name]
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]

    live = live_round_trips(Path(a.fills), days) if a.fills and Path(a.fills).is_dir() else {}
    text, ok = render(books, symdays, errors, days, elapsed, jobs, error_days,
                      universe=a.pairs, dataset=a.dataset, live=live)
    cut = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
    emit(text, a.out,
         header=f"common.feed_delay pairs={a.pairs} dataset={a.dataset} sessions={len(days)} "
                f"symbol_days={symdays} cut={cut} qty={QTY} registered={REGISTERED}"
                + ("" if ok else "  STOPPED: +0 book is not the published book"))
    write_csv(a.csv, books)
    G.write_meta(a.csv, days, symdays, cut,
                 {"pairs": a.pairs, "dataset": a.dataset, "registered": REGISTERED,
                  "offsets_min": list(OFFSETS), "stopped": not ok})
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
