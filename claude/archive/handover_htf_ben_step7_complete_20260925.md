entity: Handover — HTF-Ben v0: step 7 (the whole backtest engine) is code-complete, 2026-09-25

**From:** Build & test chat · **To:** Build & test chat (next session) / Ben · **Workstream:** W15 - High-timeframe futures (1h–1d) · **Board item:** W15-0004 (id 2867153345), subitem "7. Exits + runner + full sec.3 report emission, score sec.4" (id 2867172235)

## Where things stand

G1–G5 (data read-back, pre-flight, holdout wiring, no-look-ahead guards, costs) were already cleared and committed in earlier sessions. **This session built and tested the entire remaining piece of step 7** — the runner, controls, scoring, and every `REGISTERED_htf_ben_v0.md` §3 item and §4 criterion — as 11 checkpoints, all committed to `D:\Trading` on `main`:

| # | Module | What it does | Commit |
|---|---|---|---|
| 1 | `strategy/htf/exits.py` | S1–S5 exit/trail simulation | `0326511` (prior session) |
| 2 | `strategy/htf/costs.py` | Amendment A friction pricing ($/contract/side) | `92b1bce` |
| 3 | `strategy/htf/runner.py` | E5-enforced trade ledger, roll/raw P&L | `acf5934` |
| 4–5 | `strategy/htf/controls.py` | C1 (reuse), C2 Donchian, C3 random entries | `a512650`, `98d5e7a` |
| 6 | `strategy/htf/book.py` | §3 aggregation + §4 scoring (9 criteria) | `28f418e` |
| 7 | `strategy/htf/neighbours.py` | §3 item 8: 18-cell trail/window/swing grid | `c550dff` |
| 8 | `strategy/htf/account.py` | §2.5/§3 item 9: equity curve, drawdown, ruin, max size, overnight margin | `2f40cd2` |
| 9 | `strategy/htf/weekly.py` | E6/§3 item 6: weekly trend, with/against net | `1fd7704` |
| 10 | `strategy/htf/readback.coverage()` | §3 item 11: bars/year, gaps, roll dates | `312fa16` |
| 11 | `strategy/htf/report.py` | **The CLI** — wires all of the above into one command, every §3 item + §4 criterion, B/A-2H/A-1H/A-4H side by side, training side only | `9519b02` |

**215/215 `tests/strategy/htf/` tests pass in the cloud container.** None of this has been run against the real archive yet — that is the very next step.

## What Ben needs to run next (commands are also posted on the board — subitem AT-7's Updates and the parent item's Updates, in `<pre>` blocks)

```powershell
Set-Location D:\Trading
.\.venv\Scripts\python.exe -m pytest tests\strategy\htf\ -q
.\.venv\Scripts\python.exe -m strategy.htf.report --skip-neighbours --skip-c3 --out claude\htf_ben_v0_report_dryrun.json
.\.venv\Scripts\python.exe -m strategy.htf.report --out claude\htf_ben_v0_report_20260925.json
```

The first confirms the suite for real. The second is a fast dry run of `report.py` (skips the expensive neighbour grid and C3's 1,000 draws) to sanity-check the whole pipeline end to end. The third is the full registered run — expensive (neighbour grid × 4 scenarios[1] × 18 cells, C3 × 4 scenarios × 1,000 draws, each of those independently rebuilding the 1H/2H/4H grids — see `report.py`'s own docstring, "COST") — so it may take a while; report back timing, not just results, if it runs long.

[1] by default the neighbour grid only runs on the two **scored** scenarios (B, A-2H) — `--all-neighbours` runs it on every `--scenarios` given if a full 4-way neighbour read is wanted.

## Documented scope decisions worth knowing before reading the report's output

- **1 MCL, mid friction is the headline** everywhere (§7's own rule). A single 1-CL summary is reported once per scenario (§2.5's "and per 1 CL") without mirroring every year/half/friction breakdown across both symbols.
- **C3's own 1,000-draw pool is not date-restricted to the training window.** `controls.run_c3` (already committed, already tested) has no such parameter; v0's own compared net stays training-only throughout, so this doesn't leak holdout information into v0's own number, but it's a known imprecision — flagged in the report's own `controls.c3_pool_not_date_restricted` field. A follow-up to actually restrict the pool would touch `controls.py`, not `report.py`.
- **Every trade list is cut to the training side via `holdout.split_dates(spend=False)`** (`report.training_trades()`) — never a locally re-derived date window. `report.py` never calls `split_dates(spend=True)`; **the holdout is still unspent.**

## Next steps (board)

- **W15-0004 / subitem AT-7** (Assignee: **Ben**) — run the three commands above, report results back on the subitem.
- Once the real report is in hand: turn it into the §5/§4 Result doc (`create_doc`, `doc_mm7crfy6` on the item), and a short chat summary per the project's own rule 8.
- **W15-0007** (v0-TL, the trend-line break+retest variant) — REGISTERED's own note says this is needed before step 7 is considered *fully* complete; not yet built, not blocking the report run above.
- The **holdout stays unspent** until v0 has been read on the training side (this report) and, separately, W15-0007 is in — spending it is Ben's own deliberate decision, a dedicated command, never a side effect of running `report.py`.

AT-ids: W15-0004 (subitem AT-7).
