import unittest
from unittest.mock import Mock, patch

from daily_inviter import reddit_inviter as bot


class FeedNavigationTests(unittest.TestCase):
    def device(self, nodes):
        device = Mock()
        device.dump_hierarchy.return_value = f"<hierarchy>{nodes}</hierarchy>"
        device.window_size.return_value = (720, 1480)
        return device

    def test_game_search_in_subreddit_is_feed_even_without_post_descriptions(self):
        device = self.device('''
            <node resource-id="com.reddit.frontpage:id/feed_lazy_column" />
            <node resource-id="subreddit_screen_surface" />
            <node class="android.widget.EditText" content-desc="Search clues" />
        ''')
        self.assertEqual(bot.current_screen(device), "feed")

    def test_actual_invite_search_still_detected(self):
        device = self.device('<node class="android.widget.EditText" content-desc="Search communities" />')
        self.assertEqual(bot.current_screen(device), "invite")

    def test_native_invite_sheet_is_detected_without_search(self):
        device = self.device('<node resource-id="com.reddit.frontpage:id/btn_invite" /><node resource-id="com.reddit.frontpage:id/txt_choose_community" />')
        self.assertEqual(bot.current_screen(device), "invite")

    def test_native_community_tile_is_selected_without_typing(self):
        device = Mock()
        tile = Mock()
        tile.exists.return_value = True
        device.return_value = tile
        with patch.object(bot, "safe_click") as click, patch.object(bot, "pause"), patch.object(bot, "populate_invite_message"):
            self.assertTrue(bot.select_invite_community(device, "example_user"))
        click.assert_called_once_with(device, tile)
        tile.set_text.assert_not_called()

    def test_native_sheet_without_target_does_not_type_in_message(self):
        tile, chooser = Mock(), Mock()
        tile.exists.return_value = False
        chooser.exists.return_value = True
        device = Mock(side_effect=[tile, chooser])
        self.assertFalse(bot.select_invite_community(device, "example_user"))
        self.assertEqual(device.call_count, 2)

    def test_comments_have_priority_over_feed_markers(self):
        device = self.device('<node resource-id="feed_lazy_column" /><node resource-id="subreddit_screen_surface" /><node resource-id="com.reddit.frontpage:id/action_sort" />')
        self.assertEqual(bot.current_screen(device), "comments")

    def test_cards_ignore_ads_and_bare_comment_icons_and_prefer_comment_button(self):
        device = self.device('''
            <node content-desc="Comment" bounds="[20,200][60,240]" />
            <node content-desc="From advertiser, Promoted post, 30 comments" bounds="[0,300][720,500]" />
            <node content-desc="From game-app, puzzle, 65 comments" bounds="[0,600][720,1000]" />
            <node resource-id="com.reddit.frontpage:id/actionBar_comment_button" bounds="[240,900][380,980]" />
        ''')
        self.assertEqual(bot.visible_post_cards(device), [("From game-app, puzzle, 65 comments", "[240,900][380,980]")])

    def test_tap_stays_inside_short_comment_button(self):
        self.assertEqual(bot.header_tap_point("[240,900][380,940]"), (310, 920))

    def test_unlabelled_card_footer_uses_comment_group_instead_of_game(self):
        device = self.device('''
            <node content-desc="From puzzle author, 23 comments" bounds="[0,188][720,1014]" />
            <node resource-id="post_unit" bounds="[0,188][720,1014]" />
            <node resource-id="post_dev_platform_custom_post" bounds="[30,188][690,878]" />
            <node resource-id="post_footer" bounds="[0,924][720,1014]">
                <node bounds="[30,939][202,999]" />
                <node bounds="[213,939][325,999]" />
                <node bounds="[527,939][603,999]" />
                <node bounds="[614,939][690,999]" />
            </node>
        ''')
        self.assertEqual(bot.visible_post_cards(device), [("From puzzle author, 23 comments", "[213,939][325,999]")])

    def test_feed_swipe_stays_outside_game(self):
        device = self.device("")
        with patch.object(bot, "run_shell_input") as shell:
            bot.scroll_subreddit_feed(device)
        self.assertEqual(shell.call_args.args[1], "input swipe 10 1154 10 325 400")

    def test_failed_thread_tap_is_not_reported_as_open(self):
        device = self.device("")
        with patch.multiple(bot,
                            MAX_FEED_SCROLLS=1,
                            ensure_reddit_feed_context=Mock(),
                            visible_post_cards=Mock(return_value=[("Example, 20 comments", "[0,400][720,700]")]),
                            safe_tap_point=Mock(), pause=Mock(), dismiss_nsfw_modal=Mock(),
                            wait_for_comments=Mock(return_value=False), scroll_subreddit_feed=Mock()):
            self.assertEqual(bot.find_qualifying_post(device, float("inf"), set(), "syllo"), (False, None))
            bot.scroll_subreddit_feed.assert_called_once_with(device)

    def test_low_card_is_scrolled_once_before_rescanning(self):
        device = self.device("")
        with patch.multiple(bot,
                            MAX_FEED_SCROLLS=1,
                            ensure_reddit_feed_context=Mock(),
                            visible_post_cards=Mock(return_value=[("Example, 20 comments", "[0,1200][720,1450]")]),
                            pause=Mock(), scroll_subreddit_feed=Mock()):
            bot.find_qualifying_post(device, float("inf"), set(), "syllo")
            bot.scroll_subreddit_feed.assert_called_once_with(device, scale=0.25)

    def test_real_run_stops_at_requested_invitation_limit(self):
        device = self.device("")
        with patch.multiple(bot,
                            get_visible_usernames=Mock(return_value=[((100, 500), "example_user")]),
                            safe_tap_point=Mock(), pause=Mock(), dismiss_nsfw_modal=Mock(),
                            _on_comment_screen=Mock(return_value=False),
                            invite_user=Mock(return_value="success"), navigate_back_to_comments=Mock(),
                            record_invited_user=Mock(), update_daily_tally=Mock()):
            result = bot.run_invite_loop(device, float("inf"), set(), "syllo", max_invites=1)
            self.assertEqual(result, ("invite_limit", 1))
            bot.invite_user.assert_called_once_with(device, "example_user", dry_run=False)
            bot.record_invited_user.assert_called_once_with("example_user")
            bot.update_daily_tally.assert_called_once_with(processed_delta=1, successful_delta=1)


if __name__ == "__main__":
    unittest.main()
