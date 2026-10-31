# RESULT — W10-0013 sub 6: trader data on a read-only NAS share, heartbeat session lock — 2026-10-31

Board: W10-0013 sub 6 (2869874613) -> Done. Parent W10-0013 (2869884333) stays In progress. Code commit 0595a3a. The handover `claude/handover_w10_0013_sub6_shared_data_lock_20261028.md` is not in the repo; this was worked from the board Updates and NAS-TRADER-SETUP.md Part 3.

## In plain terms
The NAS trader now runs the sub 6 code and keeps its data in the DSM shared folder `trader-data`. Its session lock carries a heartbeat that refreshes every 20 seconds. The ProArt reads that lock over SMB as the read-only user `pc-reader`, so a backtest or `main.py` on the PC refuses while the NAS trader is in session. A Windows scheduled task copies the NAS fills into `D:\Trading\var\nas_mirror` every 2 hours, one way, never deleting or overwriting.

## Steps and checks
| Step | Result |
|---|---|
| S1 (Ben, 28 Oct) | Shared folder `trader-data`, user `pc-reader` with read-only access. |
| A (Ben, 28 Oct) | 202 passed, 1 skipped; commit 0595a3a; tar dirty=False. sha256 cac9164e…51a1 is the same on the PC and the NAS. |
| B (Ben ran it, Claude checked over SSH, 31 Oct) | RELEASE.json 0595a3a, dirty false. run_trader.py, session_lock.py, main.py and compose.yaml match git. `.env`: mcl,mc5 / 3 / strategy / TRADER_VAR_DIR=/volume1/trader-data/var, no TRADER_MODE (dry). var/ owned by 1000:1000 and readable by all. The old /volume1/trader/var is left in place. |
| Heartbeat | Lock: mode dry, mcl,mc5, version …g0595a3a, tree /app. heartbeat_epoch went 1793439233.60 -> 1793439253.60 in 20 s steps. PASS. |
| C (Ben ran cmdkey; Claude did the rest, 31 Oct) | `setx SESSION_LOCK_REMOTE` and `setx NAS_TRADER_VAR` set for the user. `python -m common.session_lock`: "LIVE SESSION -- dry session for strategy mcl,mc5 … on another machine (687645023ab6) … last heartbeat 16s ago". Clocks: PC 09:36:29.208Z, NAS 09:36:29.381Z (0.2 s apart). First pull: fills 3 copied (20261028, 20261030, 20261031). Scheduled task `Algo - pull NAS var`: started once, LastTaskResult 0, second pull "unchanged 3", next run 22:20 and every 2 h after that. |

## Found along the way
- The trader runs its 04:00–09:30 NY window on weekends too (it started a dry session on Sat 31 Oct at 05:32 NY). This is harmless in dry mode; weekend skipping belongs to the sub 9 scheduled start.
- The trader logs to docker stdout only; there is no var/logs on the NAS, so pull_nas_var copies no logs and reading the log still needs Ben's `docker logs`.
- The scheduled task was registered without a principal, so it runs only while Ben is logged on to the ProArt.
- PowerShell pipes scripts to ssh with a UTF-8 BOM and CRLF. On the NAS side use `sed '1s/^\xEF\xBB\xBF//' | tr -d '\r' | sh -s`.

## Undo
Delete the scheduled task `Algo - pull NAS var`, run `setx SESSION_LOCK_REMOTE ""`, and point TRADER_VAR_DIR back to /volume1/trader/var.

## Next steps (board ids)
- W10-0013 sub 8 (Sonnet · Medium): shadow run; dry mode is the shadow mode.
- W10-0013 sub 9 (Sonnet · High): DSM scheduled start (weekdays only), TRADER_MODE=paper, runbook, `--promote` cut-over.
- W10-0013 sub 7 (Opus · High): security review of the trader side.
