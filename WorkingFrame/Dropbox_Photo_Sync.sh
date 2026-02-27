#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

exec "$PY" "$HERE/Dropbox_Photo_Sync.py" "$@"

