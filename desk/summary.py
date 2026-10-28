r"""Rank one day's decisions and write SUMMARY.md.

Ben's rule: at most `max_open_positions` open at once; if more than that are
buys, the desk's own ranking decides. Ranking = conviction (high first), then
reward:risk (high first), then ticker (so ties are stable). The top N
actionable names are marked TAKE, the rest WAIT. This ranks; it places nothing.

    .\.venv\Scripts\python.exe -m desk.summary [--date 2026-10-28]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from desk import config as cfgmod
from desk import pipeline


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def rank(rows: list[dict], max_open: int) -> list[dict]:
    act = [r for r in rows if str(r.get("actionable")).lower() == "true"]
    act.sort(key=lambda r: (-_f(r["conviction"]), -_f(r["reward_risk"]), r["ticker"]))
    out = []
    for i, r in enumerate(act, 1):
        r = dict(r)
        r["rank"] = i
        r["take"] = i <= max_open
        out.append(r)
    return out


def render(date: str, rows: list[dict], missing: list[str], max_open: int) -> str:
    ranked = rank(rows, max_open)
    passed = sorted((r for r in rows if str(r.get("actionable")).lower() != "true"), key=lambda r: r["ticker"])
    L = [f"# Desk summary {date}", "",
         f"{len(rows)} decided, {len(ranked)} buys (Buy/Overweight), {len(passed)} no position; "
         f"max open positions {max_open}.", ""]
    if missing:
        L += [f"NOT DECIDED YET: {', '.join(missing)}", ""]
    if ranked:
        L += ["## Buys, ranked", "| # | Ticker | Rating | Conv | Entry | Stop | Target | R:R | Days | Action |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for r in ranked:
            L.append(f"| {r['rank']} | {r['ticker']} | {r['rating']} | {r['conviction']} | {r['entry']} | "
                     f"{r['stop']} | {r['target']} | {r['reward_risk']} | {r['horizon_days']} | "
                     f"{'TAKE' if r['take'] else 'WAIT (over the position cap)'} |")
        L.append("")
    if passed:
        L += ["## No position", "| Ticker | Rating | Conv |", "|---|---|---|"]
        L += [f"| {r['ticker']} | {r['rating']} | {r['conviction']} |" for r in passed]
        L.append("")
    warned = [r for r in rows if r.get("warnings")]
    if warned:
        L.append("## Warnings")
        L += [f"- {r['ticker']}: {r['warnings']}" for r in warned]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = cfgmod.load_config(a.config)
    date = cfgmod.norm_date(a.date) if a.date else cfgmod.default_run_date()
    csv_path = cfgmod.runs_dir(cfg) / pipeline.DECISIONS_CSV
    if not csv_path.exists():
        print("no decisions.csv yet")
        return 1
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["run_date"] == date and r["ticker"] in cfg["tickers"]]
    missing = [t for t in cfg["tickers"] if t not in {r["ticker"] for r in rows}]
    text = render(date, rows, missing, cfg["paper_rules"]["max_open_positions"])
    out = cfgmod.day_dir(cfg, date) / "SUMMARY.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
