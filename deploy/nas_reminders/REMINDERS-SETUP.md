# NAS reminders sync (W11-0041 sub 9; install = sub 10)

Turns each item on the monday **Reminders** board into a task in the Synology task list **monday reminders**. The iPhone
shows it in the Reminders app and alerts at the time. Ticking it on the phone sets the item to **Done** on monday and posts
one Update on the linked Wxx task. A Telegram message goes out at the time as a backup.

## Limits and risks (read first)
- **Tested here only against fakes** (a fake feed, fake CalDAV server, fake monday, fake Telegram). It has never talked to
  the real Synology Calendar, so step 4 (`--check`) is the first real test. Synology's exact CalDAV paths and task format
  are the likeliest thing to need a tweak.
- The **monday API token** is Ben's own, so it can do everything Ben can on monday. It lives only in `reminders.env`
  (mode 600) on the NAS. If it leaks, delete it in monday (Developers > My access tokens) and make a new one.
- Only TCP **38443** is forwarded to the internet. This script never needs DSM (5000/5001) or SSH from outside.
- It only touches the list **monday reminders**. It never reads or changes Ben's own tasks (My Task).
- A ticked reminder is only noticed on the next 5-minute run, and the iPhone syncs in the background, so allow a few minutes.
- Python on the NAS may be old (3.8). The code avoids newer features, but `--check` proves it.

## Choices made
- **Feed vs API:** the monday calendar feed is read every run (no API calls). The API is used once an hour (to learn item ids
  and to catch a reminder set Done in monday) and when a tick happens: about 24 to 30 calls a day, under the 50 budget.
- **A reminder leaves the feed (deleted or moved):** its phone task is **deleted**. A ticked task stays on the phone's
  list for 7 days after it was due, then is removed.
- **A task deleted on the phone** counts as dismissed: no recreate, no Telegram, monday unchanged.
- **A reminder already more than 15 minutes late when first seen** gets no task and no Telegram (old board items stay quiet).
- **If the sync fails 6 runs in a row (30 min)** it sends one Telegram alarm, and one more when it recovers.

## Files (in /volume1/docker/reminders)
`reminders_sync.py` (the script), `run_reminders.sh` (what DSM runs), `make_reminders_env.sh` (writes `reminders.env`),
`reminders.env` (secrets, mode 600, made by you), `reminders_state.json` and `reminders.log` (made by the script).

## Install (sub 10)
1. **PC:** the tar is in `D:\Trading\Claude outputs\w11_0041_sub9_nas.tar`; copy it to the NAS with the commands on the board.
2. **NAS:** unpack, then `bash /volume1/docker/reminders/make_reminders_env.sh` (asks for the feed link, the monday token and
   the calendar-monday password; hides them; sets mode 600).
3. **monday token:** click your profile picture > Developers > My access tokens (menu names may differ slightly) > copy.
4. **Check (changes nothing):** `sudo python3 /volume1/docker/reminders/reminders_sync.py --check`
   Expect PASS for feed, CalDAV login, task list and monday API. If it says the list is missing, run `--create-list` once.
   If `--create-list` is refused, create the list by hand: Synology Calendar, signed in as calendar-monday, Tasks, new task
   list named exactly `monday reminders`. Then add that list's account to the iPhone Reminders (it syncs with the same account).
5. **Dry run:** `sudo python3 /volume1/docker/reminders/reminders_sync.py --dry-run` prints what it would create.
6. **DSM Task Scheduler:** Create > Scheduled Task > User-defined script. User: root. Schedule: every 5 minutes, all day.
   Command: `bash /volume1/docker/reminders/run_reminders.sh`. Untick "send run details by email" or leave as you like.
7. **Live test (with the chat):** add a Reminders item due about 20 minutes ahead; it should appear in iPhone Reminders after
   the next run and alert on time; tick it and check the item turns Done on monday.

To see what Synology wrote for your own test task: `sudo python3 /volume1/docker/reminders/reminders_sync.py --dump "My Task"`.

## Rules not to undo
- A failed feed or failed task listing must never delete, tick or dismiss anything (tests enforce it).
- `reminders.env` stays mode 600 and never goes into the repo. The script never touches the trader or Gateway containers
  or `/volume1/docker/trader/.env` (it only reads the two Telegram lines of it, through `make_reminders_env.sh`, once).
- Never change the Wxx task's own Status from here; only add the one Update.
