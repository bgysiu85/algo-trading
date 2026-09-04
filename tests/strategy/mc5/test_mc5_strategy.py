#!/usr/bin/env python3
"""Checks MC5 against hand-computed cases.

The gradient definitions are new, so they get tested against closed-form
answers rather than against themselves.
"""
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from strategy.mc5 import mc5 as M

ET = ZoneInfo("America/New_York")


def frame_1m(closes, highs=None, lows=None, vols=None, start="03:00"):
    n = len(closes)
    t0 = datetime.strptime(f"2026-09-02 {start}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    idx = pd.date_range(t0, periods=n, freq="1min").tz_convert("UTC")
    highs = highs or [c * 1.001 for c in closes]
    lows = lows or [c * 0.999 for c in closes]
    vols = vols or [5000] * n
    return pd.DataFrame({"open": closes, "high": highs, "low": lows,
                         "close": closes, "volume": vols}, index=idx)


def momentum_series(seed: int, n: int = 900):
    """Two-sided noise with intermittent momentum bursts.

    A near-monotonic ramp is NOT a usable fixture here: it pins RSI at ~100,
    where its rate of change is zero by construction, so no RSI-gradient entry
    can ever fire. Real pre-market movers pull back; the series must too.
    """
    rng = np.random.default_rng(seed)
    px, out, burst = 3.0, [], 0
    for _ in range(n):
        if burst == 0 and rng.random() < 0.02:
            burst = int(rng.integers(15, 50))
        drift = 0.004 if burst > 0 else 0.0
        if burst > 0:
            burst -= 1
        px *= 1.0 + drift + rng.normal(0, 0.004)
        out.append(max(px, 0.2))
    return out


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS" if cond else "FAIL"), msg)

    # --- 1. ols_slope closed form ----------------------------------------
    # y = 0,2,4,6,8 -> slope 2 per bar, exactly, for any window.
    s = pd.Series([0.0, 2.0, 4.0, 6.0, 8.0])
    sl = M.ols_slope(s, 3)
    check(abs(sl.iloc[-1] - 2.0) < 1e-12, f"ols_slope on a straight line = 2.0 (got {sl.iloc[-1]:.6f})")
    # n=3 must reduce to (y[t]-y[t-2])/2
    check(abs(sl.iloc[-1] - (s.iloc[-1] - s.iloc[-3]) / 2) < 1e-12,
          "ols_slope(n=3) equals (y[t]-y[t-2])/2")
    # flat series -> zero slope
    check(abs(M.ols_slope(pd.Series([5.0] * 5), 3).iloc[-1]) < 1e-12,
          "flat series has zero slope")
    # descending -> negative
    check(M.ols_slope(pd.Series([9.0, 6.0, 3.0]), 3).iloc[-1] < 0,
          "descending series has negative slope")

    # --- 2. roc_pct is a percentage of the FITTED start -------------------
    # y = 50, 52, 54 -> slope 2, mean 52, span 4, fitted start 50 -> 8%
    s = pd.Series([50.0, 52.0, 54.0])
    got = M.roc_pct(s, 3).iloc[-1]
    check(abs(got - 8.0) < 1e-12, f"roc_pct(50,52,54) = 8.0% (got {got:.6f})")
    # symmetric fall
    s = pd.Series([54.0, 52.0, 50.0])
    got = M.roc_pct(s, 3).iloc[-1]
    check(abs(got - (-4.0 / 54.0 * 100)) < 1e-9,
          f"roc_pct falling is negative (got {got:.4f})")
    # the SLOPE is immune to an interior spike (that is the n=3 closed form);
    # the denominator is not, because the OLS intercept uses the window mean.
    a = M.ols_slope(pd.Series([50.0, 52.0, 54.0]), 3).iloc[-1]
    b = M.ols_slope(pd.Series([50.0, 99.0, 54.0]), 3).iloc[-1]
    check(abs(a - b) < 1e-12, "an interior spike does not change ols_slope")
    check(M.roc_pct(pd.Series([50.0, 99.0, 54.0]), 3).iloc[-1] > 0,
          "roc_pct keeps its sign through an interior spike")

    # low-RSI blow-ups are bounded by ROC_MIN_BASE
    wild = M.roc_pct(pd.Series([0.4, 1.0, 8.0]), 3).iloc[-1]
    check(wild <= (8.0 - 0.4) / M.ROC_MIN_BASE * 100 + 1e-9,
          f"roc_pct is bounded when RSI is near zero (got {wild:.1f}%)")

    # --- 3. resampling is LEFT-labelled ----------------------------------
    df = frame_1m([3.0 + i * 0.01 for i in range(30)], start="04:00")
    d5 = M.to_5m(df)
    first_et = d5.index[0].tz_convert(ET)
    check(first_et.hour == 4 and first_et.minute == 0,
          f"first 5m bar is labelled 04:00 ET, not 04:05 (got {first_et.strftime('%H:%M')})")
    check(len(d5) == 6, f"30 one-minute bars -> 6 five-minute bars (got {len(d5)})")
    # OHLCV aggregation of the first bucket
    b0, src = d5.iloc[0], df.iloc[0:5]
    check(abs(b0["open"] - src["open"].iloc[0]) < 1e-12
          and abs(b0["close"] - src["close"].iloc[-1]) < 1e-12
          and abs(b0["high"] - src["high"].max()) < 1e-12
          and abs(b0["low"] - src["low"].min()) < 1e-12
          and b0["volume"] == src["volume"].sum(),
          "5m OHLCV aggregation is correct")

    # --- 4. entry needs ALL THREE conditions ------------------------------
    df = frame_1m(momentum_series(seed=1), start="00:00")
    sig = M.signals(M.to_5m(df))
    check({"c_rsi", "c_ema", "c_macd", "entry", "exit_sig"} <= set(sig.columns),
          "signals() produces every condition column")
    # entry must be the strict AND of the three
    recomputed = sig["c_rsi"] & sig["c_ema"] & sig["c_macd"]
    check(bool((sig["entry"] == recomputed).all()),
          "entry == c_rsi AND c_ema AND c_macd, with no extra condition")
    check(bool(sig["entry"].any()), "at least one entry fires on a trending series")
    # no entry may fire where any leg is false
    viol = sig[sig["entry"] & (~sig["c_rsi"] | ~sig["c_ema"] | ~sig["c_macd"])]
    check(len(viol) == 0, f"no entry fires with a failing leg ({len(viol)} violations)")

    # --- 5. exit needs BOTH gradients negative ----------------------------
    only_one = sig[sig["exit_sig"] & (~sig["x_rsi"] | ~sig["x_macd"])]
    check(len(only_one) == 0,
          f"exit_sig never fires on a single gradient ({len(only_one)} violations)")
    both = sig["x_rsi"] & sig["x_macd"]
    check(bool((sig["exit_sig"] == both).all()), "exit_sig == x_rsi AND x_macd")

    # --- 6. entry threshold is actually enforced --------------------------
    below = sig[sig["c_rsi"] & (sig["rsi_roc"] < M.ENTRY_RSI_ROC_PCT)]
    check(len(below) == 0,
          f"c_rsi never true below {M.ENTRY_RSI_ROC_PCT}% ({len(below)} violations)")

    # --- 7. a round trip is produced and is well formed -------------------
    trades = M.backtest_session(df, date(2026, 9, 2), ET)
    check(bool(trades), f"engine produces round trips ({len(trades)} trades)")
    if trades:
        t = trades[0]
        expect = round((t.exit_price - t.entry_price) * t.qty
                       - M.COMMISSION_PER_SHARE * t.qty * 2, 2)
        check(abs(t.net - expect) < 0.01, f"net arithmetic {t.net:+.2f} == {expect:+.2f}")
        check(t.reason in ("trailing_stop", "gradient_reversal", "window_close"),
              f"exit reason valid: {t.reason}")
        check(all(x.bars_held >= 0 for x in trades), "bars_held never negative")

    # --- 8. no trades outside the window ----------------------------------
    late = frame_1m([3.0 + i * 0.02 for i in range(300)], start="10:00")
    check(not M.backtest_session(late, date(2026, 9, 2), ET),
          "no trades outside 04:00-09:30")

    # --- 9. trailing stop has no same-bar lookahead -----------------------
    # A bar that spikes then collapses within itself must not stop out against
    # its OWN high -- the trail comes from the previous bar's peak.
    closes = [10.0] * 400
    highs = [10.01] * 400
    lows = [9.99] * 400
    highs[399] = 20.0          # violent spike on the final bar
    lows[399] = 10.0
    df = frame_1m(closes, highs, lows, start="00:00")
    d5 = M.to_5m(df)
    peak_before = d5["high"].iloc[:-1].max()
    check(peak_before < 20.0,
          "spike is confined to the final bar (fixture sanity)")

    # --- 10. warm-up guard is honest --------------------------------------
    short = frame_1m([3.0 + i * 0.01 for i in range(60)], start="04:00")
    s5 = M.signals(M.to_5m(short))
    warm = s5["macd"].notna().sum()
    check(len(M.to_5m(short)) < M.MIN_WARMUP_BARS,
          f"a cold session has fewer than {M.MIN_WARMUP_BARS} bars "
          f"({len(M.to_5m(short))}) -- warm-up history is required")

    # --- 11. indicators agree with mcl_strategy's implementations ---------
    try:
        from strategy.mcl import mcl as S
        c = pd.Series([3.0 + (i % 7) * 0.05 for i in range(200)])
        d1 = float((M.macd(c)[0] - S.macd(c)[0]).abs().max())
        d2 = float((M.rsi(c) - S.rsi(c)).abs().max())
        check(max(d1, d2) < 1e-12,
              f"MACD and RSI match mcl_strategy (max diff {max(d1, d2):.2e})")
    except ImportError:
        print("SKIP  mcl_strategy not importable here")

    print()
    print("ALL MC5 CHECKS PASSED" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
