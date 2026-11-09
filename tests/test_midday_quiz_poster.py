import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "daily_poster"))
import midday_quiz_reddit_poster as midday


QUIZ = {"id": "12345", "title": "World Geography", "description": "Explore places around the world."}


class MiddayQuizPosterTests(unittest.TestCase):
    def test_daily_title_rotation_keeps_quiz_title_and_date(self):
        self.assertEqual(len(midday.TITLE_TEMPLATES), 72)
        self.assertEqual(len(set(midday.TITLE_TEMPLATES)), 72)
        start = date(2026, 11, 9)
        titles = []
        for offset in range(72):
            day = start + timedelta(days=offset)
            title = midday.build_reddit_title(QUIZ, day)
            self.assertIn(QUIZ["title"], title)
            self.assertIn(day.strftime("%d/%m"), title)
            titles.append(title.replace(day.strftime("%d/%m"), "DATE"))
        self.assertEqual(len(set(titles)), 72)

    def test_description_rotation_preserves_quiz_metadata(self):
        self.assertEqual(len(set(midday.BODY_INTROS)), 64)
        self.assertEqual(len(set(midday.BODY_FOOTERS)), 13)
        start = date(2026, 11, 9)
        bodies = []
        with patch.object(midday, "fetch_daily_quiz_item", return_value=QUIZ):
            for offset in range(832):
                day = start + timedelta(days=offset)
                payload = midday.build_post_payload(day)
                self.assertEqual(payload["description"], QUIZ["description"])
                self.assertEqual(payload["quiz_title"], QUIZ["title"])
                self.assertEqual(payload["date_key"], day.isoformat())
                self.assertEqual(payload["url"], "https://www.pineapplecactus.com/quiz/world-geography-12345")
                self.assertIn("\n\n" + QUIZ["description"] + "\n\n", payload["body"])
                bodies.append(payload["body"])
            self.assertEqual(midday.build_post_payload(start)["body"], bodies[0])
        self.assertEqual(len(set(bodies)), 832)
        self.assertEqual({body.split("\n\n")[0] for body in bodies[:64]}, set(midday.BODY_INTROS))

    def test_missing_quiz_description_still_produces_readable_body(self):
        with patch.object(midday, "fetch_daily_quiz_item", return_value={**QUIZ, "description": ""}):
            payload = midday.build_post_payload(date(2026, 11, 9))
        intro, footer = payload["body"].split("\n\n")
        self.assertIn(intro, midday.BODY_INTROS)
        self.assertIn(footer, midday.BODY_FOOTERS)

    def test_long_quiz_titles_remain_within_reddit_limit(self):
        title = midday.build_reddit_title({**QUIZ, "title": "Geography " * 100}, date(2026, 11, 9))
        self.assertLessEqual(len(title), midday.MAX_REDDIT_TITLE_LENGTH)


if __name__ == "__main__":
    unittest.main()
