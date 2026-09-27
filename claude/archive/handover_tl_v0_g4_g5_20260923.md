# Handover — TL-v0 gates G4 + G5 built (2026-09-23)

**From:** Futures Trading Viability Analysis chat · **Board:** W01-0011 (Done), parent W01-0002.

## What happened

Ben reported a handful of manually profitable CL paper trades on NinjaTrader (~$16,000) and
asked to continue testing. Decision (Ben's choice, asked directly): keep the manual trades
separate — an informal note only, not evidence — and continue TL-v0 exactly as gated in
`docs/research/REGISTERED_tl_v0.md`. Nothing about the registered spec changed.

Checked where TL-v0's five pre-run gates (§0) actually stood:

- **G1** (pre-flight) — done, 2026-09-20.
- **G2** (TSMOM training-side result exists) — satisfied. W06-0005 closed 2026-09-23
  (NOT CARRIED FORWARD, 6/9), but the result *exists*, which is all G2 required; its own
  Result doc explicitly names W01-0002 as free to proceed on its own.
- **G3** (Python↔Pine parity) — built and synthetic-tested (2026-09-20, W01-0006), still
  **Waiting on Ben** for the real-archive pytest/pre-flight run.
- **G4 / G5** — not yet built. Opened and built this session as **W01-0011**.

## What was built (W01-0011)

- `common/tl_v0_holdout.py` — TL-v0's own holdout enforcement, mirroring
  `common/tsmom_holdout.py`'s pattern but **not reusing its ledger** (see the module's own
  docstring for why: two separate registrations must never share one spend record). Locked
  from 2022-01-01 (same date as TSMOM, matches `TRAIN_END` in `tl_v0_preflight.py`). Refuses
  `--limit` and every narrowing flag. Refuses the equity and TSMOM holdout files by name.
  Stricter than TSMOM's version per REGISTERED_tl_v0.md §6 ("Spent once, by v0-rev only"):
  every candidate name except the literal `"v0-rev"` is refused outright, before any ledger
  is even consulted — `v0` cannot spend it at all (§4).
- `tests/common/test_tl_v0_holdout.py` — 16 tests covering the above, written so that
  breaking the enforcement breaks a test (mutation-checked by hand, not by a mutmut run —
  this repo has no mutmut tool; it mutation-tests by writing the specific bug scenario as a
  test, same convention as `tests/strategy/test_tsmom_holdout.py`).
- `tests/test_tl_v0_hindsight_guard.py` — 4 tests for G5. No new production code: proved
  that `find_pivots()`/`walk_line_and_breaks()` in `common/tl_v0_lines.py` already only arm a
  pivot pair on its confirm bar (`pivot_idx + R`), with a synthetic two-pivot case showing no
  line exists one bar before the second pivot confirms — and, the literal mutation check
  §0's G5 row asks for, that shifting a pivot's confirm bar one bar early (simulating an
  off-by-one bug) is shown to leak a line at that bar, proving the "no line before confirm"
  assertion is actually sensitive to the bug class, not vacuous.

All 39 tests (the two new files plus the adjacent `tl_v0_lines` and `tsmom_holdout` suites,
run together) pass, no regressions, verified with a Linux Python + pytest in the cloud
container against the live mounted repo (Ben's own Windows `.venv` cannot be executed from
there, so this was a logic check, not the authoritative run — that's Ben's command below).

Files were written directly into Ben's live `D:\Trading` working tree via the device bridge
(git status showed them untracked, no conflicts) — not delivered as a bundle, so there is no
merge step, only a commit.

## Next steps (board)

1. **Ben, on W01-0011:** run the verification + commit commands (posted on the item):
   ```
   Set-Location D:\Trading
   .\.venv\Scripts\python.exe -m pytest tests\common\test_tl_v0_holdout.py tests\test_tl_v0_hindsight_guard.py tests\test_tl_v0_lines.py tests\strategy\test_tsmom_holdout.py -v
   git add common\tl_v0_holdout.py tests\common\test_tl_v0_holdout.py tests\test_tl_v0_hindsight_guard.py
   git commit -m "tl_v0: G4 holdout enforcement + G5 hindsight-guard tests (W01-0011)"
   ```
2. **Ben, on W01-0006 (still open):** the real-archive G3 run — pytest plus the pre-flight
   against the real Databento archive (commands already posted there). This is the only
   remaining gate.
3. Once G3 clears: all five gates (G1–G5) are satisfied and the step-4 TL-v0/v0-rev backtest
   (REGISTERED_tl_v0.md §3–§4) can be built.

## Source files

`common/tl_v0_holdout.py`, `tests/common/test_tl_v0_holdout.py`,
`tests/test_tl_v0_hindsight_guard.py`, `docs/research/REGISTERED_tl_v0.md` §0 (G4, G5),
`common/tsmom_holdout.py` (the pattern this follows).
