# The point-in-time screen: universe shape

`python -m common.screen_sim` — 2026-09-11, 168.9s, archive `E:\Databento/XNAS.BASIC`,
cadence 60s, capture 0.552. Output `var/reports/screen_sim.txt`,
universe `var/state/screen_pairs_pit.json`.

## 0. The gate

    ticks compared   11
    disagreements    0

The fast accumulated path reproduces `screen_at` exactly at every sampled tick.
Per the module's own rule, this is what makes the rest of the file readable.
If a re-run ever prints a non-zero disagreement count, every number below is void.

## 1. The universe

    547 sessions, 04:00–09:30 ET
    symbol-days                 4,997
    per session   mean          9.1
                  median        8
                  p90           16
                  max           31
    sessions with none          1
    dropped, no prior close     3

For comparison, `screen.py`'s stage 2 — the universe every P/L figure in
this project was drawn from — produces **41.8 candidates per session** (median 41,
cap binding on 53 sessions). The live screen, run forward, surfaces roughly a
fifth of that.

## 2. When a name first clears the screen — THE ENTRY FLOOR

Cumulative share of symbol-days that have first appeared on the watchlist:

    04:00    15.5%      cum  15.5%
    04:30     5.9%      cum  21.5%
    05:00     3.8%      cum  25.3%
    05:30     3.2%      cum  28.4%
    06:00     4.4%      cum  32.8%
    06:30     5.0%      cum  37.8%
    07:00    11.0%      cum  48.8%
    07:30     9.0%      cum  57.9%
    08:00    18.5%      cum  76.4%
    08:30    12.2%      cum  88.6%
    09:00    11.2%      cum  99.7%
    09:30     0.3%      cum 100.0%

**Only 15.8% of symbol-days (789 of 4,997) are on the watchlist by 04:30**, which
is H0's registered entry time. Half the universe does not appear until after
07:30; the single largest half-hour is 08:00.

Per session, at 04:30:

    0 names   162 sessions   (29.7%)
    1 name    170
    2 names   112
    3 names    49
    4+ names  102            max 8

The median session has **one** name knowable at 04:30, and close to a third have
none at all. Every backtest in this project has assumed a 04:00 watchlist of
tens of names.

For the 789 knowable at 04:30: `first_rank` p50 1, `best_rank` p50 1,
`ticks_on` p10 4 / p50 155 / p90 325. The early names are the day's top-ranked
names and most of them stay on the list — the floor is about *when the list
fills*, not about marginal names flickering on and off.

## 3. Overlap with the traded universe

Restricted to the 546 dates both files cover (`screen_pairs.json` spans 861
dates, back to 2023; the simulation covers 2024-07 onward):

    old stage-2 universe on those dates   8,615 symbol-days
    point-in-time universe                4,997
    in both                               1,364   (15.8% of the old universe)
    in both AND knowable by 04:30            291   ( 3.4% of the old universe)
    in the PIT universe only               3,633   (72.7% of the PIT universe)

Nearly three-quarters of what the live screen surfaces is a name the stage-2
filter never passed.

**This 15.8% is not by itself a look-ahead measurement.** Three things differ at
once between the two universes:

1. **Tape** — stage 2 ran on EQUS.SUMMARY daily bars; the simulation ran on
   XNAS.BASIC minute bars at a measured 55.2% capture.
2. **Clauses** — stage 2 filters on today's daily RVOL and today's daily range;
   the live screen filters on pre-market change, price and pre-market volume.
   These are different columns, not the same column measured at different times.
3. **Time** — stage 2 decides a 03:59 question with 20:00 facts.

Only (3) is leakage. Separating it from (1) and (2) is what `pit_h0` is for.

## 4. What this does and does not answer

This is a **universe**, not a result. The measurement is H0 run on it against the
bracket `leak_control` established:

    stage-2 survivors   H0  +$4.72/trade
    stage-2 rejects     H0  −$9.81/trade

Land near +$4.72 and the screen was doing real work. Land near −$9.81 and the
+$4.72 was the leak, and with it every P/L figure this project has produced.

It also does not reproduce TradingView's *data*, only their *columns*, so it
cannot say whether this exact watchlist would have appeared on Ben's screen on
any given morning. That question is not worth the work; this one is.

## 5. What the shape already implies for `pit_h0`

With 789 knowable-at-04:30 symbol-days and H0 firing at most once per symbol-day,
the like-for-like arm will be a few hundred trades at best, concentrated in a
minority of sessions. `pit_h0` already refuses a verdict on an empty knowable
bucket and reports drop-top-5-symbols and both halves; a thin-but-non-empty
bucket needs the same scepticism. A result read off 291 overlapping pairs is a
result about those 291 pairs.

The second arm (AS SCREENED, entry at `max(04:30, first_seen)`) uses all 4,997
and is the tradeable number, but its entry time moved, so it is **not**
comparable to the +$4.72 — two changes at once.
