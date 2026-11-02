# AI research desk (W18) — TradingAgents-style, run inside Claude Code

Ben's list of Seeking Alpha Alpha Picks goes in; for each stock the desk gives a rating, entry, stop and target. Long-only, paper-test only. The desk itself never places an order; the separate bridge (`desk/bridge.py`, W18-0002) does, and only with `--place`. Board: W18-0001 (this build is sub 2).

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

A Hold may carry an optional `watch_plan` (W18-0007): `revisit_on`, `trigger` (`close_above`/`close_below` + level), `entry_zone`, `stop`, `target`, `size_note`. The checker logs it in the `watch` and `plan_*` columns of `decisions.csv`; `actionable` stays False. The summary lists these as "Watching" and, across days, as "Open watches" (DUE once the revisit date is reached) for W18-0003 to re-run. A watch is a reminder, never an order: the IBKR bridge (W18-0002) acts only on a fresh Buy/Overweight.

## Before the first run
Since 2026-10-28 the paper IB Gateway runs on the NAS (`trader-ib-gateway`, W10-0013) and its API is reachable only
from containers that join its Docker network. One IBKR paper username = one session, so do NOT start IB Gateway paper on
the PC: it would knock the NAS Gateway and the NAS trader off. The run is therefore split (W18-0001 sub 4):

1. **NAS, data only (no Claude usage).** The code is in `/volume1/docker/desk/app` (a copy of `desk/`, `RELEASE.json` says
   which commit), output in `/volume1/docker/desk/var/desk_runs/<US date>/<TICKER>/`. In Ben's NAS SSH session:
   `sudo docker run --rm --security-opt seccomp=unconfined --network container:trader-ib-gateway --user 1043:100 ...
   python:3.12-slim python -m desk.prepare MPC --date <US date>` (full command on the board). Client id 91, read-only,
   paper port 4002 inside the Gateway's network. It can run while the NAS trader runs (a separate API client, client id 17).
2. **Copy to the PC**: `scp -r` the day's folder into `D:\Trading\var\desk_runs\` (command on the board).
3. **PC**: `$env:SEC_CONTACT` is not needed here (fundamentals were fetched on the NAS). Start Claude Code in
   `D:\Trading`, then `/desk MPC` on the same US date. The skill sees `market_data.md` and skips prepare. The first
   time, Claude Code asks permission to write files and run the Python helpers; "don't ask again" for `var/desk_runs` is fine.
4. `/desk next 3` runs the next three undecided picks; `/desk all` runs every pending one. Interrupted runs resume where
   they stopped (a stage is skipped if its file already exists; delete a file to redo that stage). Prepare those tickers
   on the NAS first (repeat step 1 once per ticker, same date).
5. The US date rolls over at 16:00 Sydney time (15:00 while New York is on daylight time). Run steps 1-3 on the same US
   date, or the PC will look in a different day's folder and try to prepare locally (and fail, which is safe).

## IBKR paper bridge (W18-0002)
`python -m desk.bridge` turns today's Buy / Overweight decisions into bracket orders on the PAPER account: a day limit buy at `entry`, a GTC take-profit at `target` and a GTC stop-market at `stop` (the two exits cancel each other), 1 share, orderRef `desk:<date>:<TICKER>`. It re-checks every row (stop < entry < target, 1 share, horizon <= 180, entry not more than 2% above the last close, ticker on the list), ignores anything not dated today's US date, never acts on a Hold's watch plan, and respects the 15-position cap using the desk's own ranking (existing stock positions in the list and pending desk entries count). Three modes:

| Command | Connects? | Can place? | Writes |
|---|---|---|---|
| `python -m desk.bridge` | no | no | nothing (positions, open orders and funds are NOT checked) |
| `python -m desk.bridge --check` | yes, read-only | no | nothing |
| `python -m desk.bridge --place [--ticker MPC]` | yes | yes | `var/desk_runs/orders.csv` |

Guards: ports other than 4002 / 7497 refused, connection dropped unless every managed account starts with `DU`, client id 92. If any leg of a bracket is refused, the whole bracket is cancelled so an entry is never left without its stop. `orders.csv` keeps a PLACED row for the day (a later run skips that ticker); SKIPPED / REJECTED rows say why.

Like `prepare`, `--check` / `--place` must run on the NAS (a one-off container on the Gateway's network), because the PC cannot reach the paper API. Same `docker run` as the data step with `-v /volume1/docker/desk/var:/app/var` and `python -m desk.bridge --check`; `decisions.csv` has to be copied to `/volume1/docker/desk/var/desk_runs/` first, and `orders.csv` is copied back afterwards. Check that the `US date` line the bridge prints is the date of the desk run.

Not done by the bridge: closing a position when its horizon (`hold_until` in orders.csv) passes, tracking fills and exits for the scorecard (W18-0004), and the daily schedule (W18-0003). GTC exits stay working until filled or cancelled; IBKR may cancel GTC orders around corporate actions.

## Files
`desk/config.json` — the 20 tickers, paper rules (1 share per symbol, max 15 open, 180-day hold), IBKR port and client id 91 (17 trader, 55 scanner, 77 viewer, 88 params dump are taken). `desk/pipeline.py` — the order and file names (the tests check the prompts against it).

## Known limits
- Agents' prompts cannot be unit-tested; `tests/desk/test_desk_agents.py` lints them (file names, tool allowlist, order, JSON example) but quality is judged in sub 3.
- AI desks cannot be backtested honestly (the model already knows the past). Only forward paper results count (W18-0004).
- Per-run Pro usage is unmeasured: sub 3 measures it and may switch models (edit `model:` in the agent files) or cut the debate.
