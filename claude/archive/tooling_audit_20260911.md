# Tooling audit — from the awesome-systematic-trading bibliography

**Created:** 2026-09-11
**Status:** VERIFIED EXTRACTION + maintenance audit. No backtest run.
**Source:** `github.com/paperswithbacktest/awesome-systematic-trading`, read 2026-09-11.
**Context:** follow-on from the Papers With Backtest assessment. The bibliography was the one
free thing worth taking from that site.

---

## 0. The urgent item, first

> ## ⚠ `ib_insync` IS ARCHIVED AND UNMAINTAINED
>
> - Repository **archived 2024-03-14**. Last PyPI release **2023-07-02**.
> - The author, Ewald de Wit, died in March 2024.
> - **This project's IBKR integration is built on it.**
>
> **Replacement: [`ib_async`](https://github.com/ib-api-reloaded/ib_async)** — the community
> continuation, near drop-in, same `IB()` / `reqHistoricalData` surface. Version **2.1.0,
> released 2025-12-08**.
>
> Migration is largely `import ib_async as ib_insync`, but **pin the version** — the
> maintainer group has turned over more than once. This should be checked against the live
> path before the next paper session, because an unmaintained broker API is a silent risk:
> it does not fail loudly, it fails when IBKR changes something.
>
> Note the bibliography itself still lists `ib_insync` as *the* Interactive Brokers option
> with no pointer to a successor. **There is no other non-crypto broker API in the entire
> list.**

---

## 1. What the repository actually is — and a tool-reliability incident worth recording

### 1a. Verified current structure

The **Strategies** section is no longer a curated list. It is an auto-generated leaderboard.
Verbatim from the README:

> *"Every strategy below is a published paper that has been coded and run over its own full
> history. The table is regenerated from the replication catalogue by
> `scripts/build_strategies_table.py`, so the numbers move when the catalogue does."*

> *"Showing the 61 strongest of 1,687 replications that clear a t-statistic of 1.96 over at
> least 10 years, up to 12 per asset class. Sharpe ratios are measured on each strategy's own
> active window, not on a common calendar, and **are gross of trading costs**. Series with an
> annualised volatility outside 1% to 100% are treated as degenerate and dropped."*

Table columns: `| Strategy | Sharpe | t-stat | Volatility | Years tested |`
Asset-class headings, in order: **Equities, Bonds, Commodities, Currencies, Cryptocurrencies,
Derivatives, Multi-asset** — 12 rows max each, 61 total.

**There is no description column, no annual return, no drawdown, no rebalancing frequency, and
no link to the paper** — each row links only to a `paperswithbacktest.com` replication page.

The README also states: *"Older QuantConnect implementations of some of these papers are kept
in `static/strategies`."* **Not verified** — the directory was not inspected.

### 1b. The incident — three reads, three different answers

This is recorded because `PROGRAM_INDEX.md` §4's **"control the tool"** applies here and
caught a real error.

| Read | Reported structure |
|---|---|
| First pass (github.com HTML) | *"does not contain a traditional data table… no Sharpe ratios or performance data displayed"* |
| Second pass (raw markdown) | Auto-generated leaderboard, `Strategy / Sharpe / t-stat / Volatility / Years`, 61 rows |
| Third pass (github.com `?plain=1`) | `Title / Sharpe Ratio / Volatility / Rebalancing / Implementation / Source`, 58 rows, **Faber TAA, Time Series Momentum, Paired Switching, FX Carry** |

**The second read was correct**, confirmed by a fourth read asking for verbatim character-for-
character quotes of the header and first two data rows.

The third read described the **superseded** version of this README — the Quantpedia-derived
list with rebalancing frequencies and QuantConnect implementation files. That content is real
and did exist, but **it is not in the current README**, and anything attributed to it must be
sourced to the underlying papers instead (see §5).

**Methodological note for this project:** summarisation-based web fetching is unreliable on
long documents. It will confidently describe a structure that is not there, including
plausible-looking tables reconstructed from prior knowledge of an older version.
**When a fetched document's structure is load-bearing, re-fetch demanding verbatim quotes of
the exact lines, and treat the first answer as a hypothesis.** This is the same rule
`execution_cost_measured.md` §5 established for data sources, now extended to fetched documents.

---

## 2. The strategy leaderboard is not usable — and it is worse than "not relevant"

Three reasons, in increasing order of seriousness.

**(a) Nothing is intraday.** Zero of the 12 equities rows trade intraday. The fastest rebalance
in the equities table is **weekly** (one row); the mode is monthly. Four rows touch small caps,
all as size-sorted decile portfolios, three of them European — and the one US entry, *Fact,
Fiction, and the Size Effect* (Alquist, Israel & Moskowitz), concludes there is **no robust
pure size premium after adjusting for market beta, delisting bias, January seasonality, and
liquidity.** No row uses float, relative volume, or a price filter.

**(b) The Sharpes are gross of costs, by the README's own admission**, and are measured on each
strategy's own window rather than a common calendar — so they are not comparable to each other,
let alone to anything measured here.

**(c) The auto-generation does not check that the paper describes a tradable strategy.**
This is the disqualifying one. Actual rows from the **Multi-asset** table, verbatim:

| "Strategy" | Sharpe | Vol |
|---|---|---|
| Optimal Annuity Risk Management | 1.62 | 5.4% |
| Explaining low annuity demand: an optimal portfolio application to Japan | 1.60 | 4.8% |
| Inconsistent investment and consumption problems | 1.26 | 2.6% |
| Heuristic Portfolio Rules with Labor Income | 1.21 | 10.5% |

And from **Derivatives**:

| "Strategy" | Sharpe |
|---|---|
| Rational Decision-Making Under Uncertainty: Observed Betting Patterns on a Biased Coin | 0.60 |
| A Theory of Model Sophistication and Operational Risk | 0.50 |

**Annuity demand in Japan, life-cycle consumption theory, a behavioural coin-flipping
experiment, and an operational-risk theory paper have each been assigned a Sharpe ratio and
ranked as trading strategies.** These are not near-misses; they are papers with no trading rule
in them at all.

Two further artefacts confirm the table is unsupervised:

- **Commodities** contains a row at **98.5% annualised volatility** (*Rolling vs. Expanding
  Windows in Mean-Reversion Strategies*, Sharpe 0.36) — squeaking under the stated 100%
  "degenerate" cutoff rather than being caught by it.
- **Currencies** contains a row whose title is truncated mid-sentence:
  *"The Time-Varying Systematic Risk of"*.

**Conclusion: the leaderboard should not be used as a source of strategy candidates, and no
Sharpe figure from it should be quoted anywhere.** The filter that produced it (t > 1.96,
≥10 years, top 12 per class, from 1,687 replications) is a selection rule over a pool whose
members were never checked for being strategies.

---

## 3. Maintenance audit — what in the list is dead

Roughly a third of the bibliography is a graveyard. The entries that matter here:

| Tool | Status | Consequence |
|---|---|---|
| **`ib_insync`** | **Archived 2024-03-14**, last release 2023-07-02 | §0 — **in use in this project** |
| `pandas-ta` | README's own marker: **"no longer available"**; repo taken down | Anything pinning it breaks |
| `pyfolio` | Last release **2019-04-15**; depends on `empyrical` (2020-10-13) | Will not install on modern pandas. **It is the entire "Risk" section of the list** |
| `MlFinLab` | Dormant since 2023-10, **no longer on PyPI** | The trap for robustness work — most blog advice to "use mlfinlab for deflated Sharpe / triple-barrier" recommends software that cannot be installed |
| `backtrader` | Dormant since 2024-08, last release 2023-04-19 | Still the most-recommended framework online, still a dead end. Known look-ahead footguns around `cheat-on-open` |
| `zipline` | Dormant since 2024-02 | Live fork is `zipline-reloaded` (3.1.1, 2025-07-19), not mentioned in the list. Daily-bar engine regardless — wrong for intraday |
| `Quandl` | Archived | — |
| `finta`, `go-tart`, `ta-rust`, `gobacktest`, `Deepdow`, `TradingGym`, `quanttrader`, plus most crypto entries | Archived or dormant per the list's own markers | — |

**`PineForge`** (Pine Script v6 → C++ for offline backtests) is listed and looks directly
relevant given the Pine work. It is brand new, single-purpose and has no track record.
**Treat any claim of Pine-to-TradingView semantic fidelity as unverified** until its output is
diffed bar-by-bar against TradingView. A wrong conversion is worse than no conversion.

---

## 4. Tools worth adopting

Four, in priority order. The rest of the list is either dead, crypto, or solves a problem this
project does not have (portfolio optimisation, forecasting, RL).

**1. `ib_async` — replace `ib_insync`.** §0. Highest priority, lowest effort.

**2. `arch` (`arch.bootstrap`) — the robustness gap.**
<https://github.com/bashtage/arch> · 8.0.0, released 2025-10-21.
Kevin Sheppard's package. Contains `StationaryBootstrap`, `CircularBlockBootstrap`,
`MovingBlockBootstrap`, plus **SPA (Hansen's Superior Predictive Ability)**, **StepM** and the
**Model Confidence Set**.

This maps directly onto `PROGRAM_INDEX.md` §4. The paired-by-symbol bootstrap already in use
is a hand-rolled version of what `arch` does properly, and SPA/StepM/MCS are the peer-reviewed
answers to *"I tested six trail widths and boundary-checked a grid — is the best one real?"* —
a question this project asks constantly and currently answers only with drop-top-N.

**It is not in the bibliography.** The list's entire answer to robustness statistics is
`pyfolio` (dead) and `mlfinlab` (gone). This is the largest omission in the README relative to
what this project actually needs.

**3. `nautilus_trader` — evaluate, do not adopt yet.**
<https://github.com/nautechsystems/nautilus_trader> · 1.231.0, released 2026-08-02.
Rust-core event-driven backtester and live engine with **explicit fill models, latency models
and a simulated matching engine per venue** — and stable adapters for **both Interactive
Brokers and Databento**, the two things already paid for here.

It is the only thing in the list that addresses realistic intraday fills and the broker/data
stack simultaneously. **Catch:** still beta, the API churns between minor versions, and it is a
framework rather than a library — adopting it means rebuilding around its data/actor model and
converting `bar_cache` into a `ParquetDataCatalog`. Worth an evaluation against the open
stop-fill question in `friction_reconciliation_20260911.md` §4, not a migration.

**4. `quantstats` — reporting only.** <https://github.com/ranaroussi/quantstats> · 0.0.81,
2026-01-13 (a more active fork exists as `QuantStats-Lumi`). Tearsheets from a returns series.
**It does not do deflated Sharpe, bootstrap CIs, or multiple-testing correction** — pair with
`arch`, do not mistake it for robustness tooling. Defaults to 252-day annualisation, which is
wrong for an intraday strategy unless set explicitly.

**Explicitly not worth it:** `backtesting.py` (bar-based, fills stops from OHLC without
intrabar sequencing — will systematically flatter stop strategies on wide 1-minute small-cap
bars); `vectorbt` (vectorised, will happily let a signal trade the bar it fired on — the exact
leak §4 of the index exists to catch); every portfolio-optimisation library; everything crypto.

> **The honest comparison:** this project's own engine already charges measured friction and
> has a documented fill model. **It is more honest than at least five of the eight frameworks
> in this list.** The case for adopting anything new is `nautilus_trader`'s event model and
> adapters, or nothing.

---

## 5. Data sources — the list is useless, and the gap is already filled

**Not one entry in the bibliography's Data Sources section offers US intraday bars with
delisted securities and pre-market coverage.** Verified item by item:

- `yfinance` — ~60 days of 1-minute, no delisted tickers, unreliable pre-market. Survivorship-
  biased by construction.
- `pandas-datareader`, `findatapy`, `Investpy`, `Wallstreet`, `FundamentalAnalysis` — daily/EOD
  or fundamentals only.
- `TuShare`, `AkShare` — China only. `Quandl` — archived.
- `OpenBB` / `Fincept` — aggregators; they proxy to other vendors and inherit their biases.
- `pwb-toolbox` — the one entry mentioning tick data, but its documented datasets are daily
  prices, yield curves, fundamentals and macro. Gated behind a subscription.

It is, functionally, a Chinese-market and crypto data list with `yfinance` stapled on.

**Databento — already subscribed here — is the correct answer to this gap**, and is not in the
list. Built from raw exchange feeds (Nasdaq TotalView-ITCH, NYSE, consolidated `EQUS`), which
gives continuous timestamping **including pre- and post-market** and **point-in-time instrument
definitions**, so delisted and renamed tickers remain in the historical record.

> **The point that actually matters, and it is not a vendor question.**
> `PROGRAM_INDEX.md` §7 and `screener_simulation_scope.md` should be checked for whether
> `bar_cache` is built from a **point-in-time universe snapshot** or from a ticker list
> assembled later. If the latter, the screened-universe backtests never see the names that
> halted, reverse-split or delisted — and in $2–20 low-float small caps that is not a rounding
> error, it is most of the tail. Databento supplies the raw material to fix this; it does not
> fix it automatically.
>
> **This is the highest-value item in this document after §0.** It is a bias that would make
> every result in the project look *better* than reality, in the same direction as the three
> `bar_cache` findings that have already inverted.

---

## 6. The diversifier candidates — correctly sourced

The superseded version of this README contained a curated multi-asset list that **is** relevant
to the L2 diversifier question, with rebalancing frequencies and working implementations. It is
no longer in the README. **The following are therefore cited to their papers, not to the
repository**, and their reported figures come from those papers rather than from any replication
seen here.

| Candidate | Instruments | Rebalance | Why it diversifies intraday equity momentum |
|---|---|---|---|
| **Time Series Momentum** — Moskowitz, Ooi & Pedersen, *JFE* 2012 ([PDF](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf)) | ~8–12 micro futures (MES, M2K, MGC, **MCL**, ZN, 6E) | Monthly | Long/short across bonds, FX and commodities — no exposure to US small-cap order flow. Documented crisis alpha: it pays in sustained equity drawdowns, which is when intraday momentum supply also dries up. Peer-reviewed, heavily replicated. **MCL is already traded here, so part of the futures plumbing exists.** |
| **Asset Class Trend-Following** — Faber ([SSRN 962461](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461)) | 5 ETFs | Monthly | 10-month SMA, long-or-cash. **No leverage, no shorting** — so the AUD 50,000 retail margin cap (`largecap_evidence_20260911.md` §3.4) does not bind at all. Lowest operational load of anything credible. |

**Both are cash-funded and need no margin borrowing**, which makes them the only diversifier
candidates identified anywhere in this program that are unaffected by the AUD 50k cap — unlike
L2a's 40–100 name market-neutral book.

**Caveats that must travel with these.** Unlevered they are slow: roughly 5–7%/yr at ~10% vol.
Faber-style TAA has materially underperformed buy-and-hold since roughly 2009, and any figure
quoted for it needs its test window stated. **Neither has been measured here.** They are
candidates for registration, not results — and both must be re-derived over a window chosen
here before any capital moves, per §4 of the index.

---

## 7. What was verified and what was not

**Verified** (verbatim quotation, re-fetched to confirm): the README's Strategies preamble,
table columns, asset-class headings, and the full Multi-asset / Derivatives / Commodities /
Currencies row sets quoted in §2.

**Verified externally:** PyPI release dates and archive status for `ib_insync`, `ib_async`,
`arch`, `nautilus_trader`, `pandas-ta`, `pyfolio`, `backtrader`, `zipline`, `mlfinlab`,
`quantstats`.

**Not verified:** the contents of `static/strategies`; whether `pwb-toolbox`'s gated datasets
include intraday equities; whether `PineForge` reproduces TradingView semantics; the star
counts (rendered as live badges, absent from the raw markdown).

**Superseded and not to be cited:** any description of this README containing a `Rebalancing`
or `Implementation` column, or naming Faber / TSMOM / Paired Switching / FX Carry as rows in
it. That was the previous version of the file. See §1b.
