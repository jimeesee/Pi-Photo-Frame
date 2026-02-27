"""Dropbox sync loop with connectivity checks."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


try:
    import dropbox
    from dropbox.files import FileMetadata, FolderMetadata, ListFolderResult
except Exception:  # pragma: no cover - handled at runtime
    dropbox = None  # type: ignore
    FileMetadata = FolderMetadata = ListFolderResult = None  # type: ignore


@dataclass
class SyncConfig:
    token: str
    refresh_token: str
    app_key: str
    app_secret: str
    remote_folder: str
    cache_dir: Path
    log_file: Path
    log_level: str = "INFO"
    loop_seconds: int = 120
    online_check_host: str = "1.1.1.1"
    online_check_port: int = 53
    online_timeout: float = 2.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dropbox sync service")
    parser.add_argument("--once", action="store_true", help="Run a single sync then exit.")
    parser.add_argument(
        "--loop-seconds",
        type=int,
        default=int(os.getenv("SYNC_LOOP_SECONDS", "120")),
        help="Seconds to sleep between sync passes.",
    )
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    """Minimal .env loader to avoid extra dependencies."""
    if not path.is_file():
        logging.warning("No .env file found at %s", path)
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val


def load_config(args: argparse.Namespace) -> SyncConfig:
    repo_root = Path(__file__).resolve().parents[1]
    load_env_file(repo_root / ".env")
    token = os.getenv("DROPBOX_TOKEN", "").strip()
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN", "").strip()
    app_key = os.getenv("DROPBOX_APP_KEY", "").strip()
    app_secret = os.getenv("DROPBOX_APP_SECRET", "").strip()
    remote = os.getenv("DROPBOX_FOLDER", "").strip() or "/"
    log_file = repo_root / "logs" / "sync.log"
    cache_dir = repo_root / "cache" / "photos"
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    return SyncConfig(
        token=token,
        refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
        remote_folder=remote if remote.startswith("/") else f"/{remote}",
        cache_dir=cache_dir,
        log_file=log_file,
        log_level=log_level,
        loop_seconds=args.loop_seconds,
    )


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


def list_files(dbx: "dropbox.Dropbox", remote_folder: str) -> List[FileMetadata]:
    files: List[FileMetadata] = []
    result: ListFolderResult = dbx.files_list_folder(remote_folder, recursive=True)
    files.extend([e for e in result.entries if isinstance(e, FileMetadata)])
    while result.has_more:
        result = dbx.files_list_folder_continue(result.cursor)
        files.extend([e for e in result.entries if isinstance(e, FileMetadata)])
    return files


def should_download(entry: FileMetadata, local: Path) -> bool:
    if not local.exists():
        return True
    size_matches = local.stat().st_size == entry.size
    return not size_matches


def download_file(dbx: "dropbox.Dropbox", entry: FileMetadata, cache_dir: Path, remote_root: str) -> None:
    rel_path = entry.path_lower[len(remote_root) :].lstrip("/")
    target = cache_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    dbx.files_download_to_file(str(tmp), entry.path_lower)
    tmp.replace(target)
    mtime = entry.client_modified.timestamp()
    os.utime(target, (mtime, mtime))
    logging.info("Synced %s (%d bytes)", target, entry.size)


def sync_once(cfg: SyncConfig) -> None:
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    if cfg.refresh_token and cfg.app_key and cfg.app_secret:
        dbx = dropbox.Dropbox(
            oauth2_refresh_token=cfg.refresh_token,
            app_key=cfg.app_key,
            app_secret=cfg.app_secret,
            timeout=30,
        )
    else:
        dbx = dropbox.Dropbox(cfg.token, timeout=30)
    files = list_files(dbx, cfg.remote_folder)
    remote_root = cfg.remote_folder.lower().rstrip("/")
    if not remote_root:
        remote_root = ""
    synced = 0
    for entry in files:
        rel_path = entry.path_lower[len(remote_root) :].lstrip("/")
        if not rel_path:
            continue
        local = cfg.cache_dir / rel_path
        if should_download(entry, local):
            download_file(dbx, entry, cfg.cache_dir, remote_root)
            synced += 1
    logging.info("Sync complete. Downloaded %d files. Total scanned: %d", synced, len(files))


def main() -> int:
    args = parse_args()
    cfg = load_config(args)
    configure_logging(cfg.log_file, cfg.log_level)

    if not dropbox:  # pragma: no cover - runtime guard
        logging.error("dropbox package not installed; pip install dropbox")
        return 2

    def creds_ok(current: SyncConfig) -> bool:
        if current.refresh_token and current.app_key and current.app_secret:
            return True
        if current.token:
            return True
        return False

    if not creds_ok(cfg):
        logging.error(
            "Dropbox credentials missing; set DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET (preferred) "
            "or legacy DROPBOX_TOKEN."
        )
        if args.once:
            return 3
        logging.error("Waiting for credentials; re-checking every %ds.", cfg.loop_seconds)
        while True:
            time.sleep(cfg.loop_seconds)
            cfg = load_config(args)
            if creds_ok(cfg):
                break
    if cfg.refresh_token and cfg.app_key and cfg.app_secret:
        logging.info("Using Dropbox refresh token auth (values not logged); folder=%s", cfg.remote_folder)
    else:
        logging.info("Using Dropbox access token (length=%d); folder=%s", len(cfg.token), cfg.remote_folder)

    logging.info("Starting Dropbox sync loop -> cache: %s, remote: %s", cfg.cache_dir, cfg.remote_folder)
    while True:
        if not is_online(cfg.online_check_host, cfg.online_check_port, cfg.online_timeout):
            logging.warning("Offline detected; deferring sync.")
        else:
            try:
                sync_once(cfg)
            except Exception as exc:  # pragma: no cover
                logging.exception("Sync failed: %s", exc)

        if args.once:
            break
        time.sleep(cfg.loop_seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
