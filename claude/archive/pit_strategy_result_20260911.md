# MCL and MC5 on the point-in-time universe

`python -m common.pit_strategy --strategy mcl` (292.0s) and `--strategy mc5`,
2026-09-11, on bundle `20260911s`. 546 sessions, one session of warm-up, 100
shares. Outputs `var/reports/pit_mcl.txt`, `var/reports/pit_mc5.txt`.

This supersedes the first run, whose report carried three defects (§7).

## 1. The headline: the leak was not where we thought it was

Splitting the leak in two — same tape, same slices, same dates, both arms
unfloored for the universe comparison — gives, at $4.26:

    MCL   STAGE-2                  -5.86/trade over 2,656
          POINT-IN-TIME, no floor  -3.65/trade over 4,378
          POINT-IN-TIME, floored  -10.49/trade over 2,682

            universe leak  -2.20     intraday leak  +6.84     total +4.63

    MC5   STAGE-2                  -6.37/trade over 5,854
          POINT-IN-TIME, no floor  -2.25/trade over 9,137
          POINT-IN-TIME, floored  -14.25/trade over 5,451

            universe leak  -4.11     intraday leak +11.99     total +7.88

**The universe leak is NEGATIVE for both strategies.** Choosing names with the
session's own daily bar in hand made results *worse*, not better. Stage 2's RVOL
and day-range filter — the thing this whole investigation was aimed at —
selected slightly unfavourable names relative to what the live pre-market screen
would have surfaced.

**The entire leak, and more, is the intraday one**: buying a name before the
screen would have shown it. That was never the target of the audit. It is bigger
than the universe leak for both strategies, and for MC5 it is nearly three times
the size of the total.

This is a different defect with a different fix, and it matters more:

- It is purely a **backtest artefact**. The published runs turned MCL loose over
  the whole 04:00–09:30 window on names chosen for the day, so the engine could
  enter at 04:05 on a name that would not appear on the watchlist until 07:20.
- The **live trader has never had it** — the feed surfaces a name when it
  surfaces it. So this is a concrete, quantified part of the execution gap:
  the backtests were flattered by $6.84 (MCL) to $11.99 (MC5) per trade of
  timing that live trading cannot reproduce.
- The floor removes **39% of MCL's trades and 40% of MC5's**
  (4,378 → 2,682 and 9,137 → 5,451).

Its footprint, independently measured:

    symbol-days where the unfloored run's first entry preceded first_seen
      MCL   1,351 of 4,997   (27.0%)
      MC5   3,436 of 4,997   (68.8%)

## 2. MCL beats its control. MC5 has no verdict.

    H0 as screened      -15.78/trade   -14.43/symbol-day   (0.91 trades/day)
    MCL point-in-time   -10.49/trade    -5.63/symbol-day   (0.54)   +5.29 / +8.80
    MC5 point-in-time   -14.25/trade   -15.54/symbol-day   (1.09)   +1.53 / -1.12

MCL beats H0 on **both** denominators: its trades are individually better than
H0's *and* it declines most opportunities. Both point the same way, which is
about as robust as this gets without a new measurement.

MC5's two denominators disagree. Per trade it beats the control; per opportunity
it loses to it. Which figure flatters MC5 is decided by how often it chooses to
trade, not by how well it trades, so neither may be quoted alone. **No verdict.**

One thing the per-symbol-day figure does not establish: "never trade" scores
0.00/symbol-day and beats everything here. Beating H0 per opportunity is
necessary, not sufficient.

## 3. It is still a loss

MCL point-in-time is **−$10.49/trade**, and −$6.23 gross of friction. Every arm
of both strategies is negative at every friction level. Selection is doing
something real and it is not doing nearly enough.

## 4. The supporting checks hold

- **Both halves negative** in every arm. MCL point-in-time −11.37 early,
  −9.75 late.
- **drop-top-5 makes every arm worse** — −30,876 against −28,131 for MCL
  point-in-time. No arm is carried by a handful of names.
- **Sign stable** across $1.00–$8.92 in all six arms.
- **Tape attrition 99% vs 100%** between the compared arms, well inside the
  caveat threshold, so the subtraction is not comparing two subsamples.
- **Holdout not spent.**

## 5. The early-names question is open

    MCL   early -9.19 vs all -10.49   (+1.30)
    MC5   early -8.39 vs all -14.25   (+5.86)

H0 found the late qualifiers worth −$1.14, i.e. nothing. These differ, MC5's
substantially. Two readings this run cannot separate: the strategies really do
select better among names the screen surfaces early, or the early subset (789
symbol-days, 559 of which MCL trades) is small and concentrated. MC5's early arm
shows heavy concentration — drop-top-5 moves it from −12,293 to −19,607, so five
symbols carry about +7,300. Needs its own measurement.

## 6. What this changes elsewhere

`claude/pit_h0_result_20260911.md` §2 concluded "the universe — not the rule —
was the edge." **For the strategies that is now wrong**, and the H0 case is
untested rather than confirmed: `pit_h0` has no unfloored arm, so it never split
its own leak the way this module does. Adding one is cheap and should be done
before the H0 framing is repeated anywhere.

The correct statement for MCL and MC5 is: *the timing, not the universe, was the
edge* — and it was an edge only in the backtest.

## 7. The three defects in the first run's report

Recorded because two are shapes this project keeps hitting, and because the
first run's MC5 conclusion was wrong.

1. **Two values that looked comparable and were not.** The control comparison
   was per trade only. H0 takes at most one trade per symbol-day; a strategy
   takes as many as it likes, so selectivity alone separates the two
   denominators. MC5 read +1.53/trade and −1.11/symbol-day — a sign flip living
   entirely in the denominator — and the report printed the flattering one and
   declared a win. Both are now printed, with the trade rate beside them, and a
   disagreement refuses the verdict.
2. **A wrong quantity under the right label.** The EARLY arm's "had bars on this
   tape" was the count of symbol-days that produced *trades*. It printed 71%
   coverage inside a superset showing 100% — impossible, and unflagged, because
   a hit rate and a coverage rate are both plausible percentages.
3. **The leak was two leaks.** Reported as one sum and called "the look-ahead
   alone". Fixing this is what produced §1, which is the most important finding
   in the run.

## 8. Next

1. Add an unfloored arm to `pit_h0`, so H0's leak splits the same way and §6 can
   be settled rather than flagged.
2. The early-names effect needs its own measurement.
3. MCL is the first candidate in this project worth spending the holdout on —
   but not yet. It loses money in sample; the holdout would only confirm that
   more expensively.
