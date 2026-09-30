# W15-0032 · CHARTMARK-v1 (long) training backtest — RESULT (2026-09-30, Build & test chat)

**Board:** W15-0032 sub 4 (build) + sub 5 (backtest) · **Code:** `strategy/chartmark/` (commit 489891b) · **Raw:** `claude/raw/w15_0032_chartmark_long_backtest_20260930.txt` · **Pre-flight:** `claude/raw/w15_0032_chartmark_preflight_20260930.txt` · **Registration:** `docs/research/REGISTERED_chartmark_v1.md` incl. Amendment A · **Data:** CL 1H, 2010-06-06 → 2021-12-31, difference-back-adjusted, IBKR costs.

## In plain terms
Ben's chart-marked long method, coded exactly as registered, **loses money**. Over 11.5 years of 1-hour crude bars it took 2,670 trades (a win 41% of the time) and lost **($13,422)** per 1 MCL after IBKR costs; even before costs it is down ($3,867). It is negative in 11 of 12 years, both halves of the sample, and every one of the 27 neighbouring settings. It also does worse than a plain 20/10 Donchian channel (($3,412)) and worse than 85% of random in-session entries using the same exits. Registered criteria 5 and 6 fail, which **closes the study**. The holdout stays unspent.

## Verdict and what Ben must decide
**FAIL — criteria 5 and 6 close CHARTMARK-v1 (long).** No holdout was spent (`holdout_chartmark_v1.json` not written). Ben decides: (1) accept the close; (2) whether the short side (sub 8/9) is worth building given the same mechanical-fidelity issue below; (3) whether any new hypothesis is warranted — a new registration needs a reason that doesn't begin with this result.

## Headline (BASE, 1 MCL, mid friction, training)
| | |
|---|---|
| Trades / wins / losses | 2,670 / 1,095 / 1,575 |
| Gross | ($3,867) |
| Costs (IBKR, mid) | $9,554 |
| **Net** | **($13,422)** |
| Net at high friction | ($18,820) |
| Net, 1 CL, mid | ($105,447) |
| Average win / loss | $49 / ($43) |
| Largest loss · worst losing run · max drawdown | ($286) · 15 · $15,247 |
| Halves | ($10,655) / ($2,767) |

## The ten registered criteria
| # | Criterion | Result | Value |
|---|---|---|---|
| 1 | Net > $0 at mid | FAIL | ($13,422) |
| 2 | Both halves > $0 | FAIL | ($10,655) / ($2,767) |
| 3 | Drop-top-1 / top-2 years > $0 | FAIL | ($13,737) / ($13,701) |
| 4 | Bootstrap by year ≥ 95% | FAIL | 0.0% |
| 5 | Beats C1 on net and net per unit of volatility | FAIL | ($13,422) vs ($3,412) |
| 6 | Beats C3 p99 | FAIL | ($13,422) vs p99 ($2,808) |
| 7 | No year > 50% of net | FAIL | largest year 23% of a negative total |
| 8 | Net > $0 at high friction | FAIL | ($18,820) |
| 9 | ≥ 18 of 27 grid cells > $0 | FAIL | 0 of 27 |
| 10 | ≥ 150 trades | PASS | 2,670 |

## Net by year (BASE, 1 MCL, mid)
| Year | Trades | W/L | Gross | Costs | Net |
|---|---|---|---|---|---|
| 2010 | 132 | 67/65 | $417 | $474 | ($57) |
| 2011 | 230 | 90/140 | ($857) | $828 | ($1,686) |
| 2012 | 240 | 90/150 | ($1,612) | $857 | ($2,468) |
| 2013 | 226 | 90/136 | ($339) | $807 | ($1,146) |
| 2014 | 219 | 85/134 | ($1,259) | $779 | ($2,038) |
| 2015 | 223 | 79/144 | ($2,239) | $796 | ($3,036) |
| 2016 | 217 | 97/120 | $746 | $782 | ($36) |
| 2017 | 236 | 96/140 | $93 | $839 | ($746) |
| 2018 | 220 | 92/128 | $200 | $793 | ($593) |
| 2019 | 246 | 91/155 | ($890) | $881 | ($1,772) |
| 2020 | 231 | 101/130 | $669 | $828 | ($159) |
| 2021 | 250 | 117/133 | $1,204 | $889 | $316 |

## Controls
| | Trades | Net (1 MCL, mid) |
|---|---|---|
| C1 Donchian 20/10, long, session-filtered | 1,551 | ($3,412) (high ($6,624)) |
| C3 random entries, same count/year, same exits — p5 / p50 / p95 / p99 | 1,000 draws | ($15,143) / ($10,303) / ($4,833) / ($2,808) |
| CHARTMARK-v1 BASE | 2,670 | ($13,422) — beats 14.6% of C3 draws |
| C2 HTF-Ben v2 | reference only, not re-run (NinjaTrader friction) | — |

## Where the money goes (BASE exits)
| Exit | Trades | Gross | Avg gross | Median bars held |
|---|---|---|---|---|
| S initial stop | 714 | ($43,662) | ($61) | 2 |
| R reversal-candle | 1,621 | $37,256 | $23 | 4 |
| P1 EMA9 trail | 246 | $644 | $3 | 4 |
| P2 EMA21 trail | 89 | $1,895 | $21 | 8 |
Reached P1 985 (37%), P2 471 (18%). The initial stop is hit fast and costs about $61 a time; R takes small profits on most trades but they don't cover the stops plus $9,554 of costs.

## Variants (reported, never ranked; 1 MCL mid)
| Variant | Trades | Gross | Net | Net at high |
|---|---|---|---|---|
| BASE | 2,670 | ($3,867) | ($13,422) | ($18,820) |
| V-STALL N=3 | 2,735 | ($3,840) | ($13,621) | ($19,147) |
| V-STALL N=4 | 2,712 | ($4,380) | ($14,083) | ($19,565) |
| X4 on | 2,576 | ($4,908) | ($14,123) | ($19,329) |
| No P2 | 2,688 | ($3,452) | ($13,063) | ($18,493) |
| No R | 1,928 | $3,562 | ($3,422) | ($7,368) |
| Session off | 3,419 | ($5,937) | ($18,189) | ($25,111) |
| V-AVOID | 2,047 | ($2,863) | ($10,198) | ($14,342) |
No variant is positive net. Session off is the worst, so the 02:00–12:00 filter is doing something. No R is the only variant with positive gross ($3,562) but still loses after costs, and its total leans on one year (89% top-year share). None of this rescues the base (registration §4, §7).

## Registered prediction vs actual (§10)
Predicted 300–600 fills; **actual 2,670** (4.5× more). Win rate under 50%: yes (41%). Beats Donchian and random p50: **no**. The P2 tail supplying the profit: **no** (P2 gross $1,895).

## Fidelity: how well does the code reproduce Ben's picks? (G6, seen window, not evidence)
On the TradingView bars Ben marked, the engine fires 250 times in the year (Ben marked 14). Against his 14 entry lines: **1 of 14 within 1 bar and 2 ticks**; 9 of 14 within 1 bar of his bar; price gaps range from 2 to 146 ticks. Against 5 levels he stated in fire notes: 0 of 5 within 2 ticks. So the registered buy-stop (3-bar high + 1 tick) is not what Ben's discretionary lines are. This backtest tests the mechanical coding, not his eye. Seen window for reference: engine BASE 250 trades, net $3,027 (seen — not evidence; it does not offset the 11.5-year result).

## Method, caveats
- Cut to sessions before 2022-01-01 before resample and back-adjust. No bar from 2022 on was read by this package (the seen window uses Ben's TradingView CSV). 1H OHLC can't show intrabar order; the base has 0 same-bar level+stop touches by construction (stop uses the entry bar's own low, live from the next bar; 175 entries have their stop set by the entry bar's own low).
- Interpretations fixed before any number was seen (spec.py, I1–I10): A0 = ATR before the fill bar; working P1/P2 stop = max(S, EMA[j−1]); V-STALL semantics; roll carries the position (+2 sides) and cancels a working entry order; criterion-5 volatility = net ÷ std of daily net P&L; C3 = independent single-trade outcomes from a random in-session bar's open.
- 34 tests pass (truncation-invariance look-ahead guard on 5 variants × 3 seeds plus a mutation test that catches a one-bar leak, ledger refusals, order mechanics, costs). Hand-traced three real trades against the bars.
- C2 (HTF-Ben v2) not re-run: reference only, different friction; cite its own Result doc.

## Next steps (board)
- **W15-0032 sub 4 and sub 5:** Done (this doc). Ben: read the verdict.
- **W15-0032 sub 8** (short engine build) and **sub 9** (short backtest) are unaffected in rule but share the fidelity risk; Ben decides whether to proceed.
- Files in `D:\Trading\Claude outputs\`: `w15_0032_chartmark_backtest_20260930.txt/.json`, `w15_0032_chartmark_trades_base_20260930.csv`, `w15_0032_chartmark_preflight_20260930.txt`, `w15_0032_chartmark_parity_20260930.txt`.
