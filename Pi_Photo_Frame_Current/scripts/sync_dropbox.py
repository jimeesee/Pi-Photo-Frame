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


def load_config(args: argparse.Namespace) -> SyncConfig:
    repo_root = Path(__file__).resolve().parents[1]
    token = os.getenv("DROPBOX_TOKEN", "").strip()
    remote = os.getenv("DROPBOX_FOLDER", "").strip() or "/"
    log_file = repo_root / "logs" / "sync.log"
    cache_dir = repo_root / "cache" / "photos"
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    return SyncConfig(
        token=token,
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

    if not cfg.token:
        logging.error("DROPBOX_TOKEN not set; cannot sync")
        return 3

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
