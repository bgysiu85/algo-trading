# Zero conflicts — and the zero is the finding — 2026-09-12

`python -m common.tape_conflict` · raw: `var/reports/tape_conflict.txt`

## Result

```
3,406,462 symbol-day(s) carried by BOTH files, over 552 session(s)
test: daily_low <= every premarket print <= daily_high
tolerance: 0.5% of the daily range, min 0.01

0 symbol-day(s) in conflict   (0.00%)
```

Not one premarket print fell outside its own day's daily range, across the
entire archive.

## What a zero rules out, and what it leaves

The report's own caveat is the point: **this does not clear the archive.** It
tests one class — the two files contradicting each other — and finds that class
empty. Our minute slices and our daily bars **agree with each other**, and the
hand checks show both disagreeing with TradingView.

That rules out a corrupt file, an off-by-one row, and a bad chunk merge. It
leaves one source being wrong the same way everywhere.

## It also retires a "defect" I reported

I told Ben that ISPC's premarket close of 2.11 on 09-08, against TradingView's
whole-day high of 1.94, was our two files contradicting each other. **It is
not.** TradingView's daily bar is the REGULAR session; 2.11 was a premarket
print that faded before the open (TV has ISPC opening at 1.905). A premarket
spike above the regular-session high is ordinary, and `tape_conflict` correctly
passes it because our own daily bar — which includes premarket — contains it.

I was comparing a premarket print to a regular-hours bar and calling the
difference a fault. The zero caught my error, which is the point of running it.

## The remaining candidate, stated before the test

**Databento's `ohlcv-1d` aggregates the whole feed**, so its close is the last
print of the extended day (20:00 ET). **TradingView's `premarket_change` divides
by the official 16:00 regular-session close.** Two closes that look comparable
and are not — the project's signature defect.

A name that runs after hours then carries an inflated `prior_close` in our
frame, which **deflates** its computed premarket change. That is
one-directional, and it is exactly the shape `screen_validate` found: 16 missed
against 2 sim-only. It fits all three hand checks:

| name | our close | TV regular close | consistent with an after-hours run? |
|---|---:|---:|---|
| ACVA 09-10 | 10.38 | 7.22 | yes — ran to ~10.4 after hours, gapped open at 10.455 next day |
| ISPC 09-04 | ~1.99 | 1.54 | yes |
| TPET 09-09 | 1.86 | 1.81 | yes — small drift |

It also explains why ACVA's 09-08 and 09-09 closes matched TV **exactly**: on
quiet after-hours days the two closes coincide. Only the day it ran diverges.

## The row that decides it

ACVA traded `o 7.36 h 7.39 l 7.00 c 7.22` on the market on 2026-09-10.

- If our daily bar for that date shows a **high near 10.46** — a level the
  regular session never reached — our bar covers hours TradingView's does not,
  and the defect is named.
- If it shows **h 7.39**, the bar is simply wrong and this is a different
  problem.

Both outcomes were written down before the run. `prior_close_check` now prints
each daily bar's high and low (bundle `20260912m`); one rerun answers it.

    python -m common.prior_close_check

## If confirmed, the fix is a data pull, not a threshold

`prior_closes()` would need the **regular-session** close, which the archive
does not currently carry — the window slices are 04:00–09:30 only, and the
daily bars are whole-feed. The cheapest repair is a narrow Databento pull of
`ohlcv-1m` for roughly 15:55–16:00 ET across the 552 sessions and taking the
last print at or before 16:00.

That is a change to the simulated screen's inputs and every screen figure —
including the 58% — has to be re-stated afterwards, not adjusted.

**Do not cancel Databento until this is done.**
