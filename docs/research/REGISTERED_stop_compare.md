# REGISTERED — H-S6: does the give-back's SHAPE beat a flat daily stop? (PRE-RUN)

## 0. A correction to this doc's own citation (PRE-RUN, 2026-09-18)

This registration and `REGISTERED_giveback_cap` §1 both cite "`PROGRAM_INDEX`
§7 item 11, the daily loss stop". **That number is stale in both.** §7 was
rewritten on 2026-09-12 and again on 09-16 and 09-17; item 11 in the current
list is *Cameron's breakeven stop as a `pit_delta` variant*, and **the daily
loss stop is not in the current §7 at all** — it was dropped in a rewrite and
two chats have been citing its old number to each other since.

Nothing about the hypothesis changes. What changes is how it is referred to:
**the rule is named here, in full, and the index entry is created to match**
rather than pointed at by number. §4's standard already says a hash cited in
prose is a second source of truth that goes stale in silence; an item NUMBER
cited across chats is the same failure with a smaller blast radius.

## 1. The question, and why it is not answered by H-S4 passing

The daily loss stop — an absolute drawdown from zero — has been wanted since
2026-09-12 and has never been run. It is registered now because H-S4 passed:
`session_scenarios_RESULT_20260918.md` reports MC5's 50% give-back cap clearing
all six of its readings under both scopes at every friction level, and §6 of
that registration says a pass is not adoptable on its own. **Committed before
`common/stop_compare.py` exists.**

The give-back cap fires on sessions **selected for having declined from a
peak**, and on such a session stopping is close to tautologically better than
continuing. What H-S4 established is that the cap beats a random cut *in those
same sessions*. What it did not ask is whether the **peak-relative shape** —
"give back half of what you had" — beats the simplest rule in the same family:

```
For each session, walking the closed trades in time order:
    realised = cumulative realised P&L so far, net of friction
    if realised <= -STOP:
        no further ENTRIES this session
```

No arm, no peak, no ratio. An absolute drawdown from zero — what the daily
loss stop has always meant, and what most traders actually run.

The two rules are genuinely different and it is worth saying how, so the result
cannot be read as a tautology either way. A session that goes **+$200 then back
to +$50** trips the give-back and never trips a flat stop. A session that goes
**straight to −$150 without ever being up** trips a flat stop and can never
trip the give-back, which needs a $40 peak first. The give-back carries one
extra piece of information — that there was something to give back — and this
registration asks what that information is worth.

## 2. The comparison is matched on trades removed, and that is the whole design

A flat stop has a free parameter and the give-back does not, so comparing them
at an arbitrary $STOP would be a search wearing a comparison's clothes. The
threshold is therefore **not chosen; it is solved for**:

> For each (strategy, scope, friction) cell in which the give-back fired,
> find the `STOP` whose rule removes as close as possible to the **same number
> of trades** the give-back removed, and compare the two rules at that point.

Both rules then spend the same abstention budget on the same book, and the only
thing that differs is **which** trades they spend it on. This is the same logic
as the matched-count control in H-S4 amendment A4, and it removes the
threshold as a degree of freedom entirely: `STOP` is determined by a
constraint, never by a P&L.

**This is not circular.** The count comes from the give-back's behaviour, not
from either rule's profitability; no flat stop is ever selected for performing
well.

## 3. Cells

| cell | rule | status |
|---|---|---|
| **FLAT-MATCHED** | `STOP` solved to match the give-back's removal count | **PRIMARY** |
| FLAT-40 / FLAT-100 / FLAT-200 | fixed dollar stops | **reported, never scored** |
| give-back | H-S4's GB-50, unchanged | the incumbent |

The three fixed stops exist so the trade-off between threshold and removal
count is visible. **A best cell among them is not a result and is not
adoptable**, and no fixed stop may be quoted as the comparator afterwards —
that role belongs to FLAT-MATCHED alone, which was fixed before the run.

Both strategies, both scopes, all three friction levels, on the same
`session_scenarios_trades.csv` the H-S4 pass was measured on. No second pass
over the tape: the books are identical by construction, which is the point.

## 4. The decision rule, fixed here

At each cell, let **D_give** and **D_flat** be the two rules' deltas per
remaining trade.

- **THE SHAPE SURVIVES** iff `D_give > D_flat` **and** a bootstrap of the
  *difference*, clustered **by session** (the unit both rules act on), is above
  zero in ≥ 95% of 2,000 resamples, at **$4.26 and $8.92** — the same two
  levels H-S4 §7 requires.
- **THE SHAPE ADDS NOTHING** iff `D_flat >= D_give` at either level. In that
  case the give-back is an ornament: the flat stop is simpler, has no arm, no
  ratio and no peak to track live, and it should be the thing registered
  instead.
- Anything else — the difference positive but the bootstrap short — is
  **UNDECIDED**, and the holdout is not spent on either rule.

**Reported, and how the result is read rather than scored:** the solved `STOP`
per cell; how many sessions each rule fires on and how many they share; the
per-trade P&L of what each removes; and the fire-time distribution of both,
because H-S4 §5's worry — that this is the time-of-day filter under another
name — applies to a flat stop at least as much.

## 5. Registered prediction

- **THE SHAPE SURVIVES, narrowly.** `D_give − D_flat` of **+0.10 to +0.50** per
  trade, with the bootstrap marginal. Confidence: **moderate**.
- **Reason:** the two rules fire on overlapping but genuinely different session
  sets (§1), so the flat stop cannot be a perfect substitute; but both are
  abstention on a losing book, both fire mostly in the back half of the
  session, and most of what either achieves is removing trades from a book that
  loses per trade. I expect the flat stop to capture most of the give-back's
  78 cents and the residual to be small.
- **If the flat stop wins outright**, the honest conclusion is that H-S4's pass
  measured "stopping on a bad day helps" and not "the 50% give-back helps", and
  the two practitioners' 50% is then a number without a mechanism.

## 6. What this does not decide

Nothing about shipping either rule. `holdout.json` stays shut — this is the
test that decides **which** rule is worth the one holdout spend, not a spend
itself. The live parity requirement in H-S4 §6 stands for whichever survives:
the live trader must compute `realised` exactly as the backtest does before a
session-level rule goes anywhere near a live session.
