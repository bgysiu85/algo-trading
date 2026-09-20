> **ARCHIVED 2026-09-08.** Superseded by `mcl_rejected_mechanics.md`, which carries the verdict.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

> **Stale figures — the fill-model correction.** Every P/L number below predates
> the 2026-09-05 fix to gap-through fills and peak-seeding, and is overstated
> because of it: MCL's headline went +$1,567 → +$161 and MC5's +$20,156 →
> −$400, on identical trades. Only the price they were booked at changed.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check.** Measured on a fuller tape
> that includes off-exchange prints, the backtests charge ~$2.00 per 100-share
> round trip against a real ~$1.00 — they are slightly *conservative* on
> slippage, not wrong. See `execution_cost_measured.md`.
>
> So: overstated by the fill-model correction, and by that alone. The reasoning
> and the decisions recorded here stand.

# TRAIL_PCT decision — 2026-09-05

`claude/mcl_robustness_analysis.md` called `TRAIL_PCT` "the largest open lever
in the project" and listed four checks required before it moves. This ran them.

**Verdict: do not move the trail. Keep `TRAIL_PCT = 5.0`.**

Not because 5% is good — it is still the trough of the raw curve — but because
**no candidate value, tight or wide, survives the standards of evidence this
project already applies.** The raw table was measuring the wrong thing.

Source: `common/trail_study.py --candidates ...`, run against the 373-session
cache with the shipped configuration (apex OFF, MACD>0 ON). Costs ~2.5 minutes
per pass, entirely offline.

---

## 0. The control — the method is sound

Before trusting any of this, the same paired-bootstrap code was pointed at the
already-published apex result:

| | delta | 95% CI | P(>0) |
|---|---:|---|---:|
| published (`mcl_apex_macd_sweep.md`) | +$1,702 | [+$703, +$2,816] | 100% |
| this tool, seed 20260905 | **+$1,701.78** | [+$713, +$2,847] | 100% |
| seeds 1 / 42 / 7777 | +$1,701.78 | [+$689…+$712, +$2,821…+$2,842] | 100% |

Exact to the cent, stable across seeds. What follows is therefore a real
difference in kind from the apex result, not an artifact of a different
implementation.

---

## 1. The curve that raised the question

Full sample, apex OFF, `after fric` applies the measured $4.26/round trip.

| trail | trades | net | $/tr | drop5 | after fric | med hold | p95 | worst trade |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2% | 556 | +$4,157.25 | +7.48 | **+$3,053** | +$1,788.69 | 1 | 8 | **−$40.04** |
| 3% | 533 | +$4,036.87 | +7.57 | +$2,841 | +$1,766.29 | 1 | 17 | −$59.06 |
| 4% | 517 | +$3,930.51 | +7.60 | +$2,061 | +$1,728.09 | 2 | 28 | −$78.08 |
| **5%** | **496** | **+$3,865.53** | **+7.79** | **+$1,883** | **+$1,752.57** | **2** | **35** | **−$97.10** |
| 6% | 479 | +$3,822.84 | +7.98 | +$1,900 | +$1,782.30 | 3 | 43 | — |
| 8% | 449 | +$5,724.37 | +12.75 | +$2,757 | +$3,811.63 | 5 | 73 | −$137.40 |
| 10% | 426 | +$6,654.09 | +15.62 | +$3,738 | +$4,839.33 | 7 | 90 | −$176.00 |
| 12% | 402 | +$6,998.56 | +17.41 | +$4,193 | +$5,286.04 | 10 | 131 | — |
| 15% | 382 | +$8,643.41 | +22.63 | +$3,255 | +$7,016.09 | 14 | 156 | −$237.30 |
| 20% | 344 | +$13,607.32 | +39.56 | +$1,920 | +$12,141.88 | 30 | 214 | — |

Read alone this says "go to 20%". Two things it hides:

- **A wider trail takes fewer trades and so pays less friction.** Part of the
  apparent gain is avoided cost, not edge.
- **It is a level table, not a difference table.** The question is not "how
  does 15% score" but "is 15% better than 5% by more than noise".

---

## 2. Holdout — everything passes, which is the first warning

| trail | EARLY net | EARLY drop5 | LATE net | LATE drop5 | both halves? |
|---:|---:|---:|---:|---:|---|
| 5% | +$1,185.34 | **−$60.77** | +$2,680.19 | +$872.95 | (incumbent) |
| 2% | +$1,391.57 | **+$583.25** | +$2,765.68 | **+$1,760.06** | YES |
| 3% | +$1,407.79 | +$471.20 | +$2,629.08 | +$1,611.59 | split |
| 4% | +$1,637.21 | +$237.97 | +$2,293.30 | +$920.02 | split |
| 8% | +$1,766.80 | −$377.49 | +$3,957.57 | +$1,778.85 | YES |
| 10% | +$2,830.49 | +$123.74 | +$3,823.60 | +$1,771.92 | YES |
| 15% | +$5,674.96 | +$533.46 | +$2,968.45 | +$425.80 | YES |

Split fixed at 2026-03-20 — the same date `analysis.py` uses, deliberately not
swept.

Four of six candidates improve in both halves. When almost everything passes a
test, the test is not discriminating: a monotonic parameter will trivially move
both halves the same direction. The holdout was the right check for a binary
rule like apex; it is close to uninformative for a continuous one.

---

## 3. Paired bootstrap — nothing clears the bar

10,000 resamples of symbols, zero-filled over all 275 cache symbols so both
sides see the same universe.

| trail | delta vs 5% | 95% CI | P(>0) | better | worse | median |
|---:|---:|---|---:|---:|---:|---:|
| 2% | +$291.72 | [−$1,663, +$2,054] | 62.5% | 121 | 52 | $0.00 |
| 3% | +$171.34 | [−$1,501, +$1,641] | 59.5% | 125 | 48 | $0.00 |
| 4% | +$64.98 | [−$1,051, +$1,051] | 55.6% | 130 | 43 | $0.00 |
| 8% | +$1,858.84 | [−$1,123, +$5,417] | 87.0% | 61 | 111 | $0.00 |
| 10% | +$2,788.56 | [−$531, +$6,573] | 94.9% | 67 | 105 | $0.00 |
| 15% | +$4,777.88 | [−$875, +$11,918] | 94.8% | 74 | 98 | $0.00 |
| *apex removal, for scale* | *+$1,701.78* | *[+$713, +$2,847]* | *100%* | *51* | *51* | *$0.00* |

**Every interval straddles zero.** The best is 94.9%, against the 100% the
apex change reached with a CI comfortably clear of zero. On this project's own
stated standard, none of these is a result.

Note the sign asymmetry, which the net column completely hides: **widening
makes more symbols worse than better** (8%: 61 better, 111 worse). Tightening
does the opposite (2%: 121 better, 52 worse). The wide end's headline is
carried by a minority against a majority moving the other way.

---

## 4. The check that actually decides it

Apply the drop-top-N rule — the one that killed V8 and V9 — to the *delta*
rather than the level. Remove the five symbols contributing most to the
improvement, and ask whether an improvement remains.

| trail | raw delta | after removing top-5 movers | survives? |
|---:|---:|---:|:--|
| 2% | +$291.72 | **−$457.53** | no |
| 3% | +$171.34 | −$379.55 | no |
| 4% | +$64.98 | −$256.32 | no |
| 8% | +$1,858.84 | **−$1,092.64** | no |
| 10% | +$2,788.56 | −$70.40 | no |
| 15% | +$4,777.88 | −$419.16 | no |

**Not one value survives.** Every trail change on this dataset is five names.

The names are largely the same ones each time — WLDS appears in the top five of
every widening candidate and is the single largest contributor at every width
(+$1,116 at 8%, +$1,022 at 10%, +$2,378 at 15%), with BATL, SDOT, AKAN, QNRX
and TRT recurring. The 15% column is close to "WLDS and BATL had two very good
days".

This is the same failure mode the apex sweep was careful to disclose about
itself — but apex passed the paired bootstrap anyway. The trail does not pass
either check.

---

## 5. The one real argument for changing it, and it is not about return

Setting the delta aside: **the 2% configuration is a less fragile machine than
the 5% one, at the same expected return.**

| | 5% | 2% |
|---|---:|---:|
| net | +$3,865.53 | +$4,157.25 |
| drop5 | +$1,883.03 | **+$3,053.19** |
| drop5, EARLY half | **−$60.77** | **+$583.25** |
| drop5, LATE half | +$872.95 | +$1,760.06 |
| symbols better / worse | — | 121 / 52 |
| worst single trade | −$97.10 | **−$40.04** |
| median hold | 2 bars | **1 bar** |
| p95 hold | 35 bars | **8 bars** |
| trades held >30 bars | 33 | **4** |

The return claim is unsupported (+$292, P(>0) = 62.5%, a coin flip). The
*robustness* claims are not statistical inferences at all — they are properties
of the resulting configuration, and they are large:

- **5% is the only setting whose early half is concentration-negative.** The
  robustness analysis flagged this: "three of the four cells are negative once
  their five best names are removed". At 2% both halves are positive.
- **The operational risk shrinks by roughly 4×.** p95 hold 35 bars → 8. Outside
  RTH there is no native stop resting at IBKR; the trail lives inside the
  running process, so a crash with a position open leaves it unprotected. That
  was named as apex removal's main danger. A 2% trail largely retires it.
- **Worst single trade halves**, −$97 → −$40.

### What tightening costs

- **A thinner friction buffer per trade.** 2% takes 60 more trades, so it pays
  ~$255 more friction and its break-even is **$7.48/trade against 5%'s $7.79**.
  Both clear the measured $4.26, but 2% clears it by slightly less.
- **It partly undoes the apex removal** — see §6.

---

## 6. The interaction nobody has measured until now

Apex and MACD>0 were independent and additive. **Apex and the trail are not.**

| | trades | net | $/tr | drop5 | after fric | med hold |
|---|---:|---:|---:|---:|---:|---:|
| trail 2%, apex ON | 569 | +$3,845.88 | +6.76 | +$2,772.72 | +$1,421.94 | 1 |
| trail 2%, apex OFF | 556 | +$4,157.25 | +7.48 | +$3,053.19 | +$1,788.69 | 1 |
| trail 5%, apex ON | 561 | +$2,163.75 | +3.86 | +$315.73 | **−$226.11** | 2 |
| trail 5%, apex OFF | 496 | +$3,865.53 | +7.79 | +$1,883.03 | +$1,752.57 | 2 |

**Apex removal is worth +$1,702 at a 5% trail but only +$311 at a 2% trail.**

They are substitutes, not complements: a tight trail already cuts the positions
the apex rule was cutting, so removing apex adds much less. This does not
retract the shipped change — it is positive at both widths — but it means the
+$1,702 figure is specific to a 5% trail and should not be quoted as the value
of apex removal in general.

It also means a trail change is not the single-variable move it looks like. It
silently re-prices a decision already shipped.

---

## Recommendation

1. **Keep `TRAIL_PCT = 5.0` for now.** No value clears the paired bootstrap,
   and no value's delta survives removing five symbols. Widening in particular
   should be dropped as a candidate: it is tail-carried, it makes the majority
   of symbols worse, and it multiplies the unprotected-position risk.

2. **Reopen 2% specifically, as a risk decision rather than a return one.** The
   case for it does not rest on P/L and so does not need a bootstrap: better
   concentration robustness in both halves, half the worst-case trade, and a
   quarter of the hold-time exposure, for a return difference indistinguishable
   from zero. That is a legitimate reason to change a parameter. It should be
   argued and decided on those terms, explicitly, not smuggled in on the net
   column.

3. **Before 2% ships, re-run the apex comparison at 2%** and record that its
   value drops to +$311. One variable at a time means knowing what the other
   variable is worth after the change.

4. **The friction figure is now doing even more work.** At 2% the break-even is
   $7.48/trade against a $4.26 estimate from **one** session. Re-measuring
   friction is worth more than any further trail sweeping.

---

## Caveats

- Same 373-session, 275-symbol contemporaneous set; still IB split-adjusted
  prices; selection bias inherited and unfixed.
- `TRAIL_PCT` is a module constant, monkeypatched around each run
  (single-threaded, `try/finally`). If the trail becomes a real tunable it
  should get the per-call parameter treatment `use_apex` already has.
- The holdout split was not swept, deliberately.
- The drop-top-5-movers test is a robustness screen, not a significance test.
  It is used here the same way the project already uses drop-top-N on levels.
