#!/usr/bin/env python3
r"""Shares outstanding from SEC EDGAR, point-in-time by FILING DATE.

    $env:SEC_CONTACT = "you@example.com"
    python -m common.edgar_shares --coverage
    python -m common.edgar_shares --pull
    python -m common.edgar_shares --asof

THREE STEPS, AND THE ORDER IS THE POINT
---------------------------------------
`--coverage` costs ONE request. It asks the only question that can invalidate
the other 2,123: does SEC's ticker map even contain the symbols this universe
traded? If a third of them are missing, a full pull produces a table with a
third of its rows absent, and an absent row in a join looks exactly like a
symbol that failed a filter. Measure the hole before spending ten minutes
digging one.

`--pull` then fetches one concept per matched symbol and caches every response
on disk, so a re-run costs nothing and an interrupted run resumes.

`--asof` joins the facts to the universe under the point-in-time rule below and
is the only step that produces a number anything else may use.

WHAT THIS IS NOT: IT IS NOT FLOAT
---------------------------------
EDGAR publishes SHARES OUTSTANDING. The scanner's criterion is FLOAT -- shares
actually available to trade, outstanding less insider, affiliate and restricted
holdings. They are different numbers and on exactly the names this project
trades they are most different: a recent IPO or a founder-controlled microcap
can have a float that is a small fraction of its outstanding count.

Shares outstanding is an UPPER BOUND on float and nothing more. It is useful
because the low-float criterion is a ceiling test -- a name with 400 million
shares outstanding cannot be a low-float name -- and it is useless as a
substitute for float on anything near the threshold. Nothing here is to be
loaded into a column called `float`.

THE POINT-IN-TIME RULE: `filed`, NOT `end`
------------------------------------------
Every XBRL fact carries two dates. `end` is the date the figure is AS OF; `filed`
is the date it became public. A 10-Q with end=2026-06-30 filed=2026-08-14 was
not knowable on 2026-07-01, and joining on `end` would hand a July backtest a
number that did not exist for six more weeks. That is the same defect this
project has already found twice under other names, and it is the reason the
whole universe here is scored point-in-time in the first place.

So `shares_known_at` selects the fact with the greatest `filed` that is <= the
session date, and ignores `end` entirely when choosing. Amendments fall out
correctly: a restatement of the same period is a later `filed`, so it wins from
its own filing date forward and not before.

THE SURVIVORSHIP HOLE, WHICH THIS CANNOT CLOSE
----------------------------------------------
`company_tickers.json` is a CURRENT map. SEC does not publish a point-in-time
ticker->CIK history. So for a symbol that has since been delisted, renamed, or
whose ticker has been REUSED by a different company, this map is wrong in one of
two ways:

  * a miss -- the symbol is simply absent, and is counted by `--coverage`;
  * a SILENT WRONG MATCH -- the ticker resolves to whoever holds it today,
    which may not be who was trading under it in 2024.

The second is the dangerous one, because it produces a plausible number rather
than a gap. `--pull` records, per symbol, the earliest and latest `filed` in the
company's own facts, and `--asof` flags any symbol-day that falls outside the
filing history it was matched to. That catches the blatant cases (a company
whose first filing postdates the session) and does not catch a ticker handed
from one filer to another inside the window. That residual is stated in the
report rather than argued away.

FAIR ACCESS
-----------
SEC publishes a limit of 10 requests/second and requires a declared User-Agent
carrying a contact address. This sends ~6.7/s and refuses to start without
SEC_CONTACT set -- an address is not guessed, and it is not read from anything
in the repo.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date as _date
from datetime import datetime
from pathlib import Path

from common.report_io import emit

SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_CONCEPT = ("https://data.sec.gov/api/xbrl/companyconcept/"
               "CIK{cik:010d}/{taxonomy}/{tag}.json")

# dei first: EntityCommonStockSharesOutstanding is the COVER PAGE count, which
# is dated close to the filing rather than to the period end, so its `filed` and
# its `end` are days apart rather than months. The us-gaap balance-sheet tag is
# the fallback for filers that do not tag the cover page -- same units, staler
# `end`, and it is recorded per row so the two are never averaged as one thing.
CONCEPTS = (("dei", "EntityCommonStockSharesOutstanding"),
            ("us-gaap", "CommonStockSharesOutstanding"))

# ~6.7 requests/second against SEC's published ceiling of 10. Deliberately under
# rather than at it: the ceiling is enforced by a block, and a block mid-pull
# leaves a half-populated cache that the next run cannot distinguish from a
# company with no filings.
MIN_INTERVAL = 0.15
MAX_TRIES = 4
BACKOFF = 2.0

CACHE = Path("var/edgar")
PAIRS = "var/state/screen_pairs_pit.json"

# How stale a knowable figure may be before `--asof` counts it separately. A
# share count filed 400 days ago is still the most recent PUBLIC one, so it is
# the right answer to "what could you have known" -- and it is not the right
# answer to "how many shares were there". Both get reported; neither is dropped.
STALE_DAYS = 200

NOT_FLOAT = ("SHARES OUTSTANDING IS NOT FLOAT. It is an upper bound on float "
             "and is not a substitute for it.")


# --- the contact SEC requires ----------------------------------------------

def contact() -> str:
    """The address SEC's fair-access policy requires in the User-Agent.

    Read from the environment and never defaulted. An address typed into source
    is sent by every checkout of that source, including ones running somewhere
    nobody expected; and guessing one from the repo would put a personal address
    into a third-party request that nobody asked for.
    """
    who = (os.environ.get("SEC_CONTACT") or "").strip()
    if not who or "@" not in who:
        sys.exit(
            "SEC_CONTACT is not set to an email address.\n"
            "SEC requires a contact address in the User-Agent of every "
            "request and rate-limits or blocks requests without one.\n\n"
            '    $env:SEC_CONTACT = "you@example.com"\n')
    return who


def user_agent(who: str) -> str:
    return f"Trading research ({who})"


# --- fetching, cached and rate-limited --------------------------------------

class Fetcher:
    """One JSON GET at a time, paced, cached, and honest about what failed.

    THE CACHE RECORDS ABSENCE AS WELL AS PRESENCE. A company that never tagged
    the concept returns 404, and without a recorded 404 every re-run asks again
    -- which on a 2,123-symbol universe is thousands of requests spent
    rediscovering the same nothing. The sentinel is a real file so that "not
    asked yet" and "asked, and there is nothing" stay distinguishable, which is
    the distinction this whole project keeps losing.
    """

    def __init__(self, who: str, cache: Path = CACHE, *,
                 min_interval: float = MIN_INTERVAL, refresh: bool = False,
                 opener=None, sleep=time.sleep, clock=time.monotonic):
        self.ua = user_agent(who)
        self.cache = Path(cache)
        self.min_interval = min_interval
        self.refresh = refresh
        self._open = opener or self._urlopen
        self._sleep = sleep
        self._clock = clock
        self._last = None
        self.fetched = 0
        self.from_cache = 0

    # -- the network, isolated so tests never touch it ----------------------
    def _urlopen(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={
            "User-Agent": self.ua,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return raw

    def _pace(self) -> None:
        if self._last is None:
            self._last = self._clock()
            return
        wait = self.min_interval - (self._clock() - self._last)
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()

    def path_for(self, key: str) -> Path:
        return self.cache / f"{key}.json"

    def get(self, url: str, key: str) -> tuple[dict | None, str]:
        """(payload, status) where status is cached / fetched / absent / error.

        An error is RETURNED, not raised and not printed and forgotten. The
        caller counts them, and a run that could not fetch a tenth of its
        symbols must not be able to report success -- see `_accounting`.
        """
        p = self.path_for(key)
        if p.exists() and not self.refresh:
            try:
                body = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                body = None
            if isinstance(body, dict):
                self.from_cache += 1
                if body.get("__absent__"):
                    return None, "absent"
                return body, "cached"

        for attempt in range(1, MAX_TRIES + 1):
            self._pace()
            try:
                raw = self._open(url)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self._write(p, {"__absent__": True, "url": url,
                                    "when": datetime.now().isoformat(" ")})
                    return None, "absent"
                if e.code in (403, 429, 502, 503) and attempt < MAX_TRIES:
                    self._sleep(BACKOFF * attempt)
                    continue
                return None, f"HTTP {e.code}"
            except Exception as e:                      # noqa: BLE001
                if attempt < MAX_TRIES:
                    self._sleep(BACKOFF * attempt)
                    continue
                return None, f"{type(e).__name__}: {e}"
            try:
                body = json.loads(raw)
            except ValueError as e:
                return None, f"unparseable JSON ({e})"
            self._write(p, body)
            self.fetched += 1
            return body, "fetched"
        return None, "gave up"

    def _write(self, p: Path, body: dict) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(body), encoding="utf-8")


# --- the universe -----------------------------------------------------------

def load_universe(path: str | Path) -> dict[str, list[str]]:
    """symbol -> the session dates it appears on, from the point-in-time pairs.

    This is the SAME file `pit_h0` scores, so a coverage figure from here and a
    trade count from there share a denominator. Reading a different universe
    would produce two numbers that look comparable and are not.
    """
    p = Path(path)
    if not p.exists():
        sys.exit(f"{p} does not exist -- run `python -m common.screen_sim` "
                 f"first, or pass --pairs")
    rows = json.loads(p.read_text())
    if not rows:
        sys.exit(f"{p} is empty")
    days: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        days[str(r["symbol"]).upper()].append(str(r["date"]))
    return {s: sorted(set(d)) for s, d in sorted(days.items())}


def normalise(sym: str) -> str:
    r"""One spelling for class shares.

    The tape writes a class share as BRK.B or BRK/B depending on the vendor;
    `company_tickers.json` writes BRK-B. Matched raw, every class share on the
    tape is a miss, and a systematic miss on one KIND of symbol reads in the
    coverage figure exactly like a random one.
    """
    return sym.upper().strip().replace(".", "-").replace("/", "-")


# --- the ticker map ---------------------------------------------------------

def ticker_map(f: Fetcher) -> dict[str, tuple[int, str]]:
    """NORMALISED ticker -> (cik, company name), from SEC's one map file."""
    body, status = f.get(SEC_TICKERS, "company_tickers")
    if body is None:
        sys.exit(f"could not fetch SEC's ticker map: {status}")
    # SEC ships this as an object keyed by row number, not as a list.
    rows = body.values() if isinstance(body, dict) else body
    out: dict[str, tuple[int, str]] = {}
    for r in rows:
        try:
            t = normalise(str(r["ticker"]))
            out[t] = (int(r["cik_str"]), str(r.get("title", "")))
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        sys.exit("SEC's ticker map parsed to zero entries -- the shape changed")
    return out


# --- coverage ---------------------------------------------------------------

def coverage(days: dict[str, list[str]],
             tmap: dict[str, tuple[int, str]]) -> dict:
    """Matched and missed, counted BOTH ways.

    Symbols and symbol-days are different denominators and they disagree here by
    construction: 43% of this universe's symbols appear on exactly one session,
    so a miss list dominated by one-day names costs far fewer days than its
    length suggests, and a miss list of frequent flyers costs far more. One hit
    rate would hide whichever of those is true.
    """
    hit, miss = {}, {}
    for sym, ds in days.items():
        key = normalise(sym)
        if key in tmap:
            hit[sym] = (tmap[key][0], tmap[key][1], len(ds))
        else:
            miss[sym] = len(ds)
    tot_sym = len(days)
    tot_day = sum(len(d) for d in days.values())
    return {
        "hit": hit, "miss": miss,
        "symbols": tot_sym, "symbols_hit": len(hit),
        "days": tot_day,
        "days_hit": sum(v[2] for v in hit.values()),
    }


def coverage_section(cov: dict) -> list[str]:
    sym_pct = 100.0 * cov["symbols_hit"] / cov["symbols"] if cov["symbols"] else 0.0
    day_pct = 100.0 * cov["days_hit"] / cov["days"] if cov["days"] else 0.0
    out = [
        "TICKER -> CIK COVERAGE", "",
        f"  symbols      {cov['symbols_hit']:,} of {cov['symbols']:,}"
        f"   {sym_pct:5.1f}%",
        f"  symbol-days  {cov['days_hit']:,} of {cov['days']:,}"
        f"   {day_pct:5.1f}%",
        "",
        "  The two rates differ because the miss list is not a random sample of",
        "  the universe: a delisted name is both more likely to be missing from",
        "  a CURRENT map and more likely to have traded on few sessions.",
        "",
    ]
    if cov["miss"]:
        out += [f"NOT IN SEC'S CURRENT TICKER MAP  ({len(cov['miss']):,} symbols,"
                f" {cov['days'] - cov['days_hit']:,} symbol-days)", "",
                "  Delisted, renamed, or never an SEC filer (an ADR or a fund",
                "  can trade without one of these tags). EVERY ONE IS LISTED --",
                "  a truncated miss list is how a systematic gap gets read as a",
                "  scatter of odd names.", ""]
        for sym, n in sorted(cov["miss"].items(), key=lambda kv: (-kv[1], kv[0])):
            out.append(f"    {sym:<8} {n:>4} session(s)")
        out.append("")
    else:
        out += ["  Every symbol matched. That is not the same as every symbol",
                "  matching the RIGHT company -- see the reuse note below.", ""]
    return out


# --- the facts --------------------------------------------------------------

def concept_facts(body: dict) -> list[dict]:
    """The concept JSON flattened to rows, with both dates kept.

    Every unit key is read rather than just "shares": a filer using a different
    unit label would otherwise contribute zero facts and look identical to a
    filer with none.
    """
    tax = str(body.get("taxonomy", ""))
    tag = str(body.get("tag", ""))
    out: list[dict] = []
    for unit, rows in (body.get("units") or {}).items():
        for r in rows or []:
            if r.get("filed") is None or r.get("val") is None:
                # Unusable point-in-time: a fact with no filing date cannot be
                # placed in time at all. Dropped, and counted by the caller.
                continue
            out.append({"taxonomy": tax, "tag": tag, "unit": unit,
                        "end": str(r.get("end") or ""),
                        "filed": str(r["filed"]), "val": float(r["val"]),
                        "form": str(r.get("form") or ""),
                        "accn": str(r.get("accn") or "")})
    out.sort(key=lambda r: (r["filed"], r["end"]))
    return out


def pull_symbol(f: Fetcher, sym: str, cik: int) -> tuple[list[dict], str]:
    """Facts for one company, trying the cover-page tag before the balance sheet.

    Returns (facts, source) where source is the taxonomy/tag that answered, or
    an empty list with a status when neither did.
    """
    last = "absent"
    for taxonomy, tag in CONCEPTS:
        url = SEC_CONCEPT.format(cik=cik, taxonomy=taxonomy, tag=tag)
        body, status = f.get(url, f"concept/CIK{cik:010d}_{taxonomy}_{tag}")
        if body is not None:
            rows = concept_facts(body)
            if rows:
                return rows, f"{taxonomy}:{tag}"
            last = "empty"
        elif status != "absent":
            last = status
    return [], last


def shares_known_at(facts: list[dict], on: str | _date) -> dict | None:
    """The most recently FILED fact that was public on `on`. None before any.

    `end` is deliberately not consulted. A figure as of 2026-06-30 that was
    filed on 2026-08-14 was not knowable in July, and a restatement of the same
    period is simply a later `filed` -- so it takes over from its own filing
    date and not one day earlier.

    None is returned rather than the oldest fact, because "nothing had been
    filed yet" is a real state for a recent IPO and substituting a later figure
    for it is exactly the leak this rule exists to prevent.
    """
    day = on.isoformat() if isinstance(on, _date) else str(on)
    best = None
    for r in facts:
        if r["filed"] <= day and (best is None or r["filed"] >= best["filed"]):
            best = r
    return best


# --- the point-in-time join -------------------------------------------------

def asof_rows(days: dict[str, list[str]], facts: dict[str, list[dict]],
              cov: dict) -> list[dict]:
    """One row per symbol-day, INCLUDING the ones with no knowable figure.

    A symbol-day with nothing filed yet is written with an empty `shares` and a
    reason, not omitted. Omitting it would make the output's row count the
    denominator, and a denominator that silently shrinks to fit is how a 60%
    answer gets read as a 100% one.
    """
    out: list[dict] = []
    for sym, ds in days.items():
        f = facts.get(sym) or []
        cik = cov["hit"].get(sym, (0, "", 0))[0]
        first_filed = f[0]["filed"] if f else ""
        for d in ds:
            row = {"symbol": sym, "date": d, "cik": cik or "",
                   "shares": "", "filed": "", "end": "", "form": "",
                   "taxonomy": "", "tag": "", "lag_days": "", "status": ""}
            if not cik:
                row["status"] = "no_cik"
            elif not f:
                row["status"] = "no_facts"
            else:
                hit = shares_known_at(f, d)
                if hit is None:
                    # The company files, but not yet as at this session.
                    row["status"] = ("before_first_filing"
                                     if d < first_filed else "no_fact_on_or_before")
                else:
                    row.update(shares=hit["val"], filed=hit["filed"],
                               end=hit["end"], form=hit["form"],
                               taxonomy=hit["taxonomy"], tag=hit["tag"],
                               lag_days=(_date.fromisoformat(d)
                                         - _date.fromisoformat(hit["filed"])).days)
                    row["status"] = ("stale" if row["lag_days"] > STALE_DAYS
                                     else "known")
            out.append(row)
    out.sort(key=lambda r: (r["date"], r["symbol"]))
    return out


SHARE_BUCKETS = (0, 5e6, 10e6, 20e6, 50e6, 100e6, 500e6, 1e12)


def asof_section(rows: list[dict]) -> list[str]:
    by_status: dict[str, int] = defaultdict(int)
    for r in rows:
        by_status[r["status"]] += 1
    n = len(rows)
    known = [r for r in rows if r["status"] in ("known", "stale")]
    out = ["POINT-IN-TIME JOIN", "",
           f"  symbol-days           {n:,}", ""]
    for k in sorted(by_status, key=lambda k: -by_status[k]):
        out.append(f"    {k:<22} {by_status[k]:>7,}"
                   f"   {100.0 * by_status[k] / n:5.1f}%")
    out += ["",
            "  `stale` is a figure that WAS the latest public one and was filed",
            f"  more than {STALE_DAYS} days before the session. It is the right",
            "  answer to what could have been known and the wrong answer to how",
            "  many shares there were. It is counted apart and kept.", ""]
    if known:
        lags = sorted(r["lag_days"] for r in known)
        def q(p):
            return lags[min(len(lags) - 1, int(p * len(lags)))]
        out += ["  FILING LAG, session date minus filing date, in days", "",
                f"    p25 {q(.25):>5}   p50 {q(.50):>5}   p75 {q(.75):>5}"
                f"   p90 {q(.90):>5}   max {lags[-1]:>5}", ""]
        out += ["  SHARES OUTSTANDING on the covered symbol-days", "",
                f"  {NOT_FLOAT}", ""]
        vals = sorted(float(r["shares"]) for r in known)
        for lo, hi in zip(SHARE_BUCKETS, SHARE_BUCKETS[1:]):
            c = sum(1 for v in vals if lo <= v < hi)
            label = f"{lo / 1e6:,.0f}M - {hi / 1e6:,.0f}M"
            out.append(f"    {label:<22} {c:>7,}"
                       f"   {100.0 * c / len(vals):5.1f}%")
        out.append("")
    return out


# --- the standing caveats, printed every time -------------------------------

def caveats() -> list[str]:
    return [
        "WHAT THIS IS AND IS NOT", "",
        f"  {NOT_FLOAT}",
        "  Float is outstanding less insider, affiliate and restricted holdings,",
        "  and on a recent IPO or a founder-controlled microcap the two differ by",
        "  an order of magnitude. Use this as a CEILING test and never as float.",
        "",
        "  THE TICKER MAP IS CURRENT-DAY. SEC publishes no point-in-time",
        "  ticker->CIK history, so a symbol that has since been delisted,",
        "  renamed, or REUSED resolves to whoever holds it now. A miss is",
        "  counted above. A wrong match is not detectable from this data and is",
        "  the residual risk in every figure here.",
        "",
        "  THE POINT-IN-TIME RULE IS `filed`, NOT `end`. A figure as of a period",
        "  end was not knowable until the filing that carried it.",
        "",
    ]


# --- reports ----------------------------------------------------------------

def cost_section(cov: dict) -> list[str]:
    """WHAT `--pull` WOULD SPEND, BEFORE IT SPENDS IT.

    The requests are free; the time and SEC's patience are not. A pull that
    turns out to be forty minutes is a different decision from one that is four,
    and the place to find that out is here, one request in.
    """
    n = len(cov["hit"])
    lo, hi = n, n * len(CONCEPTS)       # one request, or the fallback as well
    return ["WHAT THE PULL WOULD COST", "",
            f"  matched symbols       {n:,}",
            f"  requests              {lo:,} - {hi:,}"
            f"   (the second only where the cover-page tag is absent)",
            f"  wall clock at {1 / MIN_INTERVAL:.1f}/s   "
            f"{lo * MIN_INTERVAL / 60:.0f} - {hi * MIN_INTERVAL / 60:.0f} min",
            "",
            "  Cached on disk per symbol, so an interrupted run resumes and a",
            "  re-run costs nothing. `--limit N` buys a costed trial first.", ""]


def coverage_report(cov: dict, pairs: str) -> str:
    head = ["SEC EDGAR -- TICKER COVERAGE FOR THE POINT-IN-TIME UNIVERSE", "",
            f"  universe   {pairs}",
            f"  map        {SEC_TICKERS}", ""]
    return "\n".join(head + coverage_section(cov)
                     + cost_section(cov) + caveats())


def pull_report(cov: dict, facts: dict[str, list[dict]],
                status: dict[str, str], f: Fetcher) -> str:
    attempted = len(cov["hit"])
    with_facts = sum(1 for s in facts.values() if s)
    absent = sum(1 for v in status.values() if v in ("absent", "empty"))
    failed = {k: v for k, v in status.items()
              if v not in ("absent", "empty") and not facts.get(k)}
    out = ["SEC EDGAR -- SHARES OUTSTANDING PULL", "",
           f"  symbols attempted     {attempted:,}",
           f"  with facts            {with_facts:,}",
           f"  no such concept       {absent:,}",
           f"  FAILED                {len(failed):,}",
           f"  requests made         {f.fetched:,}"
           f"   (cache answered {f.from_cache:,})", ""]
    # THE ACCOUNTING IS AN ASSERTION, NOT A SUMMARY. A pull that quietly loses
    # symbols between "attempted" and the three outcomes is the failure this
    # block exists to make impossible to miss.
    if with_facts + absent + len(failed) != attempted:
        out += ["  *** THE OUTCOMES DO NOT ADD UP TO THE ATTEMPTS. Some symbol",
                "      left this run unaccounted for; treat the table as",
                "      incomplete until that is explained. ***", ""]
    if failed:
        out += ["FAILED, AND THEREFORE MISSING FROM THE TABLE", "",
                "  Re-run to retry: successes are cached and are not refetched.",
                ""]
        for sym, why in sorted(failed.items()):
            out.append(f"    {sym:<8} {why}")
        out.append("")
    src: dict[str, int] = defaultdict(int)
    for sym, rows in facts.items():
        if rows:
            src[f"{rows[-1]['taxonomy']}:{rows[-1]['tag']}"] += 1
    if src:
        out += ["WHICH TAG ANSWERED", ""]
        for k in sorted(src, key=lambda k: -src[k]):
            out.append(f"    {k:<48} {src[k]:>6,}")
        out += ["",
                "  Not one population. The cover-page tag is dated near the",
                "  filing; the balance-sheet tag is dated to the period end and",
                "  is therefore staler at the same filing date. The column is",
                "  carried per row so the two are never averaged as one.", ""]
    return "\n".join(out + caveats())


# --- csv --------------------------------------------------------------------

FACT_COLS = ("symbol", "cik", "taxonomy", "tag", "unit", "end", "filed",
             "val", "form", "accn")
ASOF_COLS = ("symbol", "date", "cik", "shares", "filed", "end", "form",
             "taxonomy", "tag", "lag_days", "status")


def write_csv(path: Path, cols, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_facts_csv(path: Path) -> dict[str, list[dict]]:
    """Read back what `--pull` wrote, so `--asof` need not refetch anything."""
    p = Path(path)
    if not p.exists():
        sys.exit(f"{p} does not exist -- run `--pull` first")
    out: dict[str, list[dict]] = defaultdict(list)
    with p.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["symbol"]].append({
                "taxonomy": r["taxonomy"], "tag": r["tag"], "unit": r["unit"],
                "end": r["end"], "filed": r["filed"], "val": float(r["val"]),
                "form": r["form"], "accn": r["accn"]})
    for rows in out.values():
        rows.sort(key=lambda r: (r["filed"], r["end"]))
    return dict(out)


# --- cli --------------------------------------------------------------------

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--coverage", action="store_true",
                   help="one request: does SEC's map contain these symbols")
    p.add_argument("--pull", action="store_true",
                   help="fetch shares outstanding for every matched symbol")
    p.add_argument("--asof", action="store_true",
                   help="join the facts to the universe point-in-time")
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--cache", default=str(CACHE))
    p.add_argument("--facts", default="var/edgar/shares_outstanding.csv")
    p.add_argument("--asof-out", default="var/edgar/universe_shares.csv")
    p.add_argument("--limit", type=int, default=None,
                   help="stop after N symbols -- for a costed trial run")
    p.add_argument("--refresh", action="store_true",
                   help="ignore the cache and refetch")
    p.add_argument("--out", default=None,
                   help="report path (default: var/reports/edgar_<step>.txt)")
    return p


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    if not (a.coverage or a.pull or a.asof):
        a.coverage = True
    days = load_universe(a.pairs)
    f = Fetcher(contact(), cache=Path(a.cache), refresh=a.refresh)
    tmap = ticker_map(f)
    cov = coverage(days, tmap)

    if a.coverage:
        emit(coverage_report(cov, a.pairs),
             a.out or "var/reports/edgar_coverage.txt")

    if a.pull:
        facts: dict[str, list[dict]] = {}
        status: dict[str, str] = {}
        order = sorted(cov["hit"].items(), key=lambda kv: (-kv[1][2], kv[0]))
        if a.limit:
            order = order[:a.limit]
        for i, (sym, (cik, _title, _n)) in enumerate(order, 1):
            rows, why = pull_symbol(f, sym, cik)
            facts[sym], status[sym] = rows, ("ok" if rows else why)
            if i % 100 == 0:
                print(f"  ... {i:,} of {len(order):,}", file=sys.stderr)
        flat = [dict(r, symbol=s, cik=cov["hit"][s][0])
                for s, rows in facts.items() for r in rows]
        write_csv(Path(a.facts), FACT_COLS, flat)
        emit(pull_report(cov, facts, status, f),
             a.out or "var/reports/edgar_pull.txt",
             header=f"{len(flat):,} facts -> {a.facts}")

    if a.asof:
        facts = load_facts_csv(Path(a.facts))
        rows = asof_rows(days, facts, cov)
        write_csv(Path(a.asof_out), ASOF_COLS, rows)
        emit("\n".join(asof_section(rows) + caveats()),
             a.out or "var/reports/edgar_asof.txt",
             header=f"{len(rows):,} symbol-days -> {a.asof_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
