r"""W18-0003: which tickers does today's scheduled desk run cover?

Ben's rule (2026-11-07): ALL tickers once a week (a "full" day), and on every other
weekday only the ACTIVE names: a desk order that is still working or open, a buy that
was decided but never ordered, or a Hold whose watch plan is due (W18-0007).

    python -m desk.schedule --explain            # mode, tickers and the reason for each
    python -m desk.schedule --tickers            # space-separated tickers only (what /desk scheduled runs)
    python -m desk.schedule --date 2026-11-10

Tickers that already have a decision for the date are left out, so a re-run resumes.
Known gap until W18-0009 (fill and exit tracking): a PLACED order stays "active" until its
hold_until date, even if the entry never filled or the position already exited.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from desk import config as cfgmod
from desk import pipeline, status, summary

DEFAULT_FULL_WEEKDAY = 0            # Monday (US date): Sydney Tuesday morning, fresh orders for the Tuesday US open


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def full_run_day(cfg: dict, date: str) -> bool:
    wd = int(cfg.get("schedule", {}).get("full_run_weekday", DEFAULT_FULL_WEEKDAY))
    return datetime.strptime(cfgmod.norm_date(date), "%Y-%m-%d").weekday() == wd


def active_names(cfg: dict, date: str, base: Path | None = None) -> dict[str, str]:
    """ticker -> why it is active today."""
    runs = cfgmod.runs_dir(cfg, base)
    tickers = set(cfg["tickers"])
    decisions = [r for r in _read_csv(runs / pipeline.DECISIONS_CSV) if r["ticker"] in tickers]
    orders = [o for o in _read_csv(runs / pipeline.ORDERS_CSV) if o.get("ticker") in tickers]
    why: dict[str, str] = {}
    for o in sorted(orders, key=lambda o: o.get("logged_at_utc", "")):
        if o.get("outcome") == "PLACED" and (o.get("hold_until") or "9999-12-31") >= date:
            why[o["ticker"]] = f"desk order placed {o['run_date']}, working or open (hold until {o['hold_until']})"
    latest: dict[str, dict] = {}
    for r in sorted(decisions, key=lambda r: (r["run_date"], r.get("decided_at_utc", ""))):
        latest[r["ticker"]] = r
    for t, r in latest.items():
        if t not in why and str(r.get("actionable")).lower() == "true" and r["run_date"] < date:
            why[t] = f"buy decided {r['run_date']} but no order logged"
    for w in summary.open_watches(decisions, date):
        if w["due"] and w["ticker"] not in why:
            why[w["ticker"]] = f"watch plan due (revisit {w['plan_revisit_on']})"
    return why


def plan(cfg: dict, date: str, base: Path | None = None) -> dict:
    date = cfgmod.norm_date(date)
    pending = set(status.pending(cfg, date, base))
    if full_run_day(cfg, date):
        mode = "full"
        reasons = {t: "weekly full run" for t in cfg["tickers"] if t in pending}
    else:
        act = active_names(cfg, date, base)
        reasons = {t: act[t] for t in cfg["tickers"] if t in act and t in pending}
        mode = "active" if reasons else "none"
    return {"date": date, "mode": mode, "tickers": list(reasons), "reasons": reasons,
            "already_decided": [t for t in cfg["tickers"] if t not in pending]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--tickers", action="store_true", help="print only the tickers, space separated")
    ap.add_argument("--explain", action="store_true", help="print mode, tickers and reasons")
    a = ap.parse_args(argv)
    cfg = cfgmod.load_config(a.config)
    date = cfgmod.norm_date(a.date) if a.date else cfgmod.default_run_date()
    p = plan(cfg, date)
    if a.tickers:
        print(" ".join(p["tickers"]))
        return 0
    print(f"Desk schedule for {p['date']} (US date): mode {p['mode']}, {len(p['tickers'])} ticker(s)")
    for t, r in p["reasons"].items():
        print(f"  {t:<6} {r}")
    if p["already_decided"]:
        print(f"  already decided today: {' '.join(p['already_decided'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
