import unittest

from argo_exporter import extract_collections, safe_filename, short_id


class ExportTests(unittest.TestCase):
    def test_extracts_only_future_homework_and_promemoria(self):
        dashboard = {
            "registro": [
                {
                    "materia": "Math",
                    "docente": "Teacher",
                    "datGiorno": "2026-09-01",
                    "compiti": [
                        {"compito": "Old", "dataConsegna": "2026-09-07"},
                        {"compito": "Today", "dataConsegna": "2026-09-08"},
                        {"compito": "Future", "dataConsegna": "2026-09-10"},
                    ],
                }
            ],
            "promemoria": [
                {"desAnnotazioni": "Old", "datGiorno": "2026-09-07"},
                {"desAnnotazioni": "Future", "datGiorno": "2026-09-09"},
            ],
            "bacheca": [{"pk": 1}, {"pk": 2}],
        }
        result = extract_collections(dashboard, "2026-09-08")
        self.assertEqual(["Today", "Future"], [x["compito"] for x in result.homework])
        self.assertEqual(["Future"], [x["desAnnotazioni"] for x in result.reminders])
        self.assertEqual(2, len(result.bacheca))

    def test_safe_filename_removes_path_components(self):
        self.assertEqual("report_.pdf", safe_filename("../../report?.pdf"))

    def test_short_id_is_stable_and_short(self):
        self.assertEqual(short_id("a very long Argo id"), short_id("a very long Argo id"))
        self.assertEqual(10, len(short_id("a very long Argo id")))


if __name__ == "__main__":
    unittest.main()
