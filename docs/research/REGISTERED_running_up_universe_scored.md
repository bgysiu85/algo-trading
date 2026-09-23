# REGISTERED — Running Up universe, Tier-1 SCORED: drop whole symbol-days

**W05-0019.** Written before `common/running_up_universe_gate.py` exists (repo at commit
`712d1a7`, the commit that registered the Tier-1 preflight) — no code, no run, no P&L computed
yet. Continues `docs/research/REGISTERED_running_up_universe.md` §4, opened off that
preflight's own result (`claude/running_up_universe_preflight_RESULT_20260923.md`, Done):
85.3% of traded symbol-days had pre-entry history; a moderate cut covers ~43% of all traded
symbol-days at ~11 minutes of lead time.

## 0. What this reopens, and what it does not

`REGISTERED_running_up_universe.md` (W05-0006) measured coverage and lead time only — no
threshold, no rule, no P&L. This document is the "later registration" its §4 named: it fixes
the rule and the reading BEFORE either the mask code or a scored run exists, so a threshold is
never picked with a P&L already in view.

## 1. The rule — a symbol-day MASK, not an entry gate

For each of the 3,903 traded symbol-days
(`var/reports/running_up_universe_features.csv`, W05-0006's own preflight output), the WHOLE
symbol-day is kept only if:

  - it had at least one pre-entry bar (`pre_bars > 0`), AND
  - its pre-entry PEAK of `ret_5m` (the proxy alert) cleared the cut.

A symbol-day failing either condition loses EVERY trade in it, in BOTH books — unlike the
closed entry gate (`running_up_preflight_RESULT_20260918.md`), which dropped individual rows
within a symbol-day. `peak_ret5m` is `NaN` exactly when `pre_bars == 0` (the preflight's own
convention), so no separate zero-bar case is needed: `NaN >= cut` is already `False`.

**No engine re-run.** The mask never changes which bar an entry fires on — it only removes
whole days — so the trades that survive a cut are bit-identical rows from the already-published
book, `var/reports/session_scenarios_trades.csv` (books `MCL` and `MC5`). The mask is applied
directly to that file; `E:\Databento` is not touched.

## 2. The cuts — the preflight's own nine deciles, none chosen after seeing a number

Registered here exactly as printed in `var/reports/running_up_universe_preflight.txt`
(2026-09-23), the deciles of `peak_ret5m` among the 3,331 eligible (`pre_bars > 0`)
symbol-days, computed BEFORE this document existed:

```
CUTS = 0.045, 0.067, 0.089, 0.117, 0.148, 0.188, 0.243, 0.336, 0.542
```

All nine are scored, for BOTH `MCL` and `MC5` — a sweep, the same shape `chase_gate.py`'s
`CEILS` took, not a single pick, so no cut is favoured after a first look at its P&L. The p50
cut (0.148, ~43% coverage of all traded symbol-days, ~11 min median lead) is the one the item's
own notes anticipated as "moderate"; it is scored on the same footing as the other eight, not
singled out.

## 3. What decides — `gate_study`'s five criteria (`REGISTERED_range_rank.md` §3, inherited)

For every `(book, cut)` pair, against that book's own unfiltered baseline:

  1. delta per trade >= $4.26 (one round-trip of friction) AND delta per symbol-day > 0; a
     sign disagreement between the two is a REFUSAL, not a partial pass.
  2. both halves (split at the median session), both denominators, > 0.
  3. drop-top-3 on the level and on the delta.
  4. the symbol-cluster bootstrap on the delta, P >= 0.95.
  5. the abstention control: the same number of trades removed from the baseline at random,
     2,000 seeded draws (SEED 20260916); the cut's per-trade delta must beat the draws' p95.

**Per-symbol-day denominator:** the scanned point-in-time universe, 6,411 symbol-days
(`var/state/screen_pairs_pit_itch_v2.json`), the SAME for `MCL` and `MC5` and for every cut —
disclosed in full in §5, because it is a proxy, not a fresh engine recount.

## 4. What this is not

  - **NOT a re-run of the engines.** The trades are the already-published book; only symbol-day
    MEMBERSHIP changes, never an entry price, exit, or reason.
  - **NOT Tier 2.** The 2,508 scanned-but-never-traded symbol-days are still untested
    (`REGISTERED_running_up_universe.md` §6).
  - **NOT `rvol_5m`.** The proxy is `ret_5m` alone, same as the preflight; the volume half of
    "climbing fast on a burst of volume" is still deferred.
  - **NOT a re-open of the closed entry gate.** `running_up_preflight_RESULT_20260918.md`
    stands; this is the universe-selector question, on a coarser (symbol-day) intervention.

## 5. Caveats disclosed BEFORE the run

  - **The symdays denominator is the scanned PIT universe count (6,411), not a fresh engine
    recount** — `E:\Databento` is not reachable from the environment that built this mask, so
    the exact count of symbol-days the ORIGINAL `session_scenarios_trades.csv` run processed
    successfully (which would be a handful below 6,411, for unreadable sessions) is not
    re-derived here. Using the scanned-universe count is the same choice the Tier-1 preflight
    already made and keeps one denominator common to every book and every cut; if it differs
    from a fresh engine recount, it is by at most the small number of sessions `gate_study`
    runs typically report as unreadable, and the per-symbol-day figures below should be read
    with that in mind, not as wrong.
  - **Descriptive population, not a fresh sample.** Same 550 sessions, same tape, same two
    books as every other 2026-09-23 study on this universe; `holdout.json` untouched.
  - **A cut with no eligible symbol-days below it removes nothing** — reported as "the gate
    never bound" per book, not silently skipped.

## 6. Commands

This mask is pure arithmetic over two already-written CSVs (`session_scenarios_trades.csv`,
`running_up_universe_features.csv`) — no Databento archive access, no PowerShell required to
run it. Reproducible from Ben's own machine as:

```
Set-Location D:\Trading
.\.venv\Scripts\python.exe -m pytest tests\common\test_running_up_universe_gate.py -v
.\.venv\Scripts\python.exe -m common.running_up_universe_gate
```

**What to report back:** the pytest pass/fail count, then
`var\reports\running_up_universe_gate.txt` (this is what the RESULT doc's tables come from).

## 7. Timeline

  1. **This document.**
  2. `common/running_up_universe_gate.py` + `tests/common/test_running_up_universe_gate.py`.
  3. Run; write the RESULT doc (in dollars, negatives bracketed, per book per cut).
  4. **Ben's decision**, only if at least one `(book, cut)` PASSES all five readings: study-only,
     close, or a second, independent registration — the same three-way choice
     `REGISTERED_dist_from_high.md` §6 laid out for its own gate.
