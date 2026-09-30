#!/usr/bin/env python3
"""CHARTMARK-v2 (long): every registered constant in one place. W15-0036 sub 2.
REGISTERED_chartmark_v2.md sec 2 + Amendments 1-4 (all PRE-RUN). Nothing here is tuned; a change after a result is a new hypothesis.

Interpretations fixed here BEFORE any count or return was computed on the training bars (listed in the handover):
  J1  Arm/level maths is the seen-window prototype's (Claude outputs/w15_0036_v2_seen_proto_live.py), made a module.
  J2  Live level: P-conditions use bar t's EMA/MACD/signal and ATR[t]; each is solved for the price P of bar t+1 and taken
      +1 tick (Amendment 1.1); the level is ceil-to-tick of the highest of all terms.
  J3  Fill-bar backstop: taken as hit whenever low[j] <= backstop (sec 2.4 reduces to this: both of its branches hit).
      Exit price = the backstop level. Counted as BACKSTOP-fillbar.
  J4  EMA21 exit is evaluated from the bar AFTER the fill; breaches in the fill bar are not counted (sec 2.5).
  J5  Clause counting in the pre-flight is exclusive by priority 1, 2, 3 (any-true counts are also reported).
  J6  V-WICK: the wick breach at bar k (low[k] < EMA21[k-1]) is known intrabar; clauses 2/3 (MACD) are read on the bars
      ending k-1 (the last closed bar) so nothing from bar k's close is used. Exit fills at min(EMA21[k-1], open[k]);
      if the backstop also triggers in bar k, the higher trigger level fires first (tie: backstop).
  J7  V-REDTOP = sec 2.2-2.3 with the Amendment-2 red level, no previous-high term, no live P-conditions; confirmation at the
      fill bar's close; not confirmed -> UNCONFIRMED exit at the next open; re-arm only after arming was false at a close.
  J8  V-CONFIRMED arms at the close of t only on A-fresh or B-confirmed (H[t] >= theta*ATR, H[t-1] < 0, gap widening);
      level = Amendment-2 red level (+ previous high when the candidate has it on); fills max(level, next open); no live terms.
      (L <= close[t] -> no order, as sec 2.1.)
  J9  V-WICKGATE: previous high + 1 tick is included only when >= 2 of the last 3 green bars (t-2..t) have an upper wick
      >= 50% of their range; a zero-range bar has no wick and does not count.
  J10 A roll (held_id changes between bars t and t+1) blocks a new order at t; an open position is carried through and pays
      two extra sides (the futbt convention; prices are difference-back-adjusted).
  J11 Data end -> exit at the last close.
  J12 The count 'orders' is order-bars: an order is recomputed and re-placed at every close while arming holds (sec 2.1).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from strategy.chartmark import spec as S1        # costs, MULT, per_side: unchanged (sec 4 / v1 Amendment A.3)

TICK = S1.TICK
MULT, FEE, LEVELS, per_side = S1.MULT, S1.FEE, S1.LEVELS, S1.per_side
ATR_LEN = S1.ATR_LEN

NEAR_MACD = 0.05        # B "within reach": MACD within 0.05 ATR of its signal (sec 2.1)
NEAR_GAP = 0.10         # A-early: EMA9 within 0.10 ATR of EMA21
PAR_BARS = 6            # B: EMA9 above EMA21 for >= 6 bars
RED_LOOK = 10           # red-candle lookback t-9..t
FRESH_MAX = 3           # A-fresh: EMA9 above EMA21 for 1-3 bars
EMA_WINDOW = 4          # 2nd breach within 4 bars (k-3..k-1)
BELOW_N = 5             # H < 0 on each of 5 bars
ACCEL_N = 3             # H < 0 on 3 bars and the gap widening each bar, each widening larger
WICK_FRAC = 0.5         # V-WICKGATE
SESSION_FIRST, SESSION_LAST = 2, 12

# Amendment 4.2 / 4.3: the two windows (NY entry date)
DEV_FIRST, DEV_LAST = "2010-06-06", "2015-12-31"
CONF_FIRST, CONF_LAST = "2016-01-01", "2021-12-31"
MIN_TRADES_WINDOW = 75  # Amendment 4.2 / 4.7


@dataclass(frozen=True)
class Params:
    prev_high: bool = True         # Amendment 3 (K1/K2 on, K3/K4 off)
    theta: float = 0.05            # B: H(P) >= theta * ATR[t]
    backstop: float = 0.60         # dollars below the fill
    backstop_atr: float | None = None   # V-STOPATR: multiple of ATR[t]; overrides backstop
    session: bool = False          # V-SESSION
    wick: bool = False             # V-WICK
    confirmed: bool = False        # V-CONFIRMED
    redtop: bool = False           # V-REDTOP
    wickgate: bool = False         # V-WICKGATE
    avoid: bool = False            # V-AVOID
    par_bars: int = PAR_BARS       # grid: {4, 6, 8}
    ema_window: int = EMA_WINDOW   # grid: {3, 4, 5} (2nd breach within this many bars)


K1 = Params(prev_high=True, theta=0.05)
K2 = Params(prev_high=True, theta=0.03)
K3 = Params(prev_high=False, theta=0.05)
K4 = Params(prev_high=False, theta=0.03)
CANDIDATES = {"K1": K1, "K2": K2, "K3": K3, "K4": K4}


def variants_of(base: Params) -> dict[str, Params]:
    """Amendment 4.5: variants are applied to the step-C winner, reported, never selectable."""
    return {
        "V-THETA03": replace(base, theta=0.03),
        "V-WICK": replace(base, wick=True),
        "V-STOP20": replace(base, backstop=0.20),
        "V-STOPATR": replace(base, backstop_atr=1.0),
        "V-SESSION": replace(base, session=True),
        "V-CONFIRMED": replace(base, confirmed=True),
        "V-AVOID": replace(base, avoid=True),
        "V-REDTOP": replace(base, redtop=True),
        "V-WICKGATE": replace(base, wickgate=True),
    }


GRID_PAR = (4, 6, 8)
GRID_STOP = (0.40, 0.60, 0.80)
GRID_EMA = (3, 4, 5)
