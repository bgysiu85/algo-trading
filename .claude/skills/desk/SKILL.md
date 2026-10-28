---
name: desk
description: Run Ben's AI research desk (TradingAgents-style, W18) on one or more stocks and get a rating, entry, stop and target for each. Manual use only.
argument-hint: "<TICKER ...> | next <N> | all"
disable-model-invocation: true
---

# /desk — the AI research desk

You are the ORCHESTRATOR. You do not analyse stocks yourself. You run Python helpers and call the desk's subagents in the right order, keep your own context small, and report a short table at the end. The desk is long-only, paper-trading research for Ben's Seeking Alpha Alpha Picks (list and rules in `desk/config.json`). It never places orders.

Arguments: `$ARGUMENTS`

## 0. Work out what to run
Python for every helper below is the repo venv, run from the repo root:
- PowerShell tool: `.\.venv\Scripts\python.exe -m desk.<module> ...`
- Git Bash tool: `./.venv/Scripts/python.exe -m desk.<module> ...`

1. Get the run date: `python -m desk.status --show-date` (the US market date, not Sydney's). Call it DATE. DAY_DIR = `var/desk_runs/DATE`.
2. Tickers:
   - explicit tickers (`MPC AMZN`) → those, upper-cased;
   - `next N` → `python -m desk.status --pending --limit N`;
   - `all` → `python -m desk.status --pending`;
   - empty → ask Ben which of those he wants (one short question), do not guess.
3. Tell Ben in one line what you are about to run (tickers, date). Do not ask for confirmation.

## 1. Once per day: the macro note
If `DAY_DIR/_macro.md` does not exist, call subagent `desk-macro-analyst` (task text: see "Task text" below, with DAY_DIR). Skip if it exists.

## 2. For each ticker, one at a time
RUN_DIR = `var/desk_runs/DATE/TICKER`. Resume rule: before spawning ANY agent, skip it if its output file already exists in RUN_DIR (an earlier run got that far). To redo a stage, Ben deletes that file.

1. **Prepare** (no LLM): `python -m desk.prepare TICKER --date DATE`. The last line is `PREPARED {...}` on success. On `PREPARE FAILED`: record the ticker as SKIPPED with the reason and go to the next ticker. If the failure says it could not connect to the Gateway, do NOT keep looping over the other tickers: stop the whole run and tell Ben the one thing to fix (start IB Gateway paper on port 4002, logged in, API enabled).
2. **Four analysts IN PARALLEL**: send ONE message containing four Agent calls — `desk-market-analyst`, `desk-fundamentals-analyst`, `desk-news-analyst`, `desk-sentiment-analyst`. Wait for all four.
3. **Debate and decision, strictly in this order, one at a time**: `desk-bull` → `desk-bear` → `desk-research-manager` → `desk-trader` → `desk-risk-aggressive` → `desk-risk-conservative` → `desk-risk-neutral` → `desk-portfolio-manager`.
4. After each agent returns, its output file (listed in `desk/pipeline.py`) must exist in RUN_DIR. Check with a directory listing, NOT by reading the file. If it is missing, call that agent once more; if it is still missing, mark the ticker FAILED at that stage and move on.
5. **Check the decision** (no LLM): `python -m desk.decision --ticker TICKER --date DATE`.
   - `OK ...` → done; note the rating line.
   - `INVALID ...` (exit 2) → call `desk-portfolio-manager` ONE more time with the Task text plus the exact `INVALID` lines, then run the check again. If it is still invalid, mark FAILED (validator message) and move on.
   - `WARNING ...` lines are not failures; carry them into your final report.

## 3. Finish
Run `python -m desk.summary --date DATE` (ranks the day's buys; writes `DAY_DIR/SUMMARY.md`). Then reply with ONLY:
- a compact table: ticker · rating · conviction · entry · stop · target · reward:risk (from the OK lines / summary), then any SKIPPED/FAILED tickers with reasons, then any warnings;
- the folder where the full reports are (`DAY_DIR`);
- one line: "re-run `/desk next N` to continue" if tickers remain.

## Task text (copy this shape into every Agent call; fill the values)
```
Ticker: TICKER
Run date (US): DATE
RUN_DIR: var/desk_runs/DATE/TICKER
DAY_DIR: var/desk_runs/DATE
Do your job exactly as defined in your instructions. Reply with the one-line DONE message only.
```
For the portfolio manager's retry, append: `The checker rejected your last file with: <paste the INVALID lines>. Fix exactly that and rewrite final_report.md.`

## Rules for you, the orchestrator
- Subagent type = the exact agent name (e.g. `desk-bull`). Pass paths in the task text, never report contents.
- Do NOT read the agents' report files yourself and do not paste them anywhere. They are for the next agent, and reading them wastes Ben's Pro usage.
- Keep your own messages between tool calls to a few words.
- If a usage limit or error interrupts the run, files already written are kept; tell Ben to re-run `/desk next N` later and it resumes.
- Never place, edit or cancel orders; never touch D:\TradingProd; write nothing outside `var/desk_runs/`.
