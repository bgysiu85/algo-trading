# AT-106 · Kevin Davey channel — Part 2: verdict and recommendation — RESULT

2026-09-20 · Futures Trading Viability Analysis chat (Opus, high effort) · builds on the extraction doc (AT-106 subitem 2). Verdict only; nothing built, nothing backtested.

## In plain terms

Kevin Davey is the more credible of the two channels. He codes his strategies, tests them on many markets and says openly when they fail. The trouble is where the tested material sits. Everything he publishes in full, he himself says not to trade. What he does trade is kept in his books and courses, and its record since publication is only 6–12 months. So there is no Davey strategy worth building here. What does carry over is three habits of his process, plus one uncomfortable number. His own micro-futures portfolio, run on an account about Ben's size, has had a single-week drawdown of about $19,000 in backtest. That would be 86% of Ben's $22,129.

## Verdict / what Ben must decide

- **Verdict: do not build a Davey strategy.** His fully disclosed strategies (Golden Cross, Keltner, reverse Keltner) fail his own tests. The strategies he trades (CL, ES, CAD and the 12-strategy portfolio) are only partly disclosed. Their post-publication record is too short to tell skill from luck, and the book holds 11 strategies. Testing the one that looks best would be a search, not a test.
- **Take three process tools instead:** a Monte Carlo drawdown check at Ben's actual account size, a quit point set before trading, and an incubation (paper) period. Add them to work already registered: TSMOM (AT-43) and TL-v0 (AT-105).
- **On futures vs equities:** the channel shows that micro contracts make a single futures system small enough for a $22k account. It gives no evidence of an edge Ben could capture. That answer still comes from TSMOM (AT-43).
- **Decision for Ben (AT-108):**
  - **A (recommended):** add the three tools to TSMOM and TL-v0 as PRE-RUN amendments. They would be reported, never scored, and would not change any rule. No new strategy.
  - **B:** buy the book and register one of its strategies (CL) for a test on the daily bars already owned. Not recommended, for the reasons above.
  - **C:** close AT-106 with nothing carried forward.

## 1. How much his evidence is worth

| Claim | What backs it | Weight |
| --- | --- | --- |
| 3× contest winner, >100%/yr, 2nd/1st/2nd | His own site and interviews name the World Cup Championship of Futures Trading, 2005–07. The contest's own records were not checked here | Probably real, but 20 years old. It was won in a format that rewards leverage: his own account fell 50% mid-contest ($15,000 → about $7,500). A winning contest entry is picked from many entrants, so it says little about expected returns |
| Live 12-strategy micro portfolio, $24,837 → $36,750 (Jan–Jul 2026) | His own broker screenshots | One account over seven months. That is +$11,913, or +48% in one good half-year. It shows the portfolio exists and trades. It doesn't show that it has an edge |
| Book strategies: CL $96k, ES $187k, CAD $46k walk-forward | Equity curves; code partly or fully withheld | Walk-forward results from a process that screens many candidates and keeps the survivors. The number of discarded candidates is never stated (extraction red flag 4) |
| Golden Cross, Keltner and reverse Keltner fail on 44 markets | Full code, 220 to 1,848 equity curves each | **The most reliable evidence on the channel.** It agrees with this project: simple indicator rules rarely survive costs |

## 2. What his numbers mean at Ben's size ($22,129)

Assumption: the book's per-strategy figures are for one full-size contract. That fits a $5,000 stop producing a $6,800 largest loss. Micro contracts are one-tenth the size.

| Figure (his) | Full-size | Micro equivalent | Share of $22,129 |
| --- | --- | --- | --- |
| CL strategy, largest loss | (6,800) | (680) | (3.1%) |
| CL catastrophic stop | (5,000) | (500) | (2.3%) |
| ES strategy, COVID drawdown | (20,000) | (2,000) | (9.0%) |
| **12-strategy micro portfolio, worst week (backtest)** | already micros | **(19,000)** | **(85.9%)** |
| Contest account, mid-contest drawdown | — | (7,500) on $15,000 | (50%) of that account |

**What this means:** one Davey-style system on one micro fits a $22k account at about 2–9% risk. A dozen of them together, the way he actually trades, reached a one-week drawdown that would all but wipe out Ben's account. The micros make each piece small enough, but the portfolio he sells is still far too risky for this account. That matches TSMOM's own capacity finding: the paper's sizing needs about $532,000.

## 3. What transfers, and what the project already has

| His process step | Already in the project? | Take it? |
| --- | --- | --- |
| Test on many markets and bar sizes, not one | Yes: multi-market registration, drop-top-N by market, cluster bootstrap | No need |
| Walk-forward optimisation (re-fitting parameters on a rolling window) | Deliberately not: the project fixes parameters or uses an ensemble, because re-fitting is itself a search | **No.** The project's rule is stricter |
| Out-of-sample / holdout | Yes: locked holdout, spent once, enforced in code | No need |
| **Monte Carlo drawdown at the real account size** | Partly: TSMOM §5 reports integer sizing at $22k/$100k/$500k, but no drawdown distribution | **Yes.** Report the 50th/95th-percentile worst drawdown in dollars and the chance of a 30% and a 50% drawdown at $22,129 |
| **Quit point fixed before going live** | No: the give-back cap is a session rule, not a strategy-retirement rule | **Yes.** Stop trading a strategy if its live drawdown passes its Monte Carlo 95th percentile, written down before the first trade |
| **Incubation (paper) before real money** | In practice (IBKR paper) but not as a written rule | **Yes.** Set a minimum paper period with a pass condition before any live order |
| Don't reject a strategy by combing through metrics | Yes: pass criteria fixed in the registration | No need |

## 4. Why not build his CL strategy anyway (option B)

- **Rules incomplete:** the ADX threshold and the full exit code are in the book, so a version built from the video would test our guess, not his rule. That is the same fidelity problem as TL-v0.
- **Multiplicity:** the book has 11 strategies. Picking the one with the best shown curve spends the multiplicity budget before the test starts.
- **Out-of-sample window:** the book was published around September 2025, so the only truly out-of-sample period is about 12 months on daily bars, roughly one reading per strategy. Everything before that is his in-sample.
- **Same family as work already queued:** ADX plus momentum is a trend filter, which TSMOM and TL-v0 already cover.

## Caveats

- This is a judgement from 16 transcripts. No backtest was run, and no profit or loss was computed.
- The micro conversions in §2 assume his figures are per full-size contract. If some are already micros, those rows are ten times larger in account terms.
- The contest was checked only against his own sources and interviews, not the contest's published results.
- One video (the MasterClass strategies preview) was not read.

## Next steps

- **AT-108** · Decide: add the three process tools (Monte Carlo drawdown at $22k, quit point, incubation rule) to TSMOM and TL-v0 as reported-only PRE-RUN amendments (A), buy the book and test one strategy (B), or close (C). Assignee Ben.
- **AT-43** (TSMOM training run) remains what decides futures vs equities.

## Source files

- Extraction: `claude/kevindavey_extraction_20260920.md` · `D:\Trading\Claude outputs\kevindavey_extraction_20260920.txt`
- This result: `claude/kevindavey_verdict_RESULT_20260920.md` · `D:\Trading\Claude outputs\kevindavey_verdict_20260920.txt`
- Compared against: `claude/tori_trades_systematic_RESULT_20260920.md` (AT-104), `docs/research/REGISTERED_tsmom.md` §5
