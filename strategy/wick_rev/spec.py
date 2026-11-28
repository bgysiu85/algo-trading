#!/usr/bin/env python3
"""WICK-REV constants. Every number here is fixed by docs/research/REGISTERED_wick_reversal.md
(W15-0063, committed 13d9516 + 1418297 Amendment A). Changing one after a result is a new hypothesis."""
from __future__ import annotations

from strategy.futbt.costs_ibkr import FEE_PER_SIDE, LEVEL_TICKS

# --- markets / timeframes (sec 2) -------------------------------------------------------------
# usd_per_point: dollars per 1.0 of price; tick: minimum price step; tick_usd: dollars per tick.
MARKETS = {
    "MCL": {"usd_per_point": 100.0, "tick": 0.01, "tick_usd": 1.0, "fee": FEE_PER_SIDE["MCL"]},
    # MNQ fee is not in costs_ibkr's table: the CME micro-equity all-in rate = the MES rate (0.62),
    # recorded as PRE-RUN Amendment B in the registration before any P&L was computed.
    "MNQ": {"usd_per_point": 2.0, "tick": 0.25, "tick_usd": 0.5, "fee": FEE_PER_SIDE["MES"]},
}
BAR_MINUTES = {"30m": 30, "1H": 60, "4H": 240}
# fixed display order (sec 5): never ranked
COMBOS = [("MCL", "30m"), ("MCL", "1H"), ("MCL", "4H"), ("MNQ", "30m"), ("MNQ", "1H"), ("MNQ", "4H")]
REPORTED_ONLY = {("MCL", "30m")}                     # Amendment A / G1b: too short for training
PRIMARY_COMBOS = [c for c in COMBOS if c not in REPORTED_ONLY]     # 5 combos x 2 directions = 10 tests
N_PRIMARY_TESTS = 2 * len(PRIMARY_COMBOS)            # 10

# --- definitions (sec 3) ----------------------------------------------------------------------
EMA_LEN = 20
ATR_LEN = 14
WARMUP = 200
UWR_CUT = 0.6                                        # primary group: wick ratio >= 0.6
BUCKET_EDGES = [i / 10 for i in range(11)]           # 0-0.1 ... 0.9-1.0
SIZE_EDGES = (0.75, 1.25)                            # small < 0.75 <= normal <= 1.25 < large
K_HEADLINE = 1.0
K_SIDE = (0.5, 1.5)
KS = (0.5, 1.0, 1.5)
LOOKAHEAD = 20                                       # race scans t+1 .. t+20
WINDOW = 3                                           # headline "next 1-3 bars"
CUM_BARS = (1, 2, 3, 5, 10, 20)
SESSION_MINUTES = 1380                               # 18:00 -> 17:00 ET; 17:00-18:00 bars are not traded
STAR_WICK_TO_BODY = 2.0                              # classic shape: wick >= 2 x body ...
STAR_RATIO = 2.0 / 3.0                               # ... and wick ratio >= 2/3

# --- costs (sec 4): IBKR per side, low = fee, mid = fee + 1 tick, high = fee + 2 ticks ---------
LEVELS = tuple(LEVEL_TICKS)                          # ("low", "mid", "high")


def side_cost(market: str, level: str) -> float:
    m = MARKETS[market]
    return round(m["fee"] + LEVEL_TICKS[level] * m["tick_usd"], 4)


# --- reading rule (sec 6) ----------------------------------------------------------------------
MIN_SIGNALS = 300
MAX_YEAR_SHARE = 0.25
CI_LEVEL_BONF = 0.995                                # 95% family-wise over 10 tests
CI_LEVEL = 0.95
BOOT_DRAWS = 2000

# --- windows (sec 8) ---------------------------------------------------------------------------
TRAIN_FROM = "2010-06-06"
TRAIN_TO = "2021-12-31"
HOLD_FROM = "2022-01-03"
HOLD_TO = "2025-09-22"
SEEN_FROM = "2025-09-23"

CANDIDATE = "WICK-REV"
LEDGER = "holdout_w15_0063.json"
REGISTRATION = "docs/research/REGISTERED_wick_reversal.md"
