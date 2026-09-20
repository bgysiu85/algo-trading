# ORB on liquid "stocks in play": data pre-flight (2026-09-17)

This is the ORB chat's new line, following the close of ORB on the small-cap PIT universe (`orb_pit_RESULT_20260917.md`). **No P/L exists yet.** This document records the tape choice and the rules to be registered. All of it was measured before any registration or run.

## Rules, verified from the full paper

Source: Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy for the U.S. Equity Market" (SSRN 4729284), read in full.

**Universe**
- Opening price above $5.
- Average volume over the prior 14 days of at least 1,000,000 shares.
- ATR (average true range) over the prior 14 days above $0.50.

**Relative volume (RVOL)**
- `RelativeVolume(t, j) = ORVolume(t, j) / (1/14 × Σ ORVolume over the prior 14 days)`, where ORVolume is the stock's volume in the 5-minute opening range.
- RVOL must be at least 100%. Trade the **top 20** stocks by RVOL.

**Entry**
- Direction comes from the first 5-minute candle.
- Bullish candle: a buy stop order at its high.
- Bearish candle: a sell stop order at its low.
- Doji (open equals close): no order.

**Stop loss and exit**
- A stop at a **10% ATR distance from the executed entry price**. This settles the conflict: QuantConnect's write-up of 1.5 is wrong.
- Otherwise the position is closed at 16:00 ET.

**Sizing and costs**
- Risk 1% of capital per position, with 4× maximum leverage and $25,000 starting capital.
- Commission of $0.0035/share and nothing else.
- Data from IQFeed.
- Sample from 2016-01-01 to 2023-12-31.

**Paper results (Tables 2 and 3)**

| | IRR | Sharpe | MDD |
|---|---:|---:|---:|
| ORB base (no RVOL) | 3.2% | 0.48 | 13% |
| ORB + RVOL, 5-minute range | 41.6% | 2.81 | 12% |
| ORB + RVOL, 15-minute range | 17.4% | 1.43 | |
| ORB + RVOL, 30-minute range | 2.3% | 0.21 | |
| ORB + RVOL, 60-minute range | 4.1% | 0.40 | |

**What this means for our test**

- **The stop is very tight.** 10% of a $0.50–$3 ATR is $0.05–$0.30. With a ~1¢ spread, one tick of slippage on each side of both the entry and the stop is a large share of the risk. The cost model decides this test more than any other choice.
- **Our sample is 2024-07 → 2026-09.** That is entirely after the paper's sample ended, so this is an out-of-sample test of a published rule. It is the strongest design this project has had.

## Tape: which dataset can carry the selection rule

The RVOL ranking is the whole claimed edge, so the tape has to rank stocks the way consolidated volume would. I measured this on daily bars already on disk, 2025-03 to 2025-05. The sample is the 1,655 stocks that pass the price and volume filters, compared against EQUS.SUMMARY consolidated volume.

"Capture" is the share of consolidated volume each tape sees. CV is the coefficient of variation (standard deviation ÷ mean) of each stock's day-to-day capture.

| tape | capture p10 / p50 / p90 | per-stock CV (p50) | daily-RVOL rank corr vs consolidated | top-20 overlap per day (p50 / p10) |
|---|---|---|---|---|
| **XNAS.BASIC** | 0.47 / **0.56** / 0.93 | 0.11 | **0.95** | **16 / 14** |
| XNAS.ITCH | 0.08 / 0.12 / 0.37 | 0.21 | 0.81 | 12 / 9 |
| EQUS.MINI | 0.05 / 0.06 / 0.08 | 0.24 | 0.78 | 12 / 9 |

**Decision, to be registered**

- **Minute bars on XNAS.BASIC.** ITCH and MINI pick a materially different top 20.
- **Price and average-volume filters from EQUS.SUMMARY.**
- **ATR(14) from BASIC's own RTH minute bars.** Daily bars include extended hours, which would widen the ATR and therefore the stop.
- **BASIC is clean in RTH:** 0.40 spike bars per 10,000.

**Known limits, to be stated in the registration**

1. **The rank check used daily RVOL, not first-5-minute RVOL.** The opening-range version cannot be checked without consolidated minute bars.
2. **BASIC does not carry the NYSE opening auction.** For NYSE-listed stocks this cuts ORVolume in both the numerator and the 14-day denominator, so the ratio is mostly preserved. That is not proven.

## Data on disk vs needed

**On disk**
- EQUS.SUMMARY and XNAS.BASIC `ohlcv-1d`, from 2024-07.
- XNAS.BASIC `ohlcv-1m`, only for 04:00–09:30 and 15:55–16:05.
- XNAS.ITCH `ohlcv-1m` for 09:30–16:00. Another chat is pulling this now and it is not the tape chosen.

**Needed**
- XNAS.BASIC `ohlcv-1m` for **09:30–16:00, all symbols, 2024-07-01 → 2026-09-16**.

## Next

1. Price the BASIC RTH pull.
2. Commit `docs/research/REGISTERED_orb_sip.md` before anything runs on the data. It will cover:
   - the cost model, at three levels
   - long and short sides reported separately
   - a $5 floor replacing the $2–20 price band
   - the §11 criteria
   - a prediction
3. Build on `strategy/orb/`, then pull and run.
