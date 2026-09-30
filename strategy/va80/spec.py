"""VA80 v1 fixed numbers. REGISTERED_va80.md (W15-0025). Nothing here is tuned."""
from __future__ import annotations

TICK = 0.25                      # ES / NQ, index points
OPEN_MIN = 9 * 60 + 30           # 09:30 ET, minutes since midnight
DEADLINE_MIN = 15 * 60           # the acceptance must be complete by 15:00 (last bracket ENDS <= 15:00)
RANDOM_FROM_MIN = 10 * 60        # C-RT / C-ND entry bars start between 10:00 ...
RANDOM_TO_MIN = 15 * 60          # ... and 15:00
MAX_GAP_MIN = 5                  # a session with a gap > 5 minutes is skipped (and the one after it)

VA_SHARE = 0.70                  # primary
ACCEPT = 2                       # consecutive brackets that must close inside
BRACKET_MIN = 30

GRID_ACCEPT = (1, 2, 3)
GRID_LENGTH = (15, 30, 60)
GRID_SHARE = (0.60, 0.70, 0.80)
CENTRE = (ACCEPT, BRACKET_MIN, VA_SHARE)
GRID_MIN_POSITIVE = 18           # criterion 6: at least 18 of 27 cells net > $0 at mid

CR_DRAWS = 1000
CR_SEED_TAG = 80                 # default_rng([crc32(str(draw)), crc32(date), 80])
MIN_TRIGGERS = 200               # stop rule: fewer than 200 ES triggers on the training side
MIN_TRADES = 200                 # criterion 7: fewer than 200 trades -> NOT READ

ABOVE, BELOW, INSIDE = "above", "below", "inside"
LONG, SHORT = 1, -1
TARGET, STOP, TIME = "target", "stop", "time"
