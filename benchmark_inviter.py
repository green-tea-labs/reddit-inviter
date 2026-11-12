"""Compare inviter discovery/navigation speed without sending invitations."""

import argparse
import hashlib
import json
import time
from collections import Counter
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from console_output import run_with_logging, start_run_logging

if __name__ == "__main__":
    start_run_logging(__file__)

from daily_inviter import reddit_inviter as bot


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--subreddit", default="dailyguess")
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")

    folder = Path(__file__).resolve().parent / "logs" / "benchmarks"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    label = "".join(char if char.isalnum() or char in "-_" else "_" for char in args.label)
    output = folder / f"{label}_{stamp}.json"
    source = Path(bot.__file__)
    (folder / f"{label}_{stamp}.source.py").write_bytes(source.read_bytes())
    tracked = (bot.INVITED_USERS_FILE, bot.DAILY_TALLY_FILE)
    hashes_before = {str(path): file_hash(path) for path in tracked}
    previously_invited = bot.load_invited_users()
    observed, fresh = set(), set()
    counters, results, durations = Counter(), Counter(), Counter()
    original_users, original_invite, original_log = bot.get_visible_usernames, bot.invite_user, bot.log

    def users(d):
        rows = original_users(d)
        for _, name in rows:
            normalized = bot.normalize_username(name)
            observed.add(normalized)
            if normalized not in previously_invited:
                fresh.add(normalized)
        return rows

    def invite(d, username, dry_run=False):
        if not dry_run:
            raise RuntimeError("Benchmark refuses to send real invitations")
        counters["invite_attempts"] += 1
        result = original_invite(d, username, dry_run=True)
        results[result] += 1
        return result

    def log(message):
        if message.startswith("Comment scan pass"):
            counters["comment_scan_passes"] += 1
        if "Verified: thread comments are open" in message:
            counters["threads_opened"] += 1
        if "Feed scan expected" in message:
            counters["feed_recoveries"] += 1
        original_log(message)

    def timed(name, function):
        def wrapper(*positional, **keywords):
            started = time.monotonic()
            try:
                return function(*positional, **keywords)
            finally:
                durations[name] += time.monotonic() - started
                counters[name + "_calls"] += 1
        return wrapper

    source_hash = file_hash(source)
    started = time.monotonic()
    status = "completed"
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(bot, "get_visible_usernames", users))
            stack.enter_context(patch.object(bot, "invite_user", timed("invite_flow", invite)))
            stack.enter_context(patch.object(bot, "log", log))
            for name in ("ensure_target_account", "open_subreddit", "find_qualifying_post", "dismiss_nsfw_modal", "current_screen", "navigate_back_to_comments"):
                stack.enter_context(patch.object(bot, name, timed(name, getattr(bot, name))))
            bot.main(dry_run=True, subreddit=args.subreddit, max_runtime_seconds=args.seconds)
    except BaseException as exc:
        status = f"failed: {type(exc).__name__}: {exc}"
        raise
    finally:
        elapsed = time.monotonic() - started
        hashes_after = {str(path): file_hash(path) for path in tracked}
        summary = {
            "label": args.label, "status": status, "subreddit": args.subreddit,
            "budget_seconds": args.seconds, "elapsed_seconds": round(elapsed, 2),
            "source_sha256": source_hash, "known_users_at_start": len(previously_invited),
            "unique_visible_users": len(observed), "unique_not_previously_invited": len(fresh),
            "counters": dict(counters), "dry_invite_results": dict(results),
            "completed_dry_flows_per_minute": round(results["success"] * 60 / elapsed, 3),
            "function_wall_seconds_inclusive": {key: round(value, 2) for key, value in durations.items()},
            "tracking_files_unchanged": hashes_before == hashes_after,
        }
        output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print("BENCHMARK SUMMARY:", json.dumps(summary, indent=2), flush=True)
        print(f"Benchmark JSON: {output}", flush=True)


if __name__ == "__main__":
    run_with_logging(__file__, main)
