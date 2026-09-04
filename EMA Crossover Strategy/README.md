# EMA Crossover Strategy

Two full-session (04:00-20:00 ET) EMA-based strategies, sibling to
`../MCL Strategy`'s pre-market (04:00-09:30 ET) momentum work. Specs live in
the Algo Trading Claude project:

- **E15** -- 15-minute, 9/20 EMA crossover + pullback. `claude/ema15_full_day_strategy_spec.md`
- **VW9** -- VWAP + 9 EMA, 5-minute and 15-minute. `claude/vw9_strategy_spec.md`

**Status as of this folder's creation: neither strategy's production module is
written yet.** Both specs say so explicitly ("Code not yet written") and both
end with the same instruction: run the pre-flight measurements in their §7/§8
*before* writing `strategies/e15.py` / `strategies/vw9.py`, because most of
each spec's parameters are uncalibrated guesses (E15: 6 of 13; VW9: 12 of 18)
and the whole approach is a **go/no-go** on sample size first.

## What's here right now

This folder currently holds VW9's §8.3 measurement -- "Setup counts": *how
many Setup A (VWAP reclaim) and Setup B (9 EMA retest) triggers fire per pair
per session, at 5-minute and 15-minute, before the §4.3 gates are applied.*
That count is the sample-size go/no-go the spec calls for before anything
else gets built.

| File | What |
|---|---|
| `indicators.py` | `ema`/`rma` (identical to `../MCL Strategy/mcl_strategy.py`), `atr`, `session_vwap`, `resample_bars` |
| `vw9_strategy.py` | Pure logic: the §3 regime gate (STRONG/WEAK_BULL/BEARISH) and §4.1/§4.2 Setup A/B detection, deliberately **without** the §4.3 gates |
| `data_ib.py` | Pulls full-session 1-minute bars from IB, caches to `bars_cache/`, resumable (needs `ib_async`) |
| `cache_io.py` | Pair-list and bar-cache reading, shared by `data_ib.py` and `vw9_setup_counts.py` -- kept free of the `ib_async` dependency so the analysis step runs anywhere pandas does |
| `vw9_setup_counts.py` | The §8.3 report itself: offline, reads the cache, resamples to 5m/15m, counts, flags the noise-trading threshold |
| `test_indicators.py`, `test_vw9_strategy.py` | Unit tests on hand-built bar sequences, verified before any real data is touched (24 tests, all passing) |

Not yet built: E15's own crossover-count measurement (its spec's §7 item 3 --
same idea, different rules), the §4.3 gates, §5 exits, §4.4 context levels, or
either strategy's production module. Those come after this go/no-go, per each
spec's own "Next, in order" section.

Reuses `../MCL Strategy/traded_pairs.json` (the same 407 symbol/date pairs as
V7/MC5) rather than duplicating it -- both specs' §1 say to, so E15/VW9 stay
comparable to the existing strategies on the same tape.

## Setup

Reuses `../MCL Strategy`'s virtual environment -- it already has `pandas` and
`ib_async`. Only `pytest` needs adding for the test suite:

```powershell
..\MCL Strategy\.venv\Scripts\pip install pytest
```

No new credentials: this only talks to IB Gateway on localhost, same as
everything in `../MCL Strategy`.

## Running

```powershell
# 1. Pull and cache full-session bars for all 407 pairs (needs IB Gateway
#    running on the paper port -- see ../MCL Strategy/README.md). Resumable;
#    Ctrl-C is safe. Expect a similar order of magnitude to mcl_backtest.py's
#    ~75 minutes, since it's paced by the same IB request cap.
..\MCL Strategy\.venv\Scripts\python.exe data_ib.py

# 2. Run the §8.3 measurement against the cache. No IB connection; safe to
#    re-run as often as needed while parameters are tuned -- the bars don't
#    change.
..\MCL Strategy\.venv\Scripts\python.exe vw9_setup_counts.py
```

A quick trial against the first 20 pairs, before committing to a full run:

```powershell
..\MCL Strategy\.venv\Scripts\python.exe data_ib.py --limit 20
..\MCL Strategy\.venv\Scripts\python.exe vw9_setup_counts.py --limit 20
```

`vw9_setup_counts.py` writes `setup_counts_trades.csv` -- every individual
trigger, with `entry_ref`/`structure_low` already computed. That's also the
raw material §8.4 (distributions) needs next, so it's kept rather than
discarded once the count is read.

## Tests

```powershell
..\MCL Strategy\.venv\Scripts\python.exe test_indicators.py
..\MCL Strategy\.venv\Scripts\python.exe test_vw9_strategy.py
```

`test_vw9_strategy.py` is the one worth reading before trusting the §8.3
numbers: it documents, with a worked scenario for each, why a reclaim needs
>= 2 bearish bars, why a pullback dies if it breaches VWAP or drops more than
1.5x ATR in one bar or runs past 6 bars, and why a retest is blocked if the
last session high was more than 10 bars ago. Every numeric scenario in it was
verified interactively (regime printed bar by bar) before being pinned into
an assertion, rather than hand-derived from the EMA/VWAP formulas -- that
stops being practical past a handful of bars.

## Why the pullback-control check can look strict

`vw9_strategy.py`'s ATR is `ta.rma`-based from bar 1, with no hard warm-up
gate (same soft convention `../MCL Strategy/mcl_strategy.py`'s RSI uses). On
a synthetic steep trend, EMA9 lags price by more than a realistic ATR would
allow a "controlled" pullback to cross -- see the comment on `impulse()` in
`test_vw9_strategy.py` for the concrete numbers. This is a property of the
spec's chosen thresholds interacting with trend steepness, not a bug; it's
also exactly the kind of thing §8.4's distributions (bars-to-trigger,
pullback depth in ATR) exist to characterise on real data before the
`PULLBACK_CTRL_ATR = 1.5` default is trusted.
