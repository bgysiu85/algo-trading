# YouTube info collation — "The 3R Rule" (small-account futures day-trading framework) (2026-09-23)

**From:** Project management chat · **For:** W01-0010 · **Channel:** The Rumers

**Note on source:** TubeAlfred (the transcript tool) disconnected mid-session and could not be restored. This collation
is built from a third-party transcript-extraction site's summary plus YouTube oEmbed metadata, **not** a verified
full verbatim transcript. Treat it as a reliable overview of the video's structure and claims, not a word-for-word
source — re-pull the full transcript later if exact wording ever matters.

- Title: **"If You Only Have $50, Do This Every Morning (The 3R Rule)"**
- URL: https://www.youtube.com/watch?v=XBOGd67BJks
- Channel: The Rumers
- Presenter: "Doug," described as a 26-year trader

## Summary

Framework for starting day trading with very small capital (as little as $50 risk per trade) and scaling up
methodically. Built around three "R" pillars:

1. **Risk** — keep initial per-trade losses small ($20–$50), sized to the account, not to a target dollar amount.
2. **Reward** — assess realistic profit targets via what the presenter calls a "probability factor," rather than
   picking arbitrary reward multiples.
3. **(Scaling) Raise** — the "Wall Street Raise" method: increase position size by 10% for every 10% of account
   growth, but only after a consistency bar is met (framework specifies at least 3 profitable days out of a 5-day
   trading week before scaling up).

### Core stated philosophy
"If you can't make $50 consistently, you can't make $50,000" — the emphasis is on proving a repeatable process at
small size before scaling capital, not on chasing large single trades.

### Technical/analysis method described
- **Trend bias** via a 50-day moving average.
- **Liquidity zones** — range high/low, swing high/low — used as key levels.
- **Average True Range (ATR)** used for value/volatility assessment (i.e. gauging whether price is cheap/expensive
  relative to its recent range).
- **Stop-loss placement** is explicitly framework-driven ("structurally positioned" — presumably at technical
  invalidation points like beyond a swing high/low or liquidity zone) rather than an arbitrary fixed-dollar stop.

### Instrument recommendation
Recommends **futures** (E-mini S&P, Nasdaq, Dow) for beginners specifically citing a natural long/uptrend bias
("~80% of the time") as a structural tailwind for new traders — i.e. a discretionary reason to favor long setups on
index futures.

## Relevance flag for the analysis/decision step
This is a **discretionary, manual day-trading framework** (position sizing + trend/liquidity/ATR-based technical
setup), not a coded, backtestable strategy — there's no Pine Script, no source repo, and no quantified backtest or
out-of-sample result attached to it, unlike the Kevin Davey / TAI / Tori-trend-line channel reviews already on this
board (W01-0001, W01-0003, W01-0007). The closest existing angle on this board is the general "long bias on index
futures ~80% of the time" claim, which is an empirical, testable claim (could be checked against actual E-mini/ES
or NQ historical up-day frequency) even though the rest of the framework (3R risk/reward/scaling, discretionary
stop placement) is a manual trading discipline rather than something to encode into TSMOM/TL-v0 or the other
quant workstreams.
