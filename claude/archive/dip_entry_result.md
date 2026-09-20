# Dip buying, measured — and the three defects the run exposed

Run 2026-09-11, `common/dip_study.py`, 66 training sessions of `bar_cache`
(the holdout side untouched). Report at `var/reports/dip_entry.txt`.

## 0. Why this was built

`warrior_census_20260910.md` §6 puts `dip_buy` at **129 mentions** against the
micro pullback's 172, at the **same 0.7 red-day lift**. MCL implements the
second and nothing in the repository implements the first. Given
`HANDOVER_TO_BUILD_20260910.md` §0 — MCL is Ben's own version of this method,
loosely derived — this is not a strategy we declined to build. It is half a
method inherited without noticing.

Four independent findings in this project already pointed at the same
mechanism, which is why it outranked the 129 mentions on its own:

| finding | reading |
|---|---|
| `premarket_hypotheses_results_20260908.md` §2 | every confirmation entry made the screen worse: H0 +$4.72/trade, H1 −$8.44, H2 −$12.21 |
| `consolidation_filter_test.md` §2 | entries into a **contracting** range +$10.09/trade, into an **expanding** range −$0.85, both halves |
| `hold_cap_decision.md` §4 | 1-bar holds: 107 trades at −$36.68 |
| Ben, 2026-09-10, on MCL and again on MC5 | *"all the entries were enter at the close of the 5min bar and much of the move were gone by then"* |

Four readings, four methods, one direction: **our entries are late.** Dip
buying is the named, sourced strategy that is late's opposite.

## 1. What was built, and what deliberately was not

**A measurement, not a strategy**, following `warrior_4_reversal.md` §5 item 2.
The reason is in §6 of that same document: the two dip videos (`ORWJzImSTdE`,
`hz7vhSIXXSc`) are **untranscribed**, so there is no stated dip-buy rule to
implement. `common/dip_entry.py` is inferred from the shape the census names
plus the four findings above. Shipping an engine off an inference and then
scoring it is a different exercise from testing a rule.

Every parameter derives from something already settled. **Nothing swept:**

| knob | value | derivation |
|---|---|---|
| impulse_min | 10% | 2 × `TRAIL_PCT` — smaller is inside the noise the stop already tolerates |
| dip_min | 5% | 1 × `TRAIL_PCT` — shallower is a wiggle MCL would not have been stopped out of |
| hold_min | 0.50 | the hold-50% rule, `warrior_5_selection_in_practice` §1 |
| dip_max | 0.50 | `1 − hold_min`. **Not a fifth knob** — a pullback past half the impulse *is* a hold-50% failure |

Scored on **MFE and MAE**, never P/L. Scoring with an exit model would put the
exit — the project's largest open question — inside the answer. MFE and MAE
need no exit rule. They are reported together and never apart, because **MFE
alone rewards an earlier entry for being earlier**: there is simply more session
in front of it.

## 2. The result

| bucket | n | MFE | MAE | MFE/MAE | early | late |
|---|---:|---:|---:|---:|---:|---:|
| BOTH fired (dip) | 35 | 45.4% | 12.2% | 5.09 | 6.95 | 4.69 |
| BOTH fired (MCL) | 35 | 49.2% | 15.4% | 3.34 | 5.67 | 2.50 |
| **DIP ONLY** | **24** | **28.4%** | **23.9%** | **1.49** | **1.49** | **2.48** |
| MCL ONLY | 2 | 26.3% | 1.4% | 18.67 | — | 18.67 |

Median fill difference on the paired sessions: **+4.5%** — the dip entry buys
that much lower. The dip fired **earlier on 18** sessions and **later on 17**.

**The paired advantage is arithmetic.** Buy the pullback instead of the
breakout and the price is lower every time; the ratio rises for that reason
alone. The study was built around this trap.

**The question is DIP ONLY** — the 24 setups the confirmation entry refused and
dip buying would take. They come in at **1.49 against MCL's 3.34, in both
halves.** Buying into the pullback picks up setups MCL was right to skip.

> **Verdict: not adoptable as measured.** And note what that does *not* say —
> a detector inferred from four adjacent findings failing is evidence about the
> inference. The census still has dip buying at 129 mentions and a 0.7 lift, and
> the two videos that state the actual rule are untranscribed. **Transcribing
> `ORWJzImSTdE` and `hz7vhSIXXSc` is now the highest-value item on this thread.**

One reading worth carrying separately: **roughly half the signals (17 of 35)
fired *after* MCL's entry.** Those are re-entries into a position MCL already
holds, not earlier entries. Whatever this detector is finding, it is not
uniformly the earlier version of the same setup.

## 3. Three defects the first real run exposed

All three are the project's recurring shape — **a control whose output is
indistinguishable from the failure it detects** — and all three are now pinned
by tests.

**1. The baseline was empty and the report called it a win.**
`Trade.entry_time` is a **string**, not a Timestamp. The position map was keyed
by Timestamp and matched **none of 71 real MCL trades**. MCL's median ratio came
out 0.00, every positive dip reading cleared it, and the report printed *"THE
ADDED TRADES STAND ON THEIR OWN"*. Fixed twice over: `strict_positions` now
**raises** on an unmatched entry rather than dropping it, and `render` refuses a
verdict when the baseline bucket is empty.

**2. The detector was scanning the warm-up days.** `load_sessions` returns a
**three-day** frame; MCL trades only 04:00–09:30 of the last day. Unbounded, the
detector fired on prior sessions — the first run reported dips a median of **245
bars** (four hours) "earlier" than MCL's entry and scored their excursion over
everything that followed. **Bounding it moved DIP ONLY from 4.86 to 1.49 and
flipped the verdict.** The window is imported from MCL rather than restated.

**3. An empty half read as a refutation.** An empty half has a median of zero
and fails the both-halves test for exactly the same reason a genuinely bad half
does. It now gets its own NO VERDICT branch.

## 4. What is not in here

- **His stop.** Three of his setups land on 10–20c (`warrior_4` §3) and that
  cent stop was measured and **rejected** on 2026-09-10 on the price band.
  Putting it back inside a test of the *entry* would confound the two.
- **His level-2 trigger** (`warrior_1` §3b). No level 2 in the backtest, and a
  proxy would be a fifth parameter.
- **P/L**, for the reason in §1.
- **The holdout.** Untouched — `--spend-holdout` exists and was not passed.
