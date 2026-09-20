# Three results: H0's leak split, the floor-delta test, MFE-after-exit

Run 2026-09-11 on bundle `20260911u`. Outputs `var/reports/pit_h0.txt` (see §0),
`pit_delta_mcl_ladder.txt`, `mfe_exit_mcl.txt`.

> **CORRECTION, same day, after the 2026-09-11 live session.** §3's claim *"this
> inverts `win_rate_and_r.md` §2"* is **overstated and withdrawn**. The live
> record — MCL n=17, win 47.1%, R 0.72 — matches the published stage-2 shape
> (48.7%, R 0.58), not the point-in-time shape (21.7%, R 1.67), and it carries no
> look-ahead at all. All 17 of those trades come from automated `tv_feed`
> sessions built on the same `FILTERS` the simulation imports, so a screen-spec
> mismatch does not explain it. The correct statement is that **the simulation
> disagrees with both the published figures and the live record about the shape
> of the deficit, and that disagreement is the finding.** See
> `claude/mcl_session_20260911_review.md` §3–§4.

## 0. Two defects in the reporting, both fixed in `20260911v`

**The H0 run overwrote the original `pit_h0` report.** `pit_strategy --strategy
h0` defaulted to `var/reports/pit_h0.txt`, exactly where `common.pit_h0` writes.
Nothing was actually lost — the new report's POINT-IN-TIME and EARLY arms
reproduce that file's AS SCREENED and KNOWABLE arms to the cent (4,568 trades /
−72,086 / −15.78 and 713 / −10,440 / −14.64), which is how the clobber was
noticed at all. That is luck, not design. Output is now
`var/reports/pit_strategy_{name}.txt`.

The accidental reproduction is worth keeping as evidence: it verifies the
`h0_engine` adapter against 4,568 real trades, not just fixtures.

**`pit_delta`'s sign check outranked its own magnitude check.** The ladder's
delta moved −0.09 → +0.07 — nine cents to seven cents, on a strategy losing
$10.49 a trade — and the report printed *"it reverses it, all four must be
re-run"*. Both deltas are economically zero and the flip is noise crossing an
axis. The pre-registration said "below MATERIAL **and** no sign change", and
the code now implements that conjunction. **The verdict in §2 below is the corrected
one.**

---

## 1. H0's own leak splits — and the universe leak is hugely negative

At $4.26, all three arms on one tape:

    STAGE-2 (leaky)              +1.24/trade over 4,814
    POINT-IN-TIME, no floor     +45.28/trade over 4,022
    POINT-IN-TIME, floored      (15.78)/trade over 4,568

      universe leak   (44.05)
      intraday leak    +61.06
      total            +17.02

This settles `pit_h0_result_20260911.md` §6, which had to be left flagged.
**H0's leak splits the same way the strategies' did, and far more violently.**

**The stage-2 arm reproduces the published +$4.72.** At $1.00 friction H0 on
stage-2 names makes **+$4.50/trade**. The bracket was real — for that universe
and that timing.

**But it does not survive the friction range.** STAGE-2 is the only arm in any
of these runs that **FLIPS**: +4.50 at $1.00, +1.24 at $4.26, **−3.42 at $8.92**.
Since `stop_fill_20260911.md` puts the central case at $8.92, the published
+$4.72 is negative at the friction we now believe.

**The +$45.28 middle arm is not a typo and not tradeable.** The point-in-time
universe is *defined by intraday movement* — a name qualifies because it ran
+20% at some point. Buying every one of them at 04:30, before the run, is close
to perfect foresight on a momentum universe, and H0 buys with no signal at all,
so it collects the whole selection benefit. That is why H0's intraday leak
(+61.06) dwarfs MCL's (+6.84) and MC5's (+11.99).

The correct reading of universe leak −44.05: **the point-in-time universe
contains far better names than stage 2 ever selected.** Essentially all of that
quality lives in movement that happens *after* the screen surfaces the name, so
none of it is capturable. Stage 2's RVOL/range filter was not merely leaky — it
was picking worse names than the live screen would have.

Two smaller notes:

- The floor bit on **66.2%** of H0's symbol-days, against 27.0% for MCL.
- The unfloored arm has **fewer** trades than the floored one (4,022 vs 4,568).
  That is correct, not a bug: H0 takes the first bar at or after its floor
  whether or not the price is in the $2–20 band, so a name out of band at 04:30
  and in band at 07:20 trades only in the floored arm.

---

## 2. The floor does not move a delta — corrected verdict

    UNFLOORED   base (3.65)   variant (3.74)   delta (0.09)   net (392)
    FLOORED     base (10.49)  variant (10.42)  delta   0.07   net   195

      the LEVEL moved  (6.84)
      the DELTA moved    0.16

**NOT MATERIAL**, against the $0.50 pre-registered before the run. A **43×
difference** between the level move and the delta move, which is exactly what a
subtraction between two exit rules on the same trades should do — the entry
timing is common to both sides and cancels.

Note the level move is **−6.84**, identical to the intraday leak
`pit_strategy` measured independently for MCL. Two modules, two code paths, the
same number.

**`HANDOVER_20260911.md` §4's inference does not hold.** Every published MCL/MC5
*delta* is **not** overstated by $6.84–$11.99; that figure is a property of
levels. `PROGRAM_INDEX` §7 item 3 should drop down the list accordingly.

What one mechanic cannot settle: the other three. A null here is weaker evidence
than a positive would have been, and the ladder was chosen partly *because* its
delta was already near zero. Cameron's partial and the dip entry had larger
deltas and could still move. But the theoretical reason the ladder did not move
applies to them identically, and the burden has shifted.

---

## 3. MFE-after-exit — and a disagreement with the live record

At $4.26, on the point-in-time floored universe:

    actual    n 2,682   win 21.7%   avg win $41.53   avg loss $24.87
              R 1.67    needed 3.62              per trade (10.49)

    ceiling   n 2,682   win 86.0%   avg win $135.80  avg loss $5.84
              R 23.24   needed 0.16              per trade +115.94

On this universe the reward side looks fine — the average win is 1.67× the
average loss — and only **21.7%** of trades win, where break-even at that R needs
37.5%. **That shape is not what live trading shows.** See the correction at the
top: MCL live is 47.1% / R 0.72, which is the published stage-2 shape. Three
universes, three answers, and the two with look-ahead removed disagree with each
other. Until §4's archive extension settles which universe the simulation is
actually describing, neither framing should be built on.

What survives the disagreement, because it is a property of the exits rather
than of the universe:

    capture ratio, exit vs post-entry high    p10 (2.26)   p50 (0.15)   p90 0.37
    left on the table after exit, $/share     p50 0.41     mean 1.18
                                              = $118/trade mean on 100 shares

**The median trade exits below its entry despite having traded above it.** The
8% trail gives back the entire move on the median trade, and even the best
decile captures 37% of what was available. 2,400 of 2,682 exits are
`trailing_stop`, leaving a median $0.50/share behind — and the live session
independently shows trailing stops filling (0.0563)/share worse than reference
while signal exits fill at 0.0000.

**Read the ceiling as a weak bound, not an invitation.** +$115.94/trade against
an actual −$10.49 is so far above that "the exit is worth attacking" is
technically true and not very informative. Perfect foresight on low-float
runners captures enormous moves; no rule gets near it.

Two validity checks inside the run:

- `window_close` exits leave **exactly $0.00** behind, mean and median, on all
  282 of them. Correct by construction — there are no bars after the session's
  last one — and a non-zero value there would have meant the excursion window
  was wrong.
- **Hold time: winners median 4 bars, losers 3.** The *opposite* of Garvey &
  Murphy's disposition asymmetry, as expected from a mechanical stop.

---

## 4. What this changes on the list

| Item | Change |
|---|---|
| `pit_h0_result` §6 | **Settled.** H0's leak splits like the strategies'; the universe part is negative and the intraday part carries it |
| `HANDOVER` §4 / `PROGRAM_INDEX` §7 item 3 | **Demoted.** The level-to-delta inference does not hold; deltas moved 0.16 against a level move of 6.84 |
| `win_rate_and_r.md` §2 | **Not inverted** — see the correction at the top. Flag that R = 0.58 is a stage-2 figure and that the simulation disagrees with it |
| `exit_candidates` | **Not dropped.** Hold the re-motivation until the universe question is settled |
| The published +$4.72 | Reproduced at $1.00 friction (+4.50), **negative at $8.92** (−3.42) |
| **NEW, above all of these** | **Extend the Databento archive past 2026-09-04** so the simulated screen can be checked against the automated live watchlists. Every point-in-time figure here depends on a universe whose agreement with the live screen is unmeasured |

## 5. Next

1. **Extend the archive and validate the simulated screen against the live
   watchlists.** This now gates everything else in this document.
2. Re-register the exit candidates once the universe question is settled.
3. The early-names measurement is still outstanding.
4. Cameron's partial and the dip entry through `pit_delta`, if the ladder's null
   is not considered sufficient for the family.
