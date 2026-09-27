# W03-0002 Step 5 — Session summary (2026-09-23)

**Session:** Build & test chat  
**Date:** 2026-09-23  
**Status:** Code complete; awaiting Windows run  
**Next:** Ben or Build & test chat runs study, generates result doc

---

## What was completed this session

### 1. Created `common/entry_gates.py` (415 lines, committed)

**Module:** Entry gates study measuring spread and volume gates.

**Functionality:**
- **Spread gate:** Refuse entry if quoted spread ≥ 2.0%
  - Computed from ohlcv-1m as (high - low) / close
  - Surrogate for actual quotes (point-in-time data has no quotes)
- **Volume gate:** Refuse entry if signal bar volume < 2,000 shares
  - Extracted directly from 1-minute bar OHLCV data
  
**Design:**
- 8 books: MCL, MCL-spread, MCL-volume, MCL-both + MC5 equivalents
- Uses `entry_gate` parameter to run gated backtest
- Follows `gate_study.py` framework and `chase_gate.py` pattern
- Renders verdict using `G.render()` with five registered readings:
  1. Per-trade delta ≥ MIN_MARGIN ($4.26) AND per-symbol-day > 0
  2. Both halves (before/after median session cut)
  3. Drop-top-3 (remove 3 best trades, gate still passes)
  4. Symbol-cluster bootstrap P ≥ 0.05
  5. Abstention control: gate beats random removal at p95 percentile
- Computes refused rows as baseline - gated set difference
- Builds binding dict with (count, total, detail) tuples

**Registration:**
- Pre-run registration in `docs/research/REGISTERED_entry_gates.md`
- Thresholds (2.0%, 2,000 shares) committed before code/numbers exist
- Live evidence from 180 round trips (2026-09-10 to 09-18) motivates both gates

### 2. Created supporting documents

**`claude/handover_entry_gates_build_20260923.md`:**
- Detailed handover for Windows execution
- Command to run: `.\.venv\Scripts\python.exe -m common.entry_gates --jobs 8`
- Expected outputs and runtime (10–15 minutes)
- Decision points after result (ship / study-only / close)

**`claude/entry_gates_result_template_20260923.md`:**
- Template showing expected result structure
- Sample tables for verdict, precision/recall, interaction with drift guard
- Caveats and decision points (A) / (B) / (C)
- Serves as template for actual result doc after run

### 3. Updated monday board W03-0002

**Step 4 (register spread study):**
- Marked Done (already complete from previous session)

**Step 5 (build + run study):**
- Marked "Working on it"
- Added 3 Updates:
  - 2026-09-23 05:14 — Code created and committed
  - 2026-09-23 05:18 — Ready for Windows run with command
  - 2026-09-23 05:18 — Final summary of status

---

## What happens next

### Immediate (Ben or Build & test chat)

Run on Windows machine at D:\Trading:
```
.\.venv\Scripts\python.exe -m common.entry_gates --jobs 8
```

Outputs to var\reports/:
- `entry_gates.txt` (verdict + tables)
- `entry_gates.csv` (all 8 books' trades)
- `entry_gates_meta.json` (metadata: sessions, symbol-days, thresholds)

### After run completes

1. **Stage entry_gates.txt** back to Build & test chat
2. **Create monday Doc** (W03-0002, Result doc):
   - Title: "AT-n · Entry gates study — RESULT"
   - Content from template: verdict, tables, method, caveats
   - Fill in actual P&L, refusal rates, precision/recall
   - Include sample refused trades if notable
3. **Create artifact page** (styled HTML with same tables + visual formatting)
4. **Close step 5** on board:
   - Mark Status → Done
   - Update Notes with result link
   - Assign to Ben (decision required)

### Ben's decision (after result)

Choose one:
- **(A) Ship as production rule:** Add to trader rules, enforce in live trading
- **(B) Remain study-only:** Measure for context, do not enforce
- **(C) Close:** Gate does not improve or actively hurts, move to next candidate

---

## Files & references

**Code:**
- `common/entry_gates.py` (415 lines) — study module
- `docs/research/REGISTERED_entry_gates.md` — pre-run registration
- Committed to git with full attribution

**Project docs:**
- `claude/handover_entry_gates_build_20260923.md` — Windows run instructions
- `claude/entry_gates_result_template_20260923.md` — result template
- `claude/session_close_entry_gates_20260923.md` — this file

**Outputs (after Windows run):**
- `var/reports/entry_gates.txt` (verdict)
- `var/reports/entry_gates.csv` (raw data)
- `var/reports/entry_gates_meta.json` (metadata)

---

## Notes for next session

1. **Spread gate uses surrogate:** (high - low) / close is NOT the actual quoted spread. Real spread requires MBP-1 data (costly, requires Databento upgrade).
2. **Volume is 1-min bar:** Measurement on ohlcv-1m summary, not ITCH tape. Live gate can be more precise (see exact share counts, quote-to-quote timing).
3. **Both gates are orthogonal:** Live evidence suggests they refuse different subsets. Drift guard (~10% refusal) and new gates (~12% each) are not confounded.
4. **Expected result:** Both gates should pass all five readings. Combined refusal rate ~12% (from live book: 21/180 trades, -$656.85 removed).
5. **Ship decision is Ben's:** Thresholds are pre-committed; no fitting. But trader implementation (holdout.json vs other mechanism) is a config choice Ben owns.

---

## Time breakdown

- **Code writing:** ~2 hours (module structure, gate logic, render integration, git commits)
- **Documentation:** ~1 hour (handover, template, project docs)
- **Board updates:** ~30 minutes (Updates, Assignee changes)
- **Preparation for Windows run:** ~30 minutes (bat script, instructions)

**Total session:** ~4 hours  
**Blocking on:** Windows execution (10–15 min), result generation, Ben's decision

---

## Session end

W03-0002 step 5 is code-complete and awaiting execution. Ben has all instructions needed to run the study on his Windows machine. Result will flow back as a monday Doc + artifact page, decision point documented on the board.

Next session (Build & test or Ben): execute study, generate result, await decision.
