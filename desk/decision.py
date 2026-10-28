r"""Check the portfolio manager's decision and log it.

The portfolio manager ends final_report.md with ONE fenced ```json block. This
module finds it, validates it against the run's verified snapshot and Ben's
paper rules, writes decision.json, and appends/replaces one row in
decisions.csv. That CSV is the input to the IBKR bridge (W18-0002) and the
8-week scorecard (W18-0004), so a malformed or absurd decision must be stopped
here, not discovered at order time.

    .\.venv\Scripts\python.exe -m desk.decision --ticker MPC [--date 2026-10-28]

Exit 0 = valid (warnings allowed), 2 = invalid (errors printed, nothing logged).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from desk import config as cfgmod
from desk import pipeline

RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
ACTIONABLE = ("Buy", "Overweight")       # long-only: the only ratings that open a position
CSV_COLUMNS = ["run_date", "ticker", "rating", "actionable", "conviction", "entry", "stop", "target",
               "horizon_days", "size_shares", "risk_per_share", "reward_risk", "last_close",
               "atr14", "warnings", "decided_at_utc"]

_FENCE = re.compile(r"```json\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict:
    blocks = _FENCE.findall(text)
    if not blocks:
        raise ValueError("no ```json block found at the end of final_report.md")
    try:
        obj = json.loads(blocks[-1])
    except json.JSONDecodeError as e:
        raise ValueError(f"the last ```json block is not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("the JSON block must be an object")
    return obj


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def validate(d: dict, ticker: str, run_date: str, snapshot: dict | None, rules: dict):
    """-> (errors, warnings, clean). `clean` is the normalised decision."""
    errors: list[str] = []
    warns: list[str] = []

    if str(d.get("ticker", "")).upper() != ticker:
        errors.append(f"ticker is {d.get('ticker')!r}, expected {ticker!r}")
    if str(d.get("run_date", "")) != run_date:
        errors.append(f"run_date is {d.get('run_date')!r}, expected {run_date!r}")

    rating = d.get("rating")
    rating = next((r for r in RATINGS if str(rating).strip().lower() == r.lower()), None)
    if rating is None:
        errors.append(f"rating must be one of {list(RATINGS)}")

    conv = d.get("conviction")
    if isinstance(conv, bool) or not isinstance(conv, int) or not 1 <= conv <= 10:
        errors.append("conviction must be a whole number 1-10")

    size = d.get("size_shares")
    want = rules.get("shares_per_symbol", 1)
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        errors.append("size_shares must be a whole number >= 0")
    elif size != want and rating in ACTIONABLE:
        errors.append(f"size_shares must be {want} (Ben's paper rule: {want} share per symbol)")

    hz = d.get("horizon_days")
    maxh = rules.get("max_hold_days", 180)
    if isinstance(hz, bool) or not isinstance(hz, int) or not 1 <= hz <= maxh:
        errors.append(f"horizon_days must be a whole number 1-{maxh}")

    for k in ("thesis",):
        if not isinstance(d.get(k), str) or not d.get(k, "").strip():
            errors.append(f"{k} must be a non-empty string")
    risks = d.get("key_risks")
    if not isinstance(risks, list) or not risks or not all(isinstance(x, str) and x.strip() for x in risks):
        errors.append("key_risks must be a non-empty list of strings")

    entry, stop, target = _num(d.get("entry")), _num(d.get("stop")), _num(d.get("target"))
    actionable = rating in ACTIONABLE
    rr = risk = None
    last = atr = None
    if snapshot:
        last = snapshot.get("price", {}).get("close")
        atr = snapshot.get("indicators", {}).get("atr14")

    if actionable:
        for name, v in (("entry", entry), ("stop", stop), ("target", target)):
            if v is None or v <= 0:
                errors.append(f"{name} must be a positive number for a {rating} (absolute price, not a percentage)")
        if not errors and entry is not None and stop is not None and target is not None:
            if not stop < entry:
                errors.append("stop must be below entry (long-only)")
            if not target > entry:
                errors.append("target must be above entry (long-only)")
        if entry and stop and target and stop < entry < target:
            risk = entry - stop
            rr = (target - entry) / risk
            if rr < 1.5:
                warns.append(f"reward:risk only {rr:.2f} (< 1.5)")
            if last and abs(entry / last - 1.0) > 0.08:
                warns.append(f"entry {entry} is {abs(entry / last - 1) * 100:.1f}% from the last close {last}")
            if atr:
                if risk < 0.75 * atr:
                    warns.append(f"stop is only {risk / atr:.2f} ATR from entry (likely to be noise-stopped)")
                if risk > 4.0 * atr:
                    warns.append(f"stop is {risk / atr:.2f} ATR from entry (very wide)")
    else:
        if any(v is not None for v in (entry, stop, target)):
            warns.append("entry/stop/target given for a non-buy rating; ignored (long-only, no position)")
        entry = stop = target = None

    clean = {
        "ticker": ticker, "run_date": run_date, "rating": rating, "actionable": actionable,
        "conviction": conv if isinstance(conv, int) else None,
        "entry": entry, "stop": stop, "target": target,
        "horizon_days": hz if isinstance(hz, int) else None,
        "size_shares": size if isinstance(size, int) else None,
        "risk_per_share": round(risk, 4) if risk else None,
        "reward_risk": round(rr, 3) if rr else None,
        "last_close": last, "atr14": atr,
        "thesis": d.get("thesis"), "key_risks": risks,
        "warnings": warns,
    }
    return errors, warns, clean


def _read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def log_decision(csv_path: Path, clean: dict, now: datetime | None = None) -> None:
    """Insert or replace the (run_date, ticker) row, atomically."""
    now = now or datetime.now(timezone.utc)
    row = {c: "" for c in CSV_COLUMNS}
    for c in CSV_COLUMNS:
        v = clean.get(c)
        if c == "warnings":
            v = " | ".join(v or [])
        row[c] = "" if v is None else v
    row["decided_at_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [r for r in _read_rows(csv_path)
            if not (r["run_date"] == clean["run_date"] and r["ticker"] == clean["ticker"])]
    rows.append(row)
    rows.sort(key=lambda r: (r["run_date"], r["ticker"]))
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = csv_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(csv_path)


def process(run_dir: Path, ticker: str, run_date: str, rules: dict, csv_path: Path):
    """-> (errors, warnings, clean). Writes decision.json + the CSV row only if valid."""
    report = run_dir / pipeline.FINAL_REPORT
    if not report.exists():
        return [f"{pipeline.FINAL_REPORT} does not exist in {run_dir}"], [], None
    try:
        raw = extract_json(report.read_text(encoding="utf-8"))
    except ValueError as e:
        return [str(e)], [], None
    snap = None
    sp = run_dir / "snapshot.json"
    if sp.exists():
        snap = json.loads(sp.read_text(encoding="utf-8"))
    errors, warns, clean = validate(raw, ticker, run_date, snap, rules)
    if errors:
        return errors, warns, None
    (run_dir / pipeline.DECISION_JSON).write_text(json.dumps(clean, indent=2), encoding="utf-8")
    log_decision(csv_path, clean)
    return [], warns, clean


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (US market date); default today")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = cfgmod.load_config(a.config)
    ticker = cfgmod.norm_ticker(a.ticker)
    date = cfgmod.norm_date(a.date) if a.date else cfgmod.default_run_date()
    rd = cfgmod.run_dir(cfg, date, ticker)
    csv_path = cfgmod.runs_dir(cfg) / pipeline.DECISIONS_CSV
    errors, warns, clean = process(rd, ticker, date, cfg["paper_rules"], csv_path)
    for w in warns:
        print(f"WARNING {ticker}: {w}")
    if errors:
        for e in errors:
            print(f"INVALID {ticker}: {e}")
        return 2
    print(f"OK {ticker} {clean['rating']} conviction {clean['conviction']}"
          + (f" entry {clean['entry']} stop {clean['stop']} target {clean['target']} "
             f"(reward:risk {clean['reward_risk']})" if clean["actionable"] else " (no position)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
