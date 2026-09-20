# Sizing and capacity — task #11, 2026-09-08

Three parts, run in the order the task set them: capacity, then realistic
equity, then optimisation. The answer to all three is the same shape, and it is
not the answer the task expected.

**Every size above 100 shares is worse on drop-top-5, in every cell of the grid,
for both strategies, with and without a capacity cap.** The sweep's optimum sits
on the smallest cell of the box in all four runs — which by this project's own
boundary rule is not an optimum, it is the sweep saying "smaller".

And at 100 shares the strategy is **already** at or past a 1% participation cap
on a quarter of its trades. Size is not a free parameter here. It ran out before
the study started.

Reports: `var/reports/capacity_mcl_xnas.txt` (primary, 2,411 trades),
`var/reports/capacity_mcl.txt` (replication, 555), `var/reports/sizing_sweep.txt`.
Code: `common/capacity.py` (new), `common/portfolio.py` (two new ceilings).
Bars: `bar_cache_xnas` for capacity, `bar_cache` (IB, 373 sessions) for the
sweep. Costs: tiered commission plus the measured $4.26/RT.

---

## 1. A regulatory fact that changed under us

Task #11 named ~$4,132 as the account. Under the rule this project has assumed
throughout, that account could not run this strategy at all: a margin account
under $25,000 was limited to three day trades in five business days, and MCL
averages 4.4 a session.

**That rule is gone.** FINRA Regulatory Notice 26-10 replaced the pattern-day-
trader designation and its $25,000 minimum with intraday margin monitoring,
effective **4 June 2026**, with a phase-in ending **20 October 2027**. What
replaces it is a requirement to hold maintenance margin — 25% of long market
value — throughout the day rather than only at the close, with repeated unmet
intraday deficits risking a 90-day restriction. The Reg T **$2,000** minimum
still applies to margin or short positions.

So $4,132 can day trade. Two things follow that are worth acting on:

- **Confirm with IBKR which regime this account is under.** Members have until
  October 2027 to transition and may still be applying the old PDT count.
  A strategy plan that assumes the new rule and meets the old one fails on its
  fourth trade of the week.
- At 25% maintenance, $4,132 supports about $16,500 of long market value
  intraday. That is not the binding constraint — §3 is — but it is the number
  the margin arithmetic starts from, and IBKR's house requirements on low-float
  small caps are higher than the regulatory floor.

This is a hard-rules change and no doc in this project recorded it.

## 2. What `EQUITY = 100_000` was actually hiding — less than expected

The per-session engines size with `min(MAX_SHARES=100, 40% × equity / price)`.
At the $100,000 placeholder the second arm never binds: 40% is $40,000, and at
$20 a share that is 2,000 shares against a ceiling of 100.

At $4,132 the second arm binds above **$16.53** a share, and only there.

| trades CSV | above $16.53 | share of trades | their net | total net |
|---|---:|---:|---:|---:|
| MCL | 52 of 2,413 | 2.2% | −$84 | −$1,270 |
| MC5 | 199 of 7,495 | 2.7% | +$3,036 | +$7,545 |
| VW9 5m | 116 of 1,527 | 7.6% | +$927 | −$7,633 |

So the placeholder is **nearly harmless in the per-session engines** — it touches
2–8% of trades, and for MCL those trades carry 7% of a small number. The one
place it matters proportionally is MC5, where 2.7% of trades carry 40% of the
net, and those are exactly the trades real equity would have shrunk.

The real distortion was never in `size_for()`. It is in what happens when sizing
comes from capital rather than a flat 100 — §4.

## 3. Capacity: the minutes we actually trade in

`common/capacity.py` measures, for every trade the engine took, the volume of
the minute the fill happened in — on both sides, because they are not the same
minute. Entries fire on a volume surge; exits fire on a trailing stop, which is
a falling market and frequently a thinner one.

Run twice, on two different tapes and two different trade sets. **XNAS.BASIC on
the full 2,411-trade screened set is the primary run**; the IB cache on 555
trades is the replication.

**The exit minute is the thinner of the two on 1,589 of 2,411 trades (66%)** —
and on 360 of 555 (65%) in the replication.

| binding minute, MCL, XNAS.BASIC, 2,411 trades | p10 | p50 | p90 |
|---|---:|---:|---:|
| shares printed | 4,006 | 32,154 | 169,306 |
| shares at a 1% cap | 40 | 322 | 1,693 |
| position dollars at 1% | $158 | $1,445 | $8,981 |
| implied account at 40% per position | $396 | $3,612 | $22,451 |
| **the same, corrected for tape capture** | **~$717** | **~$6,543** | **~$40,700** |

Read the p10 row, not the p50: it is the size at which a tenth of the trades are
already too big for the minute they fill in. At a 1% participation cap that is an
account of roughly **$700**.

**At the current flat 100 shares, 533 of 2,411 trades (22%) already exceed 1% of
their binding minute.** 141 exceed 5%. This is before any of the sizing work the
task asked for.

### The two tapes disagree about volume and agree about the answer

| | XNAS.BASIC, 2,411 trades | IB cache, 555 trades |
|---|---:|---:|
| exit is the thinner minute | 66% | 65% |
| 100 shares over the 1% cap | 22% | 24% |
| implied account, p10 at 1%, as printed | $396 | $406 |
| implied account, p50 at 1%, as printed | $3,612 | $7,130 |
| tape capture vs the consolidated daily bar | 0.552 | 0.831 |

Different tapes, different trade sets, different session counts — and the p10
figures land within 2.5% of each other while the headline percentages land within
two points. The median differs by 2×, which is the honest spread on this. The
conclusion replicates; the precision does not, and it should not be quoted
tighter than "a few hundred dollars at p10, single-digit thousands at p50."

### A measured fact about XNAS.BASIC that the index does not have

The capture control compares each cache against the **EQUS.SUMMARY** consolidated
daily bar — the same denominator for both runs. It returns:

- **XNAS.BASIC: p50 0.552** over 177 traded sessions — a median 55% of the
  consolidated tape, p10 0.458, p90 0.656.
- IB `bar_cache`: p50 0.831 over 214 sessions.

This is not an anomaly, it is what XNAS.BASIC *is*: Nasdaq's own feed carries
Nasdaq executions plus its TRF, not NYSE, ARCA or Cboe prints. But
`PROGRAM_INDEX.md` §3 describes it only as "TRF-inclusive" and "the tape to
prefer", which is true relative to EQUS.MINI's 4.8% and reads as "consolidated"
if you are not careful. **The number is 55%, and it is now measured.** The
project has three capture figures where it had one: EQUS.MINI ~4.8%,
XNAS.BASIC 55%, IB ~83% — the last on a different session set, so treat it as
indicative rather than a matched comparison.

Two things keep the capacity figures honest:

- **Nothing here models impact.** 1%, 5% and 10% are conventions. The report
  prices each one so the assumption is the reader's, made explicitly.
- **The correction is printed, never applied.** Capacity scales linearly with the
  cache's share of the tape, so the report states that share and leaves the
  multiplication to the reader. A correction applied silently is a correction
  nobody can check — which is the same rule that caught the ORB pre-flight
  printing an EQUS.MINI caveat over XNAS.BASIC numbers.

## 4. The sweep, and the thing it found that I did not expect

`common/portfolio.py --sweep` at $4,132, max 2 open, over MAX_SHARES ×
per-trade %, run twice — once optimistically and once with positions capped at
1% of the entry minute.

MCL, drop-top-5, no tape cap:

| MAX_SHARES → | 100 | 200 | 400 | 800 | none |
|---|---:|---:|---:|---:|---:|
| at 40% per trade | **−$1,262** | −$2,482 | −$4,531 | −$6,180 | −$6,187 |

Monotone, at every per-trade percentage, for both strategies. MC5's net is
positive across the grid but its **drop-top-5 is negative in every single cell**
— on Ben's own trade days, which is in-sample, and the top five symbols carry
the entire figure.

Then the finding worth keeping:

| MCL at 100 shares, 60% per trade | net | drop-top-5 | entries the tape shrank |
|---|---:|---:|---:|
| no tape cap | +$270 | −$1,265 | 0 |
| capped at 1% of the entry minute | **−$384** | −$1,793 | **74 of 479** |

**Capping size made the result worse.** Smaller positions on a strategy that
loses money should lose less. They lost more, which means the trades the cap
shrank were the profitable ones: the money is in the thin minutes, and the thin
minutes are precisely where size cannot go. That is the exact shape of a capacity
constraint that kills a strategy rather than merely limiting it — and it shows up
at 100 shares, not at some future scale.

At the uncapped extreme the same run buys 1,652 shares of a $2 stock and the fill
model prices every one of them at the bar's close. That number is arithmetic, not
a forecast, and it is why the cap exists.

## 5. What this closes and what it opens

**Closed.** Sizing up as a route to making any current strategy work. The
direction is monotone against it, on the level and on drop-top-5, capped and
uncapped, on both engines. Also closed: the idea that `EQUITY = 100_000` was
hiding something large in the per-session engines — it was not (§2).

**A number to carry.** Capacity for this universe, at a 1% participation cap and
40% of equity per position, is a few hundred dollars of account equity at p10 and
single-digit thousands at p50, corrected to the consolidated tape. That is a
property of the tape, not of the rules, so it binds whatever strategy eventually
has an edge — including the screener-simulated H0 that §7 of the index now ranks
first.

**Also settled.** XNAS.BASIC's capture is 55%, measured, not asserted.

**Open, in order.**

1. **Ask IBKR which day-trading regime this account is under** (§1). One
   support question; it decides whether a 4-trade week is possible at all
   before October 2027.
2. **Correct `PROGRAM_INDEX.md` §3** to carry the 55% figure alongside
   EQUS.MINI's 4.8%. "TRF-inclusive" is accurate and reads as "consolidated",
   and every capacity and dollar-volume figure measured on that cache is
   understated by 1.8× until someone knows the number.
3. **Quote depth instead of trade volume.** Participation against prints is a
   proxy for participation against the book. `tcbbo` is already in the archive
   and the friction study already reads it, so this is a smaller piece of work
   than it sounds.
4. **A measured impact curve from Ben's own larger fills.** `flex_round_trips.csv`
   has real executions at real sizes; it is the only non-assumed impact evidence
   this project owns.

**What I did not do, and why.** No impact model. A square-root law would have
turned §3's participation distribution into a dollar cost per trade and made the
sweep look decisive, and it would have been an assumption dressed as a
measurement. The participation figures are what the tape says; what they cost is
still unmeasured, and item 4 is how it stops being.

---

## Verification

25 new tests (838 passed, 2 skipped). Four sizing mutations were introduced
deliberately and all four are now caught:

- the participation cap off by 100× (it passed every test until `size_at()` was
  pulled out of the report renderer — arithmetic reachable only through printed
  text is arithmetic that is not tested)
- the tape cap applied before MAX_SHARES instead of after, which returns the
  same share count and differs only in which constraint reports itself as
  binding
- a zero-volume minute sized to zero rather than exempted, which would silently
  drop trades and make the capped and uncapped runs incomparable on trade count
- the sweep ranked on net rather than drop-top-5

The prepared-signals cache added for the sweep is asserted to change nothing:
two runs sharing one cache must agree with two runs that build their own.
