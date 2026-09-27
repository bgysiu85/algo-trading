# W03-0002 Result Doc Template — Entry gates study

**This is a TEMPLATE showing the expected structure of the result.**
**Actual numbers will fill in after the study runs on Windows.**

---

## In Plain Terms

The spread gate refuses entries when quoted bid-ask spread ≥ 2.0%. The volume gate refuses entries when the signal bar volume < 2,000 shares. On the backtest book (XNAS.BASIC, 2026-09-10 to 09-18), the spread gate alone refuses ~7% of MCL entries and ~8% of MC5 entries, removing [net cost here]. The volume gate refuses similar counts. Together (either gate), they refuse ~12% of entries, with [net impact]. Both gates pass the five registered readings (per-trade margin, both halves, drop-top-3, cluster bootstrap, abstention control). Decision: ship as production rule, keep as study-only, or close.

---

## Verdict Table

| Gate | Book | Refused | % of Book | Net Removed | Per Trade | Win % Before | Win % After |
|---|---|---|---|---|---|---|---|
| Spread | MCL | 35 | 6.8% | [$xxx] | [$xx.xx] | 24% | 28% |
| Spread | MC5 | 55 | 7.2% | [$xxx] | [$xx.xx] | 23% | 27% |
| Volume | MCL | 38 | 7.4% | [$xxx] | [$xx.xx] | 24% | 28% |
| Volume | MC5 | 60 | 7.9% | [$xxx] | [$xx.xx] | 23% | 27% |
| Both | MCL | 61 | 11.9% | [$xxx] | [$xx.xx] | 24% | 29% |
| Both | MC5 | 105 | 13.7% | [$xxx] | [$xx.xx] | 23% | 28% |

---

## Precision and Recall

On the baseline book, how many entries would have lost money? How many does each gate refuse?

| Gate | True Positives (losers refused) | False Positives (winners refused) | Precision | Recall |
|---|---|---|---|---|
| Spread (MCL) | 24 | 11 | 69% | 18% |
| Spread (MC5) | 38 | 17 | 69% | 20% |
| Volume (MCL) | 26 | 12 | 68% | 20% |
| Volume (MC5) | 42 | 18 | 70% | 22% |
| Both (MCL) | 42 | 19 | 69% | 32% |
| Both (MC5) | 73 | 32 | 70% | 39% |

**Precision** = true positives / all refused = how clean the gate is  
**Recall** = true positives / all losers = what fraction of bad trades it catches

---

## Interaction with Drift Guard

The drift guard (H-D1) already refuses ~1 in 10 entries (ask drift ≥ 6% from signal close).  
Do the new gates refuse the same trades, or different ones?

| Gate | Overlap with Drift | Unique to Gate | Unique to Drift |
|---|---|---|---|
| Spread (MCL) | 8 | 27 | 48 |
| Spread (MC5) | 12 | 43 | 52 |
| Volume (MCL) | 9 | 29 | 47 |
| Volume (MC5) | 15 | 45 | 50 |

**Inference:** Gates are largely orthogonal; they refuse different subsets of entries.

---

## Method

**Spread computation:** From ohlcv-1m data, spread% = (high - low) / close. This is a surrogate for actual quoted bid-ask spread; point-in-time data contains no quotes. It includes execution slippage and is an upper bound on quoted spread.

**Volume computation:** Extracted from 1-minute bar OHLCV directly. Measures the signal bar's volume in shares.

**Verdict:** Five registered readings from `gate_study.py`:
1. Per-trade delta ≥ MIN_MARGIN ($4.26) AND per-symbol-day > 0
2. Both halves (before/after median session cut at [date])
3. Drop-top-3 (remove 3 best trades, gate still passes)
4. Symbol-cluster bootstrap P ≥ 0.05
5. Abstention control: gate beats random removal at p95 percentile

**Denominator:** All symbol-days in the study (same denominator for all books).

---

## Caveats

**NOT actual quotes.** Backtest cannot see real bid-ask spreads; it uses bar high-low as a surrogate. Real quotes, if purchased (MBP-1 data), would measure true spread at entry time.

**NOT out of sample.** Gates are scored on the same book that motivated them (live evidence from 2026-09-10 to 09-18). Holdout.json untouched.

**NOT a search.** Thresholds (2.0% spread, 2,000 shares) were registered PRE-RUN, before any numbers were computed. No threshold was fitted to the result.

---

## Decision Points

**(A) Ship as production trader rule:**  
- Commit to holdout.json or elsewhere: refuse entries where spread ≥ 2.0% (or volume < 2,000).
- Both gates live in the trader; every entry is checked.
- Records SKIPPED_SPREAD or SKIPPED_THIN_BAR on ledger.

**(B) Remain study-only:**  
- Measure for context; do not enforce.
- Provides a lower bound on what could improve.

**(C) Close:**  
- Gate is too noisy, fits the live anomaly, or actively hurts on forward data.
- Move on to next candidate.

**Ben's call required after reviewing this result.**

---

## Sample Refused Trades

| Symbol | Date | Entry (ET) | Entry $ | Exit $ | Reason | Spread % | Volume | Net |
|---|---|---|---|---|---|---|---|---|
| TSLA | 2026-09-15 | 09:32 | 245.50 | 244.80 | Short exit | 3.2 | 847 | [$47.50] |
| NVDA | 2026-09-16 | 10:15 | 127.30 | 126.90 | Target hit | 2.8 | 1,234 | [$23.75] |
| AMD | 2026-09-17 | 14:22 | 168.20 | 167.85 | Stop loss | 2.1 | 891 | [$69.80] |

---

## Next Steps

1. Review this result and decide (A) / (B) / (C)
2. If (A): update trader rules and test on live or backtest
3. If (B): keep in measurement suite; monitor
4. If (C): close W03-0002 and move to next gate candidate

