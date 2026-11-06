#!/bin/bash
# W11-0041 sub 9: what the DSM Task Scheduler entry runs every 5 minutes (as root).
# One sync run; all output goes to reminders.log (the script writes it itself) and to the DSM task log.
export PATH="$PATH:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"      # DSM tasks start with a thin PATH
DIR="${REMINDERS_DIR:-/volume1/docker/reminders}"
cd "$DIR" || exit 2
exec /usr/bin/python3 "$DIR/reminders_sync.py" "$@"
