#!/bin/bash
# Pre-session API check for the NAS paper IB Gateway (W10-0013 sub 16). For DSM Task Scheduler (run as root).
#
#   api_precheck.sh check            one check, Telegram on failure only      -> use before the window (alert only)
#   api_precheck.sh check-restart    check; on failure restart the Gateway ONCE, wait, check again
#                                    (refused while trader-trader is running)  -> use BEFORE the trader starts
# Anything after the mode goes to api_precheck.py, e.g. a safe alarm test:  api_precheck.sh check --port 7497 --attempts 1 --label "TEST"
#
# The check itself is api_precheck.py (a real read-only API session), run inside the Gateway's network so nothing is
# published. Output is appended to precheck.log in the trader folder as well as printed.
# Settings (environment, all optional): PRECHECK_NOTIFY_OK=yes|no (default yes: a short "OK" so a silent task is noticed),
# PRECHECK_WAIT_S (wait after a restart, default 240), PRECHECK_LABEL, TRADER_DIR (tests only).
set -u
export PATH="$PATH:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"      # DSM tasks start with a thin PATH; docker lives in /usr/local/bin
MODE="${1:-check}"; [ $# -gt 0 ] && shift
EXTRA=("$@")                       # optional extra api_precheck.py arguments
DIR="${TRADER_DIR:-/volume1/docker/trader}"      # TRADER_DIR is only for the tests
LOG="$DIR/precheck.log"
GATEWAY=trader-ib-gateway
IMAGE=trade-journal-recorder:latest
WAIT_S="${PRECHECK_WAIT_S:-240}"
NOTIFY_OK="${PRECHECK_NOTIFY_OK:-yes}"
export PRECHECK_LABEL="${PRECHECK_LABEL:-$MODE}"

case "$MODE" in check|check-restart) ;; *) echo "usage: $0 check|check-restart" >&2; exit 2;; esac

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

# Only the two Telegram values are passed on (not the whole .env: it holds the IBKR password).
getenv_key() { grep -E "^$1=" "$DIR/.env" 2>/dev/null | head -1 | cut -d= -f2- | sed -e "s/^'//" -e "s/'$//"; }
TELEGRAM_BOT_TOKEN="$(getenv_key TELEGRAM_BOT_TOKEN)"; TELEGRAM_CHAT_ID="$(getenv_key TELEGRAM_CHAT_ID)"
export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID

run_check() {   # $@ = extra api_precheck.py arguments
    docker run --rm --security-opt seccomp=unconfined --network "container:$GATEWAY" \
        -e TELEGRAM_BOT_TOKEN -e TELEGRAM_CHAT_ID -e PRECHECK_LABEL \
        -v "$DIR/api_precheck.py:/precheck.py:ro" --entrypoint python "$IMAGE" /precheck.py "$@" ${EXTRA[@]+"${EXTRA[@]}"} 2>&1 | tee -a "$LOG"
    return "${PIPESTATUS[0]}"
}

OKFLAG=""; [ "$NOTIFY_OK" = "yes" ] && OKFLAG="--notify-ok"

if [ "$MODE" = "check" ]; then
    log "check: start"
    run_check $OKFLAG; rc=$?
    log "check: exit $rc"
    exit $rc
fi

# check-restart
log "check-restart: first pass (no message yet)"
run_check --no-notify; rc=$?
if [ $rc -eq 0 ]; then
    log "check-restart: API fine, no restart needed"
    run_check $OKFLAG; exit $?                      # a second quick pass only to send the OK message
fi
if [ "$(docker inspect -f '{{.State.Running}}' trader-trader 2>/dev/null)" = "true" ]; then
    log "check-restart: API failed but trader-trader is RUNNING - not restarting the Gateway under it; alerting"
    run_check --note "The Gateway was NOT restarted because the trader is running." ; exit 1
fi
log "check-restart: API failed (exit $rc) and the trader is not running - restarting $GATEWAY once, waiting ${WAIT_S}s"
docker restart "$GATEWAY" >/dev/null 2>&1 || log "check-restart: docker restart reported an error"
sleep "$WAIT_S"
run_check --note "After one automatic Gateway restart." $OKFLAG; rc=$?
log "check-restart: exit $rc"
exit $rc
