"""Utilities for switching Reddit Android app accounts via UIAutomator2."""

from __future__ import annotations

import re
import time


REDDIT_PACKAGE = "com.reddit.frontpage"
PROFILE_OPEN_DELAY_SECONDS = 4.0
ACCOUNT_SWITCHER_DELAY_SECONDS = 2.5
ACCOUNT_SWITCH_TIMEOUT_SECONDS = 10.0


def normalize_account_username(username: str) -> str:
    normalized = username.strip().lower()
    if normalized.startswith("u/"):
        normalized = normalized[2:]
    return normalized


def format_account_username(username: str) -> str:
    normalized = normalize_account_username(username)
    return f"u/{normalized}"


def iter_selector_elements(selector):
    for index in range(selector.count):
        yield selector[index]


def current_account_username(d) -> str:
    for selector in (
        d(resourceId="logged_in_user"),
        d(resourceId="profile_username_text"),
    ):
        try:
            if selector.exists(timeout=0.2):
                info = getattr(selector, "info", {}) or {}
                text = (info.get("text") or "").strip()
                if text:
                    return normalize_account_username(text)
        except Exception:
            continue

    for text in visible_texts(d):
        if text.lower().startswith("u/"):
            return normalize_account_username(text)

    return ""


def visible_texts(d) -> list[str]:
    texts: list[str] = []
    try:
        for selector in (
            d(className="android.widget.TextView"),
            d(className="android.view.View"),
        ):
            for element in iter_selector_elements(selector):
                info = getattr(element, "info", {}) or {}
                for key in ("text", "contentDescription"):
                    value = (info.get(key) or "").strip()
                    if value and value not in texts:
                        texts.append(value)
    except Exception:
        return texts

    return texts


def open_reddit_home(d, pause):
    d.shell(
        'am start -W -S -a android.intent.action.VIEW '
        '-d "https://www.reddit.com/" '
        f'{REDDIT_PACKAGE}'
    )
    pause(6.0)


def open_profile_tab(d, log, pause, safe_click) -> bool:
    if d(resourceId="account_switcher_button").exists(timeout=0.6):
        return True

    selectors = (
        d(resourceId="bottom_nav_button_label", text="You"),
        d(text="You"),
        d(descriptionMatches=r"(?i).+ account"),
    )

    for selector in selectors:
        if selector.exists(timeout=0.6):
            log("Opening the Reddit profile tab via the bottom-right You button.")
            safe_click(d, selector)
            pause(PROFILE_OPEN_DELAY_SECONDS)
            return d(resourceId="account_switcher_button").exists(timeout=1.0)

    return False


def open_account_switcher(d, log, pause, safe_click) -> bool:
    button = d(resourceId="account_switcher_button")
    if button.exists(timeout=0.8):
        log("Opening the account switcher.")
        safe_click(d, button)
        pause(ACCOUNT_SWITCHER_DELAY_SECONDS)
        return d(resourceId="com.reddit.frontpage:id/account_picker_accounts").exists(timeout=1.0)
    return False


def select_account_row(d, target_username: str, safe_click) -> bool:
    target_normalized = normalize_account_username(target_username)

    selector = d(resourceId="com.reddit.frontpage:id/account_name")
    for row in iter_selector_elements(selector):
        try:
            info = getattr(row, "info", {}) or {}
            text = (info.get("text") or "").strip()
        except Exception:
            text = ""

        if normalize_account_username(text) == target_normalized:
            safe_click(d, row)
            return True

    fallback = d(textMatches=rf"(?i)^u/{re.escape(target_normalized)}$")
    if fallback.exists(timeout=0.5):
        safe_click(d, fallback)
        return True

    return False


def wait_for_account_switch(d, target_username: str, pause, safe_click) -> bool:
    deadline = time.monotonic() + ACCOUNT_SWITCH_TIMEOUT_SECONDS
    target_normalized = normalize_account_username(target_username)

    while time.monotonic() < deadline:
        if d(resourceId="account_switcher_button").exists(timeout=0.3):
            current = current_account_username(d)
            if current == target_normalized:
                return True
        else:
            open_profile_tab(d, lambda *_args, **_kwargs: None, pause, safe_click)
            current = current_account_username(d)
            if current == target_normalized:
                return True

        pause(0.6)

    return False


def switch_reddit_account(d, target_username: str, log, pause, safe_click) -> bool:
    formatted_target = format_account_username(target_username)
    target_normalized = normalize_account_username(target_username)

    open_reddit_home(d, pause)

    if not open_profile_tab(d, log, pause, safe_click):
        raise RuntimeError("Could not open the Reddit profile tab to switch accounts.")

    current = current_account_username(d)
    if current == target_normalized:
        log(f"Reddit account already set to {formatted_target}.")
        return True

    if not open_account_switcher(d, log, pause, safe_click):
        raise RuntimeError("Could not open the Reddit account switcher.")

    if not select_account_row(d, target_username, safe_click):
        raise RuntimeError(f"The account {formatted_target} was not found in the Reddit account switcher.")

    pause(3.0)
    if wait_for_account_switch(d, target_username, pause, safe_click):
        log(f"Switched Reddit account to {formatted_target}.")
        return True

    raise RuntimeError(f"Reddit did not finish switching to {formatted_target}.")