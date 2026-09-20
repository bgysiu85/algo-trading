# H-B3 — rank by session range: NOTHING, and the gate did what a coin flip does

2026-09-17. Registered `docs/research/REGISTERED_range_rank.md` (committed before the
gate existed), run on the point-in-time universe: 551 sessions, 6,170 symbol-days,
XNAS.BASIC, flat 100, `first_seen` floor, 77.8 s on 8 workers. Raw:
`D:\Trading\Claude outputs\range_rank_20260917.txt`. MCL's book counts **3,955** —
matches. All figures at **$4.26** friction unless the line says otherwise.

---

## 0. The one-paragraph verdict

**MCL: NOTHING. MC5: NOTHING.** Both fail reading 1 (the $4.26 margin on per trade)
and reading 5 (the abstention control). The gate bound on **85% of MCL's entries** and
**83% of MC5's** — my registered expectation that it would rarely bind was wrong; the
point-in-time watchlist has four to fifteen names visible at most signal minutes — and it
refused **2,189 of MCL's 3,955 trades** (55%) and 3,070 of MC5's 6,883. Per trade moved
**+$0.86** (MCL) and **+$0.96** (MC5). Removing the same number of trades **at random**
moves per trade by +$1.27 (MCL) and +$1.34 (MC5) at the 95th percentile, with a median of
+$0.01 and +$0.08: the gate's per-trade gain sits inside the band that no selection at
all produces. Per symbol-day the gate reads +$3.97 for MCL; random removal of the same
count reads +$3.73 at the median. **Ranking on session range removes trades; it does not
choose them.** That is what `won_vs_lost_20260916.md` said `range_pct` would do, and it
did. Entries removed: 2,185 (MCL), 3,021 (MC5). Losses avoided / winners lost among the
refused trades: MCL −$41,605 / +$17,041; MC5 −$72,783 / +$27,234. Four of each
strategy's ten best trades are gone.

---

## 1. The books

| book | trades | net | per trade | per symbol-day | halves (per trade) | drop-top-3 | win |
|---|---:|---:|---:|---:|---|---:|---:|
| MCL | 3,955 | (41,598.92) | (10.52) | (6.74) | (10.68) / (10.40) | (43,469.18) | 22.2% |
| **MCL-top3** | 1,770 | (17,103.36) | (9.66) | (2.77) | (9.16) / (10.20) | (18,358.23) | 22.8% |
| MCL-top1 (reported) | 581 | (4,929.09) | (8.48) | (0.80) | (9.17) / (7.54) | (6,002.55) | 22.7% |
| MC5 | 6,883 | (92,903.63) | (13.50) | (15.06) | (14.89) / (12.44) | (99,624.56) | 21.2% |
| **MC5-top3** | 3,862 | (48,409.82) | (12.53) | (7.85) | (13.59) / (11.53) | (50,173.86) | 22.3% |
| MC5-top1 (reported) | 1,850 | (19,904.14) | (10.76) | (3.23) | (12.16) / (9.24) | (21,810.18) | 23.5% |

Sign stable at $1.00 / $4.26 / $8.92 in every book. Every book loses; the tightest gate
still loses $8.48 a trade on MCL.

## 2. The five registered readings

| reading | MCL-top3 vs MCL | MC5-top3 vs MC5 |
|---|---|---|
| 1. Δ per trade ≥ 4.26 · Δ per symbol-day > 0 | **+0.86** · +3.97 — **fails** the margin | **+0.96** · +7.21 — **fails** the margin |
| 2. both halves, both denominators | early +1.52 / +1.53; late +0.20 / +2.44 — holds | early +1.30 / +3.03; late +0.91 / +4.18 — holds |
| 3. drop-top-3 level · delta | (18,358) vs (43,469) · +23,902 — holds | (50,174) vs (99,625) · +43,449 — holds |
| 4. cluster bootstrap on the delta | P = 1.000 [+20,084, +28,571], 1,231 symbols — holds | P = 1.000 [+31,174, +54,362], 1,496 symbols — holds |
| 5. abstention control (2,000 draws) | random per trade p05 −1.27 · p50 +0.01 · **p95 +1.27**; the gate **+0.86** — **fails** | random p05 −1.39 · p50 +0.08 · **p95 +1.34**; the gate **+0.96** — **fails** |
| **verdict** | **NOTHING: fails 1, 5** | **NOTHING: fails 1, 5** |

Readings 2, 3 and 4 hold for both, as they held for H-B1, and for the same reason: they
are built from totals, and on a book whose average trade loses $10–15, any rule that
removes half the trades passes them. Reading 5 is the one that asks the question, and
the answer is that the gate's per-trade gain is indistinguishable from random removal
of the same count. Per symbol-day makes the same point from the other side: the gate
+3.97, random removal's median +3.73, its 95th percentile +4.09 — the gate's whole
headline is abstention.

**The reported cell, top-1**, tightens the same way on both sides: MCL +$2.03 per trade
against random's p95 +$2.88; MC5 +$2.74 against +$3.02. Closer, still under, and the
tighter the cut the wider random removal's band — a form of the rule that removed 85% of
the trades would need to beat a much higher bar. Declared before the run, not read.

## 3. Did the gate run? Yes

| | MCL-top3 | MC5-top3 | MCL-top1 | MC5-top1 |
|---|---:|---:|---:|---:|
| baseline entries where the gate could refuse | 3,359 (84.9%) | 5,728 (83.2%) | 3,881 (98.1%) | 6,701 (97.4%) |
| refused, exact | 2,189 | 3,070 | 3,379 | 5,092 |
| cascade (gated entries the baseline lacks) | 4 | 55 | — | — |

Visible names at MCL's signal minutes: one name at 74 entries, two at 231, three at 291,
then 374 / 325 / 389 / 349 / 337 at four through eight, and a tail to fifteen-plus. The
registration expected a median of one and said so; the point-in-time file's 9.1
candidates a session are mostly all visible by the time MCL fires. **The expectation was
wrong, the gate bound, and the result is a result, not an absence.**

## 4. What it refused

| | refused | per trade | losses avoided | winners lost | top-10 absent |
|---|---:|---:|---:|---:|---:|
| MCL-top3 | 2,189 · (24,563.91) | (11.22) | 1,713 · (41,605.26) | 476 · +17,041.35 | 4 (QMMM +946, UPC +476, UPC +401, TTRX +382) |
| MC5-top3 | 3,070 · (45,548.59) | (14.84) | 2,468 · (72,782.97) | 602 · +27,234.38 | 4 (UVIX +5,461, BTCT +520, MBX +493, UPC +443) |

The refused trades lose $11.22 a trade for MCL against the book's $10.52 — the gate is
refusing a slightly worse-than-average slice, which is the +$0.86, and random removal
finds a slice that bad one draw in twelve.

## 5. What this changes

Two of the four B-series hypotheses are read and both say the same thing from different
directions: **the losing trades are not marked.** Not by being first in the name (H-B1),
not by the name being quieter than its neighbours (H-B3). `entry_features` (22 features,
0 of 11 families), `entry_margins` (112 buckets, none positive), and `won_vs_lost` said
this about bar features and about Ben's own selection before either was run.

The abstention control did its job on its first outing. Without it, reading 1's margin
alone would have carried the verdict, and a future gate with a +$4.50 per-trade gain on a
70% removal would have passed readings 1–4 while random removal's p95 sat at +$5. Keep
it, and keep the per-symbol-day quantiles beside the gate's number, because that is the
line that shows the abstention share of a headline in one look.

**H-B4** (the same-day cold veto after 07:00) is a gate of the same shape and runs on the
same runner. **H-B2** waits on the concurrency cap. **B5**, the combination, has nothing
to combine.

## 6. What this is not

Not out of sample. Not a cap model: this gate is the ranking rule the cap would need,
and that combination is B2, not this. Not the tape: ranking against every symbol in the
archive is what `universe_lift` measured (14.85× at top 5) and it is not implementable
live. Not `dollar_vol` or `gap_pct`; each would be its own registration, and after two
NOTHINGs on selection I would not register either without a reason the record does not
currently give.

## Commands already run

```
python -m common.range_rank --jobs 8
```
