# TSMOM — specification, written from the paper

**Created:** 2026-09-17
**Status:** SPECIFICATION. Nothing measured. No data bought. No backtest code written.
**Owns:** the TSMOM chat, from 2026-09-17.
**Source of record:** Moskowitz, Ooi & Pedersen, "Time series momentum", *Journal of
Financial Economics* 104 (2012) 228–250.
<https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf>
(redirects to `https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf`)

**Reads:** `claude/handover_tsmom_20260917.md`, `claude/PROGRAM_INDEX.md` §1/§2/§4,
`claude/diversifier_candidates_20260911.md` §4/§5.1.

---

## 0. Provenance of every paper claim in this document — read this first

**The PDF was refused at the proxy from both environments on 2026-09-17
(`CONNECT tunnel failed, response 403` from the cloud container and from Ben's
device), so §1–§3 were first written from a fetch tool's reading of it rather
than from the page. Ben allowlisted `pages.stern.nyu.edu` and
`w4.stern.nyu.edu` at 22:17 the same evening; the PDF was then downloaded and
read directly, and every ★ line below has been checked against it.**

| Tag | Meaning |
|---|---|
| **[P]** | **Read off the PDF and verified verbatim**, with a page or section reference. |
| **[D]** | A **decision made here**, because the paper is silent or the choice is this project's. Registered, not inherited. |
| **[E]** | External to the paper (CME, Databento, IBKR), sourced inline. |
| **[M]** | Measured here, from free data, on the date stated. |

**Gate G1 of the registration is CLEARED.** All five ★ lines were confirmed:
equation (1) and its lag sentence, equation (5), the 40% sizing sentence, the
overlapping-portfolio averaging, and the skip question.

### 0.1 What the fetch tool got wrong, and why it is written down

The first pass **manufactured an ambiguity that does not exist in the paper.**
It reported that footnote 10 (p. 240) "indicates" the skip-the-most-recent-month
convention and that the §3.2 wording "suggests" the time-series signal does not
skip — leaving the single most consequential question in the construction open,
and §1.1 originally registered a **[D] decision** to resolve it.

Read on the page, footnote 10 says the opposite of ambiguous:

> "Asness, Moskowitz, and Pedersen (2010) exclude the most recent month when
> computing 12-month **cross-sectional** momentum. For consistency, we follow
> that convention here, but **our results do not depend on whether the most
> recent month is excluded or not**." (p. 240, emphasis added)

It is about the cross-sectional comparison factor of §5, not the TSMOM signal,
and it explicitly disclaims the sensitivity. §1.1 is now **[P]**, not [D].

**This is `PROGRAM_INDEX` §4's "control the tool" arriving on a document rather
than on a tape** — *measure on a second source before stating a conclusion, not
after*. A summarising layer does not fail loudly; it hedges, and a hedge reads
like diligence. Every ★ in this document exists because that layer was not
trusted, and the one that mattered is the one it got wrong.

---

## 1. The strategy, as the paper specifies it

### 1.1 The signal ★

**[P]** Equation (5), p. 236, as printed:

```
r^{TSMOM,s}_{t,t+1} = sign(r^s_{t-12,t}) × (40% / σ^s_t) × r^s_{t,t+1}
```

The signal is **the sign of the trailing 12-month excess return** of instrument
`s`. Positive → long one unit; negative → short one unit. There is no magnitude,
no threshold and no neutral band: the position is always on, in one direction or
the other. **[P]** p. 233: the signal uses "the sign of the past return from time
t−k−1 to t−1".

**[P] The lookback does NOT skip the most recent month. This is settled, not
chosen.** ★ Equation (5) signs on `r^s_{t-12,t}` and earns `r^s_{t,t+1}`, and
§3.2 (p. 234–235) spells the same thing out for general (k, h):

> "Specifically, for each instrument, we compute the time-t return based on the
> sign of the past return from time **t−k−1 to t−1**. We then compute the time-t
> return based on the sign of the past return from t−k−2 to t−2, and so on until
> we compute the time-t return based on the final past return that is still being
> used from t−k−h to t−h."

The freshest portfolio's signal is the k months ending at **t−1**, the month-end
immediately before the month whose return is earned. Equation (5) is the same
statement with the index shifted by one. **No gap, no skip.**

Footnote 10's skip convention belongs to the **cross-sectional** factor of §5,
and the same footnote adds that "our results do not depend on whether the most
recent month is excluded or not" (p. 240). §0.1 records why this paragraph
previously said something weaker.

**[D]** The one-month-skip variant is still carried as a **reported neighbour**
in the grid — cheap to compute, and the paper's insensitivity claim is a claim
about *their* sample, not this one.

**[D] "Excess return", for a futures contract, is the contract's own return.**
A futures position posts margin rather than capital, so its return is already an
excess return over the risk-free rate; no T-bill series is subtracted.
**[P]** p. 230 supports the reading indirectly: "For the equity indexes, our
return series are almost perfectly correlated with the corresponding returns of
the underlying cash indexes **in excess of the Treasury bill rate**." The paper
does not spell out a subtraction for futures anywhere the fetch could find, and
none is performed here. **This differs from GEM**, where absolute momentum is
explicitly measured against T-bills (`diversifier_candidates` §1) — do not carry
that habit across.

### 1.2 The ex-ante volatility estimator ★

**[P]** Equation (1), p. 233:

```
σ²_t = 261 × Σ_{i=0..∞} (1−δ) δ^i (r_{t−1−i} − r̄_t)²
```

- **[P]** `r̄_t` is "the exponentially weighted average return computed similarly" (p. 233).
  The variance is taken about the **exponentially weighted mean**, not about zero.
- **[P]** δ is set so "the center of mass of the weights is Σ(1−δ)δⁱ·i = δ/(1−δ) = 60 days"
  (p. 233) → **δ = 60/61 ≈ 0.98361**.
- **[P]** The annualisation factor is **261**, not 252. (p. 233)
- **[P]** The weights "(1−δ)δⁱ add up to one". (p. 233)
- **[P]** Lag, p. 233: "To ensure no look-ahead bias contaminates our results, we use the
  volatility estimates at time t−1 applied to time-t returns throughout the analysis." ★

**[D]** Implementation: `pandas.Series.ewm(com=60).var(bias=True)` on daily simple
returns, then × 261, then `.shift(1)`. The bias flag matters — `bias=False`
applies a debiasing factor that equation (1) does not have. **A test asserts the
`pandas` path and a hand-built weighted sum agree**, because this is exactly the
kind of one-flag difference that has produced a plausible wrong number in this
project before.

**[D]** Warm-up: the estimator is not read until **261 daily returns** exist for
the instrument. Before that the instrument is absent from the book, not
zero-weighted. (`PROGRAM_INDEX` §4: "an empty half is not a sign flip" — an
absent instrument and a flat instrument must be distinguishable in the output.)

### 1.3 Sizing ★

**[P]** p. 236: "We size each position (long or short) so that it has an ex ante
annualized volatility of 40%." And: "The choice of 40% is inconsequential, but it
makes it easier to intuitively compare our portfolios to others." ★

**[P]** p. 236, verbatim, and note which subscript it carries: "the position
size is chosen to be **40%/σ_{t−1}**, where σ_{t−1} is the estimate of the ex
ante volatility of the contract as described above." **Equation (5) on the same
page prints `40%/σ^s_t`.** The two are the paper's own notation for one quantity
— §1.2's estimator is lagged by construction — but they are not the same symbol,
and a reader implementing from equation (5) alone could reasonably compute an
unlagged volatility. **This project uses the lagged estimate**, and a test
asserts the series is shifted.

**[P]** p. 236: the portfolio is the **equal-weighted average across all
available instruments**, which delivers "an annualized volatility of **12% per
year** over the sample period 1985–2009". **[P]** footnote 8, p. 236: this "implies a use of margin capital
of about 5–20%, which is well within what is feasible to implement."

**[D] The dollar formulation used here**, which is equation (5) rewritten for an
account of finite size and integer contracts:

```
target $vol per market  =  0.40 × (E / N)
n*_s                    =  target $vol / (multiplier_s × price_s × σ_s)
n_s                     =  round(n*_s)            # integer contracts; 0 means NOT TRADED
```

where `E` is account equity, `N` the number of instruments with a live signal,
`σ_s` the annualised ex-ante volatility from §1.2. **§3 shows that this rounding
is not a detail at $22k — it is the finding.**

### 1.4 Rebalance ★

**[P]** Monthly, at the end of each month. **[P]** p. 233: the reported return
"represents the average return across all portfolios at that time … portfolios
constructed last month, the month before … and so on" — the overlapping-portfolio
averaging that makes TSMOM(k,h) well-defined for holding periods h > 1 month.
The published headline is the **(k=12, h=1)** cell, where that averaging collapses
to a single portfolio. ★

**[D] Rebalance-date luck is registered up front, not discovered later.**
`diversifier_candidates` §4 puts timing luck at "often exceeding 100 basis points
annualized", scaling with concentration, and notes nobody has published the
21-trading-day grid for GEM. A monthly, ~10-market book is concentrated enough to
care. This project therefore registers **tranching as the specification**: capital
is split into **five sleeves rebalanced on trading days 1, 5, 9, 13 and 17 of the
month**, each holding one fifth of the book. The **full 21-day grid is reported
beside it** as the distribution the chosen spec sits in (`PROGRAM_INDEX` §4,
"where does the chosen cell sit in the DISTRIBUTION of cells"). The tranched book
is the registered answer; the grid is the honesty check, not a menu.

### 1.5 The paper's universe, for reference only

**[P]** §2.1, p. 230: "futures prices for **24 commodities, 12 cross-currency
pairs (from nine underlying currencies), nine developed equity indexes, and 13
developed government bond futures**, from **January 1965** through December
2009." The headline sample is cut at **1985** "to ensure that a comprehensive
set of instruments" is available (p. 236); the 1965–1985 data is what the
out-of-sample check below runs on. **58 instruments in total.** **[P]** "We focus on the most liquid
instruments to avoid returns being contaminated by illiquidity" (p. 230).

**[P]** Reported results: annual Sharpe "greater than 1.0 … roughly 2.5 times the
Sharpe ratio for the equity market portfolio" (pp. 236–237); ~12% portfolio vol;
Table 2's t-statistics cluster around k = 12 with h = 1–12 months. **[P]** an
earlier out-of-sample window, 1966–1985, gives "a statistically significant return
and an annualized Sharpe ratio of 1.1" (p. 248).

**[P]** Roll handling, p. 230: "Each day, we compute the daily excess return of
the most liquid futures contract (typically the nearest or next nearest-to-delivery
contract), and then compound the daily returns to a cumulative return index."
**[P]** §6.3, p. 247: `futures return = price change + roll return`.

**[P] Transaction costs: the paper does not deduct them, and says so in its own
figure captions.** Fig. 2 (p. 239) reports "the annualized **gross** Sharpe ratio
of the 12-month time series momentum or trend strategy for each futures
contract". A full-text search of the paper finds **no transaction-cost
treatment anywhere** — the only two occurrences of the phrase are a
related-literature aside and a title in the bibliography. Neither does Faber's,
neither does Antonacci's (`diversifier_candidates` §1, §5.3 item 4). Every number
in the paper is gross. **This project reports nothing gross** (`PROGRAM_INDEX` §1:
"every P/L figure states whether friction is charged").

**[P] What the paper does NOT say:** the fetch found no multiple-testing or
data-mining caveat anywhere in it. p. 248 offers "These findings are robust across
a number of subsamples, look-back periods, and holding periods" and frames the
consistency across 58 instruments as evidence against spuriousness. That framing
is exactly what ReSolve dismantled for GEM (`diversifier_candidates` §4:
Antonacci's published spec beat only 61% of 1,226 variants, and its 12-month
window "also happens to be the best-performing window"). **Treat the paper's
robustness claim as a hypothesis this project tests, not as a result it inherits.**

---

## 2. The instrument set, and the rule that chose it

### 2.1 The selection rule, stated before any return is seen

**[D]** An instrument is in the set if and only if **all five** hold. No step in
this rule reads a return, a Sharpe, or anything a backtest produces.

1. **It is tradeable by Ben today** — a CME-listed contract available at IBKR
   Australia, at a size a ~$22k account can hold at all.
2. **It is PRICE-quoted, not YIELD-quoted.** See §2.3; this is a sign trap, not a
   preference.
3. **Its full-size CME predecessor has GLBX.MDP3 daily history**, so the signal
   can be measured over more than the micro's own life. **Where that history
   begins after the dataset's start, the root enters the book when the warm-up
   rule admits it and the coverage table reports the gap.**
   *(Amended PRE-RUN 2026-09-18. The original read "from the dataset's start"
   and was false for RTY: Russell 2000 futures were listed on ICE until CME
   relisted them for trade date 2017-07-10, so RTY has no GLBX history for about
   seven of the sixteen years, and nothing had checked it. The instrument set is
   NOT changed — swapping RTY out after seeing which root failed would be
   choosing an instrument from a property of the data.
   `REGISTERED_tsmom_fetch` §1.4.)*
4. **It is the most liquid contract in its bucket** by 2026 volume, where a bucket
   is a group of near-substitutes (US large-cap index, US small-cap index,
   precious metal, base metal, crude, gas, and one per currency pair).
5. **At most one instrument per bucket**, so that the equal-weighted portfolio is
   not four correlated ways of owning the S&P.

Rule 4's liquidity ordering is taken from **front-month session volume on
2026-09-17** and is recorded in §2.2 so that it cannot be quietly re-ordered later.

### 2.2 The set

**[E]** Contract specifications from CME Group (cmegroup.com fact cards, rulebook
chapters and listing advisories, retrieved 2026-09-17; see `handover` §2.1 for the
name-collision warning about "MCL").

| Bucket | Signal contract | Traded as | Micro mult. | Micro launch | Fraction |
|---|---|---|---|---|---|
| US large-cap equity | **ES** | MES | $5 × index | 2019-05-06 | 1/10 |
| US small-cap equity | **RTY** | M2K | $5 × index | 2019-05-06 | 1/10 |
| Precious metal | **GC** | MGC | 10 oz | 2010-10-04 | 1/10 |
| Second precious metal | **SI** | SIL | 1,000 oz | 2013-06-17 | 1/5 |
| Base metal | **HG** | MHG | 2,500 lb | 2022-05-02 | 1/10 |
| Crude | **CL** | MCL | 100 bbl | 2021-07-12 | 1/10 |
| Natural gas | **NG** | MNG | 1,000 MMBtu | 2023-11-06 | 1/10 |
| EUR | **6E** | M6E | €12,500 | 2009-03-23 | 1/10 |
| AUD | **6A** | M6A | A$10,000 | 2009-03-23 | 1/10 |
| GBP | **6B** | M6B | £6,250 | 2009-03-23 | 1/10 |
| JPY | **6J** | MJY | ¥1,250,000 | 2010-12-20 | 1/10 |
| 10-year rates | **ZN** | *see §2.3* | — | — | — |

Twelve buckets. **Nasdaq (NQ/MNQ) is excluded by rule 5** — it is the same bucket
as ES and the two are near-substitutes; including both would weight US large-cap
equity double. **MYM/YM likewise.**

**The micro launch dates are the reason the handover's instruction matters:** the
earliest micro in this set is **March 2009** (E-micro FX) and the latest is
**November 2023** (micro nat gas). Six of the eleven micros did not exist before
2019. **Signals are computed on the full-size contract's history throughout; the
micro is the execution vehicle only.** That choice is registered explicitly, per
the handover.

### 2.3 Rates — the one genuinely open decision, and the sign trap

**[E] CME Micro Treasury *Yield* futures (2YY, 5YY, 10Y, 30Y) are quoted and
settled on YIELD, not price.** CME's own wording: "Yield futures trade in a
**direct relationship to changes in yield**, unlike the traditional US Treasury
Futures contracts, which trade in price terms and as an **inverse relationship to
yield**"
(<https://www.cmegroup.com/education/courses/cme-institute-live-micro-treasury-yield-futures/micro-treasury-yield-futures-contract-description-and-terms.html>),
and, as a sign check, "The correlation between the Micro Ultra 10-Year futures and
the 10-Year Yield futures is **−0.997**"
(<https://www.cmegroup.com/articles/2024/micro-treasury-futures-vs-yield-futures.html>).

**A long signal on ZN is a SHORT in 10Y.** A TSMOM engine that maps a bond signal
onto a yield contract without the flip trades the opposite of its own rule, and
would do so while printing a perfectly ordinary-looking equity curve. Rule 2 of
§2.1 excludes yield-quoted contracts outright for exactly this reason. **They are
not in the set and are not to be substituted in later** without a registered
amendment that carries the sign flip as a per-symbol attribute in code, with a
test.

**[E]** There is **no micro of ZN, ZB, ZF or ZT**. CME lists **MTN** (Micro Ultra
10-Year Note) and **MWN** (Micro Ultra Bond), launched **2024-03-25**, price-quoted,
1/10 size, cash-settled — but they are micros of **TN** and **UB** (the Ultra
contracts), not of ZN and ZB. MTN's reference basket has a materially longer
duration than ZN's (~$8.80 DV01 against ZN's ~$6.5–7), so the hedge ratio to ZN is
not 10:1.
(<https://www.cmegroup.com/articles/2024/understanding-micro-treasury-futures.html>)

**[D] Registered: signals are computed on ZN, and the rates sleeve is measured
three ways in the same run, reported side by side and not ranked:**

- **(a) ZN itself**, full size — honest, and at ~$2,062 maintenance it is 9% of
  equity for one contract.
- **(b) MTN**, signal from TN's own history rather than ZN's, accepting that the
  live history begins 2024-03-25.
- **(c) rates omitted entirely**, an 11-market book.

**Which of the three is traded is Ben's call, and it is not made from the
backtest's ranking** — that would be a one-family grid searched on the result.
The run reports all three; the choice is made on margin and on whether a rates
sleeve is wanted at all.

### 2.4 What this set gives up, stated now rather than discovered later

- **No agricultural commodities.** CME lists no micro corn, wheat, soy, sugar,
  coffee or cattle. The paper's 24 commodities become five here.
- **No non-US equity index.** The paper carries nine developed-market indices; the
  micro suite carries only US ones. Both US equity buckets are one macro exposure.
- **No non-US government bonds.** The paper carries thirteen.
- **Eleven or twelve markets against the paper's 58.** The diversification that
  produces the paper's ~12% portfolio vol out of 40% positions is materially
  thinner here, and §3 is what that costs.

---

## 3. Capacity and granularity — measured, 2026-09-17, before any data was bought

**[M]** Prices: TradingView front-month closes, 2026-09-17.
**[M]** Volatilities: the §1.2 estimator (EWMA, com = 60, × 261), on 400 daily
bars of the front-month continuous series, same date. Equity `E = $22,129`
(`DUM215828` net liquidation, `PROGRAM_INDEX` §1). `N = 13` (the §2.2 set plus NQ
and ZN, to show the full spread).
**[E]** Maintenance margins are **broker-republished CME figures (AMP Futures,
2026-09-17)** — indicative, not pulled from CME's own margin tool, which does not
render to a text fetch. They are used here only to show an order of magnitude.

Target dollar volatility per market: `0.40 × (22,129 / 13)` = **$681/yr**.

| Market | Traded as | Notional | $vol per contract | n* (target) | forced n | × target | margin |
|---|---|---:|---:|---:|---:|---:|---:|
| S&P 500 | MES | 38,432 | 4,842 | 0.14 | 1 | **7.1×** | 2,863 |
| Nasdaq 100 | MNQ | 59,140 | 12,301 | 0.06 | 1 | **18.1×** | 4,646 |
| Russell 2000 | M2K | 14,540 | 2,428 | 0.28 | 1 | 3.6× | 1,237 |
| Gold | MGC | 43,661 | 11,483 | 0.06 | 1 | **16.9×** | 2,426 |
| Silver | SIL | 64,630 | 32,767 | 0.02 | 1 | **48.1×** | 7,171 |
| Copper | MHG | 16,500 | 4,340 | 0.16 | 1 | 6.4× | 1,320 |
| WTI crude | MCL | 10,073 | 5,661 | 0.12 | 1 | 8.3× | 1,089 |
| Nat gas | MNG | 2,883 | 1,205 | 0.57 | 1 | 1.8× | 309 |
| EUR/USD | M6E | 14,388 | 719 | 0.95 | 1 | 1.1× | 231 |
| AUD/USD | M6A | 7,098 | 511 | 1.33 | 1 | 0.8× | 193 |
| GBP/USD | M6B | 8,357 | 476 | 1.43 | 1 | 0.7× | 187 |
| JPY/USD | MJY | 8,076 | 808 | 0.84 | 1 | 1.2× | 264 |
| 10y T-Note | ZN (full) | 105,984 | 4,663 | 0.15 | 1 | 6.8× | 2,062 |

**Five of thirteen markets reach half a contract. Eight do not.**

Forced to a one-lot minimum across all thirteen:

- **13 contracts, $23,998 maintenance margin — 108% of equity.** The account
  cannot hold the book at all.
- Gross notional **$393,764, 17.8× equity**.
- Portfolio volatility, at one lot each and zero correlation, **≈$38,236/yr — 173%
  of equity**, against the paper's ~12%.

**Equity required for the minimum one lot to land within 2× of the paper's target
size:** silver **~$532,000**; Nasdaq ~$200,000; gold ~$187,000; crude ~$92,000;
S&P ~$79,000. **All thirteen feasible: ~$532,000.**

**The largest one-lot book that fits a portfolio volatility cap at $22,129**
(0.15 average pairwise correlation assumed, margin held under half of equity):

| Vol cap | Markets that fit | Realised vol | Margin |
|---|---|---:|---:|
| 10% | MNG, M6E, M6A, M6B, MJY | 10% | $1,184 |
| 15% | M2K, M6E, M6A, M6B, MJY | 14% | $2,112 |
| 25% | M2K, MNG, M6E, M6A, M6B, MJY | 16% | $2,421 |
| 40% | M2K, MHG, MNG, M6E, M6A, M6B, MJY, ZN | 40% | $5,803 |

**Read plainly: at this account size a vol-targeted TSMOM book is four currencies
and one other thing.** That is one and a bit asset classes. The crisis alpha, the
commodity trends and the bond trends — the entire reason `diversifier_candidates`
§5.1 ranked TSMOM above everything else unbuilt — are the parts that do not fit.

**This is a finding, not a tuning knob** (`handover` §2.3). It does not say TSMOM
has no edge. It says **measuring the edge and trading it are now two separate
decisions**, and the measurement is worth making on its own terms — both because
the account may not stay at $22k, and because a strategy that needs $500k to hold
properly is worth knowing about before, not after, the data is bought.

### 3.1 A warning the measurement produced on its own

**[M]** Building those volatility estimates off **front-month continuous series**
put a **−46.3% single-day return** into natural gas on 2026-01-27 (6.954 → 3.732).
It is a **roll break**, not a price move: the expiring February contract had run
to 7.44 and the series stepped down to the next contract. Four more |r| > 24% days
sit in the same 2026-01-18 → 2026-02-01 window. Left in, they take NG's ex-ante
volatility from **41.8% to 56.7%** — a 15-point error in a number that divides
the position size.

**This is `PROGRAM_INDEX` §3's "signature failure" arriving before a single line
of strategy code was written**: "a continuous series that looks right while
booking the wrong contract". It happened on a free data pull whose only job was to
size a table. **The back-adjustment rule in §4 is not boilerplate.**

Silver shows a −31.4% day on 2026-01-29 that could be a genuine squeeze unwind or
a second roll break; closes alone cannot separate them. **That ambiguity is itself
the argument for buying the `definition` schema** (§5) rather than inferring rolls
from price.

---

## 4. Data: what is needed, and the roll rule

**[D] Dataset:** Databento **GLBX.MDP3**, schemas **`ohlcv-1d`** and
**`definition`**. `definition` carries expiration dates and multipliers, so the
roll calendar is read rather than inferred — which §3.1 just demonstrated is not
a theoretical distinction.

**[D] Instruments:** the full-size roots of §2.2 — **ES, RTY, GC, SI, HG, CL, NG,
6E, 6A, 6B, 6J, ZN** — plus **TN** if rates arm (b) is wanted. Twelve or thirteen
roots, all contract months, over the dataset's full daily history.

**[D] The roll rule, registered:**

1. The **held** contract is the **front month**, rolled **five trading days before
   its expiration date** as given by the `definition` schema — never inferred from
   volume or open interest, which are outcomes.
2. The **signal** is computed on a **back-adjusted continuous series** built by
   the **difference method** (subtract the price gap at each roll), not the ratio
   method. Difference-adjustment preserves dollar changes, which is what a
   volatility estimate on dollar P/L needs; ratio-adjustment preserves percentage
   changes and distorts old levels, badly, on a series that has rolled 60+ times.
3. **P/L is computed on the actual held contract, at that contract's price**, and
   **the roll is charged** as two round-trip legs at the §6 cost model. The
   continuous series is used for the signal and the volatility estimate and for
   **nothing else**.
4. **A test asserts (3) against (2):** a synthetic two-contract series with a known
   gap at the roll, where the continuous series and the held-contract book must
   disagree by exactly the gap. **If that test cannot be made to fail by breaking
   the code, it is removed** (`PROGRAM_INDEX` §1: mutation-test every guard).

**[E] Hazard inherited:** `claude/archive_defect_daily_chunk_start_20260917.md` —
`databento_universe` month chunks that start mid-month overwrite the full month.
The futures pull is range-based rather than day-chunked and should not meet it,
but the archive layout is shared and the manifest is not.

**[D] The archive path is `E:\Databento\GLBX.MDP3\`**, alongside the existing
XNAS trees and outside the repo, per `PROGRAM_INDEX` §3. Billing is on retrieval:
once pulled, it is free to re-read forever.

---

## 5. Cost of the data — DRY RUN ONLY, and the number is not yet known

**Nothing has been spent. Nothing will be spent until Ben confirms a figure.**

`common/tsmom_data_price.py` is delivered with this spec. It **estimates only**:
it calls `metadata.get_cost()` and `metadata.get_billable_size()` for each root
and prints a table and a total. It has **no download path at all** — not a guarded
one — so there is no flag that can spend money by accident. `--max-cost` aborts
above a ceiling (default $5). The key is read from `DATABENTO_API_KEY` and is
never an argument and never printed (`PROGRAM_INDEX` §1).

**[E] Why the real number has to come from Ben's machine.** Databento meters on
**uncompressed binary size**, at a per-GB rate that varies by dataset and schema,
and `get_cost()` "respects any discounts provided by flat rate plans"
(<https://databento.com/docs/api-reference-historical/metadata/metadata-get-cost>).
Ben is on the **$199/month Standard plan**, which includes **16+ years of L0**
history — and `ohlcv-1d`, `definition` and `statistics` are all **L0**
(<https://databento.com/pricing>). **The likely answer is therefore that this pull
costs nothing beyond the subscription already being paid**, which is exactly what
happened when the XNAS.BASIC archive was extended through 2026-09-17 at $0.00
(`PROGRAM_INDEX` §3). But "likely" is not a number, the API key is env-only on
Ben's machine, and `get_cost()` is the only thing that knows his plan.

**[E] Note for §7 item 23 of `PROGRAM_INDEX`** — "cancel the Databento
subscription, $199/month, blocked by item 1". **TSMOM is now a second claim on
that subscription**, and the claim is specifically on the L0 16-year history that
the Standard plan is what provides. Cancelling before this pull turns a $0 pull
into a metered one. That interaction is not TSMOM's to decide, but it should not
be discovered by cancelling first.

**Run this on Ben's machine and paste the total back:**

```
cd D:\Trading
.\.venv\Scripts\python.exe -m common.tsmom_data_price
```

Add `--with-tn` if the rates arm (b) of §2.3 is wanted.

---

## 6. Costs, charged — the project reports nothing gross

**[E]** IBKR futures commission, Australia, is roughly **USD 0.25–0.85 per micro
contract per side** depending on product and tier, plus exchange and regulatory
fees. **[D]** Until a figure is read off one of Ben's own IBKR statements, the
registration uses a **stated placeholder** and reports at **three levels**, the
way every `pit_*` module in this repo already does (`PROGRAM_INDEX` §4, "report at
all three friction levels"):

| Level | Per micro contract, per side | What it represents |
|---|---|---|
| **low** | $0.50 | commission and fees only, best tier |
| **mid** | $1.25 | commission, fees and one tick of slippage |
| **high** | $2.50 | the same, doubled — the "measured friction was half of what we thought" margin that §4 of the index was written by |

**[D]** Turnover charged: **two sides at every rebalance where the sign or the
integer size changes**, plus **two sides at every roll** (§4 rule 3). A month in
which the signal does not change and the rounded size does not change **costs
nothing but the roll** — which is the structural reason this strategy is worth
testing at all after everything intraday here died of friction.

**[D]** A monthly, ~12-market book rolling quarterly is on the order of **100–250
contract-sides a year**. At the mid level that is **$125–310/yr, 0.6–1.4% of
$22,129** — a headwind measured in percent of equity per year, against the
intraday book's $4.26 per round trip on a strategy that trades hundreds of times a
week. **State it; do not assume it is negligible.**

---

## 7. What this spec does not settle, and where it goes

**Open, and registered as open:**

1. ~~The five ★ [P] lines have not been read off the page.~~ **CLOSED
   2026-09-17**, after Ben allowlisted the host. All five verified; the skip
   question resolved against the fetch tool's hedge. §0 and §0.1.
2. **The rates arm** — (a) ZN, (b) MTN, (c) none. §2.3. Ben's call, not the
   backtest's.
3. **The real friction number**, from an IBKR statement. §6.
4. **The data cost**, from `get_cost()` on Ben's machine. §5.
5. **Whether the strategy is traded at all at $22k**, given §3. Separate from
   whether it is measured.

**Next, in order** (`handover` §4): the registration
(`docs/research/REGISTERED_tsmom.md`) is committed **before any backtest code
runs**; then the engine with hand-built tests for roll handling, volatility
scaling and integer contracts; then the data pull, once Ben has confirmed §5's
number; then the run.

**Not touched, by instruction:** `strategy/orb/` — ORB runs in the ORB chat.
