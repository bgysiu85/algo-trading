# Swing pre-flight — liquid US large/mid caps, 2-20 day holds

**Created:** 2026-09-14
**Status:** PRE-FLIGHT MEASUREMENT. No strategy was designed, coded, or tested.
**Prompted by:** Ben's 2026-09-14 reframe — open the discussion on swing trading, given
intraday results.
**Governing standards:** `PROGRAM_INDEX.md` §4.
**Pattern followed:** `orb_preflight_xnas.md` — measurements and go/no-go criteria fixed
BEFORE any entry logic exists.

---

## 0. The verdict, in three lines

1. **The cost objection dies.** At 2-20 day holds in liquid large/mid caps, a realistic
   round trip is **2-16% of the median absolute move**, against roughly **75%** in the
   intraday small-cap programme. Cost is no longer the thing that kills the strategy.
2. **A new cost takes its place, and it is bigger than the spread.** At IBKR Australia's
   retail USD margin rate of **~7.13%**, leverage costs **~1 bp per day held**. Past about
   four days at 2:1, the loan costs more than the entire round trip.
3. **The real barrier is statistical, not economic.** With 10.3 years of data, an **outright
   directional** strategy worth less than **~20% a year is undetectable** — and a bigger
   universe does not fix it. A **market-relative** construction drops that floor to
   **~3% a year**. That is not a style preference. It is the difference between a programme
   that can produce evidence and one that cannot.

---

## 1. What was measured, and from what

| Item | Value |
|---|---|
| Source used | **TradingView daily bars** via `TV_Remix_MCP.get_ohlcv` |
| Independent cross-check | Alpha Vantage `TIME_SERIES_DAILY` (free, raw) — SPY and NFLX matched **to the tick, including volume** |
| Universe | 36 stocks (12 MEGA / 12 LARGE / 12 MID) + SPY, sector- and volatility-stratified |
| Span | 2016-05-10 -> 2026-09-11, ~2,600 bars/symbol, **95,850 symbol-days** |
| Split adjustment | **Verified**, not assumed — all 20 observations of \|1-day return\| > 25% individually investigated and confirmed genuine news events |
| Dividend adjustment | **Not applied.** Effect **bounded by measurement**, not waved off: back-adjusted the two highest-yield names (PFE 6.20%, DUK 3.58%) properly and re-ran. Every statistic moved **< 0.2 pp**; stop-through rates moved **<= 0.04 pp** |
| Bar integrity | 0 violations of `low <= open,close <= high`; 0 non-positive prices; 0 duplicate symbol-dates; 0 calendar gaps > 7 days |

**Measured vol spread is deliberate and wide:** PG 19.1% annualised to ROKU 72.7%. A
mega-cap-tech-only sample would have badly understated dispersion, which is the number the
whole cost argument turns on.

**Deliberately absent: any mean return, t-statistic, or significance test on the raw
panel.** The universe is 100% survivors (§8) and the windows overlap. Reporting a drift
figure off this panel would be exactly the class of error `PROGRAM_INDEX.md` §4 exists to
prevent.

---

## 2. The numerator — how big is the move

Absolute forward move, `|close[t+N]/close[t] - 1|`, in %. All 36 stocks, overlapping windows.

| N | n | p10 | p25 | **p50** | p75 | p90 | p95 |
|---|---|---|---|---|---|---|---|
| 2 | 93,173 | 0.26 | 0.69 | **1.55** | 3.01 | 5.16 | 7.00 |
| 3 | 93,137 | 0.33 | 0.86 | **1.92** | 3.70 | 6.38 | 8.70 |
| 5 | 93,065 | 0.44 | 1.14 | **2.53** | 4.89 | 8.32 | 11.26 |
| 10 | 92,885 | 0.66 | 1.67 | **3.73** | 7.11 | 11.82 | 15.69 |
| 20 | 92,525 | 0.98 | 2.51 | **5.49** | 10.23 | 16.86 | 22.68 |

Median by tier at N=5: **MEGA 2.05% / LARGE 2.40% / MID 3.43% / SPY 1.19%.**
Mid-caps move ~1.65x mega-caps at every horizon and every percentile; single names move
~2.1x SPY. The ordering MEGA < LARGE < MID holds across all 30 horizon x percentile
comparisons without exception — which is just the volatility ordering, and should not be
read as anything more interesting.

**Maximum favourable excursion** (the honest numerator — best a perfect exit could capture,
`max(high[t+1..t+N])/close[t] - 1`), medians: N=2 **1.53%**, N=5 **2.59%**, N=10 **3.91%**,
N=20 **5.93%**.

Two things in the MFE numbers are worth carrying forward:

- **MFE adds essentially no information below N=10.** Median MFE ~= median \|fwd\| at N=2-5.
  Verified rather than trusted: `MAE <= fwd <= MFE` holds with **zero violations** across all
  93k observations, and three random symbol-dates were recomputed by brute force to 1e-12.
  It is a real coincidence of scale, not a bug — but it means MFE-based reasoning only starts
  to pay at N >= 10.
- **The window is close to symmetric.** Median adverse excursion is **0.79-0.89x** the median
  favourable excursion at every horizon. That is what an entry with no edge looks like. It is
  the baseline any candidate has to beat.

---

## 3. The denominator — what a round trip actually costs

### 3.1 The public cost data this project relied on no longer exists

**The SEC stopped publishing spread and depth data after December 2013.** Its current
market-structure files are partitioned exactly the way we want — market cap x price x
volatility deciles, through June 2026 — and contain **no spread and no depth metric**. The
only SEC file that ever carried them stops at 2013-12-31.

> Anyone quoting "SEC DERA" for a 2026 large-cap spread is quoting 13-year-old data.
> That includes this project's own prior citations.

Best available figures, all labelled:

| Source | Window | Figure |
|---|---|---|
| Collver, SEC DERA (2014) — caps out at <$5bn, so **no true large-cap bucket** | full-year **2013** | $2-5bn / $20-39.99: quoted 1.99c (6.6 bps), **effective 1.29c (4.5 bps)** |
| SEC DERA thinly-traded NMS paper | Q4 **2017** | ADV > 100k shares: median quoted **$0.04 / 19 bps**, ~990 shares at the inside each side |
| Nasdaq (secondary, no stated window) | pub. **2024** | S&P 500 portfolio-weighted quoted spreads ~**1.0-4.5 bps** |

### 3.2 The effective-spread trap — this one cuts against us

Effective spread is far below quoted spread **because of wholesaler price improvement under
payment for order flow** — and an IBKR Pro account does not receive it.

| Venue type | Effective/quoted ratio | Orders price-improved |
|---|---:|---:|
| Wholesalers (PFOF) | 0.76 (S&P 500 ~0.53) | 65.7% |
| **Exchanges — where IBKR Pro routes** | **0.97** | **9.5%** |

*(Dyhrberg & Shkilko, Rule 605 data 2019-2022; academic working paper, secondary source.)*

**Model the full quoted spread per round trip (E/Q ~ 0.95-1.0).** Do not apply Collver's
effective/quoted ratio to our own fills — that ratio is mostly other people's internalised
retail flow. Any tighter number requires proof from Ben's own fills.

### 3.3 IBKR commission — the Tiered headline is misleading

Verified from IBKR AU pricing, 2026-09-14. Tiered is **USD 0.0035/share, USD 0.35 minimum
per order** — but under Tiered the **exchange take fee of USD 0.0030/share is passed through**
(Cboe BZX, effective 2026-09-01), so a marketable Tiered order is really ~**0.0067/share**.
A passive fill earns a **0.0016 rebate**, making the same order ~**0.0021/share**. That is a
**3x swing driven purely by order type** — and it points the same direction as
`external_evidence_20260911.md` §2, where four independent literatures found the money
accrues to whoever posts liquidity rather than takes it.

Worked round trips (buy + sell, both legs marketable, Tiered):

| Position | Tiered take | bps | Tiered post | Fixed | Fixed bps |
|---|---:|---:|---:|---:|---:|
| 100 sh @ $150 = $15,000 | $1.67 | 1.11 | $0.75 | $2.33 | 1.55 |
| 100 sh @ $40 = $4,000 | $1.44 | 3.61 | $0.52 | $2.10 | 5.25 |

**Two easily-missed traps.** (a) The per-order minimum is charged again for each day a GTC
order persists — "orders that persist overnight will be considered a new order for purposes
of determining order minimums." A resting limit that sits five days costs USD 1.75, not 0.35.
(b) **IBKR Lite at 0.000/share is US residents only** and is not available on this account.

### 3.4 Financing — the dominant swing cost, and it is not the spread

IBKR AU quotes **5.130%** for USD balances under 100k (BM + 1.5%), **plus a stated 2%
IBAU surcharge on all non-AUD borrowings for retail clients**. Effective rate for this
account: **~7.13% p.a.**, not 5.13%.

| Hold at 2:1 | 2 days | 5 days | 10 days | 20 days |
|---|---:|---:|---:|---:|
| Financing cost, bps of position | **2.0** | **5.0** | **9.9** | **19.8** |

**A 10-day leveraged hold in a large cap costs ~9.9 bps in financing against ~3.5 bps in all
trading friction combined** — financing is roughly **3x** spread-plus-commission, and unlike
trading cost it **scales linearly with hold length**.

> **The AUD trap.** IBKR does not auto-convert. Buying USD stock against an AUD cash balance
> creates a **USD margin loan for the full position value** at ~7.13%, even in an
> economically unlevered account. A "cash-funded" position financed that way costs ~19.8 bps
> over 10 days instead of zero. Convert AUD->USD explicitly on IDEALPRO first. Verify against
> an actual statement.

FX conversion itself is immaterial if done once: ~1.9-2.3 bps of capital one way, under
0.1 bp per round trip amortised over 50+ trades.

### 3.5 All-in estimate

Position USD 8,000-10,000 (realistic at 3-5 concurrent on a USD 22,000 account), Tiered,
marketable both sides, single-day order life.

| Component | Large cap ($100-200) | Mid cap ($30-80) |
|---|---:|---:|
| Spread crossing (full quoted, per round trip) | 1.0 - 3.0 | 4.0 - 12.0 |
| Impact beyond the touch | 0 - 1.0 | 1.0 - 5.0 |
| Commission, both legs | 0.5 - 0.9 | 0.9 - 1.6 |
| Exchange + regulatory + clearing | 0.6 - 0.8 | 1.1 - 1.7 |
| FX amortisation | < 0.1 | < 0.1 |
| **All-in round trip, cash-funded** | **~2.5 - 5.5 bps** | **~7 - 20 bps** |
| **Add if 2:1 leveraged** | **+0.99 bps per day held** | **+0.99 bps per day held** |

For comparison: Ben's measured small-cap cost is **USD 8.46-8.92 per 100-share round trip**
in names with ~79-83 bps median spreads. **A large-cap round trip at these sizes runs ~USD 3
and ~3.5 bps — roughly an order of magnitude cheaper.**

---

## 4. The cost-to-move arithmetic — the question this pre-flight was asked

**Moves MEASURED (§2). Costs ASSUMED at three levels (§3.5 brackets them).**

| N | Median \|move\| | cost @10bp | @20bp | @40bp |
|---|---|---|---|---|
| 2 | 1.55% | 6.5% | 12.9% | 25.9% |
| 3 | 1.92% | 5.2% | 10.4% | 20.8% |
| 5 | 2.53% | **3.9%** | **7.9%** | 15.8% |
| 10 | 3.73% | **2.7%** | **5.4%** | 10.7% |
| 20 | 5.49% | **1.8%** | **3.6%** | 7.3% |

**At N >= 5, cost is 4-16% of the median move. At N = 10-20, 2-11%.**

Against the intraday programme, where friction of USD 8.46-8.92 per 100-share round trip
runs against an average win of 11.9c/share (**USD 11.90 per 100 shares**) — **~75% of an
average winning trade**.

**That is a necessary condition, and it is met with room to spare. It is not a sufficient
condition, and none of this says an edge exists.**

---

## 5. The risk that replaces intraday stop risk

Swing trades cannot be protected by a software-managed stop across the close. Long position,
stop X% below prior close, "through" = next **open** below the stop.

| Stop | Through rate | ~1 in N sessions | Median realised loss | p90 | Worst |
|---|---:|---:|---:|---:|---:|
| 3% | **1.91%** | 52 | **-4.2%** | -8.2% | -29.7% |
| 5% | **0.63%** | 160 | **-6.8%** | -12.3% | -29.7% |
| 8% | **0.21%** | 480 | **-10.5%** | -17.4% | -29.7% |

By tier at a 5% stop: MEGA 0.44% (1 in 228), LARGE 0.55% (1 in 180), **MID 0.89% (1 in 113)**.

**Holding 5 positions overnight, a 5%-stop gap-through happens somewhere in the book roughly
every 32 trading sessions — about every six or seven weeks.**

Supporting gap distribution, all 36 stocks, `open[t+1]/close[t] - 1`: p1 **-4.08%**,
p5 -1.80%, p50 +0.05%, p95 +1.88%, p99 +4.28%, min **-29.66%**, max +37.51%.
Down-gaps worse than -2% / -3% / -5% / -8%: **4.16% / 1.91% / 0.63% / 0.21%** of sessions
(MID: 6.05 / 2.88 / 0.89 / 0.32).

Two consequences that must be carried into any sizing rule:

1. **The stop level is not the max loss.** At a 5% stop the planning assumption for worst
   case is roughly **-12%** (p90), not -5%.
2. **IBKR auto-liquidates rather than issuing margin calls.** A gap that takes equity below
   the 25% maintenance level can be liquidated before Ben sees it — and the gap sessions in
   this table are exactly the sessions where spreads widen and the 20 bps cost assumption
   fails.

*(Ex-COVID, stop-through rates fall to 1.59 / 0.46 / 0.14% and medians move under 0.1 pp —
the result is not a COVID artefact.)*

---

## 6. The statistical power finding — and the design it forces

This is the part that changes what should be built, and it was not anticipated.

**Measured inputs:** signed N-day return SD (5.47% at N=5 pooled), and average pairwise
correlation of same-date N-day returns across the 36 names, computed on **non-overlapping**
anchors: **rho = 0.25-0.30 at every horizon**.

With equicorrelated names, effective sample size converges to **(non-overlapping periods) /
rho** as the universe grows. **Adding names does not help.**

### Minimum detectable edge, 80% power, 5% two-sided, 10.3 years of data

| N | non-ovl dates | **Directional (raw)** | | **Market-relative** | |
|---|---:|---:|---:|---:|---:|
| | | rho | **floor, %/yr** | rho | **floor, %/yr** |
| 2 | 1,124 | 0.273 | **19.8%** | 0.009 | **3.1%** |
| 3 | 749 | 0.249 | **18.6%** | 0.010 | **3.1%** |
| 5 | 449 | 0.263 | **19.6%** | 0.009 | **3.1%** |
| 10 | 224 | 0.299 | **20.9%** | 0.009 | **3.1%** |
| 20 | 112 | 0.268 | **20.2%** | 0.009 | **3.1%** |

*(Market-relative = each name's return minus the cross-sectional mean that day — what a
long-vs-market or dollar-neutral construction earns. Residual correlations are debiased for
the mechanical -1/(m-1) that demeaning imposes.)*

**Read it plainly.** A **long-only directional** swing strategy on this data must be worth
**more than ~20% a year** before ten years of history can distinguish it from zero — and
buying more data years is the only lever, because universe size is not one. A
**market-relative** construction removes the common factor and drops the floor to **~3% a
year**, which is a target a real strategy might actually hit.

**The same result from the live side:** at 5 concurrent positions and a 5-day hold (252
trades/year), detecting a 0.5%-per-trade edge takes **~1,900 trades, or 7.6 years of live
trading**. The intraday programme could generate that many trades in weeks. Swing cannot.

> **This is the single most important thing in this document.** It says the construction
> decision — cross-sectional/market-relative versus outright directional — is not a matter
> of taste. It decides whether the programme can produce evidence at all. It also means the
> `PROGRAM_INDEX.md` §4 both-halves temporal holdout gets **dramatically** harder: halving
> 449 non-overlapping 5-day windows leaves 224 per half.

*Caveat: the annual-return floors assume a fully-deployed book. A strategy in the market
only part of the time takes fewer trades at a higher per-trade edge; the annualised floor
is roughly preserved, the per-trade floor is not.*

---

## 7. Cross-sectional dispersion — the room a selector has

On each date, across the 36 names:

| N | median (p90 - p10) | median (top-decile mean - bottom-decile mean) |
|---|---:|---:|
| 5 | **8.78%** | **14.01%** (top +7.52%, bottom -5.79%) |
| 10 | **12.61%** | **20.15%** (top +11.22%, bottom -8.03%) |

**These are the numbers most likely to be misused.** They are what a selector with *perfect
hindsight on that date* could have captured — an **upper bound**, not an available edge. The
honest planning assumption is that an unskilled selector captures **zero** of it. A 36-name
cross-section also makes the daily decile ~4 names, so these are indicative, not a calibrated
S&P 500 figure.

They are recorded because a market-relative construction (§6) earns out of exactly this
spread, and it is worth knowing its size.

---

## 8. Go / no-go criteria — fixed now, before any strategy logic

Per `PROGRAM_INDEX.md` §4, *register before you run*. These are committed before a single
line of swing strategy code exists.

| # | Criterion | Fails if |
|---|---|---|
| **G1** | **Construction.** A candidate is either market-relative (cross-sectional rank, long-vs-market, or dollar-neutral) **or** outright directional with a pre-registered target above the §6 detectability floor. | An outright directional candidate targets < 20%/yr. Its result is then **uninterpretable**, not merely weak, and must not be reported as evidence either way. |
| **G2** | ~~**Cost measured, not assumed.**~~ **CLEARED 2026-09-19** on one full session: measured all-in round trip **5.46 bps** against a 40 bps threshold, every symbol passing individually. See `swing_g2_RESULT_20260919.md`. | Provisionally cleared, not closed -- one session, and G2's own text says *several*. |
| **G3** | **Financing charged, always, and stated.** Every P/L reported **both** cash-funded and at 2:1 with **7.13%/yr charged per day held**. | A candidate is profitable only when financing is ignored. |
| **G4** | **Gap risk in the sizing rule.** Max-loss-per-position assumption = stop level **plus the p90 extra** (~7.3 pp at a 5% stop), not the stop level. | A risk model that treats the stop as the max loss. |
| **G5** | **Horizon floor, N >= 5.** | A candidate with median hold < 5 days, unless G2 measures cost at the low end (<= 10 bps). Below N=5 cost is 5-26% of the median move and MFE adds no information over \|fwd\| (§2). |
| **G6** | **Its own locked holdout.** A swing temporal holdout cut and locked **before** the first swing result exists, enforced in code the way `holdout.split_sessions` is. The intraday `holdout.json` is not it. | A holdout cut after seeing a result, or spent by a second candidate. |
| **G7** | **Distribution of specs, not a chosen cell.** Report where the chosen parameter sits in the full distribution, and report the **equal-weight ensemble** alongside it. | Only the best cell is reported. |
| **G8** | **Point-in-time universe.** Index constituents as of each date. | Today's ticker list used as history. This pre-flight's own universe is 100% survivors (§9) — acceptable for magnitude and dispersion, **not** for any strategy result. |

---

## 9. What could be wrong with this

**Survivorship is the biggest single defect.** All 36 tickers were chosen in 2026 from names
that exist in 2026. Not one delisting, bankruptcy, or acquisition-at-a-discount is in the
sample. The one name that did corporate-action away (IPG) was dropped for an unrelated data
reason, leaving the sample **100% survivors**.

- **Do not trust:** any mean or drift figure. The uniform +0.05% median overnight gap across
  all three tiers is exactly where survivorship lands. No mean return is reported here, and
  nothing in this document should be used to justify a long bias.
- **Usable:** absolute move size, MFE, dispersion, and the gap/stop-through distributions —
  these measure magnitude and spread, not direction. A survivor and a casualty both have
  2-5% weekly moves and both gap. Excluding the casualties makes these **conservative**:
  real survivorship-free gap tails would be **worse**. **The risk side of this report is an
  optimistic bound.**

**Other limits, stated:**

- **Tier labels are present-day and static.** CLF is labelled MID at ~$6bn today but was a $3
  stock in 2016; AMD is labelled LARGE but is mega-cap by 2026. A mild look-ahead in the
  *labelling*, not in the price data. It slightly inflates the MID/MEGA gap.
- **10.3 years is close to one macro regime.** One severe crash (COVID), one bear year
  (2022), a great deal of bull market. It does not contain 2000-02 or 2008.
- **No liquidity, borrow or halt modelling.** Median dollar volume is >= $85M/day for every
  name so capacity is not binding at this size — but the §5 gap sessions are precisely when
  spreads widen and the cost assumptions fail.
- **Both vendors could share an upstream.** TV Remix and Alpha Vantage agreeing to the tick
  including volume is strong evidence, but would not catch an error common to a shared
  consolidated-tape provider.
- **Costs in §3 are researched, not measured.** They are the best public figures available
  and several are stale by construction (§3.1). G2 exists because of this.
- **Unverified and worth checking in-account:** whether Australian GST (10%) applies to IBKR
  US *equity* commissions (it demonstrably does to FX commissions); the IDEALPRO AUD.USD
  typical spread (IBKR publishes none); whether the 7.13% figure — arithmetic on a quoted
  tier plus a stated surcharge — matches an actual statement.

---

## 10. What this does not say

- **Not that swing trading works.** No signal was tested. §2 says the moves are big enough
  for costs not to eat them; that is all.
- **Not that the §7 dispersion is capturable.** It is a perfect-hindsight bound.
- **Not a P/L, and not a recommendation to build anything yet.**
- **Not that the intraday programme should stop.** MCL remains the only look-ahead-free
  evidence in the project, and §7 item 1 of `PROGRAM_INDEX.md` — validating the simulated
  screen against live watchlists — is unaffected by any of this.

---

## 11. Open items this creates, in priority order

1. ~~**Measure real large/mid-cap spreads.**~~ **DONE 2026-09-19.** The live
   IBKR sampler ran a full regular session; `strategy/swing/` holds the tooling
   and `swing_g2_RESULT_20260919.md` the result. Measured **5.46 bps** all-in.
   Two more sessions, ideally including a volatile one, before G2 is closed.
2. **Decide G1: market-relative or directional.** §6 makes this the highest-leverage decision
   in the programme, and it is a decision, not a measurement.
3. **Source a point-in-time universe** (historical index constituents). This is the
   survivorship problem in §9 and it is a data-acquisition question with no obvious free
   answer. It blocks G8.
4. **Re-check amended SEC Rule 605 filings from October 2026.** Compliance date was
   2026-08-01; the first reports cover August 2026 and are due during September 2026. It is
   the best forthcoming public source for retail-relevant effective spreads by stock group
   and order size — an independent cross-check on item 1.
5. **Verify in-account:** whether IBKR has implemented FINRA Notice 26-10 (their AU pages
   still reference the USD 25,000 PDT minimum, and the phase-in runs to 2027-10-20 — though
   PDT is largely moot for 2-20 day holds anyway), and whether GST applies to equity
   commissions.
6. **Note for the intraday programme:** §3.3's 3x add/take fee swing is independent
   corroboration of `external_evidence_20260911.md` §9 item 3 — posted limit entries instead
   of marketable. The fee schedule says the same thing the four literatures said.

---

## Appendix — artefacts

Scripts and full numeric output: `build_panel.py`, `analyse.py`, `quality.py`, `div_bound.py`,
`power.py`, `power2.py`, `results.txt`, `dividend_bound.txt`, `panel.csv.gz` (95,850
symbol-days, 36 stocks + SPY, 2016-05-10 to 2026-09-11).
