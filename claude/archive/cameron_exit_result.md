# Cameron's exit, measured — 2026-09-11

`warrior_0` §5.3, `warrior_1` §6 and `HANDOVER_TO_BUILD_20260910.md` all name
this as **the largest untested gap in the spec set**, and the handover's §0
explains why it outranks the others: MCL is Ben's own version of the method, so
this is the intent and MCL is the drift.

**Measured. The gap is real, and closing it in the direction the handover
describes costs money.**

> # ⚠ SUPERSEDED IN PART — corrected 2026-09-11
>
> `ladder_and_regime_20260911.md` §2 re-ran this identical 2×2 on the **screened
> universe: 4,481 trades across 19,292 sessions**, roughly 9× the sample this
> document used. **The one positive finding here did not survive.**
>
> | | this doc (485 trades, `bar_cache`) | re-run (4,481 trades, screened) |
> |---|---:|---:|
> | **Partial at target** | **+$261** | **−$1,435** |
> | Breakeven stop | −$4,271 | **−$27,260** |
> | Cameron's exit (both) | −$1,741 | **−$38,916** vs −$23,394 baseline |
> | Win rates (base / stop / partial / both) | 34.0 / 22.7 / 34.0 / 34.1% | 26.2 / **17.1** / 26.3 / 26.1% |
>
> **What changed:** §2's "the partial helps" is **withdrawn**. Both halves of his
> exit now measure negative. The ladder's +$272 — which §1 below cites as
> corroboration — went the same way: **−$1,612 on 4,481 trades**, and
> `ladder_and_regime` calls the original *"373 sessions of noise agreeing with a
> wish."* Two in-sample measurements agreeing with each other is not two pieces
> of evidence; it was one dataset answering twice.
>
> **What survives:** everything in §3 (the mechanism by which a breakeven stop
> widens rather than tightens), §4 (the premise does not reproduce — now
> reproduced *harder*, the stop alone cutting the win rate 9pp on the large
> sample), and §4.2 (the two transplant failure modes). The §4.1 target sweep's
> **direction** survives; its **dollar levels do not** — see the note there.

| | verdict (corrected) |
|---|---|
| Take half at a target | **REJECTED** — +$261 in-sample became **−$1,435** on 9× the data |
| Move the remainder to a breakeven stop | **REJECTED** — −$4,271, then **−$27,260**; it *lowers* the win rate |
| The two together (his exit) | **REJECTED** — −$1,741, then **−$38,916** |
| The premise — that this explains 71% vs 32% | **does not reproduce**, on either sample |

Tools: `common/target_exit.py`, `common/cameron_exit.py`. Report:
`var/reports/cameron_exit.txt`.

> **§4.2 WAS WRONG AND IS WITHDRAWN — corrected the same day.** It claimed the
> cent rules fail because his parameters are scaled to a much larger position.
> They are not: `MEASURED_FRICTION` is **$0.0426 per SHARE**, and $4.26 is that
> × 100. At 10,000 shares a 15c target is $1,500 against $426 of friction — the
> same 28%. **The ratio is invariant to position size.** The real reasons are
> two different ones and are in §4.2 as rewritten.

> **Friction note added 2026-09-11.** Every dollar figure in this document is
> charged at $4.26/round trip, which is an **n = 2** measurement of stop-fill
> slippage taken on a session with the wrong exit mix. See
> `friction_reconciliation_20260911.md`. MCL's `bar_cache` baseline of +$161
> **flips sign across the plausible friction range** (+$1,742 at $1.00/RT,
> −$2,099 at $8.92/RT), so every comparison below should be read as a delta
> against a baseline that is itself not reliably positive.

---

## 1. How the target was chosen, because it decides everything

`warrior_0` §5.2 lists four unreconciled statements of his first target — 2:1,
15–20 cents, the next half or whole dollar, 20c-on-10c — and then says the thing
that settles the method:

> *"§5.1's rejection removes the cent stop these targets were scaled against, so
> the target question has to be re-posed against a percentage stop before it can
> be answered at all."*

**Re-posed as §5.2 asks, his 2:1 against MCL's validated 5% trail is a 10%
target.** That is where `TARGET_PCT = 10.0` comes from, and nowhere else. It also
happens to be the ladder rung measured at +$272 — so one half of this exit
already had a measurement pointing the right way.

> **Corrected:** that +$272 was **−$1,612 on 4,481 trades**. The two
> measurements were the same in-sample dataset, not independent corroboration.
> Only **7.9%** of trades reach the first rung at all.

**The 5% trail stays in force before the target.** Substituting his rejected
initial stop into a test of his exit would confound the question with a settled
answer. Our stop until the target, his after it. This is a hybrid and is
reported as one.

---

## 2. The 2×2 — because the combination alone attributes nothing

373 sessions, 100 shares, after commission and $4.26/RT:

| cell | trades | net | per trade | win% | scratch% | avg bars | drop-top-3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| MCL today | 485 | +$161 | +$0.33 | 34.0% | 8.7% | 9.9 | −$923 |
| stop change only | 463 | **−$4,110** | −$8.88 | **22.7%** | 9.1% | **19.0** | −$5,708 |
| partial only | 485 | **+$422** | +$0.87 | 34.0% | 8.7% | 9.9 | **−$610** |
| **CAMERON** | 463 | **−$1,580** | −$3.41 | 34.1% | 9.1% | 19.0 | −$2,687 |

**Attribution:**

| | net | per trade | win rate |
|---|---:|---:|---:|
| stop change only | **−$4,271** | −$9.21 | **−11.3pp** |
| partial only | **+$261** | +$0.54 | +0.0pp |
| both (his exit) | −$1,741 | −$3.74 | +0.1pp |

> **⚠ THIS TABLE IS SUPERSEDED.** On 4,481 trades the partial is **−$1,435** and
> the stop is **−$27,260**. The conclusion that followed — "the partial helps" —
> **is withdrawn.** Note also that every cell here fails drop-top-3, *including
> the baseline* (−$923): on this cache no configuration survives removing three
> symbols, which on its own should have capped how much weight the +$261 carried.

~~**The partial helps. The breakeven stop is catastrophic.** Only one of the two
needs discarding~~ — **both need discarding.** The 2×2 was still the right design:
it is what let the stop's −$27,260 be separated from the partial's −$1,435
instead of reporting one blended −$38,916.

---

## 3. Why the breakeven stop fails — it is not what it sounds like

**This section stands, and the large sample strengthens it.**

A breakeven stop reads as risk reduction. **For a winner it is the opposite.**

Once a trade is up more than about 5.3%, the entry price sits *below* a 5% trail
from the peak. Moving the stop to breakeven therefore gives the remainder **more
room, not less**. On a constructed fade: the trail exits at 4.4459 after 33 bars;
breakeven holds to 4.0208 and 53 bars.

The cache agrees: **average hold goes from 9.9 bars to 19.0.** The mechanic is
*take the certain half, then give the rest a very wide stop*. On a tape where
most names that reach the target fade rather than run, that loses — and
`ladder_study` had already measured exactly that: only 28.3% of MCL trades
reaching +10% go on to +21%.

**Confirmed on 4,481 trades:** hold goes 8.3 → 13.5 bars, the win rate falls
**9pp**, and the scratch rate does not move at all (7.6 → 7.6 → 7.5 → 7.7) — so
the stop is not manufacturing the scratches it exists to manufacture, on either
sample size.

---

## 4. The premise does not reproduce, and this is the important part

> *"That single difference produces the 32.4%-versus-71.1% win rate."*

**It does not.** His exit moves MCL's win rate from 34.0% to **34.1%**. The
scratch rate barely moves (8.7% → 9.1%), so the breakeven stop is not even
manufacturing the scratches it was supposed to. Used *alone* it **lowers** the
win rate to 22.7%.

**On the screened universe the same thing happens more starkly:** 26.2% → 26.1%
for the full exit, and **17.1%** for the stop alone.

### 4.1 What does produce it — a closer target, and it costs money

| target | trades | net | per trade | **win%** | drop-top-3 |
|---|---:|---:|---:|---:|---:|
| no target | 485 | +$161 | +$0.33 | 34.0% | −$923 |
| **2%** | 485 | −$155 | −$0.32 | **39.8%** | −$964 |
| **3%** | 485 | −$122 | −$0.25 | **39.6%** | −$932 |
| 5% | 485 | +$96 | +$0.20 | 36.1% | −$713 |
| 7.5% | 485 | +$180 | +$0.37 | 34.0% | −$630 |
| 10% | 485 | +$422 | +$0.87 | 34.0% | −$610 |
| 15% | 485 | +$428 | +$0.88 | 34.0% | −$607 |

**Win rate falls monotonically as the target widens. P/L rises monotonically.** A
2% target buys **+5.8 percentage points of win rate for −$316**.

> **So his win rate is not evidence of a better exit. It is a different point on
> the same trade-off curve** — and the curve points the other way for us.

> **Status, 2026-09-11.** This sweep has **not** been re-run on the screened
> universe, and everything else on this cache that was re-run got worse.
> **Treat the monotone direction as the durable finding and the dollar levels as
> in-sample.** The direction is corroborated independently — it is the same
> trade-off visible in `hold_cap_decision.md` (forcing shorter holds raises
> nothing and costs $585–$2,084) and in the R arithmetic of
> `win_rate_and_r.md` §1.
>
> **Re-running this sweep on `bar_cache_xnas` is the cheapest open item in the
> project and is now the only thing standing between the most decision-relevant
> table here and an out-of-sample verdict.**

### 4.2 Why the transplants fail — TWO reasons, and neither is size

**This section stands unchanged.**

**The earlier claim that this is a position-size effect is withdrawn.** Friction
is $0.0426 per share, so the cost-to-target ratio is the same at 100 shares and
at 10,000. Size explains nothing here. The two failures have two different
causes:

**The cent stop failed on the PRICE BAND.** Across $2–20, 15c is 7.5% at $2 and
0.75% at $20. His names sit around $5–8, where 15c is a coherent 2–3%. One cent
value cannot serve a band ten times wider, at any share count. That was
`cent_stop_decision.md`'s own stated reason and it survives.

**The close target failed on OUR TRADE DISTRIBUTION.** Cutting at 2–3% forfeits
the right tail. MCL's R is 2.01 against his 1.20 — our money is in fewer, larger
wins, so a close target costs more than the extra wins pay. His distribution is
many small wins, and a close target suits it.

The second is partly circular — the distribution is itself a product of the exit
— which is precisely why the 2×2 was needed and why the answer is ~~"the partial
yes, the stop no"~~ **"neither, but for two different reasons"** rather than a
verdict on his method.

**What actually generalises from this:** a rule denominated in **cents** cannot
cross a $2–20 band, and a rule that **cuts the right tail** cannot cross to a
distribution whose money is in the right tail. Test any remaining Warrior
parameter against those two, not against a share count.

---

## 5. Boundary check

The best cell is **15%, at the edge of the tested range** — nominally a failed
boundary check. But 10% and 15% are within $6, so it is a **plateau, not a ramp**.
Extending to 20–30% would settle it and is cheap. **Still not done.**

---

## 6. What is adopted

**Nothing — and that verdict is now stronger, not weaker.**

`target_exit=None` on `backtest_session`; the live path is untouched. The
partial's +$261 here and the ladder's +$272 were the same effect measured twice,
both in-sample on the fitted 373 sessions — **and when that next step was taken
on `bar_cache_xnas`, both went negative** (−$1,435 and −$1,612 respectively).

**This document's original §6 named the right next step and the step returned a
negative answer.** That is the process working. Recorded here rather than
quietly dropped, because a rejected candidate that was once promising is exactly
what future work needs to not re-propose.

---

## 7. What this does NOT say

**It does not say his method is not worth building.** What was tested is three of
his *numbers*. The scoreboard:

| | status |
|---|---|
| **Micro pullback** — his most-used (172) and safest (0.7 lift) setup | **BUILT. It is MCL's core**, and the census endorses it |
| **Dip buying** — 129 mentions, half his book, same 0.7 lift | **NOT BUILT AT ALL** |
| Regime gate — 16× on the mean day | **tested 2026-09-11 — not adoptable** (p = 0.2964, non-monotone) |
| Hold-50% rule | untested |
| Front-side gate (MA cross, close below 20 EMA) | MCL has the MACD leg only |
| Daily loss stop | untested — and measured on **Ben's own tape** at +$55,083 |
| Re-arm 4–5× per move | untested |
| Early entry at a half/whole dollar | untested |
| Re-rank the screen at decision time | untested |
| Spread gate | untested |
| 07:00 window | untested |
| Cent stop · close target · breakeven stop · **partial at target** | **tested, all four rejected** |

Four numbers rejected, one setup built and validated, one setup untouched, one
gate tested and not adoptable, and roughly seven gates and state rules never
tried. **The rejected four are all risk-management parameters. Not one of his
setups has been tested.**

## 8. What this opens

1. ~~**The regime gate.**~~ **Tested 2026-09-11 and not adoptable** —
   `ladder_and_regime_20260911.md` §4: hot − cold +$2.65/trade, permutation
   **p = 0.2964**, non-monotone (mixed is best). The same-day version has a
   monotone +$5.86 ceiling and is the remaining live question.
2. **Dip buying**, which is the largest genuinely untested thing in the source.
   Note `ladder_and_regime` §3 rejected the *inferred* dip entry (MFE/MAE 0.85 vs
   MCL's 0.97, and the signal fires **after** MCL's entry on 1,176 sessions vs 830
   before). **That is a rejection of the inference, not of dip buying** — the two
   videos stating the actual rule (`ORWJzImSTdE`, `hz7vhSIXXSc`) remain
   untranscribed and are the highest-value open source item.
3. **The hold-50% rule**, still the best entry-side item, with a home in
   `screen_at.py`.
4. `warrior_0` §5.3 and `warrior_1` §6 should record that the breakeven stop **and
   the partial** were tested and lost, and that the win-rate argument does not
   survive. See `win_rate_and_r.md` for why the win-rate argument was never going
   to survive.
5. **Re-run §4.1's target sweep on `bar_cache_xnas`** — the cheapest open item
   here (§4.1 status note).
