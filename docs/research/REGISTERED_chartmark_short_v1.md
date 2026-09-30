# REGISTERED — CHARTMARK-S v1: Ben's chart-marked CL 1H short method (rollover sell-stop, EMA9 cut, EMA9 retest exit), range gate and session filter as reported variants

**Committed before any CHARTMARK-S code runs on the training archive, before its pre-flight is run, and before any count or return has been computed on bars before 2025-09-08.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0032** (sub 6 = this file; sub 7 = Ben commits it; sub 8 = free steps; sub 9 = backtest). Separate from the long side (`REGISTERED_chartmark_v1.md`), which stands on its own. Source: Ben's 13 "Short" screenshots (14 trades, CL1! 1H, Nov 2025–Apr 2026), his corrections and 18 annotated draft trades in `D:\Trading\Claude outputs\w15_0032_short_fires_review.xlsx`; analysis in `claude/w15_0032_chartmark_short_RESULT_20260930.md` and `claude/raw/w15_0032_chartmark_short_v1draft_20260930.txt`. Costs: IBKR (W15-0033).

Ben's decisions, 2026-09-30, in his words:
- Reading the marks: *"Please pay attention to where the line is drawn across the bar … the line was placed specifically to indicate the entry position. Do not assume entering at the closing of the bar."*
- Exits (from his notes): *"the 4:00 bar already went above EMA9 once … I would stop just before the highest point of the 4:00 bar"*; *"above EMA9 the second time (restest)"*; *"when the price went above EMA9 for the 3rd time in the last 3-4 bars"*.
- Initial stop: *"it's a bit of hindsight. I most likely would have exited at the 4am bar before the price broke EMA9 and then re-entered at 25 Nov 2025 7:00 bar at around $58.40"*.
- Costs: *"please use the IBKR costs as that will be the broker i'm using"*.
- *"5-day range - test as a variant"* · *"let's test the session filter as a variant"*.
- *"let's continue with the short now as i get more avoid samples"* — Avoid zones are **not** part of this registration.

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a result is a new hypothesis.

---

## 0. Where this sits, stated plainly

- **Origin.** A rule set fitted to Ben's 15 short trades (his 14 marks, #4 split into two by his own answer) and his 18 Take/Skip notes, all on **seen** bars (2025-09-08 →). Nothing here has touched the training archive. The fit describes Ben's discretion; it is not evidence of an edge. The only evidence is §4 on §6's bars.
- **What it is.** A short-only, 1H **rollover** method on CL: after a fresh 20-bar top, while EMA9 has not yet clearly crossed below EMA21 and MACD momentum is fading, sell on a stop under the prior bar's low. Cut quickly if price pushes back above EMA9 before the trade is 1 ATR in profit (re-entry allowed). Once 1 ATR in profit, tolerate one poke above EMA9 and exit on the next.
- **Relation to the long side.** Same indicators (EMA9/21, MACD 12-26-9, ATR 14), different mechanism: the long (CHARTMARK-v1) is trend continuation with an EMA9→EMA21 trail; this is a top reversal with an EMA9 cut and retest. The long rules mirrored for shorts caught 5 of Ben's 14 (reported as control C2).
- **What the seen year said (reported, not evidence).** On Ben's own 15 entries the exit rule makes 55.84 pts against his 56.07. The full rule, 2025-09-10 → 2026-09-28: 651 trades, 227 W / 424 L, +40.85 pts gross, about +$1,781 per MCL at IBKR mid cost. Inside the 13 screenshot windows it trades 157 times Ben did not mark, for (25.23) pts gross. Nothing on the 1H chart separated Ben's picks from those trades; the range gate (V-RANGE) was the only measure that did, and it also drops 7 of his 15.
- **Fidelity caveat.** Ben's entries are judgement ("price went below EMA9", "resistance in price lowering"); this tests a mechanical coding, not his eye. The trade count (~50 a month on the seen year) makes slippage the main cost.

---

## 1. The hypothesis, in one sentence

**Selling CL 1H on a stop under the prior bar's low after a fresh 20-bar top while EMA9 is still at or above EMA21 − 0.25 ATR and the MACD histogram is falling, cutting at EMA9 before +1 ATR and exiting on the second push above EMA9 after, makes money after IBKR costs on the owned GLBX 1H history, beats a 20/10 Donchian short channel on the same bars, and beats the 99th percentile of random short entries of the same count.**

---

## 2. The rules — CL 1H, short only

**All thresholds fixed now. None is tuned to the archive.** Times are New York. "ATR" = ATR(14) on 1H bars (Wilder). Tick = 0.01. EMA9, EMA21 = exponential moving averages of the close; MACD(12,26,9) histogram = MACD line − signal line. All values at bar t use closes up to and including t.

### 2.1 Context (all must hold at the close of bar t for an order to work in bar t+1)

| | Rule |
|---|---|
| **X1 Fresh top** | the highest high of bars t−19…t was made within the last **16** bars (bars since that high ≤ 16) |
| **X2 Not yet crossed** | EMA9[t] ≥ EMA21[t] − **0.25** × ATR[t] |
| **X3 Momentum fading** | MACD histogram[t] < histogram[t−1] |
| **X4 Flat** | no open CHARTMARK-S position |

No session filter and no range gate in the base (both are reported variants, §2.6).

### 2.2 Entry

| | Rule |
|---|---|
| **E1 Level** | sell-stop at **low[t] − 1 tick** |
| **E2 Placement** | order works in bar t+1; while context holds and it has not filled, it is **re-set each bar** to the latest bar's low − 1 tick (it may move up or down); if context fails, the order is cancelled |
| **E3 Timeout** | cancelled if unfilled **6** bars after first placement |
| **E4 Fill** | in the first bar j whose low ≤ level, at **min(level, open[j])** (a gap through the level fills at the open) |
| **E5 Re-arm** | after a cancel (E2) a new order may be placed at the next bar where context holds; after a timeout (E3) only once context has been false for at least one bar; **after an exit, a new order may be placed from the exit bar's close** (Ben re-enters) |

### 2.3 Backstop

Buy-stop at **the highest high of the 20 bars ending at the entry bar + 1 tick**, active for the life of the trade, filled at max(level, open). An entry bar that also trades through the backstop (opened below it) is counted as a loss at the backstop in that bar (conservative), reported as "same-bar".

### 2.4 Exit — which order is live depends on how far the trade has travelled

"A₀" = ATR at the context bar t. "Travelled" = entry price − lowest close since entry (entry bar included), in A₀. Evaluated at each bar's close; takes effect from the next bar. Phases only advance.

| Phase | Condition | Exit order working in bar j |
|---|---|---|
| **P0 Cut** | travelled < 1.0 A₀ | buy-stop at **EMA9[j−1] + 2 ticks**; fill at max(level, open[j]) if high[j] ≥ level. Not active in the entry bar itself |
| **P1 Retest** | travelled ≥ 1.0 A₀ | the **first** bar j (after P1 starts) whose high > EMA9[j−1] + 2 ticks is a *poke*: no exit on it; record its high Hₚ. From the bar after the poke: buy-stop at **min(EMA9[j−1] + 2 ticks, Hₚ − 1 tick)**, fill at max(level, open[j]) |

The backstop (§2.3) stays live in both phases. EMA values used for a working order are those of the prior bar's close (known when the order is placed).

### 2.5 Costs — IBKR (W15-0033, Ben 2026-09-30)

Per contract per side, IBKR Pro published rates read 2026-09-30 (interactivebrokers.com/en/pricing/commissions-futures.php; /en/accounts/fees/NYMEX.php):

| | Commission | NYMEX exchange | Regulatory (≈) | **All-in per side** |
|---|---|---|---|---|
| **MCL** | $0.25 (E-micro rate, Fixed and Tiered ≤ 1,000/month) | $0.50 | $0.02 | **$0.77** |
| **CL** | $0.85 | $1.50 | $0.02 | **$2.37** |

Levels (every fill in this method is a stop order, so slippage applies to every entry and exit leg, and to roll legs as in the long registration): **low** = all-in fee, 0 ticks; **mid (headline)** = fee + **1 tick** per side ($1 MCL / $10 CL); **high** = fee + **2 ticks**. Round trip MCL $1.54 / $3.54 / $5.54; CL $4.74 / $24.74 / $44.74. **PRE-RUN check (G5):** if Ben's first IBKR futures fills show a different all-in fee, it is amended here before any P&L is computed.

### 2.6 Reported variants (fixed now, never ranked, cannot spend the holdout)

| Variant | Change | Tells us |
|---|---|---|
| **V-RANGE** | add to context: close[t] in the top 40% of the 120-bar range: (close[t] − lowest low t−119…t) ÷ (highest high − lowest low) ≥ **0.6** | Ben's Skips (median 0.48) vs Takes (0.73): whether shorting near the top of the week's range is what separates good rollovers |
| **V-SESSION** | add to context: bar t opens **02:00–12:00** New York | whether the long side's session window helps shorts (9 of Ben's 14 inside it) |
| **V-WIDE** | no P0 cut: only the backstop before +1 A₀ | the pre-answer version: whether the quick cut pays for its extra trades |
| **V-CLOSE9** | P1 retest replaced by: first close above EMA9 → out at the next bar's open (P0 cut kept) | the simpler exit that kept 70.1 of 77.8 ATR on Ben's entries |

**Known departures, not coded:** Avoid zones (to be registered separately from Ben's Avoid screenshots); his reading of wicks ("resistance in price lowering"), flat EMAs/MACD and volume, which could not be pinned to thresholds that spared his own trades; his gap-open exit ("the opening price was lots higher than the previous session's closing"); holding for "MACD positive and price breaches EMA9 again" when "more than 50% profit" remains; longs.

---

## 3. What every run must emit

For CHARTMARK-S v1 and every variant, per year: orders placed, fills, cancels (E2), timeouts (E3), re-entries after an exit, exits by type (P0 cut / P1 retest / backstop / same-bar / data end), share reaching P1, median bars order→fill and fill→exit, trades, wins/losses, gross, costs, **net at low / mid / high**, per 1 MCL and per 1 CL, average win, average loss, largest loss, worst losing run, max drawdown in $, both halves.

**Controls — same bars, fills, sizing, costs:**
- **C1** Donchian 20/10 on 1H, short only: sell-stop under the 20-bar low, exit on a buy-stop over the 10-bar high, same backstop rule, same fill model.
- **C2** The long rules mirrored for shorts (context close < EMA21, histogram ≤ 0 or falling 2 bars, 02:00–12:00 NY; sell-stop under the 3-bar low; EMA9 → EMA21 trail; reversal-candle exit) — **reference only**, the "5 of 14" rule.
- **C3** **Random short entries:** for each year, the same number of short entries as CHARTMARK-S v1, at random bars where it was flat, exited by the same §2.3–§2.4 rules; 1,000 seeded draws (`np.random.default_rng([crc32(str(d)), crc32("CL-S"), N])`); p5 / p50 / p95 / **p99**.

**Neighbour grid (27 cells, unranked):** X1 window {10, 16, 24 bars} × P1 arming {0.75, 1.0, 1.5 A₀} × P0 cut buffer {0, 2, 4 ticks}; net at mid per cell, share positive.

**Seen window** (2025-09-08 →), reported only, labelled "seen — not evidence"; Ben's 15 trades listed beside the engine's on the same bars.

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — CHARTMARK-S v1 base, CL 1H, training side, mid friction

Sizing: **as CHARTMARK-v1 / HTF-Ben v2** ($10,000 account framing, per 1 MCL headline, 1 CL reported), inherited unchanged so the long and short sides are comparable. Costs: §2.5 (IBKR).

Passes only if all hold:
1. Net > $0 at mid friction.
2. Both halves net > $0 (split at the median entry date).
3. Drop-top-1 and drop-top-2 by calendar year still > $0.
4. Bootstrap by year (2,000 seeded resamples): net > 0 in ≥ 95%.
5. Beats C1 on net and on net per unit of realised volatility.
6. **Beats the p99 of C3** on net.
7. No single year supplies more than 50% of net.
8. Still net > $0 at high friction.
9. At least **18 of 27** neighbour cells net > $0.
10. **At least 150 trades.** Fewer → **NOT READ**, not failed. No variant is swapped in to rescue the count.

**Failing 5 or 6 closes the study whatever else passes.** C2 is reported beside it, not a criterion. If a variant passes and the base does not, that is a *new* registration, not a rescue.

---

## 5. Before the backtest — no P&L in this section

| # | Gate | Status |
|---|---|---|
| G1 | Data: the CL 1H archive from W15-0002 (Databento GLBX ohlcv-1h); roll rule as documented there; the TradingView CL1! difference (W15-0026) noted, not fixed here | Reused |
| G2 | **Count-only pre-flight** on the training side: orders, fills, cancels, timeouts, re-entries, exits by type, share reaching P1, per year. Runner refuses any exit price or P&L | Open (W15-0032 sub 8) |
| G3 | **Holdout ledger** `holdout_chartmark_short_v1.json`, its own file, mutation-tested; refuses `--limit` and every narrowing flag | Open (sub 8) |
| G4 | **Look-ahead guards**, each broken by a one-bar shift in a test: context uses bar t's close only; E1 uses low[t]; the P0/P1 levels use EMA9[j−1]; the poke high Hₚ is recorded only after its bar closes; the 120-bar range (V-RANGE) uses bars ≤ t | Open (sub 8) |
| G5 | Costs: §2.5 IBKR figures wired at three levels; **checked against Ben's first IBKR futures fills** (PRE-RUN amendment if different); the long side's sim/fill layer reused where it fits, its tests stay green | Open (sub 8) |
| G6 | **Seen-window parity** on the TradingView bars in `w15_0032_cl1_1h_bars_indicators.csv` (2025-09-08 → 2026-09-29), counts only: the engine reproduces **651 trades, first fill 2025-09-10 16:00 at 63.73, exits P0 542 / P1 108 / backstop 1**, and the first five trades listed below this table (reference script `D:\Trading\Claude outputs\w15_0032_short_read\engine2.py`, config `cut_retest`, cut buffer 2, arm 1.0, backstop 20, K 6) | Open (sub 8) |

**Stop rule, fixed now:** fewer than **150 fills** on the training side → stop as underpowered, reported as the finding, back to Ben before any P&L.

Reference: first five seen-window trades (for G6) — fill 2025-09-10 16:00 63.73 → 18:00 63.80 P0 · 20:00 63.74 → 21:00 63.72 P0 · 22:00 63.60 → 09-11 02:00 63.62 P0 · 09-11 06:00 63.27 → 09-12 04:00 62.09 P1 · 09-12 12:00 63.20 → 09-14 20:00 62.71 P1.

---

## 6. The holdout

- **Training:** 2010-06 → 2021-12-31. **Holdout:** 2022-01-03 → 2025-09-07, own ledger `holdout_chartmark_short_v1.json`, **spent once**, by the base only, **only if all ten criteria pass**. Variants never spend it. The long side's ledger is separate.
- **Seen window:** 2025-09-08 onward (the bars Ben marked). Never scored.

---

## 7. Registered as NOT to be done

- Tuning any threshold to the training result, to Ben's charts, or to anything from 2022 on.
- Promoting V-RANGE, V-SESSION, V-WIDE, V-CLOSE9 or a grid cell into the base after a result.
- Adding Avoid zones, a target, adds, news, a higher-timeframe filter or longs under this registration.
- Quoting gross, a variant, NinjaTrader-cost figures or the seen window as the headline.
- Spending the holdout on anything but a full ten-of-ten pass of the base.

---

## 8. Ways this could go wrong

- **Fitted to 15 trades on seen bars.** The rule reproduces Ben's exits closely; his entries far less so (157 unmarked trades in the windows).
- **Trade count and slippage.** ~50 trades a month on the seen year, most of them small P0 cuts: 1 tick per side is two-thirds of the mid cost. The high-friction criterion is the guard.
- **Stop-order fills on 1H OHLC.** A bar that touches both the entry level and an exit level is resolved conservatively; the count is reported.
- **Regime.** The seen year includes the 2026 oil spike, where three of Ben's shorts made 39.3 of his 56.1 points; the training years may hold few such tops.
- **Short-side drift.** CL's long-run drift over 2010–2021 is not neutral; C3's random shorts carry the same drift, which is why p99 of C3 is the bar.

---

## 9. Multiplicity budget

One primary hypothesis (the base), one variant family (V-RANGE, V-SESSION, V-WIDE, V-CLOSE9), one holdout spend. Avoid zones are a **separate** registration when Ben's marks exist.

---

## 10. A prediction, written down now

**The base fills 3,000–7,000 trades on the training side (about 11.5 years; the rule fires on chart structure, not volatility, so the seen year's ~50 a month is a fair guide). Win rate is about one in three; most exits are P0 cuts. At mid friction I expect it to be close to zero — the cut keeps losses small, but slippage on that many trades is large. I give it under even odds of beating random p99. V-WIDE and V-RANGE trade less and may look better net of costs; V-SESSION is the weakest (it was negative on the seen year).** I'd be glad to be wrong.

---

## Next steps (board)

- **W15-0032 sub 7** — Ben: commit this file to `docs/research/` (commands on the subitem).
- **W15-0032 sub 8** — Build & test chat: engine, guards G3/G4, IBKR costs G5, seen-window parity G6, count-only pre-flight G2 (Sonnet / Medium).
- **W15-0032 sub 9** — Build & test chat: training-side backtest vs C1–C3 + variants + grid → Result doc (Sonnet / Medium; runs on Ben's PC).
- **W15-0033** — switch the other futures registrations to IBKR costs.
- Avoid zones — Ben adding screenshots (sub 3); a separate registration follows.

---

### Amendment A — PRE-RUN, 2026-09-30 (Avoid variant + holdout exclusion; before any code, count or P&L for this registration)

Source: Ben's 15 Avoid screenshots (`D:\Trading\Claude outputs\Strategy\Avoid\`), read in `claude/raw/w15_0032_avoid_20260930.txt`. Ben's words: *"even quieter times for CL seems to still have movements of around a $1 range which is substantial enough when buying 5 contracts or so. The screenshots tend to have lower volume (below Volume MA) and crosses the EMA lines multiple times rather than having an obvious trend."* Decisions: *"let's test them on both sides"* · *"yes leave them out of the final test"*.

**A.1 New reported variant V-AVOID (never ranked, cannot spend the holdout).** Adds one context condition, evaluated at the close of bar t with bar t's values only:

AVOID(t) = |EMA21[t] − EMA21[t−10]| < **0.5** × ATR(14)[t] **and** at least **7** of bars t−9…t have volume < SMA(volume, 20) of that same bar.

While AVOID(t) is true no order is placed for bar t+1 and any working entry order is cancelled (as a context failure). Open positions are not affected. Look-ahead guard (G4): AVOID uses bars ≤ t only; a one-bar shift must break its test.

What the seen window said (reported, not evidence): the Avoid boxes have flat, tangled averages (EMA9−EMA21 gap 0.26 vs 0.53 ATR outside) and slightly more below-average volume (70% vs 60% of bars). The condition flags 32% of bars inside the boxes and 14% outside. It would have blocked 2 of Ben's 15 shorts and **7 of his 14 longs**, whose entries launch out of exactly such quiet stretches. On the short draft it blocked 96 of 651 seen-year trades (29 W / 67 L, (1.78) pts gross).

**A.2 Holdout exclusion.** Two Avoid screenshots show bars inside this registration's holdout (2022-01-03 → 2025-09-07): `Avoid/5.png` ≈ 20 Feb → 3 Mar 2025 and `Avoid/4.png` ≈ 23 Jun → 2 Jul 2025. Ben has seen them; they were not measured. **Holdout scoring excludes every trade whose entry falls in 2025-02-19 00:00 → 2025-03-04 23:59 or 2025-06-22 00:00 → 2025-07-03 23:59 (New York).** Those trades are listed separately in the holdout report, never counted in the pass/fail figures. The holdout ledger records both windows. Future marking by Ben is limited to bars from 2025-09-08 onward.
