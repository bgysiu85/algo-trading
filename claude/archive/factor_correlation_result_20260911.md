# Momentum vs mean reversion — measured

**Run:** 2026-09-11
**Status:** MEASURED. First actual measurement in the large-cap program.
**Prompted by:** `largecap_strategy_spec.md` §3.4 — "the cheapest thing worth doing first".
**Supersedes:** §3.4 of that spec (now answered) and part of §3.1 (redundancy test, partly answered).

---

## 0. Findings, in order of importance

1. **Momentum and short-term reversal genuinely diversify each other.** Mean rolling 252-day
   correlation **−0.124**, negative on 77% of days. A 50/50 blend cuts volatility **35%**.
2. **The diversification holds where it is supposed to fail.** It survives the tails, it
   survives high VIX, and joint drawdown overlap is indistinguishable from independence.
   My earlier warning that they "correlate to 1 in stress" is **not supported at the factor
   level** — see §3.
3. **But both legs are flat.** Momentum **−0.26%/yr**, reversal **+0.10%/yr** over 19 years on
   this universe, before costs. Diversifying two things that do not make money gives a
   lower-variance nothing.
4. **RSI(14) and Bollinger %b are the same signal — confirmed on our own universe at
   ρ = +0.911.** But **RSI(2) vs %b is only +0.696**, which corrects my earlier blanket claim.
5. **A Bollinger dip-buying edge that looked real was an artefact of clustered observations.**
   Naive pooling said +0.286% excess per trade. The correct date-level calculation says
   **−0.010%, t = −0.18**. Detail in §5 — this is the most instructive result in the run.

---

## 1. What was measured, and why not Ken French

Ben asked for the correlation between the Ken French `ST_Rev` and `Mom` daily factors.
**`mba.tuck.dartmouth.edu` is blocked by this session's egress policy** (403 at the proxy,
not a site outage). Per the proxy's own guidance that is reported, not routed around.

So the factors were **rebuilt from scratch** on real price data, which is arguably the better
answer anyway: French's `ST_Rev` is a value-weighted, monthly-formed factor over the entire
NYSE/AMEX/NASDAQ cross-section. Ben's question is about **liquid US large caps**, which is a
different universe with a different expected answer.

### Data

| | |
|---|---|
| Source | TradingView daily bars via `TV_Remix` MCP |
| Universe | **120 liquid US large caps**, sector-spread |
| Span | 2006-10-23 → 2026-09-10; **4,743 factor days** from 2007-11-01 |
| Bars | 5,000 per name (median); shortest 3,422 (ZTS, IPO 2013) |
| Integrity | 0 NaN closes, 0 non-positive closes, 0 duplicate dates, all series end 2026-09-10 |
| Split adjustment | **Verified.** AAPL prices continuous across both the 2014 7:1 and 2020 4:1 splits. The 14 daily moves > ±35% are all real events (OXY in the Mar-2020 oil crash, 2009 financials, ORCL +36% Sep-2025, AMD Apr-2016) |

### Construction — registered before results were looked at

```
eligibility (at each formation date):
    price >= $10  AND  60d median dollar volume >= $20M  AND  >= 252 prior sessions

MOM    signal = cumulative return from t-252 to t-21   (12-1, skip-month)
         long top quintile, short bottom quintile
STREV  signal = return from t-21 to t                  (prior 1 month)
         long BOTTOM quintile (losers), short top quintile (winners)

both:  monthly rebalance, equal weight, dollar-neutral (0.5 long / 0.5 short, gross 1.0)
```

---

## 2. The headline correlation

| Frequency | Pearson | |
|---|---|---|
| Daily | **−0.171** | Spearman −0.129 |
| Weekly | **−0.200** | |
| Monthly | **−0.240** | n = 227 months |

**Rolling 252-day:** mean **−0.124**, median −0.135, range **−0.561** (Aug 2026) to **+0.706**
(Mar 2010). **Negative on 77% of days.**

By year — the correlation is persistently negative, and the two positive stretches are mild
and short-lived:

| | | | | |
|---|---|---|---|---|
| 2008 −0.340 | 2009 −0.098 | 2010 **+0.048** | 2011 −0.135 | 2012 −0.161 |
| 2013 −0.220 | 2014 −0.089 | 2015 −0.138 | 2016 **+0.006** | 2017 **+0.091** |
| 2018 −0.204 | 2019 −0.141 | 2020 −0.414 | 2021 **+0.012** | 2022 **+0.079** |
| 2023 −0.118 | 2024 −0.323 | 2025 −0.153 | 2026 −0.290 | |

Some of this is mechanical: a name that is a 1-month loser is often also a 12-1 loser, so the
two books take opposite positions in the names where the horizons agree. That does not make
the diversification less real, but it does mean it is structural rather than lucky.

---

## 3. Does it survive stress? — yes, and this corrects my earlier warning

I told Ben that momentum and reversal "correlate to 1 in deleveraging events", citing
Khandani & Lo on August 2007. **At the factor level, on this universe, that does not show up.**

### By VIX quartile

| VIX quartile | VIX range | **Correlation** | MOM ann. | STREV ann. |
|---|---|---|---|---|
| Q1 calm | 9–14 | **−0.125** | +5.28% | +0.33% |
| Q2 | 14–18 | **−0.234** | +7.34% | −2.48% |
| Q3 | 18–23 | **−0.129** | −4.22% | +2.15% |
| Q4 stressed | 23–83 | **−0.176** | **−8.59%** | +0.44% |

The correlation is negative in **every** regime including the most stressed. What the table
does show is that **momentum is the leg that breaks in stress** (−8.59% annualised in the top
VIX quartile, +5.28% in the calmest) — reversal does not rescue it, but it does not compound it.

### In the tails

| | |
|---|---|
| Worst 5% of days for **MOM** (n=238, MOM mean −1.67%) | STREV averages **+0.206%**; negative on only **47.1%** of them vs a 50.0% base rate |
| Worst 5% of days for **STREV** (n=238, STREV mean −1.29%) | MOM averages **+0.140%**; negative on only **41.6%** vs a 47.2% base rate |

Within-tail correlations are −0.109 and +0.006. **No tail dependence.**

### Joint drawdown

| | |
|---|---|
| Days MOM in >5% drawdown | 96.8% |
| Days STREV in >5% drawdown | 61.2% |
| Days **both** | **60.8%** |
| Expected if independent | **59.2%** |

Essentially no excess overlap.

### The quant-quake analogue

The worst joint weeks, ranked by combined loss:

| Week | MOM | STREV | Sum |
|---|---|---|---|
| **2009-05-10** | **−7.55%** | **−7.17%** | **−14.71%** |
| 2020-11-15 | −8.71% | +0.14% | −8.58% |
| 2009-04-12 | −4.75% | −2.26% | −7.01% |
| 2023-02-05 | −4.31% | −2.69% | −7.00% |
| 2021-03-07 | −3.81% | −2.29% | −6.11% |

**One genuine joint blow-up in 19 years** — the March–May 2009 momentum crash, where both legs
lost ~7% in a week. That is the risk, and it is real, but it is a single event rather than a
pattern. Khandani & Lo's August 2007 mechanism was *leveraged* deleveraging; these factors are
unlevered, which is most likely why it does not reproduce.

**Implication for sizing:** size for one week in which both legs lose ~7% simultaneously.
Do not size on the average correlation.

---

## 4. The blend — and the catch

| | Ann. return | Ann. vol | Sharpe | Max DD |
|---|---|---|---|---|
| MOM | **−0.26%** | 10.39% | −0.03 | −39.4% |
| STREV | **+0.10%** | 8.79% | +0.01 | −25.1% |
| **50/50 blend** | **+0.19%** | **6.21%** | +0.03 | **−23.0%** |

**Volatility falls 35%** against the naive average of the legs (9.59% → 6.21%). That is a
large, real diversification benefit — the correlation is doing exactly what diversification
is supposed to do.

**And it is worth nothing, because neither leg earns anything.** Both are flat over 19 years
**before any costs**. On the monthly rebalancing these strategies require, costs would put
both firmly negative — which is precisely what Novy-Marx & Velikov (−1.28%/month after costs)
and Blitz et al. (break-even 10 bps) predicted.

**The diversification premise holds. The return premise does not.** Those are separate
questions and this run answers both.

---

## 5. The Bollinger dip-buy: how a real-looking edge evaporated

This is the most instructive part of the run and it is worth reading in full, because I nearly
shipped the wrong answer.

**First pass** — pooled every (name, day) observation where the close was below the lower
Bollinger band, and averaged the 5-day forward return against the universe baseline:

```
BB alone          n=25,089   +0.286% excess per trade
BB + RSI(2)<10    n=19,301   +0.345% excess per trade
```

Against a 5.4 bps round trip that looks tradeable. **It is not.**

**The error:** signals cluster. On a selloff day dozens of names trigger at once, and pooling
weights those days far more heavily than quiet days. The observations are not independent, so
the correct unit is **the day**, not the (name, day) pair.

**Re-run on date-level excess returns:**

| | |
|---|---|
| Mean excess per trade | **−0.0100%** |
| Signal days | 3,494 |
| t-stat, date-clustered | **−0.23** |
| t-stat, Newey-West (maxlags=5, corrects the 5-day overlap) | **−0.18** |

**Zero.** And it decomposes badly:

| Split | Excess |
|---|---|
| **2008 alone** | **+0.532%** |
| 2007–2015 | +0.093% |
| **2016–2026** | **−0.078%** |
| Excluding 2008–09 | −0.039% |

**Drop-top-N by symbol** (project standard):

| | |
|---|---|
| All 120 symbols | +0.0612% |
| Drop top 1 (AVGO) | +0.0528% |
| Drop top 3 (AVGO, CRM, NFLX) | +0.0386% |
| Drop top 5 (+ UNH, TMUS) | +0.0271% |
| **Drop top 10** | **−0.0007%** |

After the 5.4 bps round trip, the date-level figure is **−0.064% per trade**.

### The clustering finding in its own right

| | |
|---|---|
| Median names signalling on a signal day | **3** |
| 90th percentile | 17 |
| **Maximum** | **105 of 120**, on 2015-08-24 |

On the days this strategy is most active it is **long 105 of 120 large caps at once**. That is
a leveraged long market bet wearing the costume of a diversified mean-reversion book. Any
backtest that treats those as 105 independent positions will understate risk by an enormous
margin.

**This is the single most important design warning to carry into L2b.**

---

## 6. Redundancy test — partly confirmed, partly corrected

Spearman rank correlation, pooled over 529,858 eligible (name, day) observations:

| Pair | ρ |
|---|---|
| **RSI(14) vs Bollinger %b** | **+0.911** |
| RSI(2) vs Bollinger %b | **+0.696** |
| RSI(2) vs RSI(14) | +0.594 |

Per-name RSI(14) vs %b: median **+0.912**, 5th percentile 0.902, 95th percentile 0.920 across
120 names. **Extraordinarily consistent** — this is a structural identity, not an average.

**Correction to what I told Ben.** I said Bollinger and RSI are the same signal, citing
ρ = 0.95. That is right for **RSI(14)** (we measure 0.911 on our own universe) but
**overstated for RSI(2)**, which at 0.696 carries meaningfully independent information —
unsurprising, since a 2-period lookback is far shorter than a 20-period band.

Signal overlap on the oversold trigger:

| | |
|---|---|
| Bars with close < lower band | 25,145 |
| Bars with RSI(2) < 10 | 60,155 |
| Both | 19,349 |
| P(RSI(2)<10 \| below band) | **76.9%** |
| P(below band \| RSI(2)<10) | 32.2% |

So adding RSI(2) to a Bollinger entry removes **23%** of trades. Given §5, it removes 23% of
trades that have no edge either way.

---

## 7. Medhat & Schmeling — could not reproduce, and the test was weak

The most decision-relevant claim in the evidence review was that short-horizon **momentum**,
not reversal, is the live effect in high-turnover large caps. Attempted here:

| Turnover tercile | Winners − losers, next month | Annualised | t | n |
|---|---|---|---|---|
| Low | −0.128% | −1.53% | −0.39 | 224 |
| Mid | +0.092% | +1.11% | +0.30 | 224 |
| High | −0.180% | −2.14% | −0.44 | 224 |
| Univariate (all) | −0.072% | −0.86% | −0.26 | 224 |
| **High − low spread** | **−0.052%** | | **−0.12** | 224 |

Published (M&S 2022, 1963–2018, full US cross-section, value-weighted): low turnover
−1.41% (t=−7.13), high turnover **+1.37%** (t=4.74), univariate −0.28% (t=−1.68).

**The univariate reversal figure matches in sign and insignificance** (−0.072%, t=−0.26 here vs
−0.28%, t=−1.68 published). **The turnover split does not reproduce.**

**This is a failed reproduction with a weak instrument, not evidence against M&S.** Two reasons
it should not be read as a refutation:

1. **My turnover measure is a proxy and not theirs.** They use share turnover
   (volume ÷ shares outstanding). Shares outstanding is not in this dataset, so I used
   **abnormal turnover** (21-day mean volume ÷ 252-day median volume). That is size-neutral,
   which is a virtue, but it measures a *change* in turnover rather than the *level* — and the
   level is what their economic story is about.
2. **120 survivor large caps is not the full cross-section**, and their effect is documented
   across the whole market with NYSE breakpoints.

**Conclusion: M&S is neither confirmed nor refuted here, and L2a should not be built on it
until it has been tested with real share turnover.** Note the era split is unstable too
(2007–2015 −0.790%, 2016–2026 +0.492%), which is a further reason not to lean on this run.

---

## 8. Caveats — what would change these numbers

| Caveat | Effect |
|---|---|
| **Survivorship bias.** 120 *current* large caps over 19 years. Names that failed are absent. | **Inflates every return figure**, and inflates dip-buying most of all — you are buying dips in names we already know recovered. It does **not** materially bias the *correlation* results, which are the main deliverable. That the dip-buy shows no edge **despite** this bias makes §5 stronger, not weaker. |
| **Dividends excluded.** TradingView closes are split-adjusted but not dividend-adjusted. | Understates total return, mostly for high-yield names. Near-zero effect on long/short factor correlation. |
| **No costs in the factor returns.** | Correlation is robust to this; the return levels in §4 are optimistic and would go clearly negative with monthly-rebalance costs. |
| **Not French's factors.** Different universe, equal-weighted not value-weighted, 120 names not thousands. | The correlation sign and magnitude should be read as "for a liquid large-cap book", which is the relevant question, not as a replication of the published factor correlation. |
| **Turnover proxy** (§7). | Reason the M&S test is inconclusive. |
| Overlapping forward windows in §5 | Corrected with Newey-West; conclusion unchanged. |

---

## 9. What this changes in the specs

| Spec item | Change |
|---|---|
| `largecap_strategy_spec.md` **§3.4** | **ANSWERED.** Correlation is −0.12 mean rolling. Diversification premise holds. |
| **§3.3** ("when diversification fails") | **SOFTENED.** No tail dependence, no excess drawdown overlap, negative correlation in every VIX quartile. One joint blow-up in 19 years (May 2009, both −7% in a week). Size for that week, not for the average. |
| **§3.1**, arms A/B/C | **PARTLY PRE-ANSWERED.** RSI(14) is redundant with %b (ρ=0.911); RSI(2) is not (0.696). Adding RSI(2) cuts trade count 23%. Run arms A/B/C with **RSI(2)**, not RSI(14) — with RSI(14) the test is already settled. |
| **§3.1**, expected outcome | **STRENGTHENED.** The raw BB dip-buy has no edge on 19 years of large-cap data: −0.010%/trade, t=−0.18, −0.064% after costs, and what edge existed was 2008 only. |
| **§3.1**, new mandatory requirement | **Cap concurrent positions and measure signal clustering.** Up to 105 of 120 names trigger on one day. Any equity curve built without a concurrency cap is measuring a leveraged long market bet. |
| **§3.2** (L2a / Medhat & Schmeling) | **DOWNGRADED pending a proper test.** Could not reproduce with an abnormal-turnover proxy. Needs real share turnover before L2a is built on it. |
| **All backtests** | Use **date-level** observations, not pooled (name, day) pairs. §5 shows the two differ by the entire result. |

---

## 10. Reproduction

Scripts: `fac.py` (factor construction), `regime.py` (correlation, VIX, tails, drawdown),
`redundancy.py` (RSI vs %b), `bbtest.py` (date-level dip-buy test), `ms.py` (turnover split).
Data: 120 daily CSVs + VIX + SPX, TradingView via `TV_Remix` MCP, fetched 2026-09-11.
All construction choices in §1 were fixed before any result was inspected.
