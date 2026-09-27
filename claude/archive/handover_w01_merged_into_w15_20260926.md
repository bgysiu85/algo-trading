# Handover — W01 merged into W15 (2026-09-26)

**From:** Research & spec chat · **To:** every Algo Trading chat · **Adds to:**
`claude/handover_workstream_codes_20260923.md` (its map now carries W14, W15 and this change).

## What changed

Ben's decision, 2026-09-26, in his words: *"Merge into W15 (Recommended)"*. The reasoning he
agreed to: W01's question ("should we move to futures?") was answered when he pivoted to
higher-timeframe futures on 2026-09-25, and everything still open in W01 is higher-timeframe futures
work on CL. It uses the same 1-hour data, the same `strategy/htf` engine, the same trend-line code
(`common/tl_v0_lines.py`) and the same cost model as W15.

- **W15 - High-timeframe futures (1h–1d)** is now the only futures strategy workstream: HTF-Ben
  (Ben's own 4H method), TL-v0 / TL-v0-rev (Tori, daily, 12 markets), TL-bounce (Tori, CL 4H), and
  the Tori channel sweep.
- **W01** is closed. Its group is renamed *"W01 - Futures Trading Viability Analysis (closed
  2026-09-26, merged into W15)"* and holds only Done/Dropped items, kept as the record. **Nothing new
  goes in W01.**
- The two non-futures channel reviews were closed as **Dropped: reviewed, not pursued**, as the option
  Ben chose said: **W01-0010** (The Rumers, intraday index day-trading) and **W01-0012** (Mulham,
  forex/gold scalping). Their collations stay in the project.

## Id mapping (open items moved, new W15 numbers)

| Old id | New id | Item | Status |
|---|---|---|---|
| W01-0009 | **W15-0013** | Free TradingView check of SMA-Fib v2 (TAI) on CL1! 60-min | Waiting on Ben (likely drop: TSMOM not carried forward) |
| W01-0013 | **W15-0014** | TL-v0 / TL-v0-rev step 4 backtest vs Donchian | Not Started, Build & test chat |
| W01-0016 | **W15-0015** | TL-bounce free steps (Pine, engine, guards, parity, pre-flight) | Next up, Build & test chat |
| W01-0017 | **W15-0016** | TL-bounce backtest | Backlog, blocked by W15-0014, W15-0015 |
| W01-0018 | **W15-0017** | Tori Trades full-channel sweep | Next up, Research & spec chat |

Each moved item keeps its old id at the end of its name ("… (was W01-0013)") and has a dated Update
saying so. Subitems moved with their parents. Items that stayed in W01 (0001–0008, 0011, 0014, 0015
Done; 0010, 0012 Dropped) keep their W01 ids.

## Docs

- `docs/research/REGISTERED_tl_bounce.md` — Amendment 0 (PRE-RUN, board ids only; no rule changed).
- `claude/w01_0014_tori_bounce_video_RESULT_20260926.md` — next steps carry the new ids.
- Older docs (`REGISTERED_tl_v0.md`, W01 channel reviews, handovers) still cite W01-00xx or AT-n ids.
  They are not rewritten; translate with the table above and the 2026-09-23 map.

## Next steps (board)

- **W15-0013** — Ben: confirm the drop (his W01-0008 condition has been met since 2026-09-23).
- **W15-0014**, **W15-0015** — Build & test chat.
- **W15-0017** — Research & spec chat, fresh session, Sonnet.
