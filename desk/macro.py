r"""W18-0006: the day's market closes (indices, volatility, crude, 10-year yield) from IBKR, as a file
the macro analyst reads FIRST. No LLM involved.

    .\.venv\Scripts\python.exe -m desk.macro --date 2026-11-10

Writes var/desk_runs/<US date>/_macro_data.md. Read-only API connection, paper ports only (same rules as
desk.fetch_bars). Each instrument is tried as the real series first (VIX and the 10-year yield are CBOE
indices, crude is the NYMEX front-month future); if the account has no data subscription for it, a
clearly labelled stand-in fund is used instead; if that fails too the row says UNAVAILABLE and the macro
analyst falls back to web search for that line only. A failure of one instrument never stops the others.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from desk import config as cfgmod
from desk import fetch_bars, snapshot
from desk.pipeline import MACRO_DATA_FILE

MIN_BARS = 2             # need a previous close for the 1-day change
FIVE_DAY_BARS = 6        # last bar + 5 earlier

# kind: stock | index | future.  `yield_pct`: quoted as a yield, so changes are shown in basis points (bp).
INSTRUMENTS = (
    {"key": "SPY", "label": "S&P 500 (SPY fund)", "kind": "stock", "symbol": "SPY"},
    {"key": "QQQ", "label": "Nasdaq-100 (QQQ fund)", "kind": "stock", "symbol": "QQQ"},
    {"key": "IWM", "label": "Russell 2000 small caps (IWM fund)", "kind": "stock", "symbol": "IWM"},
    {"key": "VIX", "label": "VIX (S&P 500 volatility index)", "kind": "index", "symbol": "VIX", "exchange": "CBOE",
     "standin": {"label": "VIXY (short-term VIX futures fund, NOT the VIX itself)", "kind": "stock", "symbol": "VIXY"}},
    {"key": "CL", "label": "WTI crude oil, front month (CL, $/barrel)", "kind": "future", "symbol": "CL",
     "exchange": "NYMEX",
     "standin": {"label": "USO (oil fund, NOT the crude price)", "kind": "stock", "symbol": "USO"}},
    {"key": "TNX", "label": "US 10-year Treasury yield (%)", "kind": "index", "symbol": "TNX", "exchange": "CBOE",
     "yield_pct": True,
     "standin": {"label": "IEF (7-10 year Treasury bond fund; its price FALLS when yields RISE)", "kind": "stock",
                 "symbol": "IEF"}},
)


class MacroError(RuntimeError):
    pass


# ---------------------------------------------------------------- fetching

def _contract(spec: dict, mod, ib):
    kind = spec["kind"]
    if kind == "stock":
        return fetch_bars._qualify(ib, spec["symbol"], mod.Stock)
    c = mod.Index(spec["symbol"], spec["exchange"]) if kind == "index" else \
        mod.ContFuture(spec["symbol"], spec["exchange"])
    got = ib.qualifyContracts(c)
    if not got or not getattr(got[0], "conId", 0):
        raise MacroError(f"IBKR could not identify {spec['symbol']} on {spec.get('exchange')}")
    return got[0]


def fetch_series(ib, mod, spec: dict, duration: str):
    """Daily bars for one instrument -> cleaned frame with the unfinished current-day bar removed."""
    contract = _contract(spec, mod, ib)
    bars = ib.reqHistoricalData(contract, endDateTime="", durationStr=duration, barSizeSetting="1 day",
                                whatToShow="TRADES", useRTH=True, formatDate=1)
    if not bars:
        raise MacroError("IBKR returned no bars (usually: no market-data subscription for this series)")
    df = snapshot.clean_bars(fetch_bars.bars_to_df(bars))
    df, _ = snapshot.drop_partial_bar(df)
    if len(df) < MIN_BARS:
        raise MacroError(f"only {len(df)} bar(s) returned")
    return df


def _one(ib, mod, spec: dict, duration: str) -> dict:
    """Real series, else stand-in, else UNAVAILABLE. Never raises."""
    attempts = []
    for variant, cand in (("real", spec), ("standin", spec.get("standin"))):
        if cand is None:
            continue
        try:
            df = fetch_series(ib, mod, cand, duration)
            return {"spec": spec, "variant": variant, "label": cand["label"], "df": df,
                    "why_not_real": "; ".join(attempts)}
        except Exception as e:                       # noqa: BLE001 - broker errors vary; reported in the file
            attempts.append(f"{cand['symbol']}: {e}")
    return {"spec": spec, "variant": "unavailable", "label": spec["label"], "df": None,
            "why_not_real": "; ".join(attempts)}


# ---------------------------------------------------------------- numbers

def summarize(df, yield_pct: bool = False) -> dict:
    close = df["close"]
    last, prev = float(close.iloc[-1]), float(close.iloc[-2])
    if yield_pct and last > 20:
        # Older CBOE yield indices quote the yield times 10 (42.5 = 4.25%). Undo that, and say so.
        close = close / 10.0
        last, prev = last / 10.0, prev / 10.0
        scaled = True
    else:
        scaled = False
    five = float(close.iloc[-FIVE_DAY_BARS]) if len(close) >= FIVE_DAY_BARS else None
    out = {"date": df.index[-1].strftime("%Y-%m-%d"), "close": round(last, 4), "scaled": scaled}
    if yield_pct:
        out["chg"] = round((last - prev) * 100.0, 1)                       # basis points
        out["chg5"] = None if five is None else round((last - five) * 100.0, 1)
    else:
        out["chg"] = round(last - prev, 4)
        out["pct"] = round((last / prev - 1.0) * 100.0, 2) if prev else None
        out["chg5"] = None if five is None else (round((last / five - 1.0) * 100.0, 2) if five else None)
    return out


def _num(x, nd: int = 2) -> str:
    """Negatives in brackets, like the desk's fundamentals file."""
    if x is None:
        return "n/a"
    return f"({abs(x):,.{nd}f})" if x < 0 else f"{x:,.{nd}f}"


def _row(r: dict) -> str:
    spec = r["spec"]
    if r["variant"] == "unavailable":
        return f"| {spec['label']} | UNAVAILABLE | - | - | - | - | {r['why_not_real']} |"
    s = r["stats"]
    if spec.get("yield_pct") and r["variant"] == "real":
        close = f"{_num(s['close'], 3)}%"
        c1, c5 = f"{_num(s['chg'], 1)} bp", ("n/a" if s["chg5"] is None else f"{_num(s['chg5'], 1)} bp")
        pct = "-"
    else:
        close = _num(s["close"], 2)
        c1 = _num(s["chg"], 2)
        pct = "n/a" if s.get("pct") is None else f"{_num(s['pct'], 2)}%"
        c5 = "n/a" if s["chg5"] is None else f"{_num(s['chg5'], 2)}%"
    if r["variant"] == "real":
        note = "IBKR, real series" + (" (index quoted x10, divided by 10)" if s["scaled"] else "")
    else:
        note = f"STAND-IN, not the real series. Real series failed: {r['why_not_real']}"
    return f"| {r['label']} | {s['date']} | {close} | {c1} | {pct} | {c5} | {note} |"


def render(results: list[dict], date: str, now: datetime) -> str:
    dates = sorted({r["stats"]["date"] for r in results if r["variant"] != "unavailable"})
    lines = [
        f"# Market and macro closes, US date {date}",
        f"Computed by script from the IBKR paper Gateway at {now.strftime('%Y-%m-%d %H:%M')} UTC. "
        "Daily closes only (the unfinished current-day bar is removed). These are the ONLY exact index, "
        "VIX, crude and yield figures you may quote; do not replace them with web numbers.",
        "",
        "| Instrument | Last close date | Close | 1-day change | 1-day % | 5-day change | Source |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [_row(r) for r in results]
    lines.append("")
    if len(dates) > 1:
        lines.append(f"WARNING: the latest bar dates differ ({', '.join(dates)}). A row with an older date is "
                     "stale (holiday, or a feed that has not updated): say so, do not present it as today's close.")
    if any(r["variant"] == "standin" for r in results):
        lines.append("A STAND-IN row is a fund that tracks the idea, not the series itself. Name it as a "
                     "stand-in when you use it.")
    if any(r["variant"] == "unavailable" for r in results):
        lines.append("An UNAVAILABLE row: get that line from WebSearch, date it, and mark it unconfirmed if you "
                     "cannot verify it.")
    lines.append("Negatives are in brackets. 'bp' = basis points (100 bp = 1 percentage point). 5-day change "
                 "compares the last close with the close five trading days earlier.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- run

def build(cfg: dict, date: str, base: Path | None = None, _ib=None, _mod=None,
          now: datetime | None = None) -> dict:
    ib_cfg = cfg["ibkr"]
    mcfg = cfg.get("macro", {})
    port = ib_cfg["port"]
    if port in fetch_bars.LIVE_PORTS:
        raise MacroError(f"port {port} is {fetch_bars.LIVE_PORTS[port]}; the desk uses paper ports only")
    if port not in fetch_bars.PAPER_PORTS:
        raise MacroError(f"port {port} is not a known paper port {sorted(fetch_bars.PAPER_PORTS)}")
    if _ib is None:
        try:
            import ib_async
        except ImportError as e:
            raise MacroError("ib_async is not installed in this Python") from e
        ib, mod = ib_async.IB(), ib_async
    else:
        ib, mod = _ib, _mod
    try:
        try:
            ib.connect(ib_cfg["host"], port, clientId=mcfg.get("client_id", 93),
                       timeout=ib_cfg.get("timeout_s", 15), readonly=True)
        except Exception as e:                           # noqa: BLE001
            raise MacroError(f"cannot connect to {ib_cfg['host']}:{port}: {e}") from e
        duration = mcfg.get("duration", "10 D")
        results = []
        for spec in INSTRUMENTS:
            r = _one(ib, mod, spec, duration)
            if r["df"] is not None:
                r["stats"] = summarize(r["df"], bool(spec.get("yield_pct")) and r["variant"] == "real")
            results.append(r)
    finally:
        try:
            ib.disconnect()
        except Exception:                                # noqa: BLE001
            pass
    ok = sum(r["variant"] == "real" for r in results)
    standin = sum(r["variant"] == "standin" for r in results)
    missing = [r["spec"]["key"] for r in results if r["variant"] == "unavailable"]
    if ok + standin == 0:
        raise MacroError("no instrument returned data: " + "; ".join(r["why_not_real"] for r in results))
    day = cfgmod.runs_dir(cfg, base) / date
    day.mkdir(parents=True, exist_ok=True)
    path = day / MACRO_DATA_FILE
    path.write_text(render(results, date, now or datetime.now(timezone.utc)), encoding="utf-8")
    return {"file": str(path), "real": ok, "standin": standin, "unavailable": missing}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=None, help="YYYY-MM-DD US market date; default today")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = cfgmod.load_config(a.config)
    date = cfgmod.norm_date(a.date) if a.date else cfgmod.default_run_date()
    try:
        res = build(cfg, date)
    except Exception as e:                               # noqa: BLE001
        print(f"MACRO FAILED: {e}")
        return 2
    print("MACRO " + json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
