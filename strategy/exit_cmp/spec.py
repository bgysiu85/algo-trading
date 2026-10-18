#!/usr/bin/env python3
"""EXIT-CMP: every registered constant in one place. W15-0053 sub 2. REGISTERED_exit_cmp.md sec 4-10, 12.
Nothing here is tuned. A change after an outcome has been read is a new hypothesis (sec 11)."""
from __future__ import annotations

import zlib
from pathlib import Path

from exitmgr.rules import Params

STUDY = "W15-0053 EXIT-CMP"
ID = "w15_0053"
REGISTRATION = Path("docs") / "research" / "REGISTERED_exit_cmp.md"
LEDGER_FILE = "exit_cmp_ledger.json"
OUT_DIR = Path(r"D:\Trading\Claude outputs")

# sec 4: the fixed entry set (same pool as W15-0050; the clone spec holds the registered per-year counts)
TRADES_CSV_NAME = "w15_0032_chartmark_trades_base_20260930.csv"      # parity only (G2)
LABELS_FILE = "labels_chartmark_clone.csv"                           # candidate ids only (the Ben-takes slice)
BEN_TAKES_REGISTERED = 155

# sec 5
FLAT_HOUR = 16            # the 1H bar opening 16:00 NY closes at 17:00: flat at that close
HOLD_CAP = 120            # 1H bars after the entry bar (HOLD scenario)
SCENARIOS = ("FLAT", "HOLD")
HEADLINE_SCENARIO = "FLAT"
HEADLINE_SYM, HEADLINE_LEVEL = "MCL", "mid"

# sec 7 / 10
CONTROL_DRAWS = 1000
BOOTSTRAP_N = 2000
HALF_SPLIT = "2016-01-01"                     # criterion 3: 2010-06..2015-12 | 2016-01..2021-12 (by entry date)
NOT_READ_BELOW = 200                          # trigger count under which a rule set is NOT READ
GRID_MIN_POSITIVE = 6                         # of 9 cells

SCORED = ("R-BEN", "R-MOM", "X-ALERT-touch", "X-ALERT-close", "X-JUMP")
BASELINE = "B-STOP"
REFERENCE = "B-V1"
VARIANTS = ("R-BEN-EMA", "R-MOM+BEN", "X-JUMP-1R-half", "B-STOP-EMERG")

BASE = Params()
# sec 6 neighbour grids (9 cells each; the middle one is the registered base). Dimension values as registered.
GRIDS = {
    "R-BEN": (("ben_arm", (0.10, 0.20, 0.30)), ("ben_frac", (0.40, 0.50, 0.60))),
    "R-MOM": (("mom_run", (2, 3, 4)), ("mom_wick", (0.40, 0.50, 0.60))),
    "X-ALERT-touch": (("al_L", (3, 5, 8)), ("al_buf", (0.05, 0.10, 0.20))),
    "X-JUMP": (("jump_arm", (0.75, 1.0, 1.5)), ("jump_L", (2, 3, 4))),
}
GRID_ALSO = {"X-ALERT-touch": "X-ALERT-close"}      # "close reported beside it"

# the trigger that decides NOT READ, per rule set (names are the `fired` flags of exitmgr.rules)
TRIGGER = {"R-BEN": ("ratchet_armed",), "R-MOM": ("m1", "m2_placed"), "X-ALERT-touch": ("line_active",),
           "X-ALERT-close": ("line_active",), "X-JUMP": ("jump_armed",)}

TRAIN_FIRST, TRAIN_LAST = "2010-06-06", "2021-12-31"
WINDOWS = {"2014-07..2015-01": ("2014-07-01", "2015-01-31"), "2020-02..2020-06": ("2020-02-01", "2020-06-30")}
EMERGENCY = 0.60                                # sec 13 / 14 rail 3, CL / MCL


def draw_rng(draw: int, rule_id: str):
    """sec 7: np.random.default_rng([crc32(draw), crc32(b'EXIT-CMP'), crc32(rule_id)])."""
    import numpy as np
    return np.random.default_rng([zlib.crc32(str(draw).encode()), zlib.crc32(b"EXIT-CMP"), zlib.crc32(rule_id.encode())])


def boot_seed(rule_id: str) -> int:
    return zlib.crc32(("EXIT-CMP-BOOT-" + rule_id).encode())
