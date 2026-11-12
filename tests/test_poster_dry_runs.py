import re
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "daily_poster"))
import daily_challenge_reddit_poster as challenge
import midday_quiz_reddit_poster as midday
import reddit_account_switcher as accounts


class PosterDryRunTests(unittest.TestCase):
    def test_both_dry_runs_populate_but_never_submit_or_check_success_history(self):
        payload = {"title": "Test quiz", "url": "https://example.com/quiz", "body": "Test body"}
        keys = ("DRY_RUN", "TARGET_SUBREDDIT", "TARGET_URL", "TARGET_FLAIR", "TARGET_REDDIT_ACCOUNT",
                "POST_HISTORY_FILE", "TITLE_TEMPLATES", "BODY_INTROS", "BODY_FOOTER")
        for module in (challenge, midday):
            with self.subTest(module=module.__name__):
                originals = {key: getattr(module.base, key) for key in keys}
                device = Mock()
                device.device_info = {"version": "14"}
                try:
                    with patch.object(module, "build_post_payload", return_value=payload), patch.multiple(
                        module.base, adb_connected_devices=Mock(return_value=["phone"]),
                        u2=Mock(connect=Mock(return_value=device)), go_to_home_screen=Mock(),
                        ensure_target_account=Mock(), open_submit_screen=Mock(), populate_post_form=Mock(),
                        close_reddit_app=Mock(), save_ui_diagnostics=Mock(), record_post_attempt=Mock(), successful_post_exists=Mock(return_value=True),
                        tap_post_button=Mock(), wait_for_submission_result=Mock(),
                    ):
                        module.main(dry_run=True)
                        module.base.populate_post_form.assert_called_once_with(device, payload)
                        module.base.tap_post_button.assert_not_called()
                        module.base.wait_for_submission_result.assert_not_called()
                        module.base.successful_post_exists.assert_not_called()
                        self.assertEqual(module.base.record_post_attempt.call_args.args[1], "dry_run")
                finally:
                    for key, value in originals.items():
                        setattr(module.base, key, value)

    def test_both_cli_flags_enable_dry_run(self):
        for module in (challenge, midday):
            with self.subTest(module=module.__name__), patch.object(sys, "argv", ["poster.py", "--dry-run"]), patch.object(module, "main") as main:
                module.cli()
                main.assert_called_once_with(dry_run=True)

    def test_account_fallback_matches_exact_names_with_or_without_u_prefix(self):
        device = Mock()
        missing_rows = Mock(count=0)
        target = Mock()
        target.exists.return_value = True
        device.side_effect = [missing_rows, target]
        click = Mock()
        self.assertTrue(accounts.select_account_row(device, "u/PineappleCactusQuiz", click))
        pattern = device.call_args.kwargs["textMatches"]
        for label in ("PineappleCactusQuiz", "u/PineappleCactusQuiz", "pineapplecactusquiz"):
            self.assertIsNotNone(re.fullmatch(pattern, label))
        self.assertIsNone(re.fullmatch(pattern, "OtherPineappleCactusQuiz"))
        click.assert_called_once_with(device, target)

    def test_swipe_lock_is_dismissed_before_account_navigation(self):
        device = Mock()
        device.dump_hierarchy.side_effect = [
            '<hierarchy><node resource-id="com.android.systemui:id/keyguard_indication_text" /></hierarchy>',
            '<hierarchy><node resource-id="subreddit_toolbar_title" /></hierarchy>',
        ]
        with patch.object(accounts.time, "sleep"):
            accounts.ensure_device_unlocked(device, Mock())
        device.shell.assert_called_once_with("wm dismiss-keyguard")

    def test_secure_lock_requires_manual_unlock(self):
        device = Mock()
        device.dump_hierarchy.return_value = '<hierarchy><node resource-id="com.android.systemui:id/keyguard_indication_text" /></hierarchy>'
        with patch.object(accounts.time, "sleep"), self.assertRaisesRegex(RuntimeError, "Unlock it manually"):
            accounts.ensure_device_unlocked(device, Mock())

    def test_header_recovery_only_presses_back_when_keyboard_is_visible(self):
        for keyboard_visible in (False, True):
            with self.subTest(keyboard_visible=keyboard_visible):
                device = Mock()
                package = "com.samsung.android.honeyboard" if keyboard_visible else "com.reddit.frontpage"
                device.dump_hierarchy.return_value = f'<hierarchy><node package="{package}" /></hierarchy>'
                device.window_size.return_value = (720, 1480)
                with patch.object(challenge.base, "pause"):
                    challenge.base.reveal_composer_header(device)
                if keyboard_visible:
                    device.press.assert_called_once_with("back")
                else:
                    device.press.assert_not_called()

    def test_missing_required_flair_stops_form_population(self):
        base = challenge.base
        title, url, body = Mock(), Mock(), Mock()
        with patch.multiple(base, ensure_link_post_mode=Mock(), reveal_optional_body_field=Mock(),
                            collect_edit_fields=Mock(return_value=[{}, {}, {}]),
                            best_matching_field=Mock(side_effect=[title, url, body]),
                            element_center=Mock(side_effect=[(10, 10), (20, 20)]),
                            fill_text_field=Mock(), ensure_post_flair=Mock(return_value=False)):
            with self.assertRaisesRegex(RuntimeError, "required post flair"):
                base.populate_post_form(Mock(), {"title": "Test", "url": "https://example.com", "body": "Body"})


if __name__ == "__main__":
    unittest.main()
