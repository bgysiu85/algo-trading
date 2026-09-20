# Scoping the data the tape cannot see — 2026-09-14

**Status:** first probe, two symbols' worth of evidence. No pull run, nothing spent.
**Why:** `entry_split_result_20260914.md` closed the entry question **for minute
OHLCV**. Ben chose to scope other data before working forward from the run
census. This is that scope.

## 0. The organising question is POINT-IN-TIME, not availability

Almost everything here is *available*. Very little of it is available **as of a
historical session**, and for this universe that distinction is not a refinement
— it is the whole exercise.

`tooling_audit_20260911.md` §5 already flagged this as "the highest-value item
in this document after §0", about the universe. It applies with more force to
features: a feature computed from today's fundamentals and attached to a trade
from eighteen months ago is a look-ahead, and it is the same class of defect this
project spent 2026-09-14 removing from the universe.

## 1. The probe, and why it settles the shape of the work

`COMPANY_OVERVIEW` and `BALANCE_SHEET` on **TPET** — one of the nine names the
screen still misses, chosen because it was already under examination.

**Current snapshot (available, one call):**

    Exchange          AMEX
    SharesOutstanding 5,323,900
    SharesFloat       5,044,700
    PercentInsiders   4.845
    PercentInstitutions 3.921

**Quarterly shares outstanding, from the same symbol:**

| fiscal period end | shares outstanding |
|---|---:|
| 2026-07-31 | 5,051,085 |
| 2026-04-30 | 3,118,106 |
| 2026-01-31 | 1,168,515 |
| 2025-10-31 | 1,005,285 |
| 2025-07-31 | 885,912 |
| 2025-04-30 | 247,369 |
| 2024-10-31 | 247,369 |
| 2023-10-31 | 172,481 |

**From 172,481 to 5,051,085 — a 29x change over the backtest window, in one
name.** Today's float attached to a trade from April 2025 would be wrong by a
factor of twenty.

So the answer to "can we use float?" is not yes or no. It is: **a current
snapshot is not approximately right for this universe, it is a different
number**, and any float feature has to be built from the quarterly series or not
at all. That is a much larger piece of work than a single overview call, and it
is worth knowing before anything is built rather than after.

**It also reframes float as a candidate.** A variable that moves 29x inside the
window is not a static descriptor of a company — it is a live, fast-moving state
that plausibly carries exactly the information the tape does not. That is an
argument for pursuing it, on the same evidence that says the easy version is
useless.

## 2. What is available, and in what form

| want | source | point-in-time? | verdict |
|---|---|---|---|
| **listing venue** | `COMPANY_OVERVIEW.Exchange` | current only | **usable now** for the 4-session screen residual, which is contemporaneous. Not safe for 551 sessions — a name that moved venue is mislabelled backwards |
| **shares outstanding** | `BALANCE_SHEET.quarterlyReports` | **quarterly, by fiscal period end** | usable with a filing lag (§3) |
| **float** | `COMPANY_OVERVIEW.SharesFloat` | current only | **not usable historically**. Proxy: outstanding × today's float ratio, and the ratio itself is a snapshot |
| **insider / institutional %** | `COMPANY_OVERVIEW` | current only | not usable historically |
| **short interest** | not in Alpha Vantage's surface as probed | — | FINRA publishes bi-monthly with settlement dates, free and point-in-time by construction. **Untested** |
| **halt state / LULD** | Databento `status` schema | point-in-time by construction | **costs money, untested.** Would need a schema pull priced before anything is requested |
| **news timing** | `NEWS_SENTIMENT` | has timestamps | **untested** whether history reaches back 551 sessions |
| **order-book depth** | Databento MBP-10 / MBO | point-in-time | expensive; capture on XNAS.BASIC is already 55.2%, so depth on one venue is a partial book |

## 3. Two corrections that must be built in, not discovered later

**`fiscalDateEnding` is not an as-of date.** The market does not know the
2026-07-31 share count until the 10-Q is filed, typically 40–45 days later. Using
the period end as the as-of date is a six-week look-ahead on every row. Either
lag it by a registered constant, or take actual filing dates from SEC EDGAR,
which publishes them free.

**Shares outstanding is not float.** TPET is 94.8% float today, but that ratio is
only known currently. Applying today's ratio to a historical share count is a
second snapshot smuggled into a point-in-time series, and it should be stated
wherever the feature is used rather than buried.

## 4. The risk that would quietly invalidate all of it

**Survivorship.** An 18-month universe of $2–20 low-float small caps contains
names that have since delisted. If the fundamentals source covers only live
tickers, every feature built on it is computed on the survivors, and the
delisted names — which are most of the left tail in this universe — silently
carry nulls or drop out.

This project has just spent a day removing a look-ahead from the universe. Adding
a survivorship bias to the features in the next step would be the same mistake in
a new place, and it points the same way: it makes results look better than
reality.

**This is the first thing to test**, before any bulk pull: take ten symbols known
to have delisted during the window and ask whether the source returns anything
for them. Ten calls, no commitment.

## 5. What it would cost, and the question that decides it

The universe is 6,170 symbol-days; unique symbols are far fewer, but unknown —
counting them is a one-line read of `screen_pairs_pit.json` and should come
first.

At two calls per symbol (overview + balance sheet), a few thousand symbols is a
few thousand calls. **Alpha Vantage's free tier is 25 requests a day, which makes
this impossible; the premium tiers are 75–1,200 a minute, which makes it an hour.**
Which tier is in use decides whether this is an afternoon or a non-starter, and
it is not something to discover halfway through a pull.

## 6. Next, in order

1. **Count the unique symbols** in `var/state/screen_pairs_pit.json`. One line;
   sizes everything below.
2. **Test ten delisted names.** If they come back empty, the fundamentals route
   carries survivorship bias and needs a different source before anything is
   built on it.
3. **Confirm the Alpha Vantage tier**, because it decides feasibility outright.
4. **Take venue for the nine missed names now** — nine calls, current data,
   contemporaneous with the sessions in question. Settles the AMEX residual that
   `screen_miss` could not, and it is the one item here with no point-in-time
   problem at all.
5. Only then: price the Databento `status` schema for halts, and check how far
   `NEWS_SENTIMENT` history reaches.

Items 1, 2 and 4 cost about twenty API calls between them and answer whether
there is a programme here at all.
