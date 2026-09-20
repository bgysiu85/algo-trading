# Brokers with a full REST API that are short-friendly — 2026-09-10

> **Companion to `broker_api_comparison.md` (2026-09-02), which still stands for the
> question it answered.** That review asked *which broker executes MCL pre-market*. The new question,
> from the cloud-UI design work (`cloud_ui_design.md`), is: **which broker has a full
> broker-hosted REST API (orders + market data, no local gateway) and is short-selling
> friendly for this universe?** Researched 2026-09-10. Nothing below has been tested by
> us; every "yes" is from the broker's own docs or a dated third-party page.

## For an Australian resident

**Answer: no single broker matches IBKR on both. The closest pair is TradeZero
(orders + locates) with a separate data feed; Alpaca alone is the one-vendor option.**

| | TradeZero | Alpaca | Webull AU | Lime | Schwab | TradeStation | moomoo AU |
|---|---|---|---|---|---|---|---|
| Takes Australians | Yes (Bahamas entity) | Probably — "contact support" | Yes (local entity) | Some countries restricted; AU unconfirmed | Yes | Yes | Yes |
| API | Hosted REST + WS (streams beta), API keys | Hosted REST + WS, API keys | Hosted HTTP + MQTT/gRPC | Hosted REST (OAuth) + FIX | Hosted REST, OAuth, **re-login every 7 days** | Hosted REST, OAuth | **Needs OpenD gateway** |
| Pre-market via API | 04:00–20:00; pre-market order types **undocumented** | 04:00, plus overnight; **limit only** | Earlier review: limit only | FAQ says from **07:00** | From **07:00** | From **06:00** | Not checked |
| Market data | **None** | $99/mo SIP (all exchanges), 7+ yrs incl. extended hours; free tier IEX only | Paid add-on | Quotes, history, T&S | Quotes, history | Bars incl. pre-market | L2 free (promo), symbol quotas |
| HTB locates via API | **Yes** — check, quote, accept, reuse, sell back unused; per-share fee on accept | **Yes, since 24 Jun 2026** — 100-share lots, fee non-refundable, no reuse, expire EOD, margin accounts only | Undocumented | Undocumented | Via trade desk | **Phone the desk** | Not verified |
| Paper via API | Yes (locates rejected in paper) | Yes, excellent | Test environment | Separate terms | **No** | Sim | Yes |
| Cost / minimum | $500 min; adding-liquidity limits free, else $0.49 min | $0 commission; $99/mo data | — | $1k cash / $2k margin; $0.005/sh non-US | None | **$10k for API** | No API fee |

**Ruled out:** Tradier (blocks Australians); tastytrade (no new opening orders from
Australians since 12 Jun 2026); Clear Street (US residents only, app launched 14 May
2026); IBKR Web API (retail still needs the local Client Portal Gateway — OAuth is
institutional only); Cobra / CenterPoint / DAS (strong locate desks, but APIs go through
desktop software, not REST).

### Ranking

1. **TradeZero for execution + locates, plus a separate data feed** (Alpaca $99/mo SIP is
   the obvious one). The only hosted REST API built around small-cap locates; 04:00–20:00;
   no API fee. **Risks:** two vendors; Bahamas entity likely weaker investor protection
   (unverified); API ~3½ months old, streams beta; pre-market order types undocumented —
   test with paper keys at 04:00 ET first. The 2026-09-02 rejection reason (no market
   data) still stands; it is now answered by pairing, not by TradeZero.
2. **Alpaca all-in-one.** Best API and paper, SIP data with pre-market bars, HTB locates
   since June. **Risks:** extended hours limit-only (stops stay software-side — true
   everywhere, see "the finding that outranks the broker choice" in `broker_api_comparison.md`); locates brand
   new and sunk; margin for non-US accounts unconfirmed (shorting needs margin); whether
   Alpaca imposes a small-cap block like IBKR's is unknown; confirm AU eligibility.
3. **Webull AU** — watch item; ask about API locates/HTB before building on it.

### Why it matters to the architecture

- **Alpaca alone removes IB Gateway from the design entirely** — the trader could run
  anywhere. **IBKR data + TradeZero execution still needs the Gateway** (the hybrid in
  `tradezero_hybrid_probe.md`).
- A short-friendly broker fixes only **obstacle 1 of 5** in `short_selling_feasibility.md`.
  Locate fees are sunk at acceptance and at 100 shares are of the order of the whole
  measured edge; SSR still forbids hitting the bid on the sessions a fade would target.

### Regulatory change under this project

**FINRA Notice 26-10** ended the $25,000 pattern-day-trader minimum on 2026-06-04,
replacing it with intraday margin checks; brokers may phase in until 2027-10-20. Alpaca,
TradeZero America and TradeStation already apply it. Shorting still needs a margin
account ($2,000 minimum under Rule 4210 — general understanding, not re-verified).

### Not verified

TradeZero extended-hours order types; Alpaca AU eligibility and non-US margin; Webull AU
pre-market order rules and locates; Lime AU eligibility and 04:00 API trading; moomoo AU
shorting via API; SpeedTrader / Lightspeed; whether any of these applies a small-cap
opening-trade block like IBKR's.

### Sources (2026-09-10)

- [TradeZero API](https://tradezero.com/en-us/api-trading) · [TradeZero docs](https://developer.tradezero.com/docs/documentation) · [TradeZero pre-market short recipe](https://developer.tradezero.com/recipes/pre-market-short-setup) · [TradeZero pricing](https://tradezero.com/en/pricing) · [TradeZero Australia (BrokerChooser, Aug 2025)](https://brokerchooser.com/broker-reviews/tradezero-review/tradezero-australia)
- [Alpaca HTB locates, 24 Jun 2026](https://alpaca.markets/blog/htb-trading-api-locates/) · [Alpaca margin & shorting](https://docs.alpaca.markets/us/docs/margin-and-short-selling) · [Alpaca orders](https://docs.alpaca.markets/us/docs/orders-at-alpaca) · [Alpaca data](https://alpaca.markets/data) · [Alpaca non-US accounts](https://alpaca.markets/learn/live-trading-account-non-us) · [Alpaca countries](https://alpaca.markets/support/countries-alpaca-is-available)
- [FINRA Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)
- [Webull AU API](https://developer.webull.com.au/apis/docs/market-data-api/getting-started/) · [Webull AU short selling](https://www.webull.com.au/short-selling)
- [Lime trading docs](https://docs.lime.co/trader/trading) · [Lime FAQ](https://lime.co/faq/) · [Lime pricing](https://lime.co/pricing/)
- [Schwab Australia](https://international.schwab.com/open-account-step-2AUS) · [TradeStation FAQ](https://www.tradestation.com/faqs/) · [moomoo OpenAPI](https://openapi.moomoo.com/moomoo-api-doc/en/intro/intro.html)
- [Tradier blocked countries](https://support.tradier.com/kb/guide/en/permitted-and-blocked-countries-CLzSa0D1rf/Steps/4997916) · [tastytrade Australia](https://optionstradingiq.com/tastytrade-australia/) · [Clear Street launch](https://www.globenewswire.com/news-release/2026/05/14/3294970/0/en/The-New-Clear-Street-Trading-App-Goes-Live-Placing-Groundbreaking-Technology-into-the-Hands-of-Sophisticated-Individual-Traders.html)
- [IBKR Web API docs](https://ibkrcampus.com/campus/ibkr-api-page/webapi-doc/) · [Cobra FAQ](https://www.cobratrading.com/faq/) · [CenterPoint locate tool](https://centerpointsecurities.com/short-locate-tool-faq/) · [DAS API overview](https://dastrader.com/docs/api-overview/)
