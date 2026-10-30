# RESULT — W10-0013 sub 5: the trader as a container on the NAS — 2026-10-30

Board: W10-0013 sub 5 (2869863011) -> Done. Parent W10-0013 (2869884333) stays In progress. Handover: `claude/handover_w10_0013_sub5_trader_container_20261028.md`.

## In plain terms
The NAS trader ran a full New York session in dry mode on 2026-10-28 and stopped by itself at 09:30, with no errors. Its position cap was still 3 in total (cap_scope=account) because `.env` had no `TRADER_CAP_SCOPE` line. Ben added `TRADER_CAP_SCOPE=strategy` on 2026-10-30 and recreated the container; the log now shows 3 positions per strategy. The code on the NAS is the sub 5 release (1cc53d4); sub 6 is not deployed yet.

## Checks
| Check | Result |
|---|---|
| Full 04:00–09:30 NY window | Container started 2026-10-28 04:52:49Z (00:52 NY, EDT), finished 13:30:00Z (09:30 NY), exit 0. Log: "entering main loop — DRY RUN", "09:30:00 ET reached and flat — stopping", session summary, clean disconnect, session time 31.0 ks. No ERROR or Traceback lines. Signal counts not read (grep only). |
| max_positions=3 | Pass (both runs). |
| cap_scope=strategy | 2026-10-28 run: cap_scope=account (no `TRADER_CAP_SCOPE` in `.env`, so the trader's default). Fixed 2026-10-30: Ben appended `TRADER_CAP_SCOPE=strategy` to `/volume1/docker/trader/.env`, ran `docker compose --profile trade up -d --no-deps trader`; log 08:27:58 NY: `max_positions=3 cap_scope=strategy strategies=MCL+MC5 dry_run=True bridge=off`, then "entering main loop — DRY RUN". |
| RELEASE.json vs git HEAD | NAS `app/RELEASE.json`: commit 1cc53d4, dirty false (built 2026-10-28T04:32:50Z). Git HEAD 878e76d; last code commit 0595a3a (sub 6). Checksums: NAS `run_trader.py` = 1cc53d4 version; NAS `compose.yaml` = ca31f78 version (network-mode fix). Does not match HEAD: sub 6 is not deployed. Accepted for sub 5, since 1cc53d4 is the tested sub 5 release. |

## Found along the way
- Claude's NAS SSH login (W10-0017) works. User `claude` cannot read `/volume1/trader` (root, mode 700, the trader's var/) or run docker, so trader logs still need Ben's session until sub 6 moves var/ to the `trader-data` share (currently empty).
- Remote scripts piped from PowerShell carry a UTF-8 BOM and CRLF: strip with `tr -d '\r'` and start the script with a throwaway comment line.

## Next steps (board ids)
- W10-0013 sub 6 (Opus · High): build the release tar from 0595a3a or later (dirty=False), deploy it, move var/ to `trader-data`. Claude can copy and unpack over SSH; Ben approves replacing `app/` and runs the docker steps.
- W10-0013 sub 8 (Sonnet · Medium): shadow run.
- W10-0013 sub 9 (Sonnet · High): DSM scheduled start, TRADER_MODE=paper, runbook.
