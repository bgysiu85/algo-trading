# The thin-tape pre-flight: volume separates strongly — and points the wrong way for a floor

**2026-09-19.** Under `docs/research/REGISTERED_thin_tape.md` (H-T1), committed `d7d134e`
before any code existed. 550 sessions, 6,411 symbol-days, 10,370 entries, 36 seconds.
Population exact (MCL 3,908). Every entry stamp landed on its engine's own grid — MC5's
6,456 five-minute entries and the 6 thin-name entries it trades unresampled alike.
Raw: `thin_tape_20260919.txt`, `var/reports/thin_tape_entries.csv`.

---

## 0. In one paragraph

**Absolute signal-bar volume separates the trades that die on the next bar — strongly on
MC5, AUC 0.681, clearing the registered 0.60 — and it separates them in the opposite
direction from the one a floor needs.** On MC5 the one-bar death rate *rises* with volume
across every one of the ten deciles, from **14.1%** on the thinnest bars to **59.5%** on the
thickest. The bars that looked like no market at all are MC5's *safest* entries on this
measure: at the live cut's own threshold of 2,000 shares, those 744 entries die on the next
bar **14.7%** of the time against the book's 37.3%. **A volume floor would refuse the trades
least likely to die instantly and keep the ones most likely to.** By the rule registered
before the numbers existed, no volume gate is registered — both books fail the
monotone-falling clause, and MC5 fails it as emphatically as it is possible to.

**But this does not say AEHL was fine, and §3 is why.** The backtest fills at the bar's close
plus a tick. It cannot see the thing that makes a thin bar expensive live — **the spread** —
because `ohlcv-1m` carries no quotes. AEHL filled at the ask on a 10.47% spread. So this
measures whether a thin bar predicts a bad *price path*, and the answer is no. It cannot
measure whether a thin bar predicts a bad *fill*, which is what actually cost the money. That
routes the whole question to the spread clause, now for a sharper reason than the one the
registration anticipated.

---

## 1. The separation

Against the one-bar label, the same one the Running Up pre-flight scored, so the numbers sit
directly beside its published ones (`ret_5m` 0.751 / 0.636).

| | AUC | median signal bar, dies next bar | median, survives | `rand` null | clock control |
|---|---:|---:|---:|---:|---:|
| **MCL** | **0.573** | 24,416 | 16,608 | 0.524 | 0.528 |
| **MC5** | **0.681** | **91,768** | 27,516 | 0.514 | 0.477 |

AUC above 0.500 means the trade that dies scores **higher**. **On MC5 the median dying trade
was entered on a signal bar carrying 3.3× the volume of the median survivor.** The null lands
where it should, and the clock does not separate — so this is not time of day in disguise.

Against H-R1's sharper population (one-bar exits that were the trailing stop firing),
reported and never scored, both books read stronger in the same direction: MCL **0.620**, MC5
**0.701**.

## 2. The shape — which is what actually decides anything

A floor is a threshold, and a threshold can only express a monotone relationship. So the
decile table is the reading the registration's rule turns on.

| decile | MCL volume (shares) | MCL one-bar | MC5 volume (shares) | MC5 one-bar |
|---|---:|---:|---:|---:|
| 1 | 0 – 2,940 | 8.2% | 0 – 1,626 | **14.1%** |
| 2 | 2,940 – 5,410 | 9.0% | 1,626 – 5,533 | 19.8% |
| 3 | 5,410 – 8,438 | 13.0% | 5,533 – 14,217 | 22.1% |
| 4 | 8,438 – 12,042 | 11.0% | 14,217 – 27,637 | 29.4% |
| 5 | 12,042 – 17,556 | 9.5% | 27,637 – 46,761 | 36.5% |
| 6 | 17,556 – 25,032 | 13.0% | 46,761 – 73,500 | 44.0% |
| 7 | 25,032 – 35,802 | 14.9% | 73,500 – 114,800 | 44.3% |
| 8 | 35,802 – 52,141 | 13.3% | 114,800 – 174,400 | 49.2% |
| 9 | 52,141 – 85,160 | 14.6% | 174,400 – 283,857 | 54.3% |
| 10 | 85,160 + | **19.4%** | 283,857 + | **59.5%** |

**MC5 is close to perfectly monotone — rising.** Every step up the volume ladder raises the
chance of dying on the next bar, from one in seven at the bottom to three in five at the top.
MCL is noisier and weaker, but the same way round: 8.2% at the bottom, 19.4% at the top.

**The registered rule, applied exactly:**

| | separation ≥ 0.10 | bottom five deciles fall | registers a gate? |
|---|---|---|---|
| MCL | 0.073 — **short** | `^^vv` — **no** | no |
| MC5 | 0.181 — **clears** | `^^^^` — **no, rises at every step** | no |

**No volume gate is registered.** MC5 clears the separation bar and fails the shape clause in
the most decisive way available: the relationship is real, strong and monotone, and it runs
backwards.

## 3. Why this does not mean AEHL was a good trade

This is the part that matters most, and it is a limit on what a backtest can see rather than
a finding about the market.

**The backtest fills a marketable entry at the signal bar's close plus one tick of slippage.
It has no quotes, so it has no spread, so it charges a 634-share bar exactly what it charges a
600,000-share one.** Live, the two are nothing alike. AEHL at 04:06 filled at the **ask**, on
a **10.47%** spread — a position roughly 5% under water the instant it opened, before the
price had moved at all. That cost is invisible here by construction.

So the pre-flight answers precisely one question: **does a thin signal bar predict a bad
price path afterwards?** And the answer is no — the opposite. It does **not** answer whether a
thin bar predicts a bad *fill*, and a bad fill is what the live table's under-2,000 bucket is
most likely showing: (17.87) a trade over 12 trades, on entries whose subsequent path the
backtest says is among the safest in the book.

**The two readings are consistent, and together they say where the money went.** The thin
bars are not the ones that die; they are the ones that cost too much to get into. That is a
**spread** problem, not a volume problem, and it is exactly the clause of
`handover_thin_tape_entries_20260918.md` §4(b) — the one that cannot be scored on these books
because they carry no quotes. The registration predicted this route; it did not predict that
volume would separate strongly on the way there.

## 4. The DAIC question, answered

Every MCL entry passed both of its relative volume clauses. How often did it do so on a bar
with almost nothing in it?

| | shares | MCL entries at or below |
|---|---:|---:|
| p1 | 810 | 40 |
| p5 | 1,706 | 196 |
| p10 | 2,940 | 391 |
| p25 | 6,784 | 977 |
| median | **17,556** | — |

DAIC's 2,037 shares sits at about the **sixth percentile** of MCL's entries. **"Three times
nothing" is routine, not a freak** — roughly one MCL entry in ten is on a bar thinner than
3,000 shares, having passed a rule that is supposed to require a volume surge. My second
registered prediction said this and it holds.

**But those entries are not where MCL's instant deaths live.** At 2,000 shares and below, 237
MCL entries die on the next bar **9.3%** of the time against the book's **12.6%**. The ratio
rule's blindness to an empty tape is real; on the price path, it has not been costing MCL
anything. Whether it has been costing it on the *fill* is §3's question again.

## 5. Scoring the predictions

- **"AUC lands between 0.52 and 0.60 on both books."** Right for MCL (0.573). **Wrong for
  MC5** (0.681) — it separates far more strongly than predicted.
- **"The decile shape is not monotone."** Right for MCL. **Wrong for MC5**, and wrong in an
  informative way: it is monotone, almost perfectly, in the wrong direction.
- **"So this closes the volume line and points at the spread clause."** Right, but not for
  the reason predicted. I expected *no signal*. What came back is *a strong signal pointing
  the other way*, which is a more decisive closing than the one I predicted.
- **The "interesting outcome" I named** — a monotone bottom half with AUC clearing 0.60 —
  **half happened.** MC5 did clear 0.60 and is monotone. It is monotone rising, which kills a
  floor rather than supporting one.
- **"Three times nothing is common rather than exceptional."** Right: about one MCL entry in
  ten is on a bar under 3,000 shares.

## 6. The thing this has in common with three other results, and it is one finding

This is the fourth measurement in two days that points at the same structure from a different
angle:

- **Running Up pre-flight** (09-18): MCL's dying trades were entered after a median **+11.43%**
  five-minute move against **+4.90%** for survivors. AUC 0.751, wrong way for a momentum gate.
- **H-P1, the chase gate** (09-18): **94.7%** of MC5's one-bar deaths are the trailing stop
  firing, at a median −5.23% against a stop at −5%. Stop-hits on volatile names.
- **H-R1, the rebound census** (09-18): after those stops fire, the further fall arrives
  before the recovery at every plausible amount of extra room. The stop is right to fire.
- **H-T1, this** (09-19): MC5's dying trades are entered on a signal bar carrying **3.3×**
  the survivors' volume, monotonically across the whole range.

**One reading covers all four.** These strategies buy into volatility spikes — the big move,
the big bar, the big volume — and a fixed 5% trail set at the top of a spike gets taken out
by the next bar's ordinary range. A high-volume five-minute bar is very often a wide-range
bar, and wide ranges cluster, so the bar after it is wide too. **The volume is not the cause;
it is another view of the same spike.**

**That is a direction worth recording and not a result worth chasing,** for the reason §7
gives.

## 7. What this does NOT license

**It does not license a volume CEILING**, however tempting the MC5 table looks. A ceiling —
"don't buy the climax bar" — is the mirror of a floor, and it would be a gate that refuses
high-volume entries. **H-P1 already ran that experiment on the price axis**: it refused the
trades that had just run, removed up to two thirds of the one-bar deaths, and paid **$0.29 a
trade** against a ±$1.70 random band, because the trades it refused lost $4.81–$7.89 where
the book lost $8.57 — the better half of a bad book. `vol_bar` is almost certainly strongly
correlated with the five-minute move H-P1 gated on, and this pre-flight did not measure that
correlation. **The prior on a volume ceiling is H-P1's result, and it is bad.** It would need
its own registration, with the correlation to `ret_5m` measured first, before anyone ran it.

**It does not license anything about MCL.** 0.573 is short of the bar and the shape is noise.

**It does not say thin bars are safe to trade live.** §3.

**And separation is not money.** Nothing here was priced, by design, and a feature that
separates can still refuse the better half of a bad book.

## 8. What changes

- **Handover options (a) and (c) — a volume floor inside MC5, or a minimum signal-bar volume
  gate in the trader — are closed on the backtest evidence.** At the live cut's own threshold,
  a floor refuses 744 MC5 entries that die less than half as often as the book.
- **Option (b), the spread gate, is now the only live route, and better motivated than
  before**: the reason thin bars hurt live is almost certainly the spread, which is the one
  quantity the backtest structurally cannot see. Its measurement problem stands — there are
  no quotes in `ohlcv-1m` — so it either waits on your MBP-1 entitlement being priced, or it
  ships as what it honestly is: a cost control refusing to cross a visible 10% toll, not an
  edge claim, on the same footing the drift guard shipped.
- **The four-result synthesis in §6 is the most useful thing here** for anything built next,
  including the 10-second strategy: an entry that waits for the spike to *happen* and then
  buys it is buying the bar most likely to be followed by another wide one.

## 9. What this is not

Nothing ships; `holdout.json` untouched. Not a gate and not a price on one. The **feature** is
knowable at entry; the **label** is not — the only honest form of the question, and the one
the Running Up pre-flight used. No P&L anywhere in the report, enforced by a test.

## Commands run

```
python -m common.thin_tape --jobs 8
```
