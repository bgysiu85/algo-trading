# The 1-second pull: what it would cost, and why the cost is not the reason to say no

2026-09-18, build chat. **Nothing has been bought and nothing is queued.** This
is the "state the number before you spend it" step, plus the part that turned
out to matter more than the number.

## First, a correction I owe you

This morning I said the 10-second question "needs data this project does not
own" and implied it was unavailable. That was wrong on the facts. Databento
bills `ohlcv-*` at the **L0** tier, which gets 8+ years — the same tier the
minute bars we already hold come from. **One-second bars on XNAS.ITCH are
available over the same window.** It is a purchase, not a wall.

## The estimate, from Databento rather than from me

`databento_fetch` already does this properly: **without `--confirm` it only
estimates**, it prints megabytes and dollars per date, and `--max-cost` aborts
rather than proceeding. That machinery exists because the same request once
priced at **$1,500** with `symbols="ALL_SYMBOLS"` and under a cent scoped
properly, so the number should come from the vendor's own cost API and not from
my arithmetic.

Run from `D:\Trading`. **This spends nothing** — there is no `--confirm` on it:

```
python -m common.databento_fetch --pairs var\state\screen_pairs_pit_itch_v2.json --dataset XNAS.ITCH --schemas ohlcv-1s --lookback 0 --max-cost 0.01 --report var\reports\price_1s.txt
```

```
copy var\reports\price_1s.txt "D:\Trading\Claude outputs\price_1s_20260918.txt"
```

Two things to know when you read the number it prints:

**It prices WHOLE DAYS, not the pre-market window.** `databento_fetch` requests
`start = day` to `day + 1`; the "04:00–09:30" in our archive is how the files are
*named*, not how they were *requested*. A regular session has far more
one-second bars than 04:00–09:30 does, so this estimate is an **upper bound** —
a windowed request is a small change and would cut it substantially, worth making
only if the whole-day figure is what blocks the decision.

**The shape, so the number is not a surprise:** one-second bars over the same
window are up to **60× the rows** of the one-minute bars for the same
symbol-days, before the whole-day multiplier.

And the subscription question is entangled with this. **Item 23 — cancel the
$199/month Databento subscription — is open and currently unblocked.** If
sub-minute data is wanted, that cancellation waits; if it is not, the estimate
above is the last thing standing between us and cancelling.

## Now the part that matters more

**On MCL and MC5, the sub-minute line is bounded above by numbers we already
have, and the bound is below zero.** Two arguments, and the second is decisive.

**A 10-second trigger is at best an execution improvement.** Cameron drops to a
10-second chart once a name has already met his criteria — he is not finding the
trade there, he is placing the entry. Our equivalent is the same trades, entered
at a better price within the signal bar. That is a friction improvement, and
`friction_reconciliation` measured the ceiling on friction improvements on
2026-09-11: **break-even friction is −$0.96 a round trip for MCL and −$4.67 for
MC5.** Negative break-even means the book loses money **at zero cost**. So a
*perfect* execution — zero spread, zero slippage, free commission — still leaves
MCL losing about a dollar a trade and MC5 losing four and a half. **No entry
timing inside the bar reaches that**, because there is nothing there to win.

**And if it is not execution, it is selection, which H-E2 priced this morning.**
If the 10-second chart is used to *confirm* rather than to place — take the trade
only if the sub-minute move holds — then it is a confirmation level, and the
entry sweep gave the exchange rate for those: moving median entry extension by
0.62 percentage points bought 855 trades worth **−$7.00 each**, the best marginal
trade anywhere in the sweep. Every other cell was worse, down to −$9.99.

Those two between them cover both things a 10-second trigger could be.

## So what I would actually do

**Run the estimate anyway** — it is free, it takes a minute, and it turns an open
question into a closed one either way. But I would not buy it *for MCL or MC5*,
because the ceiling on what it could win is already measured and it is negative.

The case for buying it is a different one, and it is worth stating so it is not
lost: **sub-minute data would be new capability rather than a repair.** ORB is
the only strategy here that has ever cleared six of seven criteria, it trades
RTH where liquidity is real, and its point-in-time run is still outstanding. If
one-second bars are ever bought, ORB — or something not yet built — is the
reason, not the pre-market books. That is a decision to make on its own merits
with its own registration, not as a rescue for two books that lose gross.

**And the cheaper thing is already queued.** Tomorrow's chase-gate run prints
where the one-bar exits landed relative to the 5% trail. If they cluster **at**
the trail, the instant deaths were never an entry-timing problem at all — they
were a fixed stop too tight for the volatility at entry — and the fix is a
volatility-scaled trail on the trades we already take. That costs nothing, needs
no new data, and would make the sub-minute question moot for these books.

## What this is not

Not a purchase, and not an authorisation for one — nothing here runs with
`--confirm`. Not a claim that one-second data is worthless; it is a claim that
its value on **these two books** is bounded by a break-even friction that is
already negative. And not a statement about ORB, which has not been measured
against any of this.
