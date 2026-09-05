#!/usr/bin/env python3
"""Ben's TradingView pre-market screen, as a reproducible call.

    python -m common.tv_screener --json          # print the payload to send
    python -m common.tv_screener --check-band    # flag rows MCL cannot trade

WHY THIS FILE EXISTS
--------------------
The screen lives in Ben's TradingView account as a saved Screener. Nothing in
this repo could reach it -- the tvremix MCP exposes saved watchlists, alerts,
charts and portfolios, but not saved screeners -- so it was reproduced from
its filter panel and pinned here. That turns a thing you click into a thing
that can be diffed, versioned, and compared against what the backtest assumes.

THE FILTER SYNTAX, which PROGRAM_INDEX recorded as unresolved
-------------------------------------------------------------
run_screener takes `filters` as a list of TradingView-native clauses:

    {"left": <column>, "operation": <op>, "right": <value>}

Operations confirmed working: "greater", "less", "egreater", "eless",
"in_range" (with `right` as a two-element [min, max] list). Column names are
TradingView's internal ones, not the labels shown in the UI -- the mapping
below is the part that took the guessing.

    UI label            column
    ----------------    ------------------------------
    Pre-mkt chg %       premarket_change
    Pre-mkt price       premarket_close
    Rel vol             relative_volume_10d_calc
    Float               float_shares_outstanding
    (pre-mkt volume)    premarket_volume

WHICH RELATIVE VOLUME. Settled 2026-09-05 on relative_volume_10d_calc, the
column the saved screen uses. A day-over-day version was tried and reverted;
the findings are kept because they are not obvious and would otherwise be
rediscovered the hard way.

TradingView has no 1-day relative-volume column. What it has:

    relative_volume            volume / average_volume_10d_calc  (whole day)
    relative_volume_10d_calc   the same, TIME-OF-DAY ADJUSTED over 10 days
    relative_volume_intraday|5 the same, adjusted, over 5 days
    volume_change              PERCENT change vs the PREVIOUS DAY's volume

Only the last is a comparison against one day ago. Verified on names where the
answer is checkable: NVDA +0.50%, AAPL +6.39%, GOOGM -91.2% -- a plain
day-over-day percent, not a ratio.

THE UNIT TRAP, if it is ever used: it is a percent CHANGE, so "5x yesterday"
is volume_change > 400, not > 500. 500 would be six times.

THE SILENT-FAILURE TRAP, which is worse and nearly cost this file its point:
**volume_change cannot be used as a FILTER.** The server accepts the clause,
returns a perfectly plausible result set, and simply does not apply it -- the
only evidence is an `ignored_filters` key in the response. Sent with the other
three it returned three rows including one at +266% when the threshold was
+400%, i.e. exactly the rows the other three filters produce on their own.

Checked either way round: `relative_volume` filters normally (19,959 rows ->
629), `volume_change` does not (19,959 -> 19,959, ignored).

That is the reason the day-over-day version could not simply replace this one
server-side, and it generalises: ALWAYS read `ignored_filters` on a screener
response before trusting the rows. check_response() below does it.
relative_volume_10d_calc, the column actually used, filters correctly.

AND THE REASON THE 10-DAY COLUMN IS THE RIGHT ONE for a PRE-MARKET screen: it
is adjusted for time of day, so "5x" means the same thing at 04:30 as at
09:00. volume_change is not -- it compares today's volume SO FAR against
yesterday's FULL day, so a screen built on it is tightest at the start of
pre-market and loosens through the morning. For a 04:00-09:30 strategy that is
a moving goalpost.

VERIFIED against the live server 2026-09-05.

THE GAP WORTH KNOWING ABOUT
---------------------------
The screen has NO UPPER PRICE BOUND -- "Pre-mkt price > 2 USD" and nothing
above. Every MCL backtest enforces $2-20 (strategy/mcl/mcl.py PRICE_MIN /
PRICE_MAX), and brokers/ibkr/scanner.py screens on the same band. So this
screen can legitimately surface a $60 stock that the backtest has never
modelled. --check-band flags those rather than silently dropping them, because
which way to resolve it is Ben's call: widen the backtest, or cap the screen.
"""
from __future__ import annotations

import argparse
import json

from strategy.mcl.mcl import PRICE_MIN, PRICE_MAX

MARKET = "america"

# The saved screen, one clause per row of the TradingView filter panel.
PREMARKET_CHANGE_MIN = 20.0        # Pre-mkt chg  > 20%
RELATIVE_VOLUME_MIN = 5.0          # Rel vol      > 5  (10-day, time-adjusted)
PREMARKET_PRICE_MIN = 2.0          # Pre-mkt price > 2 USD
FLOAT_RANGE = (0, 20_000_000)      # Float        0 to 20M

# Only for the day-over-day alternative, which is NOT the shipped screen.
# volume_change is a percent change, so 5x yesterday is +400%, not +500%.
VOLUME_CHANGE_MIN = (RELATIVE_VOLUME_MIN - 1.0) * 100.0

# All four apply server-side. Confirmed, not assumed -- see check_response().
FILTERS = [
    {"left": "premarket_change", "operation": "greater",
     "right": PREMARKET_CHANGE_MIN},
    {"left": "relative_volume_10d_calc", "operation": "greater",
     "right": RELATIVE_VOLUME_MIN},
    {"left": "premarket_close", "operation": "greater",
     "right": PREMARKET_PRICE_MIN},
    {"left": "float_shares_outstanding", "operation": "in_range",
     "right": list(FLOAT_RANGE)},
]

COLUMNS = ["name", "premarket_change", "premarket_close", "premarket_volume",
           "volume", "volume_change", "relative_volume_10d_calc",
           "float_shares_outstanding", "close"]

# volume_change stays in COLUMNS so the day-over-day figure is visible on
# every row for comparison, even though it does not filter.


def payload(limit: int = 50, cap_price: bool = False) -> dict:
    """The exact arguments to hand to the tvremix run_screener tool.

    cap_price adds the $20 ceiling the backtest assumes but the saved screen
    does not have. Off by default: this function's job is to reproduce the
    screen as saved, not to quietly improve it.
    """
    filters = list(FILTERS)
    if cap_price:
        filters.append({"left": "premarket_close", "operation": "less",
                        "right": PRICE_MAX})
    return dict(market=MARKET, limit=limit, filters=filters,
                columns=COLUMNS, sort_by="premarket_change", sort_order="desc")


def day_over_day_only(rows: list[dict]) -> list[dict]:
    """The rejected alternative, kept runnable: rows whose volume is
    RELATIVE_VOLUME_MIN x yesterday's. Not part of the shipped screen -- it has
    to be applied here because volume_change cannot filter server-side."""
    out = []
    for r in rows:
        vc = r.get("volume_change")
        if vc is not None and vc > VOLUME_CHANGE_MIN:
            out.append(r)
    return out


def check_response(resp: dict) -> list[str]:
    """Return any filters the server admitted to ignoring. Call this on every
    screener response before believing it."""
    data = resp.get("data", resp)
    return list(data.get("ignored_filters") or [])


def out_of_band(rows: list[dict]) -> list[dict]:
    """Rows this screen returns that MCL's backtest would refuse to trade."""
    bad = []
    for r in rows:
        px = r.get("premarket_close")
        if px is None or not (PRICE_MIN <= px <= PRICE_MAX):
            bad.append(r)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="Ben's TradingView pre-market screen")
    ap.add_argument("--json", action="store_true",
                    help="print the run_screener payload")
    ap.add_argument("--capped", action="store_true",
                    help="add the $20 ceiling the MCL backtest assumes")
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()

    if a.json or True:
        print(json.dumps(payload(a.limit, a.capped), indent=2))
    print()
    print("# All four filters apply server-side. Still check")
    print("# check_response() for ignored_filters on every call -- the server")
    print("# accepts unsupported clauses and silently drops them.")
    print()
    print(f"# MCL trades ${PRICE_MIN:.0f}-${PRICE_MAX:.0f}. This screen has no "
          f"upper bound, so rows above ${PRICE_MAX:.0f} are outside")
    print("# everything the backtest has measured. Pass --capped to add it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
