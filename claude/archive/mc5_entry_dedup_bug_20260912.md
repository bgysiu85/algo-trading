# LIVE BUG: one MC5 signal could open five positions — 2026-09-12

Found while answering "did the trail stop fail on TNON?" Evidence:
`var/fills/mcl_fills_20260911.csv`. Fixed in `79567d9`, bundle `20260912j`.

## The trail stop did not fail

```
07:47:25  SELL trailing_stop  level 8.7305  fill 8.67  entry 7.75  +$90.62 (+11.9%)
07:47:25  BUY  entry_signal   ref_close 7.90  bid 8.62/ask 8.67  limit 8.69  FILL 8.69
07:48:23  SELL trailing_stop  level 8.3030  fill 8.11  entry 8.69  -$59.38 (-6.7%)
07:48:23  BUY  entry_signal   ref_close 7.90  FILL 8.20
07:56:31  SELL trailing_stop  level 7.8375  fill 7.80  entry 8.20  -$41.38 (-4.9%)
```

The trail worked exactly as configured. MC5 sold a +11.9% winner and **bought
back in the same second, two cents higher**, on a signal whose reference close
was **7.90** — paying 8.69, **10% above the price the signal was based on**. The
trail level it inherited (8.303) was already 4.4% below the entry, because the
trail tracks the peak and the peak had already happened. The position was
underwater against its own stop the instant it opened.

Net over the three: **+90.62 − 59.38 − 41.38 = −$10.14.** The winner was given
back in full.

## The cause

`brokers/ibkr/trader.py` deduped entries with:

```python
if st.last_bar_ts == last_ts:   # last_ts = df.index[-1], the last 1-MINUTE row
    return
```

MC5's signal is computed on the last complete **5-minute bucket**
(`mc5.last_closed_bucket`). Inside one bucket the 1-minute frame advances every
minute while the signal does not — so the guard never fired, and the same
signal re-entered every minute at whatever the market had moved to.

**MCL was unaffected**: for a 1-minute strategy the signal bar *is* the frame's
last row, which is precisely why the guard looked correct for three sessions.

This is the project's recurring shape again: **a guard whose key is not the thing
it guards**, and **two values that look comparable and are not**.

## The evidence, 2026-09-11

| | |
|---|---|
| entries | 48 |
| distinct signal bars | 29 |
| entries reusing an already-traded bar | **19 (40%)** |
| bars used more than once | 10 |

```
MC5 TNON  bucket close 7.51  -> bought 7.22, 7.04, 6.94, 6.98, 6.96  (5 minutes)
MC5 LBGJ  bucket close 2.78  -> bought 2.68, 2.62, 2.68, 2.67
MC5 TNON  bucket close 6.63  -> bought 6.20, 6.28, 6.22, 6.20
MC5 FTFT  bucket close 2.461 -> bought 2.41, 2.33, 2.27
MC5 TNON  bucket close 7.90  -> bought 8.69, 8.20
```

Every group is five consecutive minutes or fewer — one bucket.

Session P/L, 48 round trips, **net −$156.91**:

| | n | net | median hold | win |
|---|---:|---:|---:|---:|
| MC5 | 43 | (203.03) | 2.1 min | 14% |
| MCL | 5 | 46.12 | 24.3 min | 60% |

- **18 of 48 trades held under one minute**, and they lost **−$137.67** — 88% of
  the day's loss.
- 11 entries fired within 5 seconds of exiting the same name: **−$117.10**
  (−$10.65/trade) against **+$0.54/trade** for fresh entries.

## The fix

`Signals` now carries `bar_ts` — the bar the strategy actually evaluated — and
the trader dedupes on that. The adapter's design principle is that *the trader
never learns what a 5-minute bar is*; that is right, and it is exactly why the
signal must hand the trader its own bar. A caller that cannot know the bar size
cannot derive the bar.

A strategy omitting `bar_ts` falls back to the old key. `tests/brokers/
test_entry_dedup.py` asserts (a) no shipped adapter relies on that fallback,
(b) MC5's `bar_ts` differs from the frame's last row, (c) it is stable across
the minutes inside a bucket, and (d) — the vacuous-guard — that the **old** key
would have admitted all five. 1,785 passed, 2 skipped.

**Not a strategy change.** No rule, threshold or parameter moved.

## What this does NOT license

- **It does not say MC5 is profitable once fixed.** It says one session lost
  $137.67 to sub-minute churn that could not have been intended. The backtest
  never had this bug — `backtest_session` evaluates each bucket once — so every
  published MC5 figure was computed on the *correct* behaviour, and none of them
  showed a profit either.
- **n = 1 session.** The 40% figure is 2026-09-11. The other fill logs
  (09-02, 09-03, 09-08, 09-09, 09-10) are on disk and have not been counted.
- **It does not explain the live/backtest divergence.** If anything it widens
  the puzzle: live was running a *worse* rule than the backtest, so the backtest
  should have been the optimistic one, and on MCL — which never had this bug —
  live still disagrees with simulation about the shape of the deficit.
