# MCL and MC5 re-read against the repaired universe — 2026-09-14

`python -m common.pit_strategy --strategy mcl` (292.6s) / `--strategy mc5`
(229.2s) · raw: `var/reports/pit_strategy_mcl.txt`, `pit_strategy_mc5.txt` ·
bundle `20260914b`

551 sessions, 6,170 point-in-time symbol-days (99.4% repaired prior close),
control from `pit_h0_refresh_20260914.md`. Supersedes
`pit_strategy_result_20260911.md`, which was measured on 4,997.

## 1. Both verdicts stand

    H0 as screened      (15.40)/trade   (13.99)/symbol-day   (0.91 trades/day)
    MCL point-in-time   (10.52)/trade    (6.74)/symbol-day   (0.64)  +4.88 / +7.25
    MC5 point-in-time   (13.50)/trade   (15.06)/symbol-day   (1.12)  +1.90 / (1.06)

**MCL beats its control on both denominators and still loses money.** Margins
narrowed from +5.29/+8.80 to +4.88/+7.25 — the same answer, slightly quieter.

**MC5 still has no verdict.** Per trade it beats the control, per opportunity it
loses to it, and which figure flatters it is decided by how often it chooses to
trade. Unchanged from 09-11.

Every arm of both strategies is negative at every friction level. Sign STABLE
across $1.00–$8.92 in all six. Drop-top-5 deepens the loss in all six.

## 2. The finding that did move: MCL's universe leak is gone

At $4.26, same tape, same slices, same dates:

| | 4,997-day | 6,170-day repaired |
|---|---:|---:|
| **MCL** universe leak | (2.20) | **(0.13)** |
| **MCL** intraday leak | 6.84 | 4.79 |
| **MCL** total | 4.63 | 4.66 |
| **MC5** universe leak | (4.11) | **(2.24)** |
| **MC5** intraday leak | 11.99 | 9.37 |
| **MC5** total | 7.88 | 7.14 |

`pit_strategy_result_20260911.md` §1 said the universe leak was NEGATIVE for
both — *"stage 2 was picking worse names than the live screen would have."* For
MCL that is now **thirteen cents**, which is nothing. The claim was
substantially an artefact of the defective prior close: the names the broken
divisor kept out of the point-in-time universe were the ones that made it look
better than stage 2. With them back, the two universes are near enough equal for
MCL. MC5's halved but survives at (2.24).

**The intraday leak still carries everything** — 4.79 for MCL, 9.37 for MC5.
Buying a name before the screen would have shown it remains the whole of the
look-ahead, and it is purely a backtest artefact the live trader has never had.
Floor footprint: MCL **1,524 of 6,170 (24.7%)**, MC5 **4,207 of 6,170 (68.2%)**.

## 3. §5 of the 09-11 doc: settled for MCL, still open for MC5

The early-names question, against H0's own gap of **(1.35)**:

| | early vs all | H0's gap | differs? |
|---|---:|---:|---|
| MCL | 1.49 | 1.35 | **no** |
| MC5 | 3.91 | 1.35 | yes |

**MCL's early-name advantage is the screen's, not MCL's.** 1.49 against H0's
1.35 is the same number: buying the early names outright already collects it, so
MCL is not selecting better among them. That closes one of the two readings
09-11 could not separate.

**MC5's still differs, and is still concentrated.** 3.91 against 1.35, and
drop-top-5 moves its early arm from (24,642) to (31,527) — five symbols carrying
about 6,885 of it, against 1,693 for MCL. The 09-11 caveat holds: MC5's early
edge may be five names. It needs its own measurement, now over 1,394 early
symbol-days rather than 789.

## 4. The arm that should not have moved did not

MCL's STAGE-2 arm reads **(5.86)/trade over 2,656** — identical to 09-11 to the
cent; MC5's (6.36) over 5,857 against (6.37) over 5,854. Stage 2 is chosen from
the session's own daily bar and never touches the prior close, so a change there
would have meant the repair had leaked somewhere it had no business being. It is
the run's own control and it held.

## 5. One defect found

**A stale H0 figure was typed into the report's prose.** The line
`H0 found the late qualifiers worth $(1.14)` was a literal from the 5,021-day
run, living in a rendered string rather than in the `H0_*` block — outside
everything the staleness guard can see. It survived the refresh that moved the
figure to (1.35), so both reports printed the new control beside the old one's
gap and invited exactly the comparison the guard exists to prevent.

Derived from the four constants now (`h0_late_qualifiers()`). The test checks
the **rendered text**, not the source, because that is where a stale literal is
indistinguishable from a derived value — and it asserts the live figures are
still present, so it cannot pass by the report having stopped quoting H0.

The 2026-09-11 and 09-12 reports contain the (1.14) line and are wrong on that
one number. Nothing else in them depends on it.

2,118 tests passing.

## 6. What this changes on the list

| Item | Change |
|---|---|
| `pit_strategy_result_20260911.md` §1, "the universe leak is negative for both" | **Withdrawn for MCL** (0.13). Halved but standing for MC5 (2.24) |
| `pit_strategy_result_20260911.md` §5, early names | **Settled for MCL** — indistinguishable from H0's own gap. Still open for MC5 |
| §6, "the timing, not the universe, was the edge" | **Stands, and strengthened.** With the universe leak near zero for MCL, the intraday leak is now essentially the entire look-ahead |
| MCL beats its control | **Stands**, +4.88/trade and +7.25/symbol-day |
| MC5 | **Still no verdict** |
| Every figure in the 09-11/09-12 reports quoting H0's late qualifiers as (1.14) | **Wrong number**, now (1.35) |

## 7. Next

1. **Capture on the 9 remaining missed names** (`capture_sensitivity()`), the
   last unexplored piece of the screen's 76%.
2. **MC5's early-names arm on its own**, over 1,394 symbol-days, with the
   concentration question asked directly.
3. Re-state the **58% figure from `screen_lag`** and the other screen figures
   against the repaired universe.
4. From earlier: the `mins_since_open` forced-flatten confound; the `c_vol`-alone
   population (15,956 bars, unpriced); the name-level separator, which must beat
   top-5-by-volatility rather than the universe.
