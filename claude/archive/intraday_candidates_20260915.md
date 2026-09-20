# Intraday equity — what is closed, and the five candidates left

**Written 2026-09-15, in the research chat.** No program logic was touched.
This doc exists to stop the build chat re-proposing anything in §1 and to give
§2 enough specification to be registered without another round trip.

> **The framing, and it is the point of the document.** Four independent
> measurements on 2026-09-14 closed the same question from four directions:
> **MCL on this universe, with minute OHLCV, does not work, and no tuning
> inside it will.** It loses roughly **$6.26/trade gross of all friction**, so
> the cost side cannot rescue it either.
>
> What that leaves is not "another indicator". The remaining moves on intraday
> equity are to change the **data**, the **session**, the **allocation**, or the
> **fill**. §2 is ranked on that basis.

---

## 1. Closed — do not re-propose

Every row below was measured, not argued. Figures are per trade at the $4.26
friction level unless stated.

| Question | Verdict | The measurement |
|---|---|---|
| **Can an entry filter built from minute OHLCV separate winners?** | **No** | 22 features, 11 families, **0 clear**. Base rate 29.2%; break-even needs **54.3%, a 1.86× lift**. Best: `macd_margin` 1.56×, `ma20_dist` 1.46×, `ma20_slope` 1.37× — all under the bar. **88 buckets, none profitable**; best bucket (8.31) against a (10.52) book. On two of three best features the best-rate bucket has the *worst* P/L. |
| **Are the entries taken on thin or momentum-less bars?** | **No on momentum, yes on size, and it does not matter** | **112 bucket means across six clause margins × 4 quartiles × 4 splits: zero positive.** Best (6.02), worst (13.46), book (9.16). Median RSI **+11.35 pts** and MFI **+15.56** over the 3 bars into entry. 39.7% of entries do sit on bars under $100,000 (min $1,380) — but session volume is never thin (min $158,706, median $4.17M). |
| **Do dollar-volume or liquidity floors help?** | **No** | Floors $5k–$1M: **removed trades lose the same as kept** ((7.85)–(9.89) against a (9.16) book), and the two halves disagree in direction. |
| **Can a better stop help?** | **No** | $5–$25 with slippage charged is **monotone worse**: (9.26) → (14.45). The only improving row, $5, still loses $9.26, **cuts 69.8% of winners**, and **88% of the book is stopped** — so the row is almost entirely the slippage estimate's own assumption. Reproduces the old 10/15/20c rejection on the honest universe, now with a mechanism. |
| **Can a better exit rescue the losing trades?** | **No** | Two-population split over 3,955 trades: dips-then-runs **1,156 (29.3%) at +$19.13**; pops-then-fades **2,794 (70.7%) at −$22.73** with only **$15.30 available in 30 bars = 3.6× friction**. The earlier "THE EXIT IS WORTH ATTACKING" verdict is **withdrawn as under-specified**. |
| **Is MCL's early-name advantage MCL's?** | **No — it is the screen's** | MCL early-name gap **1.49** against H0's own **1.35**. Settled. (MC5's 3.91 still differs and is still concentrated in five symbols ≈ 6,885.) |
| **Was MCL's universe leak negative?** | **Withdrawn** | (2.20) → **(0.13)** on the repaired universe. The intraday leak carries everything: MCL **4.79**, MC5 **9.37**. |

**Also closed, from earlier work and still closed:** the take-profit ladder,
Cameron's partial, Cameron's breakeven stop, the inferred dip entry, the
scale-out, the pyramid, the scale-up, confirm-N, every `TRAIL_PCT` candidate,
VW9, MC5 as a candidate, H0 as a rule, GEM, and the Donchian/LWTI and
trend-line strategies from the source-video set (`source_videos_20260907.md`
§2.1, §8).

**Current state.** Universe rebuilt at **6,170 symbol-days / 551 sessions**,
99.4% repaired prior close; knowable-by-04:30 share up 15.9% → 22.6%. MCL
**(10.52)/trade, (6.74)/symbol-day**, beating the control by **+4.88 / +7.25**
and still losing. MC5 **(13.50)/trade, (15.06)/symbol-day**, **no verdict** —
its denominators disagree. H0 **(15.40)** as-screened, **(14.06)** knowable at
04:30 over 1,258 trades. Nothing is profitable at any friction level, and
drop-top-5 deepens the loss in all six arms. **The locked holdout is unspent.**

---

## 2. The five candidates

Ranked by expected value, not by ease. Each carries what would kill it, because
a candidate without a kill condition is not registerable.

> **Added 2026-09-15, second pass: §6 sits ahead of all five.** Its first item
> is 401 free API calls that were identified as the obvious next step on
> 2026-09-10 and never run, and it unblocks the regime gate — the single
> largest effect measured anywhere in this project.

### 2.1 ORB — the strongest, because it is structurally different

**Why it is first.** Not the setup. **Every order is inside RTH**, and that
independently sidesteps the three measured facts that have been killing
everything else:

| Fact | Pre-market | RTH |
|---|---|---|
| Median spread | **83 bps** | **60 bps** |
| EQUS.MINI tape capture | **1.5%**, p05 **0.0%**, 26% of symbol-days with no reading | 4.7% |
| The exit that ends the session | `window_close`, **−$0.0700/share** median — the most expensive exit measured | not required |

Every pre-market strategy in this project pays all three. ORB pays none of
them, and that is an argument from measurement rather than from preference.

**State.** Specified, pre-flight done. Usable 15-minute range on **57.2% of
symbol-days against 27.4%** on the old tape; leak cut passes; structure stop
usable at **p50 2.98% of price**. Go/no-go fixed in `orb_strategy_spec.md` §11
**before any code**. 15 of 20 parameters uncalibrated; §14 puts **six
measurements before entry logic**.

**What to do:** the six pre-flight measurements, **§10.2 first** — it is the
only one that can invalidate the premise.

**What would kill it:** §10.2 failing; or the opening range proving to be a
volatility tautology in the same way `range_pct` is in `universe_lift`.

**Caveat the build chat must carry:** ORB inherits the §7 item 1 universe gate
for *name selection* — the simulated screen is still unvalidated against the
live watchlists. It does **not** inherit it for the intrabar mechanics, so the
six measurements can proceed now.

### 2.2 Rank allocation instead of arrival-order allocation

**The cheapest real change available, and it fixes something already broken.**

Live, **29% of buy attempts were rejected by the concurrency cap** — 46 of 159,
and 30 of 62 on 09-10. So the position slots are already the binding
constraint, and **which signals get taken is decided by arrival order, not by
quality.** No backtest models this at all.

Meanwhile `universe_lift` measured within-session concentration:

| criterion | top 5 | top 20 | top 50 | top 250 |
|---|---|---|---|---|
| `range_pct` | **14.85×** | 6.91× | 3.18× | 1.14× |
| `gap_pct` | 10.79× | 4.65× | 2.20× | 0.93× |
| `volume` | 6.47× | 3.12× | 1.88× | 1.05× |
| `dollar_vol` | **0.29×** | 0.68× | 0.90× | 0.95× |
| `price` *(control)* | 0.05× | 0.06× | 0.12× | 0.84× |

**Nearly all the separation lives in the first handful and is gone by a
hundred.** And the live screen surfaces a median of **one** name by 04:30 with
**29.7% of sessions empty** anyway, so the cap binds on the days that have
names.

This is the **sixth independent arrival at rank-don't-gate** in the project's
source material, and it is the one place in the system where ranking is not
optional — we are forced to choose and we currently choose badly.

**Two things that must be registered with it, or it will read as a win when it
is not:**

1. **`dollar_vol` is INVERTED** (0.29×). Sorting by most dollars traded selects
   big liquid names and size suppresses percentage moves. It is the sort most
   people would guess at and it is worse than useless. Any ranking experiment
   must include it as a **negative control**.
2. **`universe_lift` measures run STARTS, not P&L**, and the doc is explicit
   that *"volatile names keep being volatile"* is most of what the 14.85×
   measures — *"that is not alpha."* The P&L version has never been run.

**What would kill it:** rank allocation and arrival-order allocation producing
the same trade list (check trade **count** and overlap, not just P/L — a
variant that equals its base prints 0.00 and renders as NOT MATERIAL); or the
ranked arm failing drop-top-5.

### 2.3 Participate in runs already underway, rather than predict their start

**The inversion nobody has tried, and the census argues for it.**

`run_census` is the newest instrument here and **no strategy has been built
from it.** 552 sessions, 45,041,524 bars, **67,814 runs** at 8%-in-15 =
**122.85 per session**, median **$42 per 100 shares** at the oracle's own entry
and exit. The distribution is savage: **top 1% carry 27.5%, top 5% carry
56.5%.**

`run_signal` asked only *does anything precede a run*, and the answer was
effectively no — whole-tape base rate **0.108% (1 bar in 926)**, best
volatility-independent feature `ma20_slope` at **1.94×**, taking you to 1-in-476
while firing on a quarter of all bars. *"Real, small, not a condition."*

**So stop predicting.** The untested form is to enter into **confirmed
extension** and accept a poor fill, on the argument that catching a small share
of the *big* runs at bad fills beats catching typical runs at good fills. Three
things support it:

- The concentration above. A rule that catches the typical run earns ~nothing
  after friction **by construction**.
- MCL's losing population is **70.7% pops-then-fades at −$22.73**, which is what
  buying hesitation looks like. The profitable population dips first.
- It is the same question already named as the next pre-registered item —
  **"the fill, not the filter"**, paying up into the spike — and never tested
  directly.

**What would kill it:** the entry slippage exceeding the concentration benefit —
which is exactly why §2.5 must be tested *with* it, not after it. Also: any
version of this that selects on `range_pct` is at risk of the same tautology as
§2.2, because a run is *defined* as a percentage move.

### 2.4 Off-tape features, and halt state first

The tape has now been established not to separate on this universe — 88 buckets
across 22 features, plus 112 margin buckets. **The only features left are ones
that are not the tape.** In order of expected value:

| Source | State | What it gives | Cost |
|---|---|---|---|
| **Databento `status` (LULD halts)** | **untested, must be priced first** | halt and pause state, point-in-time | money |
| **FINRA short interest** | untested | bi-monthly, **point-in-time by construction** | free |
| **SEC EDGAR shares outstanding** | **built** (`common/edgar_shares.py`, 37 tests) | point-in-time shares outstanding joined on `filed` | free; pull is 1,592–3,184 requests, 4–8 min, must run on Ben's machine |
| `NEWS_SENTIMENT` | untested whether history reaches 551 sessions | timestamped news | unknown |

**Halt state first, and the case is specific to this universe.** Nothing in the
project models LULD at all; **36.4% of Tier 2 pauses fall in 09:45–09:50 ET**
and Tier 2 pauses occur on **100% of trading days**. Low-float gappers halt
constantly. It is simultaneously a feature and a risk control, and it is the
kind of state variable that could plausibly separate a dip-then-run from a
pop-then-fade when price alone provably cannot.

**Carry this caveat on every figure:** EDGAR covers **80.2% of symbol-days**
(4,948/6,170; 75.0% of symbols). The uncovered 20% passes untouched, so any
filter built on it is **weaker than it looks, not wrong** — and the covered
fraction must travel with the number. **Shares outstanding is not float**, and
it enters as a **ceiling test bucketed against entry outcomes**, not as a
filter.

### 2.5 Posted limit entries — infrastructure, but it moves every future bar

Not a strategy. It changes what every candidate above has to clear.

| Order type | Cost per share |
|---|---|
| Marketable | **≈ 0.0067** (0.0035 tiered + 0.0030 passed-through take fee) |
| Passive | **≈ 0.0021** (0.0035 − 0.0016 rebate) |

**A 3× swing decided purely by order type, before any strategy question.** It
will **not** save MCL — that is broken gross of friction — and the doc should
say so plainly so nobody re-opens MCL on this basis.

It belongs tested **alongside §2.3**, not separately: §2.3 deliberately pays up
and §2.5 deliberately does not, so they are the two ends of one axis and
running them apart measures neither. Related measured facts: a signal exit
fills at the reference (`gradient_reversal` **$0.0000/share**) while a stop
fills through it (trailing-stop sells **−$0.0563/share**); GTC orders re-incur
the USD 0.35 minimum each day.

---

## 3. Do not try

- **Any entry filter computed from minute OHLCV on the screened universe.** §1.
- **Stop-width work.** §1, monotone.
- **Exit rescues on the losing population.** §1, $15.30 against 3.6× friction.
- **Dollar-volume or liquidity floors.** §1, and `dollar_vol` ranks *inverted*.
- **The Cameron flat-top / gap-and-go / reversal set.** His own 401-video census
  makes these his riskiest setups — flat top 1.9× red-day lift, halt resumption
  2.4×, reversal 2.6×, against the micro pullback's 0.7 — and the reversal's
  short side is not buildable on this broker.
- **Bollinger + RSI on large caps.** Premise measured: **−0.010% excess per
  trade, t = −0.18** Newey-West, and RSI(14) vs %b is **ρ = +0.911** — one
  signal, not two.
- **Volume-profile / value-area constructions on the pre-market window.** Tape
  capture is **1.5%** with p05 **0.0%**; a distribution of volume across price
  cannot be built from that. Regular hours may survive sampling and is worth
  measuring separately. `source_videos_20260907.md` §3.1.

---

## 4. Proposed `PROGRAM_INDEX.md` §7 insert — for the build chat to apply

Not applied here. Suggested as new items after the existing item 1, renumbering
the rest:

```
2.  ORB's six pre-flight measurements (orb_strategy_spec.md §10), starting
    §10.2 -- the only one that can invalidate the premise. Promoted from
    item 7 on 2026-09-15: it is now the only intraday candidate whose
    structural argument does not depend on the tape that is failing.

3.  Rank allocation vs arrival-order allocation under the concurrency cap.
    29% of live buy attempts are rejected and no backtest models it.
    Register dollar_vol as a NEGATIVE control (universe_lift: 0.29x).
    Report trade count and overlap, not only P/L.

4.  Run participation: enter into confirmed extension rather than predict a
    run start. From run_census -- top 5% of runs carry 56.5%. Must be
    registered TOGETHER with posted-limit entries (item 5), because the two
    are opposite ends of one axis.

5.  Posted limit vs marketable entries. Measured 3x cost swing
    (0.0021 vs 0.0067 per share). NOT a rescue for MCL, which is negative
    gross.

6.  Price the Databento `status` schema, then bucket entry outcomes on halt
    state. 36.4% of Tier 2 pauses fall 09:45-09:50; nothing models LULD.
```

Added 2026-09-15, second pass — these go BEFORE the five above:

```
1a. Recover real publish dates for census.csv: 401 metadata calls, free.
    Identified as "the obvious next step" in warrior_census_20260910.md §8
    on 2026-09-10 and not run. Without dates the census can be ordered but
    not joined to anything.

1b. Fit a computable regime classifier against the 234 human-labelled
    recaps. Cold costs Cameron 16x his mean day and is 61% of the sample.
    Candidate inputs already listed in execution_gap_20260910.md §5.

1c. Do Cameron's named symbols beat our top-5-by-volatility ranking on the
    same date? Decides whether name selection is worth attacking.

1d. Transcribe the two dip videos (ORWJzImSTdE, hz7vhSIXXSc). Dip buying is
    half his book at the same risk lift as the micro pullback and MCL does
    not implement it. Existing PROGRAM_INDEX §7 item 8.
```

---

## 5. Standing requirements on all five

From `PROGRAM_INDEX.md` §4, restated because these are the ones most likely to
be skipped on a candidate that looks promising:

1. **Register before you run.** Rules and pass criteria committed first; the
   commit hash is the timestamp.
2. **Report at all three friction levels** — $1.00 / $4.26 / $8.92 — and never
   commission-only.
3. **Two denominators**, per trade and per symbol-day. **A disagreement is a
   refusal, not a result.**
4. **drop-top-N on the level and on the delta.** Say `n/a`, never `$0`, when the
   arm has N or fewer symbols.
5. **Both halves.** And remember an empty half is not a sign flip.
6. **The sample is SESSIONS, not trades.**
7. **Boundary check on any grid.**
8. **A control whose output is indistinguishable from the failure it detects is
   not a control** — the recurring failure in this project. For §2.2
   specifically, a rank rule that reproduces arrival order will print 0.00 and
   render as NOT MATERIAL.
9. **The locked holdout is spent once, by one candidate.** Still unspent. None
   of the five above is ready to spend it.


---

## 6. The Cameron corpus — four items, and the first is free

**Added 2026-09-15.** Ben proposed working through Ross Cameron's daily recaps to
learn how he entered, what worked and what did not, and build a strategy from it.
The instinct is right and the work is largely already done — twice. This section
records what exists, what it concluded, and the one step that was left undone.

### 6.1 What already exists

- **35 recaps read in full**, 2026-09-10 → `execution_gap_20260910.md`.
- **A census of 401 videos** — every upload in the 90-second-to-40-minute band
  from 2025-07-01 to 2026-09-10, **all read in full**, each reduced to one
  structured row → `warrior_census_20260910.md`, `census.csv`, `CENSUS_SPEC.md`.
  317 are recaps. Schema carries symbols, setups, mistakes, regime label, first
  trade time, trade count, day result and stated P/L.

**The census exists because the 35-video pass was title-selected, and it
overturned two of that pass's findings.** `back_side` read as a top-four failure
mode in the small sample (4 of 7) and censuses at **1.1×**; `slippage` at
**1.0×**. Selected-sample viewing of this channel has already produced wrong
answers twice. **Only a census or a labelled join adds information.**

### 6.2 What it concluded, and it answers the question directly

| mistake | red days | green days | lift |
|---|---:|---:|---:|
| ignored_own_filter | 38.5% | 3.6% | **10.7×** |
| broke_ice_boredom | 12.8% | 1.6% | 8.0× |
| **oversized** | **46.2%** | 7.2% | **6.4×** |
| stop_widened | 7.7% | 1.6% | 4.8× |
| traded_low_quality | 30.8% | 7.2% | 4.3× |

Setups by risk lift: micro pullback **0.7**, dip buy **0.7**, flat top 1.9, halt
resumption 2.4.

> **Every high-lift item is a position-sizing or gating decision. Not one is an
> entry rule.**

So the corpus has already been mined for "how he enters and what works," and the
answer is **that the entry is not where his money is won or lost.** Three Cameron
mechanics have since been coded and tested here and all three lost: the partial
(−$1,435, its original +$261 withdrawn), the breakeven stop (**−$27,260**), and
an inferred dip entry.

**Do not commission another entry-extraction pass.** It re-asks a settled
question against a source whose selected samples have already misled this project
twice.

### 6.3 The step that was left undone

`warrior_census_20260910.md` §8, verbatim:

> *"Dates are position-ordered, not calendar-dated — the playlist endpoint
> returns no date field, so the census can be ordered but not joined to Ben's
> tape by date. Recovering real dates would need **one metadata call per video
> (401 calls, free)** and is the obvious next step if a date-level join is
> wanted."*

It is item 6 on that document's own priority list. **401 free calls.** Without
dates `census.csv` ranks but joins to nothing. With them every row joins to Ben's
134 trading days, to the Databento archive (which covers most of the
2025-07-01 → 2026-09-04 window), and to MCL's backtest trades.

### 6.4 What the dates unlock, in order

**(a) A regime classifier with 234 human-labelled days — the highest-value item
in this document.**

| his label | n | green rate | mean day | no-trade days |
|---|---:|---:|---:|---:|
| hot | 53 | 94.3% | **$46,481** | 0 |
| mixed | 38 | 97.2% | $24,172 | 2 |
| **cold** | **143** | 76.9% | **$2,835** | 22 |

A cold market costs him **16× his mean day**, and **cold is 61% of the labelled
sample**. The census's own words: *"nothing else measured in this project moves
an outcome that far."* MCL has no regime gate at all and is being paper traded
inside a cold regime.

With real dates those 234 labels become a **supervised target**. The computable
inputs are already enumerated in `execution_gap_20260910.md` §5: count of stocks
up >100% on the day; magnitude of the leading gainer (58% = cold, 300–500% =
hot); round-trip rate among top gappers; float of the leaders; share of movers
under $1 against $2–20. He also states the transition is asymmetric — *"the shift
from hot to cold is much more subtle than the shift from cold back to hot"* —
which argues for a slow entry into the cold state and a fast exit from it.

> **Why this use of the corpus is sound where copying his trades is not.** The
> regime label is a claim about **the tape**, independently checkable against our
> own daily bars. His P/L is self-reported on a channel that sells a course. The
> census fixed *selection* bias; it could not fix *source* bias. Using the labels
> and not the P/L sidesteps the part that cannot be audited.

**(b) Does his selection beat our ranking?** With dates, `census.csv`'s `symbols`
column is a list of symbol-days a professional chose to trade — an externally
sourced label for name quality, independent of `common/screen.py`.

`where_the_edge_is_20260913.md` found the screen adds only **1.35×** over a
one-line volatility sort, and that watchlist size is its own lever (**14.85×** at
top 5, **1.14×** at 250). So the test is direct: **do his named symbols beat our
top-5-by-volatility ranking on the same date?** If yes, name selection is worth
attacking and §2.2 gets sharper. If no, the question closes. Either answer is
worth having and the measurement is cheap.

**(c) Dip buying — half his book, and we have none of it.** 129 mentions against
the micro pullback's 172, at the **same 0.7 risk lift**, and MCL does not
implement it. `PROGRAM_INDEX.md` §7 item 8 already asks for the two dip videos
(`ORWJzImSTdE`, `hz7vhSIXXSc`) to be transcribed, precisely because *"every dip
finding so far is about an inference, not about his rule."* The rejected dip
entry was an inference; his actual rule has never been read.

### 6.5 Two items from the earlier pass that were never run

Both computable today, no new data:

1. **Position construction on winners against losers.** Cameron's winners carry
   **36% more shares** than his losers (19,000 vs 14,000); Ben's carry **26%
   fewer** (1,963 vs 2,467), on 12.1 fills against 10.3. He adds to winners; the
   live ledger added to losers. `execution_gap_20260910.md` calls this *"the
   cleanest, most actionable difference in this document"* and it is one ratio
   off `flex_round_trips.csv` and any backtest trade list.
2. **The hold-50% rule** — reject a candidate not still holding half its initial
   pre-market impulse at decision time (`warrior_5_selection_in_practice.md` §1).
   Computable from `bar_cache` with no new field; serves the screen and the
   regime gate with one computation. **MCL ranks by gap size and never asks
   whether the gap is holding.**

### 6.6 Standing on this source

**Use the recaps as labels, not as a strategy.** Regime and symbol selection are
claims about the tape and can be checked. His entries have been censused and
ruled out as the lever; his P/L cannot be audited; and every mechanic of his that
has been coded here has lost money.

**If (b) comes back saying his symbol picks beat our ranking, then — and only
then — going back to the tape for how he entered those specific names becomes
worth the hours.**
