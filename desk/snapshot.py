"""Daily bars -> the "verified market snapshot" the market analyst treats as the
only source of exact numbers.

The same discipline as the TradingAgents original: every number an agent quotes
about price must come from here, not from a web page or from memory.
"""
from __future__ import annotations

import math
from datetime import datetime, time, timezone

import pandas as pd

from desk import indicators as ind

COLUMNS = ["open", "high", "low", "close", "volume"]
MIN_BARS = 60           # below this the snapshot is refused: nothing to analyse


def _f(x, nd: int = 4):
    """float or None. JSON has no NaN, and a silent NaN in a prompt is a lie."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd)


def clean_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Index = date (normalised, tz-naive), columns open/high/low/close/volume,
    sorted, de-duplicated, rows without a close dropped."""
    if df is None or len(df) == 0:
        raise ValueError("no bars")
    d = df.copy()
    d.columns = [str(c).strip().lower() for c in d.columns]
    if "date" in d.columns:
        d = d.set_index("date")
    missing = [c for c in COLUMNS if c not in d.columns]
    if missing:
        raise ValueError(f"bars are missing columns: {missing}")
    idx = pd.to_datetime(d.index, errors="coerce")
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    d.index = idx.normalize()
    d = d[~d.index.isna()]
    d = d[COLUMNS].apply(pd.to_numeric, errors="coerce")
    d = d.dropna(subset=["close"])
    d = d[~d.index.duplicated(keep="last")].sort_index()
    d["volume"] = d["volume"].fillna(0.0)
    d.index.name = "date"
    return d


def drop_partial_bar(df: pd.DataFrame, now_utc: datetime | None = None) -> tuple[pd.DataFrame, bool]:
    """If the newest bar is TODAY (US/Eastern) and the session has not closed,
    it is a half-built bar: drop it, so every number is "as of the last close".
    Returns (frame, dropped)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return df, False
    last = df.index[-1].date()
    session_open = now_et.weekday() < 5 and now_et.time() < time(16, 15)
    if last == now_et.date() and session_open:
        return df.iloc[:-1], True
    return df, False


def build_snapshot(df: pd.DataFrame, ticker: str, run_date: str, partial_dropped: bool = False) -> dict:
    d = clean_bars(df)
    if len(d) < MIN_BARS:
        raise ValueError(f"only {len(d)} daily bars for {ticker}; need at least {MIN_BARS}")
    c, h, lo, v = d["close"], d["high"], d["low"], d["volume"]

    sma50, sma200 = ind.sma(c, 50), ind.sma(c, 200)
    ema10 = ind.ema(c, 10)
    ml, ms, mh = ind.macd(c)
    rsi14 = ind.rsi(c, 14)
    bm, bu, bl = ind.bollinger(c, 20, 2.0)
    atr14 = ind.atr(h, lo, c, 14)
    vw20 = ind.vwma(c, v, 20)

    last = d.iloc[-1]
    close = float(last["close"])
    prev = float(c.iloc[-2])
    n = len(d)

    def ret(k: int):
        return _f((close / float(c.iloc[-1 - k]) - 1.0) * 100.0, 2) if n > k else None

    win = d.iloc[-252:]
    hi52, lo52 = float(win["high"].max()), float(win["low"].min())
    avgv = float(v.iloc[-20:].mean()) if n >= 20 else None
    band = (float(bu.iloc[-1]) - float(bl.iloc[-1])) if not math.isnan(bu.iloc[-1]) else None
    pct_b = ((close - float(bl.iloc[-1])) / band) if band else None

    snap = {
        "ticker": ticker,
        "run_date": run_date,
        "last_bar_date": d.index[-1].strftime("%Y-%m-%d"),
        "partial_bar_dropped": bool(partial_dropped),
        "bars": n,
        "first_bar_date": d.index[0].strftime("%Y-%m-%d"),
        "price": {
            "close": _f(close), "prev_close": _f(prev),
            "change_1d_pct": _f((close / prev - 1.0) * 100.0, 2),
            "open": _f(last["open"]), "high": _f(last["high"]), "low": _f(last["low"]),
            "volume": _f(last["volume"], 0),
        },
        "returns_pct": {"1m": ret(21), "3m": ret(63), "6m": ret(126), "12m": ret(252)},
        "range_52w": {
            "high": _f(hi52), "low": _f(lo52),
            "pct_below_high": _f((close / hi52 - 1.0) * 100.0, 2),
            "pct_above_low": _f((close / lo52 - 1.0) * 100.0, 2),
        },
        "indicators": {
            "ema10": _f(ema10.iloc[-1]), "sma50": _f(sma50.iloc[-1]), "sma200": _f(sma200.iloc[-1]),
            "macd": _f(ml.iloc[-1]), "macd_signal": _f(ms.iloc[-1]), "macd_hist": _f(mh.iloc[-1]),
            "rsi14": _f(rsi14.iloc[-1], 2),
            "boll_mid": _f(bm.iloc[-1]), "boll_upper": _f(bu.iloc[-1]), "boll_lower": _f(bl.iloc[-1]),
            "boll_pct_b": _f(pct_b, 3),
            "atr14": _f(atr14.iloc[-1]),
            "atr14_pct_of_close": _f(float(atr14.iloc[-1]) / close * 100.0, 2),
            "vwma20": _f(vw20.iloc[-1]),
        },
        "volume": {
            "avg_20d": _f(avgv, 0),
            "last_vs_avg": _f(float(last["volume"]) / avgv, 2) if avgv else None,
        },
    }
    i = snap["indicators"]
    flags = {}
    if i["sma50"] is not None:
        flags["close_above_sma50"] = close > i["sma50"]
    if i["sma200"] is not None:
        flags["close_above_sma200"] = close > i["sma200"]
    if i["sma50"] is not None and i["sma200"] is not None:
        flags["sma50_above_sma200"] = i["sma50"] > i["sma200"]
    if i["macd_hist"] is not None:
        flags["macd_hist_positive"] = i["macd_hist"] > 0
    if i["rsi14"] is not None:
        flags["rsi_zone"] = "overbought>70" if i["rsi14"] > 70 else ("oversold<30" if i["rsi14"] < 30 else "neutral")
    snap["flags"] = flags
    return snap


def _fmt(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def render_market_markdown(s: dict) -> str:
    p, i, r, g, vol = s["price"], s["indicators"], s["returns_pct"], s["range_52w"], s["volume"]
    note = (" (today's unfinished bar was dropped, so everything is as of the previous close)"
            if s.get("partial_bar_dropped") else "")
    lines = [
        f"# {s['ticker']} verified market snapshot",
        f"Run date {s['run_date']} (US). Last completed daily bar: {s['last_bar_date']}{note}. "
        f"{s['bars']} daily bars from IBKR ({s['first_bar_date']} onward). "
        "These numbers are computed by script and are the ONLY authority for exact prices and indicator values.",
        "",
        "| Item | Value |", "|---|---|",
        f"| Close | {_fmt(p['close'])} |",
        f"| Prior close / 1-day change | {_fmt(p['prev_close'])} / {_fmt(p['change_1d_pct'])}% |",
        f"| Day range (O/H/L) | {_fmt(p['open'])} / {_fmt(p['high'])} / {_fmt(p['low'])} |",
        f"| Volume vs 20-day average | {_fmt(p['volume'], 0)} vs {_fmt(vol['avg_20d'], 0)} (x{_fmt(vol['last_vs_avg'])}) |",
        f"| Return 1m / 3m / 6m / 12m | {_fmt(r['1m'])}% / {_fmt(r['3m'])}% / {_fmt(r['6m'])}% / {_fmt(r['12m'])}% |",
        f"| 52-week high / low | {_fmt(g['high'])} / {_fmt(g['low'])} |",
        f"| Distance from 52w high / above 52w low | {_fmt(g['pct_below_high'])}% / {_fmt(g['pct_above_low'])}% |",
        f"| 10 EMA / 50 SMA / 200 SMA | {_fmt(i['ema10'])} / {_fmt(i['sma50'])} / {_fmt(i['sma200'])} |",
        f"| MACD / signal / histogram | {_fmt(i['macd'], 3)} / {_fmt(i['macd_signal'], 3)} / {_fmt(i['macd_hist'], 3)} |",
        f"| RSI(14) | {_fmt(i['rsi14'])} |",
        f"| Bollinger(20,2) lower / mid / upper | {_fmt(i['boll_lower'])} / {_fmt(i['boll_mid'])} / {_fmt(i['boll_upper'])} (%B {_fmt(i['boll_pct_b'], 3)}) |",
        f"| ATR(14) | {_fmt(i['atr14'])} ({_fmt(i['atr14_pct_of_close'])}% of close) |",
        f"| VWMA(20) | {_fmt(i['vwma20'])} |",
        "",
        "Facts (true/false, computed): " + ", ".join(f"{k}={v}" for k, v in s["flags"].items()),
    ]
    return "\n".join(lines) + "\n"
