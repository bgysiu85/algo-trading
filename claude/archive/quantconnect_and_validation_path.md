# QuantConnect, Alpaca, and the validation path

Researched 2026-09-02. Companion to `claude/broker_api_comparison.md`, which covers
IBKR / TradeZero / Schwab / Webull / DAS as **execution** venues. This doc covers the two
that are a different kind of question.

## Alpaca — rejected

Same pre-market wall as everyone else, plus a data problem specific to this universe.

- **Extended hours: limit orders only.** Alpaca docs: *"Only limit orders with
  `time_in_force` set to `day` or `gtc` orders are accepted as extended hours eligible."*
- **Trailing stops explicitly excluded:** *"Trailing stop will not trigger outside of the
  regular market hours."*
- Pre-market window 04:00–09:30 ET, which does match.
- Paper trading API is genuinely good and free.

**The disqualifier is data.** The free feed is **IEX only** — one exchange, ~2% of US
volume. For a thin pre-market small cap the 3× volume rule and the 60-bar volume average
would be computed against a fraction of real volume, so the core signal becomes noise. The
consolidated SIP feed requires the paid Algo Trader Plus subscription (price not published
on the FAQ page read — verify before assuming). Either way it is paying for data IBKR
already provides.

## QuantConnect — not an execution answer, but the best answer to a bigger question

QuantConnect is a backtest-and-deploy platform, not a broker. It deploys live **through
IBKR**, so the broker stays. It therefore cannot fix the pre-market order-type wall —
nothing can.

**What it could fix is selection bias**, which is the largest unresolved threat to this
strategy and is bigger than slippage. Every backtest figure so far (V7: +$924 / 50 trades)
comes from **21 tickers chosen because they ran**. Slippage shaves an edge; selection bias
raises the possibility there was never one.

QC has point-in-time data including delisted securities, plus a universe-selection
framework. That is the machinery for the real question: *across every name that met the
screen on every day — not just the winners — does this work?*

### Four real obstacles

1. **Universe selection is daily, not intraday.** The screen is "top-2 *pre-market*
   gainer" — a live cross-sectional ranking during the session. QC's fundamental universe
   runs on daily data. Workaround: pre-filter nightly on price / prior volume / float,
   then subscribe that reduced set with `extended_market_hours=True` and rank live in
   pre-market. Feasible, but this is the actual work of the project, and node cost scales
   with universe size.
2. **Float data gap.** The screen needs float < 20m. QC fundamentals give *shares
   outstanding*; true free float is not straightforwardly available. For small caps with
   heavy insider ownership those differ materially, so a central screen criterion would be
   approximated.
3. **It is a rewrite.** LEAN's `Initialize` / `OnData` / subscription model is a different
   paradigm from `mcl_paper_trader.py`, and Python on LEAN is slower than C#.
4. **The backtest fill model is still a model.** QC simulates pre-market limit fills from
   assumptions, not measurements. It does **not** replace the IBKR fill-log exercise.

### Cost

~$60/month researcher tier; ~$120/month once live; more for large universes.

## The sequencing that follows

1. **Finish the IBKR fill measurement.** Free, broker-agnostic, already built and running.
   Produces measured slippage vs bar close, and a no-fill rate.
2. **Rebuild the backtest on QuantConnect** with point-in-time universe selection,
   substituting the *measured* slippage and no-fill rate for the 1-tick assumption. This is
   the first genuinely honest estimate of the edge.
3. **Only then** revisit execution venue — at which point DAS→IBKR is the one alternative
   with a real case (see `broker_api_comparison.md`).

Steps 1 and 2 are complementary and both are prerequisites: step 1 measures friction, step
2 removes selection bias. Neither is an execution upgrade, and that is the point — the
strategy's problem right now is not execution, it is that nobody knows whether the edge
exists.

## Sources

- [Alpaca — placing orders / extended hours](https://docs.alpaca.markets/us/docs/orders-at-alpaca)
- [Alpaca — extended hours support](https://alpaca.markets/support/extended-hours-trading)
- [Alpaca — market data FAQ (IEX vs SIP)](https://docs.alpaca.markets/us/docs/market-data-faq)
- [QuantConnect — requesting US equity data / extended market hours](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data)
- [QuantConnect — fundamental universes](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/universe-selection/fundamental-universes)
- [QuantConnect pricing](https://www.quantconnect.com/pricing/)
- [QuantConnect review 2026 (tier costs, limitations)](https://www.quantt.co.uk/resources/quantconnect-review)
