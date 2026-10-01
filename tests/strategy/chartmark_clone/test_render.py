"""G3: the picture is blind (matplotlib). Pixels: truncation invariance, relative price axis, one-bar sensitivity.
Text: only weekday/hour, dollars from the order, and fixed labels -- no date, month, year, instrument or absolute price."""
import re

import matplotlib
matplotlib.use("Agg")
import numpy as np

from strategy.chartmark.data import make_frame
from strategy.chartmark_clone import render as R
from strategy.chartmark_clone.chartdata import build_chart_data
from tests.strategy.chartmark.synth import walk

WD = "Mon|Tue|Wed|Thu|Fri|Sat|Sun"
WD2 = "Mo|Tu|We|Th|Fr|Sa|Su"
MONTHS = r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(t(ember)?)?|oct(ober)?|nov(ember)?|dec(ember)?)\b"
TEXT_OK = [
    re.compile(rf"^({WD})( \d\dh)?$"),
    re.compile(rf"^({WD2})$"),
    re.compile(r"^[-+−]?\d+\.\d\d$"),                               # dollars from the order (tick labels)
    re.compile(r"^(today|prev) (hi|lo)$"),
    re.compile(r"^buy-stop for the next bar$"),
    re.compile(r"^Daily: 60 days \+ today so far \(hollow\)  EMA9 blue  EMA21 orange$"),
    re.compile(r"^1H: last 120 bars, right edge = decision bar   axis = \\\$ from the order   ATR\(14\) (\\\$\d+\.\d\d|n/a)$"),
    re.compile(r"^Volume with SMA\(20\)$"),
    re.compile(r"^MACD\(12,26,9\): line blue, signal orange, histogram bars$"),
]


def clone(fr):
    o, h, l, c, v = (getattr(fr, k).copy() for k in "ohlcv")
    return make_frame(fr.t, o, h, l, c, v, fr.roll_after.copy(), "mut")


def frame():
    return walk(3000, 7, drift=0.0, vol=0.3, start="2015-03-02 00:00")


def pix(fr, t, lvl):
    return R.render_rgba(build_chart_data(fr), t, lvl)


def test_truncation_invariance_mutating_every_bar_after_t_leaves_the_pixels_identical():
    fr = frame()
    for t in (200, 1234, 1800, 2400):
        lvl = float(fr.h[t]) + 0.4
        base = pix(fr, t, lvl)
        mut = clone(fr)
        rng = np.random.default_rng(t)
        for arr in (mut.o, mut.h, mut.l, mut.c, mut.v):
            arr[t + 1:] = rng.uniform(1, 900, len(arr) - t - 1)
        assert pix(mut, t, lvl) == base, t


def test_a_one_bar_shift_or_a_change_in_the_last_bar_changes_the_picture():
    fr = frame()
    t, lvl = 1500, float(fr.h[1500]) + 0.4
    base = pix(fr, t, lvl)
    assert pix(fr, t - 1, lvl) != base
    assert pix(fr, t, lvl + 0.05) != base
    for k in ("c", "h", "l", "o", "v"):
        mut = clone(fr)
        getattr(mut, k)[t] += 0.37 if k != "v" else 900.0
        assert pix(mut, t, lvl) != base, k
    mut = clone(fr)
    mut.c[t - 1] += 0.4
    assert pix(mut, t, lvl) != base


def test_the_last_drawn_bar_is_t_not_t_plus_one():
    fr = frame()
    t, lvl = 900, float(fr.h[900]) + 0.2
    base = pix(fr, t, lvl)
    mut = clone(fr)
    mut.h[t + 1] += 5.0
    mut.c[t + 1] -= 3.0
    assert pix(mut, t, lvl) == base


def test_the_price_axis_is_relative_absolute_price_is_hidden():
    fr = frame()
    t, lvl = 1500, float(fr.h[1500]) + 0.4
    base_txt = _texts(fr, t, lvl)
    sh = clone(fr)
    for k in "ohlc":
        setattr(sh, k, getattr(sh, k) + 512.0)
    txt = _texts(sh, t, lvl + 512.0)
    assert txt == base_txt                                                # every label is unchanged by a level shift
    a = np.frombuffer(pix(fr, t, lvl), np.uint8).astype(int)
    b = np.frombuffer(pix(sh, t, lvl + 512.0), np.uint8).astype(int)
    assert np.mean(a != b) < 0.002                                        # same picture up to float rounding


def _texts(fr, t, lvl):
    fig = R.new_figure()
    R.draw_candidate(fig, build_chart_data(fr), t, lvl)
    return R.figure_texts(fig)


def test_no_date_month_year_instrument_or_absolute_price_reaches_the_picture():
    fr = frame()
    for t in (36, 400, 1500, 2900):
        lvl = float(fr.h[t]) + 0.3
        for s in _texts(fr, t, lvl):
            assert any(p.match(s) for p in TEXT_OK), f"unexpected text {s!r}"
            assert not re.search(r"\b(19|20)\d{2}\b", s)
            assert not re.search(MONTHS, s.lower())
            assert not re.search(r"\bm?cl[fghjkmnquvxz]?\d{0,2}\b", s.lower())
            assert "crude" not in s.lower()


def test_an_early_candidate_with_little_history_renders():
    fr = frame()
    assert len(pix(fr, 36, float(fr.h[36]) + 0.1)) > 0
