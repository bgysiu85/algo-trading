r"""W18-0003: the short phone summary of a desk run (Telegram, via the NAS).

    .\.venv\Scripts\python.exe -m desk.notify --date 2026-11-10 --expected "GM BTSG" [--dry-run]

Builds one compact message from decisions.csv for the date. Without --dry-run it uploads the text to the NAS
outbox; a DSM task there (deploy/nas_desk/send_outbox.py) sends it with the bot token the reminders sync already
holds, so no secret lives on the PC. The desk never places orders: the message says which buys are waiting.
"""
from __future__ import annotations

import argparse
import csv
import sys

from desk import config as cfgmod
from desk import pipeline, pull_nas, summary

MAX_LEN = 3500          # Telegram allows 4096


def build_message(date: str, rows: list[dict], expected: list[str], max_open: int,
                  watches: list[dict] | None = None, mode: str = "") -> str:
    ranked = summary.rank(rows, max_open)
    watching = [r for r in rows if summary.is_watch(r)]
    nopos = sorted(r["ticker"] for r in rows if str(r.get("actionable")).lower() != "true" and not summary.is_watch(r))
    decided = {r["ticker"] for r in rows}
    missing = [t for t in expected if t not in decided]
    head = f"Desk {date}" + (f" ({mode})" if mode else "") + f": {len(rows)} decided"
    if missing:
        head += f", {len(missing)} not finished"
    L = [head]
    if ranked:
        L.append("BUY (not ordered yet):")
        for r in ranked:
            L.append(f"- {r['ticker']} {r['rating']} {r['conviction']}/10 entry {r['entry']} stop {r['stop']} "
                     f"target {r['target']} R:R {r['reward_risk']}" + ("" if r["take"] else " (over cap)"))
        L.append("Orders are not placed automatically: run the bridge --check, then --place.")
    else:
        L.append("No buys today.")
    if watching:
        L.append("WATCH: " + "; ".join(f"{r['ticker']} {r['plan_trigger']} (revisit {r['plan_revisit_on']})" for r in watching))
    due = [w for w in (watches or []) if w.get("due") and w["ticker"] not in decided]
    if due:
        L.append("DUE, not run today: " + ", ".join(w["ticker"] for w in due))
    if nopos:
        L.append("No position: " + " ".join(nopos))
    if missing:
        L.append("NOT FINISHED: " + " ".join(missing) + " (re-run /desk next N)")
    warned = [f"{r['ticker']}: {r['warnings']}" for r in rows if r.get("warnings")]
    if warned:
        L.append("Warnings: " + " | ".join(warned))
    text = "\n".join(L)
    return text if len(text) <= MAX_LEN else text[: MAX_LEN - 20] + "\n...(cut)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=None)
    ap.add_argument("--expected", default="", help="space-separated tickers this run was meant to cover")
    ap.add_argument("--mode", default="")
    ap.add_argument("--dry-run", action="store_true", help="print the message, send nothing")
    ap.add_argument("--key", default=None)
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = cfgmod.load_config(a.config)
    date = cfgmod.norm_date(a.date) if a.date else cfgmod.default_run_date()
    path = cfgmod.runs_dir(cfg) / pipeline.DECISIONS_CSV
    if not path.exists():
        print("no decisions.csv yet")
        return 1
    with path.open("r", encoding="utf-8", newline="") as f:
        all_rows = [r for r in csv.DictReader(f) if r["ticker"] in cfg["tickers"]]
    rows = [r for r in all_rows if r["run_date"] == date]
    text = build_message(date, rows, a.expected.split(), cfg["paper_rules"]["max_open_positions"],
                         summary.open_watches(all_rows, date), a.mode)
    print(text)
    if a.dry_run:
        return 0
    return pull_nas.push_outbox(cfg, text, f"desk_{date}.txt", a.key)


if __name__ == "__main__":
    sys.exit(main())
