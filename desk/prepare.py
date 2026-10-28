r"""Step 0 for one ticker: get the numbers the agents will read. No LLM involved.

    .\.venv\Scripts\python.exe -m desk.prepare MPC
    .\.venv\Scripts\python.exe -m desk.prepare MPC --bars-csv D:\some\bars.csv   # no Gateway needed
    .\.venv\Scripts\python.exe -m desk.prepare MPC --skip-fundamentals

Writes into var/desk_runs/<US date>/<TICKER>/ : bars.csv, snapshot.json,
market_data.md, fundamentals_data.md, status.json. The last line printed is a
single JSON object (PREPARED {...}) the /desk skill reads.

Bars are essential: no bars -> exit 2 and the desk skips the ticker.
Fundamentals are best-effort: if SEC cannot be reached the file says so and the
fundamentals analyst falls back to web search.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from desk import config as cfgmod
from desk import fetch_bars, fundamentals, snapshot


def prepare(ticker: str, date: str, cfg: dict, bars_csv: str | None = None,
            skip_fundamentals: bool = False, base: Path | None = None,
            _fetch=None, _facts=None) -> dict:
    rd = cfgmod.run_dir(cfg, date, ticker, base)
    rd.mkdir(parents=True, exist_ok=True)
    status = {"ticker": ticker, "run_date": date, "bars": None, "fundamentals": None}

    # --- bars (essential)
    try:
        if bars_csv:
            df = fetch_bars.load_csv(bars_csv)
            src = f"csv:{bars_csv}"
        else:
            ib = cfg["ibkr"]
            fetch = _fetch or fetch_bars.fetch_daily_bars
            df = fetch(ticker, host=ib["host"], port=ib["port"], client_id=ib["client_id"],
                       duration=ib["duration"], timeout=ib["timeout_s"])
            src = f"ibkr:{ib['host']}:{ib['port']}"
        df = snapshot.clean_bars(df)
        df, dropped = snapshot.drop_partial_bar(df)
        snap = snapshot.build_snapshot(df, ticker, date, partial_dropped=dropped)
    except Exception as e:                       # noqa: BLE001 - reported, not hidden
        status["bars"] = f"FAILED: {e}"
        (rd / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        raise
    df.to_csv(rd / "bars.csv", encoding="utf-8")
    (rd / "snapshot.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
    (rd / "market_data.md").write_text(snapshot.render_market_markdown(snap), encoding="utf-8")
    status["bars"] = f"ok ({src}, {snap['bars']} bars, last {snap['last_bar_date']})"

    # --- fundamentals (best effort)
    asof = datetime.strptime(date, "%Y-%m-%d").date()
    if skip_fundamentals:
        status["fundamentals"] = "skipped"
        fmd = (f"# {ticker} fundamentals\nNot fetched (skipped). Use WebSearch/WebFetch on the latest filings "
               "and say figures are not script-verified.\n")
    else:
        try:
            if _facts is not None:
                facts, title = _facts(ticker)
            else:
                facts, title = fundamentals.fetch_facts(
                    ticker, cfgmod.runs_dir(cfg, base) / "_cache", cfg.get("sec_user_agent_env", "SEC_CONTACT"))
            summ = fundamentals.summarize(facts, asof)
            fmd = fundamentals.render_markdown(ticker, title, summ, asof)
            status["fundamentals"] = f"ok ({len(summ['metrics'])} metrics)" if summ["metrics"] else "empty"
        except Exception as e:                   # noqa: BLE001
            status["fundamentals"] = f"unavailable: {e}"
            fmd = (f"# {ticker} fundamentals\nSEC EDGAR data UNAVAILABLE ({e}).\n"
                   "Use WebSearch/WebFetch on the latest 10-K/10-Q or annual report, and state plainly that "
                   "figures are not script-verified.\n")
    (rd / "fundamentals_data.md").write_text(fmd, encoding="utf-8")
    (rd / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return {"dir": str(rd), "status": status, "close": snap["price"]["close"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ticker")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD US market date; default today")
    ap.add_argument("--bars-csv", default=None)
    ap.add_argument("--skip-fundamentals", action="store_true")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = cfgmod.load_config(a.config)
    ticker = cfgmod.norm_ticker(a.ticker)
    date = cfgmod.norm_date(a.date) if a.date else cfgmod.default_run_date()
    try:
        res = prepare(ticker, date, cfg, a.bars_csv, a.skip_fundamentals)
    except Exception as e:                       # noqa: BLE001
        print(f"PREPARE FAILED {ticker}: {e}")
        return 2
    print("PREPARED " + json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
