# AI research desk (W18) — TradingAgents-style, run inside Claude Code

Ben's list of Seeking Alpha Alpha Picks goes in; for each stock the desk gives a rating, entry, stop and target. Long-only, paper-test only, nothing here places an order. Board: W18-0001 (this build is sub 2).

## How it works
`/desk MPC` (a Claude Code skill, `.claude/skills/desk/SKILL.md`) runs 13 subagents (`.claude/agents/desk-*.md`) in this order:

| Step | Agent | Model | Web? | Writes (in `var/desk_runs/<US date>/<TICKER>/`) |
|---|---|---|---|---|
| 0, daily | desk-macro-analyst | sonnet | yes | `../_macro.md` |
| 1, parallel | desk-market-analyst | sonnet | no | `market_report.md` |
| 1 | desk-fundamentals-analyst | sonnet | yes | `fundamentals_report.md` |
| 1 | desk-news-analyst | sonnet | yes | `news_report.md` |
| 1 | desk-sentiment-analyst | haiku | yes | `sentiment_report.md` |
| 2 | desk-bull | sonnet | no | `bull.md` |
| 3 | desk-bear | sonnet | no | `bear.md` |
| 4 | desk-research-manager | sonnet | no | `research_plan.md` |
| 5 | desk-trader | sonnet | no | `trader_plan.md` |
| 6 | desk-risk-aggressive / -conservative / -neutral | haiku | no | `risk_*.md` |
| 7 | desk-portfolio-manager | sonnet | no | `final_report.md` (ends with a JSON block) |

Before the agents, `python -m desk.prepare` (no Claude usage) pulls 2 years of daily bars from IBKR, computes the indicators, and pulls SEC EDGAR fundamentals. After the portfolio manager, `python -m desk.decision` checks the JSON (long-only, stop < entry < target, 1 share, horizon <= 180 days, conviction 1-10) and logs it to `var/desk_runs/decisions.csv`. `python -m desk.summary` ranks the day's buys (top 15 = TAKE).

## Before the first run
1. IB Gateway **paper** running and logged in, API enabled, port 4002 (TWS paper 7497 also works; live ports are refused).
2. `$env:SEC_CONTACT = "your@email"` in the same PowerShell window you start Claude Code from (SEC requires a contact address; without it fundamentals fall back to web search).
3. Start Claude Code in `D:\Trading`, then `/desk MPC`. The first time, Claude Code asks permission to write files and run the Python helpers; "don't ask again" for `var/desk_runs` is fine.
4. `/desk next 3` runs the next three undecided picks; `/desk all` runs every pending one. Interrupted runs resume where they stopped (a stage is skipped if its file already exists; delete a file to redo that stage).

## Files
`desk/config.json` — the 20 tickers, paper rules (1 share per symbol, max 15 open, 180-day hold), IBKR port and client id 91 (17 trader, 55 scanner, 77 viewer, 88 params dump are taken). `desk/pipeline.py` — the order and file names (the tests check the prompts against it).

## Known limits
- Agents' prompts cannot be unit-tested; `tests/desk/test_desk_agents.py` lints them (file names, tool allowlist, order, JSON example) but quality is judged in sub 3.
- AI desks cannot be backtested honestly (the model already knows the past). Only forward paper results count (W18-0004).
- Per-run Pro usage is unmeasured: sub 3 measures it and may switch models (edit `model:` in the agent files) or cut the debate.
