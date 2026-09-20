# H0 on the point-in-time universe — the look-ahead is measured

`python -m common.pit_h0` — 2026-09-11, 145.5s, trail 8%, 546 sessions,
4,997 screened symbol-days, halves split 2025-08-06 (derived).
Output `var/reports/pit_h0.txt`. Universe built by `screen_sim`
(`claude/screen_sim_result_20260911.md`), whose fast-path gate read
**disagreements 0**.

> **CORRECTION, 2026-09-11 later the same day.** §6's line "the universe — not
> the rule — was the edge" does not survive `pit_strategy`, which split the leak
> into a universe part and an intraday part on one tape and found the **universe
> part NEGATIVE** for both MCL and MC5 — the stage-2 filter picked slightly
> *unfavourable* names — with the whole leak, and more, coming from entering
> before a name's `first_seen`. This module cannot make that split for H0: it
> has no unfloored arm. So for H0 the attribution is **untested, not confirmed**.
> Read §2 and §6 with that caveat, and see
> `claude/pit_strategy_result_20260911.md` §1 and §6.

## 1. The result

KNOWABLE AT 04:30 — entry time held fixed, only the universe changes:

    friction   trades       net      per   win%   drop-top-5    early     late
    $1.00         713    -8,115   -11.38  27.1%      -9,644    -8.49   -13.83
    $4.26         713   -10,440   -14.64  24.7%     -11,929   -11.75   -17.09
    $8.92         713   -13,762   -19.30  21.6%     -15,195   -16.41   -21.75

AS SCREENED — bought at `max(04:30, first_seen)`, the tradeable rule:

    $1.00        4,568   -57,194  -12.52  25.1%     -61,611   -12.92   -12.19
    $4.26        4,568   -72,086  -15.78  22.7%     -76,457   -16.18   -15.45
    $8.92        4,568   -93,373  -20.44  19.5%     -97,679   -20.84   -20.11

## 2. The verdict

    survivors (whole day known)   +4.72/trade
    rejects                       -9.81/trade
    KNOWABLE AT 04:30            -14.64/trade   n=713

**The +$4.72 was a look-ahead artefact.** H0 on a universe that can actually be
assembled at 04:30 does not land between the brackets — it lands **33% of a
bracket-width BELOW the rejects**. The report's own wording ("lands with the
rejects") understates it; the honest universe is worse than the set stage 2
threw away.

Two readings, and they are not exclusive:

- the look-ahead was worth more than the bracket width implied; and/or
- the point-in-time universe is not the same population as the stage-2 reject
  set — different tape (XNAS.BASIC vs EQUS.SUMMARY), different clauses
  (pre-market change/price/volume vs daily RVOL/range), and 73% of its names
  were in neither stage-2 bucket.

So do not over-read the "−33%" arithmetic. The sign and the magnitude are
unambiguous; the precise placement inside a bracket built on a different tape
is not.

*Which KIND of look-ahead produced the +$4.72 is not settled here* — see the
correction above. The AS SCREENED arm floors every entry at `first_seen`, so
this run cannot separate "the universe was chosen with hindsight" from "names
were bought before the screen showed them". `pit_strategy` found the second to
be the dominant one for both strategies.

## 3. The number that ends the argument

Per-trade net plus the friction charged, at all three levels:

    -11.38 + 1.00  =  -10.38
    -14.64 + 4.26  =  -10.38
    -19.30 + 8.92  =  -10.38

**H0 loses $10.38 a trade GROSS on the honest universe.** No friction estimate
rescues it, and the friction argument this project has had three times over is
irrelevant to this result. Buying the live screen's leaders at 04:30 and
trailing 8% is a losing rule before a single cost is charged. AS SCREENED is
−$11.52 gross.

## 4. The supporting checks all hold

- **Both halves negative**, in both arms. KNOWABLE early −11.75, late −17.09;
  AS SCREENED −16.18 / −15.45. No half carries the result and there is no sign
  flip to explain away.
- **drop-top-5 makes it WORSE** (−11,929 vs −10,440): the best five symbols were
  net contributors of about +$1,489, and removing them deepens the loss. The
  result is not a handful of names — it is the population.
- **Sign stable** across $1.00–$8.92 in both arms.
- **Win rate 24.7%** at $4.26, falling to 21.6% at $8.92.
- **Holdout NOT spent.** `holdout.json` was cut over the screened universe on
  2026-09-07 and remains clean for a screen built after it.

## 5. What the late qualifiers are worth: nothing

    AS SCREENED  -15.78/trade over 4,568
    KNOWABLE     -14.64/trade over   713
    difference    -1.14

The re-ranking through the session neither destroys nor creates value. Names
that surface at 08:00 perform like names that surface at 04:00. This kills a
hypothesis worth killing: there is no "the good names come early" effect to
harvest, and the 04:30 entry time was never load-bearing.

**But the strategies disagree with this.** `pit_strategy` found early names
better by +$1.30 (MCL) and +$5.86 (MC5). Either the strategies select on
something the screen's ordering already carries, or the early subset is small
and concentrated. Unresolved.

## 6. What this does and does not damage

**Damaged: every LEVEL claim measured on a stage-2 universe.** Every P/L figure
in this project was drawn from a universe chosen with the day's own daily bar,
and run over the whole session on names selected for that day. Those figures are
upper bounds. See the correction at the top for *which* of those two defects
turned out to carry the bias — it was the second, and it was never the target of
this audit.

**Not automatically damaged: DELTA claims.** The exit and entry studies — the
ladder vs its linear control, Cameron's partial and breakeven stop, the dip
entry, the hold cap — compare two rules **on the same trades**. A universe-level
shift that moves everything down does not by itself flip a difference between
two exits. Those verdicts stand until re-measured, but their *levels* do not.

**Not damaged: the live paper sessions.** Those ran on the real TradingView
screen and never touched stage 2. They are the only figures in this project with
no look-ahead in them at all — and this result explains why they have
persistently disagreed with the backtests.

**Recast, importantly: the control itself.** The standing finding was "every
entry rule we tested made H0 worse." That was H0 at +$4.72 — an artefact. H0 on
the honest universe is −$14.64. Whether MCL's rules beat *that* is now an open
question. **Answered since:** MCL does, on both denominators
(`pit_strategy_result_20260911.md` §2); MC5's two denominators disagree and it
gets no verdict.

## 7. Next measurement

~~Run MCL and MC5 on the point-in-time universe.~~ **Done** —
`claude/pit_strategy_result_20260911.md`.

Outstanding from this module: **add an unfloored arm to `pit_h0`** so H0's leak
splits into universe and intraday parts the way `pit_strategy`'s does. Until
that exists, every statement here about *which* look-ahead produced the +$4.72
is an assumption.
