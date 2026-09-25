# W15-0005 — HTF-Ben v0 fidelity check — RESULT (2026-09-25)

REGISTERED_htf_ben_v0.md sec 6.1. Reported, not a gate: no P&L, no holdout spend.

## In plain terms

Ben's own NinjaTrader paper trades (11 completed CL round trips, 2026-09-20
→ 09-23, pulled live via the Ninja Trader connector) were checked against
what the coded v0 rules (MACD cross + EMA confirmation + daily filter) would
have done on the same 4-hour chart, at the same time. For the 9 trades that
fall inside the archive's current data coverage, **v0's coded rules never
triggered at all** — not on the wrong side, not on an adjacent bar: zero
qualifying entries anywhere near any of the 9. The other 2 trades (Sep 23
evening and Sep 24) sit right at or past the edge of the archive's current
coverage and can't be judged either way.

## Verdict / what this means

This is a real, data-backed finding, not a coverage artifact (confirmed
directly against the archive: 19 four-hour bars actually cover the window).
It lines up with two things already on the board — W15-0004's outright
training-side rejection of v0 (0/9 criteria), and W15-0008's finding that
Ben's own trading criteria (spread narrowing, opposite-signal exits) diverge
from what got coded. Together they say the same thing three different ways:
**v0 as literally coded does not describe how Ben actually trades.**

**Nothing to decide here that isn't already in motion** — v1 (W15-0010) was
already registered from Ben's own answers and is the intended fix; it's
currently blocked on W15-0007 (the v0-TL variant, still owed to the v0
registration regardless of this result). This result is one more data point
for whichever of those Ben wants to prioritize.

## Coverage table

| trade | Ben's entry (UTC) | side | in archive coverage | v0 signal found |
|---|---|---|---|---|
| 1 | 2026-09-20 23:30:07 | long | yes | **no** |
| 2 | 2026-09-21 12:08:53 | short | yes | **no** |
| 3 | 2026-09-22 07:57:06 | short | yes | **no** |
| 4 | 2026-09-22 09:52:22 | short | yes | **no** |
| 5 | 2026-09-22 13:35:01 | short | yes | **no** |
| 6 | 2026-09-22 14:21:22 | long | yes | **no** |
| 7 | 2026-09-22 14:24:32 | short | yes | **no** |
| 8 | 2026-09-23 13:25:50 | long | yes | **no** |
| 9 | 2026-09-23 13:27:10 | long | yes | **no** |
| 10 | 2026-09-23 22:01:52 | long | at the data edge | inconclusive |
| 11 | 2026-09-24 13:35:04 | long | past the data edge | inconclusive |

## Method

Scenario B (4-hour, multi-day — Ben's own method, held overnight).
`strategy/htf/fidelity.py` (commit `0ee843e`) reuses `preflight.detect_v0`
(the same E1–E3/S1 chain W15-0004's G2 already tested) over the whole
back-adjusted 4H series, keeps only entries whose fill bar falls in
2026-09-19→26, and matches each of Ben's trades by side + same/adjacent
4-hour bar. `n_entry_bars_in_window` (19) and a direct archive read both
confirm real coverage, not a vacuous window. No exit price, no P&L,
anywhere in the module.

## Caveats

- Trades 10 and 11 are unjudged, not "failed" — the archive (pulled
  2026-09-25 as part of W15-0002) ends 2026-09-23 23:00 UTC. A fresh pull
  would let them be checked too (separate ask; the fetcher is idempotent).
- 9 trades is a small sample — this is a fidelity spot-check, not a
  statistical test, and was never meant to be one (sec 6.1 explicitly
  computes no P&L and spends no holdout).
- Trade 1 was a 4-second, 1-lot scratch (entered and exited within 5
  seconds) — included for completeness, doesn't change the reading.

## Source files

- `claude/raw/w15_0005_ninjatrader_trades_20260925.json` — Ben's trade list
- `strategy/htf/fidelity.py`, `tests/strategy/htf/test_fidelity.py` — the check
- `Claude outputs\w15_0005_fidelity_20260925.json` — Ben's run output
- `Claude outputs\w15_0005_fidelity_RESULT_20260925.txt` — raw report
