# Handover — the ORB build, as it stands

From: the strategy build and test chat (this one is moving to the luck-vs-edge / first-entry handover).
To: the new chat dedicated to ORB.
Written 2026-09-17 (Sydney). Everything below is on `main` in `D:\Trading` at `c1b3888` or earlier. Nothing ORB-related is in `D:\TradingProd`, and nothing should be.

**Read in this order:** `claude/orb_strategy_spec.md` (the spec, with the 2026-09-07 corrections), `claude/orb_preflight_RESULT_20260916.md` (the grid that eliminated `opposite` and found the length × stop coupling), `docs/research/REGISTERED_orb_grid.md` in the repo (registration, amendments A, B pre-run and C post-run), `claude/orb_first_results.md` (the one XNAS.BASIC run), `claude/PROGRAM_INDEX.md` §2 and §7 items 2–5. Then this.

---

## 1. Where it is, in one paragraph

ORB is built, tested, registered, and has run once on the registered tape. On the stage-2-survivor universe (27,758 symbol-days, XNAS.BASIC) the baseline cell — `ORB_MINUTES 15 · STOP structure · RETEST none · EXIT r_2`, flat 100 shares, §9 fills, IBKR Tiered — clears §11 criteria 1 through 6: **+$3.33/trade over 4,875 trades, drop-top-5 +$13,571, halves +$7,050 / +$9,168, cluster bootstrap 1.000.** Criterion 7 (no optimum on a grid boundary) is **not met** and needs the box pushed to 45 minutes. **And every one of those numbers is on the universe that gave H0 +$4.72 before the point-in-time run gave −$15.78.** The first thing the ORB chat does is register and run the PIT universe; until then nothing in `orb_first_results.md` §1 is believed. That is not caution for its own sake — the leak measurement in §5 of that doc cannot separate a real edge from stage-2 look-ahead, and the spec said ORB's exposure to that leak is larger than a pre-market strategy's.

---

## 2. What exists in the repo

| file | what | tests |
|---|---|---|
| `strategy/orb/orb.py` (690 lines) | the strategy: `Config` (frozen, validates modes, `orb_minutes % trigger_bar_minutes == 0`, `entry_on_close=False` requires retest `none`), `BASELINE`, `Trade`, `SessionResult` (`has_open_bar`, `passes_rth_screen`), `Bars` list view, `trigger_bars`, `opening_range`, `buy_fill`/`sell_fill`, `backtest_session(sess, symbol, day, cfg, bars=None)`, `_resolve_entry`, `_run_position`, `_close` | `tests/strategy/test_orb_state_machine.py` — 44, on hand-built bars, every trap in spec §14 step 8 |
| `strategy/orb/grid.py` (677 lines) | the runner: `GRID_MINUTES=(5,15,30)`, `GRID_STOPS=("structure","rangefrac")`, retest × exit families, `MIN_TRADES=100`, `Cell` accumulator (`add`/`merge`, `by_symbol_day`, per-symbol lists for the bootstrap), `run_chunk`, `_rth_screen`, `read()`, `deltas()` (refuses when per-trade and per-symbol-day deltas disagree in sign), `render`, `provenance`, `tape_check`, CLI | `tests/strategy/test_orb_grid.py` — 27 |
| `strategy/orb/preflight.py` (729 lines) | the pre-P/L grid: usable ranges, trigger rates, R distribution per stop, leak cut, `load_bars(cache, symbol, day)`, `rth_session`, `cache_tape` | `tests/strategy/test_orb_preflight.py` |
| `docs/research/REGISTERED_orb_grid.md` | registration §1–§7, amendments A/B (PRE-RUN), C (POST-RUN) | ordering asserted against git by the breadth test pattern |
| `var/reports/orb_grid.txt`, `orb_grid_cells.csv` | the XNAS run's raw output (on Ben's machine, not in git) | |

Constants that are decisions, not defaults: `ZONE_LO, ZONE_HI = 0.38, 0.62` (V4's retest zone); `LAST_ENTRY = FLATTEN_BAR = 15:55`; `SLIPPAGE_TICKS = 1`; `COMMISSION_PLAN = "ibkr_tiered"`; `MAX_ENTRIES_PER_SESSION = 1`; `opposite` stop excluded by the pre-set `MAX_R_PCT` (pre-flight, before any P/L).

Fill model, so it is not re-derived: entry at the next trigger bar's open + 1 tick; stops gap through, targets do not; a bar holding both stop and target is the stop's; the peak for trailing starts at the fill; the structure anchor is the last bar that had **closed** when the order filled, not the bar in which it filled; a fixed stop is live in every exit mode. One resample per symbol-day, `Bars` as a list view — 90 cells run at about 76 ms per symbol-day.

The data lives on Ben's machine only: `bar_cache_xnas\3d_to_2000` (XNAS.BASIC, the registered tape, `SOURCE.txt` beside it) and `bar_cache_db\3d_to_2000` (EQUS.MINI — **not** the registered tape; the runner refuses it without `--anyway`). One file per symbol-day, `SYMBOL_YYYY-MM-DD.csv.gz`. This is not the Databento archive that the MCL PIT studies read, and the two are not interchangeable.

---

## 3. What the run found, beyond the seven criteria

- **`trail_pct` beat every fixed target at every length and both stops** (+$5.78 against `r_2`'s +$3.33 at 15 min). Registered prediction B held, but for the spec's §7.1 reason (fixed targets cap the runners this universe is screened to produce), not the reason I gave in the amendment. `r_1_5` did worse than `r_2`.
- **Retest hurts at the structure stop** (`required` +$1.37 against `none` +$3.33) and is roughly neutral at range-fraction. Hypothesis, not a result: the retest candle's low sits close to the reclaim, R is tiny, and 2R is inside noise. Checkable from an R-per-cell distribution the runner does not yet write. `zone`/structure at +$4.38 is a 478-trade lead and nothing more.
- **Length and stop are one question.** Baseline row read alone: 5 wins (4.74 / 3.33 / 2.28). Joint length × stop, `none` arm: 30 wins (rangefrac 6.60). Opposite edges — the pre-flight's predicted coupling, now measured. Amendment C.1 fixes what "wins" means: the joint reading, `none` arm only.
- **The 09:45 screen splits the survivors cleanly** — passes +$31,103 on 2,912 symbol-days, fails −$13,281 on 1,470 — on three of its four rules. The fourth, `relative_volume_10d_calc`, is not computable from a three-session cache, and `largecap_evidence_20260911.md` says that rule is where the outside literature's entire stocks-ORB edge lives. Registered in advance (§6) so criterion 6 cannot be quoted as a full pass. `bar_minute` (21.0M XNAS rows) may hold enough sessions to compute it as a query — unchecked.
- **Rejected symbol-days (the leak control)** trade half as often and lose −$1,604 on 493 days. Consistent with the screen finding real movers, and equally consistent with stage 2 manufacturing the survivors' edge. Undecidable from this cut.
- 63.8% of entries land 09:45–10:29 with a long thin tail; exits stop 52.6% / target 37.9% / session-end 9.6%; 79 bars held both stop and target and the stop won every one; zero positions open when bars ran out.

---

## 4. Defects recorded and not yet fixed (amendment C)

1. **`_boundary_block` reads across all readable cells including retest arms.** It must be narrowed to the `none` arm (C.1). Small change, test it can fail.
2. **`Cell` counts legs, not round trips.** `r_3_trim` books two legs per position, so its `trades` column is 6,722 on 4,875 symbol-days and its per-trade figure is per-leg. Count round trips in `Cell.add` (one per symbol-day under `MAX_ENTRIES_PER_SESSION = 1`), keep legs as a separate column (C.3). Until then `r_3_trim`'s per-trade column is not read — and the comparison-level refusal in `deltas()` is what caught it, so keep that refusal.
3. **45 minutes is not in `GRID_MINUTES`.** `(5, 15, 30, 45)` → 120 cells (C.2). `Config` already accepts 45 (45 % 5 == 0). 3 minutes is a hard edge of the design and is reported as such, not pushed.

Two provenance lessons that are now code and should stay code: the first full grid ran on EQUS.MINI because the runner recorded no tape — `tape_check` + the `WHAT THIS RUN MEASURED` block exist so that cannot recur; and a hash cited in prose is a second source of truth — the registration's "committed before the run" claim is the git ordering, never a quoted hash.

---

## 5. Next, in order — none of it is "ship"

1. **Register and run the point-in-time universe.** `var\state\screen_pairs_pit.json` (6,170 symbol-days, 551 sessions). Registration before the run, as a new `docs/research/REGISTERED_orb_pit.md` or an amendment D — say which criteria are re-read (all seven, baseline cell), that the split date is derived from the PIT symbol-days and not carried over from the survivor run, and what would make the run wrong. **Check first that `bar_cache_xnas\3d_to_2000` covers the PIT symbol-days** — it was built for the consolidated + rejects pairs, and the grid's behaviour on a missing cache file needs to be a counted skip, not a silent one. Expected wall clock: the survivor run was 296 s for 27,758 symbol-days at 90 cells on 8 jobs, so the PIT run at 120 cells is a few minutes.
2. **Push the box to 45** and read criterion 7 under C.1's definition of "wins". Do 1 and 2 in one run if the registration says so up front; do not read 2 before 1 is written.
3. **Fix the two runner defects** (§4 items 1 and 2) before that run, so the report it produces is readable without caveats.
4. **Close the §12 gaps** the first run did not produce: capital-based sizing via `compound_sim` and the price-decile table (the number that flipped MCL's sign); per-ticker table; per-exit-reason friction break-even; aggregate the downside break and the V2 fade that `orb.py` already measures per symbol-day; R as % of price per cell.
5. **Only if 1 and 2 both hold:** the paper-trading question. ORB has no `strategy_adapter`, the trader has never placed an RTH order, and RTH permits a native stop that the backtest deliberately does not model (spec §6). That is a build of its own, and it starts with the live gate sharing code with the backtest the way `mcl.in_session_mask` does.

---

## 6. How to run it (Ben's machine, from `D:\Trading`)

The survivor run, as it was run:

```
python -m strategy.orb.grid --pairs var\state\screen_pairs_consolidated.json var\state\screen_rejects.json --cache bar_cache_xnas --jobs 8
```

The PIT run will be the same shape with `--pairs var\state\screen_pairs_pit.json` and `--out` / `--csv` pointing at new names so the survivor report is not overwritten. Flags: `--pairs` (one or more), `--cache` (root; `--window 3d_to_2000` default), `--jobs`, `--limit`, `--out`, `--csv`, `--expect-tape XNAS.BASIC` (default), `--anyway` (only for a deliberately off-tape run, and the report then says so in capitals).

Tests: `python -m pytest tests/strategy/test_orb_state_machine.py tests/strategy/test_orb_grid.py tests/strategy/test_orb_preflight.py -q`.

---

## 7. Rules of the house that bite here

- Register before you run. Amendments marked PRE-RUN or POST-RUN. A threshold changed after seeing a result is a new hypothesis.
- The tape is named in every report or the report cannot be reconciled. Refuse rather than warn.
- Two denominators (per trade, per symbol-day) are reported and a sign disagreement between their deltas is a refusal, not a tie to break.
- Drop-top-N and the halves are on the level and on every delta. The split date is derived once from the data run and never swept.
- `var/state/holdout.json` is unspent and stays shut until something passes everything on the PIT set.
- Mutation-test before commit; a guard that cannot fire is removed, not kept as reassurance.
- One branch, `main`. Two (now three) chats write to one repo: cut bundles only on a base containing Ben's current tip, deliver to `D:\Trading\Claude outputs`, and prefix bundle names by chat — suggest `orb-YYYYMMDD[a-z].bundle` so they cannot collide with this chat's `YYYYMMDD[a-z]` series or the analysis chat's `trf-probe-`/`tape-spikes-` series.
- All text-mode opens name `encoding="utf-8"` — `tests/test_encoding_guard.py` refuses a bare one anywhere in the tree, and refuses a file whose parse raises a SyntaxWarning (a `\.` in a non-raw string). Ben's machine is cp1252; the cloud is UTF-8; the guard exists because a `§` in a report proved it.
- Results go to files, then to a published artifact page in addition to the raw `.txt`. Ben gets exact commands, one per line, paths under `Claude outputs`.

---

## 8. Ownership from here

The ORB chat owns `strategy/orb/`, `tests/strategy/test_orb_*.py`, `docs/research/REGISTERED_orb_grid.md` and its successors, and `claude/orb_*.md`. This chat will not touch them again. This chat is on `claude/handover_luck_vs_edge_and_entry_quality_20260917.md` (H-B1 first), in `common/` and `tests/common/`, and will keep `PROGRAM_INDEX` §7 items 2–5 as the ORB chat reports them — send the result doc names and I will index them.
