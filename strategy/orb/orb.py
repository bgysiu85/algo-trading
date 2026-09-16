#!/usr/bin/env python3
"""ORB — the opening-range break, as a session state machine.

`claude/orb_strategy_spec.md` §14 item 7. Written AFTER the pre-flight
(`strategy/orb/preflight.py`) and after criterion 2 was replaced
(`docs/research/REGISTERED_breadth.md`), and BEFORE any grid is run
(`docs/research/REGISTERED_orb_grid.md` says how the grid is read).

WHAT THIS FILE IS AND IS NOT

It is the rule, and the fill model, for ONE symbol-day. It produces trades and
a coverage row, and it computes no aggregate of any kind -- no totals, no
per-trade averages, no verdict. That belongs to the runner, which is written
after this and reads `REGISTERED_orb_grid.md` §5 for what every cell must emit.
Keeping the two apart is not tidiness: a rule module that also reports is a
rule module that can be tuned while looking at its own output.

WHAT IT DELIBERATELY DOES NOT SHARE WITH THE OTHER STRATEGIES

`common/backtest.py` and `strategy/mcl/mcl.backtest_session` model a
pre-market strategy on 1-minute bars with an apex signal and a percentage
trail. ORB is a different object -- RTH only, no indicators, a level fixed at
09:45, a hard stop that defines R, and five exit rules of which only one is a
trail. §10 of the spec says so outright: *slice the superset, do not import
backtest.py*. What IS shared is shared by CALLING it: `resample_bars`,
`order_cost`, and the pre-flight's `load_bars` / `rth_session`, so the grid
cannot be measuring a different bar shape from the pre-flight that sized it.

THE FILL MODEL IS §9's, FROM THE FIRST COMMIT

Every assumption below was paid for once already. MC5 reported +$20,156 and
passed every robustness test; honest fills took it to -$400, on identical
trades. So: entry at the NEXT bar's open and never the trigger close;
gap-through fills on stops; the trail peak seeded from the fill; the stop wins
a bar that contains both stop and target; slippage symmetric at one tick; and
the $2-20 price band enforced before a single P/L number exists, because VW9
shipped without it and took positions at $4,152 a share.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import time as dtime

import pandas as pd

from common.commissions import order_cost
from common.indicators import resample_bars

# --------------------------------------------------------------------------
# What the cache slicer needs to know. Spec §10: ORB wants ONE session ending
# at 16:00, which is neither MCL's two-sessions-to-09:30 nor VW9's
# one-session-to-20:00.
# --------------------------------------------------------------------------
STRATEGY_NAME = "ORB"
BACKTEST_SESSIONS = 1
BACKTEST_END_HOUR = 16
BACKTEST_END_MINUTE = 0

RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)
LAST_ENTRY = dtime(15, 55)      # §3.3 -- trading 09:45 to 15:55
FLATTEN_BAR = dtime(15, 55)     # flat at the 15:55-16:00 bar's close

# MANDATORY, and not a parameter. PROGRAM_INDEX §1 and §5.
PRICE_MIN, PRICE_MAX = 2.0, 20.0

# §9. One tick, both sides, symmetric -- measured across 18,552 fills at
# $0.0009 versus -$0.0009, i.e. indistinguishable from zero. The single-session
# asymmetry this row used to carry was noise AND was sign-reversed.
TICK = 0.01
SLIPPAGE_TICKS = 1
COMMISSION_PLAN = "ibkr_tiered"

# V4's retest zone, as a fraction of the range measured UP from orb_low.
# A 38% retracement from the high is orb_low + 0.62 * width, so the deeper
# edge of the zone carries the SMALLER multiplier. Named here once because
# reading it the other way round is a silent 24%-of-range error.
ZONE_LO, ZONE_HI = 0.38, 0.62

RETEST_MODES = ("none", "required", "zone")
STOP_MODES = ("structure", "opposite", "rangefrac")
EXIT_MODES = ("r_2", "r_1_5", "r_3_trim", "range_1x", "trail_pct")


@dataclass(frozen=True)
class Config:
    """One grid cell. Frozen, because ninety of these exist at once and a
    mutable default shared between cells is how a sweep silently measures one
    configuration ninety times."""

    orb_minutes: int = 15
    trigger_bar_minutes: int = 5
    entry_on_close: bool = True          # False reproduces V8's resting order
    entry_buffer_pct: float = 0.0
    retest_mode: str = "none"
    retest_max_bars: int = 6
    stop_mode: str = "structure"
    stop_buffer_pct: float = 0.10        # percent OF PRICE, not of the range
    stop_range_frac: float = 0.5
    max_r_pct: float = 12.0
    exit_mode: str = "r_2"
    trail_pct: float = 5.0
    time_stop_bars: int | None = None
    max_entries_per_session: int = 1
    min_range_bars_frac: float = 10 / 15
    min_range_pct: float = 0.5
    max_range_pct: float = 25.0
    fade_window_bars: int = 3
    shares: int = 100
    enforce_price_band: bool = True

    def __post_init__(self):
        # A typo'd mode name must not silently select the baseline. Every one
        # of these strings comes from a grid literal, and a cell that quietly
        # ran `structure` while labelled `rangefrac` would be reported as a
        # comparison between two identical arms.
        for name, allowed in (("retest_mode", RETEST_MODES),
                              ("stop_mode", STOP_MODES),
                              ("exit_mode", EXIT_MODES)):
            v = getattr(self, name)
            if v not in allowed:
                raise ValueError(f"{name}={v!r} is not one of {allowed}")
        if self.orb_minutes % self.trigger_bar_minutes:
            # Otherwise the range ends mid-bucket and the first trigger bar
            # straddles the level it is supposed to break.
            raise ValueError(
                f"orb_minutes={self.orb_minutes} must be a whole number of "
                f"{self.trigger_bar_minutes}-minute bars")
        if not self.entry_on_close and self.retest_mode != "none":
            # V8's resting order fills on a wick; a retest is defined by a
            # CLOSE back above the level. The combination has no rule in any
            # of the ten sources, and picking one silently would put an
            # invented strategy in a cell labelled as someone else's.
            raise ValueError(
                "entry_on_close=False is V8's resting order and V8 requires "
                "no retest; retest_mode must be 'none'")


BASELINE = Config()      # REGISTERED_orb_grid.md §2, fixed from the sources


@dataclass
class Trade:
    symbol: str
    date: str
    entry_time: pd.Timestamp
    entry_px: float                  # the modelled FILL, slippage included
    shares: int
    exit_time: pd.Timestamp
    exit_px: float
    exit_reason: str                 # stop | target | trail | be_stop | time_stop | session_end
    r: float                         # entry_fill - stop, in dollars
    orb_width: float
    gross: float
    commission: float
    net: float
    bars_held: int
    leg: int = 0                     # 0 unless r_3_trim split the position


@dataclass
class SessionResult:
    """One symbol-day. Coverage in the SAME object as the trades, per §12 --
    a report that cannot say what it failed to read is not a report."""

    symbol: str
    date: str
    status: str = ""     # OK | NO_RTH | FEW_BARS | TOO_NARROW | TOO_WIDE
                         # | NO_TRIGGER | NO_ENTRY_BAR | RETEST_FAILED
                         # | R_NOT_POSITIVE | R_TOO_WIDE | OUT_OF_BAND | TOO_LATE
    rth_bars: int = 0
    range_bars: int = 0
    missing_range_minutes: int = 0
    # §4 trap 1 says "the 09:30 bar must be present" and then specifies a rule
    # that only COUNTS bars -- so a range missing its opening minute but
    # holding fourteen others passes. The prose and the rule disagree, and
    # picking one of them here would be inventing a filter or ignoring a
    # warning. Recorded instead, so the runner can cut on it and Ben can
    # settle it against a number rather than against the paragraph.
    has_open_bar: bool = False
    first_ts: pd.Timestamp | None = None
    last_ts: pd.Timestamp | None = None

    orb_high: float | None = None
    orb_low: float | None = None
    orb_width: float | None = None
    width_pct: float | None = None

    up_trigger: bool = False
    up_trigger_bar: int | None = None
    down_trigger: bool = False           # §5.4 -- measured, never traded
    down_trigger_bar: int | None = None

    entry_px: float | None = None
    stop_px: float | None = None
    r: float | None = None
    r_pct: float | None = None

    trades: list[Trade] = field(default_factory=list)
    open_at_close: bool = False
    both_in_bar: int = 0                 # §7.2 -- how often the stop-wins bit
    faded: bool | None = None            # §7.4 -- V2's counter-hypothesis
    # §10.2, set by the runner and NOT by the rule: whether a 09:30 RTH screen
    # would have picked this symbol-day. It lives here so the split is computed
    # from the same trades as the headline, and it is FALSE until something
    # sets it -- the rule itself never looks at it, because a strategy that
    # filtered on its own buildability check would make §10.2 unanswerable.
    passes_rth_screen: bool = False
    fade_return_pct: float | None = None

    @property
    def net(self) -> float:
        return sum(t.net for t in self.trades)


# --------------------------------------------------------------------------
# the range
# --------------------------------------------------------------------------

def opening_range(sess: pd.DataFrame, cfg: Config) -> tuple[str, dict]:
    """The first `orb_minutes` of RTH, wick to wick, or why there isn't one.

    §4's four definitional traps, each of which returns a PLAUSIBLE WRONG
    ANSWER rather than an error if it is not checked: a missing 09:30 bar, a
    range with no width, a range that already contains the day's move, and a
    range that gets re-anchored later. The fourth is prevented by construction
    -- this function is called once and its result is never updated.
    """
    out: dict = {"orb_high": None, "orb_low": None, "orb_width": None,
                 "width_pct": None, "range_bars": 0, "missing": 0}
    if sess.empty:
        return "NO_RTH", out

    end_min = 9 * 60 + 30 + cfg.orb_minutes
    end = dtime(end_min // 60, end_min % 60)
    opening = sess[[t.time() < end for t in sess.index]]
    out["range_bars"] = len(opening)
    out["missing"] = cfg.orb_minutes - len(opening)
    if len(opening) < int(cfg.orb_minutes * cfg.min_range_bars_frac):
        return "FEW_BARS", out

    hi, lo = float(opening["high"].max()), float(opening["low"].min())
    if lo <= 0:
        return "FEW_BARS", out
    out["orb_high"], out["orb_low"] = hi, lo
    out["orb_width"] = hi - lo
    out["width_pct"] = (hi - lo) / lo * 100.0

    if out["width_pct"] < cfg.min_range_pct:
        return "TOO_NARROW", out
    if out["width_pct"] > cfg.max_range_pct:
        return "TOO_WIDE", out
    return "OK", out


# --------------------------------------------------------------------------
# the bar view
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Bars:
    """Trigger-sized bars as PLAIN PYTHON LISTS, not a DataFrame.

    Built once per symbol-day and handed to all ninety cells. Two reasons, and
    the second is the one that matters:

      * `df.iloc[j]` inside a walk costs tens of microseconds. Ninety cells
        over 27,777 symbol-days is 2.5 million session walks, and at pandas
        speed the grid takes hours instead of minutes -- long enough that it
        would get run once, on a subset, and believed.
      * ONE resample per symbol-day means every cell sees exactly the same
        bars. Ninety independent resamples of the same frame should agree, and
        would; but "should" is how two arms of a comparison end up measuring
        different objects.

    `backtest_session` builds this itself when it is not given one, and
    `test_a_cached_bar_view_gives_identical_results` runs both ways over the
    same frames and asserts the trades match -- an equivalence test, not a copy
    of the construction.
    """

    t: list                 # ET timestamps, bucket START (left-labelled)
    tm: list                # the same instants as datetime.time, precomputed
    o: list
    h: list
    l: list
    c: list
    minutes: int

    def __len__(self) -> int:
        return len(self.t)


def trigger_bars(sess: "pd.DataFrame", minutes: int) -> Bars:
    b = resample_bars(sess, minutes)
    # `Timestamp.time()` is not free and the grid asks for it three times per
    # cell per bar -- ninety cells over 27,777 symbol-days is where a
    # microsecond becomes six minutes.
    return Bars(t=list(b.index), tm=[x.time() for x in b.index],
                o=[float(v) for v in b["open"]],
                h=[float(v) for v in b["high"]],
                l=[float(v) for v in b["low"]],
                c=[float(v) for v in b["close"]],
                minutes=minutes)


# --------------------------------------------------------------------------
# fills
# --------------------------------------------------------------------------

def fill_below(o: float, lo: float, level: float) -> float | None:
    """A sell at or below `level` -- a stop. Gap-through honoured.

    §9: you cannot sell AT a level the market never offered. When the bar OPENS
    below the stop the fill is the OPEN, which is worse. 48% of MC5's stop
    exits were affected by this one line.
    """
    if o <= level:
        return o
    return level if lo <= level else None


def fill_above(o: float, hi: float, level: float) -> float | None:
    """A sell at or above `level` -- a target.

    The asymmetry with `fill_below` is DELIBERATE and both halves are
    conservative. A stop gapped through fills worse than the level, so the gap
    is taken. A target gapped through would fill BETTER than the level, so the
    gap is NOT taken and the level stands. Modelling both the same way would
    make one of the two flatter us.
    """
    if o >= level:
        return level
    return level if hi >= level else None


def buy_fill(px: float) -> float:
    return round(px + SLIPPAGE_TICKS * TICK, 4)


def sell_fill(px: float) -> float:
    return round(px - SLIPPAGE_TICKS * TICK, 4)


# --------------------------------------------------------------------------
# the state machine
# --------------------------------------------------------------------------

def _stop_for(cfg: Config, entry: float, anchor_low: float,
              orb_low: float, orb_width: float) -> float:
    """§6. `anchor_low` is the low of the candle that produced the entry --
    the trigger candle in `none`, the RETEST candle in the retest modes, which
    is the spec's wording and the reason this is an argument rather than a
    lookup."""
    buf = entry * cfg.stop_buffer_pct / 100.0
    if cfg.stop_mode == "structure":
        return anchor_low - buf
    if cfg.stop_mode == "opposite":
        return orb_low - buf
    return entry - cfg.stop_range_frac * orb_width


def _targets(cfg: Config, entry: float, r: float, orb_width: float):
    """(level, fraction-of-position) pairs, nearest first. Empty for a pure
    trail."""
    if cfg.exit_mode == "r_2":
        return [(entry + 2.0 * r, 1.0)]
    if cfg.exit_mode == "r_1_5":
        return [(entry + 1.5 * r, 1.0)]
    if cfg.exit_mode == "r_3_trim":
        return [(entry + 2.0 * r, 0.5), (entry + 3.0 * r, 1.0)]
    if cfg.exit_mode == "range_1x":
        return [(entry + orb_width, 1.0)]
    return []                      # trail_pct


def backtest_session(sess: pd.DataFrame, symbol: str, day: str,
                     cfg: Config = BASELINE,
                     bars: "Bars | None" = None) -> SessionResult:
    """One symbol-day, one cell. `sess` is RTH 1-minute bars, ET-indexed.

    Returns a SessionResult whatever happens, including when nothing happens.
    A day that produced no trade for a NAMED reason and a day that was never
    read are different facts, and only one of them is a problem -- which is
    exactly the distinction `preflight.DayRow.rth_bars` was added to restore.
    """
    res = SessionResult(symbol=symbol, date=day, rth_bars=len(sess))
    if len(sess):
        res.first_ts, res.last_ts = sess.index[0], sess.index[-1]
        res.has_open_bar = any(t.time() == RTH_OPEN for t in sess.index)

    status, rng = opening_range(sess, cfg)
    res.range_bars, res.missing_range_minutes = rng["range_bars"], rng["missing"]
    res.orb_high, res.orb_low = rng["orb_high"], rng["orb_low"]
    res.orb_width, res.width_pct = rng["orb_width"], rng["width_pct"]
    res.status = status
    if status != "OK":
        return res

    hi, lo, width = res.orb_high, res.orb_low, res.orb_width

    # RESAMPLED ONCE, OVER THE WHOLE SESSION, and then indexed into -- not
    # resampled over the post-range slice. The opening range's own buckets are
    # needed: the structure stop anchors on the last bar that had CLOSED when
    # the order filled, and for a break on the very first post-range bar that
    # is a bar inside the range. Slicing first would have made that anchor
    # unreachable and the fallback would have been orb_low, i.e. a `structure`
    # cell quietly running `opposite` on exactly the rows where the two differ
    # most.
    if bars is None:
        bars = trigger_bars(sess, cfg.trigger_bar_minutes)
    elif bars.minutes != cfg.trigger_bar_minutes:
        # A cached view built at a different bar size is not this cell's data.
        # Refusing beats silently resampling, because a grid that quietly
        # re-derived its own bars here would stop being one resample per day
        # and nobody would see the difference in the output.
        raise ValueError(
            f"cached bars are {bars.minutes}-minute; cfg wants "
            f"{cfg.trigger_bar_minutes}")
    end_min = 9 * 60 + 30 + cfg.orb_minutes
    end = dtime(end_min // 60, end_min % 60)
    after = [i for i, t in enumerate(bars.tm) if t >= end]
    if not after:
        res.status = "NO_TRIGGER"
        return res
    start = after[0]

    level = hi * (1.0 + cfg.entry_buffer_pct / 100.0)

    # ---- the downside break: MEASURED, NEVER TRADED (§5.4) ----------------
    # Long-only discards roughly half the sources' signals by construction, so
    # the discarded half is counted rather than assumed away. If the short side
    # is where the edge is, that is worth knowing before the borrow-feasibility
    # work, not after it.
    for j in range(start, len(bars)):
        if bars.c[j] < lo:
            res.down_trigger, res.down_trigger_bar = True, j - start
            break

    # ---- the trigger -----------------------------------------------------
    trig = None
    for j in range(start, len(bars)):
        if cfg.entry_on_close:
            if bars.c[j] > level:
                trig = j
                break
        elif bars.h[j] >= level:
            # V8's resting stop order. It fills on any wick, which is the
            # whole difference: a close-based rule requires the market to HOLD
            # the level for a full bar. Kept as a cell precisely because this
            # project has already been burnt by a touch-based rule -- VW9's
            # vwap_lost fired on the fill bar.
            trig = j
            break
    if trig is None:
        res.status = "NO_TRIGGER"
        return res
    res.up_trigger, res.up_trigger_bar = True, trig - start

    # ---- V2's counter-hypothesis, also measured and not traded (§7.4) -----
    # One source in ten does not trade this breakout. He fades the failed one.
    # It costs two columns to find out whether the premise holds at all here.
    for j in range(trig + 1, min(trig + 1 + cfg.fade_window_bars, len(bars))):
        if bars.c[j] < hi:
            res.faded = True
            back_inside = bars.c[j]
            res.fade_return_pct = (back_inside - lo) / back_inside * 100.0
            break
    else:
        res.faded = False

    # ---- the retest fork (§5.3) ------------------------------------------
    # A retest rule can only REMOVE trades, never add them. That ordering is
    # what makes the comparison legitimate, and it is why `none` returns the
    # trigger bar unchanged rather than running a degenerate search.
    entry_bar, status = _resolve_entry(bars, trig, cfg, hi, lo, width)
    if status != "OK":
        res.status = status
        return res

    if entry_bar >= len(bars):
        res.status = "NO_ENTRY_BAR"
        return res
    # THE ANCHOR IS THE LAST BAR THAT HAD CLOSED WHEN THE ORDER FILLED, in
    # every mode. On a close-based entry that is the trigger candle (or the
    # retest candle), which is §6's wording. On V8's resting order the fill
    # happens DURING the trigger bar, so the trigger bar's own low is not
    # knowable yet -- using it would be a look-ahead that this uniform rule
    # removes rather than special-cases.
    anchor_bar = entry_bar - 1
    if anchor_bar < 0:
        res.status = "NO_STOP_ANCHOR"
        return res
    if bars.tm[entry_bar] >= LAST_ENTRY:
        # §3.3. An entry at 15:56 is a position opened to be flattened four
        # minutes later at the close; it is not the strategy.
        res.status = "TOO_LATE"
        return res

    if cfg.entry_on_close:
        entry = buy_fill(bars.o[entry_bar])
    else:
        # A resting stop at the level fills AT the level, or at the open when
        # the bar gapped through it -- the same gap logic as a stop exit, in
        # the other direction.
        entry = buy_fill(max(level, bars.o[entry_bar]))
    res.entry_px = entry

    if cfg.enforce_price_band and not (PRICE_MIN <= entry <= PRICE_MAX):
        res.status = "OUT_OF_BAND"
        return res

    anchor_low = bars.l[anchor_bar]
    stop = _stop_for(cfg, entry, anchor_low, lo, width)
    r = entry - stop
    res.stop_px, res.r = stop, r
    if r <= 0:
        # The stop is at or above the fill. Not a small trade -- an undefined
        # one, because R is the denominator of every target in §7.1.
        res.status = "R_NOT_POSITIVE"
        return res
    res.r_pct = r / entry * 100.0
    if res.r_pct > cfg.max_r_pct:
        # §6: a size cap does not fix an unusable stop, it just makes the loss
        # smaller and the sample thinner. Skipped and COUNTED.
        res.status = "R_TOO_WIDE"
        return res

    res.status = "OK"
    _run_position(bars, entry_bar, res, cfg, entry, stop, r, width)
    return res


def _resolve_entry(bars, trig: int, cfg: Config, hi: float, lo: float,
                   width: float) -> tuple[int, str]:
    """(entry bar index, status). The stop anchor is always the bar before it.

    `none` enters on the bar after the trigger. The retest modes wait for price
    to come back and then close above the level again; the entry is the bar
    after THAT close -- which is what makes a retest entry closer to the level,
    smaller in R, and therefore never comparable against a `none` cell at a
    different stop rule (§5.3).
    """
    if cfg.retest_mode == "none":
        # A close-based trigger is acted on at the NEXT bar's open, because
        # the trigger close is a price that has already gone (§9). V8's
        # resting order instead fills DURING the trigger bar, on the wick that
        # reached the level.
        return (trig + 1 if cfg.entry_on_close else trig), "OK"

    if cfg.retest_mode == "zone":
        # V4: the retest must reach INTO the 38-62% retracement, not merely
        # touch the level. Measured UP from orb_low a 38% retracement from the
        # high is `lo + ZONE_HI * width`, so the SHALLOW edge of the zone
        # carries the LARGER multiplier -- reading it the other way round is a
        # silent 24%-of-range error in the permissive direction.
        depth = lo + ZONE_HI * width
    else:
        depth = hi

    touched = False
    for j in range(trig + 1, min(trig + 1 + cfg.retest_max_bars, len(bars))):
        c = bars.c[j]
        if c < lo:
            # The setup is dead, not merely waiting. Price closing back below
            # the far side of the range is the break failing, and a rule that
            # kept waiting here would be entering on a third attempt at a level
            # that has already failed twice.
            return -1, "RETEST_FAILED"
        if bars.l[j] <= depth:
            touched = True
        # One bar may BOTH reach the depth and close back above the level --
        # a textbook retest-and-reclaim. Testing the touch first and the
        # reclaim second, with no `continue` between them, is what allows it;
        # skipping to the next bar would have required the reclaim to take an
        # extra bar and quietly deepened every retest entry.
        if touched and c > hi:
            return j + 1, "OK"
    return -1, "RETEST_FAILED"


def _run_position(bars, entry_bar: int, res: SessionResult, cfg: Config,
                  entry: float, stop: float, r: float, width: float) -> None:
    """Walk the bars from the entry bar to the flatten, closing legs as they
    resolve. §7.2's priority order, and the stop wins any bar containing both.

    THE ENTRY BAR IS LIVE. Entry is at its OPEN, so the whole of that bar is
    after the fill and its high and low both count. That is NOT the same
    situation as the live trader's, where a signal bar has already closed
    before the order goes out -- and the difference is why `seed_peak_with_bar_high`
    reads as a contradiction if the two are not held apart. The peak is seeded
    from the FILL either way; what differs is which bars may contribute to it.
    """
    shares = cfg.shares
    remaining = shares
    entry_time = bars.t[entry_bar]
    peak = entry                    # §9: from the fill, never the trigger bar
    stop_level = stop
    targets = _targets(cfg, entry, r, width)
    ti = 0
    be_armed = cfg.exit_mode == "range_1x"
    be_level = entry + 0.5 * width if be_armed else None
    leg = 0

    for j in range(entry_bar, len(bars)):
        ts = bars.t[j]
        held = j - entry_bar

        # The trail and the break-even move both use the peak as it stood at
        # the START of this bar. Updating first and then testing would let a
        # bar's own high raise a stop that its own low then hits -- an exit at
        # a level the position never reached in that order.
        trail_level = (peak * (1.0 - cfg.trail_pct / 100.0)
                       if cfg.exit_mode == "trail_pct" else None)
        effective_stop = stop_level
        if trail_level is not None and trail_level > effective_stop:
            effective_stop = trail_level

        want = targets[ti][0] if ti < len(targets) else None
        hit_stop = fill_below(bars.o[j], bars.l[j], effective_stop)
        hit_target = (fill_above(bars.o[j], bars.h[j], want)
                      if want is not None else None)

        if hit_stop is not None and hit_target is not None:
            # §7.2. On 5-minute bars on a name moving 20% intraday this is not
            # rare, and the count is reported rather than buried -- it says how
            # often the assumption that keeps the result honest actually bit.
            res.both_in_bar += 1

        if hit_stop is not None:
            reason = ("trail" if effective_stop == trail_level
                      else "be_stop" if effective_stop > stop else "stop")
            _close(res, cfg, entry_time, ts, sell_fill(hit_stop), remaining,
                   entry, r, width, reason, held, leg)
            return

        if hit_target is not None:
            frac = targets[ti][1]
            qty = remaining if frac >= 1.0 else int(round(shares * frac))
            qty = min(qty, remaining)
            _close(res, cfg, entry_time, ts, sell_fill(hit_target), qty, entry,
                   r, width, "target", held, leg)
            remaining -= qty
            leg += 1
            ti += 1
            if remaining <= 0:
                return

        # Now the bar's own extremes may move the peak and arm break-even, for
        # the bars that follow.
        peak = max(peak, bars.h[j])
        if be_armed and be_level is not None and bars.h[j] >= be_level:
            stop_level = max(stop_level, entry)

        if cfg.time_stop_bars is not None and held >= cfg.time_stop_bars:
            _close(res, cfg, entry_time, ts, sell_fill(bars.c[j]),
                   remaining, entry, r, width, "time_stop", held, leg)
            return

        if bars.tm[j] >= FLATTEN_BAR:
            _close(res, cfg, entry_time, ts, sell_fill(bars.c[j]),
                   remaining, entry, r, width, "session_end", held, leg)
            return

    # Ran out of bars before 15:55 -- the cache ends early, or the name stopped
    # printing. The position is closed at the last bar there was, and the day
    # is FLAGGED, because a silently-carried position is a P/L that never
    # happened.
    res.open_at_close = True
    _close(res, cfg, entry_time, bars.t[-1], sell_fill(bars.c[-1]),
           remaining, entry, r, width, "session_end", len(bars) - 1 - entry_bar, leg)


def _close(res: SessionResult, cfg: Config, entry_time, ts, px: float,
           qty: int, entry: float, r: float, width: float, reason: str,
           held: int, leg: int) -> None:
    """One closing leg. Commission is per ORDER on both sides, from the same
    schedule `common/friction.py` measures against -- §7.1's warning about
    `r_3_trim` paying the per-order minimum twice is only true if this charges
    it twice, so it does."""
    gross = (px - entry) * qty
    comm = (order_cost(qty, entry, False, COMMISSION_PLAN)
            + order_cost(qty, px, True, COMMISSION_PLAN))
    res.trades.append(Trade(
        symbol=res.symbol, date=res.date,
        entry_time=entry_time,
        entry_px=entry, shares=qty, exit_time=ts, exit_px=px,
        exit_reason=reason, r=r, orb_width=width,
        gross=round(gross, 4), commission=round(comm, 4),
        net=round(gross - comm, 4), bars_held=held, leg=leg))
