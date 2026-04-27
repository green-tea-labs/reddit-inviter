"""
Reddit Auto-Inviter
===================
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
    python reddit_inviter.py

Set DRY_RUN = True below to test navigation without confirming any invites.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TUNING SELECTORS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run discover_ui.py first to dump the UI hierarchy at each key screen.
Search the resulting XML files for "resource-id" values and paste them
into the RESOURCE_IDS section below for faster, more reliable matching.
If left as empty strings (""), the script falls back to text-based selectors.
"""

import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import adbutils
import uiautomator2 as u2

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
]

# Community to invite users to (as typed into the search field)
INVITE_COMMUNITY = "pineapple cactus"

# Invite community display name to match in search results (regex, case-insensitive)
INVITE_COMMUNITY_PATTERN = r"(?i)pineapple.?cactus"

# A post must have at least this many comments to qualify
MIN_COMMENTS = 20

# Stop after this many consecutive "Unknown error" responses
# (signals rate-limit OR user already invited)
MAX_CONSECUTIVE_ERRORS = 7

# Maximum feed scrolls before giving up on finding a qualifying post
MAX_FEED_SCROLLS = 25

# Maximum comment-list scrolls before considering all users processed
MAX_COMMENT_SCROLLS = 150

# Stop the entire run after this many seconds.
MAX_RUNTIME_SECONDS = 30 * 60

# Base delay between actions in seconds — increase if the app is slow to respond
ACTION_DELAY = 0.5

# Randomize action timing a bit so clicks and scrolls are less robotic.
# Example: 1.5 seconds becomes roughly 1.1 to 2.0 seconds.
ACTION_DELAY_JITTER_MIN = 0.75
ACTION_DELAY_JITTER_MAX = 1.35

# Small movement jitter so coordinate taps and swipes are less uniform.
TAP_JITTER_PX = 10
SWIPE_SCALE_JITTER_MIN = 0.9
SWIPE_SCALE_JITTER_MAX = 1.15
SWIPE_X_JITTER_PX = 28

# File that stores usernames already invited across previous runs.
INVITED_USERS_FILE = Path(__file__).with_name("invited_users.txt")

# ── Optional: paste resource-id values found via discover_ui.py ──────────────
# Leave as "" to use text/description-based selectors (default, always works).
RESOURCE_IDS = {
    "comment_count": "",      # e.g. "com.reddit.frontpage:id/comment_count_text"
    "post_author":   "",      # e.g. "com.reddit.frontpage:id/post_author_name"
    "sort_button":   "",      # e.g. "com.reddit.frontpage:id/sort_button"
    "overflow_menu": "",      # e.g. "com.reddit.frontpage:id/overflow_menu"
    "invite_button": "",      # e.g. "com.reddit.frontpage:id/invite_to_community"
    "search_field":  "",      # e.g. "com.reddit.frontpage:id/community_search_input"
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


def timed_out(deadline: float) -> bool:
    return time.monotonic() >= deadline


def log_timeout_and_stop() -> bool:
    log(f"Reached hard runtime limit of {MAX_RUNTIME_SECONDS // 60} minutes. Stopping.")
    return True


def go_back(d, times: int = 1):
    for _ in range(times):
        d.press("back")
        pause(0.8)


def toast_visible(d, text: str, timeout: float = 3.0) -> bool:
    """Return True if a toast / snackbar containing text appears within timeout."""
    try:
        return d(textContains=text).wait(timeout=timeout)
    except Exception:
        return False


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
                pause(1.5)
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


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Open r/dailyguess via deep link
# ─────────────────────────────────────────────────────────────────────────────

def open_subreddit(d, subreddit: str):
    log(f"Opening r/{subreddit}...")
    d.shell(
        f'am start -a android.intent.action.VIEW '
        f'-d "https://www.reddit.com/r/{subreddit}" '
        f'com.reddit.frontpage'
    )
    pause(4)
    dismiss_nsfw_modal(d)
    log("Subreddit opened.")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Find first post with MIN_COMMENTS+ comments and open it
# ─────────────────────────────────────────────────────────────────────────────

def find_qualifying_post(d, deadline: float) -> bool:
    log(f"Scanning feed for a post with {MIN_COMMENTS}+ comments...")
    _, screen_height = d.window_size()

    for scroll_num in range(MAX_FEED_SCROLLS):
        if timed_out(deadline):
            return not log_timeout_and_stop()
        found_candidate = False

        for desc, bounds in visible_post_cards(d):
            count = parse_comment_count(desc)
            if count < MIN_COMMENTS:
                continue

            found_candidate = True
            _, top, _, bottom = parse_bounds(bounds)
            if top > int(screen_height * 0.8) or bottom >= screen_height:
                log(f"  Found qualifying post with {count} comments, but it is too low on screen. Scrolling it into view...")
                safe_swipe_up(d, scale=0.35)
                pause(1.5)
                break

            log(f"  Found feed card with {count} comments — tapping post...")
            x, y = header_tap_point(bounds)
            safe_tap_point(d, x, y)
            pause(3)
            dismiss_nsfw_modal(d)
            return True

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
                        pause(3)
                        dismiss_nsfw_modal(d)
                        return True
                except Exception:
                    continue

        log(f"  Scroll {scroll_num + 1}/{MAX_FEED_SCROLLS} — no qualifying post yet.")
        safe_swipe_up(d, scale=0.8)
        pause(1.5)

    log("ERROR: No qualifying post found after maximum scrolls.")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Filter comments by New
# ─────────────────────────────────────────────────────────────────────────────

def filter_by_new(d):
    log("Sorting comments by New...")
    pause(2)  # let comments load

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
    pause(1.5)

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
        pause(1.5)
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
        pause(1.2)
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
        pause(2)
    else:
        safe_click(d, invite_btn)
        pause(2)

    # If the coordinate fallback missed and we are still on the profile/menu, stop here.
    search_field = find_element(d, "search_field", className="android.widget.EditText")
    if not search_field.exists(timeout=3):
        log(f"  [{username}] Community search field not found. Skipping.")
        return "not_found"

    # ── Type the community name in the search field ───────────────────────────
    safe_click(d, search_field)
    search_field.clear_text()
    search_field.set_text(INVITE_COMMUNITY)
    pause(2.5)  # wait for search results to populate

    # ── Tap the correct community result ─────────────────────────────────────
    community_result = d(textMatches=INVITE_COMMUNITY_PATTERN)
    if not community_result.exists(timeout=5):
        log(f"  [{username}] Community not found in search results. Skipping.")
        return "not_found"

    safe_click(d, community_result)
    pause(1.5)

    if DRY_RUN:
        log(f"  [{username}] DRY RUN — skipping send tap.")
        return "success"

    # ── Tap send / paper-plane / confirm button ───────────────────────────────
    sent = False

    # Strategy 1: text-based confirm button
    confirm_btn = d(textMatches=r"(?i)^invite$|^send invite$|^confirm$|^send$")
    if confirm_btn.exists(timeout=2):
        safe_click(d, confirm_btn)
        sent = True
        pause(2)

    # Strategy 2: description-based (covers icon/paper-plane buttons)
    if not sent:
        for desc_pat in [r"(?i)send.?invite", r"(?i)send", r"(?i)paper.?plane"]:
            btn = d(descriptionMatches=desc_pat)
            if btn.exists(timeout=1):
                safe_click(d, btn)
                sent = True
                pause(2)
                break

    # Strategy 3: XML geometry — first clickable element to the right of the EditText
    if not sent:
        tap = _find_send_button_right_of_search(d)
        if tap:
            log(f"  [{username}] Tapping send button via XML geometry at {tap}.")
            safe_tap_point(d, *tap)
            sent = True
            pause(2)

    if not sent:
        log(f"  [{username}] No explicit send button found — treating as auto-confirmed.")
        pause(1)

    # ── Detect result via toast ───────────────────────────────────────────────
    if toast_visible(d, "Unknown error", timeout=3):
        log(f"  [{username}] 'Unknown error' — already invited or rate-limited.")
        return "error"

    # Any success-flavoured toast
    if (toast_visible(d, "Invite sent", timeout=2)
            or toast_visible(d, "invited", timeout=2)
            or toast_visible(d, "success", timeout=2)):
        log(f"  [{username}] Invite sent!")
        return "success"

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
    descs        = [node.attrib.get("content-desc", "") for node in root.iter("node")]
    classes      = [node.attrib.get("class", "") for node in root.iter("node")]

    if "action_sort" in resource_ids:
        return "comments"
    if any(d.startswith("Level 1 comment by ") for d in descs):
        return "comments"
    if "android.widget.EditText" in classes and any(
        "invite" in d.lower() or "community" in d.lower() or "search" in d.lower()
        for d in descs
    ):
        return "invite"
    if any(d.lower() in ("karma", "followers", "follow", "message") for d in descs):
        return "profile"
    # feed posts have many comment-count descriptions
    comment_count_nodes = [
        d for d in descs
        if re.search(r"\d+\s*(?:comment|k comment)", d, re.IGNORECASE)
    ]
    if len(comment_count_nodes) >= 2:
        return "feed"
    return "unknown"


def navigate_back_to_comments(d, max_backs: int = 8):
    """Press back until the comment list is visible, logging each step."""
    for i in range(max_backs):
        screen = current_screen(d)
        log(f"  [nav] screen={screen} (step {i})")
        if screen == "comments":
            return True
        go_back(d)
        pause(1.2)
    log("  [nav] WARNING: could not navigate back to comments after max backs.")
    return False


def run_invite_loop(d, deadline: float):
    visited_users: set[str] = load_invited_users()
    tap_miss_counts: dict[str, int] = {}
    low_viewport_deferred: set[str] = set()
    consecutive_errors: int = 0
    total_invited: int = 0
    _, screen_height = d.window_size()
    bottom_viewport_threshold = int(screen_height * 0.86)

    log(f"Invite loop started. Loaded {len(visited_users)} previously invited usernames.")

    for scroll_num in range(MAX_COMMENT_SCROLLS + 1):
        if timed_out(deadline):
            log_timeout_and_stop()
            break

        usernames = get_visible_usernames(d)
        new_users = [
            (point, u)
            for point, u in usernames
            if normalize_username(u) not in visited_users
        ]

        if not new_users:
            if scroll_num >= MAX_COMMENT_SCROLLS:
                log("Reached maximum comment scrolls. Stopping.")
                break
            log(f"All visible users processed — scrolling for more comments ({scroll_num + 1}/{MAX_COMMENT_SCROLLS})...")
            safe_swipe_up(d, scale=0.6)
            pause(1.5)
            continue

        should_scroll_for_more = False

        for point, username in new_users:
            if timed_out(deadline):
                log_timeout_and_stop()
                log(f"Invite loop complete. Total invited this session: {total_invited}")
                return

            normalized = normalize_username(username)

            if point[1] >= bottom_viewport_threshold:
                if normalized in low_viewport_deferred:
                    continue
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
            pause(2.5)
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
            navigate_back_to_comments(d)
            pause(1.0)

            if result == "success":
                visited_users.add(normalized)
                record_invited_user(username)
                total_invited += 1
                consecutive_errors = 0
                log(f"  Invited. Total this session: {total_invited}")

            elif result == "error":
                consecutive_errors += 1
                log(f"  Consecutive errors: {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}")
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    log(
                        f"Reached {MAX_CONSECUTIVE_ERRORS} consecutive errors — "
                        f"stopping to respect rate limit."
                    )
                    log(f"Total invited this session: {total_invited}")
                    return

            # 'not_found' does not count toward the error limit

        if should_scroll_for_more:
            safe_comment_scroll(d)
            pause(1.5)
            continue

    log(f"Invite loop complete. Total invited this session: {total_invited}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    deadline = time.monotonic() + MAX_RUNTIME_SECONDS
    source_subreddit = random.choice(SOURCE_SUBREDDITS)

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
        open_subreddit(d, source_subreddit)

        if not find_qualifying_post(d, deadline):
            if timed_out(deadline):
                log("Script complete.")
                return
            log("Could not find a qualifying post. Exiting.")
            sys.exit(1)

        if timed_out(deadline):
            log_timeout_and_stop()
            log("Script complete.")
            return

        filter_by_new(d)
        run_invite_loop(d, deadline)
    except InputInjectionBlocked:
        log("The phone is blocking simulated taps/swipes from ADB and UIAutomator.")
        log("On POCO/Xiaomi devices, enable Developer options > USB debugging (Security settings).")
        log("If that option exists, also enable Install via USB, then reconnect the cable and accept prompts.")
        sys.exit(1)

    log("Script complete.")


if __name__ == "__main__":
    main()
