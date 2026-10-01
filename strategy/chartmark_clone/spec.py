#!/usr/bin/env python3
"""CHARTMARK-CLONE: every registered constant in one place. W15-0050 sub 2.
REGISTERED_chartmark_clone.md sec 3-5 (+ Amendment 1, PRE-LABEL). Nothing here is tuned; a change after a label exists is
a new hypothesis.

Implementation interpretations fixed here BEFORE the queue is built or any label exists (listed in Amendment 1):
  I1  candidate_id = the fill bar's open time, New York wall clock, 'YYYY-MM-DD HH:MM:SS' (the format of entry_t in the
      v1 trades CSV, which is how the manifest is checked against it -- entry_t is the ONLY column read from that file).
  I2  level = max over s in placed_j..fill_j-1 of (highest high of the E1 lookback ending at s + 1 tick): the value the
      engine's order state held at the close of the decision bar. The builder proves it for every fill:
      fill price == max(level, open of the fill bar), high of the fill bar >= level.
  I3  Trading day = 18:00 NY roll (wall clock + 6h, floor to date). A daily bar aggregates the 1H bars of one trading day.
  I4  F1 = +1 when the last completed daily close > daily EMA21 (SMA-seeded, strategy.htf.signals.ema_seeded), else -1.
      Warm-up (no daily EMA21 yet, or no completed day) counts as -1; the count is reported by the builder.
  I5  Queue: strata (year, F1) visited in ascending order; one numpy default_rng per queue, seeded by QUEUE_SEED_WORDS;
      for each stratum permutation first, then u. rank[perm[k]] = k; key = (rank + u) / n_stratum.
  I6  Repeat slot k (k = 1, 2, ...) follows the (10k)-th NEW candidate and exists iff 10k - 100 >= 1. Its target is drawn by
      default_rng([crc32(b'W15-0050-repeat'), k]) from queue positions 0 .. 10k-101 not already repeated.
  I7  labels file has one extra column, 'seq' (presentation index), appended after the registered columns; an UNDO row
      carries the seq of the decision it removes.
  I8  ms_to_decide = milliseconds from the chart appearing to the first T or S key.
  I9  Confidence is entered with K then 1/2/3 (digits alone choose the skip reason).
"""
from __future__ import annotations

import zlib

STUDY = "W15-0050 CHARTMARK-CLONE"
ID = "w15_0050"

# ---- pool (registration sec 3.1) ----
POOL_N = 2670
POOL_PER_YEAR = {2010: 132, 2011: 230, 2012: 240, 2013: 226, 2014: 219, 2015: 223,
                 2016: 217, 2017: 236, 2018: 220, 2019: 246, 2020: 231, 2021: 250}
TRADES_CSV_NAME = "w15_0032_chartmark_trades_base_20260930.csv"

# ---- queue / repeats (sec 3.2-3.3) ----
QUEUE_SEED_WORDS = [zlib.crc32(b"W15-0050"), zlib.crc32(b"CHARTMARK-CLONE")]
REPEAT_SEED_WORD = zlib.crc32(b"W15-0050-repeat")
REPEAT_EVERY = 10
REPEAT_MIN_GAP = 100

# ---- how much labelling (sec 3.4): counts only ----
MIN_UNIQUE, MIN_TAKES, MAX_UNIQUE = 500, 60, 1000

# ---- chart (sec 4) ----
N_1H = 120
N_DAILY = 60
DAY_ROLL_HOURS = 6                     # 18:00 NY roll

# ---- label schema (sec 5) ----
SKIP_REASONS = {
    "1": "Against the daily trend",
    "2": "Already run too far (extended)",
    "3": "Chop / quiet (tangled EMAs, low volume)",
    "4": "Momentum weak or fading (MACD)",
    "5": "Order too far above price / risk too big",
    "6": "Scheduled event hour (e.g. Wed inventory report)",
    "7": "Other (type a few words)",
}
TAKE_REASONS = {
    "A": "Fresh momentum turn (EMA/MACD cross)",
    "B": "Breakout from a range",
    "C": "Trend continuation",
    "D": "Other",
}
LABELS = ("TAKE", "SKIP", "UNDO")
LABEL_COLUMNS = ["candidate_id", "queue_pos", "is_repeat", "label", "skip_reason", "take_reason", "note",
                 "confidence", "ms_to_decide", "sitting_id", "labelled_at_utc", "seq"]

# ---- files (written to the output folder, D:\Trading\Claude outputs by default) ----
MANIFEST_FILE = f"clone_manifest_{ID}.csv"
QUEUE_FILE = f"clone_queue_{ID}.csv"
LEDGER_FILE = f"clone_ledger_{ID}.json"
LABELS_FILE = "labels_chartmark_clone.csv"
FRAME_CACHE_FILE = f"clone_frame_{ID}.npz"        # goes to var/ (gitignored)
MANIFEST_COLUMNS = ["candidate_id", "decision_t", "decision_idx", "level", "year", "daily_trend"]
QUEUE_COLUMNS = ["queue_pos", "candidate_id", "key"]

# ---- the fit (sub 4; REGISTERED sec 8 + Amendment 2, PRE-RUN) ----
CV_SEED_WORD = zlib.crc32(b"W15-0050-cv")
CV_REPEATS, CV_FOLDS, INNER_FOLDS = 5, 5, 5
RULE_MIN_USES = 15
EVENT_CELL_MIN = 3
FIDELITY_RECALL, FIDELITY_PRECISION = 0.75, 0.50
LOGIT_C_GRID = (0.01, 0.1, 1.0)
FROZEN_FILE = f"clone_frozen_{ID}.json"
FEATURE_TABLE_FILE = f"clone_features_{ID}.csv"
FIT_REPORT_FILE = f"clone_fit_report_{ID}.txt"
FAMOUS_WINDOWS = (("2014-07-01", "2015-01-31"), ("2020-02-01", "2020-06-30"))
