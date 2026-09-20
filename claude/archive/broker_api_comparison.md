# Broker API comparison for MCL pre-market execution

Researched 2026-09-02, mid-session, after the IBKR paper layer was already built.
Alternatives evaluated: **TradeZero, Charles Schwab, Webull, DAS Trader (routing to IBKR)**.

**Answer: IBKR stays.** DAS is the only alternative worth a follow-up, and it is blocked
on two unanswered questions. Reasons below, plus the finding that outranks the whole
question.

## What the strategy actually needs

1. **1-minute bars including pre-market** — MACD, MFI, RSI and a 60-bar volume average.
2. **Live bid/ask** — to price marketable limits and to run the trailing stop.
3. **Pre-market order placement** on US small caps, 04:00–09:30 ET.
4. **A paper account reachable from the API** — the edge is unproven and the backtest is
   contaminated by selection bias, so live capital is premature.

## The comparison

| | IBKR | TradeZero | Schwab | Webull | DAS → IBKR |
|---|---|---|---|---|---|
| Pre-market order mechanism | Marketable limit, `outsideRth=True` | Limit + `Day_Plus` TIF | Limit + `SEAMLESS` | **Limit only** | Limit |
| Market order pre-market | Rejected | Rejected (`R78`) | Not viable | Not allowed | Not viable |
| Native pre-market trailing stop | No | No — `TrailStop` unsubmittable | Not offered | **Not allowed** | **Possibly** ⭑ |
| **Paper trading via API** | **Yes (`DU`)** | Yes | **No — live only** | Sandbox, unverified | Yes (IB paper) |
| **Market data included** | **Yes** | **No** | Yes, incl. **L2** | Yes | Yes, incl. **L2** |
| 1-min history depth | Deep | None | ~30–48 days | Yes (OHLCV) | Yes |
| API style | Socket (`ib_async`) | REST + WS (beta) | REST + OAuth + WS | REST + MQTT/gRPC | TCP CMD API :9910 |
| Auth burden | Gateway session | API keys | **Re-auth ~7 days** | App key/secret | Platform must run |
| Recurring cost | Data subs only | None | None | None | **$100–250/mo** |
| Maturity | Decades | Launched 22 May 2026 | Post-TDA migration | Established | Established |

⭑ Unconfirmed — see the DAS section.

## Why each alternative was rejected

**TradeZero — no market data at all.** Their own product page: *"It does not provide
quotes, charts, or historical prices."* The WebSocket streams P&L and order status, not
prices. This strategy is mostly market data, so adopting TradeZero means bolting on a
third-party feed: extra cost, extra integration, and quotes sourced from somewhere other
than the venue filling the order. The API is also only ~3 months old, WebSocket in beta.

*Genuine upside, for later:* low-float pre-market momentum is exactly TradeZero's niche,
and routing quality on this universe is a real question documentation can't settle.

**Schwab — no paper trading via API.** The sandbox is synthetic data, not a paper
account. Adopting Schwab now means going straight to live capital to find out whether the
strategy works. Also no trailing-stop order type, and a ~7-day refresh-token cycle meaning
manual re-authentication roughly weekly for something meant to run unattended each morning.

*Genuine upside, for later:* Level 1 **and Level 2** streaming on NYSE/NASDAQ. If the fill
log shows no-fills are the binding problem, seeing depth before crossing would help.

**Webull — limit orders only in pre-market.** Their trading-hours page: *"Only limit
orders can be placed during the pre-market and extended hours sessions."* No market
orders, no stop orders, **no trailing stops**. Strictly worse than IBKR, which at least
accepts stop-limit outside RTH. The OpenAPI itself is capable (OHLCV bars, tick/snapshot
quotes, MQTT + gRPC streaming, trailing stops and OTO/OCO brackets *in regular hours*), so
it would be a fair candidate for a regular-hours strategy — but the pre-market restriction
guts it here. Sandbox exists but was not verified to be a true paper account with
realistic fills; eligibility requirements undocumented.

**DAS Trader → IBKR — the only real contender, blocked on two questions.**

Supported configuration: DAS connects to IBKR PRO accounts over an aggregate FIX link, no
IBKR software or account reconfiguration needed, **paper and live IB accounts both
supported**, market data supplied by DAS, pre-market from 04:00 ET. DAS's own broker table
states IBKR supports all their advanced order types **including trailing stops and trigger
orders**.

The CMD API is a TCP socket on `localhost:9910` against a running DAS Trader Pro instance:

- Orders: Market, Limit, Stop, Stop Limit, **Trailing Stop**, Peg
- Data: Level 1, **Level 2**, Time & Sales, historical daily *and minute* bars
- Streaming: order status, fills, positions, P&L

*Why it matters:* a broker-side trailing stop is structurally closer to Pine's intrabar
fill than our 1-second poll. That is the single real discrepancy between the Pine and the
Python. L2 would also answer the no-fill question directly.

**The two unanswered questions** (DAS documentation is silent on both; ask support):

> 1. When DAS Trader Pro is linked to an Interactive Brokers account, are Stop Trailing
>    orders held on DAS servers, or in the local DAS Trader Pro application? If the
>    application closes or loses connection with an open position, does the trailing stop
>    remain active?
> 2. During pre-market (04:00–09:30 ET) on a US equity via IBKR, when a Stop Trailing
>    order triggers, does it send a market order or a limit order? If market, is there a
>    trailing-stop-limit variant that works in extended hours?

If stops are client-side, DAS buys latency but not resilience — same failure mode as our
Python trail. If the trigger sends a market order, IBKR rejects it pre-market and we are
back at the same wall.

*Other caveats:* ~$100/mo platform (**not** waived by volume at IBKR) plus data, so
$150–250/mo realistically — against a V7 backtest edge of **+$924 over 50 trades** across
six favourable sessions, before realistic slippage. DAS's own table also notes all IB
orders route "through a gateway" rather than direct market access, blunting DAS's main
selling point.

## The finding that outranks the broker choice

**No broker will accept a market order pre-market, and none offers a usable native
trailing stop there** — with DAS the sole possible exception, unconfirmed. That is market
structure, not an IBKR limitation.

So the software-side trailing stop in `mcl_paper_trader.py` is not a workaround for a poor
broker choice — it is the only way this strategy can be executed almost anywhere.
Switching brokers cannot fix it. Its known weakness (a 1-second poll that crosses the
spread, versus Pine's intrabar fill *at* the stop price) is inherent to live trading and is
precisely what the fill log is being built to measure.

## Decision

Stay on IBKR. It is the only broker evaluated that offers paper trading **and** market
data on a single connection with no recurring platform fee.

Revisit only if the measured fill data justifies it:

- If **slippage** is the problem → compare routing: DAS→IBKR, or TradeZero.
- If **no-fills** are the problem → L2 becomes valuable: DAS or Schwab.
- If the trailing stop's latency is the problem → DAS, subject to the two questions above.
- If the edge does not survive realistic friction at all → the broker question is moot.

The slippage and no-fill measurement is **broker-agnostic and free**. Finish it before
considering any migration or recurring platform cost.

## Sources

- [TradeZero Equity Trading API docs](https://developer.tradezero.com/docs/documentation/trading)
- [TradeZero API Trading product page](https://tradezero.com/en-us/api-trading)
- [TradeZero change log](https://developer.tradezero.com/docs/changelog)
- [TradeZero API launch release, 22 May 2026](https://www.prnewswire.com/news-releases/tradezero-launches-developer-api-for-programmatic-equity-options-and-short-locate-execution-302779235.html)
- [schwab-py client docs (price history, quotes)](https://schwab-py.readthedocs.io/en/latest/client.html)
- [Schwab API workflow-fit checklist (paper trading, tokens, limits)](https://mylinedchart.com/resources/articles/schwab-api-for-technical-traders-workflow-fit-checklist)
- [QuantConnect Schwab brokerage docs (order types, paper trading)](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab)
- [Webull OpenAPI docs](https://developer.webull.com/apis/docs/)
- [Webull stock trading API](https://developer.webull.com/apis/docs/trade-api/stock/)
- [Webull trading hours & extended-hours order types](https://www.webull.com/help/faq/10960-What-are-the-trading-hours-for-stock-and-ETF-orders)
- [DAS supported functions by broker (DAS / IBKR / Schwab)](https://dastrader.com/docs/supported-functions-by-das-ib-and-td-ameritrade/)
- [IBKR's DAS Trader integration docs](https://www.interactivebrokers.com/docs/third-party-integrations/specific-third-party-connection-details/das-trader/introduction)
- [DAS stop order types](https://dastrader.com/docs/limit-order-market-order-and-stop-orders/)
- [das-bridge CMD API library](https://github.com/misantroop/das-bridge)
- [DAS Trader Pro cost breakdown](https://rizetrade.com/brokers/das-trader-pro-cost)
