# Handover — W15-0037 sub 2: CHARTMARK-v2 F1 weekly forward scorer (the scored book)

**Date:** 2026-09-30 · **Chat:** Build & test chat (Sonnet / Medium) · **Board:** W15-0037 sub 2 (Working on it, Assignee Ben for the commit + first run), sub 4 and sub 5 unchanged
**Registration:** `docs/research/REGISTERED_chartmark_v2_forward.md` + **Amendment 1 (PRE-RUN)** added this session (scorer interpretations only; no rule, date or bar changed).
**Frozen engine:** commit f3872ff (`strategy/chartmark_v2/engine.py`, `spec.py` — byte-identical check passes on this checkout).

## What was built
- `strategy/chartmark_v2/forward.py` — `python -m strategy.chartmark_v2.forward` (estimate only) / `--confirm` (pull, score, append, report). K1, V-SESSION, V-WICKGATE on new CL 1H bars, ledger `forward_chartmark_v2.json` (repo root, commit after each run), report `Claude outputs\w15_0037_forward_<date>.txt/.json`.
- `strategy/chartmark_v2/forward_scheduled.py` — Task Scheduler wrapper (runs `--confirm`, commits + pushes the ledger only if it changed; log `Claude outputs\w15_0037_weekly_log.txt`). Same pattern as W16-0014.
- `strategy/chartmark_v2/ref_stepC_k1_trades.csv` — step C's 317 K1 trades, the regression-gate reference (copied from `w15_0036_v2_stepC_trades_20260930.csv`).
- `tests/strategy/chartmark_v2/test_forward.py` (28 tests) and `test_forward_scheduled.py`. Whole chartmark + chartmark_v2 suites: 169 passed here (Linux, Python 3.10).

## How it works (one paragraph)
Each run rebuilds the frame (warm-up + every forward day on disk), runs the frozen engine from the fixed first forward bar, and keeps only **closed** trades. Recorded trades must be reproduced exactly or the run refuses and leaves the ledger alone, so a scored session is never re-scored; scoring week by week gives the same trades as scoring once (tested). Gates, each a refusal: freeze (engine/spec = f3872ff), regression (step C's 317 K1 trades on 2016–2021 and the seen-window 69 trades / +2.29 pts reproduced — scoring runs only), read-back (hourly closes vs `ohlcv-1d` within 1 tick on ≥ 99% of days), contiguity (only the unbroken run of days on disk is scored). Stops A/B are evaluated trade by trade and latched per rule; a K1 stop writes `paper_orders = STOPPED` for the runner. Provisional F1–F7 and C1/C3 controls are printed every run and decide nothing.

## Not verified here — what the first real run tests
This sandbox has no Databento key and no access to `E:\Databento`, so these were tested with a fake client and synthetic CME-shaped bars only: the real pull and `read_dbn` of day files, the 1-tick read-back against real `ohlcv-1d`, the regression gate on the real 2010–2021 archive (the seen-window half does run here and passes), and the no-session-day detection (it relies on the same error text W16 uses). The first `--confirm` will show each. The regression gate also needs `Claude outputs\w15_0032_cl1_1h_bars_indicators.csv` (git-ignored) on whichever machine runs it, so it will not pass on the W10-0013 cloud server until that file is copied there.

## Decisions for the record (Amendment 1 lists all eight)
Warm-up is a separate Databento pull (sessions from 2026-06-01), not the archive, so the 2022–2025 holdout never enters a frame; open positions are never ledgered; C3 draws cannot overlap; the F7 extension to 2027-12-31 is not built (a POST-RUN amendment if a rule has < 50 trades on 2027-09-30).

## Next (board)
- **W15-0037 sub 2** — Ben: run the commands on the subitem (tests, commit + push, estimate). Then Done.
- **W15-0037 sub 3** — Ben: NYMEX data + share to paper + futures permission (unchanged).
- **W15-0037 sub 4** — Build & test chat, **Sonnet / High**: paper runner (§3.1), waits on sub 3 and the scorer. Needs `paper_orders` in the ledger and the scorer's trade rows to compare dry decisions.
- **W15-0037 sub 5** — Ben: weekly schedule (block on the subitem), then monthly check-ins (Live analysis chat, **Haiku / Low**) reading `w15_0037_forward_<date>.txt`; final read vs F1–F8 after 2027-09-30 → Result doc.
