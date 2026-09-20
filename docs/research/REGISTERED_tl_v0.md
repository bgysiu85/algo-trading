# REGISTERED — TL-v0 and TL-v0-rev: Tori Trades' trend-line method, coded, on CME futures, daily

**Committed before the pre-flight is run, before any backtest code exists, and before any
return of either rule set has been seen.** `PROGRAM_INDEX` §1: a hypothesis is registered
before it is run.

Board: AT-105. Source analysis: `claude/tori_trades_systematic_RESULT_20260920.md` (§1–§5).
Pine reference build and fidelity check: `claude/tl_v0_fidelity_RESULT_20260920.md`,
`D:\Trading\Claude outputs\TL_v0.pine` (TradingView script "Futures - Trend-line method").
Ben's decision, 2026-09-20, in his words: *"please go ahead with your recommendation"* —
the recommendation being to register **both** v0 and a variant v0-rev, fixed before any
profit is seen.

Amendments are marked **PRE-RUN** or **POST-RUN**. A threshold changed after seeing a
result is a new hypothesis and spends from the budget in §9.

---

## 0. PRE-RUN GATES — step 4 (the backtest) does not start until all five are cleared

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **Pre-flight run and read** (§5): signals per market per year, stop distance in $ per micro, share sizeable at 1% and 2% of $22k — **training side only, no P&L**. | If the account cannot hold the trades, the backtest answers a question nobody can act on. §5.1 fixes the stop rule now. |
| **G2** | **TSMOM's training-side result (AT-43) exists.** | Same markets, same family (slow trend). If TSMOM fails for reasons that apply here too (cost, concentration), TL-v0 inherits them, and that is known for free. Recommended in the AT-104 result; kept as a gate. |
| **G3** | **Python ↔ Pine parity.** The Python engine reproduces the Pine indicator's signals, entries, stops and exits bar for bar on a fixed sample (CL1! daily, 2015–2019, B-ADJ off to match the chart), mismatches listed, zero tolerated or each explained. | Two implementations of line geometry will disagree somewhere. Finding out after a result is how a project measures a strategy adjacent to the one it registered. |
| **G4** | **Holdout cut and enforced in code** (§6), mutation-tested. | `PROGRAM_INDEX` §1. |
| **G5** | **The hindsight guard is tested.** A synthetic series where a pivot confirms at bar i+R: a line through it must not exist at bar i+R−1. Mutation-checked (shift the pivot back, the test must fail). | AT-104 §2 trap 1. Every line drawn on a finished chart, including all of her replays, has this bias. |

---

## 1. The hypothesis, in one sentence

**Trend-line breakout entries with a trend-line trailing stop (Tori Trades' method, coded)
make money after measured costs on the owned GLBX daily history of the TSMOM markets, and
beat a plain 20/10 Donchian channel on the same markets, sizing and costs.**

The second half is the one that matters. Coded, this is trend following with a sloping
stop. If it cannot beat a channel breakout, the trend lines are decoration (AT-104 §4).

---

## 2. The two rule sets, fixed here

Parameters were chosen in the AT-104 judgment session and the Pine build, **not from any
measurement of returns**. None of them comes from her; the fidelity check showed where
they differ from her practice (§2.3).

### 2.1 Common to both

| Element | Registered rule |
|---|---|
| Execution timeframe | **Daily.** (Her 1H/4H is step 5, only if step 4 passes, data priced first.) |
| Pivots | `pivothigh/pivotlow(L, R)` with L = R; a pivot enters the line set only at bar i+R |
| **Pivot size — deployed spec** | **Equal-risk ensemble over L = R ∈ {3, 5, 8}**: three independent sleeves, each sized at one third of the per-trade risk |
| Pivot size — reported neighbours | each of 3, 5, 8 alone |
| Resistance line | through the two latest confirmed swing highs, **only if falling** |
| Support line | through the two latest confirmed swing lows, **only if rising** |
| Line validity at birth | invalid if any close from its first pivot to the confirming bar sits beyond it by > 0.10 × ATR(14); max span 400 bars |
| Action line (entry) | close beyond the active line by > **0.10 × ATR(14)** → enter at the **next bar's open** |
| Top-down filter | trade only in the direction of the last line break on the **weekly** chart, **completed weekly bars only** |
| Initial stop, fallback | if no opposing line exists: last confirmed swing low (high) ∓ 0.25 × ATR(14); if that is on the wrong side of price, the lowest low (highest high) of the last 2L+1 bars ∓ 0.25 × ATR |
| Stop behaviour | resting stop; **never loosens**; fills at the stop, or at the open if the bar gaps through it |
| Target | none |
| Signal series | **difference-back-adjusted continuous** (never ratio-adjusted: CL printed negative in April 2020) |
| P&L series | **the actual held contract**, roll charged, using the TSMOM roll rule **including Amendment C** (`REGISTERED_tsmom.md` §0.2) |
| Markets | the TSMOM archive's roots as registered there; the rates arm as chosen at TSMOM G3 (**MTN**, signal from TN) |
| Sizing | risk **1% of equity** per trade (her beginner rule); contracts = floor(risk $ ÷ (stop distance × multiplier)); **zero means skip, and every skip is counted** |
| Friction | three levels, per contract per side: **$0.50 / $1.25 / $2.50**, plus one tick of slippage on every stop fill |

### 2.2 The difference between them

| | **TL-v0** | **TL-v0-rev** |
|---|---|---|
| Opposite action-line break while in a position | **ignored**; only the stop exits | **exit at the next open and reverse** (the reversal still needs the weekly filter; if the filter blocks it, go flat) |
| Safety line (stop + trail) | opposing **daily** line ∓ 0.25 × ATR(14) | opposing **weekly** line (completed weekly bars) ∓ 0.25 × daily ATR(14); **falls back to v0's daily line** when no valid weekly line exists |

**v0-rev is the holdout candidate** (§6): it is the version closer to how she trades in the
one trade that could be checked. v0 is its reported neighbour. Fixed now; not revisited on
results.

### 2.3 Known departures from her method — both versions, deliberately not coded

Chained lines ("previous point B is new point A") and maximising touch points; pyramiding on
a second break; support/resistance and news for exits; "A+ setup" selection; her 4–7% risk.
Recorded so the result is read as *the method*, not *her*.

---

## 3. What every run must emit

1. **Net and net per year at all three friction levels**; gross stated separately, never as the headline.
2. **Both halves**, split at the median date of the training sample, split not swept.
3. **Every calendar year**, none omitted.
4. **drop-top-N by market**, N = 1, 2, 3 (`n/a`, not `$0`, if N ≥ market count).
5. **Cluster bootstrap by market** and **by calendar year**, 2,000 resamples each, seeded.
6. **The three controls side by side, same markets, sizing, costs and fills:**
   - **C1** Donchian breakout: 20-day entry, 10-day opposite-channel exit.
   - **C2** v0 entries with a 3 × ATR(14) chandelier stop instead of the safety line.
   - **C3** TSMOM sign (12-month) on the same market, held for the same median holding period.
7. **v0 and v0-rev, unranked**, and each pivot size alone.
8. **Counts:** signals, HTF-blocked, ignored-in-position (v0) / reversals (v0-rev), skipped at 1% for size, voided (opened beyond stop), median hold.
9. **Fractional sizing (in R) and integer sizing at $22k, $100k, $500k**, separately.
10. **Coverage in the same pass:** bars per market, first/last date, gaps, and the roll cross-check the TSMOM runner already does.

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — all of it, for the holdout candidate (v0-rev)

1. **Positive after costs at mid friction** ($1.25/side), ensemble spec, training sample.
2. **Both halves positive** at mid friction (an empty half is a failure).
3. **drop-top-1 and drop-top-2 by market** still positive.
4. **Bootstrap by market and by year: total > 0 in ≥ 95%** of resamples, each.
5. **Beats C1 (Donchian) at mid friction, on net and on net per unit of realised volatility.** Failing this closes the study whatever else passes.
6. **No single year and no single market supplies more than 50% of net.**
7. **The ensemble is not beaten by the median single pivot size.**
8. **Still positive at high friction** ($2.50/side).

v0 is scored against the same bar and reported, but **cannot spend the holdout** in this
registration.

---

## 5. Step 2 — the pre-flight (no P&L), fixed now

Run on the **training side only** (2010-06 → 2021-12), both rule sets, each pivot size:

- signals per market per year (and HTF-blocked, ignored/reversed)
- stop distance at entry, in $ per **micro** contract where a micro exists (MES, M2K, MCL, MGC, SIL, MHG, M6A, M6B, M6E), else per full contract, with the micro-less markets named
- share of signals sizeable (≥ 1 contract) at **1%** and **2%** of **$22,000**

It reads **no exit prices and no P&L**. The runner must refuse to compute them in this mode.

### 5.1 The stop rule, registered before the pre-flight is read

**If, at 2% risk on $22k, fewer than half of v0-rev's signals can be sized in more than half
of the markets, the study stops for this account size.** That is reported as the finding
("the method cannot be held at $22k"), not worked around by raising the risk percentage.

---

## 6. The holdout

**2022-01-01 onward is locked**, the same cut as TSMOM, but **TL-v0 writes and enforces its
own cut file**; the TSMOM and equity holdout files are refused by name. **Spent once, by
v0-rev only.** Refuses `--limit` and every narrowing flag; a mutation-checked test asserts
the refusal fires.

---

## 7. Registered as NOT to be done

- Tuning to the one fidelity trade. The May 2026 CL short sits **inside the holdout** and is not read again.
- Swapping in a grid winner (pivot size, buffers) for the ensemble.
- Raising risk above 2% because 1% cannot be sized. That is the §5.1 finding.
- Reporting the continuous series' P&L.
- Adding her discretionary pieces (S/R, news, A+ selection, pyramiding) as "improvements" after a result. Each would be a new registration.
- Using the Pine indicator's counts as the result. Pine is the reference for G3 only.
- **Writing to Ben's TradingView Pine Editor from any chat** (AT-107). Pine changes are delivered as files for Ben to paste.

---

## 8. Ways this could go wrong, given this project's history

- **Hindsight lines** (G5).
- **Roll gaps read as breaks.** The signal is back-adjusted; the pre-flight also prints the count of action-line breaks falling within three sessions of a roll, per market, as a diagnostic.
- **A daily-bar gap through the stop booked at the stop.** Fills are at the open when gapped (§2.1), and a test pins it.
- **Weekly filter peeking** at the forming week. Completed weeks only; a test with a mid-week break must not change the filter until the week closes.
- **A guard that cannot fail.** Every check is mutation-tested before commit.

---

## 9. Multiplicity budget

Families: **pivot size** (one), **rule set v0 / v0-rev** (one, fixed in advance with the holdout candidate named), **friction** (not a search). **Two families.** Budget: **two further registered hypotheses** on this line before it closes (for example, a chained-line construction, or her 1H timeframe at step 5). A third needs a reason that does not begin with a result.

---

## 10. A prediction, written down now

**Both rule sets are positive gross and about flat at mid friction on 2010–2021, and neither
beats Donchian (criterion 5)**, because a sloping line through two pivots is a noisier
version of a channel. v0-rev does better than v0 on CL and on the energy roots generally,
and worse on the currencies, where reversals pay the spread twice. If that is what happens,
the reading is: *the trend lines add nothing measurable over a channel, and her results
come from what cannot be coded.*

---

## Next steps

- **AT-105 subitem 3** — pre-flight (§5), Python, training side only. Suggested session: **Sonnet, medium effort**.
- Then G2 (AT-43) and G3–G5 before any backtest (step 4).
