"""
Reddit Daily Poster
===================
Creates one daily link post in r/pineapplecactus using the Reddit Android app
running on a USB-connected Android phone.

The script:
1. Opens the subreddit submit screen in the Reddit app.
2. Selects the daily title/body variant based on the current date.
3. Fills out a link post for https://www.pineapplecactus.com/puzzles.
4. Records successful submissions locally so the same day is not posted twice.

Usage:
    python daily_poster/daily_puzzle_reddit_poster.py

Set DRY_RUN = True below to test navigation and form filling without tapping Post.
"""

import json
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import adbutils
import uiautomator2 as u2


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from console_output import configure_utf8_output
import reddit_account_switcher


configure_utf8_output()


DRY_RUN = False

TARGET_SUBREDDIT = "pineapplecactus"
TARGET_URL = "https://www.pineapplecactus.com/puzzles"
TARGET_FLAIR = "🧩Puzzle"
TARGET_REDDIT_ACCOUNT = "u/PineappleCactusQuiz"
MAX_RUNTIME_SECONDS = 10 * 60

ACTION_DELAY = 0.5
ACTION_DELAY_JITTER_MIN = 0.85
ACTION_DELAY_JITTER_MAX = 1.15
TAP_JITTER_PX = 8

POST_HISTORY_FILE = Path(__file__).with_name("post_history.json")

RESOURCE_IDS = {
    "title_field": "",
    "url_field": "",
    "body_field": "",
    "post_button": "",
    "link_tab": "",
    "flair_button": "",
}

TITLE_TEMPLATES = [
    "Pineapple Cactus - Puzzles 🍍🌵 - {date_label}",
    "Can you solve today’s puzzles? 🧠🔥 ({date_label})",
    "Think you can solve today’s puzzles? 🧠 ({date_label})",
    "Ready for today’s puzzles? 🍍🌵 ({date_label})",
    "Can you crack today’s puzzles? 🧩 ({date_label})",
    "Give today’s puzzles a shot 🧠🔥 ({date_label})",
    "How many of today’s puzzles can you solve? 👀 ({date_label})",
    "Test your brain with today’s puzzles 🧠 ({date_label})",
    "Up for today’s puzzle challenge? 🍍🌵 ({date_label})",
    "Can you beat today’s puzzles? 👀 ({date_label})",
    "Try today’s puzzles (if you dare) 🧠🔥 ({date_label})",
    "Quick brain test: today’s puzzles 🍍🌵 ({date_label})",
]

BODY_INTROS = [
    "A fresh set of puzzles is ready for you today. See how many you can solve.",
    "Jump into today’s mix of puzzles and put your brain to work.",
    "Ready for a quick puzzle session? Give today’s set a go.",
    "There’s a new batch of puzzles waiting today. How many can you crack?",
    "Put your thinking cap on and see how far you get with today’s puzzles.",
    "If you’re up for a brain workout, today’s puzzles are ready.",
    "Take on today’s puzzles and see which ones you can beat.",
]

BODY_FOOTER = "***We post a new quiz every day 🍍 If you enjoy these, you can tap the 🔔 to get notified when they go live.***"

SUCCESS_PATTERNS = [
    r"(?i)post submitted",
    r"(?i)posted",
    r"(?i)your post has been submitted",
    r"(?i)success",
]

FAILURE_PATTERNS = [
    r"(?i)duplicate",
    r"(?i)already submitted",
    r"(?i)something went wrong",
    r"(?i)try again",
    r"(?i)error",
    r"(?i)not allowed",
    r"(?i)spam",
]


class InputInjectionBlocked(RuntimeError):
    pass


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


def load_post_history() -> dict:
    if not POST_HISTORY_FILE.exists():
        return {"posts": []}

    try:
        payload = json.loads(POST_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"posts": []}

    if not isinstance(payload, dict):
        return {"posts": []}

    posts = payload.get("posts")
    if not isinstance(posts, list):
        payload["posts"] = []
    return payload


def save_post_history(history: dict):
    POST_HISTORY_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def successful_post_exists(post_day: date) -> bool:
    date_key = post_day.isoformat()
    history = load_post_history()
    for entry in history.get("posts", []):
        if entry.get("date") == date_key and entry.get("status") == "success":
            return True
    return False


def record_post_attempt(post_payload: dict, status: str, details: str = ""):
    history = load_post_history()
    history.setdefault("posts", []).append(
        {
            "date": post_payload["date_key"],
            "submitted_at": datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "title": post_payload["title"],
            "url": post_payload["url"],
            "details": details,
        }
    )
    save_post_history(history)


def build_post_payload(post_day: date | None = None) -> dict[str, str]:
    post_day = post_day or date.today()
    date_label = post_day.strftime("%d/%m")
    seed = post_day.toordinal()
    title = TITLE_TEMPLATES[seed % len(TITLE_TEMPLATES)].format(date_label=date_label)
    intro = BODY_INTROS[(seed * 5 + 3) % len(BODY_INTROS)]
    body = f"{intro}\n\n{BODY_FOOTER}"
    return {
        "date_key": post_day.isoformat(),
        "date_label": date_label,
        "title": title,
        "body": body,
        "url": TARGET_URL,
    }


def current_package_name(d) -> str:
    try:
        info = d.app_current()
    except Exception:
        return ""

    if isinstance(info, dict):
        return str(info.get("package") or "")
    return ""


def reddit_in_foreground(d) -> bool:
    return current_package_name(d) == "com.reddit.frontpage"


def close_reddit_app(d):
    try:
        d.app_stop("com.reddit.frontpage")
    except Exception:
        try:
            d.shell("am force-stop com.reddit.frontpage")
        except Exception as exc:
            log(f"WARNING: Could not close Reddit app: {exc}")


def go_to_home_screen(d):
    d.press("home")
    pause(1.0)
    d.press("home")
    pause(1.0)


def run_shell_input(d, command: str):
    result = d.shell(command)
    exit_code = getattr(result, "exit_code", 0)
    output = getattr(result, "output", "") or ""
    if exit_code != 0:
        if "INJECT_EVENTS permission" in output:
            raise InputInjectionBlocked(output.strip())
        raise RuntimeError(output.strip() or f"Shell command failed: {command}")
    return result


def parse_bounds(bounds: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        raise ValueError(f"Invalid bounds: {bounds}")
    return tuple(map(int, match.groups()))


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


def _jitter_point(d, x: int, y: int) -> tuple[int, int]:
    width, height = d.window_size()
    return _clamp_point(
        x + random.randint(-TAP_JITTER_PX, TAP_JITTER_PX),
        y + random.randint(-TAP_JITTER_PX, TAP_JITTER_PX),
        width,
        height,
    )


def safe_click(d, el):
    try:
        el.click()
        return
    except Exception as exc:
        try:
            x, y = element_center(el)
            tap_x, tap_y = _jitter_point(d, x, y)
            run_shell_input(d, f"input tap {tap_x} {tap_y}")
            return
        except Exception:
            raise exc


def iter_selector_elements(selector):
    for index in range(selector.count):
        yield selector[index]


def visible_feedback_texts(d) -> list[str]:
    try:
        xml = d.dump_hierarchy(pretty=True)
        root = ET.fromstring(xml)
    except Exception:
        return []

    texts: list[str] = []
    for node in root.iter("node"):
        for value in (node.attrib.get("text", ""), node.attrib.get("content-desc", "")):
            cleaned = value.strip()
            if cleaned and cleaned not in texts:
                texts.append(cleaned)
    return texts


def wait_for_text_feedback(d, timeout: float = 8.0) -> tuple[str, str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            toast_message = d.toast.get_message(wait_timeout=0.6, default=None)
        except Exception:
            toast_message = None

        if toast_message:
            return (str(toast_message).strip(), "toast")

        for text in visible_feedback_texts(d):
            if any(re.search(pattern, text) for pattern in SUCCESS_PATTERNS + FAILURE_PATTERNS):
                return (text, "ui")

        pause(0.2)

    return ("", "")


def fill_text_field(d, field, value: str, label: str):
    safe_click(d, field)
    pause(0.4)
    try:
        field.clear_text()
    except Exception:
        pass

    try:
        field.set_text(value)
    except Exception:
        d.send_keys(value, clear=True)

    log(f"Filled {label}.")
    pause(0.8)


def field_haystack(field) -> str:
    info = getattr(field, "info", {}) or {}
    values = [
        info.get("text", ""),
        info.get("contentDescription", ""),
        info.get("hintText", ""),
        info.get("resourceName", ""),
        info.get("resourceId", ""),
        info.get("resource-id", ""),
        info.get("className", ""),
    ]
    return " ".join(str(value) for value in values if value).lower()


def collect_edit_fields(d):
    fields = []
    for field in iter_selector_elements(d(className="android.widget.EditText")):
        try:
            center_x, center_y = element_center(field)
        except Exception:
            continue
        fields.append(
            {
                "field": field,
                "center": (center_x, center_y),
                "haystack": field_haystack(field),
            }
        )

    fields.sort(key=lambda item: (item["center"][1], item["center"][0]))
    return fields


def best_matching_field(
    fields,
    resource_id: str,
    keywords: tuple[str, ...],
    exclude_centers: set[tuple[int, int]],
    allow_fallback: bool = True,
) -> object | None:
    if resource_id:
        for item in fields:
            if item["center"] in exclude_centers:
                continue
            if resource_id in item["haystack"]:
                return item["field"]

    for item in fields:
        if item["center"] in exclude_centers:
            continue
        if all(keyword in item["haystack"] for keyword in keywords):
            return item["field"]

    for item in fields:
        if item["center"] in exclude_centers:
            continue
        if any(keyword in item["haystack"] for keyword in keywords):
            return item["field"]

    if allow_fallback:
        for item in fields:
            if item["center"] not in exclude_centers:
                return item["field"]

    return None


def reveal_optional_body_field(d):
    for selector in (
        d(textMatches=r"(?i)add body text"),
        d(textMatches=r"(?i)add text"),
        d(textMatches=r"(?i)body text(?: \(optional\))?"),
        d(descriptionMatches=r"(?i)add body text"),
    ):
        if selector.exists(timeout=0.6):
            safe_click(d, selector)
            pause(1.0)
            return True
    return False


def tap_bottom_left_link_button(d) -> bool:
    try:
        width, height = d.window_size()
    except Exception:
        return False

    tap_x = max(1, int(width * 0.08))
    tap_y = max(1, int(height * 0.84))

    try:
        run_shell_input(d, f"input tap {tap_x} {tap_y}")
    except Exception:
        return False

    log("Tapped the bottom-left chain icon to switch into link mode.")
    pause(1.0)
    return True


def ensure_link_post_mode(d):
    selectors = []

    if RESOURCE_IDS["link_tab"]:
        selectors.append(d(resourceId=RESOURCE_IDS["link_tab"]))

    selectors.extend(
        [
            d(textMatches=r"(?i)^link$"),
            d(textMatches=r"(?i)^link post$"),
            d(descriptionMatches=r"(?i)^link$"),
            d(descriptionMatches=r"(?i)^link post$"),
            d(textMatches=r"(?i)^url$"),
        ]
    )

    for selector in selectors:
        if selector.exists(timeout=0.5):
            safe_click(d, selector)
            pause(1.0)
            return True

    return tap_bottom_left_link_button(d)


def open_flair_picker(d) -> bool:
    selectors = []

    if RESOURCE_IDS["flair_button"]:
        selectors.append(d(resourceId=RESOURCE_IDS["flair_button"]))

    selectors.extend(
        [
            d(resourceId="flair_hint"),
            d(textMatches=r"(?i)^add flair$"),
            d(textMatches=r"(?i)^post flair$"),
            d(textMatches=r"(?i)^flair$"),
            d(textMatches=r"(?i)^edit flair$"),
            d(textContains="tags & flair"),
            d(textContains="Add tags & flair"),
            d(descriptionMatches=r"(?i).*flair.*"),
            d(textContains="Add flair"),
            d(textContains="Post flair"),
        ]
    )

    for selector in selectors:
        if selector.exists(timeout=0.6):
            safe_click(d, selector)
            pause(1.0)
            return True

    return False


def expand_all_flairs(d):
    for selector in (
        d(textMatches=r"(?i)^view all flair$"),
        d(textContains="View all flair"),
        d(descriptionMatches=r"(?i).*view all flair.*"),
    ):
        if selector.exists(timeout=0.8):
            safe_click(d, selector)
            pause(1.2)
            log("Expanded the full flair list.")
            return True
    return False


def confirm_flair_selection(d) -> bool:
    for selector in (
        d(textMatches=r"(?i)^apply$"),
        d(textMatches=r"(?i)^save$"),
        d(textMatches=r"(?i)^done$"),
        d(textMatches=r"(?i)^next$"),
        d(descriptionMatches=r"(?i)^(apply|save|done|next)$"),
    ):
        if selector.exists(timeout=0.6):
            safe_click(d, selector)
            pause(1.0)
            return True
    return False


def ensure_post_flair(d, flair_name: str) -> bool:
    current_texts = visible_feedback_texts(d)
    if any(text.strip().lower() == flair_name.lower() for text in current_texts):
        log(f"Post flair already set to {flair_name}.")
        return True

    if not open_flair_picker(d):
        log("Flair control was not found on the current Reddit composer screen.")
        return False

    expand_all_flairs(d)

    flair_selectors = (
        d(text=flair_name),
        d(textMatches=rf"(?i)^{re.escape(flair_name)}$"),
        d(textContains=flair_name),
        d(descriptionMatches=rf"(?i).*{re.escape(flair_name)}.*"),
    )

    for selector in flair_selectors:
        if selector.exists(timeout=1.0):
            safe_click(d, selector)
            pause(0.8)
            confirm_flair_selection(d)
            log(f"Applied post flair: {flair_name}.")
            return True

    log(f"Flair picker opened, but the '{flair_name}' option was not found.")
    d.press("back")
    pause(0.8)
    return False


def open_subreddit_feed(d):
    target_url = f"https://www.reddit.com/r/{TARGET_SUBREDDIT}/"
    log(f"Opening subreddit feed for r/{TARGET_SUBREDDIT}...")
    d.shell(
        f'am start -W -S -a android.intent.action.VIEW '
        f'-d "{target_url}" '
        f'com.reddit.frontpage'
    )
    pause(5.0)


def tap_bottom_center_create_post_button(d) -> bool:
    try:
        width, height = d.window_size()
    except Exception:
        return False

    tap_x = max(1, int(width * 0.5))
    tap_y = max(1, int(height * 0.92))

    try:
        run_shell_input(d, f"input tap {tap_x} {tap_y}")
    except Exception:
        return False

    log("Tapped the bottom-center create post button fallback.")
    pause(2.0)
    return True


def tap_create_post_button(d) -> bool:
    selectors = (
        d(textMatches=r"(?i)^create post$"),
        d(textMatches=r"(?i)^create$"),
        d(textContains="Create post"),
        d(textContains="Create"),
        d(descriptionMatches=r"(?i).*create post.*"),
        d(descriptionMatches=r"(?i)^create$"),
    )

    for selector in selectors:
        if selector.exists(timeout=0.8):
            log("Opening the subreddit composer via the Create post button.")
            safe_click(d, selector)
            pause(2.0)
            return True

    return tap_bottom_center_create_post_button(d)


def open_submit_screen(d):
    open_subreddit_feed(d)
    if tap_create_post_button(d):
        return

    raise RuntimeError("Could not open the subreddit composer from the subreddit feed.")


def ensure_target_account(d):
    reddit_account_switcher.switch_reddit_account(
        d,
        TARGET_REDDIT_ACCOUNT,
        log,
        pause,
        safe_click,
    )


def populate_post_form(d, post_payload: dict[str, str]):
    ensure_link_post_mode(d)
    reveal_optional_body_field(d)

    fields = collect_edit_fields(d)
    if len(fields) < 2:
        raise RuntimeError(
            "Could not find enough text fields on the Reddit submit screen. "
            "Run the script while the phone is unlocked and the app is up to date."
        )

    used_fields: set[tuple[int, int]] = set()

    title_field = best_matching_field(
        fields,
        RESOURCE_IDS["title_field"],
        ("title",),
        used_fields,
    )
    if title_field is None:
        raise RuntimeError("Could not identify the title field.")
    used_fields.add(element_center(title_field))
    fill_text_field(d, title_field, post_payload["title"], "title")

    url_field = best_matching_field(
        fields,
        RESOURCE_IDS["url_field"],
        ("url", "link"),
        used_fields,
    )
    if url_field is None:
        url_field = best_matching_field(fields, "", ("http",), used_fields)
    if url_field is None:
        raise RuntimeError("Could not identify the URL field required for a link post.")
    used_fields.add(element_center(url_field))
    fill_text_field(d, url_field, post_payload["url"], "URL")

    reveal_optional_body_field(d)
    fields = collect_edit_fields(d)
    body_field = best_matching_field(
        fields,
        RESOURCE_IDS["body_field"],
        ("body", "optional", "details"),
        used_fields,
        allow_fallback=False,
    )

    if body_field is not None:
        fill_text_field(d, body_field, post_payload["body"], "body")
    else:
        log("Body field was not exposed by the current Reddit UI. Continuing with title and link only.")

    ensure_post_flair(d, TARGET_FLAIR)


def composer_still_visible(d) -> bool:
    if d(textMatches=r"(?i)^post$").exists(timeout=0.2):
        return True
    if d(className="android.widget.EditText").count >= 2:
        return True
    return False


def tap_post_button(d):
    selectors = []
    if RESOURCE_IDS["post_button"]:
        selectors.append(d(resourceId=RESOURCE_IDS["post_button"]))

    selectors.extend(
        [
            d(textMatches=r"(?i)^post$"),
            d(descriptionMatches=r"(?i)^post$"),
            d(textMatches=r"(?i)^next$"),
            d(descriptionMatches=r"(?i)^next$"),
        ]
    )

    for selector in selectors:
        if selector.exists(timeout=0.6):
            safe_click(d, selector)
            pause(1.0)
            return

    raise RuntimeError("Could not find the Post button.")


def wait_for_submission_result(d, timeout: float = 25.0) -> tuple[str, str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        feedback_text, feedback_source = wait_for_text_feedback(d, timeout=1.2)
        if feedback_text:
            if any(re.search(pattern, feedback_text) for pattern in SUCCESS_PATTERNS):
                return ("success", f"{feedback_source}: {feedback_text}")
            if any(re.search(pattern, feedback_text) for pattern in FAILURE_PATTERNS):
                return ("failed", f"{feedback_source}: {feedback_text}")

        if reddit_in_foreground(d) and not composer_still_visible(d):
            return ("success", "Composer closed after submission.")

        pause(0.5)

    return ("unknown", "Timed out waiting for Reddit submission feedback.")


def main():
    started_at = datetime.now()
    deadline = time.monotonic() + MAX_RUNTIME_SECONDS
    post_payload = build_post_payload()
    submission_recorded = False
    d = None

    if successful_post_exists(date.today()):
        log("A successful post is already recorded for today. Exiting without posting again.")
        return

    log(f"Prepared daily title: {post_payload['title']}")
    log(f"Prepared target URL: {post_payload['url']}")

    if DRY_RUN:
        log("DRY RUN MODE — the script will stop before the final Post tap.")

    if time.monotonic() >= deadline:
        raise RuntimeError("Runtime budget expired before the poster could start.")

    log("Checking ADB device visibility...")
    try:
        devices = adb_connected_devices()
    except Exception as exc:
        log(f"Failed to query the local ADB server: {exc}")
        sys.exit(1)

    if not devices:
        log("No Android device is visible to ADB.")
        log("Check USB debugging, authorization prompts, and that the phone is unlocked.")
        sys.exit(1)

    log("Connecting to Android device via USB...")
    try:
        d = u2.connect()
    except Exception as exc:
        log(f"Failed to connect: {exc}")
        log("Run 'adb devices' to confirm the device is visible and authorized.")
        sys.exit(1)

    info = d.device_info
    log(f"Connected: {info.get('productName', 'unknown')} (Android {info.get('version', '?')})")

    d.screen_on()

    try:
        go_to_home_screen(d)
        ensure_target_account(d)
        open_submit_screen(d)
        populate_post_form(d, post_payload)

        if DRY_RUN:
            record_post_attempt(post_payload, "dry_run", "Form populated without submitting.")
            log("Dry run complete. Review the populated Reddit form on the device.")
            return

        tap_post_button(d)
        status, details = wait_for_submission_result(d)
        log(f"Submission result: {status} ({details})")
        record_post_attempt(post_payload, status, details)
        submission_recorded = True

        if status != "success":
            raise RuntimeError(f"Reddit did not confirm a successful post: {details}")
    except InputInjectionBlocked:
        record_post_attempt(post_payload, "input_blocked", "ADB/UIAutomator input injection blocked by device settings.")
        log("The phone blocked simulated taps or swipes from ADB/UIAutomator.")
        log("Enable any device-specific USB debugging security options, then try again.")
        sys.exit(1)
    except Exception as exc:
        if not DRY_RUN and not submission_recorded:
            record_post_attempt(post_payload, "crashed", str(exc))
        raise
    finally:
        if d is not None:
            close_reddit_app(d)
        elapsed = int((datetime.now() - started_at).total_seconds())
        log(f"Runtime: {elapsed} seconds")


if __name__ == "__main__":
    main()
