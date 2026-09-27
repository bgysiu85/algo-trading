# YouTube Collation — "The Simplest Scalping Strategy I Use Daily" (Oliver Velez Trading)

- **Source:** https://www.youtube.com/watch?v=MM4yzIq5Q-c
- **Channel:** Oliver Velez Trading
- **Published:** 2025-09-12, 23:08
- **Presenter:** Oliver Velez — veteran discretionary trader/educator, says he helped coin the term "swing trading" in the early 1990s
- **Collated:** 2026-09-23

## What this is
A discretionary, chart-reading scalping technique for intraday stocks. **Not systematic** — no code, no backtest, no automation; it's a visual pattern-recognition rule taught by eye on a live chart. Relevant to the project mainly as a source of a testable hypothesis (retracement-depth statistics), not as a ready-made strategy.

## Trading style taxonomy (his framing)
He places scalping within a hierarchy of holding periods: **wealth trading/investing → core trading (months) → swing trading (his own coinage) → day trading → scalping** (scalping = the smallest/shortest subset of day trading).

## Setup / tools
- **2-minute chart** (5-minute as an alternative) — his preference is 2-min.
- **20-period simple moving average (SMA)** and **200-period SMA**, both on closing price, overlaid together ("buddy system" — always use a short + long MA together, never one alone). He explicitly says the flavor of MA (EMA/weighted/etc.) doesn't matter much; he just prefers simple.
- MAs used purely as trend filters ("iron out the wrinkles") — if the 20-period MA is sloping down, treat the trend as down regardless of individual up bars, and vice versa.
- Briefly mentions a separate concept ("space") — when price, the 20 MA and the 200 MA are all separated from each other (a "dual space reversal event"), he treats that as a reversal setup; not the topic of this video, just referenced in passing.

## The core scalp rule (the actual tested claim)
Central claim: after a sharp, one-directional move (down move used as the example), the retracement/bounce depth has an empirically-asserted probability distribution (his numbers, presented as personal experience/observation, not a formal backtest):
- Bounce reaches **100%** (fully retraces the move): ~**1 in 10** tries.
- Bounce reaches **~75%**: ~**2 in 10** tries.
- Bounce reaches **~50%**: ~**6 in 10** tries.
- Bounce reaches **~25%**: ~**9 in 10** tries.

His conclusion: a scalper should target the **25% retracement** level specifically, because it's the level reached most reliably (~90% of the time per his claim), even though it's the smallest, least "exciting" move. Trying to catch a 50%, 75% or 100% retracement is framed as lower-probability and less consistently profitable, despite the bigger potential reward.

## Secondary rule: when NOT to scalp (trade vs. scalp distinction)
- If a bounce after a sharp drop stays **below the 50% retracement level**, he expects the next leg to make a **new low** — i.e., stay with the trend, don't fade it further.
- If a bounce **significantly exceeds the 50% retracement level**, he treats that as a signal the down-move is exhausted and reframes the setup as a **trade** (a longer, larger intraday position) rather than a quick scalp — sizing/holding period differs from the 25%-target scalp.
- Practical entry trigger he uses: wait for "green to eliminate red" (i.e., an up bar/candle that closes above/erases the prior down bar) before entering long against the drop, with a stop placed beyond the recent extreme (e.g., above the last down bar for a long scalp).

## Explicitly not covered / caveats
- No defined stop-loss sizing, position-sizing, or risk-per-trade rules given beyond "stop above/below the triggering bar."
- No named instruments, no session/time-of-day filter, no stated win/loss $ expectancy — all his percentages are stated as personal observation, not sourced from any dataset or backtest shown on screen.
- Applies the same idea symmetrically for both down-move bounces (long scalps) and (implied) up-move pullbacks (short scalps), though only the downside case is fully walked through with charts.

## Possible relevance to Ben's own work
- The one quantifiable, testable claim here is the **retracement-depth distribution** (25% reached ~90% of the time, 50% ~60%, 75% ~20%, 100% ~10%, after a "sharp" one-directional move). That's a concrete, cheap hypothesis to check against Ben's own data (e.g., NDX/TQQQ/SQQQ or futures instruments already in the project) rather than something to take on faith — it reads as a plausible but unverified rule of thumb from a discretionary trader, not a rigorously tested edge like the Kinfo/Mallik video collated separately (`claude/yt_collation_kinfo_mallik_tqqqtrader_20260923.md`).
- Everything else in the video (2-min chart scalping, "buddy system" MAs, discretionary "green eliminates red" entry trigger) is manual/discretionary and doesn't fit the project's fully-systematic approach — flagged for awareness only, not for direct adoption.
