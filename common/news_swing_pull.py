#!/usr/bin/env python3
r"""W07-0011 subitem 2/3 -- per-symbol EDGAR + Alpaca pull for SWING-v0
picks, priced before pulled (same G4 convention `common.news_pull` and
`docs/research/REGISTERED_news_events.md` §0 G4 use).

    $env:SEC_CONTACT = "you@example.com"
    $env:ALPACA_API_KEY_ID = "..."
    $env:ALPACA_API_SECRET_KEY = "..."
    python -m common.news_swing_pull --coverage
    python -m common.news_swing_pull --pull-edgar --confirm
    python -m common.news_swing_pull --pull-alpaca --confirm

REUSE, NOT A REWRITE -- exactly what W07-0011's design doc (subitem 2) asks
for ("reuse W03-0010's per-symbol Alpaca/EDGAR puller and cache"):

  * EDGAR: calls `common.news_pull.pull_edgar` UNCHANGED. That function was
    already population-agnostic (it takes `pop: dict[symbol, date]` as a
    parameter, not a hardcoded population) -- only `news_pull.py`'s own CLI
    hardcodes the chase_gate_trades.csv population. This module supplies a
    DIFFERENT population (SWING-v0's picks, via
    `news_swing_tag.population_from_picks`) and a different output path, and
    otherwise runs the identical fetch/cache/pace/retry code the W03-0010
    line already trusts (`common.edgar_shares.Fetcher`).

  * Alpaca: calls `common.news_pull.alpaca_symbol_history` UNCHANGED per
    symbol (same pagination, same pacing). What differs is what gets
    written: `news_pull.pull_alpaca` keeps only {symbol, headline,
    created_at} per item, discarding Alpaca's own `symbols` field (the full
    ticker list a headline is tagged to). W07-0011 §11.2 needs that count
    (the ">5 symbols = market wrap" exclusion,
    `news_swing_tag.MARKET_WRAP_MAX_SYMBOLS`), so this module's own
    `pull_alpaca_with_symbol_count` keeps `len(symbols)` alongside the two
    fields `news_pull` already keeps, writing a SEPARATE cache file
    (`SWING_HEADLINES_CSV`) rather than changing `news_pull`'s own schema
    and risking the W03-0010 line's existing cache/tests.

WHY A SEPARATE POPULATION, NOT THE FULL POINT-IN-TIME UNIVERSE
-----------------------------------------------------------------
SWING-v0's universe (`var/swing_pit/membership.csv`) is ~1,600 names across
ten years. Pulling per-symbol history for all of them, most of which
SWING-v0 never actually picks on any given day, would be priced far above
what this study needs. The population here is `news_swing_tag.
population_from_picks` -- symbols SWING-v0's own picks CSV actually names,
same convention `news_pull.population_symbols` uses for the chase_gate line
(read the population from the study's own scored rows, not re-derived).

THIS MODULE CANNOT RUN YET. `strategy/swing/reversal_v0.py` (W07-0010) has
not been built, so there is no picks CSV to read a population from. Every
function below is population-agnostic and unit-tested against a synthetic
picks fixture; `main()` fails loudly with a clear message pointing at
W07-0010 if the picks file is missing, the same shape
`news_swing_tag.load_picks_csv` already fails with.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from common import edgar_shares as E
from common import news_pull as P
from common.news_swing_tag import PICK_FIELDS, load_picks_csv, population_from_picks
from common.report_io import emit

SWING_FILINGS_CSV = "var/edgar/swing_news_filings.csv"
SWING_HEADLINES_CSV = "var/news/swing_alpaca_headlines.csv"
SWING_HEADLINE_COLS = ("symbol", "headline", "created_at", "symbol_count")

DEFAULT_PICKS_CSV = "var/reports/swing_v0_picks.csv"

ALPACA_PACE_S = P.ALPACA_PACE_S
HISTORY_BUFFER_DAYS = P.HISTORY_BUFFER_DAYS   # same buffer-before-earliest-date convention


# --- population --------------------------------------------------------------

def swing_population(picks_csv: str = DEFAULT_PICKS_CSV) -> dict[str, str]:
    """symbol -> earliest `drop_start_date` across that symbol's picks. Exits
    with the same clear message `news_swing_tag.load_picks_csv` gives if the
    picks file doesn't exist -- this pull cannot start before W07-0010 has
    run."""
    picks = load_picks_csv(picks_csv)   # raises SystemExit if missing (deliberate)
    pop = population_from_picks(picks)
    if not pop:
        sys.exit(f"{picks_csv} has no pick rows -- nothing to pull for.")
    return pop


# --- EDGAR: news_pull.pull_edgar, unchanged, different population -----------

def edgar_cost_section(pop: dict, tmap: dict) -> list[str]:
    # identical shape to news_pull.edgar_cost_section; kept as its own
    # function only so this module's report can say "SWING-v0 picks" instead
    # of the chase_gate population's own header line.
    matched = [s for s in pop if E.normalise(s) in tmap]
    n = len(matched)
    return ["EDGAR -- WHAT THE SWING-v0 PICKS PULL WOULD COST", "",
           f"  population symbols (from picks)  {len(pop):,}",
           f"  matched to a CIK                 {n:,}",
           f"  requests                         {n:,}",
           f"  wall clock at {1 / E.MIN_INTERVAL:.1f}/s              "
           f"{n * E.MIN_INTERVAL / 60:.0f} min", ""]


def pull_edgar_for_swing(pop: dict, f: E.Fetcher, tmap: dict,
                         limit: int | None = None):
    """Thin pass-through to `news_pull.pull_edgar` -- see module docstring.
    Kept as a named wrapper (not called inline) so a test can assert this
    module calls the SAME function W03-0010 already trusts, rather than a
    reimplementation that happens to look similar."""
    return P.pull_edgar(pop, f, tmap, limit=limit)


# --- Alpaca: alpaca_symbol_history reused, symbol_count kept ----------------

def alpaca_cost_section(pop: dict) -> list[str]:
    n = len(pop)
    return ["ALPACA/BENZINGA -- WHAT THE SWING-v0 PICKS PULL WOULD COST", "",
           f"  population symbols (from picks)  {n:,}",
           f"  requests                         at least {n:,} (one page per "
           "symbol; dense history pages further)",
           f"  wall clock                       at least {n * ALPACA_PACE_S / 60:.0f} "
           f"min at {ALPACA_PACE_S}s/page, single-threaded", ""]


def pull_alpaca_with_symbol_count(pop: dict, key: str, secret: str, *,
                                  limit: int | None = None, opener=None,
                                  sleep=time.sleep) -> tuple[list[dict], dict[str, str]]:
    """Same per-symbol call as `news_pull.pull_alpaca`
    (`P.alpaca_symbol_history`, unchanged), but keeps `len(symbols)` per
    headline -- the field §11.2's >5-symbol exclusion needs and
    `news_pull.pull_alpaca` discards (module docstring)."""
    rows: list[dict] = []
    status: dict[str, str] = {}
    order = sorted(pop)
    if limit:
        order = order[:limit]
    for sym in order:
        start = P._buffered_start(pop[sym])
        st, news = P.alpaca_symbol_history(sym, start, key, secret,
                                           opener=opener, sleep=sleep)
        status[sym] = "ok" if st == 200 else f"HTTP {st}"
        for n in news:
            syms = n.get("symbols") or [sym]
            rows.append({"symbol": sym, "headline": n.get("headline", ""),
                        "created_at": n.get("created_at", ""),
                        "symbol_count": len(syms)})
    return rows, status


def alpaca_pull_report(rows: list[dict], status: dict[str, str]) -> str:
    failed = {s: v for s, v in status.items() if v != "ok"}
    L = ["ALPACA/BENZINGA -- SWING-v0 PICKS PER-SYMBOL HEADLINE PULL", "",
        f"  symbols attempted     {len(status):,}",
        f"  headlines written     {len(rows):,}",
        f"  ok                    {sum(1 for v in status.values() if v == 'ok'):,}",
        f"  FAILED                {len(failed):,}", ""]
    if failed:
        L += ["FAILED", ""]
        for s, v in sorted(failed.items()):
            L.append(f"    {s:<8} {v}")
        L.append("")
    return "\n".join(L)


# --- csv ----------------------------------------------------------------------

def load_swing_headlines_csv(path: str = SWING_HEADLINES_CSV) -> dict[str, list[dict]]:
    """symbol -> its headline rows, as `news_swing_tag.headline_events`
    expects them (headline, created_at, symbol_count)."""
    out: dict[str, list[dict]] = {}
    p = Path(path)
    if not p.exists():
        return out
    import csv as _csv
    with p.open(newline="", encoding="utf-8") as fh:
        for r in _csv.DictReader(fh):
            out.setdefault(r["symbol"], []).append(
                {"headline": r["headline"], "created_at": r["created_at"],
                "symbol_count": r["symbol_count"]})
    return out


# --- cli ------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--picks-csv", default=DEFAULT_PICKS_CSV)
    p.add_argument("--coverage", action="store_true")
    p.add_argument("--pull-edgar", action="store_true")
    p.add_argument("--pull-alpaca", action="store_true")
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--cache", default=str(E.CACHE))
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--filings-out", default=SWING_FILINGS_CSV)
    p.add_argument("--headlines-out", default=SWING_HEADLINES_CSV)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    from common import secrets_util

    a = build_parser().parse_args(argv)
    if not (a.coverage or a.pull_edgar or a.pull_alpaca):
        a.coverage = True

    pop = swing_population(a.picks_csv)   # exits with a clear W07-0010 message if absent

    if a.coverage or a.pull_edgar:
        f = E.Fetcher(E.contact(), cache=Path(a.cache), refresh=a.refresh)
        tmap = E.ticker_map(f)
        cost = edgar_cost_section(pop, tmap)
        if a.coverage:
            emit("\n".join(cost), a.out or "var/reports/news_swing_pull_edgar_cost.txt")
        if a.pull_edgar:
            if not a.confirm:
                sys.exit("--pull-edgar needs --confirm (priced before pulled).\n\n"
                         + "\n".join(cost))
            rows, status = pull_edgar_for_swing(pop, f, tmap, limit=a.limit)
            P.write_csv(a.filings_out, P.FILING_COLS, rows)
            emit(P.edgar_pull_report(rows, status),
                a.out or "var/reports/news_swing_pull_edgar.txt",
                header=f"{len(rows):,} filings -> {a.filings_out}")

    if a.coverage or a.pull_alpaca:
        cost = alpaca_cost_section(pop)
        if a.coverage:
            emit("\n".join(cost), "var/reports/news_swing_pull_alpaca_cost.txt")
        if a.pull_alpaca:
            if not a.confirm:
                sys.exit("--pull-alpaca needs --confirm (priced before pulled).\n\n"
                         + "\n".join(cost))
            key = secrets_util.resolve("ALPACA_API_KEY_ID", "Alpaca key id")
            secret = secrets_util.resolve("ALPACA_API_SECRET_KEY", "Alpaca secret")
            if not (key and secret):
                sys.exit("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not resolvable.")
            rows, status = pull_alpaca_with_symbol_count(pop, key, secret, limit=a.limit)
            import csv as _csv
            pth = Path(a.headlines_out)
            pth.parent.mkdir(parents=True, exist_ok=True)
            with pth.open("w", newline="", encoding="utf-8") as fh:
                w = _csv.DictWriter(fh, fieldnames=list(SWING_HEADLINE_COLS))
                w.writeheader()
                w.writerows(rows)
            emit(alpaca_pull_report(rows, status),
                a.out or "var/reports/news_swing_pull_alpaca.txt",
                header=f"{len(rows):,} headlines -> {a.headlines_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
