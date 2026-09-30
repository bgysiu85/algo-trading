# W15-0036 · CHARTMARK-v2 step C (confirmation on 2016–2021) — RESULT (2026-09-30, Build & test chat)

**Board:** W15-0036 sub 4 · **Raw:** `claude/raw/w15_0036_v2_stepC_20260930.txt` · **Trades:** `Claude outputs/w15_0036_v2_stepC_trades_20260930.csv` · **Registration:** `docs/research/REGISTERED_chartmark_v2.md` Amendments 4.3, 4.5, 5 · **Holdout: not read, not spent.**

## In plain terms
K1 — the rule picked on 2010–2015 — made **$533 net on 317 trades** over 2016–2021 (1 MCL, IBKR mid costs). That is a small gain on a six-year test, and it does not survive the registered bar: it turns to **($129)** at high friction, **84% of it comes from 2021 alone**, and it is beaten by both controls. Random entries using the same exits reach +$2,349 at their 99th percentile, and a plain Donchian 20/10 channel made +$2,357. The strategy's own exits do the work: the 232 EMA21 exits earned +$5,972 and the 85 backstop stops lost ($5,438). **Verdict: FAIL on criteria 5 and 6, which the registration says closes the study.** The 2022–2025 holdout was never touched and stays locked.

## Verdict and what Ben must decide
**FAIL — six of nine criteria failed (2, 4, 5, 6, 7, 8); 1, 3 and 9 passed.** Criterion 5 or 6 failing closes CHARTMARK-v2 (Amendment 4.3). Decisions:
1. **Accept the closure** of CHARTMARK-v2 as registered (nothing to run; holdout stays unspent).
2. **W15-0037 (forward paper test of K1):** the backtest gives it no support — 2010–2015 lost ($1,795) and 2016–2021 is marginal and fails the controls. Go or stop is yours; it was opened before this result.
3. **Anything new** (a v3) needs a reason that does not begin with a result (registration §0.5). The variants below were all read on this window, so none of them is that reason. Raised as **W15-0038**.

## The nine criteria (K1, 1 MCL, 2016–2021)
| # | Criterion | Result | Value |
|---|---|---|---|
| 1 | Net > $0 at mid | PASS | $533 |
| 2 | Net > $0 at high friction | **FAIL** | ($129) |
| 3 | Drop-top-1 calendar year still > $0 | PASS | $88 |
| 4 | Bootstrap by year, net > 0 in ≥ 90% | **FAIL** | 85.9% |
| 5 | Beats C1 on net **and** net ÷ std of daily net | **FAIL** | net $533 vs $2,357; net ÷ daily std 16 vs 41 |
| 6 | Beats the p99 of C3 (random entries) | **FAIL** | $533 vs $2,349 |
| 7 | No single year > 50% of net | **FAIL** | 83.6% (2021) |
| 8 | ≥ 18 of 27 grid cells net > $0 | **FAIL** | 9 of 27 |
| 9 | ≥ 75 trades | PASS | 317 |

## Headline (1 MCL)
| | Trades | Wins / losses | Gross | Costs | Net mid | Net low | Net high | Max drawdown |
|---|---|---|---|---|---|---|---|---|
| K1, 2016–2021 | 317 | 103 / 214 | $1,705 | $1,172 | **$533** | $1,195 | ($129) | $1,355 |
| K1, 2010–2015 (step S) | 317 | — | ($637) | — | ($1,795) | — | — | $2,301 |

Average win $92, average loss ($42), largest loss ($91), worst losing run 9. Halves (median trade date): $614 / ($81). 1 CL at mid: $8,861. Median hold 13 bars.

## By year
| Year | Trades | Wins / losses | Gross | Costs | K1 net | C1 net |
|---|---|---|---|---|---|---|
| 2016 | 41 | 13 / 28 | $119 | $156 | ($37) | $384 |
| 2017 | 42 | 15 / 27 | $210 | $159 | $51 | ($533) |
| 2018 | 57 | 18 / 39 | $472 | $209 | $263 | $143 |
| 2019 | 63 | 19 / 44 | $116 | $234 | ($118) | ($944) |
| 2020 | 58 | 17 / 41 | $137 | $209 | ($72) | $1,264 |
| 2021 | 56 | 21 / 35 | $651 | $205 | $446 | $2,043 |

## Where the money came from (exits)
| Exit | Trades | Wins | Net |
|---|---|---|---|
| EMA21 two-breach rule | 232 | 103 | $5,972 |
| $0.60 backstop | 81 | 0 | ($5,184) |
| Backstop inside the fill bar | 4 | 0 | ($254) |

Arms: A-early 90, A-fresh 206, B 21 fills. 1,070 order-bars, 317 fills, 753 unfilled.

## Controls (same window, same costs)
| | Trades | Net mid | Notes |
|---|---|---|---|
| C1 Donchian 20/10 long, no session filter | 878 | $2,357 | net at high friction $531; halves $83 / $2,274 |
| C3 random entries, same count per year, same exits (1,000 draws) | 317 each | p5 ($2,647) · p50 ($577) · p95 $1,410 · **p99 $2,349** | K1 beats 83.1% of draws |

## Sample trades
| Entry | Exit | In | Out | Net | Exit |
|---|---|---|---|---|---|
| 14 May 2020 02:00 | 19 May 00:00 | 24.16 | 31.05 | $685 | EMA21 |
| 26 Jun 2018 11:00 | 1 Jul 20:00 | 70.66 | 75.26 | $456 | EMA21 |
| 6 Dec 2021 00:00 | 8 Dec 02:00 | 68.23 | 71.92 | $365 | EMA21 |
| 21 Feb 2020 16:00 | 23 Feb 18:00 | 58.36 | 57.49 | ($91) | Backstop |
| 20 Jul 2016 13:00 | 21 Jul 07:00 | 56.62 | 56.02 | ($67) | Backstop |

## Neighbour grid (27 cells, unranked) — 9 of 27 positive
Only the **$0.60 backstop row is positive** ($532 / $533 / $553 across EMA21 windows 3/4/5); $0.40 gives ($204) / ($207) / ($193) and $0.80 gives ($78) / ($79) / ($59). The parallel-bars axis (4 / 6 / 8) changed no fill — every B fill came after a long run — so the grid is effectively nine distinct cells each counted three times. The result is tied to the one stop size registered.

## Variants (Amendment 4.5 — reported, never selectable, cannot spend the holdout; 1 MCL)
| Variant | Trades | Wins / losses | Gross | Net mid | Net high | Max DD |
|---|---|---|---|---|---|---|
| V-THETA03 | 333 | 106 / 227 | $1,420 | $192 | ($502) | $1,466 |
| V-WICK | 329 | 95 / 234 | $783 | ($417) | ($1,095) | $1,463 |
| V-STOP20 | 336 | 71 / 265 | $1,350 | $132 | ($556) | $775 |
| V-STOPATR | 326 | 86 / 240 | $1,758 | $565 | ($109) | $1,211 |
| V-SESSION | 154 | 57 / 97 | $1,792 | $1,229 | $911 | $528 |
| V-CONFIRMED | 233 | 76 / 157 | $1,301 | $434 | ($56) | $1,047 |
| V-AVOID | 201 | 61 / 140 | $363 | ($377) | ($795) | $1,234 |
| V-REDTOP | 385 | 107 / 278 | $1,505 | $100 | ($694) | $1,454 |
| V-WICKGATE | 411 | 137 / 274 | $3,389 | $1,877 | $1,023 | $1,204 |

Registration §4: *a variant that passes when the base does not is a new registration, not a rescue.* V-SESSION and V-WICKGATE are the two that stay positive at high friction; they were seen here on the confirmation window, so any test of them needs fresh data (the locked holdout is reserved for a nine-of-nine base pass) and pays a multiplicity cost.

## Against the registered prediction (§9)
Predicted net between ($4,000) and +$3,000 — observed +$533, inside. Predicted about one chance in four of beating the random p99 — it did not. Predicted BACKSTOP as most common exit — EMA21 was (232 of 317), because Amendment 1 removed the UNCONFIRMED exit.

## Method
Runner `strategy/chartmark_v2/confirm_c.py` (new, uncommitted — commands on the board). It refuses to run without `selection_chartmark_v2.json`, refuses any candidate other than the file's winner (K1), refuses window/holdout/variant/grid flags, and writes `confirmation_chartmark_v2.json` so a second run is refused. Indicators are computed over the training frame (2010-06 → 2021-12-31, archive cut before 2022 before loading), the engine is flat until the first bar of 2016 (`simulate(start=…)`), so every trade, control and grid cell is a 2016–2021 entry. C1 is CHARTMARK-v1's Donchian 20/10 without the session filter. C3: every bar of the window as a standalone random entry at its open, backstop $0.60, exits by the base's backstop/EMA21 walk, per-year count equal to K1's, 1,000 draws seeded `[crc32(draw), crc32("CL-v2"), 317]`. Bootstrap: 2,000 resamples of the six yearly nets. Tests: 100 pass in `tests/strategy/chartmark_v2` (15 new in `test_confirm_c.py`).
Consistency check: K1 re-run on the full frame gives 317 trades / ($1,795) on 2010–2015 entries, exactly step S's record.

## Caveats
- Six years, not twelve (Amendment 4.8): criteria 4 and 8 rest on half the data. A bootstrap over six yearly nets is coarse.
- C3 draws are independent single-trade outcomes (overlap allowed), as CHARTMARK-v1's C3 was; the entry bar's low is taken as after the entry.
- Prices are difference-back-adjusted; 1H bars cannot show the path inside a bar (Amendment 5 governs the fill bar).
- The selection among K1–K4 (multiplicity four) and the exploratory numbers of §0.2 are disclosed costs of the design. Step S never read 2016+.
- The one-run ledger means a code change after this result cannot be re-run under this registration.

## Source files
`strategy/chartmark_v2/confirm_c.py`, `tests/strategy/chartmark_v2/test_confirm_c.py`, `selection_chartmark_v2.json`, `confirmation_chartmark_v2.json`, `Claude outputs/w15_0036_v2_stepC_20260930.{txt,json}`, `…_trades_20260930.csv`.

## Next steps (board)
- **W15-0036 sub 4** — closed Done with this result.
- **W15-0036** — Done; CHARTMARK-v2 closed FAIL.
- **W15-0037** — Ben: decide whether the K1 forward paper test still runs (no backtest support).
- **W15-0038** — Ben: decision on any further CHARTMARK line (v3 needs a reason that does not begin with a result).
- Commit of the runner, tests and raw/result files — commands on sub 4.
