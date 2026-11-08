"""Inspect or exercise thread navigation without sending Reddit invitations."""

import argparse
import time
import xml.etree.ElementTree as ET

from console_output import run_with_logging, start_run_logging

if __name__ == "__main__":
    start_run_logging(__file__)

import uiautomator2 as u2

from daily_inviter import reddit_inviter as bot


def snapshot(d, details=False):
    print("Screen:", bot.current_screen(d), "app:", d.app_current(), flush=True)
    root = ET.fromstring(d.dump_hierarchy())
    for node in root.iter("node"):
        rid = node.get("resource-id", "")
        desc = node.get("content-desc", "")
        if (any(part in rid for part in ("post_", "feed_", "sort_", "actionBar_"))
                or "comment" in desc.lower() or (details and (node.get("text") or desc or node.get("class") == "android.widget.EditText"))):
            print({key: node.get(key) for key in ("resource-id", "text", "content-desc", "bounds", "clickable")}, flush=True)
        if details and rid.rsplit("/", 1)[-1] == "post_footer":
            print("Footer XML:", ET.tostring(node, encoding="unicode"), flush=True)
    print("Detected cards:", bot.visible_post_cards(d), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subreddit")
    parser.add_argument("--scroll", action="store_true")
    parser.add_argument("--find", action="store_true")
    parser.add_argument("--feed-view", choices=("Card", "Compact"), help="test a specific Reddit feed layout")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--details", action="store_true", help="include full comment-footer XML")
    parser.add_argument("--screenshot", help="save a screenshot of the inspected screen")
    parser.add_argument("--open-invite", action="store_true", help="open the current profile's invite dialog without sending")
    parser.add_argument("--select-community", action="store_true", help="select the invite community without sending")
    args = parser.parse_args()
    d = u2.connect()
    d.screen_on()
    d.shell("wm dismiss-keyguard")
    if args.subreddit:
        bot.open_subreddit(d, args.subreddit)
    if args.feed_view:
        view = d(resourceId="view_mode_icon")
        if view.exists(timeout=3):
            view.click(timeout=3)
            d(description=args.feed_view).click(timeout=3)
            time.sleep(1)
    if args.scroll:
        width, height = d.window_size()
        d.swipe(int(width * .015), int(height * .78), int(width * .015), int(height * .25), .4)
        time.sleep(1)
    if args.open_invite:
        invite = d(text="Invite to Community")
        if not invite.exists(timeout=1):
            bot.safe_tap_relative(d, *bot.COORDINATE_FALLBACKS["profile_more_actions"])
        invite.click(timeout=5)
        time.sleep(1)
    if args.select_community:
        if not bot.select_invite_community(d, "diagnostic"):
            raise SystemExit("Could not select invite community")
        print("Send button:", d(resourceId="com.reddit.frontpage:id/btn_invite").info, flush=True)
    snapshot(d, args.details)
    if args.screenshot:
        d.screenshot().save(args.screenshot)
    if args.find:
        source = args.subreddit
        if not source:
            title = d(resourceId="subreddit_toolbar_title")
            if not title.exists(timeout=1):
                parser.error("--find needs --subreddit when no subreddit title is visible")
            source = title.get_text().replace("\ufeff", "").removeprefix("r/")
        result = bot.find_qualifying_post(d, time.monotonic() + args.timeout, set(), source)
        print("Navigation result:", result, flush=True)
        snapshot(d, args.details)
        if not result[0] or bot.current_screen(d) != "comments":
            raise SystemExit(1)


if __name__ == "__main__":
    run_with_logging(__file__, main)
