#!/usr/bin/env python3
r"""A stock-split detector and back-adjuster for raw (unadjusted) daily bars.

Registered in docs/research/REGISTERED_dux_veto.md sec 10, before this file
existed -- Ben's decision on W03-0012 subitem 3 ("let's go with databento"):
Tag B/R's daily history comes from Databento's `ohlcv-1d` bars, which are NOT
split-adjusted, corrected here by a heuristic rather than a real
corporate-actions table this project does not own.

THE HEURISTIC, EXACTLY (sec 10)
--------------------------------
A split is detected between consecutive RAW daily bars (day t-1, day t) when
BOTH the price ratio and the volume ratio land within tolerance of the SAME
candidate factor, in opposite directions:

    price_ratio  = close[t-1] / close[t]
    volume_ratio = volume[t]  / volume[t-1]

    detected when, for some R in CANDIDATE_FACTORS:
        |price_ratio / R  - 1| * 100 <= PRICE_TOL   AND
        |volume_ratio / R - 1| * 100 <= VOLUME_TOL

WHY PRICE *AND* VOLUME, NOT PRICE ALONE
-----------------------------------------
Tag B and Tag R exist to find genuine, organic spike days and green runs --
exactly the kind of huge single-day move this module must NOT eat. A real
spike (buying pressure) does not carry a compensating INVERSE move in raw
share volume; a split mechanically does, because the share count itself
changed, not the dollars traded. Requiring both conditions in the SAME
direction is what tells a mechanical artefact apart from a real move. A large
price jump with no matching inverse volume jump is left alone, untouched,
exactly as printed.

RESIDUAL RISK, NAMED RATHER THAN HIDDEN
------------------------------------------
A genuine move whose price and volume both happen to land inside both
tolerance bands, purely coincidentally, would be misread as a split. This is
the same class of heuristic used industry-wide absent a corporate-actions
feed, and it is not zero risk. See sec 10's own note on checking concentrated
symbol-days by hand before trusting a Tag B/R verdict driven by one or two of
them.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

CANDIDATE_FACTORS: tuple[float, ...] = (
    2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0,
    1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 6, 1 / 8, 1 / 10,
)
PRICE_TOL = 3.0    # % tolerance around a candidate factor, on the price ratio
VOLUME_TOL = 25.0  # % tolerance around the same factor, on the volume ratio


@dataclass(frozen=True)
class DailyBar:
    date: str
    close: float
    volume: float
    high: float
    low: float


def _within(ratio: float, factor: float, tol_pct: float) -> bool:
    if factor <= 0:
        return False
    return abs(ratio / factor - 1.0) * 100.0 <= tol_pct


def detect_split(prev: DailyBar, curr: DailyBar) -> float | None:
    """The candidate factor R detected between RAW `prev` (day t-1) and
    `curr` (day t), or None if no candidate satisfies both the price and the
    volume test. Ties (more than one factor within tolerance) resolve to
    whichever factor's price ratio is closest -- an edge case the tolerance
    bands make rare in practice (adjacent factors are >20% apart) but which
    should never be ambiguous behaviour.

    NaN/zero-guarded: a non-positive prior close or volume returns None
    rather than raising or dividing by zero -- an unusable bar is read as
    "no split detected", never as a false positive.
    """
    if prev.close <= 0 or curr.close <= 0 or prev.volume <= 0:
        return None
    price_ratio = prev.close / curr.close
    volume_ratio = curr.volume / prev.volume
    best: tuple[float, float] | None = None  # (factor, |price_ratio/factor - 1|)
    for factor in CANDIDATE_FACTORS:
        if not _within(price_ratio, factor, PRICE_TOL):
            continue
        if not _within(volume_ratio, factor, VOLUME_TOL):
            continue
        dist = abs(price_ratio / factor - 1.0)
        if best is None or dist < best[1]:
            best = (factor, dist)
    return best[0] if best else None


def adjust_for_splits(daily: list[DailyBar]) -> list[DailyBar]:
    """Return a NEW list of `DailyBar`, back-adjusted to the scale of the
    LAST (most recent) bar in `daily`. `daily` must be sorted ascending by
    date; the window is exactly what the caller queried (sec 10: detection
    and adjustment never reach further back than the supplied window).

    Detection always reads the ORIGINAL, raw `daily` list (never the
    partially-adjusted output), so multiple splits inside one window are
    each detected independently and their rescales compound correctly on
    every bar before them.
    """
    out = list(daily)
    for i in range(1, len(daily)):
        factor = detect_split(daily[i - 1], daily[i])
        if factor is None:
            continue
        for j in range(i):
            b = out[j]
            out[j] = replace(b, close=b.close / factor, high=b.high / factor,
                             low=b.low / factor, volume=b.volume * factor)
    return out
