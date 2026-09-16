# REGISTERED — MCL-PB v6: v3 on five-minute bars

Ben, after v5 closed the line on one-minute bars: *"before going with your
recommendation, I would like to try running this strategy on a 5 min
timeframe."* Committed before it runs.

## 1. The rule

**v3 exactly**, with every bar-denominated parameter kept in bars and the bars
five minutes long, resampled from the same 1-minute tape by
`common.indicators.resample_bars` (left-labelled, empty buckets dropped — the
convention MC5 uses):

| parameter | v3 (1m) | v6 (5m) |
|---|---|---|
| swing high, two red bars, bounce-top level | same | same, on 5m bars |
| break qualifies at the bar's close: close > level, volume > SMA20 (prior 20 bars), MACD 12/26/9 > signal | same | same, 20 bars = 100 min, MACD on 5m closes |
| entry | close + 1 tick | close + 1 tick |
| green hold | 3 bars = 3 min | 3 bars = 15 min |
| level expiry | 60 bars from the peak bar | 60 bars = the whole session |
| trail | 5%, MCL's engine | 5%, MCL's engine on 5m bars |
| session, floor, band, size, costs | as v3 | as v3; the floor tests the 5m bar's START, one bar coarser and in the safe direction, as MC5 does |

No decisive-close condition (v5, NOTHING), no structure stop (v4, NOTHING).

## 2. Cells and controls

| cell | bars | green hold |
|---|---|---|
| **PB3-5m-g3** (primary) | 5m | 3 |
| PB3-5m-g0 | 5m | none |
| PB3-g3 | 1m | 3 — v3, for the timeframe comparison |

Controls, same run, same universe and floor: **MCL** (1m, as every version) and
**MC5** (the project's 5-minute strategy, `strategy/mc5`, published point-in-time
figure (13.50)/trade on 6,170 symbol-days).

## 3. Readings

1. PB3-5m-g3 against MCL: v1 §3 unchanged.
2. PB3-5m-g3 against MC5: same rule form (better per trade in both halves by at
   least $4.26, and better total in both halves) — the like-for-like control on
   this timeframe.
3. PB3-5m-g3 against PB3-g3: reported, not registered — different bar counts
   make it a description of the timeframe, not a test of the rule.

Expectation, written first: fewer trades (a 5-minute pullback is rarer), a
larger fill premium (the close of a 5-minute break bar is further from the
level), and the same sign. `holdout.json` untouched.
