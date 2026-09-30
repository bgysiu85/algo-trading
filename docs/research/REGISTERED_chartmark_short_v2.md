# REGISTERED — CHARTMARK-S v2: CHARTMARK-S v1's rollover short, entered only on Ben's confirmation (EMA9 crossed below EMA21, or MACD below signal with a failed EMA9 retest)

**Committed before any CHARTMARK-S v2 code exists, before its pre-flight is run, and before any count or return has been computed on bars before 2025-09-08.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0039** (sub 1 = this file; sub 2 = Ben commits it; sub 3 = build + free gates; sub 4 = backtest). Separate from CHARTMARK-S v1 (`REGISTERED_chartmark_short_v1.md`, closed FAIL, criteria 5 and 6) and from the long side. Costs: IBKR (W15-0033).

Ben's decision, 2026-09-30, in his words (after marking up 10 of the last 30 v1 trades in `w15_0032_chartmark_short_last30_check.xlsx`):
- *"when trade was entered EMA9 was still above EMA21 and most of the time not on a downward trend. Price was also above EMA9."*
- *"IF MACD is negative, i would wait until price is below EMA9 on a retest. Best confirmation is when EMA9 crosses below EMA21"* — and, asked what "MACD is negative" means: *"sorry, i meant MACD below signal"* (histogram below zero).
- Rule shape chosen: **two tiers**. Retest = **the bar rallies to EMA9 and closes below it**. Exits: **unchanged from v1**.
- His 10 marks: 8 rejected with *"EMA9 was still above EMA21 and not downward trending"*; 1 taken (9 Sep 22:00, 96.25): *"Price dipped below EMA9 and MACD is negative"*; 1 rejected but he would have entered an hour later (11 Sep 01:00, ~102.09): *"below EMA9 instead"*.

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a result is a new hypothesis.

---

## 0. Where this sits, stated plainly

- **Honest origin.** This registration was requested **after CHARTMARK-S v1 failed** (net ($28,532) per 1 MCL, 6,997 trades, criteria 5 and 6 failed) and after Ben read 10 of its trades on seen bars. `W15-0038` records that a further version needs a reason that does not begin with a result. The reason here is a **fidelity** one: Ben's own method waits for confirmation and v1 did not code it (v1's context allowed EMA9 up to 0.25 ATR *above* EMA21 minus nothing, i.e. EMA9 above EMA21, and never looked at price against EMA9). It is still a request made after a failure, and Ben proceeds knowing that.
- **Data already seen.** The training bars 2010-06 → 2021-12 were read by v1 (short), CHARTMARK-v1/v2 (long) and other lines. Multiplicity is met by: every number below is **fixed now with no grid selection**; criterion 6 stays at **p99**; the **holdout is the only evidence that counts** (§6).
- **What it changes.** **Only the context / entry timing.** X1, the order machine (E1–E5), the backstop, the exits (P0 cut, P1 retest), costs, sizing, controls, the grid and the holdout are **v1's, word for word** (`REGISTERED_chartmark_short_v1.md` §2.2–§2.6, §3–§6, Amendment A).
- **Fidelity caveat.** "Downward trend", "retest" and "MACD below signal" are Ben's judgement; this tests a mechanical coding, not his eye.

---

## 1. The hypothesis, in one sentence

**Selling CL 1H on a stop under the prior bar's low after a fresh 20-bar top, but only once EMA9 is below EMA21, or, if EMA9 is still above EMA21, only on a bar that rallies to EMA9 and closes back below it while the MACD histogram is negative, with v1's EMA9 cut and retest exits, makes money after IBKR costs on the owned GLBX 1H history, beats a 20/10 Donchian short channel on the same bars, and beats the 99th percentile of random short entries of the same count.**

---

## 2. The rules — CL 1H, short only

Thresholds fixed now. Times New York. ATR = ATR(14) Wilder. Tick = 0.01. All values at bar t use closes up to and including t.

### 2.1 Context (at the close of bar t, for an order working in bar t+1)

| | Rule |
|---|---|
| **X1 Fresh top** | as v1: the highest high of bars t−19…t was made within the last **16** bars |
| **X4 Flat** | no open position |
| **Tier A — crossed** | EMA9[t] **<** EMA21[t] |
| **Tier B — retest** (EMA9[t] ≥ EMA21[t]) | all of: **B1** close[t−1] < EMA9[t−1] (price was below EMA9) · **B2** high[t] ≥ EMA9[t] − 2 ticks (the bar rallies to EMA9) · **B3** close[t] < EMA9[t] (and closes back below it) · **B4** MACD(12,26,9) histogram[t] < 0 (MACD below its signal line) |

Context holds when **X1 and (Tier A or Tier B)** and X4. v1's X2 (EMA9 ≥ EMA21 − 0.25 ATR) and X3 (histogram falling) are **removed**. Each trade is tagged with the tier true on its context bar (A if EMA9 < EMA21, else B). No session filter and no range gate in the base.

### 2.2 Entry, backstop, exits, costs
**Unchanged from `REGISTERED_chartmark_short_v1.md`:** E1 sell-stop at low[t] − 1 tick; E2 re-set each bar while context holds (a Tier B context lasts one bar, so its order lives one bar; a Tier A context may persist); E3 cancel 6 bars after first placement; E4 fill min(level, open); E5 re-arm rules, re-entry from an exit bar's close; §2.3 backstop = highest high of the 20 bars ending at the entry bar + 1 tick; §2.4 exits (P0 cut at EMA9[j−1] + 2 ticks before +1 A₀; P1 first poke tolerated, then min(EMA9[j−1] + 2 ticks, poke high − 1 tick)), A₀ = ATR at the last context bar; §2.5 IBKR costs (MCL $0.77 / $1.77 / $2.77 per side at low / mid / high). Interpretations J1–J10 of the v1 build apply.

### 2.3 Reported variants (never ranked, cannot spend the holdout)
| Variant | Change | Tells us |
|---|---|---|
| **V-A** | Tier A only | whether the cross alone (Ben's "best confirmation") carries it |
| **V-B** | Tier B only | whether the retest tier adds anything |
| **V-RANGE** | add close[t] in the top 40% of the 120-bar range (v1 definition) | as v1 |
| **V-SESSION** | add bar t opens 02:00–12:00 NY | as v1 |
| **V-AVOID** | add v1 Amendment A.1 AVOID filter | as v1 |

**Not coded / not in this registration:** Avoid zones as a hard rule beyond V-AVOID; wicks, volume, flat-EMA judgement; longs; any change of exits; target; adds.

---

## 3. What every run must emit
As v1 §3, plus: fills and trades **by tier (A / B)** with gross, costs, net at low / mid / high, W/L, per year; share of context bars that are Tier A vs Tier B.

**Controls — same bars, fills, sizing, costs:** **C1** Donchian 20/10 short (v1 code). **C3** random short entries, same count per year as the base, at random bars where flat, exited by the same exit rules; 1,000 seeded draws `np.random.default_rng([crc32(str(d)), crc32("CL-S2"), N])`; p5 / p50 / p95 / **p99**. CHARTMARK-S v1 base reported beside them (reference only). **Neighbour grid (27 cells, unranked):** X1 window {10, 16, 24} × P1 arming {0.75, 1.0, 1.5 A₀} × P0 cut buffer {0, 2, 4 ticks}; the Tier B tolerance stays 2 ticks in every cell. **Seen window** (2025-09-08 →): reported only, "seen — not evidence".

---

## 4. The bar to clear — base, training side (2010-06 → 2021-12), 1 MCL, IBKR mid
Passes only if all hold: 1 net > $0 at mid · 2 both halves > $0 · 3 drop-top-1 and drop-top-2 years > $0 · 4 bootstrap by year (2,000 seeded) net > 0 in ≥ 95% · 5 beats C1 on net and on net per unit of daily volatility · 6 **beats C3 p99** on net · 7 no single year > 50% of net · 8 net > $0 at high friction · 9 at least 18 of 27 grid cells > $0 · 10 **at least 150 trades** (fewer → NOT READ, no variant swapped in).
**Failing 5 or 6 closes the study.** A variant that passes when the base does not is a new registration, not a rescue.

---

## 5. Before the backtest — no P&L in this section
| # | Gate |
|---|---|
| G1 | Data: CL 1H archive (W15-0002), cut to sessions before 2022-01-01 before resample / back-adjust; TradingView roll difference (W15-0026) noted |
| G2 | Count-only pre-flight (orders, fills, cancels, timeouts, re-entries, exits by type, by tier, per year). **Fewer than 150 fills → stop, report to Ben before any P&L.** Runner refuses any exit price or P&L flag |
| G3 | Ledger `holdout_chartmark_short_v2.json`, own file, refuses limit / narrowing / other candidates / a second spend; records v1 Amendment A.2's two excluded windows |
| G4 | Look-ahead guards, each broken by a one-bar shift in a test: context uses bar t only (B1 uses t−1 and t); the P0/P1 levels use EMA9[j−1]; the poke high is recorded after its bar closes |
| G5 | IBKR costs wired at three levels; CHARTMARK-S v1 tests stay green |
| G6 | **Seen-window fidelity to Ben's marks** (counts only): the engine takes **none** of the 8 entries he rejected for "EMA9 above EMA21, not falling" (fills within 1 bar of 8 Sep 08:00, 8 Sep 22:00, 9 Sep 00:00, 9 Sep 13:00, 9 Sep 20:00, 10 Sep 19:00, 10 Sep 21:00, 14 Sep 01:00), **does** fill at 9 Sep 22:00 (±1 bar, within 2 ticks of 96.25) and at 11 Sep 01:00 (±1 bar, near 102.09). A mismatch is reported to Ben as a fidelity finding **before any P&L**; the rule is not adjusted to make it pass |

---

## 6. The holdout
Training 2010-06 → 2021-12-31. Holdout 2022-01-03 → 2025-09-07, own ledger, **spent once**, by the base only, **only if all ten criteria pass**; trades entered in 2025-02-19 → 2025-03-04 and 2025-06-22 → 2025-07-03 are excluded and listed separately (v1 Amendment A.2). Variants never spend it. Seen window 2025-09-08 on: never scored.

---

## 7. Registered as NOT to be done
- Tuning any threshold to the training result, to Ben's charts, or to anything from 2022 on.
- Promoting V-A, V-B, V-RANGE, V-SESSION, V-AVOID or a grid cell into the base after a result.
- Changing the exits, adding a target, adds, news, a higher-timeframe filter or longs under this registration.
- Quoting gross, a variant, or the seen window as the headline.
- Spending the holdout on anything but a full ten-of-ten pass of the base.

## 8. Ways this could go wrong
- **Fewer trades, same problem.** v1's gross was ($3,599) before costs; filtering to confirmed rollovers cuts the cost drag but the exits still cut most trades quickly. On the seen year only 74 of v1's 651 entries had EMA9 below EMA21.
- **Late entries.** Waiting for the cross gives up the first part of each drop; the P1 retest exit may then have less room.
- **Fitted to 10 marks on seen bars.** The tiers reproduce Ben's stated reasons, not evidence of an edge.
- **Regime.** Confirmed downtrends (2014–15) may carry the total; criterion 7 guards.

## 9. Multiplicity budget
One primary hypothesis (the base), one variant family (V-A, V-B, V-RANGE, V-SESSION, V-AVOID), one holdout spend.

## 10. A prediction, written down now
**The base fills 400–1,500 trades on the training side (roughly 5–15% of v1's 6,997), with a win rate near one in three. At mid friction I expect it near zero or negative; I give it well under one-in-three odds of beating random p99. V-A should trade least and V-B most. I would be glad to be wrong.**

---

## Next steps (board)
- **W15-0039 sub 2** — Ben: commit this file to `docs/research/` (commands on the subitem).
- **W15-0039 sub 3** — Build & test chat: engine change (context tiers), G2–G6, no P&L (Sonnet / Medium).
- **W15-0039 sub 4** — Build & test chat: training backtest vs C1, C3, variants, grid → Result doc (Sonnet / Medium).
