"""Fundamentals from SEC EDGAR "company facts" (keyless, free).

Why EDGAR and not Yahoo: the filings ARE the source, and the desk then does not
depend on a scraper that breaks. SEC asks for a declared User-Agent with a
contact address and at most 10 requests/second; this refuses to run without
SEC_CONTACT set (same convention as common/edgar_shares.py) and sends well under
the cap.

What it produces is deliberately small -- a few compact tables -- because every
line of it is read by an LLM and paid for in Pro usage.
"""
from __future__ import annotations

import gzip
import json
import os
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
MIN_GAP_S = 0.2

TAX = ("us-gaap", "ifrs-full")

# (label, concepts in order of preference, kind, unit prefix)
#   kind: "flow" = a period total (quarterly/annual); "instant" = a balance on a date
CONCEPTS = [
    ("Revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                 "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "Revenue"], "flow", "USD"),
    ("Gross profit", ["GrossProfit"], "flow", "USD"),
    ("Operating income", ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"], "flow", "USD"),
    ("Net income", ["NetIncomeLoss", "ProfitLoss", "ProfitLossAttributableToOwnersOfParent"], "flow", "USD"),
    ("EPS diluted ($)", ["EarningsPerShareDiluted", "DilutedEarningsLossPerShare"], "flow", "USD/"),
    ("Operating cash flow", ["NetCashProvidedByUsedInOperatingActivities",
                              "CashFlowsFromUsedInOperatingActivities"], "flow", "USD"),
    ("Capex", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
               "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"], "flow", "USD"),
    ("Cash", ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"], "instant", "USD"),
    ("Total assets", ["Assets"], "instant", "USD"),
    ("Total liabilities", ["Liabilities"], "instant", "USD"),
    ("Equity", ["StockholdersEquity", "Equity"], "instant", "USD"),
    # Total debt where the filer reports it (LongTermDebt and DebtAndCapitalLeaseObligations include the current
    # portion), else the non-current part. The concept actually used is printed under the tables.
    ("Debt", ["LongTermDebt", "DebtAndCapitalLeaseObligations", "DebtLongtermAndShorttermCombinedAmount",
              "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtNoncurrent",
              "NoncurrentPortionOfNoncurrentBondsIssued", "NoncurrentPortionOfNoncurrentLoansReceived"],
     "instant", "USD"),
]

# A concept whose newest figure ends more than this long before the run date is out of date (filers switch
# concepts: MPC's "Revenues" stops in 2019 and "LongTermDebt" in 2012). 550 days still keeps an annual-only
# 20-F filer's last fiscal year (up to ~16 months old before the next annual report).
STALE_DAYS = 550


class FundamentalsError(RuntimeError):
    pass


# ----------------------------------------------------------------- fetching

def _get_json(url: str, user_agent: str, _opener=None):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"})
    opener = _opener or urllib.request.urlopen
    with opener(req, timeout=30) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _cached(path: Path, max_age: timedelta, fetch):
    if path.exists() and datetime.now() - datetime.fromtimestamp(path.stat().st_mtime) < max_age:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)
    time.sleep(MIN_GAP_S)
    return data


def cik_for(ticker: str, ticker_map: dict) -> tuple[int, str]:
    for row in ticker_map.values():
        if str(row.get("ticker", "")).upper() == ticker.upper():
            return int(row["cik_str"]), str(row.get("title", ""))
    raise FundamentalsError(f"{ticker} is not in SEC's ticker map")


def fetch_facts(ticker: str, cache_dir: Path, user_agent_env: str = "SEC_CONTACT", _opener=None) -> tuple[dict, str]:
    contact = os.environ.get(user_agent_env, "").strip()
    if not contact:
        raise FundamentalsError(
            f"{user_agent_env} is not set. SEC requires a contact address in the User-Agent. "
            f'PowerShell:  $env:{user_agent_env} = "you@example.com"')
    ua = f"BenTradingResearch {contact}"
    tmap = _cached(cache_dir / "company_tickers.json", timedelta(days=7),
                   lambda: _get_json(TICKER_MAP_URL, ua, _opener))
    cik, title = cik_for(ticker, tmap)
    facts = _cached(cache_dir / f"companyfacts_{cik:010d}.json", timedelta(days=1),
                    lambda: _get_json(FACTS_URL.format(cik=cik), ua, _opener))
    return facts, title


# ------------------------------------------------------------- summarising

def _d(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _latest_end(arr: list[dict], asof: date):
    ends = []
    for e in arr:
        try:
            if _d(e["filed"]) <= asof:
                ends.append(_d(e["end"]))
        except (KeyError, ValueError, TypeError):
            continue
    return max(ends) if ends else None


def _pick(facts: dict, concepts: list[str], unit_prefix: str, asof: date):
    """The concept with the NEWEST figure filed by `asof` (ties: the earlier one in `concepts`).
    -> (concept, unit, facts, latest end) or (None, None, [], None).
    Picking the first concept that merely exists used MPC's 2019 "Revenues" and 2012 "LongTermDebt"."""
    best = None
    for tax in TAX:
        node_tax = facts.get("facts", {}).get(tax, {})
        for c in concepts:
            node = node_tax.get(c)
            if not node:
                continue
            for unit, arr in node.get("units", {}).items():
                if unit.startswith(unit_prefix):
                    le = _latest_end(arr, asof)
                    if le is not None and (best is None or le > best[3]):
                        best = (c, unit, arr, le)
                    break
    return best if best else (None, None, [], None)


def _dedupe(arr: list[dict], asof: date, keyf) -> dict:
    """Latest FILED fact per period, ignoring anything filed after `asof`."""
    best: dict = {}
    for e in arr:
        try:
            if _d(e["filed"]) > asof:
                continue
            k = keyf(e)
        except (KeyError, ValueError, TypeError):
            continue
        if k is None:
            continue
        if k not in best or e["filed"] > best[k]["filed"]:
            best[k] = e
    return best


def _flow_periods(arr, asof: date, derive: bool = True):
    """-> (quarterly, annual, derived_quarter_ends); the lists are (end_date, value) newest first.

    10-Qs report cash flows only year-to-date (6 and 9 months) and nobody files a 3-month Q4, so with
    `derive` a missing quarter is the difference of two periods with the SAME start whose ends are one
    quarter apart (H1 - Q1 = Q2, 9M - H1 = Q3, FY - 9M = Q4). Not for per-share figures (they do not add up)."""
    def key(e):
        if "start" not in e:
            return None
        return (e["start"], e["end"])
    best = _dedupe(arr, asof, key)
    periods = {(_d(st), _d(en)): e["val"] for (st, en), e in best.items()}
    q, a = {}, {}
    for (st, en), v in periods.items():
        days = (en - st).days
        if 80 <= days <= 100:
            q[en] = v
        elif 340 <= days <= 380:
            a[en] = v
    derived = set()
    if derive:
        by_start: dict = {}
        for (st, en), v in periods.items():
            by_start.setdefault(st, []).append((en, v))
        for lst in by_start.values():
            lst.sort()
            for (e1, v1), (e2, v2) in zip(lst, lst[1:]):
                if 80 <= (e2 - e1).days <= 100 and e2 not in q:
                    q[e2] = v2 - v1
                    derived.add(e2)
    srt = lambda m: sorted(m.items(), reverse=True)     # noqa: E731
    return srt(q), srt(a), derived


def _instant_periods(arr, asof: date):
    best = _dedupe(arr, asof, lambda e: e["end"])
    return sorted(((_d(k), e["val"]) for k, e in best.items()), reverse=True)


def summarize(facts: dict, asof: date, n_q: int = 5, n_a: int = 3) -> dict:
    out = {"entity": facts.get("entityName", ""), "metrics": {}, "derived": {}, "notes": [], "sources": {}}
    for label, concepts, kind, unit in CONCEPTS:
        c, u, arr, latest = _pick(facts, concepts, unit, asof)
        if not arr:
            continue
        if (asof - latest).days > STALE_DAYS:
            out["notes"].append(f"{label} left out: the newest SEC figure ({c}) ends {latest}, too old to use")
            continue
        out["sources"][label] = c
        if kind == "flow":
            q, a, der = _flow_periods(arr, asof, derive=not unit.startswith("USD/"))
            if q or a:
                out["metrics"][label] = {"concept": c, "unit": u, "kind": kind, "quarterly": q[:n_q],
                                          "annual": a[:n_a], "derived_quarters": sorted(der)}
        else:
            ip = _instant_periods(arr, asof)
            if ip:
                out["metrics"][label] = {"concept": c, "unit": u, "kind": kind, "instant": ip[:n_q]}
    # shares outstanding (dei)
    sh = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares")
    if sh:
        best = _dedupe(sh, asof, lambda e: e["end"])
        if best:
            k = max(best)
            out["shares_outstanding"] = (_d(k), best[k]["val"])
    cur = {m["unit"] for m in out["metrics"].values() if m["unit"] and not m["unit"].startswith("USD/")}
    if cur - {"USD"}:
        out["notes"].append(f"non-USD reporting units seen: {sorted(cur - {'USD'})}")

    m = out["metrics"]
    dv = out["derived"]

    def ttm(label):
        """-> (value, basis): four consecutive quarters, else the latest fiscal year, labelled as such."""
        x = m.get(label)
        if not x:
            return None, None
        q = x["quarterly"]
        if len(q) >= 4:
            ends = [e for e, _ in q[:4]]
            if all(80 <= (ends[i] - ends[i + 1]).days <= 100 for i in range(3)):
                return sum(v for _, v in q[:4]), f"TTM (4 quarters to {ends[0]})"
        if x["annual"]:
            e, v = x["annual"][0]
            return v, f"fiscal year to {e}"
        return None, None

    def yoy(label):
        x = m.get(label)
        if not x or not x["quarterly"]:
            return None
        e0, v0 = x["quarterly"][0]
        for e1, v1 in x["quarterly"][1:]:
            if 350 <= (e0 - e1).days <= 380 and v1:
                return e0, (v0 / v1 - 1.0) * 100.0
        return None

    (rev, rb), (ni, nb), (oi, ob), (gp, gb) = ttm("Revenue"), ttm("Net income"), ttm("Operating income"), ttm("Gross profit")
    (ocf, cb), (capex, xb) = ttm("Operating cash flow"), ttm("Capex")
    if rev is not None:
        dv[f"Revenue {rb}"] = rev
        # a margin only when both figures cover the same period
        for name, val, basis in (("Gross margin %", gp, gb), ("Operating margin %", oi, ob), ("Net margin %", ni, nb)):
            if val is not None and basis == rb and rev:
                dv[f"{name}, {rb}"] = val / rev * 100.0
    if ni is not None:
        dv[f"Net income {nb}"] = ni
    if ocf is not None:
        dv[f"Operating cash flow {cb}"] = ocf
        if capex is not None and xb == cb:
            dv[f"Free cash flow (OCF - capex) {cb}"] = ocf - abs(capex)
    for label, name in (("Revenue", "Revenue growth"), ("Net income", "Net income growth")):
        g = yoy(label)
        if g is not None:
            dv[f"{name}, quarter to {g[0]} vs a year earlier %"] = g[1]
    cash = dict(m.get("Cash", {}).get("instant", []))
    debt = dict(m.get("Debt", {}).get("instant", []))
    eq = dict(m.get("Equity", {}).get("instant", []))
    both = sorted(set(cash) & set(debt), reverse=True)        # same balance-sheet date only
    if both:
        d = both[0]
        dv[f"Net debt (debt - cash) at {d}"] = debt[d] - cash[d]
    both = sorted(set(debt) & set(eq), reverse=True)
    if both and eq[both[0]]:
        d = both[0]
        dv[f"Debt / equity at {d}"] = debt[d] / eq[d]
    return out


# --------------------------------------------------------------- rendering

def _money(x, eps=False):
    if x is None:
        return "n/a"
    if eps:
        s = f"{abs(x):,.2f}"
    elif abs(x) >= 1e9:
        s = f"{abs(x) / 1e9:,.2f}B"
    elif abs(x) >= 1e6:
        s = f"{abs(x) / 1e6:,.1f}M"
    else:
        s = f"{abs(x):,.0f}"
    return f"({s})" if x < 0 else s          # negatives in brackets, as Ben reads them


def render_markdown(ticker: str, title: str, summ: dict, asof: date) -> str:
    L = [f"# {ticker} fundamentals from SEC EDGAR ({title or summ.get('entity', '')})",
         f"Source: SEC company facts, filings made on or before {asof}. USD unless noted; negatives in brackets. "
         "Computed by script from the filings; quarterly = 3-month periods; * = worked out from year-to-date or "
         "annual totals (10-Qs give cash flow year-to-date; nobody files a 3-month Q4).", ""]
    m = summ["metrics"]
    if not m:
        L.append("NO USABLE XBRL FACTS FOUND. Use WebSearch/WebFetch (the company's latest 10-K/10-Q or "
                 "annual report) and say clearly that figures are not script-verified.")
        return "\n".join(L) + "\n"

    flows = {k: v for k, v in m.items() if v["kind"] == "flow"}
    qe = sorted({e for v in flows.values() for e, _ in v["quarterly"]}, reverse=True)[:5]
    if qe:
        L += ["## Quarterly", "| Item | " + " | ".join(str(e) for e in qe) + " |",
              "|---|" + "---|" * len(qe)]
        for k, v in flows.items():
            qd = dict(v["quarterly"])
            der = set(v.get("derived_quarters", ()))
            if qd:
                L.append(f"| {k} | " + " | ".join(
                    _money(qd.get(e), k.startswith("EPS")) + ("*" if e in der and e in qd else "") for e in qe) + " |")
        L.append("")
    ae = sorted({e for v in flows.values() for e, _ in v["annual"]}, reverse=True)[:3]
    if ae:
        L += ["## Annual", "| Item | " + " | ".join(str(e) for e in ae) + " |", "|---|" + "---|" * len(ae)]
        for k, v in flows.items():
            ad = dict(v["annual"])
            if ad:
                L.append(f"| {k} | " + " | ".join(_money(ad.get(e), k.startswith("EPS")) for e in ae) + " |")
        L.append("")
    inst = {k: v for k, v in m.items() if v["kind"] == "instant"}
    ie = sorted({e for v in inst.values() for e, _ in v["instant"]}, reverse=True)[:4]
    if ie:
        L += ["## Balance sheet", "| Item | " + " | ".join(str(e) for e in ie) + " |", "|---|" + "---|" * len(ie)]
        for k, v in inst.items():
            idc = dict(v["instant"])
            L.append(f"| {k} | " + " | ".join(_money(idc.get(e)) for e in ie) + " |")
        L.append("")
    if summ["derived"]:
        L.append("## Derived (script-computed)")
        for k, v in summ["derived"].items():
            pct = "%" in k
            ratio = "/ equity" in k
            L.append(f"- {k}: " + (f"{v:,.1f}%" if pct else (f"{v:,.2f}x" if ratio else _money(v))))
        L.append("")
    if "shares_outstanding" in summ:
        d, v = summ["shares_outstanding"]
        L.append(f"Shares outstanding (cover page, as of {d}): {v:,.0f}")
    if summ.get("sources"):
        L.append("SEC concept per row: " + "; ".join(f"{k} = {c}" for k, c in summ["sources"].items()))
    for n in summ["notes"]:
        L.append(f"Note: {n}")
    if not qe:
        L.append("Note: no quarterly periods on file (typical of 20-F filers that report half-yearly); annual only.")
    return "\n".join(L) + "\n"
