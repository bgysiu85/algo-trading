# VW9 salvage — a tighter entry filter cannot work, and the exit was never tested

**Research chat, 2026-09-17. Read-only: no program logic touched.**
Source: `var/reports/screened/backtest_trades_vw9_5m.csv` — 1,527 trades, 724
symbols, 459 sessions. Raw report:
`D:\Trading\Claude outputs\vw9_salvage_20260917.txt`.

Ben asked whether VW9 could be salvaged by **(a)** adding a volume requirement
at entry and **(b)** replacing the exit with a trailing stop. Answering it
required opening the trade list rather than the docs, and that surfaced a
correction.

> **(a) No, and it is arithmetic rather than judgement.** A filter uncorrelated
> with outcome cannot flip a negative at any strength, and both volume filters
> this project has measured were uncorrelated or worse.
>
> **(b) Untested — and I said otherwise earlier today.** The screened-universe
> run is `fixed_2r` on **all 1,527 trades**. `trail_atr` won on the old
> 374-pair hindsight set and **was never re-run after the universe was fixed.**

---

## 1. The correction

An earlier answer in this chat stated that the trailing stop "is already the
configuration." That is true of the archived 374-pair run and **false of the
screened run that produces the current standing rejection**:

```
exit_mode:  fixed_2r  x 1527   (every trade)
```

Recorded because the error is the recurring shape in this project — a figure
quoted from one run applied to another that shares its name.

---

## 2. What the screened run actually contains

| exit reason | n | share |
|---|---:|---:|
| **vwap_lost** | **917** | **60.0%** |
| stop | 284 | 18.6% |
| target_2r | 265 | 17.4% |
| session_close | 61 | 4.0% |

| arm | n | net | /trade | win% |
|---|---:|---:|---:|---:|
| PRE | 188 | (1,628) | (8.66) | 17.6% |
| RTH | 1,313 | (5,543) | (4.22) | 23.2% |
| POST | 26 | (462) | (17.76) | 15.4% |
| setup A | 1,120 | (5,511) | (4.92) | 18.7% |
| setup B | 407 | (2,123) | (5.22) | 32.4% |

**Total (7,633). 211 of 724 symbols profitable (29.1%). drop-top-3 (10,552),
drop-top-5 (12,084).** Top five: SQFT +1,158, ARTL +905, PTIX +855, AMIX +818,
WYHG +714.

**Two things here contradict the archived write-ups and should be carried
forward.**

1. **The pre-market concentration is gone.** The archived run had PRE at
   **+$10,262** and RTH at **−$1,257**; here RTH is **86% of trades** and every
   block loses. The "all the profit is pre-market, where fills are fiction"
   diagnosis was true of the hindsight pair set and is **not** true of this one.
2. **It is no longer two names.** WLDS and PLYX are absent; the top five are
   small and the book is broadly negative. The failure mode changed shape when
   the universe got more honest — and got worse, not better.

3. **Setup B has a higher win rate than A (32.4% vs 18.7%) and a worse
   per-trade figure** ((5.22) vs (4.92)). Consistent with the archived Setup-B
   decision, from a different direction.

---

## 3. The required-precision test — the general result

An entry filter **removes trades**. Let `p_w` be the fraction of winner dollars
it removes and `p_l` the fraction of loser dollars, within the pool that
drop-top-N is scored on. To bring that pool to non-negative:

```
p_l·|L| − p_w·W  ≥  |L| − W
```

VW9's non-top-3 pool: **W = +36,540**, **|L| = 47,092**, gap **10,552**;
333 winners against 1,182 losers (22.0% win rate).

> **A filter uncorrelated with outcome has `p_w = p_l = f`, so the pool becomes
> `(W+L)·(1−f)` — a negative number scaled toward zero. It never crosses.**
> **No such filter works at any strength.** Selectivity `s = p_l / p_w` must
> strictly exceed 1, and the closer to 1 it sits the more of the book it has to
> destroy.

| selectivity `s` | winner $ removed | loser $ removed |
|---:|---:|---:|
| 1.10 | 69.1% | 76.1% |
| 1.25 | 47.3% | 59.1% |
| 1.50 | 30.9% | 46.4% |
| **2.00** | **18.3%** | **36.6%** |
| 3.00 | 10.1% | 30.2% |
| 5.00 | 5.3% | 26.5% |
| ∞ (perfect) | 0.0% | **22.4%** |

**This construction generalises.** Any strategy in this project that fails
drop-top-N can be asked the same question before a filter is designed for it:
*how selective would the filter have to be, and is that within the range of
anything we have ever measured?* It is four lines of arithmetic off an existing
trade list.

---

## 4. What volume filters actually measure here

Two have been measured, and the selectivity of each is known:

| filter | result | implied `s` |
|---|---|---:|
| **Dollar-volume floors $5k–$1M on MCL** (`entry_margins_result_20260914.md`) | **removed trades lose the same as kept** — (7.85)–(9.89) against a (9.16) book; halves disagree in direction | **≈ 1.0** |
| **6,000-share volume floor** (earlier) | removed ~**$872 of winners** against ~**$115 of losers** | **≈ 0.13** |

One is uncorrelated. The other is **actively inverted** — it removed winners
seven times faster than losers. Against a requirement of `s > 1` and a
practical need for `s ≥ 2`, neither is close.

VW9's own pre-flight said the same from the other side: §8.2 found the
dollar-volume floor **"nearly inert"**, §8.4 found the gates **"barely
binding."** The gate Ben proposes already exists in the spec
(`MIN_TRIGGER_DV_PER_MIN`, plus Setup B's pullback-volume test) and was
measured as doing almost nothing.

**Verdict on (a): no.** Not "unlikely" — the uncorrelated case is closed in
arithmetic, and the two measured instances sit at or below it.

---

## 5. The exit lever, sized honestly

Only **265 of 1,527 trades (17.4%) exit at the 2R target** — those are the only
ones a trail can extend. **917 (60.0%) exit on `vwap_lost`**, which preempts
both target and trail. Closing a (10,552) gap across 265 trades needs roughly
**$40 per trade** on trades already exiting at 2R.

> **And the archived "best cell" was `trail_atr` with the VWAP exit switched
> OFF.** That is two changes, and the second disables the rule the spec calls
> *"the rule the whole strategy rests on."* **A configuration that only looks
> good with its defining rule turned off is not that strategy**, and the old
> +$9,004 headline should be read with that attached.

**Verdict on (b): one legitimate registered run**, because it genuinely has
never been done on an honest universe — `--exit-mode trail_atr` against the
`fixed_2r` baseline, **VWAP exit left ON**, as a delta with drop-top-N on the
delta. A VWAP-off variant is a second cell and should be named as a different
strategy, not as VW9.

---

## 6. Standing

**VW9 is closed** (`archive/vw9_setup_b_decision.md`) and its break-even
friction on this universe is **−$0.70/RT** — negative, meaning it loses at zero
cost. It is not a friction problem and not a filter problem.

The archived closing note said reopening needs *"a universe that is not
hindsight-selected"* and *"measured pre-market fills."* Both have since moved —
but the screened universe is **already less hindsight-selected than the 374
pairs, and the result is worse there**, which is evidence the concentration was
not purely selection bias.

**Recommendation: do not reopen for the filter.** The single trail run is
cheap and defensible if a slot is free, but it competes with MA-TREND's free
pre-check and the ORB joint grid, and reopening a formally closed strategy on a
parameter change is the exact shape `orb_strategy_spec.md` §11 names as how the
scale-out exit survived four studies before the fill audit killed it.
