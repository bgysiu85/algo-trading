# Running Up: the features separate cleanly, and every one of them points the wrong way

2026-09-18. `common/running_up_preflight`, 550 sessions, 10,370 entries, 11.2
seconds. **Descriptive: no rule, no threshold, no verdict, no P&L.** Raw:
`running_up_preflight_20260918.txt`; features CSV beside it.

---

## 0. In one paragraph

The pre-flight asked whether any feature computable at the entry bar tells the
trades that die in one bar apart from the ones that survive. **It does — and
the direction is the opposite of the hypothesis.** On MCL, `ret_5m` reads
**AUC 0.751** against a null of 0.526; the trades that die were entered after a
**+11.43%** five-minute move, the survivors after **+4.90%**. Every momentum
feature on both books reads the same way. **A "Running Up" gate — enter only
when the name is climbing fast — would have kept a larger share of the
one-bar trades than of the survivors at every threshold.** The scanner, built
as specified, would have concentrated the losers rather than removed them.
What the data supports is the reverse filter: **don't chase.**

---

## 1. The separation, and why it can be believed

| | MCL AUC | MC5 AUC |
|---|---:|---:|
| `ret_5m` | **0.751** | **0.636** |
| `ret_3m` | 0.745 | 0.595 |
| `ret_1m` | 0.700 | 0.557 |
| `rvol_1m` | 0.642 | 0.596 |
| `rvol_5m` | 0.636 | 0.573 |
| `accel` | 0.632 | 0.511 |
| `pos_in_range` | 0.555 | 0.551 |
| `up_bars_5` | 0.546 | 0.558 |
| `dist_from_high` | 0.494 | 0.443 |
| **`minutes_since_0400` (control)** | 0.528 | 0.477 |
| **`rand` (control)** | 0.526 | 0.505 |

AUC above 0.500 means a **higher** value marks the trade that dies. Eight of
the nine momentum features read above 0.500 on both books.

**The two controls did their job, and that is what makes the reading
interpretable.** `rand` landed at 0.526 and 0.505 — that is the noise floor at
these sample sizes, and it is why 0.751 is a large number rather than a
suggestive one. And `minutes_since_0400` sat at 0.528 / 0.477, so **this is not
the time-of-day filter wearing a new name** — the closed question stays closed,
and the momentum features are not a clock in disguise.

The medians say it without any statistic at all:

| | median `ret_5m` at entry | median `ret_1m` | median `rvol_1m` |
|---|---:|---:|---:|
| MCL, died in one bar | **+11.43%** | +5.91% | 15.01 |
| MCL, survived | +4.90% | +2.61% | 8.40 |
| MC5, died in one bar | **+5.01%** | +1.03% | 2.26 |
| MC5, survived | +1.97% | +0.40% | 1.36 |

## 2. The gate, read as it would actually bind

This is the part that closes the hypothesis. A Running Up gate is
`feature >= cut` — take the trade only if the name is moving. Here is what
that keeps, on MCL:

| `ret_5m >= cut` | of the one-bar trades | of the survivors |
|---|---:|---:|
| 0.033 | 88.8% | 67.3% |
| 0.053 | 79.2% | 45.8% |
| **0.083** | **64.0%** | **25.1%** |
| 0.109 | 52.3% | 15.3% |

At every threshold it keeps **more** of the trades that die than of the ones
that live. A useless feature would keep the same share of both; this one is
worse than useless in the hypothesised direction. MC5's table runs the same
way, less steeply.

**Turned around, the same numbers are a real filter.** `ret_5m <= cut` — refuse
the entry when the name has already run:

| `ret_5m <= cut` | one-bar trades removed | survivors lost |
|---|---:|---:|
| MCL, 0.050 | **81%** | 49% |
| MCL, 0.083 | **64%** | 25% |
| MCL, 0.100 | 57% | 18% |
| MC5, 0.050 | 50% | 26% |
| MC5, 0.083 | 38% | 14% |
| MC5, 0.100 | 33% | 11% |

MCL separates far more sharply; MC5 is where the money is. Neither of these is
a result — no P&L has been computed and none belongs in a pre-flight — but the
trade-off is favourable enough on both books to be worth a registration.

## 2b. Monotone on MCL, but MC5 is U-shaped — and that part of the idea survives

Everything above reads the upper tail. Asked for the whole shape — the one-bar
**rate** by decile of the feature, which is descriptive and involves no
threshold — the two books answer differently, and MC5's answer is not what §2
implies.

| decile of `ret_5m` | range | MCL one-bar rate | MC5 one-bar rate |
|---|---|---:|---:|
| 1 | most negative | **4.6%** | **41.3%** |
| 2 | | 4.4% | 24.6% |
| 3 | | 5.1% | **21.9%** |
| 4 | | 5.1% | 22.8% |
| 5 | | 6.9% | 24.9% |
| 6 | | 6.9% | 32.2% |
| 7 | | 12.3% | 34.7% |
| 8 | | 14.6% | 44.8% |
| 9 | | 23.6% | 54.8% |
| 10 | most extended | **42.3%** | **70.2%** |
| | *base rate* | *12.6%* | *37.2%* |

**MCL is monotone.** The safest entries are the least extended ones, all the
way down to a negative five-minute return. There is no band; more momentum is
worse everywhere.

**MC5 is U-shaped, and the left arm is real.** Its bottom decile — entries
taken while the name was falling, `ret_5m` between −45% and −1.8% — dies
**41.3%** of the time, *above* the 37.2% base. The floor of the U sits in
deciles 2–5, roughly **−1.8% to +2.7%** over five minutes, at 21.9–24.9%.

So a piece of the original intuition does survive, on MC5, in a much weaker
form than "running up": **don't buy while the name is dropping.** That is a
falling-knife condition, and it is worth about four percentage points against
the base rate. The thing at the other end is worth thirty-three. The dominant
structure is a **ceiling**, not a floor — and on MCL there is no floor at all.

`rvol_5m` adds nothing on MC5 (29–40% flat across nine deciles, then 55.8% in
the tenth) and is monotonically bad on MCL (4.4% to 25.4%). The volume burst is
not the useful half of the concept in either book.

## 3. The shape of the trade that dies

Two features together describe it. The dying trades have a **high recent run**
and, on MC5, sit **further below the session high** than the survivors
(−12.09% against −10.01%). That is a sharp bounce in a name that is well off
its high — not a grind into new highs.

**Ben's own scanner capture shows exactly this pattern in the wild.** DLXY was
down 49.78% on the gap and 52% from the close, and fired "Running Up" alerts
thirteen times over thirty-five minutes while bouncing between $1.10 and $1.29.
The Running Up scanner is direction-agnostic about the day by design — measured
observation, in `running_up_scanner_observed_20260918.txt` — so it surfaces
precisely the bounce-in-a-downtrend setup that this pre-flight says kills MCL
and MC5 trades.

## 4. The leading alternative explanation, which is mechanical and matters more

A name that has just moved 11% in five minutes is **more volatile**, and the 5%
trail is a fixed percentage. The next bar's ordinary range is larger, so the
trail is more likely to be hit by noise rather than by a real reversal. On that
reading the one-bar deaths are not bad entries at all — **they are a stop that
is too tight for the volatility at the moment of entry.**

The two readings predict the same separation and are not distinguishable from
this pass. They point at different fixes, and the second one is cheaper and
does not throw trades away:

- **entry gate** — refuse the chase, take fewer trades;
- **volatility-scaled trail** — take the same trades, widen the stop in
  proportion to recent range.

`PROGRAM_INDEX` §4 says a rule should be read back as a measurement. The
measurement that separates these two is whether the one-bar exits cluster at
the trail level rather than below it, and whether the same entries survive a
wider trail. That is one registration and it does not need the tape twice.

## 5. What this does and does not license

**It closes the Running Up scanner as an entry filter in its hypothesised
form.** Not "no effect" — the wrong sign, cleanly, on both books, with the
controls behaving. Building the scanner to select for acceleration would have
concentrated the trades that die. That holds for the gate used **as an aide
alongside the existing entry conditions**, which is the only way it was ever
measured: every entry read here had already satisfied MCL's or MC5's own rules,
so ANDing a Running Up condition onto them can only remove entries the strategy
already wanted — and §2's table says it removes the survivors faster.

**Why it works for the trader it came from.** The scanner's job in a discretionary
workflow is *discovery* — it says a name is in play. The entry is then a separate
decision, and the micro-pullback discipline exists precisely to avoid buying the
extension. Using the alert itself as the entry trigger collapses the two steps
into one and buys the extension. In this project discovery is already done by the
screener, so the scanner adds nothing at that stage and hurts at the other.

**What is still live, and untested:** the same idea as a SESSION-level flag
rather than an entry-bar condition — *has this name had a running-up episode
today at all* — which is a different feature from *is it running up at this
instant*, and nothing here measures it.

**It does not establish that the reverse filter makes money.** There is no P&L
in this report by design. A "don't chase" gate has to be registered with its
threshold taken from the distributions printed here, then scored against
`gate_study.abstention`, the friction margin and the symbol-cluster bootstrap,
exactly like H-B1, H-B3 and H-B4 — all three of which read as random removal.
The trade-off above looks better than any of those did, which is a reason to
register it and not a reason to believe it.

**And the ceiling from the sizing pass still stands.** Even a perfect filter on
MC5's one-bar problem leaves +$0.70 a trade at $8.92.

## 6. What this is not

Not out of sample — `holdout.json` untouched. Not a rule: nothing here has a
threshold, and the thresholds quoted in §2 are the printed deciles, used to
describe the trade-off rather than chosen. Not Warrior's scanner: their
baseline is prior sessions at the same time of day and this one is the
session's own median, so no number here is comparable to their screen. Not
minute-faithful: their alerts fire seconds apart, so this reads a 1-minute
approximation of a tick-level signal. And the entries are already
momentum-selected by MCL and MC5's own rules, so what is measured is variation
*within* a momentum-filtered population, not against the market at large.

## Commands run

```
python -m common.running_up_preflight --jobs 8
```
