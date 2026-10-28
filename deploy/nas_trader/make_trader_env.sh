#!/bin/bash
# W10-0013 sub 4: builds /volume1/docker/trader/.env from .env.example by asking for the three secrets.
# Nothing is shown on screen or stored anywhere else. Run:  bash /volume1/docker/make_trader_env.sh
set -u
DIR="${TRADER_DIR:-/volume1/docker/trader}"
REC_ENV="${RECORDER_ENV:-/volume1/docker/trade-journal/.env}"
[ -f "$DIR/.env.example" ] || { echo "No $DIR/.env.example - unpack the package first (step D)."; exit 1; }
if [ -f "$DIR/.env" ]; then
  read -r -p ".env already exists. Overwrite it? (yes/no) " a
  [ "$a" = "yes" ] || { echo "Left unchanged."; exit 0; }
fi
read -r -p "Paper IBKR username: " U
read -r -s -p "Paper IBKR password: " P; echo
read -r -s -p "Choose a VNC password (any): " V; echo
for v in "$U" "$P" "$V"; do
  case "$v" in
    ""|*"'"*|*\\*) echo "Empty value, or it contains ' or \\ - not supported here. Nothing written."; exit 1;;
  esac
done
IMG="$(sudo grep '^IB_GATEWAY_IMAGE=' "$REC_ENV" | cut -d= -f2-)"
[ -n "$IMG" ] || echo "NOTE: the recorder's .env has no IB_GATEWAY_IMAGE pin; this Gateway will follow the 'stable' tag."
export U P V IMG
awk '
/^TWS_USERID=/          {print "TWS_USERID=\047" ENVIRON["U"] "\047"; next}
/^TWS_PASSWORD=/        {print "TWS_PASSWORD=\047" ENVIRON["P"] "\047"; next}
/^VNC_SERVER_PASSWORD=/ {print "VNC_SERVER_PASSWORD=\047" ENVIRON["V"] "\047"; next}
/^IB_GATEWAY_IMAGE=/    {print "IB_GATEWAY_IMAGE=" ENVIRON["IMG"]; next}
{print}' "$DIR/.env.example" > "$DIR/.env.new" && mv "$DIR/.env.new" "$DIR/.env"
chmod 600 "$DIR/.env"
unset U P V IMG
echo "Written $DIR/.env (mode 600). Passwords hidden below:"
sed -E "s/^(TWS_PASSWORD|VNC_SERVER_PASSWORD)=.*/\1=<hidden>/" "$DIR/.env" | grep -E '^(TWS_USERID|TWS_PASSWORD|VNC_SERVER_PASSWORD|IB_GATEWAY_IMAGE|VNC_HOST_PORT|GATEWAY_SETTINGS_DIR)='
