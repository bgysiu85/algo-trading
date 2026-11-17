# Handover - W18-0006 macro closes file for the desk - 2026-11-07

Chat: Build & test chat (Sonnet). Board: AI Research Desk, W18-0006 (2896326618). Follows W18-0001 sub 3 (first run: the macro agent could not confirm closes, VIX, crude or the FOMC date by web search).

## In plain terms
The NAS prepare job now also writes one file per day, `_macro_data.md`: the last close, 1-day change and 5-day change for SPY, QQQ, IWM (index funds), the VIX (volatility index), WTI crude and the US 10-year yield, all from the paper Gateway, no Claude usage. The macro analyst reads it first and quotes those numbers instead of searching for them, so the market note stops being full of UNCONFIRMED lines. If a series has no data subscription, a clearly labelled stand-in fund is used (VIXY, USO, IEF); if that fails too the row says UNAVAILABLE and the analyst searches the web for that line only.

## Built (tested, not yet run for real)
- `desk/macro.py` (`python -m desk.macro --date DATE`): read-only, paper ports only, client id 93 (new, unused). Real series first (CBOE index VIX and TNX, NYMEX front-month CL via ContFuture), then stand-in, then UNAVAILABLE; one failure never stops the others. Negatives in brackets, yield changes in basis points (bp, 100 bp = 1 percentage point). Warns if bar dates differ (stale feed). A yield index quoted x10 (42.5) is divided by 10 and labelled.
- `desk/config.json`: `macro` block. `desk/pipeline.py`: `MACRO_DATA_FILE`.
- `.claude/agents/desk-macro-analyst.md`: now has Read; reads the file first, fewer searches, cites "script data".
- `deploy/nas_desk/run_prepare_all.sh`: runs the macro step once before the ticker loop (same container flags). Best effort: a failure alerts on Telegram and exits 1 but never stops the stock data. `SKIP_MACRO=1` skips it. New sha256 959088c78f6e... (old b873cd30...).
- Tests: 12 new in `tests/desk/test_desk_macro.py`, 1 agent lint, 1 script lint. 248 pass, 1 skipped (run in a scratch environment on Linux, Python 3.10).
- The PC pull copies the whole day folder, so `_macro_data.md` reaches the PC with no change to `pull_nas.py`. Without the file the analyst works as before.

## Limits and risks
- Unverified until a real run: that the account has CBOE index data (VIX, TNX) and NYMEX data (CL); that ContFuture history works with it; the real quote scale of TNX. The first file shows which rows are real, stand-in or UNAVAILABLE.
- Deploy order matters: desk code to `/volume1/docker/desk/app/desk/` FIRST, then the root script. The new script with old code only logs "FAILED macro" and alerts.
- Deploy only after the first scheduled full run (Tue 10 Nov) has passed (W18-0003 sub 5), so a problem has one cause.
- Everything is uncommitted; Ben's W18-0003 commit was also never run, so one commit covers both (command on the board).

## Next steps (board)
- **W18-0006** - Ben: commit; after Tue 10 Nov check, copy the code to the NAS, install the script, run the one-ticker test (commands on the item).
- **W18-0006** - Claude, fresh chat, Haiku/Low: read the first `_macro_data.md` and the resulting `_macro.md`; if rows are stand-ins, ask Ben about the data subscriptions.
- Related: W18-0003 sub 5 (first scheduled run), W18-0010 (daily refresh also reads the macro note).
