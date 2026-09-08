#!/usr/bin/env python3
"""The VW9 Pine port must reproduce strategy/vw9/vw9.py, setup for setup.

CONTROL THE TOOL. PROGRAM_INDEX section 4. A Pine translation of a state
machine is exactly the kind of artefact that looks right and is subtly wrong:
an off-by-one in the pullback length, a streak updated before it is checked
instead of after, an indicator that carries yesterday's value into today. None
of those raise. They just change which bars are STRONG, and every trigger with
them.

There is no Pine interpreter here, so the check is the next best thing that is
still a check: the Pine script's logic is TRANSCRIBED below, line for line from
the .pine file rather than from vw9.py, and the two are run over the same real
bars. Transcribing from the Python would make this circular and prove nothing.

WHAT THIS DOES AND DOES NOT COVER
---------------------------------
Covers: session-scoped ema9 / ATR14 / VWAP / bar count, the maturity gate, the
regime call, Setup A's streak-then-update ordering, Setup B's pullback tracker,
and the impulse-volume freeze.

Does NOT cover: order fills, the exit ladder, or Pine's broker emulator. Those
differ from Python by construction and the differences are listed in the .pine
header. This is a check on the SIGNAL, which is the part that is supposed to be
identical.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from common.indicators import resample_bars
from strategy.vw9 import vw9 as V

ET = "America/New_York"
REPO = Path(__file__).resolve().parents[3]
WINDOW = "3d_to_2000"
BARS_CANDIDATES = [REPO / "bar_cache_db" / WINDOW,
                   REPO / "bar_cache_xnas" / WINDOW,
                   Path("/mnt/user-data/uploads/Trading/bar_cache_db") / WINDOW]

CASES = [
    ("AAL", "2024-12-05"),
    ("AAOZ", "2026-08-06"),
    ("AAOZ", "2026-08-07"),
    ("ABAT", "2026-06-08"),
    ("ABCL", "2025-06-10"),
    ("ABCL", "2026-08-10"),
]


def bars_dir() -> Path:
    for c in BARS_CANDIDATES:
        if c.is_dir():
            return c
    return BARS_CANDIDATES[0]


def session_5m(symbol: str, day: str) -> pd.DataFrame:
    """One 04:00-20:00 ET session at 5 minutes, the shape VW9-5 is given."""
    p = bars_dir() / f"{symbol}_{day}.csv.gz"
    if not p.exists():
        pytest.skip(
            f"{p} absent -- the bar cache is gitignored and machine-local, so "
            "the VW9 Pine port is NOT being checked against the engine here. "
            "Build the cache or point at one with these symbol-days.")
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    et = df.index.tz_convert(ET)
    m = (et.date == pd.Timestamp(day).date())
    one = df[m]
    return resample_bars(one, 5) if not one.empty else one


# --- the transcription, read off vw9.pine -----------------------------------

def pine_setups(bars: pd.DataFrame, *, ema_fast=9, atr_len=14, min_vwap_bars=3,
                min_vwap_dv=50_000.0, min_below_bars=2, reclaim_lookback=6,
                impulse_lookback=10, pullback_ctrl_atr=1.5,
                max_pullback_bars=6,
                new_session=None) -> list[tuple[int, str, float]]:
    """What the Pine script fires, in Pine's own order of operations.

    `new_session` is a per-bar flag, exactly Pine's `newSession`. Passing None
    means "one session, resetting at bar 0", which is the single-session case.
    Passing a real boundary vector is what the live script does, and it is the
    only way the RESET is under test at all -- see
    test_the_session_reset_is_real.
    """
    o = bars["open"].tolist()
    h = bars["high"].tolist()
    lo = bars["low"].tolist()
    c = bars["close"].tolist()
    v = bars["volume"].tolist()

    emaV = atrV = None
    cumPV = cumV = cumDV = 0.0
    barCount = 0
    sessHigh = None
    barsSinceHigh = 0
    bearRun = 0
    bearLows: list[float] = []
    inPullback = False
    pbLow = None
    pbStartIdx = 0
    impulseUpVol = 0.0
    pbImpulseUpVol = None
    pbMaxDownVol = None
    prevRegime = 0
    prevClose = None
    out: list[tuple] = []

    flags = [t == 0 for t in range(len(bars))] if new_session is None \
        else list(new_session)
    for t in range(len(bars)):
        if flags[t]:
            emaV = atrV = None
            cumPV = cumV = cumDV = 0.0
            barCount = 0
            sessHigh, barsSinceHigh = None, 0
            bearRun, bearLows = 0, []
            inPullback = False
            impulseUpVol = 0.0
            prevRegime, prevClose = 0, None
        barCount += 1
        trV = (h[t] - lo[t]) if barCount == 1 else max(
            h[t] - lo[t], abs(h[t] - c[t - 1]), abs(lo[t] - c[t - 1]))
        emaV = c[t] if barCount == 1 else emaV + (2.0 / (ema_fast + 1)) * (c[t] - emaV)
        atrV = trV if barCount == 1 else atrV + (trV - atrV) / atr_len
        cumPV += ((h[t] + lo[t] + c[t]) / 3.0) * v[t]
        cumV += v[t]
        cumDV += c[t] * v[t]

        vwapV = cumPV / cumV if cumV > 0 else None
        mature = (barCount >= ema_fast and barCount >= min_vwap_bars
                  and cumDV >= min_vwap_dv and vwapV is not None)
        regime = 0
        if mature:
            regime = 1 if c[t] <= vwapV else (2 if c[t] > emaV else 3)

        if sessHigh is None or h[t] >= sessHigh:
            sessHigh, barsSinceHigh = h[t], 0
        else:
            barsSinceHigh += 1

        # Setup A: check on the streak as of the previous bar, THEN update.
        if regime == 2 and bearRun >= min_below_bars:
            window = bearLows[-reclaim_lookback:] if bearLows else [lo[t]]
            out.append((t, "A", min(window), None, None))
            bearRun, bearLows = 0, []
        if regime == 1:
            bearRun += 1
            bearLows.append(lo[t])
        else:
            bearRun, bearLows = 0, []

        # Setup B
        if inPullback:
            pbLow = min(pbLow, lo[t])
            pbLen = barCount - pbStartIdx
            drop = 0.0 if prevClose is None else prevClose - c[t]
            unc = bool(atrV) and atrV > 0 and drop > pullback_ctrl_atr * atrV
            if drop > 0:
                pbMaxDownVol = max(pbMaxDownVol or 0.0, v[t])
            if regime == 1:
                inPullback = False
            elif regime == 2:
                if pbLen <= max_pullback_bars and not unc:
                    out.append((t, "B", pbLow, pbImpulseUpVol, pbMaxDownVol))
                inPullback = False
            else:
                if unc or pbLen > max_pullback_bars:
                    inPullback = False
        else:
            if regime == 3 and prevRegime == 2 and barsSinceHigh <= impulse_lookback:
                drop = 0.0 if prevClose is None else prevClose - c[t]
                unc = bool(atrV) and atrV > 0 and drop > pullback_ctrl_atr * atrV
                if not unc:
                    inPullback = True
                    pbStartIdx = barCount
                    pbLow = lo[t]
                    pbImpulseUpVol = impulseUpVol
                    pbMaxDownVol = v[t] if drop > 0 else 0.0

        if regime == 2:
            if prevClose is not None and c[t] > prevClose:
                impulseUpVol = max(impulseUpVol, v[t])
        else:
            impulseUpVol = 0.0
        prevRegime, prevClose = regime, c[t]
    return out


def engine_setups(bars: pd.DataFrame, **kw) -> list[tuple]:
    return [(s.bar_index, s.kind, s.structure_low,
             s.impulse_max_up_vol, s.pullback_max_down_vol)
            for s in V.find_setups(bars, **kw)]


def _same(g, w, where):
    assert g[0] == w[0], f"{where}: trigger bar differs {g} vs {w}"
    assert g[1] == w[1], f"{where}: setup kind differs {g} vs {w}"
    assert g[2] == pytest.approx(w[2], rel=1e-12), (
        f"{where}: structure low differs {g} vs {w} -- the stop would sit "
        "somewhere else and every R with it")
    # Setup B only. These two ARE the 4.3 pullback-volume gate: if the largest
    # down-bar volume of the pullback exceeds the largest up-bar volume of the
    # impulse, the entry is rejected. Getting them wrong silently changes which
    # Setup B trades are taken, and nothing about the trigger itself moves.
    for i, name in ((3, "impulse max up-volume"), (4, "pullback max down-volume")):
        if g[i] is None or w[i] is None:
            assert g[i] is None and w[i] is None, (
                f"{where}: {name} is None on one side only, {g} vs {w}")
        else:
            assert g[i] == pytest.approx(w[i], rel=1e-12), (
                f"{where}: {name} differs {g} vs {w} -- the pullback-volume "
                "gate would accept or reject a different set of entries")


# --- the control ------------------------------------------------------------

@pytest.mark.parametrize("symbol,day", CASES)
def test_the_pine_port_fires_the_same_setups(symbol, day):
    bars = session_5m(symbol, day)
    if bars.empty:
        pytest.skip(f"{symbol} {day}: no bars in the 04:00-20:00 window")
    got = pine_setups(bars)
    want = engine_setups(bars)
    assert len(got) == len(want), (
        f"{symbol} {day}: Pine fires {len(got)} setups, the engine "
        f"{len(want)}\n  pine   {got}\n  engine {want}")
    for g, w in zip(got, want):
        _same(g, w, f"{symbol} {day}")


def test_the_control_actually_exercises_setups():
    """A port that fires nothing agrees with an engine that fires nothing. If
    no case produces a setup this test says so instead of reporting six green
    comparisons of two empty lists."""
    total = 0
    checked = 0
    for symbol, day in CASES:
        p = bars_dir() / f"{symbol}_{day}.csv.gz"
        if not p.exists():
            continue
        bars = session_5m(symbol, day)
        if bars.empty:
            continue
        checked += 1
        total += len(engine_setups(bars))
    if checked == 0:
        pytest.skip("no cached symbol-days -- nothing was compared")
    assert total >= 1, (
        f"{checked} sessions compared and not one setup fired in any of them. "
        "The equivalence test above is vacuous; use symbol-days that trigger.")


# --- the two things the single-session comparison could not see -------------
#
# Both of these were found by mutating the transcription and watching the tests
# above stay green. A mutation the suite does not catch is a gap in the suite,
# not a harmless difference.

def all_sessions(symbol: str, day: str):
    """Every 04:00-20:00 ET session in one cache file, at 5 minutes.

    Each file holds THREE sessions. The single-session test only ever fed the
    last one, so `barCount == 1` and "this is the first bar we have seen" were
    the same condition and the session RESET was untestable -- replacing it
    with a run-once initialisation passed every case. The live script runs
    across every session on the chart, where they are not the same condition at
    all: without the reset each session inherits the previous one's ema9, ATR
    and VWAP, and the regime call changes with them.
    """
    p = bars_dir() / f"{symbol}_{day}.csv.gz"
    if not p.exists():
        pytest.skip(f"{p} absent -- the multi-session control is NOT running.")
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    out = []
    for d in sorted({t.date() for t in df.index.tz_convert(ET)}):
        one = df[df.index.tz_convert(ET).date == d]
        five = resample_bars(one, 5)
        if not five.empty:
            out.append((d, five))
    return out


@pytest.mark.parametrize("symbol,day", CASES)
def test_the_session_reset_is_real(symbol, day):
    """Run every session in the file as ONE continuous series with Pine's
    newSession flags, and require the same setups the engine finds when each
    session is handed to it separately."""
    sessions = all_sessions(symbol, day)
    if len(sessions) < 2:
        pytest.skip(f"{symbol} {day}: only {len(sessions)} session(s) in the file")

    frames = [f for _, f in sessions]
    joined = pd.concat(frames)
    flags, want = [], []
    offset = 0
    for f in frames:
        flags += [True] + [False] * (len(f) - 1)
        want += [(offset + s.bar_index, s.kind, s.structure_low,
                  s.impulse_max_up_vol, s.pullback_max_down_vol)
                 for s in V.find_setups(f)]
        offset += len(f)

    got = pine_setups(joined, new_session=flags)
    assert len(got) == len(want), (
        f"{symbol} {day}: across {len(frames)} sessions Pine fires {len(got)}, "
        f"the engine {len(want)}\n  pine   {got}\n  engine {want}")
    for g, w in zip(got, want):
        _same(g, w, f"{symbol} {day} multi-session")


# A pullback length off by one changed nothing at the shipped max of 6 -- the
# boundary is simply never reached on these sessions, so the comparison was
# insensitive to it. Sweeping the parameters puts the boundaries where the data
# actually is instead of hoping the default lands on one.
GRID = [
    dict(max_pullback_bars=1), dict(max_pullback_bars=2),
    dict(max_pullback_bars=3), dict(max_pullback_bars=12),
    dict(min_below_bars=1), dict(min_below_bars=4),
    dict(reclaim_lookback=1), dict(reclaim_lookback=2),
    dict(impulse_lookback=1), dict(impulse_lookback=3),
    dict(pullback_ctrl_atr=0.2), dict(pullback_ctrl_atr=5.0),
]


@pytest.mark.parametrize("kw", GRID, ids=lambda k: ",".join(
    f"{a}={b}" for a, b in k.items()))
def test_the_port_agrees_off_the_default_parameters(kw):
    """Every knob the Pine script exposes as an input, moved off its default.

    A port can agree on the shipped settings and diverge the moment a boundary
    is crossed -- which is exactly what an off-by-one in the pullback length
    is. These are the same real sessions, read at settings that reach the
    boundaries the defaults never touch.
    """
    compared = 0
    for symbol, day in CASES:
        p = bars_dir() / f"{symbol}_{day}.csv.gz"
        if not p.exists():
            continue
        bars = session_5m(symbol, day)
        if bars.empty:
            continue
        compared += 1
        got = pine_setups(bars, **kw)
        want = engine_setups(bars, **kw)
        assert len(got) == len(want), (
            f"{symbol} {day} at {kw}: Pine {len(got)}, engine {len(want)}"
            f"\n  pine   {got}\n  engine {want}")
        for g, w in zip(got, want):
            _same(g, w, f"{symbol} {day} at {kw}")
    if compared == 0:
        pytest.skip("no cached symbol-days")
