# TV vs broker — reconciling the price gap, 2026-09-09

Ben: *"the BNC buy at 6:21am by IBKR was filled at $5.41 whereas in TV it was
filled at $5.10. That's a 31c difference which is significant."*

It is. 31c on a $5.22 decision is 5.9%, and MCL's entire trailing stop is 5%.
A position can be through its own stop before the fill is confirmed — a
plausible mechanism for `consolidation_filter_test.md` §4, where two thirds of
trades stop out inside five minutes and lose $1,935.

## 1. The fill log already decomposes it

From `var/fills/mcl_fills_20260909.csv`:

```
06:23:01  BNC BUY  ref_close 5.22  bid 5.40 / ask 5.42  limit 5.44
          filled 5.41 × 100, 1.3s   slippage_vs_ref −0.19
```

| component | | value |
|---|---|---:|
| `bar_gap` | TV's reference (5.10) vs ours (5.22) — a **different bar** | **+0.12** |
| `drift` | our close (5.22) vs the ask when the order went out (5.42) | **+0.20** |
| `execution` | our fill (5.41) vs that ask (5.42) — *inside* the quote | **−0.01** |
| **cost** | | **+0.31** |

**Execution is not the problem.** We filled a cent inside the ask in 1.3
seconds, and the night's other three entries slipped +1c, +2c and +1c. The cost
is upstream: we decided on a bar TV had already passed, and then the market
moved 20c before the order reached the book.

That distinction matters because the three parts have three different fixes,
and only one of them is an order-type question. Guessing which dominates is how
a project spends a week tuning execution when the problem was bar alignment.

## 2. What was built

**`common/tv_reconcile.py`** — joins TV alerts to the fill log and splits every
trade the way the table above does. The identity is arithmetic, not a model:
`cost = bar_gap + drift + execution`, signed so positive is money lost on both
sides of the market (paying more on a buy, receiving less on a sell) — without
that flip, buys and sells cancel and the total understates the cost.

It names the largest component and says what it means, because a bare table of
three numbers invites acting on whichever looks biggest without knowing which
are even fixable.

**`pine/MCL.pine`** — the alerts already existed but said *what* was decided and
never *when*, so the only timestamp available was TradingView's delivery time.
Reading a delivery time as a bar time is exactly how a two-minute gap becomes
unexplainable. The payload is now structured JSON carrying **both** bar stamps:

```json
{"v":1,"strategy":"MCL","symbol":"BNC","action":"BUY","reason":"entry_signal",
 "bar_time_ms":...,"bar_close_ms":...,"ref_close":5.10,"qty":100,"tf":"1"}
```

Both, because "the 06:21 signal" is ambiguous between the bar *labelled* 06:21
and the moment 06:22:00 when it closed and the rule could first fire. The
trader cannot act before the close, so that is what its fill is measured
against; the label is what the chart shows.

The trailing stop fires **intrabar** and so cannot use `alert()`, which is
once-per-bar-close by design. It carries `alert_message` instead — without it
the record would show every entry and almost no exit, since 456 of 479
backtested exits are that stop.

## 3. Why not read the Strategy Tester

Because after the session it is a **backtest of the day**, recomputed from
current bar history — not a recording of what fired live. Differences between it
and our fills would be partly artefacts of the recomputation, with no way to
tell which. A fired alert is stamped when it fired. Only an alert can answer a
question about timing.

## 4. Why TV Remix cannot do this

Measured, not assumed:

- **No strategy tester.** Its tools are quotes, bars, screeners, technicals,
  watchlists, portfolios. Nothing returns a Pine strategy's trade list.
- **1-minute bars are regular hours only.** 400 AAPL 1-minute bars come back as
  10 from 2026-09-04's close plus *exactly* 390 from 09-08 — 390 being precisely
  09:30–15:59. The newest bar for any symbol is the previous RTH close.

Our session is 04:00–09:30. TV Remix cannot see a single bar of it. It remains
useful for RTH context and screening; it is not an instrument for this.

## 5. Open

- **Where the alerts land.** TradingView webhooks need a public HTTPS URL,
  which this setup does not have. Putting a Telegram bot token in a TV webhook
  URL would work but stores a live token on TradingView's servers. The likely
  answer is TradingView's own **alert log** — alerts fire live and TV records
  each fire, so reading that log after the session gives real fire timestamps
  with no server at all. Needs verifying against the CDP tooling.
- **The Pine is not compiler-validated.** No TradingView with CDP was reachable
  in this session. Compile it before trusting it.
- **`common/bar_freshness.py`** still needs a run inside a session. If the
  history trim is discarding a closed bar, part of the 0.12 `bar_gap` is that,
  and it is fixable.
