# Handover from the research chat — 2026-09-11

*(Paste everything below into the build chat.)*

---

Read `claude/HANDOVER_20260911.md` first. It is revised as of after
`pit_strategy_result_20260911.md` landed, and it indexes everything produced today on both sides.

## What I am not asking for

**Not the PIT strategy comparison — you have done it**, and the two-leak split is the most
important finding of the day. The universe leak being *negative* while the intraday leak carries
the whole thing is genuinely surprising, and the fact that the live trader never had that defect
turns part of the execution-gap mystery in `execution_gap_20260910.md` into a number.

The denominator trap you recorded in §7 item 1 is the same shape I hit this morning on a
large-cap Bollinger test: pooled by (name, day) it read **+0.286%/trade**; computed **date-level**
— the correct unit, because signals cluster — it read **−0.010%, t = −0.18 Newey-West**. Same
class of error, opposite corner of the project. Worth treating as a standing check.

## One thing that follows from your §0.3 and is not in your §8

**Every published MCL/MC5 delta measured on an unfloored run is overstated by $6.84–$11.99 per
trade.** That is larger than most of the deltas this project has been arguing about. Any of the
four rejected mechanics — ladder, Cameron's partial, Cameron's breakeven stop, dip entry — should
be **re-run floored** before the rejection is treated as settled, if any is ever revisited.

## Corrections to docs you may be reading

| Doc | Change |
|---|---|
| `cameron_exit_result.md` | The **partial-at-target finding is withdrawn**. +$261 became **−$1,435** on 4,481 trades. §4.1's target sweep is now flagged direction-durable, dollar levels in-sample. Superseded banners added |
| `warrior_5_selection_in_practice.md` §8 item 4 | The **prior-spike figure it cited as support inverted** on the screened universe: +$4.67 vs −$3.22 became **−$5.77 vs −$5.38**. That filter now has one route to it, not two. A caution was added to §5's price-band figure for the same reason |
| `warrior_4_reversal.md` | The **RSI 10/90 thresholds are not corroborated** by Cameron's own RSI video (`iS5lvJGMM8E`, read in full). They stay sourced to the W-REV web page alone. §4 revised; his explicit rejection of RSI as a momentum entry is recorded |

## Method docs worth having before the next runs

- **`friction_reconciliation_20260911.md`** — the three friction figures measure **different
  legs**, not the same thing. Your `stop_fill` result confirms that and quantifies the leg I
  flagged as the open one. Also: break-even friction on the screened universe is **negative** for
  all three strategies (MCL −$0.96/RT, VW9 −$0.70, MC5 −$4.67) — they lose *gross*, so the
  friction argument never changed the sign.
- **`win_rate_and_r.md`** — ten docs in this project report a win rate with **no paired reward
  figure**, which makes R unrecoverable from them. Proposed standing rule: any doc stating a win
  rate states average win, average loss and R alongside it, or says explicitly that they were not
  computed.
- **`exit_candidates_20260911.md`** — three registerable exit experiments, sequenced. **Run
  MFE-after-exit first**: it is a pure measurement with no parameters, and it decides whether the
  other two matter. If exits cluster far below the session high, the exit is the problem; if they
  do not, **R = 0.58 is an entry problem** and the whole exit queue is a distraction.
  `dip_entry_result.md` already has the MFE/MAE machinery — this turns it on exits rather than
  entries. Also records one **anti-pattern** (widening a losing stop on discretion) so it is not
  reconsidered.
- **`external_evidence_20260911.md`** — the academic literature independently reproduces this
  project's findings from completely different data. §1 and §2 are the ones to read. Short
  version: our win rate is fine and R is the defect (confirmed from live professional trading
  records), and four independent literatures find the money in this activity goes to whoever
  **posts** liquidity, not whoever takes it.

## Two urgent items not on `PROGRAM_INDEX` §7

**1. `ib_insync` is archived.** Repo archived 2024-03-14, last release 2023-07-02, the author
died in March 2024. Our IBKR integration is built on it. Replacement is **`ib_async` 2.1.0**
(released 2025-12-08) — near drop-in, same `IB()` / `reqHistoricalData` surface, but pin the
version. An unmaintained broker API does not fail loudly; it fails when IBKR changes something.
Detail in `tooling_audit_20260911.md` §0.

**2. `PROGRAM_INDEX` §7 is stale in both directions.** It was written at **07:32**; three results
landed after it. Item 1 — the one it calls *"the one that gates everything else"* — was answered
at **11:03** and still reads as open. None of today's proposals are in it either. There is a
**proposed replacement table in `HANDOVER_20260911.md` §5**, reordered around your own §8 plus
the exit queue, the unpriced `window_close` leg, and halt modelling. Take it or amend it — but
the current §7 will send someone to redo closed work.

I did not rewrite the index directly, because you were editing it this morning and
`project_write` replaces whole content. It is yours to apply.

## Scope

Unchanged: **this chat does not touch program logic under `D:\Trading`.** Everything above is
spec, source assessment, method and corrections. The runs are yours.

## Not a build item, but worth saying

**MCL beating H0 on both denominators is the first structurally positive finding in this
project** — its trades are individually better than the control's *and* it declines most
opportunities. That deserves its due; selection is doing something real.

It is also −$10.49/trade and −$6.23 gross, every arm of both strategies is negative at every
friction level, and your own line is the right frame to keep beside it: **"never trade" scores
0.00/symbol-day and beats everything here.**
