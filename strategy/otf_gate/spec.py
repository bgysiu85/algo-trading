"""OTF-G v1 fixed numbers. REGISTERED_otf_gate.md (W15-0025). Nothing here is tuned."""
from __future__ import annotations

UP, DOWN, BAL, UNDEF = 1, -1, 0, 2      # timeframe state codes; UNDEF = no completed bar yet
LONG, SHORT = 1, -1

TIMEFRAMES = ("M", "W", "D")            # monthly, weekly, daily (report order; the gate needs all three)

# sec 4 / sec 5
MIN_KEPT_A = 60                          # H-A (C1 Donchian) kept trades
MIN_KEPT_B = 150                         # H-B (ES + NQ ORB) kept trades
CR_DRAWS = 1000                          # sec 3, C-R
CR_SEED_TAG = 25                         # np.random.default_rng([crc32(str(draw)), crc32(cell), 25])
CR_PCT = 97.5                            # two scored hosts -> p97.5, not p95
HOLDOUT_P = 90                           # sec 6 holdout pass: >= p90 of C-R

# G5 reproduction targets (sec 0 / sec 5)
HA_HOST = ("C1", "single", "frac", 22129.0)        # spec, share, sizing, equity of the host rows
HA_TRADES = 1175
HA_NET_MID_ROUNDED = -847                           # ($847) at the old $1.25 mid
HB_TRADES = {"ES": 3443, "NQ": 3427}
HB_NET_L2_ROUNDED = {"ES": -14617, "NQ": -2384}    # NinjaTrader L2, W16-0003 (1 MES / 1 MNQ)

# H-B (sec 2.3)
HB_ROOTS = ("ES", "NQ")
HB_MAX_SWITCH_MINUTES = 5                # roll gap: the two 1-min bars must be <= 5 minutes apart
HB_MISSING_STOP = 0.01                   # G6: XNYS sessions missing > 1% in a year -> stop
CME_OPEN_SHIFT_HOURS = 6                 # 18:00 ET + 6h = 00:00 -> the trading-date label

FRICTIONS = ("low", "mid", "high")

# sec 2.5 variants: fixed now, reported, never ranked
VARIANTS = ("strict", "soft", "day_week", "live", "dalton", "naive", "opposite")
