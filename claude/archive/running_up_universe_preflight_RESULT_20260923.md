# Running Up as a universe selector — Tier 1 preflight

2026-09-23. Descriptive preflight, no threshold, no P&L, no verdict on money — registered under `docs/research/REGISTERED_running_up_universe.md`. 550 sessions, 3,903 traded symbol-days, 44.9 seconds, 5/5 unit tests passed. Raw: `var/reports/running_up_universe_preflight.txt`, `var/reports/running_up_universe_features.csv`. Full monday Doc: W05-0006 item, "Tier 1 preflight RESULT".

## In plain terms

The original Running Up idea was closed as an entry filter (it kept more losing trades). This preflight tests the other half of Ben's idea — using it to decide which NAMES to watch, before any trade happens. The scanned universe has 6,411 symbol-days but only 3,903 were ever traded; the other 2,508 have no price data saved, so this pass only covers the 3,903 that traded (Tier 1). On those: 85.3% of symbol-days had at least one bar of history before the first trade that day, so there was room for an alert to have fired first — much better than feared. At a moderate cut on the proxy signal (`ret_5m`), an alert could have covered about 43% of all traded symbol-days with roughly 11 minutes of warning before the first trade; a looser cut covers about 77% with roughly 19–20 minutes of warning.

## Table

| cut (proxy ret_5m) | coverage of eligible names | coverage of ALL traded symbol-days (ceiling) | median lead time |
|---|---:|---:|---:|
| 0.045 | 90.0% | 76.8% | 19.5 min |
| 0.067 | 80.0% | 68.3% | 17.0 min |
| 0.089 | 70.0% | 59.7% | 15.0 min |
| 0.117 | 60.0% | 51.2% | 13.0 min |
| 0.148 | 50.0% | 42.7% | 11.0 min |
| 0.188 | 40.0% | 34.2% | 8.0 min |
| 0.243 | 30.0% | 25.6% | 6.0 min |
| 0.336 | 20.0% | 17.1% | 5.0 min |
| 0.542 | 10.0% | 8.6% | 4.0 min |

Pre-entry bar count (n=3,903): p10 = 0, p25 = 8, p50 = 37, p75 = 86, p90 = 144 bars. 572 symbol-days (14.7%) had zero pre-entry bars — bought on sight, no alert possible there whatever the threshold.

## What this reopens, and caveats

Does not reopen the closed entry gate (`running_up_preflight_RESULT_20260918.md` stands). Restricted to the traded population — the 2,508 scanned-but-never-traded symbol-days are untested (Tier 2, priced pull, not run). Proxy is `ret_5m` only; `rvol_5m` deferred. 1-minute bars approximate a tick-based scanner. Same selection-bias caveat as every `bar_cache` study.

## Next

W05-0019 opened: register and run the Tier-1 SCORED study (drop whole symbol-days on the proxy, read on `gate_study`'s five criteria) before any of this is scored as money.
