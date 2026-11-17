#!/bin/bash
# W18-0003: DSM Task Scheduler entry, run as root, Tue-Sat ~08:20 Sydney (after the US close).
# Data step of the desk for ALL tickers (bars from the paper Gateway + SEC fundamentals; no Claude usage), so the
# PC's scheduled run can pick any subset. One one-off container per ticker, same flags as the manual step in
# claude/handover_w18_0001_sub4_nas_prepare_20261101.md. Nothing here places or changes an order.
#
# SECURITY: this runs as root, so everything root WRITES lives in the root-owned folder $SCHED (log, alerts, env).
# The `claude` SSH user owns /volume1/docker/desk, so root never writes there (a planted symlink would turn a root
# write into an overwrite of any file); the containers do, as uid 1043.
#
# Needs $SCHED/desk.env (root:root, mode 600) holding:  SEC_CONTACT='<a real e-mail>'   (SEC answers 403 otherwise)
export PATH="$PATH:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
SCHED="${SCHED_DIR:-/volume1/docker/desk-sched}"
DESK="${DESK_DIR:-/volume1/docker/desk}"
ENVF="$SCHED/desk.env"
LOG="$SCHED/prepare_all.log"
mkdir -p "$SCHED/outbox"

say() { echo "$(date '+%F %T') $*" >> "$LOG"; }
alert() { printf '%s\n' "$1" > "$SCHED/outbox/prepare_$(date +%Y%m%d_%H%M%S).txt"; }   # sent by send_outbox.py

[ -r "$ENVF" ] || { say "STOP: $ENVF missing"; alert "Desk prepare did not run: $ENVF is missing."; exit 2; }
# shellcheck disable=SC1090
. "$ENVF"
[ -n "$SEC_CONTACT" ] || { say "STOP: SEC_CONTACT empty"; alert "Desk prepare did not run: SEC_CONTACT is empty in desk.env."; exit 2; }

DATE=$(TZ=America/New_York date +%F)                 # the US market date, as desk.config.default_run_date does
TICKERS=$(/usr/bin/python3 -c "import json; print(' '.join(json.load(open('$DESK/app/desk/config.json'))['tickers']))") \
  || { say "STOP: cannot read config.json"; exit 2; }
[ -n "$ONLY" ] && TICKERS="$ONLY"                    # test run: sudo env ONLY=MPC bash run_prepare_all.sh
say "START prepare for US date $DATE: $TICKERS"

# W18-0006: one file for the day with the index / VIX / crude / 10-year yield closes (the macro analyst reads it first).
# Best effort: if it fails the analyst falls back to web search for those lines, and the stock data below still runs.
# SKIP_MACRO=1 skips it (test runs).
macro_failed=""
if [ -z "$SKIP_MACRO" ]; then
  if docker run --rm --security-opt seccomp=unconfined --network container:trader-ib-gateway --user 1043:100 \
       -e HOME=/tmp -e PYTHONPATH=/app:/deps \
       -v /volume1/docker/trader/deps:/deps:ro -v "$DESK/app":/app:ro -v "$DESK/var":/app/var -w /app \
       python:3.12-slim python -m desk.macro --date "$DATE" >> "$LOG" 2>&1; then
    say "macro closes ok"
  else
    macro_failed=1; say "FAILED macro closes (the macro analyst will use web search)"
  fi
fi

ok=0; failed=""; consecutive=0
for T in $TICKERS; do
  # config.json is writable by the claude user: only plain tickers ever reach the docker command
  [[ "$T" =~ ^[A-Z][A-Z0-9.-]{0,9}$ ]] || { say "SKIP odd ticker name"; continue; }
  if docker run --rm --security-opt seccomp=unconfined --network container:trader-ib-gateway --user 1043:100 \
       -e HOME=/tmp -e PYTHONPATH=/app:/deps -e SEC_CONTACT="$SEC_CONTACT" \
       -v /volume1/docker/trader/deps:/deps:ro -v "$DESK/app":/app:ro -v "$DESK/var":/app/var -w /app \
       python:3.12-slim python -m desk.prepare "$T" --date "$DATE" >> "$LOG" 2>&1; then
    ok=$((ok+1)); consecutive=0
  else
    failed="$failed $T"; consecutive=$((consecutive+1)); say "FAILED $T"
    if [ "$consecutive" -ge 3 ]; then say "STOP: 3 failures in a row (Gateway down?)"; break; fi
  fi
done
say "END prepared $ok, failed:${failed:- none}"
if [ -n "$failed" ]; then
  alert "Desk prepare $DATE: $ok ok, failed:$failed.${macro_failed:+ Macro closes failed too.} See $LOG. A Gateway dialog (IBKR 10141) needs: sudo docker restart trader-ib-gateway"
  exit 1
fi
if [ -n "$macro_failed" ]; then
  alert "Desk prepare $DATE: $ok stocks ok, but the macro closes failed (the analyst falls back to web search). See $LOG."
  exit 1
fi
exit 0
