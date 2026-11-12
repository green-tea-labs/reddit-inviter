# Debugging subreddit navigation

## Automatic logs for every script

Run scripts normally; logging is always enabled. Each process prints its log path and saves a separate UTF-8 text file under `logs/<script-name>/`, for example `logs/reddit_inviter/2026-11-08_13-30-00_123456_1234.txt`. Paths are relative to the repository, regardless of the task runner's working directory.

Logs include a timestamp and output channel for every line, the script/arguments, Python/platform and dependency versions, console output, stderr, library DEBUG messages, uncaught tracebacks (including dependency import errors), final exit status, and runtime. Console output remains visible. File writes are flushed immediately so the last recorded action survives an abrupt termination; a forcibly killed process may have no final status footer.

Logging covers the inviter, all three posters, the account switcher, UI discovery, feed diagnostics, and LAN status server. Shared imports stay in the calling script's log. HTTP requests to the status server are recorded at DEBUG level. There is no automatic rotation or deletion, and `logs/` is excluded from Git.

When a script fails, start with the newest text file in its folder and look at the final actions and traceback. Copy the updated scripts and `console_output.py` to the downstairs PC so it gets the same logging.

## Poster dry runs

Run the two posters sequentially against the connected phone:

```powershell
.\.venv\Scripts\python.exe -u daily_poster/daily_challenge_reddit_poster.py --dry-run
.\.venv\Scripts\python.exe -u daily_poster/midday_quiz_reddit_poster.py --dry-run
```

These switch to the posting account and populate the form, including its flair, but never tap Post. They can run even if a successful post is already recorded today. Dry runs are recorded as `dry_run`, so they do not count as a successful daily post. Screenshots and UI XML are saved beside the run log before Reddit closes; failures also capture that screen.

The account switcher dismisses simple swipe locks and accepts account labels with or without `u/`. A PIN/password lock still needs manual unlocking. The composer hides a visible keyboard and scrolls toward the header before choosing flair. Missing required flair stops the run before posting.

## Navigation tests

Run commands from the repository root, with the phone unlocked and USB debugging authorized.

Test thread discovery without opening profiles or sending invitations:

```powershell
.\.venv\Scripts\python.exe -u debug_reddit_feed.py --subreddit syllo --find --timeout 120
```

This prints the detected screen, Reddit's post elements, comment counts, and the result. Success ends with `Verified: thread comments are open` and `Screen: comments`. Add `--feed-view Card` or `--feed-view Compact` to reproduce a particular layout. Without `--subreddit` or `--find`, the tool only inspects the current screen; `--scroll` also tests a feed-edge swipe.

For a bounded invitation-flow test that skips Send and does not update invitation tracking files:

```powershell
.\.venv\Scripts\python.exe -u daily_inviter/reddit_inviter.py --dry-run --subreddit syllo --max-runtime-seconds 180
```

Supported source communities are `dailyguess`, `dailymix`, `HotAndCold`, `syllo`, and `QuizPlanetGame`. Runtime limits are checked between operations; an in-progress UI operation can finish after the deadline.

To deliberately test one real invitation:

```powershell
.\.venv\Scripts\python.exe -u daily_inviter/reddit_inviter.py --subreddit dailyguess --max-runtime-seconds 240 --max-invites 1
```

The limit counts invitations recorded by the bot; Reddit may not display a success confirmation after Send.

For the downstairs PC, copy/pull the updated `daily_inviter/reddit_inviter.py` and `debug_reddit_feed.py`, then run the navigation test there. To capture its output:

```powershell
.\.venv\Scripts\python.exe -u debug_reddit_feed.py --subreddit syllo --find --timeout 120 *> feed-debug.log
```

The fixes recognize a subreddit before post descriptions load, swipe along the left margin outside embedded games, actually select the configured feed sort, keep taps clear of the bottom navigation, and require evidence that the thread opened before processing comments. Promoted cards are skipped.

Card-view puzzles can expose an unlabeled native footer. The bot uses the comment group's bounds instead of tapping inside the puzzle. The native invite sheet is supported directly: select the PineappleCactus tile, leave the default invitation message when no custom message is configured, and tap the explicit Send invitation button. The message composer is excluded from community-search detection.

Focused regression checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
