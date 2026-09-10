#!/usr/bin/env python3
"""The live screen, evaluated as of a timestamp.

    from common.screen_at import screen_at, ScreenConfig

WHY THIS EXISTS
---------------
Every P/L figure in this project is drawn from a universe chosen with the whole
day already known. `common/screen.py`'s `stage2` filters on today's daily RVOL
and today's daily range -- both of which are 20:00 facts used to decide a 03:59
question. `leak_control.py` bracketed what that is worth and did not locate it:

    stage-2 survivors   H0 +$4.72/trade
    stage-2 rejects     H0 -$9.81/trade

Land the simulated live screen near +$4.72 and the screen was doing the work.
Land near -$9.81 and the +$4.72 was the leak -- and with it every P/L figure
this project has produced. See `claude/screener_simulation_scope.md` §5.

THE RULES ARE IMPORTED, NEVER RESTATED
--------------------------------------
`PREMARKET_CHANGE_MIN`, `PREMARKET_PRICE_RANGE`, `PREMARKET_VOLUME_MIN` and
`MAX_SYMBOLS` come from `tv_screener`/`tv_feed` at import time. This is the
single most important line of design in the file.

The scope document found `screen.py`'s `stage2` applying `min_rvol = 5.0` while
the shipped screen has no RVOL clause at all -- the simulation and the thing it
simulates had drifted apart and neither said so. A restated constant is a copy
that goes stale silently; an imported one cannot. If Ben changes the screen, a
re-run changes with it or fails loudly.

TWO CONVENTIONS THAT DECIDE THE ANSWER
--------------------------------------
**1. A bar counts only once it has CLOSED.** `ts_event` is the interval START
(`dbn_io` convention 1), so the bar stamped 04:29 covers 04:29:00-04:29:59 and
is not knowable until 04:30:00. Screening at t on `index <= t` therefore reads
up to 59 seconds of the future on every symbol, every cadence tick.

This is the entry-latency defect wearing a different hat: the live trader was
found acting a minute late because a closed bar was being discarded, and this
would have the simulation acting a minute EARLY because a forming bar is being
kept. Same axis, opposite sign, and it flatters the result rather than costing
it -- which is why it would not have been noticed.

**2. The volume threshold is on a PARTIAL TAPE.** `premarket_volume >= 100,000`
is a threshold against TradingView's consolidated figure. XNAS.BASIC carries a
measured median 55.2% of the consolidated tape (p10 0.458, p90 0.656). Holding
100,000 against our tape silently demands ~182k of real pre-market volume, so
the simulated screen would be strictly tighter than the live one and would
under-select -- reading, in the output, as "the screen is too tight".

So the threshold is SCALED by the capture ratio, which makes that ratio a
load-bearing input rather than a footnote. `capture_sensitivity()` re-runs the
screen at p10/p50/p90 and is meant to be reported alongside any headline: a
finding that only survives at p50 is a finding about the capture estimate.

WHAT THIS DOES NOT REPRODUCE
----------------------------
TradingView's *columns*, not TradingView's *data*. Even a perfect
reimplementation ranks a slightly different list, because their
`premarket_volume` is some consolidation of their own. This answers "is the
+$4.72 a look-ahead artefact?" and not "would this exact watchlist have appeared
on Ben's screen that morning". Only the first question is worth the work.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from common.tv_feed import MAX_SYMBOLS
from common.tv_screener import (PREMARKET_CHANGE_MIN, PREMARKET_PRICE_RANGE,
                                PREMARKET_VOLUME_MIN)

ET = ZoneInfo("America/New_York")

# Measured in var/reports/capture_ratio.txt over 177 traded sessions. p50 is the
# default; the other two are the sensitivity band, not alternatives to pick from.
CAPTURE_P10, CAPTURE_P50, CAPTURE_P90 = 0.458, 0.552, 0.656

SESSION_OPEN = dtime(4, 0)      # pre-market open; premarket_volume accumulates
                                # from here, per tv_screener's own note
BAR_SECONDS = 60

# Tolerance on the COMPUTED percentage change only. Nine decimal places is far
# finer than any threshold anyone would set and far coarser than the binary
# representation error it absorbs.
CHANGE_EPS = 1e-9


@dataclass(frozen=True)
class ScreenConfig:
    """The shipped screen's numbers, imported. Override only in tests and in
    the capture sensitivity, never to tune."""
    change_min: float = PREMARKET_CHANGE_MIN
    price_range: tuple[float, float] = PREMARKET_PRICE_RANGE
    volume_min: int = PREMARKET_VOLUME_MIN
    max_symbols: int = MAX_SYMBOLS
    capture: float = CAPTURE_P50
    session_open: dtime = SESSION_OPEN
    bar_seconds: int = BAR_SECONDS

    @property
    def volume_min_on_tape(self) -> int:
        """What `volume_min` becomes on a tape carrying `capture` of the whole.

        A name needs `volume_min` CONSOLIDATED shares to pass the live screen.
        Our tape shows it `capture` x that, so the threshold our tape must clear
        is scaled DOWN. Getting this backwards costs the universe roughly a
        factor of three and looks like a screen that is simply too tight.

        ROUNDED TO A WHOLE SHARE, and not for tidiness: 100_000 * 0.552 is
        55200.00000000001 in binary, so a name with exactly 55,200 shares fails
        a threshold it exactly meets. Volume is a count of shares and a
        fractional threshold has no meaning; the float was pure artefact.
        """
        return round(self.volume_min * self.capture)


def session_open_utc(t: datetime, cfg: ScreenConfig) -> pd.Timestamp:
    """04:00 ET on t's own ET date, as UTC.

    Built from the ET calendar date rather than by subtracting a fixed offset,
    because the offset is -4 or -5 depending on DST and the archive spans three
    changeovers. A fixed -5 would move the window an hour for eight months of
    every year and quietly change what `premarket_volume` sums.
    """
    et_date = t.astimezone(ET).date()
    return pd.Timestamp(datetime.combine(et_date, cfg.session_open, tzinfo=ET)
                        ).tz_convert("UTC")


def visible_bars(bars: pd.DataFrame, t: datetime,
                 cfg: ScreenConfig = ScreenConfig()) -> pd.DataFrame:
    """The bars a screen running at `t` could legitimately have seen.

    THE TRUNCATION HAPPENS HERE, NOT IN THE CALLER. It would be simpler to
    document "pass me a frame already cut at t" and trust it -- but then the
    leak test cannot exist: appending future rows to the input would change the
    output, and correctly so, leaving nothing to assert. A function that
    truncates its own input is a function whose blindness can be MEASURED.
    """
    if bars.empty:
        return bars
    t = pd.Timestamp(t)
    if t.tzinfo is None:
        raise ValueError("t must be timezone-aware; a naive t is a silent "
                         "local-time assumption on a UTC index")
    idx = bars.index
    if idx.tz is None:
        raise ValueError("bars index must be tz-aware UTC (see dbn_io.read_dbn)")
    closes_at = idx + timedelta(seconds=cfg.bar_seconds)
    return bars[(closes_at <= t) & (idx >= session_open_utc(t, cfg))]


def premarket_features(bars: pd.DataFrame, prior_close: pd.Series,
                       t: datetime,
                       cfg: ScreenConfig = ScreenConfig()) -> pd.DataFrame:
    """The three screened columns, per symbol, as of `t`.

    `bars` is the dbn_io shape: UTC-indexed on ts_event, with `symbol`, `close`
    and `volume` columns. `prior_close` maps symbol -> previous REGULAR-session
    close, which is what tv_screener's `premarket_change` measures against (its
    sibling `premarket_change_from_open` measures something else and is not the
    screened column).
    """
    win = visible_bars(bars, t, cfg)
    if win.empty:
        return pd.DataFrame(columns=["symbol", "premarket_close",
                                     "premarket_volume", "premarket_change"])
    g = win.groupby("symbol", sort=True)
    out = pd.DataFrame({
        "premarket_close": g["close"].last(),
        "premarket_volume": g["volume"].sum(),
    }).reset_index()
    out["prior_close"] = out["symbol"].map(prior_close)
    # A name with no prior regular close has no change to compute. Dropping it
    # is right -- an unknown denominator is not a 0% move -- and it is counted
    # so a run can say how many names it lost that way.
    out = out[out["prior_close"].notna() & (out["prior_close"] > 0)]
    out["premarket_change"] = (
        (out["premarket_close"] / out["prior_close"] - 1.0) * 100.0)
    return out.reset_index(drop=True)


def screen_at(bars: pd.DataFrame, prior_close: pd.Series, t: datetime,
              cfg: ScreenConfig = ScreenConfig()) -> pd.DataFrame:
    """The watchlist the live screen would have produced at `t`.

    Three clauses, a sort and a cap -- exactly `tv_screener.FILTERS`, with the
    volume threshold scaled to our tape.
    """
    f = premarket_features(bars, prior_close, t, cfg)
    if f.empty:
        return f.assign(rank=pd.Series(dtype=int))
    lo, hi = cfg.price_range
    keep = (
        # EPS, and it is not fussiness. premarket_change is COMPUTED --
        # (3.60/3.00 - 1) * 100 is 19.999999999999996 in binary -- so a name at
        # exactly the +20% threshold fails a test it exactly passes. Across 550
        # sessions and thousands of names this drops real names, always in the
        # same direction: it makes the simulated universe smaller than the live
        # one, which is precisely the bias this whole exercise is measuring.
        #
        # The price bounds get no epsilon: `close` is a raw archive price, not
        # a computed quantity, and 2.0 and 25.0 are exactly representable.
        (f["premarket_change"] >= cfg.change_min - CHANGE_EPS)
        # in_range is INCLUSIVE at both ends -- confirmed 2026-09-05 against the
        # float filter, which used the same operation.
        & (f["premarket_close"] >= lo) & (f["premarket_close"] <= hi)
        & (f["premarket_volume"] >= cfg.volume_min_on_tape)
    )
    # Ties broken by symbol, ALWAYS. Two names at the same pre-market change is
    # common on a 2-decimal figure, and an unstable sort would make the top-40
    # cut depend on row order -- which changes with pandas versions and with
    # how the archive was concatenated. The leak test would then fail
    # intermittently and be read as flaky rather than as a real leak.
    out = (f[keep]
           .sort_values(["premarket_change", "symbol"], ascending=[False, True])
           .head(cfg.max_symbols)
           .reset_index(drop=True))
    out["rank"] = range(1, len(out) + 1)
    return out


def capture_sensitivity(bars: pd.DataFrame, prior_close: pd.Series,
                        t: datetime,
                        cfg: ScreenConfig = ScreenConfig()) -> pd.DataFrame:
    """The same screen at the p10/p50/p90 capture ratios.

    Report this next to any headline. The volume threshold is the only clause
    that depends on an ESTIMATE rather than on a printed price, so it is the
    only one whose error can move the universe; a result that holds at p50 and
    not at p10 is a result about the capture measurement.
    """
    rows = []
    for label, c in (("p10", CAPTURE_P10), ("p50", CAPTURE_P50),
                     ("p90", CAPTURE_P90)):
        sel = screen_at(bars, prior_close, t, replace(cfg, capture=c))
        rows.append({"capture": label, "ratio": c,
                     "threshold_on_tape": cfg.volume_min * c,
                     "n": len(sel),
                     "symbols": ",".join(sel["symbol"].tolist()[:10])})
    return pd.DataFrame(rows)
