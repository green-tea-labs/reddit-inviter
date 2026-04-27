"""
UI Hierarchy Discovery Tool
===========================
Run this script ONCE before using reddit_inviter.py to capture the Reddit app's
UI element structure at each key screen. This generates XML files you search to
find the exact resource-id values for your installed version of the Reddit app.

Reddit's app (React Native) changes its internal resource IDs across updates, so
you need to discover them on your own device.

Usage:
    python discover_ui.py

After running, open each XML file in a text editor (or VS Code) and search for:
    "comment"  -> find the comment-count element resource-id
    "u/"       -> find username element resource-id
    "invite"   -> find the invite button resource-id
    "sort"     -> find the sort/filter button resource-id
    "new"      -> find the "New" sort option resource-id

Copy the relevant resource-id values into the CONFIG dict in reddit_inviter.py
"""

import os
import time
import uiautomator2 as u2

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def dump_screen(d, name: str):
    path = os.path.join(OUTPUT_DIR, f"ui_{name}.xml")
    xml = d.dump_hierarchy(pretty=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"  Saved: {path}")


def main():
    print("Connecting to device...")
    d = u2.connect()
    print(f"Connected: {d.device_info.get('productName', 'unknown')}\n")

    print("Starting Reddit app...")
    d.app_start("com.reddit.frontpage")
    print("Waiting 5 seconds for the app to load...")
    time.sleep(5)

    screens = [
        (
            "1_feed",
            "Navigate to r/dailyguess so the post feed is fully loaded",
        ),
        (
            "2_post_open",
            "Tap on a post with 100+ comments so it is open and comments are visible",
        ),
        (
            "3_sort_filter_open",
            "Tap the sort/filter button on the post so the sort OPTIONS are visible (dropdown open)",
        ),
        (
            "4_user_profile",
            "Close the sort menu, then tap a commenter's username so their profile page is open",
        ),
        (
            "5_overflow_menu",
            "Tap the 3-dot overflow menu on the user profile (before tapping any option)",
        ),
        (
            "6_invite_dialog",
            "Tap 'Invite to community' (or similar) so the community-search screen is visible",
        ),
    ]

    for screen_key, instruction in screens:
        print(f"\n{'─' * 60}")
        print(f"  Screen: [{screen_key}]")
        print(f"  Action: {instruction}")
        input("  >> Press Enter when ready to dump this screen... ")
        dump_screen(d, screen_key)
        print(f"  Done.")

    print(f"\n{'═' * 60}")
    print("All screens captured!")
    print()
    print("Now open the XML files in this folder and search for:")
    print("  'comment'  -> comment count element (look for text like '842 comments')")
    print("  'u/'       -> username element (look for text starting with 'u/')")
    print("  'invite'   -> invite button element")
    print("  'sort'     -> sort/filter button element")
    print("  'new'      -> 'New' sort option element")
    print()
    print("Update the CONFIG dict in reddit_inviter.py with any resource-id values you find.")
    print("If resource-ids are absent or unstable, text-based selectors (already in the script)")
    print("will be used as the default — no changes needed.")


if __name__ == "__main__":
    main()
