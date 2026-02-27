"""Fullscreen pi3d slideshow for the Raspberry Pi photo frame."""

from __future__ import annotations

import argparse
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import pi3d
import yaml


@dataclass
class ViewerConfig:
    cache_dir: Path
    interval_seconds: float = 15.0
    fade_seconds: float = 1.5
    shuffle: bool = True
    image_extensions: Sequence[str] = (".jpg", ".jpeg", ".png")
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

    viewer = raw.get("viewer", {})
    logging_cfg = raw.get("logging", {})

    return ViewerConfig(
        cache_dir=repo_root / viewer.get("cache_dir", default.cache_dir),
        interval_seconds=float(viewer.get("interval_seconds", default.interval_seconds)),
        fade_seconds=float(viewer.get("fade_seconds", default.fade_seconds)),
        shuffle=bool(viewer.get("shuffle", default.shuffle)),
        image_extensions=tuple(viewer.get("image_extensions", default.image_extensions)),
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
    return sorted(
        p for p in cache_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in lowered
    )


def build_slides(
    image_paths: Iterable[Path],
    camera: pi3d.Camera,
    shader: pi3d.Shader,
) -> List[pi3d.ImageSprite]:
    slides = []
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
    try:
        while True:
            for idx in order:
                current = slides[idx]

                # Fade in
                start = time.time()
                while time.time() - start < fade_seconds:
                    if not display.loop_running():
                        return
                    alpha = min(1.0, (time.time() - start) / fade_seconds)
                    current.set_alpha(alpha)
                    current.draw()
                    if keyboard.read() == 27:  # ESC
                        return

                # Hold
                hold_until = time.time() + interval
                while time.time() < hold_until:
                    if not display.loop_running():
                        return
                    current.set_alpha(1.0)
                    current.draw()
                    if keyboard.read() == 27:
                        return

                current.set_alpha(0.0)

            if shuffle:
                random.shuffle(order)

    finally:
        keyboard.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/local.yaml"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    configure_logging(cfg.log_file, cfg.log_level)

    logging.info("Starting slideshow with cache_dir=%s", cfg.cache_dir)

    images = find_images(cfg.cache_dir, cfg.image_extensions)
    logging.info("Loaded %d images", len(images))

    display = pi3d.Display.create(background=(0, 0, 0, 1))
    camera = pi3d.Camera(is_3d=False)
    shader = pi3d.Shader("uv_flat")

    slides = build_slides(images, camera, shader)

    try:
        slideshow_loop(
            display,
            slides,
            cfg.interval_seconds,
            cfg.fade_seconds,
            cfg.shuffle,
        )
    except Exception:
        logging.exception("Viewer crashed")
        return 1
    finally:
        display.destroy()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())