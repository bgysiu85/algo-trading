# H-B1 — skip the first entry: NOTHING, and the live table does not replicate

2026-09-17. Registered `docs/research/REGISTERED_first_entry_skip.md` (committed before
the code existed), run on the point-in-time universe: 551 sessions, 6,170 symbol-days,
XNAS.BASIC, flat 100, `first_seen` floor, 81.5 s on 8 workers. Raw:
`D:\Trading\Claude outputs\first_entry_skip_20260917.txt` and
`time_of_day_pit_20260917.txt`. MCL's book counts **3,955** — matches the published figure.
All figures at **$4.26** friction unless the line says otherwise.

---

## 0. The one-paragraph verdict

**MCL: NOTHING** — it fails the both-halves reading, and the reading it "passes" is the
one that cannot fail on a losing book (§3). **MC5: REFUSED** — its two denominators
disagree (−1.05 per trade, +4.71 per symbol-day). The rule cuts MCL's trade count from
3,955 to 1,953 and leaves the per-trade figure where it was: **−$10.49 against
−$10.52.** The live table that motivated this — first entries −$21.97 a trade, later
entries +$0.53 — is not what 6,170 symbol-days say: **first trades −$11.08, later trades
−$9.64**, both losing, $1.44 apart. The rule also removes **8 of MCL's 10 best trades** and
8 of MC5's. Entries removed: 2,002 (MCL), 2,492 (MC5). Losses avoided and winners lost,
under the accounting form: MCL −$46,969 avoided against +$20,215 lost; MC5 −$87,003 against
+$43,354. Net effect on MCL: loses $21,112 less **by trading half as much**, not by trading
better.

---

## 1. The books

| book | trades | net | per trade | per symbol-day | halves (early / late, per trade) | drop-top-3 | win |
|---|---:|---:|---:|---:|---|---:|---:|
| MCL | 3,955 | (41,598.92) | (10.52) | (6.74) | (10.68) / (10.40) | (43,469.18) | 22.2% |
| **MCL-skip1** | 1,953 | (20,487.04) | (10.49) | (3.32) | (10.58) / (10.43) | (21,513.03) | 23.2% |
| MC5 | 6,883 | (92,903.63) | (13.50) | (15.06) | (14.89) / (12.44) | (99,624.56) | 21.2% |
| **MC5-skip1** | 4,391 | (63,871.42) | (14.55) | (10.35) | (15.94) / (13.48) | (66,315.40) | 20.7% |

Sign stable across $1.00 / $4.26 / $8.92 in every book: everything loses at every level.

## 2. The four registered readings

| reading | MCL-skip1 vs MCL | MC5-skip1 vs MC5 |
|---|---|---|
| 1. both denominators improve | per trade **+0.03**, per symbol-day +3.42 — both > 0 | per trade **−1.05**, per symbol-day +4.71 — **REFUSED** |
| 2. both halves, both denominators | early +0.10 / +1.52; late **−0.03** / +1.91 — **fails** | (not read; refused at 1) |
| 3. drop-top-3, level and delta | level (21,513) vs (43,469); delta +20,398 — holds | level (66,315) vs (99,625); delta +26,813 |
| 4. cluster bootstrap on the delta | P = 1.000 [+16,266, +25,585], 1,231 symbols — holds | P = 1.000 [+15,232, +39,563], 1,496 symbols |
| **verdict** | **NOTHING: fails 2** | **REFUSED** |

Cost lines, both strategies: 8 of the baseline's top-10 trades are absent from the skip
book (QMMM +946, UPC +476, EPSM +408, UPC +401, WBUY +399, TTRX +382, ARTL +358, HCAI +315
for MCL; UVIX +5,461 heads MC5's list). The signal-ordinal form did run: 417 MCL-skip1 and
1,360 MC5-skip1 entries are bars the baseline never entered on — the cascade the
registration said to look for, and the reason the skip book is not a subset.

## 3. What the readings that "held" were measuring

Items 3 and 4 held for both strategies, with bootstrap P = 1.000. **That is not evidence
for the rule.** Every trade in these books loses $10–15 on average; a rule that takes half
of them away must improve the per-symbol-day total, must improve it after dropping any
three days, and must improve it in every resample of symbols, because every symbol's
deleted trades were, on average, losers. The bootstrap on the delta measured *trades
less* with certainty and *trades better* not at all. **Per trade is the only line in the
table that asks the second question, and it says +$0.03.**

The registration required both denominators (item 1) and both halves on both (item 2),
which is what stopped this reading PASSES on MCL; but it would have been better to say
in advance what §3 below now says for the next three hypotheses. I am recording that as
a defect in the registration rather than in the result.

## 4. The accounting form, and the live table

| | first trades removed | per trade | losses avoided | winners lost | later trades kept | per trade |
|---|---:|---:|---:|---:|---:|---:|
| MCL | 2,415 | **(11.08)** | 1,896 · (46,969.00) | 519 · +20,214.87 | 1,540 | **(9.64)** |
| MC5 | 3,731 | (11.70) | 2,933 · (87,003.40) | 798 · +43,354.05 | 3,152 | (15.63) |

This is the construction the live 09-09..09-16 table used (37 first entries at −$21.97,
97 later at +$0.53). On the point-in-time books the first and later trades are $1.44
apart for MCL and the *later* trades are worse for MC5. The live table was six sessions
of a circular cut, and it does not replicate. **First entries are not the problem; the
book is.**

## 5. Time of day — the question closes

The block table on the same MCL book, 30-minute ET blocks, all three frictions, halves,
drop-top-3 and the session denominator: **every block is negative at every friction
level**, every drop-top-3 is negative, and no block has a positive session median. The
named cell, **07:45–08:00**, which the stale run had at +$20.98 a trade: **161 trades,
(2,957.11), (18.37)/trade, drop-3 (3,682.35), halves (1,565.20) / (1,391.91), 131 sessions
with a median of (19.83)** — fails all four of the checks written before the numbers. The
hour 07:00–08:00: 894 trades, (9,677.54), 404 sessions of which 21.0% positive. Under
registration §4, **the time-of-day question closes and the 07:00-window backlog item
comes off.**

The one non-negative cell in either table is MC5's 04:00–04:30 block: +$367 at $4.26,
(2,484) at $8.92, and drop-top-3 (6,039) on 612 trades. Concentration, described and not
read.

## 6. What this changes for H-B2, H-B3 and H-B4

The handover's test — *a filter only helps if it removes more loss dollars than winner
dollars* — is satisfied on these books by **any** rule that removes trades, including a
coin flip, because the average trade loses. So the next three registrations carry two
things this one did not, written now, before any of them has a number:

1. **The abstention control.** Alongside the filter, the same number of trades removed
   at random from the baseline (2,000 draws, seeded), giving the distribution of
   per-symbol-day and per-trade deltas that *trading less* produces on its own. The
   filter's per-trade delta must sit above the 95th percentile of that distribution.
   A filter that cannot beat random removal is not selecting.
2. **Per trade carries a margin.** Item 1 becomes Δ per trade ≥ $4.26 (one round trip of
   friction, `MIN_MARGIN` as v5 used it) and Δ per symbol-day > 0, rather than both merely
   positive. +$0.03 a trade should never have been able to satisfy an item.

H-B2 additionally needs the concurrency cap modelled (§7 item 15) before it can be run
at all; H-B3 and H-B4 can be registered against these books directly, since the baseline
CSV now carries every trade with its entry time.

Catalogue entry for `PROGRAM_INDEX` §4: **on a losing book, a total-based reading rewards
abstention.** Per-symbol-day, drop-top-N on the delta, and a bootstrap on the delta all
pass for a rule that trades less; only per trade, against an abstention control, asks
whether it trades better.

---

## 7. What this is not

Not out of sample — MCL was fitted on this calendar; `holdout.json` is untouched. Not a
cap model — each symbol-day ran alone, so the slot a skipped entry frees is not priced.
Not the variant — "skip until a new session high after the first signal" was named and
not run, and this result gives no reason to run it: the first entry is not worse than the
rest.

## Commands already run (for the record)

```
python -m common.first_entry_skip --jobs 8
python -m common.time_of_day
```
