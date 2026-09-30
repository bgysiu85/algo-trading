# REGISTERED — CHARTMARK-S v3: CHARTMARK-S v2 with one condition removed (B1, "price was already below EMA9")

**Committed before any CHARTMARK-S v3 code exists, before its pre-flight or G6 is run, and before any count or return has been computed on bars before 2025-09-08.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0042** (sub 1 = this file; sub 2 = Ben commits it; sub 3 = build + free gates; sub 4 = backtest). Separate from CHARTMARK-S v1 (`REGISTERED_chartmark_short_v1.md`, closed FAIL, criteria 5 and 6) and from v2 (`REGISTERED_chartmark_short_v2.md`, closed at G6, never scored). Costs: IBKR (W15-0033).

Ben's decision, 2026-09-30, in his words: **"go with B"** — i.e. register a v3 that relaxes B1, after being told that v2's G6 fidelity check failed on his 11 Sep mark, that the relaxation is a new hypothesis fitted to one seen bar, and that W15-0038 applies.

---

## 0. Where this sits, stated plainly

- **Honest origin.** v3 exists because **v2 failed its own G6 check on seen bars**. v2's engine took none of the 8 entries Ben rejected and filled his 9 Sep 22:00 entry exactly (96.25), but did **not** fill near his 11 Sep 01:00 entry (about 102.09). The cause was one condition, **B1** (close[t−1] < EMA9[t−1], "price was already below EMA9"): on 11 Sep the 00:00 bar rallied to EMA9 and closed below it with the MACD histogram negative, but the bar before it had closed *above* EMA9. B1 was part of the mechanical coding of "retest" in v2 (§2.1); it is **not in Ben's words** ("*IF MACD is negative, i would wait until price is below EMA9 on a retest*"; his note on that trade: "*I would have entered 11 Sep 01:00 below EMA9 instead*"). Removing it is a **fidelity correction that was found by looking at a seen bar**. It is not a reason that stands apart from a result, and `W15-0038` (a further version needs a reason that does not begin with a result) is met only in this narrow sense: the reason is Ben's stated method, not a P&L. Ben proceeds knowing that.
- **What v2 produced.** No P&L was ever computed for v2. Its count-only pre-flight (G2, 2026-09-30) gave 4,208 base fills on the training side (Tier A 3,067, Tier B 1,141), against a registered prediction of 400–1,500: the prediction was wrong, and the filter removes far less than expected because Tier A persists after a fresh 20-bar high. v3 makes Tier B **larger**, so v3 will trade **more** than v2.
- **Data already seen.** The training bars 2010-06 → 2021-12 were read by v1, v2's pre-flight (counts only), CHARTMARK-v1/v2 (long) and other lines. Multiplicity is met by: every number below is **fixed now with no grid selection**; criterion 6 stays at **p99**; the **holdout is the only evidence that counts** (§6); and this is the **third** short-side version tested against the same bars, which the reader should discount for.
- **What it changes.** **Only Tier B's condition B1 is removed.** Everything else — X1, Tier A, B2, B3, B4, the order machine (E1–E5), the backstop, the exits (P0 cut, P1 retest), costs, sizing, controls, the grid, the criteria and the holdout — is **v2's, word for word** (`REGISTERED_chartmark_short_v2.md` §2–§6 and its Amendment 1, interpretations K1–K7; v1 §2.2–§2.6, §3–§6, Amendment A beneath it).
- **Fidelity caveat.** "Downward trend", "retest" and "MACD below signal" are Ben's judgement; this tests a mechanical coding, not his eye. Two of his ten marks are all it has been checked against.

---

## 1. The hypothesis, in one sentence

**Selling CL 1H on a stop under the prior bar's low after a fresh 20-bar top, but only once EMA9 is below EMA21, or, if EMA9 is still above EMA21, only on a bar that rallies to EMA9 and closes back below it while the MACD histogram is negative (whether or not the bar before it was already below EMA9), with v1's EMA9 cut and retest exits, makes money after IBKR costs on the owned GLBX 1H history, beats a 20/10 Donchian short channel on the same bars, and beats the 99th percentile of random short entries of the same count.**

---

## 2. The rules — CL 1H, short only

Thresholds fixed now. Times New York. ATR = ATR(14) Wilder. Tick = 0.01. All values at bar t use closes up to and including t.

### 2.1 Context (at the close of bar t, for an order working in bar t+1)

| | v3 rule | Change from v2 |
|---|---|---|
| **X1 Fresh top** | the highest high of bars t−19…t was made within the last **16** bars | none |
| **X4 Flat** | no open position | none |
| **Tier A — crossed** | EMA9[t] **<** EMA21[t] | none |
| **Tier B — rally and close back below** (EMA9[t] ≥ EMA21[t]) | all of: **B2** high[t] ≥ EMA9[t] − 2 ticks (the bar rallies to EMA9) · **B3** close[t] < EMA9[t] (and closes back below it) · **B4** MACD(12,26,9) histogram[t] < 0 (MACD below its signal line) | **B1 removed** (v2 also required close[t−1] < EMA9[t−1]) |

Context holds when **X1 and (Tier A or Tier B)** and X4. Each trade is tagged with the tier true on its context bar (A if EMA9 < EMA21, else B) exactly as v2 K4. Tier B now uses only bar t, so every v3 Tier B context is a superset of v2's.

### 2.2 Entry, backstop, exits, costs
**Unchanged from `REGISTERED_chartmark_short_v2.md` §2.2 and v1:** E1 sell-stop at low[t] − 1 tick; E2 re-set each bar while context holds; E3 cancel 6 bars after first placement; E4 fill min(level, open); E5 re-arm rules; backstop = highest high of the 20 bars ending at the entry bar + 1 tick; exits P0 / P1; IBKR costs (MCL $0.77 / $1.77 / $2.77 per side at low / mid / high). Interpretations J1–J10 (v1) and K1–K7 (v2) apply, except K2's clause "Tier B needs bar t−1", which no longer applies.

### 2.3 Reported variants (never ranked, cannot spend the holdout)
| Variant | Change | Tells us |
|---|---|---|
| **V-A** | Tier A only | the cross alone (identical to v2's V-A) |
| **V-B** | Tier B only | the rally-and-close-below tier alone |
| **V-B1** | Tier B with B1 restored (v2's base) | what B1 was doing: v2's base rule, scored for reference |
| **V-RANGE / V-SESSION / V-AVOID** | as v2 | as v2 |

**Not coded / not in this registration:** any further loosening or tightening of Tier B; a different histogram test; wicks, volume, flat-EMA judgement; longs; any change of exits; target; adds.

---

## 3. What every run must emit
As v2 §3 (fills and trades by tier with gross, costs, net at low / mid / high, W/L, per year; tier shares of context bars), with **C1** Donchian 20/10 short and **C3** random short entries (1,000 seeded draws `np.random.default_rng([crc32(str(d)), crc32("CL-S3"), N])`, p5 / p50 / p95 / **p99**), the 27-cell neighbour grid (unranked), CHARTMARK-S v1 base and v2 base (**V-B1**) beside them as reference only, and the seen window (2025-09-08 →) "seen — not evidence".

---

## 4. The bar to clear — base, training side (2010-06 → 2021-12), 1 MCL, IBKR mid
As v2 §4, unchanged: 1 net > $0 at mid · 2 both halves > $0 · 3 drop-top-1 and drop-top-2 years > $0 · 4 bootstrap by year (2,000 seeded) net > 0 in ≥ 95% · 5 beats C1 on net and on net per unit of daily volatility · 6 **beats C3 p99** on net · 7 no single year > 50% of net · 8 net > $0 at high friction · 9 at least 18 of 27 grid cells > $0 · 10 at least 150 trades. **Failing 5 or 6 closes the study.** A variant that passes when the base does not is a new registration, not a rescue.

---

## 5. Before the backtest — no P&L in this section
| # | Gate |
|---|---|
| G1 | Data: as v2 (CL 1H archive cut to sessions before 2022-01-01 before resample / back-adjust) |
| G2 | Count-only pre-flight by tier and per year. **Fewer than 150 fills → stop.** Runner refuses any exit price or P&L flag |
| G3 | Ledger `holdout_chartmark_short_v3.json`, own file, refuses limit / narrowing / other candidates (v1's and v2's ledgers by name) / a second spend; records v1 Amendment A.2's two excluded windows |
| G4 | Look-ahead guards, each broken by a one-bar shift in a test: Tier B now uses bar t only; P0/P1 levels use EMA9[j−1]; the poke high is recorded after its bar closes |
| G5 | IBKR costs at three levels; CHARTMARK-S v1 and v2 tests stay green |
| G6 | **Seen-window fidelity, same ten marks, same tolerances as v2** (v2 Amendment 1 K6): the engine takes **none** of the 8 rejected entries (8 Sep 08:00, 8 Sep 22:00, 9 Sep 00:00, 9 Sep 13:00, 9 Sep 20:00, 10 Sep 19:00, 10 Sep 21:00, 14 Sep 01:00, 2026, ±1 bar), **does** fill at 9 Sep 22:00 (within 2 ticks of 96.25) and at 11 Sep 01:00 (within 0.25 of 102.09), ±1 bar. **If G6 fails again the study closes.** There is no v4 under this registration: the rule is not adjusted to make it pass |

**Stated before the run:** removing B1 makes the 11 Sep 00:00 bar a Tier B context (I read its values while diagnosing v2, so I expect the second accepted mark to pass). The real test is whether any of the 8 rejected entries now fills.

---

## 6. The holdout
Training 2010-06 → 2021-12-31. Holdout 2022-01-03 → 2025-09-07, own ledger, **spent once**, by the base only, **only if all ten criteria pass**; trades entered in 2025-02-19 → 2025-03-04 and 2025-06-22 → 2025-07-03 are excluded and listed separately (v1 Amendment A.2). Variants never spend it. Seen window 2025-09-08 on: never scored.

---

## 7. Registered as NOT to be done
- Tuning any threshold to the training result, to Ben's charts, or to anything from 2022 on.
- Promoting a variant or a grid cell into the base after a result.
- Changing the exits, adding a target, adds, news, a higher-timeframe filter or longs under this registration.
- Adjusting Tier B further if G6 fails; a G6 failure closes the study.
- Quoting gross, a variant, or the seen window as the headline.
- Spending the holdout on anything but a full ten-of-ten pass of the base.

## 8. Ways this could go wrong
- **Weaker filter, more trades.** v2 already left 60% of v1's fills; v3 keeps more. The confirmation filter may barely differ from v1 in practice, and v1 lost ($28,532) per 1 MCL on 6,997 trades.
- **Fitted to two marks on seen bars.** B1's removal is justified by one entry Ben marked. It reproduces his stated reasons, not evidence of an edge.
- **Same bars, third version.** Three short rules have now been scored or counted against the same training history.
- **Regime.** Confirmed downtrends (2014–15) may carry the total; criterion 7 guards.

## 9. Multiplicity budget
One primary hypothesis (the base), one variant family (V-A, V-B, V-B1, V-RANGE, V-SESSION, V-AVOID), one holdout spend. v2 was never scored, so it spends no multiplicity; v1 was, and is not counted as a rescue.

## 10. A prediction, written down now
**The base fills 4,300–6,000 trades on the training side (more than v2's 4,208, less than v1's 6,997), Tier A still about 3,000 of them, with a win rate near one in three. At mid friction I expect it negative; I give it under one-in-four odds of beating random p99. G6: I expect the second accepted mark to pass and give one-in-two odds that at least one of the eight rejected entries is now filled. I would be glad to be wrong.**

---

## Next steps (board)
- **W15-0042 sub 2** — Ben: commit this file to `docs/research/` (commands on the subitem).
- **W15-0042 sub 3** — Build & test chat: remove B1 (thin layer over `strategy/chartmark_s2`), own ledger, G2 pre-flight, G6 re-run, tests (Sonnet / Medium).
- **W15-0042 sub 4** — Build & test chat: training backtest vs C1, C3, variants, grid → Result doc, only if G2 and G6 clear (Sonnet / Medium).
