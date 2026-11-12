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

The fixed source order is `syllo`, `QuizPlanetGame`, `FitTheWord`, `ColorPuzzleGame`, `dailyguess`, `wordle`, `dailymix`, `NYTConnections`, `HotAndCold`, `WordleSpinoffs`, then `LETTERSET`. Runtime limits are checked between operations; an in-progress UI operation can finish after the deadline.

Without `--subreddit`, the inviter follows that order, starting each new server-local date with **syllo → QuizPlanetGame → FitTheWord → ColorPuzzleGame**. Runs within the same day resume from `daily_inviter/source_progress.json`; yesterday's progress and older undated progress are ignored. Overnight runs save against their original date so the next run still starts the new day's priorities. Each community gets up to two threads or eight minutes per turn, and the bot moves on after six scans with no new candidates. Productive cycles continue until the overall runtime limit; exhausted thread keys are retained within the run. Dry runs leave the rotation file untouched. An explicit `--subreddit` isolates that source for testing.

Threads with at least three comments are eligible. Reply authors are included, automated accounts are skipped, and unavailable invite actions are remembered only for the current session. The no-warning popup check takes one UI snapshot instead of waiting on six selectors. Existing send pacing and the consecutive-error stop remain in place.

The added communities cover related word/puzzle interests: [Wordle](https://www.reddit.com/r/wordle/), [NYTConnections](https://www.reddit.com/r/NYTConnections/), and [WordleSpinoffs](https://www.reddit.com/r/WordleSpinoffs/).

## Inviter benchmark

```powershell
.\.venv\Scripts\python.exe -u benchmark_inviter.py --label before --subreddit dailyguess --seconds 180
# After updating the inviter, repeat with the same starting account and phone:
.\.venv\Scripts\python.exe -u benchmark_inviter.py --label after --subreddit dailyguess --seconds 180
```

The benchmark always uses dry-run mode and refuses real sends. It saves JSON results and a copy of the tested inviter source under `logs/benchmarks/`. Results include unique visible/new users, completed dry invitation flows, function timings, and a check that invitation/tally files did not change. Function times are inclusive, so nested timings must not be added together. A UI flow in progress can finish after the time budget. Live Reddit content and network latency vary; a short dry benchmark measures navigation/discovery, not confirmed sends per day or the full community-rotation schedule.

On 12 November 2026, matching 180-second-budget tests in `dailyguess`, starting from the posting account with the same 49,115-user invite history, produced:

| Metric | Before | After |
| --- | ---: | ---: |
| Actual elapsed seconds (including finishing an active UI flow) | 183.90 | 191.81 |
| Completed dry invite flows | 4 | 6 |
| Completed dry flows per minute | 1.305 | 1.877 |
| Unique not-previously-invited candidates observed | 6 | 6 |
| Threads opened | 1 | 2 |
| Popup-check wall time (seconds) | 29.53 | 4.79 |

Both tests left invitation/tally files unchanged. This is approximately 44% higher dry-flow throughput in a small live-content sample; it does not establish a daily sending capacity. The JSON files are `before_2026-11-12_18-26-38_305804.json` and `after_2026-11-12_18-33-07_802173.json` in `logs/benchmarks/`.

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
