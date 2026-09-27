# AT-105 subitem 3 — TL-v0 pre-flight RESULT (REGISTERED_tl_v0.md §5)

**Training side only. No exit prices, no P&L — by design (§5's explicit refusal).**
Code: `common/tl_v0_data.py`, `common/tl_v0_lines.py`, `common/tl_v0_preflight.py`
(commit `9a6a232`). Raw output: `D:\Trading\Claude outputs\tl_v0_preflight_20260920.txt`,
`..._entries_20260920.csv`, `..._counts_20260920.csv`.

## In plain terms

This measures how often TL-v0's trend-line breakout would fire on the owned
GLBX daily bars (2010-06→2021-12), how often the weekly top-down filter would
block it, and — the number that matters most — how big the initial stop is in
dollars, and what fraction of signals could actually be sized at $22,000. It
does **not** run a backtest: no stop-hit is simulated and no trade P&L exists
anywhere in this run. One real consequence of that: v0 (which only exits on a
stop, never on an opposite break) opens once per market and then "ignores"
every later opposite break for the rest of the window, since there's no stop
simulation to close it — so v0's own "signals" count is ~1/market, and
"allowed breaks/year" is the more honest frequency number for it. v0-rev
(which reverses instead of ignoring) has a real, if stop-independent, entry
count: roughly 6–14 signals/market over 11.6 years at pivot size 5.

## Verdict — §5.1's stop rule

Genuinely ambiguous on two readings; both are reported rather than picking
the one that passes:

- **Reading A** (per-market): 7 of 13 markets have ≥50% of their v0-rev
  signals sizeable at 2% risk — **clears, barely** (>half of 13 is 7).
- **Reading B** (pooled across all markets): only **42.2%** of all v0-rev
  signals are sizeable at 2% — **fails** on this reading.

**What Ben needs to decide:** which reading of §5.1 governs before step 4
(the actual backtest) is built — or whether to treat this as inconclusive
and let G2 (AT-43, TSMOM's own training-side result) and G3–G5 settle it
first, which is the order already registered.

## Tables (dollars; the per-market breakdown, v0-rev pooled R=3/5/8)

| Market | n signals | Unit | Median stop $ | % sizeable @1% | % sizeable @2% |
|---|---:|---|---:|---:|---:|
| 6A | 33 | micro | 178 | 64% | 76% |
| 6B | 28 | micro | 165 | 57% | 75% |
| 6E | 24 | micro | 292 | 25% | 71% |
| CL | 30 | micro | 453 | 23% | 50% |
| GC | 40 | micro | 404 | 25% | 55% |
| HG | 33 | micro | 371 | 15% | 55% |
| MTN | 11 | micro | 140 | 64% | 100% |
| ES | 15 | micro | 496 | 20% | 47% |
| RTY | 12 | micro | 456 | 17% | 33% |
| 6J | 35 | full | 2,066 | 9% | 9% |
| ZN | 25 | full | 1,122 | 8% | 16% |
| NG | 36 | full | 2,995 | 3% | 3% |
| SI | 38 | full | 990 | 3% | 11% |

Weakest markets match TSMOM's own AT-43 capacity finding (NG, SI, ZN
unsizeable at $22k) — joined here by 6J and RTY under TL-v0-rev's tighter
trend-line stops. The four currency majors plus MTN size best, because their
stops are small in $ terms relative to $22k, not because their line geometry
is cleaner.

## Method, in one paragraph

Held-contract continuous series built the same way TSMOM's amendment C was
(front-month `c.0` for ES/RTY/CL/NG/6A/6B/6E/6J, cross-checked already via
AT-41; active-cycle lookup replicated from the TN/MTN top-up read-back for
GC/SI/HG/ZN/TN), difference-back-adjusted (never ratio — CL's April 2020
negative print survives). Pivots at L=R∈{3,5,8}, resistance/support from the
two most-recently-confirmed pivots only (no search through older pivots for
a qualifying pair — a judgement call, flagged below). Action-line breaks are
crossover events (close beyond the line by >0.10×ATR14). Weekly filter uses
the identical construction on weekly bars, completed weeks only, gated one
week behind the daily bar it filters. Initial stop = opposing line (daily
for v0, weekly falling back to daily for v0-rev) ∓0.25×ATR14, else the
registered swing-point fallback.

## Caveats — read before this feeds step 4

1. **No stop-hit simulation anywhere.** This is the biggest scope limit:
   v0's real trade count can only come from the step-4 engine.
2. **Weekly pivot size = daily sleeve's pivot size.** Not pinned by the
   registration; this run's judgement call.
3. **§5.1 has two readings** that disagree (see Verdict). Not resolved here.
4. **MTN's $100/point multiplier is applied to TN's training-window
   geometry** even though MTN itself wasn't listed until 2024-03-25 — a
   fixed contract spec, not a look-ahead, but MTN's training-window figures
   describe signal risk, not executability.
5. Full per-year, per-market, per-pivot-size cut is in the delivered CSVs,
   not reproduced in the raw .txt (which pools by pivot size and by market
   separately to stay readable).

## Next step

Per REGISTERED_tl_v0.md "Next steps": G2 (AT-43, TSMOM training-side result)
and G3–G5 (Python↔Pine parity, holdout cut+mutation test, hindsight-guard
test) before any backtest (step 4) starts. AT-105 subitem 3 is done.
