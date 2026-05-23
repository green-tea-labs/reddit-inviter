"""
Reddit Daily Challenge Poster
=============================
Creates one daily link post in r/pineapplecactus for the current daily challenge
using the Reddit Android app running on a USB-connected Android phone.

The script mirrors the daily puzzle poster flow:
1. Opens the subreddit submit screen in the Reddit app.
2. Selects the daily title/body variant based on the current date.
3. Fills out a link post for https://www.pineapplecactus.com/daily-challenges.
4. Records successful submissions locally so the same day is not posted twice.

Usage:
    python daily_poster/daily_challenge_reddit_poster.py

Set DRY_RUN = True below to test navigation and form filling without tapping Post.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import daily_puzzle_reddit_poster as base


DRY_RUN = False

TARGET_SUBREDDIT = "pineapplecactus"
TARGET_URL = "https://www.pineapplecactus.com/daily-challenges"
TARGET_FLAIR = "🎯Challenge"
TARGET_REDDIT_ACCOUNT = "u/PineappleCactusQuiz"

POST_HISTORY_FILE = Path(__file__).with_name("daily_challenge_post_history.json")

TITLE_TEMPLATES = [
    "Pineapple Cactus - Daily Challenges 🍍🌵 - {date_label}",
    "Can you take on today’s daily challenges? 🔥 ({date_label})",
    "Ready for today’s daily challenge drop? 🧠 ({date_label})",
    "How many daily challenges can you beat today? 👀 ({date_label})",
    "Take a shot at today’s daily challenges 🍍 ({date_label})",
    "Think you can handle today’s challenges? 🌵 ({date_label})",
    "Today’s daily challenges are live now 🧩 ({date_label})",
    "Jump into today’s challenge set 🧠🔥 ({date_label})",
    "Your daily challenge lineup is ready 🍍🌵 ({date_label})",
    "Can you conquer today’s daily challenges? ⚡ ({date_label})",
    "Fresh daily challenges just dropped 👀 ({date_label})",
    "How far can you get in today’s challenge set? 🧠 ({date_label})",
    "Today’s Pineapple Cactus challenges are waiting 🌵 ({date_label})",
    "Give today’s daily challenges a try 🔥 ({date_label})",
    "New day, new daily challenges 🍍 ({date_label})",
    "Up for today’s challenge run? 🧩 ({date_label})",
    "See if you can beat today’s daily challenge set 👀 ({date_label})",
    "Test yourself with today’s daily challenges 🧠🔥 ({date_label})",
]

BODY_INTROS = [
    "Today’s daily challenges are live and ready when you are. See how many you can beat.",
    "A new set of daily challenges has dropped today. Give them a go.",
    "Ready for a quick brain workout? Today’s daily challenges are waiting.",
    "Take on today’s daily challenges and see how far you get.",
    "If you’re up for it, today’s daily challenges are lined up and ready.",
    "See how you do with today’s fresh set of daily challenges.",
    "Today’s challenge set is up. Jump in and see which ones you can clear.",
    "There’s a fresh batch of daily challenges waiting for you today.",
    "Put your brain to work with today’s lineup of daily challenges.",
    "Give today’s daily challenges a go and see how many you can finish.",
    "If you want a quick challenge session, today’s set is ready.",
    "See whether today’s daily challenges can stump you.",
    "A new day means a new round of daily challenges to take on.",
    "Jump into today’s daily challenges and test yourself.",
    "Today’s daily challenges are ready whenever you are.",
    "Take a crack at today’s challenge lineup and see how you do.",
]

BODY_FOOTER = "***We post new daily challenges every day 🍍 If you enjoy these, you can tap the 🔔 to get notified when they go live.***"


def configure_base_module():
    base.DRY_RUN = DRY_RUN
    base.TARGET_SUBREDDIT = TARGET_SUBREDDIT
    base.TARGET_URL = TARGET_URL
    base.TARGET_FLAIR = TARGET_FLAIR
    base.TARGET_REDDIT_ACCOUNT = TARGET_REDDIT_ACCOUNT
    base.POST_HISTORY_FILE = POST_HISTORY_FILE
    base.TITLE_TEMPLATES = TITLE_TEMPLATES
    base.BODY_INTROS = BODY_INTROS
    base.BODY_FOOTER = BODY_FOOTER


def main():
    configure_base_module()

    started_at = datetime.now()
    deadline = base.time.monotonic() + base.MAX_RUNTIME_SECONDS
    post_payload = base.build_post_payload()
    submission_recorded = False
    d = None

    if base.successful_post_exists(date.today()):
        base.log("A successful daily challenge post is already recorded for today. Exiting without posting again.")
        return

    base.log(f"Prepared daily challenge title: {post_payload['title']}")
    base.log(f"Prepared target URL: {post_payload['url']}")

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
            base.record_post_attempt(post_payload, "dry_run", "Daily challenge form populated without submitting.")
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