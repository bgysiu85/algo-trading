# Handover to the build chat — SPY intraday momentum (H-S1 / H-S2)

Paste the block below into the build chat.

---

## Message to the build chat

We are opening a new strategy line: **SPY intraday momentum**, from
Gao/Han/Li/Zhou, *Market Intraday Momentum*, Journal of Financial Economics 129
(2018). This is the first mechanism in this project with peer-reviewed,
independently replicated evidence behind it, and the first whose out-of-sample
status is actively contested. Both matter.

**The full pre-registration is `claude/spy_intraday_spec_20260917.md` in the
project. Read it before writing code — this message is a summary, not the spec.**

### The rule

```
10:00 ET   r1 = close(10:00) / close(prior 16:00) − 1     # includes the overnight gap
15:30 ET   r1 > 0  -> LONG SPY ;  r1 <= 0 -> SHORT SPY
16:00 ET   flat, unconditionally
```

One trade per session, one symbol. No stop, no target, no trail — the exit is
the clock, deliberately, so the test is of the predictor and nothing else.

**H-S1 (primary):** the rule as written.
**H-S2 (secondary, pre-registered):** the same, gated on `sigma1` (realised vol
of 09:30–10:00) ≥ the **trailing 252-session 67th percentile**, point-in-time,
never full-sample.
**H0 (control):** same dates and sizes, random sign, 10,000 draws.

Everything else — long-only, 10:05/10:15, 15:25/15:35, the `r1 AND r12` double
filter, other percentile thresholds — is **reported, not scored**, and cannot be
promoted without a new registration on a fresh window.

### Window and data

**Minimum viable: 2015-01-01 → present**, ≈2,900 sessions. Not the paper's
sample; deliberately the era Ben would actually trade, which includes the 0DTE
regime that the skeptical evidence says killed the effect. Longer is welcome,
not required.

Four prices per session (prior close, 10:00, 15:30, 16:00) plus 1-minute bars
inside 09:30–10:00 for `sigma1`. `common/data_ib.py` already wraps
`reqHistoricalData`; note IBKR gives ~6 months of 1-minute, so `sigma1` needs a
second source or a registered 5-minute proxy — **decide and register which
before running.** Alpha Vantage intraday history is a premium endpoint on the
current key (confirmed unavailable 2026-09-17).

### Three data traps, all of which have already bitten this project

1. **Timestamps are ET**, named `ts_et`. The screened MCL book stores
   `entry_time` in UTC and was read as ET. Assert 10:00/15:30/16:00 bars land
   correctly across **both** DST transitions every year.
2. **Half-days close at 13:00 ET** (~9/year) and have **no 15:30 bar**. Exclude
   them and report the count. A silent NaN would drop the most unusual sessions
   in the sample.
3. **Dividend adjustment.** `r1` spans a close-to-open boundary. Use a
   consistently adjusted *or* consistently unadjusted series — mixing them
   injects a spurious ~0.4% jump into `r1` four times a year with the same sign.
   VW9 lost its entire headline to this class of error.

### Friction ladder

SPY at 754.05; a USD 10,000 account is 13 shares = $9,803 notional.

| level | bps RT | |
|---|---:|---|
| optimistic | 0.55 | ≥100 shares, passive/mid fills |
| **realistic (primary)** | **1.15** | Ben's account today, crossing the spread |
| pessimistic | 2.50 | wide 15:30 spread, partial fills, slippage |

The IBKR $0.35 order minimum is a small-account tax at 13 shares — 7.6× the
marginal per-share rate — and stops binding at 100 shares. A result that survives
only at the optimistic level is a NOTHING.

### Gates — the `gate_study` five, at the realistic level, all required

1. mean net per trade > 0 and annualised > 0
2. both temporal halves positive, split at the median session
3. drop-top-3 **and** drop-top-5 sessions, on level **and** delta vs H0
4. cluster bootstrap, **block = calendar month** (volatility clusters), 95% CI
   lower bound above zero
5. beats the 95th percentile of the H0 random-sign distribution

Plus three refusals that are independent of the five:

- **Boundary surface (§8.5):** `r1` at 10:00/10:05/10:15 × entry at
  15:25/15:30/15:35. Positive at 15:30 but negative either side = fitted to the
  clock, refuse.
- **Breadth control (§8.4):** run H-S1 unchanged on QQQ and IWM. The paper
  reports the effect on both. SPY passing alone = single-instrument fluke,
  refuse.
- **Mechanism test (§8.3):** `sigma1` is a proxy for hedging demand; add the
  explicit version (first-half-hour dollar volume vs trailing median) and see
  whether the answer moves. **If volume is only available from `XNAS.ITCH` it is
  Nasdaq-share, not consolidated — report the test as NOT RUN rather than run it
  on a partial denominator.**

One trade per session on one symbol means the per-trade and per-symbol-day
denominators are identical by construction. That removes the two-denominator
ambiguity every prior study in this project has had to carry.

### Holdout

`holdout.json` (`lock_from: 2026-01-12`) governs the small-cap universe and does
**not** apply. Create **`holdout_spy.json`** before the first run: most recent
**20%** of sessions locked (≈2024-10 → present on a 2015 start), session list
fingerprinted, `cut_at` recorded. Opened **once**, only after a cell has cleared
all five gates on the training window, and the result is final.

### Build order

1. Data + assertions (DST, half-days, boundary). **Stop and report session
   counts and exclusions before computing any P/L.**
2. Compute `r1`, `r13`, `sigma1`. **Report the distribution of `|r13|` by year.**
   The spec's economics assume an average absolute last-half-hour move of
   0.2–0.3%; if it is materially smaller the arithmetic changes and the study
   must be re-registered before running.
3. H0 first. If the control is not flat, stop.
4. H-S1, then H-S2, five gates, three friction levels.
5. Boundary surface, mechanism test, breadth control.
6. `claude/spy_intraday_RESULT_<date>.md`, raw `.txt` to `D:\Trading\Claude
   outputs`, artifact page with negatives bracketed and red. Holdout only after.

### Registered prediction (on the record, pre-run)

- **H-S1: NOTHING.** Positive but marginal overall, failing either both-halves or
  drop-top-5, with the 2022+ portion flat. Moderate confidence.
- **H-S2: genuinely uncertain**, +2 to +5 bps/trade, 80–90 trades/year. Low
  confidence, deliberately — this is the open question.
- **H0:** flat. If H0 shows an edge, the harness is wrong, not the market.

### Two notes that change how results should be read

**Shorting SPY is fine.** The project's "short selling not feasible" finding
(borrow 54–1,000%, sunk locates, IBKR Error 201) was measured on **low-float
small caps**. SPY borrow is a few tenths of a percent annualised on a
**30-minute** hold — arithmetically negligible. Do not discount the short leg.

**The dollars are small and that is arithmetic, not pessimism.** A perfect
replication of the published 6.67%/yr earns roughly **$370/year on $10,000**,
because the strategy is exposed 30 minutes a day — 2% of the time. This is being
built as a validated process to compound and scale, not as an income. Please do
not let that tempt anyone into leverage, a second entry per day, or MES-instead-
of-SPY as a "friction fix" — MES is cheaper per round trip but only by adding
3.8× leverage on a $10k account.

### Also queued for this chat

`claude/mc5_apex_live_split_20260917.md` — MC5's `evaluate_last_bar` never reads
`USE_APEX_EXIT`, so live has been running apex ON since 2026-09-10 while every
published MC5 figure is apex OFF. Same defect MCL had and fixed on 2026-09-08.
One-line fix plus a test; details in that doc.

---

*(End of message to the build chat.)*
