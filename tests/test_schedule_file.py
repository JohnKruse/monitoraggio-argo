"""Unit tests verifying the integrity and accuracy of the class schedule CSV."""

import csv
import unittest
from pathlib import Path


class ScheduleFileTests(unittest.TestCase):
    def setUp(self):
        self.schedule_path = Path(__file__).resolve().parent.parent / "data" / "schedule.csv"

    def test_schedule_file_exists(self):
        if not self.schedule_path.exists():
            self.skipTest("Local data/schedule.csv is not present (ignored by git)")
        self.assertTrue(self.schedule_path.exists(), f"Schedule file {self.schedule_path} must exist")

    def test_schedule_structure_and_periods(self):
        if not self.schedule_path.exists():
            self.skipTest("Local data/schedule.csv is not present (ignored by git)")
        with self.schedule_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))

        self.assertGreaterEqual(len(rows), 7, "Must contain header and at least 6 period rows")
        headers = rows[0]
        self.assertIn(headers[0], ["Hour", "Ora"])
        self.assertEqual(len(headers), 6, "Must have 6 columns (Hour + 5 weekdays)")

        for idx in range(1, 7):
            row = rows[idx]
            self.assertEqual(len(row), 6, f"Row {idx} must have 6 entries")
            self.assertTrue(row[0].startswith(f"{idx} - "), f"Row {idx} must start with '{idx} - '")
            for col_idx in range(1, 6):
                self.assertTrue(bool(row[col_idx].strip()), f"Row {idx}, Col {col_idx} should not be empty")

    def test_schedule_4cs_teachers_and_rooms(self):
        if not self.schedule_path.exists():
            self.skipTest("Local data/schedule.csv is not present (ignored by git)")
        with self.schedule_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))

        all_text = " ".join(" ".join(row[1:]) for row in rows[1:7])

        # New teachers and rooms for 4Cs
        self.assertIn("Carnevale", all_text)
        self.assertIn("TF21", all_text)
        self.assertIn("LagrangeF15", all_text)
        self.assertIn("KantF57", all_text)
        self.assertIn("BooleF79", all_text)
        self.assertIn("RamaF82", all_text)

        # Obsolete teacher/rooms from 3Cs must not appear
        self.assertNotIn("Tartaglia", all_text)
        self.assertNotIn("TF30", all_text)


if __name__ == "__main__":
    unittest.main()
