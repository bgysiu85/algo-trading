# MA-TREND gate 2.1 — interior-peak pre-check: NONE FOUND → STOP (2026-09-17)

Reading only; no new run, no new data. Source: `var/reports/entry_split_mcl.txt`
(2026-09-14), definitions from `common/entry_features.py` (trend family =
`vwap_dist`, `ma20_dist`, `ma20_slope`, line 173). Raw report:
`D:\Trading\Claude outputs\ma_trend_precheck_20260917.txt`.

## Table (MCL, 551 sessions, 3,955 trades, quartiles; P/L at $4.26)

| feature | line | Q1 | Q2 | Q3 | Q4 | shape |
|---|---|---|---|---|---|---|
| ma20_slope | rate | 36.3% | 32.4% | 24.7% | 23.6% | monotone both halves |
| | P/L | (9.95) | (11.16) | (11.82) | **(9.13)** | **interior TROUGH** |
| ma20_dist | rate | 38.1% | 32.2% | 24.9% | 21.8% | monotone both halves |
| | P/L | (10.85) | (10.41) | (11.89) | **(8.93)** | best at edge |
| vwap_dist | rate | 28.9% | 34.1% | 29.4% | 24.5% | Q2 bump, unconfirmed |
| | P/L | (10.16) | **(9.82)** | (11.86) | (10.22) | Q2 by $0.34 |
| extension | rate | 32.0% | 31.1% | 27.4% | 26.4% | monotone-ish |
| | P/L | (10.82) | (11.30) | (11.90) | **(8.05)** | interior trough |

## Verdict

**No interior peak in either MA-TREND premise feature, on rate or money.**
`ma20_slope`'s money is U-shaped — middle worst, the inverse of the premise.
The lone bump (`vwap_dist` Q2) is not an MA-TREND component, is $0.34/trade, and
interior bumps occur on 5/22 features' rate lines (noise would give ~11).
Per spec §3.2/§10.1 and the build brief §2.1: **STOP. Nothing further built.**

## Limits (must survive into any citation)

1. Quantity mismatch: `ma20_slope` = raw % over 3 bars; spec `slope20_n` = 5 bars
   ÷ per-bar sigma. Raw slope on $2–20 names is largely a volatility proxy.
2. Population mismatch: MCL pre-market momentum entries, not RTH retracements.
3. Quartiles, not quintiles.

## Only legitimate re-entry

A **registered** quintile profile of `slope20_n` / `ext_n` on RTH bars, which
requires gate 2.2 (08:00 interleaved-price defect) and 2.3 (full-day ohlcv-1m).
Those have other consumers (`entry_place` `ema200_dist`, ORB RVOL). If done for
them, the profile is cheap; MA-TREND alone does not justify them.
