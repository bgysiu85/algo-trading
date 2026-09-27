# Notes for the ORB build chat (2026-09-18)

Paste the block below into the ORB chat. It carries no new instruction to change
code; it records what is settled, what is still open, and the one item worth
spending a registration on — with the prior against it stated up front.

---

## Message to the ORB build chat

### 0. Read this first

**ORB on stocks in play is closed at 1 of 7 criteria. The holdout is unspent.**
Nothing below asks you to reopen that verdict. It asks you to record two standing
facts, to stop three specific mistakes from being made later, and to price one
cheap follow-up that came out of a source review today.

Figure of record, from `orb_sip_RESOLVED_20260918.md`:

| | value |
|---|---:|
| net per trade, BASE friction | **+0.001R** |
| **gross per trade** | **+0.351R** |
| BASE friction | 0.350R |
| total, 7,239 top-20 trades | **+4.8R** |
| drop the single best symbol | **(52.1)R** |
| bootstrap P(total > 0) | 0.496 |

---

### 1. The one asymmetry that makes ORB different from everything else here

**ORB SIP is the only line in this project with a positive gross.**

| line | gross | status |
|---|---:|---|
| MCL (PIT book) | **(6.26)/trade** | loses before any cost |
| MC5 | negative | loses before any cost |
| VW9 | negative | loses before any cost |
| SPY intraday H-S1 / H-S2 | **(0.308) / (0.271) bps** | closed 2026-09-18 |
| **ORB SIP (resolved)** | **+0.351R** | **positive, 1 of 7 on other grounds** |

This matters for one reason and it is a narrow one. `spy_intraday_AMENDMENT_A_20260917`
§A.5 and `friction_reconciliation_20260911` §3 both argue that **venue choice,
commission reduction and conditioning gates cannot rescue a book with negative
gross** — there is nothing there to rescue. That argument is correct and it has
been used to shut down several proposals.

**It does not apply to ORB SIP.** Gross is +0.351R against friction of 0.350R.
This is the one place in the program where a cost reduction or a conditioning
rule could, in principle, move the number.

**Record that, and then read §2 before acting on it.** The reason ORB fails is
not friction.

---

### 2. Why it fails, stated so nobody mistakes the problem

The binding failure is **criterion 1, concentration** — not friction, not the
mean, not the fill model.

| | total |
|---|---:|
| resolved book | **+4.8R** |
| drop top 1 symbol | **(52.1)R** |
| drop top 3 | **(155.5)R** |
| drop top 5 | **(257.5)R** |
| drop top 10 | **(492.4)R** |

Top five: MWA +57R, TD +52R, NYT +51R, IONS +51R, THC +51R.

Underneath: of the 1,602 trades the one-second resolution freed from a phantom
same-bar stop, **1,301 (81.2%) re-reach the same stop within a minute or two and
die anyway**. Only **301 change outcome**, and those 301 carry **+2,536R** —
+8.43R each, median +4.6R, largest +46.9R — against a registered book of
(2,532)R.

**So the entire positive book is a few hundred trades.** Any proposal that
improves the *mean* without improving *drop-top-N* has not addressed the failure.
Hold every follow-up to that test.

---

### 3. Two standing facts for PROGRAM_INDEX, both new and both general

These are the durable output of the resolution and they outlive the strategy.

**(a) A minute bar's high and low have no order, and at a 10%-ATR stop that
ambiguity is worth 0.35R per trade.** 39.9% of top-20 trades had the stop price
touched during the entry minute. One-second bars settled it for **$0.00** inside
the Databento free window (2,888 symbol-days, 698.1 MB, every one resolved):

| verdict | trades | share |
|---|---:|---:|
| `stop_first` — no position existed to stop | **1,602** | **55.5%** |
| `entry_first` — genuinely stopped | 993 | 34.4% |
| `same_second` — unresolvable at this schema | 293 | 10.2% |

**More than half of the entry-minute stops never happened.** Any strategy whose
stop sits inside typical one-bar range needs this check **before its fill model
is believed** — this includes MCL, MC5 and VW9, whose stops sit well inside a
one-minute range.

**(b) Freeing a trade from a same-bar stop mostly does not save it.** 81.2%
re-reach the same stop. The change concentrates in a small tail. This is a
**drop-top-N question, not a mean question** — which is exactly why resolution
moved the mean by +0.35R and still could not move the verdict.

---

### 4. Three mistakes to refuse in advance

**(a) Do not re-score criterion 7 by comparing a resolved top-20 against an
unresolved top-40.** The seconds were bought for the primary cell alone, per
amendment E.2's scope. Ranks 21–40, the `eligible` and `unfiltered` arms and the
15-minute arm all still carry unresolved entry-minute stops. Ranking across them
would award the difference between two *readings*, not two cells — the
two-denominator refusal in PROGRAM_INDEX §4. Criterion 7 fails in both readings,
so the verdict does not turn on it, and it stays unscored.

**(b) The band is not the result.** `+0.058R` (band) and `+0.055R` (alternative,
charging no same-bar stops) are a **disclosed sensitivity** showing the width of
what one-second bars could not settle — 293 trades. E.2 fixed the recombination
**before the data was bought**: `same_second` keeps the stop, because that is the
conservative side. The figure of record is **+0.001R**. If a later doc quotes
+0.055R, it has quoted the optimistic arm as the answer.

**(c) The holdout stays unspent.** A closed line does not get a holdout look to
see whether it might have passed.

---

### 5. The one item worth pricing — market context — and the prior against it

From `source_videos_14_breitstein_20260918.md` §14.2–14.3.

Breitstein's dedicated ORB video (`QmPUp9ISuDw`) confirms what
`orb_strategy_spec.md` already recorded as blanks: **he states no stop and no
target.** They are not in public and nobody should go looking. What he does
specify is the range — first 30 minutes, **wick of the high to wick of the low** —
and four nuances: consolidation quality inside the range, **volume confirmation
on the break** (*"weak volume breakouts are far more likely to fail"*), **market
context**, and risk management over setup.

He also gives three use cases, which are context classifications rather than
rules: an **exhaustion gap** after a vertical run where the break *down* is the
trade; **day-one continuation** after a material catalyst, because
*"institutional money often cannot fully position immediately"*; and **macro
panic or euphoria on index instruments**, where *"everyone is watching the same
levels."*

**Market context is the only testable item, and it is nearly free.** It appears
in both that video and his breakout rubric, where he weights it as decisive:

> *"This one variable can single-handedly downgrade an A setup to a C or worse."*

`orb_sip_RESOLVED_20260918` leaves a resolved ledger of **7,239 top-20 trades**
on disk. Adding SPY's state as a column and re-splitting costs **no new data and
no re-run of the strategy.**

**The prior, stated honestly before anyone runs it:**

1. **A context gate does not fix concentration.** The failure is that one symbol
   is worth (56.9)R of swing. Splitting the book by market state produces two
   concentrated halves, not one clean one. **High confidence.**
2. **The volatility- and regime-gate family has now failed four times on this
   project's data** — `luck_vs_edge_RESULT_20260917` (hot/mixed/cold: flat across
   all three), `cold_veto_RESULT_20260917` (NOTHING), `spy_intraday_RESULT_20260918`
   H-S2 (0 of 5 gates, gross moved (0.308) → (0.271) bps, i.e. the gate did almost
   nothing on the cell where the literature said the effect lived), and the
   BandWidth squeeze pre-flight is registered to close on the same shape.
3. **The honest expectation is NOT ADOPTABLE.**

**So if it is run, it is run as a cheap measurement with a pre-registered
negative prediction, not as a rescue attempt.** Its value is that it retires an
open item on a source rather than leaving it to be re-proposed in three months.

**Scoring, if it runs:** the primary reading is **drop-top-N within each context
bucket**, not the bucket means. A bucket mean that improves while its drop-top-3
stays negative is the same failure wearing a different split. Date-level, never
pooled — ORB days are market-wide by construction and the clustering trap that
inverted the Bollinger dip-buy (pooled +0.286%/trade → date-level **(0.010)%,
t = (0.18)**) applies here with more force, not less.

**Volume confirmation on the break** is a second, separate candidate from the
same source. It is cheaper still — it is a column already in the bars — and it
has the same prior. If both are run, they are registered separately; a two-filter
grid on a book this concentrated is a search, not a test.

---

### 6. What is owed from the last session, unchanged

- Live MC5 rows need tagging as **apex-ON** in the fills ledger, per
  `mc5_apex_live_split_20260917.md`. The live path emits `exit_signal` ungated at
  `strategy/mc5/mc5.py:378` while the backtest gates it at `:561`; 25
  `gradient_reversal` rows are already in `var/fills/mcl_fills_20260911..17.csv`.
  Until those rows are tagged, live and backtest MC5 are not the same strategy and
  should not be compared as though they were.
- The TradingView feed carries a **15-minute delay**; anything reading it for a
  live decision is reading stale prices.

---

*(End of message to the ORB build chat.)*
