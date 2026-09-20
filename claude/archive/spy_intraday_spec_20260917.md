# SPEC — SPY intraday momentum (H-S1 / H-S2), pre-registration draft — 2026-09-17

> **Read this first.** This is the first strategy in the project with a
> **published, peer-reviewed, independently replicated** mechanism behind it.
> It is also the first one whose out-of-sample status is **actively contested**.
> Both facts are load-bearing, and §2 is not optional reading.
>
> **Nothing is built or run yet.** This document is the registration.

Author: research chat. Build: the build chat. No program logic under `D:\Trading`
was changed to write this.

---

## 1. The mechanism and where it comes from

Gao, Han, Li & Zhou, *Market Intraday Momentum*, **Journal of Financial
Economics** 129 (2018) 394–414. Sample **1993-02-01 → 2013-12-31**, SPY.

The claim: the **first half-hour return predicts the last half-hour return**.

| definition | |
|---|---|
| `r1` | prior day's **close (16:00)** → **10:00** today. *Includes the overnight gap.* |
| `r12` | 15:00 → 15:30 (second-to-last half hour) |
| `r13` | **15:30 → 16:00** — the traded window |

Reported, full sample:

| | |
|---|---:|
| annualised return (r1 timing) | **6.67%** |
| standard deviation | 6.19% |
| Sharpe | **1.08** |
| directional hit rate | **54.37%** |
| net of spreads, post-2005 sub-period | 6.52%, Sharpe 1.00 |

Where the paper says predictability **concentrates** — this matters more than
the headline, see §6:

| condition | R² |
|---|---:|
| first half-hour volatility **low** | 0.6% |
| first half-hour volatility **high** | **3.3%** |
| expansion | 1.0% |
| recession | **6.6%** |
| non-release day | 2.5% |
| **FOMC minutes day** | **11.0%** |

FOMC days: 20.04% annualised vs 6.24% otherwise. The pattern replicates across
10 major ETFs (QQQ, DIA, IWM, EEM…), R² 1.16%–8.54%.

**Why this is categorically different from everything in this project so far.**
MCL, MC5, VW9, pullback_break v1–v6, ORB and MA-TREND were all patterns observed
in videos or charts and then coded. This is a documented statistical regularity
with a stated economic mechanism (late-day hedging demand and infrequent
rebalancing by leveraged and target-date funds), published in a top-three finance
journal, and replicated across instruments and countries by other authors. That
does not make it true **today**. It makes it worth a registered test.

---

## 2. The out-of-sample problem — the thing most likely to kill this

The paper's sample **ends in 2013**. Two independent readings of what happened
since:

**Against.** An analysis of **1,085 SPX sessions, 2022-04-14 → 2026-08-20**
reports the unconditional effect is **gone**: slope **+0.006, t = +0.6**, flat in
every individual year with alternating signs. Its argument is that the sample
pre-dates the 0DTE options regime that now dominates index closes. One exception
survived: on **short-gamma dealer closes** (~15% of sessions) the slope was
**+0.055, t = +3.1**.
*Caveat: a blog analysis, not peer-reviewed; it tests SPX (index, not the ETF)
and uses a `rest-of-day → last 30 min` predictor, which is a **variant** of `r1`,
not `r1`. Treat as a serious warning, not a settled refutation.*

**For.** Concretum Group (2024, SSRN N°24-97) reports **19.6% annualised, Sharpe
1.33, 2007 → early 2024** on SPY using a more elaborate form — volatility-since-open
"noise bands", VWAP trailing stop, volatility-targeted sizing, ~43% win rate.
*Caveat: a commercial research group promoting its own paper; an independent
review flags instant-fill assumptions, no cross-market out-of-sample, and a
convex low-hit-rate payoff that is fragile to parameter change. More moving parts
than the original = more fitting surface.*

**The honest synthesis, and the reason for the cell structure in §7:** the
*unconditional* effect looks weak-to-absent in the modern era; the surviving
evidence on both sides points at a **conditional** effect that lives in
high-volatility / high-dealer-hedging-demand sessions. The paper's own R² table
said the same thing in 2018. So H-S2 is not a rescue filter invented after a
failure — it is **pre-registered here, before the run, as the mechanism the
literature actually describes**.

That distinction is the whole difference between this and the VW9 salvage
attempt.

---

## 3. The rule, exactly

**H-S1 (primary) — unconditional.**

```
At 10:00:00 ET      r1 = close(10:00) / close(prior 16:00) − 1
At 15:30:00 ET      if r1 > 0   -> LONG  SPY
                    if r1 <= 0  -> SHORT SPY
At 16:00:00 ET      flat, unconditionally. No overnight position, ever.
```

One position per session. One session per trade. No stop, no target, no trailing
— the exit is the clock. **Deliberate:** every discretionary exit mechanic tested
in this project has cost money, and adding one here would confound the test of
the predictor.

**H-S2 (secondary) — volatility-conditioned.** Identical, plus a gate:

```
sigma1 = realised vol of the 09:30–10:00 window (sum of squared 1-min returns)
Trade only if sigma1 >= the 67th percentile of sigma1 over the trailing 252 sessions.
```

Trailing percentile, **point-in-time**, never full-sample — a full-sample
percentile is look-ahead and would be exactly the defect the `first_entry_skip`
and `screen_itch` work was built to avoid.

**Long-only variant (reported, not scored):** H-S1 with shorts suppressed.
Registered now so that if H-S1 passes and the short leg turns out to be the
problem, the variant is not a post-hoc rescue.

### 3.1 The short side is fine here — this is not the small-cap short problem

The project's standing finding is *short selling not feasible*: borrow 54–1,000%,
$0.08/share sunk locate fees, 2× margin, IBKR Error 201 refusing opening trades.
**All of that was measured on low-float small caps.** SPY is among the most
liquid, easiest-to-borrow instruments in existence; borrow is a few tenths of a
percent annualised and the position is held **30 minutes**, so the borrow cost is
arithmetically negligible (~0.0004 bps). Ben should confirm short permission is
enabled on the account, but no result here should be discounted for borrow.

---

## 4. Universe and data

**Instrument:** SPY only for the test. QQQ and IWM are run as **breadth
controls** (§8.4), not as additional cells to pick from.

**Bars needed:** four prices per session — prior close, 10:00, 15:30, 16:00 —
plus 1-minute bars inside 09:30–10:00 for `sigma1`.

**Minimum viable window: 2015-01-01 → present** (≈2,900 sessions). This is not the
paper's sample and does not attempt to re-run it; it is the window that answers
the question that matters — *does this work in the era Ben would trade it*, which
includes the 0DTE regime §2 identifies as the threat. Longer history is welcome
if cheap, and 2005→present would allow a genuine replication leg, but the test
does not depend on it.

**Sources, in order of preference:**

1. **IBKR historical** (`common/data_ib.py` already wraps `reqHistoricalData`).
   30-minute `TRADES` bars reach back years; 1-minute is limited to roughly six
   months, so `sigma1` needs either a second source or a 5-minute proxy —
   **register which before running.**
2. Databento. The subscription already covers `XNAS.BASIC` / `EQUS.MINI`. SPY is
   NYSE Arca-listed but heavily traded on Nasdaq, so `XNAS.ITCH` trades are fine
   for a *price at a timestamp*; they are **not** fine for volume-based
   conditioning (§8.3 notes this).
3. Alpha Vantage intraday history is a **premium** endpoint on the current key —
   confirmed unavailable 2026-09-17.

**Known data traps, carried forward from this project's own scars:**

- **Timestamps.** The screened MCL book stores `entry_time` in **UTC** while
  reading as if it were ET. Every timestamp in this study is **ET**, stated in the
  column name (`ts_et`), and the first check in §12 is a boundary assertion that
  10:00 and 15:30 bars land where they should across **both** DST transitions.
- **Half-day sessions.** The US market closes at 13:00 ET roughly 9 times a year
  (day after Thanksgiving, Christmas Eve, July 3…). There is **no 15:30 bar**.
  These sessions are **excluded**, and the count of exclusions is reported. A
  silent `NaN` here would quietly drop the most unusual sessions in the sample.
- **Adjustment.** SPY pays quarterly dividends. `r1` spans a close-to-open
  boundary, so it must be computed on a **consistently adjusted or consistently
  unadjusted** series — mixing them puts a spurious ~0.4% jump into `r1` four times
  a year, always with the same sign. VW9 lost its entire headline to exactly this
  class of error (trading the adjustment factor).

---

## 5. Friction — measured, at Ben's actual account size

SPY closed **754.05** on 2026-09-16. A USD 10,000 account buys **13 shares**
unlevered = **$9,802.65** notional.

| component | $ per round trip | bps of notional |
|---|---:|---:|
| IBKR tiered commission, 2 orders, **minimum binding** | 0.70 | 0.71 |
| SEC + FINRA TAF (sell side) | 0.28 | 0.29 |
| spread, crossing 1 cent | 0.13 | 0.13 |
| **total** | **0.98 + 0.13 = 1.11** | **1.13** |

Annual drag at 252 sessions: **2.86% of notional.**

**The commission minimum is a small-account tax.** 13 shares × $0.0035 = $0.046
of marginal commission, but the $0.35 order minimum charges 7.6× that. It stops
binding at 100 shares:

| account | shares | friction / RT | annual drag |
|---|---:|---:|---:|
| **$10,000** | 13 | **1.13 bps** | **2.86%** |
| $25,000 | 33 | 0.70 bps | 1.75% |
| $50,000 | 66 | 0.55 bps | 1.39% |
| $75,400 | 99 | 0.51 bps | 1.28% |
| $150,000 | 198 | 0.51 bps | 1.27% |

**Friction ladder for the study — three levels, per this project's standard:**

| level | bps RT | what it represents |
|---|---:|---|
| optimistic | **0.55** | ≥100 shares, passive or mid fills |
| **realistic (primary)** | **1.15** | Ben's account today, crossing the spread |
| pessimistic | **2.50** | wider spread into a volatile 15:30, partial fills, slippage |

A result that only survives at the optimistic level is a **NOTHING**.

---

## 6. Pre-flight arithmetic: does the published edge clear the friction?

This is the calculation that should have been done before MCL was ever built.

The paper's 6.67%/yr at a 54.37% hit rate implies an average absolute last-half-hour
move of **0.303%** over 1993–2013 (a sample containing 2008). Expected value per
trade is `(2·hit − 1) × |move|`, minus friction:

| cell | trades/yr | gross | net of 1.15 bps | %/yr | **$/yr on $9,803** |
|---|---:|---:|---:|---:|---:|
| unconditional, paper-era volatility | 252 | 2.65 bps | **1.51 bps** | 3.81% | **$373** |
| unconditional, calmer regime (0.20%) | 252 | 1.75 bps | **0.61 bps** | 1.54% | **$151** |
| high-vol tercile (0.50%, 57%) | 84 | 7.00 bps | **5.87 bps** | 4.93% | **$483** |
| high-vol tercile, calmer (0.40%, 56%) | 84 | 4.80 bps | **3.67 bps** | 3.08% | **$302** |

**Three things follow, and they should be read before any code is written.**

1. **The unconditional rule is marginal, not comfortable.** Friction is
   **43% of gross** at $10k. That is better than MCL (where friction was ~75% of
   the average win and gross was *negative*), but it is not a wide margin. In a
   calm regime it nearly vanishes.
2. **The conditional rule is where the margin is**, and the literature said so in
   2018 — before anyone needed it to be true. Fewer trades, more per trade, less
   exposure. This is the single reason to expect a different outcome from the
   last year of work.
3. **The dollars are small, and that is arithmetic, not pessimism.** A *perfect*
   replication of the published result earns roughly **$370 a year** on $10,000.
   The strategy is in the market **30 minutes a day — 2% of the time** — so it
   produces a high Sharpe on a tiny exposure. At 3.8%/yr net it would take
   **USD 4.1M** for this sleeve alone to produce AUD 20k/month.

Point 3 is not an argument against building it. It is the argument for building
it as **a validated process to compound and scale**, which is what the five-year
plan actually is, and for not expecting it to be an income.

---

## 7. What gets scored — the cells, named now

The MA-TREND spec carried 800 cells. That is a multiplicity problem dressed as
thoroughness. This spec has **two scored cells and one control**:

| | cell | status |
|---|---|---|
| **H-S1** | unconditional r1 → r13, long and short | **PRIMARY** |
| **H-S2** | H-S1 gated on `sigma1` ≥ trailing 67th pctile | **SECONDARY, pre-registered** |
| **H0** | same trade dates and sizes, **random sign** | control, 10,000 draws |

Reported but **not scored**, and explicitly not eligible for promotion without a
new registration: long-only; `r1` measured at 10:05/10:15; entry at 15:25/15:35;
the `r1 AND r12` double-filter from the paper; 50th/75th/90th percentile
`sigma1` thresholds.

Anything found in the reported-not-scored set that looks good gets a **new
registration and a fresh window**. It does not get promoted inside this study.

---

## 8. The gates

### 8.1 The five (the `gate_study` standard)

At the **realistic** friction level, H-S1 (and separately H-S2) PASSES only if
**all five** hold:

1. mean net per trade **> 0**, and the annualised figure **> 0**;
2. **both temporal halves** of the window positive, split at the median session;
3. **drop-top-3 and drop-top-5 sessions** — still positive, on level *and* on
   delta vs. H0;
4. **cluster bootstrap** (block = calendar month, to respect volatility
   clustering) — 95% CI lower bound above zero;
5. beats the **95th percentile of the H0 random-sign distribution**.

Any one failing → **NOTHING**. There is no partial credit and no "directionally
encouraging".

### 8.2 One trade per session — a genuine simplification

Every prior study in this project has had to report **two denominators** (per
trade and per symbol-day) and refuse when they disagreed. Here there is exactly
**one trade per session on one symbol**, so the denominators are identical by
construction. That removes a whole class of ambiguity and is a real argument for
this design over a multi-name book.

### 8.3 Mechanism test (§8.3 of `source_videos`, applied)

`sigma1` is a *proxy* for hedging demand / dealer positioning. The mechanism test
says: add the explicit version of what the proxy claims to capture and see whether
the result moves materially.

- **Explicit version available cheaply:** first-half-hour **dollar volume** relative
  to its own trailing median. The paper reports predictability rising across volume
  terciles independently of volatility.
- **If `sigma1` and the volume version give materially different answers, neither
  is doing what it claims** and the conditional cell is not adoptable on this
  evidence.
- **Data caveat, registered now:** if volume comes from `XNAS.ITCH` it is Nasdaq
  share only, not consolidated. Either source consolidated volume or report the
  test as **not run** — do not run it on a partial denominator and call it a
  mechanism test. *A control whose output is indistinguishable from the failure it
  detects is not a control.*

### 8.4 Breadth control

Run H-S1 unchanged on **QQQ** and **IWM**. The paper reports the effect on both.
If SPY passes and QQQ/IWM show nothing, the SPY result is a **single-instrument
fluke** and is refused regardless of its own statistics. This is the cheapest
available guard against having fitted one series.

### 8.5 Boundary check

Report H-S1 at `r1` measured 10:00 / 10:05 / 10:15, and entry at 15:25 / 15:30 /
15:35 — a 3×3 surface. **A result that is positive at 15:30 and negative at 15:25
and 15:35 is fitted to the clock, not to a mechanism**, and is refused. The
published effect should degrade smoothly, not sit on a spike.

### 8.6 DST and holiday assertions

Assert, before any P/L is computed: every included session has bars at exactly
10:00, 15:30 and 16:00 ET; both DST transitions each year are represented; all
half-days are excluded and counted. Fail loudly.

---

## 9. Holdout

The existing `holdout.json` (`lock_from: 2026-01-12`) governs the **small-cap
universe** and does not apply here.

Create **`holdout_spy.json`** before the first run:

- **Locked: the most recent 20% of sessions.** On a 2015→present window that is
  roughly 2024-10 → present, ≈580 sessions.
- Fingerprint the session list and record `cut_at`.
- **The holdout is opened exactly once**, only after H-S1 or H-S2 has PASSED all
  five gates on the training window, and the result of opening it is **final** —
  no re-specification afterwards, no "one more variant".

Given §2's warning that the effect may have died specifically in the recent era,
the recency of the holdout is a feature: it is precisely the period the skeptical
analysis says should fail.

---

## 10. Registered prediction

Recorded **before the run**, per §4 of `PROGRAM_INDEX`:

- **H-S1 (unconditional): NOTHING.** Expected to be positive-but-marginal on the
  full window, and to fail either the both-halves gate or the drop-top-5 gate,
  with the 2022+ portion flat. Confidence: moderate. Reason: §2's out-of-sample
  reading, and the fact that friction is 43% of gross at this account size.
- **H-S2 (volatility-conditioned): the coin-flip, and the reason to run this at
  all.** Expected per-trade net +2 to +5 bps, roughly 80–90 trades/year. Genuinely
  uncertain whether it clears all five gates. Confidence: low, and deliberately so
  — a prediction registered at low confidence is what an honest open question
  looks like.
- **H0 control:** indistinguishable from zero. If H0 shows a positive edge, the
  harness is wrong, not the market.
- **Breadth:** if H-S2 passes on SPY, QQQ is expected to agree in sign. If it does
  not, refuse.

**If both cells return NOTHING, that is a complete and useful answer**, it is
reached in a few days of work on four prices per session rather than months, and
it closes intraday equity for this project with a published mechanism rather than
a homemade one — which is a materially stronger closing argument than any of the
six `pullback_break` NOTHINGs.

---

## 11. Sizing, and what live trading would actually look like

**Research phase:** 1 unit of notional. Sizing is irrelevant to whether the
predictor works and should not be entangled with it.

**Live at USD 10,000:** 13 shares, unlevered, ~$9,800 notional. A 1-sigma
last-half-hour move (0.25%) is **±$25**. Max realistic daily loss on a 3-sigma
move ≈ $75. This is a **small, survivable** position — which at this stage is the
point.

**The MES alternative, for later.** One Micro E-mini S&P contract is $5 × index
≈ **$37,700** notional — **3.8× a $10,000 account**. Round-trip cost ≈ $2.49
(commission + exchange/regulatory + 0.25-point spread) = **0.66 bps**, cheaper
than SPY at Ben's size, with no PDT question and no commission minimum penalty.
But a 1-sigma move becomes **±$94 = 0.9% of the account**, and size can only move
in whole contracts. **Do not switch to MES to fix a friction problem — it fixes
friction by adding 3.8× leverage.** Revisit only after a PASS, and size it from
the measured volatility rather than from what the account can margin.

**PDT is not a constraint:** the rule was eliminated 2026-06-04, which is what
makes a once-a-day round trip on a $10k account possible at all.

---

## 12. Build order

1. **Data and assertions first.** Pull the window; run §8.6 boundary, DST and
   half-day assertions; report session count and exclusions. **Stop here and show
   the numbers** before computing any P/L.
2. Compute `r1`, `r13`, `sigma1`. Report the distribution of `|r13|` by year — this
   directly tests the §6 assumption that the average absolute move is ~0.2–0.3%,
   and if it is materially smaller the whole arithmetic changes and the study
   should be re-registered before running.
3. Run **H0** first. A control that does not come out flat means stop.
4. Run **H-S1**, then **H-S2**. Five gates each, at all three friction levels.
5. Boundary surface (§8.5), mechanism test (§8.3), breadth control (§8.4).
6. Write `claude/spy_intraday_RESULT_<date>.md` with the verdict, and only then
   consider the holdout.

Deliverables follow the project's convention: raw `.txt` report to
`D:\Trading\Claude outputs`, plus a published artifact page with negatives
bracketed and red.

---

## 13. Go / no-go

**Adopt** only if a cell clears all five gates at the **realistic** friction level,
passes the boundary surface, agrees with the breadth control, and then survives the
holdout being opened once.

**Refuse** on any single gate failure. In particular: a cell that passes only at
the optimistic friction level is a NOTHING, and a cell that passes on SPY alone
while QQQ and IWM show nothing is a NOTHING.

**If adopted:** paper-trade for six months against live fills before a single
dollar is risked, per the five-year schedule. The gap between backtest and live
is where this project has lost most of its money so far — MC5 has been running a
different exit rule live than in the backtest since 2026-09-10 (see
`claude/mc5_apex_live_split_20260917.md`), and that defect was found by reading a
screenshot, not by a test.

---

### Sources

- Gao, Han, Li & Zhou, *Market Intraday Momentum*, JFE 129 (2018) 394–414 — https://www.sciencedirect.com/science/article/abs/pii/S0304405X18301351 · SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866
- Concretum Group, *Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)*, SFI N°24-97 — https://www.sfi.ch/en/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy
- Independent review of the above — https://quantmacro.substack.com/p/paper-review-an-effective-intraday
- Out-of-sample measurement, 1,085 SPX sessions 2022–2026 (blog, not peer-reviewed) — https://dev.to/firmtape/intraday-momentum-is-dead-in-the-0dte-era-we-measured-it-on-1085-spx-sessions-43g0
- SPY quote 2026-09-16: 754.05 (Alpha Vantage `GLOBAL_QUOTE`)
