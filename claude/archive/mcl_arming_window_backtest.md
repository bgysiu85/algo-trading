> **ARCHIVED 2026-09-08.** An early MCL parameter test, rejected; the shipped config is in `PROGRAM_INDEX.md` §2.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

> **Stale figures — the fill-model correction.** Every P/L number below predates
> the 2026-09-05 fix to gap-through fills and peak-seeding, and is overstated
> because of it: MCL's headline went +$1,567 → +$161 and MC5's +$20,156 →
> −$400, on identical trades.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check.** Measured on a fuller tape
> that includes off-exchange prints, the backtests charge ~$2.00 per 100-share
> round trip against a real ~$1.00 — they are slightly *conservative* on
> slippage, not wrong. See `execution_cost_measured.md`.
>
> So: overstated by the fill-model correction, and by that alone. The reasoning
> and the decisions recorded here stand.

# Arming-window backtest — the fix does not work

2026-09-03. Tests the change proposed after the JLHL diagnosis: let a 3× volume
burst **arm** the setup for N bars instead of requiring it on the same bar as the
MACD/MFI/RSI confirmation.

**Verdict: rejected.** More trades, less money, worse expectancy, worse
concentration. The diagnosis was right; the remedy is wrong.

## Result

Both configurations run today, on the same data, across the same 21 names.

| | Trades | Net | Win rate | $/trade | Profitable names |
|---|---|---|---|---|---|
| **armBars = 0** (V7) | 51 | **+$890.56** | 31.4% | **+$17.46** | 9/21 |
| **armBars = 5** | 89 | +$779.60 | 30.3% | +$8.76 | 8/21 |

Trade count rose **75%** while net P/L **fell**. Expectancy halved.

## Per-ticker

| Ticker | arm=0 trades | net | arm=5 trades | net | delta |
|---|---|---|---|---|---|
| WETO | 6 | −17 | 8 | −41 | −24 |
| MOVE | 2 | +60 | 3 | **+157** | **+97** |
| AEHL | 3 | +60 | 4 | +43 | −17 |
| XAIR | 1 | −32 | 1 | −32 | 0 |
| XPON | 4 | −36 | 7 | −47 | −11 |
| QNRX | 3 | −45 | 6 | **−174** | **−129** |
| XLAB | 2 | +180 | 3 | +211 | +31 |
| PPCB | 1 | −14 | 1 | −14 | 0 |
| YMT | 1 | −2 | 2 | −3 | −1 |
| VCIG | 2 | +6 | 3 | **+158** | **+152** |
| AMIX | 1 | +19 | 2 | +23 | +4 |
| NEXR | 1 | +49 | 2 | **−86** | **−135** |
| DAIC | 3 | −44 | 7 | −78 | −34 |
| SDOT | 3 | −99 | 5 | −164 | −65 |
| WVVIP | 3 | +367 | 7 | **+509** | **+142** |
| USDE | 2 | −30 | 2 | −19 | +11 |
| OLOX | 2 | −7 | 3 | −10 | −3 |
| SUGP | 2 | −22 | 5 | −25 | −3 |
| JUNS | 3 | −76 | 4 | −40 | +36 |
| ADXN | 3 | +304 | 6 | **+138** | **−166** |
| SGLY | 3 | +270 | 8 | +274 | +4 |

Five names move by more than $100 and they point in **both** directions
(+152 VCIG, +142 WVVIP against −166 ADXN, −135 NEXR, −129 QNRX). That is noise
from extra trades, not a systematic improvement.

## Concentration got worse, which matters more than the P/L

| Drop top N names | arm=0 | arm=5 |
|---|---|---|
| 1 | +$523.56 | +$270.60 |
| 2 | +$219.56 | **−$3.40** |
| 3 | −$50.44 | −$214.40 |

V7 survives losing its two best names. The arming window does not survive losing
**two**. It concentrates the result into fewer winners while adding losers — the
opposite of robustness.

## Why the fix failed

The JLHL diagnosis was correct: the volume rule and the trend confirmations are
structurally anti-correlated, and the rule held on only 7.6% of bars there.

But relaxing the timing did not surface *good* trades that timing had been
hiding. It admitted trades where the burst had already been and gone — entering
into the back half of a move rather than its ignition. `armBars=5` roughly
quintupled armed bars (e.g. SGLY 10 → 50, SUGP 27 → 128) and the extra entries
were, on balance, worse than the ones V7 already took.

**The 3× rule was not merely a timing filter. Its restrictiveness was doing real
work** — the same finding as the volume-floor test, where the floor's value was
trade-count reduction rather than noise removal.

## Validation of the test itself

`armBars = 0` reproduces V7 exactly by construction (armed only on the burst
bar). Confirmed against the recorded V7 per-ticker numbers:

- **Exact matches:** MOVE 2/+60, XAIR 1/−32, XPON 4/−36, QNRX 3/−45,
  XLAB 2/+180, WVVIP 3/+367, SGLY 3/+270
- **Drifted:** WETO 6/−17 vs recorded 5/+20, AEHL 3/+60 vs 3/+52

So the rewrite is faithful, and the drifted names reflect **changed 1-minute
history** since 2026-09-01, not a logic change. This is why the comparison uses a
freshly measured `armBars=0` baseline rather than the documented V7 table.

Aggregate today (51 / +$890.56 / 31.4%) is close to the recorded V7
(50 / +$924 / 32.0%), so the two runs describe the same strategy.

### A trap worth recording

Bare ticker symbols are unsafe in TradingView. `MOVE` resolves to **`TVC:MOVE`**,
the bond-volatility index, and produced a silent zero row that would have entered
the table as a legitimate result. Every symbol must carry its exchange prefix.

Also: `indicator_set_inputs` still returns `updated_inputs: {}` and does nothing.
Parameter changes require editing the source default and recompiling, which is
why this tested one arming length rather than a sweep.

## Where this leaves the strategy

The entry logic remains unimproved, and the honest position is that **V7 is still
the best version we have** — 51 trades, +$890, but with two-thirds of the profit
in three names and negative once those three are removed.

That concentration, not the entry timing, is the real problem. A strategy whose
edge lives in 3 of 21 hand-picked names is not yet demonstrated to have one.

Things worth trying next, roughly in order of expected value:

1. **Relax `MACD > 0` instead of the volume rule.** The V8 script already has a
   `requireMacdPos` toggle, untested. On JLHL, MACD was false through the entire
   06:05–06:21 move and only turned positive at 06:22 — it is the laggiest of the
   three confirmations and the likeliest single blocker.
2. **Test whether the strategy works at all without the concentration** — e.g.
   equal-weight by name rather than by trade, or cap per-name contribution.
3. **Forward testing on contemporaneous picks**, which remains the only fix for
   selection bias and is already running via the paper trader.

The arming window should not be carried forward. `armBars` stays in the script as
an input defaulting to 5 — **set it to 0 to restore V7 behaviour before any
further live use.**
