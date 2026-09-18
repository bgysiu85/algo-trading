# G2 RESULT — the swing universe's round-trip cost, measured

**Created:** 2026-09-19
**Status:** RESULT. G2 cleared on one full session; see §6 before treating it as settled.
**Registered in:** `swing_preflight_20260914.md` §8, criterion G2
**Tooling:** `strategy/swing/spread_sampler.py`, `strategy/swing/spread_report.py`
**Raw report:** `var/reports/spread_report.txt`

---

## 0. The answer

| | |
|---|---:|
| Median quoted spread, regular hours | **3.65 bps** |
| Median all-in round trip (spread + IBKR tiered fees, marketable both legs) | **5.46 bps** |
| Same, on a USD 9,000 position | **USD 4.91** |
| G2 threshold | 40 bps |
| **Verdict** | **PASS** |

Every one of the 37 symbols passes G2 individually. The range is **SPY 0.26 bps**
to **SJM 14.66 bps**; no name is within a factor of two of the threshold.

**Financing is now unambiguously the dominant cost.** At 2:1 and the IBKR AU
retail USD rate of ~7.13%/yr, carry is 0.99 bps per day held, so it **exceeds
the entire round trip after 5.5 days**:

| Hold | Financing | vs the round trip |
|---:|---:|---:|
| 2 days | 1.98 bps | 0.36x |
| 5 days | 4.95 bps | 0.91x |
| 10 days | 9.90 bps | **1.81x** |
| 20 days | 19.80 bps | **3.63x** |

The pre-flight predicted this from published rates. It is now measured against
a real spread rather than an assumed one, and the conclusion strengthens: at
the horizons G5 permits (N >= 5), **the loan costs more than the trading.**

---

## 1. What was collected

| Item | Value |
|---|---|
| Source | Live IBKR quotes via IB Gateway paper, port 4002 |
| Sessions | **2026-09-18, full regular session** (09:30-16:00 ET) plus 29 min of 2026-09-17's open |
| Rows collected | 75,665 |
| Rows usable (regular hours, live) | **31,043** |
| Rows excluded, outside the session | 44,622 — all from the 09-17 overnight run |
| Market data type | **1 (live) on every usable row.** No delayed, no frozen |
| Disconnections | **none** — "the connection held for the whole run" |
| Cadence | 30 s, 37 symbols, 839 observations per symbol |

The 09-18 session alone gives a median of **3.63 bps** against the pooled
**3.65**, so the 29 minutes of 09-17 opening data — which is the widest part of
the day — moves the headline by 0.02 bps. The two are not meaningfully
different and the pooled figure is used throughout.

---

## 2. By symbol

Median quoted spread, regular hours, both sessions. `$depth` is the median
displayed dollar value at the touch, the smaller of the two sides.

| | bps p50 | | bps p50 | | bps p50 |
|---|---:|---|---:|---|---:|
| SPY | 0.26 | GOOGL | 1.43 | XOM | 2.46 |
| NVDA | 0.46 | NFLX | 1.39 | JPM | 2.60 |
| AAPL | 0.90 | SCHW | 1.91 | HAL | 2.96 |
| WMT | 0.93 | AMZN | 1.98 | BEN | 3.04 |
| NEE | 1.24 | MSFT | 2.02 | META | 3.28 |
| | | PG | 2.05 | AMD | 3.49 |

...rising through PFE 3.64, UNH 3.73, MOS 4.03, CRM 4.19, ROKU 4.56,
GILD 4.67, JNJ 5.56, CAT 5.87, MRVL 6.16, FDX 6.90, WYNN 7.31, ALK 7.44,
GS 7.50, CLF 8.03, ETSY 8.26, AA 8.83, ALB 9.04, KMX 10.24, to **SJM 14.66**.

**Depth is no longer the binding constraint.** Every symbol's median displayed
depth at the touch exceeds a USD 9,000 position. The five names flagged in the
29-minute sample — ALK, BEN, ETSY, KMX, MOS — were an artefact of the opening
half-hour, when the book is thinnest. Over a full session all of them clear it.

---

## 3. Time of day — the finding worth acting on

| ET half-hour | bps p50 | vs pooled |
|---|---:|---:|
| **09:30** | **7.98** | **2.19x** |
| 10:00 | 4.58 | 1.25x |
| 10:30 | 4.01 | 1.10x |
| 11:00 | 3.94 | 1.08x |
| 11:30 | 3.61 | 0.99x |
| 12:00 | 3.31 | 0.91x |
| 12:30 | 3.21 | 0.88x |
| 13:00 | 3.04 | 0.83x |
| 13:30 | 3.04 | 0.83x |
| 14:00 | 3.31 | 0.91x |
| 14:30 | 3.04 | 0.83x |
| 15:00 | 3.03 | 0.83x |
| **15:30** | **2.96** | **0.81x** |

**The opening half-hour costs 2.7x the closing half-hour**, and the decay is
monotone through 13:00 before flattening. A candidate that enters on the open
pays 7.98 bps; one that enters after 11:00 pays under 4.

This is a free lever and it should be registered as one before any entry logic
assumes an open fill. It is also a caution: the 2026-09-17 sample looked like
8.00 bps precisely because it was all opening data.

---

## 4. What it does to the pre-flight's arithmetic

`swing_preflight_20260914.md` §4 used assumed costs of 10 / 20 / 40 bps.
Replacing them with the measured 5.46 bps all-in:

| N | Median move | Cost, cash-funded | Cost, 2:1 levered |
|---:|---:|---:|---:|
| 2 | 1.55% | **3.5%** | 4.8% |
| 3 | 1.92% | **2.8%** | 4.4% |
| 5 | 2.53% | **2.2%** | 4.1% |
| 10 | 3.73% | **1.5%** | 4.1% |
| 20 | 5.49% | **1.0%** | 4.6% |

The pre-flight's assumed range put this at 4-16% of the median move at N >= 5.
**Measured, it is 1.0-2.2% cash-funded.** The intraday programme's comparable
figure is roughly **75% of an average winning trade**.

Note what the right-hand column does: levered, the total lands in a flat
4.1-4.8% band at every horizon, because financing grows with N at almost
exactly the rate the move does. **Leverage cancels the horizon advantage.**
That is a new observation, and it argues for cash-funded at the longer holds.

### §3.5 of the pre-flight, corrected

| Component | Assumed (2026-09-14) | **Measured (2026-09-19)** |
|---|---:|---:|
| Spread crossing, large cap | 1.0 - 3.0 | **3.65 universe median** |
| All-in, large cap | 2.5 - 5.5 | **5.46 universe median** |
| All-in, mid cap | 7 - 20 | covered by the same 5.46 |

The large-cap assumption was good — the measurement lands at the top of its
range. **The mid-cap assumption was too pessimistic by roughly 2-4x**, because
it was built from Collver's 2013 small-cap data, the only public source left,
and those names are not these names.

---

## 5. G2, formally

> **G2. Cost measured, not assumed.** Quoted spread and depth at the touch
> measured for the candidate universe from live IBKR quote sampling across
> several sessions. Model the full quoted spread. **Fails if the measured
> all-in round trip exceeds 40 bps.**

**Measured all-in: 5.46 bps. G2 PASSES**, by a factor of seven.

The full quoted spread was modelled with no price-improvement discount, per
§3.2 — an IBKR Pro account routes to exchanges and does not receive the
wholesaler internalisation that makes published effective spreads look tight.
So this is the conservative reading, not a favourable one.

---

## 6. What could be wrong with this

- **One full session.** G2's text says "several sessions". 2026-09-18 was a
  single ordinary Friday; a volatile day, an index rebalance, or a macro print
  would widen everything. The pre-flight already established that gap sessions
  are exactly when spreads blow out, and none is in this sample. **This is the
  reason to call G2 provisionally cleared rather than closed.**
- **It measures the QUOTE, not a fill.** This is the correct input to a cost
  model and is not a measurement of slippage. Only real fills measure slippage
  — that is what `common/friction_quotes.py` does, and it needs trades in these
  names before it can say anything.
- **Snapshots on a 30-second cadence** are an unbiased sample of the spread
  over time, but not the spread at the moments a strategy would trade, and they
  under-represent brief dislocations entirely.
- **Displayed depth is not available depth.** Hidden and reserve size cuts in
  our favour; the book also disappears faster than it displays when it matters.
- **No impact model.** A marketable order moves the book and nothing here
  prices that.
- **The fee side is scheduled, not observed.** 0.0138/share round trip comes
  from IBKR's published tiered schedule plus the Cboe take fee, not from a
  statement. Whether Australian GST applies to US equity commissions is still
  unverified and would add 10% to the fee component — about 0.1 bps.

---

## 7. What this unblocks, and what it does not

**Unblocked.** G2 was the last gate standing between the pre-flight and a
candidate spec. G1 (long-only, market-relative), G3-G7 are registered and
answerable in code. A spec can now be written.

**Still blocking.** **G8** — the point-in-time universe. The pre-flight's own
36 names are 100% survivors, which is fine for magnitude and dispersion and
**not fine for any strategy result**. Historical index constituents have no
obvious free source and this has not been solved.

**Unchanged.** §6 of the pre-flight still governs: on 10.3 years, an outright
directional strategy worth under ~20%/yr is undetectable, and market-relative
drops that floor to ~3%/yr. Cheap trading does not make a weak edge visible.

### Recommended next registrations

1. **Entry-time-of-day as a parameter, not an assumption.** §3 measures a 2.7x
   swing across the session. Any candidate should state when it enters and pay
   that bucket's spread, not the pooled median.
2. **Cash-funded as the base case at N >= 10.** §4 shows leverage cancelling
   the horizon advantage. Report both, per G3, but do not default to 2:1.
3. **A second and third session before G2 is called closed**, ideally including
   one visibly volatile day.
