# REGISTERED — CHARTMARK-v2: Ben's momentum-trigger CL 1H long (anticipating buy-stop above the last red body, EMA21 two-breach exit, $0.60 backstop)

**Committed before any CHARTMARK-v2 code runs on the training archive and before its pre-flight.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run. Board: **W15-0036**. Parent line: W15-0032 (CHARTMARK-v1, closed FAIL 2026-09-30).

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a training result is a new hypothesis.

---

## 0. Where this comes from — stated plainly, because it is not clean

1. **CHARTMARK-v1 failed** on the same training bars (2010-06 → 2021-12): 2,670 trades, net ($13,422) per 1 MCL at IBKR mid, criteria 5 and 6 failed (`claude/w15_0032_chartmark_long_backtest_RESULT_20260930.md`). v2 is written **after** that result and after Ben inspected its trades.
2. **Exploratory in-sample numbers were seen before this registration** (`Claude outputs/w15_0032_explore_ema21_hold.py`, 2026-09-30, on v1's entries): exit on the 2nd close below EMA21 within 4 bars → net ($4,083); with a "fresh EMA cross ≤ 3 bars" entry filter → **+$974 on 299 trades, 10 of 12 years positive**. Those runs shaped the questions put to Ben. That is a real multiplicity cost; §4 and §6 are the guard, not the training net.
3. **The rules below come from Ben's own description of how he reads the chart**, given 2026-09-30 on his trades of 31 Aug and 1 Sep 2026 (seen window). His words:
   - Entry: *"Most of the time i would prefer when EMA9 crosses over EMA21 and MACD is on an upward trend, i.e. closing the gap between it and the signal line. But given that EMA9 is already above EMA21, or rather running in parallel for a while, I used the MACD to judge and I can see that when MACD crossed above the Signal line, the EMA9 and EMA21 gap started to widen as well."*
   - Skip (31 Aug): *"The EMA9 is above EMA21 all the time and MACD is positive for half a day and negative for the other half. So there is no clear indication that there is momentum."*
   - Small cross (1 Sep 00:00): *"the 00:00 cross was too small. It looks like it simply touched it and bounced back down."* — *"seems a bit loose at 0.05. can we test 0.05 and 0.03?"* — *"use the tighter setting as the main"*.
   - Entry price: *"i meant the open price of the 1:00 bar which was 87.01. so i would have bought around 87.05"* — *"go with anticipating"*.
   - Exit: *"it can be the second breach but because the MACD was already below the signal line for quite a few bars, i decided to exit on the first breach is lower risk"* — *"i think 5 bars or more. but it also depends if the rate of the widening of the gap is accelerating. if it's accelerating rapidly, then i would prefer 3 bars"* — *"let's use close as the main test"*, wick as a variant.
   - Stop: *"a breach of EMA21 would be a good indication"*; backstop *"we can widen the backstop to 60c as the main but i would like to test a variant if it's 20c as well"*.
   - Session: *"I didn't really consider which window. i was simply looking at the trend"*.
4. **Seen-window parity already checked (not evidence):** the rule as coded in `Claude outputs/w15_0036_v2_seen_proto.py` reproduces Ben's 1 Sep trade (entry 04:00 @ 87.02; exit 2 Sep 08:00 open @ 89.11 after the 07:00 close below EMA21 with MACD 8 bars below signal) and takes no trade on 31 Aug. On the whole seen year it takes 83 trades, 23 winners, +0.61 pts gross (≈ +$61 per MCL before ≈ $294 of costs). 28 of the 83 are anticipating orders whose cross never came.
5. **Multiplicity budget.** v2 is the one remaining hypothesis on the CHARTMARK long line. A v3 needs a reason that does not begin with a result.

---

## 1. The hypothesis in one sentence

**Buying CL 1H on a stop just above the top of the last red candle's body when a momentum turn is within reach (EMA9 about to cross or just crossing EMA21 with MACD rising, or — in an established EMA9-over-EMA21 trend — MACD about to cross its signal), keeping the trade only if the turn is confirmed at the fill bar's close, and exiting on a $0.60 backstop or on the EMA21 two-breach rule, makes money after IBKR costs on 2010–2021, beats a 20/10 Donchian channel and beats the 99th percentile of random entries with the same exits.**

---

## 2. The rules — CL 1H, long only, New York time, tick 0.01, ATR = ATR(14) Wilder, MACD(12,26,9), histogram H = MACD − signal, gap G = EMA9 − EMA21. All values at the close of the bar named; nothing from a later bar.

### 2.1 Arming (close of bar t → order working in bar t+1)

| | Condition |
|---|---|
| **A-early** (cross coming) | EMA9[t] ≤ EMA21[t]; (EMA21−EMA9) narrowed on each of the last 2 bars; H rising on each of the last 2 bars; (EMA21−EMA9)[t] ≤ 0.10·ATR[t] |
| **A-fresh** (cross done) | EMA9 has been above EMA21 for 1–3 bars ending at t; H[t] > H[t−1] |
| **B** (parallel trend, MACD cross coming) | EMA9 above EMA21 for ≥ **6** bars ending at t; H[t] > H[t−1]; −0.05·ATR[t] ≤ H[t] < 0 |
| **Level** | L = open of the most recent red bar (close < open) among bars t−9…t, **+ 1 tick**. No red bar in that span → no order. **L ≤ close[t] → no order** (a buy-stop must sit above the market). |
| **One position** | No order while a position is open. After an UNCONFIRMED exit (§2.3), no new order until the arming conditions have been false at one close. |

The order is re-evaluated at every close: it is kept (level re-computed) while any arming condition holds, cancelled otherwise. No session filter.

### 2.2 Fill
Buy-stop fills in the first bar j with high[j] ≥ L, at **max(L, open[j])**, plus the friction model's slippage.

### 2.3 Confirmation at the fill bar's close
| Arm | Confirmed if, at the close of the fill bar j |
|---|---|
| A-early / A-fresh | EMA9[j] > EMA21[j] and H[j] > H[j−1] |
| B | H[j] ≥ **θ**·ATR[j] with **θ = 0.05** (base) and G[j] > G[j−1] |
Not confirmed → **UNCONFIRMED exit at the open of j+1.**

### 2.4 Backstop
Sell-stop at **fill − $0.60**, live from the fill bar. In the fill bar it is taken as hit if low[j] ≤ backstop **and** open[j] < L (the low may have come after the fill); if the bar opened above L (gap fill) it is taken as hit whenever low[j] ≤ backstop. Fills at min(backstop, open) after the fill bar. Counted separately as BACKSTOP-fillbar.

### 2.5 EMA21 exit (from the bar after the fill)
A **breach** = close[k] < EMA21[k]. At a breach bar k, exit at the **open of k+1** if any holds:
1. another breach occurred in bars k−3…k−1 (**2nd breach within 4 bars**);
2. H < 0 on each of the **5** bars ending at k (MACD below signal ≥ 5 bars);
3. H < 0 on each of the **3** bars ending at k **and** the gap D = −H widened on each of the last 3 bars with each widening larger than the one before (accelerating).

A position is carried through a roll (two extra sides charged). Data end → exit at the last close.

### 2.6 Reported variants (fixed now, never ranked, cannot spend the holdout)
| Variant | Change |
|---|---|
| **V-θ03** | θ = 0.03 |
| **V-WICK** | breach = low[k] < EMA21[k−1]; the exiting breach fills at min(EMA21[k−1], open[k]) in bar k |
| **V-STOP20** | backstop $0.20 |
| **V-STOPATR** | backstop 1.0 × ATR at the arming bar |
| **V-SESSION** | orders only for bars opening 02:00–12:00 New York |
| **V-CONFIRMED** | no anticipating: arm only on a confirmed trigger at the close of t (A-fresh, or B with H[t] ≥ θ·ATR and H[t−1] < 0 and G widening); level as §2.1 but the order may fill at the next open |
| **V-AVOID** | CHARTMARK-v1 Amendment A.1's AVOID filter added to arming |

---

## 3. What every run must emit
Per year and in total, base and every variant: orders, fills, cancels, UNCONFIRMED exits, exits by type (BACKSTOP / BACKSTOP-fillbar / EMA21 by clause 1/2/3 / UNCONFIRMED / data end), arm type (A-early / A-fresh / B), trades, wins/losses, gross, costs, **net at low/mid/high**, per 1 MCL and 1 CL, average win and loss, largest loss, worst losing run, max drawdown, both halves.

**Controls — same bars, fills, costs:** C1 Donchian 20/10 long, no session filter (CHARTMARK-v1's C1 code). C3 random entries: per year the same count as the base, at the open of random bars where flat, exited by §2.4–§2.5 (no confirmation step), 1,000 seeded draws `np.random.default_rng([crc32(str(d)), crc32("CL-v2"), N])`; p5/p50/p95/**p99**. CHARTMARK-v1 base reported beside it.

**Neighbour grid (27 cells, unranked):** B parallel lookback {4, 6, 8} × backstop {$0.40, $0.60, $0.80} × EMA21 window {3, 4, 5}.

**Seen window** (2025-09-08 →): reported only, labelled "seen — not evidence"; Ben's 1 Sep trade listed beside the engine's.

---

## 4. The bar to clear — base, training side, 1 MCL, IBKR mid

Costs (Amendment A.3 of v1, IBKR Pro): MCL $0.77 per side + 0/1/2 ticks (low/mid/high); CL $2.37 + 0/1/2 ticks. Sizing 1 MCL headline, 1 CL reported, $10,000 account framing as v1.

Passes only if all hold:
1. Net > $0 at mid.
2. **Both calendar halves net > $0: 2010-06 → 2015-12 and 2016-01 → 2021-12.**
3. Drop-top-1 and drop-top-2 calendar years still > $0.
4. Bootstrap by year (2,000 seeded resamples): net > 0 in ≥ 95%.
5. Beats C1 on net and on net ÷ standard deviation of daily net.
6. **Beats the p99 of C3** on net.
7. No single year > 50% of net.
8. Net > $0 at high friction.
9. At least 18 of 27 grid cells net > $0.
10. At least **150 trades**. Fewer → NOT READ.

Failing 5 or 6 closes the study. A variant that passes when the base does not is a new registration, not a rescue.

---

## 5. Before the backtest — no P&L

| # | Gate |
|---|---|
| G1 | Data: CL 1H GLBX archive (W15-0002), cut to sessions before 2022-01-01 before resample/back-adjust (strategy.futbt.loading). |
| G2 | Count-only pre-flight: orders, fills, UNCONFIRMED, exits by type, arm types, per year. **< 150 fills → stop, back to Ben.** |
| G3 | Ledger `holdout_chartmark_v2.json`, refuses limit / narrowing / other candidates / a second spend; records v1 Amendment A.2's two excluded windows. |
| G4 | Look-ahead guards: truncation invariance on all variants and a one-bar-shift mutation test that must fail. |
| G5 | Costs as §4; CHARTMARK-v1 tests stay green. |
| G6 | Seen-window parity: the engine reproduces Ben's 1 Sep 2026 trade (entry bar 04:00 within 2 ticks of 87.02; exit 2 Sep 08:00 open) and takes no trade whose fill falls 30 Aug 18:00 → 31 Aug 23:59. |

## 6. The holdout
Training 2010-06 → 2021-12-31. Holdout 2022-01-03 → 2025-09-07, own ledger, **spent once, by the base only, only on a ten-of-ten pass**; trades with entries in 2025-02-19 → 2025-03-04 and 2025-06-22 → 2025-07-03 are excluded from scoring (v1 Amendment A.2). Seen window 2025-09-08 → never scored. CHARTMARK-v1 never touched this holdout.

## 7. Registered as NOT to be done
Tuning any threshold to the training result; promoting a variant or grid cell after a result; adding filters, targets, adds or shorts under this registration; quoting gross, a variant or the seen window as the headline; spending the holdout on anything but a full pass of the base.

## 8. Ways this could go wrong
- **Anticipating orders** fill before the turn is confirmed; UNCONFIRMED exits are small but many (28 of 83 in the seen year) and each pays full costs.
- **$0.60 backstop vs volatility:** $0.60 was ~1 ATR in 2026; in quiet years (ATR ≈ $0.20–0.30) it is 2–3 ATR, in 2020 it is a fraction. V-STOPATR is the check.
- **Fill-bar ordering:** a 1H bar can't show whether the low came before or after the fill; §2.4's rule is conservative and counted.
- **"Within reach" thresholds** (0.05 ATR for MACD, 0.10 ATR for the EMA gap, 6 bars of parallel trend, 10-bar red-body lookback) are Claude's coding of Ben's description, fixed now; the grid tests one of them.
- **Seen before:** see §0.2.

## 9. Prediction, written now
**Base: 400–900 fills on training; win rate 25–35%; net between ($4,000) and +$3,000; I give it about one chance in four of beating random p99.** UNCONFIRMED exits will be the most common exit type. V-STOP20 loses more than the base.

## Next steps (board)
- **W15-0036 sub 1** — Ben: read §2 and §8 (the "within reach" thresholds are Claude's coding); OK or PRE-RUN changes.
- **W15-0036 sub 2** — Build & test chat (Sonnet / Medium): engine, G2–G6, count-only pre-flight.
- **W15-0036 sub 3** — Build & test chat (Sonnet / Medium): training backtest → Result doc.

---

### Amendment 1 — PRE-RUN, 2026-09-30 18:25 (live trigger level; before any code, count or P&L on training)

Ben, 2026-09-30: *"for the confirmation part, what do you mean by the trade is kept? Because my idea is that the trade shouldn't be entered in the first place until it reach above 0.05"* — then, after seeing that on 1 Sep the cross only reached 0.05 ATR at about 87.67, *"ok then keep the 0.05 rule"*.

**1.1 Replaces §2.2–§2.3 for the base.** EMA9, EMA21, the MACD line, its signal and H are linear in the current price P of the bar being traded, so the lowest price at which each trigger condition holds *live* is known at the close of the arming bar t. The buy-stop level for bar t+1 is

L* = ceil-to-tick( max( red-body top + 1 tick, P-conditions + 1 tick ) )

where the P-conditions use bar t's EMA, MACD and signal values and **ATR[t]**:
- **B:** H(P) ≥ θ·ATR[t] (θ = 0.05 base, 0.03 in V-θ03); G(P) > G[t]; EMA9(P) > EMA21(P).
- **A-early / A-fresh:** EMA9(P) > EMA21(P); H(P) > H[t].

Fill at max(L*, open[t+1]) when high[t+1] ≥ L*. **There is no after-the-fill confirmation and no UNCONFIRMED exit in the base.** L* ≤ close[t] → no order. The arming conditions of §2.1 are unchanged. The order lives one bar and is recomputed at each close.

**1.2 New reported variant V-REDTOP** = the original §2.2–§2.3 (buy-stop at the red-body top + 1 tick, confirmation at the fill bar's close, UNCONFIRMED exit at the next open, re-arm only after a false close). V-CONFIRMED stays.

**1.3 G6 parity replaced.** The engine, started flat at the close of 1 Sep 2026 03:00, must fill in the 04:00 bar within 2 ticks of **87.69** and exit at the 2 Sep 08:00 open (89.11); it must not fill in the 1 Sep 00:00 bar (level 87.25 > high 87.09); and it takes no trade whose fill falls 30 Aug 18:00 → 31 Aug 23:59.

**1.4 Seen window, as re-run (not evidence), `Claude outputs/w15_0036_v2_seen_proto_live.py`.** Base: 98 trades, 20 winners, (1.39) pts gross ≈ ($139) per MCL before ≈ $347 of costs; exits EMA21 41 / BACKSTOP 37 / BACKSTOP-fillbar 20; arms A 78 / B 20. V-STOP20: 75 of 110 stopped inside the fill bar. Run as a whole, the rule enters on Fri 28 Aug 14:00 at 83.52 on an A trigger (EMA9 crossing EMA21, MACD rising) and holds to 2 Sep 08:00 (89.11), so it is already long on 1 Sep and does not take Ben's 04:00 entry.

**1.5 §9 prediction unchanged in range; UNCONFIRMED no longer exists in the base, so BACKSTOP will be the most common exit.**
