import unittest

from drive_uploader import DriveUploader


class DriveUploaderTests(unittest.TestCase):
    def test_property_id_is_stable_and_within_drive_limit(self):
        argo_id = "x" * 300
        first = DriveUploader._property_id(argo_id)
        self.assertEqual(first, DriveUploader._property_id(argo_id))
        self.assertEqual(64, len(first.encode("utf-8")))


if __name__ == "__main__":
    unittest.main()
