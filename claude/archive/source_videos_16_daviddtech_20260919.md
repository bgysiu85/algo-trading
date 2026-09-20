# §16 — DaviddTech, *"I Told Claude to Make Me As Much Money as Possible Trading"* (companion to `source_videos_20260907.md`)

`wYuP1QFZ0Bg`, 11:48, published 2026-08-10, 49,650 views.
Channel: *Trading with DaviddTech* (`UC7NJLsf6IonOy8QI8gt5BeA`).

## 16.0 Verdict

**Not adoptable, and nothing in it should be registered.** One technical claim in
it is correct and this project has already established the same thing at far
higher rigour, with a number attached. The tooling it promotes is a **downgrade**
in evidence quality relative to what this project already runs. Its headline
figure is, on its own reported numbers, **roughly 96% position sizing and 4%
edge** — see §16.3.

It is logged here so it is not re-proposed.

## 16.1 What it is

The author gives Claude Code one instruction — *"make as much money as possible
using trading bots"* — plus a `tradingkit.com` MCP server that writes and
backtests Pine Script against TradingView without a TradingView account. Three
iterations, all on crypto (chosen, per the video, because 24/7 bars mean
continuous candle data):

| # | instrument / TF | return | max DD | note |
|---|---|---:|---:|---|
| 1 | ETH 1h | 2,000,000% | 8% | rejected by the author as a backtest artefact |
| 2 | BTC 1h | 58,000% | 66.17% | rejected as untradeable drawdown |
| 3 | **BTC 2h** | **5,622%** | **18.13%** | 199 trades, 77% win, PF 3.3 |
| 3, "entire history" | BTC 2h | 12,355% | 36% | *"much lower profit factor"*, figure not given |

The author's own closing line: **"Would I actually trade this strategy?
Absolutely not."** He forward-tests for three months instead.

## 16.2 The one thing it gets right, which this project already owns

He rejects strategy #1 on the correct grounds: **TradingView has no tick data**,
so a backtest with an intrabar trailing stop is resolving an ordering the data
cannot contain.

> *"you only have the open, close, high, and low data for each and every candle.
> You don't have every single tick."*

**This project established the same thing on 2026-09-18 and put a number on it.**
`orb_sip_RESOLVED_20260918`, from 2,888 symbol-days of one-second bars bought at
$0.00 inside the free window:

- **55.5% of entry-minute stops never happened** — the low printed *before* the
  trigger, so no position existed to stop.
- The ambiguity was worth **0.35R per trade** at a 10%-ATR stop.
- And the standing fact that matters more: **freeing a trade from a same-bar stop
  mostly does not save it** — 81.2% re-reach the same stop within a minute or two.

So the video's central technical observation is an independent confirmation of a
finding this project has already measured, quantified and closed. **That is the
full extent of the convergence, and it adds nothing operational.**

He also rejects tight trailing stops on slippage, fees and alert latency. Same
direction as `friction_reconciliation_20260911`, no new information.

## 16.3 Why the headline number means almost nothing

The reported figures are internally sufficient to back out the shape of the
strategy, and the shape is unremarkable.

```
win rate w = 0.77,  profit factor PF = 3.3,  n = 199

R = PF × (1−w)/w          = 3.3 × 0.23/0.77 = 0.986
breakeven win rate        = 1/(1+R)         = 50.4%
cushion                   = 77.0 − 50.4     = +26.6 points
expectancy                = wR − (1−w)      = 0.529 × (average loss) per trade
```

**Now solve for the position sizing implied by the headline.** 5,622% is 57.22×,
i.e. 0.0203 of log growth per trade over 199 trades. At an expectancy of 0.529
average-losses per trade, that requires:

> **≈3.8% of equity risked on every losing trade** (and ≈4.6% for the 12,355%
> full-history figure).

Hold the edge fixed and vary only the sizing:

| risk per losing trade | return over the same 199 trades |
|---|---:|
| 1% | **+187%** |
| 2% | +721% |
| 3% | +2,253% |
| **≈3.8% (as reported)** | **+5,622%** |

**The edge is +187% at ordinary retail sizing. The other 5,435 points are
leverage.** The 18.13% and 36% drawdowns are the price of that sizing, and the
author's own excuse for the drawdown — *"partially because they are using the
compounding effect"* — cannot be offered while the compounded return is the
headline. Same denominator or neither: PROGRAM_INDEX §4.

## 16.4 What it fails, against this project's own rubric

| standard | this video |
|---|---|
| **registration before run** | none — the search ran first, the criteria were invented as reactions to each result |
| **drop-top-N** | **not run.** 199 trades on one instrument across (probably) multiple crypto cycles. This is the exact shape that took ORB SIP from +4.8R to (52.1)R on dropping one symbol |
| **honest out-of-sample** | **the "entire history" run contains the in-sample period.** The held-out segment's standalone result is never reported. Two denominators presented as one |
| **friction at three levels** | fees included at one level, no sensitivity |
| **both temporal halves** | not shown |
| **boundary check** | the *instrument and the timeframe themselves moved* between iterations — ETH 1h → BTC 1h → BTC 2h. Those are searched parameters, uncounted |
| **search accounting** | *"a huge, huge amount"* of backtests by Claude, against a platform advertising **647,000** community backtests. Multiple comparisons entirely unaddressed |
| **benchmark** | the 5,622% is compared to a 290% sub-period buy-and-hold; the **12,355% full-history figure is given no buy-and-hold comparison at all**, and over BTC's full history that comparison is the one that matters |

**Conflict of interest, stated:** the video sells a Skool community and the
TradingKit MCP server. The 647,000 figure is a marketing number, not a sample.

## 16.5 The tooling question — TradingKit MCP

**Not worth adopting, and the reason is structural rather than a matter of taste.**

TradingKit backtests Pine Script on TradingView. The video itself states the
binding limitation: **TradingView has no tick data.** This project has already
reached the point where minute bars were insufficient — `REGISTERED_orb_sip`
amendment E exists *because* a minute bar's high and low have no order, and the
question was settled only by buying one-second bars.

A tool that generates strategies faster, against data that is strictly coarser
than what this project already uses, would raise the rate of candidate production
while lowering the evidence standard. That is the wrong direction for a program
whose problem is not a shortage of candidates.

The existing stack — Python on `D:\Trading`, Databento bars including `ohlcv-1s`,
registration-before-run — answers questions TradingView cannot.

## 16.6 The one number in it worth keeping

Unprompted, near the end:

> **"I've backtested over 2,000 strategies very much like this, and I'm currently
> trading seven."**

**That is a 0.35% survival rate, volunteered by someone with a commercial
interest in the method looking productive.** It is the most honest figure in the
video and it argues against the method it is meant to advertise.

**It is also the right frame for this project's own record.** Registered and
closed here so far: MCL, MC5, VW9, the Bollinger dip-buy, profit floor, chase
gate, cold veto, luck-vs-edge, SPY intraday (H-S1 and H-S2), ORB SIP, BandWidth
squeeze pre-flight — with TSMOM outstanding. **Zero adopted, out of roughly a
dozen.**

At a 0.35% base rate, zero from twelve is the expected outcome, not evidence of
a broken process. The difference between this project and the video is that here
the rejections are registered in advance and documented with the number that
killed them, so the twelve are not re-proposed — which is the only mechanism by
which a search like this ever terminates in something real.

### Sources

- `wYuP1QFZ0Bg` — *Trading with DaviddTech*, 2026-08-10, transcript read in full
- cross-references: `orb_sip_RESOLVED_20260918.md`,
  `friction_reconciliation_20260911.md` §3, `PROGRAM_INDEX.md` §4
