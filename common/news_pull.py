#!/usr/bin/env python3
r"""G4 -- per-symbol EDGAR filing history and Alpaca/Benzinga headline
history, for every symbol in REGISTERED_news_events.md's §2.1 population
(chase_gate_trades.csv, book in {MCL, MC5} -- the same 10,370 entries, 1,578
symbols). Promotes the read-only probe (w03_0010_news_probe.py, subitem 2)
from a sample to a per-symbol, full-history pull, the input news_study.py
scores.

    $env:SEC_CONTACT = "you@example.com"
    $env:ALPACA_API_KEY_ID = "..."
    $env:ALPACA_API_SECRET_KEY = "..."
    python -m common.news_pull --coverage
    python -m common.news_pull --pull-edgar --confirm
    python -m common.news_pull --pull-alpaca --confirm

PRICED BEFORE PULLED (§0 G4)
-------------------------------
`--coverage` runs first and costs one request (the ticker map, already cached
by `common.edgar_shares` if that has run). It reports what a full pull of
EACH source would cost -- requests and wall clock -- and neither pull runs
without `--confirm`: the registration's own words are "if either prices above
$0 it stops for Ben," and this makes stopping the default rather than
something the CLI has to remember to do.

WHAT THIS PULLS AND WHAT IT DOES NOT
-------------------------------------
EDGAR: one `submissions` request per matched symbol, exactly the probe's own
endpoint (`common.news_pull.SEC_SUBMISSIONS`), reusing `edgar_shares.Fetcher`
so the pacing, the cache-records-absence convention, and the retry/backoff
are the same code this project already trusts -- not a second implementation
of the same rules. EVERY filing in `filings.recent` is written, not only the
ones `common.news_events.classify_filing` would flag: the filter can change
without a re-pull. `filings.recent` IS NOT THE COMPLETE HISTORY for a filer
who has filed more than SEC keeps in that block (WHLR's own 70-in-90-days
rate makes it a candidate) -- older filings live in `filings.files`, paginated,
and this module does not follow that pagination. The report says so for every
symbol whose recent block does not reach back to its earliest scored trade,
rather than silently truncating; that is `SYMBOL_HISTORY_CAVEAT` below.

Alpaca/Benzinga: every headline per symbol since its earliest scored trade
(a small buffer earlier, `HISTORY_BUFFER_DAYS`), oldest first, paged. Unlike
`edgar_shares.Fetcher`, headline pages are NOT cached to disk per request --
a re-run re-fetches. At the population's size (1,578 symbols) that is a
deliberate simplicity trade, not an oversight; a cache is the obvious next
step if this needs re-running often.

G2(d), CARRIED HERE. EDGAR's acceptanceDateTime is written to the filings CSV
exactly as SEC returns it (`common.news_events.parse_edgar_accepted` reads it
later); this module never reformats it, so the same clustering evidence that
motivated that function's docstring is preserved for Ben to eyeball against a
real pull, not just the probe's eight-symbol sample.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from common import edgar_shares as E
from common.report_io import emit

TRADES_CSV = "var/reports/chase_gate_trades.csv"
SCORED_BOOKS = ("MCL", "MC5")            # REGISTERED §2.1: the two baseline books

SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ALPACA_NEWS = "https://data.alpaca.markets/v1beta1/news"

FILINGS_CSV = "var/edgar/news_filings.csv"
HEADLINES_CSV = "var/news/alpaca_headlines.csv"

FILING_COLS = ("symbol", "form", "items", "accepted", "filed")
HEADLINE_COLS = ("symbol", "headline", "created_at")

# A pull starts this many days before a symbol's EARLIEST scored trade, so a
# trigger whose window (§3: 2 or 30 days) reaches back before the first
# trade is still measurable on that trade rather than silently absent.
HISTORY_BUFFER_DAYS = 35

ALPACA_PACE_S = 0.35     # Alpaca's free tier: 200 req/min; well under it


# --- the population, read from the study's own scored trades ----------------

def population_symbols(trades_csv: str = TRADES_CSV,
                       books=SCORED_BOOKS) -> dict[str, str]:
    """symbol -> its EARLIEST scored-trade date, from `chase_gate_trades.csv`
    filtered to `books`. This is the population §2.1 names, read from the
    file itself rather than re-derived, so a mismatch between this and the
    10,370/1,578 figures in the registration is a fact about the CSV having
    changed, not about two different counting rules."""
    p = Path(trades_csv)
    if not p.exists():
        sys.exit(f"{p} does not exist -- this is REGISTERED_news_events.md §2.1's "
                 f"population; run `python -m common.chase_gate` first.")
    earliest: dict[str, str] = {}
    with p.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("book") not in books:
                continue
            s, d = r["symbol"], r["date"]
            if s not in earliest or d < earliest[s]:
                earliest[s] = d
    if not earliest:
        sys.exit(f"{p} has no rows with book in {books} -- wrong file or wrong "
                 f"population.")
    return earliest


# --- EDGAR, reusing edgar_shares.Fetcher for the pacing/cache/retry rules ----

def interesting_filing_rows(sub: dict) -> list[dict]:
    """Every filing in a submissions payload's `filings.recent`, unfiltered.
    `common.news_events.classify_filing` decides what matters; this keeps
    the full history on disk once so that decision can change without a
    re-pull."""
    r = (sub or {}).get("filings", {}).get("recent", {})
    forms = r.get("form", [])
    n = len(forms)
    items_col = r.get("items") or [""] * n
    accepted_col = r.get("acceptanceDateTime") or [""] * n
    filed_col = r.get("filingDate") or [""] * n
    return [{"form": forms[i], "items": items_col[i] or "",
            "accepted": accepted_col[i] or "", "filed": filed_col[i] or ""}
           for i in range(n)]


def oldest_recent_filing_date(sub: dict) -> str:
    """The oldest `filingDate` in `filings.recent`, or '' if empty -- used to
    flag a symbol whose recent block does not reach back to its earliest
    scored trade (the §0 caveat this module's docstring names)."""
    rows = interesting_filing_rows(sub)
    dates = [r["filed"] for r in rows if r["filed"]]
    return min(dates) if dates else ""


def edgar_cost_section(pop: dict, tmap: dict) -> list[str]:
    matched = [s for s in pop if E.normalise(s) in tmap]
    n = len(matched)
    return ["EDGAR -- WHAT THE PULL WOULD COST", "",
           f"  population symbols    {len(pop):,}",
           f"  matched to a CIK      {n:,}",
           f"  requests              {n:,}   (one `submissions` GET per matched symbol)",
           f"  wall clock at {1 / E.MIN_INTERVAL:.1f}/s   {n * E.MIN_INTERVAL / 60:.0f} min",
           "",
           "  Cached on disk per symbol via edgar_shares.Fetcher, so an interrupted",
           "  run resumes and a re-run costs nothing for symbols already fetched.", ""]


def pull_edgar(pop: dict, f: E.Fetcher, tmap: dict,
              limit: int | None = None) -> tuple[list[dict], dict[str, str]]:
    """rows (FILING_COLS shape) and a per-symbol status."""
    rows: list[dict] = []
    status: dict[str, str] = {}
    order = sorted(pop)
    if limit:
        order = order[:limit]
    for sym in order:
        hit = tmap.get(E.normalise(sym))
        if not hit:
            status[sym] = "no_cik"
            continue
        cik, _name = hit
        sub, st = f.get(SEC_SUBMISSIONS.format(cik=cik), f"sub_{cik}")
        if sub is None:
            status[sym] = st
            continue
        oldest = oldest_recent_filing_date(sub)
        status[sym] = ("ok" if not oldest or oldest <= pop[sym]
                       else f"ok, but recent-block truncated (oldest {oldest} "
                            f"> earliest trade {pop[sym]})")
        for r in interesting_filing_rows(sub):
            rows.append(dict(r, symbol=sym))
    return rows, status


def edgar_pull_report(rows: list[dict], status: dict[str, str]) -> str:
    truncated = {s: v for s, v in status.items() if v.startswith("ok, but")}
    missing = {s: v for s, v in status.items() if v not in ("ok",) and s not in truncated}
    L = ["EDGAR -- PER-SYMBOL FILING PULL", "",
        f"  symbols attempted     {len(status):,}",
        f"  filings written       {len(rows):,}",
        f"  ok, full recent block {sum(1 for v in status.values() if v == 'ok'):,}",
        f"  ok, TRUNCATED         {len(truncated):,}", ""]
    if truncated:
        L += ["SYMBOL_HISTORY_CAVEAT: `filings.recent` does not reach the symbol's",
             "earliest scored trade for these -- a Trigger A/B window near that",
             "trade could be missing an earlier filing. Not followed into",
             "`filings.files` (§0 docstring). Reported, not silently dropped:", ""]
        for s, v in sorted(truncated.items()):
            L.append(f"    {s:<8} {v}")
        L.append("")
    if missing:
        L += ["NOT PULLED", ""]
        for s, v in sorted(missing.items()):
            L.append(f"    {s:<8} {v}")
        L.append("")
    return "\n".join(L)


# --- Alpaca/Benzinga, per symbol, full scored-window history ----------------

def alpaca_get(params: dict, key: str, secret: str, opener=None) -> tuple[int, dict]:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    req = urllib.request.Request(f"{ALPACA_NEWS}?{q}", headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"message": e.read().decode("utf-8", "replace")[:300]}


def alpaca_symbol_history(symbol: str, start: str, key: str, secret: str, *,
                          opener=None, max_pages: int = 2000,
                          sleep=time.sleep, pace_s: float = ALPACA_PACE_S
                          ) -> tuple[int, list[dict]]:
    """Every headline for ONE symbol since `start` (a date string), oldest
    first, paged. Returns (last HTTP status, rows). `max_pages` is a safety
    cap, not an expected count -- at 50/page it is 100,000 headlines."""
    token, rows, status = None, [], 200
    for _ in range(max_pages):
        status, body = alpaca_get({"symbols": symbol, "start": start, "limit": 50,
                                   "sort": "asc", "include_content": "false",
                                   "page_token": token}, key, secret, opener=opener)
        if status != 200:
            return status, rows
        rows += body.get("news", [])
        token = body.get("next_page_token")
        if not token:
            break
        sleep(pace_s)
    return status, rows


def alpaca_cost_section(pop: dict) -> list[str]:
    n = len(pop)
    return ["ALPACA/BENZINGA -- WHAT THE PULL WOULD COST", "",
           f"  population symbols    {n:,}",
           f"  requests              at least {n:,} (one page per symbol; a symbol",
           "                         with dense history pages further -- not "
           "predictable",
           "                         ahead of the pull, unlike EDGAR's fixed "
           "one-per-symbol)",
           f"  wall clock            at least {n * ALPACA_PACE_S / 60:.0f} min at "
           f"{ALPACA_PACE_S}s/page, single-threaded",
           "",
           "  NOT cached to disk per request -- a re-run re-fetches (module "
           "docstring).", ""]


def pull_alpaca(pop: dict, key: str, secret: str, *, limit: int | None = None,
                opener=None, sleep=time.sleep) -> tuple[list[dict], dict[str, str]]:
    rows: list[dict] = []
    status: dict[str, str] = {}
    order = sorted(pop)
    if limit:
        order = order[:limit]
    for sym in order:
        start = _buffered_start(pop[sym])
        st, news = alpaca_symbol_history(sym, start, key, secret,
                                         opener=opener, sleep=sleep)
        status[sym] = "ok" if st == 200 else f"HTTP {st}"
        for n in news:
            rows.append({"symbol": sym, "headline": n.get("headline", ""),
                        "created_at": n.get("created_at", "")})
    return rows, status


def _buffered_start(earliest_trade_date: str) -> str:
    """`earliest_trade_date` minus HISTORY_BUFFER_DAYS, as a date string --
    the pull's `start` parameter, so a trigger window reaching before the
    first scored trade is still covered."""
    from datetime import date, timedelta
    d = date.fromisoformat(earliest_trade_date) - timedelta(days=HISTORY_BUFFER_DAYS)
    return d.isoformat()


def alpaca_pull_report(rows: list[dict], status: dict[str, str]) -> str:
    failed = {s: v for s, v in status.items() if v != "ok"}
    L = ["ALPACA/BENZINGA -- PER-SYMBOL HEADLINE PULL", "",
        f"  symbols attempted     {len(status):,}",
        f"  headlines written     {len(rows):,}",
        f"  ok                    {sum(1 for v in status.values() if v == 'ok'):,}",
        f"  FAILED                {len(failed):,}", ""]
    if failed:
        L += ["FAILED, AND THEREFORE MISSING", "",
             "  Re-run to retry -- nothing here is cached, so a re-run refetches",
             "  everything, not only these.", ""]
        for s, v in sorted(failed.items()):
            L.append(f"    {s:<8} {v}")
        L.append("")
    return "\n".join(L)


# --- csv ----------------------------------------------------------------------------

def write_csv(path: str, cols, rows: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_filings_csv(path: str = FILINGS_CSV) -> dict[str, list[dict]]:
    """symbol -> its filing rows, as `common.news_events.events_from_filings`
    expects them. What `news_study.py` reads."""
    out: dict[str, list[dict]] = {}
    p = Path(path)
    if not p.exists():
        return out
    with p.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["symbol"], []).append(
                {"form": r["form"], "items": r["items"], "accepted": r["accepted"]})
    return out


def load_headlines_csv(path: str = HEADLINES_CSV) -> dict[str, list[dict]]:
    """symbol -> its headline rows, as `events_from_headlines` expects them."""
    out: dict[str, list[dict]] = {}
    p = Path(path)
    if not p.exists():
        return out
    with p.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["symbol"], []).append(
                {"headline": r["headline"], "created_at": r["created_at"]})
    return out


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--trades-csv", default=TRADES_CSV)
    p.add_argument("--coverage", action="store_true",
                   help="one request: cost both pulls would carry, then stop")
    p.add_argument("--pull-edgar", action="store_true")
    p.add_argument("--pull-alpaca", action="store_true")
    p.add_argument("--confirm", action="store_true",
                   help="required for --pull-edgar / --pull-alpaca to actually run "
                        "(§0 G4: priced before pulled)")
    p.add_argument("--limit", type=int, default=None,
                   help="stop after N symbols -- for a costed trial run")
    p.add_argument("--cache", default=str(E.CACHE))
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--filings-out", default=FILINGS_CSV)
    p.add_argument("--headlines-out", default=HEADLINES_CSV)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    from common import secrets_util

    a = build_parser().parse_args(argv)
    if not (a.coverage or a.pull_edgar or a.pull_alpaca):
        a.coverage = True

    pop = population_symbols(a.trades_csv)

    if a.coverage or a.pull_edgar:
        f = E.Fetcher(E.contact(), cache=Path(a.cache), refresh=a.refresh)
        tmap = E.ticker_map(f)
        cost = edgar_cost_section(pop, tmap)
        if a.coverage:
            emit("\n".join(cost), a.out or "var/reports/news_pull_edgar_cost.txt")
        if a.pull_edgar:
            if not a.confirm:
                sys.exit("--pull-edgar needs --confirm (§0 G4: priced before "
                         "pulled).\n\n" + "\n".join(cost))
            rows, status = pull_edgar(pop, f, tmap, limit=a.limit)
            write_csv(a.filings_out, FILING_COLS, rows)
            emit(edgar_pull_report(rows, status),
                a.out or "var/reports/news_pull_edgar.txt",
                header=f"{len(rows):,} filings -> {a.filings_out}")

    if a.coverage or a.pull_alpaca:
        cost = alpaca_cost_section(pop)
        if a.coverage:
            emit("\n".join(cost), "var/reports/news_pull_alpaca_cost.txt")
        if a.pull_alpaca:
            if not a.confirm:
                sys.exit("--pull-alpaca needs --confirm (§0 G4: priced before "
                         "pulled).\n\n" + "\n".join(cost))
            key = secrets_util.resolve("ALPACA_API_KEY_ID", "Alpaca key id")
            secret = secrets_util.resolve("ALPACA_API_SECRET_KEY", "Alpaca secret")
            if not (key and secret):
                sys.exit("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not resolvable.")
            rows, status = pull_alpaca(pop, key, secret, limit=a.limit)
            write_csv(a.headlines_out, HEADLINE_COLS, rows)
            emit(alpaca_pull_report(rows, status),
                a.out or "var/reports/news_pull_alpaca.txt",
                header=f"{len(rows):,} headlines -> {a.headlines_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
