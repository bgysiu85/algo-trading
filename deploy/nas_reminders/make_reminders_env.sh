#!/bin/bash
# W11-0041 sub 9: builds /volume1/docker/reminders/reminders.env (mode 600) by asking for the three secrets.
# The Telegram bot settings are copied from the trader's .env (read with sudo). Nothing is shown on screen.
# Run on the NAS:  bash /volume1/docker/reminders/make_reminders_env.sh
set -u
DIR="${REMINDERS_DIR:-/volume1/docker/reminders}"
TRADER_ENV="${TRADER_ENV:-/volume1/docker/trader/.env}"
OUT="$DIR/reminders.env"
if [ -f "$OUT" ]; then
  read -r -p "$OUT already exists. Overwrite it? (yes/no) " a
  [ "$a" = "yes" ] || { echo "Left unchanged."; exit 0; }
fi
read -r -s -p "monday Reminders calendar feed link (the one you sent to your iPhone): " F; echo
read -r -s -p "monday API token: " M; echo
read -r -s -p "Password of the DSM user calendar-monday: " P; echo
for v in "$F" "$M" "$P"; do
  case "$v" in
    ""|*"'"*|*\\*) echo "Empty value, or it contains ' or \\ - not supported here. Nothing written."; exit 1;;
  esac
done
case "$F" in
  webcal://*) F="https://${F#webcal://}";;      # monday gives webcal:// links; it is the same address over https
  https://*) ;;
  *) echo "The feed link must start with webcal:// or https://. Nothing written."; exit 1;;
esac
TT="$(sudo grep -E '^TELEGRAM_BOT_TOKEN=' "$TRADER_ENV" 2>/dev/null | head -1 | cut -d= -f2- | sed -e "s/^'//" -e "s/'$//")"
TC="$(sudo grep -E '^TELEGRAM_CHAT_ID=' "$TRADER_ENV" 2>/dev/null | head -1 | cut -d= -f2- | sed -e "s/^'//" -e "s/'$//")"
[ -n "$TT" ] && [ -n "$TC" ] || echo "NOTE: no Telegram settings found in $TRADER_ENV; the Telegram backup will not be sent."
umask 077
TMP="$(mktemp)" || { echo "Could not make a temporary file. Nothing written."; exit 1; }
{
  echo "# W11-0041 reminders sync. Mode 600. Never copy this file into the repo."
  echo "REMINDERS_FEED_URL='$F'"
  echo "MONDAY_API_TOKEN='$M'"
  echo "CALDAV_PASSWORD='$P'"
  echo "CALDAV_USER='calendar-monday'"
  echo "CALDAV_URL='https://siuds.synology.me:38443/caldav/'"
  echo "CALDAV_CONNECT_HOST='127.0.0.1'"
  echo "CALDAV_TASK_LIST='monday reminders'"
  echo "REMINDERS_BOARD_ID='5032297480'"
  echo "TELEGRAM_BOT_TOKEN='$TT'"
  echo "TELEGRAM_CHAT_ID='$TC'"
} > "$TMP"
# The folder is root's (the tar was unpacked with sudo), so the file is placed with sudo and owned by root, mode 600.
if ! { sudo mv "$TMP" "$OUT" && sudo chown root:root "$OUT" && sudo chmod 600 "$OUT"; }; then
  rm -f "$TMP"; unset F M P TT TC
  echo "Could not write $OUT. Nothing written."; exit 1
fi
unset F M P TT TC
echo "Written $OUT (mode 600, owned by root). Secrets hidden below:"
sudo sed -E "s/^(REMINDERS_FEED_URL|MONDAY_API_TOKEN|CALDAV_PASSWORD|TELEGRAM_BOT_TOKEN)=.*/\1=<hidden>/" "$OUT"
sudo ls -l "$OUT"
