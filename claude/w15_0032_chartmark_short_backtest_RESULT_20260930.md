# W15-0032 · CHARTMARK-S v1 (short) training backtest — RESULT (2026-09-30, Build & test chat)

Board: W15-0032 sub 8 (build) + sub 9 (backtest). Code: `strategy/chartmark_s/`, tests `tests/strategy/chartmark_s/` (48 tests). Registration: `docs/research/REGISTERED_chartmark_short_v1.md` incl. Amendment A. CL 1H, 2010-06 → 2021-12, IBKR costs, 1 MCL, mid friction (1 tick per side). Holdout not touched, ledger `holdout_chartmark_short_v1.json` does not exist.

## In plain terms
Coded exactly as registered, the short method loses money. It took 6,997 trades (24% wins) over 11.5 years and lost ($28,532) per 1 MCL after costs; before costs it was already slightly negative (gross ($3,599)). It loses in every friction level, in both halves, in 11 of 12 years, and in all 27 neighbouring settings. Random short entries with the same exits lost less (median ($16,266)); the base beat only 0.5% of them. A plain 20/10 Donchian short made $1,069. Criteria 5 and 6 fail, which closes the study.

The pattern is clear in the exit types: the 1,042 trades that ran to the EMA9 retest exit earned $55,993 gross; the 5,933 quick cuts at EMA9 lost ($58,611) gross and paid $21,070 in costs. Cutting fast keeps each loss small, but the entry does not pick tops well enough for the winners to pay for the cuts.

## Verdict
**FAIL.** Criteria 1, 2, 3, 4, 5, 6, 7, 8, 9 fail; 10 passes (6,997 trades). Ben decides: accept the close; whether any new hypothesis for the short side is warranted (Avoid zones were registered as a reported variant only, V-AVOID, ($28,338), and did not change the picture).

## Headline (BASE, 1 MCL, mid)
| | |
|---|---|
| Trades / wins / losses | 6,997 / 1,678 / 5,319 |
| Gross | ($3,599) |
| Costs | $24,932 |
| **Net, mid** | **($28,532)** |
| Net low / high friction | ($14,446) / ($42,618) |
| 1 CL net low / mid / high | ($69,377) / ($210,237) / ($351,097) |
| Avg win / avg loss / largest loss | $36 / ($17) / ($668) |
| Worst losing run / max drawdown | 34 / $28,595 |
| Halves | ($15,684) / ($12,848) |

## Criteria
1 net>0 **FAIL** ($28,532) · 2 halves **FAIL** · 3 drop-top-1/2 **FAIL** ($28,941)/($28,162) · 4 bootstrap **FAIL** 0% · 5 vs C1 **FAIL** (net ($28,532) vs $1,069; per-volatility ($514) vs $15) · 6 vs C3 p99 **FAIL** (($28,532) vs ($3,789)) · 7 top-year share **FAIL** (14% of a negative total) · 8 high friction **FAIL** ($42,618) · 9 grid **FAIL** 0/27 · 10 trades **PASS** 6,997.

## By exit type (BASE, gross before costs)
| Exit | Trades | Wins | Gross | Costs | Net |
|---|---|---|---|---|---|
| P0 cut at EMA9 | 5,933 | 815 | ($58,611) | $21,070 | ($79,681) |
| P1 retest exit | 1,042 | 863 | $55,993 | $3,784 | $52,208 |
| Backstop | 22 | 0 | ($981) | $78 | ($1,059) |

The three net figures add to the total: ($79,681) + $52,208 + ($1,059) = ($28,532).

## By year (1 MCL)
| Year | Fills | W/L | Gross | Net low | Net mid | Net high |
|---|---|---|---|---|---|---|
| 2010 | 364 | 78/286 | ($1,658) | ($2,220) | ($2,950) | ($3,680) |
| 2011 | 625 | 189/436 | ($1,667) | ($2,635) | ($3,893) | ($5,151) |
| 2012 | 612 | 165/447 | ($245) | ($1,191) | ($2,419) | ($3,647) |
| 2013 | 644 | 126/518 | ($1,630) | ($2,628) | ($3,924) | ($5,220) |
| 2014 | 564 | 145/419 | $2,417 | $1,544 | $410 | ($724) |
| 2015 | 525 | 141/384 | ($785) | ($1,600) | ($2,658) | ($3,716) |
| 2016 | 588 | 152/436 | $1,317 | $405 | ($779) | ($1,963) |
| 2017 | 620 | 104/516 | ($454) | ($1,417) | ($2,667) | ($3,917) |
| 2018 | 555 | 127/428 | $802 | ($59) | ($1,177) | ($2,295) |
| 2019 | 612 | 133/479 | ($775) | ($1,728) | ($2,966) | ($4,204) |
| 2020 | 604 | 166/438 | ($617) | ($1,550) | ($2,762) | ($3,974) |
| 2021 | 684 | 152/532 | ($303) | ($1,366) | ($2,746) | ($4,126) |

## Controls and variants (1 MCL; variants reported, never ranked)
| | Trades | Gross | Net mid | Net high |
|---|---|---|---|---|
| C1 Donchian 20/10 short | 1,610 | — | $1,069 | ($2,275) |
| C2 long rules mirrored (reference) | 2,662 | $6,384 | ($3,135) | ($8,513) |
| C3 random shorts, p5 / p50 / p95 / p99 | | | ($24,135) / ($16,266) / ($7,293) / ($3,789) | |
| BASE | 6,997 | ($3,599) | ($28,532) | ($42,618) |
| V-RANGE | 4,441 | ($7,888) | ($23,709) | ($32,647) |
| V-SESSION | 3,436 | $303 | ($11,942) | ($18,860) |
| V-WIDE | 3,183 | $2,728 | ($8,763) | ($15,255) |
| V-CLOSE9 | 6,972 | ($3,342) | ($28,196) | ($42,238) |
| V-AVOID | 6,105 | ($6,591) | ($28,338) | ($40,624) |

Neighbour grid: 0 of 27 cells net > $0 (range ($23,803) to ($33,663)).

## Prediction vs actual (sec 10)
Predicted 3,000–7,000 fills: actual 6,997 (top of the range). Predicted "close to zero" at mid: actual ($28,532), well below zero. Predicted under even odds of beating random p99: it beat 0.5% of draws. Predicted V-WIDE and V-RANGE might look better net of costs: V-WIDE ($8,763) and V-RANGE ($23,709) are both less negative than the base but negative. Predicted V-SESSION weakest: it was not (($11,942)); every variant is negative.

## Gates (sub 8), all done before any P&L
G1 data reused (67,565 training bars, 139 rolls). G2 count-only pre-flight: 6,997 fills, clears the 150 stop rule. G3 holdout ledger built (`strategy/chartmark_s/holdout.py`, own file, tests refuse limits/other ledgers; the long ledger now refuses it too). G4 look-ahead guards: truncation invariance for all 6 variants, one-bar-shift mutation tests caught, context/range/AVOID use bars ≤ t only. G5 IBKR costs wired at three levels ($0.77 / $1.77 / $2.77 per side MCL). G6 seen-window parity: 651 trades, exits P0 542 / P1 108 / backstop 1, first five trades identical, and 651/651 trades identical to the reference `engine2.py`; seen-window net $1,781 per MCL at mid matches the registration (seen, not evidence).

## Method, caveats
- Interpretations fixed before any count (spec.py J1–J10): A0 at the last context bar; backstop includes the entry bar's own high (so same-bar backstop touches are 0 by construction); no maximum hold; a roll cancels a working entry and a held position pays two extra sides; C3 random entries at the open of any bar.
- 1H OHLC cannot show the path inside a bar; every fill is a stop at the level or the open. 6,997 trades in 11.5 years is about 50 a month; slippage is two-thirds of the mid cost, but gross is negative before any cost.
- C2 is scored by running the long engine on a price-negated frame (a long there is a short here).
- Fidelity: the engine has an entry within one bar of 10 of Ben's 15 marked entries; his discretion is not fully captured by the mechanical rules (registered known departures).
- Seen window (2025-09-08 →) is reported only.

## Files
`D:\Trading\Claude outputs\` — `w15_0032_chartmark_short_backtest_20260930.txt/.json`, `..._trades_base_20260930.csv`, `..._preflight_20260930.txt`, `..._parity_20260930.txt`. Repo: `claude/raw/w15_0032_chartmark_short_{backtest,preflight,parity}_20260930.txt`, code `strategy/chartmark_s/`, tests `tests/strategy/chartmark_s/`, one line added to `strategy/futbt/holdout.py` (the new ledger name).

## Next steps (board)
- **W15-0032 sub 11** — Ben: read this result, accept the close of CHARTMARK-S v1, and commit the code and result files (commands on the subitem).
- Nothing else is queued under W15-0032: both sides of the chart-marked method have now failed criteria 5 and 6. A new hypothesis (for example a different entry idea for tops, or Avoid zones as a hard filter on the long side) would be a new registration in the High timeframe chat.
