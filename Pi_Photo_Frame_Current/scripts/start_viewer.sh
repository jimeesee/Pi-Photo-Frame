#!/usr/bin/env bash
set -euo pipefail

LOG="$HOME/Pi_Photo_Frame/logs/autostart.log"
echo "===== start_viewer.sh $(date) =====" >> "$LOG"

if pgrep -af "src.viewer.main" >/dev/null 2>&1; then
  echo "Viewer already running; not starting another." >> "$LOG"
  exit 0
fi

export DISPLAY=:0
export XAUTHORITY="$HOME/.Xauthority"
export XDG_SESSION_TYPE=x11

cd "$HOME/Pi_Photo_Frame"

"$HOME/Pi_Photo_Frame/.venv/bin/python" -m src.viewer.main \
  --config "$HOME/Pi_Photo_Frame/config/local.yaml" >> "$LOG" 2>&1
