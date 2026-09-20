# The lag is refuted — two other defects found — 2026-09-12

`python -m common.screen_lag` · raw: `var/reports/screen_lag.txt`
Artifact: "Screen Agreement"

## Verdict: NOT ESTABLISHED

| offset | found | of | rate | sessions | |
|---:|---:|---:|---:|---:|---|
| −2 | 1 | 38 | 2.63% | 4 | |
| −1 | 9 | 38 | 23.68% | 4 | |
| **+0** | **22** | **38** | **57.89%** | **4** | as shipped |
| +1 | 4 | 30 | 13.33% | 3 | not the same sessions as offset 0 |
| +2 | 1 | 19 | 5.26% | 2 | not the same sessions as offset 0 |

Offset 0 wins outright. **The watchlist dates are not shifted.** My four-name
hypothesis from `prior_close_check` does not survive contact with all 38 names,
which is exactly what the pre-registration was for.

Excluded: `watchlist_20260902.txt`, `watchlist_20260903.txt` (hand-synced).

## But the archived files show the mechanism anyway — as a UNION, not a shift

Reading the four automated watchlists directly:

```
09-08 (6):  BNC WYHG QCML HCWB SLE ISPC
09-09 (13): RML ODD SUNE IRD BIAF TNON FGL YMAT DPU LABT ACCL | BNC WYHG
09-10 (11): TNON PCLA TPET FTFT CULP GDHG | BIAF RML ODD SUNE IRD
09-11 (8):  TNON ACVA AENT LBGJ PCLA FTFT SXTC XRTX
```

The carried names sit at the **END** of each file, after that session's fresh
ones. This is not a lag — each file is that session's names **plus** the
previous session's leftovers.

`archive_watchlist` refuses to archive-and-clear when the session stopped before
`SESSION_END` or a position was still open. Both guards are correct in
themselves; the consequence is that the surviving list is added to rather than
replaced.

**Seven of the sixteen misses are carry-overs:**

- 09-09: BNC, WYHG (carried from 09-08) — 2 of that session's 4 misses
- 09-10: BIAF, RML, ODD, SUNE, IRD (carried from 09-09) — **5 of that session's
  7 misses**

For every one of these, **the simulation was right.** They were not on the screen
that day; they were left in the file. `screen_validate` counted them as
simulation failures.

## The second defect: our daily closes disagree with the market

Checked against TradingView for three names that are **not** carry-overs:

| symbol | listed | figure | ours | market | error | what ours looks like |
|---|---|---|---:|---:|---:|---|
| ACVA | **NYSE** | 09-10 close | 10.38 | 7.22 | +43.8% | the *next* day's close, to the cent |
| ISPC | NASDAQ | 09-08 pm close | 2.11 | 1.94 (day's HIGH) | +8.8% | above the whole day's range |
| TPET | **AMEX** | 09-09 close | 1.86 | 1.81 | +2.8% | plausible, and decisive |

- **ACVA**: TV has 09-10 at o 7.36 / h 7.39 / l 7.00 / **c 7.22** on 19.6M shares,
  and 09-11 at **c 10.41**. Our frame has 09-10 = 10.38 — within a cent of the
  next day's close. Our 09-08 (7.03) and 09-09 (7.37) match TV exactly, so this
  is not a uniform shift; one row is wrong. A 44% error in the denominator turns
  a genuine +44% gapper into 0.76%.
- **ISPC**: our premarket close of 2.11 on 09-08 is **above TV's whole-day high
  of 1.94**. Our window slice and our daily bar contradict each other — no
  external source is needed to detect this class.
- **TPET**: the quiet one and the most dangerous. At the market's 1.81 baseline,
  our own premarket close of 2.18 screens at **+20.4% and clears**. At our 1.86
  it reads 17.20% and is dropped. A 2.8% error in the denominator decides
  membership at a threshold.

Also worth noting: **ACVA is NYSE-listed and TPET is AMEX**. The archive is
XNAS.BASIC. Cross-listed names reach that tape only through Nasdaq-venue prints,
which is a different and thinner sample than the one TradingView consolidates.

## What this means

The 58% was measuring **two defects at once, neither of them the screen logic**:

1. the live watchlist is contaminated with the previous session's names, and
2. the daily closes feeding every `premarket_change` are sometimes wrong.

Neither is fixed by re-scaling a threshold, and (2) is the one that matters for
the backtest, because `prior_close` divides into every change the simulated
screen computes across all 550 sessions — not just these four.

## Next

A local, external-source-free check exists for defect (2): a premarket print
outside its own date's daily high/low is an internal contradiction between the
ohlcv-1m window slice and the ohlcv-1d bar for that symbol-date. Every input is
already on disk. That measures how widespread the problem is across the whole
archive rather than across three names checked by hand.

Three names is enough to establish that the daily closes can be wrong and by how
much. It is not a measurement of how often.
