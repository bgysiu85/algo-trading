#!/usr/bin/env python3
"""
VW9 backtest engine -- vw9_strategy_spec.md §4.3 entry gates, §5 exits, §9
execution model. Pure logic, no broker, no I/O -- sibling to
strategy/mcl/mcl.py's backtest_session(), same Trade-dataclass/asdict()
shape so common/backtest.py's Runner can drive it unchanged. Entries
themselves come from strategy.vw9.vw9.find_setups(), which already
implements §3/§4.1/§4.2 (regime gate, Setup A, Setup B) "before gates" --
this module adds the gates, the position simulation, and the fills.

SCOPE, EXPLICITLY
-----------------
Implemented: all five §4.3 gates except overhead-headroom (see below),
§5.1 stop, all three §5.2 target variants (run independently -- each call
picks one via `exit_mode`), §5.3 hard-exit priority (stop > VWAP-lost >
session-end, with "stop wins" on intrabar stop/target ambiguity falling
naturally out of checking the stop first), and §9's next-bar-open fill
(explicitly NOT MCL's trigger-bar-close -- see _simulate_trade).

NOT implemented, by documented decision (2026-09-05 build):
  - §4.4 context levels / daily 200 EMA, and therefore the overhead-headroom
    gate that depends on them. This pipeline has no daily-bar source, and
    MIN_HEADROOM_R is off by default per spec anyway (§4.3's own table), so
    the gate is simply never evaluated -- it is not wired to a "always
    pass" stub, it does not exist here at all.
  - MIN_TRIGGER_DV_PER_MIN below is the spec's own NAIVE placeholder scaling
    ($20k/30s -> $40k/minute -> $200k/5m bar, $600k/15m bar). §6 says
    outright "do not guess this one -- measure the actual distribution
    (§8.2) and set it from that." This constant is a placeholder pending
    that measurement, not a calibrated value, and is flagged again at its
    definition below.

TWELVE of eighteen §6 parameters are uncalibrated guesses (the spec's own
count -- see §6's table). Every default below is a starting point for a
sweep, not a claim about what will make money.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time as dtime
from zoneinfo import ZoneInfo

import pandas as pd

from common.commissions import order_cost
from common.indicators import resample_bars
from strategy.vw9.vw9 import Setup, apply_indicators, find_setups

ET = ZoneInfo("America/New_York")

# --- session, matching setup_counts.py's own choice (§1, §9) ---------------
SESSION_START = dtime(4, 0)
SESSION_END = dtime(20, 0)
RTH_START = dtime(9, 30)
RTH_END = dtime(16, 0)

# --- §4.3 gates --------------------------------------------------------------
MAX_EXT_ATR = 2.0
MAX_ENTRIES_PER_SESSION = 4

# NOT MEASURED -- see module docstring. §6's own naive scaling of the
# volume-floor finding, not what §6 instructs ("measure first"). Replace
# once §8.2 (dollar volume per bar, by session block and timeframe) has run.
MIN_TRIGGER_DV_PER_MIN = 40_000.0

# --- §5 exits ----------------------------------------------------------------
STOP_BUFFER_ATR = 0.10
TARGET_R = 2.0
TRAIL_ATR = 2.0

# MCL's exit, ported so the two strategies can be compared on the same terms.
#
# The measurement that prompted it: VW9's ATR trail is far wider than it reads.
# 2 x ATR14 as a percentage of price, over 67,020 5-minute bars, is median
# 7.3%, p75 12.7%, p90 21.0%, p99 63.4% -- against MCL's flat 5%. It is widest
# on exactly the names that move most, which is backwards.
#
# MCL's exit is TWO decisions, not one, and both are ported here:
#   1. the trail is a fixed PERCENTAGE of the peak, not a volatility multiple
#   2. there is NO fixed stop -- since V4 the trail is the only protection
# Keeping VW9's structural stop while swapping the trail would test neither,
# so use_structural_stop exists to turn it off. It is worth turning off: in
# the best cell those 123 stop exits were -$6,505.99 at a 0% win rate, which
# they must be, since the stop sits below the entry by construction.
TRAIL_PCT = 5.0
EXIT_MODES = ("fixed_2r", "ride_ema9", "trail_atr", "trail_pct")

# --- universe band -----------------------------------------------------------
# §1: the universe is "$2-20, RVOL(1D) >= 5x, float < 20m, top-2 pre-market
# gainer". Price is the only one of those four this engine can enforce, and
# until 2026-09-05 it enforced none of them -- MCL has had ENFORCE_PRICE_BAND
# since the apex sweep, VW9 never did, and nobody noticed because the two
# strategies' reports were never read side by side.
#
# It is not a cosmetic filter. IB returns SPLIT-ADJUSTED history, so a small
# cap that later reverse-split comes back with inflated prices -- up to $32,104
# observed on this very pair set. Without the band VW9 traded entries from
# $0.30 to $4,152.11 and took positions in PFSA at $4,152/share and ZNB at
# $1,976/share. Those are not prices anyone could have traded; they are the
# adjustment factor.
#
# Measured effect on VW9-5 EMA9 trail_atr over 374 sessions:
#     all trades        643 tr   -$31,296.17   -$48.67/tr
#     inside $2-20      436 tr    +$3,941.88    +$9.04/tr
#     outside the band  207 tr   -$35,238.05  -$170.23/tr
#
# The band carries the same residual UPWARD bias it does for MCL, and for the
# same reason: filtering on adjusted price preferentially drops names that
# later reverse-split, and reverse splits follow collapses. It removes an
# artifact; it does not make the sample clean.
PRICE_MIN, PRICE_MAX = 2.0, 20.0
ENFORCE_PRICE_BAND = True

# --- sizing / costs, unchanged from MCL so results are comparable (§9) ------
EQUITY = 100_000.0
# Shown on alerts so a fill on a phone says which strategy fired it.
# Lives on the STRATEGY rather than in the trader, so a second trader
# cannot end up labelling its fills with the first one's name.
STRATEGY_NAME = "VW9"

MAX_SHARES = 100
MAX_EQUITY_PCT = 40.0
# See strategy/mcl/mcl.py and claude/ibkr_commission_structure.md. Same plan
# names, same reason for accumulating per order rather than per share.
COMMISSION_PLAN = "ibkr_tiered"
COMMISSION_PER_SHARE = 0.005     # legacy plan only
SLIPPAGE_TICKS = 1
TICK = 0.01


@dataclass
class Trade:
    symbol: str
    date: str
    timeframe: int
    setup_kind: str
    exit_mode: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    qty: int
    reason: str
    bars_held: int
    gross: float
    commission: float
    net: float
    r_multiple: float
    session_block: str
    # Scale-out bookkeeping, same meaning as strategy/mcl/mcl.py's. Both are
    # 0 / initial size when scaling is off, so default output only gains two
    # columns. shares_traded is what friction must be charged against: a
    # mechanic that triples the shares transacted per trade cannot be scored
    # on a one-round-trip cost model.
    cycles: int = 0
    shares_traded: int = 0


def size_for(price: float, equity: float = EQUITY) -> int:
    if price <= 0:
        return 0
    return max(0, min(MAX_SHARES,
                      math.floor(equity * MAX_EQUITY_PCT / 100.0 / price)))


def session_block(ts) -> str:
    """PRE / RTH / POST, per §9's execution-model report requirement."""
    t = ts.astimezone(ET).time() if getattr(ts, "tzinfo", None) is not None else ts
    if t < RTH_START:
        return "PRE"
    if t < RTH_END:
        return "RTH"
    return "POST"


def _passes_entry_gates(setup: Setup, bar_minutes: int, ext_atr: float | None,
                        trigger_dollar_vol: float, *,
                        min_trigger_dv_per_min: float,
                        max_ext_atr: float) -> bool:
    """§4.3, everything except re-entry (the caller's job -- it is the only
    gate needing cross-trade state) and overhead-headroom (not implemented
    at all -- see module docstring).
    """
    # Liquidity: trigger bar dollar volume >= threshold * bar minutes.
    if trigger_dollar_vol < min_trigger_dv_per_min * bar_minutes:
        return False

    # Extension: (close - ema9) / atr14 <= MAX_EXT_ATR. ext_atr is None only
    # when atr14 is exactly zero (a degenerate, effectively-flat opening
    # print) -- treat that as "not extended" rather than divide by zero,
    # since §2.3's percentage-of-price fallback is not implemented here.
    if ext_atr is not None and ext_atr > max_ext_atr:
        return False

    # Pullback volume (Setup B only): largest down-bar volume in the
    # pullback must not exceed the largest up-bar volume of the impulse.
    # Setup A has no such gate (both fields are None on it).
    if setup.kind == "B":
        up, down = setup.impulse_max_up_vol, setup.pullback_max_down_vol
        if up is not None and down is not None and down > up:
            return False

    return True


def _simulate_trade(sig: pd.DataFrame, entry_bar_index: int, setup: Setup,
                    exit_mode: str, stop_buffer_atr: float, target_r: float,
                    trail_atr: float, *,
                    enforce_price_band: bool = ENFORCE_PRICE_BAND,
                    use_vwap_exit: bool = True,
                    vwap_exit_grace_bars: int = 0,
                    trail_pct: float = TRAIL_PCT,
                    use_structural_stop: bool = True,
                    scale_out_pct: float | None = None,
                    partial_trail_pct: float = 2.5,
                    rebuy_qty: int | None = None,
                    max_position_shares: int | None = None,
                    rebuy_slip_bps: float = 0.0,
                    max_cycles: int | None = None,
                    commission_plan: str = COMMISSION_PLAN,
                    rebuy_trigger: str = "peak",
                    gap_fills: bool = True,
                    entry_shares: int | None = None) -> dict | None:
    """Fill next-bar-open (§9 -- extended hours takes Day Limit orders only,
    so the trigger bar's close can never be the fill), then manage to
    whichever of the §5.3 hard exits or the exit_mode's target comes first.

    Returns None (no trade) when: the setup fired on the session's last bar
    (nothing to fill on), the stop-buffer leaves no positive R to risk, or
    sizing rounds to zero shares -- all deliberately silent skips rather
    than errors, since a go/no-go measurement over hundreds of pairs cannot
    stop for a handful of degenerate sessions.
    """
    n = len(sig)
    fill_i = entry_bar_index + 1
    if fill_i >= n:
        return None

    opens = sig["open"].tolist()
    highs = sig["high"].tolist()
    lows = sig["low"].tolist()
    closes = sig["close"].tolist()
    ema9 = sig["ema9"].tolist()
    vwap = sig["vwap"].tolist()
    atrs = sig["atr14"].tolist()
    times = sig.index

    entry_price = opens[fill_i] + SLIPPAGE_TICKS * TICK

    # §1 universe band, applied to the price actually paid. MCL applies the
    # same test at the same point (mcl.py's entry branch), so the two agree on
    # what is in the universe.
    if enforce_price_band and not (PRICE_MIN <= entry_price <= PRICE_MAX):
        return None

    atr_at_entry = atrs[entry_bar_index] or 0.0
    stop = setup.structure_low - stop_buffer_atr * atr_at_entry
    r = entry_price - stop
    if r <= 0:
        return None
    target = entry_price + target_r * r if exit_mode == "fixed_2r" else None

    # entry_shares bypasses size_for() so a comparison against a real trading
    # day holds size fixed -- see strategy/mcl/mcl.py backtest_session.
    qty = size_for(entry_price) if entry_shares is None else int(entry_shares)
    if qty < 1:
        return None

    # Scale-out bookkeeping, mirroring strategy/mcl/mcl.py so the same four
    # knobs mean the same thing in both strategies: trail_pct / trail_atr is
    # the full exit, partial_trail_pct is where a portion leaves,
    # scale_out_pct is how much of the CURRENT position that is, and
    # rebuy_qty is what comes back on a reclaim (None = restore what was
    # sold, so size stays constant). avg_px is the running cost of the shares
    # still held; realised banks the P/L of partial sells; shares_traded
    # drives commission, which must be per share actually transacted.
    init_qty = qty
    avg_px = entry_price
    realised = 0.0
    shares_traded = qty
    commission = order_cost(qty, entry_price, False, commission_plan)
    scaled_out = False
    sold_qty = 0
    cycles = 0
    prev_high = None
    rebuy_level = None
    capped_out = False

    # Trailing peak starts at entry price ONLY -- not the fill bar's own
    # high -- and is updated at the BOTTOM of each iteration, so the trail
    # checked on any given bar always reflects the peak as of the PREVIOUS
    # bar. Same "no same-bar lookahead" convention as mcl.py's trailing
    # stop, applied from the fill bar onward.
    peak = entry_price
    last_i = n - 1

    for i in range(fill_i, n):
        h, l, c, o = highs[i], lows[i], closes[i], opens[i]
        last_of_session = (i == last_i)

        exit_px = exit_reason = None

        # --- §5.3 priority: stop > VWAP-lost > session-end ------------------
        # Checking the stop first is what makes "stop wins" on intrabar
        # stop/target ambiguity fall out automatically: a bar whose range
        # spans both is never evaluated for the target below.
        # vwap_exit_grace_bars exists because of what the measurement showed:
        # 189 of 386 vwap_lost exits fired on the FILL BAR ITSELF (bars_held=0),
        # for -$27,191.79. The mechanism is structural, not bad luck. Setup A
        # enters because a bar CLOSED back above VWAP; §9 fills at the NEXT
        # bar's open; if that bar closes back below VWAP the position is shut
        # the instant it is opened. Price sitting on VWAP is exactly when it
        # oscillates across it, so the rule fires hardest precisely where it is
        # least informative -- and each round trip still pays two ticks and
        # commission both ways.
        #
        # A grace period lets the trade prove itself over N bars before the
        # hard rule applies. 0 restores the spec's literal §5.3 behaviour.
        # GAP-THROUGH FILLS, added 2026-09-05 after MC5's first real run
        # exposed the same flaw in mcl.py and mc5.py. Selling AT a level
        # assumes the market offered it; when the bar OPENS below, price was
        # already through before the bar began and the best obtainable fill is
        # the open. On MC5 that assumption was 48% of stop exits and the whole
        # apparent edge. It applies to EVERY level-based exit below -- the
        # structural stop and both trails -- because all three sell at a
        # computed price on the strength of the bar's LOW reaching it.
        def _fill(level: float) -> float:
            return min(level, o) if gap_fills else level

        if use_structural_stop and l <= stop:
            exit_px, exit_reason = _fill(stop) - SLIPPAGE_TICKS * TICK, "stop"
        elif (use_vwap_exit and (i - fill_i) >= vwap_exit_grace_bars
              and c <= vwap[i]):
            exit_px, exit_reason = c - SLIPPAGE_TICKS * TICK, "vwap_lost"
        elif last_of_session:
            exit_px, exit_reason = c - SLIPPAGE_TICKS * TICK, "session_close"
        elif exit_mode == "fixed_2r" and h >= target:
            exit_px, exit_reason = target - SLIPPAGE_TICKS * TICK, "target_2r"
        elif exit_mode == "ride_ema9" and c < ema9[i]:
            exit_px, exit_reason = c - SLIPPAGE_TICKS * TICK, "ema9_lost"
        elif exit_mode == "trail_atr":
            trail = peak - trail_atr * (atrs[i] or 0.0)
            if l <= trail:
                exit_px, exit_reason = _fill(trail) - SLIPPAGE_TICKS * TICK, "trail_atr"
        elif exit_mode == "trail_pct":
            # mcl.py's exact form: trail off the peak as of the PREVIOUS bar
            # (peak is updated at the bottom of this loop), tested against this
            # bar's low, filled at the trail level less one tick. No same-bar
            # lookahead, same as MCL.
            trail = peak * (1.0 - trail_pct / 100.0)
            if l <= trail:
                exit_px, exit_reason = _fill(trail) - SLIPPAGE_TICKS * TICK, "trail_pct"

        if exit_px is not None:
            gross = realised + (exit_px - avg_px) * qty
            comm = commission + order_cost(qty, exit_px, True, commission_plan)
            return {
                "entry_time": times[fill_i], "exit_time": times[i],
                "entry_price": entry_price, "exit_price": exit_px,
                "qty": init_qty, "reason": exit_reason, "bars_held": i - fill_i,
                "gross": gross, "commission": comm, "net": gross - comm,
                "r_multiple": (exit_px - entry_price) / r,
                "exit_bar_index": i, "cycles": cycles,
                "shares_traded": shares_traded + qty,
            }

        # --- scale out / scale back in, only when enabled ------------------
        # Every hard exit above has already been ruled out for this bar, so a
        # partial sell here cannot be masking a full exit. Selling is checked
        # before buying back, so a bar that both dips to the partial level and
        # tags the previous high resolves as a sell -- against the position.
        if scale_out_pct and not capped_out:
            partial = peak * (1.0 - partial_trail_pct / 100.0)
            if not scaled_out and l <= partial:
                sell_q = int(qty * scale_out_pct / 100.0)
                if 1 <= sell_q < qty:
                    px_out = partial - SLIPPAGE_TICKS * TICK
                    realised += (px_out - avg_px) * sell_q
                    commission += order_cost(sell_q, px_out, True, commission_plan)
                    qty -= sell_q
                    shares_traded += sell_q
                    scaled_out = True
                    sold_qty = sell_q
                    # Freeze the level the pullback began from -- see mcl.py.
                    rebuy_level = peak
            elif scaled_out and (
                    (trigger_level := (rebuy_level if rebuy_trigger == "peak"
                                       else prev_high)) is not None) \
                    and h >= trigger_level:
                # Hitting the cap retires the mechanic -- selling as well as
                # buying -- for the rest of the trade. See mcl.py.
                capped = max_cycles is not None and cycles >= max_cycles
                if capped:
                    capped_out = True
                add = rebuy_qty if rebuy_qty is not None else sold_qty
                if max_position_shares is not None:
                    add = min(add, max_position_shares - qty)
                if not capped and add >= 1:
                    # A break above the trigger cannot be bought with a
                    # resting limit -- a limit placed above the market fills
                    # immediately at the ask instead of waiting. Live this is
                    # a marketable limit sent after the break is seen, so the
                    # fill is above the trigger. 0 bps models a fill nobody
                    # can get; trader.py crosses by 20.
                    px_in = (trigger_level * (1.0 + rebuy_slip_bps / 10_000.0)
                             + SLIPPAGE_TICKS * TICK)
                    avg_px = (avg_px * qty + px_in * add) / (qty + add)
                    commission += order_cost(add, px_in, False, commission_plan)
                    qty += add
                    shares_traded += add
                    cycles += 1
                scaled_out = False

        peak = max(peak, h)
        prev_high = h

    # Unreachable in practice -- the last bar of the session always exits
    # via session_close above -- but never leave a position unaccounted for.
    return None  # pragma: no cover


def backtest_session_tf(bars_1m: pd.DataFrame, session_date, tz,
                        timeframe_minutes: int, *,
                        exit_mode: str = "fixed_2r",
                        ema_fast: int | None = None,
                        min_trigger_dv_per_min: float = MIN_TRIGGER_DV_PER_MIN,
                        max_ext_atr: float = MAX_EXT_ATR,
                        max_entries_per_session: int = MAX_ENTRIES_PER_SESSION,
                        stop_buffer_atr: float = STOP_BUFFER_ATR,
                        target_r: float = TARGET_R,
                        trail_atr: float = TRAIL_ATR,
                        enforce_price_band: bool = ENFORCE_PRICE_BAND,
                        use_vwap_exit: bool = True,
                        vwap_exit_grace_bars: int = 0,
                        trail_pct: float = TRAIL_PCT,
                        use_structural_stop: bool = True,
                        scale_out_pct: float | None = None,
                        partial_trail_pct: float = 2.5,
                        rebuy_qty: int | None = None,
                        max_position_shares: int | None = None,
                        rebuy_slip_bps: float = 0.0,
                        max_cycles: int | None = None,
                        commission_plan: str = COMMISSION_PLAN,
                        rebuy_trigger: str = "peak",
                        only_setup: str | None = None,
                        gap_fills: bool = True,
                        entry_shares: int | None = None) -> list[Trade]:
    """One session, one timeframe, one exit mode.

    bars_1m must be 1-minute bars covering at least 04:00-20:00 ET on
    session_date (§1), tz-aware, chronological -- the same shape
    setup_counts.py already slices from the shared bar cache. Resampling to
    `timeframe_minutes` and slicing to the single session happen here, so
    callers (the adapters below, or a test) can just hand over raw 1m bars.
    """
    if exit_mode not in EXIT_MODES:
        raise ValueError(f"unknown exit_mode {exit_mode!r}; must be one of {EXIT_MODES}")

    local = bars_1m.index.tz_convert(tz)
    mask = ((local.date == session_date)
            & (local.time >= SESSION_START) & (local.time < SESSION_END))
    sess_1m = bars_1m[mask]
    if sess_1m.empty:
        return []

    bars_tf = sess_1m if timeframe_minutes == 1 else resample_bars(sess_1m, timeframe_minutes)
    if bars_tf.empty:
        return []

    kwargs = {} if ema_fast is None else {"ema_fast": ema_fast}
    setups = find_setups(bars_tf, **kwargs)
    if not setups:
        return []

    sig = apply_indicators(bars_tf, **kwargs)
    closes = sig["close"].tolist()
    ema9s = sig["ema9"].tolist()
    atrs = sig["atr14"].tolist()
    volumes = sig["volume"].tolist()

    trades: list[Trade] = []
    entries_taken = 0
    # No trade yet: -1 so a setup on bar 0 always clears "t > blocked_until".
    # After a trade, this becomes its exit_bar_index, which enforces BOTH
    # no-overlap (the next setup cannot trigger while a position is open)
    # and the re-entry gap (>= 1 bar since the last exit) with one check.
    blocked_until = -1

    for setup in setups:
        if entries_taken >= max_entries_per_session:
            break
        # SETUP FILTER, and where it sits is the whole point.
        #
        # Filtering HERE -- before the entry cap and before the no-overlap
        # block -- is what makes a Setup-B-only run different from slicing
        # kind == "B" out of a mixed run afterwards. In a mixed run Setup A is
        # 81% of triggers, so A consumes max_entries_per_session and holds the
        # position that blocks B from triggering at all. The post-hoc B slice
        # is therefore not "what B would have done"; it is "what B managed to
        # do in the gaps A left". Every B-only figure quoted before this
        # parameter existed is that weaker thing.
        if only_setup and setup.kind != only_setup:
            continue
        t = setup.bar_index
        if t <= blocked_until:
            continue

        atr_t = atrs[t]
        ext_atr = ((closes[t] - ema9s[t]) / atr_t) if atr_t else None
        trigger_dv = closes[t] * volumes[t]

        if not _passes_entry_gates(setup, timeframe_minutes, ext_atr, trigger_dv,
                                   min_trigger_dv_per_min=min_trigger_dv_per_min,
                                   max_ext_atr=max_ext_atr):
            continue

        res = _simulate_trade(sig, t, setup, exit_mode, stop_buffer_atr,
                              target_r, trail_atr,
                              enforce_price_band=enforce_price_band,
                              use_vwap_exit=use_vwap_exit,
                              vwap_exit_grace_bars=vwap_exit_grace_bars,
                              trail_pct=trail_pct,
                              use_structural_stop=use_structural_stop,
                              scale_out_pct=scale_out_pct,
                              partial_trail_pct=partial_trail_pct,
                              rebuy_qty=rebuy_qty,
                              max_position_shares=max_position_shares,
                              rebuy_slip_bps=rebuy_slip_bps,
                              max_cycles=max_cycles,
                              commission_plan=commission_plan,
                              rebuy_trigger=rebuy_trigger, gap_fills=gap_fills,
                              entry_shares=entry_shares)
        if res is None:
            continue

        entry_time = res["entry_time"]
        trades.append(Trade(
            symbol="", date=str(session_date), timeframe=timeframe_minutes,
            setup_kind=setup.kind, exit_mode=exit_mode,
            entry_time=str(entry_time), exit_time=str(res["exit_time"]),
            entry_price=round(res["entry_price"], 4),
            exit_price=round(res["exit_price"], 4),
            qty=res["qty"], reason=res["reason"], bars_held=res["bars_held"],
            gross=round(res["gross"], 2), commission=round(res["commission"], 2),
            net=round(res["net"], 2), r_multiple=round(res["r_multiple"], 3),
            session_block=session_block(entry_time),
            cycles=res.get("cycles", 0),
            shares_traded=res.get("shares_traded", res["qty"] * 2)))
        entries_taken += 1
        blocked_until = res["exit_bar_index"]

    return trades
