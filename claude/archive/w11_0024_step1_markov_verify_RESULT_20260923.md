# W11-0024 · Step 1 — Markov / HMM regime-model claims: verified or debunked — RESULT

2026-09-23 · Opus/High session on W11-0024 (Project management chat) · Code read, both videos' transcripts read in full, the method re-run on SPY and Bitcoin.

## In plain terms

The claims don't hold up well enough to spend build time on. I ran the published code on SPY (2001–2026) and it made money, not the loss the video says the old version made. It turned $22,129 into $30,201 after costs, while simply holding SPY turned it into $124,902. I then rebuilt "Markov 2.0" three ways from the video's description, and all three **lost about 80% on SPY**. The video says that version made the S&P profitable. On Bitcoin, a "23x → nearly 60x" result is believable. My rebuilds landed anywhere from 22x to 211x depending on design choices the video doesn't specify. But **holding Bitcoin did 172x over the same ten years**, and the video never compares against that. Stripped of its maths, the published strategy is **the same trade on 94% of SPY days** as a one-line rule: "short if the last 20 days fell more than 5%, otherwise long". The Markov machinery adds nothing.

## Verdict: what Ben must decide

- **Debunked as a trading edge. Only partly true as statements.** One claim is right: overlapping 20-day windows fake "stickiness", and I confirm it below. The performance claims either don't reproduce (S&P) or are unfair comparisons (Bitcoin, no buy-and-hold benchmark, no costs, same-close fills).
- **Recommendation for step 2 (scope an HMM/Markov study): skip it.** Its condition ("if claims hold up") isn't met. The only piece that survives, a long-only 20-day trend filter, is ordinary time-series momentum, which TSMOM (W06) already covers properly.
- **Nothing to run, nothing to buy.** Ben decides at step 4 whether to close W11-0024. Step 3 (the mean-reversion cross-check) is independent of this result and can still go ahead.

## The claims, one by one

| # | Claim (Fable 5 video, 2026-06-13) | Finding |
| --- | --- | --- |
| C1 | Old version "lost money on the S&P over ~30 years" | **Not reproduced.** The public v1 code made money on SPY, 2001–2026: 1.36x after costs (+$8,072 on $22,129). It is still far behind buy-and-hold at 5.64x (+$102,773). |
| C2 | Fable 5's "Markov 2.0" makes the S&P profitable | **Not reproduced. The opposite happened.** All three rebuilds of the non-overlap fix lost money on SPY: 0.16x–0.20x net, a $17,646–$18,499 loss on $22,129 (drawdowns of 86–93%). Markov 2.0's own code isn't public, so this is a rebuild from the description. |
| C3 | Bitcoin 23x → "nearly 60x" | **Plausible but unfalsifiable, and misleading.** v1 over 10 years: 16.5x gross. The v2 rebuilds: 22x, 39x or 211x depending on unstated choices. Buy-and-hold over the same 10 years: **172x**. Costs cut v1's ending value by 45%, and filling one day later cuts it from 16.5x to 5.1x. |
| C4 | Overlapping windows inflate "stickiness" | **True.** If SPY's daily returns are shuffled randomly (so there is no real persistence at all), the overlapping method still shows bull→bull at 84%, which is higher than the real 72%. Measured on non-overlapping 20-day blocks, persistence is close to the base rate (bull 10.8% vs 11.3% base). |
| C5 | The fix was removing look-ahead bias, and that's what changed the numbers | **Doesn't match the public code.** v1 already refits the matrix only on past data. There was no look-ahead in the matrix to fix. What remains optimistic in v1 is the same-close fill. The HMM is fitted on the full history (look-ahead if it were used as a signal), but the HMM is never backtested. |

Two things the video gets wrong in the maths, for the record. A 2-day forecast is **not** 0.6 × 0.6 of the signal; it is the transition matrix squared. And long-range forecasts don't "get so small they're meaningless": they converge to the long-run mix, which for SPY is about 79% sideways.

## Results in dollars ($22,129 start; SPY 1bp and BTC 10bp cost per unit traded; negatives in brackets)

### SPY, 2001-01-31 → 2026-09-21 (price only, no dividends)

| Version | Gross | Net | Net P&L | Trades | Wins / losses | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| **Buy and hold** | 5.64x | 5.64x | **$102,773** | 1 | — | (56.5%) |
| v1 (published code) | 1.44x | 1.36x | $8,072 | 260 | 88 / 172 | (60.8%) |
| One-line rule, no Markov | 1.43x | 1.36x | $7,938 | 239 | 85 / 154 | (51.0%) |
| v2 rebuild: all 20-day pairs | 0.22x | 0.20x | **($17,646)** | 481 | 238 / 243 | (85.7%) |
| v2 rebuild: non-overlapping chain | 0.18x | 0.17x | ($18,279) | 138 | 79 / 59 | (87.2%) |
| v2 rebuild: rebalance every 20 days | 0.17x | 0.16x | ($18,499) | 72 | 35 / 37 | (93.2%) |
| v1 long-only (flat instead of short) | 3.53x | 3.43x | $53,873 | 131 | 56 / 75 | (45.3%) |

- v1's 15% of days short turned $1 into $0.41. The whole loss against holding comes from shorting a rising market.
- Last 10 years (2016–2026): v1 +$9,417 vs buy-and-hold +$56,673. The one-line rule gives the identical result, trade for trade.

**Why v2 loses on SPY:** at a 20-day horizon, the chance of sideways → bear (8.9%) versus sideways → bull (8.7%) is a coin flip. SPY is "sideways" 79% of the time, so v2 ends up **short on 100% of sideways days**, which means short in most of a rising market.

### Bitcoin, 10 years to 2026-05-22

| Version | Gross | Net | Net P&L | Trades | Wins / losses | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| **Buy and hold** | 172.5x | 172.5x | **$3,794,849** | 1 | — | (83.8%) |
| v1 (published code) | 16.5x | 9.2x | $180,555 | 296 | 93 / 203 | (74.9%) |
| v1, filled one day later | 5.1x | 2.9x | $40,830 | 296 | 122 / 174 | (86.3%) |
| One-line rule, no Markov | 24.8x | 14.4x | $296,424 | 273 | 86 / 187 | (74.9%) |
| v2 rebuild: all 20-day pairs | 22.4x | 13.0x | $265,854 | 271 | 85 / 186 | (76.1%) |
| v2 rebuild: non-overlapping chain | 39.0x | 36.7x | $790,391 | 31 | 13 / 18 | (89.0%) |
| v2 rebuild: rebalance every 20 days | 210.9x | 183.9x | $4,047,294 | 69 | 30 / 39 | (67.4%) |
| v1 long-only | 140.2x | 104.1x | $2,282,432 | 149 | 53 / 96 | (69.0%) |

- The rebuild that beats holding (rebalance every 20 days) is **one of three equally valid readings** of the video. The same variant loses 84% on SPY. Choosing it after seeing this table would be choosing the luckiest result.
- v1's short days (34%) turned $1 into $0.12. The long days made all the money.
- Sample v1 trades (most recent): Short 2026-01-29 +18.3%; Long 2026-02-25 (1.6%); Short 2026-02-28 (3.1%); Long 2026-03-02 (2.9%); Short 2026-04-02 (7.4%); Long 2026-04-07 +6.3%.

### How often each version takes the same position as the one-line rule

SPY: v1 **93.5%** of days (100% over the last 10 years). BTC: v1 88.8%, v2 (all pairs) 99.0%.

## What survives

A **long-only 20-day trend filter** (be in when the market isn't down more than 5% over 20 days, otherwise stay out) cut SPY's drawdown from 56% to 45% at the cost of about 2 points of annual return, with the same Sharpe (0.42 vs 0.45). On Bitcoin it matched holding on Sharpe (1.17 vs 1.10) with a smaller ending value (104x vs 172x net). That is textbook time-series momentum, with nothing Markov about it. W06 (TSMOM) already tests that idea on futures with proper registration.

## Next steps (board ids)

- **W11-0024 subitem 1:** Done (this doc).
- **W11-0024 subitem 2 (HMM/Markov study):** recommend skip, because its condition isn't met. Ben confirms at step 4.
- **W11-0024 subitem 3 (mean-reversion cross-check):** unaffected; Project management chat, Sonnet/Low.
- **W11-0024 subitem 4:** Ben decides (suggested: close W11-0024; log the Markov method as "don't re-propose").

### Token recommendation (rule 9)

- Step 2: don't run it. That saves a Sonnet/Medium session.
- Step 3: Sonnet/Low is right. It is a read-and-compare against `/areas/mean-reversion-strategy.md` and the video-4 claims.
- Step 4: Ben, or Sonnet/Low to write up his decision. Running steps 3 and 4 in one session is cheapest.

## Method

- **Claims:** both Lewis Jackson transcripts read in full through TubeAlfred ("I Re-Built A Quant Trading Strategy With Fable 5", 21:11, 662 caption segments; "I Re-Created A Quant Trading Strategy With Claude Code", 27:15, 770 segments), plus both video descriptions.
- **v1 code:** `github.com/jackson-video-resources/markov-hedge-fund-method` at commit fe24cf9 (2026-05-20). `scripts/markov_regime.py` was imported unmodified. My position series reproduces its published walk-forward Sharpe exactly (SPY 0.1702, BTC 0.9869).
- **v2 ("Markov 2.0"):** not public; the prompt sits behind the ZeroOne Skool classroom. Rebuilt three ways from the video's own description ("wait until there's no overlap… 20 more days"): (a) transitions from state[t−20] to state[t] on every day; (b) the same, sampled every 20th day only; (c) (a) with the position changed only every 20 days. All are walk-forward, with a 252-day warm-up, and signal = sign(P(bull) − P(bear)).
- **Scoring:** the position decided at close t earns close t → t+1 (the published convention), plus a lag-1 check. Costs are charged per unit of position change. Shorts pay no borrow or funding. Sharpe is annualised at 252 (SPY) and 365 (BTC).
- **Data:** SPY raw daily close 2000-01-03 → 2026-03-20 (GitHub willhjw/big_movers), stitched to 2023-09-19 → 2026-09-22 (GitHub babaros2555-del/market-data, a yfinance mirror). The 628 overlapping days agree to within 0.03%. BTC is Coin Metrics PriceUSD 2010-07-18 → 2026-05-23 (GitHub coinmetrics/data).
- Script: `w11_0024_markov_verify.py`. Raw report: `claude/raw/w11_0024_markov_verify_report_20260923.txt`.

## Caveats

- **Markov 2.0 was rebuilt, not run.** Its "enhanced states" option is never defined in the video. If the gated prompt differs materially, C2 and C3 could land differently. But the rebuilds span the plausible readings, and they disagree with each other by 10x on BTC, which is itself the finding.
- **SPY series is price-only (no dividends) and starts in 2000, not 1993.** Dividends add about 1.5–2% a year to buy-and-hold and the long days, and cost the short days. Adding them makes v1 and v2 look *worse* against holding, not better.
- **The workspace can't reach Yahoo, IBKR or Ben's D:\Trading data this session**, so the data are GitHub mirrors. They were cross-checked against each other but not against IBKR.
- **Bitcoin shorting has real funding and borrow costs** that aren't charged here. They would lower every long/short BTC figure further.
- **The video's own backtest windows and costs are never stated,** so "23x" and "60x" can't be pinned to a date range.

## Sources

- Lewis Jackson, "I Re-Built A Quant Trading Strategy With Fable 5": https://www.youtube.com/watch?v=Z-hU97WO30I
- Lewis Jackson, "I Re-Created A Quant Trading Strategy With Claude Code": https://www.youtube.com/watch?v=ZVMTeDBmSrI
- Published v1 code: https://github.com/jackson-video-resources/markov-hedge-fund-method
- Coin Metrics community data: https://github.com/coinmetrics/data
- SPY history mirrors: https://github.com/willhjw/big_movers · https://github.com/babaros2555-del/market-data
