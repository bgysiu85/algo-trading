# `screen_at` — the point-in-time screen, built 2026-09-10

Step 4 of `screener_simulation_scope.md` §6. The screen evaluated **as of a
timestamp**, so the universe can be chosen at 03:59 instead of with the whole
day already known.

Module: `common/screen_at.py`. Tests: `tests/common/test_screen_at.py`, 27.
Shipped in bundle `20260910k`. **Not yet run on the archive.**

---

## 1. The one design decision that matters

**The screen's rules are imported from `tv_screener`, never restated.**

```python
from common.tv_feed import MAX_SYMBOLS
from common.tv_screener import (PREMARKET_CHANGE_MIN, PREMARKET_PRICE_RANGE,
                                PREMARKET_VOLUME_MIN)
```

The scope document found `screen.py`'s `stage2` applying `min_rvol = 5.0` while
the shipped screen has no RVOL clause at all. The simulation and the thing it
simulates had drifted apart and neither said so. A restated constant is a copy
that goes stale silently; an imported one cannot.

Two tests pin it: the config fields must **be** the live objects (`is`, not
`==`), and `tv_screener.FILTERS` must still be exactly three named clauses — so
a clause added live and not here fails the suite rather than surfacing as a
wrong number in a report.

## 2. Two conventions that decide the answer

### A bar counts only once it has CLOSED

`ts_event` is the interval **start** (`dbn_io` convention 1). The bar stamped
04:29 covers 04:29:00–04:29:59 and is not knowable until 04:30:00. Screening at
`t` on `index <= t` therefore reads up to 59 seconds of the future on **every
symbol, on every cadence tick**.

This is the entry-latency defect with the sign reversed. There, a closed bar was
being discarded and cost the live trader a minute. Here, a forming bar would be
kept and would **flatter** the result — which is why nobody would have caught it
downstream.

### The volume threshold is on a partial tape

`premarket_volume >= 100,000` is a threshold against TradingView's
**consolidated** figure. XNAS.BASIC carries a measured median **55.2%** of the
consolidated tape (p10 0.458, p90 0.656).

Holding 100,000 against our tape silently demands ~182k of real pre-market
volume, so the simulated screen would be strictly tighter than the live one and
would under-select — reading, in the output, as *"the screen is too tight"*
rather than as a units error.

The threshold is therefore **scaled**, which makes the capture ratio a
load-bearing input rather than a footnote. `capture_sensitivity()` re-runs the
screen at p10/p50/p90 and should be reported next to any headline: **a finding
that only survives at p50 is a finding about the capture estimate.**

## 3. The leak test

`screen_at` truncates its **own** input rather than trusting the caller to pass
a pre-cut frame. That is the entire reason the leak test can exist — if the
caller truncated, appending future rows would legitimately change the output and
there would be nothing to assert.

The test appends a **+567% move on 10 million shares** after `t` and asserts the
output is byte-identical. The poison is priced **inside** the $2–25 band on
purpose: an earlier draft used $30, which the price clause rejected on its own,
so the test passed without the truncation doing anything. That is the same fault
shape as the halves control that divided nothing — a test whose pass does not
depend on the thing it claims to test.

A companion test screens the same poisoned frame at a **later** `t` and requires
the answer to change, which shows the assertion constrains something real rather
than comparing two empty frames.

`stage1`'s existing guard greps its own source. It catches a named call and
nothing else. This is behavioural.

## 4. Two float-boundary defects, found by the boundary tests

Both real, both in the same direction — they **shrink the simulated universe
relative to the live one**, which is exactly the quantity this exercise measures.

| | |
|---|---|
| `100_000 * 0.552` | `= 55200.00000000001`, so a name with exactly 55,200 shares failed a threshold it exactly met |
| `(3.60/3.00 - 1) * 100` | `= 19.999999999999996`, so a name at exactly +20% failed the +20% clause |

Fixed by rounding the volume threshold to a whole share — volume is a count and
a fractional threshold has no meaning — and by `CHANGE_EPS = 1e-9` on the
**computed** change only. The price bounds get no epsilon: `close` is a raw
archive price and 2.0 and 25.0 are exactly representable.

Ties in the ranking break by symbol, always. Two names at the same 2-decimal
change is common, and an unstable sort makes the top-40 cut depend on row order
— which varies with pandas and with how the archive was concatenated. The leak
test would then fail intermittently and be dismissed as flaky.

## 5. Data on hand — and a correction to the scope doc

`E:\Databento\XNAS.BASIC` manifest, verified:

| | |
|---|---:|
| windowed `ohlcv-1m` 04:00–09:30 chunks | 550 |
| coverage | 2024-07-01 → 2026-09-09 |
| size | 1.79 GB |
| daily `ohlcv-1d` chunks (monthly) | 27, 0.19 GB |

**550 sessions, not the 864 the scope document assumed.** XNAS.BASIC begins
2024-07-01. Everything downstream — statistical power, the both-halves split,
how much of the holdout is reachable — should be read against 550.

## 6. What is still missing before §5's comparison can run

1. **The daily prior-close series**, symbol → previous regular-session close,
   from the `ohlcv-1d` archive. `screen_at` takes it; nothing builds it yet.
2. **The cadence.** `tv_feed` re-fetches and re-ranks through the session; a
   simulation that screens once at 04:30 measures a different mechanism. Needs
   `screen_series()` plus the HOT/WARM/COLD tiering, including *never drop a
   symbol with an open position*.
3. **Reconcile `screen.py`'s `stage2`** with the live `FILTERS` — the RVOL
   disagreement in §1 is still there in `screen.py` itself.
4. **Then §5**: re-run H0 and MCL on the simulated universe against the two
   numbers that bracket it, +$4.72/trade and −$9.81/trade, with both halves,
   drop-top-N, and the capture sensitivity.

The holdout stays clean for this. It was cut 2026-09-07 over the screened
universe and a screen built on 09-10 has not been fitted on it — still the first
measurement in this project for which that is true.
