#!/usr/bin/env python3
r"""Trading halts on the exchange tape: what the status schema holds, how often the universe is halted, what it did to the books.

    python -m common.halt_census
    python -m common.halt_census --trades var/reports/first_entry_skip_trades.csv
    python -m common.halt_census --limit 3          # first three monthly chunks

Registered in docs/research/REGISTERED_halt_census.md before the pull and
before this ran. A census, not a hypothesis: it describes the schema first
(action x reason, printed raw before anything is interpreted), then counts
halts on the point-in-time universe's symbol-days against every symbol the
tape carries, then marks the baseline trades a halt fell inside.

WHAT A HALT IS HERE
-------------------
A halt opens on the first record for an instrument with `action` in
{HALT, PAUSE, SUSPEND} while it is not already halted, and closes on the next
record with `action == TRADING` or `is_trading` true. Repeated halt records
extend the open halt; a halt still open at the end of the day is reported as
open, with its duration to 20:00, and counted. Pre-open / pre-close / close
records are ignored. Times are ET; the day is the ET date of the record.

The reason recorded is the OPENING record's reason. LULD pauses carry
`LULD_PAUSE` (50); regulatory halts carry NEWS_PENDING (30) and its kin;
whatever else appears is printed in the crosstab so nothing is folded into a
bucket it does not belong to.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.report_io import emit

ET = ZoneInfo("America/New_York")
DATASET = "XNAS.ITCH"
SCHEMA = "status"
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
HALT_ACTIONS = {8: "HALT", 9: "PAUSE", 10: "SUSPEND"}
TRADING = 7
ACTION_NAMES = {0: "NONE", 1: "PRE_OPEN", 2: "PRE_CROSS", 3: "QUOTING", 4: "CROSS", 5: "ROTATION",
                6: "NEW_PRICE_INDICATION", 7: "TRADING", 8: "HALT", 9: "PAUSE", 10: "SUSPEND",
                11: "PRE_CLOSE", 12: "CLOSE", 13: "POST_CLOSE", 14: "SSR_CHANGE",
                15: "NOT_AVAILABLE_FOR_TRADING"}
REASON_NAMES = {0: "NONE", 1: "SCHEDULED", 2: "SURVEILLANCE_INTERVENTION", 3: "MARKET_EVENT",
                4: "INSTRUMENT_ACTIVATION", 5: "INSTRUMENT_EXPIRATION", 6: "RECOVERY_IN_PROCESS",
                10: "REGULATORY", 11: "ADMINISTRATIVE", 12: "NON_COMPLIANCE", 13: "FILINGS_NOT_CURRENT",
                14: "SEC_TRADING_SUSPENSION", 15: "NEW_ISSUE", 16: "ISSUE_AVAILABLE", 17: "ISSUES_REVIEWED",
                18: "FILING_REQS_SATISFIED", 30: "NEWS_PENDING", 31: "NEWS_RELEASED",
                32: "NEWS_AND_RESUMPTION_TIMES", 33: "NEWS_NOT_FORTHCOMING", 40: "ORDER_IMBALANCE",
                50: "LULD_PAUSE", 60: "OPERATIONAL", 70: "ADDITIONAL_INFORMATION_REQUESTED",
                80: "MERGER_EFFECTIVE", 90: "ETF", 100: "CORPORATE_ACTION", 110: "NEW_SECURITY_OFFERING",
                120: "MARKET_WIDE_HALT_LEVEL1", 121: "MARKET_WIDE_HALT_LEVEL2",
                122: "MARKET_WIDE_HALT_LEVEL3", 123: "MARKET_WIDE_HALT_CARRYOVER",
                124: "MARKET_WIDE_HALT_RESUMPTION", 130: "QUOTATION_NOT_AVAILABLE"}
PRE = (4 * 60, 9 * 60 + 30)
RTH = (9 * 60 + 30, 16 * 60)
DAY_END_MIN = 20 * 60


def aname(a) -> str:
    return ACTION_NAMES.get(int(a), str(int(a)))


def rname(r) -> str:
    return REASON_NAMES.get(int(r), str(int(r)))


def et_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Add ET date and minute-of-day; keep the columns the census reads."""
    et = df.index.tz_convert(ET)
    out = pd.DataFrame({"symbol": df["symbol"].values, "action": df["action"].astype(int).values,
                        "reason": df["reason"].astype(int).values,
                        "is_trading": df["is_trading"].astype(bool).values if "is_trading" in df.columns
                        else (df["action"].astype(int).values == TRADING),
                        "date": et.strftime("%Y-%m-%d"),
                        "min": (et.hour * 60 + et.minute + et.second / 60.0)})
    return out.sort_values(["symbol", "date", "min"], kind="mergesort").reset_index(drop=True)


def crosstab(f: pd.DataFrame) -> Counter:
    return Counter(zip(f["action"].tolist(), f["reason"].tolist()))


def halts(f: pd.DataFrame) -> list[dict]:
    """Halt intervals per (symbol, date). See the module docstring."""
    out = []
    for (sym, day), g in f.groupby(["symbol", "date"], sort=False):
        open_ = None
        for a, r, tr, m in zip(g["action"].values, g["reason"].values, g["is_trading"].values, g["min"].values):
            if a in HALT_ACTIONS:
                if open_ is None:
                    open_ = {"symbol": sym, "date": day, "start_min": float(m), "action": aname(a),
                             "reason": rname(r)}
            elif open_ is not None and (a == TRADING or tr):
                open_["end_min"] = float(m)
                open_["open_at_close"] = False
                out.append(open_)
                open_ = None
        if open_ is not None:
            open_["end_min"] = float(DAY_END_MIN)
            open_["open_at_close"] = True
            out.append(open_)
    for h in out:
        h["dur_min"] = h["end_min"] - h["start_min"]
    return out


def hhmm(m: float) -> str:
    m = int(m)
    return f"{m // 60:02d}:{m % 60:02d}"


def window(h: dict) -> str:
    s = h["start_min"]
    if PRE[0] <= s < PRE[1]:
        return "pre"
    if RTH[0] <= s < RTH[1]:
        return "rth"
    return "other"


def read_trades(path: str) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("book") not in ("MCL", "MC5"):
                continue
            e = r["entry_et"]; x = r["exit_et"]
            rows.append({"book": r["book"], "symbol": r["symbol"], "date": r["date"],
                         "entry_min": int(e[:2]) * 60 + int(e[3:5]), "exit_min": int(x[:2]) * 60 + int(x[3:5]),
                         "net": float(r["net"]), "reason": r.get("reason", "")})
    return rows


def mark_trades(trades: list[dict], hs: list[dict]) -> list[dict]:
    by = defaultdict(list)
    for h in hs:
        by[(h["symbol"], h["date"])].append(h)
    for t in trades:
        t["halt_inside"] = False; t["exit_on_resume"] = False; t["halt_reason"] = ""
        for h in by.get((t["symbol"], t["date"]), ()):
            if t["entry_min"] <= h["start_min"] <= t["exit_min"]:
                t["halt_inside"] = True; t["halt_reason"] = h["reason"]
            if int(h["end_min"]) == t["exit_min"] and not h["open_at_close"]:
                t["exit_on_resume"] = True
    return trades


def q(vals, p):
    return float(np.quantile(vals, p)) if len(vals) else float("nan")


def summary(ct: Counter, hs: list[dict], universe: set, universe_days: dict, sessions: int,
            trades: list[dict] | None, friction: float = 4.26) -> dict:
    s = {"sessions": sessions, "records_by_action_reason": [
        {"action": aname(a), "reason": rname(r), "n": n} for (a, r), n in ct.most_common()]}
    uni = [h for h in hs if (h["symbol"], h["date"]) in universe]
    s["halts_all"] = len(hs); s["halts_universe"] = len(uni)
    for tag, pop in (("all", hs), ("universe", uni)):
        d = {}
        for w in ("pre", "rth"):
            sel = [h for h in pop if window(h) == w]
            d[w] = {"n": len(sel),
                    "by_reason": dict(Counter(h["reason"] for h in sel).most_common()),
                    "symbol_days": len({(h["symbol"], h["date"]) for h in sel}),
                    "dur_p10_p50_p90": [q([h["dur_min"] for h in sel], p) for p in (.1, .5, .9)],
                    "open_at_close": sum(h["open_at_close"] for h in sel)}
        rth = [h for h in pop if window(h) == "rth"]
        d["rth_first_half_hour_share"] = (sum(1 for h in rth if h["start_min"] < 10 * 60) / len(rth)) if rth else None
        d["open_at_0930"] = sum(1 for h in pop if h["start_min"] < RTH[0] <= h["end_min"])
        d["starts_by_half_hour"] = dict(sorted(Counter(hhmm(int(h["start_min"]) // 30 * 30) for h in pop).items()))
        d["luld_before_0930"] = sum(1 for h in pop if h["reason"] == "LULD_PAUSE" and h["start_min"] < RTH[0])
        s[tag] = d
    n_uni_days = sum(len(v) for v in universe_days.values())
    s["universe_symbol_days"] = n_uni_days
    s["universe_share_pre_halt"] = (s["universe"]["pre"]["symbol_days"] / n_uni_days) if n_uni_days else None
    s["universe_share_rth_halt"] = (s["universe"]["rth"]["symbol_days"] / n_uni_days) if n_uni_days else None
    if trades is not None:
        s["books"] = {}
        for book in ("MCL", "MC5"):
            tb = [t for t in trades if t["book"] == book]
            hit = [t for t in tb if t["halt_inside"]]
            rest = [t for t in tb if not t["halt_inside"]]
            res = [t for t in tb if t["exit_on_resume"]]
            per = lambda rows: (sum(t["net"] for t in rows) / len(rows) - friction) if rows else None  # noqa: E731
            s["books"][book] = {"trades": len(tb), "halt_inside": len(hit), "exit_on_resume": len(res),
                                "share": (len(hit) / len(tb)) if tb else None,
                                "per_trade_halted": per(hit), "per_trade_rest": per(rest),
                                "per_trade_exit_on_resume": per(res),
                                "halted_exit_reasons": dict(Counter(t["reason"] for t in hit).most_common()),
                                "halted_reasons": dict(Counter(t["halt_reason"] for t in hit).most_common())}
    return s


def money(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def render(s: dict, elapsed: float, chunks: int) -> list[str]:
    L = [f"TRADING HALTS ON {DATASET} -- {SCHEMA} schema", "",
         "  registered  docs/research/REGISTERED_halt_census.md",
         f"  {chunks} monthly chunk(s)   {s['sessions']:,} sessions   elapsed {elapsed:.1f}s", "",
         "WHAT THE SCHEMA HOLDS (records by action x reason, whole pull)", ""]
    for row in s["records_by_action_reason"][:40]:
        L.append(f"  {row['action']:<26}{row['reason']:<32}{row['n']:>12,}")
    if len(s["records_by_action_reason"]) > 40:
        L.append(f"  ... {len(s['records_by_action_reason']) - 40} more combinations in the JSON")
    L += ["", f"HALTS   all symbols {s['halts_all']:,}   universe symbol-days {s['halts_universe']:,} "
          f"(of {s['universe_symbol_days']:,} symbol-days)", ""]
    for tag, title in (("universe", "THE POINT-IN-TIME UNIVERSE (v2)"), ("all", "EVERY SYMBOL ON THE TAPE")):
        d = s[tag]
        L += [title, ""]
        for w, name in (("pre", "04:00-09:30"), ("rth", "09:30-16:00")):
            e = d[w]
            p10, p50, p90 = e["dur_p10_p50_p90"]
            L.append(f"  {name}  halts {e['n']:,}   symbol-days {e['symbol_days']:,}   "
                     f"duration min p10/p50/p90 {p10:.0f}/{p50:.0f}/{p90:.0f}   open at 20:00 {e['open_at_close']:,}")
            for r, n in list(e["by_reason"].items())[:8]:
                L.append(f"      {r:<32}{n:>8,}")
        share = d["rth_first_half_hour_share"]
        L.append(f"  RTH halts starting 09:30-10:00: {100 * share:.1f}%" if share is not None else "  RTH halts: none")
        L.append(f"  halts open at 09:30: {d['open_at_0930']:,}   LULD pauses before 09:30: {d['luld_before_0930']:,}")
        L.append("  starts by half hour: " + "  ".join(f"{k} {v:,}" for k, v in d["starts_by_half_hour"].items()
                                                       if "04:00" <= k < "16:30"))
        L.append("")
    if s.get("universe_share_pre_halt") is not None:
        L += [f"  universe symbol-days with a halt starting pre-market: {100 * s['universe_share_pre_halt']:.2f}%   "
              f"in RTH: {100 * s['universe_share_rth_halt']:.2f}%", ""]
    if "books" in s:
        L += ["THE BOOKS (baseline MCL and MC5 from first_entry_skip, net per trade at $4.26)", ""]
        for book, b in s["books"].items():
            L += [f"  {book}: {b['trades']:,} trades   halt began inside {b['halt_inside']:,} "
                  f"({100 * (b['share'] or 0):.2f}%)   exit on the resumption bar {b['exit_on_resume']:,}",
                  f"      per trade, halted {money(b['per_trade_halted'])}   rest {money(b['per_trade_rest'])}   "
                  f"exit-on-resume {money(b['per_trade_exit_on_resume'])}",
                  "      halted trades' exit reasons: " + ", ".join(f"{k} {v}" for k, v in b["halted_exit_reasons"].items()),
                  "      halt reasons: " + ", ".join(f"{k} {v}" for k, v in b["halted_reasons"].items()), ""]
    else:
        L += ["THE BOOKS", "", "  no --trades CSV given; run first_entry_skip on the v2 universe and pass its CSV.", ""]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--trades", default=None, help="first_entry_skip trades CSV (books MCL and MC5)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", default="var/reports/halt_census.txt")
    p.add_argument("--json", default="var/reports/halt_census.json")
    p.add_argument("--csv", default="var/reports/halt_census.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.dbn_io import read_dbn
    from common.pit_h0 import load_pit

    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    d = archive / DATASET / SCHEMA
    chunks = sorted(d.glob("*.dbn.zst"))
    if a.limit:
        chunks = chunks[:a.limit]
    if not chunks:
        raise SystemExit(f"no {SCHEMA} chunks under {d}")
    by_date = load_pit(Path(a.pairs))
    universe = {(r["symbol"], day) for day, recs in by_date.items() for r in recs}
    t0 = time.time()
    ct: Counter = Counter()
    hs: list[dict] = []
    days: set = set()
    for k, p in enumerate(chunks, 1):
        try:
            df = read_dbn(p)
        except Exception as e:                                  # noqa: BLE001
            print(f"  ! {p.name}: unreadable ({type(e).__name__}: {e})", flush=True)
            continue
        if df.empty:
            continue
        f = et_frame(df)
        ct.update(crosstab(f))
        days.update(f["date"].unique().tolist())
        hs.extend(halts(f))
        print(f"  {k}/{len(chunks)} {p.name}  records {len(f):,}  halts so far {len(hs):,}", flush=True)
    trades = None
    if a.trades:
        trades = mark_trades(read_trades(a.trades), hs)
    s = summary(ct, hs, universe, by_date, len(days), trades)
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(s, indent=1), encoding="utf-8")
    with open(a.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "date", "start_et", "end_et", "dur_min", "action", "reason", "open_at_close", "in_universe"])
        for h in hs:
            w.writerow([h["symbol"], h["date"], hhmm(h["start_min"]), hhmm(h["end_min"]), f"{h['dur_min']:.1f}",
                        h["action"], h["reason"], int(h["open_at_close"]), int((h["symbol"], h["date"]) in universe)])
    emit("\n".join(render(s, time.time() - t0, len(chunks))), a.out,
         header=f"common.halt_census  {DATASET}/{SCHEMA}  pairs={a.pairs}"
                + (f"  trades={a.trades}" if a.trades else "") + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
