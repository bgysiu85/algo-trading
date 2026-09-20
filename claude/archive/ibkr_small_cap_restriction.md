# IBKR blocks opening trades in this strategy's universe

Discovered live on 2026-09-02, ~06:34 ET, on JLHL.

## What happened

Three entry signals fired on JLHL. All three were rejected:

```
Error 201: Order rejected - reason:No Trading Permission, Customer Ineligible;
Ineligibility reasons: No Opening Trades: Small Cap, Subject to Compliance Restriction
```

The order was a valid marketable limit (BUY 100 @ 7.78, `outsideRth=True`) on a
paper `DU` account. Nothing was wrong with the order. **IBKR will not let this
account open a position in that security at all.**

## Why this is potentially structural, not incidental

The screen is: **$2–20 price, RVOL ≥ 5x, float < 20m, top pre-market gainer.**

That is close to a description of the population IBKR flags for compliance
restriction — low-float small caps with violent pre-market moves. The strategy
selects for exactly the names the broker refuses.

IBKR does not publish the restricted list, it is account-dependent, and it
changes. So it cannot be predicted — only measured.

## DAS does NOT solve this (correction)

An earlier note in `broker_api_comparison.md` recommended DAS→IBKR as the one
alternative worth pursuing. That recommendation addressed the **trailing stop
latency** question and does not carry over to this one.

In DAS→IBKR, **IBKR remains the broker and clearing firm**; DAS is a front-end
sending orders down a FIX link into the IBKR account. A different order-entry
platform cannot grant a permission the broker withholds. The rejection simply
arrives through DAS instead.

The two problems are different in kind:

| Problem | Kind | DAS→IBKR helps? |
|---|---|---|
| Trailing stop is a 1s poll, not intrabar | platform / front-end | possibly |
| IBKR blocks opening trades in the universe | **broker compliance** | **no** |

## What would actually address it

- **TradeZero as the broker.** Their business is low-float small-cap momentum,
  including short locates on these names; their compliance posture is built
  around this universe. Previously rejected for having no market data — that
  trade-off changes if IBKR simply will not accept the trades.
- **DAS with a first-party broker** (CenterPoint, Cobra, others on the DAS
  Broker Network) — IBKR leaves the chain entirely, and DAS's execution
  advantages come with it.

**Unverified:** that any of these would accept JLHL specifically. Every broker
maintains an unpublished restricted list. This is empirical, not answerable from
documentation.

## Handling built into the trader (2026-09-02)

- **Pre-flight `whatIf` probe at subscribe time.** IB validates permissions and
  compliance restrictions on a non-transmitted order exactly as on a live one,
  so an ineligible name is caught before any signal is wasted.
- **Rejection reason captured from `ib.errorEvent`**, not `trade.log` — the log
  is usually empty and previously yielded only `"Inactive"`.
- **Blocked symbols are commented out of `watchlist.txt` in place**, annotated
  with timestamp and reason, and appended to `watchlist_blocked.txt`.
- **`mcl_scanner.py` reads `watchlist_blocked.txt`** and will not re-add them.

Before this, each fresh signal re-issued an order and was rejected again — three
real entries burned on JLHL alone.

## The measurement that decides the broker question

`watchlist_blocked.txt` now accumulates every refused name. After a few sessions:

- **Occasional blocks** → nuisance; work around it, stay at IBKR.
- **Most candidates blocked** → IBKR cannot host this strategy, and the broker
  choice becomes the primary question rather than a refinement.

This also contaminates results in the meantime: if blocked names are
disproportionately the good setups, realised P/L is being filtered by IBKR's
compliance list rather than by the strategy. Any session review must state how
many candidates were blocked.
