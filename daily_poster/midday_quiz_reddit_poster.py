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

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from html import unescape
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from console_output import run_with_logging, start_run_logging

if __name__ == "__main__":
    start_run_logging(__file__)

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
    "Your midday brain break: {quiz_title} 🧩 ({date_label})",
    "Today's quiz is ready: {quiz_title} 🍍 ({date_label})",
    "What do you know about {quiz_title}? 🧠 ({date_label})",
    "Time for a quiz break: {quiz_title} ☕ ({date_label})",
    "Put yourself to the test with {quiz_title} 🎯 ({date_label})",
    "A fresh quiz for your day: {quiz_title} 🌵 ({date_label})",
    "Who's trying {quiz_title} today? 👀 ({date_label})",
    "Today's knowledge check: {quiz_title} 🧠 ({date_label})",
    "Take a break with {quiz_title} 🍍 ({date_label})",
    "Your next quiz is here: {quiz_title} 🧩 ({date_label})",
    "Have a go at {quiz_title} today 🎯 ({date_label})",
    "New quiz on the menu: {quiz_title} ☕ ({date_label})",
    "How much can you remember? {quiz_title} 🧠 ({date_label})",
    "Midday at Pineapple Cactus: {quiz_title} 🍍🌵 ({date_label})",
    "Today's quiz spotlight: {quiz_title} 🔦 ({date_label})",
    "Looking for a brain break? {quiz_title} 🧩 ({date_label})",
    "Try your luck with {quiz_title} 👀 ({date_label})",
    "Quiz time: {quiz_title} 🍍 ({date_label})",
    "Ready to test your knowledge? {quiz_title} 🎯 ({date_label})",
    "Today's lunchtime quiz: {quiz_title} ☕ ({date_label})",
    "See how you fare: {quiz_title} 🌵 ({date_label})",
    "A little knowledge workout: {quiz_title} 🧠 ({date_label})",
    "New day, new quiz: {quiz_title} 🍍 ({date_label})",
    "Your daily quiz link: {quiz_title} 🧩 ({date_label})",
    "Got your thinking cap on? {quiz_title} 🎯 ({date_label})",
    "Take on {quiz_title} at your own pace 🌵 ({date_label})",
    "What will your score be? {quiz_title} 👀 ({date_label})",
    "Today's Pineapple Cactus pick: {quiz_title} 🍍 ({date_label})",
    "Make room for {quiz_title} in your next break ☕ ({date_label})",
    "A quiz to get you thinking: {quiz_title} 🧠 ({date_label})",
    "The midday quiz has landed: {quiz_title} 🧩 ({date_label})",
    "Give your knowledge a workout: {quiz_title} 🎯 ({date_label})",
    "Fancy a quiz? Try {quiz_title} 🌵 ({date_label})",
    "Today's quiz invitation: {quiz_title} 🍍 ({date_label})",
    "Something for your next coffee break: {quiz_title} ☕ ({date_label})",
    "How confident are you on {quiz_title}? 👀 ({date_label})",
    "Let's see what you know: {quiz_title} 🧠 ({date_label})",
    "Today's quiz is calling: {quiz_title} 🍍 ({date_label})",
    "Your next knowledge challenge: {quiz_title} 🎯 ({date_label})",
    "Drop into today's quiz: {quiz_title} 🌵 ({date_label})",
    "A fresh reason to take a quiz break: {quiz_title} 🧩 ({date_label})",
    "Who's up for {quiz_title}? 🍍 ({date_label})",
    "Today's quiz lineup starts with {quiz_title} 🧠 ({date_label})",
    "Bring your best guesses: {quiz_title} 👀 ({date_label})",
    "Time to meet today's quiz: {quiz_title} 🎯 ({date_label})",
    "Your daily helping of trivia: {quiz_title} 🍍 ({date_label})",
    "Can {quiz_title} catch you out? 🌵 ({date_label})",
    "A little quiz for a well-earned break: {quiz_title} ☕ ({date_label})",
    "Today we're quizzing on {quiz_title} 🧠 ({date_label})",
    "Pick up today's quiz: {quiz_title} 🧩 ({date_label})",
    "Your midday knowledge check is here: {quiz_title} 🎯 ({date_label})",
    "Put your quiz instincts to work: {quiz_title} 👀 ({date_label})",
    "Today's quiz drop from Pineapple Cactus: {quiz_title} 🍍 ({date_label})",
    "Make this your next brain break: {quiz_title} 🌵 ({date_label})",
    "A new quiz to get stuck into: {quiz_title} 🧩 ({date_label})",
    "See what you make of {quiz_title} 🧠 ({date_label})",
    "Fancy testing yourself on {quiz_title}? 🎯 ({date_label})",
    "The daily quiz is live: {quiz_title} 🍍 ({date_label})",
    "Another quiz day, another topic: {quiz_title} 🌵 ({date_label})",
    "What's your verdict on {quiz_title}? 👀 ({date_label})",
    "Take today's quiz for a spin: {quiz_title} 🧩 ({date_label})",
    "Your quiz break starts here: {quiz_title} ☕ ({date_label})",
    "Show us what you know: {quiz_title} 🧠 ({date_label})",
    "Ready when you are: {quiz_title} 🍍🌵 ({date_label})",
]

BODY_INTROS = [
    "Today’s quiz is live. Give it a go and see how you get on.",
    "A fresh quiz has landed for your next brain break.",
    "Ready to put your knowledge to the test? Here’s today’s quiz.",
    "Take a little time out with today’s Pineapple Cactus quiz.",
    "Your midday quiz is ready. Bring your best guesses.",
    "Fancy a change of pace? Try today’s quiz and see what you know.",
    "Pick up today’s quiz whenever you’re ready for a challenge.",
    "Here’s a fresh excuse to take a quiz break today.",
    "Today’s knowledge check has arrived. How will you do?",
    "Put the kettle on and give today’s quiz a try.",
    "A new day brings a new quiz. Come and join in.",
    "Think you know your stuff? Put it to work in today’s quiz.",
    "There’s a fresh quiz waiting for your next break.",
    "Here’s today’s link for anyone in the mood for a little trivia.",
    "Give your brain something different to work on with today’s quiz.",
    "Your daily quiz check-in is here. See what you make of this one.",
    "A little knowledge workout is ready when you are.",
    "Today’s quiz is up. Have a go before reading everyone else’s results.",
    "Take on today’s quiz at your own pace and let us know how it goes.",
    "Looking for something to get you thinking? Here’s the latest quiz.",
    "Come and try today’s quiz. You might surprise yourself.",
    "Time for another Pineapple Cactus quiz break.",
    "Bring your curiosity along to today’s quiz.",
    "How confident are you feeling today? Put it to the test.",
    "A fresh quiz is ready for a fresh pair of eyes.",
    "Swap a little scrolling time for some thinking time with today’s quiz.",
    "Your next knowledge challenge starts with today’s quiz link.",
    "Got your thinking cap handy? Today’s quiz is waiting.",
    "Here’s today’s invitation to test yourself on something fun.",
    "Another quiz day is here. Jump in whenever it suits you.",
    "Try today’s quiz and tell us which questions made you stop and think.",
    "Make your next break a quiz break with today’s offering.",
    "Today’s quiz has landed. What will your final score look like?",
    "A new topic, a fresh quiz, and a chance to see what you remember.",
    "Think you’ve got this one covered? Give today’s quiz your best shot.",
    "Drop in for today’s quiz and see how your knowledge holds up.",
    "If you’re in a quiz mood, today’s link is ready for you.",
    "Put your quiz instincts to work on today’s questions.",
    "Your next little brain workout is waiting in today’s quiz.",
    "Take a breather and see how you fare with today’s quiz.",
    "Here’s a new quiz to get stuck into on your next break.",
    "Test what you know, and maybe pick up something new along the way.",
    "Today’s quiz is open. See where your knowledge takes you.",
    "A fresh quiz is on the menu. Ready to have a go?",
    "Fancy testing your memory today? Start with the latest quiz.",
    "Another day, another reason to put your knowledge to the test.",
    "Here’s today’s quiz for anyone who enjoys a good knowledge challenge.",
    "Try today’s questions and see which ones click straight away.",
    "Today’s quiz is ready for its next player. Want to join in?",
    "Need a little distraction? Today’s quiz is here for your next break.",
    "Bring what you know and make your best guesses on the rest.",
    "Give today’s quiz a spin, then come back and share your thoughts.",
    "Your daily dose of quiz questions is ready.",
    "Here’s something for your next coffee break: today’s fresh quiz.",
    "A new quiz day means another chance to test your knowledge.",
    "Today’s quiz link is here. Save it for later or jump straight in.",
    "See how you do with today’s questions and compare notes afterwards.",
    "There’s a fresh knowledge challenge waiting for you today.",
    "Give your usual routine a quiz-shaped detour today.",
    "Ready for a little friendly competition with yourself? Try today’s quiz.",
    "Today’s Pineapple Cactus quiz is live and ready to play.",
    "Come for the questions, stay to see how you did.",
    "Set aside a moment for today’s quiz and give it your best attempt.",
    "Your next quiz break is just a link away. Here’s today’s pick.",
]

BODY_FOOTERS = [
    BODY_FOOTER,
    "***A fresh quiz lands every day 🍍 Tap the 🔔 if you’d like a reminder for the next one.***",
    "***Enjoyed today’s quiz? There’s another one tomorrow 🌵 Tap the 🔔 for notifications.***",
    "***Make us part of your daily quiz break 🧠 Tap the 🔔 to keep up with new posts.***",
    "***Come back tomorrow for another quiz 🍍 The 🔔 can help you catch the next post.***",
    "***We’ll be back with another quiz tomorrow 🧩 Tap the 🔔 if you want to follow along.***",
    "***There’s a new quiz each day 🎯 Tap the 🔔 if that sounds like your kind of routine.***",
    "***Thanks for giving today’s quiz a go 🍍 Tap the 🔔 if you’d like to catch the next one.***",
    "***More quizzes are on the way 🌵 You can tap the 🔔 for updates when they’re posted.***",
    "***Fancy doing this again tomorrow? 🧠 Tap the 🔔 to follow our daily quiz posts.***",
    "***Keep a little room for tomorrow’s quiz 🍍 Tap the 🔔 for notifications.***",
    "***Another day, another quiz 🧩 Tap the 🔔 if you’d like to join us for the next one.***",
    "***We share a fresh quiz every day 🎯 Tap the 🔔 to hear when the next one goes live.***",
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
    seed = post_day.toordinal()
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
    seed = post_day.toordinal()
    intro = BODY_INTROS[(seed * 5 + 3) % len(BODY_INTROS)]
    footer = BODY_FOOTERS[seed % len(BODY_FOOTERS)]
    body_parts = [part for part in (intro, description, footer) if part]
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


def main(dry_run: bool = DRY_RUN):
    configure_base_module()
    base.DRY_RUN = dry_run

    started_at = datetime.now()
    deadline = base.time.monotonic() + base.MAX_RUNTIME_SECONDS
    submission_recorded = False
    d = None

    post_payload = build_post_payload()

    if not base.DRY_RUN and base.successful_post_exists(date.today()):
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
            base.save_ui_diagnostics(d, "dry-run")
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
        base.save_failure_diagnostics(d)
        if not base.DRY_RUN and not submission_recorded:
            base.record_post_attempt(post_payload, "crashed", str(exc))
        raise
    finally:
        if d is not None:
            base.close_reddit_app(d)
        elapsed = int((datetime.now() - started_at).total_seconds())
        base.log(f"Runtime: {elapsed} seconds")


def cli():
    parser = argparse.ArgumentParser(description="Post today's midday quiz to Reddit.")
    parser.add_argument("--dry-run", action="store_true", default=DRY_RUN,
                        help="populate the form without tapping Post")
    main(dry_run=parser.parse_args().dry_run)


if __name__ == "__main__":
    run_with_logging(__file__, cli)
