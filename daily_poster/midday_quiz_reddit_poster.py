"""
Reddit Midday Quiz Poster
=========================
Creates one daily link post in r/pineapplecactus for the current quiz surfaced by
https://www.pineapplecactus.com/todays-quiz.

The script resolves the current quiz from Pineapple Cactus' DailyFix API,
builds the final quiz details URL, uses the live quiz title as the Reddit post
title, and includes the quiz description in the post body.

Usage:
    python daily_poster/midday_quiz_reddit_poster.py

Set DRY_RUN = True below to test navigation and form filling without tapping Post.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import date, datetime
from html import unescape
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import daily_puzzle_reddit_poster as base


DRY_RUN = False

TARGET_SUBREDDIT = "pineapplecactus"
DAILY_QUIZ_URL = "https://www.pineapplecactus.com/todays-quiz"
DAILY_FIX_API_URL = "https://www.pineapplecactus.com/api/Quiz/DailyFix"
TARGET_FLAIR = "Quiz"
TARGET_REDDIT_ACCOUNT = "u/PineappleCactusQuiz"
MAX_REDDIT_TITLE_LENGTH = 300

POST_HISTORY_FILE = Path(__file__).with_name("midday_quiz_post_history.json")
BODY_FOOTER = "***We post a new quiz every day 🍍 If you enjoy these, you can tap the 🔔 to get notified when they go live.***"

TITLE_TEMPLATES = [
    "{quiz_title} | Today's Pineapple Cactus Quiz 🍍 ({date_label})",
    "Can you beat today's quiz: {quiz_title}? 🧠 ({date_label})",
    "Ready for today's challenge: {quiz_title}? 🌵 ({date_label})",
    "How well will you do on: {quiz_title}? 👀 ({date_label})",
    "Give today's quiz a go: {quiz_title} 🔥 ({date_label})",
    "Think you can ace: {quiz_title}? 🍍 ({date_label})",
    "Midday quiz drop: {quiz_title} 🧠 ({date_label})",
    "Try today's Pineapple Cactus quiz: {quiz_title} 🌵 ({date_label})",
]


def configure_base_module():
    base.DRY_RUN = DRY_RUN
    base.TARGET_SUBREDDIT = TARGET_SUBREDDIT
    base.TARGET_FLAIR = TARGET_FLAIR
    base.TARGET_REDDIT_ACCOUNT = TARGET_REDDIT_ACCOUNT
    base.POST_HISTORY_FILE = POST_HISTORY_FILE


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    lowered = lowered.replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "quiz"


def fetch_daily_quiz_item() -> dict[str, str]:
    request = Request(
        DAILY_FIX_API_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except URLError as exc:
        raise RuntimeError(f"Could not fetch daily quiz metadata: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Daily quiz API returned invalid JSON: {exc}") from exc

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("Daily quiz API did not return any quiz items.")

    first_item = items[0]
    if not isinstance(first_item, dict):
        raise RuntimeError("Daily quiz API returned an unexpected item format.")

    quiz_id = str(first_item.get("id") or "").strip()
    title = unescape(str(first_item.get("title") or "").strip())
    description = unescape(str(first_item.get("description") or "").strip())

    if not quiz_id or not title:
        raise RuntimeError("Daily quiz API response is missing the quiz id or title.")

    return {
        "id": quiz_id,
        "title": title,
        "description": description,
    }


def build_quiz_url(quiz_id: str, quiz_title: str) -> str:
    return f"https://www.pineapplecactus.com/quiz/{slugify(quiz_title)}-{quiz_id}"


def fit_reddit_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    if len(cleaned) <= MAX_REDDIT_TITLE_LENGTH:
        return cleaned
    return cleaned[: MAX_REDDIT_TITLE_LENGTH - 3].rstrip() + "..."


def build_reddit_title(quiz_item: dict[str, str], post_day: date) -> str:
    date_label = post_day.strftime("%d/%m")
    quiz_title = quiz_item["title"].strip()
    seed = post_day.toordinal() + sum(ord(char) for char in quiz_item["id"])
    template = TITLE_TEMPLATES[seed % len(TITLE_TEMPLATES)]
    return fit_reddit_title(
        template.format(
            quiz_title=quiz_title,
            date_label=date_label,
        )
    )


def build_post_payload(post_day: date | None = None) -> dict[str, str]:
    post_day = post_day or date.today()
    quiz_item = fetch_daily_quiz_item()
    title = build_reddit_title(quiz_item, post_day)
    description = quiz_item["description"]
    body_parts = [part for part in (description, BODY_FOOTER) if part]
    body = "\n\n".join(body_parts)
    final_url = build_quiz_url(quiz_item["id"], quiz_item["title"])

    return {
        "date_key": post_day.isoformat(),
        "date_label": post_day.strftime("%d/%m"),
        "title": title,
        "quiz_title": quiz_item["title"],
        "body": body,
        "url": final_url,
        "source_url": DAILY_QUIZ_URL,
        "description": description,
    }


def main():
    configure_base_module()

    started_at = datetime.now()
    deadline = base.time.monotonic() + base.MAX_RUNTIME_SECONDS
    submission_recorded = False
    d = None

    post_payload = build_post_payload()

    if base.successful_post_exists(date.today()):
        base.log("A successful midday quiz post is already recorded for today. Exiting without posting again.")
        return

    base.log(f"Prepared midday quiz title: {post_payload['title']}")
    if post_payload.get("quiz_title"):
        base.log(f"Source quiz title: {post_payload['quiz_title']}")
    base.log(f"Resolved quiz URL: {post_payload['url']}")
    if post_payload.get("description"):
        base.log(f"Resolved quiz description: {post_payload['description']}")

    if base.DRY_RUN:
        base.log("DRY RUN MODE — the script will stop before the final Post tap.")

    if base.time.monotonic() >= deadline:
        raise RuntimeError("Runtime budget expired before the poster could start.")

    base.log("Checking ADB device visibility...")
    try:
        devices = base.adb_connected_devices()
    except Exception as exc:
        base.log(f"Failed to query the local ADB server: {exc}")
        sys.exit(1)

    if not devices:
        base.log("No Android device is visible to ADB.")
        base.log("Check USB debugging, authorization prompts, and that the phone is unlocked.")
        sys.exit(1)

    base.log("Connecting to Android device via USB...")
    try:
        d = base.u2.connect()
    except Exception as exc:
        base.log(f"Failed to connect: {exc}")
        base.log("Run 'adb devices' to confirm the device is visible and authorized.")
        sys.exit(1)

    info = d.device_info
    base.log(f"Connected: {info.get('productName', 'unknown')} (Android {info.get('version', '?')})")
    d.screen_on()

    try:
        base.go_to_home_screen(d)
        base.ensure_target_account(d)
        base.open_submit_screen(d)
        base.populate_post_form(d, post_payload)

        if base.DRY_RUN:
            base.record_post_attempt(post_payload, "dry_run", "Midday quiz form populated without submitting.")
            base.log("Dry run complete. Review the populated Reddit form on the device.")
            return

        base.tap_post_button(d)
        status, details = base.wait_for_submission_result(d)
        base.log(f"Submission result: {status} ({details})")
        base.record_post_attempt(post_payload, status, details)
        submission_recorded = True

        if status != "success":
            raise RuntimeError(f"Reddit did not confirm a successful post: {details}")
    except base.InputInjectionBlocked:
        base.record_post_attempt(post_payload, "input_blocked", "ADB/UIAutomator input injection blocked by device settings.")
        base.log("The phone blocked simulated taps or swipes from ADB/UIAutomator.")
        base.log("Enable any device-specific USB debugging security options, then try again.")
        sys.exit(1)
    except Exception as exc:
        if not base.DRY_RUN and not submission_recorded:
            base.record_post_attempt(post_payload, "crashed", str(exc))
        raise
    finally:
        if d is not None:
            base.close_reddit_app(d)
        elapsed = int((datetime.now() - started_at).total_seconds())
        base.log(f"Runtime: {elapsed} seconds")


if __name__ == "__main__":
    main()