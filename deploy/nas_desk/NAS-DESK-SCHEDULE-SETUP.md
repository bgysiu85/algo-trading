# Desk daily schedule (W18-0003) - NAS setup

Ben's choices (2026-11-07): all 20 tickers once a week (US Monday = Sydney Tuesday), every other weekday only the
active names; run from the PC ~09:00 Sydney Tue-Sat; summary to Telegram.

## Daily flow (Sydney time, Tue-Sat)
| When | Where | What |
|---|---|---|
| 08:20 | NAS, DSM task as root | `run_prepare_all.sh`: first the day's index/VIX/crude/yield closes (`desk.macro`, W18-0006), then bars + SEC data for all 20 tickers, no Claude usage (about 1 min per ticker) |
| every 5 min | NAS, DSM task as root | `send_outbox.py`: sends queued messages to Telegram |
| ~09:00 | PC, scheduled task | `/desk scheduled`: pull the NAS data, pick the tickers (`desk.schedule`), run the desk, send the summary |
| later | Ben | reads the Telegram message; places any buys with the bridge (`--check`, then `--place`) - NOT automatic |

The US date rolls over at 16:00 Sydney: 08:20 Sydney is 16:20 the day before in New York, so Tue-Sat mornings are US Mon-Fri.
IB Gateway's own daily restart fell about 09:30 Sydney in November (it was 16:30 Chicago, check the Gateway log): the
08:20 job finishes before it; if the job ever overlaps a restart it fails safely, alerts on Telegram and the PC does nothing.

## One-time setup (Ben, NAS SSH session, bash)
Why a root-owned folder: these two scripts run as root, and the `claude` SSH user owns `/volume1/docker/desk`. Root
must never write there (a planted symlink would let root overwrite any file), so the scripts and everything root writes
live in `/volume1/docker/desk-sched` (root:root).
```
sudo mkdir -p /volume1/docker/desk-sched/outbox
sudo install -o root -g root -m 755 /volume1/docker/desk/staging/run_prepare_all.sh /volume1/docker/desk-sched/run_prepare_all.sh
sudo install -o root -g root -m 755 /volume1/docker/desk/staging/send_outbox.py /volume1/docker/desk-sched/send_outbox.py
sudo sh -c "umask 077; echo \"SEC_CONTACT='bens85@icloud.com'\" > /volume1/docker/desk-sched/desk.env"
sudo chown root:root /volume1/docker/desk-sched/desk.env
sudo chmod 600 /volume1/docker/desk-sched/desk.env
sha256sum /volume1/docker/desk-sched/run_prepare_all.sh /volume1/docker/desk-sched/send_outbox.py
ls -l /volume1/docker/desk-sched
```
Report back: the two sha256 values must start `b873cd30389be180` (run_prepare_all.sh) and `68e7cbba6210f330` (send_outbox.py).

Then in DSM, Control Panel > Task Scheduler > Create > Scheduled Task > User-defined script, user **root**:
1. "desk prepare": Schedule Tuesday-Saturday 08:20; command `/bin/bash /volume1/docker/desk-sched/run_prepare_all.sh`
2. "desk telegram outbox": every 5 minutes; command `/usr/bin/python3 /volume1/docker/desk-sched/send_outbox.py`

## Tests (Ben)
NAS, one ticker only (takes about 1 minute; connects read-only to the paper Gateway like the manual step did):
```
sudo env ONLY=MPC /bin/bash /volume1/docker/desk-sched/run_prepare_all.sh
tail -20 /volume1/docker/desk-sched/prepare_all.log
```
Report back: the last lines of the log (the "START prepare for US date ..." line shows the date to use below).

PC (PowerShell), with that date in place of 2026-11-06:
```
Set-Location D:\Trading
.\.venv\Scripts\python.exe -m desk.pull_nas --date 2026-11-06
.\.venv\Scripts\python.exe -m desk.schedule --date 2026-11-06 --explain
.\.venv\Scripts\python.exe -m desk.notify --date 2026-11-06 --expected "MPC" --mode test
```
Report back: the three outputs, and whether the Telegram message arrived within 5 minutes.

## Adding the macro closes (W18-0006) - after the first scheduled run has passed
Code first, then the script (the script with old code only logs "FAILED macro" and alerts). PC (PowerShell):
```
Set-Location D:\Trading
scp -O -i "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519" desk\macro.py desk\pipeline.py desk\config.json claude@192.168.1.109:/volume1/docker/desk/app/desk/
scp -O -i "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519" deploy\nas_desk\run_prepare_all.sh claude@192.168.1.109:/volume1/docker/desk/staging/
ssh -i "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519" claude@192.168.1.109 "chmod 644 /volume1/docker/desk/app/desk/macro.py /volume1/docker/desk/app/desk/pipeline.py /volume1/docker/desk/app/desk/config.json /volume1/docker/desk/staging/run_prepare_all.sh"
```
NAS SSH session (bash): install the script, then test (macro only plus one ticker):
```
sudo install -o root -g root -m 755 /volume1/docker/desk/staging/run_prepare_all.sh /volume1/docker/desk-sched/run_prepare_all.sh
sha256sum /volume1/docker/desk-sched/run_prepare_all.sh
sudo env ONLY=MPC /bin/bash /volume1/docker/desk-sched/run_prepare_all.sh
tail -25 /volume1/docker/desk-sched/prepare_all.log
cat /volume1/docker/desk/var/desk_runs/$(TZ=America/New_York date +%F)/_macro_data.md
```
Report back: the sha256 (must start `959088c78f6e`), the log tail, and the table in `_macro_data.md` (which rows say STAND-IN or UNAVAILABLE).

## Rules not to undo
- Root scripts write only inside `/volume1/docker/desk-sched`; `send_outbox.py` skips symlinks in the claude-writable outbox.
- The desk never places orders. A buy is only announced; Ben runs the bridge.
- Never start IB Gateway paper on the PC. The PC pulls files; it never talks to the Gateway.

## AI Desk Telegram group (W18-0012, 2026-11-13)
Desk messages (the PC's run summary and the NAS prepare alerts) go to the Telegram group "AI Desk" (same bot as the
reminders, so no new secret) when `desk.env` sets `DESK_TELEGRAM_CHAT_ID`; without it they go to the reminders chat as
before. Reminders are not affected. Install (Ben, NAS SSH session, bash), after Claude copied the new script to staging:
```
sha256sum /volume1/docker/desk/staging/send_outbox.py
sudo install -o root -g root -m 755 /volume1/docker/desk/staging/send_outbox.py /volume1/docker/desk-sched/send_outbox.py
sudo sh -c "echo \"DESK_TELEGRAM_CHAT_ID='-5475374837'\" >> /volume1/docker/desk-sched/desk.env"
sudo chmod 600 /volume1/docker/desk-sched/desk.env
sudo /usr/bin/python3 /volume1/docker/desk-sched/send_outbox.py --test
```
Report back: the sha256 must start `85481e3aeeecfe17`; the last line must say `OK sent to chat -5475374837` and the
test message must appear in the AI Desk group. `FAILED ... chat not found` means the bot is not in the group or the
id is wrong. To undo: delete the DESK_TELEGRAM_CHAT_ID line from desk.env (messages go back to the reminders chat).
