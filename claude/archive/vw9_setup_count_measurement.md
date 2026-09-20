> **ARCHIVED 2026-09-08.** VW9 is rejected on history and paper-traded only for live data; its rules live in `vw9_strategy_spec.md`.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

> **Stale figures — the fill-model correction.** Every P/L number below predates
> the 2026-09-05 fix to gap-through fills and peak-seeding, and is overstated
> because of it. Applied to VW9 that correction cost roughly 73% of its
> headline; MCL went +$1,567 → +$161 and MC5 +$20,156 → −$400, on identical
> trades.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check.** Measured on a fuller tape
> that includes off-exchange prints, the backtests charge ~$2.00 per 100-share
> round trip against a real ~$1.00 — they are slightly *conservative* on
> slippage, not wrong. See `execution_cost_measured.md`.
>
> So: overstated by the fill-model correction, and by that alone. The reasoning
> and the decisions recorded here stand.

# VW9 §8.3 setup-count measurement — built, not yet run

Built 2026-09-04. Code lives on bens-proart at
`D:\Trading\EMA Crossover Strategy` (new sibling folder to
`D:\Trading\MCL Strategy`, at Ben's request — going forward, everything for
the EMA-crossover strategy family goes there).

## What this is

`claude/vw9_strategy_spec.md` §8.3 ("Setup counts") is the go/no-go pre-flight
measurement that has to run before any of VW9's twelve uncalibrated parameters
are trusted: how many Setup A (VWAP reclaim, §4.1) and Setup B (9 EMA retest,
§4.2) triggers fire per pair per session, at 5-minute and 15-minute, **before**
the §4.3 gates (liquidity, pullback-volume, extension, headroom, re-entry cap)
are applied. The spec's own words: "This sets the sample size and is the
go/no-go. If VW9-5 produces more than ~5 triggers per pair per session the
gates are too loose and the strategy is closer to noise-trading than to the
sources' intent."

## What was built

Against the real interfaces in `MCL Strategy/mcl_backtest.py` and
`mcl_strategy.py` (per Ben's instruction), not written standalone:

- `indicators.py` — `ema`/`rma` copied verbatim from `mcl_strategy.py` (so
  E15/VW9/V7/MC5 never silently disagree on what those mean), plus `atr` and
  `session_vwap`, which MCL never needed. `resample_bars` follows
  `mc5_strategy.to_5m`'s left-labelled convention, and — per both E15 §1 and
  VW9's inherited rule — drops a bucket with zero source bars rather than
  synthesising a flat one.
- `vw9_strategy.py` — the §3 regime gate (STRONG/WEAK_BULL/BEARISH, gated on
  VWAP and EMA9 maturity) and §4.1/§4.2 Setup A/B detection as a bar-by-bar
  state machine. Deliberately stops short of §4.3 gates, §5 exits, and §4.4
  context levels — this is only the count.
- `data_ib.py` — full 04:00–20:00 ET session bar puller, adapted from
  `mcl_backtest.py`'s `Runner` (same qualify/pace/checkpoint pattern), caching
  to disk so repeated measurement runs don't re-hit IB.
- `cache_io.py` — split out so the analysis step (`vw9_setup_counts.py`) has
  no `ib_async` dependency and can be re-run offline as often as needed while
  parameters are tuned.
- `vw9_setup_counts.py` — the CLI that produces the §8.3 report: per-timeframe
  mean/median triggers per pair, Setup A vs B split, the noise-trading
  threshold flag, and `setup_counts_trades.csv` (every trigger, with
  `entry_ref`/`structure_low` already computed — the raw material §8.4 needs
  next).
- `test_indicators.py` + `test_vw9_strategy.py` — 24 tests, all passing.
  Every numeric scenario in the latter (clean reclaim, insufficient bearish
  run, clean retest, VWAP-breach abandon, uncontrolled-drop abandon,
  too-long-pullback abandon, stale-high block, VWAP-never-matures) was
  verified interactively bar-by-bar before being pinned into an assertion —
  hand-deriving EMA/VWAP by formula stops being practical past a handful of
  bars.

Full pipeline (load pairs → load cached bars → session-slice → resample →
detect → aggregate → CSV) was exercised end-to-end against synthetic cached
bars in the build sandbox and produced sensible output. What was **not**
exercised: an actual IB connection, or real market data — this sandbox has
neither. `data_ib.py` needs to run on bens-proart against IB Gateway (paper
port) before `vw9_setup_counts.py` has anything real to measure.

## Known interpretive calls, worth reviewing before trusting the numbers

- **ATR is unconditional from bar 1** (soft `rma` warm-up, matching how
  `mcl_strategy.py` treats RSI — no hard gate). On a synthetic steep trend
  this makes the `PULLBACK_CTRL_ATR` check read as strict, since EMA9 lags
  price further than a realistic ATR "allows" a controlled pullback to
  cross. See the `impulse()` comment in `test_vw9_strategy.py`. Whether this
  matters on real data is exactly what §8.4's distributions (pullback depth
  in ATR, bars-to-trigger) will show — not yet run.
- **Setup A counts every reclaim, including ones that fail immediately.**
  The spec's entry is unconditional on the reclaim bar; a next-bar drop back
  below VWAP is a §5.3 exit, not something that un-fires the §8.3 count. So
  §8.3's Setup A number is not itself a quality signal, only a frequency one.
- **Re-entry is uncapped**, per §4.3's `MAX_ENTRIES_PER_SESSION` being one of
  the gates this measurement is explicitly counting *before*.
- E15's equivalent (§7 item 3, "Crossover count") was **not** built — only
  VW9's §8.3, per what was actually asked. The two share enough machinery
  (`indicators.py`, `data_ib.py`, `cache_io.py`) that E15's version would be
  a small follow-on if wanted.

## Next

1. Run `data_ib.py` on bens-proart (full 407-pair pull, ~75 min order of
   magnitude, same IB pacing as `mcl_backtest.py`).
2. Run `vw9_setup_counts.py` against the cache. Read the go/no-go: is VW9-5's
   mean triggers/pair/session in a workable range, or above the ~5 noise
   threshold?
3. If it's viable: §8.1, §8.2, §8.5 (bar availability, dollar volume, VWAP
   degeneracy), then §8.4 (distributions) to replace the twelve guessed
   parameters — `setup_counts_trades.csv` is already positioned to feed that.
4. Only after that: write `strategies/vw9.py` for real, per §12 of the spec.
