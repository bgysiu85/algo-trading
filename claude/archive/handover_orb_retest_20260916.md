# Handover to the build chat — 2026-09-16

**From:** the research chat. No program logic was touched; nothing under
`D:\Trading` was modified.

**Supersedes** `handover_intraday_candidates_20260915.md` rev. 2. Its section 0
(the Cameron corpus) and its item 1 (ORB pre-flight) have both been **run** —
thank you. What follows is built on those results, not on the state they
replaced.

**New docs:** `claude/orb_retest_depth_20260916.md` (the detail and the kill
conditions), plus §10 and §11 of `claude/source_videos_20260907.md` (two
channels assessed and rejected; §8.5's stop table updated).

---

## A. ORB — three additions to a grid that is already specified

The pre-flight settled five of twenty parameters, eliminated `STOP_MODE =
opposite` on measurement, and passed the leak cut at 84%. Three things to add
before the grid runs.

**A1. Add `RETEST_MODE = zone_impulse` as a fourth cell.**

A Reddit/chart source arrived at `RETEST_MODE = zone` independently of V4 —
mild corroboration, nothing more. But its **anchor is different and it is a
different object**:

| | 0% anchor | 100% anchor |
|---|---|---|
| `zone` (V4, already specified) | `orb_high` | `orb_low` |
| **`zone_impulse` (new)** | a **post-breakout swing high** | the breakout extreme |

The range-anchored zone is fixed at 09:45 and cannot move, so a violent trigger
leaves the retest zone far below entry. The impulse-anchored zone travels with
the move, so its depth is proportional to the thrust. At a **9.46% median
15-minute range width** those two are nowhere near each other. One more column
in a pass already loading the bars.

**A2. The fork's price is already measured — carry it.**

From your own §10.6 table, arithmetic ours:

| `ORB_MINUTES` | usable | up-triggers | zone retest | **zone as % of triggers** |
|---:|---:|---:|---:|---:|
| 5 | 19,260 | 12,998 | 5,037 | **38.8%** |
| **15** | 15,886 | 9,684 | 2,618 | **27.0%** |
| 30 | 14,089 | 7,971 | 1,715 | **21.5%** |

**Requiring a 38–62% retest at 15 minutes discards 73% of triggers.** The source
says *"sometimes it never comes"*; it is the majority case. Any deep-retest cell
is spending three quarters of its triggers to buy a better entry, and its
per-trade figure has to clear that. Standing rule from §5.3 unchanged: a retest
rule can only remove trades, so compare per-trade P/L **and drop-top-N on the
delta**, never totals.

**A3. The coupling is four-way, not three.**

Your finding — *"picking a length first and a stop second would fix the wrong
confound"* — extends. §10.5 says stops resolve at a median of 4 bars against 2R
targets at 6, so `EXIT_MODE = r_2` starts behind. **A deeper entry moves entry
toward the stop and away from the target, which changes that race directly.**
The retest-depth fork and the stop-beats-target problem are one problem seen
twice. Run `ORB_MINUTES × STOP_MODE × RETEST_MODE × EXIT_MODE` jointly.

**A4. The blocker is still RVOL, and it is worth spending on.**

Only 8–13% of usable symbol-days pass three of four screen rules, and the
fourth — `relative_volume_10d_calc` — is NOT COMPUTABLE. That matters more here
than anywhere: `largecap_evidence_20260911.md` finds **100% of the stocks-ORB
paper's claimed edge came from ranking on first-5-minute relative volume**, not
from the trigger. **Check `bar_minute`'s 21.0M XNAS rows for ten-session
coverage before spending on a Databento pull** — as your own doc says.

**A5. Settle criterion 2 before ORB produces a number**, and re-score MC5 under
whatever replaces it, in the same pass. §11.1 is explicit that relaxing it
afterwards is the sin the section exists to prevent.

---

## B. Rank allocation — promote it, because it just got external validation

`cameron_names_RESULT_20260916.md` was run to answer "do a professional's picks
beat our ranking?" The answer was **no — and that is the good outcome.**

- Our within-session rank discriminates his names at **AUC 0.688** (n=451)
  against random 0.500, with **0 of 2,000 draws** reaching it, and it holds in
  both halves (0.676 early / 0.704 late).
- Our screen ranked his names **best-rank 1 in 265 of 451 covered pairs (59%)**.

**So our ranking already carries real information about which names a
professional would trade** — measured against an external label, not against
ourselves. That is the strongest support the rank-allocation item has ever had,
and it was previously the item's weakest point (`universe_lift` measures run
*starts*, not P&L, and its own doc warns *"volatile names keep being volatile…
that is not alpha"*).

Meanwhile **29% of live buy attempts are still rejected by the concurrency cap**
(46 of 159), slots are the binding constraint, and we still fill them by
**arrival order rather than by rank**. No backtest models this.

Two registration requirements, unchanged:

- **`dollar_vol` ranks INVERTED (0.29×)** — register it as a **negative
  control**. It is the sort most people would guess at.
- **Report trade count and overlap, not only P/L.** A rank rule that reproduces
  arrival order prints 0.00 and renders as NOT MATERIAL.

This also shares a lever with A4: if `bar_minute` yields RVOL, it serves both
ORB's fourth screen rule and the ranking criterion. Check once, use twice.

---

## C. Still open from the last handover

**C1. Run participation + posted limit entries, registered together.** Enter
into confirmed extension and accept a poor fill (`run_census`: 67,814 runs, top
5% carry 56.5%; `run_signal` says predicting a start does not work). Pair with
posted-limit vs marketable — a measured **3× cost swing**, ≈0.0021/share passive
against ≈0.0067 marketable. Opposite ends of one axis; running them apart
measures neither. **Posted limits are not a rescue for MCL, which is negative
gross — please don't let this reopen it.**

A second, independent argument for posting arrived this week and is worth one
line: a practitioner's case is **fill probability**, not the rebate — a limit
resting *at* a level frequently does not fill because the queue ahead absorbs
the move. Same direction, different reason. `source_videos_20260907.md` §11.

**C2. Price the Databento `status` schema, then bucket entry outcomes on halt
state.** Nothing models LULD; **36.4% of Tier 2 pauses fall 09:45–09:50** and
Tier 2 pauses occur on 100% of trading days. Price before pulling.

**C3. The two unrun items from the Cameron pass** — position construction on
winners vs losers (his winners carry 36% more shares, Ben's 26% fewer), and the
hold-50% rule. Both computable today, no new data.

---

## Things to refuse if they come up

**Fibonacci ratios as constants.** 23.6 / 38.2 / 50 / 61.8 / 78.6 is five levels
across one range, so *something* is almost always "at a fib level" — multiple
comparisons dressed as analysis. Retracement **depth** survives as a swept
parameter; the ratios do not.

**MACD (or any indicator) as an ORB confirmation layer.** `entry_split_result`:
22 features, 11 families, 0 clear against a needed 1.86× lift, and
`macd_margin` was the **best at 1.56×** — already the nearest miss and it still
misses. The spec is deliberate: *"Indicators: None. The range, and price."*

**Fair value gaps / ICT / SMC entries.** An FVG is a three-bar minute-OHLCV
pattern — the class already closed on our tape. Externally, 648 backtests across
four ETFs from 1993: **0 beat buy-and-hold**, while 100% of order-block variants
"made money" and a frequency-matched **coin flip averaged $46,270**.
`source_videos_20260907.md` §10.

Plus everything on the previous refuse list: another entry-extraction pass over
Cameron's recaps; entry filters from minute OHLCV; stop-width work; exit rescues
on the losing population; dollar-volume or liquidity floors; the Cameron
flat-top / gap-and-go / reversal set; Bollinger + RSI on large caps; and
volume-profile constructions on the pre-market window.

---

## Proposed `PROGRAM_INDEX.md` §7 edit

Not applied — it is yours.

```
1.  ORB, joint grid: ORB_MINUTES x STOP_MODE x RETEST_MODE x EXIT_MODE.
    Add RETEST_MODE = zone_impulse (impulse-anchored, not range-anchored)
    and count it in §10.3 beside the three already counted. Carry the
    27.0% trigger->zone rate as the fork's price. Length/stop/retest/exit
    are coupled -- see orb_retest_depth_20260916.md §4.

2.  ORB blocker: check bar_minute (21.0M XNAS rows) for ten-session
    coverage before any Databento spend. RVOL is the one screen rule that
    is NOT COMPUTABLE and the outside literature says it carries 100% of
    the stocks-ORB edge.

3.  Settle §11.1 criterion 2 BEFORE ORB produces a number; re-score MC5
    under the replacement in the same pass.

4.  Rank allocation vs arrival-order allocation under the concurrency cap.
    PROMOTED: cameron_names validated our ranking externally at AUC 0.688
    (0 of 2,000 draws). Register dollar_vol as a NEGATIVE control (0.29x).
    Report trade count and overlap, not only P/L. Shares the RVOL lever
    with item 2.

5.  Run participation + posted-limit entries, registered TOGETHER.
    NOT a rescue for MCL, which is negative gross.

6.  Price the Databento `status` schema, then bucket entry outcomes on
    halt state.
```

---

## Standing requirements

Register before you run. All three friction levels, never commission-only. Two
denominators, and a disagreement is a refusal. drop-top-N on the level and the
delta, `n/a` never `$0`. Both halves. Sessions, not trades. Boundary check on
any grid. And the one this project keeps failing: **a control whose output is
indistinguishable from the failure it detects is not a control** — the 648-test
coin flip in the refuse list above is this week's illustration from outside.

**Nothing is profitable. `holdout.json` is cut 2026-09-07 and unspent, and
nothing here is ready to spend it.**
