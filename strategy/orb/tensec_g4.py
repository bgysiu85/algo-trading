#!/usr/bin/env python3
r"""G4 (W05-0003, `docs/research/REGISTERED_10sec.md` section 0 gate G4 and
section 6.1) -- price, then pull, XNAS.ITCH MBP-1 windows around every T1
(H-X1) trigger, for H-Q1 (order-book imbalance).

    python -m strategy.orb.tensec_g4                 # price only (default)
    python -m strategy.orb.tensec_g4 --confirm        # price, then pull

PRECONDITION: step 5 (H-X1) has run and `var/cache/orb_sip/tensec_hx1_trades.csv.gz`
exists (board W05-0003 subitem 5, Done 2026-09-24, verdict NOT ADOPTABLE for
H-X1 itself -- H-Q1 is unaffected by that verdict and is scored separately,
per the parent item's Update on this board).

WHAT THIS DOES, EXACTLY
------------------------
One window per T1 trade (`t1_why == "OK"`) inside H-Q1's in-sample population
(REGISTERED_10sec.md section 6.1): every in-sample session from the plan edge
-- 365 days back from the day this pull runs -- through 2026-04-30. The
holdout (2026-05-01 onward) is never in `tensec_hx1_trades.csv.gz` to begin
with (it is built from the in-sample primary cell only), so nothing here can
touch it.

The window itself is fixed by the registration, not a parameter: 60 seconds
before the trigger bar STARTS to 60 seconds after it ENDS. `t1_trigger_sec`
is the trigger bar's start (seconds-of-day, America/New_York,
`strategy.orb.tensec_engine.SecTrade.trigger_sec`, T1 branch); the bar is
10 seconds wide, so the window is
    [trigger_sec - 60, trigger_sec + 10 + 60)   in ET, converted to UTC.

Dataset and schema are fixed by the registration too -- XNAS.ITCH mbp-1, not
a candidate comparison like `common.quote_price`'s AT-24 pull (that priced
several tapes against each other for a different study; this one already
knows which tape, section 3.3). Pricing and pulling machinery (window
dataclass, retry-on-blip pricing, skip-if-on-disk pull, manifest writer) is
reused from `common.quote_price` rather than re-implemented; only the window
construction and the report are specific to G4.

WHERE IT WRITES, AND WHY A SEPARATE SUBTREE
---------------------------------------------
`common.quote_price`'s own windows for AT-24 live at
`<archive>/XNAS.ITCH/mbp-1/windows/<day>/<symbol>.dbn.zst` -- a DIFFERENT
window per day/symbol (10 min before/5 min after each thin-tape entry) than
this gate needs (60 s before/after a T1 trigger). Reusing that exact path
scheme would either collide on disk (same day/symbol, wrong window) or,
worse, silently look "already pulled" and skip a window this gate actually
needs. So G4 writes to its own subtree,
`<archive>/g4_10sec/XNAS.ITCH/mbp-1/windows/<day>/<symbol>.dbn.zst`,
namespaced by study, never by the two studies' shared dataset/schema alone.

SPENDING GUARDS (unchanged from `common.quote_price` / `common.databento_fetch`)
----------------------------------------------------------------------------------
  * every run prices first and prints the total (section 0, G4: "Run without
    --confirm first; if not $0.00 it stops for Ben");
  * nothing downloads without --confirm;
  * --confirm re-prices in the same run and refuses above --max-cost
    (default $0.00 -- any nonzero total is a decision for Ben, not this
    script);
  * windows already on disk are skipped, so a re-run is free;
  * the key comes from DATABENTO_API_KEY (via `common.databento_fetch`,
    op:// resolved), is never an argument and is never printed.

Reads:
  var/cache/orb_sip/tensec_hx1_trades.csv.gz   T1 trigger list (step 5)

Writes:
  var/reports/tensec_g4_RESULT.txt                     this module's report
  <archive>/g4_10sec/XNAS.ITCH/mbp-1/windows/<day>/<symbol>.dbn.zst   pulled quotes
  <archive>/g4_10sec/XNAS.ITCH/mbp-1/windows/manifest.json            window index
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.quote_price import Window, money, plan_edge, price, pull, write_manifest
from common.report_io import emit

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

TRADES_DEFAULT = Path("var/cache/orb_sip/tensec_hx1_trades.csv.gz")
REPORT = Path("var/reports/tensec_g4_RESULT.txt")
DATASET = "XNAS.ITCH"
SCHEMA = "mbp-1"
BEFORE_SEC = 60
AFTER_SEC = 60
TRIGGER_BAR_SEC = 10       # a T1 trigger bar is always 10 seconds wide
STUDY_SUBDIR = "g4_10sec"  # keeps this pull off common.quote_price's own tree


def load_trades(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        sys.exit(f"{p} not found. It is written by step 5:\n"
                 "  python -m strategy.orb.tensec_hx1 --jobs 8\n"
                 "and holds every T1 trade this study's triggers come from.")
    df = pd.read_csv(p)
    need = {"symbol", "date", "t1_why", "t1_trigger_sec"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"{p} is missing columns {sorted(missing)}")
    return df


def trigger_window(day: str, trigger_sec: float) -> tuple[datetime, datetime]:
    """[trigger bar start - 60s, trigger bar end + 60s), ET -> UTC. Section
    3.2/6.1: the trigger bar is `t1_trigger_sec` for `TRIGGER_BAR_SEC`
    seconds; the window is 60s either side of the BAR, not the fill."""
    sod = int(trigger_sec)
    d = date.fromisoformat(day)
    bar_start = datetime(d.year, d.month, d.day, tzinfo=ET) + timedelta(seconds=sod)
    bar_end = bar_start + timedelta(seconds=TRIGGER_BAR_SEC)
    lo = bar_start - timedelta(seconds=BEFORE_SEC)
    hi = bar_end + timedelta(seconds=AFTER_SEC)
    return lo.astimezone(UTC), hi.astimezone(UTC)


def windows(df: pd.DataFrame, edge: date, holdout_start: date) -> list[Window]:
    """One window per OK T1 trigger, inside the plan edge and short of the
    holdout (section 6.1). `tensec_hx1_trades.csv.gz` is in-sample-only
    already, so the holdout check is a belt-and-braces guard, not load-
    bearing -- if it ever trips, that file has changed shape and this
    should be looked at before pulling anything."""
    ok = df[df["t1_why"] == "OK"].copy()
    ok["_date"] = pd.to_datetime(ok["date"]).dt.date
    ok = ok[(ok["_date"] >= edge) & (ok["_date"] < holdout_start)]
    out = []
    for r in ok.itertuples():
        lo, hi = trigger_window(r.date, r.t1_trigger_sec)
        out.append(Window(r.symbol, r.date, lo, hi, entries=1, books={"t1"}))
    return sorted(out, key=lambda w: (w.day, w.symbol))


def head(all_ok: int, ws: list[Window], df: pd.DataFrame, edge: date,
         holdout_start: date) -> list[str]:
    n_total = len(df)
    n_ok = int((df["t1_why"] == "OK").sum())
    days = sorted({w.day for w in ws})
    span = sum((w.end - w.start).total_seconds() for w in ws)
    return [
        "G4 -- PRICE THEN PULL XNAS.ITCH MBP-1 AT T1'S IN-WINDOW TRIGGERS "
        "(W05-0003, REGISTERED_10sec.md gate G4)", "",
        f"  source        {TRADES_DEFAULT}",
        f"  T1 trades     {n_total:,} rows, {n_ok:,} OK (trigger fired)",
        f"  plan edge     {edge} (last 365 days)",
        f"  holdout       {holdout_start} onward excluded (not in this file anyway)",
        f"  in window     {len(ws):,} OK triggers, {len(days)} sessions, "
        f"{days[0] if days else '-'} .. {days[-1] if days else '-'}",
        f"  window        {BEFORE_SEC}s before the trigger bar starts to "
        f"{AFTER_SEC}s after it ends ({TRIGGER_BAR_SEC}s bar)",
        f"  total span    {span/60:,.0f} minutes ({span/max(len(ws),1):.0f}s per window)",
        "",
    ]


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--trades", default=str(TRADES_DEFAULT))
    ap.add_argument("--confirm", action="store_true",
                     help="price, then pull -- refuses above --max-cost")
    ap.add_argument("--max-cost", type=float, default=0.00)
    ap.add_argument("--archive", default=None)
    ap.add_argument("--report", default=str(REPORT))
    ap.add_argument("--holdout-start", default="2026-05-01")
    return ap.parse_args(argv)


def main(argv=None, *, client=None, today: date | None = None) -> int:
    a = parse(argv)
    from common import databento_fetch as F

    df = load_trades(a.trades)
    edge = plan_edge(today or date.today())
    holdout_start = date.fromisoformat(a.holdout_start)
    ws = windows(df, edge, holdout_start)

    L = head(len(df), ws, df, edge, holdout_start)
    if not ws:
        emit("\n".join(L + ["  Nothing to price -- no OK T1 trigger falls "
                            "inside the plan edge."]), a.report)
        return 1

    if client is None:
        db = F.require_databento()
        client = db.Historical(F._key())
    scrub = F._scrub

    print(f"pricing {DATASET} {SCHEMA}, {len(ws):,} windows ...", flush=True)
    p = price(client, DATASET, SCHEMA, ws, scrub=scrub)
    L += [f"PRICING: {DATASET} {SCHEMA}", "",
          f"  priced        {p.n:,} of {len(ws):,} windows ({p.failed} failed)",
          f"  cost          {money(p.usd)}",
          f"  size          {p.nbytes/1e9:,.2f} GB",
          f"  paid windows  {p.paid:,}" + (f"  (dates {min(p.paid_days)} .. "
                                          f"{max(p.paid_days)})" if p.paid_days else ""),
          ""]
    if p.failed:
        L.append(f"  first error: {p.first_error}")
        L.append("")

    if not a.confirm:
        L += ["Nothing downloaded. Ben: if the cost above is $0.00, pull "
              "exactly this:", "",
              "  python -m strategy.orb.tensec_g4 --confirm", "",
              "If it is NOT $0.00, this stops here per section 0 (G4) -- "
              "tell the chat before running --confirm."]
        emit("\n".join(L), a.report)
        return 0

    if p.failed:
        emit("\n".join(L + ["REFUSED: some windows did not price, so the "
                            "total above is not the whole cost."]), a.report)
        return 2
    if p.usd > a.max_cost + 1e-9:
        emit("\n".join(L + [f"REFUSED: {money(p.usd)} is above --max-cost "
                            f"{money(a.max_cost)}. Nothing downloaded. This "
                            f"is a decision for Ben (section 0, G4)."]), a.report)
        return 2

    root = Path(a.archive) if a.archive else F.default_archive()

    # pull() (from common.quote_price) writes to root/dataset/schema/windows/...;
    # namespacing this study means handing it root/STUDY_SUBDIR instead, so the
    # files land under <archive>/g4_10sec/XNAS.ITCH/mbp-1/windows/... (see
    # module docstring) rather than colliding with AT-24's own tree.
    study_root = root / STUDY_SUBDIR
    got, skipped, errors = pull(client, DATASET, SCHEMA, ws, study_root, scrub=scrub)
    man = write_manifest(study_root, DATASET, SCHEMA, ws,
                         BEFORE_SEC // 60, AFTER_SEC // 60)
    L += ["PULLED", "",
          f"  new           {got:,}",
          f"  on disk       {skipped:,} (skipped, free)",
          f"  errors        {len(errors):,}",
          f"  archive       {study_root / DATASET / SCHEMA / 'windows'}",
          f"  manifest      {man}", ""]
    L += [f"  {e}" for e in errors[:20]]
    emit("\n".join(L), a.report)
    return 0 if not errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
