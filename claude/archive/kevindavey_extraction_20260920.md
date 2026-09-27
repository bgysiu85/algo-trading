# AT-106 · Kevin Davey channel — structured extraction (for viability-judgment session)

**Chat:** Futures Trading Viability Analysis chat (this chat) — Sonnet, medium effort
**Date:** 2026-09-20
**Channel:** "Algo Trading With Kevin Davey" — youtube.com/@AlgoTradingWithKevinDavey
**Channel stats:** 26,400 subscribers, 733 videos, 1,132,094 total views, joined Dec 2012.

Same workflow as AT-104 (Tori Trades), applied to a second, very different channel: this one is explicitly systematic/coded and futures-native (unlike Tori Trades' discretionary chart-pattern trading).

---

## 1. Who he is / claimed credentials

- Self-describes as "verified algo trading champion" / "verified trading champion" Kevin Davey in nearly every video's opening line.
- Claims: 3-time real-money trading contest winner, 3 consecutive years of >100% annual returns (finishes: 2nd, 1st, 2nd), 30 years of trading experience, ex-NASA intern (used as a "this isn't rocket science" rhetorical point, not a trading credential).
- Author of 6 trading books (most recently *11 AI-Inspired Algo Trading Strategies*, ~July/Aug 2025, released ~Sept 2025).
- Runs "KJ Trading Systems," the "Strategy Factory" strategy-development methodology, and the "Strategy Factory Workshop" (claims: "won best trading school" 3 years running per *Technical Analysis of Stocks & Commodities* magazine reader poll).
- Co-hosting a paid "Trading MasterClass" live Zoom event (Sept 24-26, 2026) with Perry Kaufman (well-known author of *Trading Systems and Methods*, a real, independently-recognized systematic-trading figure — legitimate co-branding, not a fabricated credential).
- Sells/gives away a "MultiWalk" walk-forward/multi-market backtesting add-on for TradeStation (built by "a student of mine"); bundled free for "Platinum" workshop students.

## 2. Videos reviewed (16 of ~17 targeted; 1 excluded — see note)

1. **"How I Won A Real Money Algo Trading Contest — Secrets Revealed"** — narrates 3x contest wins, mindset/discipline framing (steps 7-8 of an 8-step series), no strategy specifics. Started $15K, drew down to ~$7.5K (50%) mid-contest, recovered to finish >100%. No verifiable statements/records shown — verbal claim + a described equity-curve shape only.
2. **"Does the Golden Cross Actually Work? I Tested 220 Markets"** — 44 markets x 5 bar sizes, Monte-Carlo risk-adjusted return metric, walk-forward (2007-2026). Verdict: poor / "absolutely pass" — only ~12 of 220 combos even marginally tradeable, best case (lean hogs) barely worth it. Full code shown (TradeStation + Python) — NOT paywalled.
3. **"Crude Oil AI Inspired Algo Trading Strategy — $96K in Walkforward Profits"** — a strategy from his paid book. Entry rules and code shown on screen (ADX threshold + 2-bar momentum + 200-bar momentum filter); exits (monthly cease-trading + $5,000 catastrophic stop) described but full code "in the book." 61% win rate, largest loss $6,800, walk-forward equity curve shown, "since book release" (~Sept 2025) window highlighted separately from full history.
4. **"$187K Profit Out-of-Sample From This ES Strategy"** — a bonus strategy given only to book-buyers/email-signups. Two of the entry conditions shown (VWAP/ATR + momentum), full code explicitly withheld ("wouldn't be fair to book buyers"). $20K drawdown shown around COVID-2020; acknowledges the strategy loses money on the short side and argues against cherry-picking out the losing side after the fact (a genuine anti-curve-fitting point).
5. **"+48% in 2026 YTD — You Could Be Trading This Micro Futures Portfolio Too!"** — his own real, currently-traded 12-strategy micro-futures portfolio (started ~2020, $25-35K account). Shows real NinjaTrader account statements: $24,837 (Jan 2026) → $36,750 (July 2026), and separately claims 48-54% return since Feb 2026. Full backtest since 2021: 37-38% CAGR, one $19K weekly drawdown. Explicitly shows real-money under/overperforming the hypothetical backtest in different months (an honest, non-cherry-picked touch), and explicitly says he is NOT scaling up contract size to avoid "juicing" an equity curve.
6. **"Canadian Dollar Algo Trading Strategy — $46K In Walkforward Net Profit"** — a losing-lately example from the same book; most of the last ~9 months have been losing months. Presented deliberately as "not everything works all the time" — an honest-negative example, anchored to a fully coded, walk-forward-tested system rather than a discretionary call.
7. **"What I am Algo Trading This Month — From a Verified Trading Champion"** — restates the 12-strategy micro portfolio; $25,980 hypothetical profit since Jan 2025 across 12 systems; explicitly flags 2 of 12 (soybeans, GBP) as currently losing.
8. **"Is A Reverse Keltner Strategy Any Good? I Decided To Test It..."** — 44 markets x 7 bar sizes x 6 walk-forward configs, 1,848 equity curves. Verdict: "nothing really worth trading in the current state." Full code shown, no stop/target (always-in-market signal only).
9. **"I Backtested A Keltner Channel Strategy — Here Is What I Found!"** (standard version) — same 44x7x6 test matrix; 33% of cases profitable, only 12% "significant" profit; verdict middle-of-the-pack, "not something you could trade" alone. Full code shown.
10. **"Why Most AI Trading Strategies FAIL!"** — 7 named failure modes: overfitting, false-pattern discovery, curse of dimensionality (a model needing exponentially more data as its number of input variables grows), "AI doesn't know the future ≠ the past," black-box problem, data-quality blindness (continuous-contract adjustment method, missing/bad data), "fantasy returns" (unrealistically smooth AI-generated equity curves). Concludes: use AI as a "research assistant," never as a strategy-building replacement.
11. **"Common AI Trading Myths — Watch Out!"** — 5 myths debunked: AI can predict markets (no), more data = better models (no — data quality > quantity), model complexity = better performance (no — simpler/robust models tend to survive better), AI removes the need to understand fundamentals/walk-forward testing (no), black-box strategies are fine to just trade (no — psychologically very hard to hold through a drawdown you don't understand).
12. **"Shocking AI Trading Case Study — Watch Out!"** — a narrated ("Juan," explicitly illustrative/pseudonymous) case study: trader gets ChatGPT to generate a crude-oil strategy end-to-end, backtest shows 28% CAGR/18% drawdown, he "improves" the backtest (unknowingly curve-fitting to noise), skips proper walk-forward/Monte Carlo testing, paper-trades only 3 days, goes live — wins 2 months, then gives back all gains in a never-before-seen drawdown. Framed as a cautionary tale about skipping his "Strategy Factory" process.
13. **"Where AI Actually Works In Trading"** — his positive-use list for AI: idea generation (research-paper mining), feature/portfolio-rule brainstorming, data cleaning/error-checking, parameter exploration (flagged "with caution" — can shade into curve-fitting), pattern discovery (flagged "with caution" — can be false patterns), execution/slippage analysis.
14. **"How Pro Traders Use AI For Their Algo Trading"** — pro-vs-amateur framing: amateurs let AI dictate risk control, position sizing, and end-to-end strategy building ("a recipe for disaster"); pros use AI only to enhance an already-existing, self-understood systematic process.
15. **"When Should You Quit An Algo Trading Strategy?"** (MasterClass promo) — promotes a "Quit Point Evaluator" tool given to MasterClass attendees; mostly promotional, but the underlying concept (psychological fit between mechanical stop-trading rules and a trader's own risk tolerance) is a genuine point.
16. **"Don't Make This Mistake When Algo Trading!"** — warns against (a) picking apart every performance metric until you find a reason to reject any strategy, and (b) blindly following "expert" metric advice (cites Bob Pardo's book advising against raw net-profit as a walk-forward optimization metric, then notes Davey has won contests using exactly that metric). Core message: validate metrics against your own live-tracked outcomes.

**EXCLUDED:** "Strategies Included In The Trading MasterClass — Perry Kaufman & Kevin Davey" (video id FiqereOTcYY, 44 min) — transcript exceeded this session's single-call size limit and was not re-fetched given time constraints; a MasterClass-strategies preview/promo video, lower priority than the videos above for the viability judgment.

## 3. Monetization / funnel structure

Every video (without exception among the 16 reviewed) opens or closes with a call to sign up (free, email-gated) for a "free algo strategy." That funnel feeds into:

Free algo (email capture) → 6 paid books (most recent bundles "bonus" strategies for buyers/emailers only) → paid multi-day "Trading MasterClass" live Zoom event (with Perry Kaufman) → "Strategy Factory Workshop" (his flagship paid course, explicitly "not cheap," "intermediate/advanced traders only," multi-year "best trading school" award claims) → "MultiWalk" software (bundled free only for Workshop "Platinum" students).

This is a well-built, multi-tier education/content business layered on top of the free YouTube content — consistent with (not necessarily contradicting) genuine trading skill, but it means the free videos are, by design, a sales funnel, not a full disclosure of his actual traded rule sets.

## 4. Red flags for the judgment session

1. **Unverified / self-reported live results** — the only real-money evidence shown is his own NinjaTrader/TradeStation account-statement screenshots (Jan-July 2026) and verbal claims of 3x contest wins; no independent/third-party-audited track record is shown for any of it.
2. **Free-vs-paywalled asymmetry** — the fully-disclosed, fully-tested-to-destruction strategies (Golden Cross, Keltner, Reverse Keltner) are consistently the ones he says NOT to trade; the strategies he actually trades or sells have code partially or fully withheld. The free content demonstrates his testing rigor, not his edge.
3. **Short "since book release" windows layered on longer backtests** — several strategies (CL, ES, 12-strategy portfolio "since Feb 2026") lean on 6-9 month "look how well it's done since I published it" framing, too short to distinguish skill from luck.
4. **Survivorship among his own developed-but-discarded ideas is not addressed** — no account of how many strategy candidates from his own "Strategy Factory" process get discarded before one reaches his traded 12-strategy portfolio.
5. **AI-skepticism content doubles as a sales argument** for his paid Workshop/MasterClass — every AI-skeptic video (7 of 16 reviewed) ends by redirecting to his paid course. The underlying technical critique is standard, correct systematic-trading practice — but the consistent pairing with a pitch is a content-marketing pattern worth flagging, not a reason to distrust the technical claims themselves.
6. **No equities-to-futures or portfolio-sizing guidance for a new trader's own capital** — no content on how someone (like Ben) would decide how much capital to allocate to a first systematic futures strategy, or how to validate a strategy built from scratch rather than bought from Davey.

## 5. How this differs from the Tori Trades (AT-104) review

Tori Trades: discretionary, chart-pattern-based, minimal disclosed methodology — AT-104's red flags centered on unverifiable P&L claims and discretionary-to-systematic translation risk.

Kevin Davey: explicitly systematic/coded, futures-native, methodologically sophisticated (44-market x multi-bar-size x walk-forward-config testing, Monte Carlo risk-adjusted return, proper in/out-of-sample discipline) — genuinely higher technical credibility than Tori Trades. The viability question for this channel is less "can this even be systematized" (it already is) and more "how much of the demonstrated methodology transfers to a strategy Ben could build or verify himself, versus how much of the actual edge is paywalled inside the books/Workshop."

## 6. Suggested next step

Per the AT-104 pattern, Ben should open a new Opus / high-effort session and hand it this extraction doc to do the systematic-translation + futures-viability judgment (comparable to AT-104 subitem 3) — including whether Davey's disclosed methodology (walk-forward testing, Monte Carlo risk-adjusted sizing, multi-market/bar-size robustness screening) is directly reusable in Ben's own TSMOM/Swing/ORB work regardless of any view on Davey's own track record.
