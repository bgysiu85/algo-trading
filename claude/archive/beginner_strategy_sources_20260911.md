# Three beginner strategy sources, assessed — and independently tested

**Created:** 2026-09-11
**Status:** SOURCE ASSESSMENT + an independent replication run on SPX 2006–2026.
**Sources:** an r/algotrading thread, an IG Australia marketing page, and a Quantified
Strategies YouTube video, supplied by Ben 2026-09-11.
**Governing standards:** `PROGRAM_INDEX.md` §4.

---

## 0. Verdict

| Source | Verdict |
|---|---|
| **r/algotrading thread** | **Could not read** — reddit.com is blocked by this session's egress policy. Not routed around. |
| **IG Australia, "Top 5 Algorithmic Trading Strategies"** | **No operational content.** Five strategy names, zero rules, zero parameters, zero numbers. Marketing copy from a CFD broker. |
| **Quantified Strategies, "7 Best Algorithmic Trading Strategies for Beginners"** | **Genuinely specified and worth reading** — precise entry and exit rules for all seven. But it reports one badly misleading metric, omits transaction costs entirely, and **all seven underperform buy-and-hold** when I ran them myself. |

**Two things in the video are worth taking.** Both are in §5.

---

## 1. The Reddit thread — read 2026-09-11 from text Ben supplied

`reddit.com` is blocked for this session at both the fetch layer (`SITE_BLOCKED`) and the
browser pane (*"not allowed due to safety restrictions"*). Reported rather than worked around.
Ben pasted the text, so it was assessed from that.

**What it is:** a **taxonomy**, not a set of strategies. ~20 archetype headings (trend
following, mean reversion, grid, arbitrage, scalping, options, SMC, martingale…) with
sub-bullets. **613 upvotes, 178 comments, and zero backtests, zero parameters, zero performance
figures, zero cost assumptions anywhere in the post or the comments.**

To be fair to the author, he states his purpose plainly: *"I simply want to implement different
strategies and see which is performing which way to test my software."* It is a test-harness
checklist, and on that basis it is reasonable. It is not what the title implies.

**The best comment in the thread got 4 upvotes** — *"the main question should be which of these
actually have edge."* The reply is the thread conceding the point: *"Most of the basic ones only
become interesting, with additional tweaking. For applying certain stop loss limit strategies or
only utilizing them in certain market regimes."*

**Three things worth extracting**, all pursued:

| Item | Outcome |
|---|---|
| **"151 Trading Strategies"**, SSRN 3247865 | Assessed in full — **§9 below**. Short version: retracted, and contains no backtests by design. |
| **Momentum rotation** — Antonacci GEM, Meb Faber, Clenow | Verified — **`diversifier_candidates_20260911.md`**. GEM **rejected** on out-of-sample evidence; a robustness finding worth keeping came out of it. |
| **TradingView strategy script library** | Not pursued. Relevant given the Pine work; expect mostly noise, and the editors' picks filter is the sane entry point. |

**One item to actively ignore: martingale**, which the post includes with *"it is a classic and
basic strategy for you to play with. There are good papers on it too."* There are good papers on
gambler's ruin; that is not the same thing. Grid trading, also on the list, shares the failure
mode — a commenter flags it himself: *"can blow up accounts if not managed properly."*

**Two context notes.** The two highest-engagement comments in the thread (84 and 74 upvotes)
were both removed by moderators. And this thread is the likely origin of the Papers With
Backtest suggestion — a commenter lists it first among paid resources at *"$600-1200/year"*;
the assessment in `tooling_audit_20260911.md` stands, and the actual price is $450/yr.

---

## 2. IG Australia — nothing to assess

Published 2025-07-07, Anzél Killian. Five "strategies": **trend following, arbitrage, mean
reversion, index fund rebalancing, market timing.**

For every one of the five: no entry rule, no exit rule, no indicator named, no threshold, no
timeframe, no universe, no backtest, no sample, no performance figure. The mean reversion
entry, in full, is *"seeking instances where prices deviate significantly with expectation
they'll return"* — no definition of "significantly".

Transaction costs appear once, as a **benefit**: *"transaction costs may be reduced."* No
spread or slippage figure anywhere.

Two things worth naming. First, IG is a **CFD broker** — the page assumes CFD trading and
carries the standard leverage warning. A broker whose revenue is spread and financing has an
interest in readers trading more, which is context for a page listing "market timing" as a
strategy. Second, "index fund rebalancing" — front-running index reconstitution — is a real
documented effect but it is an **institutional** one; it needs to be in the queue ahead of the
funds, which a retail account is not.

**Nothing here is actionable and nothing should be cited from it.**

---

## 3. Quantified Strategies — the rules, extracted

Credit where due: the video opens with *"about 90% of trading advice online is impossible to
backtest"* and then gives precise, codeable rules for all seven. That is rarer than it should
be. Their claimed results:

| # | Strategy | Rules | Their claim |
|---|---|---|---|
| 1 | **200-day MA** | Long S&P 500 when close > 200-day MA, flat below | Since 1960: **6.6%/yr** vs buy-hold 7.1% (ex-div), maxDD **28%** vs 56%, invested ~70% |
| 1b | **…as a regime filter** | Buy RSI(5)<35, sell RSI(5)>50; trade only when price > 200-day MA | maxDD **31% → 14%** with the filter |
| 2 | **Golden cross** | Long when 50-day MA > 200-day MA | Since 1960: 33 trades, ~400 days each, **79% winners**, avg gain **15.7%**, **6.7%/yr**, maxDD 33% |
| 3 | **TQQQ / BTAL** | Each January rebalance to 33% TQQQ / 67% BTAL | 2012–now: **18%/yr**, maxDD 28%, beat NASDAQ 8 of 13 years |
| 4 | **Gold momentum** (via Allocate Smartly) | Month-end: if 12-month total return of **both** GLD and IEF is positive → long gold; else cash | Since 1970: **11.5%/yr**, maxDD 31% vs 64% |
| 5a | **RSI(2) on SPY** | Buy RSI(2)<10, sell RSI(2)>80, at the close | 33 yrs: $100k → **$1.6M**, **9%/yr**, invested 27% |
| 5b | **RSI(2) + "QS exit"** | Buy RSI(2)<10, **sell when close > yesterday's high** | $100k → $1.2M, maxDD **23%**, "rarely worse than 12%" |
| 6 | **Choppiness + RSI(2)** | Choppiness(14) < 50 **and** RSI(2) < 20 → long; exit when close > yesterday's close, or after 5 days | **0.69%/trade**, invested 15%, **8.5%/yr**, maxDD 23% |
| 7 | **Turnaround Tuesday** | If Monday and close < Friday's low → buy Monday close; exit when close > previous day's high, or after 4 days | 1993–now: $100k → **$800k**, **0.6%/trade**, 6.5%/yr, invested 11%, maxDD 20% |

**What the video never states: any transaction cost, spread or slippage assumption.** For a
video whose opening pitch is backtestability, that is the omission that matters.

Two more, by this project's standards: strategy 2 reports **"79% of trades were winners"**
and an average gain, but **no average loss and no R** — the failure `win_rate_and_r.md` exists to
name. And these seven are the survivors of a site advertising *"hundreds of both free and paid
strategies"*: a selected top-7 from a large search, with no trial count and no deflated Sharpe.

---

## 4. I ran them — SPX, 2006-10-24 → 2026-09-10, 5,000 bars

Independent test on TradingView SPX daily. Costs charged at **2 bps per side** (generous but
realistic for SPY, the cheapest instrument in existence). Price index, so dividends excluded —
the same basis the video uses for its buy-and-hold comparison.

| Strategy | CAGR | Max DD | In market | Trades |
|---|---:|---:|---:|---:|
| **Buy & hold SPX** | **9.07%** | **−56.8%** | 100% | 0 |
| 1. 200-day MA | 6.53% | **−20.0%** | 76% | 61 |
| 2. Golden cross | 7.61% | −33.9% | 76% | 9 |
| 1b. RSI(5)<35/>50, **no** filter | 6.38% | −29.9% | 24% | 232 |
| 1c. same **+ 200-day filter** | 5.69% | **−15.4%** | 15% | 167 |
| 5a. RSI(2)<10 → >80 | **5.00%** | −34.5% | 27% | 183 |
| 5b. RSI(2)<10 → QS exit | 6.22% | −22.9% | 16% | 212 |
| 6. Choppiness + RSI(2) | 5.50% | **−15.0%** | 11% | 323 |
| 7. Turnaround Tuesday | 6.51% | −21.5% | 11% | 199 |

### 4a. What replicates

**Strategies 1, 2 and 7 reproduce closely.** 200-day MA at 6.53% against their 6.6%; golden
cross 7.61% against 6.7%; Turnaround Tuesday 6.51% against 6.5%. On a different window, from a
different data source, with costs applied. That is a real point in the video's favour and it
should be said.

**The regime-filter claim reproduces almost exactly.** They claim max drawdown falls from 31%
to 14% when the 200-day filter is added to the RSI(5) mean-reversion rule. I measure
**29.9% → 15.4%**. That is the cleanest verified finding in the whole video.

### 4b. What does not

**Strategies 5a and 6 come in far below their claims.** 5a: they say 9%/yr, I measure
**5.00%**. Strategy 6: they say 8.5%/yr, I measure **5.50%**. Their windows start in 1993 and
earlier; mine is the most recent 20 years. Short-horizon index mean reversion has decayed,
which is exactly what Nagel (*RFS* 2012) and the decay literature in
`largecap_evidence_20260911.md` §2 predict.

### 4c. The finding that matters most

**All seven underperform buy-and-hold on return.** Buy-and-hold returns 9.07% price-only;
the best strategy returns 7.61%.

Dividends and cash interest roughly cancel across the table — a 76%-exposure strategy collects
most of the ~1.9% dividend yield, an 11%-exposure strategy collects almost none but earns cash
on idle capital for 89% of the time — so the comparison stands as shown.

**What they do buy is drawdown.** −56.8% becomes −20.0%, −15.4%, −15.0%. That is a genuine and
valuable property, and the video is honest about it for strategies 1 and 2. It is **not** what
strategies 5, 6 and 7 are sold as — those are presented as standalone return generators, with
no buy-and-hold comparison offered at all.

### 4d. Split-half — the decay check the video does not do

| Strategy | 2007–2016 | 2016–2026 |
|---|---:|---:|
| **Buy & hold** | **4.5%** | **13.4%** |
| 200-day MA | 3.87% | 9.08% |
| Golden cross | 6.32% | 8.88% |
| RSI(2) → >80 | 3.04% | 6.80% |
| RSI(2) → QS exit | 5.35% | 7.03% |
| Choppiness + RSI(2) | 6.54% | **4.57%** |
| Turnaround Tuesday | 8.12% | **5.07%** |

**Relative to buy-and-hold, every one of them got worse in the second half** — and the two
shortest-horizon rules got worse in absolute terms while the index tripled its rate.

---

## 5. The metric problem — and it is serious

The video reports strategy 6 as *"8.5% annually… risk-adjusted return of 52%"* and strategy 1
as *"a better risk-adjusted return, 9.6%"*.

**That is not risk adjustment. It is CAGR ÷ time-in-market.** Reproduced on my own run:

| Strategy | CAGR | Their metric, applied |
|---|---:|---:|
| Buy & hold | 9.07% | **9.1%** |
| 200-day MA | 6.53% | 8.5% |
| Choppiness + RSI(2) | 5.50% | **48.6%** |
| Turnaround Tuesday | 6.51% | **59.8%** |

My 48.6% against their quoted 52% for the same strategy confirms the formula.

**It is a pure function of exposure.** It assumes idle capital earns the same rate — it does
not — and it ignores that concentrated exposure carries concentrated risk. Applied to
buy-and-hold it does nothing at all (100% exposure), which is precisely why it always flatters
the low-exposure strategy. By this metric Turnaround Tuesday "returns" 59.8% against
buy-and-hold's 9.1%, while actually earning **6.51% against 9.07%**.

**Do not let this number travel.** Any figure labelled "risk-adjusted return" from this source
should be multiplied back by time-in-market before it is compared to anything.

---

## 6. What is actually worth taking

Two things, both testable here in an afternoon.

### 6.1 The "QS exit" — a genuinely different exit rule

> **Exit when the close is above the previous bar's high.**

Not a trail, not a target, not a time stop — a **first-profitable-close** exit. It is the only
mechanically novel idea in the video and it is not in this project's tested set
(`mcl_rejected_mechanics.md` covers scale-out, pyramid, scale-up, confirm-N; `cent_stop` and
`hold_cap` cover stops and time; `cameron_exit_result.md` covers partials and breakeven stops).

**In my own run it was a material improvement**, swapping only the exit:

| | CAGR | Max DD | In market |
|---|---:|---:|---:|
| RSI(2)<10 → exit RSI(2)>80 | 5.00% | −34.5% | 27% |
| RSI(2)<10 → **exit close > prev high** | **6.22%** | **−22.9%** | 16% |

Better return, one-third less drawdown, 40% less exposure. Stable across both halves.

**Why this is worth a run on MCL.** `cameron_exit_result.md` names the exit as the largest
untested gap, and `hold_cap_decision.md` §4 found that **1-bar trades are 107 of 485 at
−$36.68 each** while long holds are the best bucket. A first-profitable-close exit is a
different shape from everything rejected so far — it is not a time cap (rejected, monotone),
not a cent stop (rejected, price-band), not a target (cuts the right tail). Register it and
run it on `bar_cache_xnas`.

**Caveat:** it was measured on a mean-reversion entry into an index, where a bounce is the
thesis. MCL is a momentum entry into a low-float runner, where the thesis is continuation. The
same exit could plausibly cut the right tail there — which is exactly the failure mode
`cameron_exit_result.md` §4.2 identified for close targets. **Expect it to fail; run it anyway,
because it is one line and the exit question is open.**

### 6.2 The 200-day regime filter — verified, and different from what was already rejected

Max drawdown **29.9% → 15.4%** on identical entries, reproduced independently. The filter is
the instrument's own price against its own 200-day average.

`ladder_and_regime_20260911.md` §4 tested a regime gate and found it **not adoptable**
(p = 0.2964, non-monotone) — but that gate was **yesterday's market-wide breadth**, a lagged
external measure. This is a **per-instrument, same-bar, price-only** filter. Different
construction, different information, and the same doc noted that the **same-day** version had a
monotone +$5.86 ceiling that was never pursued.

It is also the same shape as the **hold-50% rule** in `warrior_5_selection_in_practice.md` §1 —
"is this name still holding its gain?" — which that doc calls its highest-value item and which
remains unbuilt.

### 6.3 Not worth taking

- **Strategies 3 and 4.** TQQQ/BTAL is 13 years of backtest on a 3× leveraged ETF over the only
  regime that flatters it; the video's own warning (*"built for short-term trades, not
  long-term holds"*) contradicts the strategy it is describing. Gold momentum is fine but the
  video concedes the edge has waned since ~2002 — that is 24 of its 55 years.
- **Strategies 5, 6, 7 as strategies.** They underperform buy-and-hold, and the two fastest
  decayed in the recent half.

---

## 7. One distinction worth recording

`largecap_evidence_20260911.md` §2 assembled a strong case against short-horizon mean
reversion. **That case is about CROSS-SECTIONAL, single-stock reversal** — Novy-Marx & Velikov,
Medhat & Schmeling, Avramov/Chordia/Goyal: sorting stocks on last month's return and trading
the losers against the winners.

**Strategies 5, 6 and 7 here are TIME-SERIES reversal on an index.** That is a different
effect: an index dip is liquidity-driven and carries no idiosyncratic bankruptcy risk, no
delisting, no borrow problem, and the instrument costs 1–2 bps to trade rather than 200+.

So the two bodies of evidence are not in conflict, and index-level mean reversion is the more
defensible of the two. **It is still not a good business** — §4c shows it losing to
buy-and-hold over 20 years on this data — but the reason it fails is decay and opportunity
cost, not the transaction-cost argument that kills the cross-sectional version.

---

## 8. Reproduction

Script: `qs_test.py`. Data: `data_idx/SPX.csv`, TradingView `TVC:SPX`, 5,000 daily bars,
fetched 2026-09-11. Costs 2 bps/side. Choppiness index computed as
`100 · log10(ΣTR(14) / (max(high,14) − min(low,14))) / log10(14)`. All rules coded directly
from the transcript; no parameter was tuned.

**Limits:** price index, dividends excluded; cash interest on idle capital not modelled;
one instrument; no bootstrap or significance testing run — this was a replication check of
published claims, not a strategy evaluation.

---

## 9. Appendix — "151 Trading Strategies" (Kakushadze & Serur), assessed

The one substantive-looking item in the Reddit thread. **It is not what it appears to be.**

### 9.1 The disqualifying facts, in order

**It is formally RETRACTED.** Springer/Palgrave lists it as *"RETRACTED BOOK: 151 Trading
Strategies"*, every one of 19 chapters flagged. The stated reason, verbatim: *"has been retracted
due to **copyright issues regarding the images**."* **Important nuance — this is a
rights/permissions failure, not a finding of misconduct or error.** Almost certainly the ~550
option payoff diagrams were reproduced without clearance. The intellectual content is not
repudiated. But the publisher has withdrawn it.

**It contains no backtests. At all. By explicit design.** The authors state it outright:

> *"Intencionalmente estas notas… **no contienen ninguna simulación numérica, backtests,
> estudios empíricos, etc.**"*

and on purpose:

> *"el propósito de estas notas **no es enseñar al lector cómo hacer dinero** utilizando
> estrategias de trading, sino que simplemente proporcionar información acerca de las
> estrategias que las personas han considerado."*

No performance figures, no Sharpe ratios, no win rates, no drawdowns, no dataset, **no
transaction cost model**, and — remarkably for a work cataloguing 151 strategies — **no
discussion of overfitting, data snooping or multiple testing**. The companion "source code" is
**one generic ~1-page R script** in an appendix, not per-strategy implementations. There is no
public repository.

**The count is padded.** Chapter 17 lists **money laundering, pawning and usury** as
"strategies." That is a direct indicator that the organising principle is "things people do with
capital", not "sources of alpha", and that 151 is a marketing figure.

### 9.2 The reception signal

**232,281 SSRN downloads against roughly 10 academic citations** (Semantic Scholar: 10 citations,
**0 influential**; RePEc: 7). Zero Hacker News submissions. Goodreads **3.00/5 from 9 ratings**;
the sole written review reads **"Graveyard of dead strategies!"**

People download it because it is free and the title promises 151 edges. Almost nobody builds on
it, because there is nothing empirical to build on.

### 9.3 Fitness for this project

| | |
|---|---|
| Strategies that are **intraday** | **2 of ~151** — §6.4 intraday index-ETF arbitrage, §3.19 market-making. Both are latency races retail loses by construction. |
| Strategies touching **US small caps** | **Zero.** The full ~200-section taxonomy contains no heading referencing float, capitalisation tier, gaps, pre-market, or relative volume. |
| Sections that *look* relevant (§3.11–3.15 moving averages, support/resistance, channel) | **Specify no time horizon at all.** Frequency-agnostic formula statements. |
| Chapter 2 — 56 option structures, 38% of the book | Payoff-diagram definitions (what a bull call spread *is*), not edges. Any options primer covers it. |

**Its one legitimate use is as a free, structured bibliography** — roughly 2,000 references and a
900-term glossary. For scoping the *diversifier* leg, chapters 3, 4, 9, 10 and 19 give a fast map
into the literature. Read it as an index into papers, then evaluate those papers on their own
evidence. **Every performance claim must come from elsewhere; the book supplies none.**

Kakushadze's credentials are genuine (physics PhD at Cornell at 23, WorldQuant, author of the
well-known *101 Formulaic Alphas*), which makes the book's framing more surprising rather than
less. Neither author is upselling a course or a signal service.

**Access:** prefer the authors' own free postings — the SSRN English text
(<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3247865>, which the authors themselves
point to as the complete free English version) or the Spanish edition on arXiv
(<https://arxiv.org/abs/1912.04492>). SSRN's PDF delivery endpoint is blocked from this session,
so it needs downloading in a normal browser.
