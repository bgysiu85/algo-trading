> **ARCHIVED 2026-09-08.** An early MCL parameter test, rejected; the shipped config is in `PROGRAM_INDEX.md` §2.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

> **Stale figures — the fill-model correction.** Every P/L number below predates
> the 2026-09-05 fix to gap-through fills and peak-seeding, and is overstated
> because of it. Applied to VW9 that correction cost roughly 73% of its
> headline; MCL went +$1,567 → +$161 and MC5 +$20,156 → −$400, on identical
> trades.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check.** Measured on a fuller tape
> that includes off-exchange prints, the backtests charge ~$2.00 per 100-share
> round trip against a real ~$1.00 — they are slightly *conservative* on
> slippage, not wrong. See `execution_cost_measured.md`.
>
> So: overstated by the fill-model correction, and by that alone. The reasoning
> and the decisions recorded here stand.

# Entry relaxation backtest — V9 rejected

2026-09-03. Second attempt at improving the entry after the arming window failed.

**Changes tested (both at once):**
1. Drop `MACD > 0`; require only `MACD > signal`.
2. Drop the 3× volume-vs-previous-bar rule. Floor becomes
   `prevVol >= max(60-bar avg × 0.5, 5000)`.

**Verdict: rejected.** Nearly 4× the trades for 28% less money.

## Result

Both measured today on the same data and the same 21 names.

| | Trades | Net | Win rate | $/trade | Profitable names |
|---|---|---|---|---|---|
| **V7** | 51 | **+$890.56** | **31.4%** | **+$17.46** | 9/21 |
| **V9** | 192 | +$639.73 | 27.1% | +$3.33 | 9/21 |

Expectancy fell from $17.46 to **$3.33 per trade** — an 81% collapse. At that
level the strategy is well inside the noise of real pre-market friction: the
measured spread on 2026-09-02 was 0.26–1.57%, which on a $5 stock is $1.30–$7.85
per round trip on 100 shares. **V9's average trade does not clear its own spread.**

## Per-ticker

| Ticker | V7 tr | V7 net | V9 tr | V9 net | delta |
|---|---|---|---|---|---|
| WETO | 6 | −17 | 12 | +59 | +76 |
| MOVE | 2 | +60 | 4 | +114 | +54 |
| AEHL | 3 | +60 | 17 | −21 | −81 |
| XAIR | 1 | −32 | 2 | −42 | −10 |
| XPON | 4 | −36 | 4 | −19 | +17 |
| QNRX | 3 | −45 | 16 | −155 | **−110** |
| XLAB | 2 | +180 | 8 | +116 | −64 |
| PPCB | 1 | −14 | 2 | −14 | 0 |
| YMT | 1 | −2 | 0 | 0 | +2 |
| VCIG | 2 | +6 | 3 | +158 | **+152** |
| AMIX | 1 | +19 | 2 | −53 | −72 |
| NEXR | 1 | +49 | 4 | −91 | **−140** |
| DAIC | 3 | −44 | 21 | −73 | −29 |
| SDOT | 3 | −99 | 5 | +80 | **+179** |
| WVVIP | 3 | +367 | 14 | +570 | **+203** |
| USDE | 2 | −30 | 4 | −37 | −7 |
| OLOX | 2 | −7 | 1 | −4 | +3 |
| SUGP | 2 | −22 | 30 | −179 | **−157** |
| JUNS | 3 | −76 | 7 | +101 | **+177** |
| ADXN | 3 | +304 | 15 | +121 | **−183** |
| SGLY | 3 | +270 | 21 | +9 | **−261** |

Nine names move by more than $100, in both directions. That is not an improvement
signal — it is variance from tripling the trade count.

**SUGP is the clearest illustration:** 2 trades → **30 trades**, 2 wins and 28
losses, −$179. With the floor at `max(avg×0.5, 5000)` and no surge requirement,
246 of its 617 session bars cleared the floor and the strategy simply traded
continuously.

## Concentration got worse again

| Drop top N | V7 | V9 |
|---|---|---|
| 1 | +$524 | +$70 |
| 2 | +$220 | **−$88** |
| 3 | −$50 | −$209 |

V7 survives losing its two best names. V9 does not survive losing **two**. Same
failure mode as the arming window.

## What this tells us, taken with the previous test

Three entry configurations have now been measured on identical data:

| Config | Trades | Net | $/trade | Survives dropping 2 names |
|---|---|---|---|---|
| **V7** (3× surge, MACD > 0) | 51 | +$891 | **+$17.46** | **yes (+$220)** |
| V8 (5-bar arming window) | 89 | +$780 | +$8.76 | no (−$3) |
| V9 (no surge, MACD cross only) | 192 | +$640 | +$3.33 | no (−$88) |

**A clean monotonic relationship: every relaxation of the entry increases trade
count and decreases both expectancy and robustness.** Trades, expectancy and
survivability move together in the same direction across three independent
changes. That is a real pattern, not a coincidence of one test.

The implication is uncomfortable but clear: **the restrictiveness of V7's entry
is doing the work, not the specific indicators.** The 3× surge and the `MACD > 0`
requirement are not well-motivated signals that happen to be strict — their
strictness *is* the signal. They admit roughly 51 trades from ~5,000 session bars,
and that scarcity is what produces a positive expectancy.

This also means further loosening is not worth testing. The direction has been
established three times.

## What is actually left

V7 stands, but its own numbers are the problem, not its entry rules:

- **+$891 over 51 trades, but −$50 without its top 3 names.** Two-thirds of the
  profit sits in WVVIP, ADXN and SGLY.
- Those 21 names were chosen **because they ran**. A strategy whose edge lives in
  3 of 21 hindsight-selected names has not been shown to have one.

So the remaining questions are not about entry conditions:

1. **Does the edge survive out of sample?** Only forward testing on
   contemporaneous scanner picks answers this, and it is already running.
2. **Does it survive equal-weighting by name** rather than letting three names
   dominate? Cheap to compute from existing per-ticker data.
3. **Does it survive measured friction?** The paper fill log gives the number;
   V7's $17.46/trade has roughly $5–8 of headroom against observed spreads,
   which is thin but not obviously fatal.

Question 1 is the one that matters. No amount of further parameter work on 21
hindsight-picked names can answer it.

## Housekeeping — DONE 2026-09-03

The saved Pine script has been **restored to V7** and verified:

    requireMacdPos = true      MACD > 0 required
    useVolMultiple = true      3x surge required
    armBars        = 0         surge must land on the confirmation bar
    minAbsFloor    = 0         pure relative floor
    dateMode       = "Off"     every session, for live/forward use

Two additions made at the same time:

- The diagnostics table prints **`Config | V7`**, or **`MODIFIED — not V7`** if
  any of those four toggles drifts off spec. A stray experimental setting can no
  longer ride quietly into a live session.
- The three `alert()` calls were restored. They had been stripped during testing,
  and without them an "Any alert() function call" alert fires nothing.

All experimental variants remain reachable from the same script via their
toggles, so any of these tests can be reproduced without a rewrite.
