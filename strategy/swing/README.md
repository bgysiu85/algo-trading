# strategy/swing

Swing trading: 2-20 trading day holds in liquid US large/mid caps.

**Status as of 2026-09-14: pre-flight only. There is no strategy here, by
design.** `docs/swing_preflight_20260914.md` fixed go/no-go criteria G1-G8
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
python -m strategy.swing.spread_sampler --minutes 390
```

Defaults to `var/reports/spread_samples.csv`, append mode, flushed per row, so
a disconnect mid-session loses nothing and a re-run continues the same file.

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

## Open, blocking

- **G2** stays open until the sampler has run over several sessions and the
  report clears 40 bps for the chosen universe.
- **G8** (point-in-time universe) has no answer yet. The pre-flight's own
  universe is 100% survivors — fine for magnitude and dispersion, not for any
  strategy result.
- Amended SEC Rule 605 filings from October 2026 are worth re-checking as an
  independent cross-check on whatever the sampler measures.

See `docs/swing_preflight_20260914.md` for the full pre-flight and the G1-G8
register.
