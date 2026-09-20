# The exit question, closed — and the regime gate: real, but not predictable

Runs 2026-09-11 on Ben's machine. Reports at `var/reports/ladder_mcl.txt`,
`cameron_exit.txt`, `dip_entry.txt`, `regime.txt`. Holdout untouched in all four
(8,484 xnas sessions and 307 bar_cache sessions set aside).

> **The headline: MCL's 5% trail survives every challenge brought against it.**
> The ladder, Cameron's partial, Cameron's breakeven stop and the dip entry were
> four separate attempts to improve the exit or the entry on 19,292 sessions.
> All four lose. Three of them looked promising on `bar_cache` first.

---

## 1. The take-profit ladder is REJECTED — and this supersedes the `bar_cache` result

| | trades | net | per trade | win% | drop-top-3 |
|---|---:|---:|---:|---:|---:|
| hold (baseline) | 4,481 | −$23,394 | −$5.22 | 26.2% | −$28,310 |
| **ladder** | 4,481 | **−$25,006** | **−$5.58** | 26.3% | −$28,531 |
| ladder, linear | 4,481 | −$25,019 | −$5.58 | 26.3% | −$28,544 |

**Net −$1,612, −$0.36 per trade. Worse, exactly as registered.**

> **This overturns the earlier reading.** On `bar_cache` — 373 sessions — the
> ladder measured **+$272** (+$106 after the extra orders), positive in both
> halves and better after drop-top-3, *against* the registered prediction. On
> 19,292 sessions it is negative. **The +$272 was 373 sessions of noise
> agreeing with a wish**, and it had already been cited as evidence in two
> module docstrings.

The rung-survival table is the mechanism, and it needed no ladder to compute:

```
ended at or above the FIRST rung  (+10%):  355 of 4,481   (7.9%)
ended at or above the SECOND rung (+21%):  122            (34.4% of those)
```

Only 7.9% of trades reach the first rung. Selling half of those forfeits the
runners, and the runners are the only thing paying for the other 92%.

The **linear control lands within $13** of the compounding form (−$1,625 vs
−$1,612), so this is about taking profit at all, not about rung spacing.

## 2. Cameron's exit is REFUTED, and so is the mechanism I registered for it

| cell | trades | net | per trade | win% | scratch% | avg bars |
|---|---:|---:|---:|---:|---:|---:|
| MCL today | 4,481 | −$23,394 | −$5.22 | 26.2% | 7.6% | 8.3 |
| stop change only | 4,320 | **−$50,654** | −$11.73 | 17.1% | 7.6% | 13.5 |
| partial only | 4,481 | −$24,829 | −$5.54 | 26.3% | 7.5% | 8.3 |
| **CAMERON** | 4,320 | −$38,916 | −$9.01 | 26.1% | 7.7% | 13.5 |

**Attribution: the partial −$1,435 (and the sign flips between halves), the
breakeven stop −$27,260, the combination −$15,522.**

Registered before the run: *"the partial helps, the breakeven hurts, and the
combination lands between them."* One right, one wrong, one right. The partial
does **not** help — consistent with §1, which is the same rung measured a
different way.

**The breakeven stop is the expensive half, and the stated mechanism did not
appear.** The argument for it was that it converts a small loss into a scratch,
lifting the win rate without adding money — how 32% becomes 71%. On this tape:

- **scratch% does not move at all**: 7.6 → 7.6 → 7.5 → 7.7 across all four cells
- the win rate **falls** 9pp on the stop change, it does not rise
- average hold goes **8.3 → 13.5 bars**, and the trade count *drops* 4,481 →
  4,320 because the longer holds consume the session

So the breakeven stop is not banking scratches. It is **holding losers longer**
— exactly what the docstring's own fade arithmetic predicted (once a trade is up
more than ~5.3%, breakeven sits *below* a 5% trail and gives the position *more*
room, not less) and the opposite of the risk reduction it sounds like.

> **`cameron_exit_result.md` §4 needs correcting on one point**: the partial's
> +$261 there came from the same 373 sessions as the ladder's +$272 and does not
> survive. The breakeven conclusion stands and strengthens.

## 3. Dip buying: same verdict on 50× the data, plus one new fact

| bucket | n | MFE | MAE | MFE/MAE | early | late |
|---|---:|---:|---:|---:|---:|---:|
| BOTH fired (dip) | 2,061 | 21.3% | 14.3% | 1.56 | 1.82 | 1.38 |
| BOTH fired (MCL) | 2,061 | 18.4% | 17.2% | 1.05 | 1.09 | 1.03 |
| **DIP ONLY** | **3,307** | 8.5% | 10.4% | **0.85** | 0.89 | 0.81 |
| MCL ONLY | 571 | 2.5% | 4.4% | 0.56 | 0.49 | 0.60 |

The added trades — the 3,307 setups MCL's confirmation entry refused — come in
at **0.85 against MCL's 0.97**, in both halves. The paired advantage (1.56 vs
1.05) is the fill: the dip buys 3.0% lower by construction.

**The new fact, and it reframes the whole thread: the signal is mostly LATE.**
1,176 sessions where the dip fired *after* MCL's entry against 885 before. A dip
that fires after the entry is a re-entry into a position MCL already holds, not
an earlier entry. So whatever this detector is finding, **it is not the earlier
entry the four convergent findings argued for** — it is a different setup that
happens to fire on the same names.

That is still evidence about the *inference*, not about dip buying. `warrior_4`
§6 names `ORWJzImSTdE` and `hz7vhSIXXSc` as the sources that state the actual
rule and **neither is transcribed**. Transcribing them remains the highest-value
item on this thread.

## 4. The regime gate: measured properly, and still null — but not dead

The `bar_cache` run was undecidable, not informative: the corrected sessions
column showed **cold = 1 session**, and 71 trades from 14 mornings is not a
sample. `regime_study` now refuses a verdict below
`MIN_SESSIONS_PER_BUCKET` for that reason.

On `bar_cache_xnas` — **378 labelled sessions, 4,481 trades**:

| bucket (yesterday's regime) | sessions | trades | per trade | win% |
|---|---:|---:|---:|---:|
| cold | 101 | 892 | −$8.73 | 24.6% |
| **mixed** | 126 | 1,392 | **−$1.61** | 27.7% |
| hot | 151 | 2,197 | −$6.08 | 25.9% |

**Not adoptable.** hot − cold = +$2.65, permutation **p = 0.2964**, and the
ordering is not monotone — **mixed is the best bucket by a wide margin**. Both
halves agree in sign (+2.95 / +4.72) and it survives drop-top-3, so two controls
pass and two fail. A middle bucket that beats both ends is not a temperature.

### The ceiling IS significant — and that changes what this thread is

The same-day split, which cannot be acted on at 04:00:

| bucket (today's regime) | sessions | trades | per trade |
|---|---:|---:|---:|
| cold | 100 | 873 | −$8.81 |
| mixed | 127 | 1,386 | −$6.59 |
| hot | 151 | 2,222 | **−$2.95** |

**hot − cold = +$5.86, permutation p = 0.0240, monotone.** Against the lagged
split's +$2.65, p = 0.2964, non-monotone.

So of the two possible causes of a null lagged gate, it is the second:

> **The breadth features DO separate MCL's trades. Today's reading is simply
> not recoverable from yesterday's.** Persistence is 45.8% against 33% for
> chance — real, but not enough to carry the ordering across a day.

**The bottleneck is predictability, not signal.** That is a different problem
from "regime does not matter here", and it has obvious next moves where the
other conclusion had none.

**Three caveats, and the first is mine to own:**

1. **The ceiling test was added after seeing the ordering.** I looked at a
   monotone, wide table in the previous run and then decided to test it. That
   is not a pre-registered p-value and 0.024 should be read as suggestive, not
   decisive. Anything built on it needs its own registration.
2. **Every bucket is negative.** −$8.81 / −$6.59 / −$2.95. Even a *perfect*
   regime gate leaves MCL losing $2.95 a trade on this universe against −$5.22
   ungated. The gate is worth about $2.30 a trade at its theoretical best —
   real, but not a path to profit on its own.
3. **Still in-sample**, and the holdout does not cleanly cover it: the regime
   features are new since the cut, but MCL's own parameters were fitted over
   the whole period including the locked slice.

### What this licenses next

**The intraday reading, not a smoother.** You cannot know at 04:00 how the day
will end — but by **07:00** you can see how today's movers are behaving, and
`warrior_census_20260910.md` §7 puts **50 of 87 stated first trades in the
07:00 hour and none at 04:00 or 05:00**. A partial same-day regime reading is
available before most entries happen. `screen_at.py` is already a point-in-time
screen, so this is the same computation on a truncated day rather than a new
mechanism.

That converts the ceiling into something actionable without asking yesterday to
predict today, and it needs no fitted constants — which the asymmetric smoother
(*"the shift from hot to cold is much more subtle than the shift from cold back
to hot"*) does. The smoother is now motivated rather than speculative, but it is
two swept parameters and should wait behind the intraday version.

And the separate point stands regardless: his gate is discretionary and changes
**size**, not participation — in a cold market he cuts ~5×, drops to A-only and
stops by 10:00. Given caveat 2, a size response is the only version of this
worth much anyway.

## 5. Four defects the runs exposed — all fixed, `20260911f` and `g`

Each is the same shape: **a control whose output is indistinguishable from the
failure it detects.**

1. **The leading gainer was mostly reverse splits.** 195% median, ≥100% gainer
   on 729 of 863 sessions. Daily bars are not split-adjusted, so a 1-for-10
   prints as a ~900% overnight gain with no volume behind it, and across ~9,000
   names in the band there are several every session. A move must now clear the
   screen's own relative-volume floor against the symbol's **shifted** trailing
   median — shifted, or a huge day raises the bar it has to clear and the
   biggest movers filter themselves out.
2. **The sessions column counted the archive, not the run** — "297" beside nine
   trades, in a column the eye reads as sample size.
3. **"The sign flips between halves" was wrong.** `late +0.00` was an *empty*
   bucket; `spread()` returns 0.0 for one, failing the both-halves test for the
   same reason a real reversal does.
4. **A one-session bucket carried a verdict** — §4.

## 6. What this leaves

**Settled and not worth revisiting:** the ladder, Cameron's partial, Cameron's
breakeven stop, the inferred dip entry. The 5% trail stands.

**Open, in order:**

1. **The intraday regime reading at 07:00**, per §4 — the one move the ceiling
   result licenses, and it needs no fitted constants.
2. **Transcribe the two dip videos.** Every dip finding so far is about an
   inference, not about his rule.
3. **The SIZE response rather than a go/no-go** — what he actually changes, and
   the only version worth much given that every regime bucket is negative.
4. The asymmetric smoother, behind (1), with its settings pre-registered.
5. `backtest_trades_mc5.csv` is now produced; the apex-off decision rests on
   `mc5_apex.txt` (+$3,177, both halves, drop-top-3).
