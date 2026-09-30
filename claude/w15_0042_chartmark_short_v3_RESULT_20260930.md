# W15-0042 · CHARTMARK-S v3 short — RESULT (training side, 2026-09-30)

## In plain terms
The v3 rule sold crude oil 4,830 times over eleven and a half years. Before costs it made $1,237. IBKR costs took $17,250, so the net at mid friction is ($16,013) per 1 micro contract. About $3.57 of cost on every trade wiped out an average gross gain of about 26 cents. It is also worse than luck: random short entries with the same exits lose ($10,907) at the median, and this rule beat only 11.4% of them. The Tier A half (EMA9 below EMA21) had a positive gross of $4,911 and still lost ($5,493) after costs; the Tier B half, the relaxed retest tier, lost money before costs.

**VERDICT: FAIL. Criteria 5 and 6 fail, so the study closes.** 9 of 10 criteria fail; only "at least 150 trades" passes. G6 waived for 8 Sep 08:00 (Amendment 1): v3 is not evidence of anything on the training side; only the holdout counts, and it was not spent.

## What Ben must decide
Accept the closure. CHARTMARK-S is finished: v1 failed, v2 closed at G6 unscored, v3 fails criteria 5 and 6. The registration allows no v4; a new short idea needs a new registration with a reason that does not start from these results.

## Headline (base, 1 MCL, mid friction)
| | |
|---|---|
| Trades / wins / losses | 4,830 / 1,099 / 3,731 |
| Gross / costs / net | $1,237 / $17,250 / ($16,013) |
| Net low / mid / high | ($6,267) / ($16,013) / ($25,759) |
| Max drawdown | ($16,529) |
| Halves | ($8,987) / ($7,027) |
| 1 full CL, mid | ($108,188) |
| Avg win / avg loss / largest loss | $61 / ($22) / ($668) |

## By tier
| Tier | Fills | W / L | Gross | Costs | Net low | Net mid | Net high |
|---|---|---|---|---|---|---|---|
| A | 2,913 | 701 / 2,212 | $4,911 | $10,404 | $385 | ($5,493) | ($11,371) |
| B | 1,917 | 398 / 1,519 | ($3,674) | $6,846 | ($6,652) | ($10,520) | ($14,388) |

Tier A is 80% of context bars, Tier B 20%.

## Criteria
| # | Criterion | Result | Value |
|---|---|---|---|
| 1 | Net above $0 at mid | FAIL | ($16,013) |
| 2 | Both halves above $0 | FAIL | ($8,987) / ($7,027) |
| 3 | Drop top 1 and 2 years above $0 | FAIL | ($16,502) / ($16,713) |
| 4 | Bootstrap by year, net above $0 in 95% | FAIL | 0.0% |
| 5 | Beats C1 (Donchian 20/10 short) on net and net per volatility | FAIL | ($16,013) vs $1,069 |
| 6 | Beats C3 p99 (random entries) | FAIL | ($16,013) vs ($780) |
| 7 | No single year above 50% of net | FAIL | 20.3% (of a loss) |
| 8 | Net above $0 at high friction | FAIL | ($25,759) |
| 9 | At least 18 of 27 grid cells above $0 | FAIL | 0 of 27 |
| 10 | At least 150 trades | PASS | 4,830 |

## Controls and variants (1 MCL, mid; variants reported, never ranked)
C1 Donchian 20/10 short: 1,610 trades, $1,069. C3 random entries (1,000 draws): p5 ($17,994), p50 ($10,907), p95 ($3,698), p99 ($780); base beats 11.4%. Reference v1 base: 6,997 trades, gross ($3,599), net ($28,532).

| Variant | Trades | Gross | Net mid | Net high | Net low |
|---|---|---|---|---|---|
| BASE | 4,830 | $1,237 | ($16,013) | ($25,759) | ($6,267) |
| V-A | 3,403 | $3,815 | ($8,355) | ($15,231) | ($1,479) |
| V-B | 1,917 | ($3,674) | ($10,520) | ($14,388) | ($6,652) |
| V-B1 (v2's rule) | 4,208 | $1,302 | ($13,726) | ($22,216) | ($5,236) |
| V-RANGE | 2,078 | ($3,061) | ($10,484) | ($14,678) | ($6,290) |
| V-SESSION | 2,993 | $3,651 | ($7,071) | ($13,129) | ($1,013) |
| V-AVOID | 4,042 | ($1,456) | ($15,889) | ($24,043) | ($7,735) |

Neighbour grid: 0 of 27 cells above $0 (best ($10,464), worst ($22,685)). Only 2014 (+$488) and 2020 (+$212) are positive years at mid.

## Predictions, scored (written before the run)
Right: base fills 4,300 to 6,000 (4,830); Tier A about 3,000 (2,913); negative at mid; under one-in-four odds of beating p99; G6 11 Sep mark passes; at least one rejected entry fills (1 of 8). Wrong: win rate near one in three (22.8%).

## Method, caveats, sources
Registration REGISTERED_chartmark_short_v3.md (v2 with B1 removed) + Amendment 1. Training bars cut before 2022-01-01, resampled and difference back-adjusted; IBKR costs at three levels; hourly bars cannot show the path inside a bar; C3 draws are independent single-trade outcomes; third short version on the same training bars. Seen window (8 Sep 2025 on, not evidence): engine 465 trades, gross ($1,048), net ($2,694).
Files: claude/raw/w15_0042_chartmark_short_v3_backtest_20260930.txt (+ .json, trades csv), Claude outputs/w15_0042_chartmark_short_v3_g6_20260930.txt. Published page: https://claude.ai/artifact/PvSozV6PbGSdKPeFJi5yVu

## Next steps (board)
- **W15-0042** — Done (study closed FAIL). Ben: accept the closure.
