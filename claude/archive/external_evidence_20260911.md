# The external evidence base — what the literature says about what we are doing

**Created:** 2026-09-11
**Status:** LITERATURE REVIEW. No new measurement.
**Why:** a search for a knowledge base for algo trading strategy. The useful answer turned out
not to be a list of strategy sources.
**Governing standards:** `PROGRAM_INDEX.md` §4.

---

## 0. The headline

Three independent research passes — books, research libraries, and the academic evidence on
intraday equity trading — converged on one thing:

**The published literature independently reproduces this project's own findings, from completely
different data.** Not loosely. Specifically, on the exact numbers.

| This project measured | The literature independently says |
|---|---|
| Win rate 48.7%, R = 0.58, needs 63.4% | The two documented routes to profit are **high win rate with symmetric R** or **low win rate with large positive R**. 48.7% with R = 0.58 is neither. **The win rate is fine; R is the defect.** |
| MCL loses on the screened universe before friction | Heston/Korajczyk/Sadka (*JF* 2010): single-stock intraday continuation is real, robust, and **loses money after the spread in large NYSE stocks** — with spreads 10–100× tighter than ours |
| Friction $4.26/RT, pre-market spread 83 bps | SEC DERA: **median effective spread 13.29c** for sub-$100m stocks at $10–19.99. Our average win is **11.9c** |
| Census: the money is in sizing/gating, not entries | Four independent literatures: the money goes to **liquidity providers, not takers** |

**Nothing here is new information about markets. It is external corroboration that the
measurements in this project are correct, and it names two specific structural choices —
long-only, and crossing the spread — that the evidence says are on the wrong side.**

---

## 1. Our arithmetic, found in someone else's paper

### 1.1 The dead zone

| Book | Win rate | Avg win | Avg loss | **R** | Result |
|---|---:|---:|---:|---:|---|
| **Ben, real** | **48.7%** | 11.9c | 20.6c | **0.58** | **−$114,983** |
| Garvey & Murphy — *profitable* professional day traders | **62%** | $0.09 | $0.10 | **~0.90** | +$1.43m over 68 days |
| Zarattini ORB backtest | **48.4%** | — | — | **+0.38R** | (uncosted, see §3.3) |

Ben's win rate is **48.7%**. Zarattini's is **48.4%** — statistically the same — and that
strategy is presented as highly profitable because it runs winners to **+0.38R average**.
Garvey & Murphy's professionals win far more often, at **near-symmetric** trade sizes.

**Two documented routes to profit. Ben is on neither, and the reason is R, not the hit rate.**
This is exactly what `win_rate_and_r.md` §1 derived from the identity `p > 1/(1+R)`. The
literature arrives at it from live professional trading records.

### 1.2 The mechanism, also already documented

**Garvey & Murphy (*Financial Analysts Journal* 2004)**, on 15 profitable professional day
traders, >$1.4m of intraday profit:

> **Losers held 268 seconds on average vs 166 seconds for winners.**
> Losing trades: $0.10 average adverse move, $100.46 average loss.
> Winning trades: $0.09 average favourable move, $85.43 average gain.

**Holding losers ~60% longer than winners is the mechanical generator of a sub-1 payoff ratio.**
They also found prices kept moving favourably after the traders closed winners, and
unfavourably after they exited losers.

**These are the profitable ones.** They carry the same disposition bias and still make money —
offset by a 62% hit rate and essentially zero commissions. We have neither offset.

> **This is the strongest external support for `exit_candidates_20260911.md` §3** — the
> MFE-after-exit measurement. Garvey & Murphy measured exactly that on professionals and found a
> gap. It is the right diagnostic, and it has precedent.

---

## 2. The convergent finding — and it is the most important thing in this document

**Four independent literatures, different countries, different decades, different data, all say
the same thing: in this activity the money accrues to whoever POSTS liquidity, not whoever
TAKES it.**

| Source | Finding |
|---|---|
| **Barber, Lee, Liu & Odean** (*JFM* 2014) — complete Taiwan day-trader population, ~450,000 traders, 1992–2006 | What distinguishes the profitable minority: past performance, concentration, **willingness to short sell**, and **greater use of passive limit orders** |
| **Garvey & Murphy** — 15 profitable professionals, 96,323 trades | **64% of volume via passive limit orders** on Island ECN; 32% marketable |
| **Anand, Samadi, Sokobin & Venkataraman** (*Review of Finance* 2025) — FINRA OATS, **27 million retail orders**, 19 brokers | Retail limit orders beat marketable by **~9–10 bps**; **~20 bps in small caps** — *"greater compensation for providing liquidity in less liquid markets."* Fill rate ~60% in small caps |
| **Dai, Medhat, Novy-Marx & Rizova** (NBER 30917) | Reversal profits are **compensation for liquidity provision** — they accrue to whoever is posting, not whoever is taking |

**MCL crosses the spread, long only.** On this evidence that is the wrong side of both the
order-type finding and the direction finding.

Two counterweights, stated honestly:

- **Linnainmaa (*Journal of Finance* 2010):** limit orders suffer **adverse selection** — they
  fill precisely when the price is about to keep going against you. Lower measured cost, worse
  conditional fills. Both facts are true at once, and the ~40% non-fill rate in small caps is a
  real cost that must be modelled, not assumed away.
- **`short_selling_feasibility.md`** already answered that IBKR refuses opening short trades in
  this universe in either direction. **The short-side finding is not currently actionable** —
  but it does mean long-only is a constraint we are paying for, not a design choice that was
  validated.

> **What this licenses as a measurement:** MCL's marketable entries versus a posted-limit
> variant, with a realistic fill model (60% fill rate, adverse selection on the fills you get).
> That is a substantial piece of work and `friction_reconciliation_20260911.md` §5 already names
> the missing input — the stop-fill model. This is the same gap seen from the entry side.

---

## 3. The cost reality for our universe

### 3.1 The number that matters most

**Collver, SEC DERA, "A Characterization of Market Quality for Small Capitalization US
Equities"** (2014) — all US-listed stocks under $5bn, ~2,814 stocks/day, full year 2013.

For market cap **<$100m priced $10–19.99**:

| | Smallest caps | Mid-cap ($2–5bn) |
|---|---:|---:|
| Median quoted spread | **28.61c** | 1.03c |
| **Median effective spread** | **13.29c** | 0.96c |
| Relative spread | 2.08–2.83% | 0.07–0.08% |
| Median daily dollar volume | **$11,000** | $16.75m |

**Our average win is 11.9 cents. The median effective spread in that bucket is 13.29 cents.**

And the depth figure is worse than the spread figure: **99% of the smallest stocks priced
$10–19.99 have less than $5,000 of displayed liquidity within one cent of the midpoint.** At
~1,450 shares average size — implied by $114,983 ÷ 1,658 trades ÷ 4.77c per share — we are
frequently **larger than the entire displayed book at the touch**.

**Two honest caveats in our favour:** the study applies **no relative-volume filter**, so on a
40× RVOL day our names are more liquid than these medians; and 41% of small caps had mean
quoted spreads of 4.5c or less. The order of magnitude still stands.

### 3.2 The null hypothesis our backtests must beat

**Heston, Korajczyk & Sadka (*Journal of Finance* 2010)** — 1,715 NYSE firms, 2001–2005,
half-hour intervals. A real, statistically strong single-stock intraday continuation effect
(3.01 bps per half-hour, t > 8.7).

Then they subtract the spread:

> once you buy at the offer and sell at the bid, *"the average results are negative for all size
> categories at all times of the day"*, and *"strategies that attempt to take advantage lose
> money, after paying the bid-ask spread."*

**The best-identified single-stock intraday continuation effect in the peer-reviewed literature
does not survive the spread — in large NYSE stocks.** Ours are 10–100× wider.

### 3.3 Why the one paper that looks like us cannot be trusted

**Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy for the U.S. Equity Market"** is
the closest published analogue: ~7,000 US stocks, 2016–2023, survivorship-free, "Stocks in Play"
+ 5-minute ORB, reported **Sharpe 2.81** and **+1,600%**.

Two disqualifiers, both fatal:

1. **It filters our universe out.** Opening price **> $5**, 14-day average volume **≥ 1,000,000
   shares**, ATR **> $0.50**. The paper says explicitly: *"Penny stocks and low-liquidity
   equities are deliberately excluded."*
2. **Cost model: $0.0035/share commission and nothing else.** No spread, no slippage, no impact,
   no capacity. Against a measured **13.29c median effective spread**, that understates the cost
   of crossing by roughly **35–75×**. For a strategy averaging 0.38R, that is not a haircut, it
   is the entire result.

An independent replication of the companion QQQ paper
(<https://github.com/giovannibrusco/zarattini-2023-orb-qqq>) reproduces it closely and then
finds break-even at **~2.2c/share slippage against a ~1c spread**, with **76% of the P&L from
2022 alone**. Complete runnable code, bootstrap CIs, placebo controls.

> **That repository is the single highest-signal artifact found in this entire search: our
> evidence standard, applied to our strategy family, by someone else, with the code published.**
> Read it before anything else.

Note also the author conflict: Andrew Aziz runs Bear Bull Traders, a day-trading education
business, and his own books are cited as references in the paper.

---

## 4. What we are systematically long

This is uncomfortable and it should be recorded.

| Literature | Finding | Our overlap |
|---|---|---|
| **Bali, Cakici & Whitelaw, "Maxing Out"** (*JFE* 2011) | Highest-MAX decile (biggest single-day gainer last month) earns **−1.03%/month**, 4-factor alpha −1.18%. Median market cap of that decile: **$21.5m** | Our screen ranks on exactly this |
| **Barber, Huang, Odean & Schwarz** (*JF* 2022) — Robinhood herding | Herded stocks average **14% daily return with an 11% opening return** — pre-market gappers on top-mover lists with abnormal volume. Subsequent: **−3.5% at 5 days**, up to −19.6% at extreme herding | That is our screen, described |
| **Frieder & Zittrain** | For a touted stock, probability of being the day's most actively traded stock jumps from **4% to 70%** | Extreme RVOL in a microcap is historically a marker of **promotion**, not information |
| **Eraker & Ready** (*JFE* 2015) | Lottery-like low-priced stocks: extremely negative mean returns, highly positive skew | The adjacent population |

**The horizons are days to months, so none of this directly falsifies an intraday strategy.**
But we are systematically long the exact securities that three independent peer-reviewed
literatures identify as negative expected return, and **long-only is what puts us on that side.**

We are fighting a documented current, not riding one.

---

## 5. Two structural facts about our session window

**Pre-market — we are, by construction, the uninformed side.**
Barclay & Hendershott (*RFS* 2003), on the **250 most liquid** Nasdaq stocks:
**probability of informed trading is 0.25 pre-open vs 0.13 in regular hours**, and the
**fraction of informed trades is 65% in the pre-open** vs 32% during the day. Trading costs
*"four to five times larger than during the trading day."* Conditions in a $3 low-float name are
worse than anything that paper measures.

**Halts cluster in our exact window.**
SEC DERA LULD papers: Tier 2 securities (everything outside the S&P 500 / Russell 1000) average
**$0.36 quoted spread**, 18× Tier 1. **Trading pauses occur in at least one Tier 2 security on
100% of trading days**, averaging **29.19 per day**. And:

> **24.3% of Tier 2 pauses occur in the first 15 minutes; 36.4% occur between 9:45 and 9:50am.**

Only **46%** of Tier 2 pauses are followed by a price reversal to the pre-limit-state level
(vs 87% for Tier 1) — they more often mark a genuine repricing. **53% followed low-volume
periods** — liquidity events, not information events.

**Nothing in this project currently models halts.** A long-only momentum strategy in Tier 2
names will meet halt-on-the-way-up and halt-on-the-way-down, concentrated in the first twenty
minutes, and cannot exit through either.

---

## 6. The base rate, stated plainly

| Study | Sample | Profitable |
|---|---|---|
| Barber, Lee, Liu & Odean — Taiwan, complete population 1992–2006 | ~450,000 day traders/yr | ~20% in a typical year; **<1% reliably** |
| Chague, De-Losso & Giovannetti — Brazil | persistent day traders | **97% lost money**; 1.1% beat minimum wage |
| Jordan & Diltz (*FAJ* 2003) — US, 324 traders | 1998–99 | **35.8% net profitable.** Average gross profit **+$8,000**; average net **−$750** |

The Jordan & Diltz decomposition is the precedent that matters most: **the gross edge existed
and costs consumed all of it.** It is entirely possible that MCL's signal is gross-positive and
that the spread is the whole deficit. `friction_reconciliation_20260911.md` §3 says otherwise on
the screened universe — break-even friction there is **negative** — but that is one strategy on
one universe, and the fill-level decomposition has never been done.

**The other finding to sit with:** Chague et al. establish that **persistence does not produce
competence.** Barber et al. found unprofitable traders return at 95.3% and profitable ones at
96.4% — statistically indistinguishable. Continuing is not itself evidence of anything.

**Caveat that cuts the other way, and it is real:** both US studies are **pre-decimalisation**
(1998–2000), before Reg NMS, sub-penny price improvement, PFOF at current scale, HFT
market-making and LULD. The large modern datasets are **Taiwanese and Brazilian**, with
different tick regimes and transaction taxes (Taiwan's 30bps sales tax has no US analogue).
**There is no modern, large-sample, post-decimalisation US study of retail day-trader
profitability.** Anyone quoting "95% of day traders lose" for the US is extrapolating from
Taipei and São Paulo.

---

## 7. Where the literature is silent — and why the silence is not neutral

**Our exact intersection has never been studied.** No peer-reviewed work on US exchange-listed,
sub-$20, low-float, **high-relative-volume** intraday momentum:

- The small-cap microstructure work (Collver) has **no relative-volume conditioning** — typical
  days in typical small caps, not the 40× volume day
- The lottery/attention literature covers the right **stocks** at daily-to-monthly horizons
- The intraday work (Heston, Gao) covers the right **horizon** in the wrong stocks — large NYSE
  and SPY
- The one paper that aims at the intersection **filters our universe out** (§3.3)

Four more genuine vacuums, each one a place where we spend money blind:

1. **Nobody has measured what it costs to trade a low-float stock on a spike day.** Spreads may
   tighten or blow out; depth may deepen or evaporate. No published measurement either way.
2. **Market impact at retail size in illiquid names is unmodelled.** The entire impact
   literature is calibrated on institutional orders in liquid stocks. There is no model for
   1,450 shares in a $4 stock with $5,000 of displayed depth.
3. **Stop orders in fast equities are essentially unstudied.** The only serious work (Osler,
   FRBNY) is **foreign exchange** — clustered stops beyond round numbers triggering cascades.
   The mechanism transfers and is worse in a thin book. This is the mechanical source of our
   20.6c average loss and there is no published guidance.
4. **Retail algorithmic execution is unstudied entirely.** Every profitability study measures
   humans clicking. Nobody knows whether systematising the same strategy helps (removes the
   disposition effect Garvey & Murphy document) or hurts (mechanises entry into a 60%-fill
   order book).

> **The asymmetry that matters.** The silence is not symmetric in its implications. Everywhere
> the literature *has* looked at something adjacent — the stocks, the horizon, the population,
> the costs — **the findings are consistently negative, and negative specifically because of
> transaction costs.** The unstudied region is unstudied partly because the data is hard to get
> and partly because the surrounding results make it an unpromising place to look. That is not
> proof it cannot work. But the correct prior on an unstudied region surrounded on all sides by
> negative results is not "unexplored opportunity."

**The corollary is genuinely useful, though.** We hold **1,658 real fills** in this universe at
this size. On the question "what does it actually cost to trade a low-float stock on a spike
day", **that is better data than anything published.** It is the one dataset nobody can produce
for us, and the highest-value analysis available is our own fill decomposition — not more
reading.

---

## 8. The knowledge base — what actually earns time

### 8.1 Sources

| # | Source | Why |
|---|---|---|
| 1 | **[Rob Carver — qoppac.blogspot.com](https://qoppac.blogspot.com/)** + [pysystemtrade](https://github.com/robcarver17/pysystemtrade) | The only publisher with **costs-first, negative-results-by-default, open-code** as standing policy. Wrong markets (futures, slow), right method. Active Sep 2026 |
| 2 | **[SEC Market Structure Data](https://www.sec.gov/data-research/market-structure-data)** | Free empirical spread / depth / quote-lifetime data **broken out by market-cap, price and volatility decile**, through Jun 2026. Replaces a flat slippage assumption with something defensible. Zero conflicts |
| 3 | **[Brusco ORB replication](https://github.com/giovannibrusco/zarattini-2023-orb-qqq)** | Our evidence standard applied to our strategy family by someone else, with runnable code |
| 4 | **[AQR trading-cost papers](https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs)** | Real implementation shortfall from **$1.7tn of live executed orders** — the only public dataset of its kind. Read for the impact-vs-ADV function |
| 5 | **[CXO Advisory](https://www.cxoadvisory.com/)** | Twenty years of killing published findings, with a literal **Research Graveyard**. Our failure mode as someone else's house style |
| 6 | **[FINRA REMA](https://www.finra.org/about/office-chief-economist)** + [SEC DERA](https://www.sec.gov/dera) | Regulators with audit-trail data nobody else has. Retail limit orders, short-sale venue choice |
| 7 | **[Quantocracy](https://quantocracy.com/)** | Not research — the discovery layer for ~100 quant blogs. Filter hard; ~80% is cost-free backtest theatre |
| 8 | **[Quantopian archive](https://quantopian-archive.netlify.app/)** (dead 2020) | Mine once, for the statistical-pitfalls lectures and their study of **how badly retail backtests degrade out of sample** |

**Recommend against:** Quantpedia (a paid catalogue of ideas — the opposite of what is needed),
Build Alpha (software funnel; a strategy generator is a multiple-comparisons machine),
ReSolve (product marketing), Elite Trader / Wilmott (noise or dead). Alpha Architect and Robot
Wealth are borderline funnels — Robot Wealth's is honest and Longmore publishes his failures.

**Concretum** publishes directly in our niche and has **no negative results in its entire
output**. A research shop with a 100% hit rate is not doing research. Read the papers for the
hypotheses; never for the numbers.

### 8.2 Books — three, not a reading list

1. **Bouchaud, Bonart, Donier & Gould, *Trades, Quotes and Prices*** (CUP 2018). The
   **spread–volatility relation** is the formal statement of why "find the same setup in a
   tighter-spread name" is not available — the spread is mechanically tied to the volatility
   that makes the setup attractive. Plus square-root impact and order-book resilience: what our
   own 1,450-share orders do to a thin book.
2. **Timothy Masters, *Testing and Tuning Market Trading Systems*** (Apress 2018, ~US$14,
   [free code](https://github.com/Apress/testing-and-tuning-market-trading-systems)).
   **Nested walk-forward** and permutation tests over the *whole selection process* — the two
   things our protocol is missing, and plausibly why three findings inverted at 9× sample.
3. **Joel Hasbrouck, *Empirical Market Microstructure*** (OUP 2007, ~208pp). The econometrics to
   decompose **our own 1,658 fills** into *effective spread paid* versus *adverse selection
   suffered*. Turns "the reward side is short" into an attributable number.

Free, first, in one evening: **Harris's 2015 CFA monograph**
(<https://www.cfainstitute.org/sites/default/files/-/media/documents/book/rf-publication/2015/rf-v2015-n4-1-pdf.pdf>).

**Explicitly skip:** Ernie Chan (mean reversion on liquid instruments, poor out-of-sample
reputation), Kaufman (encyclopaedia — exactly wrong for someone who has tested too many things),
Clenow (we already have an engine), Van Tharp and Ralph Vince (optimal *f* on a mis-estimated
edge is the fastest route to ruin), and the entire day-trading paperback shelf — **no serious
book on intraday equity trading reports aggregate results.** López de Prado: read ch. 7, 11–13
and **15** from a library copy; the printed code is known-buggy.

### 8.3 The five papers

1. **Collver, SEC DERA (2014)** — <https://www.sec.gov/marketstructure/research/small_cap_liquidity.pdf>
   The 13.29c effective spread against our 11.9c average win.
2. **Garvey & Murphy, *FAJ* (2004)** — our P&L written about someone else: losers 268s, winners 166s.
3. **Heston, Korajczyk & Sadka, *JF* (2010)** — the null our backtests must beat.
4. **Anand, Samadi, Sokobin & Venkataraman, *Review of Finance* (2025)** — retail limit orders
   beat marketable by ~20 bps in small caps. The most directly actionable result found.
5. **Chague, De-Losso & Giovannetti (2020)** — persistence does not produce competence.

---

## 9. What this changes

**Nothing measured. Everything about priors.**

1. **`win_rate_and_r.md` is externally corroborated.** Garvey & Murphy and Zarattini bracket our
   exact win rate from both sides. The defect is R, confirmed from live professional records.
2. **`exit_candidates_20260911.md` §3 (MFE after exit) gains precedent.** Garvey & Murphy ran
   that measurement on professionals and found a gap. Run it first, as planned.
3. **A new candidate, and it may outrank everything:** **posted limit entries instead of
   marketable.** Four independent literatures converge; the small-cap advantage is measured at
   ~20 bps. It needs a fill model (~60% fill rate, adverse selection on the fills you get) —
   which is the same missing piece as the stop-fill model in
   `friction_reconciliation_20260911.md` §5, seen from the entry side. **Build the fill model
   once and it serves both.**
4. **Halts should be modelled.** 36.4% of Tier 2 pauses fall between 09:45 and 09:50 ET. Nothing
   in this project accounts for them.
5. **Long-only is a cost we are paying, not a design we validated.** `short_selling_feasibility.md`
   made it a constraint; the evidence says it is an expensive one.
6. **The highest-value analysis available is not reading — it is decomposing our own fills**
   against the NBBO at execution time. Nobody has better data on this question than we do.
