#!/usr/bin/env python3
"""W16 OWA-v0: the open-window rule -- bars, indicators, trend filters,
triggers A/B/C, the one-book simulation and the trailing-stop walk.
docs/research/REGISTERED_w16_open_window.md (sec 2-3). Board W16-0040 sub 4.

NO DOLLARS HERE. Everything below is index prices and times. Costs, P&L,
controls, the grid and reporting live in strategy.w16.owa_controls and
strategy.w16.owa_runner; the pre-flight (strategy.w16.owa_preflight) calls
the signal code and `candidate_fill`, and never `walk_exit`.

TWO PRICE SERIES
------------------------------------------------------------------------
Indicators run on the ADJUSTED series, trade prices are the held contract's
REAL prices (sec 2). The adjustment is computed in its causal form: at each
change of held id, every LATER bar is shifted by -(new contract's first price
- old contract's last price), so a bar's adjusted value depends only on rolls
at or before it. It differs from textbook back-adjustment (earlier bars
shifted up) by a constant, which cancels in every registered comparison (EMA
order and gaps, crosses, MACD, ranges, close against the prior high/EMA).
`roll_off` is the amount to ADD to an adjusted level to get a real price.

LOOK-AHEAD GUARDS (sec 7.2) -- WHERE EACH ONE LIVES
------------------------------------------------------------------------
* `filter_state`: a 5-min bar starting at s reads the last filter bar whose
  nominal close is <= s.
* `slot_average`: the value at day d's bar of slot s is the average BEFORE
  that bar was added.
* `adjustment`: cumulative from the start, so later rolls cannot reach back.
* `candidate_fill`: a signal at bar j fills inside [tau_j, tau_j + 5m).
* `walk_exit`: the stop during 5-min bar k is the one set at the close of
  bar k-1; the walk starts at the fill minute.
* `simulate_book`: a new signal bar must start after the exit minute of the
  trade before it; the cap counts fills already made.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.w16.sessions import early_close_days, market_closed_days

ET = "America/New_York"
TICK = 0.25
MARKET = "NQ"

NS_MIN = 60_000_000_000
NS_DAY = 1440 * NS_MIN

# ---- registered values (sec 2-3). Changing one is a new hypothesis. ----
BIG_MULT = 1.5               # big bar: range >= this x the slot average
CROSS_K = 3                  # A: EMA cross within k bars back
MACD_K = 3                   # C: MACD cross within k bars back
PULLBACK_BARS = 12           # B: bars armed after the big bar
SWING_BARS = 6               # initial stop swing lookback
STOP_MIN_ATR = 0.5
STOP_MAX_ATR = 2.0
TRAIL_ATR = 2.5
MAX_FILLS_PER_DAY = 2
SLOT_LEN = 20                # slot average weight 2 / (SLOT_LEN + 1)
SLOT_MIN_OBS = 20
ATR_LEN = 14
EMA_FAST, EMA_SLOW = 9, 21
MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9

WINDOW_FIRST_MIN = 8 * 60           # first signal bar starts 08:00
WINDOW_LAST_MIN = 11 * 60 + 55      # last signal bar starts 11:55
WINDOW_END_MIN = 12 * 60            # latest fill 12:00
RTH_OPEN_MIN = 9 * 60 + 30          # pre-open / RTH split of fills
FLAT_MIN = 15 * 60 + 55             # time exit
FLAT_MIN_EARLY = 12 * 60 + 55
SKIP_FIRST_MIN = 7 * 60             # data-gap window start
SKIP_GAP_MIN = 15
WARMUP_5M, WARMUP_15M, WARMUP_1H = 35, 21, 21

LONG, SHORT = "long", "short"
UP, DOWN, NONE = 1, -1, 0
FILTERS = {"1H": 60, "15": 15}
TRIGGERS = ("A", "B", "C")
ALL_BOOK = "All"                    # A or B or C, first in that order (sec 6, reported)


@dataclass(frozen=True)
class Params:
    """The grid dimensions (sec 8.3). The defaults ARE the registered rule."""
    big_mult: float = BIG_MULT
    macd_k: int = MACD_K
    trail_mult: float = TRAIL_ATR


REGISTERED = Params()


# ---------------------------------------------------------------------
# indicators (sec 3.1)
# ---------------------------------------------------------------------

def ema(values: np.ndarray, length: int) -> np.ndarray:
    """Exponential average, weight 2/(n+1), seeded with the first value
    (Pine ta.ema)."""
    return pd.Series(values, dtype=float).ewm(
        alpha=2.0 / (length + 1), adjust=False).mean().to_numpy()


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               length: int = ATR_LEN) -> np.ndarray:
    """Pine ta.atr: Wilder average (weight 1/n) of true range, seeded with
    the simple mean of the first n true ranges; NaN before that. The first
    bar's true range is its high - low."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < length:
        return out
    prev = np.concatenate(([np.nan], close[:-1]))
    tr = np.fmax(high - low, np.fmax(np.abs(high - prev), np.abs(low - prev)))
    seeded = np.concatenate(([tr[:length].mean()], tr[length:]))
    out[length - 1:] = pd.Series(seeded).ewm(alpha=1.0 / length, adjust=False).mean().to_numpy()
    return out


def crossed_up(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a_i > b_i and a_(i-1) <= b_(i-1). False on the first bar."""
    out = np.zeros(len(a), dtype=bool)
    out[1:] = (a[1:] > b[1:]) & (a[:-1] <= b[:-1])
    return out


def within_last(flags: np.ndarray, k: int) -> np.ndarray:
    """True at j if `flags` was true at any of bars j-k .. j."""
    out = flags.copy()
    for back in range(1, k + 1):
        out[back:] |= flags[:-back]
    return out


def slot_average(slot: np.ndarray, rng: np.ndarray, length: int = SLOT_LEN):
    """For each bar: (average of the range at the same clock slot over EARLIER
    days, number of earlier observations). Exponential, weight 2/(length+1),
    seeded with the first observation; the bar itself is added only after it
    has been judged (sec 3.1). A slot occurs once per calendar day."""
    prev = np.full(len(rng), np.nan)
    n_prior = np.zeros(len(rng), dtype=np.int64)
    order = np.argsort(slot, kind="stable")          # stable: keeps time order inside a slot
    s = slot[order]
    starts = np.flatnonzero(np.concatenate(([True], s[1:] != s[:-1])))
    ends = np.concatenate((starts[1:], [len(s)]))
    for a, b in zip(starts, ends):
        idx = order[a:b]
        after = ema(rng[idx], length)
        prev[idx[1:]] = after[:-1]
        n_prior[idx] = np.arange(len(idx))
    return prev, n_prior


# ---------------------------------------------------------------------
# bars
# ---------------------------------------------------------------------

@dataclass
class Bars:
    """Clock-anchored bars of one size; a period with no 1-minute bar has no
    bar. `start` is UTC ns; NY offsets are whole hours, so UTC anchoring and
    NY anchoring give the same bars."""
    period_min: int
    start: np.ndarray            # UTC ns of the period start
    close_time: np.ndarray       # UTC ns, start + period (when it is knowable)
    day: np.ndarray              # NY calendar day number
    minute: np.ndarray           # NY minute of day of the period start
    o: np.ndarray                # real prices
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    ao: np.ndarray               # adjusted prices
    ah: np.ndarray
    al: np.ndarray
    ac: np.ndarray
    first: np.ndarray            # index of the first 1-minute bar in it
    last: np.ndarray             # index of the last 1-minute bar in it

    def __len__(self) -> int:
        return len(self.start)


@dataclass
class Minutes:
    t: np.ndarray                # UTC ns of the bar start
    day: np.ndarray              # NY calendar day number
    minute: np.ndarray           # NY minute of day
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    held: np.ndarray
    roll_off: np.ndarray         # real price = adjusted + roll_off
    bar5: np.ndarray = field(default=None)   # index of the 5-min bar holding each minute

    def __len__(self) -> int:
        return len(self.t)


def adjustment(o: np.ndarray, c: np.ndarray, held: np.ndarray) -> np.ndarray:
    """Cumulative roll gap at each 1-minute bar: at a change of held id the
    gap is (new contract's first price - old contract's last price), added
    from that bar onward."""
    step = np.zeros(len(o))
    if len(o) > 1:
        rolled = held[1:] != held[:-1]
        step[1:][rolled] = o[1:][rolled] - c[:-1][rolled]
    return np.cumsum(step)


def day_number(date_str: str) -> int:
    return int(np.datetime64(date_str, "D").astype(np.int64))


def day_string(day: int) -> str:
    return str(np.datetime64(int(day), "D"))


def hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def ny_string(t_ns: int) -> str:
    """A UTC ns stamp as 'YYYY-MM-DD HH:MM' New York wall clock."""
    return pd.Timestamp(int(t_ns), tz="UTC").tz_convert(ET).strftime("%Y-%m-%d %H:%M")


def build_minutes(df_1m: pd.DataFrame) -> Minutes:
    """From a tz-aware 1-minute frame (open/high/low/close and held_id or
    instrument_id)."""
    if df_1m.index.tz is None:
        raise ValueError("index must be tz-aware")
    df = df_1m if df_1m.index.is_monotonic_increasing else df_1m.sort_index()
    if df.index.has_duplicates:
        raise ValueError("duplicate 1-minute timestamps -- is more than one contract series loaded?")
    id_col = "held_id" if "held_id" in df.columns else "instrument_id"
    utc = df.index.tz_convert("UTC").as_unit("ns")
    t = utc.asi8.copy()
    naive = utc.tz_convert(ET).tz_localize(None).as_unit("ns").asi8
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    if not (np.isfinite(o).all() and np.isfinite(h).all() and np.isfinite(l).all()
            and np.isfinite(c).all()):
        raise ValueError("non-finite price in the 1-minute bars")
    held = df[id_col].to_numpy()
    return Minutes(t=t, day=naive // NS_DAY, minute=(naive % NS_DAY) // NS_MIN,
                   o=o, h=h, l=l, c=c, held=held, roll_off=adjustment(o, c, held))


def resample(m: Minutes, period_min: int) -> Bars:
    period = period_min * NS_MIN
    key = m.t // period
    first = np.flatnonzero(np.concatenate(([True], key[1:] != key[:-1])))
    last = np.concatenate((first[1:], [len(key)])) - 1
    start = key[first] * period
    off = m.roll_off
    return Bars(
        period_min=period_min, start=start, close_time=start + period,
        day=m.day[first], minute=(m.minute[first] // period_min) * period_min,
        o=m.o[first], h=np.maximum.reduceat(m.h, first), l=np.minimum.reduceat(m.l, first),
        c=m.c[last],
        ao=m.o[first] - off[first], ah=np.maximum.reduceat(m.h - off, first),
        al=np.minimum.reduceat(m.l - off, first), ac=m.c[last] - off[last],
        first=first, last=last)


def filter_state(bar_start: np.ndarray, htf_close_time: np.ndarray,
                 htf_state: np.ndarray):
    """(state, completed filter bars) for each 5-min bar start: the state of
    the last filter bar that closed at or before that start (sec 3.2)."""
    idx = np.searchsorted(htf_close_time, bar_start, side="right") - 1
    state = np.where(idx >= 0, htf_state[np.clip(idx, 0, None)], NONE)
    return state.astype(np.int64), idx + 1


def trend_of(htf: Bars) -> np.ndarray:
    """UP if EMA9 > EMA21, DOWN if EMA9 < EMA21, else NONE, per filter bar."""
    fast, slow = ema(htf.ac, EMA_FAST), ema(htf.ac, EMA_SLOW)
    return np.where(fast > slow, UP, np.where(fast < slow, DOWN, NONE))


# ---------------------------------------------------------------------
# the prepared market: bars, indicators, days
# ---------------------------------------------------------------------

@dataclass
class Day:
    day: int
    date: str
    early: bool
    status: str                  # "tradable" | "skipped" | "warmup"
    window: np.ndarray           # 5-min bar indices starting 08:00..11:55
    exit_idx: int                # first 1-min bar at/after the flat time, -1 if none
    last_idx: int                # last 1-min bar of the NY date, -1 if none
    roll_inside: bool            # held id changes inside 08:00..flat


@dataclass
class Market:
    m1: Minutes
    b5: Bars
    e9: np.ndarray
    e21: np.ndarray
    atr: np.ndarray
    macd: np.ndarray
    signal: np.ndarray
    slot_prev: np.ndarray
    slot_n: np.ndarray
    filt: dict                   # "1H"/"15" -> state per 5-min bar
    filt_n: dict                 # "1H"/"15" -> completed filter bars per 5-min bar
    days: list                   # list[Day], every XNYS trading day in the data's span

    def day_by_number(self) -> dict:
        return {d.day: d for d in self.days}


def trading_calendar(first_day: int, last_day: int) -> list[tuple[int, str, bool]]:
    """(day number, date, early close) for every XNYS trading day in the
    span -- the same calendar as strategy.w16.sessions, computed once."""
    if last_day < first_day:
        return []
    y0 = int(day_string(first_day)[:4])
    y1 = int(day_string(last_day)[:4])
    closed = market_closed_days(y0, y1)
    early = early_close_days(y0, y1)
    out = []
    for d in range(first_day, last_day + 1):
        if (d + 3) % 7 >= 5:             # 1970-01-01 was a Thursday; 5, 6 = Sat, Sun
            continue
        s = day_string(d)
        if s in closed:
            continue
        out.append((d, s, s in early))
    return out


def has_gap(minutes_of_day: np.ndarray, flat_min: int) -> bool:
    """True if there is a gap of more than 15 minutes between consecutive
    1-minute bars anywhere in 07:00..flat, counting the two edges of that
    window (a day whose data starts late or stops early is a gap)."""
    inside = minutes_of_day[(minutes_of_day >= SKIP_FIRST_MIN) & (minutes_of_day <= flat_min)]
    if len(inside) == 0:
        return True
    points = np.concatenate(([SKIP_FIRST_MIN], inside, [flat_min]))
    return bool(np.max(np.diff(points)) > SKIP_GAP_MIN)


def prepare(df_1m: pd.DataFrame) -> Market:
    """Everything that does not depend on a trigger or a grid value."""
    m1 = build_minutes(df_1m)
    if len(m1) == 0:
        raise ValueError("no 1-minute bars")
    b5 = resample(m1, 5)
    m1.bar5 = np.repeat(np.arange(len(b5)), b5.last - b5.first + 1)

    e9, e21 = ema(b5.ac, EMA_FAST), ema(b5.ac, EMA_SLOW)
    atr = wilder_atr(b5.ah, b5.al, b5.ac)
    macd = ema(b5.ac, MACD_FAST) - ema(b5.ac, MACD_SLOW)
    signal = ema(macd, MACD_SIG)
    slot_prev, slot_n = slot_average(b5.minute, b5.ah - b5.al)

    filt, filt_n, htf_closes = {}, {}, {}
    for name, minutes in FILTERS.items():
        htf = resample(m1, minutes)
        htf_closes[name] = htf.close_time
        filt[name], filt_n[name] = filter_state(b5.start, htf.close_time, trend_of(htf))

    # NY days are contiguous and ascending in both arrays
    m_first = np.searchsorted(m1.day, np.arange(m1.day[0], m1.day[-1] + 2))
    b_first = np.searchsorted(b5.day, np.arange(m1.day[0], m1.day[-1] + 2))
    days = []
    for d, date_str, early in trading_calendar(int(m1.day[0]), int(m1.day[-1])):
        k = d - int(m1.day[0])
        a, z = int(m_first[k]), int(m_first[k + 1])          # minutes of this NY date
        ba, bz = int(b_first[k]), int(b_first[k + 1])        # 5-min bars of this NY date
        flat = FLAT_MIN_EARLY if early else FLAT_MIN
        minute = m1.minute[a:z]
        window = ba + np.flatnonzero((b5.minute[ba:bz] >= WINDOW_FIRST_MIN)
                                     & (b5.minute[ba:bz] <= WINDOW_LAST_MIN))
        at_flat = np.flatnonzero(minute >= flat)
        exit_idx = a + int(at_flat[0]) if len(at_flat) else -1
        held = m1.held[a:z][(minute >= WINDOW_FIRST_MIN) & (minute <= flat)]
        roll_inside = bool(len(held) and (held != held[0]).any())

        # warm-up first (sec 2: "counted as warm-up, not skipped"): bar counts at
        # 08:00, and the slot average valid for every signal-window bar of the day
        t08 = int(pd.Timestamp(f"{date_str} 08:00", tz=ET).as_unit("ns").value)
        warm = (int(np.searchsorted(b5.close_time, t08, side="right")) < WARMUP_5M
                or int(np.searchsorted(htf_closes["15"], t08, side="right")) < WARMUP_15M
                or int(np.searchsorted(htf_closes["1H"], t08, side="right")) < WARMUP_1H
                or bool((slot_n[window] < SLOT_MIN_OBS).any()))
        if warm:
            status = "warmup"
        elif has_gap(minute, flat):
            status = "skipped"
        else:
            status = "tradable"
        days.append(Day(day=d, date=date_str, early=early, status=status, window=window,
                        exit_idx=exit_idx, last_idx=(z - 1) if z > a else -1,
                        roll_inside=roll_inside))
    return Market(m1=m1, b5=b5, e9=e9, e21=e21, atr=atr, macd=macd, signal=signal,
                  slot_prev=slot_prev, slot_n=slot_n, filt=filt, filt_n=filt_n, days=days)


# ---------------------------------------------------------------------
# signals (sec 3.4)
# ---------------------------------------------------------------------

@dataclass
class Signals:
    """Per 5-min bar, for one filter timeframe and one set of grid values.
    `a_*` and `c_*` are finished trigger conditions. B is path-dependent
    (arming resets on a fill), so it is given as its three parts."""
    big: np.ndarray
    big_up: np.ndarray
    big_dn: np.ndarray
    a_long: np.ndarray
    a_short: np.ndarray
    c_long: np.ndarray
    c_short: np.ndarray
    b_arm_long: np.ndarray       # big green, filter UP, bar starts 08:00..11:55
    b_arm_short: np.ndarray
    b_touch_long: np.ndarray     # low <= EMA9
    b_touch_short: np.ndarray    # high >= EMA9
    b_fire_long: np.ndarray      # filter, EMA order, close beyond prior bar and EMA9
    b_fire_short: np.ndarray


def compute_signals(mk: Market, filter_name: str, params: Params = REGISTERED) -> Signals:
    b = mk.b5
    f = mk.filt[filter_name]
    up, dn = f == UP, f == DOWN
    e9, e21 = mk.e9, mk.e21
    rng = b.ah - b.al
    with np.errstate(invalid="ignore"):
        big = (mk.slot_n >= SLOT_MIN_OBS) & (rng >= params.big_mult * mk.slot_prev)
    big_up = big & (b.ac > b.ao)
    big_dn = big & (b.ac < b.ao)

    x_up, x_dn = crossed_up(e9, e21), crossed_up(e21, e9)
    m_up, m_dn = crossed_up(mk.macd, mk.signal), crossed_up(mk.signal, mk.macd)

    a_long = up & (e9 > e21) & within_last(x_up, CROSS_K) & big_up
    a_short = dn & (e9 < e21) & within_last(x_dn, CROSS_K) & big_dn

    n = len(b)
    rising = np.zeros(n, dtype=bool)
    falling = np.zeros(n, dtype=bool)
    narrow_below = np.zeros(n, dtype=bool)      # EMA21 - EMA9 narrowed
    narrow_above = np.zeros(n, dtype=bool)      # EMA9 - EMA21 narrowed
    gap = e21 - e9
    rising[1:] = e9[1:] > e9[:-1]
    falling[1:] = e9[1:] < e9[:-1]
    narrow_below[1:] = gap[1:] < gap[:-1]
    narrow_above[1:] = gap[1:] > gap[:-1]
    c_long = (up & within_last(m_up, params.macd_k) & rising
              & (((e9 <= e21) & narrow_below) | x_up))
    c_short = (dn & within_last(m_dn, params.macd_k) & falling
               & (((e9 >= e21) & narrow_above) | x_dn))

    in_window = (b.minute >= WINDOW_FIRST_MIN) & (b.minute <= WINDOW_LAST_MIN)
    above_prior = np.zeros(n, dtype=bool)
    below_prior = np.zeros(n, dtype=bool)
    above_prior[1:] = b.ac[1:] > b.ah[:-1]
    below_prior[1:] = b.ac[1:] < b.al[:-1]
    return Signals(
        big=big, big_up=big_up, big_dn=big_dn,
        a_long=a_long, a_short=a_short, c_long=c_long, c_short=c_short,
        b_arm_long=big_up & up & in_window, b_arm_short=big_dn & dn & in_window,
        b_touch_long=b.al <= e9, b_touch_short=b.ah >= e9,
        b_fire_long=up & (e9 > e21) & above_prior & (b.ac > e9),
        b_fire_short=dn & (e9 < e21) & below_prior & (b.ac < e9))


class PullbackState:
    """Trigger B's arming for one side (sec 3.4): armed by a qualifying big
    bar i for bars j with 1 <= j - i <= 12; a later one re-arms and clears
    the touch; arming ends at NY midnight (a new object per day) and on a
    B fill (`reset`)."""

    __slots__ = ("armed_at", "touched")

    def __init__(self):
        self.armed_at = None
        self.touched = False

    def step(self, j: int, qualifies: bool, touches: bool, fires: bool) -> bool:
        if qualifies:
            self.armed_at, self.touched = j, False
        if self.armed_at is None or not 1 <= j - self.armed_at <= PULLBACK_BARS:
            return False
        if touches:
            self.touched = True
        return self.touched and fires

    def reset(self):
        self.armed_at, self.touched = None, False


# ---------------------------------------------------------------------
# entry and exit (sec 3.5, 3.6)
# ---------------------------------------------------------------------

def floor_tick(x):
    return np.floor(np.asarray(x) / TICK + 1e-9) * TICK


def ceil_tick(x):
    return np.ceil(np.asarray(x) / TICK - 1e-9) * TICK


def nearest_tick(x: float) -> float:
    return math.floor(x / TICK + 0.5) * TICK


def candidate_fill(mk: Market, j: int, *, at_signal_close: bool = False):
    """(1-min index, fill price, fill time ns) for a signal at 5-min bar j,
    or None if it must be dropped. Registered: the open of the first 1-min bar
    starting in [tau_j, tau_j + 5m). `at_signal_close` is the reported Pine
    view: bar j's close, walked from the first minute at or after tau_j."""
    m1, b = mk.m1, mk.b5
    tau = int(b.close_time[j])
    i = int(np.searchsorted(m1.t, tau, side="left"))
    if i >= len(m1):
        return None
    if at_signal_close:
        if m1.day[i] != b.day[j]:
            return None
        return i, float(b.c[j]), tau
    if m1.t[i] >= tau + 5 * NS_MIN:
        return None
    return i, float(m1.o[i]), int(m1.t[i])


def initial_stop(mk: Market, j: int, fill_idx: int, fill_price: float, side: str) -> float:
    """1 tick beyond the 6-bar swing ending at the signal bar, the distance
    from the fill clamped to [0.5, 2.0] x ATR_j, rounded to the nearest tick,
    at least 1 tick from the fill (sec 3.6)."""
    b = mk.b5
    lo = max(0, j - SWING_BARS + 1)
    off = float(mk.m1.roll_off[fill_idx])      # adjusted level -> the fill contract's price
    atr = float(mk.atr[j])
    if side == LONG:
        swing = float(b.al[lo:j + 1].min()) + off - TICK
        dist = fill_price - swing
    else:
        swing = float(b.ah[lo:j + 1].max()) + off + TICK
        dist = swing - fill_price
    dist = min(max(dist, STOP_MIN_ATR * atr), STOP_MAX_ATR * atr)
    if side == LONG:
        return min(nearest_tick(fill_price - dist), fill_price - TICK)
    return max(nearest_tick(fill_price + dist), fill_price + TICK)


def walk_exit(mk: Market, day: Day, fill_idx: int, fill_price: float, side: str,
              stop0: float, trail_mult: float = TRAIL_ATR):
    """(exit 1-min index, exit price, reason). Reasons: "initial_stop" (the
    stop had not moved), "trail_stop", "time" (open of the first 1-min bar at
    or after the flat time), "time_no_bar" (the date has no such bar: the last
    bar's close; counted).

    The stop during 5-min bar k is the level set at the close of bar k-1; at
    each close best = max(best, high_k), best starting at the fill price, and
    stop = max(stop, best - mult x ATR_k) rounded away from the market
    (shorts mirrored). Walked on 1-min bars from the fill minute: a bar that
    opens through the stop fills at its open, else at the stop."""
    m1, b = mk.m1, mk.b5
    end = day.exit_idx if day.exit_idx >= 0 else day.last_idx + 1
    if fill_idx < end:
        bars = m1.bar5[fill_idx:end]
        b0 = int(bars[0])
        bn = int(bars[-1]) + 1
        atr = mk.atr[b0:bn]
        if side == LONG:
            best = np.maximum.accumulate(np.maximum(b.h[b0:bn], fill_price))
            after = np.maximum.accumulate(np.fmax(floor_tick(best - trail_mult * atr), stop0))
        else:
            best = np.minimum.accumulate(np.minimum(b.l[b0:bn], fill_price))
            after = np.minimum.accumulate(np.fmin(ceil_tick(best + trail_mult * atr), stop0))
        during = np.empty(bn - b0)
        during[0] = stop0
        during[1:] = after[:-1]
        stops = during[bars - b0]
        if side == LONG:
            hit = m1.l[fill_idx:end] <= stops
        else:
            hit = m1.h[fill_idx:end] >= stops
        k = int(hit.argmax())
        if hit[k]:
            i = fill_idx + k
            stop = float(stops[k])
            op = float(m1.o[i])
            gapped = op <= stop if side == LONG else op >= stop
            return i, (op if gapped else stop), ("initial_stop" if stop == stop0 else "trail_stop")
    if day.exit_idx >= 0:
        i = max(day.exit_idx, fill_idx)
        return i, float(m1.o[i]), "time"
    i = day.last_idx
    return i, float(m1.c[i]), "time_no_bar"


def make_trade(mk: Market, day: Day, j: int, side: str, trigger: str, fill_idx: int,
               fill_price: float, fill_time: int, trail_mult: float) -> dict:
    stop0 = initial_stop(mk, j, fill_idx, fill_price, side)
    exit_idx, exit_price, reason = walk_exit(mk, day, fill_idx, fill_price, side, stop0, trail_mult)
    m1 = mk.m1
    fill_minute = int(m1.minute[fill_idx])
    exit_time = int(m1.t[exit_idx])
    return {
        "date": day.date, "market": MARKET, "direction": side, "trigger": trigger,
        "signal_idx": int(j), "signal_bar": hhmm(int(mk.b5.minute[j])),
        "fill_idx": int(fill_idx), "fill_time": ny_string(fill_time),
        "fill_minute": hhmm(fill_minute), "pre_open": fill_minute < RTH_OPEN_MIN,
        "fill_price": float(fill_price), "stop": float(stop0),
        "stop_dist": abs(float(fill_price) - float(stop0)), "atr_signal": float(mk.atr[j]),
        "exit_idx": int(exit_idx), "exit_time": ny_string(exit_time),
        "exit_price": float(exit_price), "exit_reason": reason,
        "hold_minutes": max(0.0, (exit_time - fill_time) / NS_MIN),
        "voided": bool(m1.held[fill_idx] != m1.held[exit_idx]),
        "entry_fill_kind": "market_or_stop", "exit_fill_kind": "market_or_stop",
    }


# ---------------------------------------------------------------------
# one book (sec 3.5): one trigger set, one filter, both sides
# ---------------------------------------------------------------------

def simulate_book(mk: Market, sig: Signals, trigger: str, dates=None, *,
                  params: Params = REGISTERED, sides=(LONG, SHORT),
                  max_fills: int | None = MAX_FILLS_PER_DAY,
                  at_signal_close: bool = False, exits: bool = True) -> dict:
    """Run one book over the tradable days in `dates` (None = every tradable
    day). `trigger` is "A", "B", "C" or "All". Returns {"trades", "signals",
    "dropped", "days"}.

    `exits=False` is the pre-flight (sec 7.1): `walk_exit` is never called, so
    only the first fill of a day exists (the cap and re-entry depend on exits),
    and B's arming is reset by that first fill only. Each day's row then also
    carries how many of its signals had a fill bar."""
    if trigger not in TRIGGERS and trigger != ALL_BOOK:
        raise ValueError(f"unknown trigger {trigger!r}")
    names = TRIGGERS if trigger == ALL_BOOK else (trigger,)
    wanted = None if dates is None else set(dates)
    trades: list[dict] = []
    signals: list[dict] = []
    dropped: list[dict] = []
    day_rows: list[dict] = []
    start = mk.b5.start

    for day in mk.days:
        if day.status != "tradable" or (wanted is not None and day.date not in wanted):
            continue
        pb = {LONG: PullbackState(), SHORT: PullbackState()}
        busy_until = None            # exit minute (ns) of the last trade of the day
        n_fills = 0
        fillable = 0
        first_fill = None
        for j in day.window:
            j = int(j)
            hits = {LONG: [], SHORT: []}
            for side in (LONG, SHORT):
                is_long = side == LONG
                for name in names:
                    if name == "A":
                        fired = bool((sig.a_long if is_long else sig.a_short)[j])
                    elif name == "C":
                        fired = bool((sig.c_long if is_long else sig.c_short)[j])
                    else:
                        fired = pb[side].step(
                            j,
                            bool((sig.b_arm_long if is_long else sig.b_arm_short)[j]),
                            bool((sig.b_touch_long if is_long else sig.b_touch_short)[j]),
                            bool((sig.b_fire_long if is_long else sig.b_fire_short)[j]))
                    if fired:
                        hits[side].append(name)
            chosen = None
            for side in (LONG, SHORT):                     # long before short
                if side in sides and hits[side]:
                    chosen = (side, hits[side][0])         # A, B, C order
                    break
            if chosen is None:
                continue
            side, name = chosen
            fill = candidate_fill(mk, j, at_signal_close=at_signal_close)
            signals.append({"date": day.date, "idx": j, "direction": side, "trigger": name,
                            "fillable": fill is not None})
            if fill is not None:
                fillable += 1
            free = busy_until is None or int(start[j]) > busy_until
            capped = max_fills is not None and n_fills >= max_fills
            if not exits:
                free = first_fill is None
                capped = False
            if not free or capped:
                continue
            if fill is None:
                dropped.append({"date": day.date, "idx": j, "direction": side, "trigger": name})
                continue
            fill_idx, fill_price, fill_time = fill
            n_fills += 1
            if exits:
                trade = make_trade(mk, day, j, side, name, fill_idx, fill_price, fill_time,
                                   params.trail_mult)
                trades.append(trade)
                busy_until = int(mk.m1.t[trade["exit_idx"]])
            else:
                stop0 = initial_stop(mk, j, fill_idx, fill_price, side)
                first_fill = {
                    "date": day.date, "direction": side, "trigger": name, "signal_idx": j,
                    "fill_idx": fill_idx, "fill_price": fill_price,
                    "fill_minute": int(mk.m1.minute[fill_idx]),
                    "stop_dist": abs(fill_price - stop0)}
                trades.append(first_fill)
            if name == "B":
                pb[side].reset()
        day_rows.append({"date": day.date, "fills": n_fills, "fillable_signals": fillable})
    return {"trades": trades, "signals": signals, "dropped": dropped, "days": day_rows}
