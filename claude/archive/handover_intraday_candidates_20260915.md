# Handover to the build chat — 2026-09-15 (rev. 2)

> **Rev. 2 adds section 0 — the Cameron corpus.** Its first item is 401 free
> API calls that were named as the obvious next step on 2026-09-10 and never
> run, and it unblocks the regime gate, which is the largest single effect
> measured anywhere in this project. **It goes ahead of everything else below.**

**From:** the research chat. No program logic was touched; nothing under
`D:\Trading` was modified.

**Read first:** `claude/intraday_candidates_20260915.md` in the project. This
message is the summary and the ask; that doc has the figures and the kill
conditions.

---

## Why this exists

The 09-14 batch closed the intraday question from four directions at once, and
the conclusion is stronger than any single result in it:

**MCL on this universe, with minute OHLCV, does not work, and no tuning inside
it will.** It loses roughly **$6.26/trade gross of all friction**, so the cost
side cannot rescue it either.

Four measurements, independently:

- **Entry filtering** — 22 features, 11 families, **0 clear**. Break-even needs
  a 1.86× lift (29.2% → 54.3%); best feature reaches 1.56×. **88 buckets, none
  profitable.**
- **Entry margins** — **112 bucket means, zero positive.** Ben's "no momentum"
  read was right on bar size (39.7% of entries under $100,000) and wrong on
  momentum (median RSI +11.35, MFI +15.56 into entry). Dollar-volume floors:
  removed trades lose the same as kept.
- **Stops** — $5–$25 **monotone worse**, (9.26) → (14.45). The one improving row
  is 88% the slippage assumption's own arithmetic.
- **Exit** — the losing 70.7% has **$15.30 available against 3.6× that in
  friction**. The "THE EXIT IS WORTH ATTACKING" verdict is withdrawn.

So the useful conclusion is not "try another indicator". **The remaining moves
on intraday equity are to change the data, the session, the allocation, or the
fill.**

---

## 0. FIRST — the Cameron corpus, and the first item is free

Ben proposed working through Ross Cameron's daily recaps to learn how he entered,
what worked and what did not. **It has already been done twice**: 35 recaps read
in full on 2026-09-10, then a **census of 401 videos — every upload from
2025-07-01 to 2026-09-10, all read in full** (`census.csv`, 317 recaps).

**Two things to take from that before anything else.**

**(i) The census already answered the entry question, and the answer is that
entries are not the lever.** Red-day mistake lifts: ignored_own_filter **10.7×**,
broke_ice_boredom 8.0×, **oversized 6.4× and present on 46.2% of red days against
7.2% of green**, stop_widened 4.8×. Setups by risk: micro pullback **0.7**, dip
buy **0.7**, flat top 1.9, halt resumption 2.4. *"Every high-lift item is a
position-sizing or gating decision. Not one is an entry rule."* Three Cameron
mechanics have since been coded here and all three lost — the partial (−$1,435),
the breakeven stop (**−$27,260**), an inferred dip entry. **Please do not
commission another entry-extraction pass.**

**(ii) Selected-sample viewing of this channel has already misled us twice.** The
35-video pass had `back_side` as a top-four failure mode; across all 317 recaps
its lift is **1.1×**, and `slippage` is **1.0×**. Only a census or a labelled
join adds information.

**What was left undone**, from `warrior_census_20260910.md` §8 verbatim:

> *"Recovering real dates would need **one metadata call per video (401 calls,
> free)** and is the obvious next step if a date-level join is wanted."*

**401 free calls.** Without dates the census ranks but joins to nothing. With
them every row joins to Ben's 134 trading days, to the Databento archive, and to
MCL's backtest trades. Please run it first. Then:

**0a. Fit a computable regime classifier against the 234 human-labelled recaps.**
Hot 53 days at a **$46,481** mean; cold **143** days at **$2,835** — a **16×**
swing — and **cold is 61%** of the labelled sample. The census's own words:
*"nothing else measured in this project moves an outcome that far."* MCL has no
regime gate at all and is being paper traded inside a cold regime. Candidate
inputs are already enumerated in `execution_gap_20260910.md` §5: count of stocks
up >100%, magnitude of the leading gainer, round-trip rate among top gappers,
float of the leaders, share of movers under $1 vs $2–20. He also states the
transition is asymmetric — slow into cold, fast out of it.

*Why this use is sound where copying his trades is not:* the regime label is a
claim about **the tape** and is independently checkable against our own daily
bars. His P/L is self-reported on a channel that sells a course. The census fixed
**selection** bias; it could not fix **source** bias. Use the labels, not the P/L.

**0b. Do his named symbols beat our top-5-by-volatility ranking on the same
date?** `where_the_edge_is` found the screen adds only **1.35×** over a one-line
volatility sort, and watchlist size is its own lever (**14.85×** at top 5,
**1.14×** at 250). His `symbols` column is an externally sourced label for name
quality. If his picks win, name selection is worth attacking and item 2 below
gets sharper. If not, the question closes. Either answer is worth having.

**0c. Transcribe the two dip videos** (`ORWJzImSTdE`, `hz7vhSIXXSc`) — existing
§7 item 8. Dip buying is **129 mentions against the micro pullback's 172, at the
same 0.7 risk lift**, and MCL does not implement it at all. The dip entry we
rejected was an *inference*; his actual rule has never been read.

**0d. Two items from the earlier pass that were never run**, both computable
today with no new data: **position construction on winners vs losers** —
Cameron's winners carry **36% more shares** than his losers, Ben's carry **26%
fewer** on more fills, called *"the cleanest, most actionable difference in this
document"* — and **the hold-50% rule**, rejecting a candidate not still holding
half its pre-market impulse at decision time. MCL ranks by gap size and never
asks whether the gap is holding.

---

## What I am asking for next, in priority order

**1. ORB's six pre-flight measurements, §10.2 first.**

Promote it. Not for the setup — because **every order is inside RTH**, and that
one property independently sidesteps the three measured facts killing
everything else: pre-market spreads 83 bps vs RTH 60; EQUS.MINI pre-market tape
capture 1.5% (p05 0.0%, 26% of symbol-days with no reading) vs 4.7%; and
`window_close` at **−$0.0700/share**, the most expensive exit measured. Every
pre-market strategy here pays all three. ORB pays none.

§10.2 is the only one that can invalidate the premise, so it goes first.

**Caveat to carry:** ORB inherits the §7 item 1 universe gate for *name
selection*. It does **not** inherit it for intrabar mechanics, so the six
measurements can proceed before the archive extension lands.

**2. Rank allocation instead of arrival-order allocation.**

**29% of live buy attempts are rejected by the concurrency cap** (46 of 159; 30
of 62 on 09-10), and no backtest models it. Slots are already the binding
constraint and we fill them by arrival order rather than by quality.
`universe_lift` says within-session concentration is **14.85× at the top five,
3.18× at fifty, 1.14× at 250** — nearly all of it in the first handful.

Two registration requirements, or this reads as a win when it is not:

- **`dollar_vol` ranks INVERTED (0.29×).** It is the sort most people would
  guess at. Register it as a **negative control**.
- `universe_lift` measures **run starts, not P&L**, and its own doc says
  *"volatile names keep being volatile"* is most of the 14.85× — *"that is not
  alpha."* Report trade count and overlap, not only P/L: a rank rule that
  reproduces arrival order prints 0.00 and renders as NOT MATERIAL.

**3 and 4, registered together — run participation, and posted limit entries.**

`run_census` is the newest instrument here and **nothing has been built from
it**: 67,814 runs, 122.85/session, median $42/100 shares, and **the top 5% carry
56.5%**. `run_signal` already established that predicting a run start does not
work (base rate 0.108%, best volatility-independent feature 1.94×).

So invert it: **enter into confirmed extension and accept a poor fill**, on the
argument that catching a small share of the big runs beats catching typical ones
— which by construction earn ~nothing after friction. MCL's losing population is
70.7% pops-then-fades at −$22.73; the profitable 29.3% dips first. This is the
"**the fill, not the filter**" question already named as next and never tested.

Pair it with **posted limit vs marketable entries** — a measured **3× cost
swing** (≈0.0021/share passive against ≈0.0067/share marketable). These are
opposite ends of one axis, so running them apart measures neither.

To be explicit: posted limits are **not** a rescue for MCL, which is negative
gross. Please don't let this re-open it.

**5. Price the Databento `status` schema, then bucket entry outcomes on halt
state.**

The tape provably does not separate on this universe, so the only features left
are ones that are not the tape. Halt state first: nothing models LULD at all,
**36.4% of Tier 2 pauses fall 09:45–09:50**, Tier 2 pauses occur on **100% of
trading days**, and low-float gappers halt constantly. It is a feature and a
risk control at once. Price it before pulling it.

Behind it: FINRA short interest (free, bi-monthly, point-in-time by
construction, untested), and EDGAR shares outstanding — already built, but carry
the coverage figure on every number (**80.2% of symbol-days**; the uncovered 20%
passes untouched, so it is weaker than it looks, not wrong) and remember shares
outstanding is not float.

---

## Proposed `PROGRAM_INDEX.md` §7 edit

Not applied — it is yours. Suggested as items 2–6 after the existing item 1,
renumbering the rest:

```
1a. Recover real publish dates for census.csv: 401 metadata calls, FREE.
    Named "the obvious next step" in warrior_census_20260910.md §8 on
    2026-09-10 and not run. Unblocks 1b-1d.

1b. Fit a computable regime classifier against the 234 labelled recaps.
    Cold costs Cameron 16x his mean day and is 61% of the sample; MCL has
    no regime gate. Inputs listed in execution_gap_20260910.md §5.

1c. Do Cameron's named symbols beat our top-5-by-volatility ranking on the
    same date? Decides whether name selection is worth attacking.

1d. Transcribe ORWJzImSTdE and hz7vhSIXXSc. Dip buying is half his book at
    the micro pullback's risk lift and MCL does not implement it.
    (Supersedes the old §7 item 8 by making it concrete.)

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

---

## Things to refuse if they come up

Another entry-extraction pass over Cameron's recaps — censused, and entries are
not the lever (section 0). Entry filters from minute OHLCV; stop-width work; exit rescues on the losing
population; dollar-volume or liquidity floors; the Cameron flat-top /
gap-and-go / reversal set (his own census makes these his riskiest, and the
reversal's short side is not buildable on this broker); Bollinger + RSI on large
caps (−0.010% excess, t = −0.18; RSI(14) vs %b ρ = +0.911); and volume-profile
or value-area constructions on the **pre-market** window, where 1.5% tape
capture means the distribution cannot be built at all.

---

## Standing requirements on all five

Register before you run. All three friction levels, never commission-only. Two
denominators, and a disagreement is a refusal. drop-top-N on the level and the
delta, `n/a` never `$0`. Both halves, remembering an empty half is not a sign
flip. Sessions, not trades. Boundary check on any grid. And the one this project
keeps failing: **a control whose output is indistinguishable from the failure it
detects is not a control.**

**The locked holdout is still unspent. None of these five is ready to spend it.**
