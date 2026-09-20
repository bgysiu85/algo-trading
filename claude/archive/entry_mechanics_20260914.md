# The entry mechanics of MCL and MC5

**Date:** 2026-09-14 · read from the code, not from documentation
**Source:** `strategy/mcl/mcl.py`, `strategy/mc5/mc5.py`, `common/tv_screener.py`

---

## MCL: five clauses, four of them sign tests

From `signals()`, on 1-minute bars. The entry is the `and` of all five, and the
fill is at that bar's close.

| clause | code | what it is |
|---|---|---|
| MACD over signal | `macd > macd_sig` | **sign only** — any margin |
| MACD positive | `macd > 0` | **sign only** — the only absolute number is zero |
| MFI rising | `mfi > mfi.shift(3)` | **sign only** — `rising()` is `s > s.shift(3)` |
| RSI rising | `rsi > rsi.shift(3)` | **sign only** |
| volume | `volume >= prev_vol * 3.0` **and** `prev_vol >= trail_avg * 0.5` | **ratio only** |

`trail_avg` is the 60-bar mean of volume. The two halves together open at
1.5× that mean.

**No clause asks how much stock is trading, how wide the spread is, or how
large the price move is.** Every term is either a sign or a multiple of the
tape's own recent volume.

### The volume test gets easier as the tape gets quieter

`volume >= prev_vol * 3` has the previous bar in its denominator, so **a dead
minute is what makes the next minute qualify.** 600 shares after 200 is a 3×
volume surge by this definition. The `trail_avg` floor offsets part of it, but
it is a fraction of an average computed on the same dead tape, so it scales
down with everything else rather than setting a bottom.

## MC5: three clauses, and no volume condition at all

On 5-minute bars resampled from the same tape.

| clause | code | what it is |
|---|---|---|
| RSI rate of change | `rsi_roc >= 5.0` | **magnitude** — least-squares line over 3 bars, as % of its own start |
| EMA cross | `ema9 > ema21` | sign only |
| MACD over signal | `macd > macd_sig` | sign only — and MC5 does **not** require MACD > 0 |

`signals()` reads only `close`. **Volume appears once in the entire module**,
writing `vol` into a log row. Whatever MCL's volume ratio is worth, MC5 does
not have even that.

The RSI rate-of-change is the one real magnitude test in either strategy — and
it is a magnitude of RSI, not of price or of size.

## Every absolute number is in the screen, and it is checked once

| gate | value |
|---|---|
| pre-market change vs prior regular close | ≥ +20% |
| price | $2 – $25, inclusive |
| cumulative pre-market volume | ≥ 100,000 shares |
| watchlist cap | top 40 by change, ties by symbol |

**This is the gap.** A name clears 100,000 shares and +20% at 06:05 and joins
the watchlist. MCL then watches it until 09:30 and **nothing re-checks the
volume**. An entry at 08:50 on a bar of a few hundred shares, three hours after
the move that qualified the name, satisfies every rule in the system.

## What got through, measured

The 482 entries in `var/reports/entry_features_entries.txt`, at the entry bar:

| | lowest quarter spans | smallest seen |
|---|---|---|
| dollar volume, that bar | $2,655 – $145,881 | **$2,655** |
| dollar volume, session to date | $7,789 – $1,261,693 | **$7,789** |
| MACD above its signal | 0.00 – 0.01 | 0.00 |
| bar volume ÷ 60-bar mean | 1.85 – 3.68 | 1.65 |
| prev volume ÷ 60-bar mean (floor 0.50) | 0.50 – 0.79 | 0.50 |

A quarter of entries fired on a bar trading under $146,000 and the thinnest on
$2,655. A quarter had MACD above its signal by less than a hundredth — not a
trend, a crossing.

*Population caveat: these 482 come from `var/state/traded_pairs.json`, a
related population to the 3,955 point-in-time trades, not the same one.*

## The uncomfortable counter-evidence

All of the above says the rule **cannot tell a liquid bar from a dead one**. It
does not say a liquidity floor would help, and what has been measured points
the other way.

`dollar_vol_session` was bucketed against outcome and came out **WEAK** — ends
differing by more than friction in both halves, in the direction that *more*
dollar volume goes with *worse* net:

| half | quietest quarter | 2nd | 3rd | busiest quarter |
|---|---|---|---|---|
| early | +2.53 | +3.24 | (5.36) | (6.12) |
| late | +13.28 | +3.94 | (3.57) | (8.12) |

WEAK and not CANDIDATE because the middles do not line up in both halves, and
two ends differing is what noise looks like. It is not a rule. It is the only
measurement on the question, and it points away from "these entries are bad
because the volume is light."

Both can be true: the rule is **structurally** blind to liquidity, and
thresholding liquidity is **not** what fixes the P&L.

## What would settle it

The entry passes or fails on five booleans and nothing records *by how much*.
An instrument that logs, for each of the 3,955 point-in-time trades, the margin
by which every clause passed — MACD over signal, RSI and MFI over their 3-bar
reference, volume over 3×prev, prev over half the mean — beside the absolute
shares and dollars on that bar, answers it directly:

> **how many entries cleared by a hair, and did the ones that cleared by a mile
> do any better?**

One run over the tape already on disk, same shape as the shares-outstanding
instrument: every margin printed, bucketed against outcome, both halves,
nothing ranked, pre-registered before the run.
