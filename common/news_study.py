#!/usr/bin/env python3
r"""H-N1 (entry veto) and H-N2 (exit alert) -- REGISTERED_news_events.md.

    python -m common.news_study
    python -m common.news_study --filings var/edgar/news_filings.csv \
        --headlines var/news/alpaca_headlines.csv

ACCOUNTING FORM ONLY (registration §1, H-N1's own words: "refused entries
are removed, not re-entered elsewhere"). Unlike `chase_gate.py` /
`range_rank.py`, this study does NOT re-run the MCL/MC5 engines: it reads the
population straight from `var/reports/chase_gate_trades.csv` (book in
{MCL, MC5} -- the same 10,370 entries / 1,578 symbols §2.1 names) and
removes a trade from the KEPT book when Trigger A or B was active at that
trade's own entry timestamp, per `common.news_events.label_at`, fed by the
per-symbol caches `common.news_pull` writes.

H-N1's four readings 1-4 (§5.1) reuse `common.gate_study`'s own arithmetic
unchanged; reading 5 (the abstention control) does NOT reuse
`gate_study.abstention`'s default parameters -- the registration's own bar is
5,000 draws, seed 20260924, and the Bonferroni-adjusted 99.375th percentile
(four cells: 2 sources x 2 books), not `gate_study`'s 2,000/95th defaults, so
`abstention_hn1` below runs the SAME mechanism at THOSE parameters. Items 6
(the marginal trade) and 7 (fewer than half the top-20 refused) are §6's
own carry-forward bar, computed and reported separately from the PASSES /
NOTHING / REFUSED tag. Item 8 (overlap with the spread gate) is NOT computed
here -- it needs W03-0002's own refused-trades output joined in, which this
pass does not have on disk, and the report says so rather than a fabricated
zero.

H-N2 IS COUNTED, NOT SCORED, IN THIS PASS. The paired-delta simulation
(§5.2: "exit immediately at the next bar's open") needs intrabar price
data this study's population (entry/exit price only, no tape) does not
carry. §5.2.4 orders this correctly regardless -- "how many trades this
could even apply to, reported FIRST" -- so this module computes exactly that
count (a trade whose news state flips false-to-true strictly between its own
entry and exit, needing no price data at all) and, per the registration's own
prediction (§9: "UNDERPOWERED on at least one book"), stops there when the
count is under the ~30-trade power floor. If a book clears that floor, the
report says so explicitly and names what is still missing (tape access for
the simulated exit) rather than fabricating a delta from data this pass does
not have.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from common import gate_study as G
from common import news_events as N
from common import news_pull as P
from common.entry_shares import MEASURED_FRICTION
from common.report_io import emit

ET = ZoneInfo("America/New_York")
REGISTERED = "docs/research/REGISTERED_news_events.md"
TRADES_CSV = P.TRADES_CSV
BOOKS = ("MCL", "MC5")

# §5.1 item 5: the registration's OWN abstention parameters -- distinct
# from gate_study.abstention's defaults (2,000 draws / breadth.SEED / 95th).
HN1_DRAWS = 5000
HN1_SEED = 20260924
HN1_Q = 0.99375          # "the 99.375th percentile (0.05 / 4)" -- §5.1 item 5, verbatim
HN1_TOP_N = 20            # §6 item 4 / §5.1 item 7: the 20 best trades

# §5.2.4: the power floor below which H-N2 is reported as underpowered
# rather than scored, whichever book it is measured on.
HN2_MIN_TRADES = 30

FRICTIONS = (("$1.00", 1.00), ("$4.26", 4.26), ("$8.92", 8.92))


# --- population: read straight from chase_gate_trades.csv, no engine re-run -

def _to_dt(date_s: str, hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    d = _date.fromisoformat(date_s)
    return datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=ET)


def load_population(trades_csv: str = TRADES_CSV,
                    books=BOOKS) -> dict[str, list[dict]]:
    """book -> its trade rows, straight from `chase_gate_trades.csv`, with
    `entry_ts` / `exit_ts` added (tz-aware ET) for point-in-time joins. The
    same 10,370-row / 1,578-symbol population REGISTERED_news_events.md
    §2.1 names -- read here, not re-derived, so a mismatch is a fact about
    the CSV, not about two counting rules."""
    p = Path(trades_csv)
    if not p.exists():
        sys.exit(f"{p} does not exist -- run `python -m common.chase_gate` first.")
    out: dict[str, list[dict]] = {b: [] for b in books}
    with p.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["book"] not in books:
                continue
            row = dict(r, net=float(r["net"]), ordinal=int(r["ordinal"]),
                      bars_held=int(r["bars_held"]),
                      entry_px=float(r["entry_px"]), exit_px=float(r["exit_px"]))
            row["entry_ts"] = _to_dt(row["date"], row["entry_et"])
            row["exit_ts"] = _to_dt(row["date"], row["exit_et"])
            out[row["book"]].append(row)
    return out


def symbol_days(rows: list[dict]) -> int:
    return len({(r["symbol"], r["date"]) for r in rows})


def median_cut(rows: list[dict]) -> str:
    """Halves are cut at the median TRADE DATE of the rows being scored --
    the accounting-form analogue of gate_study's 'median session run', since
    this study has no session list of its own (no engine pass)."""
    dates = sorted({r["date"] for r in rows})
    return dates[len(dates) // 2] if dates else ""


def build_events(filings: dict[str, list[dict]],
                 headlines: dict[str, list[dict]]) -> dict[str, list[N.Event]]:
    """symbol -> its merged, classified Events from both sources."""
    syms = set(filings) | set(headlines)
    return {s: N.events_from_filings(s, filings.get(s, []))
                + N.events_from_headlines(s, headlines.get(s, []))
           for s in syms}


# --- H-N1: the entry veto, accounting form -----------------------------------

def gate_book(base: list[dict], events: dict[str, list[N.Event]],
             sources: frozenset[str]) -> tuple[list[dict], list[dict]]:
    """(kept, removed) -- `removed` is every trade whose OWN entry timestamp
    had Trigger A or B active, per `news_events.label_at`. A symbol absent
    from `events` (no filing or headline data pulled/found for it) is never
    vetoed -- absence of evidence is not evidence of a trigger, the same
    convention `chase_gate.py`'s gates use for a NaN feature."""
    kept, removed = [], []
    for r in base:
        ev = events.get(r["symbol"], [])
        vetoed = N.label_at(ev, r["entry_ts"], sources=sources)["veto"] if ev else False
        (removed if vetoed else kept).append(r)
    return kept, removed


def abstention_hn1(base: list[dict], k: int, symdays: int,
                   f: float = MEASURED_FRICTION, draws: int = HN1_DRAWS,
                   seed: int = HN1_SEED, q: float = HN1_Q) -> dict:
    """The same random-removal mechanism as `gate_study.abstention`, at
    H-N1's OWN parameters (§5.1 item 5) rather than that function's
    defaults -- see the module docstring for why this is not reused as-is."""
    nets = np.array([r["net"] - f for r in base], dtype=float)
    n = len(nets)
    if n == 0 or k <= 0 or k >= n:
        return {"k": k, "n": n, "valid": False, "q": q, "draws": draws}
    rng = np.random.default_rng(seed)
    base_pt = nets.mean()
    total = nets.sum()
    d_pt = np.empty(draws)
    for i in range(draws):
        idx = rng.choice(n, size=k, replace=False)
        removed = nets[idx].sum()
        d_pt[i] = (total - removed) / (n - k) - base_pt
    return {"k": k, "n": n, "valid": True, "q": q, "draws": draws,
           "per_trade_q": float(np.quantile(d_pt, q))}


def verdict_hn1(base: list[dict], gated: list[dict], cut: str,
                symdays: int) -> tuple[str, str, dict]:
    """H-N1's five registered readings (§5.1 items 1-5). Items 1-4 reuse
    `gate_study`'s own arithmetic (imported into it from `first_entry_skip`
    / `breadth`, both reachable off the `G` module); item 5 uses
    `abstention_hn1`, not `gate_study.abstention`'s default bar."""
    f = MEASURED_FRICTION
    n: dict = {}
    n["d_per_trade"] = G.per_trade(gated, f) - G.per_trade(base, f)
    n["d_per_symday"] = (G.net(gated, f) - G.net(base, f)) / symdays if symdays else 0.0
    ba, bb = G.halves(base, cut)
    ga, gb = G.halves(gated, cut)
    n["early"] = (G.per_trade(ga, f) - G.per_trade(ba, f),
                 (G.net(ga, f) - G.net(ba, f)) / symdays if symdays else 0.0)
    n["late"] = (G.per_trade(gb, f) - G.per_trade(bb, f),
                (G.net(gb, f) - G.net(bb, f)) / symdays if symdays else 0.0)
    n["drop_level"] = (G.drop_top(gated, f), G.drop_top(base, f))
    d = G.deltas_by_symbol_day(base, gated, f)
    n["drop_delta"] = G.drop_top_delta(d)
    boot = G.cluster_bootstrap(G.delta_by_symbol(d))
    n["boot_p"] = G.share_above_zero(boot["totals"]) if boot["totals"] else 0.0
    n["boot_lo"] = G.pct(boot["totals"], 0.025) if boot["totals"] else 0.0
    n["boot_hi"] = G.pct(boot["totals"], 0.975) if boot["totals"] else 0.0
    n["n_syms"] = boot["n_syms"]
    n["removed"] = max(0, len(base) - len(gated))
    n["abst_hn1"] = abstention_hn1(base, n["removed"], symdays)

    if not (ba and bb and ga and gb):
        return "NOTHING", "a half is empty in one of the books", n
    if (n["d_per_trade"] > 0) != (n["d_per_symday"] > 0):
        return "REFUSED", (f"the two denominators disagree: per trade "
                           f"{n['d_per_trade']:+.2f}, per symbol-day "
                           f"{n['d_per_symday']:+.2f}"), n
    failed = []
    if not (n["d_per_trade"] >= G.MIN_MARGIN and n["d_per_symday"] > 0):
        failed.append(f"1 (per trade >= {G.MIN_MARGIN:.2f} and per symbol-day > 0)")
    if not all(x > 0 for x in n["early"] + n["late"]):
        failed.append("2 (both halves, both denominators)")
    if not (n["drop_level"][0] > n["drop_level"][1] and n["drop_delta"] > 0):
        failed.append(f"3 (drop-top-{G.DROP} on the level and on the delta)")
    if not n["boot_p"] >= G.BOOT_MIN_P:
        failed.append(f"4 (cluster bootstrap on the delta, P={n['boot_p']:.3f} "
                      f"< {G.BOOT_MIN_P})")
    a = n["abst_hn1"]
    if not a["valid"]:
        failed.append("5 (H-N1 abstention control not computable: nothing "
                      "removed, or everything)")
    elif not n["d_per_trade"] > a["per_trade_q"]:
        failed.append(f"5 (H-N1 abstention control: per trade "
                      f"{n['d_per_trade']:+.2f} does not beat random removal's "
                      f"{HN1_Q:.5f} quantile {a['per_trade_q']:+.2f}, "
                      f"{HN1_DRAWS} draws, seed {HN1_SEED})")
    if failed:
        return "NOTHING", "fails " + "; ".join(failed), n
    return "PASSES", ("all five readings, at $4.26, H-N1's own "
                      "Bonferroni-adjusted abstention bar"), n


def marginal_trade(base: list[dict], gated: list[dict]) -> dict:
    """§5.1 item 6, all three friction levels."""
    out = {}
    n0 = len(base)
    n1 = len(gated)
    for lab, f in FRICTIONS:
        t0 = sum(r["net"] - f for r in base)
        t1 = sum(r["net"] - f for r in gated)
        out[lab] = ((t1 - t0) / (n1 - n0)) if n1 != n0 else None
    return out


def top20_check(base: list[dict], gated: list[dict]) -> tuple[int, bool]:
    """§6 item 4 / §5.1 item 7: fewer than half of the book's 20 best
    trades refused. Returns (how many of the top 20 are absent from `gated`,
    whether that is FEWER than half)."""
    gone, _rows = G.top_absent(base, gated, MEASURED_FRICTION, n=HN1_TOP_N)
    return gone, gone < HN1_TOP_N / 2


# --- H-N2: counted, not scored, in this pass ---------------------------------

def mid_hold_trades(base: list[dict], events: dict[str, list[N.Event]],
                    sources: frozenset[str]) -> list[dict]:
    """Trades where Trigger A/B was FALSE at entry and TRUE by exit -- a
    genuinely new event landing inside the hold, since these windows (2 and
    30 days) cannot expire back to False over a multi-minute MCL/MC5 hold.
    No price data needed for this count (§5.2.4's own ordering)."""
    out = []
    for r in base:
        ev = events.get(r["symbol"], [])
        if not ev:
            continue
        at_entry = N.label_at(ev, r["entry_ts"], sources=sources)["veto"]
        at_exit = N.label_at(ev, r["exit_ts"], sources=sources)["veto"]
        if not at_entry and at_exit:
            out.append(r)
    return out


# --- report -------------------------------------------------------------------

def money(x) -> str:
    if x is None:
        return "n/a"
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def hn1_cell_block(book: str, source_name: str, base, gated, removed, cut, symdays) -> list[str]:
    tag, why, n = verdict_hn1(base, gated, cut, symdays)
    marg = marginal_trade(base, gated)
    gone20, top20_ok = top20_check(base, gated)
    a = n["abst_hn1"]
    L = [f"H-N1 -- {book} x {source_name}", "",
        f"  base {len(base):,} trades   kept {len(gated):,}   refused {len(removed):,}"
        f"   symbol-days {symdays:,}   halves cut at {cut}", "",
        f"  1. per trade {n['d_per_trade']:+.2f} (margin {G.MIN_MARGIN:.2f})   "
        f"per symbol-day {n['d_per_symday']:+.2f}",
        f"  2. early  per trade {n['early'][0]:+.2f}  per symbol-day {n['early'][1]:+.2f}"
        f"     late  per trade {n['late'][0]:+.2f}  per symbol-day {n['late'][1]:+.2f}",
        f"  3. drop-top-{G.DROP} level  kept {money(n['drop_level'][0])}  base "
        f"{money(n['drop_level'][1])}     drop-top-{G.DROP} delta "
        f"{money(n['drop_delta'])}",
        f"  4. cluster bootstrap on the delta  P(total > 0) = {n['boot_p']:.3f}  "
        f"[{money(n['boot_lo'])}, {money(n['boot_hi'])}]  over {n['n_syms']:,} symbols"]
    if a["valid"]:
        L.append(f"  5. H-N1 abstention: {a['k']:,} of {a['n']:,} removed at "
                 f"random, {a['draws']} draws, seed {HN1_SEED}   "
                 f"{a['q']:.5f} quantile {a['per_trade_q']:+.2f}   the gate "
                 f"{n['d_per_trade']:+.2f}")
    else:
        L.append(f"  5. H-N1 abstention control not computable "
                 f"({a['k']:,} removed of {a['n']:,})")
    L += ["", f"  {tag}: {why}", "",
         "  6. THE MARGINAL TRADE (removed-set average, all three frictions)"]
    for lab in FRICTIONS:
        L.append(f"       at {lab[0]:<6} {money(marg[lab[0]])}")
    half = "FEWER than half" if top20_ok else "*** HALF OR MORE ***"
    L += [f"  7. top-{HN1_TOP_N} best trades refused: {gone20} of {HN1_TOP_N}   "
         f"({half})",
         "  8. overlap with the W03-0002 spread gate's refusals: NOT COMPUTED "
         "in this pass -- needs that gate's own refused-trades output joined "
         "in, which is not on disk here.",
         "",
         f"  CARRY FORWARD (§6): "
         + ("YES" if tag == "PASSES" and top20_ok else "no")
         + (" -- verdict PASSES and fewer than half the top-20 refused"
            if tag == "PASSES" and top20_ok else
            " -- " + ("verdict is not PASSES" if tag != "PASSES"
                     else "half or more of the top-20 refused")),
         ""]
    return L


def hn2_cell_block(book: str, source_name: str, base, events, sources) -> list[str]:
    mid = mid_hold_trades(base, events, sources)
    n = len(mid)
    L = [f"H-N2 -- {book} x {source_name}", "",
        f"  trades with a mid-hold trigger: {n:,} of {len(base):,} base trades", ""]
    if n < HN2_MIN_TRADES:
        L += [f"  UNDERPOWERED: under the {HN2_MIN_TRADES}-trade power floor "
             f"(§5.2.4) -- reported as such, not scored as a pass or fail.",
             "  The paired-delta simulation (§5.2: exit at the next bar's",
             "  open) is not run for this cell -- §5.2.4 orders the count",
             "  first and this count does not clear the floor.", ""]
    else:
        L += [f"  CLEARS the {HN2_MIN_TRADES}-trade power floor. The paired-delta",
             "  simulation itself is NOT computed in this pass -- it needs",
             "  intrabar price data (the next bar's open at each trigger",
             "  timestamp) that chase_gate_trades.csv does not carry. Subitem",
             "  4b (tape access via pit_strategy/DBN) is the blocker for",
             "  scoring this cell; the count alone is not a verdict.", ""]
    if mid[:5]:
        L.append("  first few (symbol, date, entry, exit):")
        for r in mid[:5]:
            L.append(f"    {r['symbol']:<6} {r['date']}  {r['entry_et']} -> "
                     f"{r['exit_et']} ET")
        L.append("")
    return L


def render(pop: dict, events: dict, cuts: dict, symdays: dict) -> list[str]:
    L = ["H-N1 / H-N2 -- NEWS AS AN ENTRY VETO / EXIT ALERT", "",
        f"  registered  {REGISTERED}",
        f"  population  {TRADES_CSV}   book in {{MCL, MC5}}",
        f"  MCL {len(pop['MCL']):,} trades   MC5 {len(pop['MC5']):,} trades", ""]
    for book in BOOKS:
        base = pop[book]
        for source_name, sources in N_SOURCE_CELLS:
            gated, removed = gate_book(base, events, sources)
            L += hn1_cell_block(book, source_name, base, gated, removed,
                                cuts[book], symdays[book])
    for book in BOOKS:
        base = pop[book]
        for source_name, sources in N_SOURCE_CELLS:
            L += hn2_cell_block(book, source_name, base, events, sources)
    L += ["WHAT THIS IS NOT", "",
         "  NOT AN ENGINE RE-RUN. Accounting form only (§1): refused entries",
         "  are removed, not re-entered elsewhere; a freed concurrency slot is",
         "  not in these numbers.",
         "  NOT H-N3. News-triggered entries are not scored anywhere in this",
         "  module (§1).",
         "  NOT OUT OF SAMPLE. holdout.json has not been touched.",
         "  NOT COMPLETE COVERAGE. A symbol with no filing/headline data pulled",
         "  is never vetoed by construction -- see `gate_book`'s own docstring;",
         "  the coverage a real pull achieves is reported by `news_pull.py`,",
         "  not re-derived here.", ""]
    return L


N_SOURCE_CELLS = (("EDGAR-only", N.EDGAR_ONLY),
                  ("EDGAR+headlines", N.EDGAR_PLUS_HEADLINES))


# --- csv ----------------------------------------------------------------------------

CSV_COLS = ("book", "source", "symbol", "date", "entry_et", "net", "vetoed")


def write_labeled_csv(path: str, pop: dict, events: dict) -> None:
    rows = []
    for book in BOOKS:
        for source_name, sources in N_SOURCE_CELLS:
            for r in pop[book]:
                ev = events.get(r["symbol"], [])
                vetoed = N.label_at(ev, r["entry_ts"], sources=sources)["veto"] if ev else False
                rows.append({"book": book, "source": source_name, "symbol": r["symbol"],
                            "date": r["date"], "entry_et": r["entry_et"],
                            "net": r["net"], "vetoed": vetoed})
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CSV_COLS))
        w.writeheader()
        w.writerows(rows)


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--trades-csv", default=TRADES_CSV)
    p.add_argument("--filings", default=P.FILINGS_CSV)
    p.add_argument("--headlines", default=P.HEADLINES_CSV)
    p.add_argument("--out", default="var/reports/news_study.txt")
    p.add_argument("--csv", default="var/reports/news_study_trades.csv")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    pop = load_population(a.trades_csv)
    filings = P.load_filings_csv(a.filings)
    headlines = P.load_headlines_csv(a.headlines)
    if not filings and not headlines:
        print("WARNING: no filings or headlines cache found -- every trade "
             "will read as un-vetoed. Run common.news_pull first (needs "
             "SEC_CONTACT / ALPACA_* and --confirm).", flush=True)
    events = build_events(filings, headlines)
    cuts = {b: median_cut(pop[b]) for b in BOOKS}
    symdays = {b: symbol_days(pop[b]) for b in BOOKS}
    body = render(pop, events, cuts, symdays)
    emit("\n".join(body), a.out,
        header=f"common.news_study trades={a.trades_csv} filings={a.filings} "
              f"headlines={a.headlines} registered={REGISTERED}")
    write_labeled_csv(a.csv, pop, events)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
