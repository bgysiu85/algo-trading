#!/usr/bin/env python3
"""ORB's grid — ninety cells, every bucket printed, nothing ranked.

    python -m strategy.orb.grid --pairs var/state/screened_pairs.json \
        var/state/screened_rejects.json --jobs 8

Spec §14 item 9. `docs/research/REGISTERED_orb_grid.md` was written and
committed BEFORE this file and decides everything about how the output is
read; this module does what that document says and adds no judgement of its
own. Where the two disagree, the registration wins and this file is the bug.

WHAT IT DOES NOT DO, and each absence is load-bearing:

  * it prints **no "best cell" table** and applies no ranking (§3);
  * it never substitutes a grid winner into §11 -- the seven criteria are read
    on the BASELINE cell and a winner is a LEAD (§3);
  * it does not search length and stop separately (§3.2), which is why the
    cell key is the whole four-tuple and there is no per-family sweep anywhere
    in here;
  * it reads NO cell with fewer than 100 trades -- printed with its count and
    no verdict (§5);
  * it refuses a verdict when the two denominators disagree (§5 item 1).

THE BOOTSTRAP IS `common/breadth.py`'s, CALLED AND NOT REIMPLEMENTED. Same
seed, same resample count, same construction MC5 was re-scored with, or ORB
and MC5 are not being judged by the same instrument (§4 of
`REGISTERED_breadth.md`).
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from common.breadth import (BOOT_MIN_P, RESAMPLES, SEED, cluster_bootstrap,
                            pct, share_above_zero)
from common.report_io import emit
from strategy.orb import orb as O
from strategy.orb.preflight import ORB_MIN_MOVE_PCT, load_bars, rth_session

# §3. `opposite` is NOT here, and its absence is a PRE-REGISTERED FILTER
# firing rather than a search selecting: median R of 9.26% of price against a
# MAX_R_PCT of 12% written in spec §6 before the measurement was made. A value
# eliminated by a threshold set in advance costs no multiplicity; a value
# chosen because it scored best costs all of it.
GRID_MINUTES = (5, 15, 30)
GRID_STOPS = ("structure", "rangefrac")
GRID_RETESTS = O.RETEST_MODES
GRID_EXITS = O.EXIT_MODES

MIN_TRADES = 100          # §5 -- below this a cell is printed and not read
DROPS = (1, 3, 5)

# §3.1. Four independent choices, not ninety. The report states this beside
# any claim made FROM the grid rather than leaving a reader to supply it.
FAMILIES = ("length", "stop", "retest", "exit")


def cells() -> list[O.Config]:
    return [O.Config(orb_minutes=m, stop_mode=s, retest_mode=r, exit_mode=e)
            for m, s, r, e in itertools.product(
                GRID_MINUTES, GRID_STOPS, GRID_RETESTS, GRID_EXITS)]


def key_of(cfg: O.Config) -> tuple:
    return (cfg.orb_minutes, cfg.stop_mode, cfg.retest_mode, cfg.exit_mode)


BASELINE_KEY = key_of(O.BASELINE)


# --------------------------------------------------------------------------
# accumulation
# --------------------------------------------------------------------------

@dataclass
class Cell:
    """Everything §5 requires, and nothing aggregated yet.

    Per-symbol nets are kept as LISTS rather than sums because the cluster
    bootstrap needs every trade of a drawn symbol to travel with it -- summing
    here would silently turn a symbol-cluster bootstrap into a symbol-total
    one, which is a different and easier test.
    """

    by_symbol: dict = field(default_factory=dict)      # sym -> [net, ...]
    by_symbol_day: dict = field(default_factory=dict)  # (sym, day) -> net
    by_date: dict = field(default_factory=dict)        # day -> net
    status: Counter = field(default_factory=Counter)
    entry_hhmm: Counter = field(default_factory=Counter)
    exit_reason: Counter = field(default_factory=Counter)
    wins: int = 0
    trades: int = 0
    both_in_bar: int = 0
    open_at_close: int = 0
    # §10.2 population split and §10.2b reject arm, carried per cell so the
    # split is computed from the same trades as the headline.
    net_by_arm: dict = field(default_factory=dict)     # (population, passes) -> [net]

    def add(self, res: "O.SessionResult", population: str) -> None:
        self.status[res.status] += 1
        self.both_in_bar += res.both_in_bar
        self.open_at_close += int(res.open_at_close)
        if not res.trades:
            return
        day_net = 0.0
        for t in res.trades:
            self.by_symbol.setdefault(t.symbol, []).append(t.net)
            self.exit_reason[t.exit_reason] += 1
            self.entry_hhmm[f"{t.entry_time:%H:%M}"] += 1
            self.wins += int(t.net > 0)
            self.trades += 1
            day_net += t.net
        self.by_symbol_day[(res.symbol, res.date)] = day_net
        self.by_date[res.date] = self.by_date.get(res.date, 0.0) + day_net
        arm = (population, bool(res.passes_rth_screen))
        self.net_by_arm.setdefault(arm, []).append(day_net)

    def merge(self, other: "Cell") -> None:
        for k, v in other.by_symbol.items():
            self.by_symbol.setdefault(k, []).extend(v)
        self.by_symbol_day.update(other.by_symbol_day)
        for k, v in other.by_date.items():
            self.by_date[k] = self.by_date.get(k, 0.0) + v
        self.status += other.status
        self.entry_hhmm += other.entry_hhmm
        self.exit_reason += other.exit_reason
        self.wins += other.wins
        self.trades += other.trades
        self.both_in_bar += other.both_in_bar
        self.open_at_close += other.open_at_close
        for k, v in other.net_by_arm.items():
            self.net_by_arm.setdefault(k, []).extend(v)


def run_chunk(args) -> dict:
    """One worker: a slice of symbol-days, all ninety cells.

    ONE resample per symbol-day, shared by every cell -- see `orb.Bars`.
    """
    cache, pairs, cfgs = args
    out = {key_of(c): Cell() for c in cfgs}
    for pr in pairs:
        sym, day, population = pr["symbol"], pr["date"], pr["population"]
        df = load_bars(Path(cache), sym, day)
        if df is None:
            continue
        sess = rth_session(df, day)
        if sess.empty:
            continue
        view = O.trigger_bars(sess, O.BASELINE.trigger_bar_minutes)
        passes = _rth_screen(sess)          # per symbol-day, not per cell
        for cfg in cfgs:
            res = O.backtest_session(sess, sym, day, cfg, bars=view)
            res.passes_rth_screen = passes
            out[key_of(cfg)].add(res, population)
    return out


def _rth_screen(sess) -> bool:
    """§10.2, as far as the cache allows -- and it says so.

    `relative_volume_10d_calc` is NOT COMPUTABLE from this cache: only 2 of
    27,777 symbol-days carry all ten prior sessions. So this is the screen on
    THREE of its four rules, and the report says that beside every number
    derived from it rather than letting `passes` read as the real screen.
    """
    o = float(sess["open"].iloc[0])
    last = float(sess["close"].iloc[-1])
    if o <= 0:
        return False
    return ((last - o) / o * 100.0 > ORB_MIN_MOVE_PCT
            and O.PRICE_MIN <= last <= O.PRICE_MAX)


# --------------------------------------------------------------------------
# reading a cell
# --------------------------------------------------------------------------

def drop_top(totals: dict, k: int) -> float:
    return sum(sorted(totals.values(), reverse=True)[k:])


def read(cell: Cell, split_date: str) -> dict:
    """Every figure §5 requires for one cell. No verdict is formed here."""
    tot = {s: sum(v) for s, v in cell.by_symbol.items()}
    net = sum(tot.values())
    n_t, n_sd = cell.trades, len(cell.by_symbol_day)
    d = {
        "trades": n_t, "symbols": len(tot), "symbol_days": n_sd, "net": net,
        "per_trade": net / n_t if n_t else 0.0,
        "per_symbol_day": net / n_sd if n_sd else 0.0,
        "win_rate": cell.wins / n_t if n_t else 0.0,
        "both_in_bar": cell.both_in_bar,
        "open_at_close": cell.open_at_close,
        "thin": n_t < MIN_TRADES,
    }
    for k in DROPS:
        d[f"drop{k}"] = drop_top(tot, k)

    early = sum(v for day, v in cell.by_date.items() if day < split_date)
    late = sum(v for day, v in cell.by_date.items() if day >= split_date)
    et = sum(1 for (s, day) in cell.by_symbol_day if day < split_date)
    d["early"], d["late"] = early, late
    d["early_days"], d["late_days"] = et, n_sd - et

    # §5 item 1's refusal is NOT computed here, and the first draft of this
    # file computed it here and was wrong.
    #
    # `per_trade` and `per_symbol_day` are the SAME net over two positive
    # divisors, so they always carry the same sign. A single-cell
    # "denominators agree" flag can never fire -- the identical shape as
    # breadth's withdrawn condition (b), which was (a) at a stricter level
    # wearing the clothes of a magnitude check. A check that cannot fail is
    # not a check, and this one would have printed "0 cells refused" forever.
    #
    # The disagreement §5 means is real and lives in the COMPARISON: the two
    # ratios can order two cells differently, because the cells have different
    # trades-per-symbol-day. So the refusal attaches to a delta against the
    # baseline, in `deltas()`.

    if n_t:
        boot = cluster_bootstrap(cell.by_symbol, RESAMPLES, SEED)
        d["boot_p"] = share_above_zero(boot["totals"])
        d["boot_lo"] = pct(boot["totals"], 0.025)
        d["boot_hi"] = pct(boot["totals"], 0.975)
        # Reported as context for reading the total, and explicitly NOT a pass
        # condition -- condition (b) was withdrawn before use because it could
        # not fail independently of (a). A figure printed beside a verdict it
        # cannot change has to say so.
        d["boot_pt_lo"] = pct(boot["per_trade"], 0.025)
        d["boot_pt_hi"] = pct(boot["per_trade"], 0.975)
    else:
        d.update(boot_p=0.0, boot_lo=0.0, boot_hi=0.0,
                 boot_pt_lo=0.0, boot_pt_hi=0.0)
    return d


def deltas(cell: Cell, base: Cell) -> dict:
    """Drop-top-N on the DELTA against the baseline cell, per §5 item 2.

    Paired by SYMBOL, because that is the unit the level's drop-top-N uses and
    the unit the bootstrap resamples. A delta table computed on a different
    unit from the level table beside it is two measurements wearing one
    heading.
    """
    a = {s: sum(v) for s, v in cell.by_symbol.items()}
    b = {s: sum(v) for s, v in base.by_symbol.items()}
    delta = {s: a.get(s, 0.0) - b.get(s, 0.0) for s in set(a) | set(b)}
    out = {"delta": sum(delta.values())}
    for k in DROPS:
        out[f"delta_drop{k}"] = drop_top(delta, k)

    # §5 item 1, WHERE IT CAN ACTUALLY FAIL. Two cells trade different numbers
    # of times on different numbers of symbol-days, so "this cell beats the
    # baseline" can come out one way per trade and the other way per
    # symbol-day. That is a genuine disagreement between two honest
    # denominators, and it is a REFUSAL -- not a tie to be broken, and not an
    # invitation to quote whichever one reads better.
    an, bn = sum(a.values()), sum(b.values())
    at, bt = cell.trades, base.trades
    ad, bd = len(cell.by_symbol_day), len(base.by_symbol_day)
    dpt = (an / at if at else 0.0) - (bn / bt if bt else 0.0)
    dpd = (an / ad if ad else 0.0) - (bn / bd if bd else 0.0)
    out["d_per_trade"], out["d_per_symbol_day"] = dpt, dpd
    # Exact zeros agree with everything, which is what the baseline compared
    # against itself must do.
    out["denoms_agree"] = (dpt >= 0) == (dpd >= 0) or (dpt == 0 and dpd == 0)
    return out


# --------------------------------------------------------------------------
# the report
# --------------------------------------------------------------------------

def _row(key, d, dd) -> str:
    m, s, rt, e = key
    flag = "  THIN" if d["thin"] else (
        "" if dd["denoms_agree"] else "  REFUSED vs baseline")
    return (f"  {m:>2} {s:<10} {rt:<8} {e:<9} "
            f"{d['trades']:>6,} {d['symbols']:>6,} "
            f"{d['per_trade']:>8.2f} {d['per_symbol_day']:>8.2f} "
            f"{d['net']:>11,.0f} {d['drop3']:>11,.0f} {d['drop5']:>11,.0f} "
            f"{d['early']:>10,.0f} {d['late']:>10,.0f} "
            f"{d['boot_p']:>6.3f} {dd['delta_drop5']:>10,.0f}{flag}")


def render(read_all: dict, delta_all: dict, split_date: str,
           seen: int, elapsed: float, args) -> list[str]:
    L = [
        "ORB GRID — ninety cells, every one printed, nothing ranked", "",
        f"  symbol-days read   {seen:,}",
        f"  cells              {len(read_all)}  "
        f"({len(GRID_MINUTES)} lengths x {len(GRID_STOPS)} stops x "
        f"{len(GRID_RETESTS)} retests x {len(GRID_EXITS)} exits)",
        f"  halves split at    {split_date}  (median session date, not swept)",
        f"  bootstrap          {RESAMPLES:,} resamples, seed {SEED} — the same "
        "call MC5 was re-scored with",
        f"  elapsed            {elapsed:,.0f}s",
        "",
        "  READ THIS FIRST. A cell that beats the baseline is a LEAD, NOT A",
        "  RESULT. It does not enter §11, it is not ORB's performance, and it",
        "  cannot ship without its own registration and its own out-of-sample",
        "  test. `var/state/holdout.json` is not spent on anything here.",
        "",
        f"  MULTIPLICITY IS COUNTED BY FAMILY, NOT COLUMN: {len(FAMILIES)} "
        f"families ({', '.join(FAMILIES)}).",
        "  Any claim made FROM the grid rather than from the baseline carries",
        "  four, not ninety and not one.",
        "",
        "  `opposite` is absent because spec §6 set MAX_R_PCT = 12% BEFORE the",
        "  pre-flight measured its median R at 9.26% of price with p90 17.72%.",
        "  A pre-registered filter firing, not a search selecting.",
        "",
    ]

    base_d = read_all[BASELINE_KEY]
    L += ["THE BASELINE CELL — and §11's seven criteria are read HERE ONLY", ""]
    m, s, rt, e = BASELINE_KEY
    L += [f"  ORB_MINUTES {m}   STOP {s}   RETEST {rt}   EXIT {e}", ""]
    L += _cell_detail(base_d)
    L.append("")

    L += ["EVERY CELL", "",
          "   m stop       retest   exit       trades symbols "
          "per_trd  per_day         net      drop3      drop5"
          "      early       late  boot_p  d_drop5",
          "  " + "-" * 136]
    for key in sorted(read_all):
        L.append(_row(key, read_all[key], delta_all[key]))
    L.append("")

    thin = [k for k, d in read_all.items() if d["thin"]]
    L += [f"  {len(thin)} of {len(read_all)} cells hold fewer than "
          f"{MIN_TRADES} trades and are NOT READ (§5): below that, drop-top-5",
          "  removes 5% of the sample and stops meaning what it says. They are",
          "  printed above with their counts and no verdict.", ""]
    refused = [k for k, d in read_all.items()
               if not d["thin"] and not delta_all[k]["denoms_agree"]]
    L += [f"  {len(refused)} readable cell(s) REFUSED: measured against the",
          "  baseline, the per-trade and per-symbol-day deltas point OPPOSITE",
          "  WAYS. That is not a tie to be broken and not an invitation to",
          "  quote whichever reads better — the comparison has not produced a",
          "  result.",
          "",
          "  Note the refusal attaches to a COMPARISON and never to a single",
          "  cell: one cell's two denominators are the same net over two",
          "  positive divisors and always share a sign, so a per-cell version",
          "  of this check could never fire.", ""]

    L += _boundary_block(read_all)
    L += _prediction_block(read_all)
    L += _screen_block(read_all)
    return L


def _cell_detail(d: dict) -> list[str]:
    pt = f"{d['per_trade']:+,.2f}"
    return [
        f"  trades            {d['trades']:,}   symbols {d['symbols']:,}   "
        f"symbol-days {d['symbol_days']:,}",
        f"  net               ${d['net']:+,.0f}",
        f"  per trade         ${pt}        per symbol-day  "
        f"${d['per_symbol_day']:+,.2f}",
        f"  drop-top-1/3/5    ${d['drop1']:+,.0f} / ${d['drop3']:+,.0f} / "
        f"${d['drop5']:+,.0f}",
        f"  halves            early ${d['early']:+,.0f} "
        f"({d['early_days']:,} days)   late ${d['late']:+,.0f} "
        f"({d['late_days']:,} days)",
        f"  cluster bootstrap P(total>0) {d['boot_p']:.3f} against a "
        f"{BOOT_MIN_P:.2f} bar   "
        f"[{d['boot_lo']:+,.0f}, {d['boot_hi']:+,.0f}]",
        f"  per-trade interval [{d['boot_pt_lo']:+.2f}, {d['boot_pt_hi']:+.2f}]"
        "   — CONTEXT ONLY, not a pass condition (withdrawn before use)",
        f"  win rate          {d['win_rate']:.1%}",
        f"  stop AND target in one bar   {d['both_in_bar']:,}  "
        "(§7.2: the stop won every one)",
        f"  positions open when bars ran out  {d['open_at_close']:,}",
    ]


def _boundary_block(read_all: dict) -> list[str]:
    """§11 criterion 7, made checkable — and honest about where it cannot be
    checked at all. A criterion that cannot fail is not a criterion, and one
    that quietly reports 'no boundary optimum' over a two-value family is
    claiming a check it did not perform."""
    L = ["THE BOUNDARY RULE (§11 criterion 7)", ""]
    per_len = {}
    for (m, s, rt, e), d in read_all.items():
        if not d["thin"]:
            per_len.setdefault(m, []).append(d["per_trade"])
    if per_len:
        best = max(per_len, key=lambda m: max(per_len[m]))
        L.append(f"  ORB_MINUTES: best readable per-trade sits at {best} "
                 f"minutes.")
        if best in (min(GRID_MINUTES), max(GRID_MINUTES)):
            L.append(f"  >> ON A BOUNDARY. The box must be pushed "
                     f"({'3' if best == 5 else '45'}) and the grid re-run "
                     "before this is read as an optimum.")
        else:
            L.append("  Interior. No push required.")
    else:
        L.append("  ORB_MINUTES: no readable cell at any length.")
    L += [
        "",
        "  STOP_MODE: two values remain, so BOTH ARE BOUNDARIES and the rule",
        "  CANNOT APPLY. Reported rather than passed silently.",
        "",
        "  RETEST_MODE and EXIT_MODE are unordered, so the rule does not apply",
        "  to them either. Also reported rather than passed silently.",
        "",
    ]
    return L


def _prediction_block(read_all: dict) -> list[str]:
    """The registered prediction, scored automatically, whichever way it went.
    REGISTERED_orb_grid.md amendment §B, written before this file existed."""
    m = O.BASELINE.orb_minutes
    row = {e: read_all.get((m, O.BASELINE.stop_mode, O.BASELINE.retest_mode, e))
           for e in GRID_EXITS}
    L = ["THE REGISTERED PREDICTION (amendment §B, written pre-run)", "",
         "  `r_2` will be beaten on per-trade net by at least one of the four",
         f"  other exits at {m} minutes, because the pre-flight found the stop",
         "  resolving at a median 4 bars against 2R at 6.", ""]
    base = row.get("r_2")
    if not base or base["thin"]:
        L += ["  NOT SCORED — the r_2 cell is thin or absent.", ""]
        return L
    beat = [e for e, d in row.items()
            if e != "r_2" and d and not d["thin"]
            and d["per_trade"] > base["per_trade"]]
    for e in GRID_EXITS:
        d = row.get(e)
        if d:
            L.append(f"    {e:<10} {d['per_trade']:>8.2f} per trade"
                     f"{'   (thin, not read)' if d['thin'] else ''}")
    L += ["",
          ("  PREDICTION HELD — beaten by " + ", ".join(beat)) if beat else
          "  PREDICTION FAILED — r_2 was not beaten. The stop/target race does "
          "not decide the exit, and that is the surprise, not a rounding error.",
          ""]
    return L


def _screen_block(read_all: dict) -> list[str]:
    return [
        "THE §10.2 POPULATION SPLIT AND THE §10.2b REJECT ARM", "",
        "  Written to the per-cell CSV (`arm_*` columns), not summarised here,",
        "  because §5 says every bucket is printed and a summary of a split is",
        "  the one place a reader stops checking.",
        "",
        "  AND THE SCREEN IS THREE OF ITS FOUR RULES. "
        "`relative_volume_10d_calc`",
        "  is not computable from this cache — 2 of 27,777 symbol-days carry",
        "  all ten prior sessions — so §11 criterion 6 is tested on three",
        "  rules. `largecap_evidence_20260911.md` finds 100% of the stocks-ORB",
        "  paper's claimed edge came from ranking on first-5-minute relative",
        "  volume: the rule we cannot simulate is the one the outside",
        "  literature says carries everything.",
        "",
    ]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def load_pairs(paths: list[str], limit: int | None) -> list[dict]:
    out = []
    for i, p in enumerate(paths):
        label = "survivors" if i == 0 else "rejected"
        rows = json.loads(Path(p).read_text())
        if limit:
            rows = rows[:limit]
        for r in rows:
            out.append({"symbol": r["symbol"], "date": r["date"],
                        "population": label})
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", nargs="+", required=True,
                   help="survivors first, then rejects")
    p.add_argument("--cache", default="bar_cache_db")
    p.add_argument("--window", default="3d_to_2000")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--limit", type=int)
    p.add_argument("--out", default="var/reports/orb_grid.txt")
    p.add_argument("--csv", default="var/reports/orb_grid_cells.csv")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    root = Path(a.cache)
    cache = root if root.name == a.window else root / a.window
    if not cache.is_dir():
        sys.exit(f"no bar cache at {cache}")

    pairs = load_pairs(a.pairs, a.limit)
    if not pairs:
        sys.exit("no symbol-days")
    # THE SPLIT POINT IS DERIVED FROM THE DATA AND NEVER SWEPT (§5 item 3).
    dates = sorted({p["date"] for p in pairs})
    split_date = dates[len(dates) // 2]

    cfgs = cells()
    t0 = time.perf_counter()
    merged = {key_of(c): Cell() for c in cfgs}

    n = max(1, len(pairs) // (a.jobs * 4)) if a.jobs > 1 else len(pairs)
    chunks = [(str(cache), pairs[i:i + n], cfgs) for i in range(0, len(pairs), n)]
    print(f"{len(pairs):,} symbol-days, {len(cfgs)} cells, "
          f"{len(chunks)} chunks, {a.jobs} job(s)")

    if a.jobs > 1:
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            for k, part in enumerate(ex.map(run_chunk, chunks), 1):
                for key, cell in part.items():
                    merged[key].merge(cell)
                if k % 10 == 0:
                    print(f"  {k}/{len(chunks)} chunks")
    else:
        for k, ch in enumerate(chunks, 1):
            for key, cell in run_chunk(ch).items():
                merged[key].merge(cell)

    seen = sum(merged[BASELINE_KEY].status.values())
    read_all = {k: read(c, split_date) for k, c in merged.items()}
    base = merged[BASELINE_KEY]
    delta_all = {k: deltas(c, base) for k, c in merged.items()}
    elapsed = time.perf_counter() - t0

    if a.csv:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for key in sorted(read_all):
            d = dict(read_all[key]); d.update(delta_all[key])
            d.update(orb_minutes=key[0], stop_mode=key[1],
                     retest_mode=key[2], exit_mode=key[3])
            for (pop, passes), nets in merged[key].net_by_arm.items():
                d[f"arm_{pop}_{'pass' if passes else 'fail'}_net"] = sum(nets)
                d[f"arm_{pop}_{'pass' if passes else 'fail'}_days"] = len(nets)
            for status, cnt in merged[key].status.items():
                d[f"status_{status}"] = cnt
            rows.append(d)
        fields = sorted({k for r in rows for k in r})
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"wrote {a.csv}")

    emit("\n".join(render(read_all, delta_all, split_date, seen, elapsed, a)),
         a.out,
         header=(f"strategy.orb.grid  cache={cache.name}  "
                 f"pairs={','.join(Path(x).name for x in a.pairs)}  "
                 f"symbol_days={seen:,}  cells={len(cfgs)}  "
                 f"split={split_date}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
