# W15-0017 · Tori Trades full-channel sweep — gap analysis vs TL-v0, TL-bounce, HTF-Ben v1 — RESULT

2026-09-26 · Research & spec chat · Step 3 of W15-0017 · Inputs: Step 1 shortlist (https://ben-siu.monday.com/docs/5031563929), Step 2 collation of 79 videos (https://ben-siu.monday.com/docs/5031564014), `docs/research/REGISTERED_tl_v0.md`, `docs/research/REGISTERED_tl_bounce.md`, `docs/research/REGISTERED_htf_ben_v1.md`, `claude/tori_trades_systematic_RESULT_20260920.md`.

## In plain terms

We now have her method from 92 videos instead of 13. Most of what she teaches is already in the coded versions: the break entry on a candle close, the stop placed beyond the opposite line with some room, trailing it as new pullbacks form, 1–2% risk with a skip when the stop is too wide, and flipping direction when the opposite line breaks. The one big thing missing is the part we had written off as "can't be coded": her **"A+" checklist** (at least 3 touches on the line, a line at least a week old, a trending market, entry close to the stop line) and the **way she draws the line** (anchored at the extreme swing and drawn to touch as many points as possible, not just through the two latest swings). Across the new videos she states both precisely enough to code, and her own tally says the 3-touch trades are where her money comes from. Since TL-v0's backtest (W15-0014) hasn't run yet, this is the last clean moment to decide whether to test that checklist; adding it after a result would not count as a fair test.

## Verdict / what Ben must decide

- **Verdict:** no registered rule is contradicted by the new videos, so nothing in TL-v0, TL-bounce or HTF-Ben v1 needs amending. One material gap: her **line construction + A+ checklist** (gaps 1–2 below), now codable, and not tested anywhere. Everything else is either covered, intentionally left out, or too discretionary / too rare to be worth a test.
- **Decision for Ben — W15-0018:**
  - **A · Register "TL-v1 (her line + A+ checklist)" now**, as the trend-line line's last registered hypothesis, before W15-0014's P&L is read. Built on the W15-0014 engine. **Recommended.**
  - **B · Add it to TL-v0 as PRE-RUN reported-only variants.** Cheaper, uses no slot, but it can never spend a holdout; a later proper test would be result-motivated.
  - **C · Record only**, wait for W15-0014 and W15-0016. Any later test counts as after-a-result (TL-v0 §7).
  - **D · Drop.**
- **Ask to Build & test chat (posted on W15-0014):** build as normal, but don't read or report W15-0014's P&L until W15-0018 is decided.

## 1. The gap table

"Covered" = the registered rule matches what she teaches. "Different on purpose" = a known, recorded departure. "Gap" = she teaches it, it's codable, and nothing registered tests it.

| # | What she teaches (main videos) | TL-v0 / v0-rev | TL-bounce | HTF-Ben v1 | Verdict |
|---|---|---|---|---|---|
| 1 | **Line construction**: ray from the extreme visible pivot (point A) to the next pivot price hasn't crossed (point B); draw to touch as many points as possible; each lower chart's line starts at the higher chart's point B, steeper each time (`ipUbsQZWFIU`, `yHAC0xtBR2Q`, `LpXZBXySIZA`, `l0InoYnlM-A`, `YROta7k11pE`) | Line through the two latest confirmed pivots (L = R ∈ {3,5,8}) | Same code, L = R = 5 | Same code, for F2 and T | **Gap — now codable.** Known departure (TL-v0 §2.3) but it was only half-specified before; now fully specified |
| 2 | **"A+" checklist**: ≥3 touch points (2 = weaker playbook), line spans >1 week, market trending not consolidating, price close to the stop line at entry else downsize (8 videos, plus the grading exercise `xRxUo3_9XRA` and `jxFzcP3J04g`) | Takes every signal ("A+ selection" listed as not codable) | Takes every touch | n/a (Ben's own filters F1, F2) | **Gap — 3 of 4 parts exactly codable**; "trending" codable as a range filter like HTF-Ben's F1. Biggest gap |
| 3 | Line invalid if price ever crossed it, apparently including wicks (`ipUbsQZWFIU`) | Closes, 0.10 × ATR buffer | Closes | Closes | Different on purpose (TL-v0 §2.3). Minor |
| 4 | Enter on the break, wait for the candle to close (`G29LbG1Xkvw`, `fGi45FCud8s`, `yZfj6h_fzPQ`) | Close beyond by 0.10 × ATR → next open | n/a | n/a | **Covered** |
| 5 | Opposite-line break = exit and new entry the other way (`LpXZBXySIZA`, `W_zXskvHimM`, `1JiU2KJG3J8`, `fGi45FCud8s`) | v0-rev reverses; v0 ignores | n/a | n/a | **Covered by v0-rev** — four more videos back v0-rev as the holdout candidate |
| 6 | **Safety line**: stop beyond the opposite line with "wiggle room", re-drawn steeper through each new pullback, never loosened; initial risk → breakeven → profit (`pasWNYvY4TA`, `l0InoYnlM-A`, `zT2hSb9IEZw` + 6) | Opposite line − 0.25 × ATR, re-drawn from new pivots, never loosens | S1 + S2 swing trail capped at the line | Own trail (Ben's) | **Covered.** Only difference is the anchor point, which is gap 1 |
| 7 | Size so a safety-line break costs 1–2%; if not, downsize or skip, never move the stop closer (`pasWNYvY4TA`, `OuwJOHC4xok`) | 1% risk, floor(), zero = skip, counted | Same, reported | $10k account view | **Covered exactly** |
| 8 | Exit ranking: safety line best; S/R or a higher-chart line are allowed alternatives; her 2024 drift to S/R exits she calls a mistake (`5xiHaXxWUQw`, `Y_Ney-Fp5T4`, `l0InoYnlM-A`) | Safety line only | X1 close-through + trail | X1/X2 + trail | **Covered** — coded exit = her stated ideal |
| 9 | S/R only as confirmation or exit; **double confirmation** (line + horizontal level break together) in choppy markets (`qsjLmbVNlCc`, `OuwJOHC4xok`, `eQzviuJfUGQ`) | Not coded | Not coded | Not coded | Gap, partly codable. Level placement is her judgement; low priority |
| 10 | **Break-and-retest** entry (`h8BKDjwXbXA`, `G29LbG1Xkvw`) | Not coded | Not coded | T rule is Ben's retest-then-continue for the curl route | Gap, but she says she used it once all year. Record only |
| 11 | **Bounce** entry: dropped (`nmUKXMhXHuk`), later redefined for tagging and used "rarely" (`q4t71xxbDsY`), taught 2026-09-24 (`TuXOgkcYw9E`). Her bounce playbook also needs >1 week + trending | n/a | Registered; no age or trending filter | n/a | Registration stands. Context: bounce is a minor setup for her, so her results say little about TL-bounce |
| 12 | Execution chart **4-hour**, CL and platinum only (`Y_Ney-Fp5T4`, `KqBV3DcC4Sc`, `jxFzcP3J04g`) | Daily, 12 markets (4H was step 5, "data priced first") | CL 4H | CL 4H | Different on purpose. Note: CL 1-hour bars are now owned (W15-0002), so step 5's data condition is met for CL |
| 13 | Top-down from monthly, each line chained from the one above | Last weekly break, completed weeks | Last daily break | Daily filter | Approximation. Chained version = gap 1 |
| 14 | High-volatility / news: drop to 1H, exit on S/R, cut size, skip before weekends and news (`ZqC6Wgndpew`, `gRdxSEEFIKc`) | Not coded | Not coded | Not coded | Not codable as she does it. ATR sizing already shrinks size when volatility rises. Keep out |
| 15 | One trade at a time, 1–2 instruments ("111 rule") | 12 markets at once | One at a time, CL | One at a time, CL | Different on purpose (avoids fitting to crude, TL-systematic §2 trap 3) |
| 16 | Continuous back-adjusted chart; exit before the roll (`OuwJOHC4xok`, `h8BKDjwXbXA`) | Back-adjusted signal, held-contract P&L, roll charged | Same | Same | **Covered** |
| 17 | Process: alerts not chart-watching, never drop to a lower chart mid-trade, Sunday line review, "pay yourself", don't discuss open trades | — | — | — | Not strategy rules; a coded system follows them by construction. Relevant to Ben trading HTF-Ben by hand, not to the code |

## 2. Her own numbers (self-reported — not evidence)

These are what she shows on screen. They are selected by her, and the coded tests exist precisely because these can't be checked. Shown here only because they are the reason gap 2 matters.

**2024, 4-hour, CL and platinum (`Y_Ney-Fp5T4`, broker statement shown, 180% on the year):**

| Playbook | Trades (from her win rates) | Win rate | Her conclusion |
|---|---|---|---|
| 2-touch break | 7 (6 won) | 85.71% | worse average win vs loss, lower net |
| 3-touch break | 9 (7 won) | 77.78% | much better average win vs loss, higher net: "double down on three touch point" |

16 trades in total. Too few to separate the two playbooks statistically; it tells us what she believes, not that it's true.

**Single trades she walks through (dollars as she states them):**

| Video | Trade | Result | Checklist met? (her words) |
|---|---|---|---|
| `ZMIDTRhLLHQ` | 3-touch break, downward line | 39,600.00 | Yes |
| `kBmtkb-Vw7c` | 3+ touch break | 34,755.00 gross (2.05R) | Yes |
| `17WoZCQcNHc` | ≥2-touch break, >1 week | 30,000.00 | Mostly (broke her own stop rule twice) |
| `E6dUUVdzMLE` | Steepest line in a fan | 29,785.00 | Partly (held past the break on purpose) |
| `yZfj6h_fzPQ` | CL, all 5 A+ boxes | 27,600.00 | Yes |
| `Rz92UpmWO0U` | Break in a consolidating market | (17,000.00) | No — market was ranging |
| `oq8nF8rq7x4` | Platinum, 2-touch line | (13,559.00) | No — 2 touches, held past the stop line |
| `lR9ppLNbC4I` | Futures loss | (7,954.00) | Checklist restated after the loss |

The pattern she draws (losses when the checklist is broken) is exactly what a coded A+ filter would test. On her own anecdotes it can't be told apart from hindsight.

## 3. What option A would register (for W15-0018; parameters fixed only in the registration)

- **Line (gap 1):** among confirmed pivots in a lookback, the line from the extreme pivot that touches the most pivots (within 0.25 × ATR) with no close beyond it; pivots confirmed at i+R only (same hindsight guard as TL-v0 G5).
- **A+ filter (gap 2):** touches ≥ 3 (2-touch reported as a variant); span ≥ one week of bars; not in a range (percentile rule like HTF-Ben F1, fixed on training bars only); stop distance within the 1% sizing (already TL-v0's skip rule).
- **Everything else from v0-rev:** entry, safety line, reversal, sizing, costs, controls C1–C3 (Donchian must still be beaten).
- **Open question for the registration, not now:** 12 markets daily (as TL-v0) or CL 4-hour (her market and chart, data owned). The one-week span only bites on 4-hour.
- **Power risk:** the filter will cut trades hard; the registration's own count-only pre-flight decides whether it can be read at all.
- **Budget:** TL-v0 §9 allowed two more; TL-bounce used one. A would use the last one.

## 4. What does not change

- **TL-v0 / v0-rev, TL-bounce, HTF-Ben v1:** no amendment. Each §7 forbids adding her discretionary pieces after a result, and nothing here shows a registered rule is wrong.
- **TL-bounce (W15-0016):** read its result knowing she rarely takes bounces and her bounce also needs a >1-week line and a trending market. That's context only, posted on W15-0016.
- **HTF-Ben v1:** Ben's method, not hers. The retest idea (gap 10) is already his T rule; the rest doesn't apply.

## Method

Each Step 2 rule note and cross-cutting finding was checked line by line against the rule tables of the three registration files (TL-v0 §2, TL-bounce §2, HTF-Ben v1 §2), plus the known-departure lists (TL-v0 §2.3, TL-bounce §2.5) and the earlier method mapping (`tori_trades_systematic_RESULT_20260920.md` §1, §7). No data read, no backtest, no P&L computed.

## Caveats

- Source is auto-generated transcripts. Her live practice may differ from what she says.
- 1 of 80 shortlisted videos had no transcript (`WUv5q-TAKyM`, title suggests the same $30k platinum trade as `H8B5ujLnU-8`). Not worth a retry: 8 other videos state the same checklist.
- 1 long podcast (`eLaFH2ShrLg`) sampled at ~35%; no rules found in what was read, consistent with its topic.
- `wXc3TbxQAeM` and `talIIKi5Gsg` are the same 2023 review, counted once.
- The dollar figures in §2 are hers, unaudited except where a statement is shown, and selected by her.

## Next steps (board)

- **W15-0018** — Ben: decide A / B / C / D. If A: registration in the Research & spec chat (Opus · Medium), then build folded into W15-0014's engine (Build & test chat, Sonnet · Medium).
- **W15-0014** — pointer posted: hold the P&L read until W15-0018 is decided.
- **W15-0016** — pointer posted: context from gap 11.
- **W15-0017** — Done.

## Source files

- Step 1 shortlist: https://ben-siu.monday.com/docs/5031563929
- Step 2 collation: https://ben-siu.monday.com/docs/5031564014
- Registrations: `docs/research/REGISTERED_tl_v0.md`, `docs/research/REGISTERED_tl_bounce.md`, `docs/research/REGISTERED_htf_ben_v1.md`
- This doc: `claude/w15_0017_tori_gap_analysis_RESULT_20260926.md` · monday Result doc: https://ben-siu.monday.com/docs/5031564077
