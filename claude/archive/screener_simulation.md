# Simulating the screener — 2026-09-06

`session_aware_screening.md` §3 recorded the gap plainly: *"Every backtest in
this project runs on `var/state/traded_pairs.json` — 407 pairs assembled in
hindsight — for the whole session. The screener is not simulated at any point."*

This is the work that closed it, and the several ways it went wrong on the way.

---

## 1. The finding that reframed the problem

Ben's full IBKR Flex history was parsed on 2026-09-06 (`common/flex.py`) and
compared against the training universe:

> **401 of the 407 pairs in `traded_pairs.json` are symbol-days Ben actually
> traded.**

So the universe was never a hindsight scanner list. It is his trade history.
Two consequences:

- **`PROGRAM_INDEX` §4's standing caveat is wrong.** "The 407 pairs are names
  chosen *because they ran*" has been discounting every result here for weeks.
  The bias is his real-time discretionary selection, which is materially
  weaker than hindsight.
- **Every parameter was fitted on those days.** Apex-off, `TRAIL_PCT = 5` and
  `REQUIRE_MACD_POSITIVE` were all chosen by sweeping them. Any comparison run
  on the same days scores MCL in-sample — which is why the first
  manual-vs-strategy run (`common/manual_vs_strategy.py`) is worthless: 366 of
  366 compared days were in the tuning set.

---

## 2. Data

`common/databento_universe.py` pulls `ohlcv-1d` for `ALL_SYMBOLS` in
non-overlapping monthly chunks.

| | |
|---|---|
| dataset | EQUS.MINI (2023-03-28 → 2026-09-04) |
| chunks | 43 monthly |
| size | 443.8 MB uncompressed |
| **cost** | **$0.0000** — L0 is included in Standard |
| rows | **7,963,309** symbol-days, **18,113** symbols, **864** sessions |

Daily first is a ~1000× reduction against pulling minute bars for everything:
one 56-byte bar per symbol per day instead of ~250. Minute bars are then bought
only for the few thousand symbol-days that survive.

---

## 3. The look-ahead boundary, which is the whole difficulty

MCL picks its watchlist at **04:00**. A daily bar is not known until **20:00**.
Any rule using today's volume or range to choose this morning's names selects on
information from after the decision — and it would not look wrong. The P/L would
simply be large.

So `common/screen.py` splits the rules and **enforces the split with a test**:

| | uses | role |
|---|---|---|
| **`stage1()`** | `prior_close`, trailing 10-day average dollar volume | **tradeable** — a live scanner at 03:59 has both |
| **`stage2()`** | today's RVOL and range | **fetch filter** — decides which symbol-days are worth buying minute bars for. *Not a trading rule.* |

`test_stage1_uses_no_column_from_todays_bar` greps `stage1`'s own source and
fails if any of today's columns appear in it. Without that, the separation is
decorative.

**Stage 2 still leaks** — it excludes days that were quiet in aggregate, so
survivors are "days that turned out active" and any P/L from them overstates.
See §6.

---

## 4. Three iterations, and what each was

### Run 1 — "864 symbol-days, 0 distinct symbols, 0 candidates, 0% recall"

Not a result. **A file pulled with `symbols="ALL_SYMBOLS"` embeds no symbol
mapping** — nothing was named in the request, so there is nothing to embed —
and `to_df(map_symbols=True)` does not fail on that. It returns `symbol=None`
on every row. Downstream the frame de-duplicated on `(symbol, date)`, collapsed
206,362 rows per month to one per session, and printed a tidy report in which
every figure was structurally zero.

Read quickly it looks like a finding: *the screen selects nothing, so the
thresholds must be too tight.*

Fixed in two halves. `databento_universe` now resolves the mapping via
`request_symbology` and archives it beside each chunk as
`<label>.symbology.json` — part of the archive rather than a runtime lookup,
because instrument ids are reused over time. And `dbn_io` **refuses** rather
than degrades: missing sidecar raises, an all-null symbol column raises,
`daily_frame` raises before any groupby can turn it into zeroes.

### Run 2 — 3.5 candidates/session, 8% recall

Real numbers, wrong thresholds. Diagnosis (`screen.diagnose()`) measured what
each rule rejects rather than guessing, including what the 587 traded names
looked like in the daily bars on the day they were traded:

```
prior_close      p10 $0.77    median $2.60    p90 $8.26
prior_avg_$vol   p10 $1,513   median $53,478  p90 $1.46M
rvol (daily)     p10 0.93x    median 23.92x   p90 991x
range_pct        p10 34%      median 78%      p90 253%
```

| filter | rejected of the 587 |
|---|---:|
| liquidity floor ($200k) | **67%** |
| price band ($2–20 on prior close) | **39%** |
| RVOL ≥ 5× | 32% |
| range ≥ 10% | 1% |

**The RVOL hypothesis was wrong.** I had predicted the transplanted "RVOL ≥ 5"
was measuring a different quantity from TradingView's time-of-day-adjusted
figure. Median daily RVOL on the traded names is **23.9×**. It rejects 32%, and
those are days he traded a name that did not surge — days MCL would not have
traded either.

### Run 3 — 14.0 candidates/session, 30% recall

Two filters were asking the wrong question:

**The price band was the wrong column.** MCL's live scanner screens on
`premarket_close` — the price at 04:00 — so a $1.50 stock that gaps to $4
pre-market passes live and fails a prior-close test. MCL already enforces the
real band **at entry** via `ENFORCE_PRICE_BAND`, on the price at the time,
which is both the right place and not look-ahead. The screen now applies only a
$0.50–$50 sanity range, and the report still prints how many prior closes fell
outside $2–20 so the effect stays visible.

**The liquidity floor was the wrong question.** What matters is not what a name
traded *before* the event but whether an order fills *on* the day — and these
names do ~24× their prior average when they run, so a $53k/day name is doing
~$1.3M. Liquidity is a **sizing** constraint. The floor dropped to $25k and
`Config` gained `max_pct_of_dollar_vol` for the backtest to cap size with.
`PROGRAM_INDEX` already records the volume-floor study failing in exactly this
direction: eight of 21 names produced zero trades, and the excluded names held
~$872 of winners against ~$115 of losers.

---

## 5. ZVZZT

**The second most frequent name in the first real candidate list — 30 of 864
sessions.** It is not a security: Nasdaq publishes it continuously so members
can verify connectivity, and the tape makes no distinction, so it arrives with
real-looking prices and volume and passes a relative-volume screen easily.

Left in, it would have been traded in the backtest, produced P/L, and appeared
in the per-symbol table as an ordinary name. Its prints are arbitrary — so on a
drop-top-N basis a test instrument in the top five would have read as
concentration risk rather than as garbage.

Ten distinct test symbols across 3,622 symbol-days are now excluded by explicit
list plus pattern, and the **count is reported** rather than filtered silently:
a test symbol appearing in a universe is information about the universe.

---

## 6. Current state

```
symbol-days in the daily archive   7,963,309
distinct symbols                   18,113
sessions                           864   2023-03-28 -> 2026-09-04
pass stage 1 (tradeable)           3,510,637  (44.1%)
exchange TEST symbols excluded     3,622  (10 distinct)
candidates                         12,128   -> 14.0/session
                                   median 13   p90 23   max 43
recall against the 587 known       177  (30%)
```

Thresholds, each carrying its provenance in the code:

| | value | basis |
|---|---|---|
| prior-close sanity | $0.50–$50 | **not** MCL's band; that is enforced at entry |
| avg $ volume | ≥ $25,000 over 10d | measured 2026-09-06 |
| RVOL | ≥ 5× | MCL universe rule — measured non-binding |
| day range | ≥ 10% | guess — measured non-binding |
| max per day | 60 | guess — never binds |
| size cap | 1% of the day's $ volume | guess, applied downstream |

### Why tuning stopped at 30% recall

The liquidity floor could be lowered until recall hit 80%. **That would be a
mistake, and the reason is the point of this section: Ben's trades lost
$114,983.**

Recall is a *diagnostic* — does the screen resemble the thing that generated
those picks — not an objective. A screen that perfectly reproduced a losing
trader's selections would be a perfect reproduction of something that did not
work. **100% recall would be a red flag, not a target.**

The remaining rejections are also not really misses:

- **32% rejected by RVOL** are days he traded a name with no volume surge. MCL
  requires the surge to arm; it would not have traded them either.
- **39% rejected by the $25k floor** are names trading under $25k/day before the
  event. That is the one genuine judgment call left, and it is better handled by
  sizing than by tuning against a losing sample.
- Sanity band 4%, range 1%. Nothing.

---

## 7. What is still missing

**Float.** MCL's universe rule is `float < 20m` and **no Databento tier carries
fundamentals**. Using today's float retroactively is look-ahead on the filter
the whole universe definition rests on — a name with 3m float last year may
have 60m now after dilution, and small caps dilute constantly. The screen runs
without it and measures the cost as recall; pretending the filter is present
was not an option.

**The stage-2 leakage control, which has not been run.** Stage 2 uses today's
daily bar, so survivors are "days that turned out active" and any P/L from them
overstates. The control: sample symbol-days the screen **rejected**, pull their
minute bars, and confirm the strategies produce almost no entries there. MCL
needs a volume surge to arm, so the expected answer is that it produces almost
none — but expected is not measured, and this project has been wrong about
exactly that kind of expectation before.

**Until that control runs, every downstream figure is an upper bound.** It is
printed as §4 of every screen report so it cannot quietly be forgotten.

---

## 8. A note on Ben's universe versus MCL's

Worth recording separately from anything the screen does: **39% of his trades
were on names outside MCL's stated $2–20 band the day before, and the median
was a $53k/day microcap.** His actual trading universe sat materially below
MCL's specified one.

That is true regardless of the screen, and it means MCL's backtests — run on
his symbol-days — were never quite measuring the thing he was doing by hand.

---

*Built as `common/screen.py`, `common/databento_universe.py`,
`common/dbn_io.py`. Report: `var/reports/screen_report.txt`. Candidate pairs:
`var/state/screen_pairs.json`. Neither is committed — `var/` holds real
trading data.*
