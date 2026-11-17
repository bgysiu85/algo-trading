# W18-0001 sub 2 — AI research desk rebuilt as Claude Code agents — RESULT (2026-10-28)

Board: W18-0001 sub 2 (Build & test chat, Sonnet/High). Follows sub 1 (`claude/w18_0001_sub1_tradingagents_study_RESULT_20261024.md`).

## In plain terms
The research desk now exists as files in your trading folder. In Claude Code you type `/desk MPC` and 13 small AI "staff" work through the stock in order: four analysts first (price chart, company financials, news, market mood), then a bull and a bear argue, a manager picks a side, a trader sets entry / stop / target, three risk voices push back, and a portfolio manager gives the final rating. Everything that is plain number work (pulling prices from IBKR, pulling financials from SEC filings, indicator maths, checking the final answer) is ordinary Python and costs no Pro usage. The final call is checked by script (long-only, stop below entry below target, 1 share, 180 days at most) and logged to a file that the IBKR bridge (W18-0002) will read. It is built and unit-tested in the cloud (99 tests passing) but has NOT yet been run against your live IBKR, SEC or Claude Code: that is steps 2b and 4.

## What you must do or decide
Nothing to decide. Two hands-on steps, commands are on the board: **2b** (copy 14 files into `D:\Trading\.claude`, run the tests; about 2 minutes) then **4** (run `/desk MPC` once and paste the results and the `/usage` screen). The files could not go straight into `.claude` because the remote file tool refuses that folder, which is why 2b exists.

## What was built
**Claude Code side** (waiting in `D:\Trading\Claude outputs\desk_claude_config`, copied to `D:\Trading\.claude` by step 2b)

| Step | Agent | Model | Web access | Writes |
|---|---|---|---|---|
| 0, once a day | desk-macro-analyst | sonnet | yes | `_macro.md` |
| 1, parallel | desk-market-analyst | sonnet | no | `market_report.md` |
| 1 | desk-fundamentals-analyst | sonnet | yes | `fundamentals_report.md` |
| 1 | desk-news-analyst | sonnet | yes | `news_report.md` |
| 1 | desk-sentiment-analyst | haiku | yes | `sentiment_report.md` |
| 2 | desk-bull | sonnet | no | `bull.md` |
| 3 | desk-bear | sonnet | no | `bear.md` |
| 4 | desk-research-manager | sonnet | no | `research_plan.md` |
| 5 | desk-trader | sonnet | no | `trader_plan.md` |
| 6 | desk-risk-aggressive / conservative / neutral | haiku | no | `risk_*.md` |
| 7 | desk-portfolio-manager | sonnet | no | `final_report.md` + JSON decision |

`/desk` (`.claude/skills/desk/SKILL.md`) is the conductor: `/desk MPC AMZN`, `/desk next 3`, `/desk all`. It runs the Python helpers, launches the four analysts in parallel, then the rest one at a time, never reads the reports itself (saves usage), resumes where it stopped, and ends with a one-table summary.

**Python side** (`D:\Trading\desk\`, already in place)

| Module | Job |
|---|---|
| `prepare` | 2 years of daily bars from IBKR (read-only, paper ports only, client id 91), indicators, SEC fundamentals; writes the files the analysts read |
| `fetch_bars`, `indicators`, `snapshot` | bars, RSI / MACD / Bollinger / ATR / moving averages, drops today's unfinished bar |
| `fundamentals` | SEC EDGAR company facts, point-in-time, handles 20-F (IFRS) filers, negatives in brackets |
| `decision` | finds the JSON block, validates, writes `decision.json`, logs to `var/desk_runs/decisions.csv` |
| `status`, `summary` | which tickers are pending; ranks the day's buys by conviction then reward:risk, top 15 = TAKE |
| `config.json` | the 20 Alpha Picks, paper rules (1 share, max 15 open, 180-day hold), IBKR port |

**Decision record** (the contract W18-0002 reads): `run_date, ticker, rating, actionable, conviction (1-10), entry, stop, target, horizon_days, size_shares, risk_per_share, reward_risk, last_close, atr14, warnings, decided_at_utc`. Only Buy / Overweight are actionable; Hold / Underweight / Sell mean no position.

## Tests
99 pass, on pandas 2.3 and 3.0 (indicators vs independent maths, snapshot, IBKR fetch with a fake connection, SEC parsing incl. restatements and point-in-time, decision gate with 16 bad-field cases, CSV log, ranking, prompt lint). Four deliberate code breakages were each caught by a test. The repo's own guards (UTF-8 encoding rule, "every test file defines a test") accept the new files.

## Rules a later chat must not undo
- Long-only; Hold / Underweight / Sell open nothing. The desk never places orders.
- Exact prices come only from the script-computed `market_data.md`; agents may not quote prices from memory.
- IBKR paper ports only (4002 / 7497); live ports are refused in code. Client id 91 (17 trader, 55 scanner, 77 viewer, 88 params are taken).
- Subagents have no shell; only macro / fundamentals / news / sentiment can use the web. The conductor must not read report files.
- Do not name a repo file `watchlist.txt` (gitignored); the tickers live in `desk/config.json`.
- The run date is the US market date, not Sydney's.

## Not verified (honest list)
- Live IBKR and SEC connections (the cloud cannot reach either; all tested with fakes).
- That Claude Code launches the four analysts truly concurrently from one message (its docs do not state it outright; worst case they run one after another, only slower).
- Report and decision quality: prompts cannot be unit-tested; step 3 judges them from Ben's first run.
- Pro usage per ticker: unmeasured. Worst-case turn caps are 86 agent turns per ticker plus 12 once a day for the macro note; typical use should be well below.

## Token plan for the remaining steps (project rule 9)
| Step | Who | Model / effort | Why |
|---|---|---|---|
| 2b copy + tests | Ben | Haiku / Low (reading pasted output) | mechanical |
| 4 first run | Ben | Claude Code default | needs IBKR Gateway on his PC |
| 3 judge quality and usage | Build & test chat | Sonnet / Medium | reads saved reports + `/usage`; fresh chat |
| Tune agents after step 3 | Build & test chat | Sonnet / Low | edits `model:` lines or trims debate |
| W18-0002 IBKR bridge | Build & test chat | Sonnet / High | order logic, needs care |
| W18-0003 daily schedule | Build & test chat | Haiku / Low | |
| W18-0004 scorecard | Research & spec chat | Opus / Medium | |

Cheap levers if the first run is too heavy: set `CLAUDE_CODE_SUBAGENT_MODEL=haiku` for a trial; edit one `model:` line per agent; run `/desk next 3` per session; merge the three risk voices or drop to one debate turn (a step-3 decision from the measured numbers).

## Next steps (board)
- **W18-0001 sub 2b** — Ben: copy files, run tests (commands on the item).
- **W18-0001 sub 4** — Ben: `/desk MPC`, paste results and `/usage`.
- **W18-0001 sub 3** — Build & test chat: judge quality and usage from that run (runs after 4).
- **W18-0002** — IBKR paper bridge reads `decisions.csv` (still blocked by W18-0001).

## Source files
`D:\Trading\desk\*.py`, `desk\config.json`, `desk\README.md`; `tests\desk\test_desk_data.py`, `test_desk_decision.py`, `test_desk_agents.py`; `D:\Trading\Claude outputs\desk_claude_config\{agents,skills}`.
