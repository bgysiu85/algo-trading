# Diversifier candidates — GEM verified and rejected, two survivors

**Created:** 2026-09-11
**Status:** SOURCE VERIFICATION. Nothing here has been backtested in this project.
**Prompted by:** the r/algotrading thread's momentum-rotation pointers (Antonacci, Faber, Clenow).
**Relates to:** `largecap_strategy_spec.md` §3.2 (L2a), `factor_correlation_result_20260911.md`.

---

## 0. Summary

Three candidates for a strategy that diversifies intraday small-cap momentum. All three are
**long-only or futures-based, unlevered, monthly** — so the **AUD 50,000 retail margin cap is
irrelevant to all of them**, which is the constraint that killed L2a.

| Candidate | Verdict |
|---|---|
| **Antonacci GEM (Dual Momentum)** | **NOT RECOMMENDED.** Out of sample since publication: **8.4%/yr vs SPY's 13.6%** — twelve years, −5.2pp/yr, and the drawdown advantage evaporated too. |
| **Time Series Momentum** (Moskowitz/Ooi/Pedersen) | **Best remaining candidate.** Peer-reviewed, *JFE* 2012, heavily replicated, genuine crisis alpha. |
| **Faber Asset Class Trend-Following** | **Lowest-effort candidate.** 5 ETFs, monthly, no shorting, no leverage. Weaker evidence, and underperforming since ~2009. |

**The most valuable thing in this document is §4** — a robustness finding about GEM that
applies directly to how this project chooses its own parameters.

---

## 1. GEM — the rules, stated correctly

Because most public implementations get this wrong.

**Antonacci's actual rule** (optimalmomentum.com, and his FAQ explicitly: *"On page 98, I
determine absolute momentum first using the S&P 500 index, since the U.S. often leads world
equity markets"*):

```
monthly, 12-month lookback, 100% in one asset:

1. Is SPY's 12-month total return > BIL's (T-bills)?      # absolute momentum, vs T-BILLS not zero
2.   If NO  -> hold AGG (bonds), 100%
3.   If YES -> hold whichever of SPY / VEU had the higher  # relative momentum
               12-month return, 100%
```

**The common misreading** — found in many public implementations including community
QuantConnect code — compares SPY vs VEU *first*, then gates the winner against T-bills. **These
are not equivalent.** They diverge whenever international equities are strong but the S&P is
below T-bills. Anyone building this must use Antonacci's ordering or they are testing a
different strategy.

**His claimed backtest:** 1950–2017, **CAGR 15.8%**, max DD **−17.8%**, Sharpe 0.96, ~1.5
trades/year. Self-published, hypothetical, and **no explicit cost deduction** — he asserts costs
*"would have been minimal"* given the trade frequency.

---

## 2. GEM out of sample — the reason it is rejected

The book was published in 2014. The cleanest independent out-of-sample study covers
**2014–2026**:

| | GEM | SPY buy-and-hold |
|---|---:|---:|
| CAGR | **8.4%** | **13.6%** |
| Max drawdown | −20% | −24% |
| Sharpe | 0.70 | 0.94 |

**Twelve years, −5.2 percentage points per year, and it gave up its drawdown edge as well.**
A 4-point drawdown improvement does not pay for 5.2 points a year of foregone return. The
downside protection that was the entire selling point did not show up.

**Why — and this is structural, not bad luck.** GEM's edge over simpler single-market dual
momentum *"comes primarily from periods when international equities outperformed the US
market."* Ex-US has underperformed the US for most of the period since 2010. **The
relative-momentum leg has spent fifteen years getting its one call wrong or late.**

Antonacci's own answer is that trend-following lags entering bull markets and that this is the
price of avoiding bear markets. That is coherent — but the 2014–2026 data show he **did not get
the compensating bear-market protection** that is supposed to justify the lag. And the COVID
crash is the clean illustration: GEM *"got into bonds just when the equity markets were
recovering."*

**Beware cherry-picked windows.** Several promotional sites quote GEM over windows that blend
the in-sample backtest period with the out-of-sample one (e.g. 1986–2026 at 12.3% CAGR), which
hides the post-2014 deterioration entirely. One site shows GEM beating its benchmark 2021–2025
and notes in the same breath that the full 2010–2025 window *"reverses that recent-window
headline."*

---

## 3. GEM in an Australian taxable account — a second, independent reason

Antonacci's own figure, offered as a positive: *"Since 1971, 73% of GEM's gains have been
long-term, while nearly 100% of its losses have been short-term."*

Read plainly for an Australian resident:

- **~27% of gains are realised inside 12 months** and forfeit the **50% CGT discount**.
- **Losses are realised short-term**, where in the US they offset ordinary income — in Australia
  capital losses are **quarantined against capital gains only**, so that softening does not exist.

**GEM is materially less tax-efficient here than it was for its US readership.** If anything in
this family is pursued, it belongs in a concessionally-taxed structure, not a personal taxable
account.

**Everything else about implementation is easy**, for the record: no PRIIPs-equivalent barrier
for Australian residents (that is an EU regulation; Australia's DDO regime attaches to products
*issued* in Australia), so SPY/VEU/AGG/BIL are all available at IBKR Australia. Commission is
**~USD 3–10/year** at ~1.5 trades. **Zero margin required** — it consumes none of the AUD 50k
borrowing capacity, leaving it all for the intraday book. W-8BEN cuts US dividend withholding
30% → 15%, claimable as a Foreign Income Tax Offset.

---

## 4. The robustness finding that matters beyond GEM

This is why the document is worth keeping even though the strategy is rejected.

**ReSolve built 1,226 GEM variants** (lookbacks 1–18 months, time-series vs moving-average
specs, single- vs multi-market trend signals) and tested them 1950–2018:

| Finding | |
|---|---|
| Antonacci's published specification beat **only 61%** of the alternatives | consistent with luck, not superiority |
| Cannot reject that **all 1,226 have the same expected Sharpe** | |
| Range across specs: compound return **12.4%–15.7%**, Sharpe **0.7–0.95** | Antonacci's 15.8% sits **at the top of that range** |
| Average cumulative gap, 95th vs 5th percentile spec, rolling 5-year windows | **64 percentage points** |
| Median single spec, worst five calendar years | **−7.5%** vs **−4.7%** for an equal-weight ensemble of all specs |
| Median drawdown | **17.4%** single spec vs **13.2%** ensemble |

**Newfound's version of the same test is starker.** Seven models, lookbacks 6–12 months:

> the 9-month model returned **43.1%** over the period while the 10-month lookback returned
> **146.1%**

Same strategy, same data, one month of lookback difference, **3× the terminal wealth**. In 2010
alone: 10-month **+12.2%**, 9-month **−9.31%** — a **2,151 basis point** single-year spread. And
critically, these differences *"are not expected to mean-revert"* — they are **permanent return
artifacts**. You do not get the average. You get whichever one you picked.

Samuel Lee's independent replication found the same signature from the other direction: the
**12-month window also happens to be the best-performing window**, with no theoretical reason
for 12 over 10 or 9. His conclusion: *"implies there is some data-mining here."*

### Why this belongs in `PROGRAM_INDEX.md` §4

**Boundary checks and drop-top-N ask whether the best cell sits at an edge or rests on a few
names. They do not ask the question ReSolve asked: where does the chosen cell sit in the
distribution of all cells, and how wide is that distribution?**

MCL's `TRAIL_PCT = 5.0` is one draw from such a distribution. `mcl_rejected_mechanics.md` §5
already found every trail-width confidence interval straddling zero — which is the same finding
arriving by a different route, and is stronger evidence than it was given credit for.

Two transferable rules:

1. **Report where the chosen specification sits in the full distribution of specifications**, not
   just whether it beats its neighbours. "Beat 61% of variants" is a far more honest statement
   than "best in the grid."
2. **Prefer an ensemble to a chosen parameter where the strategy allows it.** ReSolve's
   equal-weight ensemble of all 1,226 specs had a **13.2% drawdown against the median single
   spec's 17.4%**, at no cost. For MCL this would mean running several trail widths
   simultaneously rather than picking one — which is cheap to test and has never been tried.

**Rebalance-date luck is the same phenomenon.** Generic research on factor strategies puts
timing luck *"often exceeding 100 basis points annualized"*, scaling with concentration. GEM is
100%-in-one-asset — about as concentrated as a strategy gets — so its exposure should be at the
high end. **Nobody appears to have run the 21-trading-day grid on GEM and published it.** The
standard mitigation is tranching: split capital into 4–5 sleeves rebalanced on staggered days.

---

## 5. The two survivors

Neither has been measured here. Both are candidates for registration, not results.

### 5.1 Time Series Momentum — best evidence

Moskowitz, Ooi & Pedersen, *Journal of Financial Economics* 2012.
<https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf>

- ~8–12 liquid micro futures (MES, M2K, MGC, **MCL**, ZN, 6E), monthly, 12-month lookback,
  vol-scaled, long/short
- **Peer-reviewed and heavily replicated** — unlike GEM, which is self-published
- Driven by trends in bonds, FX and commodities — no exposure to US small-cap order flow
- Documented **crisis alpha**: pays in sustained equity drawdowns, which is when intraday
  momentum supply also dries up
- **MCL is already traded here**, so part of the futures plumbing exists
- Futures initial margin only, roughly USD 10–20k for a micro book at a 10% vol target — inside
  the AUD 50k cap

### 5.2 Faber Asset Class Trend-Following — lowest effort

Faber, [SSRN 962461](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461)

- 5 ETFs, 10-month SMA, long-or-cash, monthly. **No shorting, no leverage, cash-funded.**
- Lowest operational load of anything credible here
- **Caveat, and it is the same disease as GEM:** materially underperformed buy-and-hold since
  roughly 2009. Any figure quoted for it must state its test window.

### 5.3 What to do with them

Apply §4 to both **before** testing either:

1. Do not test Faber's 10-month SMA or TSMOM's 12-month lookback as *the* specification. Test
   the **grid**, report where the published value sits in the distribution, and report the
   **ensemble**.
2. Run the **rebalance-day grid** (all ~21 trading days) before committing, and plan to
   **tranche** across dates.
3. Re-derive over a window chosen here, not the paper's.
4. State the cost model. Both are cheap to trade, but "cheap" is not "free" and neither paper
   subtracts costs explicitly.

---

## 6. What was verified and what was not

**Verified:** GEM's rule set and the formulation ambiguity, from Antonacci's own site and FAQ;
his claimed backtest figures; the 2014–2026 out-of-sample comparison; the ReSolve 1,226-variant
study; the Newfound lookback-fragility figures; Samuel Lee's replication; IBKR Australia
commission schedule; the absence of a PRIIPs-equivalent barrier for Australian residents.

**Not verified:** whether Allocate Smartly maintains a GEM-specific live track (their public
list shows only *Traditional* and *Composite* Dual Momentum, and live figures are paywalled) —
that would be the single best clean, cost-adjusted live record if it exists; the widely-quoted
"17.43% CAGR 1974–2013" book figure, seen only second-hand; any published rebalance-day grid for
GEM specifically; IBKR Australia product permissions for these specific ETFs at the account
level, which should be checked in-account before relying on it.
