# YouTube Collation — "This Trader Made +$700K in 6 MONTHS — While Working a Full-Time Job" (Kinfo, feat. Mallik / TQQQTrader)

- **Source:** https://www.youtube.com/watch?v=pBS5vrqrUjk
- **Channel:** KINFO — Undiscovered Traders podcast, host Stephen Johnson
- **Published:** 2025-09-11, 52:36
- **Guest:** Mallik ("TQQQTrader" on Kinfo, "RealTQQQTrader" on X) — 20-year software engineer (Microsoft, Salesforce), fully systematic/automated trader
- **Collated:** 2026-09-23

## Who he is / track record
- Trading since ~2016; fully automated (no manual trades) for the last **3 years**.
- Started with ~$20K, scaled a live account to ~$1M; Kinfo shows $700K+ verified profit in the last 6 months (older gains show as "step" jumps because Kinfo only books closed positions, and he holds core positions for months/years).
- ~40%/yr annualized return over the ~3 years live, with drawdowns up to ~30–33%.
- Sells signals via Collective2 (~$50K of subscriber capital following his signals in real time via email/SMS).
- Runs **7 strategies** total (mix of trend-following + mean-reversion, long and short) — trend-following is the bulk of the P&L. Low frequency: ~1–2 trades/week.
- Trades **only two tickers**: TQQQ (3x long Nasdaq-100) and SQQQ (3x short Nasdaq-100). No individual stocks, no discretionary trades, no news/ML/AI inputs — price data only.

## His self-described "journey" framework (useful mental model)
1. **Exploratory phase** (~2016–2019): tried day trading (lost 30% of $20K in a year), then discretionary swing trading. Learned market structure but no consistent edge; "boom and bust" cycle of making money then giving it back.
2. **Discovery phase**: retrospection — realized he was "playing somebody else's game." Landed on three requirements for making money: **Edge, Conviction, Process**.
   - *Edge* = something you're demonstrably better at than others (his: data analysis, strategy building, coding — leveraged into systematic trading rather than discretionary).
   - *Conviction* = sticking with the edge through drawdowns because backtesting shows the expected behavior; without conviction you abandon a strategy right before it pays off.
   - *Process* = infrastructure to consistently build/test/deploy (his tool, "WhiteLight").
   - Explicitly discounts "psychology" as a separate pillar — for him it's downstream of having a tested, trusted edge.
3. **Growth phase**: consistent profitability from 2022 on (flat in 2024, big year in 2025 because the regime suited trend-following).

## Strategy substance
- Core edge = **momentum (trend-following) and mean-reversion**, framed as durable market anomalies rooted in human fear/greed, not curve-fit patterns.
- **Trend model**: simple 50-day and 250-day (~1yr) moving averages on NDX (Nasdaq-100 index). Rule of thumb he repeats: *no major NASDAQ rally has ever sustained without price being above both the 50-day and 250-day MA* — he treats "price above the 250MA" as effectively binary permission to hold a large long trend position, and holds through the whole trend (some positions open for years) rather than trying to time tops/bottoms.
- **Mean-reversion model**: rate-of-change / deceleration of the trend (his analogy: car accelerating 40→50→60 mph vs decelerating 40→30→20) triggers trimming/adding to the core position.
- Position management is **not binary in/out** — he holds a core position and scales a portion of shares up/down day to day (e.g., "30% of portfolio in TQQQ today, add more tomorrow"), fully closing only when the trend/regime actually breaks (can take months to years).
- Backtested on **42 years of NDX data** (since 1985): reports ~80%/yr strategy CAGR vs. ~12%/yr buy-and-hold QQQ; also profitable through 1987/2000/2008/2020 crashes because the short (SQQQ) side kicks in — e.g. positive in the 2000 dot-com crash (+200%, +152% following year), +83%/+155% around 2008–09, +469% in 2020.
- Big historical drawdown: ~50%, lasting ~1.5 years (early 1990s); ~30% drawdown 2014–2016 (sideways/flat market — a known weakness of the trend model). In his live 3 years: two ~30% drawdowns.
- Explicitly says the strategy struggles when NASDAQ trades flat/sideways for extended periods — a known, accepted weakness rather than something he tries to fix.
- Only inputs: daily OHLC(V) price data for TQQQ, SQQQ, NDX. No fundamentals, no news, no ML/AI.

## Execution / infrastructure ("WhiteLight" platform)
- Self-built tool (code name "WhiteLight"), does both backtesting and live execution.
- Runs on an **AWS cloud VM**, scheduled to auto-boot ~15–20 min before market close and shut down after — the whole live decision process takes **~10 minutes/day**, right before the close.
- Data source: **polygon.io** (with local caching as a fallback if polygon is down).
- Brokerages: **Fidelity** and **Alpaca** (multiple accounts).
- Daily flow: pull latest data → run all 7 strategies → output is just two numbers (target % of portfolio in TQQQ, target % in SQQQ) → diff against current holdings per account → place the orders needed to hit the target weights before the close.
- Built-in fault tolerance: falls back to cached data if polygon.io is down; retries broker order rejections (seen during volatile/bear conditions) for several minutes near the close.
- Sends telemetry/alerts to his phone (positions, orders placed, errors) — designed so he never has to babysit it; describes very few operational issues in the last ~2 years.

## His advice for someone starting out
1. Spend real time trading manually first (small size, e.g. $5–10K) to build a felt sense of market tendencies — don't skip straight to systematizing someone else's idea, because you won't have conviction to hold it through a drawdown.
2. Once you have your own market-based ideas, learn to code (any language) and model/backtest them rigorously.
3. Expect a low hit rate on strategy ideas: he backtested "300–350" strategies and only **7** survived and are in production. Most popular retail concepts (buy-the-dip, breakouts, support/resistance, chart patterns) tested against 40 years of data don't beat buy-and-hold.
4. Favor simple, mechanical rules over complexity; complexity for its own sake ("if the moon aligns with Jupiter") is a red flag, not a sign of sophistication.
5. Decide up front how much drawdown you can tolerate, then use backtested history (not hope) to hold through it — he's fully compounding, no profit-taking, because backtesting tells him what a 40–50% drawdown looks like and that it has historically been followed by strong recovery.

## Possible relevance to Ben's own work
- Conceptually adjacent to the project's [[h60-strategy]] (60-min trend/momentum work) and general TSMOM/momentum research already in the project — same "trend + mean-reversion on simple MAs, tested over decades" philosophy, just applied to leveraged NASDAQ ETFs instead of Ben's instruments.
- The "target portfolio weight → diff against current holdings → place just the delta" execution pattern (rather than discrete entry/exit signals) may be a useful reference model if/when Ben's own automation moves from signal-based to weight-based position management.
