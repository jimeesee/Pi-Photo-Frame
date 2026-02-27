#!/usr/bin/env bash
set -euo pipefail

LOG="$HOME/Pi_Photo_Frame/logs/autostart.log"
mkdir -p "$(dirname "$LOG")"

LOCK="/tmp/pi_photo_frame_viewer.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date '+%F %T') [INFO] start_viewer: already running (lockfile $LOCK)" >> "$LOG"
  exit 0
fi

DISPLAY="${DISPLAY:-:0}"
XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
XDG_SESSION_TYPE="${XDG_SESSION_TYPE:-}"

echo "$(date '+%F %T') [INFO] start_viewer: pid=$$ DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-unset}" >> "$LOG"

# Secondary guard in case a stale process exists.
if pgrep -u "$(id -u)" -af "src.viewer.main" >/dev/null 2>&1; then
  echo "$(date '+%F %T') [INFO] start_viewer: viewer already running (pgrep guard); exiting." >> "$LOG"
  exit 0
fi

cd "$HOME/Pi_Photo_Frame"
VENV_PY="/home/jimbo/Pi_Photo_Frame/.venv/bin/python"
CFG="/home/jimbo/Pi_Photo_Frame/config/local.yaml"
CMD="$VENV_PY -m src.viewer.main --config $CFG"

if [[ ! -x "$VENV_PY" ]]; then
  echo "$(date '+%F %T') [ERROR] start_viewer: missing venv python at $VENV_PY (recreate venv: python3 -m venv /home/jimbo/Pi_Photo_Frame/.venv)" >> "$LOG"
  exit 1
fi
if [[ ! -f "$CFG" ]]; then
  echo "$(date '+%F %T') [ERROR] start_viewer: missing config at $CFG" >> "$LOG"
  exit 1
fi

echo "$(date '+%F %T') [INFO] start_viewer: launching: $CMD" >> "$LOG"

exec /usr/bin/env DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" $CMD >> "$LOG" 2>&1
