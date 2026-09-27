# The chase gate: the mechanism works perfectly, pays nothing, and points somewhere else

2026-09-18. Under `docs/research/REGISTERED_chase_gate.md` (H-P1), committed
before any code existed. 550 sessions, 6,411 symbol-days, fifteen books, 181
seconds. Population check and the solve's population both match exactly — MCL
3,908, MC5 6,462. Raw: `chase_gate_20260918.txt`.

---

## 0. In one paragraph

**Nothing clears.** Ten scored cells: three NOTHING and seven REFUSED, every
per-trade delta inside random removal's band, and most of them negative. But the
run is worth more than its verdict, because two things it was required to print
turned out to matter more than the thing it was testing. **The gate does exactly
what it claims** — it removes up to 63% of the trades that die on the next bar,
monotonically, on both books — and that buys **+$0.29 a trade at best**. And the
block declared *reported and never scored* before the run says why the whole
line may have been aimed at the wrong thing: **94% of MC5's one-bar deaths are
the trailing stop firing, filling at a median −5.24% against a stop set at −5%.**
They are not bad entries being punished. They are a fixed stop being hit.

---

## 1. The sweep

Per trade at $4.26, against each book's published base.

| cell | trades | removed | per trade | per s-day | 1-bar share | verdict |
|---|---:|---:|---:|---:|---:|---|
| **MCL (base)** | 3,908 | — | (8.97) | (5.47) | 12.6% | — |
| MCL ret≤0.033 | 1,265 | 2,643 | (8.68) | (1.71) | **4.7%** | NOTHING |
| MCL ret≤0.050 | 1,886 | 2,022 | (9.32) | (2.74) | 5.2% | REFUSED |
| MCL ret≤0.083 | 2,748 | 1,160 | (9.52) | (4.08) | 6.5% | REFUSED |
| MCL ret≤0.100 | 3,013 | 895 | (9.54) | (4.48) | 7.1% | REFUSED |
| MCL ret≤0.150 | 3,470 | 438 | (8.78) | (4.75) | 9.1% | NOTHING |
| **MC5 (base)** | 6,462 | — | (8.57) | (8.64) | 37.3% | — |
| MC5 ret≤0.033 | 4,065 | 2,397 | (8.97) | (5.69) | **28.8%** | REFUSED |
| MC5 ret≤0.050 | 4,637 | 1,825 | (9.24) | (6.69) | 30.2% | REFUSED |
| MC5 ret≤0.083 | 5,259 | 1,203 | (9.20) | (7.55) | 31.7% | REFUSED |
| MC5 ret≤0.100 | 5,448 | 1,014 | (9.27) | (7.88) | 32.5% | REFUSED |
| MC5 ret≤0.150 | 5,815 | 647 | (9.56) | (8.68) | 33.8% | NOTHING |

Seven REFUSED, and always for the same reason: **per trade gets worse while per
symbol-day gets better.** That is the denominator rule doing its job, and this
time the disagreement has a clean explanation — see §3.

## 2. The mechanism operated, completely, and was worth nothing

§7 required every cell to print its one-bar share, so that "removes the trades
that chase" could be measured rather than asserted. It is the cleanest mechanism
reading this project has produced.

**Every cell lowered it, monotonically, on both books.** MCL 12.6% → 9.1 → 7.1 →
6.5 → 5.2 → **4.7%**. MC5 37.3% → 33.8 → 32.5 → 31.7 → 30.2 → **28.8%**. The
tightest MCL cell cuts the one-bar death rate to **a third** of the base.

And the best per-trade result anywhere in the ten is **+$0.29**, against a random
removal band of ±$1.70.

That is the finding, stated plainly: **you can remove two thirds of the trades
that die immediately and it does not move the money.** The pre-flight's
separation was real — AUC 0.751 is not noise, and the gate converts it into
exactly the trade population it promised — and converting it changes nothing.

## 3. Why: the chase trades lose money, but they lose LESS than average

The marginal trade explains the whole table, as it did in the entry sweep this
morning.

| cell | refused | what each refused trade was worth |
|---|---:|---:|
| MCL ret≤0.083 | 1,160 | (7.68) |
| MCL ret≤0.100 | 895 | (7.07) |
| MC5 ret≤0.083 | 1,203 | (5.81) |
| MC5 ret≤0.100 | 1,014 | **(4.81)** |
| MC5 ret≤0.033 | 2,397 | (7.89) |

Every refused trade is a loser. **But the books average (8.97) and (8.57), and
these losers lose four to eight dollars.** Refusing a trade that loses $4.81 from
a book that loses $8.57 a trade makes the per-trade figure *worse* — MC5-c100
lands at (9.27) — while the total improves simply because there are fewer trades.

That is the denominator disagreement in one sentence: **the chase trades are the
better half of a bad book.** The gate concentrates the book into what remains.

## 4. The second condition, and it inverted my prediction

§4 registered the expectation that `dist_from_high` adds nothing, because it
separates almost nothing on the one-bar outcome — AUC 0.494 on MCL and 0.443 on
MC5, against a `rand` control at 0.526 / 0.505. So it was tested **instead of**
the ceiling at a matched abstention budget, never on top of it.

At the same budget it is **better on both books**, and on MC5 the budgets match
to the trade:

| at a matched budget | removed | per trade | vs random p95 |
|---|---:|---:|---:|
| MCL ret≤0.083 | 1,160 | (0.55) | +0.75 |
| **MCL dist ≥ −0.1594** | 1,118 | **+0.92** | +0.68 — **beats it** |
| MC5 ret≤0.083 | **1,203** | (0.63) | +0.65 |
| **MC5 dist ≥ −0.1993** | **1,203** | **+0.59** | +0.65 — just inside |

Same abstention budget, opposite sign, by about **$1.25 a trade on both books**.
MCL's distance rule is the **only cell in the entire study to beat its own
abstention control**, with a session bootstrap of 1.000.

Two things keep this honest. **It is reported and never scored** — declared so
before the run, so it cannot be promoted now however it reads. And it still
fails: +0.92 is far short of the $4.26 friction margin, and the halves disagree.

But the direction is informative and it is not what I predicted. The two
features are selecting on **different things**: `dist_from_high` barely moves the
one-bar share (−0.5pp on MCL) while moving money more than the ceiling does. A
feature can fail to predict *instant death* and still predict *P&L*. The
pre-flight saw the shape — dying trades sit further below their session high, a
bounce in a downtrend — and scored it on the wrong outcome.

## 5. The block that matters most, which this study was not testing

§5.2, reported and never scored, fenced off before the numbers existed.

| | one-bar trades | trailing-stop exits | median exit | within 0.5pp of the stop | more than 0.5pp below |
|---|---:|---:|---:|---:|---:|
| MCL | 492 | **82.5%** | −5.19% | **81.9%** | 0.6% |
| MC5 | 2,412 | **94.7%** | −5.23% | **93.8%** | 1.0% |

**The one-bar deaths are the trailing stop firing.** They fill essentially at the
stop — median −5.24% against a stop at −5%, worse than −6% in 0.5–0.7% of cases,
worst case −7.17% on MCL. They are not gap-downs and not reversals running away.

That is the pre-flight's §4 alternative explanation, and it now has 2,904
observations behind it: a name that has just run 11% in five minutes is more
volatile, the trail is a **fixed** percentage, and the next bar's ordinary range
is wide enough to take it out. On that reading the entry was never the problem —
**the stop was too tight for the volatility at the moment of entry**, and this
study has been trying to fix a symptom by refusing the trades.

**What this does NOT establish**, and the distinction decides what to do next: it
shows the losses are stop-hits rather than gaps. It says **nothing** about
whether a wider stop would have helped, because what the price did *after* the
stop is not measured anywhere in this run. A wider stop converts a −5% loss into
either a recovery or a bigger loss, and which one dominates is exactly Ben's own
question from 2026-09-17 — *how often does a position drop below entry and come
back?* — still unrun.

## 6. Scoring my predictions

- **MCL clears the abstention band at 0.083 or 0.100 and still reads REFUSED.**
  Half right. Both read REFUSED, and for the reason predicted — per symbol-day up,
  per trade down. But they did not clear the band: they are **negative** per
  trade, (0.55) and (0.57), against p95s of +0.75 and +0.59.
- **MC5 is the one I would bet on for a per-trade pass**, because its one-bar
  trades lose (31.95) each and are 139% of net. **Wrong, and instructively.**
  Removing those trades made MC5's per-trade figure worse in all five cells. The
  arithmetic that looked compelling — big losers, remove them — fails because the
  removed trades are less bad than what remains.
- **"Near the session high" adds nothing.** Wrong; it adds more than the thing it
  was compared against, on both books (§4).
- **The prior from H-B1, H-B3 and H-B4 is bad.** Right, and it held: a fourth
  entry gate, with a real measured mechanism, reads as random removal.

## 7. What this closes and what it opens

**The "don't chase" entry gate is closed.** Not for want of a mechanism — the
mechanism is the strongest this project has measured and it operated in every
cell — but because the trades it refuses are the better half of a losing book.
Taken with H-E2 this morning, both directions on the entry are now read on the
tape of record: **adding trades does not select, removing them does not select.**

**Two things open, and they are ordered.**

1. **The rebound study, Ben's, asked for 2026-09-17 and now load-bearing.** §5.2
   says the deaths are stop-hits; only the rebound study can say whether a wider
   or volatility-scaled stop recovers them or deepens them. It is answerable off
   the existing trades CSV plus the tape, needs no new data, and it now gates a
   registration rather than being a curiosity.
2. **`dist_from_high` as an entry feature, on its own registration.** It beat the
   ceiling at a matched budget on both books and beat random removal on MCL. That
   is a direction, not a result — and it must be registered before it is run
   again, because everything in §4 was fenced as never-scored precisely so that a
   good-looking number could not be promoted after the fact.

**Neither reopens MCL or MC5.** The sizing ceiling stands: even a perfect filter
on MC5's one-bar problem leaves **+$0.70 a trade at $8.92**, and break-even
friction is negative on both books.

## 8. What this is not

Nothing ships; `holdout.json` untouched. Not live — `entry_gate` is a backtest
parameter and a test asserts it never appears in `evaluate_last_bar`'s signature.
Not a search: five values per family, every one printed by the pre-flight on a
pass that could not see a P&L, and the comparator solved against a removal count
rather than chosen. And §4 and §5.2 are **reported and never scored**, declared
before the run — which is the only reason the two most interesting numbers here
can be believed at all.

## Commands run

```
python -m common.chase_gate --jobs 8
```
