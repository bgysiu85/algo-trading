# EDGAR coverage: 80.2% of symbol-days — and a defect in the screen simulator

**Date:** 2026-09-14 · **Report:** `var/reports/edgar_coverage.txt`
**Cost:** one HTTP request · **Bundle carrying the fix:** `20260914x`, ref `main`

---

## The number

|  | matched | of | rate |
|---|---|---|---|
| symbols | 1,592 | 2,123 | **75.0%** |
| symbol-days | 4,948 | 6,170 | **80.2%** |

531 symbols missing, 1,222 symbol-days. The pull would cost 1,592–3,184
requests, **4–8 minutes**.

## The rate is not the finding. The shape of the miss list is.

I set 80% of symbol-days as the threshold before seeing the number, and it came
in at 80.2%. Treating that as a pass would be arithmetic standing in for
judgement, because **the misses are not a random sample of the universe.**

The top of the miss list is JFBR, NLSP, BNZI, ATNF, BSLK, SGBX, SLRX, VVPR,
FFIE, ICCT, NAOV, STSS, AGRI, CREV, DATS, SSKN, SYTA, VERO — which is to say,
**the strategy's own target population**: delisted and reverse-split microcaps.
Those are exactly the names most likely to be low float, so the 20% that EDGAR
cannot resolve is concentrated in the part of the universe a float criterion
would have the most to say about.

53% of the misses appear on exactly one session, against 43% across the whole
universe — consistent with the miss list being dominated by names that stopped
existing.

**What that means for a filter.** Shares outstanding is a CEILING test: it can
only ever *exclude* a name for having too many shares. A symbol with no match is
never excluded, so the filter would apply to 80% of symbol-days and let the
other 20% through untouched. It is therefore **weaker than it looks, not wrong**
— which is survivable, and only survivable if every downstream figure states
the covered fraction rather than quoting a rate over the matched subset alone.

## The thing worth more than the coverage figure

Two of the misses are **`ZVZZT` and `ZJZZT` — NASDAQ test symbols.** Not
securities: venues publish them continuously so members can verify connectivity,
and they carry real-looking prices and volume on a tape that makes no
distinction. SEC has no CIK for them, which is why the coverage check listed
them and why they were visible at all.

`common/screen.py` has excluded test symbols since it was written — the comment
there records ZVZZT as the second most frequent name in its first candidate
list. **`common/screen_at.py` never did**, and `screen_at` is what produces
`screen_pairs_pit.json`, the point-in-time universe that `pit_h0` and
`pit_strategy` score.

So the daily screen and the simulated screen disagreed about what a universe
*is*, silently, and the constant everything is measured against came from the
one that disagreed. This is the project's recurring defect — two things that
look comparable and are not — found from a direction nobody was looking in.

**Bounded, and the bound is worth stating precisely:**

| | |
|---|---|
| contaminated symbol-days | **4 of 6,170** (0.065%) |
| which | ZVZZT on 2024-11-22, 2025-01-02, 2025-01-03; ZJZZT on 2025-07-17 |
| displacement of real names | **none** — no session in the universe reaches `MAX_SYMBOLS = 40` |
| highest rank reached | ZVZZT was **first_rank 1** on 2025-01-03 |

Four rows cannot move a net measured over 5,606 trades by anything material, so
**the published H0 constants stand.** They were, however, measured over a
universe containing those four rows, and that is now on the record rather than
in the data unremarked.

**Fixed in `20260914x`:** both `screen_at` and `screen_sim` now apply
`screen.is_test_symbol`, from that **one** definition — two lists of test
tickers under two names agree right up until one of them is updated, which is
this same defect one level up. A test asserts neither module grows its own copy,
and both exclusions were checked to fail the suite when removed.

`screen_pairs_pit.json` still holds the four rows. Correcting that is a universe
rebuild, and it is worth batching with the next one rather than triggering one
for 0.065%.

## Recommendation

**Run the pull.** 4–8 minutes, cached and resumable, and the coverage is enough
for a ceiling test provided the covered fraction travels with every figure.

What it then feeds is **not a filter but a measurement**: shares outstanding
becomes one more feature bucketed against entry outcomes, under the same
discipline as `entry_features` — both halves, drop-top-N, every bucket printed,
multiplicity counted by family, and the 20% uncovered reported as a population
the test cannot answer for rather than quietly dropped.

That is the honest form of the question Ben has been pushing on since
yesterday — *are we selecting the wrong entries* — and it is worth noting that
88 buckets across 22 features have already failed to separate. Shares
outstanding is the first feature tried that is not derived from the same
price-and-volume tape as the other 22, which is the only reason to expect
anything different from it.
