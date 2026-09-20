# The simulated screen against the live one — 58%, and the verdict is negative

`python -m common.screen_validate`, 2026-09-12, after extending the Databento
archive through 2026-09-11. Output `var/reports/screen_validate.txt`.
This is `PROGRAM_INDEX` §7 item 1, the one that gated everything else.

## 1. The result

    date          live   sim  found  missed  sim-only   the misses
    2026-09-08       6     4      4       2         0   ISPC, SLE
    2026-09-09      13    10      9       4         1   BNC, RML, SUNE, WYHG
    2026-09-10      11     4      4       7         0   BIAF, CULP, IRD, ODD, RML, SUNE, TPET
    2026-09-11       8     6      5       3         1   ACVA, LBGJ, XRTX

    22 of 38 live names surfaced = 58%
    95% Wilson interval  42% to 72%

Against the bands registered in the module before it could run, read from the
**lower** bound:

> **A DIFFERENT UNIVERSE.** The simulation does not reproduce the live screen,
> so its figures are about the universe it built and may not be quoted as live
> expectations. Every conclusion drawn on the point-in-time universe needs this
> caveat — **including that MCL beats its control.**

## 2. What it damages, and what it does not

**Damaged: every level and comparison from 2026-09-11 as a statement about live
trading.** `pit_h0`, `pit_strategy`, `pit_delta`, `mfe_exit` — all measured on a
universe that overlaps the real one by roughly 58%.

**Not damaged: their internal comparisons.** The three arms of `pit_strategy`
share one universe, so the leak split (universe negative, intraday carrying it)
is a statement about that universe and holds within it. Same for the floor-delta
result. What cannot be carried across is any claim of the form *"MCL is worth
−$10.49 a trade"* or *"MCL beats H0"* as a description of live trading.

**Explained: the disagreement with the live record.** MCL live is 47.1% win /
R 0.72; the simulation says 21.7% / R 1.67
(`mcl_session_20260911_review.md` §3). A 58% universe overlap is a mechanism for
exactly that, and it removes the need to treat the live figures as an anomaly.

## 3. The misses are one-directional, and that is the clue

**16 missed, 2 sim-only.** The simulated universe is close to a *subset* of the
live one. A ranking difference would produce roughly symmetric disagreement;
this does not. The simulation is **under-producing**, not mis-ordering.

Two candidate causes, and they are distinguishable:

1. **Capture is worse for these names than the 55.2% average.** The volume
   threshold is scaled to `volume_min * capture` = 55,200. That 0.552 was
   measured across the whole tape. Low-float small caps trade a larger share
   off-exchange, so Nasdaq's TRF-inclusive feed may carry far less of *their*
   volume — in which case the scaled threshold is still too high for exactly the
   names this screen is for.
2. **`premarket_change` computed off a partial tape's last print.** A thin tape
   can miss the print that takes a name over +20%.

**The next measurement is (1), and it is cheap:** compute the capture ratio for
the 16 missed names specifically, against the EQUS.SUMMARY daily bar, and
compare it to the 0.552 population figure. If it is materially lower, the
threshold is mis-scaled for this universe and `screen_sim` can be re-run with a
capture measured on the names it is actually screening rather than on the
market.

`capture_sensitivity()` already re-runs the screen at p10/p50/p90 — that machinery
exists and has never been pointed at this question.

## 4. Read the sample honestly

Four sessions, 38 names, an interval **30 points wide**. The verdict was taken
from the lower bound precisely because a point estimate on this sample would be
read as precise. More sessions will move it, and the direction is not knowable
in advance.

The two earliest watchlists were **excluded, correctly**: they were hand-synced
under `RVOL(1D) >= 5x, float < 20m`, clauses the shipped `FILTERS` do not have.
Scoring against them measures the gap between two screens. An earlier by-hand
pass that included them produced 46% and meant nothing.

## 5. Also from this run

`screen_sim` now covers **551 sessions and 5,021 symbol-days**, up from 547 and
4,997. **Every `H0_PIT_*` constant in `pit_strategy` is therefore stale** — they
pin 4,997 — and the module's own staleness guard will say so on the next run
rather than comparing two universes. `pit_h0` must be re-run before any
`pit_strategy` result is quoted again.

One session is still skipped for having no prior regular close; it is named in
the report.

## 6. Next

1. **Measure capture on the missed names.** It decides whether the 58% is a
   fixable scaling error or a real limit of this tape.
2. **Re-run `pit_h0`** to refresh the control constants against the 5,021-day
   universe, then `pit_strategy` for MCL and MC5.
3. Only then re-read the 2026-09-11 conclusions, with this caveat attached to
   every one of them.
