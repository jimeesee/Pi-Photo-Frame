"""Sync a Dropbox folder to a local photo directory (Raspberry Pi-friendly).

Defaults:
- Remote: DROPBOX_FOLDER (or "/")
- Local: /home/pi/pictures
- Auth: OAuth refresh token (preferred) or legacy access token

This script is intentionally self-contained: it can load a `.env` file without
requiring extra packages.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Set, Tuple

try:
    import dropbox
    from dropbox.files import FileMetadata, ListFolderResult
except Exception:  # pragma: no cover - handled at runtime
    dropbox = None  # type: ignore
    FileMetadata = ListFolderResult = None  # type: ignore


EXIT_NO_DROPBOX = 2
EXIT_NO_CREDS = 3


@dataclass
class SyncConfig:
    remote_folder: str
    local_dir: Path
    loop_seconds: int
    delete_removed: bool
    log_file: Path
    log_level: str
    online_check_host: str = "1.1.1.1"
    online_check_port: int = 53
    online_timeout: float = 2.0
    state_file: Path | None = None

    # Auth (prefer refresh token; fall back to access token)
    refresh_token: str | None = None
    app_key: str | None = None
    app_secret: str | None = None
    access_token: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dropbox photo folder sync")
    parser.add_argument("--once", action="store_true", help="Run one pass then exit.")
    parser.add_argument("--env-file", type=Path, default=None, help="Path to .env file (default: ./WorkingFrame/.env).")
    parser.add_argument("--remote-folder", type=str, default=None, help="Dropbox folder path (default: DROPBOX_FOLDER or /).")
    parser.add_argument("--local-dir", type=Path, default=None, help="Local target dir (default: LOCAL_PHOTO_DIR or /home/pi/pictures).")
    parser.add_argument("--loop-seconds", type=int, default=None, help="Seconds between passes (default: SYNC_LOOP_SECONDS or 120).")
    parser.add_argument(
        "--delete-removed",
        action="store_true",
        help="Delete local files that no longer exist in Dropbox folder.",
    )
    parser.add_argument("--log-file", type=Path, default=None, help="Log file path (default: LOG_FILE or ./Dropbox_Photo_Sync.log).")
    parser.add_argument("--state-file", type=Path, default=None, help="State JSON path (default: <log_dir>/.dropbox_sync_state.json).")
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    """Minimal .env loader (no python-dotenv dependency)."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def normalize_remote_folder(path: str) -> str:
    path = (path or "/").strip()
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path


def configure_logging(log_file: Path, level: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file)],
    )


def is_online(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def load_state(path: Path) -> Dict[str, Dict[str, object]]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logging.warning("State file unreadable; ignoring: %s", path)
        return {}


def save_state(path: Path, state: Dict[str, Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def create_dropbox_client(cfg: SyncConfig) -> "dropbox.Dropbox":
    if cfg.refresh_token and cfg.app_key and cfg.app_secret:
        return dropbox.Dropbox(
            oauth2_refresh_token=cfg.refresh_token,
            app_key=cfg.app_key,
            app_secret=cfg.app_secret,
            timeout=30,
        )
    if cfg.access_token:
        return dropbox.Dropbox(cfg.access_token, timeout=30)
    raise ValueError("No Dropbox credentials configured")


def list_files(dbx: "dropbox.Dropbox", remote_folder: str) -> List[FileMetadata]:
    files: List[FileMetadata] = []
    result: ListFolderResult = dbx.files_list_folder(remote_folder, recursive=True)
    files.extend([e for e in result.entries if isinstance(e, FileMetadata)])
    while result.has_more:
        result = dbx.files_list_folder_continue(result.cursor)
        files.extend([e for e in result.entries if isinstance(e, FileMetadata)])
    return files


def local_path_for_entry(remote_root: str, entry_path_lower: str, local_root: Path) -> Path:
    root_lower = remote_root.lower().rstrip("/")
    path_lower = entry_path_lower
    if root_lower and path_lower.startswith(root_lower + "/"):
        rel = path_lower[len(root_lower) + 1 :]
    elif root_lower and path_lower == root_lower:
        rel = ""
    else:
        rel = path_lower.lstrip("/")
    rel_posix = PurePosixPath(rel)
    if rel_posix.is_absolute() or ".." in rel_posix.parts:
        raise ValueError(f"Unsafe Dropbox path: {entry_path_lower}")
    return local_root.joinpath(*rel_posix.parts)


def should_download(entry: FileMetadata, local: Path, state: Dict[str, Dict[str, object]]) -> bool:
    if not local.exists():
        return True
    previous = state.get(entry.path_lower)
    if previous and isinstance(previous.get("rev"), str) and previous.get("rev") == entry.rev:
        return False
    return True


def download_file(dbx: "dropbox.Dropbox", entry: FileMetadata, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    dbx.files_download_to_file(str(tmp), entry.path_lower)
    tmp.replace(target)
    mtime = entry.client_modified.timestamp()
    os.utime(target, (mtime, mtime))


def sync_once(cfg: SyncConfig, state_path: Path) -> None:
    cfg.local_dir.mkdir(parents=True, exist_ok=True)

    dbx = create_dropbox_client(cfg)
    files = list_files(dbx, cfg.remote_folder)
    state = load_state(state_path)

    remote_paths: Set[str] = set()
    downloaded = 0
    for entry in files:
        remote_paths.add(entry.path_lower)
        target = local_path_for_entry(cfg.remote_folder, entry.path_lower, cfg.local_dir)
        if not target.name:
            continue
        if should_download(entry, target, state):
            download_file(dbx, entry, target)
            state[entry.path_lower] = {
                "rev": entry.rev,
                "size": entry.size,
                "client_modified": entry.client_modified.isoformat(),
                "local": str(target),
            }
            downloaded += 1
            logging.info("Synced %s (%d bytes)", target, entry.size)

    if cfg.delete_removed:
        removed = 0
        for path_lower in list(state.keys()):
            if path_lower in remote_paths:
                continue
            try:
                local = local_path_for_entry(cfg.remote_folder, path_lower, cfg.local_dir)
            except Exception:
                state.pop(path_lower, None)
                continue
            if local.exists() and local.is_file():
                try:
                    local.unlink()
                    removed += 1
                    logging.info("Deleted removed file %s", local)
                except Exception:
                    logging.exception("Failed deleting %s", local)
            state.pop(path_lower, None)
        if removed:
            logging.info("Removed %d files that no longer exist in Dropbox", removed)

    save_state(state_path, state)
    logging.info("Sync complete. Downloaded=%d scanned=%d state=%s", downloaded, len(files), state_path)


def load_config(args: argparse.Namespace) -> SyncConfig:
    here = Path(__file__).resolve().parent
    env_file = args.env_file or (here / ".env")
    load_env_file(env_file)

    remote_folder = normalize_remote_folder(args.remote_folder or os.getenv("DROPBOX_FOLDER", "/"))
    local_dir = args.local_dir or Path(os.getenv("LOCAL_PHOTO_DIR", "/home/pi/pictures"))
    loop_seconds = int(args.loop_seconds or os.getenv("SYNC_LOOP_SECONDS", "120"))
    delete_removed = bool(args.delete_removed or os.getenv("SYNC_DELETE_REMOVED", "0") == "1")

    log_file = args.log_file or Path(os.getenv("LOG_FILE", str(here / "Dropbox_Photo_Sync.log")))
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN", "").strip() or None
    app_key = os.getenv("DROPBOX_APP_KEY", "").strip() or None
    app_secret = os.getenv("DROPBOX_APP_SECRET", "").strip() or None
    access_token = os.getenv("DROPBOX_TOKEN", "").strip() or None

    cfg = SyncConfig(
        remote_folder=remote_folder,
        local_dir=local_dir,
        loop_seconds=loop_seconds,
        delete_removed=delete_removed,
        log_file=log_file,
        log_level=log_level,
        refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
        access_token=access_token,
    )

    cfg.state_file = args.state_file or (log_file.parent / ".dropbox_sync_state.json")
    return cfg


def creds_present(cfg: SyncConfig) -> Tuple[bool, str]:
    if cfg.refresh_token and cfg.app_key and cfg.app_secret:
        return True, "refresh_token"
    if cfg.access_token:
        return True, "access_token"
    return False, "missing"


def main() -> int:
    args = parse_args()
    cfg = load_config(args)
    configure_logging(cfg.log_file, cfg.log_level)

    if not dropbox:  # pragma: no cover
        logging.error("dropbox package not installed; install with: python3 -m pip install dropbox")
        return EXIT_NO_DROPBOX

    ok, mode = creds_present(cfg)
    if not ok:
        logging.error("Missing Dropbox credentials (set refresh token + app key/secret, or DROPBOX_TOKEN).")
        if args.once:
            return EXIT_NO_CREDS
        logging.error("Waiting for credentials; re-checking every %ds.", cfg.loop_seconds)
        warned = True
        while True:
            time.sleep(cfg.loop_seconds)
            cfg = load_config(args)
            ok, mode = creds_present(cfg)
            if ok:
                break
            if not warned:
                logging.error("Still missing credentials.")
                warned = True

    logging.info("Auth mode: %s (token value not logged)", mode)
    logging.info("Remote: %s -> Local: %s", cfg.remote_folder, cfg.local_dir)

    while True:
        if not is_online(cfg.online_check_host, cfg.online_check_port, cfg.online_timeout):
            logging.warning("Offline detected; deferring sync.")
        else:
            try:
                sync_once(cfg, cfg.state_file or (cfg.log_file.parent / ".dropbox_sync_state.json"))
            except Exception as exc:  # pragma: no cover
                logging.exception("Sync failed: %s", exc)

        if args.once:
            break
        time.sleep(cfg.loop_seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

