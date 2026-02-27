#!/usr/bin/env bash
# deploy.sh — Deploy touch swipe daemon to Pi Photo Frame
#
# Usage:  ./deploy.sh [pi_host]
#   pi_host defaults to "pi@piframe.local"
#
# What it does:
#   1. Copies touch_daemon.py to ~/touch_daemon/ on the Pi
#   2. Creates a Python venv and installs evdev
#   3. Installs the systemd user service
#   4. Sets picframe input_type to "keyboard"
#   5. Enables and starts the daemon
set -euo pipefail

PI_HOST="${1:-pi@raspberrypi.local}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Deploying touch daemon to ${PI_HOST}"

# ── 1. Copy daemon script ────────────────────────────────────────
echo "--- Copying touch_daemon.py"
ssh "$PI_HOST" "mkdir -p ~/touch_daemon"
scp "$SCRIPT_DIR/touch_daemon.py" "$PI_HOST:~/touch_daemon/touch_daemon.py"

# ── 2. Create venv and install evdev ──────────────────────────────
echo "--- Setting up Python venv and installing evdev"
ssh "$PI_HOST" bash <<'REMOTE_VENV'
set -euo pipefail
if [ ! -d ~/touch_daemon_venv ]; then
    python3 -m venv ~/touch_daemon_venv
fi
~/touch_daemon_venv/bin/pip install --quiet --upgrade pip
~/touch_daemon_venv/bin/pip install --quiet evdev
echo "evdev installed: $(~/touch_daemon_venv/bin/pip show evdev | grep Version)"
REMOTE_VENV

# ── 3. Install systemd user service ──────────────────────────────
echo "--- Installing systemd service"
scp "$SCRIPT_DIR/touch_daemon.service" "$PI_HOST:/tmp/touch_daemon.service"
ssh "$PI_HOST" bash <<'REMOTE_SVC'
set -euo pipefail
mkdir -p ~/.config/systemd/user
mv /tmp/touch_daemon.service ~/.config/systemd/user/touch_daemon.service
systemctl --user daemon-reload
REMOTE_SVC

# ── 4. Update picframe config: input_type → keyboard ─────────────
echo "--- Setting picframe input_type to keyboard"
ssh "$PI_HOST" bash <<'REMOTE_CFG'
set -euo pipefail
CFG=~/picframe_data/config/configuration.yaml
if grep -q 'input_type:' "$CFG"; then
    sed -i 's/input_type:.*/input_type: "keyboard"/' "$CFG"
    echo "Updated input_type to keyboard"
else
    echo "WARNING: input_type not found in $CFG — add it manually under peripherals:"
fi
REMOTE_CFG

# ── 5. Enable and start the daemon ───────────────────────────────
echo "--- Enabling and starting touch_daemon service"
ssh "$PI_HOST" bash <<'REMOTE_START'
set -euo pipefail
systemctl --user enable touch_daemon.service
systemctl --user restart touch_daemon.service
sleep 1
systemctl --user status touch_daemon.service --no-pager || true
REMOTE_START

echo ""
echo "==> Deploy complete!"
echo "    - Touch daemon is running as a systemd user service"
echo "    - picframe input_type set to 'keyboard'"
echo ""
echo "Next steps:"
echo "  1. Restart picframe:  ssh $PI_HOST 'sudo systemctl restart picframe'"
echo "  2. Test swipes on the touchscreen"
echo "  3. Check logs:  ssh $PI_HOST 'journalctl --user -u touch_daemon -f'"
echo "  4. Adjust thresholds by editing ~/touch_daemon/touch_daemon.py args"
echo "     or override in the service file ExecStart line"
