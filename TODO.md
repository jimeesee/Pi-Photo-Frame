# Pi Photo Frame TODO (Fresh Install)

## 1. Prepare Raspberry Pi OS Desktop (Pi 5, 8GB)
- Flash Raspberry Pi OS Desktop (not Lite) to microSD using Raspberry Pi Imager.
- On first boot: set locale/timezone/keyboard, create user, enable SSH, join Wi‑Fi.
- Update base system: `sudo apt update && sudo apt full-upgrade -y` then reboot.

## 2. Install System Packages
- `sudo apt install -y python3 python3-venv python3-pip git unzip`.
- Install GL/graphics stack if prompted by raspi-config; ensure HDMI display is active at native resolution.

## 3. Clone Repository
- `mkdir -p ~/Pi_Photo_Frame && cd ~/Pi_Photo_Frame`
- `git clone <repo-url> .`

## 4. Transfer Code via VS Code Remote SSH
- Install VS Code + the “Remote Development” extension pack on your laptop.
- Add an SSH target for the Pi (e.g., `pi@<pi-ip>`); connect with `Remote-SSH: Connect to Host...`.
- In VS Code Explorer, open `/home/jimbo/Pi_Photo_Frame` on the Pi. If you cloned locally instead, upload via the Explorer “Upload” action or run: `scp -r . pi@<pi-ip>:/home/jimbo/Pi_Photo_Frame`.
- Confirm permissions: `ls -la /home/jimbo/Pi_Photo_Frame` on the Pi; ensure files are owned by `jimbo`.
- Do not transfer `.venv/` from another machine (Mac/PC); always create it on the Pi.

## 5. Python Environment
- `python3 -m venv .venv`
- `./.venv/bin/python -m pip install --upgrade pip`
- `./.venv/bin/python -m pip install -r requirements.txt`

## 6. Configuration
- Copy env template: `cp config/example.env .env`; fill Dropbox settings (do not commit secrets):
  - Preferred: `DROPBOX_REFRESH_TOKEN`, `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_FOLDER`
  - Legacy: `DROPBOX_TOKEN` + `DROPBOX_FOLDER`
- Create cache directory: `mkdir -p cache/photos`
- Ensure `logs/` exists and is writable: `mkdir -p logs`
- Confirm main entry: `src/viewer/main.py`; test command `./.venv/bin/python -m src.viewer.main --config config/local.yaml`

## 7. Dropbox Setup (Folder + API token)
- In Dropbox web: create (or choose) a folder to sync, e.g. `/Photos/PiFrame`, and add photos.
- If the folder lives in another account, share it to the Pi’s Dropbox account email and accept the invite so it appears in root.
- Create an app token for long-term access:
  - Go to https://www.dropbox.com/developers/apps and create a Scoped Access app (App folder or Full Dropbox as needed).
  - Under Permissions, enable `files.metadata.read` and `files.content.read`.
  - In Settings (OAuth 2), create a refresh token (preferred over short-lived access tokens).
  - Put these in `/home/jimbo/Pi_Photo_Frame/.env`:
    - `DROPBOX_REFRESH_TOKEN` (refresh token)
    - `DROPBOX_APP_KEY` and `DROPBOX_APP_SECRET` (from the Dropbox app page)
    - `DROPBOX_FOLDER=/Photos/PiFrame` (or your path)
- (If you must use a short-lived token temporarily, note it will expire; replace with a refresh token for stable operation.)
- Update Dropbox references in the repo:
  - `.env`: set `DROPBOX_REFRESH_TOKEN`, `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_FOLDER` (local only; never commit).
  - (Legacy) `.env`: you can instead set `DROPBOX_TOKEN` + `DROPBOX_FOLDER`.
  - `config/example.env`: keep as documentation only; do not add real secrets.
  - `systemd/pi-dropbox-sync.service`: uses `/home/jimbo/Pi_Photo_Frame/.env`; adjust paths only if your install dir/user differs.
  - `scripts/sync_dropbox.py`: reads env vars; no code edits needed once `.env` is set.
  - To find all references, run `rg "DROPBOX"` from repo root.
  - To get the exact folder path, in Dropbox web right-click the folder > Share > Copy Dropbox link; extract the path portion (e.g., `/Photos/PiFrame`) and use it for `DROPBOX_FOLDER`.
  - To regenerate tokens later, return to your Dropbox app (Settings > OAuth 2) and issue a new refresh-capable token for `.env`.

## 8. Dropbox Sync Service (systemd, system-level)
- Copy service file: `sudo cp systemd/pi-dropbox-sync.service /etc/systemd/system/pi-dropbox-sync.service`
- Reload units: `sudo systemctl daemon-reload`
- Enable + start: `sudo systemctl enable --now pi-dropbox-sync.service`
- Verify: `sudo systemctl status pi-dropbox-sync.service` and `journalctl -u pi-dropbox-sync -f`

## 9. Desktop Autostart (LXDE)
- Edit `~/.config/lxsession/LXDE-pi/autostart` and append a line to run the viewer on login, e.g.:
  - `@/home/jimbo/Pi_Photo_Frame/scripts/start_viewer.sh`
- Confirm file is readable and executable by the desktop session user.

## 10. First Run & Validation
- Run manually: `DISPLAY=:0 XAUTHORITY=/home/jimbo/.Xauthority /home/jimbo/Pi_Photo_Frame/.venv/bin/python -m src.viewer.main --config /home/jimbo/Pi_Photo_Frame/config/local.yaml`
- Confirm fullscreen slideshow on HDMI; verify images load from `cache/photos`.
- Disconnect network to confirm offline playback continues; reconnect and check sync resumes.
- Check logs: `tail -n 100 logs/sync.log` and `journalctl -u pi-dropbox-sync --no-pager | tail`

## 11. Reboot Smoke Test
- Reboot: `sudo reboot`
- After login, confirm viewer autostarts fullscreen and Dropbox sync is active (`sudo systemctl status pi-dropbox-sync.service`).

## 12. Maintenance
- Update app: `git pull` then reinstall deps if `requirements.txt` changed.
- Rotate logs as needed (add a cron or logrotate snippet if growth is high).
- Keep `.env` and `cache/photos` backed up if desired; never commit secrets.
