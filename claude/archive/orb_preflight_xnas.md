# ORB pre-flight on XNAS.BASIC — the tape was the blocker, 2026-09-08

The 2026-09-07 pre-flight could not evaluate ORB. Two thirds of symbol-days had
no usable opening range, and `capture_ratio.txt` said why: EQUS.MINI publishes a
**median 4.8% of the consolidated tape at 16:00 and 1.5% by 09:30**, so an
opening range computed from it was built from roughly one print per fifteen
minutes. That was a fact about the feed, not about the market.

**XNAS.BASIC clears it.** The range is now measurable on 57% of symbol-days
against 27% before, and the pre-flight's five measurements can be read.

Nothing here is a P/L or an edge. The section 11 go/no-go is unchanged and
unmet.

Reports: `var/reports/orb_preflight_xnas.txt`, `orb_preflight_xnas.csv`.
Cache: `bar_cache_xnas/3d_to_2000`, 27,777 symbol-days.

---

## 1. What changed, and what did not

| 15-minute range | EQUS.MINI | XNAS.BASIC |
|---|---:|---:|
| symbol-days | 25,769 | 27,777 |
| usable range | 7,049 (27.4%) | **15,886 (57.2%)** |
| no RTH bars at all | 335 | **19** |
| few opening bars, ≥100 RTH bars | 4,531 | 5,991 |
| few opening bars, <100 RTH bars | 12,702 (49.3%) | **3,919 (14.1%)** |
| opening bars among excluded, p50 | 1 of 15 | **4 of 15** |
| ≥3 of 15 bars | 56.5% | **89.8%** |
| ≥10 of 15 bars | 31.8% | **64.3%** |
| width % p50 | 12.16 | 10.28 |
| width % p90 | 27.84 | 24.80 |

**These are not comparable as market facts.** Every count moved because the tape
changed; nothing about the universe or the market did. The "thin all day" bucket
falling from 12,702 to 3,919 is the TRF prints arriving, not names becoming
liquid. Ranges came in narrower for the same reason — more prints inside the
same fifteen minutes.

The 19 symbol-days with no RTH bars at all, down from 335, are the only row that
is a fact about the archive rather than the feed.

## 2. What the pre-flight now sets

**MIN_RANGE_BARS is a real choice, not a data constraint.** 89.8% of
symbol-days have ≥3 of 15 opening bars and 64.3% have ≥10. The curve is steep
across that span, so the threshold decides how much of the universe ORB gives
up. It is still a guess at 10, and it should be set from the width and trigger
numbers rather than from a default.

**ENTRY_BUFFER_PCT.** 729 of 9,684 upside triggers (7.5%) closed within 0.1% of
the level.

**The stop mode, which is where VW9 died.** VW9's structure stop produced a
median R of 9.4% of price and p90 of 20.7% — unusable, and discovered only after
the study. Asked in advance here:

| mode | n | p50 | p90 |
|---|---:|---:|---:|
| **structure** | 9,327 | **2.98%** | **8.62%** |
| opposite | 9,628 | 9.26% | 17.72% |
| rangefrac | 9,644 | 3.82% | 7.34% |

`structure` and `rangefrac` are usable. **`opposite` sits exactly where VW9's
stop sat** and can be dropped before it is ever run — which is the entire point
of running 10.4 before writing entry logic.

**Time to resolution:** 5,787 reached 2R at a median of 6 trigger bars, 6,001 hit
the structure stop at a median of 4. Those two populations are not exclusive and
not complete, so they do not divide into an expectancy. What they do say is that
losers resolve faster than winners, which is what a TIME_STOP_BARS setting has to
be chosen against.

## 3. The leak cut passes

Stage 2 selected this universe using the session's own daily bar — **including the
day's range** — and ORB trades a break that contributes to that range. That is a
structurally larger exposure than any pre-market strategy has, and it needed
answering before any exit rule existed to be tuned.

| | usable ranges | upside triggers | rate |
|---|---:|---:|---:|
| survivors | 14,018 | 8,709 | 62.1% |
| rejected | 1,868 | 975 | 52.2% |

The rejected-day trigger rate is **84% of the survivors'**. Stage 2 barely
changes how often a break happens, so it is not selecting on the event ORB
trades. This is the outcome you want and it was not guaranteed.

## 4. Still not answerable from this cache

**RVOL.** `relative_volume_10d_calc >= 5.0` needs ten sessions of intraday volume
by time of day; each cache file holds three. Reported as NOT COMPUTABLE rather
than approximated — a screen simulated on three of its four rules is not the
screen, and a two-session stand-in would make the gap invisible in every number
downstream. Closing it means loading `bar_minute` for the full history and
computing the baseline there.

So section 10.2's numbers — 53.8% inside the $2–20 band, 19.7% moving more than
5% from the open, 11.5% both — are a partial screen, and the 11.5% is an upper
bound on what the real screen would select.

## 5. Two defects found while reading this report

Both are the same shape: correct numbers under prose that asserted something the
numbers contradicted.

**The tape caveat was hardcoded.** Section 10.1b opened with a paragraph stating
the bars were EQUS.MINI and that a low bar count was therefore a feed artifact —
printed verbatim over the XNAS.BASIC numbers, telling the reader to dismiss
exactly the counts the tape change had just fixed. Two tests passed through it
because they *asserted* that paragraph appears with no tape argument at all. A
suite that pins the defect is worse than no suite.

The dataset is now read off the cache's own `SOURCE.txt`, with three outcomes:
the capture caveat for EQUS.MINI, a NOT COMPARABLE warning for a fuller tape,
and TAPE UNKNOWN when there is no marker. The report header names the cache and
the tape, so a report can no longer describe bars it did not read.

**The heading argued with its own body.** "WHY THE RANGE IS UNUSABLE" sat
directly above a section explaining that the range is measurable. A heading is a
conclusion and now follows the measured usable fraction like every other verdict
here.

## 6. The cache build

27,777 of 27,877 symbol-days written, 99.6%. 23 had no source chunk (one date's
file missing of 545), 74 were short of warm-up, 3 had no bars in the window.

One known gap, recorded rather than papered over: the daily fetch's end bound is
midnight UTC, which is **19:00 ET in winter**, so winter files stop an hour short
of the 20:00 session end. MCL and this pre-flight never reach that hour; VW9's
last post-market hour on those dates is not in the archive. A re-pull with a
wider end bound is free if that hour matters.

## 7. Next

1. Set MIN_RANGE_BARS from the width and trigger distributions rather than
   leaving it at 10.
2. Drop `opposite` as a stop mode.
3. Load `bar_minute` for the full history and compute the RVOL baseline, which
   is the only way section 10.2 stops being partial.
4. Then, and only then, write ORB entry logic against section 11.
