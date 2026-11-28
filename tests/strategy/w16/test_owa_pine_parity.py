"""Pine parity (REGISTERED_w16_open_window.md sec 4 and 14): the shared core
must give the same signals as the Pine indicator v1.0 on a fixed fixture.

Pine cannot run here, so `pine_signals` below is a line-by-line transcription
of "Claude outputs/w16_0040_open_window_signals_v0.pine" (v1.0), written bar
by bar in plain Python and sharing no code with strategy.w16.open_window. The
last test checks the .pine file's own input defaults against the registered
constants, so an edit to the indicator that moves a number is caught.

What is compared: the big bar, the trend filter, and the raw A, B and C
conditions, long and short. Position handling is not compared (Pine fills at
the signal close and does not round its stop; see sec 13)."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from strategy.w16 import open_window as OW
from tests.strategy.w16 import owa_fixtures as F

PINE = Path(__file__).resolve().parents[3] / "Claude outputs" / "w16_0040_open_window_signals_v0.pine"


def _ema(values, length):
    out, s = [], None
    for v in values:
        a = 2.0 / (length + 1)
        s = v if s is None else a * v + (1 - a) * s
        out.append(s)
    return out


def _atr(high, low, close, length=14):
    tr = [high[0] - low[0]]
    for i in range(1, len(close)):
        tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    out, s = [], None
    for i, v in enumerate(tr):
        if i == length - 1:
            s = sum(tr[:length]) / length
        elif i >= length:
            s = (v + (length - 1) * s) / length
        out.append(s)
    return out


def _bars_since(flags):
    out, last = [], None
    for i, f in enumerate(flags):
        if f:
            last = i
        out.append(None if last is None else i - last)
    return out


def _htf(times, close, minutes):
    """request.security(tf, ema(close, n)[1], lookahead_on): every 5-min bar
    inside filter bar g reads filter bar g-1."""
    groups, closes = [], []
    for t, c in zip(times, close):
        key = t // (minutes * OW.NS_MIN)
        if not groups or groups[-1] != key:
            groups.append(key)
            closes.append(c)
        else:
            closes[-1] = c
    fast, slow = _ema(closes, 9), _ema(closes, 21)
    bull, bear = [], []
    g = -1
    seen = None
    for t in times:
        key = t // (minutes * OW.NS_MIN)
        if key != seen:
            g, seen = g + 1, key
        bull.append(g >= 1 and fast[g - 1] > slow[g - 1])
        bear.append(g >= 1 and fast[g - 1] < slow[g - 1])
    return bull, bear


def pine_signals(times, day, minute, o, h, l, c, htf_minutes):
    n = len(c)
    e9, e21 = _ema(c, 9), _ema(c, 21)
    macd = [a - b for a, b in zip(_ema(c, 12), _ema(c, 26))]
    sig = _ema(macd, 9)
    bull, bear = _htf(times, c, htf_minutes)

    slot_avg, slot_n = {}, {}
    big = []
    for i in range(n):
        key = minute[i]
        rng = h[i] - l[i]
        prev = slot_avg.get(key)
        count = slot_n.get(key, 0)
        big.append(prev is not None and count >= 20 and rng >= 1.5 * prev)
        slot_avg[key] = rng if prev is None else prev + 2.0 / 21 * (rng - prev)
        slot_n[key] = count + 1

    def cross(a, b, i):
        return i > 0 and a[i] > b[i] and a[i - 1] <= b[i - 1]

    def under(a, b, i):
        return i > 0 and a[i] < b[i] and a[i - 1] >= b[i - 1]

    since_x_up = _bars_since([cross(e9, e21, i) for i in range(n)])
    since_x_dn = _bars_since([under(e9, e21, i) for i in range(n)])
    since_m_up = _bars_since([cross(macd, sig, i) for i in range(n)])
    since_m_dn = _bars_since([under(macd, sig, i) for i in range(n)])

    out = {k: [] for k in ("big", "bull", "bear", "a_long", "a_short", "b_long", "b_short",
                           "c_long", "c_short")}
    up_bar = dn_bar = None
    up_touch = dn_touch = False
    for i in range(n):
        big_up = big[i] and c[i] > o[i]
        big_dn = big[i] and c[i] < o[i]
        a_long = bool(bull[i] and e9[i] > e21[i] and since_x_up[i] is not None
                      and since_x_up[i] <= 3 and big_up)
        a_short = bool(bear[i] and e9[i] < e21[i] and since_x_dn[i] is not None
                       and since_x_dn[i] <= 3 and big_dn)

        if i > 0 and day[i] != day[i - 1]:
            up_bar = dn_bar = None
        in_imp = 8 * 60 <= minute[i] < 12 * 60
        if big_up and in_imp and bull[i]:
            up_bar, up_touch = i, False
        if big_dn and in_imp and bear[i]:
            dn_bar, dn_touch = i, False
        up_armed = up_bar is not None and i > up_bar and i - up_bar <= 12
        dn_armed = dn_bar is not None and i > dn_bar and i - dn_bar <= 12
        if up_armed and l[i] <= e9[i]:
            up_touch = True
        if dn_armed and h[i] >= e9[i]:
            dn_touch = True
        b_long = bool(up_armed and up_touch and bull[i] and e9[i] > e21[i] and i > 0
                      and c[i] > h[i - 1] and c[i] > e9[i])
        b_short = bool(dn_armed and dn_touch and bear[i] and e9[i] < e21[i] and i > 0
                       and c[i] < l[i - 1] and c[i] < e9[i])

        c_long = c_short = False
        if i > 0:
            gap, gap1 = e21[i] - e9[i], e21[i - 1] - e9[i - 1]
            turn_up = (gap < gap1) if e9[i] <= e21[i] else cross(e9, e21, i)
            turn_dn = (gap > gap1) if e9[i] >= e21[i] else under(e9, e21, i)
            c_long = bool(bull[i] and since_m_up[i] is not None and since_m_up[i] <= 3
                          and e9[i] > e9[i - 1] and turn_up)
            c_short = bool(bear[i] and since_m_dn[i] is not None and since_m_dn[i] <= 3
                           and e9[i] < e9[i - 1] and turn_dn)
        for key, value in (("big", big[i]), ("bull", bull[i]), ("bear", bear[i]),
                           ("a_long", a_long), ("a_short", a_short), ("b_long", b_long),
                           ("b_short", b_short), ("c_long", c_long), ("c_short", c_short)):
            out[key].append(bool(value))
    return {k: np.asarray(v) for k, v in out.items()}


@pytest.fixture(scope="module")
def market():
    return OW.prepare(F.random_bars(F.weekdays(90), seed=20261128))


@pytest.mark.parametrize("name", ["1H", "15"])
def test_core_matches_the_pine_transcription(market, name):
    mk, b = market, market.b5
    pine = pine_signals(b.start.tolist(), b.day.tolist(), b.minute.tolist(), b.o.tolist(),
                        b.h.tolist(), b.l.tolist(), b.c.tolist(), OW.FILTERS[name])
    sig = OW.compute_signals(mk, name)
    assert np.array_equal(sig.big, pine["big"])
    assert np.array_equal(mk.filt[name] == OW.UP, pine["bull"])
    assert np.array_equal(mk.filt[name] == OW.DOWN, pine["bear"])
    for key in ("a_long", "a_short", "c_long", "c_short"):
        got = getattr(sig, key)
        diff = np.flatnonzero(got != pine[key])
        assert len(diff) == 0, (key, diff[:5])
        assert pine[key].sum() > 0, f"fixture never fires {key}: parity would be empty"

    # B: the state machine, no fills, on every signal-window bar
    for side, key in ((OW.LONG, "b_long"), (OW.SHORT, "b_short")):
        is_long = side == OW.LONG
        fired = np.zeros(len(b), dtype=bool)
        state, day = None, None
        for j in np.flatnonzero((b.minute >= OW.WINDOW_FIRST_MIN)
                                & (b.minute <= OW.WINDOW_LAST_MIN)):
            if b.day[j] != day:
                state, day = OW.PullbackState(), b.day[j]
            fired[j] = state.step(
                int(j), bool((sig.b_arm_long if is_long else sig.b_arm_short)[j]),
                bool((sig.b_touch_long if is_long else sig.b_touch_short)[j]),
                bool((sig.b_fire_long if is_long else sig.b_fire_short)[j]))
        window = (b.minute >= OW.WINDOW_FIRST_MIN) & (b.minute <= OW.WINDOW_LAST_MIN)
        assert np.array_equal(fired[window], pine[key][window]), key
        assert fired.sum() > 0, f"fixture never fires {key}"


def test_atr_matches_pine(market):
    b = market.b5
    pine = _atr(b.h.tolist(), b.l.tolist(), b.c.tolist())
    assert market.atr[13:] == pytest.approx(pine[13:])


def test_pine_inputs_match_the_registered_numbers():
    if not PINE.exists():
        pytest.skip("the Pine file lives in 'Claude outputs' (not in git)")
    text = PINE.read_text(encoding="utf-8")
    assert "v1.0 REGISTERED" in text

    def default(name):
        m = re.search(rf'^{name}\s*=\s*input\.\w+\("?([^",)]*)"?', text, re.M)
        assert m, name
        return m.group(1)

    assert default("entrySess") == "0800-1200" and default("impSess") == "0800-1200"
    assert (int(default("startHHMM")), int(default("flatHHMM"))) == (800, 1555)
    assert default("htfTf") == "60"
    assert float(default("bigMult")) == OW.BIG_MULT
    assert int(default("slotLen")) == OW.SLOT_LEN
    assert int(default("crossBars")) == OW.CROSS_K == OW.MACD_K
    assert int(default("pbBars")) == OW.PULLBACK_BARS
    assert int(default("swingBars")) == OW.SWING_BARS
    assert float(default("minStopAtr")) == OW.STOP_MIN_ATR
    assert float(default("maxStopAtr")) == OW.STOP_MAX_ATR
    assert float(default("trailAtr")) == OW.TRAIL_ATR
    assert int(default("maxTrades")) == OW.MAX_FILLS_PER_DAY
    assert f"prevN >= {OW.SLOT_MIN_OBS}" in text
