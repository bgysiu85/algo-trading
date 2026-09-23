# REGISTERED — Oliver Velez's 25%-retracement scalp (W11-0026)

Written 2026-09-23 **before any code exists and before any result is seen**.
Source: `claude/yt_collation_olivervelez_scalping_20260923.md`
("The Simplest Scalping Strategy I Use Daily", Oliver Velez Trading, 2025-09-12).

Ben, 2026-09-23: *"the strategy should be simple enough that we can run a
backtest against it and verify any truth to his claim"*.

## 1. The two claims under test

- **C1 (the statistic).** After a sharp one-directional move, the bounce
  reaches 25% of the move ~9 in 10 times, 50% ~6 in 10, 75% ~2 in 10,
  100% ~1 in 10.
- **C2 (the trade).** A scalper should take the bounce with the 25% level
  as the target, because it is reached most reliably.

C1 can be true and C2 still lose money: by the time the entry trigger fires,
part of the 25% is already gone, while the stop sits below the low.
Both are measured.

## 2. Rules, fixed now (primary cell)

Bars: **2-minute**, built from 1-minute RTH bars (09:30–16:00 ET).
Indicators run continuously across days (as on a chart): Wilder ATR(20),
SMA(20), SMA(200).

**Sharp down move (long setup)** at bar t: bar t's low is the lowest low of
the last N = 10 bars; H = highest high of those 10 bars and it printed on an
earlier bar than t; move M = H − L ≥ K × ATR(20) as of bar t−1, K = 3.
Short setup is the exact mirror.

**Armed** from that bar. While armed: a lower low updates L (H stays, M grows);
the setup expires 5 bars after the latest low bar, or on a new 10-bar high.

**Trigger — "green eliminates red":** a green bar (close > open) whose close is
≥ the open of the most recent red bar. Entry at the **next bar's open**.
No new entries after 15:30. One position at a time per symbol.

**Target** = L + 0.25 × M (limit; fills only if the high trades ≥ 1 tick through it).
**Stop** = L − 1 tick; fills at min(stop, bar open) − 1 tick of slippage.
**Time exit** at the close of the 15:58 bar. Stop and target in the same bar
→ counted as the stop.
If the entry open is already at/above the target → no trade, counted as
"already there".

**Size:** fixed risk $110 (0.5% of $22,129) ÷ (entry − stop), notional capped
at 4 × $22,129.
**Costs:** IBKR Fixed $0.005/share, $1.00 minimum per order, both sides.
SPY: plus the slippage in the stop rule and 1 cent on entry.
Small caps: plus the measured live friction $0.0426/share per round trip
(`common/friction.py`, H-R1).

## 3. Data and holdouts

- **Primary: SPY** 1-minute, `bar_cache_spy/1min/SPY`, sessions
  2005-01-05 → **2024-05-08**. Sessions from 2024-05-09 are locked by
  `holdout_spy.json`. That file governs H-S1/H-S2 only, but they are left
  untouched here as well.
- **Secondary: small-cap momentum names**, `bar_cache_db/3d_to_2000`
  (Databento EQUS.MINI 1m, raw prices), the file's own date only, RTH only,
  sessions 2024-07-05 → **2026-01-09** (the `holdout.json` training window).
  Locked sessions are not read.

## 4. What counts as the claim holding

- **C1 holds** if, measured from the trigger with L frozen at that moment,
  the bounce (the highest high after the low bar, until a new low below L or
  the session ends) reaches 25% of M on **≥ 85%** of SPY setups.
  It is also reported frozen at the moment the move is first detected.
- **C2 holds** if the primary cell's SPY **net** P&L is > 0 on ≥ 200 trades,
  **and** it is positive in both halves of the window (split 2014-09-01).
- The small-cap result is reported beside SPY. It cannot rescue a SPY fail on
  its own, because it is a different universe with far higher friction.

## 5. Sensitivities — reported whatever they show, never promoted

K ∈ {2, 4}; N ∈ {5, 20}; trigger "close > the red bar's high"; 5-minute bars;
target ∈ {50%, 75%, 100%}; long only above / below SMA(200); 20-SMA slope
with/against the trade. Long and short are reported separately.
Seeing these is a search, not evidence (same rule as W11-0022/W11-0025).
If any of them looks good, it becomes its own registration.
