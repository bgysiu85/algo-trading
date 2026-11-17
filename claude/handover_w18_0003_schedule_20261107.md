# Handover - W18-0003 daily desk schedule + phone summary - 2026-11-07

Chat: Build & test chat (Sonnet). Board: AI Research Desk, W18-0003 (2889221934), subitems 1-5 on the subitems board.
Follows W18-0002 (Done 2026-11-06). Feeds W18-0010 (daily refresh) and W18-0004 (scorecard).

## Ben's decisions (2026-11-07)
- Cadence: "Weekly all-20 + daily for active names" (US Monday = full run of all 20; other weekdays only active names).
- Runs from the PC as a scheduled task about 09:00 Sydney, Tue-Sat (needs the PC on and the Claude desktop app open).
- Phone summary: Telegram.

## In plain terms
Every Tuesday-to-Saturday morning the NAS prepares the data for all 20 stocks (no Claude usage). Later the PC's scheduled
task runs `/desk scheduled`: it copies that data over, works out which stocks are worth a desk run today (all 20 on Tuesdays,
otherwise only stocks with a working order, a buy never ordered, or a watch plan that is due), runs the desk on them, and
sends one short Telegram message with the buys, watches and anything unfinished. It never places an order: buys are only
announced, and Ben runs the bridge. On 10 Nov the selector would pick GM and BTSG (orders still logged as working), and FN and
LITE (watch plans due).

## Built (all tested: 231 desk tests + 8 NAS-script tests pass; not yet run for real)
- `desk/schedule.py` - the selector (`--explain`, `--tickers`). `desk/config.json` got `schedule` and `nas` blocks.
- `desk/pull_nas.py` - copies the day's folder from the NAS (`scp -O`, `claude` key); also the Telegram outbox upload. Real scp/ssh
  verified from the cloud shell (pull of 2026-11-02 worked; the upload worked into a scratch folder).
- `desk/notify.py` - builds the phone message from decisions.csv and queues it on the NAS.
- `.claude/skills/desk/SKILL.md` - new `scheduled` argument: pull, plan, run, notify.
- `deploy/nas_desk/run_prepare_all.sh` (DSM task, root) and `send_outbox.py` (DSM task every 5 min, root) + `NAS-DESK-SCHEDULE-SETUP.md`.
  Staged on the NAS in `/volume1/docker/desk/staging/` (sha256 b873cd30389be180... and 68e7cbba6210f330...).
- Security decision: the `claude` user owns `/volume1/docker/desk`, so the root scripts live and write only in the root-owned
  `/volume1/docker/desk-sched` (a symlink there would let root overwrite or leak any file). The sender skips symlinks in the
  claude-writable outbox (tests cover it). Do not move the root scripts' logs or alerts into the desk folder.

## Limits and risks
- Unverified: that a desktop scheduled task can start `/desk scheduled` (the skill is manual-only by design). Subitem 4 tests it.
- "Active" is a superset until W18-0009 (fill and exit tracking): a PLACED order counts as active until its hold_until, even if the
  entry never filled. GM and BTSG will therefore be re-run daily.
- IB Gateway's daily restart was about 09:30 Sydney in November; the 08:20 prepare finishes before it. Check the log if the NAS job alerts.
- A full Monday run is about 20 x 0.7% of a 5-hour session and about an hour; a US holiday run uses the previous close.
- `/volume1/docker/reminders/reminders.env` (monday token, CalDAV password, Telegram token) is mode 644, readable by every NAS user
  including `claude`. Not changed here; Ben may want `sudo chmod 600` on it.

## Next steps (board)
- **W18-0003 sub 2** - Ben: install the two root scripts and add the two DSM tasks (commands on the item).
- **W18-0003 sub 3** - Ben: one-ticker end-to-end test (NAS prepare, PC pull, Telegram message).
- **W18-0003 sub 4** - Build & test chat, Haiku/Low: create the PC scheduled task after sub 3 passes.
- **W18-0003 sub 5** - Ben: check the first scheduled run on Tue 10 Nov (full run): Telegram message and usage %.
- **W18-0010** (daily refresh of entry/exit), **W18-0009** (fill tracking), **W18-0008** (close at hold_until) build on this schedule.
