import unittest
from datetime import date

from mailer import render_bacheca_email, render_daily_email


class MailerTests(unittest.TestCase):
    def test_daily_escapes_api_text(self):
        html = render_daily_email("Student", [{"dataConsegna": "2026-09-09", "materia": "Math", "compito": "x < y"}], [], [], None, date(2026, 9, 8))
        self.assertIn("x &lt; y", html)
        self.assertNotIn("x < y", html)

    def test_bacheca_prefers_drive_link(self):
        row = {"id": "n", "message": "Notice", "attachments": [{"filename": "a.pdf", "drive_url": "https://drive.test/a"}]}
        html = render_bacheca_email([row], {"n"}, date(2026, 9, 8))
        self.assertIn("https://drive.test/a", html)
        self.assertIn("NUOVO", html)


if __name__ == "__main__":
    unittest.main()
