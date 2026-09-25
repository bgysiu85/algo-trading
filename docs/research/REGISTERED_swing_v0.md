# REGISTERED — SWING-v0: cross-sectional short-term reversal, long-only, market-relative

**Committed before the backtest is coded, before any run exists, and before any return of
this candidate has been seen.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is
run.

**Board:** W07-0003 (was AT-46). **Governing pre-flight:** `claude/swing_preflight_20260914.md`
(G1–G8). **Cost input:** `claude/swing_g2_RESULT_20260919.md`. **Universe input:**
`claude/swing_g8_sources_20260919.md` and the W07-0002 result
(https://ben-siu.monday.com/docs/5031507115). **Decision that unblocked this doc:** Ben,
2026-09-23, on W07-0002: *"happy with the recommendation"* — accept the 2.2% G8 residual, no
Norgate upgrade, proceed to the spec.

Amendments are marked **PRE-RUN** or **POST-RUN**. A threshold changed after seeing a result
is a new hypothesis and spends from the budget in §9.

---

## 0. PRE-RUN GATES — the backtest does not start until all of these are true

| # | Gate | Status |
|---|---|---|
| **G1** | Construction: market-relative, long-only. | **Decided 2026-09-14.** Score return minus the equal-weight universe return over the same holding period, never outright directional. |
| **G2** | Cost measured from live IBKR quotes, full quoted spread modelled. | **Provisionally cleared** at 5.46 bps all-in (one session, 2026-09-18). Two more sessions are running now (W07-0001, Ben, hands-on). **This spec may be built and run, but no headline number from it is final until W07-0001 closes G2.** |
| **G8** | Point-in-time universe, not today's ticker list. | **Accepted 2026-09-23** at a 2.2% residual (35 of 1,622 membership spells with no usable price history — `var/swing_pit/suspects.csv`). The 434 no-start-date spells that had already exited are treated as members for their whole window, the same conservative assumption `pit_universe.py` makes. |
| **New — hindsight guard** | On date *t* the strategy sees only the membership as constituted on *t*: no name enters the eligible set before its `start` date in `membership.csv`, none stays after its `end` date. | **Not yet built.** Mutation-tested before the backtest runs (shift a membership date by one day, the test must fail), the same shape as TL-v0's G5. |
| **New — universe file guard** | The backtest refuses `membership.csv` with the 35 `suspects.csv` spells still in it, and refuses any file that is not the one W07-0002 published. | **Not yet built.** Per `PROGRAM_INDEX` §4: "a published count belongs to a universe file, not to a strategy." |

---

## 1. The hypothesis, in one sentence

**Short-term cross-sectional reversal — long the worst-performing decile of the point-in-time
S&P 500/400 universe over the trailing K days, equal-weighted, held N days, scored against
the equal-weight universe return over the same N days — is positive after the measured
5.46 bps round-trip cost, with financing charged separately and never assumed away.**

This is the first candidate, not the only one. It was chosen over momentum because: (a) 2–20
trading days is the classic short-term-reversal window in the literature (Jegadeesh 1990,
Lehmann 1990), not the momentum window (3–12 months); (b) it is a natural fit to the G1
decision already made — market-relative, long-only — without inventing a new construction;
and (c) the pre-flight's own §7 dispersion measurement (top/bottom-decile spread 14–20% at
N=5–10) is exactly the spread a cross-sectional selector, not a directional one, would try to
capture. It is registered as a first cell, not a preferred one — §9 reserves budget for
momentum and other constructions on the same universe.

---

## 2. The rule, fixed here

**None of this comes from a fit to any return.** Every number below is either carried over
from the pre-flight/G2 (spread by time bucket, financing rate, dispersion) or set by
convention (decile, equal weight) before any P&L exists.

### 2.1 Universe

Point-in-time S&P 500 + S&P 400 constituents, `var/swing_pit/membership.csv`, **excluding**
the 35 spells flagged in `var/swing_pit/suspects.csv` (verdict `none` or `suspect_reuse`) —
the accepted G8 residual. A name is eligible on date *t* only if some membership spell for it
covers *t* (§0, hindsight guard). Price history: EODHD daily, as validated in W07-0002.

### 2.2 Ranking signal

Trailing K-trading-day cumulative simple return, computed at the close of day *t*, over the
**eligible** universe on day *t*. **K = 5 is the deployed spec** (matches the base-case N=5
hold, §2.4). **K = 10 is a reported neighbour.** No K is chosen by search; both are reported,
neither is ranked above the other except by the criteria in §4.

### 2.3 Entry — side, selection, and the registered parameter (entry time of day)

- **Side: long only** (G1). No short leg exists in this candidate.
- **Selection:** the bottom decile of eligible names by the K-day trailing return (the
  biggest recent losers). A day with fewer than 10 eligible names in the bottom decile takes
  whatever the decile contains; a day with none in the count band is a no-trade day, and every
  no-trade day is counted, not silently skipped (§3).
- **Entry time of day — this task's registered parameter.** `swing_g2_RESULT_20260919.md` §3
  measured a 2.7x spread swing across the session (09:30 7.98 bps -> 15:30 2.96 bps). A
  candidate that assumes an open fill and prices it at the pooled median is quietly wrong by a
  factor of two. Three buckets are registered, each paying **its own bucket's measured
  spread**, not the pooled 3.65/5.46 bps figure:

  | Bucket | Time | Quoted spread (§3) |
  |---|---|---:|
  | `open` | 09:30 ET | 7.98 bps |
  | **`midday`** (deployed) | 11:30 ET | 3.61 bps |
  | `close` | 15:30 ET | 2.96 bps |

  **`midday` is the deployed spec.** It avoids the most expensive half hour while remaining a
  same-day, mechanically simple rule: the signal is known at the *previous* close, and the
  order is placed at a fixed clock time the next session — no intraday monitoring, no same-bar
  look-ahead. `open` and `close` are reported neighbours, not candidates competing to be
  chosen after the fact.

### 2.4 Hold and exit

**Ensemble over N in {5, 10, 20} trading days**, each sleeve sized at one third of the
per-trade risk budget (the same ensemble-over-family convention as TL-v0 §2.1, and the §4
standard: *prefer an ensemble to a chosen parameter*). N=5, 10, 20 are also reported alone.
G5 (horizon floor, N >= 5) is satisfied by construction — no N below 5 is registered.

Exit at N trading days after entry, at the **same time bucket's price** (e.g. a `midday`
entry exits at `midday`, N sessions later). **No stop and no target inside the holding
period.** A time-based exit with an added stop is a different rule and a new registration
(§7).

### 2.5 Sizing and financing

- **Cash-funded is the base case** (G3, and the G2 result's corrected arithmetic: at 2:1,
  financing grows with N at almost the rate the move does, cancelling the horizon advantage —
  this is exactly why a longer-N sleeve must not be leveraged by default).
- Equal weight across the day's decile, each name capped at **min(1 / decile size, 10%)** of
  the risk budget, so a thin-decile day cannot concentrate the book into two or three names.
- **2:1 levered figures are computed and reported alongside every result, at IBKR AU's
  measured 7.13%/yr charged per day held, and are never the headline** (G3, §4).

### 2.6 Friction — three levels, per §4's standard, adapted to swing's own cost unit

MCL's $1.00 / $4.26 / $8.92 ladder is a different strategy's measured friction and does not
transfer. Swing's own three levels:

| Level | Value | What it is |
|---|---:|---|
| **Measured** | **5.46 bps** | The pooled G2 figure — reported, not the entry basis (superseded by the bucket-specific figure at deployment). |
| **Bucket-specific** | 7.98 / 3.61 / 2.96 bps by entry time | §2.3 — this is what the deployed cell actually pays, both legs. |
| **Stress** | **2x the bucket figure** | A conservative multiplier for a volatile session the one-session G2 measurement has not yet seen (§6 of the G2 result: "this is the reason to call G2 provisionally cleared rather than closed"). |

Commission (IBKR tiered, both legs) is added on top of spread at every level, per
`swing_preflight_20260914.md` §3.3.

---

## 3. What every run must emit

1. **Net market-relative return** (return minus the equal-weight universe return over the
   same N) at all three friction levels (§2.6), cash-funded headline with 2:1-levered
   reported beside it, never the headline (G3).
2. **Both halves**, split at the median date of the sample, split not swept (G6).
3. **Every calendar year**, none omitted.
4. **drop-top-N by name**, N = 1, 3, 5 (`n/a`, not `$0`, if the decile ever has N or fewer
   names on the relevant days).
5. **Cluster bootstrap by calendar month**, 2,000 resamples, seeded. Per `PROGRAM_INDEX` §4:
   on a single-instrument-class study the cluster is the calendar month, because volatility
   clusters and treating overlapping-window days as independent overstates significance.
6. **The random-decile control**: on each day, a same-sized decile drawn at random from the
   eligible universe (not by rank), same N, same costs, same time bucket, 2,000 seeded draws.
   This is the selection control — it answers whether *being long a random slice of this
   universe, market-relative* already does the work, before the reversal ranking is credited
   with anything.
7. **The full K x N x bucket grid, unranked, and the ensemble** — no "best cell" table (G7).
   Two K values x three N values x three buckets = 18 cells; the deployed ensemble sits inside
   it and every other cell is reported beside it, not below a ranking.
8. **Counts**: eligible names per day, decile size per day, no-trade days (and why),
   hindsight-guard rejections (must be exactly zero — a nonzero count is a defect, not a
   result), the 35 excluded G8 residual spells never entering a signal.
9. **Coverage in the same pass**: names covered, first/last date per name, and the population
   check against `var/swing_pit/membership.csv`'s own published counts (`PROGRAM_INDEX` §4: "a
   published count belongs to a universe file").

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — all of it, for the deployed cell (K=5, `midday`, N-ensemble)

1. **Positive market-relative return after costs at the bucket-specific friction**,
   cash-funded, full sample.
2. **Both halves positive** at the same friction (an empty half fails, same as a sign flip).
3. **drop-top-3 by name** still positive.
4. **Cluster-by-month bootstrap: total > 0 in >= 95%** of resamples.
5. **Beats the random-decile control** at the same friction, same universe, same N — failing
   this means the "reversal" is just being long this universe, market-relative, and closes the
   study whatever else passes.
6. **No single year and no single name supplies more than 50% of net.**
7. **The ensemble is not beaten by the single best K/N/bucket cell** — guards against a result
   that only looks good because one cell of eighteen was quietly favoured.
8. **Still positive at the 2x stress friction level.**

K=10 and the `open`/`close` buckets are scored against the same bar and reported, but
**cannot spend the holdout** in this registration — the deployed cell is the only holdout
candidate.

---

## 5. Pre-flight — no P&L, run before the backtest, training side only

Before a single dollar of P&L is computed (mirrors TL-v0 §5 and the original pre-flight's own
method):

- Eligible-universe size per day, and decile size per day (is there ever a day with under 5
  eligible names in the bottom decile — if so, how often, and what the rule does on it).
- Hindsight-guard test suite green (synthetic membership series, mutation-checked: shifting a
  `start`/`end` date by one day must break the guard).
- Count of days the universe-file guard would refuse (should be zero against the published
  W07-0002 file).
- Distribution of decile turnover day to day (how much the bottom-decile membership churns,
  since a K=5 signal is noisy and a report should say so before it is read as evidence).

**If, on more than 10% of trading days, the bottom decile contains fewer than 5 names, the
study is reported with that as a finding — "the point-in-time universe is too thin for a
decile rule on more than 10% of days" — not worked around by widening the decile after seeing
the number.** That is this spec's version of TL-v0 §5.1's pre-registered stop rule.

---

## 6. The holdout

**A new, swing-only cut: `holdout_swing.json`.** Locked at the **last 20% of trading days in
the point-in-time sample by date** (2016-05-10 -> 2026-09-23 per `var/swing_pit/`), fixed now,
before this spec's first result exists. Refuses `--limit` and every narrowing flag, the same
way `holdout.split_sessions` and `holdout_spy.json` do; a mutation-checked test asserts the
refusal fires. **Spent once, by the deployed cell only** (K=5, `midday`, N-ensemble). Neither
`holdout.json` (intraday) nor `holdout_spy.json` (SPY-IM) governs this study, and this file
does not govern them.

---

## 7. Registered as NOT to be done

- Adding a stop or target inside the N-day hold after seeing a result. That is a new rule and
  a new registration.
- Swapping K, N, or the entry-time bucket for the ensemble after seeing per-cell returns.
- Widening the decile, or relaxing the eligible-universe count floor, after the pre-flight
  shows thin days — that is §5's finding, not a parameter to tune around.
- Substituting today's constituent list for the point-in-time file on the grounds that it is
  "close enough."
- Using price history from any of the 35 `suspects.csv` spells.
- Re-cutting `holdout_swing.json` after a near miss, or after G2 closes with a different
  number.
- Reporting a headline number as final while W07-0001 (G2's second and third session) is still
  open — this spec's results are provisional in the same sense G2 itself is provisional.

---

## 8. Ways this could go wrong

- **The hindsight guard is the single highest-risk piece of new code here.** A point-in-time
  universe is only worth building if nothing downstream of it peeks. Mutation-tested before
  the first real run, same discipline as TL-v0's G5.
- **The 2.2% G8 residual is small but not zero.** Sensitivity check: re-run with the 35
  suspect spells' available (if any) partial price history included as "member, no price
  before X" and confirm the verdict in §4 does not flip. If it does, the residual is not
  immaterial and G8 needs revisiting before this spec is trusted.
- **Delisting return is not modelled.** A name that exits the index mid-hold (acquisition,
  bankruptcy) needs an assumption for its exit price; the naive one (last available close) is
  optimistic for a bankruptcy and this is stated as a caveat, not solved, in the first run.
- **K=5 reversal on a 5-day hold is close to microstructure noise, not information.** The
  pre-flight's own §2 finding — MFE adds no information below N=10 — is a caution that a
  5-day cross-sectional signal may be dominated by bid-ask bounce rather than genuine reversal;
  the random-decile control (§3 item 6) is the check that would catch this, because bounce
  affects the ranked decile and a random decile equally.
- **The bucket-specific spread is a G2 provisional number from one session.** If the second
  and third sessions (W07-0001) move the by-bucket table materially, this spec's cost basis
  needs re-checking before any run here is called final (§7, last item).
- **Multiplicity.** 18 cells (2 K x 3 N x 3 bucket) is a real grid even with the ensemble
  absorbing most of it. §9 fixes the budget so a second candidate cannot silently reuse this
  grid's look.

---

## 9. Multiplicity budget

Families: **entry-time bucket** (one, `midday` deployed), **hold horizon N** (one, ensembled
over {5,10,20}), **lookback K** (one, two neighbours, {5,10}). **Three families.** Budget:
**two further registered hypotheses** on this line before it needs a reason that does not
begin with a result — for example, a volatility- or liquidity-conditioned variant of the same
reversal signal, or a momentum construction on the same point-in-time universe.

---

## 10. A prediction, written down now

**The deployed cell clears criteria 1–4 and 6 (there is genuine short-term reversal in this
universe, and it is not concentrated in one name or year) and fails criterion 5 — it does not
beat the random-decile control** — because market-relative scoring already removes most of
what a long-only decile earns over the index, and the pre-flight's own dispersion figures
(§7 of the pre-flight) are a perfect-hindsight upper bound, not a demonstrated selectable
edge. If that is what happens, the reading is: *this universe has cross-sectional dispersion,
and a simple reversal rank does not yet capture more of it than chance.* K=10 is expected to
do somewhat better than K=5 on criterion 5, because five days is closer to microstructure
noise than ten.

---

## 11. PRE-RUN amendment (2026-09-25) — W07-0011 news filter on SWING-v0 picks

**Committed before any SWING-v0 result exists** — W07-0010's backtest (`strategy/swing/reversal_v0.py`,
the hindsight guard, the pre-flight) has not yet run. Per the header above, this is an
**add-on** to the registration, not a new hypothesis: it does not spend one of the §9
multiplicity-budget slots, and SWING-v0's deployed rules (§§1–8) are unchanged by it. A
filtered (NO-NEWS-only) version of the deployed cell must still clear §6 (the holdout) on its
own before it can trade — this amendment does not pre-approve it.

**Origin:** W07-0011 (board), design at `claude/w07_0011_news_check_design_20260925.md`. Ben
asked whether the "TradingAgents" multi-agent AI hedge-fund video could benefit the project;
verdict on that framework was no (too slow, non-deterministic, not backtestable), but one idea
from it was worth testing here: check *why* a stock moved before trading it. Motivated by
Chan (2003), "Stock price reaction to news and no-news": the short-term-reversal bounce this
spec is built to capture (§1) is reported to come mostly from no-news drops, while news-driven
drops tend to keep drifting. **Chan (2003) is from older data and a different universe — it
motivates this test, it is not evidence for this universe.**

### 11.1 Population

Every SWING-v0 pick in the deployed cell (K=5, `midday` 11:30 ET entry, N-ensemble {5,10,20}),
§§2–4. Same universe files (`var/swing_pit/membership.csv`, less the 35 `suspects.csv`
spells, §2.1), same costs (bucket-specific + 2x stress, §2.6), same market-relative scoring
(§2, §3 item 1) as the base spec. This amendment adds a label to each pick; it does not change
how a pick is selected, sized, or scored.

### 11.2 The news tag (Step 1 — no AI)

A pick is tagged **NEWS** if, between the start of its K-day drop and its entry time, at least
one of the following exists, timestamped strictly before entry:

- A Benzinga headline (via Alpaca) tagged to that symbol, **excluding any headline tagged to
  more than 5 symbols** (market wraps and "stocks moving" lists, which would otherwise tag
  almost every name).
- An SEC filing of type 8-K, 10-Q, 10-K, or 424B* for that company, accepted before entry.
  Acceptance time is Eastern and DST-aware — the same check as W03-0010's G2(d).

Otherwise the pick is tagged **NO NEWS**. Every timestamp compared must be strictly earlier
than the entry time. The join is point-in-time and mutation-tested the same way as the §0
hindsight guard: shifting a headline or filing timestamp by one day must be able to flip a
tag's bucket, or the test fails.

### 11.3 What every Step-1 run must emit

Per bucket (**ALL**, **NEWS**, **NO NEWS**), mirroring §3's format:

1. Trades, winners, gross $, costs, net $, market-relative net $ — full sample, each half
   (§3 item 2, split at the same median date), and at 2x-cost stress (§2.6).
2. The share of picks falling in each bucket.
3. Sample trades, listed per bucket.
4. Negatives in brackets throughout (project convention).

**Lopsided-split rule:** if either the NEWS or the NO-NEWS bucket holds under 10% of picks,
the split is reported as **"too lopsided to read"** and is not scored against §11.4 — the
result is still reported, not silently dropped, and W07-0011 closes on that finding.

### 11.4 Pass bar for Step 1 — fixed here, before any run

All three of:

1. NO-NEWS net $ per trade exceeds ALL-picks net $ per trade, on the full sample **and** in
   both halves.
2. A NO-NEWS-only version of the deployed cell passes §4 items 1–4 and 8 on its own (positive
   after costs; both halves positive; drop-top-3 still positive; cluster-by-month bootstrap
   >= 95%; still positive at 2x-cost stress).
3. The NO-NEWS filter keeps at least 40% of the deployed cell's trades.

**If met:** proceed to §11.5 (Step 2) and, separately, to the §6 holdout for a NO-NEWS-only
cell. **If not met:** W07-0011 closes with the Step-1 result and no AI spend happens.

### 11.5 Step 2 — AI classifier (only if §11.4 passes)

For each NEWS-tagged pick, Claude (Haiku — the cheapest available model — first) reads that
pick's headlines and returns one fixed label: earnings/guidance · analyst downgrade ·
offering/dilution · legal/regulatory/FDA · management change · M&A · sector/market-wide ·
routine/no real news.

**Look-ahead controls**, guarding against the model "remembering" the outcome from its
training data: the company name and ticker are masked as "the company", dates are removed, no
prices are shown, and the prompt asks only for the cause, never the outcome. Temperature is 0
and every answer is cached to disk, so reruns are identical. Results are reported separately
for the slice **after the model's training cutoff** — the only slice the model cannot have
seen.

**Keep the AI only if** "NO NEWS + routine/no real news" (AI-cleared) beats the §11.4 NO-NEWS
filter, both in both halves **and** on the post-cutoff slice.

**Cost and spend gate:** the script prices the run first and requires `--confirm` (project
convention). Step 1's NEWS count sets the real price; **Ben approves the spend before Step 2
runs.** Rough estimate at design time: under US$150 (Haiku, Batch API, ~100k unique headline
sets x ~1k tokens) — not final until priced against the actual Step-1 NEWS count.

### 11.6 Registered as NOT to be done (extends §7)

- Lowering the 10% lopsided-split threshold, the 40%-trades-kept floor, or the Benzinga
  5-symbol cap after seeing a result.
- Treating a "too lopsided to read" split as a pass or a fail — it is neither, and closes the
  study.
- Running Step 2 before Step 1 clears §11.4, or before Ben approves the priced spend.
- Un-masking the company name/ticker or showing prices/dates to the Step 2 classifier.
- Spending the §6 holdout on anything but the deployed NO-NEWS-only cell, once and only once.

### 11.7 Caveats (extends §8)

- Benzinga's headline coverage of S&P 400 mid-caps is not measured here; Step 2 reports the
  share of NEWS-tagged picks with any headline, by year.
- "News" as tagged in §11.2 includes harmless items (conference appearances, dividend
  notices) — Step 1 deliberately does not tell these apart; that is Step 2's job.
- SWING-v0 itself (§4) has not been run yet. If the full deployed cell fails its own §4 bar,
  this amendment's split is still reported, because a NO-NEWS-only cell could pass where the
  whole does not — but it still must clear §4 and §6 on its own (§11.4 item 2).

### 11.8 Why not the TradingAgents framework itself

12 agents and about 8 minutes per ticker, while SWING-v0 needs a verdict on about 90 names a
day; it gives different answers on reruns; cost scales per ticker per day with no IBKR link;
and its output is Buy/Hold/Sell, not "why did it drop?". One fixed prompt through the
Anthropic SDK (already used by the Python screener, §11.5) does that job more cheaply and
testably.

---

## Next steps

- **Build `strategy/swing/reversal_v0.py`, the hindsight guard, and the universe-file guard**,
  tests first, before any run. Suggested session: **Sonnet, medium effort** (parallel logic to
  `pit_universe.py`, no new data source). Unaffected by §11 and can proceed in parallel.
- **Run the pre-flight (§5) first**, training side only, no P&L.
- **Do not treat any P&L headline from this spec as final until W07-0001 closes G2.**
- **§11 (W07-0011):** build the news tagger and point-in-time join (board subitem 2), mutation
  test it, then run the tagged backtest (subitem 3) and write the Step-1 result (subitem 4)
  before the NO-NEWS-only cell can spend §6's holdout.
- Board: raise the build task as its own item once this spec is registered (see reply).
