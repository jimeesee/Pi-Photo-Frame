#!/usr/bin/env bash
# Placeholder helper to append the viewer command to LXDE autostart.
# Updates ~/.config/lxsession/LXDE-pi/autostart with the viewer launch line.

set -euo pipefail

TARGET="${HOME}/.config/lxsession/LXDE-pi/autostart"
CMD='@/home/jimbo/Pi_Photo_Frame/scripts/start_viewer.sh'

mkdir -p "$(dirname "${TARGET}")"
if ! grep -Fq "${CMD}" "${TARGET}" 2>/dev/null; then
  echo "${CMD}" >> "${TARGET}"
  echo "[autostart] Added viewer entry to ${TARGET}"
else
  echo "[autostart] Entry already present in ${TARGET}"
fi
