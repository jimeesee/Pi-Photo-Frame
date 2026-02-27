# Bug Fixes

Use this document to track debugging steps, checks, and resolutions for project issues. Fill in as new problems arise.

## Template for Issues
- **Issue summary:**
- **Environment:** (Pi model, OS version, display details)
- **Logs/observations:**
- **Steps to reproduce:**
- **Initial checks:**
- **Hypothesis:**
- **Fix:**
- **Validation steps:**
- **Notes/Follow-ups:**

## Common Quick Checks
- `systemctl status pi-dropbox-sync.service` and `journalctl -u pi-dropbox-sync --no-pager | tail` for sync issues.
- Verify `.env` has Dropbox settings:
  - Preferred: `DROPBOX_REFRESH_TOKEN`, `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_FOLDER`
  - Legacy: `DROPBOX_TOKEN` + `DROPBOX_FOLDER`
- Ensure `cache/photos` contains media; otherwise viewer will show blank screen fallback.
- Confirm autostart entry exists in `~/.config/lxsession/LXDE-pi/autostart` and points to the correct venv path.
- Run viewer manually: `/home/jimbo/Pi_Photo_Frame/.venv/bin/python -m src.viewer.main --config /home/jimbo/Pi_Photo_Frame/config/local.yaml` and watch stdout/logs.

Add detailed steps per issue below as they occur.

## Fix Playbook (Pi 5, user=jimbo, host=piFrame)

### 1) Deploy latest code and permissions
- Sync repo to Pi: `rsync -avz --exclude '.venv' --exclude '__pycache__' ./ jimbo@piFrame:/home/jimbo/Pi_Photo_Frame/`
- Ensure executable bits: `chmod +x /home/jimbo/Pi_Photo_Frame/scripts/start_viewer.sh`
- Sanity check: `python3 -m py_compile /home/jimbo/Pi_Photo_Frame/src/viewer/main.py /home/jimbo/Pi_Photo_Frame/scripts/sync_dropbox.py`
- If venv is missing: `cd /home/jimbo/Pi_Photo_Frame && python3 -m venv .venv && ./.venv/bin/python -m pip install -U pip && ./.venv/bin/python -m pip install -r requirements.txt`

### 2) Single-instance viewer + autostart
- Autostart file should contain only: `@/home/jimbo/Pi_Photo_Frame/scripts/start_viewer.sh`
- Verify: `ssh jimbo@piFrame 'cat ~/.config/lxsession/LXDE-pi/autostart'`
- Stop stale viewers: `ssh jimbo@piFrame 'pkill -f "src.viewer.main" || true'`
- Manual start (LXDE/X11): `ssh jimbo@piFrame 'DISPLAY=:0 XAUTHORITY=/home/jimbo/.Xauthority /home/jimbo/Pi_Photo_Frame/.venv/bin/python -m src.viewer.main --config /home/jimbo/Pi_Photo_Frame/config/local.yaml'`
- Check single instance: `ssh jimbo@piFrame 'pgrep -af "src.viewer.main"'`
- Tail viewer logs: `ssh jimbo@piFrame 'tail -f /home/jimbo/Pi_Photo_Frame/logs/viewer.log'`
- Tail autostart logs: `ssh jimbo@piFrame 'tail -f /home/jimbo/Pi_Photo_Frame/logs/autostart.log'`

### 3) Dropbox sync token loading
- Ensure `.env` on Pi has Dropbox credentials (preferred refresh-token set, or legacy access token) and `DROPBOX_FOLDER`.
- Run once to confirm load: `ssh jimbo@piFrame '/home/jimbo/Pi_Photo_Frame/.venv/bin/python /home/jimbo/Pi_Photo_Frame/scripts/sync_dropbox.py --once'`
- Review logs: `ssh jimbo@piFrame 'tail -f /home/jimbo/Pi_Photo_Frame/logs/sync.log'`
- If token not found, re-open `.env` (no quotes/extra whitespace); file must be readable by user `jimbo`.

### 4) LXSession quoting and X display
- Check autostart for stray quotes/backticks: `ssh jimbo@piFrame 'cat ~/.config/lxsession/LXDE-pi/autostart'`
- Check LXSession run log: `ssh jimbo@piFrame 'tail -n 50 ~/.cache/lxsession/LXDE-pi/run.log'`
- X vars used: `DISPLAY=:0`, `XAUTHORITY=/home/jimbo/.Xauthority`, `XDG_SESSION_TYPE=x11`; ensure you run under the logged-in LXDE session.

### 5) GPU/GL sanity on Pi 5
- GPU mem: `ssh jimbo@piFrame 'vcgencmd get_mem gpu'` (Pi 5/Bookworm may show low; GL uses CMA).
- GL info: `ssh jimbo@piFrame 'glxinfo | grep OpenGL'` (install `mesa-utils` if missing).
- Boot config audit: `ssh jimbo@piFrame 'sudo cat /boot/firmware/config.txt'`; confirm `dtoverlay=vc4-kms-v3d` (or similar). Only add `gpu_mem=128` if GL apps fail.

### 6) Systemd sync service
- Service uses venv: `/home/jimbo/Pi_Photo_Frame/.venv/bin/python /home/jimbo/Pi_Photo_Frame/scripts/sync_dropbox.py`
- Status: `ssh jimbo@piFrame 'systemctl status pi-dropbox-sync.service'`
- Logs: `ssh jimbo@piFrame 'journalctl -u pi-dropbox-sync --no-pager | tail'`
- Restart after updates: `ssh jimbo@piFrame 'sudo systemctl daemon-reload && sudo systemctl restart pi-dropbox-sync.service'`

### 7) Black screen triage
- Confirm single instance (step 2), and that images exist: `ssh jimbo@piFrame 'ls /home/jimbo/Pi_Photo_Frame/cache/photos | head'`
- Heartbeats: `ssh jimbo@piFrame 'grep "Render heartbeat" /home/jimbo/Pi_Photo_Frame/logs/viewer.log | tail'`
- If still black, run viewer manually with DISPLAY/XAUTHORITY to capture stdout/stderr.
- Reboot smoke: `ssh jimbo@piFrame 'sudo reboot'`, then tail autostart/viewer logs after login.
