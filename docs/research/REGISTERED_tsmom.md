# REGISTERED — TSMOM: time-series momentum on CME futures, monthly

**Committed before any backtest code exists and before any futures data is
bought.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run, and
the commit hash is the timestamp.

Spec: `claude/tsmom_spec_20260917.md`. Handover: `claude/handover_tsmom_20260917.md`.
Evidence context: `claude/diversifier_candidates_20260911.md` §4 and §5.1.
Source: Moskowitz, Ooi & Pedersen, *JFE* 104 (2012) 228–250.

Amendments are marked **PRE-RUN** or **POST-RUN**. A threshold changed after
seeing a result is a new hypothesis and spends from the budget in §9.

---

## 0. PRE-RUN GATES — none of this runs until all four are cleared

A gate is not a caveat. If a gate is open, the run does not start.

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | ~~The paper is read off the page.~~ **CLEARED 2026-09-17.** Ben allowlisted `pages.stern.nyu.edu` and `w4.stern.nyu.edu`; the PDF was downloaded and all five ★ lines verified. | Spec §0. **And the gate earned its place:** the fetch tool had hedged the skip question into an open [D] decision, and the page settles it — footnote 10's skip convention is the *cross-sectional* factor's, and the same footnote disclaims the sensitivity. See spec §0.1. |
| **G2** | ~~Ben has seen the data cost and said yes.~~ **CLEARED 2026-09-18**, at the measured **$3.65** (§0.1). | `PROGRAM_INDEX` §1: a tool that can spend money states the number before it spends it. The pull is registered separately at `docs/research/REGISTERED_tsmom_fetch.md`. |
| **G3** | ~~Ben has chosen the rates arm — (a) ZN, (b) MTN, or (c) none — spec §2.3.~~ **CLEARED 2026-09-19: (b) MTN.** Ben, in his words: *"let's go with option b then"*, chosen after the three arms were explained and **before any return was computed**. MTN is the arm that would be traded; the run still reports all three side by side and unranked (§4 item 13), and the choice does not move with them. Consequence: arm (b)'s signal comes from **TN**'s own history (spec §2.3), which the 2026-09-18 pull did **not** buy — TN bars and roll calendar join the AT-99 top-up, priced before anything is spent. TN lists from 2016, so arm (b) has a shorter history than the other markets and is read that way. | Choosing it from the backtest's ranking is a one-family search dressed as a decision. It is a margin question and a preference, and it is his. |
| **G4** | ~~The holdout is cut and enforced in code before the first run.~~ **CLEARED 2026-09-18.** `common/tsmom_holdout.py`, `tests/strategy/test_tsmom_holdout.py`, ten mutations run and ten caught. | `PROGRAM_INDEX` §1. The equity `holdout.json` does not cover this and is refused **by name**; TSMOM cuts its own. See §6.1 for the defect its own test found. |

**G1 is the one most likely to be waved through, so it is stated hardest.**
Reading the spec's §1 back as "close enough" is how a project ends up having
measured a strategy adjacent to the one it cited.

---

## 0.1 Amendment A — PRE-RUN, 2026-09-17: how the registered data is fetched

**Registered before any data was bought and before any backtest code exists.
It changes no rule, no threshold and no number the strategy computes** — only
the scope of the request that fetches the same inputs.

**What happened.** The first whole-set estimate came back **29.030 GiB /
$71.62** and `--max-cost` aborted. Ben offered to pay it. The diagnostic
(`--diagnose`, free metadata lookups) attributed it:

| | GiB | USD | implied rate |
|---|---:|---:|---|
| `ohlcv-1d`, `parent` | 0.111 | **21.10** | ~$191/GiB |
| `definition`, `parent` | 28.919 | **50.52** | ~$1.75/GiB |

- **The bars were not buying spreads.** `parent` vs `continuous` on ES is
  **3.0×**, not the hundreds that would indicate spread resolution. It was
  buying the **deferred contract months** — CL and NG list out ~9 years — that a
  front-month strategy never holds.
- **`definition` is 70% of the bill** because it is republished for **every
  listed instrument every session**, while the expiration dates it carries are
  **static per contract**. Sixteen years of daily snapshots to learn when ESH14
  expired is the same fact bought four thousand times.

**The amendment.** `--scope lean` becomes the default and is what gets bought:

1. **Bars from `continuous` `<ROOT>.c.0` and `.c.1`** — the front contract and,
   for the five sessions before its expiry, the next one. That is the complete
   set the registered roll rule ever holds. These resolve to **real
   instruments**, so §7's "P/L on the actual held contract" is unaffected; a
   synthetic series is still used for the signal only.
2. **The roll calendar from `definition` on a monthly grid** (~190 sessions).
   A contract is listed months to years before expiry and stays listed, so a
   monthly grid catches every contract with its expiration date long before the
   roll needs it.

**Estimated at ~$4 against $71.62**, for the same inputs.

### The measured figure, 2026-09-17

`common/tsmom_data_price.py --scope lean`, run on Ben's machine.
Raw output: `claude/raw/tsmom_price_20260917.txt`.

| | billable | USD |
|---|---:|---:|
| `ohlcv-1d` | 6,254,416 | **1.11** |
| `definition` | 1,605,203,600 | **2.54** |
| **TOTAL** | **1,611,458,016** (1.501 GiB) | **3.65** |

**$3.65 against $71.62 — a 95% reduction, for the identical inputs.** The
estimate of ~$4 was made before the run and is recorded above unedited.

- **Dataset range confirmed: 2010-06-06 .. 2026-09-17.** §1.1's "mid-2010" is
  right, and §6's holdout leaves **11.6 years in-sample** (2010-06 .. 2021-12).
- **The definition figure is a per-session cost multiplied by 190.** The per-day
  cost is exact; the sample count is the assumption, and the report says so.
- **NG and CL are 51% of the bill** ($1.06 and $0.79) and 65% of the bytes.
  Their `definition` is ~3.2 MB and ~2.3 MB *per session*, against ES's 36 kB —
  roughly a hundredfold, which is the deferred-month and spread listing depth
  of the two energy roots. That is why 13 roots did not cost 13× ES.
- **ZN's definition rounds to $0.00.**

**G2 is answered but not self-cleared.** Ben's "I'm ok to pay it" was said of
$71.62 and conditioned on the data being genuinely useful, which at that scope
it was not. $3.65 is 5% of that figure, so his standing consent covers it a
fortiori — but the gate says *he* says yes, and a gate that clears itself on a
technicality is not a gate.

**And the sampling gains a control rather than costing one.** Databento's
`c.0` changes instrument at expiry, so the **symbol-change dates in the bars are
a second, independent reading of the roll calendar**. The run asserts the two
agree and **refuses to proceed on disagreement** — `PROGRAM_INDEX` §4, "measure
on a second source before stating a conclusion, not after". The full-history
`parent` pull would have had one source.

**What is NOT amended:** the roll rule (front month, 5 trading days before
expiry, read from `definition` and never inferred from volume or open
interest), the instrument set, the friction levels, the holdout, and every pass
criterion of §4.

**`--scope full` remains available** and is what a later question about
deferred months or the term structure would use. It is not the default, because
$71.62 of data the strategy does not read is a slower pull, a larger archive and
a worse re-read forever.

## 0.2 Amendment C — PRE-RUN, 2026-09-19: which contract is held (AT-99)

**Why.** Reading the bought bars back (`REGISTERED_tsmom_fetch.md` §1.6, before any
return was computed) showed the registered roll rule — *front month, rolled five
trading days before expiry* — does two things the paper does not do:

1. **In the metals it holds contracts nobody trades.** "Front month" by expiry is
   often a serial month outside the liquid cycle. Median daily volume, front vs
   next contract: GC 54 vs 1,874, SI 18 vs 353, HG 66 vs 354; the front contract
   printed no bar at all on 630, 1,234 and 559 sessions. The paper holds "the most
   liquid futures contract (typically the nearest or next nearest-to-delivery
   contract)" (MOP p. 230).
2. **In physically delivered contracts it holds into the delivery month.** GC, SI
   and HG deliver on "any business day beginning on the first business day of the
   delivery month" and stop trading on "the third last business day of the
   delivery month" [CME fact cards]. ZN and TN deliver during the delivery month
   and stop trading on the "seventh business day preceding the last business day
   of the delivery month" [CME]. Five sessions before *last trade* is therefore
   two to three weeks *inside* the delivery period — past first notice day, where
   a broker forces the position out and the liquidity has already rolled.

**What is amended — spec §4 rule 1, for five roots only:**

> For **GC, SI, HG, ZN and TN**, the held contract is the **nearest contract in the
> root's active cycle whose delivery month has not begun**, rolled **five trading
> days before the first business day of its delivery month**.

| Root | Active cycle (held months) | Source |
|---|---|---|
| GC | Feb, Apr, Jun, Aug, Oct, Dec | CME gold fact card: the months listed beyond the near three (Feb/Apr/Aug/Oct over 23 months, Jun/Dec over 72) |
| SI | Mar, May, Jul, Sep, Dec | the market's standard active cycle. CME's card also lists Jan within 23 months; **Jan is not held** (see below) |
| HG | Mar, May, Jul, Sep, Dec | CME/broker spec: "active contract months are March, May, July, September, and December" |
| ZN, TN | Mar, Jun, Sep, Dec | quarterly; the only months listed |

**Unchanged for ES, RTY, CL, NG, 6A, 6B, 6E, 6J:** front month, five trading days
before expiry. Each is either cash-settled (ES, RTY), stops trading before its
delivery month (CL, NG), or delivers after last trade (the FX contracts), so the
registered rule never holds them into delivery. **MTN** (the traded instrument
for arm (b), G3) is cash-settled and needs no change; its **signal** comes from
TN, rolled by the rule above.

**What this is NOT.** It is **not** "hold the contract with the most volume" —
the registration forbids inferring the roll from volume or open interest,
because both are outcomes, and that is not amended. Every cycle above is a
**fixed published calendar**, known before any data, identical in every year.
The one judgement is **SI's January**: CME lists it, but the cycle registered is
the conventional five-month one. Fixed here, before any return is seen, and
**not** revisited on results. The run reports, as a diagnostic that selects
nothing, the held contract's share of root volume on each roll date, so a
cycle that is wrong shows up as a number rather than as a surprise.

**What it costs in data.** In the metals, the held contract is often the third,
fourth or fifth nearest (for HG in late August, December is `c.4`), so
`c.0`/`c.1` do not carry it. **ZN and TN** roll into the next quarter while it is
still `c.1`, so they are covered. The top-up (AT-99 steps 2–4) therefore buys:
**all-contract daily bars (`parent`) for GC, SI and HG**; **TN** daily bars and
roll calendar (arm (b)'s signal, G3); **MTN** daily bars for 2024-03-25 onward;
and the **April–September 2026 `definition` samples** the 190-sample cap dropped
(fetch §1.6 (a)). Priced before anything is spent, under the registered rule
that nothing is bought until Ben confirms the figure.

**What is NOT amended:** the instrument set, the signal, the sizing, the friction
levels, the holdout, the multiplicity budget and every pass criterion of §4. The
roll cross-check (AT-41) still compares `definition` expiries against the `c.0`
symbol-change dates; that check validates the **calendar data**, which this
amendment does not touch, not the choice of held contract.

Sources: [CME gold fact card](https://www.cmegroup.com/market-regulation/files/gold-futures-and-options-fact-card.pdf) ·
[CME silver fact card](https://www.cmegroup.com/trading/metals/files/fact-card-silver-futures-options.pdf) ·
[HG specification](https://help.metrotrade.com/kb/copper-futures-hg-contract-specifications) ·
[CME Ultra 10-Year T-Note futures](https://www.cmegroup.com/education/articles-and-reports/ultra-10-year-us-treasury-note-futures.html) (listed 2016-01-11; physical delivery; last trade seventh business day before the last business day of the delivery month).

---

## 1. The hypothesis, in one sentence

**A monthly, volatility-scaled, long/short time-series momentum book across
eleven or twelve CME futures markets has a positive expected return after
measured costs, over the GLBX.MDP3 daily history, on a sample that is entirely
out of the paper's.**

### 1.1 Why the out-of-sample point is the whole of it

The paper's sample ends **2009**. GLBX.MDP3's daily history begins **mid-2010**
(the exact date is read from `metadata.get_dataset_range`, never hard-coded).
**There is therefore no overlap at all between this test and the paper's
sample.** Every result this registration produces is post-publication, which is
precisely the window where GEM lost 5.2 points a year against SPY
(`diversifier_candidates` §2) and where Faber has underperformed buy-and-hold
since ~2009 (§5.2).

That makes the test unusually clean and unusually unforgiving. **It also means a
negative result here does not refute the paper** — it refutes the strategy's
survival into the 2010s, which is the only question this project has any use
for. The report says so in those words.

---

## 2. The specification, fixed here

Values come from the paper or from spec §2.1's selection rule. **None is chosen
from a measurement of returns**, because a baseline chosen from the data is the
search it was meant to anchor.

| Parameter | Registered value | Source |
|---|---|---|
| Signal | sign of trailing excess return | MOP eq. (5), p. 236 |
| **Lookback — the deployed spec** | **equal-weight ensemble over k ∈ {3, 6, 9, 12} months** | `PROGRAM_INDEX` §4: "prefer an ensemble to a chosen parameter" |
| Lookback — reported neighbour | k = 12 alone | MOP's headline cell |
| Skip most recent month | **no** | spec §1.1 **[P]** — MOP §3.2, p. 234–235, signal is `t−k−1` to `t−1`. Settled by the paper, not chosen here. The skip variant remains a reported neighbour |
| Volatility estimator | EWMA, δ = 60/61 (com = 60), about the EW mean, × 261, lagged one day | MOP eq. (1), p. 233 |
| Warm-up | 261 daily returns before an instrument enters | spec §1.2 [D] |
| Position vol target | 40% ex-ante per position | MOP p. 236 |
| Portfolio construction | equal weight across instruments with a live signal | MOP p. 236 |
| Rebalance | monthly, **tranched over five sleeves** on trading days 1, 5, 9, 13, 17 | spec §1.4 [D]; `diversifier_candidates` §4 |
| Roll | front month, **5 trading days before expiry from the `definition` schema**, cross-checked against the `c.0` symbol-change dates. **GC, SI, HG, ZN, TN: nearest active-cycle contract, rolled 5 trading days before its delivery month begins** | spec §4; §0.1 amendment A; **§0.2 amendment C** |
| Signal series | difference-back-adjusted continuous | spec §4 |
| P/L series | **the actual held contract**, roll charged | spec §4 |
| Instruments | the eleven of spec §2.2 + the rates arm from G3 | spec §2.1 |
| Friction | three levels: $0.50 / $1.25 / $2.50 per contract per side | spec §6 |

**The ensemble is the deployed specification, not an average reported for
comfort.** ReSolve's equal-weight ensemble of 1,226 GEM variants drew a 13.2%
drawdown against the median single spec's 17.4% at no cost
(`diversifier_candidates` §4), and Newfound's 9-month and 10-month lookbacks
returned 43.1% and 146.1% on the same data — differences that "are not expected
to mean-revert". **Picking one k is picking one of those.** This project has
never run an ensemble (`PROGRAM_INDEX` §7 item 14 has wanted one for MCL's trail
since 2026-09-11); TSMOM runs one from the start.

---

## 3. What every run must emit

Fixed here because the runner is written after this document.

1. **Net, and net per year**, at **all three friction levels**, gross stated
   separately and never as the headline.
2. **Both halves of the sample**, split at the median date, **split point not
   swept**.
3. **Per-calendar-year table**, every year printed, none omitted.
4. **drop-top-N by MARKET**, N = 1, 2, 3 — the market analogue of drop-top-N by
   symbol. Printed as `n/a` rather than `$0` if N ≥ the market count
   (`PROGRAM_INDEX` §4).
5. **Cluster bootstrap by market** — markets drawn with replacement, every
   month of a drawn market travelling with it, 2,000 resamples, seeded.
6. **Cluster bootstrap by calendar year**, same shape.
7. **Two benchmarks, side by side:** equal-weight **buy-and-hold** of the same
   markets at the same volatility scaling, and **cash** (zero). A trend book
   that cannot beat owning the same things is not a trend book.
8. **Realised portfolio volatility against the 40%/12% target**, at fractional
   sizing and at integer sizing, separately.
9. **Turnover**: contract-sides per year, split into rebalance and roll.
10. **The rebalance-day grid** — all ~21 trading days — as the distribution the
    tranched spec sits in.
11. **The lookback grid** k ∈ {1, 3, 6, 9, 12, 24}, every cell printed, with the
    ensemble's position in that distribution stated as a percentile, in
    ReSolve's form: "the ensemble beat N% of single-k specs". **MOP's Table 2
    also tests k = 36 and 48; both are excluded here and the reason is a
    property of this sample, not of the result.** With the dataset starting
    mid-2010 and the holdout starting 2022, a 48-month lookback spends four of
    eleven in-sample years on warm-up. Printed in the report as excluded, with
    that reason.
12. **Coverage in the same pass as the P/L**: bars loaded per market, first and
    last date, missing intervals, instruments absent for warm-up
    (`PROGRAM_INDEX` §4).
13. **The three rates arms of spec §2.3 side by side, unranked.**

**Nothing is ranked. No "best cell" table.** Every bucket printed.

---

## 4. The bar to clear — all of it, or the strategy is not carried forward

Adapted from the seven criteria and `PROGRAM_INDEX` §4, to a monthly book.

1. **Positive after costs at the mid friction level** ($1.25/side), on the
   ensemble spec, on the non-holdout sample.
2. **Both halves positive** at mid friction. An empty half is a failure, not a
   pass (`PROGRAM_INDEX` §4: "an empty half is not a sign flip").
3. **drop-top-1 and drop-top-2 by market still positive** at mid friction.
4. **Cluster bootstrap by market: total > 0 in ≥ 95% of 2,000 resamples.**
5. **Cluster bootstrap by year: total > 0 in ≥ 95% of 2,000 resamples.**
6. **Beats equal-weight buy-and-hold of the same markets**, at mid friction, on
   both net and on return-per-unit-of-realised-volatility.
7. **No single calendar year supplies more than 50% of net**, and **no single
   market supplies more than 50% of net.** — *See §4.1.*
8. **The ensemble is not beaten by the median single-k spec.** If it is, the
   ensemble argument of §2 failed on this data and that is reported as a
   finding, not fixed by switching to the winning k.
9. **Still positive at the high friction level** ($2.50/side). A strategy whose
   sign depends on the cost model is a cost model result.

**Fewer than 60 months of data for a market is not read**; the market is printed
with its coverage and no verdict.

### 4.1 The one-strong-year rule, and why it is criterion 7

The handover names this as a registered risk and it is the criterion most
likely to be argued with after the fact. **The QQQ-ORB replication found 76% of
its P/L in 2022** (`PROGRAM_INDEX` roster, ORB row). Trend-following's
documented weak stretch after 2012 and its very strong 2022 are the same
phenomenon: a decade of mediocrity with one enormous year in it.

So: **a result that clears criteria 1–6 while failing criterion 7 is reported as
FAILED, with the concentration named.** It is not reported as "passed, with a
note". The whole point of writing it down now is that in eighteen months, with a
curve on screen showing one glorious 2022, this sentence is already here.

**And how a weak post-publication stretch is read, registered now:** if the
strategy is flat-to-negative across 2013–2021 and positive overall on the back of
2022, that is **criterion 7 failing**, and the reading is *"trend-following's
post-publication weakness reproduces here"* — the same verdict
`diversifier_candidates` §2 reached for GEM. It is **not** read as "the edge is
intact and the sample was unlucky." That reading is unavailable because it was
ruled out before the data was seen.

---

## 5. Capacity is a measurement, not a criterion

Spec §3 already measured, from free data on 2026-09-17, that **the paper's
sizing is not implementable at $22,129**: eight of thirteen markets cannot reach
half a micro contract, a forced one-lot book runs at ~173% portfolio volatility
against the paper's 12%, and all thirteen markets become feasible at roughly
**$532,000** of equity.

That finding is **not** a pass/fail criterion, because failing it would end the
measurement, and the measurement is worth making regardless — the account may
not stay at $22k, and a strategy that needs half a million dollars to hold
properly is worth knowing about *before* the data is bought rather than after.

**So the run reports, and does not score:**

- the book at **fractional** sizing — what the strategy is worth, unconstrained;
- the book at **integer** sizing at **$22k, $100k and $500k** equity — what Ben
  could actually have held;
- the **gap between them**, per market, which is the price of granularity;
- the **largest subset** of markets that fits a 10% and a 15% portfolio
  volatility cap at $22k, and what that subset's result is on its own.

**Integer rounding may move the sign.** `PROGRAM_INDEX` §5: "capital-based sizing
can flip a strategy's sign." If it does here, that is the headline, and the
fractional number is the one that must not be quoted alone.

---

## 6. The holdout — cut before the first run, enforced in code

**The last four calendar years, 2022-01-01 onward, are locked.** Everything in
§3 and §4 is measured on the sample from the dataset's start to 2021-12-31.

- The holdout is **spent once, by one candidate**, and the module refuses a
  second (`PROGRAM_INDEX` §1; the pattern is `common/holdout.py`'s
  `split_sessions`, which is the one implementation every equity study calls).
- **It refuses `--limit` and every other flag that could quietly narrow it.**
- **A test asserts the refusal fires**, and the test is mutation-checked: break
  the enforcement and the test must fail.
- `var/state/holdout.json` covers the equity universe and is **not** reused. TSMOM
  writes its own cut file and the loader refuses the equity one by name.

### 6.1 A defect the enforcement found in itself, 2026-09-18

`is_locked` originally compared `str(day)[:10] >= "2022-01-01"`. For a bare
`YYYY-MM` — the form a monthly runner passes — that is wrong at exactly one
place, the boundary:

```
"2022-01" >= "2022-01-01"   ->   False      (the shorter string sorts first)
```

**January 2022, the first month of the holdout, was classified as training**,
and `split_months` would have returned it under the label
`"training, before 2022-01-01"`. The docstring had *claimed* this case was
handled — "the correct side of a January 1st boundary either way" — which is
`PROGRAM_INDEX` §5's own entry: a report must read its own inputs, not assert
them. A bare month is now padded to its first day, and a test pins the boundary
in both forms.

**2022 sits inside the holdout deliberately.** It is trend-following's best year
of the decade and the single most likely source of a criterion-7 failure. Having
it locked means the in-sample verdict cannot be carried by it, and that spending
the holdout later is a real test rather than a victory lap.

---

## 7. What is registered as NOT to be done

- **Substituting a grid winner into the deployed spec.** §2 is the spec. The
  grid is the distribution it sits in, per `PROGRAM_INDEX` §4, and nothing more.
- **Switching the lookback after seeing the grid.** Criterion 8 exists so that
  the ensemble losing is a *finding*.
- **Choosing the rates arm from its result.** G3.
- **Adding a market because it would help**, or dropping one because it hurts.
  The §2.1 selection rule is closed; changing it is a PRE-RUN amendment with a
  reason that does not mention a return.
- **Substituting a yield-quoted contract for a price-quoted one.** Spec §2.3.
  Long ZN is **short** 10Y, and a book that gets this wrong prints an entirely
  ordinary-looking curve while trading the opposite of its own signal in one
  market.
- **Inferring the roll from volume or open interest.** Both are outcomes. The
  `definition` schema carries the expiration date; the roll is read.
- **Quoting a gross figure as a result.** `PROGRAM_INDEX` §1.
- **Reporting the continuous series' P/L.** It is for the signal and the
  volatility estimate and nothing else. Spec §4 rule 3, and spec §3.1 for what
  happens when that line is crossed: a free data pull whose only job was to size
  a table put a −46.3% roll break into natural gas and a 15-point error into the
  divisor of its position size.
- **Spending the holdout on anything from the grid.** §6.

---

## 8. What would make this run wrong, in the specific ways this project's runs
have gone wrong before

- **A continuous series that looks right while booking the wrong contract**
  (`PROGRAM_INDEX` §3, named there as the project's signature failure). Guarded
  by spec §4 rule 4's synthetic two-contract test, which must be mutation-checked.
- **A volatility estimator that is right in `pandas` and wrong by hand**, or the
  reverse. `ewm(...).var(bias=True)` versus `bias=False` is a one-flag
  difference that produces a plausible number. Guarded by an equality test
  against a hand-built weighted sum.
- **An instrument absent for warm-up counted as flat.** §2's warm-up rule and
  §3 item 12's coverage output exist so the two are distinguishable.
- **A report that asserts its data source instead of reading it.** `PROGRAM_INDEX`
  §5: the ORB pre-flight printed an EQUS.MINI caveat over XNAS.BASIC numbers and
  two tests pinned the bug. Every TSMOM report **reads** the dataset, schema and
  roll rule out of the archive manifest and **refuses** a dataset it was not
  registered on.
- **A bare text-mode open.** `tests/test_encoding_guard.py` refuses one.
- **A guard that cannot fail.** Every check written for this strategy is
  mutation-tested before it is committed, and one that survives every mutation is
  removed (`PROGRAM_INDEX` §1).

---

## 9. Multiplicity budget

Counted by **family**, not by column (`PROGRAM_INDEX` §4).

Families searched: **lookback k** (one), **rebalance day** (one), **rates arm**
(one, and settled by G3 rather than by search), **friction level** (not a search
— all three are always reported). **Three families**, and the deployed spec is
fixed in §2 before any of them is read.

**Budget: three further registered hypotheses on TSMOM before the line is
closed**, matching how the B-series was budgeted. A fourth requires a reason
written down that does not begin with a result.

---

## 10. A prediction, written down now

Recorded so that it can be wrong. `REGISTERED_orb_grid` §"why write it down"
did the same and the prediction held for the wrong reason, which was worth more
than being right.

**I predict the strategy is positive gross and roughly flat after mid friction
on the 2010–2021 sample, and that criterion 7 fails on market concentration
rather than on year concentration** — that gold and crude carry most of the net,
because they had the decade's clearest sustained trends, while the four
currencies contribute close to nothing and are half the book by count.

**If that is what happens, the honest reading is that this is a 2–3 market
strategy wearing a 12-market coat**, and the diversification argument that
ranked TSMOM top of `diversifier_candidates` was doing less work than it
appeared to. Writing it here means that reading is available on the day rather
than assembled afterwards.
