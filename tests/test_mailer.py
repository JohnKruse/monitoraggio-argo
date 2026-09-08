import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from mailer import render_bacheca_email, render_daily_email


class MailerTests(unittest.TestCase):
    def test_daily_escapes_api_text(self):
        html = render_daily_email("Student", [{"dataConsegna": "2026-09-09", "materia": "Math", "compito": "x < y"}], [], [], None, date(2026, 9, 8))
        self.assertIn("x &lt; y", html)
        self.assertNotIn("x < y", html)

    def test_bacheca_prefers_drive_link(self):
        row = {
            "id": "n", "message": "Original notice", "summary_title": "Translated title",
            "summary": "Translated summary", "attachments": [{"filename": "a.pdf", "drive_url": "https://drive.test/a"}],
        }
        html = render_bacheca_email([row], {"n"}, date(2026, 9, 8), "en")
        self.assertIn("https://drive.test/a", html)
        self.assertIn("target=\"_blank\"", html)
        self.assertIn("Translated title", html)
        self.assertIn("Translated summary", html)
        self.assertIn("Original subject", html)
        self.assertIn("NEW BACHECA", html)

    def test_daily_keeps_2024_table_and_highlights_next_day(self):
        with TemporaryDirectory() as directory:
            schedule = Path(directory) / "schedule.csv"
            schedule.write_text("Hour,Monday,Tuesday\n1,Math,History\n", encoding="utf-8")
            html = render_daily_email(
                "Student", [], [], [], schedule, date(2026, 9, 7), "en"
            )
        self.assertIn("No assignments", html)
        self.assertIn("Class Schedule - Tuesday, September 8, 2026", html)
        self.assertIn("font-size:14px", html)
        self.assertGreaterEqual(html.count("background-color:whitesmoke"), 4)


if __name__ == "__main__":
    unittest.main()
