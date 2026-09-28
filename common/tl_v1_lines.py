#!/usr/bin/env python3
"""Tori's extreme-anchor line construction + A+ checklist -- TL-v1
(REGISTERED_tl_v1.md sec 2.2-2.3). Board: W15-0019.

Reuses TL-v0's pivot finder and ATR (common/tl_v0_lines.find_pivots,
common/tl_v0_lines.atr14); this module is the DIFFERENT line geometry only.

WHY THIS IS NOT common/tl_v0_lines.walk_line_and_breaks
---------------------------------------------------------
TL-v0's line is built from the two MOST RECENTLY confirmed pivots and then
carries persistent on/off state between bars (armed until it breaks, only a
fresh pivot pair re-arms it -- AT-113). TL-v1's line is different by
construction (sec 2.2, her words: "computed at the close of every bar t from
pivots confirmed by t"):

  L1 Window   -- only pivots whose bar lies in the last W=250 bars count
  L2 Anchor A -- the WINDOW's pivots in price order, extreme first; the
                 first one a valid line can be built from wins
  L3 Point B  -- among later pivots, the one giving the FLATTEST valid line
                 (largest slope, must be negative for resistance / smallest
                 slope, must be positive for support -- both are "flattest
                 valid" once you drop the sign)
  L4 Never crossed -- invalid if any close from A to t sits beyond the line
                 by more than 0.10 x ATR at that bar (closes only, not wicks
                 -- same buffer TL-v0 uses for its own validity/break test)
  L5 Span limit -- A to t <= 400 bars, as TL-v0

so there is no "armed / broken, re-arm on next pivot" state machine here:
the anchor can also change on a bar with NO new pivot at all, purely
because the previous anchor's bar has aged out of the W=250 window. The
per-bar walk below recomputes the anchor whenever either thing happens
(new pivot confirmed, or the current anchor is about to age out) -- it does
not recompute on every single bar, but the RESULT is identical to doing so,
because between those events the winning (A, B) pair cannot change: the
candidate set is unchanged and L4's crossing test only ever gets checked up
through bar t-1 already (extending it to t cannot un-invalidate a line that
was valid through t-1, and a still-valid line's value at t is unaffected by
anything except A/B themselves).

A+ CHECKLIST (sec 2.3) IS SCORED SEPARATELY FROM THE LINE
-----------------------------------------------------------
E1 (the break itself) reuses the SAME 0.10 x ATR buffer as L4 -- gap
analysis and REGISTERED_tl_v0.md sec 2.1 call this "the same event" for
TL-v0's own line; TL-v1 keeps that here too. A1-A3 are additional gates
evaluated at the moment of a break; they do not change the line's geometry,
only whether the resulting break counts as an A+ entry.
"""
from __future__ import annotations
import numpy as np

WINDOW = 250
MAX_SPAN = 400
CROSS_BUFFER = 0.10   # L4 (line validity) / E1 (the break)
TOUCH_BUFFER = 0.25   # A1
MIN_TOUCHES = 3        # A1
MIN_SPAN_DAYS = 7      # A2 -- calendar days, not bars (daily bars only: caller passes dates)


def efficiency_ratio(close, n: int = 20) -> np.ndarray:
    """ER(20)[t] = |close[t]-close[t-n]| / sum(|close[i]-close[i-1]|, i in (t-n, t]).
    NaN for t < n (sec 2.3 A3; the training-only q20/q25/q33 percentiles are
    computed by common/tl_v1_preflight.py, PRE-RUN, and written back into
    REGISTERED_tl_v1.md -- this function only computes the raw series)."""
    close = np.asarray(close, float)
    nb = len(close)
    out = np.full(nb, np.nan)
    if nb <= n:
        return out
    diffs = np.abs(np.diff(close))
    csum = np.concatenate(([0.0], np.cumsum(diffs)))  # csum[t] = sum of diffs[0:t]
    for t in range(n, nb):
        num = abs(close[t] - close[t - n])
        den = csum[t] - csum[t - n]
        out[t] = num / den if den > 0 else np.nan
    return out


def _slope(pA, vA, pB, vB):
    return (vB - vA) / (pB - pA)


def _line_value(pA, vA, slope, x):
    return vA + slope * (x - pA)


def _valid_line(pA, vA, pB, vB, closes, atr, t_upto, kind):
    """L3 direction + L4 never-crossed, from A's bar through t_upto inclusive."""
    slope = _slope(pA, vA, pB, vB)
    if kind == "res" and not (slope < 0):
        return False, slope
    if kind == "sup" and not (slope > 0):
        return False, slope
    hi = min(t_upto, len(closes) - 1)
    for k in range(pA, hi + 1):
        lv = _line_value(pA, vA, slope, k)
        if kind == "res":
            if closes[k] - lv > CROSS_BUFFER * atr[k]:
                return False, slope
        else:
            if lv - closes[k] > CROSS_BUFFER * atr[k]:
                return False, slope
    return True, slope


def anchor_pair_at(t, confirmed_pivots, closes, atr, kind,
                    window: int = WINDOW, max_span: int = MAX_SPAN):
    """confirmed_pivots: [(pivot_idx, confirm_idx, value), ...] with
    confirm_idx <= t already filtered by the caller (or pass the full list;
    it is filtered here too, defensively).

    Returns (pA, vA, pB, vB, slope) for the winning anchor/point-B pair, or
    None if no valid line exists at t. kind='res' (resistance, for long
    entries, extreme = highest price) or 'sup' (support, mirror, extreme =
    lowest price)."""
    cands = [p for p in confirmed_pivots if p[1] <= t and t - p[0] <= window]
    if len(cands) < 2:
        return None
    order = sorted(cands, key=lambda p: (-p[2] if kind == "res" else p[2], p[0]))
    for (pA, _cA, vA) in order:
        later = [p for p in cands if p[0] > pA]
        best = None
        for (pB, _cB, vB) in later:
            if pB - pA > max_span:
                continue
            ok, slope = _valid_line(pA, vA, pB, vB, closes, atr, t, kind)
            if not ok:
                continue
            if best is None or abs(slope) < abs(best[4]):
                best = (pA, vA, pB, vB, slope)
        if best is not None:
            return best
    return None


def build_series(n, pivots, closes, atr, kind, window=WINDOW, max_span=MAX_SPAN):
    """Bar-by-bar line value (NaN when no valid line) and A+ break flags.

    Recomputes the anchor pair whenever a new pivot confirms, or the
    current pair's A has aged out of the window -- see module docstring for
    why that is equivalent to recomputing at every bar t.

    Returns dict with: line (float[n]), anchor_bar (int[n], the A used,
    -1 if none), pointB_bar (int[n], -1 if none), breaks (bool[n], the
    raw E1/L4 buffer crossing -- NOT yet gated by A1-A3).
    """
    line = np.full(n, np.nan)
    anchor_bar = np.full(n, -1, dtype=int)
    pointb_bar = np.full(n, -1, dtype=int)
    breaks = np.zeros(n, dtype=bool)

    confirmed = []  # pivots confirmed so far
    pivots_by_confirm = {}
    for pidx, cidx, val in pivots:
        pivots_by_confirm.setdefault(cidx, []).append((pidx, cidx, val))

    current = None  # (pA, vA, pB, vB, slope)
    was_on = False
    for t in range(n):
        if t in pivots_by_confirm:
            confirmed.extend(pivots_by_confirm[t])
        need_recompute = False
        if current is None:
            need_recompute = True
        elif t in pivots_by_confirm:
            need_recompute = True
        elif t - current[0] > window:
            need_recompute = True
        if need_recompute:
            current = anchor_pair_at(t, confirmed, closes, atr, kind, window, max_span)
            was_on = False  # a fresh (re)computation is not itself a break
        if current is not None:
            pA, vA, pB, vB, slope = current
            lv = _line_value(pA, vA, slope, t)
            line[t] = lv
            anchor_bar[t] = pA
            pointb_bar[t] = pB
            if kind == "res":
                crossed = closes[t] - lv > CROSS_BUFFER * atr[t]
            else:
                crossed = lv - closes[t] > CROSS_BUFFER * atr[t]
            if crossed and not was_on:
                # first bar of this crossing episode for THIS pair
                breaks[t] = True
            was_on = crossed
        else:
            was_on = False
    return {"line": line, "anchor_bar": anchor_bar, "pointb_bar": pointb_bar,
            "breaks": breaks}


def touch_pivots_between(pA, t, touch_pivots, line, atr, kind, buffer_mult=TOUCH_BUFFER):
    """A1: confirmed touch pivots (L=R=2, passed in by the caller from
    common.tl_v0_lines.find_pivots(..., R=2, kind=...)) from A's bar to
    t-1 inclusive, whose extreme sits within buffer_mult*ATR of the line's
    value at that bar. Returns the count and the list of touch bar indices."""
    hits = []
    for (pidx, cidx, val) in touch_pivots:
        if pidx < pA or pidx > t - 1 or cidx > t - 1:
            continue
        if np.isnan(line[pidx]):
            continue
        lv = line[pidx]
        if kind == "res":
            if val >= lv - buffer_mult * atr[pidx]:
                hits.append(pidx)
        else:
            if val <= lv + buffer_mult * atr[pidx]:
                hits.append(pidx)
    return len(hits), hits


def a_plus_checklist(t, pA, touches_count, span_days, er_value, er_threshold):
    """A1-A3 (sec 2.3), given the pieces already computed by the caller.
    Returns (passes: bool, dict of which sub-rule failed)."""
    a1 = touches_count >= MIN_TOUCHES
    a2 = span_days >= MIN_SPAN_DAYS
    a3 = (not np.isnan(er_value)) and (not np.isnan(er_threshold)) and er_value >= er_threshold
    return (a1 and a2 and a3), {"A1_touches": a1, "A2_span": a2, "A3_trending": a3}
