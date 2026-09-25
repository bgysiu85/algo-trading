# strategy/swing

Swing trading: 2-20 trading day holds in liquid US large/mid caps.

**Status as of 2026-09-19: G2 measured and provisionally cleared at 5.46 bps.
Still no strategy here, by design.** `docs/swing_preflight_20260914.md` fixed go/no-go criteria G1-G8
before any entry logic exists, the same way `strategy/orb/` did. This folder
holds the tooling that answers G2 and nothing else.

---

## What the pre-flight established

| | |
|---|---|
| **Cost is no longer the blocker** | At N >= 5 a realistic round trip is 4-16% of the median absolute move, against roughly 75% in the intraday small-cap programme |
| **Financing replaces it** | IBKR AU retail USD is ~7.13% (5.13% quoted + a 2% non-AUD surcharge), so 2:1 leverage costs ~0.99 bps per day held. Past ~4 days the loan costs more than the whole round trip |
| **The binding constraint is statistical** | Same-date returns correlate at rho ~0.27, which caps effective sample size at (non-overlapping periods)/rho. On 10.3 years an outright directional strategy worth under ~20%/yr is undetectable, and a bigger universe does not help. Market-relative drops the floor to ~3%/yr |

G1 was decided on 2026-09-14: **long-only, evaluated market-relative** — hold
long, but score the strategy on its return minus the market's.

---

## The G2 tooling

G2 says a candidate is not accepted until the round-trip cost is MEASURED for
the candidate universe. Three routes were considered and two are closed:

- **Public data.** The SEC stopped publishing spread and depth after December
  2013. Its current market-structure files carry the right decile breakdown
  (market cap x price x volatility, through June 2026) and no spread column.
  Any 2026 "SEC DERA" large-cap spread figure is 13-year-old data.
- **The tooling already in `common/`.** `friction_quotes.py` prices Ben's own
  Flex fills and takes a trade report as input, so it can only measure a
  universe he has already traded. `quote_fill.py` is the same shape one level
  over — it runs off the traded-pairs file. Neither can be pointed at a
  universe with no fills in it.
- **The Databento archive** is scoped to the small-cap screened universe.
  Large-cap `tcbbo` is not on disk, and retrieval is what Databento bills for.

So the spread is measured directly, live, at the venue actually traded.

### `spread_sampler.py` — the collector

Records bid, ask and quoted size for the candidate universe on a fixed cadence
and writes one CSV row per observation. It does not analyse: a bug in the
analysis should never cost a session of data.

```
python -m strategy.swing.spread_sampler --self-test
python -m strategy.swing.spread_sampler --wait-for-open --minutes 390
```

Defaults to `var/reports/spread_samples.csv`, append mode, flushed per row, so
a disconnect mid-session loses nothing and a re-run continues the same file.

`--wait-for-open` sleeps until the next 09:30 ET open and only then starts the
clock, so `--minutes 390` means open-to-close rather than 390 minutes from
whenever the command was typed. Weekends are skipped; holidays are not
modelled, and on one the collector will sit through a shut market — a wasted
night rather than a wrong number, and the report will show a session with no
usable rows.

**IB Gateway must stay up and logged into paper for the whole run.** It is the
data source, not a handshake at startup. Its daily auto-restart will otherwise
land mid-session: *Configure → Settings → Lock and Exit*, choose auto-restart
(which re-authenticates without credentials) over auto-logoff, and set a time
outside 23:30–06:00 AEST.

Carries the standing guards: ports 7497 and 4002 accepted, 7496 and 4001
refused **by name**, and `managedAccounts()` must return DU accounts before
anything is requested. There is no order code in the file, and a test asserts
that (`placeOrder`, `MarketOrder` and friends must not appear in the source).

### `spread_report.py` — the analysis

```
python -m strategy.swing.spread_report var/reports/spread_samples.csv \
    --out var/reports/spread_report.txt
```

Prints pooled and per-symbol spread percentiles in cents and bps, displayed
depth at the touch against a target position size, an ET half-hour breakdown,
and an all-in round trip combining the measured spread with the scheduled IBKR
tiered fees. States the G2 verdict against the 40 bps threshold.

Financing is deliberately **not** folded in — G3 requires it charged
separately, per day held.

---

## Conventions these two do not follow, and why

**No repo imports.** Neither module imports from `common/`. The collector runs
while a session may be live, possibly out of the production tree, and a
collector that will not start because something unrelated is mid-edit is a
collector that loses a session. Same reason neither uses `common.report_io`:
they emit no colour at all, so the ANSI-must-never-reach-a-txt rule holds by
construction rather than by remembering to.

The cost is that `tests/conftest.py`'s artefact guard does not cover them — it
monkeypatches `report_io.emit`, and these write with `Path.write_text`. The
tests compensate by running `main()` in an empty cwd and asserting nothing is
written outside `--out`.

---

## Which hours count, and why it is a default rather than a flag

`spread_report.py` defaults to `--session rth` (09:30-16:00 ET). That default
was bought with a wasted session.

The first real run was started at 11:02 AEST and left for roughly thirteen
hours. **Under 5% of its 46,805 rows landed inside US regular hours** -- the
rest were the overnight and pre-market book, which is several times wider:

| | median quoted spread |
|---|---:|
| everything collected | **34.27 bps** |
| regular hours only | **8.00 bps** |

The pooled figure **passed the 40 bps G2 gate** while measuring hours no swing
strategy trades. It was precise, it was wrong, and nothing in the output said
so. That is the exact failure this project's evidence standards are written
against, so it is now fixed in three places:

1. `load()` filters to the session and **counts** what it excluded.
2. The report prints a banner of exclamation marks when more than 20% of rows
   fall outside the session, and a file that is entirely out of session
   produces a refusal naming the cause rather than an empty table.
3. `spread_sampler.py` prints, **before collecting**, how many of the planned
   minutes fall inside regular hours, and warns when it is under half.

`--session ext` (04:00-20:00 ET) and `--session all` exist for when the
out-of-hours book is genuinely the subject. Neither is the default.

---

## The failure mode to watch for

**Delayed data looks exactly like live data.** If the market data subscription
sits on the live account and is not shared to paper, IB serves delayed quotes,
which still populate bid and ask — and would produce a spread distribution that
is precise and measures nothing.

So `md_type` is recorded on every row (1=live, 2=frozen, 3=delayed,
4=delayed-frozen), the collector warns loudly on the first tick if it is not 1,
and the report **refuses** to pool anything that is not 1 while counting what it
rejected. A file of nothing but delayed rows produces a refusal, not an empty
table — an empty table reads as "no data" when the truth is "the wrong data".

If that warning appears, fix the subscription. Do not relax the filter.

### The same shape again: a dropped socket

A disconnect does not clear `ib_async`'s ticker objects — they keep their last
bid and ask indefinitely. Writing those with a fresh timestamp records a stale
quote as a live one, and nothing downstream can tell the difference.

The first real run lost 134.6 minutes and then 10.7 more, and it took an
after-the-fact timestamp diff to notice. So the loop now checks
`ib.isConnected()` at the top of every tick **and again immediately before
writing** (a drop during the settle would otherwise slip through), writes
nothing while down, reconnects and resubscribes on its own, and records every
outage with its duration — printed at the end and written to
`<samples>.csv.outages.txt`, so a hole in the CSV is explained rather than
merely present.

---

## What is measured and what is assumed

The report's own caveats section is the authority, but the short version:

- It measures the **quote**, not a fill. It is the correct input to a cost
  model and is not a measurement of slippage. Only real fills measure
  slippage, which is what `common/friction_quotes.py` is for.
- Snapshots on a cadence are an unbiased sample of the spread over time, but
  not the spread at the moments a strategy would trade, and they
  under-represent brief dislocations entirely.
- Displayed depth is not available depth.
- There is no impact model. A marketable order moves the book; nothing here
  prices that.
- A couple of quiet sessions understate a volatile one. The pre-flight already
  established that gap sessions are exactly when spreads widen.

---

---

## G8 — `pit_universe.py`, the point-in-time universe (AT-45)

Builds S&P 500 and S&P 400 membership **as of each date**, plus daily prices for
every name that was ever a member, including the ones since delisted. Source:
EODHD "EOD Historical Data — All World" + the "Indices Historical Constituents"
marketplace API, bought 2026-09-19 (AT-100). Survey: `claude/swing_g8_sources_20260919.md`.

```
$env:EODHD_API_KEY = op read "op://Trading/EODHD/api-token"
python -m strategy.swing.pit_universe constituents
python -m strategy.swing.pit_universe prices
python -m strategy.swing.pit_universe report
```

Writes to `var/swing_pit/`: `raw/` (every response, saved before parsing),
`membership.csv`, `eod/<code>.csv`, `prices_missing.csv`, `coverage_gaps.csv`,
`report.txt`. The prices stage resumes: re-running it skips what is on disk.
The key is read from `EODHD_API_KEY` only; there is no `--key` flag.

The report counts, rather than drops, every membership spell with no prices.
Those rows **are** the survivorship hole, and the number to watch.

---

## `alpaca_coverage_probe.py` — is Alpaca's free IEX feed good enough for the bucket fill? (W07-0012)

The entry-bucket fill (`REGISTERED_swing_v0.md` S2.3, 09:30/11:30/15:30 ET) needs
an intraday quote; only daily EOD bars exist on disk. Three sources were priced
in `claude/w07_0012_intraday_data_options_20260925.md` (EODHD intraday upgrade,
Polygon.io, Alpaca free/IEX-only). Ben, 2026-09-25: *"Let's try Alpaca first. If
there is still gap, then we go for EODHD."* This probe measures that gap on a
**sample**, not the full ~900-name universe, before either the full pull or the
EODHD spend happens.

```
$env:ALPACA_API_KEY_ID = op read "op://Trading/Alpaca/key-id"
$env:ALPACA_API_SECRET_KEY = op read "op://Trading/Alpaca/secret-key"
python -m strategy.swing.alpaca_coverage_probe --sample 40 --dates 20 --confirm
python -m strategy.swing.alpaca_coverage_probe --self-test
```

Requires `membership.csv` and `eod/*.csv` from `pit_universe.py` above (a
(symbol, date) pair is only pulled if it is both a member spell on that date
and `pit_universe.py` already has an EOD close for it). Half the sampled
symbols are drawn from names that were ever delisted from the index, because
that is the coverage risk actually in question, not an all-current sample.
Prints the request-count/wall-clock plan and stops without `--confirm` (§1:
"a tool that can spend HOURS states that number too," even at $0 of billing).

Writes `var/swing_pit/alpaca_coverage_obs.csv` (one row per symbol/date/bucket:
HIT within 5 minutes of the bucket, BACKFILL further back, or MISSING) and
`alpaca_coverage_report.txt` (coverage % by bucket, split ever-delisted vs
current, the close-bucket price gap against the EOD close in bps, and the
symbols with the most missing buckets). **It measures; it does not decide** —
the board's subitem 4 (Ben) reviews the report and approves the EODHD top-up
only if the gap is material.

Same "no repo imports beyond the package" convention as `pit_universe.py`:
standard library only, plus `from strategy.swing import pit_universe as P` for
the membership/EOD readers it already owns. Key from `ALPACA_API_KEY_ID` /
`ALPACA_API_SECRET_KEY` only — the same two names `common/news_pull.py` uses
for the same vendor — never a `--key` flag, both scrubbed from everything
this tool prints.

---

## `intraday_pull.py` — the full EODHD intraday pull (W07-0012 subitem 5, part 1 of 2)

The Alpaca probe above found free IEX 100% MISSING for 2016-2019 and ~80-90%
hit/backfill from 2020 — a material gap against the swing window's
2016-05-10 start. Ben approved and made the EODHD "EOD + Intraday — All World
Extended" upgrade, 2026-09-25 (same account/key `pit_universe.py` already
uses). This pulls every (symbol, date, bucket) the fill engine (part 2, not
yet built) will actually consume — a point-in-time member with an EOD close
on file, same gating the Alpaca probe used — not a symbol's whole history.

```
$env:EODHD_API_KEY = op read "op://Trading/EODHD/api-token"
python -m strategy.swing.intraday_pull --confirm
python -m strategy.swing.intraday_pull --self-test
```

One EODHD `intraday/` request per **chunk** of up to 60 trading days for a
symbol (not one request per symbol-day — the Alpaca probe's per-pair-request
shape does not scale to the full ~900-symbol, ~10-year universe), so a call
covers roughly 60 symbol-days at once. Writes `var/swing_pit/intraday/<code>.csv`
(one row per date/bucket: HIT/BACKFILL/MISSING, same rule and tolerance the
Alpaca probe used) and resumes — a symbol with an existing file is skipped
unless `--refresh`. Prints the chunk-count/wall-clock plan and stops without
`--confirm`.

**Discovers the real per-request window cap rather than assuming it**
(`w07_0012_intraday_data_options_20260925.md`'s own caveat: the ~120-day cap
is inferred from EODHD's docs, not confirmed): any date inside a requested
chunk that has an EOD close on file but comes back with zero bars anywhere in
that chunk's response is flagged to `var/swing_pit/intraday_chunk_gaps.csv`,
never silently folded into a real MISSING bucket. A few scattered gaps look
like genuine no-print days; many clustered at the same offset from a chunk's
start means the assumed 60-trading-day chunk size is too large for the real
cap.

Same conventions as `pit_universe.py` and `alpaca_coverage_probe.py`: no repo
imports beyond `pit_universe` (the EODHD fetch factory and key handling) and
`reversal_v0` (the point-in-time universe loader and its guards) — both
siblings in this package; key from `EODHD_API_KEY` only, no `--key` flag,
scrubbed from everything this tool prints.

---

## `fill_engine.py` — bucket entry/exit pricing, the N-day exit (W07-0012 subitem 5, part 2 of 2)

Turns `reversal_v0.py`'s daily picks into priced trades off `intraday_pull.py`'s
output: entry is the very next trading session after the signal day (spec
S2.3 — "the signal is known at the previous close, and the order is placed at
a fixed clock time the next session," never the signal day itself), exit is
exactly N trading days later at the **same** bucket (S2.4).

```
python -m strategy.swing.fill_engine run --bucket midday --n 5 --k 5
python -m strategy.swing.fill_engine --self-test
```

**This is raw fill pricing only** — one row per (code, signal day): entry/exit
date, bucket price, raw simple return. No costs, no market-relative scoring,
no bootstrap, no K x N x bucket grid — that is spec S3's job, W07-0012
subitem 6, not yet built. A pick that cannot be priced (no next session, no
session N days later, or a MISSING/absent bucket price at either end) is
written to `unfilled_<tag>.csv` with a reason, never silently dropped — spec
S3 item 8 requires every count reported.

**Mutation-tested no-look-ahead guard** (`check_no_lookahead`): re-derives,
independently of trade construction, that every trade's entry index is
exactly the signal index + 1 and its exit index is exactly entry + N.
`tests/strategy/test_swing_fill_engine.py` and the module's own self-test
mutate a trade back onto its own signal day (same-day entry) and short its
hold by one session, and assert the guard catches both — the fill-side
equivalent of `reversal_v0.py`'s hindsight guard.

Writes `var/swing_pit/trades/trades_<k><bucket><n>.csv` and
`unfilled_<k><bucket><n>.csv`. Same "no repo imports beyond the package"
convention: only `pit_universe`, `reversal_v0`, and `intraday_pull` (reads
its `OBS_FIELDS` output shape rather than re-defining it).

W07-0012 subitem 5 (both parts) closes once this lands; subitem 6 (the S3
report layer) is next.

---

## `report_layer.py` — the S3 backtest/report layer (W07-0012 subitem 6)

Turns `fill_engine.py`'s priced trades into the nine things spec S3
(`docs/research/REGISTERED_swing_v0.md`) requires every run to emit: net
market-relative return at three friction levels, both halves, every
calendar year, drop-top-N by name, a 2,000-resample cluster bootstrap, a
2,000-draw random-decile control, the full K x N x bucket grid plus the
ensemble, and coverage/counts.

```
python -m strategy.swing.report_layer run --pit-dir var/swing_pit
python -m strategy.swing.report_layer --self-test
```

**Does NOT spend the holdout** (`holdout_swing.json`, spec S6) — reserved
for the deployed cell alone, and explicitly outside this subitem's own
title.

**Friction (spec S2.6), three levels:**
- `measured` — G2's own **5.46 bps all-in** figure (spread + IBKR fees
  already combined; nothing added here).
- `bucket` — the by-entry-time **spread-only** figure (7.98/3.61/2.96 bps,
  open/midday/close) **plus commission**, added per S2.6's own instruction.
- `stress` — **2x the bucket-specific level's full total** (one of two
  readings the spec's wording leaves open; documented as a caveat).

**Commission is a documented simplification**: the spec doesn't fix a
position dollar size (S2.5 sizes by risk-budget *fraction*), so this module
uses `swing_preflight_20260914.md` S3.5's own conservative upper-bound
combined commission + exchange/regulatory/clearing bps by cap tier — 1.7
bps (S&P 500) / 3.3 bps (S&P 400) — keyed by whichever index's spell covers
the code on its entry date, never an invented per-share formula.

**2:1 levered financing**: 0.99 bps per TRADING day held (linear, per
`swing_preflight` S3.4 / the G2 result's own table) — `Trade.n` already IS
that count. Reported beside the cash-funded headline, never as the
headline itself (G3).

**Market-relative scoring (G1)**: the benchmark — equal-weight average
bucket-to-bucket return of every code *eligible* on the entry date (not the
picked decile) with both a priced entry and exit — does not depend on which
codes were picked. It is cached once per `(entry_date, exit_date, bucket,
index)` and reused across every one of the 18 grid cells and every
random-decile draw that shares it, which is what keeps a 2,000-draw control
tractable.

**Every aggregation helper is weight-aware** (`aggregate`, `by_half`,
`by_year`, `drop_top_n`, `cluster_bootstrap_by_month`): a row's `weight`
defaults to 1.0, and the N-ensemble pools its three N=5/10/20 sleeves at
weight 1/3 each (S2.4) and reuses every helper unchanged rather than a
second set of ensemble-specific formulas.

**drop-top-N** ranks CODES by total weighted contribution and drops the
top N's trades entirely; `"n/a"` (never a `$0`-shaped result) when the
sample has N or fewer distinct codes traded, per the spec's own
instruction.

Writes a plain-text report (`--out`, default
`claude/raw/w07_0012_report_layer.txt`) and a JSON summary with the bulky
per-trade rows stripped (`--json-out`) — `write_scored_rows_csv()` exports
any one cell's trade-level rows separately when that detail is needed.
`--random-draws` overrides the 2,000-draw default for a quick smoke run.

Same "no repo imports beyond the package" convention: only `pit_universe`,
`reversal_v0`, and `fill_engine`, siblings in this package.

W07-0012 subitem 6 closes once this lands. Subitems 7 (the real EODHD pull,
Ben, hands-on) and 8/9 (running the backtest on real data, the S3 result
doc) are next.

---

## Open, blocking

- **G2** is **provisionally cleared**: 2026-09-18, one full regular session,
  31,043 usable observations, median all-in round trip **5.46 bps** against a
  40 bps threshold, every symbol passing individually and depth no longer
  binding at USD 9,000. Two more sessions -- ideally including a volatile one
  -- before it is called closed. `docs/swing_g2_RESULT_20260919.md`.
- **Entry time of day is a free lever and is not yet registered.** The open
  costs 2.7x the close (7.98 bps at 09:30, 2.96 at 15:30). Any candidate must
  state when it enters and pay that bucket's spread.
- **G8** (point-in-time universe): source bought (EODHD, AT-100); `pit_universe.py` builds it (AT-45). The pre-flight's own
  universe is 100% survivors — fine for magnitude and dispersion, not for any
  strategy result.
- Amended SEC Rule 605 filings from October 2026 are worth re-checking as an
  independent cross-check on whatever the sampler measures.

See `docs/swing_preflight_20260914.md` for the full pre-flight and the G1-G8
register.
