#!/usr/bin/env python3
r"""H-C2 -- a profit floor beside the 5% trail, MCL and MC5, point-in-time.

    python -m common.profit_floor_study --jobs 8

Registered in docs/research/REGISTERED_profit_floor.md before this file
existed. Four books from one `run_day` per session: MCL and MC5 as published,
and each with `profit_floor=(15, 10)` -- once a bar after the entry bar
reaches entry + 15 ticks, the stop is max(5% trail, entry + 10 ticks) from the
next bar on. The engines carry the rule (strategy/mcl/mcl.py,
strategy/mc5/mc5.py, pinned by tests/strategy/test_profit_floor.py); this
module only runs them side by side and reads §3.

Same machinery as first_entry_skip: the same point-in-time frames and warm-up,
the same `first_seen` floor, 100 shares, the published configurations,
`net` less a round-trip friction, halves cut once at the median session run,
per symbol-day over the symbol-days the run covered (one number for every
book).

THE BASELINE MUST BE THE PUBLISHED ONE. §2: each ungated book must reproduce
the published `pit_strategy` trade count and per-trade figure for the
universe it ran on, or no verdict is printed. The published figures are
keyed by pairs file below; a universe with no entry needs `--expect`.

WHAT THIS IS NOT: an exit-change study has no abstention control (the rule
does not remove entries), so gate_study's reading 5 is replaced by §3 item 5,
the floor must actually fire.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

from common.breadth import BOOT_MIN_P, RESAMPLES, SEED, cluster_bootstrap, pct, share_above_zero
from common.entry_shares import MEASURED_FRICTION, QTY
from common.first_entry_skip import (DROP, FRICTIONS, TOP, delta_by_symbol,
                                     deltas_by_symbol_day, drop_top, halves,
                                     key, money, net, new_entries, per_trade, top_absent,
                                     trade_row)
from common.report_io import emit

ET = ZoneInfo("America/New_York")
REGISTERED = "docs/research/REGISTERED_profit_floor.md"
# The registered cells of the family. A pair not listed here is refused: each
# one is its own registration, and the list is the multiplicity count.
CELLS = {(15, 10): {"registered": "docs/research/REGISTERED_profit_floor.md",
                    "out": "var/reports/profit_floor.txt",
                    "csv": "var/reports/profit_floor_trades.csv"},
         (15, 5): {"registered": "docs/research/REGISTERED_profit_floor_v2.md",
                   "out": "var/reports/profit_floor_15_5.txt",
                   "csv": "var/reports/profit_floor_15_5_trades.csv"}}
# H-C3 §3 item 6: with two cells the bootstrap bar is halved across the family.
FAMILY_BOOT_MIN_P = {1: None, 2: 0.975}
PAIRS = "var/state/screen_pairs_pit_itch_p50.json"
DATASET = "XNAS.ITCH"
PF = (15, 10)                    # §1: arm at +15 ticks, floor at +10 ticks
HIGH_FRICTION = 8.92             # §3 item 1 is read at $4.26 AND here
MIN_FLOOR_SHARE = 5.0            # §3 item 5: floor exits >= 5% of the floored book
RUNNER_PCT = 10.0                # §3 printed: "runners cut" reached >= +10%
TICK = 0.01

BOOKS = (("MCL", "mcl", None), ("MCL-floor", "mcl", PF),
         ("MC5", "mc5", None), ("MC5-floor", "mc5", PF))
PAIRED = (("MCL", "MCL-floor"), ("MC5", "MC5-floor"))

# (trades, per trade at $4.26) as published by pit_strategy for each universe.
# screen_itch_RESULT_20260917: var/reports/pit_strategy_{mcl,mc5}_itch.txt.
PUBLISHED = {
    "var/state/screen_pairs_pit_itch_p50.json": {"mcl": (3960, -8.81), "mc5": (6630, -8.49)},
}


# --- one session -----------------------------------------------------------------

def excursion(bars, entry_time, exit_time, entry_px: float) -> tuple[float, float]:
    """(max high strictly after the entry bar up to and including the exit bar,
        max high strictly after the entry bar and strictly BEFORE the exit bar).

    The first is "did it reach +10%" for the runners line. The second is what
    the floor could have armed on: a bar's high arms only after that bar's
    exits were decided, so the exit bar's own high never armed anything that
    mattered. NaN-free: an empty window returns the entry price."""
    import pandas as pd
    et, xt = pd.Timestamp(entry_time), pd.Timestamp(exit_time)
    idx = bars.index
    upto = bars.loc[(idx > et) & (idx <= xt), "high"]
    before = bars.loc[(idx > et) & (idx < xt), "high"]
    return (float(upto.max()) if len(upto) else entry_px,
            float(before.max()) if len(before) else entry_px)


def configure(pf: tuple[int, int]) -> None:
    """Select a registered cell. Sets PF and the BOOKS that carry it, module-wide,
    so pickled workers (which re-import and are handed `pf` in their task) and
    the report read the same pair."""
    global PF, BOOKS, REGISTERED
    if pf not in CELLS:
        raise SystemExit(f"REFUSED: {pf} is not a registered cell {sorted(CELLS)}")
    PF = pf
    REGISTERED = CELLS[pf]["registered"]
    BOOKS = (("MCL", "mcl", None), ("MCL-floor", "mcl", PF),
             ("MC5", "mc5", None), ("MC5-floor", "mc5", PF))


def boot_bar() -> float:
    """The cluster-bootstrap bar for the current cell: 0.95 for the first cell of
    the family (H-C2 as registered), 0.975 for any later one (H-C3 §3 item 6)."""
    return BOOT_MIN_P if PF == (15, 10) else FAMILY_BOOT_MIN_P[len(CELLS)]


def row_for(t, symbol: str, day: str, ordinal: int, bars) -> dict:
    from strategy.mcl.mcl import reaches_arm
    r = trade_row(t, symbol, day, ordinal)
    hi_upto, hi_before = excursion(bars, t.entry_time, t.exit_time, float(t.entry_price))
    r["mfe_pct"] = (hi_upto / float(t.entry_price) - 1.0) * 100.0
    r["armed"] = bool(reaches_arm(float(t.entry_price), hi_before, PF))
    return r


def run_day(args: tuple) -> tuple:
    """One session, all four books. Picklable."""
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe, pf = args
    configure(pf)
    engines = {name: engine(name) for name in ("mcl", "mc5")}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)

    res = {"books": {name: [] for name, _, _ in BOOKS},
           "symdays": 0, "errors": 0, "error_days": []}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        try:
            bars = {"mcl": df, "mc5": engines["mc5"][0].to_5m(df)}
            got = {}
            for name, eng, pf in BOOKS:
                mod, extra = engines[eng]
                trades = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                              not_before=floor, profit_floor=pf, **extra)
                got[name] = [row_for(t, rec["symbol"], day, k, bars[eng])
                             for k, t in enumerate(trades, 1)]
        except Exception as e:                              # noqa: BLE001
            # ALL OR NONE, as first_entry_skip: the books must cover the same days.
            res["errors"] += 1
            res["error_days"].append(f"{rec['symbol']} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for name, rows in got.items():
            res["books"][name] += rows
    return day, res, ""


# --- §3 -------------------------------------------------------------------------

def deltas(base, flo, symdays: int, f: float) -> tuple[float, float]:
    return (per_trade(flo, f) - per_trade(base, f),
            (net(flo, f) - net(base, f)) / symdays if symdays else 0.0)


def drop_top_symbols_delta(d: dict[tuple, float], n: int = DROP) -> float:
    """§3 item 3 as registered: the delta after removing the n SYMBOLS that
    helped the rule most -- every symbol-day of each, not the n best
    symbol-days (which is first_entry_skip's reading and a weaker one: a name
    that helped on two days survives it)."""
    by_sym: dict[str, float] = {}
    for (sym, _day), v in d.items():
        by_sym[sym] = by_sym.get(sym, 0.0) + v
    return sum(sorted(by_sym.values(), reverse=True)[n:])


def floor_exits(rows) -> list[dict]:
    return [r for r in rows if r["reason"] == "profit_floor"]


def baseline_check(name: str, rows, expect) -> tuple[bool, str]:
    """§2: count exact, per trade at $4.26 within half a cent."""
    if expect is None:
        return False, "no published figure for this universe (pass --expect)"
    n, pt = expect
    got_pt = per_trade(rows, MEASURED_FRICTION)
    ok = len(rows) == n and abs(got_pt - pt) < 0.005
    return ok, (f"{len(rows):,} trades, {money(got_pt)}/trade against published "
                f"{n:,}, {money(pt)} -- " + ("matches" if ok else "*** DOES NOT MATCH ***"))


def verdict(base, flo, cut: str, symdays: int, baseline_ok: bool) -> tuple[str, str, dict]:
    """REGISTERED §3. Nothing here may change after a run."""
    f = MEASURED_FRICTION
    n: dict = {}
    n["d426"] = deltas(base, flo, symdays, f)
    n["d892"] = deltas(base, flo, symdays, HIGH_FRICTION)
    ba, bb = halves(base, cut)
    sa, sb = halves(flo, cut)
    n["early"] = deltas(ba, sa, symdays, f)
    n["late"] = deltas(bb, sb, symdays, f)
    n["drop_level"] = (drop_top(flo, f), drop_top(base, f))
    d = deltas_by_symbol_day(base, flo, f)
    n["drop_delta"] = drop_top_symbols_delta(d)
    boot = cluster_bootstrap(delta_by_symbol(d))
    n["boot_p"] = share_above_zero(boot["totals"]) if boot["totals"] else 0.0
    n["boot_lo"] = pct(boot["totals"], 0.025) if boot["totals"] else 0.0
    n["boot_hi"] = pct(boot["totals"], 0.975) if boot["totals"] else 0.0
    n["n_syms"] = boot["n_syms"]
    n["floor_share"] = 100.0 * len(floor_exits(flo)) / len(flo) if flo else 0.0

    if not baseline_ok:
        return "NO VERDICT", "the baseline does not reproduce its published figure (§2)", n
    if not (ba and bb and sa and sb):
        return "NOTHING", "a half is empty in one of the books", n
    for lab, (pt, sd) in (("$4.26", n["d426"]), ("$8.92", n["d892"])):
        if (pt > 0) != (sd > 0):
            return "REFUSED", (f"the two denominators disagree at {lab}: per trade {pt:+.2f}, "
                               f"per symbol-day {sd:+.2f}"), n
    failed = []
    if not all(x > 0 for x in n["d426"] + n["d892"]):
        failed.append("1 (both denominators improve at $4.26 and $8.92)")
    if not all(x > 0 for x in n["early"] + n["late"]):
        failed.append("2 (both halves, both denominators)")
    if not n["drop_delta"] > 0:
        failed.append(f"3 (drop-top-{DROP} symbols on the delta)")
    bar = boot_bar()
    if not n["boot_p"] >= bar:
        failed.append(f"4 (cluster bootstrap on the delta, P={n['boot_p']:.3f} < {bar})")
    if not n["floor_share"] >= MIN_FLOOR_SHARE:
        failed.append(f"5 (floor exits {n['floor_share']:.1f}% < {MIN_FLOOR_SHARE:.0f}%)")
    if failed:
        return "NOTHING", "fails " + "; ".join(failed), n
    return "PASSES", "all five readings -- a holdout candidate, not a rule to ship", n


# --- report ---------------------------------------------------------------------

def shape(rows, f: float = MEASURED_FRICTION) -> dict:
    vals = [r["net"] - f for r in rows]
    wins = [v for v in vals if v > 0]
    loss = [v for v in vals if v <= 0]
    return {"n": len(vals),
            "win": 100.0 * len(wins) / len(vals) if vals else 0.0,
            "scratch": 100.0 * sum(1 for v in vals if abs(v) <= MEASURED_FRICTION) / len(vals)
            if vals else 0.0,
            "avg_win": sum(wins) / len(wins) if wins else 0.0,
            "avg_loss": sum(loss) / len(loss) if loss else 0.0,
            "bars": sum(r["bars_held"] for r in rows) / len(rows) if rows else 0.0}


def book_block(name: str, rows, cut: str, symdays: int) -> list[str]:
    L = [f"  {name}"]
    for lab, f in FRICTIONS:
        L.append(f"    at {lab:<6} trades {len(rows):>6,}   net {money(net(rows, f)):>12}"
                 f"   per trade {money(per_trade(rows, f)):>8}"
                 f"   per symbol-day {money(net(rows, f) / symdays if symdays else 0):>7}")
    a, b = halves(rows, cut)
    f = MEASURED_FRICTION
    s = shape(rows)
    L += [f"    halves @ $4.26    early {len(a):>5,} {money(per_trade(a, f)):>8}/t "
          f"   late {len(b):>5,} {money(per_trade(b, f)):>8}/t",
          f"    drop top {DROP} trades @ $4.26  {money(drop_top(rows, f)):>11}",
          f"    win {s['win']:.1f}%   scratch {s['scratch']:.1f}%   avg winner "
          f"{money(s['avg_win'])}   avg loser {money(s['avg_loss'])}   avg bars {s['bars']:.1f}",
          f"    exits: " + "   ".join(f"{k} {v:,}" for k, v in sorted(
              _count(r["reason"] for r in rows).items())), ""]
    return L


def _count(it) -> dict:
    out: dict = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


def mechanism_block(bname: str, sname: str, base, flo) -> list[str]:
    """§3 'printed every time' -- Ben's question, as a measurement."""
    fx = floor_exits(flo)
    armed = [r for r in flo if r["armed"]]
    L = [f"THE MECHANISM: {sname}", "",
         f"  trades that armed (a bar after entry reached +{PF[0]} ticks before the exit bar)"
         f"   {len(armed):,} of {len(flo):,}  ({100 * len(armed) / len(flo) if flo else 0:.1f}%)",
         f"  floor exits   {len(fx):,}  ({100 * len(fx) / len(flo) if flo else 0:.1f}% of trades)", ""]
    if fx:
        L.append("  share of floor exits that net > $0 after friction")
        for lab, f in FRICTIONS:
            pos = sum(1 for r in fx if r["net"] - f > 0)
            L.append(f"    at {lab:<6} {pos:>6,} of {len(fx):,}   {100 * pos / len(fx):5.1f}%"
                     f"   their net {money(net(fx, f))}")
        at_floor = below = below_entry = 0
        for r in fx:
            lvl = round(r["entry_px"] + PF[1] * TICK - TICK, 6)       # floor less the slippage tick
            if r["exit_px"] >= lvl - 1e-6:
                at_floor += 1
            else:
                below += 1
            if r["exit_px"] < r["entry_px"] - 1e-9:
                below_entry += 1
        L += ["",
              f"  floor-exit fills   at the floor (less one tick) {at_floor:,}"
              f"   gapped below it {below:,}   of which below the entry price {below_entry:,}",
              "  (a gap below the floor fills at the bar's open: the only way the floor exits"
              " below entry)", ""]
    f = MEASURED_FRICTION
    fmap = {key(r): r for r in flo}
    runners = [r for r in base if r["mfe_pct"] >= RUNNER_PCT]
    cut = [(r, fmap[key(r)]) for r in runners
           if key(r) in fmap and fmap[key(r)]["reason"] == "profit_floor"]
    forgone = sum((b["net"] - f) - (s["net"] - f) for b, s in cut)
    L += [f"  runners cut: {len(cut):,} of {bname}'s {len(runners):,} trades that reached "
          f"+{RUNNER_PCT:.0f}% exited on the floor in {sname}; P/L forgone {money(forgone)}",
          f"  cascade: {new_entries(base, flo):,} {sname} entries the baseline does not contain", ""]
    return L


def verdict_block(bname: str, sname: str, base, flo, cut: str, symdays: int,
                  bcheck: tuple[bool, str]) -> list[str]:
    f = MEASURED_FRICTION
    tag, why, n = verdict(base, flo, cut, symdays, bcheck[0])
    gone, gone_rows = top_absent(base, flo, f)
    L = [f"THE VERDICT: {sname} against {bname} (registered §3)", "",
         f"  baseline: {bcheck[1]}",
         f"  1. at $4.26 per trade {n['d426'][0]:+.2f}  per symbol-day {n['d426'][1]:+.2f}"
         f"     at $8.92 per trade {n['d892'][0]:+.2f}  per symbol-day {n['d892'][1]:+.2f}",
         f"  2. early half  per trade {n['early'][0]:+.2f}  per symbol-day {n['early'][1]:+.2f}"
         f"     late half  per trade {n['late'][0]:+.2f}  per symbol-day {n['late'][1]:+.2f}",
         f"  3. drop-top-{DROP}-symbols delta {money(n['drop_delta'])}     (level, top-{DROP} trades: {sname} "
         f"{money(n['drop_level'][0])}, {bname} {money(n['drop_level'][1])})",
         f"  4. cluster bootstrap on the delta  P(total > 0) = {n['boot_p']:.3f} (needs >= {boot_bar()})  "
         f"[{money(n['boot_lo'])}, {money(n['boot_hi'])}]  over {n['n_syms']:,} symbols  "
         f"(RESAMPLES {RESAMPLES}, SEED {SEED})",
         f"  5. floor exits {n['floor_share']:.1f}% of {sname}'s trades (needs >= "
         f"{MIN_FLOOR_SHARE:.0f}%)",
         "", f"  {tag}: {why}", "",
         f"  {gone} of {bname}'s top-{TOP} trades at $4.26 are absent or changed in {sname}:"]
    for r in gone_rows:
        L.append(f"    {r['symbol']:<6} {r['date']}  {r['entry_et']} ET  {money(r['net'] - f):>10}")
    return L + [""]


def cross_cell_block(books: dict, symdays: int, other_csv: str | None) -> list[str]:
    """H-C3 §3: this cell against (15, 10), per strategy, REPORTED NOT SCORED."""
    if PF == (15, 10) or not other_csv or not Path(other_csv).exists():
        return []
    import csv
    other: dict[str, list[dict]] = {}
    with open(other_csv, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            other.setdefault(r["book"], []).append({"net": float(r["net"])})
    f = MEASURED_FRICTION
    L = [f"THIS CELL {PF} AGAINST (15, 10) -- reported, not scored (H-C3 §3)", ""]
    for name in ("MCL-floor", "MC5-floor"):
        mine, theirs = books[name], other.get(name, [])
        if not theirs:
            L.append(f"  {name}: (15, 10) book not found in {other_csv}")
            continue
        L.append(f"  {name}  per trade {per_trade(mine, f) - per_trade(theirs, f):+.2f}"
                 f"   per symbol-day {(net(mine, f) - net(theirs, f)) / symdays if symdays else 0:+.2f}"
                 f"   ({len(mine):,} trades against {len(theirs):,})")
    return L + [""]


def provenance(pairs: str) -> list[str]:
    p = Path(pairs)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "missing"
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, encoding="utf-8", timeout=10).stdout.strip()
    except Exception:                                       # noqa: BLE001
        head = "unknown"
    return [f"  pairs {pairs}  sha256 {sha}  (var/ is not in git; the hash is the identity)",
            f"  code at commit {head or 'unknown'}"]


def render(books: dict, symdays: int, errors: int, days: list[str], elapsed: float, jobs: int,
           a, error_days: list | None = None, expect: dict | None = None) -> list[str]:
    cut = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
    expect = expect or {}
    L = ["H-C2: A PROFIT FLOOR BESIDE THE 5% TRAIL", "",
         f"  registered  {REGISTERED}",
         f"  rule        arm at entry + {PF[0]} ticks, floor at entry + {PF[1]} ticks,"
         " active from the bar after arming",
         f"  dataset     {a.dataset}", *provenance(a.pairs),
         f"  {len(days):,} sessions   {symdays:,} symbol-days   halves cut at {cut}",
         f"  {QTY} shares   commission in, friction per round trip   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped from EVERY book:"]
        L += [f"    {e}" for e in (error_days or [])[:20]] + [""]
    L += ["THE BOOKS", ""]
    for name, _eng, _pf in BOOKS:
        L += book_block(name, books[name], cut, symdays)
    for bname, sname in PAIRED:
        eng = bname.lower()
        bcheck = baseline_check(bname, books[bname], expect.get(eng))
        L += verdict_block(bname, sname, books[bname], books[sname], cut, symdays, bcheck)
        L += mechanism_block(bname, sname, books[bname], books[sname])
    L += cross_cell_block(books, symdays, CELLS[(15, 10)]["csv"] if PF != (15, 10) else None)
    L += ["WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. holdout.json has not been spent; the published PIT",
          "  baselines this reproduces are scored over the same sessions.",
          "  NOT LIVE FILLS. One tick on a floor exit; friction is carried by the",
          "  $4.26 / $8.92 levels, not by the fill model (§6).",
          "  NOT A CAP MODEL. Each symbol-day runs alone.",
          f"  NOT A SEARCH. One registered tick pair, {PF}; the family has "
          f"{len(CELLS)} cell(s).", ""]
    return L


# --- cli --------------------------------------------------------------------------

def parse_expect(text: str | None) -> dict:
    """"mcl=3960:-8.81,mc5=6630:-8.49" -> {"mcl": (3960, -8.81), ...}"""
    out: dict = {}
    if not text:
        return out
    for part in text.split(","):
        name, val = part.split("=")
        n, pt = val.split(":")
        out[name.strip().lower()] = (int(n), float(pt))
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--expect", default=None,
                   help='published baselines for a universe not in PUBLISHED, '
                        'e.g. "mcl=3960:-8.81,mc5=6630:-8.49"')
    p.add_argument("--floor", default="15,10",
                   help="a registered (arm,floor) cell: " + " or ".join(
                       f"{a},{b}" for a, b in sorted(CELLS)))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default=None, help="default: the cell's own report path")
    p.add_argument("--csv", default=None, help="default: the cell's own trades path")
    return p


CSV_COLS = ["book", "symbol", "date", "ordinal", "entry_et", "entry_px", "exit_et",
            "exit_px", "reason", "bars_held", "net", "mfe_pct", "armed"]


def write_csv(path: str, books: dict) -> None:
    import csv
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for name, _eng, _pf in BOOKS:
            for r in books[name]:
                w.writerow(dict(r, book=name))


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    try:
        pf = tuple(int(x) for x in a.floor.split(","))
    except ValueError:
        raise SystemExit(f"REFUSED: --floor must be arm,floor; got {a.floor!r}") from None
    configure(pf)
    a.out = a.out or CELLS[PF]["out"]
    a.csv = a.csv or CELLS[PF]["csv"]
    if a.dataset != DATASET:
        raise SystemExit(f"REFUSED: registered on {DATASET} (§2, §5); got {a.dataset}")
    expect = parse_expect(a.expect) or PUBLISHED.get(Path(a.pairs).as_posix(), {})
    by_date = load_pit(Path(a.pairs))
    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
        expect = {}                 # a partial run cannot reproduce a full baseline
    have = [d for d in days if d in slices]

    tasks = []
    for k, day in enumerate(have):
        first = max(0, k - WARMUP_SESSIONS)
        tasks.append(([str(slices[d]) for d in have[first:k + 1]], day, by_date[day], PF))

    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"profit_floor_study: {len(tasks):,} session(s) on {jobs} worker(s)", flush=True)
    t0 = time.time()
    got: dict[str, dict] = {}
    if jobs == 1:
        it = map(run_day, tasks)
    else:
        from concurrent.futures import ProcessPoolExecutor
        ex = ProcessPoolExecutor(max_workers=jobs)
        it = ex.map(run_day, tasks, chunksize=2)
    for k, (day, res, err) in enumerate(it, 1):
        if err:
            print(f"  ! {day}: {err}", flush=True)
        if res is not None:
            got[day] = res
        if k % 50 == 0:
            print(f"  ... {k:,} of {len(tasks):,}", flush=True)
    if jobs != 1:
        ex.shutdown()

    books = {name: [] for name, _, _ in BOOKS}
    symdays, errors, error_days = 0, 0, []
    run_days = sorted(got)
    for day in run_days:
        r = got[day]
        for name in books:
            books[name] += r["books"][name]
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]

    emit("\n".join(render(books, symdays, errors, run_days, time.time() - t0, jobs, a,
                          error_days, expect)),
         a.out, header=f"common.profit_floor_study pairs={a.pairs} dataset={a.dataset} "
                       f"sessions={len(run_days)} symbol_days={symdays} qty={QTY} pf={PF}")
    write_csv(a.csv, books)
    meta = {"sessions": run_days, "symbol_days": symdays, "pairs": a.pairs,
            "dataset": a.dataset, "qty": QTY, "profit_floor": list(PF), "timestamps": "ET",
            "registered": REGISTERED}
    Path(a.csv).with_name(Path(a.csv).stem + "_meta.json").write_text(
        json.dumps(meta, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
