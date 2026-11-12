import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from daily_inviter import reddit_inviter as bot


class InviterDiscoveryTests(unittest.TestCase):
    def test_daily_priority_order_and_new_communities(self):
        self.assertEqual(bot.SOURCE_SUBREDDITS[:4], ["syllo", "QuizPlanetGame", "FitTheWord", "ColorPuzzleGame"])
        self.assertIn("LETTERSET", bot.SOURCE_SUBREDDITS)
        self.assertEqual(len(bot.SOURCE_SUBREDDITS), len(set(bot.SOURCE_SUBREDDITS)))

    def test_new_day_resets_priority_but_same_day_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = Path(directory) / "progress.json"
            with patch.object(bot, "SOURCE_PROGRESS_FILE", progress):
                bot.remember_source_started("syllo", day="2026-11-12")
                self.assertEqual(bot.source_order(day="2026-11-12")[0], "QuizPlanetGame")
                self.assertEqual(bot.source_order(day="2026-11-13")[:4], bot.SOURCE_SUBREDDITS[:4])
                # Even if an overnight run saves again, its original date must
                # not move the new day's starting position past the priorities.
                bot.remember_source_started("wordle", day="2026-11-12")
                self.assertEqual(bot.source_order(day="2026-11-13")[0], "syllo")
                progress.write_text(json.dumps({"next_source": "wordle"}))
                self.assertEqual(bot.source_order(day="2026-11-13")[0], "syllo")

    def test_rotation_resumes_and_explicit_source_is_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = Path(directory) / "progress.json"
            with patch.object(bot, "SOURCE_PROGRESS_FILE", progress), patch.object(bot, "SOURCE_SUBREDDITS", ["a", "b", "c"]):
                self.assertEqual(bot.source_order(), ["a", "b", "c"])
                bot.remember_source_started("a")
                self.assertEqual(bot.source_order(), ["b", "c", "a"])
                self.assertEqual(bot.source_order("c"), ["c"])
                self.assertEqual(json.loads(progress.read_text())["next_source"], "b")
                progress.write_text("broken JSON")
                self.assertEqual(bot.source_order(), ["a", "b", "c"])

    def test_changed_vote_and_comment_counts_do_not_reopen_exhausted_post(self):
        self.assertEqual(
            bot.post_card_key("From player, Posted 2 hours ago, Puzzle #5, 3 upvotes, 12 comments"),
            bot.post_card_key("From player, Posted 2 hours ago, Puzzle #5, 50 upvotes, 99 comments"),
        )
        self.assertNotEqual(bot.post_card_key("From player, Puzzle #5"), bot.post_card_key("From player, Puzzle #6"))

    def test_reply_authors_are_candidates_but_automated_accounts_are_not(self):
        device = Mock()
        device.dump_hierarchy.return_value = '''<hierarchy>
            <node content-desc="Level 1 comment by game-app, This account is automated" bounds="[20,100][700,200]" />
            <node content-desc="Level 2 comment by new_player, 1 hour ago" bounds="[60,300][700,400]" />
            <node content-desc="Level 1 comment by AutoModerator, 1 hour ago" bounds="[20,500][700,600]" />
        </hierarchy>'''
        self.assertEqual(bot.get_visible_usernames(device), [((180, 350), "new_player")])
        device.assert_not_called()
        self.assertEqual(bot.current_screen(device), "comments")

    def test_no_warning_uses_one_dump_without_waiting_on_selectors(self):
        device = Mock()
        device.dump_hierarchy.return_value = '<hierarchy><node text="Ordinary profile" /></hierarchy>'
        self.assertFalse(bot.dismiss_nsfw_modal(device))
        device.dump_hierarchy.assert_called_once()
        device.assert_not_called()

    def test_warning_continue_button_is_still_dismissed(self):
        device = Mock()
        device.dump_hierarchy.return_value = '<hierarchy><node text="NSFW warning" /><node text="Continue" /></hierarchy>'
        device.return_value.exists.return_value = True
        with patch.object(bot, "safe_click") as click, patch.object(bot, "pause"):
            self.assertTrue(bot.dismiss_nsfw_modal(device))
        click.assert_called_once()

    def test_unavailable_invite_is_skipped_for_session_without_permanent_record(self):
        device = Mock()
        device.window_size.return_value = (720, 1480)
        visited = set()
        with patch.multiple(bot, MAX_COMMENT_SCROLLS=0,
                            get_visible_usernames=Mock(return_value=[((100, 400), "new_player")]),
                            safe_tap_point=Mock(), pause=Mock(), dismiss_nsfw_modal=Mock(),
                            _on_comment_screen=Mock(return_value=False),
                            invite_user=Mock(return_value="not_found"), navigate_back_to_comments=Mock(),
                            record_invited_user=Mock(), update_daily_tally=Mock()):
            bot.run_invite_loop(device, float("inf"), visited, "dailyguess")
            self.assertIn("new_player", visited)
            bot.record_invited_user.assert_not_called()

    def test_consecutive_error_stop_is_preserved(self):
        device = Mock()
        device.window_size.return_value = (720, 1480)
        rows = [((100, 400), f"player{i}") for i in range(bot.MAX_CONSECUTIVE_ERRORS + 1)]
        with patch.multiple(bot, get_visible_usernames=Mock(return_value=rows),
                            safe_tap_point=Mock(), pause=Mock(), dismiss_nsfw_modal=Mock(),
                            _on_comment_screen=Mock(return_value=False),
                            invite_user=Mock(return_value="error"), navigate_back_to_comments=Mock(),
                            record_invited_user=Mock(), update_daily_tally=Mock()):
            self.assertEqual(bot.run_invite_loop(device, float("inf"), set(), "dailyguess"), ("rate_limited", 0))
            self.assertEqual(bot.invite_user.call_count, bot.MAX_CONSECUTIVE_ERRORS)

    def main_patches(self, device):
        return patch.multiple(bot, source_order=Mock(return_value=["a", "b"]),
                              adb_connected_devices=Mock(return_value=["phone"]),
                              u2=Mock(connect=Mock(return_value=device)), load_invited_users=Mock(return_value=set()),
                              go_to_home_screen=Mock(), ensure_target_account=Mock(),
                              open_subreddit=Mock(), close_reddit_app=Mock(), remember_source_started=Mock(),
                              filter_by_new=Mock(), navigate_back_to_feed=Mock(), pause=Mock())

    def test_empty_sources_are_all_tried_and_dry_run_does_not_save_rotation(self):
        device = Mock(device_info={})
        with self.main_patches(device), patch.object(bot, "find_qualifying_post", return_value=(False, None)):
            bot.main(dry_run=True, max_runtime_seconds=60)
            self.assertEqual([call.args[1] for call in bot.open_subreddit.call_args_list], ["a", "b"])
            bot.remember_source_started.assert_not_called()

    def test_community_rotation_does_not_continue_after_rate_limit(self):
        device = Mock(device_info={})
        with self.main_patches(device), patch.object(bot, "find_qualifying_post", return_value=(True, "post")), patch.object(bot, "run_invite_loop", return_value=("rate_limited", 0)):
            bot.main(dry_run=False, max_runtime_seconds=60)
            self.assertEqual(bot.open_subreddit.call_count, 1)
            self.assertEqual(bot.remember_source_started.call_args.args, ("a",))
            self.assertRegex(bot.remember_source_started.call_args.kwargs["day"], r"^\d{4}-\d{2}-\d{2}$")

    def test_productive_cycles_continue_and_remember_exhausted_threads(self):
        device = Mock(device_info={})

        def process(d, deadline, visited, source, **kwargs):
            visited.add(f"player-{source}")
            return ("post_exhausted", 1)

        count = 0
        def run(*args, **kwargs):
            nonlocal count
            count += 1
            return process(*args, **kwargs) if count <= 2 else ("rate_limited", 0)

        with self.main_patches(device), patch.object(bot, "MAX_POSTS_PER_SOURCE", 1), patch.object(bot, "find_qualifying_post", return_value=(True, "post")) as find, patch.object(bot, "run_invite_loop", side_effect=run):
            bot.main(dry_run=True, max_runtime_seconds=60)
            self.assertEqual([call.args[1] for call in bot.open_subreddit.call_args_list], ["a", "b", "a"])
            self.assertIn("post", find.call_args_list[2].args[2])


if __name__ == "__main__":
    unittest.main()
