# REGISTERED — HTF-Ben v1: Ben's 4-hour crude method as he reads his own charts

**Committed before any v1 code exists and before any v1 return has been seen.**
`PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0010** (this registration), W15-0008 (Ben's chart notes, Result doc
https://ben-siu.monday.com/docs/5031556665), W15-0009 (Ben's answers), W15-0011 (build + run),
W15-0007 (trend-line code, needed for F2 and T). Parent: `docs/research/REGISTERED_htf_ben_v0.md`
— everything not changed here is inherited from v0 word for word (bars, session, series, costs,
account view, report contents, look-ahead guards).

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a
v1 result is a new hypothesis and spends from the budget in §9.

---

## 0. Where this comes from, and what has already been seen

Honest provenance, because it decides what the result can mean:

1. **v0 has been run and failed** its §4 criteria on the training side (W15-0004, AT-7 Result
   doc, B 0/9). v1 is **not** a re-tuning of v0: its changes come from Ben describing how he
   reads the chart, not from v0's P&L. But v1 was written after v0's result was known. It is
   therefore **hypothesis 1 of the 2 further hypotheses** v0 §9 allows on this line.
2. **Ben's notes were made on the holdout window.** The W15-0008 trade map showed v0's scenario-B
   trades from **2025-09-23 to 2026-09-23**, inside v0's locked 2022+ holdout, with their P&L.
   Ben annotated 8 of them. That window is now **seen** and cannot test v1 (§6).
3. **Power pre-check (no P&L), 2026-09-25, before this file.** On the training side
   (2010-06-06 → 2021-12-31), rebuilt 4-hour CL bars, counting setups only (trigger + confirmation
   + daily filter, crude one-at-a-time spacing, no exits): v0's rule ≈ 110 setups (the engine
   found 143 entries); v1's E2 ≈ 406 (2-bar window) / 408 (3-bar); adding the curl route without
   its trend-line requirement ≈ 744 (upper bound). No exit price was read. F1/F2 will cut these;
   §5.2 re-measures properly.

Ben's answers (W15-0009, 2026-09-25), verbatim:
- Q1 curl entry: *"Yes. Provided that there is a retest off trendline or bounce off trendline and
  still in the same direction as the trendline after 2-3 bars"*
- Q2 take-profit: *"Does not have to be. I included it this time so i don't have to keep track of
  it. When trading through algo, the stop trail will take care of it"*
- Q3 exit: *"which ever is earlier. Also, trailing stop would be part of the consideration"*
- Q4 confirmation window: *"2-3 is fine"*
- Q5 range length: *"i would say 1.5-2 days worth"*
- Q6 holdout split: *"yes"*

---

## 1. The hypothesis, in one sentence

**Ben's method as he actually reads it (EMA9 moving the trade's way against EMA21, an early
entry on a MACD curl when price has just rejected a trend line, no trades in flat ranges or
against the last-touched trend line, and an exit on whichever comes first of the opposite MACD
cross, EMA9 turning, or the half-profit trail) makes money after measured costs on 2010–2021 CL on
the 4-hour multi-day chart, and beats a plain MACD cross with the same exits, a Donchian channel
and random entries on the same bars, sizing and costs.**

---

## 2. The rules

Inherited unchanged from v0: §2.1 (bars, 18:00 New York session, back-adjusted signal series,
held-contract P&L, rolls), E3 daily filter, E4-style fills (market at the next bar's open), E5 one
position at a time, E6 weekly context reported only, E7 indicator seeding and warm-up, S1 initial
stop (swing L = R = 2, 1 tick beyond), S2 half-profit trail from $0.20/bbl, S3 conservative order,
S4 stop fills on 1-hour bars, §2.5 sizing, account view and costs (Amendment A: $1.09 / $2.09 /
$3.09 per MCL side at low / mid / high).

Notation (long shown; short is the mirror): `hist = MACD − signal`, `spread = EMA9 − EMA21`,
`ATR = ATR(14)` on the 4-hour back-adjusted series. "Line" = a 4-hour trend line from
`common/tl_v0_lines.py` (pivots L = R = 5, break buffer 0.10 × ATR), on the back-adjusted series;
a line is **active** from its second pivot's confirmation until the first close beyond it plus
the buffer.

### 2.1 Entry — two routes

| # | Rule | Source |
|---|---|---|
| **E1a Cross route** | Bar t: MACD crosses **above** signal (hist[t−1] ≤ 0 < hist[t]). Confirmation bar **c ∈ {t+1, t+2, t+3}**: the first where E2 holds and hist[c] > 0 still. None → lapses. | v0 E1; Q4 *"2-3 is fine"* (3-bar window primary, 2 in the grid) |
| **E1b Curl route** | Bar t: hist[t] < 0 and **hist has risen 2 bars in a row** (hist[t−2] < hist[t−1] < hist[t]) — MACD curling up toward its signal before crossing — **and T holds at t and E2 holds at t**. Confirmation bar c = t. | Q1; #9 (histogram 0.33 → 0.25 for the short) |
| **T Trend-line rejection** (curl route only) | Some bar k with **t − k ∈ {2, 3}** touched an active **rising** line (low ≤ line + 0.25 × ATR[k]) and closed above it; every close from k to t is above the line; the line is still active at t. | Q1 *"retest off trendline or bounce off trendline and still in the same direction as the trendline after 2-3 bars"* |
| **E2 Confirmation (replaces v0 E2)** | At c: **EMA9[c] > EMA9[c−1]** and **spread[c] > spread[c−1]**. Covers EMA9 rising toward EMA21 from below and EMA9 widening above it; rejects EMA9 converging from above. | W15-0008: #1, #3–#5 vs #7, #8 (v0's \|gap\| rule is direction-blind) |
| **F1 No range** | Skip if over the **N = 9** four-hour bars ending at c (1.5 sessions): max \|hist\| / ATR[c] ≤ q_h **and** max \|spread\| / ATR[c] ≤ q_e, where q_h, q_e are the **25th percentiles** of those two rolling ratios over all training-side bars, computed in G2 (§5.2) from indicators only. Counted as "blocked: range". | Q5 *"1.5-2 days worth"*; #3–#6 |
| **F2 Last-touched line** | Find the active line most recently touched (high/low within 0.25 × ATR) in the **30 bars** before c *(assumed ≈ one week)*. If it is **falling**, no longs; if **rising**, no shorts. No touched active line → no restriction. Counted as "blocked: trend line". | #2 (long under a week-long falling line); #9 (short off the falling line while an older rising line sat below) |
| **E3** | Daily filter, as v0 | v0 |
| **Fill** | Market at the open of bar c + 1 | v0 E4 |

### 2.2 Exits — whichever comes first

| # | Rule | Source |
|---|---|---|
| S1, S2 | Initial swing stop and $0.20/bbl half-profit trail, as v0 (tested on 1-hour bars) | Q3 *"trailing stop would be part of the consideration"* |
| **X1 Opposite cross** | On the close of any entry-chart bar after the fill bar: hist crosses to ≤ 0 (long). Exit at the next bar's open. | Q3; #7, #8 red boxes |
| **X2 EMA9 turns** | On the close of any entry-chart bar after the fill bar: **EMA9[b] < EMA9[b−1]** (long). Exit at the next bar's open. **1 bar** primary; 2 bars in a row in the grid. | Q3 *"which ever is earlier"* |
| No targets | No take-profit | Q2 |

If a stop and a signal exit fall in the same bar, the stop (tested on 1-hour bars) takes
precedence when it is hit before that bar closes; otherwise the signal exit fills at the next
open. Slippage: v0 §2.5 on every leg.

### 2.3 Scenarios

**B — multi-day, 4-hour chart: primary and the only holdout candidate.** Ben's notes were all
on B. **A-2H** (intraday, flat by 17:00, v0 §2.4) runs the same rules and is **reported** beside
it, not scored for the holdout. A-1H and A-4H are not run (v0 lost on all intraday charts and Ben
has not asked for them).

### 2.4 Reported variants (fixed now, never ranked, cannot spend the holdout)

| Variant | Change | Tells us |
|---|---|---|
| v1−curl | cross route only | whether the early entry earns its place |
| v1−F1 | no range filter | whether F1 earns its place |
| v1−F2 | no trend-line filter | whether F2 earns its place |
| v1−X | exits S1/S2 only (no X1/X2) | whether the signal exits help or cut winners |
| v0 | as registered (already run) | reference only |

---

## 3. What every run must emit

v0 §3 items 1–6 and 9–11 unchanged, for B and A-2H. Additions:

- **Counts:** triggers by route (cross / curl), lapsed, blocked by E3 / F1 / F2, curl setups
  failing T, ignored while in position, voided.
- **Exit reasons:** initial stop / trailed stop / X1 / X2 / 17:00 flat (A) / data end; median
  bars held by exit reason.
- **Controls (same bars, fills, sizing, costs, and v1's exits S1/S2/X1/X2):**
  C1 MACD cross alone (no E2, F1, F2, no curl route); C2 Donchian 20/10 as v0; C3 random entries,
  1,000 seeded draws matched to v1's trade count and long/short mix, p5 / p50 / p95.
- **Neighbour grid (24 cells, reported unranked):** confirmation window {2, 3} × range length
  N {9, 12} × range percentile {20, 25, 33} × X2 {1 bar, 2 bars}; net at mid friction per cell
  and the share net positive.
- **Seen window, reported only:** v1's trades from 2025-09-23 → end of data, clearly labelled
  "seen — not evidence", so Ben can check the code against his own annotations (#1–#8) and his
  live trade (#9). No criterion uses it.

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — v1, scenario B, 1 MCL, mid friction, training side

Passes only if all hold:

1. Net > $0.
2. Both halves net > $0 (split at the median trade date).
3. No calendar year supplies more than 50% of net.
4. Bootstrap by calendar year (2,000 seeded resamples): net > 0 in ≥ 95%.
5. **Beats C1 and C2** on net.
6. Beats the p95 of C3 on net.
7. Still net > $0 at high friction.
8. **At least 16 of the 24 neighbour cells** net > $0.
9. **At least 150 trades.** Fewer → NOT READ, not failed.

Failing criterion 5 closes v1 whatever else passes.

---

## 5. Before the backtest — no P&L in this section

### 5.1 Gates

| # | Gate |
|---|---|
| G1 | Data: v0's G1 stands (passed under Amendment B). No new data. |
| G2 | Pre-flight (5.2). |
| G3 | **v1 holdout cut and ledger** (§6) in code, mutation-tested. |
| G4 | Look-ahead guards: v0's plus **lines** (a line used at c exists from pivots confirmed at or before c's close; a one-bar shift breaks the test), **T** (touch bar and the closes after it are all completed by t), **F1 percentiles** (computed on training bars only; a test fails if a holdout bar changes q_h or q_e). |
| G5 | Costs: v0 Amendment A stands. |

### 5.2 G2 pre-flight (training side only)

Compute and **write into this file as a PRE-RUN amendment** q_h and q_e (20th / 25th / 33rd
percentiles). Then, per year, for v1 and each §2.4 variant on B and A-2H: triggers by route,
confirmations, blocks by E3 / F1 / F2, curl setups failing T, entries, initial stop distance in
$ per MCL (median, p90, max). No exit price is read; the runner refuses P&L in this mode.

**Stop rule:** fewer than **150 v1 entries on B** → stop as underpowered, reported as the
finding, and back to Ben before any P&L.

---

## 6. The holdout

- **Training:** 2010-06-06 → 2021-12-31 (as v0).
- **v1 holdout: sessions from 2022-01-03 through the session ending 2025-09-22**, its own cut
  file and ledger `holdout_htf_ben_v1.json`. **Spent once, by v1 on B, 1 MCL, mid friction, the
  same nine criteria.** Refuses `--limit` and every narrowing flag; mutation-tested.
- **Seen window: 2025-09-23 onward** (the W15-0008 trade map period, Ben's annotations, his
  NinjaTrader paper trades). Never scored; reported only (§3).
- **v0's ledger `holdout_htf_ben.json`** is closed unspent: v0 failed training (W15-0004), so it
  never qualified to spend it. Its file is kept and refused by name, like every other line's.

Ben's decision, in his words (Q6): *"yes"*.

---

## 7. Registered as NOT to be done

- Tuning any threshold to the 15 trades on the W15-0008 map, to Ben's #1–#9, or to anything
  from 2022 on.
- Changing q_h / q_e after G2 writes them in.
- Swapping a variant or grid cell in for v1 after a result.
- Adding a take-profit (Q2), a weekly filter, news or more markets as "improvements" after a
  result. Each is a new registration.
- Quoting gross, 1 CL or 10 CL figures as the headline.

---

## 8. Ways this could go wrong

- **X2 is hair-trigger.** One falling EMA9 bar ends the trade; on 4-hour crude that may cut most
  winners before the trail starts. Grid cell X2 = 2 bars and variant v1−X show it; the primary
  stays at Ben's literal "which ever is earlier".
- **Lines are fragile.** TL-v0's pivots (L = R = 5) are not the lines Ben draws by eye (his #9
  line runs from a September high over ~2 weeks). F2 and T test *a* trend-line rule, not his
  exact lines. W15-0005's timing replay is the check.
- **F1 did not separate cleanly** in the W15-0008 look: #5 had a top-10% histogram reading. The
  range filter may do little. v1−F1 shows it.
- **Curl route look-ahead.** T needs 2–3 closes after the touch; all must be completed by t. Test.
- **Back-adjusted vs raw.** The W15-0008 chart bug (raw candles against adjusted indicators) must
  not exist in the engine: signals on the adjusted series, P&L on the held contract, as v0.

---

## 9. Multiplicity budget

v1 is hypothesis **1 of 2** remaining on this line (v0 §9). Families inside v1: route (cross /
curl), filters (F1, F2), exits (X1/X2), all fixed here with their ablations reported, and one
holdout spend (v1 on B). After v1, **one** further registered hypothesis is left; a third needs a
reason that doesn't begin with a result.

---

## 10. A prediction, written down now

**v1 on B has more trades than v0 (≈ 200–300 on the training side) and a higher win rate, but a
smaller average win, because X2 exits early.** Net at mid friction lands near zero, positive in
the trending years (2014, 2020) and negative in the ranging ones. It **beats C2 Donchian but not
C1** by a margin that survives the bootstrap: the exits drive the result more than the entry
filters. v1−X (trail only) does better than v1 in trending years. If that happens, the reading is
that Ben's entry reading is fine and the question becomes the exit. I'd be glad to be wrong.

---

## Next steps (board)

- **W15-0007** — v0-TL trend-line geometry (needed by F2 and T). Build & test chat, Sonnet · Medium.
- **W15-0011** — build v1 on the `strategy/htf` engine, G2 (writes q_h, q_e here as PRE-RUN), G3–G4,
  then the run and the Result doc. Build & test chat, Sonnet · Medium; runs on Ben's PC.
- **W15-0012** — trade-map generator fix (so the "seen window" report draws correctly).
