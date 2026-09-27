# Handover — W15-0014 subitem 1: the TL-v0 / TL-v0-rev step-4 backtest engine (2026-09-28)

**Chat:** Build & test chat · **Board:** W15-0014 (subitems 1 done, 2 next, 3 after) · **Registration:** `docs/research/REGISTERED_tl_v0.md` (amendments A–D added PRE-RUN, §0.1)

## In plain terms

The engine that runs Tori's trend-line method (v0 and v0-rev) through 2010–2021 on 12 futures markets, with real contract rolls, costs and whole-contract sizing, and puts it side by side with a plain Donchian channel and two other controls, is built and tested. **No profit or loss has been computed on real data yet.** The run is the next step and happens on Ben's PC (about a minute; the archive is on E:). Nothing from 2022 onward can be read.

## What was built — `strategy/tl_v0/`

| File | What it does |
|---|---|
| `spec.py` | Every fixed value: 12 markets, vehicles, $/point, tick $, friction $0.50/$1.25/$2.50, 1% risk, $22,129 / $100k / $500k |
| `bars.py` | Daily OHLC on the held contract (TSMOM roll rule, imported), Sunday rows folded, back-adjusted signal series with the roll gap measured on the roll session, holdout cut at load |
| `signals.py` | Per bar: breaks, weekly filter (completed weeks), safety-line levels for v0 and v0-rev, fallback stops. Line geometry comes from the G3/G5-cleared `common/tl_v0_lines.py` |
| `sim.py` | The bar walk in Pine's order: pending exit → entry at the open (void if beyond stop) → resting stop (gap = fill at open) → trail (never loosens) → signals |
| `pnl.py` | Books each trade on the actual held contract, leg by leg across rolls; 2 sides per roll; 1 tick on stop fills; raw-price daily mark-to-market |
| `engine.py` | Runs v0 and v0-rev (each pivot size, as ensemble sleeve and alone), C1 Donchian 20/10, C2 chandelier, C3 TSMOM-hold, under fractional and integer sizing |
| `report.py` | §3 outputs and the §4 eight-criterion verdict for v0-rev (holdout candidate) and v0, plus Davey figures (reported only), sample trades in dollars |
| `run.py` | `python -m strategy.tl_v0.run` — writes report + 3 CSVs to `D:\Trading\Claude outputs`; refuses `--holdout` and `--limit` |

## Decisions Ben made in this session (PRE-RUN, written into the registration)

- **Amendment B — verdict book:** "Fractional @ $22,129 (Recommended)". The whole-contract book at $22,129 is printed beside every verdict line; opposite signs = the headline.
- **Amendment A — markets:** "12 markets, MTN only (Recommended)". ZN dropped (it was TSMOM's alternative rates arm).

## Calls made in the build (Amendments A and C), for Ben to veto before the run

1. Sunday UTC stub rows are folded into Monday (the pre-flight used them as whole bars: 61 of its 399 entries were Sunday-dated).
2. The back-adjustment gap is measured on the roll session (the pre-flight's loader removed one day's real move at every roll).
3. v0-rev's weekly safety line is extrapolated into the current week; the initial stop follows Pine's `pendStop`.
4. C3 holds each position exactly H sessions (H = the median hold of the rule set it is compared with), then renews on the sign.
5. ATR(14) is unknown for the first 13 bars, daily and weekly (Pine).

## Tests and review

- **53 tests** in `tests/strategy/tl_v0/` (plus the 24 existing TL-v0 line/holdout tests) pass on pandas 3.0 (Ben's venv) and pandas 2.3.
- **20 mutations** of the rules (gap fill at stop, no voiding, filter off, trail loosening, holdout skipped, no back-adjustment, weekly peeking, no slippage, rolls not charged, wrong sleeve share, …): every one is caught by a test.
- **Look-ahead:** every signal array is identical whether or not the future bars exist (cut at 70+ points); the reviewer's end-to-end cut test found 0 differing trades.
- **Independent review** (separate agent): no look-ahead and no fill-logic defects. One blocker (the verdict book was not registered) — resolved by Ben's Amendment B. Should-fix items all fixed: C3 held exactly H; stale-price fills flagged per trade; booking now checks every fill lands on the traded contract's own bar; holdout cut at load; weekly ATR gated; duplicate market names deduped.

## Known limits (in the report's caveats)

- The bars are **UTC days** (~7–8pm New York to the same time next day), so "next open" is an evening-session price, and a stop gapped through at the 5pm halt or an 8:30am release is inside the bar and booked at the stop + 1 tick. The gap-at-open rule mostly bites on Mondays.
- MTN was not listed until 2024; its 2016–2021 figures describe the signal only.
- NG and 6J trade full contracts and will mostly skip at $22,129.

## Next steps (board)

- **W15-0014 subitem 2** — Ben runs the backtest (commands on the board). Assignee Ben.
- **W15-0014 subitem 3** — Result doc from the report (Sonnet / Medium), after the run.
- W15-0019 / W15-0020 (TL-v1) reuse this engine; W15-0020 takes v0-rev's result from this run as its control C2.

## Commands (also on the board)

```
Set-Location D:\Trading
git add strategy/tl_v0 tests/strategy/tl_v0 docs/research/REGISTERED_tl_v0.md claude/handover_w15_0014_engine_20260928.md
git commit -m "W15-0014: TL-v0/TL-v0-rev step-4 backtest engine + PRE-RUN amendments A-D"
.\.venv\Scripts\python.exe -m pytest -q tests\strategy\tl_v0 tests\test_tl_v0_lines.py tests\test_tl_v0_hindsight_guard.py tests\common\test_tl_v0_holdout.py -p no:cacheprovider
.\.venv\Scripts\python.exe -m strategy.tl_v0.run
```
