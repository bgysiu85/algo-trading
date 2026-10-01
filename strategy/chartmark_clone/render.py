#!/usr/bin/env python3
"""The blind chart, drawn with matplotlib. REGISTERED_chartmark_clone.md sec 4 and gate G3.

draw_candidate(fig, cd, t, level) draws bars <= t and nothing else:
  * daily panel: last 60 completed trading days plus today so far (hollow), daily EMA9 / EMA21;
  * 1H panel: last 120 bars ending at t, EMA9 / EMA21, the buy-stop level, current and previous trading-day high / low;
  * volume with SMA(20); MACD(12,26,9) line, signal, histogram.
Price axes are dollars from the order (level = 0.00). Time axes carry weekday and hour (New York) only. The figure holds
no date, month, year, instrument name, absolute price, progress text or candidate id -- the window adds its status lines
as separate text outside this function.

Deterministic: the same inputs give the same pixels. Everything is read through indices <= t (or completed days)."""
from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.text import Text
from matplotlib.ticker import FuncFormatter, MaxNLocator

from strategy.chartmark_clone import daily as DL
from strategy.chartmark_clone import spec as S
from strategy.chartmark_clone.chartdata import ChartData, build_chart_data  # noqa: F401  (re-exported)

FIGSIZE, DPI = (11.6, 9.6), 100
UP, DOWN = "#2a9d8f", "#d1495b"
E9C, E21C, LVLC = "#1d6fb8", "#c77d00", "#7a3fb3"
INK, GRID, MUTED = "#222222", "#e2e2e2", "#777777"
DAY2 = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


def _fin(a) -> np.ndarray:
    a = np.asarray(a, float)
    return a[np.isfinite(a)]


def _rel(v, _pos=None) -> str:
    return "0.00" if abs(v) < 1e-9 else f"{v:+.2f}"


def _limits(*arrays, pad: float = 0.05) -> tuple[float, float]:
    v = np.concatenate([_fin(a) for a in arrays])
    lo, hi = float(v.min()), float(v.max())
    p = (hi - lo) * pad if hi > lo else 1.0
    return lo - p, hi + p


def _style(ax, title: str, xlim: tuple[float, float]) -> None:
    ax.set_facecolor("white")
    ax.set_xlim(*xlim)
    for sp in ax.spines.values():
        sp.set_color("#bbbbbb")
        sp.set_linewidth(0.8)
    ax.yaxis.tick_right()
    ax.tick_params(axis="y", labelsize=7.5, colors=MUTED, length=2)
    ax.tick_params(axis="x", labelsize=6.5, colors=MUTED, length=2)
    ax.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=8, color=INK, pad=3, family="monospace")


def _price_axis(ax, lo: float, hi: float) -> None:
    ax.set_ylim(lo, hi)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_major_formatter(FuncFormatter(_rel))


def _candles(ax, x, o, h, l, c, lo: float, hi: float, hollow_last: bool = False) -> None:
    minh = (hi - lo) * 0.003
    ok = np.isfinite(o) & np.isfinite(c) & np.isfinite(h) & np.isfinite(l)
    up = ok & (c >= o)
    dn = ok & (c < o)
    for mask, col in ((up, UP), (dn, DOWN)):
        i = np.where(mask)[0]
        if not len(i):
            continue
        ax.vlines(x[i], l[i], h[i], colors=col, linewidth=0.8, zorder=2)
        ax.bar(x[i], np.maximum(np.abs(c[i] - o[i]), minh), bottom=np.minimum(o[i], c[i]), width=0.62, color=col,
               linewidth=0, zorder=3)
    if hollow_last and ok[-1]:
        col = UP if c[-1] >= o[-1] else DOWN
        ax.bar([x[-1]], [max(abs(c[-1] - o[-1]), minh)], bottom=[min(o[-1], c[-1])], width=0.62, color="white",
               edgecolor=col, linewidth=0.9, zorder=4)


def _atr_txt(v) -> str:
    return f"\\${float(v):.2f}" if np.isfinite(v) else "n/a"


def draw_candidate(fig: Figure, cd: ChartData, t: int, level: float) -> None:
    fr, ind, d = cd.fr, cd.ind, cd.daily
    if t < 1 or t >= fr.n:
        raise ValueError("decision bar out of range")
    n1 = S.N_1H
    idx = np.arange(t - n1 + 1, t + 1)                          # bar indices, all <= t
    valid = idx >= 0
    ii = np.where(valid, idx, 0)

    def take(arr) -> np.ndarray:
        return np.where(valid, np.asarray(arr, float)[ii], np.nan)

    o, h, l, c = (take(x) - level for x in (fr.o, fr.h, fr.l, fr.c))
    e9, e21 = take(ind.e9) - level, take(ind.e21) - level
    day = int(d.day_of_bar[t])
    a0 = int(d.first[day])
    day_hi, day_lo = float(fr.h[a0: t + 1].max()) - level, float(fr.l[a0: t + 1].min()) - level
    prev = (float(d.h[day - 1]) - level, float(d.l[day - 1]) - level) if day >= 1 else None

    fig.clf()
    fig.set_facecolor("white")
    gs = fig.add_gridspec(4, 1, height_ratios=[3.0, 4.7, 1.25, 1.9], hspace=0.46, left=0.012, right=0.928, top=0.955,
                          bottom=0.155)
    ad, a1, av, am = (fig.add_subplot(gs[i]) for i in range(4))

    # ---- daily panel (60 completed days + today so far) ----
    nd = S.N_DAILY + 1
    dx = np.arange(nd, dtype=float)
    di = np.arange(day - S.N_DAILY, day)                        # completed days only
    dvalid = di >= 0
    dj = np.where(dvalid, di, 0)

    def dtake(arr) -> np.ndarray:
        return np.where(dvalid, np.asarray(arr, float)[dj], np.nan)

    po, ph, pl, pc = DL.partial_today(fr, d, t)
    do = np.concatenate([dtake(d.o), [po]]) - level
    dh = np.concatenate([dtake(d.h), [ph]]) - level
    dl = np.concatenate([dtake(d.l), [pl]]) - level
    dc = np.concatenate([dtake(d.c), [pc]]) - level
    de = []
    for series, n in ((d.e9, 9), (d.e21, 21)):
        last = series[day - 1] if day >= 1 else np.nan
        step = (2.0 / (n + 1)) * pc + (1 - 2.0 / (n + 1)) * last if np.isfinite(last) else np.nan
        de.append(np.concatenate([dtake(series), [step]]) - level)
    _style(ad, "Daily: 60 days + today so far (hollow)  EMA9 blue  EMA21 orange", (-0.8, nd - 0.2))
    dlo, dhi = _limits(np.array([0.0]), dh, dl, de[0], de[1])
    _price_axis(ad, dlo, dhi)
    ad.axhline(0.0, color=LVLC, linewidth=1.0, linestyle=(0, (6, 4)), zorder=1)
    _candles(ad, dx, do, dh, dl, dc, dlo, dhi, hollow_last=True)
    ad.plot(dx, de[0], color=E9C, linewidth=1.2, zorder=5)
    ad.plot(dx, de[1], color=E21C, linewidth=1.2, zorder=5)
    pos, lab = [], []
    for s in range(nd):
        dd = day - S.N_DAILY + s if s < S.N_DAILY else day
        if dd >= 0:
            pos.append(s)
            lab.append(DAY2[int(d.weekday[dd])])
    ad.set_xticks(pos)
    ad.set_xticklabels(lab, fontsize=6)

    # ---- 1H panel ----
    x = np.arange(n1, dtype=float)
    _style(a1, f"1H: last 120 bars, right edge = decision bar   axis = \\$ from the order   ATR(14) "
               f"{_atr_txt(ind.atr[t])}", (-0.8, n1 - 0.2))
    day_lines = [(day_hi, "today hi"), (day_lo, "today lo")]
    if prev:
        day_lines += [(prev[0], "prev hi"), (prev[1], "prev lo")]
    lo1, hi1 = _limits(np.array([0.0]), h, l, e9, e21, np.array([v for v, _ in day_lines]))
    _price_axis(a1, lo1, hi1)
    for val, name in day_lines:
        a1.axhline(val, color="#8a8a8a", linewidth=0.8, linestyle=(0, (2, 3)), zorder=1)
        a1.text(0.004, val, name, transform=a1.get_yaxis_transform(), va="bottom", fontsize=7, color="#8a8a8a")
    _candles(a1, x, o, h, l, c, lo1, hi1)
    a1.plot(x, e9, color=E9C, linewidth=1.2, zorder=5)
    a1.plot(x, e21, color=E21C, linewidth=1.2, zorder=5)
    a1.axhline(0.0, color=LVLC, linewidth=1.5, linestyle=(0, (7, 4)), zorder=6)
    a1.text(0.996, 0.0, "buy-stop for the next bar", transform=a1.get_yaxis_transform(), va="bottom", ha="right",
            fontsize=7.5, color=LVLC,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1.0))

    # ---- volume ----
    _style(av, "Volume with SMA(20)", (-0.8, n1 - 0.2))
    vv, vs = take(fr.v), take(ind.vol_sma)
    vmax = float(np.nanmax(np.concatenate([_fin(vv), _fin(vs), [1.0]]))) * 1.05
    av.set_ylim(0, vmax)
    av.set_yticks([])
    okv = np.isfinite(vv)
    av.bar(x[okv], vv[okv], width=0.62, color=np.where(c[okv] >= o[okv], UP, DOWN).tolist(), alpha=0.55, linewidth=0)
    av.plot(x, vs, color=INK, linewidth=1.0)

    # ---- MACD ----
    _style(am, "MACD(12,26,9): line blue, signal orange, histogram bars", (-0.8, n1 - 0.2))
    hist, ml, sg = take(cd.macd - cd.sig), take(cd.macd), take(cd.sig)
    mlo, mhi = _limits(hist, ml, sg, np.array([0.0]))
    am.set_ylim(mlo, mhi)
    am.yaxis.set_major_locator(MaxNLocator(nbins=4, steps=[1, 2, 2.5, 5, 10]))
    am.yaxis.set_major_formatter(FuncFormatter(_rel))
    okh = np.isfinite(hist)
    am.bar(x[okh], hist[okh], width=0.62, color=np.where(hist[okh] >= 0, UP, DOWN).tolist(), alpha=0.6, linewidth=0)
    am.axhline(0.0, color="#999999", linewidth=0.8)
    am.plot(x, ml, color=E9C, linewidth=1.1)
    am.plot(x, sg, color=E21C, linewidth=1.1)

    # ---- shared time axis (weekday and hour only) and the 18:00 trading-day rolls ----
    for i in range(1, n1):
        if valid[i] and valid[i - 1] and d.day_of_bar[idx[i]] != d.day_of_bar[idx[i - 1]]:
            for a in (a1, av, am):
                a.axvline(i - 0.5, color="#d0d0d0", linewidth=0.6, linestyle=(0, (1, 3)), zorder=1)
    pos = [i for i in range(n1) if valid[i] and (n1 - 1 - i) % 12 == 0]
    labs = [f"{DL.WEEKDAY[int(cd.wday[int(idx[i])])]} {int(cd.hour[int(idx[i])]):02d}h" for i in pos]
    for a in (a1, av):
        a.set_xticks(pos)
        a.set_xticklabels([])
    am.set_xticks(pos)
    am.set_xticklabels(labs, fontsize=6.5)


def new_figure() -> Figure:
    fig = Figure(figsize=FIGSIZE, dpi=DPI)
    FigureCanvasAgg(fig)
    return fig


def render_rgba(cd: ChartData, t: int, level: float) -> bytes:
    """The picture as raw pixels (used by the blinding tests)."""
    fig = new_figure()
    draw_candidate(fig, cd, t, level)
    fig.canvas.draw()
    return np.asarray(fig.canvas.buffer_rgba()).tobytes()


def figure_texts(fig: Figure) -> list[str]:
    """Every non-empty text in the figure (titles, tick labels, annotations)."""
    return [x.get_text() for x in fig.findobj(Text) if x.get_text()]
