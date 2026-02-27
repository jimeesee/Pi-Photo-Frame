#!/usr/bin/env python3
"""Touch swipe daemon for Pi Photo Frame.

Reads raw touch events from an ILITEK USB touchscreen via evdev,
detects swipe gestures with velocity scaling, and injects arrow key
events via xdotool that picframe's SDL2 keyboard handler picks up
through X11/Xwayland.

Usage:
    python3 touch_daemon.py [options]

Requires: pip install evdev, apt install xdotool
"""

import argparse
import logging
import os
import subprocess
import sys
import time

import evdev
from evdev import ecodes

logger = logging.getLogger("touch_daemon")

# ── Defaults ────────────────────────────────────────────────────────
# Touch panel is 0–16384 units. Screen is ~800px wide → ~20 units/px.
DEFAULT_DEVICE_NAME = "ILITEK"
DEFAULT_MIN_DISTANCE = 1500     # touch units (~75px) — reject taps
DEFAULT_SOFT_MAX_VEL = 60000    # units/s — soft/medium boundary
DEFAULT_MEDIUM_MAX_VEL = 100000 # units/s — medium/hard boundary
DEFAULT_HARD_MAX_KEYS = 8       # max key presses for hardest swipe
DEFAULT_DEBOUNCE_SEC = 0.3      # seconds after a swipe to ignore events
DEFAULT_KEY_INTERVAL = 0.05     # seconds between injected key presses


def find_touch_device(name_substring: str) -> evdev.InputDevice:
    """Find the first evdev device whose name contains *name_substring*."""
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        if name_substring.upper() in dev.name.upper():
            logger.info("Found touch device: %s (%s)", dev.name, dev.path)
            return dev
    raise RuntimeError(
        f"No evdev device found matching '{name_substring}'. "
        f"Available: {[evdev.InputDevice(p).name for p in evdev.list_devices()]}"
    )


class SwipeDetector:
    """State machine that tracks a single finger and emits swipe events."""

    def __init__(self, min_distance: int, soft_max_vel: float,
                 medium_max_vel: float, hard_max_keys: int,
                 debounce_sec: float):
        self.min_distance = min_distance
        self.soft_max_vel = soft_max_vel
        self.medium_max_vel = medium_max_vel
        self.hard_max_keys = hard_max_keys
        self.debounce_sec = debounce_sec

        # Tracking state
        self._tracking = False
        self._got_start = False
        self._start_x: int = 0
        self._start_time: float = 0.0
        self._current_x: int = 0
        self._last_swipe_time: float = 0.0

    def on_touch_down(self) -> None:
        """Call when finger touches the screen."""
        self._tracking = True
        self._got_start = False
        self._start_time = time.monotonic()

    def on_move(self, x: int) -> None:
        """Call on each ABS_X / ABS_MT_POSITION_X event."""
        if not self._tracking:
            return
        if not self._got_start:
            self._start_x = x
            self._current_x = x
            self._got_start = True
            logger.debug("Start X captured: %d", x)
        else:
            self._current_x = x

    def on_touch_up(self) -> "tuple[int, int] | None":
        """Call when finger lifts. Returns (direction, key_count) or None.

        direction: +1 = swipe right (next), -1 = swipe left (back)
        key_count: number of key presses to inject (1–hard_max_keys)
        """
        if not self._tracking:
            return None
        self._tracking = False

        if not self._got_start:
            logger.debug("Touch up with no position data — ignoring")
            return None

        now = time.monotonic()

        # Debounce
        if now - self._last_swipe_time < self.debounce_sec:
            logger.debug("Debounced (%.0f ms since last swipe)",
                         (now - self._last_swipe_time) * 1000)
            return None

        delta_x = self._current_x - self._start_x
        elapsed = now - self._start_time
        distance = abs(delta_x)

        if distance < self.min_distance:
            logger.debug("Tap ignored (distance=%d < %d)", distance,
                         self.min_distance)
            return None

        velocity = distance / elapsed if elapsed > 0 else 0
        direction = 1 if delta_x > 0 else -1

        # Determine intensity
        if velocity < self.soft_max_vel:
            key_count = 1
            label = "soft"
        elif velocity < self.medium_max_vel:
            key_count = 3
            label = "medium"
        else:
            # Scale linearly from 5 to hard_max_keys for very fast swipes
            ratio = min((velocity - self.medium_max_vel) / self.medium_max_vel, 1.0)
            key_count = 5 + int(ratio * (self.hard_max_keys - 5))
            label = "hard"

        self._last_swipe_time = now
        dir_label = "next" if direction > 0 else "back"
        logger.info(
            "Swipe %s (%s): start=%d end=%d delta=%d distance=%d vel=%.0f keys=%d",
            dir_label, label, self._start_x, self._current_x,
            delta_x, distance, velocity, key_count,
        )
        return direction, key_count


def inject_keys(direction: int, count: int, interval: float) -> None:
    """Inject *count* arrow-key presses via xdotool through X11."""
    # Swipe left = next (Right key), swipe right = back (Left key)
    key_name = "Left" if direction > 0 else "Right"
    env = {**os.environ, "DISPLAY": ":0"}
    for i in range(count):
        subprocess.run(["xdotool", "key", key_name],
                       env=env, timeout=2, check=False)
        if i < count - 1:
            time.sleep(interval)


def run(args: argparse.Namespace) -> None:
    """Main event loop."""
    dev = find_touch_device(args.device_name)

    # Grab the device so picframe's own touch handler doesn't also see
    # raw touch (we're using keyboard mode instead).
    dev.grab()
    logger.info("Grabbed exclusive access to %s", dev.path)

    # Verify xdotool is available
    try:
        subprocess.run(["xdotool", "version"], capture_output=True,
                       timeout=2, check=True)
        logger.info("xdotool available for key injection")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise RuntimeError("xdotool not found — install with: sudo apt install xdotool") from e

    detector = SwipeDetector(
        min_distance=args.min_distance,
        soft_max_vel=args.soft_max_vel,
        medium_max_vel=args.medium_max_vel,
        hard_max_keys=args.hard_max_keys,
        debounce_sec=args.debounce_sec,
    )

    # X position event codes to track
    x_codes = {ecodes.ABS_MT_POSITION_X, ecodes.ABS_X}

    try:
        for event in dev.read_loop():
            if event.type == ecodes.EV_ABS and event.code in x_codes:
                detector.on_move(event.value)

            elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH:
                if event.value == 1:
                    detector.on_touch_down()
                elif event.value == 0:
                    result = detector.on_touch_up()
                    if result:
                        direction, count = result
                        inject_keys(direction, count, args.key_interval)

    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        dev.ungrab()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Touch swipe daemon for Pi Photo Frame",
    )
    parser.add_argument(
        "--device-name", default=DEFAULT_DEVICE_NAME,
        help="Substring to match in evdev device name (default: %(default)s)",
    )
    parser.add_argument(
        "--min-distance", type=int, default=DEFAULT_MIN_DISTANCE,
        help="Minimum swipe distance in touch units (default: %(default)s)",
    )
    parser.add_argument(
        "--soft-max-vel", type=float, default=DEFAULT_SOFT_MAX_VEL,
        help="Max velocity (units/s) for soft swipe (default: %(default)s)",
    )
    parser.add_argument(
        "--medium-max-vel", type=float, default=DEFAULT_MEDIUM_MAX_VEL,
        help="Max velocity (units/s) for medium swipe (default: %(default)s)",
    )
    parser.add_argument(
        "--hard-max-keys", type=int, default=DEFAULT_HARD_MAX_KEYS,
        help="Max key presses for hardest swipe (default: %(default)s)",
    )
    parser.add_argument(
        "--debounce-sec", type=float, default=DEFAULT_DEBOUNCE_SEC,
        help="Debounce interval in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--key-interval", type=float, default=DEFAULT_KEY_INTERVAL,
        help="Seconds between injected key presses (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: %(default)s)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    run(args)


if __name__ == "__main__":
    main()
