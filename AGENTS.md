# Repository Guidelines

## Project Structure & Module Organization
- Runtime lives in `src/`; entry module `src/viewer/main.py`.
- `scripts/` for provisioning helpers (sync, cache bootstrap, autostart writer).
- `systemd/` holds units like `pi-dropbox-sync.service`; logs in `logs/`; git-ignore `cache/photos`; assets in `assets/`.
- Tests mirror `src/` under `tests/`; sample configs stay tracked (e.g., `config/example.env`); secrets stay only in `.env`.

## Target Platform & Boot Behavior
- Raspberry Pi 5 (8GB) on Raspberry Pi OS (Desktop, not Lite).
- HDMI display attached; viewer launches fullscreen on login.
- Viewer is Python + pi3d.
- Autostart via LXDE autostart by adding the entry to `~/.config/lxsession/LXDE-pi/autostart`.

## Build, Test, and Run Commands
- Create venv (on the Pi; don’t copy `.venv` between machines): `python3 -m venv .venv`
- Install deps: `./.venv/bin/python -m pip install -U pip && ./.venv/bin/python -m pip install -r requirements.txt`
- `./.venv/bin/python -m pytest tests` (add `-q` for terse runs).
- `./.venv/bin/python -m src.viewer.main --config config/local.yaml` to launch manually.
- `sudo systemctl status pi-dropbox-sync.service` for sync health.

## Coding Style & Naming Conventions
- Python 3.11+; format with black (88 cols) and isort, lint with flake8 or ruff before commits.
- snake_case for modules/functions, PascalCase for classes, ALL_CAPS for constants; keep hardware bindings behind interfaces for mocking.

## Testing Guidelines
- Pytest files named `test_*.py`; fixtures in `conftest.py`.
- Mark hardware-dependent cases (e.g., `@pytest.mark.hardware`) so CI skips them; prioritize playlist/cache logic.
- Aim for >=80% coverage on `src/`; note intentional gaps.

## Sync & Offline Behavior
- Dropbox sync pulls the remote folder into `cache/photos`; slideshow continues offline and resumes when back online.
- Systemd service should retry with backoff; log to `logs/sync.log` and `journalctl -u pi-dropbox-sync`.
- Env vars loaded from `.env`; preferred: `DROPBOX_REFRESH_TOKEN`, `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_FOLDER` (legacy: `DROPBOX_TOKEN`).
- Keep secrets out of git.

## Commit & Pull Request Guidelines
- Conventional commits (`feat: ...`, `fix: ...`, `chore: ...`); keep PRs focused and linked to issues.
- Describe behavior changes, list test commands run, and attach device screenshots when visuals change.

## TODO Checklist (Fresh OS Install)
- Flash Raspberry Pi OS Desktop on Pi 5; enable SSH, set locale/timezone, join Wi-Fi.
- `sudo apt update && sudo apt install python3-venv git` (add GL extras if prompted).
- Clone to `~/Pi_Photo_Frame`, create `.venv`, install requirements, copy `.env.example` -> `.env` with Dropbox credentials.
- Make writable `cache/photos`; add autostart entry to `~/.config/lxsession/LXDE-pi/autostart`.
- Place `pi-dropbox-sync.service` in `/etc/systemd/system/`, then `sudo systemctl enable --now pi-dropbox-sync`.
- Run slideshow once, reboot to confirm fullscreen autostart, and tail logs to verify sync/viewer are healthy.
