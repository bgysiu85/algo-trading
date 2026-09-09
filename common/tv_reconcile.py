#!/usr/bin/env python3
"""Where does the gap between TradingView's price and our fill actually go?

    python -m common.tv_reconcile --fills var/fills/mcl_fills_20260909.csv \\
                                  --alerts var/tv_alerts/20260909.jsonl

THE QUESTION, Ben 2026-09-09
----------------------------
"TV bought BNC at $5.10, IBKR filled at $5.41. That's a 31c difference which is
significant."

It is: 31c on a $5.22 decision is 5.9%, and MCL's entire trailing stop is 5%.
A gap that size means a position can be beyond its own stop before the fill is
even confirmed -- which is a plausible mechanism for the finding in
claude/consolidation_filter_test.md, that two thirds of trades stop out inside
five minutes and lose $1,935.

But "31c of slippage" is three different things added together, and they have
three different fixes. Guessing which one dominates is how a project spends a
week tuning execution when the problem was bar alignment. So this splits the
difference into parts that SUM EXACTLY to it:

    bar_gap     TV's reference close vs OURS.
                Non-zero means we acted on a DIFFERENT BAR than TV. Fixed by
                fetching and evaluating sooner -- see common/bar_freshness.py.

    drift       our reference close vs the market when the order went out.
                This is the cost of the delay between a bar closing and an
                order reaching the book. Fixed by shortening that delay, and
                bounded by how fast the name moves.

    execution   our fill vs the quote we were shown.
                Near zero means the broker did its job. This is the only part
                a smarter order type can improve, and on 2026-09-09 it was one
                cent INSIDE the ask.

The identity is arithmetic, not a model:

    cost = bar_gap + drift + execution

signed so that POSITIVE IS MONEY LOST in every case -- paying more on a buy,
receiving less on a sell.

WHAT FEEDS IT
-------------
Our side: the trader's fill log, which already records ref_close, the bid/ask
at order time, the limit sent, and the fill.

TV's side: the JSON payloads emitted by the alert() calls in pine/MCL.pine.
They carry bar_time_ms AND bar_close_ms, because "the 06:21 signal" is
ambiguous between the bar labelled 06:21 and the moment 06:22:00 when it
closed -- and that ambiguity is what made the original question unanswerable.

WHY NOT READ THE STRATEGY TESTER INSTEAD
-----------------------------------------
Because after the session it is a BACKTEST OF THE DAY, recomputed from current
bar history, not a recording of what fired live. Differences between it and our
fills would be partly artefacts of the recomputation with no way to tell which.
A fired alert is stamped when it fired. Only the alert can answer a question
about timing.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from common.report_io import emit

ET = ZoneInfo("America/New_York")

# How long after a TV bar closes we still believe a fill belongs to it. Wide
# enough to cover a slow order, narrow enough that two signals on the same
# symbol are not confused for each other.
MATCH_WINDOW = timedelta(minutes=10)

_OBJ = re.compile(r"\{.*\}", re.S)


def parse_alert(line: str) -> dict | None:
    """One alert payload, however it arrived.

    The JSON is EXTRACTED rather than parsed from the whole line, because the
    delivery path is not decided yet and every candidate wraps it in something:
    a webhook log adds a timestamp, a Telegram export adds a header, a copy out
    of TradingView's alert log adds the alert name. Requiring a bare line would
    make the tool depend on a choice that has not been made.
    """
    if not line or not line.strip():
        return None
    m = _OBJ.search(line)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(d, dict) or "symbol" not in d or "action" not in d:
        return None
    for k in ("bar_time_ms", "bar_close_ms"):
        if k in d and d[k] is not None:
            d[k] = int(d[k])
    d["symbol"] = str(d["symbol"]).split(":")[-1]   # NASDAQ:BNC -> BNC
    return d


def alert_time(a: dict) -> datetime | None:
    """When the rule could FIRST have been acted on.

    bar_close_ms, not bar_time_ms. A strategy that acts on a closed bar cannot
    act at the bar's label; measuring our latency from the label would charge
    us for the bar's own duration and make every entry look a minute worse than
    it is. This is the distinction the whole module exists to keep straight.
    """
    ms = a.get("bar_close_ms")
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, ET)


def load_alerts(path: Path) -> list[dict]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        a = parse_alert(line)
        if a:
            out.append(a)
    return out


def load_fills(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if r.get("status") != "FILLED":
            continue
        try:
            r["_ts"] = datetime.strptime(
                r["ts_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        except (KeyError, ValueError):
            continue
        out.append(r)
    return out


def _f(row, key):
    try:
        v = row.get(key)
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def match(alerts: list[dict], fills: list[dict]) -> list[dict]:
    """Pair each fill with the alert it acted on.

    Nearest PRECEDING alert for the same symbol and action, within
    MATCH_WINDOW, and each alert is consumed once. Consuming matters: on a name
    that signals twice in a morning, a greedy nearest-match would happily give
    both fills to whichever alert was closer and report a latency of seconds
    for a trade that took minutes.
    """
    used, out = set(), []
    for f in sorted(fills, key=lambda r: r["_ts"]):
        best, best_i = None, None
        for i, a in enumerate(alerts):
            if i in used or a["symbol"] != f["symbol"]:
                continue
            if str(a["action"]).upper() != str(f["action"]).upper():
                continue
            t = alert_time(a)
            if t is None or t > f["_ts"] or f["_ts"] - t > MATCH_WINDOW:
                continue
            if best is None or t > alert_time(best):
                best, best_i = a, i
        if best_i is not None:
            used.add(best_i)
        out.append({"fill": f, "alert": best})
    return out


def decompose(fill: dict, alert: dict | None) -> dict | None:
    """Split the difference into bar_gap + drift + execution.

    Signed so POSITIVE IS MONEY LOST on both sides of the market: on a buy we
    lose by paying more, on a sell by receiving less. Without that flip the two
    directions cannot be added together or averaged, and a report that mixed
    them would understate the total by cancelling real costs against each other.
    """
    if alert is None:
        return None
    tv = alert.get("ref_close")
    ours = _f(fill, "ref_close")
    px = _f(fill, "fill_price")
    if tv is None or ours is None or px is None:
        return None
    buy = str(fill["action"]).upper() == "BUY"
    # The side we cross to get filled: a buy lifts the ask, a sell hits the bid.
    quote = _f(fill, "ask" if buy else "bid")
    if quote is None:
        return None
    sign = 1.0 if buy else -1.0
    d = {
        "bar_gap": sign * (ours - float(tv)),
        "drift": sign * (quote - ours),
        "execution": sign * (px - quote),
    }
    d["cost"] = d["bar_gap"] + d["drift"] + d["execution"]
    d["cost_pct"] = 100.0 * d["cost"] / float(tv) if tv else 0.0
    t = alert_time(alert)
    d["latency_s"] = (fill["_ts"] - t).total_seconds() if t else None
    d["tv_ref"] = float(tv)
    return d


def render(pairs: list[dict], fills_path: str, alerts_path: str) -> list[str]:
    L = ["TV vs BROKER -- where the price difference actually goes", "",
         f"  fills   {fills_path}",
         f"  alerts  {alerts_path}",
         "",
         "  cost = bar_gap + drift + execution, exactly. Positive is money",
         "  lost: paying more on a buy, receiving less on a sell.",
         "",
         "    bar_gap     we acted on a different BAR than TV",
         "    drift       the market moved between bar close and order out",
         "    execution   our fill against the quote we were shown",
         ""]

    hdr = (f"  {'time':<9}{'sym':<7}{'act':<5}{'TV ref':>8}{'our ref':>9}"
           f"{'fill':>8}{'bar_gap':>9}{'drift':>8}{'exec':>7}{'cost':>8}"
           f"{'%':>7}{'lat s':>7}")
    L += [hdr, "  " + "-" * (len(hdr) - 2)]

    done, unmatched = [], []
    for p in pairs:
        f, a = p["fill"], p["alert"]
        d = decompose(f, a)
        if d is None:
            unmatched.append(f)
            continue
        done.append(d)
        L.append(f"  {f['_ts']:%H:%M:%S} {f['symbol']:<7}{f['action']:<5}"
                 f"{d['tv_ref']:>8.2f}{_f(f, 'ref_close'):>9.2f}"
                 f"{_f(f, 'fill_price'):>8.2f}{d['bar_gap']:>9.3f}"
                 f"{d['drift']:>8.3f}{d['execution']:>7.3f}"
                 f"{d['cost']:>8.3f}{d['cost_pct']:>6.2f}%"
                 + (f"{d['latency_s']:>7.0f}" if d["latency_s"] is not None
                    else f"{'--':>7}"))

    L.append("")
    if not done:
        L += ["  NOTHING MATCHED. Either the alert file is empty, or its",
              "  payloads predate the structured format in pine/MCL.pine, or",
              "  the alert was created with the wrong event type -- a strategy",
              "  alert set to 'alert() function calls only' drops every",
              "  trailing-stop exit, which is most of them.", ""]
    else:
        n = len(done)
        tot = {k: sum(d[k] for d in done) for k in
               ("bar_gap", "drift", "execution", "cost")}
        L += [f"  {n} matched trade(s)", "",
              f"  {'':<12}{'total':>10}{'per trade':>12}{'share':>9}"]
        for k in ("bar_gap", "drift", "execution"):
            share = (100 * tot[k] / tot["cost"]) if tot["cost"] else 0.0
            L.append(f"  {k:<12}{tot[k]:>10.3f}{tot[k] / n:>12.3f}"
                     f"{share:>8.1f}%")
        L.append(f"  {'COST':<12}{tot['cost']:>10.3f}{tot['cost'] / n:>12.3f}"
                 f"{100.0:>8.1f}%")
        lat = [d["latency_s"] for d in done if d["latency_s"] is not None]
        if lat:
            lat.sort()
            L += ["",
                  f"  latency, bar close -> fill:  median {lat[len(lat)//2]:.0f}s"
                  f"   max {lat[-1]:.0f}s",
                  "  A minute or less is the loop's own cadence. Two minutes or",
                  "  more means a bar was discarded somewhere -- run",
                  "  common.bar_freshness INSIDE a session to find out where."]

        biggest = max(("bar_gap", "drift", "execution"), key=lambda k: tot[k])
        L += ["", f"  LARGEST COMPONENT: {biggest}."]
        L += {
            "bar_gap": ["  We are not acting on the bar TV acted on. That is a",
                        "  timing defect, not an execution one, and no order",
                        "  type fixes it."],
            "drift": ["  The market moves between the bar closing and the order",
                      "  reaching the book. Shortening that delay is the only",
                      "  lever; a limit price further through the spread buys",
                      "  nothing because the quote had already moved."],
            "execution": ["  The broker is the cost, which is the one case where",
                          "  order type and routing are worth work. Check this",
                          "  against the measured $4.26/RT before acting."],
        }[biggest]

    if unmatched:
        L += ["", f"  {len(unmatched)} fill(s) had no matching alert:"]
        for f in unmatched[:10]:
            L.append(f"    {f['_ts']:%H:%M:%S} {f['symbol']} {f['action']} "
                     f"{f.get('reason', '')}")
        L += ["",
              "  An unmatched fill is NOT evidence TV disagreed. It usually",
              "  means no alert was armed for that symbol, so treat the",
              "  matched set as a sample and not as the session."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--fills", required=True)
    p.add_argument("--alerts", required=True)
    p.add_argument("--out", default="var/reports/tv_reconcile.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    pairs = match(load_alerts(Path(a.alerts)), load_fills(Path(a.fills)))
    emit("\n".join(render(pairs, a.fills, a.alerts)), a.out,
         header=f"common.tv_reconcile  fills={a.fills} alerts={a.alerts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
