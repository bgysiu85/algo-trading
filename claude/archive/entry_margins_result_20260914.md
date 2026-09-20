# Entry margins: 112 buckets, none positive

**Date:** 2026-09-14 · `var/reports/entry_margins_mcl.txt`
**Population:** 3,955 point-in-time MCL trades over 551 sessions — **matches
`pit_strategy`'s published book exactly**
**Origin:** Ben, 2026-09-14 — *"all the trades they have entered should never
have been entered. The volume is incredibly light and no momentum whatsoever."*

---

## The result

Six clause margins plus a combined tightest-clause measure, four quartiles each,
across four splits (all / 1st half / 2nd half / less-top-5).

> **112 bucket means. Zero positive.** Best cell −$6.02, worst −$13.46, book
> average −$9.16 per trade at $4.26 friction.

Every column returned NOTHING under the pre-registered rule. There is no subset
of "qualified more comfortably" that makes money, in either direction.

## Ben was right about the bars

Dollars traded on the entry bar — a quantity **no entry clause reads**:

| under | entries | share |
|---|---|---|
| $5,000 | 47 | 1.2% |
| $25,000 | 472 | 11.9% |
| $50,000 | 940 | 23.8% |
| **$100,000** | **1,572** | **39.7%** |
| $250,000 | 2,525 | 63.8% |

Minimum **$1,380**. Median $147,969. **Four entries in ten fired on a bar that
traded under $100,000.**

**But the session was never thin.** Cumulative session dollar volume at the
moment of entry had a *minimum* of $158,706 and a median of $4.17M. The name was
trading. The *minute* was not — a different problem from the one it looks like,
and the one the rule is blind to.

## Ben was wrong about the momentum

This is where the measurement disagrees with the impression.

| clause | rule | median | within a hair |
|---|---|---|---|
| rsi_slope | `rsi − rsi[3] > 0` | **11.35 pts** | 0.2% |
| mfi_slope | `mfi − mfi[3] > 0` | **15.56 pts** | 0.4% |
| macd_margin | `macd > macd_sig` | 0.020 | 0.5% |
| macd_level | `macd > 0` | 0.048 | 0.5% |
| vol_multiple | `vol ≥ 3× prev` | 4.45× | **14.4%** |
| floor_margin | `prev ≥ 0.5× mean` | 0.99× | **8.3%** |

The median entry had RSI up 11 points over three minutes and MFI up 15. Only
two to five entries per thousand were within a hair of failing a sign test.
The marginal clauses are the two **ratios** — and those are exactly the clauses
that measure the tape against itself.

So the entries are not crossings dressed as trends. They have indicator
momentum. What they lack is **size**.

## A floor would not have saved it

| floor | removed | the removed | kept, 1st half | kept, 2nd half |
|---|---|---|---|---|
| none | — | — | (9.36) | (8.98) |
| $5,000 | 47 | (9.89) | (9.32) | (9.00) |
| $25,000 | 472 | (7.85) | (9.76) | (9.00) |
| $100,000 | 1,572 | (9.01) | (10.78) | (8.15) |
| $250,000 | 2,525 | (8.72) | (13.10) | (7.93) |
| $1,000,000 | 3,524 | (9.04) | (15.67) | (6.65) |

**The removed trades lose the same as the kept ones.** At every level from
$5,000 to $1,000,000 the deleted entries average −$7.85 to −$9.89 against a book
averaging −$9.16. They are not a distinct population; there is nothing to cut
away.

And the halves **disagree about direction**: raising the floor makes the first
half monotonically worse (−9.36 → −15.67) while the second half improves
(−8.98 → −6.65). A level that helps in one half and hurts in the other is noise
wearing a rule's clothes.

## Binding clause: evenly spread

vol_multiple 19.4%, macd_level 17.9%, mfi_slope 17.8%, floor_margin 17.0%,
rsi_slope 14.7%, macd_margin 13.3%. No clause is vestigial and none is doing
disproportionate work.

## What this closes, and what it does not

**Closes:** the entry-quality lever in the form it was asked. Six margins, a
combined measure, 112 buckets, both halves, drop-top-5 — nothing separates.
The entries *are* thin, and the thin ones are not what is losing the money.

**Does not close:** whether there is an edge here at all. Every instrument so
far — 22 features / 88 buckets; two populations at entry; four exit levers; now
seven margins — asks the same shape of question: *can MCL's own entries be
subsetted into a winning book?* The answer has been no every time, which is a
strong answer about **subsetting** and a weak one about the **universe**.

## The thread that keeps reappearing

Bigger is worse, not better, across independent instruments:

- **session dollar volume** — quietest quarter beat the busiest, both halves (WEAK)
- **macd_margin** — smallest quarter is the best bucket here (−6.94); third-largest the worst (−11.89)
- **rsi_slope, mfi_slope** — the steepest quarter is the worst bucket in both halves
- **close_in_bar** (measured separately) — the losses sit in entries that paid the top tick of the bar

MCL fills at the **close of a bar its own rule requires to be a 3× volume
spike**. The consistent direction of all of these is that *paying up into the
spike* is the expensive part — a claim about the **fill**, not about the
**filter**, and one that has never been tested directly.

That is the next pre-registered question, and it is a different question from
every one asked so far.
