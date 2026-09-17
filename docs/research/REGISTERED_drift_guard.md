# REGISTERED — a placement guard on quote drift, threshold fixed before the code exists

From `claude/session_review_20260917.md` item C, and the recommendation in
`claude/session_review_20260914_15.md` §3. **Committed before
`brokers/ibkr/trader.py` carries the guard.** This is a live-path parity rule,
not a hypothesis about the market: nothing here is scored on P/L.

## 1. The claim, exactly

The engine buys the signal bar at its **close plus one tick**
(`SLIPPAGE_TICKS`), and every published figure carries a friction of $1.00 to
$8.92 a round trip — under 1% of price at $5. A live BUY placed into a quote
that has moved several percent from the signal close is a trade the backtest
**does not contain**: not a worse fill of the modelled trade, a different trade.
CRBP on 09-14 was bought 6.6% below its reference into a collapse; RETO on
09-17 was bought 34.5% above its reference four minutes after the bar closed.
Both were recorded with a slippage column that read the fill as good.

The guard: **a BUY entry is not sent when the ask is more than `DRIFT_GUARD_PCT`
away from the signal close, in either direction.** The signal is recorded as
declined with the drift and the threshold, the bar is marked evaluated, and
the next signal bar is judged on its own quote. The restriction is on what live
may buy; it never widens anything, and it never touches an exit — a position
must be able to leave at any price.

## 2. The threshold, and why it is this one

**`DRIFT_GUARD_PCT` = 6.0**, absolute, measured on the **ask** (the price a
marketable BUY pays) against `sig.close`:

    drift_pct = (ask / signal_close - 1) * 100
    refuse iff abs(drift_pct) > 6.0

It is the number written in the 09-14/15 review — "do not send a buy into a
quote 6%+ below the reference" — **before the 09-17 trades existed**. The
09-17 review's count was taken at 3%, after seeing which trades lost; using it
would be fitting the threshold to the result it was found on. On the 138 live
round trips measured in that review, drift was p10 (5.39%), p90 +2.13%,
median (0.24%), so 6% is expected to bind on **roughly one entry in ten**,
almost all of them on the downside. `ref_drift` (the fill-log column) uses the
mid; the guard uses the ask because that is the side a BUY crosses, and the
two are stated separately so the column keeps its meaning.

## 3. What it is not

- **Not an entry filter.** Drift did not separate outcomes over 138 trades
  (Q1..Q4 non-monotone, the only positive bucket interior). No claim is made
  that refused entries would have lost; the analysis chat reports what they
  did, descriptively, and nothing here is amended on that.
- **Not a retry.** A refused signal is not re-priced a second later; the bar is
  consumed exactly as a stale bar or a capped signal is.
- **Not a search.** One threshold, fixed here. Changing it is a new
  registration.
- **Not the re-entry rule.** Item B (`bar_after_exit`) refuses a signal bar
  that opened before the strategy's own exit; this guard is independent of it
  and reads the quote on bars B allows.

## 4. What decides that it is working

- Every BUY in `var/fills` after promotion has `abs(ask / ref_close - 1) <= 6%`
  at placement, and every refused signal appears as `SKIPPED_DRIFT` with the
  drift in `reject_reason`.
- The share of entry signals refused sits near one in ten over the first ten
  sessions. Materially more means the live quote is routinely far from the
  signal close and the latency, not the threshold, is the question.
- Tests: the guard refuses at both signs past 6.0, admits at and below it,
  never runs on a SELL, records the row once per bar, and admits a missing
  quote to `marketable_limit` (which records NO_QUOTE) rather than refusing it
  as drift.
