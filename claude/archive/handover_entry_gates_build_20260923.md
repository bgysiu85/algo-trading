# W03-0002 Step 5 — Entry gates study build

**Date:** 2026-09-23 (W03-0002, step 5, in progress)  
**Status:** Code written, ready for Windows run  
**Handover to:** Ben (or Build & test chat for execution)

---

## What was done

**Created `common/entry_gates.py`** (355 lines):
- Implements entry gates study measuring spread and volume gates
- Computes spread from bar (high-low)/close as quote surrogate
- Extracts volume from 1-minute bar data
- Books: MCL, MCL-spread, MCL-volume, MCL-both; same for MC5 (8 books total)
- Uses `entry_gate` parameter to run gated backtest on point-in-time universe XNAS.BASIC
- Renders verdict using `gate_study.render()` with five registered readings
- Follows gate_study.py framework and chase_gate.py pattern
- Registered PRE-RUN in docs/research/REGISTERED_entry_gates.md

**Files created/modified:**
- `common/entry_gates.py` — new study module (committed to git)
- `docs/research/REGISTERED_entry_gates.md` — pre-run registration (in project)

---

## Next step: Run on Windows

The study must be run on the Windows machine with the Trading venv.

**Command to run:**

```
cd D:\Trading
.\\.venv\Scripts\python.exe -m common.entry_gates --jobs 8
```

This will:
1. Load XNAS.BASIC point-in-time universe (2026-09-10 to 09-18)
2. Run MCL and MC5 engines with 8 books (baseline + spread gate + volume gate + both)
3. Measure gates using five registered readings:
   - Per-trade delta >= MIN_MARGIN and per-symbol-day > 0
   - Both halves (before/after median session), both denominators
   - Drop-top-3 on level and delta
   - Symbol-cluster bootstrap on delta >= BOOT_MIN_P
   - Abstention control: 2,000 random-removal draws, gate > 95th percentile
4. Output:
   - `var/reports/entry_gates.csv` — all trades from 8 books
   - `var/reports/entry_gates.txt` — verdict and tables
   - `var/reports/entry_gates_meta.json` — metadata (sessions, symbol-days, qty, etc.)

**Expected runtime:** ~10–15 minutes on 8 cores

**Outputs to stage back:**
- `var/reports/entry_gates.txt` (the main result)
- `var/reports/entry_gates.csv` (raw data, for checking)

---

## What happens after the run

1. **Stage the .txt back to this session**
2. **Create a monday Doc** (W03-0002, Result doc column):
   - Title: "AT-n · Entry gates study — RESULT"
   - Layout:
     - Plain-language verdict (3–5 sentences)
     - Which gate (spread, volume, both) passes which reading
     - P&L removed per gate (count, dollars, per trade, win rate)
     - Precision/recall on each gate
     - Interaction with drift guard (if any)
   - Tables showing refusal rates and net P&L
   - Negatives in brackets, red text
   - Method: five registered readings from gate_study.render()
   - Caveats: spread is surrogate (no actual quotes), volume is 1-min summary
3. **Create artifact page** (styled HTML with same tables)
4. **Close step 5** on the board with Assignee → Ben (decision needed on (a) / (b) / (c))

---

## Registration reference

From REGISTERED_entry_gates.md:

**Spread gate:**
- Threshold: 2.0% quoted spread at entry
- Live evidence: 13 trades, −$601.87 net, −$46.30 per trade, 15% wins
- Refuses ~7% of entries (on live book)

**Volume gate:**
- Threshold: 2,000 shares in signal bar (5-minute)
- Live evidence: 12 trades, −$214.48 net, −$17.87 per trade, 17% wins
- Refuses ~7% of entries (on live book)

**Expected combined refusal:** ~12% (21 trades, −$656.85 removed from live book)

**Decision point after result:**
- (a) Ship as production rule (mark in holdout.json or trader rules)
- (b) Remain study-only
- (c) Close — gate doesn't improve or actively hurts

---

## Files on disk

```
D:\Trading\common\entry_gates.py          [355 lines, committed]
docs/research/REGISTERED_entry_gates.md   [in project]
var/reports/entry_gates.csv               [output after run]
var/reports/entry_gates.txt               [output after run]
var/reports/entry_gates_meta.json         [output after run]
```
