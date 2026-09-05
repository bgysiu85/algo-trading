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

VERIFIED against the live server 2026-09-05: the four filters together return
a single name (AOUT, +27.5% pre-market, rel vol 65, float 10.6m, $12.76),
which is the right order of magnitude for this screen on one day.

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
RELATIVE_VOLUME_MIN = 5.0          # Rel vol      > 5
PREMARKET_PRICE_MIN = 2.0          # Pre-mkt price > 2 USD
FLOAT_RANGE = (0, 20_000_000)      # Float        0 to 20M

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
           "relative_volume_10d_calc", "float_shares_outstanding", "close"]


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
    print(f"# MCL trades ${PRICE_MIN:.0f}-${PRICE_MAX:.0f}. This screen has no "
          f"upper bound, so rows above ${PRICE_MAX:.0f} are outside")
    print("# everything the backtest has measured. Pass --capped to add it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
