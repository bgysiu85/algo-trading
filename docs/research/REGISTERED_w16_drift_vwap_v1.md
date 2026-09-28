# REGISTERED — W16 DVP-v1: Conti's literal drift-VWAP pullback on NQ, out-of-sample 2024-01-02 → latest

**Committed before any NQ bar dated 2024-01-02 or later has been read by this project for this rule.** It follows
the DVP-v0 result (`claude/w16_0006_drift_vwap_RESULT_20260928.md`) and Ben's decision on W16-0010. This is a **new
hypothesis**: it spends **1 of the 2** further hypotheses in DVP-v0 §11, and **the DVP holdout window**
(`holdout_w16_dvp.json`, candidate `DVP-v1-NQ`). DVP-v0's own scored cell failed and never spends it.

**Board:** W16-0010 (decision), W16-0012 (this study). **Chat:** Scalping chat.
**Ben's decision, 2026-09-28 (multiple choice):** *"B: Test 2024→today"*.

---

## In plain terms

DVP-v0 showed that Conti's rule, coded exactly as he describes it, reproduces his numbers in 2020–2023, the years he
tuned it on, but did not make money in 2010–2019. He also claims it kept working **out-of-sample from 2024 to
2 August 2026**. We have NQ bars for that period and have never run this rule on them. This test runs his exact rule
(80-point stop, 40-point long target, 50-point short target, 5-min trigger, his daily limits) on 2024-01-02 → the
latest bar, once, and scores it. It answers one question: **does his published out-of-sample claim hold on our data
at our costs?** It does not undo DVP-v0's 2010–2019 failure. A pass is a reason to consider paper trading under a new
registration, not to trade it live.

---

## 1. The hypothesis

**Conti's literal rule on NQ makes money per 1 NQ at L2 (NinjaTrader Free fees + 1 tick per market or stop fill)
over 2024-01-02 → the latest bar, in both halves of that window, and its choice of side beats a random side on the
same entries.**

## 2. The rule — exactly DVP-v0 §3 in its literal-points form (the §7.3 replication block)

- Everything in DVP-v0 §2–§3 (15-min VWAP and C1–C3 at 0.10%, 5-min opposite-colour trigger, fill at the next 5-min
  open, fills 10:30–15:30, flat at 15:55, early-close times, max 4 trades, stop after the 2nd losing trade of the
  session), **except the stop and targets, which are fixed in points, not scaled:** long 80 / 40, short 80 / 50.
- Code: `strategy.w16.drift_vwap.generate_dvp_trades(..., p_ref=None, loss_rule="total", trigger_minutes=5)`, the
  same call as DVP-v0's replication block (commit 048e65a). No code in the rule path changes.
- Contract: **1 NQ** is the headline, because Conti quotes 1 NQ. Per 1 MNQ (÷ 10 on points, MNQ fees) is shown beside it.
- XNYS trading days only; the window runs to the last complete session in the archive.

## 3. Costs

DVP-v0 §3.5 / SB-v0 Amendment A, unchanged. NQ: $2.87 per side all-in, tick $5.00. MNQ: $0.94, tick $0.50.
L2 is the scored level.

## 4. Pass bar — all must hold (per 1 NQ, L2, the whole window)

1. Net > $0.
2. Both halves net > $0 (split at the median trade date).
3. Net > $0 at L3 (+2 ticks).
4. Bootstrap by calendar month (2,000 seeded resamples): net > 0 in ≥ 95%.
5. Net per MNQ > the p95 of **C-D3** (the same entries and exits with the side chosen by a seeded coin, 1,000
   draws). C-D1 is **not** used for scoring: W16-0011 found its design borrows hindsight.
6. At least 300 trades. Fewer → NOT READ. (Expected about 1,800.)

**Reported, never scored:**
- Win rate, average win, average loss and trades per day beside Conti's 64% / $866 / ($1,300) / ~2.8.
- By year. 2024-01-02 → 2026-08-02 (the window he claims) and 2026-08-03 → latest, separately.
- **C-D1-after:** the same side and exits, with the entry at a random 5-min open **at or after** the real fill
  time on the same day (the W16-0011 fix). 1,000 draws; p5 / p50 / p95.
- DVP-v0's price-scaled rule (P_ref 13,034.25) on the same window, per MNQ.
- Exit reasons, same-bar ties, 20 sample trades, and the account view at $22,129 per 1 MNQ.

## 5. Guards

- The run is **refused unless `--confirm-spend` is passed**. It writes `holdout_w16_dvp.json` with candidate
  `DVP-v1-NQ` before any bar is read. The ledger is committed after the run.
- Only dates ≥ 2024-01-02 are read for scoring. No training-side figure is recomputed here.
- It is run once. A re-run after a code fix is a POST-RUN amendment that says why.

## 6. Prediction, written now

The rule is **net positive per NQ at L2** over the window, with a win rate of 60–65%. 2024–26 was a strong,
volatile NQ period, like 2020–22. I expect it to **fail at least one of criteria 2, 4 or 5**. My guess is the month
bootstrap, because about 33 months with a rule whose average win is two-thirds of its average loss is a thin sample.
I'd be glad to be wrong.

## 7. Not to be done

- Scaling, tuning or filtering the rule after seeing the result.
- Treating a pass as a live-trading signal. The next step on a pass is a paper-trading registration (W02-style).
- Reading 2024+ for any other W16 rule through this ledger.
