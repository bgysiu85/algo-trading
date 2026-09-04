#!/usr/bin/env python3
"""
VW9 -- VWAP + 9 EMA momentum strategy. Pure logic, no broker, no I/O.

Implements exactly enough of claude/vw9_strategy_spec.md to answer §8.3
("Setup counts"): the regime gate (§3) and the two entry setups (§4.1 VWAP
reclaim, §4.2 9 EMA retest), evaluated WITHOUT the §4.3 gates (liquidity,
pullback-volume, extension, overhead headroom, re-entry cap). §8.3 explicitly
asks for triggers "before gates" -- this module is deliberately that, and
nothing more. It does not implement §5 exits, §4.3 gates, or §4.4 context
levels; those come after the go/no-go this measures.

Sibling to strategy/mcl/mcl.py: same style (dataclasses, no I/O,
"verify against independent loop implementations" ethos -- see
test_vw9_strategy.py), different rules.

STATE MACHINE, IN WORDS
------------------------
Two independent trackers run bar by bar over one session's worth of bars at
one timeframe (5m or 15m -- caller resamples before calling):

1. Setup A (VWAP reclaim): count consecutive BEARISH bars. The instant a bar
   closes above BOTH vwap and ema9 (STRONG) after >= MIN_BELOW_BARS bearish
   bars, that is a trigger. Reset the streak (whether it fired or the regime
   simply changed).

2. Setup B (9 EMA retest): while STRONG with a session high inside the last
   IMPULSE_LOOKBACK bars, the first bar that closes below ema9 while still
   above vwap (WEAK_BULL) opens a pullback. Every bar inside it must be
   "controlled" (bar-to-bar drop <= PULLBACK_CTRL_ATR x atr14) and the whole
   pullback must resolve within MAX_PULLBACK_BARS bars. It resolves three
   ways: closing below vwap (BEARISH) abandons it; an uncontrolled drop or
   running past the bar limit abandons it; closing back above ema9 (STRONG)
   is the trigger.

Both trackers require the regime to be DEFINED first -- see `apply_indicators`
-- which needs both vwap maturity (§2.2: MIN_VWAP_BARS bars AND
MIN_VWAP_DOLLAR_VOL cumulative dollar volume) and ema9 maturity (9 completed
bars). Before that, regime is None and neither setup can fire, which is the
mechanism behind §0's warm-up arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from common.indicators import atr, cum_dollar_volume, ema, session_vwap

# --- parameters, defaults from vw9_strategy_spec.md §6 ---------------------
EMA_FAST = 9
ATR_LENGTH = 14

MIN_VWAP_BARS = 3
MIN_VWAP_DOLLAR_VOL = 50_000.0

MIN_BELOW_BARS = 2          # Setup A: bearish bars required before a reclaim counts
RECLAIM_LOOKBACK = 6        # Setup A: structure_low capped to this many bars back

IMPULSE_LOOKBACK = 10       # Setup B: session high must be this recent to arm
PULLBACK_CTRL_ATR = 1.5     # Setup B: max bar-to-bar drop, in ATR, before "uncontrolled"
MAX_PULLBACK_BARS = 6       # Setup B: pullback must resolve within this many bars

REGIME_STRONG = "STRONG"
REGIME_WEAK_BULL = "WEAK_BULL"
REGIME_BEARISH = "BEARISH"


@dataclass
class Setup:
    kind: str                  # "A" (VWAP reclaim) or "B" (9 EMA retest)
    trigger_time: pd.Timestamp
    bar_index: int              # 0-based index into the bars passed to find_setups
    entry_ref: float             # trigger bar's close
    structure_low: float         # lowest low over the qualifying stretch


def apply_indicators(bars: pd.DataFrame, *, ema_fast: int = EMA_FAST,
                      atr_length: int = ATR_LENGTH,
                      min_vwap_bars: int = MIN_VWAP_BARS,
                      min_vwap_dollar_vol: float = MIN_VWAP_DOLLAR_VOL) -> pd.DataFrame:
    """Add ema9/vwap/atr14/regime columns to one session's bars.

    `bars` must already be sliced to a single session, in chronological order,
    starting at the bar the VWAP should anchor from (04:00 ET per §2.2 -- this
    function itself is anchor-agnostic and just starts VWAP at row 0, matching
    indicators.session_vwap).
    """
    out = bars.copy()
    c, h, l, v = out["close"], out["high"], out["low"], out["volume"]

    out["ema9"] = ema(c, ema_fast)
    out["vwap"] = session_vwap(h, l, c, v)
    out["atr14"] = atr(h, l, c, atr_length)
    out["cum_dv"] = cum_dollar_volume(c, v)

    bar_count = pd.Series(range(1, len(out) + 1), index=out.index)
    ema_ready = bar_count >= ema_fast
    vwap_ready = (bar_count >= min_vwap_bars) & (out["cum_dv"] >= min_vwap_dollar_vol)
    mature = ema_ready & vwap_ready

    regime = pd.Series([None] * len(out), index=out.index, dtype=object)
    bearish = mature & (c <= out["vwap"])
    strong = mature & ~bearish & (c > out["ema9"])
    weak_bull = mature & ~bearish & ~strong
    regime[bearish] = REGIME_BEARISH
    regime[strong] = REGIME_STRONG
    regime[weak_bull] = REGIME_WEAK_BULL
    out["regime"] = regime
    out["mature"] = mature
    return out


def find_setups(bars: pd.DataFrame, *,
                 ema_fast: int = EMA_FAST, atr_length: int = ATR_LENGTH,
                 min_vwap_bars: int = MIN_VWAP_BARS,
                 min_vwap_dollar_vol: float = MIN_VWAP_DOLLAR_VOL,
                 min_below_bars: int = MIN_BELOW_BARS,
                 reclaim_lookback: int = RECLAIM_LOOKBACK,
                 impulse_lookback: int = IMPULSE_LOOKBACK,
                 pullback_ctrl_atr: float = PULLBACK_CTRL_ATR,
                 max_pullback_bars: int = MAX_PULLBACK_BARS) -> list[Setup]:
    """Every Setup A / Setup B trigger in one session's bars, before §4.3
    gates. `bars` needs open/high/low/close/volume, tz-aware DatetimeIndex,
    chronological, sliced to one session starting at the VWAP anchor bar.
    """
    sig = apply_indicators(bars, ema_fast=ema_fast, atr_length=atr_length,
                            min_vwap_bars=min_vwap_bars,
                            min_vwap_dollar_vol=min_vwap_dollar_vol)
    n = len(sig)
    setups: list[Setup] = []
    if n == 0:
        return setups

    highs = sig["high"].tolist()
    lows = sig["low"].tolist()
    closes = sig["close"].tolist()
    atrs = sig["atr14"].tolist()
    regimes = sig["regime"].tolist()
    times = sig.index

    # Setup A state
    bearish_run = 0
    bearish_lows: list[float] = []

    # session-high tracking (raw price structure, independent of maturity)
    session_high = float("-inf")
    bars_since_new_high = 0

    # Setup B state
    in_pullback = False
    pullback_low = None
    pullback_start_idx = None

    prev_regime = None
    prev_close = None

    for t in range(n):
        h, l, c, r = highs[t], lows[t], closes[t], regimes[t]
        a = atrs[t]

        if h >= session_high:
            session_high = h
            bars_since_new_high = 0
        else:
            bars_since_new_high += 1

        # --- Setup A: check using the streak as of bar t-1, THEN update ---
        if r == REGIME_STRONG and bearish_run >= min_below_bars:
            window = bearish_lows[-reclaim_lookback:] if bearish_lows else [l]
            setups.append(Setup(kind="A", trigger_time=times[t], bar_index=t,
                                 entry_ref=c, structure_low=min(window)))
            bearish_run = 0
            bearish_lows = []

        if r == REGIME_BEARISH:
            bearish_run += 1
            bearish_lows.append(l)
        else:
            bearish_run = 0
            bearish_lows = []

        # --- Setup B ---
        if in_pullback:
            pullback_low = min(pullback_low, l)
            length = t - pullback_start_idx
            drop = (prev_close - c) if prev_close is not None else 0.0
            uncontrolled = bool(a) and drop > pullback_ctrl_atr * a

            if r == REGIME_BEARISH:
                in_pullback = False
            elif r == REGIME_STRONG:
                if length <= max_pullback_bars and not uncontrolled:
                    setups.append(Setup(kind="B", trigger_time=times[t],
                                         bar_index=t, entry_ref=c,
                                         structure_low=pullback_low))
                in_pullback = False
            else:  # still WEAK_BULL
                if uncontrolled or length > max_pullback_bars:
                    in_pullback = False
        else:
            if (r == REGIME_WEAK_BULL and prev_regime == REGIME_STRONG
                    and bars_since_new_high <= impulse_lookback):
                drop = (prev_close - c) if prev_close is not None else 0.0
                uncontrolled = bool(a) and drop > pullback_ctrl_atr * a
                if not uncontrolled:
                    in_pullback = True
                    pullback_start_idx = t
                    pullback_low = l
                # else: fails to arm on bar 1 of the would-be pullback

        prev_regime = r
        prev_close = c

    return setups
