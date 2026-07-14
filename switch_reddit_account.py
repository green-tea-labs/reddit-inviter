"""Standalone script for switching the reddit-android-bot Reddit app account."""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import adbutils
import uiautomator2 as u2

from console_output import configure_utf8_output


configure_utf8_output()

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = BASE_DIR.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import reddit_account_switcher


ACCOUNT_ALIASES = {
    "invites": "u/Lazynick91",
    "posting": "u/PineappleCactusQuiz",
}

ACTION_DELAY = 0.5
ACTION_DELAY_JITTER_MIN = 0.85
ACTION_DELAY_JITTER_MAX = 1.15
TAP_JITTER_PX = 8


def log(message: str):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def pause(seconds: float = ACTION_DELAY):
    if seconds <= 0:
        return
    if seconds < 0.25:
        time.sleep(seconds)
        return
    time.sleep(seconds * random.uniform(ACTION_DELAY_JITTER_MIN, ACTION_DELAY_JITTER_MAX))


def adb_connected_devices() -> list[str]:
    client = adbutils.AdbClient(host="127.0.0.1", port=5037)
    return [device.serial for device in client.device_list()]


def element_center(el) -> tuple[int, int]:
    bounds = el.info.get("bounds", {})
    left = bounds.get("left")
    top = bounds.get("top")
    right = bounds.get("right")
    bottom = bounds.get("bottom")
    if None in (left, top, right, bottom):
        raise ValueError("Element bounds are unavailable")
    return ((left + right) // 2, (top + bottom) // 2)


def _clamp_point(x: int, y: int, width: int, height: int) -> tuple[int, int]:
    return (max(1, min(width - 1, x)), max(1, min(height - 1, y)))


def safe_click(d, el):
    try:
        el.click()
        return
    except Exception as exc:
        try:
            x, y = element_center(el)
            width, height = d.window_size()
            x, y = _clamp_point(
                x + random.randint(-TAP_JITTER_PX, TAP_JITTER_PX),
                y + random.randint(-TAP_JITTER_PX, TAP_JITTER_PX),
                width,
                height,
            )
            d.click(x, y)
            return
        except Exception:
            raise exc


def resolve_target_account(raw_value: str) -> str:
    alias = ACCOUNT_ALIASES.get(raw_value.strip().lower())
    if alias:
        return alias
    return raw_value


def main():
    if len(sys.argv) != 2:
        print("Usage: python switch_reddit_account.py <username|invites|posting>")
        sys.exit(1)

    target_account = resolve_target_account(sys.argv[1])

    log("Checking ADB device visibility...")
    try:
        devices = adb_connected_devices()
    except Exception as exc:
        log(f"Failed to query the local ADB server: {exc}")
        sys.exit(1)

    if not devices:
        log("No Android device is visible to ADB.")
        sys.exit(1)

    log("Connecting to Android device via USB...")
    try:
        d = u2.connect()
    except Exception as exc:
        log(f"Failed to connect: {exc}")
        sys.exit(1)

    d.screen_on()
    reddit_account_switcher.switch_reddit_account(d, target_account, log, pause, safe_click)


if __name__ == "__main__":
    main()
