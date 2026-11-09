"""
Reddit Daily Challenge Poster
=============================
Creates one daily link post in r/pineapplecactus for the current daily challenge
using the Reddit Android app running on a USB-connected Android phone.

The script mirrors the daily puzzle poster flow:
1. Opens the subreddit submit screen in the Reddit app.
2. Selects the daily title/body variant based on the current date.
3. Fills out a link post for https://www.pineapplecactus.com/daily-challenges/YYYY-MM-DD.
4. Records successful submissions locally so the same day is not posted twice.

Usage:
    python daily_poster/daily_challenge_reddit_poster.py

Set DRY_RUN = True below to test navigation and form filling without tapping Post.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from console_output import run_with_logging, start_run_logging

if __name__ == "__main__":
    start_run_logging(__file__)

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
    "What’s your first challenge today? 🍍 ({date_label})",
    "Your next brain break starts here 🧩 ({date_label})",
    "A fresh challenge set for your coffee break ☕ ({date_label})",
    "Today’s challenge lineup has arrived 🌵 ({date_label})",
    "Which of today’s challenges will you try first? 👀 ({date_label})",
    "Time for another Pineapple Cactus challenge day 🍍 ({date_label})",
    "Make room for a little puzzling today 🧠 ({date_label})",
    "Today’s daily challenges: give them your best shot 🎯 ({date_label})",
    "Got a few minutes for today’s challenges? ⏳ ({date_label})",
    "A new daily challenge set to get stuck into 🧩 ({date_label})",
    "How’s your brain feeling today? Put it to the test 🍍 ({date_label})",
    "Your daily dose of Pineapple Cactus challenges 🌵 ({date_label})",
    "The next round of daily challenges is here 🔥 ({date_label})",
    "A little challenge for your day 🧠 ({date_label})",
    "Take a puzzle break with today’s daily challenges ☕ ({date_label})",
    "New challenges, fresh start 🍍 ({date_label})",
    "Today’s challenge set is open — how will you do? 🎯 ({date_label})",
    "Give your brain something to chew on 🧩 ({date_label})",
    "Can today’s challenges catch you out? 👀 ({date_label})",
    "Your daily challenge check-in 🌵 ({date_label})",
    "The daily challenge board is ready for you 🍍 ({date_label})",
    "What will you solve today? 🧠 ({date_label})",
    "Daily challenges for a well-earned break ☕ ({date_label})",
    "Pick a challenge and jump in 🎯 ({date_label})",
    "A fresh set of brain teasers awaits 🧩 ({date_label})",
    "Let’s see what today’s challenges have in store 👀 ({date_label})",
    "Today’s Pineapple Cactus challenge drop 🍍🌵 ({date_label})",
    "Need a change of pace? Try today’s challenges 🧠 ({date_label})",
    "Another day to put your puzzle skills to work 🎯 ({date_label})",
    "Your next challenge is waiting 🍍 ({date_label})",
    "A new daily challenge lineup to explore 🧩 ({date_label})",
    "How many of today’s challenges can you finish? 🌵 ({date_label})",
    "Challenge yourself to something new today 🔥 ({date_label})",
    "Set aside a moment for today’s brain teasers 🧠 ({date_label})",
    "Daily challenge time — who’s joining in? 🍍 ({date_label})",
    "A fresh batch of challenges for curious minds 🧩 ({date_label})",
    "Start with one challenge and see where it takes you 🎯 ({date_label})",
    "Today’s challenge set is calling 👀 ({date_label})",
    "Looking for your next puzzle break? 🌵 ({date_label})",
    "Another fresh challenge day at Pineapple Cactus 🍍 ({date_label})",
    "Put today’s challenge lineup through its paces 🔥 ({date_label})",
    "Ready to give your brain a little exercise? 🧠 ({date_label})",
    "Your daily challenge link is here 🧩 ({date_label})",
    "Take on a fresh set of challenges at your own pace 🌵 ({date_label})",
    "Today’s brain break, courtesy of Pineapple Cactus 🍍 ({date_label})",
    "A few new challenges to brighten your break ☕ ({date_label})",
    "What’s your verdict on today’s challenge set? 👀 ({date_label})",
    "Time to meet today’s daily challenges 🎯 ({date_label})",
    "A new day of challenges starts here 🌵 ({date_label})",
    "Fancy testing your puzzle instincts today? 🧠 ({date_label})",
    "Drop into today’s Pineapple Cactus challenges 🍍 ({date_label})",
    "Today’s challenge lineup: ready when you are 🧩 ({date_label})",
    "Which challenge gets your brain going today? 🔥 ({date_label})",
    "Make today a challenge day 🍍🌵 ({date_label})",
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
    "Looking for something to puzzle over? Today’s challenge set is ready for you.",
    "Give your usual scrolling a break and try a few of today’s challenges.",
    "Pick a challenge that catches your eye and see where it takes you.",
    "Your next brain break is here. Come and explore today’s daily challenges.",
    "A fresh challenge day has arrived at Pineapple Cactus. What will you try first?",
    "Settle in with today’s challenges and work through them at your own pace.",
    "Fancy putting your puzzle instincts to work? There’s a new set waiting today.",
    "Today’s challenges are up. Start with one and see how you get on.",
    "Here’s a fresh excuse to take a puzzle break. Give today’s challenges a try.",
    "A new day brings a different challenge lineup. Have a look and join in.",
    "Whether you try one challenge or the whole set, today’s lineup is ready.",
    "Take a moment away from your to-do list and tackle something just for fun.",
    "The daily challenge link is ready. Drop in whenever you fancy a brain teaser.",
    "Bring your curiosity to today’s challenges and see what you can figure out.",
    "Today’s set is waiting for its next challenger. Want to give it a go?",
    "Make a little room in your day for a challenge or two.",
    "Need a change of pace? Today’s daily challenges might be just the thing.",
    "Put the kettle on, pick a challenge, and give your brain something to work on.",
    "There’s a fresh lineup to explore today. Which challenge will get your attention?",
    "Try your hand at today’s challenges and let us know how you find them.",
    "Your daily challenge check-in is here. Come and see what’s waiting today.",
    "Ready to switch gears for a bit? Take a look at today’s challenge set.",
    "A fresh batch of challenges is ready for your next break.",
    "Today’s Pineapple Cactus challenges are open. Jump in when you’re ready.",
    "Challenge yourself a little today. There’s a new set to get stuck into.",
    "Got your thinking cap handy? Today’s challenge lineup is live.",
    "Give today’s challenges your best shot, then come back and tell us how it went.",
    "Start your next puzzle session here with today’s daily challenges.",
    "Some days you fly through them; other days you need another look. How will today go?",
    "Looking for a bit of brain exercise? Today’s challenges are waiting.",
    "Swap a little screen time for some thinking time with today’s challenge set.",
    "See what you make of today’s lineup. There’s a fresh set ready to play.",
    "Another challenge day is here. Pick your starting point and give it a go.",
    "Today’s challenges are ready for a fresh pair of eyes. Yours, perhaps?",
    "Take a breather and see how you fare against today’s challenge lineup.",
    "Here’s today’s invitation to put your brain to work on something fun.",
    "Try a challenge on your next break, or save today’s set for later.",
    "Come for a quick look, stay for a challenge. Today’s lineup is ready.",
    "Your next little puzzle project is waiting in today’s daily challenges.",
    "There’s a new daily challenge set to discover. Take a look and choose where to begin.",
    "Keep your puzzle streak of curiosity going with today’s fresh challenges.",
    "Today’s lineup is live. Bring your best ideas and see what clicks.",
    "Fancy a challenge before getting back to your day? Here’s the latest set.",
    "A fresh set of challenges, a fresh chance to surprise yourself. Have a go today.",
    "Give your brain a different sort of task with today’s daily challenge lineup.",
    "Today’s challenges have landed. See which ones you enjoy tackling most.",
    "Take today’s challenge set for a spin and share your thoughts afterwards.",
    "Your daily helping of challenges is ready. Dive in whenever it suits you.",
]

BODY_FOOTER = "***We post new daily challenges every day 🍍 If you enjoy these, you can tap the 🔔 to get notified when they go live.***"
BODY_FOOTERS = [
    BODY_FOOTER,
    "***A fresh challenge set lands every day 🍍 Tap the 🔔 if you’d like a reminder for the next one.***",
    "***Enjoyed today’s challenges? There’s another set tomorrow 🌵 You can tap the 🔔 for notifications.***",
    "***Daily challenges are part of our everyday lineup 🧩 Tap the 🔔 to keep up with new posts.***",
    "***Come back tomorrow for another challenge day 🍍 The 🔔 can help you catch the next post.***",
    "***We’ll be back with more daily challenges tomorrow 🧠 Tap the 🔔 if you want to follow along.***",
    "***Make us part of your daily puzzle break 🌵 Tap the 🔔 to hear when new challenges are posted.***",
    "***There’s a new challenge set each day 🎯 If that’s your kind of thing, tap the 🔔 for updates.***",
    "***Thanks for giving today’s challenges a go 🍍 Tap the 🔔 if you’d like to catch the next set.***",
    "***More daily challenges are on the way 🧩 You can tap the 🔔 to get notified about new posts.***",
    "***Keep your next brain break on the calendar 🧠 We post daily; tap the 🔔 for notifications.***",
    "***Fancy doing this again tomorrow? 🌵 Tap the 🔔 to follow our daily challenge posts.***",
    "***Another day, another challenge set 🍍 Tap the 🔔 if you’d like to join us for the next one.***",
]


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


def build_post_payload(post_day: date | None = None) -> dict[str, str]:
    """Keep the challenge URL and title anchored to the same posting date."""
    post_day = post_day or date.today()
    configure_base_module()
    payload = base.build_post_payload(post_day)
    payload["url"] = f"{TARGET_URL.rstrip('/')}/{post_day.isoformat()}"
    footer = BODY_FOOTERS[post_day.toordinal() % len(BODY_FOOTERS)]
    payload["body"] = payload["body"].removesuffix(BODY_FOOTER) + footer
    return payload


def main():

    started_at = datetime.now()
    deadline = base.time.monotonic() + base.MAX_RUNTIME_SECONDS
    post_day = date.today()
    post_payload = build_post_payload(post_day)
    submission_recorded = False
    d = None

    if base.successful_post_exists(post_day):
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
    run_with_logging(__file__, main)
