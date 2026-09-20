# TradeZero probe: JLHL accepted where IBKR refused

2026-09-03. Tests the hybrid idea — **IBKR for market data, TradeZero for
execution on names IBKR blocks.** See `claude/ibkr_small_cap_restriction.md` for
the problem this addresses.

## Result

TradeZero **accepted an opening order in JLHL**, the exact name and the exact
operation IBKR refused with error 201.

    POST /v1/api/accounts/TZPB7212/order
    {"symbol":"JLHL","securityType":"Stock","side":"Buy","orderQuantity":1,
     "orderType":"Limit","limitPrice":0.01,"timeInForce":"Day_Plus",
     "openClose":"Open"}

    HTTP 200
    orderStatus     PendingNew
    leavesQuantity  1
    openClose       Open
    route           PAPER
    clientOrderId   0903035843576.427

Cancel returned HTTP 200.

Side by side:

| | IBKR (`DU` paper) | TradeZero (`TZPB7212` paper) |
|---|---|---|
| Opening order in JLHL | **Rejected**, error 201 | **Accepted**, `PendingNew` |
| Reason | No Opening Trades: Small Cap, Compliance Restriction | — |

**The two brokers' restrictions do not overlap.** The hybrid is viable in
principle.

## The caveat that stops this being proof

`route: "PAPER"`.

IBKR's paper account **did** enforce its compliance block — error 201 came from a
`DU` account, so IBKR applies restrictions in paper. Whether TradeZero's paper
router enforces compliance at all is unknown. Their product page claims
"functional parity to live", which is marketing copy, not a test.

If TradeZero paper accepts everything indiscriminately, this probe proves nothing
about live behaviour.

**To settle it:** ask TradeZero support directly whether the paper environment
applies the same opening-trade restrictions as live, and whether JLHL-class
low-float small caps are restricted on live accounts. That is a support email,
not an experiment.

## Probe methodology, and a hole that was closed

The first version cancelled immediately after the HTTP 200. That was not rigorous:
**at IBKR the compliance rejection arrived ~0.5s AFTER initial acceptance**
(`PendingSubmit` → `Inactive`). A late refusal here would have been invisible.

`tz_check.py --probe SYMBOL` now polls
`GET /v1/api/accounts/{id}/order/{clientOrderId}` for ~6 seconds, reports every
status transition, and treats a late `Rejected` / `Expired` as a real block
before cancelling.

The JLHL result above predates that change, so it should be re-run to be fully
sound.

## API details learned (docs summaries were incomplete)

| | Correct |
|---|---|
| Place order | `POST /v1/api/accounts/{accountId}/order` |
| Cancel order | `DELETE /v1/api/accounts/{accountId}/orders/{orderId}` — **plural** |
| Get order | `GET /v1/api/accounts/{accountId}/order/{clientOrderId}` — **singular** |
| Quantity field | `orderQuantity`, not `quantity` |
| Required, undocumented in the summary | `securityType`: `Stock` \| `Option` \| `Mleg` |
| Required | `openClose`: `Open` \| `Close` |
| Pre-market TIF | `Day_Plus` |
| Base URL | `https://webapi.tradezero.com` (live AND paper) |

Four wrong guesses before this worked: wrong route, wrong cancel path, wrong
quantity field, two missing required fields. The lesson is that this API's
validator reports **one field at a time**, so iterating on its errors is fast and
reliable — inferring the schema from prose summaries is not.

Responses may arrive **compressed**; `urllib` does not decode them, so an error
body prints as binary and hides the message. The client now sends
`Accept-Encoding: identity` and decodes gzip/deflate anyway.

## Safety note carried forward

TradeZero serves live and paper from **one base URL**, and the **key pair alone**
selects the environment. There is no equivalent of IBKR's port allowlist, where
4002 physically cannot reach the live account. `tz_check.py` therefore refuses to
place anything until every account reports `accountType == "Paper"`.

Any production hybrid must keep that guard, and must never hold live and paper
keys in the same variables.

## Where this leaves the plan

Order of work still stands:

1. **Entry-condition backtest across the 21 names** — the arming-window change.
   Nothing about execution matters if the edge is not real.
2. **Re-run one clean session with the trailing-stop peak fix**; every hold time
   recorded so far is invalid.
3. **Measure the blocked-name rate** over a few sessions. 3 of 7 signals on
   2026-09-02.
4. **Ask TradeZero support the paper-parity question** — cheap, and it gates
   everything below.
5. Only then build broker routing, per the adapter split in the architecture
   discussion (`DataSource` = IBKR always; `ExecutionVenue` = IBKR or TradeZero
   per symbol, chosen by the existing `whatIf` probe at subscribe time).
