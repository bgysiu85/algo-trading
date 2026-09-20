# REGISTERED — H-S5: a $5 entry floor on a $2–20 watchlist (PRE-RUN)

Asked for by Ben, 2026-09-17, as scenario 1 of five. **Committed before the
code that runs it exists.** Nothing in `strategy/` or `common/` implements a
`price_min` parameter at the time of this commit.

## 1. The rule

The universe does not change. The screen keeps surfacing $2–20 names, every
symbol-day in `screen_pairs_pit_itch_v2.json` is still run, and the watchlist
a live trader would be watching is the same watchlist. Only the **entry** band
moves: `PRICE_MIN` 2.00 → **5.00**, applied at the entry price in exactly the
place `ENFORCE_PRICE_BAND` already acts, so the ceiling, the slippage tick and
the delayed-entry price are all unchanged. `price_min=None` must be
bit-identical to today.

**Signal-ordinal, as H-B1.** Refusing an entry means the position is never
opened, so bars the baseline was in a trade for become live signals and the
floored book can contain entries the baseline never took. That is the form
that would be deployed and it is the form that decides. The **accounting
form** — the baseline book with its sub-$5 trades deleted — is printed beside
it and read for nothing.

## 2. Why this is not the 22-feature null wearing a hat

`entry_features` bucketed 22 features into 88 quartiles on the point-in-time
book and **not one bucket was profitable**; `price` was among them, in a family
of its own. The prior is therefore against a price cut separating outcomes,
and it is written down here rather than discovered afterwards.

What is different is the **mechanism**, which is arithmetic and not predictive.
Friction is a fixed number of dollars per round trip: $4.26 per 100 shares is
4.26¢ a share, which is **2.13% of a $2 stock and 0.85% of a $5 one**. A floor
does not have to find better trades; it has to move the book toward prices
where the same dollar cost is a smaller fraction of the move. No feature-bucket
study tests that, because `entry_features` measured net P/L per bucket — a
number that already has friction inside it and so cannot separate "worse
trades" from "the same trades costing proportionally more".

So the claim under test is narrow, and stated so it can fail: **the floored
book's Δ per remaining trade beats a matched random removal of the same number
of trades, by more than the margin.** If it does not, a $5 floor is abstention
on a losing book and the answer is NOTHING, whatever the total does.

## 3. Cells

| cell | `price_min` | status |
|---|---|---|
| **PF-5.00** | 5.00 | **PRIMARY** — the threshold named |
| PF-4.00 | 4.00 | sensitivity, **reported, never scored** |
| PF-6.00 | 6.00 | sensitivity, **reported, never scored** |
| control | None | must be bit-identical |

The two sensitivity cells exist so the primary can be seen in its
neighbourhood. **A best cell landing on 4.00 or 6.00 is not a result**, and
adopting one after the run would be a search over three thresholds reported as
one. Both strategies, MCL and MC5, are scored cells.

## 4. Readings

The project's gate standard, at $4.26 and then $1.00 and $8.92:

1. Δ per **remaining** trade ≥ $4.26 (the margin) and Δ per symbol-day > 0;
2. both denominators — **a disagreement is a refusal**;
3. both temporal halves, both denominators;
4. drop-top-3 on the level and on the delta;
5. cluster bootstrap by symbol on the delta;
6. the **abstention control** — the same number of trades removed at random,
   2,000 seeded draws, the floor's per-trade delta above the 95th percentile.

All six. Any one failing → NOTHING.

**Reported, and how the result is read rather than scored:** entries refused
and their share of the baseline; the cascade count (entries the floored book
takes that the baseline never had); the price distribution of the baseline's
entries; and **net per trade split by entry price band** ($2–5 against $5–20)
on the baseline book, which is the descriptive form of the same question.

## 5. Registered prediction

- **NOTHING for both strategies.** Δ per remaining trade **+$0.50 to +$2.00**,
  inside random removal's band, failing reading 1 or 6.
- **Reason:** `entry_features` found no profitable price bucket, and three
  B-series gates in a row read exactly random removal. The friction argument
  predicts a real but small per-trade gain — of the order of the difference in
  friction share — and on a book losing $9 a trade that is not the order of
  magnitude that closes the gap.
- **Total P&L is expected to improve**, and that is predicted here precisely so
  it cannot be reported as a success. It is the arithmetic of removing trades
  from a losing book.
- **The interesting failure mode:** the floored book improves by materially
  *more* than the friction arithmetic predicts. That would mean the floor is
  selecting as well as saving, which is a different claim and would need its
  own registration rather than being read out of this one.

## 6. What this does not decide

- Nothing about the live path. `strategy_adapter`'s `price_min` is unchanged by
  this registration; a floor that passes would have to be shipped to the live
  band as its own change, with the parity test that the last three live/backtest
  splits earned.
- Nothing about the screen. The watchlist still carries $2–20 names and the
  live trader still refuses above $20.
- `holdout.json` stays shut.
