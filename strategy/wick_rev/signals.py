#!/usr/bin/env python3
"""WICK-REV features and the reversal race. W15-0063, REGISTERED_wick_reversal.md sec 3.

LOOK-AHEAD DISCIPLINE (gate G3, each guarded by a test that a one-bar shift would break)
  * context (up / down) uses C[t-1] against EMA20[t-1]; the candle itself never decides it;
  * the size bucket divides the range by ATR(14) at t-1;
  * the race lines D = C - k*ATR and U = C + k*ATR use ATR at t, are fixed at the close of t,
    and are scanned from bar t+1 onward;
  * every feature at t depends on bars <= t only (test_features_do_not_look_ahead).

`race` and everything in `trades.py` produce OUTCOMES. The count-only pre-flight (G2) must never
call them: `counts_only` below is the only path it uses, and a test enforces it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.wick_rev import spec as S

REV, CONT, AMBIG, NONE = 1, 2, 3, 0          # race outcome codes


@dataclass
class Series:
    """Back-adjusted bar arrays for one market / timeframe (sorted by time)."""
    market: str
    tf: str
    t_open: np.ndarray        # int64 ns UTC
    t_end: np.ndarray         # int64 ns UTC
    session: np.ndarray       # datetime64[D]
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    held: np.ndarray
    short: np.ndarray         # bool
    fine_t: np.ndarray | None = None      # finer bars (ns) for same-bar double touches
    fine_h: np.ndarray | None = None
    fine_l: np.ndarray | None = None

    @property
    def n(self) -> int:
        return len(self.c)


def series_from_bars(bars_adj: pd.DataFrame, market: str, tf: str, fine: pd.DataFrame | None = None) -> Series:
    b = bars_adj.sort_values("t_open").reset_index(drop=True)
    ns = lambda x: pd.DatetimeIndex(x).tz_convert("UTC").asi8 if getattr(pd.DatetimeIndex(x), "tz", None) is not None \
        else pd.DatetimeIndex(x).asi8
    s = Series(market, tf, ns(b["t_open"]), ns(b["t_end"]),
               pd.to_datetime(b["session"]).to_numpy().astype("datetime64[D]"),
               b["open_adj"].to_numpy(float), b["high_adj"].to_numpy(float), b["low_adj"].to_numpy(float),
               b["close_adj"].to_numpy(float), b["held_id"].to_numpy(), b["short"].to_numpy(bool))
    if fine is not None and len(fine):
        f = fine.sort_values("t_open")
        s.fine_t, s.fine_h, s.fine_l = ns(f["t_open"]), f["high_adj"].to_numpy(float), f["low_adj"].to_numpy(float)
    return s


# --- indicators -----------------------------------------------------------------------------
def wilder_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = S.ATR_LEN) -> np.ndarray:
    """ATR(n), Wilder smoothing, known at the close of bar t. NaN until n bars exist."""
    m = len(c)
    out = np.full(m, np.nan)
    if m < n + 1:
        return out
    tr = np.empty(m)
    tr[0] = h[0] - l[0]
    pc = c[:-1]
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    out[n - 1] = tr[:n].mean()
    for i in range(n, m):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def ema(c: np.ndarray, n: int = S.EMA_LEN) -> np.ndarray:
    a = 2.0 / (n + 1)
    out = np.empty(len(c))
    if len(c) == 0:
        return out
    out[0] = c[0]
    for i in range(1, len(c)):
        out[i] = a * c[i] + (1 - a) * out[i - 1]
    return out


# --- features ---------------------------------------------------------------------------------
@dataclass
class Features:
    rng: np.ndarray
    uwr: np.ndarray
    lwr: np.ndarray
    atr: np.ndarray
    size_cat: np.ndarray       # 0 small, 1 normal, 2 large, -1 unknown
    ctx: np.ndarray            # +1 up, -1 down, 0 none
    colour: np.ndarray         # +1 green, -1 red, 0 doji
    star: np.ndarray           # classic shooting star (up ctx)
    hammer: np.ndarray         # classic hammer (down ctx)
    ok: np.ndarray             # has all inputs (warm-up, H > L, ATR, context) - before roll / tail drops
    drop_hl: np.ndarray        # H == L
    drop_warm: np.ndarray
    drop_roll: np.ndarray
    drop_tail: np.ndarray


def features(s: Series) -> Features:
    n = s.n
    rng = s.h - s.l
    with np.errstate(divide="ignore", invalid="ignore"):
        uwr = np.where(rng > 0, (s.h - s.c) / rng, np.nan)
        lwr = np.where(rng > 0, (s.c - s.l) / rng, np.nan)
    atr = wilder_atr(s.h, s.l, s.c)
    e = ema(s.c)
    ctx = np.zeros(n, dtype=int)
    ctx[1:] = np.where(s.c[:-1] > e[:-1], 1, np.where(s.c[:-1] < e[:-1], -1, 0))          # t-1, not t
    atr_prev = np.full(n, np.nan)
    atr_prev[1:] = atr[:-1]                                                              # t-1, not t
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = rng / atr_prev
    size = np.where(np.isnan(ratio), -1, np.where(ratio < S.SIZE_EDGES[0], 0,
                                                  np.where(ratio > S.SIZE_EDGES[1], 2, 1)))
    colour = np.sign(s.c - s.o).astype(int)
    body = np.abs(s.c - s.o)
    upper_wick = s.h - np.maximum(s.o, s.c)
    lower_wick = np.minimum(s.o, s.c) - s.l
    star = (ctx == 1) & (upper_wick >= S.STAR_WICK_TO_BODY * body) & (uwr >= S.STAR_RATIO)
    hammer = (ctx == -1) & (lower_wick >= S.STAR_WICK_TO_BODY * body) & (lwr >= S.STAR_RATIO)
    idx = np.arange(n)
    drop_warm = idx < S.WARMUP
    drop_hl = ~(rng > 0)
    # roll: held_id changes between bars; drop a signal on a roll session or with a roll in t+1..t+20
    roll = np.zeros(n, dtype=bool)
    roll[1:] = s.held[1:] != s.held[:-1]
    roll_sessions = set(s.session[roll].tolist())
    on_roll_session = np.fromiter((x in roll_sessions for x in s.session.tolist()), bool, n) if n else np.zeros(0, bool)
    cs = np.concatenate([[0], np.cumsum(roll)])
    hi = np.minimum(idx + S.LOOKAHEAD, n - 1)
    ahead = (cs[hi + 1] - cs[idx + 1]) > 0                       # roll flagged in t+1 .. t+20
    drop_roll = on_roll_session | ahead
    drop_tail = idx + S.LOOKAHEAD >= n                           # the 20-bar look-ahead must exist
    ok = ~drop_warm & ~drop_hl & ~np.isnan(atr) & ~np.isnan(atr_prev) & (ctx != 0)
    return Features(rng, uwr, lwr, atr, size, ctx, colour, star, hammer, ok, drop_hl, drop_warm,
                    drop_roll, drop_tail)


def valid_mask(f: Features) -> np.ndarray:
    return f.ok & ~f.drop_roll & ~f.drop_tail


def ratio_for(f: Features, side: int) -> np.ndarray:
    """The wick ratio the hypothesis uses: UWR for up-context (side +1), LWR for down-context (-1)."""
    return f.uwr if side == 1 else f.lwr


def bucket_of(r: np.ndarray) -> np.ndarray:
    b = np.floor(np.nan_to_num(r, nan=-1.0) * 10).astype(int)
    return np.where(np.isnan(r), -1, np.clip(b, 0, 9))


def signal_indices(f: Features, side: int, *, primary_only: bool = False) -> np.ndarray:
    """Indices of valid bars in context `side` (+1 up / -1 down); the BASE population when
    primary_only is False, the primary group (ratio >= 0.6) when True."""
    m = valid_mask(f) & (f.ctx == side)
    if primary_only:
        m = m & (ratio_for(f, side) >= S.UWR_CUT)
    return np.flatnonzero(m)


def counts_only(s: Series) -> dict:
    """G2: counts, no outcomes. Never touches the race or the trade simulation."""
    f = features(s)
    v = valid_mask(f)
    out = {"bars": s.n, "dropped_hl": int(f.drop_hl.sum()), "dropped_warmup": int(f.drop_warm.sum()),
           "dropped_roll": int((f.drop_roll & f.ok & ~f.drop_tail).sum()),
           "dropped_tail": int((f.drop_tail & f.ok).sum()), "valid": int(v.sum()),
           "up_ctx": int((v & (f.ctx == 1)).sum()), "down_ctx": int((v & (f.ctx == -1)).sum())}
    years = s.session.astype("datetime64[Y]").astype(int) + 1970
    for side, name in ((1, "up"), (-1, "down")):
        b = bucket_of(ratio_for(f, side))
        m = v & (f.ctx == side)
        out[f"{name}_bucket"] = [int((m & (b == i)).sum()) for i in range(10)]
        out[f"{name}_primary"] = int((m & (ratio_for(f, side) >= S.UWR_CUT)).sum())
        out[f"{name}_primary_by_year"] = {int(y): int((m & (ratio_for(f, side) >= S.UWR_CUT) & (years == y)).sum())
                                          for y in np.unique(years[m])} if m.any() else {}
        out[f"{name}_classic"] = int((v & (f.star if side == 1 else f.hammer)).sum())
    return out


# --- the race ----------------------------------------------------------------------------------
def _resolve_fine(s: Series, j: int, d_line: float, u_line: float, side: int) -> int:
    """Both lines inside bar j: use finer bars. Returns REV, CONT or AMBIG."""
    if s.fine_t is None:
        return AMBIG
    lo = np.searchsorted(s.fine_t, s.t_open[j], side="left")
    hi = np.searchsorted(s.fine_t, s.t_end[j], side="left")
    if hi <= lo:
        return AMBIG
    fh, fl = s.fine_h[lo:hi], s.fine_l[lo:hi]
    touch_d, touch_u = fl <= d_line, fh >= u_line
    any_t = touch_d | touch_u
    if not any_t.any():
        return AMBIG
    i = int(np.argmax(any_t))
    if touch_d[i] and touch_u[i]:
        return AMBIG                                             # same minute: no honest answer
    down_first = bool(touch_d[i])
    return REV if down_first == (side == 1) else CONT


def race(s: Series, f: Features, idx: np.ndarray, side: int, k: float) -> dict:
    """First touch of D = C - k*ATR / U = C + k*ATR from bar t+1, up to 20 bars.
    side +1 (up context): D first = reversal.  side -1 (down context): U first = reversal.
    A gap open beyond a line is a touch (the bar's low/high already contains its open).
    Returns arrays aligned to idx: kind (REV/CONT/AMBIG/NONE), bar (0-based offset of the first-touch
    bar, 0 = bar t+1; -1 for NONE)."""
    m = len(idx)
    if m == 0:
        return {"kind": np.zeros(0, int), "bar": np.zeros(0, int)}
    off = np.arange(1, S.LOOKAHEAD + 1)
    cols = idx[:, None] + off[None, :]
    hw, lw = s.h[cols], s.l[cols]
    c0, a0 = s.c[idx][:, None], f.atr[idx][:, None]
    d_line, u_line = c0 - k * a0, c0 + k * a0
    td, tu = lw <= d_line, hw >= u_line
    big = S.LOOKAHEAD
    fd = np.where(td.any(1), td.argmax(1), big)
    fu = np.where(tu.any(1), tu.argmax(1), big)
    rev_first, cont_first = (fd, fu) if side == 1 else (fu, fd)
    kind = np.full(m, NONE)
    bar = np.full(m, -1)
    r_win = rev_first < cont_first
    c_win = cont_first < rev_first
    kind[r_win], bar[r_win] = REV, rev_first[r_win]
    kind[c_win], bar[c_win] = CONT, cont_first[c_win]
    for q in np.flatnonzero((rev_first == cont_first) & (rev_first < big)):
        j = int(idx[q] + 1 + rev_first[q])
        kind[q] = _resolve_fine(s, j, float(d_line[q, 0]), float(u_line[q, 0]), side)
        bar[q] = rev_first[q]
    return {"kind": kind, "bar": bar}


def outcome_within(res: dict, nbars: int) -> np.ndarray:
    """Race outcome judged on bars t+1 .. t+nbars: the first-touch kind if it lands inside, else NONE."""
    inside = (res["bar"] >= 0) & (res["bar"] < nbars)
    return np.where(inside, res["kind"], NONE)
