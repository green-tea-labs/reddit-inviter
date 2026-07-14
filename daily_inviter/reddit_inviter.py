"""
reddit-android-bot
==================
Automates inviting commenters from r/dailyguess to r/PineappleCactus using
the Reddit Android app running on a USB-connected Android phone.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREREQUISITE SETUP (one-time)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Enable USB Debugging on your phone:
   Settings → About Phone → tap Build Number 7 times
   Settings → Developer Options → USB Debugging ON

2. Install Python dependencies:
   pip install -r requirements.txt

3. Plug phone in and confirm it is visible:
   adb devices
   (should show  <serial>  device  — NOT "unauthorized")

4. Push the automation server APK to your phone (one-time only):
   python -m uiautomator2 init

5. Keep the screen awake while the script runs (optional but recommended):
   adb shell svc power stayon true
   (undo with: adb shell svc power stayon false)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    python daily_inviter/reddit_inviter.py

Set DRY_RUN = True below to test navigation without confirming any invites.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TUNING SELECTORS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run discover_ui.py from the repo root first to dump the UI hierarchy at each key screen.
Search the resulting XML files for "resource-id" values and paste them
into the RESOURCE_IDS section below for faster, more reliable matching.
If left as empty strings (""), the script falls back to text-based selectors.
"""

import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import adbutils
import uiautomator2 as u2


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from console_output import configure_utf8_output
import reddit_account_switcher


configure_utf8_output()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — edit this section
# ─────────────────────────────────────────────────────────────────────────────

DRY_RUN = False  # True = navigate but skip the final invite confirmation tap

# Source subreddits to browse for qualifying posts.
# One subreddit is selected at random at the start of each run.
SOURCE_SUBREDDITS = [
    "dailyguess",
    "dailymix",
    "HotAndCold",
    "syllo",
    "QuizPlanetGame"
]

# Feed sort to use when opening the source subreddit.
SOURCE_FEED_SORT = "new"

# Community to invite users to.
INVITE_COMMUNITY = "pineapple cactus"

# Invite community display name to match in search results (regex, case-insensitive)
INVITE_COMMUNITY_PATTERN = r"(?i)pineapple.?cactus"

# Account that should be active before invite automation starts.
TARGET_REDDIT_ACCOUNT = "u/Lazynick91"

# Text typed into the invite field. On the current Reddit UI this becomes the
# message sent to the user, so change this if you want a different invite note.
INVITE_MESSAGE_TEXT = ""

# A post must have at least this many comments to qualify
MIN_COMMENTS = 10

# Stop after this many consecutive "Unknown error" responses
# (signals rate-limit OR user already invited)
MAX_CONSECUTIVE_ERRORS = 7

# Maximum feed scrolls before giving up on finding a qualifying post
MAX_FEED_SCROLLS = 125

# Maximum comment-list scrolls before considering all users processed
MAX_COMMENT_SCROLLS = 25

# Consecutive comment scrolls that show no new visible content before the post
# is treated as exhausted and the script returns to the feed.
MAX_STALLED_COMMENT_SCROLLS = 2

# Stop the entire run after this many seconds.
MAX_RUNTIME_SECONDS = 60 * 60

# Base delay between actions in seconds — increase if the app is slow to respond
ACTION_DELAY = 0.3

# Randomize action timing a bit so clicks and scrolls are less robotic.
# Example: 1.5 seconds becomes roughly 1.2 to 1.7 seconds.
ACTION_DELAY_JITTER_MIN = 0.40
ACTION_DELAY_JITTER_MAX = 0.64

# Small movement jitter so coordinate taps and swipes are less uniform.
TAP_JITTER_PX = 10
SWIPE_SCALE_JITTER_MIN = 0.9
SWIPE_SCALE_JITTER_MAX = 1.15
SWIPE_X_JITTER_PX = 28

# File that stores usernames already invited across previous runs.
INVITED_USERS_FILE = Path(__file__).with_name("invited_users.txt")
DAILY_TALLY_FILE = Path(__file__).with_name("daily_invite_tally.txt")

# ── Optional: paste resource-id values found via discover_ui.py ──────────────
# Leave as "" to use text/description-based selectors (default, always works).
RESOURCE_IDS = {
    "comment_count": "",      # e.g. "com.reddit.frontpage:id/comment_count_text"
    "post_author":   "",      # e.g. "com.reddit.frontpage:id/post_author_name"
    "sort_button":   "",      # e.g. "com.reddit.frontpage:id/sort_button"
    "overflow_menu": "",      # e.g. "com.reddit.frontpage:id/overflow_menu"
    "invite_button": "",      # e.g. "com.reddit.frontpage:id/invite_to_community"
    "search_field":  "",      # e.g. "com.reddit.frontpage:id/community_search_input"
    "message_field": "",      # e.g. "com.reddit.frontpage:id/invite_message_input"
}

# Relative tap fallbacks for the current Reddit Android layout.
# Values are fractions of the screen width/height.
COORDINATE_FALLBACKS = {
    "profile_more_actions": (0.943, 0.065),
    "profile_invite_bottom_item": (0.500, 0.937),
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def pause(seconds: float = ACTION_DELAY):
    if seconds <= 0:
        return
    if seconds < 0.5:
        time.sleep(seconds)
        return

    jittered = seconds * random.uniform(ACTION_DELAY_JITTER_MIN, ACTION_DELAY_JITTER_MAX)
    time.sleep(jittered)


def parse_comment_count(text: str) -> int:
    """Parse '1.2k comments', '842 Comments', '1.5K comments' → int."""
    text = text.lower().strip()
    m = re.search(r"([\d.]+)\s*([km]?)\s*comment", text)
    if not m:
        return 0
    n = float(m.group(1))
    suffix = m.group(2)
    if suffix == "k":
        n *= 1_000
    elif suffix == "m":
        n *= 1_000_000
    return int(n)


def extract_username(text: str) -> str:
    """'u/username' → 'username'; anything else returned as-is."""
    return text[2:] if text.startswith("u/") else text


def extract_comment_author(description: str) -> str:
    """Parse Reddit comment header descriptions like 'Level 1 comment by foo, 3 hours ago'."""
    match = re.search(r"comment by ([^,]+)", description, flags=re.IGNORECASE)
    if not match:
        return ""
    return extract_username(match.group(1).strip())


def normalize_username(username: str) -> str:
    return extract_username(username).strip().lower()


def load_invited_users() -> set[str]:
    if not INVITED_USERS_FILE.exists():
        return set()
    try:
        return {
            line.strip().lower()
            for line in INVITED_USERS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    except Exception as exc:
        log(f"WARNING: Could not read invited users file: {exc}")
        return set()


def record_invited_user(username: str):
    normalized = normalize_username(username)
    try:
        with INVITED_USERS_FILE.open("a", encoding="utf-8") as handle:
            handle.write(normalized + "\n")
    except Exception as exc:
        log(f"WARNING: Could not write invited user '{normalized}': {exc}")


def count_total_invited_users() -> int:
    return len(load_invited_users())


def _read_daily_tallies() -> dict[str, tuple[int, int]]:
    tallies: dict[str, tuple[int, int]] = {}

    if not DAILY_TALLY_FILE.exists():
        return tallies

    try:
        for raw_line in DAILY_TALLY_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = re.fullmatch(
                r"(\d{4}-\d{2}-\d{2})\s+processed=(\d+)\s+successful=(\d+)",
                line,
            )
            if not match:
                continue

            tally_date, processed_count, successful_count = match.groups()
            existing_processed, existing_successful = tallies.get(tally_date, (0, 0))
            tallies[tally_date] = (
                existing_processed + int(processed_count),
                existing_successful + int(successful_count),
            )
    except Exception as exc:
        log(f"WARNING: Could not read daily tally file: {exc}")

    return tallies


def _write_daily_tallies(tallies: dict[str, tuple[int, int]]):
    lines = [
        f"{tally_date} processed={processed_count} successful={successful_count}"
        for tally_date, (processed_count, successful_count) in sorted(tallies.items())
    ]

    try:
        DAILY_TALLY_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except Exception as exc:
        log(f"WARNING: Could not write daily tally file: {exc}")


def update_daily_tally(processed_delta: int = 0, successful_delta: int = 0):
    if processed_delta == 0 and successful_delta == 0:
        return

    today = datetime.now().date().isoformat()
    processed_count, successful_count = _read_daily_tallies().get(today, (0, 0))
    tallies = _read_daily_tallies()
    tallies[today] = (
        processed_count + processed_delta,
        successful_count + successful_delta,
    )
    _write_daily_tallies(tallies)


def timed_out(deadline: float) -> bool:
    return time.monotonic() >= deadline


def log_timeout_and_stop() -> bool:
    log(f"Reached hard runtime limit of {MAX_RUNTIME_SECONDS // 60} minutes. Stopping.")
    return True


def go_back(d, times: int = 1):
    for _ in range(times):
        d.press("back")
        pause(0.5)


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
    log("Closing Reddit app...")
    try:
        d.app_stop("com.reddit.frontpage")
    except Exception:
        try:
            d.shell("am force-stop com.reddit.frontpage")
        except Exception as exc:
            log(f"WARNING: Could not close Reddit app: {exc}")
            return
    pause(0.5)


def recover_reddit_to_feed(d, subreddit: str):
    log("Reddit is no longer in the foreground. Reopening the subreddit feed.")
    open_subreddit(d, subreddit)
    pause(1.0)


def ensure_reddit_feed_context(d, source_subreddit: str) -> bool:
    """Make sure Reddit is foregrounded and the subreddit feed is visible."""
    if not reddit_in_foreground(d):
        recover_reddit_to_feed(d, source_subreddit)
        return True

    screen = current_screen(d)
    if screen == "feed":
        return True

    log(f"Feed scan expected the subreddit feed, but screen='{screen}'. Recovering feed context.")
    if navigate_back_to_feed(d, source_subreddit=source_subreddit):
        return True

    recover_reddit_to_feed(d, source_subreddit)
    return True


def toast_visible(d, text: str, timeout: float = 3.0) -> bool:
    """Return True if a toast / snackbar containing text appears within timeout."""
    try:
        return d(textContains=text).wait(timeout=timeout)
    except Exception:
        return False


def _visible_feedback_texts(d) -> list[str]:
    """Collect short-lived UI feedback text from visible text and descriptions."""
    texts: list[str] = []

    try:
        xml = d.dump_hierarchy(pretty=True)
        root = ET.fromstring(xml)
    except Exception:
        return texts

    for node in root.iter("node"):
        for value in (node.attrib.get("text", ""), node.attrib.get("content-desc", "")):
            cleaned = value.strip()
            if cleaned and cleaned not in texts:
                texts.append(cleaned)

    return texts


def wait_for_feedback_message(d, timeout: float = 3.0) -> tuple[str, str, list[str]]:
    """Return (message, source, observed_toasts) for post-invite feedback."""
    deadline = time.monotonic() + timeout
    observed_toasts: list[str] = []
    feedback_patterns = [
        r"(?i)unknown error",
        r"(?i)successfully invited",
        r"(?i)you have successfully invited",
        r"(?i)invite sent",
        r"(?i)invited",
        r"(?i)success",
        r"(?i)failed",
        r"(?i)try again",
        r"(?i)already invited",
        r"(?i)rate limit",
    ]

    while time.monotonic() < deadline:
        toast_wait = min(0.5, max(0.1, deadline - time.monotonic()))
        try:
            message = d.toast.get_message(wait_timeout=toast_wait, default=None)
            if message:
                cleaned = str(message).strip()
                if cleaned and cleaned not in observed_toasts:
                    observed_toasts.append(cleaned)
                if cleaned:
                    return (cleaned, "toast", observed_toasts)
        except Exception:
            pass

        for pattern in feedback_patterns:
            for selector in (
                d(textMatches=pattern),
                d(descriptionMatches=pattern),
            ):
                try:
                    if selector.exists(timeout=0.2):
                        info = getattr(selector, "info", {}) or {}
                        for key in ("text", "contentDescription"):
                            value = (info.get(key) or "").strip()
                            if value:
                                return (value, "ui-selector", observed_toasts)
                except Exception:
                    continue

        for text in _visible_feedback_texts(d):
            if any(re.search(pattern, text) for pattern in feedback_patterns):
                return (text, "ui-hierarchy", observed_toasts)

        pause(0.1)

    return ("", "", observed_toasts)


def find_element(d, resource_id_key: str, **text_kwargs):
    """
    Try a resource-id selector first (if configured), then fall back to
    the provided text/description kwargs.
    Returns a uiautomator2 UiObject (may or may not exist — call .exists()).
    """
    rid = RESOURCE_IDS.get(resource_id_key, "")
    if rid:
        el = d(resourceId=rid)
        if el.exists(timeout=2):
            return el
    return d(**text_kwargs)


def dismiss_nsfw_modal(d, timeout: float = 3.5) -> bool:
    """Dismiss Reddit's NSFW warning modal by pressing Continue if present."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        for selector in (
            d(textMatches=r"(?i).*continue.*"),
            d(textContains="Continue"),
            d(descriptionMatches=r"(?i).*continue.*"),
            d(descriptionContains="Continue"),
            d(textMatches=r"(?i).*view.*anyway.*"),
            d(descriptionMatches=r"(?i).*view.*anyway.*"),
        ):
            if selector.exists(timeout=0.2):
                log("NSFW modal detected — pressing Continue.")
                safe_click(d, selector)
                pause(0.8)
                return True
        pause(0.3)

    return False


def iter_selector_elements(selector):
    """Yield matching UiObjects for selector APIs that expose count but not all()."""
    for index in range(selector.count):
        yield selector[index]


def element_center(el) -> tuple[int, int]:
    bounds = el.info.get("bounds", {})
    left = bounds.get("left")
    top = bounds.get("top")
    right = bounds.get("right")
    bottom = bounds.get("bottom")
    if None in (left, top, right, bottom):
        raise ValueError("Element bounds are unavailable")
    return ((left + right) // 2, (top + bottom) // 2)


def bounds_center(bounds: str) -> tuple[int, int]:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        raise ValueError(f"Invalid bounds: {bounds}")
    left, top, right, bottom = map(int, match.groups())
    return ((left + right) // 2, (top + bottom) // 2)


def header_tap_point(bounds: str) -> tuple[int, int]:
    left, top, right, _ = parse_bounds(bounds)
    return ((left + right) // 2, top + 50)


def parse_bounds(bounds: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        raise ValueError(f"Invalid bounds: {bounds}")
    return tuple(map(int, match.groups()))


def bounds_contains(outer: str, inner: str) -> bool:
    outer_left, outer_top, outer_right, outer_bottom = parse_bounds(outer)
    inner_left, inner_top, inner_right, inner_bottom = parse_bounds(inner)
    return (
        outer_left <= inner_left
        and outer_top <= inner_top
        and outer_right >= inner_right
        and outer_bottom >= inner_bottom
    )


class InputInjectionBlocked(RuntimeError):
    """Raised when the device refuses simulated taps or swipes over ADB/UIAutomator."""


def run_shell_input(d, command: str):
    result = d.shell(command)
    exit_code = getattr(result, "exit_code", 0)
    output = getattr(result, "output", "") or ""
    if exit_code != 0:
        if "INJECT_EVENTS permission" in output:
            raise InputInjectionBlocked(output.strip())
        raise RuntimeError(output.strip() or f"Shell command failed: {command}")
    return result


def safe_click(d, el):
    try:
        el.click()
        return
    except Exception as exc:
        x, y = element_center(el)
        try:
            run_shell_input(d, f"input tap {x} {y}")
        except InputInjectionBlocked:
            raise
        except Exception:
            raise exc


def _clamp_point(x: int, y: int, width: int, height: int) -> tuple[int, int]:
    return (max(1, min(width - 1, x)), max(1, min(height - 1, y)))


def _jitter_point(d, x: int, y: int, radius: int = TAP_JITTER_PX) -> tuple[int, int]:
    width, height = d.window_size()
    jitter_x = x + random.randint(-radius, radius)
    jitter_y = y + random.randint(-radius, radius)
    return _clamp_point(jitter_x, jitter_y, width, height)


def safe_tap_point(d, x: int, y: int):
    tap_x, tap_y = _jitter_point(d, x, y)
    try:
        d.click(tap_x, tap_y)
        return
    except Exception as exc:
        try:
            run_shell_input(d, f"input tap {tap_x} {tap_y}")
        except InputInjectionBlocked:
            raise
        except Exception:
            raise exc


def safe_tap_relative(d, x_fraction: float, y_fraction: float):
    width, height = d.window_size()
    safe_tap_point(d, int(width * x_fraction), int(height * y_fraction))


def safe_swipe_up(d, scale: float):
    varied_scale = scale * random.uniform(SWIPE_SCALE_JITTER_MIN, SWIPE_SCALE_JITTER_MAX)
    try:
        d.swipe_ext("up", scale=varied_scale)
        return
    except Exception as exc:
        width, height = d.window_size()
        start_x = (width // 2) + random.randint(-SWIPE_X_JITTER_PX, SWIPE_X_JITTER_PX)
        start_y = int(height * random.uniform(0.75, 0.81))
        end_y = max(200, int(start_y - (height * varied_scale * 0.5)))
        start_x, start_y = _clamp_point(start_x, start_y, width, height)
        end_x, end_y = _clamp_point(start_x + random.randint(-18, 18), end_y, width, height)
        try:
            run_shell_input(d, f"input swipe {start_x} {start_y} {end_x} {end_y} 250")
        except InputInjectionBlocked:
            raise
        except Exception:
            raise exc


def safe_comment_scroll(d):
    """Use a stronger direct upward swipe for advancing the comment list."""
    width, height = d.window_size()
    start_x = (width // 2) + random.randint(-24, 24)
    start_y = int(height * random.uniform(0.82, 0.88))
    end_x = start_x + random.randint(-14, 14)
    end_y = int(height * random.uniform(0.22, 0.30))
    start_x, start_y = _clamp_point(start_x, start_y, width, height)
    end_x, end_y = _clamp_point(end_x, end_y, width, height)

    try:
        run_shell_input(d, f"input swipe {start_x} {start_y} {end_x} {end_y} 320")
    except InputInjectionBlocked:
        raise
    except Exception:
        safe_swipe_up(d, scale=0.85)


def adb_connected_devices() -> list[str]:
    """Return serial numbers of devices currently visible to the local ADB server."""
    client = adbutils.AdbClient(host="127.0.0.1", port=5037)
    return [device.serial for device in client.device_list()]


def visible_post_cards(d) -> list[tuple[str, str]]:
    """Return visible Reddit feed cards as (content_description, tappable_bounds)."""
    xml = d.dump_hierarchy(pretty=True)
    root = ET.fromstring(xml)
    cards = []
    candidate_nodes = []

    for node in root.iter("node"):
        bounds = node.attrib.get("bounds", "")
        if not bounds:
            continue
        candidate_nodes.append((node.attrib.get("resource-id", ""), bounds))

    for node in root.iter("node"):
        desc = node.attrib.get("content-desc", "")
        bounds = node.attrib.get("bounds", "")
        if not desc or "comment" not in desc.lower() or not bounds:
            continue

        tappable_bounds = bounds
        for preferred_resource_id in (
            "post_comment_button",
            "post_unit",
            "post_dev_platform_custom_post",
        ):
            matched_bounds = None
            for resource_id, candidate_bounds in candidate_nodes:
                if resource_id == preferred_resource_id and bounds_contains(bounds, candidate_bounds):
                    matched_bounds = candidate_bounds
                    break
            if matched_bounds is not None:
                tappable_bounds = matched_bounds
                break

        cards.append((desc, tappable_bounds))

    return cards


def post_card_key(description: str) -> str:
    return re.sub(r"\s+", " ", description).strip().lower()
def summarize_post_description(description: str, limit: int = 100) -> str:
    summary = re.sub(r"\s+", " ", description).strip()
    if len(summary) <= limit:
        return summary
    return summary[: limit - 3] + "..."


def visible_comment_headers(d) -> list[tuple[str, str]]:
    """Return visible Reddit comment headers as (description, bounds)."""
    xml = d.dump_hierarchy(pretty=True)
    root = ET.fromstring(xml)
    headers = []

    for node in root.iter("node"):
        desc = node.attrib.get("content-desc", "")
        bounds = node.attrib.get("bounds", "")
        if desc.startswith("Level 1 comment by ") and bounds:
            headers.append((desc, bounds))

    return headers


def _find_send_button_right_of_search(d) -> tuple[int, int] | None:
    """
    Locate the paper-plane / send-invite button that sits to the right of the
    community search EditText.  Returns (x, y) tap coordinates, or None.
    """
    xml = d.dump_hierarchy(pretty=True)
    root = ET.fromstring(xml)

    edit_bounds = None
    for node in root.iter("node"):
        if node.attrib.get("class", "") == "android.widget.EditText":
            edit_bounds = node.attrib.get("bounds", "")
            break

    if not edit_bounds:
        return None

    _, edit_top, edit_right, edit_bottom = parse_bounds(edit_bounds)
    edit_center_y = (edit_top + edit_bottom) // 2

    for node in root.iter("node"):
        if node.attrib.get("clickable", "false") != "true":
            continue
        b = node.attrib.get("bounds", "")
        if not b:
            continue
        left, top, right, bottom = parse_bounds(b)
        center_y = (top + bottom) // 2
        if left >= edit_right and abs(center_y - edit_center_y) < 80:
            return ((left + right) // 2, center_y)

    return None


def _invite_message_field(d, search_field):
    """Best-effort lookup for the optional invite message text box."""
    if RESOURCE_IDS["message_field"]:
        candidate = d(resourceId=RESOURCE_IDS["message_field"])
        if candidate.exists(timeout=1):
            return candidate

    candidates = []
    for field in iter_selector_elements(d(className="android.widget.EditText")):
        try:
            info = getattr(field, "info", {}) or {}
            text = (info.get("text") or "").strip()
            content_description = (info.get("contentDescription") or "").strip()
            resource_name = (
                info.get("resourceName")
                or info.get("resourceId")
                or info.get("resource-id")
                or ""
            ).strip()
            haystack = " ".join((text, content_description, resource_name)).lower()
            if any(token in haystack for token in ("message", "note", "invite")):
                return field
            candidates.append(field)
        except Exception:
            continue

    if not candidates:
        return None

    if search_field is not None and len(candidates) > 1:
        try:
            search_center = element_center(search_field)
            remaining = []
            for field in candidates:
                try:
                    if element_center(field) != search_center:
                        remaining.append(field)
                except Exception:
                    remaining.append(field)
            if remaining:
                candidates = remaining
        except Exception:
            pass

    return candidates[-1]


def populate_invite_message(d, username: str, search_field) -> bool:
    """Fill the optional invite message field if configured and present."""
    if not INVITE_MESSAGE_TEXT.strip():
        return False

    message_field = _invite_message_field(d, search_field)
    if message_field is None:
        log(f"  [{username}] Invite message field not found. Leaving default message.")
        return False

    try:
        safe_click(d, message_field)
        message_field.clear_text()
        message_field.set_text(INVITE_MESSAGE_TEXT)
        log(f"  [{username}] Applied custom invite message.")
        pause(1.0)
        return True
    except Exception as exc:
        log(f"  [{username}] Could not set custom invite message: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 0: Reset to the Android home screen before starting Reddit
# ─────────────────────────────────────────────────────────────────────────────

def go_to_home_screen(d):
    log("Returning to the Android home screen...")
    try:
        d.press("home")
        pause(1.0)
        d.press("home")
        pause(1.0)
    except Exception as exc:
        log(f"Could not return to home screen cleanly: {exc}")


def subreddit_deep_link(subreddit: str) -> str:
    return f"https://www.reddit.com/r/{subreddit}/"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Open r/dailyguess via deep link
# ─────────────────────────────────────────────────────────────────────────────

def open_subreddit(d, subreddit: str):
    target_url = subreddit_deep_link(subreddit)
    log(f"Opening r/{subreddit} sorted by {SOURCE_FEED_SORT}...")
    d.shell(
        f'am start -W -S -a android.intent.action.VIEW '
        f'-d "{target_url}" '
        f'com.reddit.frontpage'
    )
    pause(5)
    dismiss_nsfw_modal(d)
    log(f"Subreddit opened via {target_url}.")


def ensure_target_account(d):
    reddit_account_switcher.switch_reddit_account(
        d,
        TARGET_REDDIT_ACCOUNT,
        log,
        pause,
        safe_click,
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Find first post with MIN_COMMENTS+ comments and open it
# ─────────────────────────────────────────────────────────────────────────────

def find_qualifying_post(d, deadline: float, skipped_post_keys: set[str], source_subreddit: str) -> tuple[bool, str | None]:
    log(
        f"Scanning feed for a post with {MIN_COMMENTS}+ comments "
        f"(skipping {len(skipped_post_keys)} exhausted posts)..."
    )
    _, screen_height = d.window_size()

    for scroll_num in range(MAX_FEED_SCROLLS):
        if timed_out(deadline):
            return (not log_timeout_and_stop(), None)

        ensure_reddit_feed_context(d, source_subreddit)
        found_candidate = False

        for desc, bounds in visible_post_cards(d):
            card_key = post_card_key(desc)
            if card_key in skipped_post_keys:
                continue

            count = parse_comment_count(desc)
            if count < MIN_COMMENTS:
                continue

            found_candidate = True
            _, top, _, bottom = parse_bounds(bounds)
            if top > int(screen_height * 0.8) or bottom >= screen_height:
                log(f"  Found qualifying post with {count} comments, but it is too low on screen. Scrolling it into view...")
                safe_swipe_up(d, scale=0.35)
                pause(0.7)
                break

            log(f"  Found feed card with {count} comments — tapping post...")
            x, y = header_tap_point(bounds)
            log(f"Candidate summary: {summarize_post_description(desc)}")
            safe_tap_point(d, x, y)
            pause(2.2)
            dismiss_nsfw_modal(d)
            return (True, card_key)

        if not found_candidate:
            # Fallback for older Reddit layouts that expose comment count as text.
            if RESOURCE_IDS["comment_count"]:
                candidates = iter_selector_elements(d(resourceId=RESOURCE_IDS["comment_count"]))
            else:
                candidates = iter_selector_elements(d(textMatches=r".*[Cc]omment.*"))

            for el in candidates:
                try:
                    text = el.get_text()
                    if not text:
                        continue
                    count = parse_comment_count(text)
                    if count >= MIN_COMMENTS:
                        log(f"  Found: '{text}' ({count} comments) — tapping post...")
                        safe_click(d, el)
                        pause(2.2)
                        dismiss_nsfw_modal(d)
                        return (True, None)
                except Exception:
                    continue

        log(f"  Scroll {scroll_num + 1}/{MAX_FEED_SCROLLS} — no qualifying post yet.")
        safe_swipe_up(d, scale=0.8)
        pause(0.9)

    log("ERROR: No qualifying post found after maximum scrolls.")
    return (False, None)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Filter comments by New
# ─────────────────────────────────────────────────────────────────────────────

def filter_by_new(d):
    log("Sorting comments by New...")
    pause(1.2)  # let comments load

    sort_btn = None

    if RESOURCE_IDS["sort_button"]:
        candidate = d(resourceId=RESOURCE_IDS["sort_button"])
        if candidate.exists(timeout=2):
            sort_btn = candidate

    if sort_btn is None:
        candidate = d(resourceId="action_sort")
        if candidate.exists(timeout=2):
            sort_btn = candidate

    if sort_btn is None:
        for pattern in [r"(?i)^best$", r"(?i)^top$", r"(?i)^hot$", r"(?i)sort\s*by"]:
            el = d(textMatches=pattern)
            if el.exists(timeout=2):
                sort_btn = el
                break

    if sort_btn is None:
        for desc in ["Sort comments", "Sort", "sort", "Filter", "filter"]:
            el = d(descriptionContains=desc)
            if el.exists(timeout=2):
                sort_btn = el
                break

    if sort_btn is None:
        log("  WARNING: Sort button not found — continuing with default sort order.")
        return

    if getattr(sort_btn, "info", None):
        try:
            x, y = element_center(sort_btn)
            safe_tap_point(d, x, y)
        except Exception:
            safe_click(d, sort_btn)
    else:
        safe_click(d, sort_btn)
    pause(0.8)

    selected = False
    for option in iter_selector_elements(d(resourceId="comment_sort_option_text")):
        try:
            if option.get_text().strip().lower() != "new":
                continue
            safe_click(d, option)
            selected = True
            break
        except Exception:
            continue

    if selected:
        pause(0.8)
        log("  Sort set to New.")
    else:
        log("  WARNING: 'New' option not found in sort menu.")
        go_back(d)  # dismiss the open dropdown


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Collect visible comment-author usernames
# ─────────────────────────────────────────────────────────────────────────────

def get_visible_usernames(d) -> list[tuple]:
    """
    Return list of ((tap_x, tap_y), username_str) for all visible comment authors.
    """
    results = []
    seen = set()

    def add(point: tuple[int, int], raw_name: str):
        name = extract_username(raw_name)
        if name and name not in seen:
            seen.add(name)
            results.append((point, name))

    for description, bounds in visible_comment_headers(d):
        username = extract_comment_author(description)
        if not username:
            continue
        left, top, _, bottom = parse_bounds(bounds)
        add((left + 120, (top + bottom) // 2), username)

    # Strategy A: resource-id (if configured)
    if RESOURCE_IDS["post_author"]:
        for el in iter_selector_elements(d(resourceId=RESOURCE_IDS["post_author"])):
            try:
                add(element_center(el), el.get_text())
            except Exception:
                pass

    # Strategy B: text starting with "u/"
    if not results:
        for el in iter_selector_elements(d(textMatches=r"^u/.+")):
            try:
                add(element_center(el), el.get_text())
            except Exception:
                pass

    # Strategy C: content-description starting with "u/"
    if not results:
        for el in iter_selector_elements(d(descriptionMatches=r"^u/.+")):
            try:
                add(element_center(el), el.info.get("contentDescription", ""))
            except Exception:
                pass

    return results


def visible_comment_snapshot(d) -> tuple[str, ...]:
    """Return a stable snapshot of the visible comments for scroll-progress checks."""
    snapshot = []

    for description, bounds in visible_comment_headers(d):
        username = normalize_username(extract_comment_author(description))
        snapshot.append(f"{username}@{bounds}" if username else description)

    if snapshot:
        return tuple(snapshot)

    for _, username in get_visible_usernames(d):
        snapshot.append(normalize_username(username))

    return tuple(snapshot)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Invite a single user (called when their profile screen is open)
# ─────────────────────────────────────────────────────────────────────────────

def invite_user(d, username: str) -> str:
    """
    Trigger the invite-to-community flow from the currently open profile screen.

    Returns:
        'success'   – invite confirmed (or dry-run skipped)
        'error'     – 'Unknown error' toast detected
        'not_found' – couldn't locate the invite UI (doesn't count toward error limit)
    """
    log(f"  [{username}] Locating invite option...")

    def invite_ui_visible() -> bool:
        return (
            d(textMatches=r"(?i)invite.*communit|communit.*invite|^invite$").exists(timeout=1)
            or d(text="Invite to Community").exists(timeout=1)
            or find_element(d, "search_field", className="android.widget.EditText").exists(timeout=1)
        )

    # ── Find the Invite button (direct or via overflow menu) ──────────────────
    invite_btn = find_element(
        d, "invite_button",
        textMatches=r"(?i)invite.*communit|communit.*invite|^invite$"
    )

    if not invite_btn.exists(timeout=2):
        log(f"  [{username}] Opening profile overflow via top-right coordinate.")
        safe_tap_relative(d, *COORDINATE_FALLBACKS["profile_more_actions"])
        pause(1.5)
        invite_btn = d(textMatches=r"(?i)invite.*communit|communit.*invite|^invite$")

        if not invite_ui_visible():
            overflow = None
            for desc in ("More profile actions", "More options"):
                candidate = d(description=desc)
                if candidate.exists(timeout=2):
                    overflow = candidate
                    break

            if overflow is not None:
                log(f"  [{username}] Coordinate tap missed — retrying overflow by description.")
                safe_click(d, overflow)
                pause(1.2)
                invite_btn = d(textMatches=r"(?i)invite.*communit|communit.*invite|^invite$")

    if not invite_btn.exists(timeout=3):
        action_item = d(text="Invite to Community")
        if action_item.exists(timeout=2):
            invite_btn = action_item

    if not invite_btn.exists(timeout=3):
        log(f"  [{username}] Invite button selector not found — using coordinate fallback.")
        safe_tap_relative(d, *COORDINATE_FALLBACKS["profile_invite_bottom_item"])
        pause(1.5)
    else:
        safe_click(d, invite_btn)
        pause(1.5)

    # If the coordinate fallback missed and we are still on the profile/menu, stop here.
    search_field = find_element(d, "search_field", className="android.widget.EditText")
    if not search_field.exists(timeout=3):
        log(f"  [{username}] Community search field not found. Skipping.")
        return "not_found"

    # ── Type the community name in the search field ───────────────────────────
    safe_click(d, search_field)
    search_field.clear_text()
    search_field.set_text(INVITE_MESSAGE_TEXT)
    pause(2.6)  # wait for search results to populate

    # ── Tap the correct community result ─────────────────────────────────────
    community_result = d(textMatches=INVITE_COMMUNITY_PATTERN)
    if not community_result.exists(timeout=5):
        log(f"  [{username}] Community not found in search results. Skipping.")
        return "not_found"

    safe_click(d, community_result)
    pause(1.3)
    populate_invite_message(d, username, search_field)

    if DRY_RUN:
        log(f"  [{username}] DRY RUN — skipping send tap.")
        return "success"

    # ── Tap send / paper-plane / confirm button ───────────────────────────────
    try:
        d.toast.reset()
    except Exception:
        pass

    sent = False

    # Strategy 1: text-based confirm button
    confirm_btn = d(textMatches=r"(?i)^invite$|^send invite$|^confirm$|^send$")
    if confirm_btn.exists(timeout=2):
        safe_click(d, confirm_btn)
        sent = True

    # Strategy 2: description-based (covers icon/paper-plane buttons)
    if not sent:
        for desc_pat in [r"(?i)send.?invite", r"(?i)send", r"(?i)paper.?plane"]:
            btn = d(descriptionMatches=desc_pat)
            if btn.exists(timeout=1):
                safe_click(d, btn)
                sent = True
                break

    # Strategy 3: XML geometry — first clickable element to the right of the EditText
    if not sent:
        tap = _find_send_button_right_of_search(d)
        if tap:
            log(f"  [{username}] Tapping send button via XML geometry at {tap}.")
            safe_tap_point(d, *tap)
            sent = True

    if not sent:
        log(f"  [{username}] No explicit send button found — treating as auto-confirmed.")

    # ── Detect result via toast / snackbar / transient feedback text ─────────
    feedback_message, feedback_source, observed_toasts = wait_for_feedback_message(d, timeout=4.5)
    if observed_toasts:
        log(f"  [{username}] Toast API saw: {' | '.join(observed_toasts)}")
    else:
        log(f"  [{username}] Toast API saw nothing.")

    if feedback_message:
        if feedback_source:
            log(f"  [{username}] Feedback after send ({feedback_source}): {feedback_message}")
        else:
            log(f"  [{username}] Feedback after send: {feedback_message}")
        normalized_feedback = feedback_message.lower()

        if "unknown error" in normalized_feedback:
            log(f"  [{username}] Invite failed — already invited or rate-limited.")
            return "error"

        if any(token in normalized_feedback for token in ("successfully invited", "invite sent", "invited", "success")):
            log(f"  [{username}] Invite sent!")
            return "success"

        if any(token in normalized_feedback for token in ("failed", "try again", "rate limit", "already invited")):
            log(f"  [{username}] Invite failed based on feedback text.")
            return "error"

    # No toast detected — Reddit sometimes gives no feedback on success
    log(f"  [{username}] No toast detected — assuming success.")
    return "success"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Main invite loop
# ─────────────────────────────────────────────────────────────────────────────

def _on_comment_screen(d) -> bool:
    """Return True if the comment list is currently visible."""
    if d(resourceId="action_sort").exists(timeout=1):
        return True
    xml = d.dump_hierarchy(pretty=True)
    root = ET.fromstring(xml)
    return any(
        node.attrib.get("content-desc", "").startswith("Level 1 comment by ")
        for node in root.iter("node")
    )


def current_screen(d) -> str:
    """
    Snapshot the UI and return a best-guess screen name:
      'comments'  – comment list is visible (action_sort or comment headers)
      'profile'   – a user profile page
      'invite'    – community search / invite picker
      'feed'      – subreddit feed
      'unknown'   – can’t identify
    """
    try:
        xml = d.dump_hierarchy(pretty=True)
        root = ET.fromstring(xml)
    except Exception:
        return "unknown"

    resource_ids = {node.attrib.get("resource-id", "") for node in root.iter("node")}
    texts        = [node.attrib.get("text", "") for node in root.iter("node")]
    descs        = [node.attrib.get("content-desc", "") for node in root.iter("node")]
    classes      = [node.attrib.get("class", "") for node in root.iter("node")]
    labels       = [value.lower() for value in texts + descs if value]

    if "action_sort" in resource_ids:
        return "comments"
    if any(d.startswith("Level 1 comment by ") for d in descs):
        return "comments"
    if "android.widget.EditText" in classes and any(
        "invite" in d.lower() or "community" in d.lower() or "search" in d.lower()
        for d in descs
    ):
        return "invite"
    if any(label in ("karma", "followers", "following", "follow", "message", "chat", "posts", "about") for label in labels):
        return "profile"
    # feed posts have many comment-count descriptions
    comment_count_nodes = [
        d for d in descs
        if re.search(r"\d+\s*(?:comment|k comment)", d, re.IGNORECASE)
    ]
    if len(comment_count_nodes) >= 2:
        return "feed"
    return "unknown"


def navigate_back_to_comments(d, max_backs: int = 8, source_subreddit: str = ""):
    """Press back until the comment list is visible, logging each step."""
    for i in range(max_backs):
        if not reddit_in_foreground(d):
            log(f"  [nav] Reddit lost focus while returning to comments (step {i}).")
            if source_subreddit:
                recover_reddit_to_feed(d, source_subreddit)
            return False
        screen = current_screen(d)
        log(f"  [nav] screen={screen} (step {i})")
        if screen == "comments":
            return True
        go_back(d)
        pause(1.2)
    log("  [nav] WARNING: could not navigate back to comments after max backs.")
    return False


def navigate_back_to_feed(d, max_backs: int = 10, source_subreddit: str = ""):
    """Press back until the subreddit feed is visible, logging each step."""
    for i in range(max_backs):
        if not reddit_in_foreground(d):
            log(f"  [nav] Reddit lost focus while returning to feed (step {i}).")
            if source_subreddit:
                recover_reddit_to_feed(d, source_subreddit)
                return True
            return False
        screen = current_screen(d)
        log(f"  [nav] screen={screen} while returning to feed (step {i})")
        if screen == "feed":
            return True
        go_back(d)
        pause(1.2)
    log("  [nav] WARNING: could not navigate back to feed after max backs.")
    return False


def attempt_comment_scroll(d, scale: float | None = None, use_direct_scroll: bool = False) -> bool:
    """Scroll the comment list and return True if the visible content changed."""
    before = visible_comment_snapshot(d)
    if use_direct_scroll:
        safe_comment_scroll(d)
    else:
        if scale is None:
            raise ValueError("scale is required when use_direct_scroll is False")
        safe_swipe_up(d, scale=scale)
    pause(0.9)
    after = visible_comment_snapshot(d)
    return after != before


def run_invite_loop(d, deadline: float, visited_users: set[str], source_subreddit: str) -> tuple[str, int]:
    tap_miss_counts: dict[str, int] = {}
    low_viewport_deferred: set[str] = set()
    consecutive_errors: int = 0
    total_invited: int = 0
    stalled_scrolls: int = 0
    _, screen_height = d.window_size()
    bottom_viewport_threshold = int(screen_height * 0.86)

    log(f"Invite loop started. Loaded {len(visited_users)} previously invited usernames.")

    for scroll_num in range(MAX_COMMENT_SCROLLS + 1):
        if timed_out(deadline):
            log_timeout_and_stop()
            return ("timed_out", total_invited)

        usernames = get_visible_usernames(d)
        new_users = [
            (point, u)
            for point, u in usernames
            if normalize_username(u) not in visited_users
        ]
        visible_names = ", ".join(u for _, u in usernames[:5]) or "none"
        log(
            f"Comment scan pass {scroll_num + 1}/{MAX_COMMENT_SCROLLS + 1}: "
            f"visible={len(usernames)}, unprocessed={len(new_users)}, "
            f"stalled={stalled_scrolls}, consecutive_errors={consecutive_errors}, "
            f"sample=[{visible_names}]"
        )

        if not new_users:
            if scroll_num >= MAX_COMMENT_SCROLLS:
                log(
                    "Reached maximum comment scan passes on this post with no new invite targets. "
                    "Returning to the feed."
                )
                return ("post_exhausted", total_invited)
            log(f"All visible users processed — scrolling for more comments ({scroll_num + 1}/{MAX_COMMENT_SCROLLS})...")
            if attempt_comment_scroll(d, scale=0.6):
                stalled_scrolls = 0
            else:
                stalled_scrolls += 1
                log(
                    f"No new comments appeared after scroll "
                    f"({stalled_scrolls}/{MAX_STALLED_COMMENT_SCROLLS})."
                )
                if stalled_scrolls >= MAX_STALLED_COMMENT_SCROLLS:
                    log("Comment thread appears exhausted. Returning to the feed for another post.")
                    return ("post_exhausted", total_invited)
            continue

        stalled_scrolls = 0
        should_scroll_for_more = False

        for point, username in new_users:
            if timed_out(deadline):
                log_timeout_and_stop()
                log(f"Invite loop complete. Total invited on this post: {total_invited}")
                return ("timed_out", total_invited)

            normalized = normalize_username(username)

            if point[1] >= bottom_viewport_threshold:
                if normalized in low_viewport_deferred:
                    log(f"u/{username} is still too low on screen — scrolling for more comments.")
                    should_scroll_for_more = True
                    break
                low_viewport_deferred.add(normalized)
                log(f"u/{username} is too low on screen to tap reliably — scrolling for more comments.")
                should_scroll_for_more = True
                break

            log(f"Processing u/{username} ...")

            # Tap the username to open their profile
            try:
                safe_tap_point(d, point[0], point[1])
            except Exception:
                log(f"  Could not tap u/{username}. Skipping.")
                continue
            pause(1.6)
            dismiss_nsfw_modal(d)

            if _on_comment_screen(d):
                tap_miss_counts[normalized] = tap_miss_counts.get(normalized, 0) + 1
                log(f"  Still on comments after tapping u/{username}. Miss {tap_miss_counts[normalized]}/2.")
                if tap_miss_counts[normalized] >= 2:
                    log(f"  Reached repeated tap misses for u/{username} — scrolling down.")
                    should_scroll_for_more = True
                    break
                continue

            tap_miss_counts.pop(normalized, None)
            low_viewport_deferred.discard(normalized)

            result = invite_user(d, username)

            # Navigate back to the comment list regardless of how many
            # screens the invite flow opened (Reddit sometimes auto-dismisses
            # the picker, leaving us already at the profile).
            navigate_back_to_comments(d, source_subreddit=source_subreddit)
            pause(0.6)

            if result == "success":
                visited_users.add(normalized)
                record_invited_user(username)
                update_daily_tally(processed_delta=1, successful_delta=1)
                total_invited += 1
                consecutive_errors = 0
                log(f"  Invited. Total this session: {total_invited}")

            elif result == "error":
                visited_users.add(normalized)
                record_invited_user(username)
                update_daily_tally(processed_delta=1)
                consecutive_errors += 1
                log(f"  Marking u/{username} as handled and recording to invited list after error.")
                log(f"  Consecutive errors: {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}")
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    log(
                        f"Reached {MAX_CONSECUTIVE_ERRORS} consecutive errors — "
                        f"stopping to respect rate limit."
                    )
                    log(f"Total invited on this post: {total_invited}")
                    return ("rate_limited", total_invited)

            # 'not_found' does not count toward the error limit
            else:
                update_daily_tally(processed_delta=1)

        if should_scroll_for_more:
            if attempt_comment_scroll(d, use_direct_scroll=True):
                stalled_scrolls = 0
            else:
                stalled_scrolls += 1
                log(
                    f"Comment scroll did not reveal new profiles "
                    f"({stalled_scrolls}/{MAX_STALLED_COMMENT_SCROLLS})."
                )
                if stalled_scrolls >= MAX_STALLED_COMMENT_SCROLLS:
                    log("Comment thread appears exhausted. Returning to the feed for another post.")
                    return ("post_exhausted", total_invited)
            continue

    log(
        f"Invite loop ended after {MAX_COMMENT_SCROLLS + 1} comment scan passes. "
        f"Total invited on this post: {total_invited}"
    )
    return ("completed", total_invited)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    deadline = time.monotonic() + MAX_RUNTIME_SECONDS
    source_subreddit = random.choice(SOURCE_SUBREDDITS)
    visited_users = load_invited_users()
    exhausted_post_keys: set[str] = set()
    total_invited = 0
    final_state = "started"
    d = None

    if DRY_RUN:
        log("=" * 60)
        log("DRY RUN MODE — invite confirmations will be skipped.")
        log("=" * 60)

    log(f"Selected source subreddit: r/{source_subreddit}")

    log("Checking ADB device visibility...")
    try:
        devices = adb_connected_devices()
    except Exception as exc:
        log(f"Failed to query the local ADB server: {exc}")
        log("Make sure Android platform-tools is installed and that the ADB server can start.")
        sys.exit(1)

    if not devices:
        log("No Android device is visible to ADB.")
        log("Check that USB debugging is enabled and the phone is unlocked.")
        log("If prompted on the phone, tap 'Allow USB debugging'.")
        log("Set the USB mode to File Transfer / Android Auto instead of charge-only.")
        log("If Windows still only shows the phone as portable storage, install the OEM USB driver.")
        sys.exit(1)

    log("Connecting to Android device via USB...")
    try:
        d = u2.connect()
    except Exception as exc:
        log(f"Failed to connect: {exc}")
        log("Run 'adb devices' to confirm the device is visible and authorized.")
        sys.exit(1)

    info = d.device_info
    log(f"Connected: {info.get('productName', 'unknown')} "
        f"(Android {info.get('version', '?')})")

    # Keep display on while script runs
    d.screen_on()

    try:
        go_to_home_screen(d)
        ensure_target_account(d)
        open_subreddit(d, source_subreddit)

        while not timed_out(deadline):
            found_post, active_post_key = find_qualifying_post(d, deadline, exhausted_post_keys, source_subreddit)
            if not found_post:
                if timed_out(deadline):
                    final_state = "timed_out"
                    log("Script complete.")
                    return
                log("Could not find a qualifying post. Exiting.")
                final_state = "no_post_found"
                sys.exit(1)

            if timed_out(deadline):
                log_timeout_and_stop()
                final_state = "timed_out"
                log("Script complete.")
                return

            filter_by_new(d)
            result, invited_count = run_invite_loop(d, deadline, visited_users, source_subreddit)
            total_invited += invited_count
            log(
                f"Post processing finished with result='{result}' and invited_count={invited_count}. "
                f"Session total is now {total_invited}."
            )

            if result == "timed_out":
                final_state = "timed_out"
                log("Stopping run because the hard runtime limit was reached during comment processing.")
                break
            if result == "rate_limited":
                final_state = "rate_limited"
                log("Stopping run because the consecutive error threshold suggests a rate limit or repeated invite failures.")
                break
            if result in {"completed", "post_exhausted"}:
                if active_post_key:
                    exhausted_post_keys.add(active_post_key)
                    if result == "completed":
                        log("Marking completed post so it will be skipped on the feed.")
                    else:
                        log("Marking current post as exhausted so it will be skipped on the feed.")
                if timed_out(deadline):
                    break
                navigate_back_to_feed(d, source_subreddit=source_subreddit)
                pause(1.5)
                if result == "completed":
                    log("Post completed. Looking for another post with enough comments...")
                else:
                    log("Post exhausted. Looking for another post with enough comments...")
                continue

        log(f"Session invite total: {total_invited}")
        log(f"Final run state: {final_state}")
    except InputInjectionBlocked:
        final_state = "input_blocked"
        log("The phone is blocking simulated taps/swipes from ADB and UIAutomator.")
        log("On POCO/Xiaomi devices, enable Developer options > USB debugging (Security settings).")
        log("If that option exists, also enable Install via USB, then reconnect the cable and accept prompts.")
        sys.exit(1)
    except Exception:
        final_state = "crashed"
        raise
    finally:
        if d is not None:
            close_reddit_app(d)

    log("Script complete.")


if __name__ == "__main__":
    main()
