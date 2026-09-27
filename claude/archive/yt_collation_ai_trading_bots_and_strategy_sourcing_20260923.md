# YouTube info collation — AI trading bots & strategy-sourcing methodology (2026-09-23)

**From:** Project management chat · **For:** W11-0022 (Opus analysis session) · **Channel:** Miles Deutscher Finance

Two videos requested by Ben for collation. Full transcripts pulled via TubeAlfred; both summarized in full below (nothing
truncated — video 1 is 17:25, video 2 is 12:36).

---

## Video 1 — "I Tested 50 AI Trading Bots With Claude. One DOMINATED."
- URL: https://www.youtube.com/watch?v=2NwO-4KD8KA
- Published 2026-09-15 · 34.2K views · 555 likes · 46 comments
- Credits David Tech (YouTube: @DaviddTech) for the sourcing methodology

### The four free strategy-sourcing sources
1. **TradingView community scripts** — browse an asset's Indicators → Marketplace → Top Editors' Picks / Trending, open "Source code" on any Pine Script indicator, copy it out. Many are visual-only; only ones with explicit buy/sell signals, stop-losses and entries are worth testing.
2. **Stonehill Forex** (home of the **NNFX method** — "No Nonsense Forex") — Resources → Indicator Library has a large free indicator set. NNFX is a structured multi-indicator confluence framework.
3. **QuantConnect** — free account exposes a leaderboard of community strategies with code included (one example cited: 127% out-of-sample return). "Out of sample" = tested on a period held back from the strategy's own development window, to mimic live performance.
4. **Quantpedia** — an academic quant-research database: plain-language trading rules + performance/risk stats distilled from published papers, with some strategies downloadable as code for free (best ones are paywalled/pro).

### Method demonstrated (all done by handing links/pasted code to Claude — presenter used **Fable** in Claude Code, calling it "the smartest model")
- Pasted 3 TradingView Pine Script indicators into Claude and asked it to rewrite them into back-testable strategies with risk/trading parameters, staying "as true to the original indicator as possible."
- Gave Claude the Stonehill indicator-library URL and asked it to browse the site, break down each method, and write a back-testable spec as a `.md` file per strategy.
- Gave Claude the QuantConnect leaderboard URL and had it download all strategies' code directly into an `.md` file (verified for accuracy against source).
- Same treatment for Quantpedia (scraped, verified for accuracy).
- Asked Claude to also pick **5 of its own strategies** from its own knowledge/inference (no back-test bias, genuinely out-of-sample selection) to round the set out to **50 total strategies**.
- Built a single back-test engine and ran **325+ backtest runs across the 50 strategies**, with a results dashboard. Claude was asked to flag (yellow border) the strategies it judged most *sustainable* — not just highest-return.
- **Cost/usage note (explicitly flagged by presenter):** running this at 50-strategy scale burned through a lot of Claude usage credits ("spending a lot of money doing this... probably wouldn't run things at this scale, I'd curate a bit more if you're on a budget"). He recommends testing a handful at a time rather than mass-testing.

### Results (aggregated across sources, various assets/timeframes)
- Top single result: **+3,447%** (BTC, H4, Binance) — but flagged by Claude itself as unreliable due to a **64% max drawdown** and low win rate.
- Other notable raw returns: +2,400%, +2,300%, +1,700%, +621% (SPY/stock market), +2,333% (ETH/USDT).
- Many strategies in the full 50 **lost money** — a good-looking indicator/strategy in theory does not imply real profitability; presenter stresses understanding *why* a strategy makes money, not just that the backtest says so.
- Claude's own top-sustainability picks (favoring profit factor, win rate, low drawdown, steady equity curve) were two **BTC daily** strategies (profit factors 1.78 and 1.54).
- When asked for its top 5 "worth testing further" with rationale:
  1. The +3,447%-type outlier (huge drawdown, not recommended for real use, kept for reference).
  2. A strategy that ~10x'd ($10K→$114K / $100K→$1.1M) but only started beating BTC buy-and-hold in recent years.
  3–5. Three strategies that **didn't beat BTC on raw returns but beat it on risk-adjusted returns**, with one only opening 2–4 trades over 6 years (theoretically fine, presenter judged it "not reliable enough to extrapolate" due to low trade count), and a Stonehill-sourced strategy the presenter ultimately favored for forward-testing: **steady equity curve outperforming BTC, strong profit factor, still actively trading through Jul–Sep**.

### Workflow after finding a candidate (presenter's stated process — matches Ben's existing pipeline)
Backtest (in-sample) → verify with TradingView chart replay → **paper/forward test** on live/forward data (this is the step that actually validates a backtest, since backtests only prove the past) → small live-money test → scale up. Architecture: an LLM (Claude) as the "brain," connected via an MCP server to an exchange (e.g. Bybit) for execution, either orchestrated directly by the LLM or via an execution "bridge" layer for reliability.
Presenter's philosophy note: align bot bias (long/short/neutral) with your own discretionary market view rather than running a bot blind to regime — a purely long-biased bot in a bear-biased portfolio is a risk many overlook.

---

## Video 2 — "3 free Github repos to print $$$ AI trading"
- URL: https://www.youtube.com/watch?v=Z3CUdMYXZm8
- Published 2026-09-21 · 10.1K views · 154 likes · 49 comments

Reviews three free, open-source GitHub trading-bot frameworks, set up via Claude Code, for **crypto-first exchanges** (not IBKR):

### 1. Freqtrade — ~54.6K GitHub stars
- Free/open-source Python crypto trading bot; supports all major exchanges; controllable via web UI or **Telegram** (`/performance`, `/start`, `/stop` commands; can run multiple bot instances per Telegram chat).
- **Built-in backtesting** (on historical exchange data) and a **"dry run"** mode (forward-test on live-fed data without real money) — both native to the bot, not something you build yourself.
- Demoed: gave Claude a BTC/ETH breakout strategy idea, iterated it, then had Claude follow Freqtrade's setup docs end-to-end to stand up the web UI dashboard and load the strategy into a dry run.
- Runs as its own persistent Python process — needs a machine (or VPS, e.g. Hostinger) on 24/7; **not dependent on Claude at runtime**, only for initial setup/strategy iteration.
- Live trading = plug in real exchange API keys (e.g. Bybit) once a dry run has proven the strategy.

### 2. Vibe Trading — ~33.7K stars, 170 contributors, active (commits within hours)
- Positioned as a **personal trading research/strategy-generation agent**, not primarily an execution engine ("turn market questions into runnable research").
- Features: ask a trading question, backtest a strategy idea, review your own trades, read institutional filings/fund letters, run "analyst teams," generate strategies.
- Ships an **"alpha library"**: 450+ pre-built quant "alpha" signals across 4 categories, benchmarkable against the S&P 500 (demoed picking "Alpha 101032" — passed out-of-sample but small edge vs. buy-and-hold).
- Execution is via connecting to **Alpaca** (or a few other supported exchanges) for paper/live trading — demoed: asked it to find the best momentum strategy across NVDA/META/AAPL/MSFT/AMZN over 2 years, backtest with realistic fees, show the equity curve, and paper-trade it on a $100K Alpaca account, then report the orders placed. (Presenter's own caveat: this demo strategy is not one he'd consider well-engineered — used purely to show the workflow.)

### 3. NoFX — presenter's favorite of the three
- "AI trading terminal assistant" for **stocks, commodities, forex and crypto**; positioned as the strategy-engine + execution middle-layer between an LLM and an exchange.
- Has an **"Autopilot"** mode: fund a wallet, run strategies server-side (no local terminal session needed) — works across **Hyperliquid** and centralized exchanges.
- Terminal UI shows: cost/liquidation map, order book, a "signal matrix" for automations, orchestration topology (useful for HFT-style decision-to-execution visibility), equity and total P&L in one view.
- Can also connect to any other centralized exchange account for strategies built outside Autopilot.
- Ships pre-built, deployable strategies directly from its home page as a quicker alternative to building your own.
- Comes with risk parameters, exchange connections, and the trading loop (read market → decide → execute → record reasoning) already built — the appeal is the "plumbing" being done, not that it's impossible to DIY.

### Presenter's overall take
All three serve different needs and aren't mutually exclusive: Freqtrade = ready execution engine + your own strategy; Vibe Trading = strategy research/generation layer; NoFX = terminal + middle-layer, most feature-complete for multi-asset. Recommends installing/trying all three to learn by doing, using paper money first, before committing real capital.

---

## Why this was collated for an Opus session (not fully analyzed here)
This is a straight collation of both transcripts — no fitness-for-Ben's-stack judgment applied yet. The obvious tension for the analysis to resolve: both frameworks in video 2 (Freqtrade, Vibe Trading, NoFX) are built around **crypto-native exchanges** (Binance, Bybit, Hyperliquid) and Alpaca for US equities — none integrate IBKR natively, which is Ben's actual brokerage/data source (see `/topics/trading-setup.md`). The strategy-*sourcing* methodology in video 1 (TradingView community scripts, Stonehill/NNFX, QuantConnect leaderboard, Quantpedia), by contrast, is asset/broker-agnostic and could plausibly feed Ben's existing strategy-research workstreams (W05 small-cap, W06 TSMOM, W07 swing) directly. See W11-0022 subitems for the specific questions the Opus session should answer.
