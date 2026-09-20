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

# Session window test — 04:00–09:30 vs 06:30–09:30

Run 2026-09-01. Identical rules either side; only the trading window changes.

**Rules (V7/V8):** 1-minute · pre-market · entry = MACD > signal & > 0 · MFI rising · RSI rising ·
volume ≥ 3× previous bar · previous bar ≥ 50% of trailing 60-bar average · exit = after apex ANY
of MACD/MFI/RSI turning down, 5% trailing stop off the high since entry, flat at window close ·
100 shares (or 40% equity) · $0.005/share · 1 tick slippage. 21 tickers, Aug 2026.

## Headline

| | V7 (04:00–09:30) | **V8 (06:30–09:30)** |
|---|---|---|
| Trades | 50 | **39** |
| Net P/L | +$924 | **+$66** |
| Win rate | 32.0% | **25.6%** |
| Avg $ / trade | $18.47 | **$1.68** |
| Profitable tickers | 10 / 21 | 7 / 21 |

**Narrowing the window removed 11 trades and $858 of profit — 93% of the strategy's P/L.**

## Where the $858 went

| Ticker | V7 | V8 | Δ |
|---|---|---|---|
| WVVIP | +$367 | −$4 | **−$371** |
| ADXN | +$304 | +$6 | **−$298** |
| SGLY | +$270 | −$7 | **−$277** |
| WETO | +$20 | +$14 | −$6 |
| SDOT | −$99 | −$48 | +$51 |
| QNRX | −$45 | −$17 | +$28 |
| USDE | −$30 | −$20 | +$10 |
| DAIC | −$44 | −$39 | +$5 |
| *(all others unchanged)* | | | |

The three biggest winners in the entire study — WVVIP, ADXN, SGLY — had **every one of their
winning trades before 06:30**. Together they lose $946. The losing tickers that improved give
back only about +$94.

**The strategy's entire edge in this sample lived in the 04:00–06:30 window.**

## V8 by date

| Date | Ticker | Trades | W/L | Net |
|---|---|---|---|---|
| **31 Aug** | WETO | 3 | 1/2 | +$14 |
| | MOVE | 2 | 1/1 | +$60 |
| | AEHL | 3 | 2/1 | +$52 |
| | XAIR | 1 | 0/1 | −$32 |
| | **subtotal** | **9** | **4/5** | **+$94** |
| **28 Aug** | QNRX | 2 | 0/2 | −$17 |
| | XLAB | 2 | 1/1 | +$180 |
| | **subtotal** | **4** | **1/3** | **+$163** |
| **27 Aug** | PPCB | 1 | 0/1 | −$14 |
| | YMT | 1 | 0/1 | −$2 |
| | **subtotal** | **2** | **0/2** | **−$16** |
| **26 Aug** | VCIG | 2 | 1/1 | +$6 |
| | AMIX | 1 | 1/0 | +$19 |
| | NEXR | 1 | 1/0 | +$49 |
| | DAIC | 2 | 0/2 | −$39 |
| | **subtotal** | **6** | **3/3** | **+$35** |
| **25 Aug** | WVVIP | 1 | 0/1 | −$4 |
| | USDE | 1 | 0/1 | −$20 |
| | OLOX | 2 | 0/2 | −$3 |
| | **subtotal** | **4** | **0/4** | **−$27** |
| **21 Aug** | JUNS | 3 | 0/3 | −$76 |
| | ADXN | 2 | 1/1 | +$6 |
| | **subtotal** | **5** | **1/4** | **−$70** |
| **Multi-session** | XPON (28+25) | 4 | 1/3 | −$36 |
| | SDOT (26+25) | 2 | 0/2 | −$48 |
| | SUGP (25+21) | 2 | 0/2 | −$22 |
| | SGLY (20+26) | 1 | 0/1 | −$7 |
| | **subtotal** | **9** | **1/8** | **−$113** |
| | **TOTAL** | **39** | **10/29** | **+$66** |

Only three of six single-date groups are now positive, versus five of six under V7. Without XLAB
(+$180) the whole thing is **−$114**.

## How to read this — the finding cuts both ways

**Against narrowing:** the early window is where these setups actually work. Low-float runners
make their initial catalyst-driven move in the 04:00–06:30 stretch, before the broader market
engages. Cutting it removes the move the strategy is built to catch.

**For narrowing:** 04:00–06:30 is also the thinnest, widest-spread part of the session — exactly
where this backtest's fill assumptions (entry at bar close, 1 tick of slippage) are least
believable. So the profit that just vanished was concentrated in the hours where the modelled
P/L is least trustworthy.

Both readings are consistent with the data. The honest conclusion is that **V7's +$924 was
largely an artifact of trading a window the backtest cannot model realistically**, and V8's +$66
is closer to what survives once you restrict to hours with a functioning book — though still on
21 hand-picked winners.

Also worth noting: the previous biggest single loss (SDOT −$51, entered 04:02, two minutes into
the old session, never traded above its entry) is gone under V8, which is a point in the narrow
window's favour.

## What this means for next steps

This strengthens the case that the **execution model is the binding constraint**, not the signal
rules. The gap between +$924 and +$66 is essentially a measure of how much of the "edge" depends
on hours where fills are fictional.

Recommended order:
1. **Rebuild fills as marketable limit orders with an explicit no-fill rate**, then re-run both
   windows. That will show which of the two is genuinely tradeable.
2. Only then decide the window. Choosing on backtest P/L alone would pick 04:00–09:30 for the
   wrong reason.
3. Everything still rests on 21 names chosen *because they ran*.
