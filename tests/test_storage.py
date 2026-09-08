import tempfile
import unittest
from pathlib import Path

from storage import ArgoStore


class StorageTests(unittest.TestCase):
    def test_bacheca_is_new_only_until_saved_again(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArgoStore(Path(directory) / "argo.db")
            profile_id = store.save_profile({"scheda": {"pk": "student-1"}}, "Student", 0)
            notice = {"pk": "notice-1", "data": "2026-09-08", "messaggio": "Hello", "listaAllegati": []}
            ids = store.save_collections(profile_id, [], [], [notice])
            self.assertEqual(1, len(ids))
            self.assertEqual(1, len(store.save_collections(profile_id, [], [], [notice])))
            store.mark_bacheca_notified(ids)
            self.assertEqual(0, len(store.save_collections(profile_id, [], [], [notice])))

    def test_attachment_metadata_is_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArgoStore(Path(directory) / "argo.db")
            profile_id = store.save_profile({}, "Student", 0)
            notice = {"pk": "n", "messaggio": "Notice", "listaAllegati": [{"pk": "a", "nomeFile": "x.pdf"}]}
            ids = store.save_collections(profile_id, [], [], [notice])
            self.assertEqual(1, len(store.pending_attachments(ids)))

    def test_bacheca_summary_is_saved_for_one_language(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArgoStore(Path(directory) / "argo.db")
            profile_id = store.save_profile({}, "Student", 0)
            notice = {"pk": "n", "messaggio": "Notice", "listaAllegati": []}
            notice_id = store.save_collections(profile_id, [], [], [notice])[0]
            self.assertTrue(store.bacheca_needs_summary(notice_id, "it"))
            store.update_bacheca_summary(
                notice_id, title="Titolo", summary="Riassunto", language="it", model="test"
            )
            self.assertFalse(store.bacheca_needs_summary(notice_id, "it"))
            self.assertTrue(store.bacheca_needs_summary(notice_id, "en"))
            self.assertEqual("Riassunto", store.bacheca_rows()[0]["summary"])


if __name__ == "__main__":
    unittest.main()
