import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "daily_poster"))
import daily_challenge_reddit_poster as challenge


class DailyChallengePosterTests(unittest.TestCase):
    def setUp(self):
        # The posters share a configurable base; leave its settings intact.
        keys = ("DRY_RUN", "TARGET_SUBREDDIT", "TARGET_URL", "TARGET_FLAIR",
                "TARGET_REDDIT_ACCOUNT", "POST_HISTORY_FILE", "TITLE_TEMPLATES",
                "BODY_INTROS", "BODY_FOOTER")
        for key in keys:
            original = getattr(challenge.base, key)
            self.addCleanup(setattr, challenge.base, key, original)

    def test_dated_url_title_and_history_key_stay_consistent(self):
        for day in (date(2026, 11, 9), date(2026, 11, 10), date(2027, 1, 1), date(2028, 2, 29)):
            with self.subTest(day=day):
                payload = challenge.build_post_payload(day)
                self.assertEqual(payload["url"], f"https://www.pineapplecactus.com/daily-challenges/{day.isoformat()}")
                self.assertEqual(payload["date_key"], day.isoformat())
                self.assertIn(day.strftime("%d/%m"), payload["title"])

    def test_date_is_resolved_when_payload_is_built(self):
        with patch.object(challenge, "date") as clock:
            clock.today.return_value = date(2026, 11, 9)
            first = challenge.build_post_payload()
            clock.today.return_value = date(2026, 11, 10)
            second = challenge.build_post_payload()
        self.assertTrue(first["url"].endswith("/2026-11-09"))
        self.assertTrue(second["url"].endswith("/2026-11-10"))

    def test_title_pool_is_unique_and_rotates_without_early_repeats(self):
        templates = challenge.TITLE_TEMPLATES
        self.assertGreaterEqual(len(templates), 70)
        self.assertEqual(len(templates), len(set(templates)))
        start = date(2026, 11, 9)
        titles = []
        for offset in range(len(templates)):
            day = start + timedelta(days=offset)
            title = challenge.build_post_payload(day)["title"]
            titles.append(title.replace(day.strftime("%d/%m"), "DATE"))
        self.assertEqual(len(titles), len(set(titles)))

    def test_descriptions_use_every_intro_and_footer_before_pairing_repeats(self):
        self.assertEqual(len(challenge.BODY_INTROS), 64)
        self.assertEqual(len(set(challenge.BODY_INTROS)), 64)
        self.assertEqual(len(set(challenge.BODY_FOOTERS)), 13)
        start = date(2026, 11, 9)
        bodies = [challenge.build_post_payload(start + timedelta(days=offset))["body"]
                  for offset in range(64 * 13)]
        self.assertEqual(len(set(bodies)), 832)
        intros = {body.split("\n\n")[0] for body in bodies[:64]}
        self.assertEqual(intros, set(challenge.BODY_INTROS))
        self.assertTrue(all(body.split("\n\n")[-1] in challenge.BODY_FOOTERS for body in bodies))
        self.assertEqual(challenge.build_post_payload(start)["body"], bodies[0])


if __name__ == "__main__":
    unittest.main()
