# Running more than one strategy on the live trader — spec

2026-09-09. Written before any code, per §4 "state the bar before the result".
Ben's choices: **MC5 first, VW9 slots in after; alongside MCL in ONE process;
built properly rather than rushed at tonight's session.**

This is the item PROGRAM_INDEX §7 lists as "generalise the trader", and it is
what currently blocks the months-of-paper plan: `LIVE_STRATEGIES = {"mcl"}`,
and `brokers/ibkr/trader.py` imports MCL directly as `S`.

**What this is not.** It is not a claim that MC5 should be traded. MC5 is
CLOSED as a candidate — −$8.93/trade on the XNAS.BASIC training set, negative
on every drop-top-N. The reason to put it on paper is the same reason MCL is
on paper: **live fills**. Yesterday's session made that the most valuable
thing this project can collect — entry slippage measured at 7–15c/share
against a $4.26/round-trip allowance, on n=2 trades. A second strategy in the
same window roughly doubles the rate that number accumulates.

---

## 1. The coupling is thinner than the docs imply

`trader.py` touches the strategy module in exactly three ways:

| | how | count |
|---|---|---|
| module attributes | `S.SESSION_START/END`, `S.PRICE_MIN/MAX`, `S.TRAIL_PCT`, `S.MAX_SHARES`, `S.MAX_EQUITY_PCT`, `S.size_for`, `S.COMMISSION_PLAN`, `S.ENFORCE_PRICE_BAND`, `S.TICK`, `S.SLIPPAGE_TICKS` | 13 sites |
| the signal call | `evaluate(df)` → `Signals` | 1 site |
| the name | `STRATEGY_NAME` | fill log, Telegram |

MC5 already exposes 9 of the 11 attributes. It is missing `evaluate_last_bar`
and `MIN_BARS_REQUIRED`, and it trades a different bar size. VW9 is missing
more and exits differently — see §6.

## 2. The six hazards, in the order they will bite

**H1 — the partial bar.** MC5 trades 5-minute bars; the trader fetches
1-minute. `common.indicators.resample_bars` labels buckets at the interval
START, so at 08:07 the last bucket is the incomplete 08:05 one. Evaluating it
enters on a signal that has not formed, and it will look like a working entry
because the bucket usually resolves in the same direction. **The last bucket
must be dropped unless the clock has passed its close.** This project has
already paid for this once: `entry_latency`'s first MC5 run compared 5-minute
fills against 1-minute bars and reported fill positions of 7.85× the bar range
with a third of signal bars "not found" — every number wrong, report complete.

**H2 — `Position.trail_level()` reads a module global.** It is
`self.peak * (1 - S.TRAIL_PCT/100)`, and `S` is whichever module was imported.
With two strategies the trail must travel with the position. MCL and MC5 are
both at 5.0 today, so getting this wrong is invisible until one of them
changes — the worst shape of defect this project has, and the same shape as
`USE_APEX_EXIT` governing the backtest and not the live path.

**H3 — one data line per symbol, not per strategy.** `self.states` is keyed by
symbol and carries the contract, the streaming ticker, the bar cache and the
position together. Two strategies watching WYHG must share ONE subscription
and ONE bar fetch: IB paces qualification (~60 requests / 10 min, signalled by
returning empty lists rather than errors) and an account carries ~100 data
lines. Duplicating the subscription halves the watchlist for no data.

**H4 — one position book, one cap.** Ben chose a shared book. The concurrency
gate counts `self.states.values()` today; it must count open positions across
both strategies against the same `MAX_CONCURRENT_POSITIONS = 2`, and the
declined-entry log line must name which strategy holds each one. A cap that
counts only its own strategy is two caps of two, which is four positions on an
account sized for two.

**H5 — different session windows.** MCL and MC5 both run 04:00–09:30, so this
does not bite today. VW9 runs 04:00–20:00. `in_session()` reads `S.SESSION_*`,
and the main loop stops when the clock passes `SESSION_END` — with VW9 loaded
that stop must be the LATEST end across active strategies, and the watchlist
archive must not fire at 09:30 while VW9 is still trading.

**H6 — the warm-up gap, which no backtest can show. MEASURED 2026-09-09, and
it was real.** `backtest_session` computes `signals()` over the whole cached
frame — three days — and only then restricts to the session date, so its
indicators are warm at 04:00. `common/history_probe.py`, run live at 06:22 ET
on four watchlist names, found what the trader was actually getting:

| durationStr | bars | span | MCL | MC5 |
|---|---:|---|---|---|
| `"1 D"` | ~143 | 04:00 → 06:22 — **this session so far** | warm | **COLD** (29 of 40) |
| `"2 D"` | ~1,100 | 26 hours | warm | warm (221 of 40) |

**`"1 D"` provides no warm-up at all: it starts at 04:00, the same minute the
strategy does.** So live has been starting cold every session while every
backtest figure assumed a warm start, and nothing said so. MCL was blind until
about 04:40 — 10.8% of its backtested trades — and MC5 would have been blind
until 07:20, which is 45.9% of its.

Fixed in bundle 2026-09-09m: `HISTORY_DURATION = "2 D"`. The duration belongs
to the FEED, not to a strategy — `SymbolFeed` shares one bar cache per symbol
precisely so two strategies cost one request — so there is one of them and it
must satisfy the hungriest. It costs no extra requests, only response size.

**A consequence recorded and NOT acted on.** MCL now takes its 04:00–04:40
trades, and in the screened backtest those 260 trades carry −$1,290 of MCL's
−$1,270 total: the window accounts for more than the entire loss. That is an
in-sample observation from reading which trades lost, and deriving an arming
window from it is exactly the fitted rule the registration discipline refuses.
It is recorded here as a measured fact and nothing else. Tonight's paper P/L
will likely look worse than previous sessions — that is a truer measurement,
not a worse strategy.

## 3. The shape

Split `SymbolState` in two, along the line the hazards draw:

```
SymbolFeed      one per SYMBOL      contract, ticker, min_tick, blocked,
                                    bars_df + bars_fetched_at  (1-minute, raw)

StrategyState   one per (STRATEGY,  position, last_bar_ts, retired
                SYMBOL)
```

and give each strategy an adapter that the trader talks to instead of `S`:

```
StrategyAdapter
    name                 "MC5"
    bar_minutes          1 for MCL, 5 for MC5
    session              (start, end)
    band                 (min, max) and whether it is enforced
    size_for(price)      -> shares
    evaluate(df1m, now)  -> Signals | None      # resamples, drops the partial
                                                # bucket, returns None if the
                                                # strategy has no CLOSED bar
    trail_pct            carried onto the Position at entry (H2)
```

`evaluate` owning the resample is the point. The trader never learns what a
5-minute bar is; it hands over 1-minute bars and the current time, and the
adapter decides whether a bar has closed. That is also what makes VW9
tractable later — its adapter can return a different exit instruction without
the trader changing.

## 4. Staging, each stage green before the next

1. **`evaluate_last_bar` + `MIN_BARS_REQUIRED` for MC5** — **DONE, bundle
   2026-09-09e.** In `strategy/mc5/mc5.py`, pure strategy code, no live path.
   The partial-bucket rule (H1) landed here rather than in the adapter, because
   the bar size is the strategy's property and putting it here makes it
   testable without a trader. 12 tests; four mutations caught, including the
   trap itself — partial bucket accepted, clock without data, a rule that
   stalls a thin name, and a warm-up far too short.
2. **The adapter** — **DONE, bundle 2026-09-09g.** `common/strategy_adapter.py`,
   every field read off the strategy module. 19 tests, four mutations caught.
3. **Split `SymbolState` (H3), trail onto the Position (H2)** — **DONE,
   bundle 2026-09-09h**, with zero test edits. **But the control was much
   weaker than stated:** seven files, including all of the trader's coverage,
   collected zero tests. Fixed in bundle 2026-09-09i, with a guard so it
   cannot recur.
4. **Two strategies in the loop, one book (H4)** — **DONE, bundle
   2026-09-09j.** `--strategy mcl mc5`, states keyed by (strategy, symbol) over
   one shared feed, one cap across both, a `strategy` column on the fill log.
   Two source-text assertions had to be rewritten as behavioural ones: they
   grepped `trader.py` for `evaluate(df)` and for the band comparison, so they
   would have failed on a correct refactor and passed if the adapter had
   quietly overridden either.
5. **A dry-run session on recorded bars** — **DONE, bundle 2026-09-09k.**
   `common/dry_session.py` replays cached sessions minute by minute through
   the real trader with a stub broker. Over 8 cached sessions: **the cap held
   on every step, and MCL's 32 decisions were IDENTICAL alone and alongside
   MC5** — same symbols, same minutes, same prices.

   Its own first run was wrong and said so loudly: the comparison reported 21
   of 32 MCL rows changed, because rows were keyed on the trader's `ts_et`,
   which is the real wall clock at write time. Correct live, useless in a
   replay. The recorder now stamps the simulated minute.
6. **VW9's adapter**, only after the exit engine is designed (§6).

**What is still open before MC5 trades live: H6.** It needs 40 five-minute
bars and the trader fetches `durationStr="1 D"`, so it would sit out until
about 07:20 of a 04:00–09:30 session. That is a measurement against IB, not a
code change, and it has to be made before an MC5 paper session means anything.

## 5. One thing I would fold in, and will not without a yes

`manage_position`'s fast path passes `ref_close=st.position.entry_price`
(`trader.py:1077`), so on every trailing-stop exit the fill log's
`slippage_vs_ref` is the trade's whole per-share P/L rather than slippage. It
is §2 of `mcl_session_20260908_review.md` and the fix is one line — the right
reference is `pos.trail_level()`, which the code computes for its log message
and discards.

Stage 3 touches that exact code and the trail moves onto the Position, so the
two changes overlap. Doing them together is cheaper and means one round of
testing rather than two. Doing them together also means a defect in either is
harder to attribute, which is why it is a question rather than an assumption.

## 6. What VW9 needs that MC5 does not

Recorded now so stage 2's interface is designed for it rather than around it:

- **A second exit engine.** MC5 and MCL both exit on a trailing stop plus a
  signal. VW9 exits on a fixed 2R target, a structure stop, and `vwap_lost` —
  `manage_position` implements none of those.
- **`signals()` in the trader's shape.** VW9's backtest has a different entry
  API; the adapter has to bridge it.
- **04:00–20:00**, which is H5 and also ~4× the bar requests per symbol.
- **A decision this spec does not make:** VW9 is REJECTED on history
  (−$4.96/trade, fails drop-top-1 badly). It is on the paper list by choice,
  for live data. Worth re-confirming that is still wanted before building an
  exit engine for it.

## 7. What would make me stop and come back

- If stage 3 cannot leave the existing suite green **without edits**, the
  split has changed MCL's behaviour and the design is wrong, not the tests.
- If the MC5 adapter and `backtest_session` disagree on any bar in stage 1,
  nothing after it is worth building until they agree.
- If shared-book concurrency turns out to need the strategies to know about
  each other, the one-process choice is costing more than the two sets of
  fills are worth, and that is Ben's call to revisit rather than mine.
