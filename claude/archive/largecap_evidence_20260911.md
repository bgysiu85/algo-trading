# Large-cap intraday + swing — evidence review

**Created:** 2026-09-11
**Status:** EVIDENCE REVIEW. No strategy in this project has been built or measured against any of it.
**Governing standards:** `PROGRAM_INDEX.md` §4.
**Companion:** `largecap_strategy_spec.md` — the two strategy specs that follow from this.

**Scope decided with Ben, 2026-09-11:** liquid US large caps (S&P 500 / Russell 1000);
one intraday momentum strategy on 5-minute bars; one diversifier holding 2–10 days;
both long and short.

---

## 0. Headline, before any detail

Three independent research passes (intraday momentum evidence, mean-reversion evidence,
execution mechanics) returned a consistent and uncomfortable picture:

1. **The published intraday momentum results everyone cites are zero-slippage.** The most
   rigorous independent replication puts the QQQ opening-range edge at a break-even of
   **~2.2¢/share against a ~1¢ spread**. The edge lives inside the spread.
2. **Bollinger + RSI mean reversion on liquid large caps is the single configuration the
   academic literature most clearly rejects** — and RSI and Bollinger %b are empirically the
   same signal (Spearman ρ ≈ 0.95), so combining them is threshold tuning, not confirmation.
3. **But the move to large caps is unambiguously right on cost.** All-in round-trip friction
   falls from Ben's measured **$4.26 on small caps** to roughly **5 bps of notional** — an
   order-of-magnitude improvement in the term that actually kills strategies.
4. **Two rule changes materially affect the design and both are recent.** The Pattern Day
   Trader rule was **eliminated 4 June 2026**. And the binding leverage constraint is not
   Reg T — it is IBKR Australia's **AUD 50,000 retail margin-lending cap**.

There is one **peer-reviewed, cost-tested, net-positive** result in exactly this universe,
and it points the opposite way from what was expected. See §3.4.

---

## 1. Intraday momentum — what the evidence actually supports

### 1.1 The opening-range breakout literature, and its problem

The work Ben would encounter first is Zarattini & Aziz (and Barbon), a cluster of SSRN
preprints promoted heavily to retail:

| Paper | Claim | Cost assumption |
|---|---|---|
| QQQ/TQQQ ORB — SSRN 4416622 | TQQQ +1,484% (2016–23), 33% annualised alpha | **$0.0005/share commission, zero spread, zero slippage** |
| US stocks ORB — SSRN 4729284 | Top-20 RVOL: +1,637%, IRR 41.6%, **Sharpe 2.81** | $0.0035/share. The words *slippage*, *bid-ask spread*, *market impact* **do not appear in the paper** |
| SPY intraday momentum — SSRN 4824172 | +1,985%, 19.6% annualised, Sharpe 1.33 | $0.0035 + **$0.001/share slippage** — about one-tenth of a typical SPY spread |

**None is peer-reviewed.** SSRN and the Swiss Finance Institute Research Paper Series are
both preprint venues. Andrew Aziz runs Bear Bull Traders, a paid day-trading education
business whose site promotes these papers directly; Carlo Zarattini runs Concretum, which
sells trading tools. This is research functioning as a marketing funnel. (The same two
authors also published *"The Art of Financial Illusion: How to Use Martingale Betting
Systems to Fool People"* — they understand exactly how backtests mislead.)

### 1.2 The independent replication — the most useful single thing found

Giovanni Brusco reproduced the QQQ paper closely (1,775 trades vs the paper's 1,795;
Sharpe 1.06 vs 1.12), which makes his cost finding credible:
<https://github.com/giovannibrusco/zarattini-2023-orb-qqq>

- Gross edge: **$0.070/share**
- At 2¢ entry / 4¢ stop slippage: net P&L falls **$138,639 → $4,860**
- **Break-even ≈ 2.2¢/share. QQQ's typical spread is ~1¢.**
- Adding an NQ-futures confirmation recovers a real signal (t = 2.05; a placebo using QQQ's
  own pre-market bar gives t = 1.27, n.s.) — but the bootstrap Sharpe CI **[0.05, 1.41]**
  fully overlaps buy-and-hold **[−0.03, 1.47]**
- **76% of the filtered P&L is 2022 alone.** The filter lost money in 2017, 2020 and 2023.

His verdict on the original: the zero-slippage assumption *"is the single load-bearing input
behind its headline result."*

### 1.3 The peer-reviewed benchmark, and it is negative

**Heston, Korajczyk & Sadka (2010), *Journal of Finance* 65(4)** — 1,715 NYSE firms,
2001–2005, half-hour intervals. They find genuine intraday return continuation at exact
one-day multiples (decile spread 3.01 bps at lag 13, t > 8.7). Then they subtract the spread:

> implied one-way costs **3 bps for large stocks** vs a **1–3 bps gross spread**; once you
> buy at the ask and sell at the bid, *"the average results are negative for all size
> categories at all times of the day, indicating that the periodicity we find does not
> indicate a pure profit opportunity."*

**This is a peer-reviewed, explicitly cost-tested finding that intraday cross-sectional
continuation in US equities does not survive the spread — in large caps specifically.**
It is the honest benchmark for anything built here.

### 1.4 Gao, Han, Li & Zhou (2018) — real, but regime-conditional

*Market Intraday Momentum*, **Journal of Financial Economics 129(2)** — peer-reviewed.
SPY, TAQ data, 1993–2013. The return from **prior close → 10:00 ET** (note: this *includes*
the overnight gap — easy to implement wrongly) predicts the **15:30 → 16:00** return.

- β = 6.94, t = 4.08, in-sample R² = 1.6%; out-of-sample R²ₒₛ = 1.4%
- Timing strategy: 6.67% annual return, Sharpe 1.08, 54.4% hit rate. **No R figure — it is a
  fixed-holding-period strategy with no stop or target, so R is undefined. That 54.4% is not
  comparable to a stop/target win rate.**
- Authors do subtract the entry spread post-2005: 7.96% → **6.52%**

**The caveat that matters:**

| Condition | Joint R² |
|---|---|
| Financial crisis (Dec 2007 – Jun 2009) | **6.9%** |
| Excluding the crisis | **1.1%** |
| Recession / expansion | 6.6% / **1.0%** |
| High-vol tercile / low-vol tercile | 3.3% / **0.6%** |

Outside crises and high-volatility days the effect is ~1% R² and close to unexploitable.
If used, it must be **gated on a realized-volatility condition** and sized for a
~6.5%/yr, Sharpe-1 effect — not a 40% IRR.

**Gap:** no peer-reviewed post-2013 US extension was found. The only decay figures located
were vendor-sourced and unverified.

### 1.5 The one component worth keeping

The stocks ORB paper's own numbers give the game away:

| Variant | Total return | IRR | **Sharpe** | MaxDD |
|---|---|---|---|---|
| **Unfiltered ORB** (all qualifying stocks) | 29% | 3.2% | **0.48** | 13% |
| **Top-20 by first-5-min relative volume** | 1,637% | 41.6% | **2.81** | 12% |

**The ORB trigger itself is worth ~3.2%/yr. One hundred percent of the claimed edge comes
from the relative-volume selection filter.** Whatever is being measured, it is not an
opening-range breakout — it is a cross-sectional selection effect on abnormal opening volume.

That is also the one part of this literature that rhymes with what this project already
believes: `warrior_5_selection_in_practice.md` is entirely about selection, and the census
found Cameron's edge sits in which names he picks, not in the trigger he uses.

### 1.6 The parameter cliff — read this as a warning

Opening-range length sensitivity, from the paper's own Table 3:

| OR length | Sharpe | MaxDD |
|---|---|---|
| **5 min** | **2.81** | 12% |
| 15 min | 1.43 | 11% |
| **30 min** | **0.21** | **35%** |
| 60 min | 0.40 | 21% |

A genuine microstructural effect degrades smoothly. Sharpe falling **2.81 → 0.21** between 5
and 30 minutes with drawdown tripling is a parameter sitting on a spike. The authors concede
the 5-minute dominance is unexplained. **Under PROGRAM_INDEX §4's boundary-check rule this
alone would disqualify the result.**

### 1.7 Other relevant peer-reviewed work

- **Li, Sakkas & Urquhart (2022), *Journal of Financial Markets* 57** — intraday time-series
  momentum across 16 markets is *"stronger when liquidity is low, volatility is high."*
  Precisely the opposite of the target universe.
- **Lou, Polk & Skouras (2019), *JFE* 134(1)** — momentum accrues **overnight**, reversal
  accrues **intraday**. A structural warning against assuming daily-horizon momentum results
  transfer to intraday execution.
- **Onishchenko et al. (2021)** — intraday momentum's predictive power vanishes once you
  control for institutional order imbalance. The pattern is a proxy for late-informed flow,
  not a standalone price effect.
- **McLean & Pontiff (2016), *Journal of Finance* 71(1)** — 97 predictors: returns **26%
  lower out-of-sample pre-publication, 58% lower post-publication**, and *predictors with
  larger in-sample returns decay more*. A Sharpe-2.81 result published in 2024 and promoted
  to a large retail audience is the exact profile that decays hardest.

---

## 2. Bollinger + RSI mean reversion — the evidence is against it

### 2.1 Bollinger and RSI are the same signal

Spearman rank correlation **RSI vs Bollinger %b = 0.95** on S&P 500 daily data, Mar 1957 –
Dec 2023 (<https://grzegorz.link/indicators>). Most pairwise correlations among RSI, ROC,
CCI, %b, Stochastic and the MACD line exceed 0.8.

This is not a curiosity, it follows from the construction: **%b is literally a z-score of
price against a rolling mean, and RSI is a bounded monotone transform of the same recent
displacement.** Requiring *both* "below the lower band" *and* "RSI < 10" does not add an
independent confirmation — it tightens the same threshold. Any backtest improvement from
adding RSI to Bollinger should be treated as **threshold tuning across two correlated
free parameters**, which inflates in-sample performance without adding out-of-sample
information.

### 2.2 Connors RSI(2) — the retail canon, and its decay

Published rules (StockCharts codification): RSI period **2**; long only above the 200-day
SMA; enter when **RSI(2) < 5** (or < 10); exit on a close above the **5-day SMA**;
**no stop loss** — Connors states stops hurt performance. Typical hold 3–5 days.
Book sample: 1995–2007. **No commission or slippage assumption is stated anywhere.**

Independent forward tests all show the same shape:

| Test | Universe | Period | Result |
|---|---|---|---|
| decodingmarkets #1 | S&P 500 index | 1995–2008 | 83.7% win, 3.91% ann. |
| same, forward | S&P 500 index | → 2016 | **1.35% ann.**, MaxDD −13.2% |
| decodingmarkets #3 | S&P 1500 stocks, survivorship-adjusted, $0.01/sh | 1995–2016 | 64.7% win, 23.9% ann. — *"strongest performance at the beginning of the test period"* |
| EasyLanguage Mastery | @ES futures | 2000–2019 | **0.041% annual return**, costs excluded |

**Not one of these reports an average win / average loss, profit factor, or expectancy.**
Under PROGRAM_INDEX §4 a win rate without a paired reward figure is not a result — and here
it is worse than usual, because the published rules contain **no stop**, so the left tail is
unbounded. A 65–84% win rate with an unbounded loss tail and no reported R is uninterpretable.

### 2.3 Bollinger Bands specifically

- **Lento, Gradojevic & Wright (2007), *Applied Financial Economics Letters* 3(4)** —
  peer-reviewed: *"after adjusting for transaction costs, the BB are consistently unable to
  earn profits in excess of the buy-and-hold trading strategy."*
- **Fang, Jacobsen et al. (2014)**, 14 indices, samples to 1885–2014: the Bollinger buy/sell
  spread collapsed from **0.454%/day pre-1983** to **0.296% (1983–2001)** to
  **0.002%/day post-2002** — effectively zero. Popularity-driven decay of a published,
  retail-distributed rule.
- **Bajgrowicz & Scaillet (2012), *JFE* 106(3)** — 7,846 technical rules on the DJIA
  1897–2011 with false-discovery-rate control: outperforming rules exist but are **not
  selectable ex ante**; *"since 1962, most strategies have been unprofitable, even with the
  assumption of zero transaction costs."*

**No peer-reviewed test of the specific "close below lower BB(20,2) → exit at the middle
band" rule on individual liquid US large caps appears to exist.** Everything on that exact
configuration is vendor content.

### 2.4 Short-term reversal is a liquidity premium — and it lives in illiquid names

This is the central finding and it bears directly on the universe choice.

- **Conrad, Gultekin & Kaul (1997), *JBES* 15(3)** — contrarian profits are *"largely
  generated by the bid-ask bounce… accounting for this bounce by using bid prices eliminates
  all profits for NASDAQ-NMS and most for NYSE/AMEX."* The residue *"disappears at trivial
  levels of transaction costs."*
- **Avramov, Chordia & Goyal (2006), *Journal of Finance* 61(5)** — weekly reversals are
  strongest in high-turnover × high-illiquidity stocks (**1.08%/week**). Proportional
  effective spreads on those same stocks: **3.18%**. The signal and the cost are the same
  variable.
- **Nagel (2012), *Review of Financial Studies* 25(7), "Evaporating Liquidity"** —
  **~41% of gross reversal return is bid-ask bounce**. For the **largest, most liquid,
  lowest-volatility stocks: ~0.05%/day at low VIX, ~0.10%/day at high VIX.** Smallest stocks
  at high VIX: ~0.80%/day. Unconditionally, large-cap reversal returns are *"very close to
  zero."*
- **Khandani & Lo** — the daily contrarian's average return decayed **1.38%/day (1995) →
  0.44% (2000) → 0.13% (2007)**, with a 1995 size gradient of **3.57%/day smallest decile vs
  0.04%/day largest**.

### 2.5 The two numbers that settle it

**Novy-Marx & Velikov (2016), *RFS* 29(1)** — value-weighted, NYSE breakpoints, 1963–2012:

| | Value |
|---|---|
| Short-term reversal, gross | +0.37%/month |
| Monthly turnover | 90.9% per side |
| Trading costs | 1.65%/month |
| **Net return** | **−1.28%/month** |
| Net with best-practice cost mitigation | **−0.72%/month** |

That is an *institutional* cost calculation. A retail version is worse.

**Blitz, Huij, Lansdorp & van Vliet** — restricted to above-NYSE-median market cap:
conventional reversal nets **−0.26%/month**, and its **break-even cost is 10 bps
round-trip**. A retail round trip in a liquid large cap is ~5 bps of spread plus commission
(§4) — at or past break-even before anything else.

### 2.6 The finding that reverses the premise

**Medhat & Schmeling (2022), "Short-Term Momentum", *Review of Financial Studies* 35(3)** —
peer-reviewed, 1963–2018, conditional double sort on prior-month return × prior-month
**turnover**, value-weighted on NYSE breakpoints:

| Portfolio | Monthly return | t |
|---|---|---|
| Univariate short-term reversal | **−0.28%** | **−1.68 (not significant)** |
| Reversal among **low-turnover** stocks | −1.41% | −7.13 |
| **Momentum among high-turnover stocks** | **+1.37%** | **4.74** |
| Large-cap (largest 500) short-term momentum | +0.42% | 4.91 |
| **Same, net of costs, ex end-of-month** | **+0.77%/month** | **3.90** |

Read carefully: **in liquid, high-turnover large caps — exactly the universe Ben chose — the
short-horizon effect is MOMENTUM, not reversal.** Buying oversold liquid large caps at a
multi-day-to-monthly horizon is trading against the documented sign.

This is the only peer-reviewed, cost-tested, **net positive** result found anywhere in this
review for this universe.

### 2.7 What does survive — and only in modified form

Every surviving version of reversal requires a transform, not the raw signal:

| Version | Break-even / net | Source quality |
|---|---|---|
| Raw price reversal, large caps | −0.26 to −1.28%/mo; break-even **10 bps** | Peer-reviewed (RFS, JBF) |
| **Residual / beta-neutralised** reversal | +0.70%/mo; break-even **56 bps** (48 bps in largest 500) | Practitioner, Robeco-affiliated |
| Discount-rate-decomposed reversal | after-cost alpha ≈ 0.54%/mo | NY Fed staff report |
| **VIX-conditional** reversal, large caps | ~0.10%/day at 95th-pct VIX | Peer-reviewed (Nagel, RFS) |
| de Groot/Huij/Zhou "smart" reversal, 100 largest | net **53.1 bps/week**, t=6.4 | Peer-reviewed, but institutional construction, $1M clips, daily rebalance, sample ends 2009 |

Note that de Groot's *standard* (non-optimised) version of the same strategy on the 1,500
largest lost **−103.7 bps/week net** — costs were 267% of gross. The edge lives entirely in
construction detail that a retail account cannot reproduce.

### 2.8 When diversification fails

The direct answer to "do momentum and mean reversion lose together": **yes, in deleveraging
events.** Khandani & Lo, week of 6–10 August 2007, unleveraged daily contrarian:
**−1.16%, −2.83%, −2.86%** on consecutive days (3-day −6.85%), then **+5.92%**. At 8:1
leverage that is roughly −25% of assets before the rebound. Long/short equity and quant
long-only funds took correlated losses simultaneously, caused by forced deleveraging among
managers sharing common factor exposures.

Correlation is low in normal times and goes to 1 precisely in the events that cause the worst
losses. Any diversification claim in the spec must carry this caveat.

**Gap:** a clean published correlation coefficient between a short-term reversal factor and a
momentum factor was not found. This is computable from Ken French's `ST_Rev` and `Mom` daily
factor files in about ten lines and is worth doing directly.

---

## 3. Execution reality — and this is where the good news is

### 3.1 Friction collapses

| | Small caps (Ben's measured) | Liquid large cap, 500 sh × $150 |
|---|---|---|
| Commission + fees, round trip | part of **$4.26** | **$6.66** (Fixed) / **$8.35** (Tiered, taking) / **$4.05** (Tiered, posting) |
| As bps of notional | very large on a $3 stock | **0.89 bps** |
| Quoted spread | 175–264 bps (<$100M cap, SEC DERA) | **~4.5 bps** S&P 500 avg; ~3.7 bps top 100; ~1 bp mega caps |
| **All-in round trip** | — | **≈ 5.4 bps ≈ $40 on $75,000** |

At the $10–19.99 price bucket the SEC's own study puts the small-cap median quoted spread at
**28.61¢** against a large-cap **1.03¢** — a **28×** difference at identical price.

**The friction case for the universe change is overwhelming.** Ben's $4.26 was dominated by
share count: cheap stock means many shares means high per-share commission and exchange fees.
On large caps the dollar figure is similar but the notional is 10–20× larger.

**Defensible backtest slippage assumption: 3 bps per side** for S&P 500 marketable orders at
≤$100k, **5 bps per side** for Russell 1000 names outside the S&P 500. Model **stop exits at
2× entry slippage** — stops fill on the wrong side of a fast move (Brusco's 2¢/4¢ asymmetry).

### 3.2 Fixed vs Tiered is a strategy-level decision

At ~$150/share, Fixed is cheaper **whenever you cross the spread** ($6.66 vs $8.35); Tiered is
~40% cheaper **whenever you post and get filled** ($4.05 vs $6.66), because you receive the
$0.0013–0.0018 add-liquidity rebate instead of paying the $0.0030 taker fee.

An account can hold only one structure at a time. **Intraday marketable system → Fixed.
Passive/MOC swing system → Tiered.** If both run in one account, Fixed is the safer default.

### 3.3 The Pattern Day Trader rule is gone

**FINRA Regulatory Notice 26-10; effective 4 June 2026.** The PDT designation and the
**$25,000 minimum equity requirement** were eliminated, replaced by per-account intraday
margin deficit calculations. The $25,000 minimum ended immediately on that date; the phase-in
to 20 October 2027 applies only to firms' implementation machinery.

It did previously apply to Ben — the trigger was always account structure (Reg T margin, US
securities), not residency. **Any design constraint built around $25k NLV or three day trades
per five days should be deleted.** IBKR's Australian pages still carry legacy text, so this
should be confirmed in Client Portal rather than assumed.

### 3.4 The actual binding constraint: AUD 50,000

IBKR Australia caps **retail** clients' margin borrowing at **AUD 50,000**, regardless of what
Reg T or Portfolio Margin arithmetic would otherwise allow. Portfolio Margin requires USD
110,000 NLV to open and would give roughly 3× the capital efficiency on a hedged book — but
that efficiency is largely theoretical under the retail cap.

**This is the most important open practical question in the whole design**, because a
dollar-neutral long/short book of 40–100 names is not constructible under it.

### 3.5 Carry dominates commission on the swing side

IBKR Australia USD margin, retail: base **5.130%** under $100k, **plus a 2% surcharge on
non-AUD borrowings** → effectively **~7.13%/yr**.

A $75,000 long held 5 calendar days on 50% margin ($37,500 borrowed) costs **≈ $36.65** in
financing — roughly **5× the entire round-trip commission**. Shorts are cheaper to carry:
short-sale proceeds earn benchmark − 0.5% (haircut below $100k NAV) against a GC borrow of
roughly 0.25–0.50% for S&P 500 names. **This long/short carry asymmetry belongs in the
expected-value model, not as an afterthought.**

### 3.6 SSR contaminates the intraday short side

Reg SHO **Rule 201** triggers when a stock falls **10% or more from the prior day's official
close**, and applies for the **rest of that day and all of the next**. While active, a short
sale **cannot be executed or displayed at or below the national best bid**.

Practically: **a marketable short becomes a passive order at NBB+$0.01.** You fill only if the
stock ticks up to you — which is adverse selection. Short *exits* are unaffected.

**Backtest requirement:** any short-side simulation that assumes a fill at the bid or at bar
close must screen out `low ≤ 0.90 × prior_close` for **both the current and prior day**, or
the short-side results are fiction. On S&P 500 names this is rare, but it clusters exactly in
the high-volatility regimes where a short strategy expects its best days.

### 3.7 IBKR is the wrong historical data source for this

The TWS API caps 5-minute bar requests at **one week per request**, with **60 requests per
ten minutes**. Five years of 5-minute bars is ~260 requests per symbol ≈ 43 minutes per
symbol — **~15 days of continuous pulling for an S&P 500 universe.** IBKR also serves **no
data for delisted securities**, which is a survivorship-bias trap for any index-constituent
backtest.

Source 5-minute history elsewhere (Alpha Vantage `TIME_SERIES_INTRADAY` is already connected
to this project; Polygon and Databento are the paid alternatives) and use IBKR for live data
and execution only.

### 3.8 Market data

IBKR's free US feed is **Cboe One + IEX — not the NBBO**. Full consolidated NBBO is
**USD 4.50/month** non-professional (the add-on streaming bundle, or three Network L1 feeds
at $1.50 each). That is less than one round trip's commission per month, and without it the
live spread-crossing cost will diverge from any model. Professional classification costs
**$125/month** — a 28× jump — so the non-pro status is worth confirming.

---

## 4. What this review could not verify

Stated explicitly, per §4 of the index:

- **Primary PDFs of all three Zarattini papers** (SSRN PDF delivery blocked). The QQQ paper's
  entry mechanic — market-at-bar-2 versus stop-at-range-extreme — is **genuinely ambiguous
  across secondary sources and matters a great deal**.
- Whether any Zarattini/Aziz paper has been peer-reviewed. None was found.
- Any **post-2013 academic extension of Gao et al.** on US data.
- **Connors & Alvarez's own results tables** — the book was not obtainable; no secondary
  source reproduces them. Any specific win rate attributed to the book is unverified.
- **Jegadeesh (1990)'s** specific abnormal-return figure (host returned HTTP 425).
- The **ST_Rev vs Mom correlation** — the Dartmouth host was blocked. Computable locally.
- IBKR's markup over street borrow rates, and how far back IBKR 5-minute bars actually extend.
- Whether IBKR Australia has completed its implementation of the post-PDT intraday margin
  regime as of 11 Sep 2026.

---

## 5. Sources

**Peer-reviewed**
- Heston, Korajczyk & Sadka (2010), *JF* 65(4) — <https://www.bauer.uh.edu/departments/finance/documents/Heston_Korajczyk_Sadka_paper_UH.pdf>
- Gao, Han, Li & Zhou (2018), *JFE* 129(2) — <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866>
- Medhat & Schmeling (2022), *RFS* 35(3) — <https://openaccess.city.ac.uk/id/eprint/31278/1/MS_short_term_mom_v27.pdf>
- Novy-Marx & Velikov (2016), *RFS* 29(1) — <https://mysimon.rochester.edu/novy-marx/research/ToAatTC.pdf>
- Nagel (2012), *RFS* 25(7) — <https://www.nber.org/system/files/working_papers/w17653/w17653.pdf>
- Avramov, Chordia & Goyal (2006), *JF* 61(5) — <https://users.nber.org/~confer/2004/mmsu04/goyal.pdf>
- Conrad, Gultekin & Kaul (1997), *JBES* 15(3) — <https://doi.org/10.1080/07350015.1997.10524715>
- Bajgrowicz & Scaillet (2012), *JFE* 106(3)
- McLean & Pontiff (2016), *JF* 71(1) — <https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365>
- Li, Sakkas & Urquhart (2022), *JFM* 57 — <https://www.sciencedirect.com/science/article/abs/pii/S138641812100001X>
- Lou, Polk & Skouras (2019), *JFE* 134(1) — <https://personal.lse.ac.uk/polk/research/TugOfWar.pdf>
- de Groot, Huij & Zhou (2012), *JBF* 36(2) — <https://repub.eur.nl/pub/25718/AnotherLook_2011.pdf>
- Lento, Gradojevic & Wright (2007), *AFEL* 3(4)

**Preprint / practitioner**
- Zarattini & Aziz, SSRN 4416622 · SSRN 4729284 · SSRN 4824172
- Brusco independent replication — <https://github.com/giovannibrusco/zarattini-2023-orb-qqq>
- Khandani & Lo — <https://w4.stern.nyu.edu/finance/docs/pdfs/Seminars/083w-lo.pdf>
- Blitz, Huij, Lansdorp & van Vliet — <https://www.efmaefm.org/0EFMSYMPOSIUM/2012/papers/017_update.pdf>
- Da, Liu & Schaumburg, NY Fed SR513 — <https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr513.pdf>
- Fang, Jacobsen et al. (2014) — <https://acfr.aut.ac.nz/__data/assets/pdf_file/0007/29896/100009-Popularity-vs-Profitability-BB-August-Final.pdf>
- Grzegorz Link, indicator rank correlations — <https://grzegorz.link/indicators>

**Regulatory / broker (primary)**
- FINRA Regulatory Notice 26-10 (PDT elimination) — <https://www.finra.org/rules-guidance/notices/26-10>
- SEC Rule 201 Reg SHO FAQ — <https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions-7>
- SEC DERA, small-cap market quality — <https://www.sec.gov/marketstructure/research/small_cap_liquidity.pdf>
- Nasdaq, S&P 500 spreads — <https://www.nasdaq.com/articles/sampling-sp-500-minimize-spreads>
- IBKR commissions — <https://www.interactivebrokers.com.au/en/pricing/commissions-stocks.php>
- IBKR AU margin rates — <https://www.interactivebrokers.com.au/en/trading/margin-rates.php>
- IBKR AU US-stocks margin — <https://www.interactivebrokers.com.au/en/index.php?f=37749&hm=au&ex=us>
- TWS API historical limits — <https://interactivebrokers.github.io/tws-api/historical_limitations.html>
