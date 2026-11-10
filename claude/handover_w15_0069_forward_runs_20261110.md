# Handover: W15-0069, weekly forward-test runs fixed (code built and tested; Ben runs, commits, schedules)

**Date:** 2026-11-10 · **Chat:** Build & test chat (Sonnet / Medium) · **Board:** W15-0069 (subitems 1-5), decision W15-0070
**Registrations:** `REGISTERED_w16_dvp_forward.md` Amendment 3 and `REGISTERED_chartmark_v2_forward.md` Amendment 2 (both POST-RUN; no rule, date or pass bar changed).

## Cause (confirmed from `w16_0014_weekly_log.txt`)
The W16-0014 task fires Saturday 08:00 Sydney = Friday 21:00 UTC. Databento's dataset end is about 8 hours behind (13:0x Z on every failed run), so Friday's UTC day is not complete. The scorer priced it anyway, was refused (`data_end_after_available_end`), retried capped, and was refused again (`data_schema_not_fully_available` on ohlcv-1d): aborted on 10-10, 10-17, 10-31 and 11-07 (the 10-25 run never finished). The W15-0037 scorer already defers unfinished days (its Amendment 1, item 2); its problem is that no scheduled task exists, so no run has happened since 2026-09-30.

## What was built (all under D:\Trading, uncommitted until Ben runs the commit block)
- `common/forward_spend.py` - one shared monthly ledger `Claude outputs\forward_spend.json`: US$5 per UTC calendar month for both tests. `check` refuses a confirmed pull that would pass the cap and logs it; `record` adds what was bought; Databento access errors (401/403/licence/subscription) are also refusals.
- `strategy/w16/dvp_forward.py` - `plan()` defers any UTC day whose end is past the dataset end (never priced, never bought partial, still due next run); a mid-run `data_end_after_available_end` also defers; cap check before download; spend recorded after.
- `strategy/chartmark_v2/forward.py` - same cap check, record and access handling (deferral was already there).
- Both scorers' `main()` return **exit code 4** on a refusal; both scheduled wrappers write "STOP AND ASK BEN" plus the refusal text to their weekly log.
- `common/forward_price_check.py` - sub 1: prices (never buys) one day of CL.c.0 1H, NQ.v.0 1m and 1d, writes `Claude outputs\w15_0069_price_check_<date>.txt`.
- `tests/conftest.py` - every test gets its own empty spend ledger (the first test run polluted the real one; reset to empty, guard added).
- Tests: 17 new in `tests/common`, 13 in the two scorers' suites. `tests/strategy/w16`, `tests/strategy/chartmark_v2` and the two new common test files: 492 passed (Linux, Python 3.10).

## Limits and risks
- Not run against real Databento: the price check, the catch-up and the first `chartmark_v2.forward --confirm` (its regression gate needs `E:\Databento` and `Claude outputs\w15_0032_cl1_1h_bars_indicators.csv`) are first-run tests on Ben's PC.
- Spend recorded after a partial download is pro-rated by files bought (get_cost is per request, not per file).
- The existing W16-0014 task's name and action are unknown to Claude; step 5a lists them before anything is changed (it may be a wrapper that sets the Databento key).
- A Saturday 14:00 Sydney run would still defer (dataset end lags about 8 h): use Sunday 10:00 Sydney (Saturday 23:00 UTC) or later. A deferred day is never lost.
- Do not `git add -A`: other sessions have uncommitted work in the repo (desk, wick_rev, futbt/holdout, NAS docs).

## Next (board)
- **W15-0069 sub 1** (Ben): run tests, then the price-only check; report the RESULT line.
- **sub 4** (Ben, then Build & test chat Haiku/Low reads the reports): catch-up estimate for both scorers, then `--confirm` if the total fits the cap.
- **sub 5** (Ben): 5a discovery of existing tasks, 5b register or re-time both weekly tasks (Claude posts 5b after reading the 5a report).
- Subs 2 and 3: built and tested here; commit with sub 1's block.
