# MC5 fails criterion 2 as replaced — and I predicted it would pass

`python -m common.breadth --run-id backtest:screened:*` · raw:
`var/reports/breadth_mc5.txt`, `_mcl.txt`, `_vw9.txt`, 2026-09-16.
Registration: `docs/research/REGISTERED_breadth.md`.

## The prediction, and it was wrong

One message before running this I wrote, in advance and on purpose so it could
not be re-read afterwards:

> MC5 should pass the replacement having failed the original — that's the
> *expected* consequence of removing a confound.

**It failed.** Recorded here rather than quietly dropped, because a prediction
registered so it cannot move is worth nothing if it is only mentioned when it
lands.

## The headline

| | trades | symbols | net | per trade | **P(total > 0)** | 95% interval on total |
|---|---:|---:|---:|---:|---:|---|
| **MC5** | 7,495 | 1,822 | 7,545 | +1.01 | **90.2%** | **−3,428 to +19,278** |
| MCL | 2,413 | 892 | (1,270) | (0.53) | 32.4% | (6,652) to +4,336 |
| VW9 5m | 1,527 | 724 | (7,633) | (5.00) | 2.4% | (14,873) to (93) |

Bar is **95%**. All three fail.

**MC5's 95% interval on total net straddles zero.** Its +$7,545 is not
distinguishable from nothing once you account for which symbols happened to be
in the sample — and MC5 is the only strategy in this project's history ever to
clear criterion 1 (drop-top-3 and drop-top-5). §11.1 treats it as the
benchmark ORB is measured against.

Criterion 1 and criterion 2 are asking different questions and MC5 answers them
differently: removing its best names does not sink it, but **redrawing the
names it was measured on does.**

## A number correction

The database run differs from the figures §11.1 quotes:

| | §11.1 | `backtest:screened:mc5:20260907T131940` |
|---|---:|---:|
| trades | 7,403 | **7,495** |
| symbols | 1,791 | **1,822** |
| per trade | +$1.11 | **+$1.01** |

Which is right is not settled here. The report prints its own counts so the
figure can never be read as the other one.

## The old criterion: retired twice, KEPT once

Observed share of profitable symbols, against the distribution it takes when
only skew and trade count are at work (nets permuted across symbol labels,
each symbol's trade count held fixed):

| | observed | shuffled mean | middle 90% | verdict |
|---|---:|---:|---|---|
| MC5 | **39.0%** | 36.5% | 35.3–37.8% | **OUTSIDE — kept** |
| MCL | 36.5% | 34.9% | 33.2–36.5% | inside — retired |
| VW9 | 29.1% | 27.9% | 26.4–29.4% | inside — retired |

The registration's escape clause fired on its first use: *"If the observed
share sits outside that distribution, the old criterion was measuring
something real... the old criterion is kept rather than dropped."*

**So both criteria stand.** One sample of three showed the old statistic
carries signal, and the conservative reading of what was registered is to keep
it.

### And the 50% bar was the wrong threshold, not the wrong statistic

MC5's 39.0% is **above** its own null of 36.5%. It has more profitable symbols
than skew and trade count predict. It failed the old criterion only because
that criterion demanded 50% — a number no right-skewed book reaches.

**This is a LEAD, not a criterion.** "Share profitable against its own
shuffled null" is a legitimate, unconfounded breadth test, and MC5 passes it.
Adding it to §11 now, after seeing that it flatters the incumbent, is exactly
what a registration exists to prevent. It is written down and left alone.

## §11.1's objection was right about VW9 and wrong about MC5

Share profitable by trades per symbol:

| trades/symbol | MC5 | MCL | VW9 |
|---|---:|---:|---:|
| 1 | 39.5% | 38.2% | **21.6%** |
| 2 | 40.6% | 33.7% | 32.4% |
| 3–5 | 38.8% | 35.1% | 38.6% |
| 6–10 | 39.8% | 38.5% | 46.7% |
| 11+ | 31.9% | 40.0% | **50.0%** |

**MC5 is flat. VW9 climbs from 21.6% to 50%.** §11.1 raised the trade-count
confound off VW9's Setup B at 1.7 trades a symbol, and the confound is exactly
where it said — and absent at MC5's 4.1. The objection was correct and
narrower than it read.

## What this changes

- **§11.1's "zero of four" base rate stands**, and is now better founded. MC5
  fails criterion 2 in its replaced form for a reason the original could not
  have detected.
- **Criteria 1, 3, 4 and 7 are untouched.** MC5 still clears them.
- **ORB inherits a harder bar than it looked.** 90.2% on 7,495 trades across
  1,822 symbols is what a near-miss looks like on a large sample; ORB will
  have fewer of both.
- `var/state/holdout.json` untouched and unspent.

## Published

Artifact page: **Does the Edge Survive a Different Draw**.
