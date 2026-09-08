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

Operations confirmed working: "greater" (>), "egreater" (>=), "less" (<),
"eless" (<=), and "in_range" (with `right` as a two-element [min, max] list,
inclusive at both ends). Column names are
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

THIS IS A PRE-MARKET SCREEN ONLY
--------------------------------
Every column here is a `premarket_*` one, and common/tv_feed.py stops at 09:30.
Correct for MCL, which trades 04:00-09:30 and nothing else. An all-day strategy
needs a different screen per session block -- the mapping is verified and
recorded in claude/session_aware_screening.md, along with the reason it is a
specification question rather than a tooling one.

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

# THE SCREEN, as of 2026-09-08 (Ben: "remove all the existing filters and
# only have the following", plus a volume floor added later that day). Three
# clauses.
#
#   1. pre-market price between $2 and $25
#   2. pre-market change >= 20%. TradingView's own definition, as Ben
#      supplied it 2026-09-08 (his final answer, after two corrections):
#
#          Pre-market Change  = premarket close - PREVIOUS REGULAR-SESSION close
#          Pre-market Change% = that / previous regular-session close * 100
#
#      i.e. the overnight GAP, including everything since yesterday's 16:00.
#      The column is `premarket_change`, verified to filter server-side on
#      2026-09-05. A name that gapped 30% at 04:00 and has been flat since
#      PASSES this -- that is what is wanted.
#
#      The sibling `premarket_change_from_open` measures movement since the
#      first pre-market print instead. It was the screen for one bundle
#      (2026-09-08q) and is NOT what Ben meant. Kept in COLUMNS so both
#      figures show on every row; the difference between them is the gap.
#
# Relative volume and float are GONE, not lowered. The previous screen's
# history is kept below because its findings about the columns were expensive
# and still hold.
#
# The $25 ceiling is the SCREEN's. The strategy's band is still $2-20
# (strategy/mcl/mcl.py PRICE_MAX): names at $20-25 appear in the watchlist as
# WARM and are refused at entry. That is deliberate -- tonight's paper data
# stays on the band the backtests measured. Widening the trader is a separate
# decision with a backtest behind it, not a side effect of a screen edit.
PREMARKET_CHANGE_MIN = 20.0            # Pre-mkt chg >= 20%  (vs previous regular close)
CHANGE_COLUMN = "premarket_change"
# 3. pre-market volume >= 100k shares (Ben, 2026-09-08). The one liquidity
#    clause on the screen: with relative volume and float gone, this is what
#    keeps a name that gapped 30% on three prints out of the watchlist.
#    premarket_volume is cumulative since 04:00, so it is tightest early and
#    loosens through the morning -- a name can fail it at 04:10 and pass at
#    06:00. That is the intended shape; HOT/WARM/COLD in tv_feed keeps a name
#    that later drops out rather than deleting it.
PREMARKET_VOLUME_MIN = 100_000
PREMARKET_PRICE_RANGE = (2.0, 25.0)    # Pre-mkt price  2 to 25 USD, inclusive

# Retained for day_over_day_only() and the record; NOT in the shipped screen.
RELATIVE_VOLUME_MIN = 5.0
PREMARKET_PRICE_MIN = PREMARKET_PRICE_RANGE[0]
FLOAT_RANGE = (0, 20_000_000)
VOLUME_CHANGE_MIN = (RELATIVE_VOLUME_MIN - 1.0) * 100.0

FILTERS = [
    {"left": CHANGE_COLUMN, "operation": "egreater",
     "right": PREMARKET_CHANGE_MIN},
    # in_range is inclusive at both ends -- confirmed 2026-09-05 with the
    # float filter, which used the same operation.
    {"left": "premarket_close", "operation": "in_range",
     "right": list(PREMARKET_PRICE_RANGE)},
    {"left": "premarket_volume", "operation": "egreater",
     "right": PREMARKET_VOLUME_MIN},
]

# Both change columns are returned so a row shows the gap AND the move since
# the open side by side -- the difference between them is the overnight gap.
COLUMNS = ["name", "premarket_change", "premarket_change_from_open",
           "premarket_close", "premarket_volume",
           "volume", "volume_change", "relative_volume_10d_calc",
           "float_shares_outstanding", "close"]

# volume_change stays in COLUMNS so the day-over-day figure is visible on
# every row for comparison, even though it does not filter.


def payload(limit: int = 50, cap_price: bool = False) -> dict:
    """The exact arguments to hand to the tvremix run_screener tool.

    cap_price narrows the price clause to the STRATEGY's band ($2-20) instead
    of the screen's ($2-25). Off by default: this function's job is to
    reproduce the screen as defined, not to quietly improve it.
    """
    filters = list(FILTERS)
    if cap_price:
        filters = [f for f in filters if f["left"] != "premarket_close"]
        filters.append({"left": "premarket_close", "operation": "in_range",
                        "right": [PRICE_MIN, PRICE_MAX]})
    return dict(market=MARKET, limit=limit, filters=filters,
                columns=COLUMNS, sort_by=CHANGE_COLUMN, sort_order="desc")


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
    screener response before believing it.

    Two response shapes reach this. The tvremix MCP tool wraps the server's
    reply under a "data" DICT; the raw scanner endpoint (common/tv_feed.py)
    returns "data" as the LIST of rows with ignored_filters beside it at the
    top level. The first version only knew the dict shape and raised
    AttributeError on the list -- which, in a feed that called it, would have
    turned every poll into a "screener call failed" backoff.
    """
    found: list[str] = []
    for level in (resp, resp.get("data")):
        if isinstance(level, dict):
            found += list(level.get("ignored_filters") or [])
    return found


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
    print("# All three filters apply server-side. Still check")
    print("# check_response() for ignored_filters on every call -- the server")
    print("# accepts unsupported clauses and silently drops them.")
    print()
    print(f"# MCL trades ${PRICE_MIN:.0f}-${PRICE_MAX:.0f}. This screen goes to "
          f"${PREMARKET_PRICE_RANGE[1]:.0f}, so rows above ${PRICE_MAX:.0f} are")
    print("# outside everything the backtest has measured. They surface as WARM")
    print("# in the watchlist and are refused at entry. Pass --capped to drop them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
