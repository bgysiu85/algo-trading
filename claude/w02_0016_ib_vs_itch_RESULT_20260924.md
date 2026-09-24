# Why live and backtest take different trades: IB bars vs ITCH bars, signal-by-signal. Result, 2026-09-24 (W02-0016): a data-density story, not a price story

Descriptive, not registered (Ben's decision A on W02-0016, raised by W02-0002 —
`mcl_vs_mc5_live_RESULT_20260923.md`). Run on the 68 live symbol-days where
live traded and either matched a sim entry or didn't (98 strategy/symbol-day
rows, MCL + MC5 together). IB bars pulled fresh 2026-09-24 via
`common/data_ib.py`; ITCH bars already cached from the W02-0002 screen run.

**A bug was found and fixed in this session, before this was reported.** The
first pass flagged every single symbol-day as "bars diverge" — 98/98. That
was wrong: IB's `reqHistoricalData` fills every quiet minute with a flat,
zero-volume bar (last close carried forward); ITCH's tick-built bars simply
don't exist for a minute nothing traded. The first version counted that as
"IB has bars ITCH doesn't → material divergence" for every name. Across a
15-symbol-day sample, 30–52% of IB's bars were these zero-volume fills — the
outer-join comparison was comparing filler against absence, not price
against price. Fixed to compare price only where both feeds show a real
trade, and to treat IB's zero-volume fill on a minute ITCH did trade as its
own, more specific finding rather than folding it into "divergence." See
`common/ib_vs_itch_study.py`'s module docstring and `bar_diff`/`classify` for
the corrected method.

## In plain terms

- **When both feeds show a real trade on the same minute, they agree closely
  on price.** Across all 98 symbol-days, the median close-price gap is
  **0.04%**, and even the worst symbol-day's median gap is 0.42%. IB and
  ITCH are not seeing meaningfully different prices.
- **The real difference is which minutes have a trade at all, not what price
  they traded at.** On **22 of 98 (22%)**, IB shows no trade at all in a bar
  where ITCH does, and the entry the strategy picks then differs between the
  two feeds — MCL/MC5's volume-surge and MFI conditions read zero on IB's
  filler bar where ITCH saw real volume, which can suppress or delay IB's
  signal relative to ITCH's.
- **On another 40 (41%), both feeds still find an entry, just not the
  identical bar** — small bar-boundary timing noise, not a different trade
  thesis: 28 of those 40 have their nearest entries within 5 minutes of each
  other; only 6 of the 40 have one feed entering and the other never firing
  at all.
- **On 36 (37%), the two feeds pick the exact same entry bar(s).**
- This is consistent with, and explains most of, W02-0002's headline fact
  (only 9 of 68 live MCL trades, 15 of 33 live MC5, matched a sim entry
  within 2 bars): most of that gap is IB missing quiet-minute trades that
  ITCH's direct feed captured, plus ordinary bar-boundary noise — not a
  pricing error, and not an execution bug.

## What Ben must decide

Nothing is forced; this is descriptive. Two options:

- **A — leave it.** The population comparison (`mcl_vs_mc5_live_RESULT.md`)
  already found MCL better per symbol-day; this explains *why* live and
  backtest disagree on individual trades without indicating either feed is
  wrong, just less complete on quiet minutes for these low-float names.
- **B — chase the 22 "IB shows no trade" cases further.** Candidate next
  step: check whether IB's SMART routing is missing off-exchange (dark
  pool / other venue) prints on these low-float names that ITCH's direct
  Nasdaq feed captures — that would be a specific, and possibly addressable,
  feed-completeness gap rather than a modelling question. Raised as
  **W02-0017** for Ben's call.

## 1. Counts (98 strategy/symbol-days: MCL + MC5)

| Verdict | n | % |
|---|---|---|
| bars and signal agree | 36 | 37% |
| bars agree, signal timing diverges (other cause, mostly near-miss) | 40 | 41% |
| IB shows no trade where ITCH does, signal timing diverges | 22 | 22% |
| bars diverge on price | 0 | 0% |

Of the 40 "other cause": 34 had both feeds fire at least one entry (28 of
those 34 within 5 minutes of each other); 6 had one feed fire zero entries.

Price agreement (median close delta, on bars both feeds traded): median of
per-symbol-day medians **0.0355%**, worst symbol-day's median **0.419%**.

## 2. Method

For each (strategy, symbol, date) where live traded (matched or live-only in
`var/reports/live_vs_sim_trades.csv`): run the identical published entry
rule (`common.pit_strategy.engine`, the same code the live trader and the
backtest both call) once on the cached IB 1-minute bars and once on the
cached ITCH bars, with the identical `not_before` floor
(`feed_delay.delayed_floor`, same offset convention as the registered
study: +15 before 2026-09-21, +0 from). Bar-level comparison restricted to
timestamps both feeds actually cover; price delta computed only where IB
shows real volume (excludes its flat filler bars) and ITCH also has a bar.

**Caveat, stated plainly:** this does not reproduce the registered
population's per-trade numbers — it hands both engines the full cached
3-session superset as warm-up rather than the registered pipeline's own
day-by-day construction. That gives both feeds identical warm-up length,
which is what makes the IB-vs-ITCH comparison itself fair; it is not a
substitute for `live_vs_sim.py`'s own numbers, and isn't meant to be.

## 3. Source files

`common/ib_vs_itch_study.py`, `var/state/ib_vs_itch_pairs.json`,
`var/reports/ib_vs_itch_study.txt`, `var/reports/ib_vs_itch_study_symdays.csv`
(copies: `claude/raw/w02_0016_ib_vs_itch_report_20260924.txt`,
`Claude outputs\w02_0016_ib_vs_itch_symdays_20260924.csv`).

## Next steps (board)

- W02-0016: Done.
- **W02-0017** (new, Ben): whether to chase the IB-SMART-routing /
  off-exchange-print hypothesis for the 22 "IB shows no trade" symbol-days,
  or leave it.
