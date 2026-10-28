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
                 "SalesRevenueNet", "Revenue"], "flow", "USD"),
    ("Gross profit", ["GrossProfit"], "flow", "USD"),
    ("Operating income", ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"], "flow", "USD"),
    ("Net income", ["NetIncomeLoss", "ProfitLoss", "ProfitLossAttributableToOwnersOfParent"], "flow", "USD"),
    ("EPS diluted ($)", ["EarningsPerShareDiluted", "DilutedEarningsLossPerShare"], "flow", "USD/"),
    ("Operating cash flow", ["NetCashProvidedByUsedInOperatingActivities",
                              "CashFlowsFromUsedInOperatingActivities"], "flow", "USD"),
    ("Capex", ["PaymentsToAcquirePropertyPlantAndEquipment",
               "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"], "flow", "USD"),
    ("Cash", ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"], "instant", "USD"),
    ("Total assets", ["Assets"], "instant", "USD"),
    ("Total liabilities", ["Liabilities"], "instant", "USD"),
    ("Equity", ["StockholdersEquity", "Equity"], "instant", "USD"),
    ("Long-term debt", ["LongTermDebt", "LongTermDebtNoncurrent", "NoncurrentPortionOfNoncurrentBondsIssued",
                         "NoncurrentPortionOfNoncurrentLoansReceived"], "instant", "USD"),
]


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


def _pick(facts: dict, concepts: list[str], unit_prefix: str):
    for tax in TAX:
        node_tax = facts.get("facts", {}).get(tax, {})
        for c in concepts:
            node = node_tax.get(c)
            if not node:
                continue
            for unit, arr in node.get("units", {}).items():
                if unit.startswith(unit_prefix):
                    return c, unit, arr
    return None, None, []


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


def _flow_periods(arr, asof: date):
    """-> (quarterly, annual) each a list of (end_date, value) newest first."""
    def key(e):
        if "start" not in e:
            return None
        return (e["start"], e["end"])
    best = _dedupe(arr, asof, key)
    q, a = {}, {}
    for (st, en), e in best.items():
        days = (_d(en) - _d(st)).days
        if 80 <= days <= 100:
            q[_d(en)] = e["val"]
        elif 340 <= days <= 380:
            a[_d(en)] = e["val"]
    srt = lambda m: sorted(m.items(), reverse=True)     # noqa: E731
    return srt(q), srt(a)


def _instant_periods(arr, asof: date):
    best = _dedupe(arr, asof, lambda e: e["end"])
    return sorted(((_d(k), e["val"]) for k, e in best.items()), reverse=True)


def summarize(facts: dict, asof: date, n_q: int = 5, n_a: int = 3) -> dict:
    out = {"entity": facts.get("entityName", ""), "metrics": {}, "derived": {}, "notes": []}
    for label, concepts, kind, unit in CONCEPTS:
        c, u, arr = _pick(facts, concepts, unit)
        if not arr:
            continue
        if kind == "flow":
            q, a = _flow_periods(arr, asof)
            if q or a:
                out["metrics"][label] = {"concept": c, "unit": u, "kind": kind,
                                          "quarterly": q[:n_q], "annual": a[:n_a]}
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
        x = m.get(label)
        if not x:
            return None
        q = x["quarterly"]
        if len(q) >= 4:
            ends = [e for e, _ in q[:4]]
            span = (ends[0] - ends[3]).days
            if 240 <= span <= 300:          # four consecutive quarters
                return sum(v for _, v in q[:4])
        if x["annual"]:
            return x["annual"][0][1]
        return None

    def yoy(label):
        x = m.get(label)
        if not x or not x["quarterly"]:
            return None
        e0, v0 = x["quarterly"][0]
        for e1, v1 in x["quarterly"][1:]:
            if 350 <= (e0 - e1).days <= 380 and v1:
                return (v0 / v1 - 1.0) * 100.0
        return None

    rev, ni, oi, gp = ttm("Revenue"), ttm("Net income"), ttm("Operating income"), ttm("Gross profit")
    ocf, capex = ttm("Operating cash flow"), ttm("Capex")
    if rev:
        dv["Revenue TTM"] = rev
        if gp is not None:
            dv["Gross margin %"] = gp / rev * 100.0
        if oi is not None:
            dv["Operating margin %"] = oi / rev * 100.0
        if ni is not None:
            dv["Net margin %"] = ni / rev * 100.0
    if ni is not None:
        dv["Net income TTM"] = ni
    if ocf is not None:
        dv["Operating cash flow TTM"] = ocf
        if capex is not None:
            dv["Free cash flow TTM (OCF - capex)"] = ocf - abs(capex)
    g = yoy("Revenue")
    if g is not None:
        dv["Revenue growth, latest quarter vs year ago %"] = g
    ge = yoy("Net income")
    if ge is not None:
        dv["Net income growth, latest quarter vs year ago %"] = ge
    cash = m.get("Cash", {}).get("instant")
    debt = m.get("Long-term debt", {}).get("instant")
    eq = m.get("Equity", {}).get("instant")
    if cash and debt:
        dv["Net debt (long-term debt - cash)"] = debt[0][1] - cash[0][1]
    if debt and eq and eq[0][1]:
        dv["Long-term debt / equity"] = debt[0][1] / eq[0][1]
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
         "Computed by script from the filings; quarterly = 3-month periods as filed.", ""]
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
            if qd:
                L.append(f"| {k} | " + " | ".join(_money(qd.get(e), k.startswith("EPS")) for e in qe) + " |")
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
            pct = k.endswith("%")
            ratio = "/ equity" in k
            L.append(f"- {k}: " + (f"{v:,.1f}%" if pct else (f"{v:,.2f}x" if ratio else _money(v))))
        L.append("")
    if "shares_outstanding" in summ:
        d, v = summ["shares_outstanding"]
        L.append(f"Shares outstanding (cover page, as of {d}): {v:,.0f}")
    for n in summ["notes"]:
        L.append(f"Note: {n}")
    if not qe:
        L.append("Note: no quarterly periods on file (typical of 20-F filers that report half-yearly); annual only.")
    return "\n".join(L) + "\n"
