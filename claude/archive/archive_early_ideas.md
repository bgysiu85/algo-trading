> **ARCHIVED 2026-09-08.** Older ideas, retained for the record.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

# Archive — early strategy ideas (August 2026)

Two strategy ideas from August 2026 that were never built. They are kept here
for the **reasoning**, not the conclusions: the setup logic, the decisions taken
and the open questions are still worth reading, but nothing in either document
represents current program state. Both are superseded by the strategies in
`PROGRAM_INDEX.md` §2 (Strategy roster).

**Neither document has been re-examined against the 2026-09-05 fill-model
correction (gap fills and peak seeding) or the 2026-09-06 crossing-cost
measurement (`execution_cost_measured.md`).** Any figure, threshold or
reward-to-risk assumption either one contains should be treated as unreliable.

The two originals — `claude/first_candle_rule_strategy.md` and
`claude/bull_flag_algo_design.md` — were merged into this file and deleted.
Their bodies follow unchanged apart from heading levels, which were shifted down
so this document has a single heading hierarchy.

---

## First candle rule

### First Candle Rule (FCR) — strategy spec

Source: short-form video "I Trade This One Candle Daily. It's Stupid and Simple" (uploaded to session 2026-08-25).
Rules recovered from the video's burned-in captions and chart diagrams. Implemented as `FCR_Strategy.pine` (Pine Script v6, TradingView).

#### Core idea

The 09:30–09:35 ET opening 5-minute candle ("first candle range", FCR) defines the only two levels used for the whole session: its high and its low. All execution happens on the 1-minute chart.

#### Entry sequence

1. **Mark the range.** On the M5 chart, record the high and low of the 09:30–09:35 ET candle.
2. **Break.** On M1, wait for price to break one of those levels — high for longs, low for shorts.
3. **Displacement / FVG.** The break must leave a **fair value gap**: a true 3-bar gap between candle *wicks* (bar[0].low > bar[2].high for bullish; bar[0].high < bar[2].low for bearish). The video is explicit that a wick poke or a plain candle close through the level is **not** enough — the gap is what signals real force and reveals who is in control.
4. **Retest.** Wait for price to trade back into the FVG.
5. **Engulfing confirmation.** Enter only when an engulfing candle prints inside/at the retest, in the direction of the break. This is the filter the video credits with avoiding losers.
6. **Target.** Fixed 3:1 reward-to-risk.

#### Decisions not specified by the video (chosen for the implementation)

| Item | Choice | Notes |
|---|---|---|
| Direction | **Long only** (breaks of the FCR high) | Shorts are implemented but disabled by default via the "Allow shorts" input. |
| Trades per session | **Max 5** | Raised from an initial cap of 2. See the gap-priority note below — the cap interacts with how stale gaps are handled. |
| Stop placement | Engulfing candle's low (+ optional tick buffer) | Matches the small risk box shown in the video's final frame. Alternatives worth testing: far edge of the FVG, or back inside the FCR. |
| Setup window | 09:35 – 11:00 ET, flat at window close | The video claims the levels hold "the entire trading day"; the morning window is the higher-conviction subset. |
| Break confirmation | Candle close beyond level (not wick) | Consistent with the video's "a wick is not enough". |
| FVG placement | Must sit entirely beyond the FCR level | Matches the diagram, where the gap box is fully outside the range. |
| Gap-to-break linkage | FVG must complete within 3 bars of the break | Ties the gap to the breakout rather than any later gap. |
| Competing gaps | Track newest **untested** gap | An untested gap left sitting there would otherwise block every later setup until it expires — this matters much more at 5 trades/session than at 2. A gap that has already been retested is never disturbed, since it is waiting on its engulfing candle. |

#### Implementation notes

- Chart timeframe: **1 minute**. The script raises a runtime error above 5 minutes.
- The FCR is computed from the 1-minute bars directly (no `request.security`), so there is no repaint risk from higher-timeframe lookahead.
- `process_orders_on_close = true` — entries fill at the close of the engulfing bar, as described. Optimistic versus a live market order; budget for slippage.
- Sizing supports fixed quantity or % of equity risked (uses `syminfo.pointvalue`).
- Gaps expire after N bars (default 30) or when price closes clean through the far side.
- One position at a time; no pyramiding.

#### Open questions for testing

- **Does long-only plus a 5-trade cap actually produce 5 setups?** The 09:35–11:00 window is ~85 M1 bars; requiring break → FVG → retest → engulf on the long side alone may well cap out at 1–2 real signals most days. Check the realised trades-per-day distribution before assuming the cap binds.
- Which stop variant survives a realistic spread/slippage assumption on ES/NQ vs. large-cap equities?
- Is 3:1 reachable within the 09:35–11:00 window, or does the window-close exit truncate most winners? Compare against a full-RTH window.
- Does the "gap fully beyond the level" constraint cut sample size too far? Test with it off.
- Body-engulf vs. close-beyond-prior-extreme as the trigger definition.
- Long-only introduces a directional bias — worth checking performance against the index's own drift over the same sample, so the edge is not just beta.

#### Relationship to the IBKR work

This is a separate setup from the bull flag design in `claude/bull_flag_algo_design.md`, but the plumbing overlaps: session-anchored levels, an intraday window filter, an R-multiple exit. If the FCR backtests acceptably, the `ib_async` execution layer described in `claude/ib_async_setup_guide.md` can drive it with only the signal function swapped.

---

## Bull flag algo design

### Bull-flag momentum algo — design notes

Delivered as `ibkr-algo.zip` on 2026-08-07. Inspired by the Warrior Trading /
Ross Cameron momentum style; implements the **bull flag continuation**
setup specifically (chosen over gap-and-go / ABCD for v1).

#### Decisions made with Ben

- Scope: scanner + backtester first (not live paper execution yet).
- Setup: bull flag continuation only, for now.
- Risk: fixed $500 risk per trade (not % of equity), 2:1 reward:risk default.
- Historical data source: IBKR's own `reqHistoricalData` via `ib_async`
  (not Polygon.io or another paid provider).

#### Architecture

- `config.py` — all tunable thresholds (flagpole %, retracement %, volume
  multiples, risk $, reward:risk ratio).
- `patterns.py` — no-lookahead flagpole → flag → breakout detector.
- `risk.py` — fixed-dollar position sizing.
- `backtest.py` — walk-forward trade simulator (stop/target/EOD exit),
  summary stats (win rate, avg R, profit factor, max drawdown).
- `scanner.py` — IBKR live scanner (top % gainers, price/volume filtered;
  no float filter available via the API).
- `data.py` — paged historical bar fetch with pacing delays.
- `main.py` — CLI entry point (`python main.py [--symbols ...] [--days N]`).

Runs locally only (local-socket connection to TWS/IB Gateway) — cannot run
inside a Claude cloud session.

#### Known limitations (see README for full list)

- No historical scanner via IBKR API — backtest universe must be supplied
  explicitly via `--symbols`, so it tests "would this rule work on this
  stock" rather than "would this rule find and trade the right stocks."
- No float filter (IBKR scanner doesn't expose it).
- No slippage/commission modeling.
- Mechanizes a discretionary setup — doesn't see news catalyst quality or
  order flow/tape, only price+volume shape.

#### Possible next steps

- Add gap-and-go and/or ABCD pattern detectors alongside bull flag.
- Add a proper equity-curve/relative-volume-vs-time-of-day baseline instead
  of the trailing-average-volume proxy currently used.
- Move from backtest-only to paper-trading execution via `ib_async`
  order placement, once backtest results are validated by hand.
- Consider a dedicated small-cap data provider (e.g. Polygon.io) if IBKR's
  historical coverage proves too thin for the symbols of interest.
