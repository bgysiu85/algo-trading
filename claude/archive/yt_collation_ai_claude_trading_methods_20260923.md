# YouTube info collation — Trading with AI/Claude: methodology + Markov-regime + 9,000-strategy result (2026-09-23)

**From:** Project management chat · **For:** W11-0024 · **Channels:** AI Pathways (2 videos), Lewis Jackson (2 videos)

**Note on source:** TubeAlfred (the full-transcript tool used for the first batch of collations) is no longer
available in this session. All four collations below are built from a third-party transcript-summary site plus
YouTube's oEmbed metadata endpoint — reliable for structure/claims/numbers, **not** verified word-for-word
transcripts.

---

## Video 1 — "Everything I've Learned Trading With Claude In 18 Minutes"
- URL: https://www.youtube.com/watch?v=CPkrCoIbBIA · Channel: **AI Pathways**

### Core framework: deterministic vs. non-deterministic use of Claude
- **Deterministic systems** (fixed rules, fully backtestable) — Claude's strong suit: generating code for
  automated trading bots/signal engines, fast strategy iteration ("hours instead of days"), and running proper
  validation (walk-forward testing, Monte Carlo simulation, sensitivity analysis). Example cited: cointegrated
  pairs systems for commodities with defined entry/exit rules.
- **Non-deterministic uses** (analytical, not repeatable/backtestable) — reading financial documents (earnings
  transcripts, 10-Qs), stress-testing a trader's own thesis, options-chain strike selection, supplementary
  portfolio guidance given the right context.

### Explicit limitations claimed
Claude cannot reliably: predict prices, read chart patterns from images, generate actionable trade ideas without
an existing thesis to react to, or produce a "backtestable" output from a non-deterministic (subjective/analytical)
query.

### Three-layer system example given
1. **Macro deployment gate** — VIX, market breadth, credit spreads, sentiment, factor crowding.
2. **Stock scanner** — quantitative screen across the S&P 500 on five factors.
3. **Analyst layer** — Claude scores fundamentals (earnings quality, growth, margins) via API.

### Practical guidance
Give Claude explicit context (trading style, current positions, time horizon, risk tolerance) and use it as a
**reviewer/challenger of your own thesis**, not as an idea generator from nothing. Cost note: deterministic
systems are essentially a flat subscription cost; non-deterministic/analytical use burns per-query tokens.

---

## Video 2 — "I Re-Built A Quant Trading Strategy With Fable 5" (Lewis Jackson)
## Video 3 — "I Re-Created A Quant Trading Strategy With Claude Code (Insanely Cool)" (Lewis Jackson)

These two videos cover **the same underlying method** (a hedge-fund-style Markov market-regime model), first built
with Fable 5, then rebuilt/re-demonstrated with Claude Code — summarized together since the content is duplicate.

- URLs: https://www.youtube.com/watch?v=Z-hU97WO30I (Fable 5) · https://www.youtube.com/watch?v=ZVMTeDBmSrI
  (Claude Code)

### The 10-part method (as presented)
1. **Market states** — quantify regime numerically instead of subjectively: classify by trailing **20-day return**
   — **Bull ≥ +5%**, **Bear ≤ −5%**, **Sideways** in between.
2. **State labeling** — tag every historical trading day with its state.
3. **Markov property (assumption)** — "where the market goes depends only on today's state," not on longer
   historical price patterns.
4. **Transition matrix** — a 3×3 grid of historical frequencies of moving from one state to another (bull→bear,
   sideways→bull, etc.).
5. **Stickiness / persistence** — bull and bear states are shown to persist more than chance would suggest
   ("the trend is your friend," expressed as a transition-matrix property).
6. **Signal** — `P(bull tomorrow) − P(bear tomorrow)`; e.g. a reading around 70% one-sided is treated as a
   stronger directional signal, sized accordingly.
7. **Multi-day forecasting** — raising the transition matrix to a power (squaring/cubing) projects the
   probabilities further ahead.
8. **Stationary distribution** — beyond roughly **28 days** the projected probabilities converge to a fixed
   long-run distribution, i.e. the model has nothing useful to say about outcomes that far out.
9. **Walk-forward testing** — recompute states/transitions using only data available as-of each day, to avoid
   look-ahead bias.
10. **Hidden Markov Model (HMM) variant** — instead of fixed ±5% thresholds, let the algorithm infer the
    state boundaries/regimes itself from the data, unsupervised.

### Reported results
- The **Fable 5** rebuild is credited with fixing a **stickiness-calculation bug** in an earlier version — the
  original overlapped its 20-day analysis windows, which the presenter says overstated persistence. After the
  fix: S&P 500 came out profitable under this framework, and Bitcoin's backtest dropped from a previously-claimed
  **23x** to a corrected (still large) **~60x** figure — note the direction of the "correction" reads oddly (a
  bug fix producing a *bigger* number) and is exactly the kind of claim that would need independent verification,
  not taken at face value.
- Delivery: a free copy-paste prompt/Claude Code skill that builds the state/transition model, plus a Pine Script
  indicator for TradingView showing current state and directional signal.
- Tools released as free GitHub resources per the presenter (Claude Code skill + Pine Script).

---

## Video 4 — "Claude Tested Over 9,000 Trading Strategies (Here's What Works)" (AI Pathways)
- URL: https://www.youtube.com/watch?v=nLQhKkjkuWI · Presenter: "Brendan," described as a UCLA math/econ grad and
  former investment banker.

### What was done
Used Claude Code to build a systematic backtesting pipeline (four modular prompts, described as reproducible) and
ran **9,000+ strategy backtests** across **30 assets over 15 years** (S&P 500, NASDAQ, sector ETFs, gold, oil,
bonds, Bitcoin, Ethereum, large caps including Apple and Nvidia), spanning strategy categories: trend, mean
reversion, volume, composite, volatility, and pattern-based.

### Validation pipeline (six filters cited)
Walk-forward testing → Sharpe ratio filter (**> 0.5** required) → max drawdown limit (**35%**) → bootstrap testing
(reshuffling trades **500 times** to check result stability) → out-of-sample verification on unseen data → (implied
sixth filter not separately named in the summary — likely a duplicate/overlap in the source's own count).

### Headline result
**9,000+ → 524 strategies survived all filters.** Of those survivors, **64% were mean-reversion strategies** —
stated as the only category that came out net positive **on average** across the full test; trend, volume,
composite, volatility and pattern strategies underperformed in isolation. Separately, only **44%** of strategies
that looked strong in-sample held up out-of-sample — offered as the headline caution against trusting in-sample
performance alone.

### Recommended strategy-construction stack (from the video)
1. Base signal = mean reversion.
2. Add risk management / position sizing.
3. Layer multiple **uncorrelated** signals together.
4. Add market-regime detection — explicitly via **Hidden Markov Models** (same technique as videos 2–3 above).

---

## Why this matters for the board (relevance flags, not yet a verdict)

1. **Mean reversion as "the" surviving category (video 4) lines up directly with Ben's own existing
   mean-reversion strategy work** (`/areas/mean-reversion-strategy.md` — confluence RSI/MFI Pine Script v5). This
   is an independent (if unverified) data point in favor of that line of work rather than a new direction — worth
   weighing as corroboration, not as a reason to start a new build.
2. **The Hidden Markov / market-state regime method (videos 2–4) is a concrete, describable technique not
   currently implemented anywhere on this board.** TSMOM (`docs/research/REGISTERED_tsmom.md`) already deals with
   trend/regime at a different level (rolling lookback momentum), but nothing currently does explicit state
   classification + transition-probability signal generation. This is the most "actionable-sounding" piece across
   all six AI-trading videos collated so far (this batch plus W11-0022/0023) — but it is a YouTube presenter's
   claims about backtested performance (23x→60x Bitcoin, "S&P 500 profitable"), not independently verified, and
   the correction direction noted above (a bug fix that *increased* a headline return) is a specific reason for
   skepticism before any board time is spent on it.
3. **Video 1's "deterministic vs non-deterministic" framing and the three-layer macro-gate/scanner/analyst system**
   are general working-method advice (how to use Claude for this kind of work at all) rather than a specific
   strategy — useful context, not a study candidate on its own.

No verdict is recorded here — this is a straight collation for W11-0024's subitems to work through.
