# Session review — 2026-09-17 paper session (and handover items)

From the live paper-trade analysis chat (read-only on production). Raw report: `D:\Trading\Claude outputs\session_review_20260917.txt`. Ran on `prod-20260916c` (`dcb5224`). Real fills, commission deducted. 09-16 is covered by `green_day_attribution_20260916.md` and `handover_meds_ghost_position_20260916.md`; its MEDS 06:16 exit fill is still unknown.

## The day
- **37 round trips, net 10.16**, 27% win. MCL 7 trades +95.37; MC5 30 trades (85.21).
- Top 3: MC5 BIAF +149.62, MCL RETO +88.63, MC5 RETO +83.63. Ex-top-3: (311.72) over 34.
- Exits: trailing_stop 25 +200.64; gradient_reversal 10 (150.74), all MC5; window_close 2 (39.74).
- IBKR refused ZTG, KXIN, NBIG. Cap skips 5.

## Last night's fixes: all held
Stale-bar gate (no entry before 04:06), trail seeded from the fill, ghost-position D1/D2 (5 exits needed a second attempt, each checked IB and filled in 1–3 s, nothing open at close).

## Defects for the build chat
**A. A cancel the trader sends itself is logged as REJECTED (measurement).** Six rows "REJECTED — Error 202: Order Canceled - reason:" with a blank reason: 4 abandoned exits (next attempt filled 1–3 s later), 2 timed-out entries (DAIC 04:50:05, 09:27:04). After `_settle`, a self-sent cancel returns status `Cancelled` plus IB's 202 echo and falls into the "IB never worked it" branch. `NO_FILL_ABANDONED` / `NO_FILL_CANCELLED` no longer appear, so fill-rate and rejection counts are wrong from 09-17. Fix: record order ids the trader cancelled and treat their 202 as a no-fill, not a refusal; test both paths.

**B. Re-entry on a bar that closed during the previous position.** While a position is open, new signal bars aren't evaluated. On exit, the bar that closed during the old position is evaluated and bought immediately at the current price. 7 re-entries within 5 s of the same strategy's own exit today: (82.62). Worst: MC5 RETO sold 3.30 at 08:24:24, bought 3.29 at 08:24:25 on a 5-minute bar that closed 2.45 (+34.5% drift). Parity question: the engine can't buy a bar's close minutes after it.

**C. No placement guard on quote drift.** 9 buys went into a quote ≥3% from the signal close: (161.35). Union of B and C: **10 trades, 1 winner, (102.73)**; the other 27 made +112.89. Drift as an *entry filter* was null over 138 trades (09-14/15 review §3); this is a narrower claim — an extreme-drift placement guard, recommended then and not built. Register before building; pick the threshold up front.

## Observation only
First entry per name today 9 trades (168.36) vs later entries 28 +178.52, same direction as 09-09..09-16 live. H-B1 read NOTHING on 6,170 PIT symbol-days, so this is not a rule.

## Running live record
194 round trips, **(980.02)** = (5.05)/trade. MCL (521.24), MC5 (458.78). 09-16 +212.95 and 09-17 +10.16 are the first two non-negative sessions in a row.
