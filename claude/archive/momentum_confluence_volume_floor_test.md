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

# Volume floor & timeframe tests

Runs of 2026-09-01. Shared rules: pre-market only, entry = MACD > signal & > 0 · MFI rising ·
RSI rising · volume ≥ 3× previous bar · **floor**; exit = after apex ANY of MACD/MFI/RSI turning
down, 5% trailing stop off the high since entry, flat at 09:30. 21 tickers, Aug 2026.

**SGLY was remapped from 21 Aug to 20 + 26 Aug** partway through. Headline comparisons are stated
**ex-SGLY** so the universe is identical across runs; SGLY is reported separately.

## Floor definitions

| Floor | Definition |
|---|---|
| Shares | previous bar ≥ 6,000 shares |
| Dollar | previous bar ≥ $20,000 traded |
| **Relative** | previous bar ≥ 50% of a **trailing** 60-bar average volume, lagged one bar |

A session median would use bars that had not happened yet — lookahead. Trailing average only.

## Full comparison (ex-SGLY)

| Config | TF | Floor | Lengths | Trades | Net P/L | Win rate | **Avg $/trade** |
|---|---|---|---|---|---|---|---|
| **V4** | 1 min | none | ×1 | 99 | **+$938** | 27.2% | $9.47 |
| **V7** | 1 min | **relative** | ×1 | **47** | +$654 | 29.8% | **$13.91** |
| Control A | 30 s | none | ×1 | 159 | +$458 | 28.6% | $2.88 |
| Shares 6k | 30 s | shares | ×1 | 40 | +$204 | 35.0% | $5.10 |
| Dollar $20k | 30 s | dollar | ×1 | 50 | +$357 | 36.0% | $7.14 |
| Relative | 30 s | relative | ×1 | 69 | +$522 | 34.8% | $7.57 |
| Control B | 30 s | relative | ×2 | 54 | +$351 | 34.4% | $6.50 |

**V7 on the current universe (with SGLY on 20 + 26 Aug): 50 trades, +$924, 32.0% win rate,
$18.47 per trade.**

## V7 per-ticker

| Ticker | Trades | Net |
|---|---|---|
| WETO | 5 | +$20 |
| MOVE | 2 | +$60 |
| AEHL | 3 | +$52 |
| XAIR | 1 | −$32 |
| XPON | 4 | −$36 |
| QNRX | 3 | −$45 |
| XLAB | 2 | **+$180** |
| PPCB | 1 | −$14 |
| YMT | 1 | −$2 |
| VCIG | 2 | +$6 |
| AMIX | 1 | +$19 |
| NEXR | 1 | +$49 |
| DAIC | 3 | −$44 |
| SDOT | 3 | −$99 |
| WVVIP | 3 | **+$367** |
| USDE | 2 | −$30 |
| OLOX | 2 | −$3 |
| SUGP | 2 | −$22 |
| JUNS | 3 | −$76 |
| ADXN | 3 | **+$304** |
| SGLY | 3 | **+$270** |
| **TOTAL** | **50** | **+$924** |

10 profitable / 11 losing — same split as V4.

## Verdict: it depends on what you optimise for, and slippage decides it

The relative floor at 1-minute is **not** the clean win the 30-second results suggested.

- It **halves trade count** (99 → 47 ex-SGLY) and **raises per-trade expectancy 47%**
  ($9.47 → $13.91).
- But **total net falls** (+$938 → +$654) and **win rate barely moves** (27.2% → 29.8%),
  unlike on 30s where the floor lifted win rate from 28.6% to 34.8%.
- **Concentration gets worse.** V7 survives dropping only its top 2 names before turning
  negative (WVVIP +$367, ADXN +$304, SGLY +$270 total +$941; everything else −$17).
  V4 survived dropping 3.

The floor's value scales with how much noise there is to remove. At 30 seconds there was a lot;
at 1 minute there is much less, so it mostly removes trades roughly in proportion — some good,
some bad.

### The slippage crossover — this is the decisive number

The backtest models $0.005/share commission and 1 tick of slippage. Real pre-market friction on a
$2–20 low-float name is far higher: a 2–5 cent spread is **$4–$10 round trip on 100 shares**.

Setting V4 and V7 equal:

> 938 − 99c = 654 − 47c → **c ≈ $5.46**

If real round-trip friction beyond what is modelled exceeds about **$5.46 per trade**, V7 beats
V4 on total P/L as well as per trade. Given realistic pre-market spreads on this universe, that
threshold is very likely already crossed.

**Recommendation: V7 (1-minute, relative volume floor) is the version to carry forward** — not
because its gross backtest number is highest, but because half the trades at 47% higher
expectancy is far more robust to the transaction costs this backtest does not model.

## SGLY remap (20 + 26 Aug)

| Config | Trades | Net |
|---|---|---|
| 1 min, relative, ×1 (V7) | 3 | +$270 |
| 30 s, no floor, ×1 | 16 | +$118 |
| 30 s, relative, ×2 | 7 | +$92 |

All positive, and much better than its old 21 Aug basis (0 trades / −$7).

## Settled questions

1. **Relative floor beats absolute floors.** Share and dollar floors vary 200×+ across names and
   act as ticker screens; the relative floor sits at 36–67% for every name and filters within
   each stock. It excluded 1 of 21 tickers versus 8 for the share floor.
2. **30 seconds is genuinely worse than 1 minute** — not mis-parameterised. Doubling every period
   to match 1-minute wall-clock made it worse (+$351 vs +$522), and 1-minute beats every 30s
   config on both total and per-trade.
3. **The floor is worth having at both timeframes**, but for different reasons: noise removal at
   30s (win rate +6pts), trade-count reduction at 1 minute (expectancy +47%).

## Caveats that still stand — and the real blocker

- 21 names chosen *because they ran*. A best case, not a fair sample.
- 1.7–3.4 bar average holds.
- **Execution model unresolved.** Fills at bar close (market-style) and a trailing stop, neither
  of which IBKR accepts pre-market for US stocks. This is now the binding constraint: no further
  parameter tuning is worth much until entries and exits are modelled as marketable limit orders
  with an explicit no-fill assumption. See `claude/momentum_confluence_strategy.md`.
