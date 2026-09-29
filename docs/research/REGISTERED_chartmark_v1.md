# REGISTERED — CHARTMARK-v1: Ben's chart-marked CL 1H long method (buy-stop entry, structural stop, EMA9 → EMA21 trails), stall-to-breakeven as a reported variant

**Committed before any CHARTMARK code exists, before its pre-flight is run, and before any count or return has been computed on the archive.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0032** (this line; subitem 4 = free steps, subitem 5 = backtest). Source: Ben's 10 "Long" + 1 "Avoid" screenshots (CL1! 1H, Sep 2025–May 2026) and his 13 annotated fires in `D:\Trading\Claude outputs\w15_0032_candidate_fires_review.xlsx`; analysis in `claude/w15_0032_chartmark_long_RESULT_20260929.md`.

Ben's decisions, 2026-09-29, in his words:
- *"All entries need to be earlier within the bar and exited earlier … my line marking the entry and exit is a specific position of the bar, not just simply that bar, but that specific moment of the bar."*
- *"There aren't many, if any, trades that I would say plainly should not have entered. They were simply entered and/or exited too late."*
- Context: *"largely yes … I would like my extra EMA9 rule built in as an optional condition that can be enabled should we find your context to be too loose."*
- Stall rule: *"leave the stall rule available as an option, so we can run backtest or comparison with and without the rule"*; breakeven *"at a price that would breakeven after accounting for commission and any other fees."*
- *"I don't mind losses as long as they are minimised and as long as it gives room for genuine good trade to maximise its profits."*
- *"The draft seems ok. Will see actual results before I can be sure."*

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a result is a new hypothesis.

---

## 0. Where this sits, stated plainly

- **Origin.** A rule set fitted to 14 hand-marked entries and 13 annotated fires on **seen** bars (2025-09 → 2026-05, the "seen window"). Nothing here has touched the training archive. The fit is a *description of Ben's discretion*, not evidence of an edge; the only evidence is §4 on §6's bars.
- **What it is.** A long-only, 1H, momentum-continuation method on CL: stop-order entry above the last swing high once MACD/EMA context is right, a structural initial stop, then a trailing exit that tightens (EMA9) and later loosens (EMA21) as the trade earns it, with a reversal-candle sell-stop throughout.
- **Relation to HTF-Ben.** Same indicators (EMA9/21, MACD 12-26-9) as HTF-Ben v0–v2, but a different mechanism: intrabar stop orders instead of close-based signals, and no "MACD cross + EMA9 rising" confirm. HTF-Ben v2 is a **reference control** here (C2), not re-scored.
- **What the seen window said (reported, not evidence).** On the 13 annotated fires, buy-stop entry + structural stop + EMA9-touch trail armed at +1 ATR: +3.47 pts gross, 9W/4L, 3 exits on Ben's bar to the cent. The stall variant turned his three no-follow-through scratches into scratches but also scratched his two biggest winners — net roughly a wash on 13 trades. That is why it is a variant.
- **Fidelity caveat.** Ben's exits are partly judgement (which candle "looks" like a reversal; when a big winner "deserves" EMA21). This tests a mechanical coding, not his eye.

---

## 1. The hypothesis, in one sentence

**Entering CL 1H on a buy-stop above the last swing high when MACD histogram is non-negative and price is above EMA21 during the London–US-morning session, with a structural stop and an EMA9-then-EMA21 touch trail, makes money after leg-by-leg friction on the owned GLBX 1H history, beats a 20/10 Donchian channel on the same bars, and beats the 99th percentile of random entries of the same count.**

---

## 2. The rules — CL 1H, long only

**All thresholds fixed now. None is tuned to the archive.** Times are New York. "ATR" = ATR(14) on 1H bars. Tick = 0.01.

### 2.1 Context (all must hold at the close of bar t for an order to be placed at t+1)

| | Rule |
|---|---|
| **X1 Momentum** | MACD(12,26,9) histogram[t] ≥ 0, **or** histogram[t] > histogram[t−1] > histogram[t−2] (rising two bars) |
| **X2 Trend** | close[t] > EMA21[t] |
| **X3 Session** | bar t opens 02:00–12:00 New York (inclusive) |
| **X4 EMA9 converging — OPTIONAL, OFF in the base** | EMA9[t] ≥ EMA21[t], **or** (EMA21 − EMA9) narrowed on each of the last **2** bars (lookback = input, 2 or 3) |
| **X5 Flat** | no open CHARTMARK position and no pending order |

### 2.2 Entry

| | Rule |
|---|---|
| **E1 Level** | buy-stop at **highest high of bars t−2…t** + 1 tick |
| **E2 Placement** | order placed for bar t+1; re-evaluated each bar: if context still holds and the level has not filled, the level is **re-set** to the new 3-bar high (it can only rise); if context fails, the order is cancelled |
| **E3 Timeout** | cancelled if unfilled after **K = 6** bars from first placement (counted "no fill") |
| **E4 Fill** | filled in the first bar whose high ≥ level, at **max(level, open)** (gap-through fills at the open), plus the friction model's stop-fill slippage |
| **E5 One shot** | a cancelled or timed-out order re-arms only after context has been false for at least one bar |

### 2.3 Initial stop (S)

Sell-stop at **lowest low of the 5 bars ending at the entry bar** − 1 tick. Filled at min(stop, open). Never widened.

### 2.4 Trails — which one is live depends on how far the trade has travelled

"Travelled" = max close since entry − entry price, in ATR at entry (A₀).

| Phase | Condition | Exit order |
|---|---|---|
| **P0 Structural** | travelled < 1.0 A₀ | S only |
| **P1 EMA9 trail** | travelled ≥ 1.0 A₀ | exit at **min(EMA9[j], open[j])** in the first bar j whose low < EMA9[j]; S remains as a floor |
| **P2 EMA21 trail** | travelled ≥ 2.0 A₀ | EMA9 rule replaced by the same rule on **EMA21**; S remains as a floor |

Phases only advance. EMA values used are those of the bar being tested (a touch is known intrabar; the stop is placed at the prior bar's close at the EMA value then, and filled at that level — **the fill price is the EMA value at the prior bar's close**, not the touched bar's, to avoid using a value that did not yet exist).

**PRE-RUN clarification of the fill:** for P1/P2 the working sell-stop for bar j is set at EMA[j−1]; it fills in bar j at min(EMA[j−1], open[j]) if low[j] < EMA[j−1].

### 2.5 Reversal-candle exit (R) — active in every phase

Any bar j after the entry bar with **upper wick ≥ 50% of its range** (high − max(open, close)) ≥ 0.5 × (high − low), range ≥ 0.3 A₀) → sell-stop at that bar's **body low** (min(open, close)) − 1 tick for bar j+1 onward; cancelled if not hit within **3** bars. Fills at min(level, open).

### 2.6 Reported variant — stall-to-breakeven (V-STALL), OFF in the base

If, **N bars** after the entry bar, no close has reached entry + **0.5 A₀**, place a sell-stop at **entry price + round-trip friction in price terms** (commission + exchange fees both legs + expected stop-fill slippage, from the leg-by-leg cost level of W03-0005, converted at the contract's tick value). It stays until filled, until P1 arms, or until S/R exits first. Run with **N = 3** and **N = 4**; reported beside the base, never ranked into it. Ben's words: *"leave the stall rule available as an option, so we can run backtest or comparison with and without the rule."*

### 2.7 Other reported variants (fixed now, never ranked)

| Variant | Change | Tells us |
|---|---|---|
| **X4 on** | EMA9-converging gate enabled (lookback 2) | whether Ben's extra context tightens usefully |
| **No P2** | EMA9 trail throughout | whether loosening to EMA21 on big winners pays |
| **No R** | reversal-candle exit off | whether R adds or subtracts |
| **Session off** | X3 removed | how much the London–US window matters |

**Known departures, not coded:** Ben's end-of-day flat rule for live (overnight margin); adds; his reading of which candles are reversals; shorts; "avoid" zones (to be registered separately from the Short/Avoid screenshots when they exist).

---

## 3. What every run must emit

For CHARTMARK-v1 and every variant, per year: orders placed, fills, no-fills (E3), exits by type (S / P1 / P2 / R / V-STALL), median bars order→fill and fill→exit, phase reached (P0/P1/P2 share), trades, wins/losses, gross, friction, net at mid and high friction, max drawdown, both halves.

**Controls — same bars, fills, sizing, costs:**
- **C1** Donchian 20/10 on 1H, long only, same session filter, same stop-fill model.
- **C2** HTF-Ben v2 (REGISTERED_htf_ben_v2.md) on the same 1H bars, reference only.
- **C3** **Random entries:** for each year, the same number of long entries as CHARTMARK-v1, at random bars inside X3's session, exited by the same §2.3–§2.5 rules; 1,000 seeded draws (`np.random.default_rng([crc32(str(d)), crc32("CL"), N])`); p5 / p50 / p95 / **p99**.

**Neighbour grid (27 cells, unranked):** E1 lookback {2, 3, 5} × P1 arming {0.75, 1.0, 1.5 A₀} × stop lookback {3, 5, 8}; net at mid per cell, share positive.

**Seen window** (2025-09-08 →), reported only, labelled "seen — not evidence"; Ben's 13 annotated trades listed beside the engine's on the same bars.

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — CHARTMARK-v1 base, CL 1H, training side, mid friction

Sizing and friction: **as HTF-Ben v2** (its $10k account framing, its contract, its leg-by-leg friction levels), inherited unchanged so the two are comparable.

Passes only if all hold:
1. Net > $0 at mid friction.
2. Both halves net > $0 (split at the median entry date).
3. drop-top-1 and drop-top-2 by calendar year still > $0.
4. Bootstrap by year (2,000 seeded resamples): net > 0 in ≥ 95%.
5. Beats C1 on net and net per unit of realised volatility.
6. **Beats the p99 of C3** on net.
7. No single year supplies more than 50% of net.
8. Still net > $0 at high friction.
9. At least **18 of 27** neighbour cells net > $0.
10. **At least 150 trades.** Fewer → **NOT READ**, not failed. No variant is swapped in to rescue the count.

**Failing 5 or 6 closes the study whatever else passes.** C2 is reported beside it, not a criterion. V-STALL is reported beside it, not a criterion — if V-STALL passes and the base does not, that is a *new* registration, not a rescue.

---

## 5. Before the backtest — no P&L in this section

| # | Gate | Status |
|---|---|---|
| G1 | Data: the CL 1H archive from W15-0002 (Databento GLBX ohlcv-1h); roll rule as documented there; the TradingView CL1! difference (W15-0026) noted, not fixed here | Reused |
| G2 | **Count-only pre-flight** on the training side: orders, fills, no-fills, exits by type, phase reached, per year. Runner refuses any exit price or P&L | Open (W15-0032 sub 4) |
| G3 | **Holdout ledger** `holdout_chartmark_v1.json`, mutation-tested; refuses `--limit` and every narrowing flag | Open (W15-0032 sub 4) |
| G4 | **Look-ahead guards**, each broken by a one-bar shift in a test: context uses bar t's close only; E1's level uses highs ≤ t; the P1/P2 stop uses EMA[j−1]; R uses bar j's own OHLC and fills from j+1; V-STALL's "no close reached" uses closes ≤ j | Open (W15-0032 sub 4) |
| G5 | Engine reuses the HTF-Ben sim/fill layer where it fits; HTF-Ben tests stay green | Open (W15-0032 sub 4) |
| G6 | **Seen-window parity:** the engine, run on the TradingView bars in `w15_0032_cl1_1h_bars_indicators.csv`, reproduces the 13 annotated trades' entries within 1 bar and 2 ticks of `w15_0032_candidate_fires_review.xlsx` where Ben stated a level. Counts only | Open (W15-0032 sub 4) |

**Stop rule, fixed now:** fewer than **150 fills** on the training side → stop as underpowered, reported as the finding, back to Ben before any P&L.

---

## 6. The holdout

- **Training:** 2010-06 → 2021-12-31. **Holdout:** 2022-01-03 → 2025-09-07, own ledger `holdout_chartmark_v1.json`, **spent once**, by the base only, **only if all ten criteria pass**. Variants never spend it.
- **Seen window:** 2025-09-08 onward (the bars Ben marked). Never scored.

---

## 7. Registered as NOT to be done

- Tuning any threshold to the training result, to Ben's charts, or to anything from 2022 on.
- Promoting V-STALL, X4, No-P2, No-R or a grid cell into the base after a result.
- Adding a target, adds, news, a daily-trend filter, or shorts under this registration.
- Quoting gross, a variant, or the seen window as the headline.
- Spending the holdout on anything but a full ten-of-ten pass of the base.

---

## 8. Ways this could go wrong

- **Fitted to 27 marks on seen bars.** The rule reproduces Ben's picks; the archive decides whether the picks had an edge.
- **Stop-order fills.** 1H OHLC cannot show the path inside the bar; a bar that touches both the level and the stop is filled conservatively (entry then stop) and counted; the count is reported.
- **Session dependence.** X3 carries much of the seen-window separation; if "Session off" is close to the base, the window was noise.
- **Trail whipsaw.** EMA9-touch after +1 A₀ can give back most of a fast move; P2 exists for the big ones but only after +2 A₀.
- **Costs.** Many small exits (R, P1) multiply friction; the high-friction criterion is the guard.

---

## 9. Multiplicity budget

One primary hypothesis (the base), one variant family (V-STALL ×2, X4, No-P2, No-R, Session off), one holdout spend. Shorts and Avoid zones are a **separate** registration when Ben's marks exist.

---

## 10. A prediction, written down now

**The base fills 300–600 trades on the training side. Win rate is under 50%; the profit comes from the P2 tail. It beats Donchian and random p50 but I give it about even odds against random p99 — the session filter and the buy-stop are the parts most likely to be real, the trails the part most likely to be noise. V-STALL raises win rate and lowers net.** I'd be glad to be wrong.

---

## Next steps (board)

- **W15-0032 sub 4** — Build & test chat: engine, guards, holdout ledger, seen-window parity, count-only pre-flight (Sonnet / Medium).
- **W15-0032 sub 5** — Build & test chat: training-side backtest vs C1–C3 → Result doc (Sonnet / Medium; runs on Ben's PC).
- **W15-0032 sub 3** — Ben: Short and Avoid screenshots → High timeframe chat registers the short side separately.
- Ben commits this file: `docs/research/REGISTERED_chartmark_v1.md` (commands on the item).
