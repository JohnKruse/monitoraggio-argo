import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from mailer import is_important_entry, render_bacheca_email, render_daily_email


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

    def test_importance_criteria_and_testo_exclusion(self):
        # Negative cases: must NOT match
        self.assertFalse(is_important_entry("Portare il libro di testo"))
        self.assertFalse(is_important_entry("Leggere il testo a pagina 45"))
        self.assertFalse(is_important_entry("Nel contesto storico e letterario"))
        self.assertFalse(is_important_entry("Compiti per casa: esercizi 1, 2, 3"))
        self.assertFalse(is_important_entry("Studiare capitolo 4"))

        # Positive cases: must match
        self.assertTrue(is_important_entry("Reading test B2"))
        self.assertTrue(is_important_entry("English grammar tests"))
        self.assertTrue(is_important_entry("Verifica di fisica"))
        self.assertTrue(is_important_entry("Verifiche scritte"))
        self.assertTrue(is_important_entry("Interrogazione di storia"))
        self.assertTrue(is_important_entry("Interrogati a sorpresa"))
        self.assertTrue(is_important_entry("Compito in classe di matematica"))
        self.assertTrue(is_important_entry("Prova scritta di italiano"))
        self.assertTrue(is_important_entry("Simulazione prima prova"))
        self.assertTrue(is_important_entry("Recupero debito formativo"))
        self.assertTrue(is_important_entry("Test INVALSI"))
        self.assertTrue(is_important_entry("Nota per William Kruse"))

    def test_daily_table_columns_source_and_highlighting(self):
        homework = [
            {
                "dataConsegna": "2026-09-18",
                "materia": "ITALIANO",
                "compito": "Portare il libro di testo",
                "dataAssegnazione": "2026-09-15",
            },
            {
                "dataConsegna": "2026-09-19",
                "materia": "MATEMATICA",
                "compito": "Verifica di trigonometria",
                "dataAssegnazione": "2026-09-16",
            },
        ]
        reminders = [
            {
                "datGiorno": "2026-09-20",
                "materia": "INGLESE",
                "desAnnotazioni": "Listening B2",
            }
        ]
        html = render_daily_email("Student", homework, reminders, [], None, date(2026, 9, 14), "en")

        # 1. Verify 3-column headers and absence of 4th "Important" column header
        self.assertIn(">Date<", html)
        self.assertIn(">Assignment<", html)
        self.assertIn(">Subject<", html)
        self.assertNotIn(">Important<", html)
        self.assertNotIn("Upcoming school work", html)

        # 2. Verify source parentheses
        self.assertIn("Portare il libro di testo (Asg. 15/09)", html)
        self.assertIn("Verifica di trigonometria (Asg. 16/09)", html)
        self.assertIn("Listening B2 (Promemoria)", html)

        # 3. Verify print-safe row accent styling and inline badge:
        # "Portare il libro di testo" is not important: no amber row highlight or dark border
        # "Verifica di trigonometria" is important: amber fill, 5px dark left border, 2px top/bottom box, and badge
        self.assertIn("background-color:#FFF8E1;", html)
        self.assertIn("border-left:5px solid #222;", html)
        self.assertIn("border-top:2px solid #222;", html)
        self.assertIn(">IMPORTANT</span>", html)

    def test_daily_excludes_same_day_assignments_and_promemoria(self):
        today = date(2026, 9, 28)
        homework = [
            {"dataConsegna": "2026-09-28", "materia": "MATEMATICA", "compito": "Due today"},
            {"dataConsegna": "2026-09-29", "materia": "ARTE", "compito": "Due tomorrow"},
        ]
        reminders = [
            {"datGiorno": "2026-09-28", "materia": "Reminder", "desAnnotazioni": "Interrogazione today"},
            {"datGiorno": "2026-09-30", "materia": "Reminder", "desAnnotazioni": "Future test"},
        ]
        manual = [
            {"Date": "2026-09-28", "Assignment": "Manual event today", "Subject": "School"},
            {"Date": "2026-09-29", "Assignment": "Manual event tomorrow", "Subject": "School"},
        ]
        html = render_daily_email("Student", homework, reminders, manual, None, today, "en")
        self.assertNotIn("Due today", html)
        self.assertNotIn("Interrogazione today", html)
        self.assertNotIn("Manual event today", html)
        self.assertIn("Due tomorrow", html)
        self.assertIn("Future test", html)
        self.assertIn("Manual event tomorrow", html)


if __name__ == "__main__":
    unittest.main()

