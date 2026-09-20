# Execution cost, measured from quotes — 2026-09-06

**Result: the backtests are slightly conservative on slippage, not wrong.**
Crossing the spread costs about **$1.00** per 100-share round trip against the
**$2.00** the engines charge, so MCL's +$0.33/trade is really about
**+$1.33**.

This document also records a false alarm, because how it was caught matters
more than the number. A first pass on a different tape said crossing cost
**$6.50** and that all three strategies were deeply negative. That was an
artifact of the tape, and only a cross-check found it.

---

## 1. What made this possible

`PROGRAM_INDEX` §7 item 1 had been the top open item for weeks: re-measure
friction. It was stuck at **n = 2** measured trailing-stop exits, with the
shipped estimate taken on a session that was 81% apex exits — for a
configuration that now produces ~95% trailing exits.

Two things arrived on 2026-09-06:

1. **The full IBKR Flex history** — 18,621 executions, 587 symbol-days,
   134 sessions, 2025-06-04 → 2026-08-31.
2. **A Databento plan**, and with it trade-plus-quote data for every one of
   those symbol-days.

Together: **a quote at the instant of every fill.** n went from 2 to 18,552.

Tooling: `common/flex.py`, `common/databento_fetch.py`,
`common/friction_quotes.py`.

---

## 2. Method

For each execution, take the last trade-with-quote record for that symbol at or
before the fill timestamp and read its bid and ask. Adverse is **positive** on
both sides:

```
BUY   slip_vs_touch = fill - ask      (paid above the offer)
SELL  slip_vs_touch = bid  - fill     (sold below the bid)
      slip_vs_mid   = |fill - mid|, signed the same way
```

Four risks, each handled rather than assumed: times converted from the
**measured** report timezone (Australia/Sydney, resolved by scoring IANA zones,
not by assuming an offset); matches older than 60s **dropped**, because a stale
quote gives a figure that is precise and measures nothing; `merge_asof(by=
"symbol")` so quotes cannot leak between names; and five tests pinning the sign
conventions.

---

## 3. The result

### 3.1 The two tapes disagree, and by a lot

Same 116,067 matched fills, priced against both:

| | EQUS.MINI `tbbo` | **XNAS.BASIC `tcbbo`** |
|---|---:|---:|
| median spread, MCL subset | 249 bps | **79 bps** |
| round trip, 100 shares — median | $6.50 | **$1.00** |
| — mean | $10.03 | **$0.92** |
| coverage | 97% | **100%** |
| fills at/inside the touch | 58% / 68% | **83% / 79%** |

MINI's quote is wider on **73% of the same fills**, 2.7× at the median.

### 3.2 Which to believe

**XNAS.BASIC**, on three independent grounds:

1. It includes **FINRA TRF prints** — the off-exchange volume that is most of
   small-cap trading — and prices 100% of fills against 97%.
2. **83% of buys and 79% of sells land at or inside the touch**, which is what
   a near-accurate quote looks like when someone is crossing it. MINI's
   58%/68% was cited at the time as evidence *against* its quote being too
   wide; it was pointing the other way.
3. **The decisive one — convergence from unrelated methods.** BASIC's
   half-spread is **40–41 bps**, and `PROGRAM_INDEX` documents an effective
   cross of **37–43 bps** derived months earlier from exchange fee schedules
   and tick rounding, with no quote data involved. Measured cross versus mid is
   **17.3 bps** against `trader.py`'s `LIMIT_CROSS_BPS = 20`. Two figures
   computed by completely different routes landing in the same place is
   corroboration; one figure on its own is not.

### 3.3 What the numbers say

Spread, on XNAS.BASIC:

| block | n | median spread | |
|---|---:|---:|---:|
| PRE | 17,625 | $0.0300 | **83 bps** |
| RTH | 755 | $0.0279 | **60 bps** |
| POST | 172 | $0.0800 | 87 bps |

In MCL's exact world — $2–20, pre-market, 13,857 fills:

| | per round trip, 100 shares |
|---|---:|
| modelled (`SLIPPAGE_TICKS = 1`) | $2.00 |
| **measured, median** | **$1.00** |
| **measured, mean** | **$0.92** |

---

## 4. What this changes

**Very little, and that is the finding.**

| | per trade |
|---|---:|
| MCL as published, honest fills | +$0.33 |
| corrected for measured crossing cost | **+$1.33 to +$1.41** |

MC5 and VW9 gain about $1/trade on the same basis. **None of them is rescued
from drop-top-N** — MCL is still −$722 after removing three symbols, MC5
−$2,031, VW9 −$6,068. The concentration problem is untouched and remains the
reason all three fail. Crossing cost was never the thing that was wrong.

Three specific corrections:

- **`SLIPPAGE_TICKS = 1` stays.** It overcharges by about $1 per round trip,
  which is the safe direction. No rewrite.
- **`LIMIT_CROSS_BPS = 20` stays.** Measured 17.3 bps.
- **The buy/sell asymmetry is not real.** `PROGRAM_INDEX` recorded "buys
  favourable −$0.0164/share, sells adverse +$0.0590" from one session. Measured
  across 18,552 fills it is **$0.0009 versus −$0.0009** — symmetric, and
  indistinguishable from zero. The single-session figure was noise.

And one claim made during the false alarm that also does not hold: pre-market
at 83 bps against RTH at 60 bps is **1.4×**, not the 2.7× briefly quoted from
MINI. RTH is cheaper to trade, but that is a modest edge, not the structural
argument for ORB it was presented as. `orb_strategy_spec.md` §0 should be read
with this figure rather than the MINI one.

---

## 5. The false alarm, and why it is worth recording

The first pass measured only EQUS.MINI and concluded that crossing cost $6.50
per round trip, that MCL was −$4.17/trade, and that all three strategies were
structurally unprofitable. That was reported as "the most consequential
measurement in the project".

It was wrong, and the interesting part is that **the uncertainty was correctly
identified before the conclusion was drawn**. EQUS.MINI is documented as a
partial anonymised tape whose BBO is not the NBBO; that was written into the
module docstring, into the report's own caveats, and into the write-up. The
cross-check existed *because* of that flag.

What went wrong was ordering: the headline was stated first and the caveat
attached afterwards, when the caveat was load-bearing enough that no headline
should have been stated at all until it was resolved. Eighteen project docs
were banner-ed with a claim that had to be reversed an hour later.

This is why `PROGRAM_INDEX` §4 now carries **"control the tool"** extended to
measurements, not just analyses: a quantity measured on one source is
re-measured on a second before anything is built on it. The rule already
existed for analyses. It had not been applied to data.

---

## 6. Uncertainties that remain

- **XNAS.BASIC is not the NBBO either.** It is a consolidated view built from
  Nasdaq quotes against Nasdaq, PSX, BX and TRF trades. It is closer than MINI
  and it corroborates independently-derived figures, which is why it is
  believed — not because it is official.
- **These are discretionary hotkey orders** at chosen moments. They bound what
  is achievable on this universe at these hours; they do not measure what MCL's
  marketable limits would get.
- **Four days are flagged degraded** by Databento and recorded in the archive
  manifest.
- **The stop-fill question is still open.** §3.3 gives the spread a
  software-managed stop has to cross in pre-market. Turning that into a fill
  model is a separate job with its own assumptions, and it has not been done.

---

## 7. Next steps, revised

The slippage rewrite that occupied steps 2–4 of the earlier plan is **off the
list**. What remains:

1. **Pull minute bars** for the 12,128 screened candidates and the 587 traded
   symbol-days — one price basis for both analyses. Free at L0.
2. **Convert into `bar_cache/` format** so the existing engines read it
   unchanged.
3. **Run the stage-2 leakage control** (`screener_simulation.md` §7). Until it
   runs, every screened-universe figure is an upper bound.
4. **Backtest all three on the screened universe** — the first backtest here
   whose universe was not handed to it in hindsight. Now the highest-value
   item, since crossing cost turned out not to be the problem and
   concentration still is.
5. **Re-run the manual-vs-strategy comparison** on the 219 out-of-sample days.
   The 2026-09-06 run was 100% in-sample and worthless.
6. Optionally re-run the three strategies with a spread-based slippage model to
   book the ~$1/trade. Low priority: it improves every figure by roughly the
   same amount and changes no comparison.

---

## 8. What this unlocks live

Databento Standard includes live data, covering EQUS.MINI and EQUS.SUMMARY.
**But the subscription is not economic**: $199/month against a ~$4,132 account
is 4.8% a month. The live uses below are worth having; they are not worth
$199/month, and IBKR's own real-time quotes — already paid for — can serve them.

1. **A spread gate at entry.** Less urgent than it looked when the spread
   appeared to be 247 bps, but 83 bps in pre-market against an edge of tens of
   bps still means the widest days are not worth trading.
2. **Log the quote with every order**, so friction is a standing measurement
   rather than a study. This is what stops n = 2 recurring.
3. **One definition of the universe.** The live screen uses TradingView's
   `relative_volume_10d_calc`; the backtest uses `common/screen.py`. Different
   quantities under the same name.

---

*Measured with `common/friction_quotes.py`. Reports:
`var/reports/friction_EQUS_MINI_tbbo.txt` and
`var/reports/friction_XNAS_BASIC_tcbbo.txt`. Per-fill detail:
`var/reports/priced_fills.csv`, `priced_fills_basic.csv`. None committed —
they contain real fills.*
