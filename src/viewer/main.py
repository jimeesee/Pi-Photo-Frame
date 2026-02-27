"""Fullscreen pi3d slideshow for the Raspberry Pi photo frame."""

from __future__ import annotations

import argparse
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import pi3d  # type: ignore
import yaml


@dataclass
class ViewerConfig:
    cache_dir: Path
    interval_seconds: float = 15.0
    fade_seconds: float = 1.5
    shuffle: bool = True
    image_extensions: Sequence[str] = (".jpg", ".jpeg", ".png", ".gif")
    log_file: Path | None = None
    log_level: str = "INFO"


def load_config(cfg_path: Path | None) -> ViewerConfig:
    repo_root = Path(__file__).resolve().parents[2]
    default = ViewerConfig(
        cache_dir=repo_root / "cache" / "photos",
        log_file=repo_root / "logs" / "viewer.log",
    )
    if not cfg_path or not cfg_path.is_file():
        return default

    with cfg_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    viewer_cfg = raw.get("viewer", {}) if isinstance(raw, dict) else {}
    logging_cfg = raw.get("logging", {}) if isinstance(raw, dict) else {}
    return ViewerConfig(
        cache_dir=repo_root / viewer_cfg.get("cache_dir", default.cache_dir),
        interval_seconds=float(viewer_cfg.get("interval_seconds", default.interval_seconds)),
        fade_seconds=float(viewer_cfg.get("fade_seconds", default.fade_seconds)),
        shuffle=bool(viewer_cfg.get("shuffle", default.shuffle)),
        image_extensions=tuple(viewer_cfg.get("image_extensions", default.image_extensions)),
        log_file=repo_root / logging_cfg.get("file", default.log_file),
        log_level=str(logging_cfg.get("level", default.log_level)).upper(),
    )


def configure_logging(log_file: Path | None, level: str) -> None:
    handlers = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def find_images(cache_dir: Path, exts: Sequence[str]) -> List[Path]:
    lowered = {e.lower() for e in exts}
    files = [
        p
        for p in cache_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in lowered
    ]
    files.sort()
    return files


def build_slides(
    image_paths: Iterable[Path],
    camera: pi3d.Camera,
    shader: pi3d.Shader,
) -> List[pi3d.ImageSprite]:
    slides: List[pi3d.ImageSprite] = []
    for img in image_paths:
        tex = pi3d.Texture(str(img), mipmap=False, automatic_resize=True)
        sprite = pi3d.ImageSprite(texture=tex, camera=camera, shader=shader)
        sprite.set_alpha(0.0)
        slides.append(sprite)
    return slides


def slideshow_loop(
    display: pi3d.Display,
    slides: List[pi3d.ImageSprite],
    interval: float,
    fade_seconds: float,
    shuffle: bool,
) -> None:
    order = list(range(len(slides)))
    if shuffle:
        random.shuffle(order)

    keyboard = pi3d.Keyboard()
    last_heartbeat = time.time()
    try:
        while display.loop_running():
            for idx in order:
                current = slides[idx]
                # Fade in
                start = time.time()
                while time.time() - start < fade_seconds:
                    alpha = min(1.0, (time.time() - start) / fade_seconds)
                    current.set_alpha(alpha)
                    current.draw()
                    if keyboard.read() == 27:  # ESC
                        return
                # Hold
                hold_until = time.time() + interval
                while time.time() < hold_until:
                    current.set_alpha(1.0)
                    current.draw()
                    if keyboard.read() == 27:
                        return
                    now = time.time()
                    if now - last_heartbeat >= 30:
                        logging.info("Render heartbeat: slide=%s", current)
                        last_heartbeat = now
                current.set_alpha(0.0)
            if shuffle:
                random.shuffle(order)
    finally:
        keyboard.close()


def fallback_loop(display: pi3d.Display) -> None:
    """Render a blank screen when no photos are available."""
    keyboard = pi3d.Keyboard()
    try:
        while display.loop_running():
            if keyboard.read() == 27:  # ESC
                return
            time.sleep(0.5)
    finally:
        keyboard.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="pi3d fullscreen slideshow")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/local.yaml"),
        help="Path to YAML config file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    configure_logging(cfg.log_file, cfg.log_level)

    logging.info("Starting slideshow with cache_dir=%s", cfg.cache_dir)
    if not cfg.cache_dir.exists():
        logging.warning("Cache dir %s does not exist; creating.", cfg.cache_dir)
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    images = find_images(cfg.cache_dir, cfg.image_extensions)
    logging.info("Loaded %d images", len(images))

    display = pi3d.Display.create(
        x=0,
        y=0,
        frames_per_second=60,
        background=(0, 0, 0, 1),
        use_pygame=False,
    )

    camera = pi3d.Camera(is_3d=False)
    shader = pi3d.Shader("uv_flat")
    slides = build_slides(images, camera=camera, shader=shader)

    try:
        if not slides:
            logging.warning("No images found; showing blank screen.")
            fallback_loop(display)
        else:
            slideshow_loop(
                display=display,
                slides=slides,
                interval=cfg.interval_seconds,
                fade_seconds=cfg.fade_seconds,
                shuffle=cfg.shuffle,
            )
    except Exception as exc:  # pragma: no cover
        logging.exception("Slideshow crashed: %s", exc)
        return 1
    finally:
        display.destroy()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
